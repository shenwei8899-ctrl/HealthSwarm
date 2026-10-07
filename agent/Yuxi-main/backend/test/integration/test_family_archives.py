"""家庭档案的 HTTP 与真实 PostgreSQL 权限、版本及记录验证。"""

import asyncio
import os
import socket
import uuid
from datetime import datetime, timedelta, UTC

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
import uvicorn
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from server.routers import router
from server.utils.auth_middleware import get_db
from yuxi.storage.postgres.models_business import Base, Department, FamilyMember, User
from yuxi.utils.auth_utils import AuthUtils

pytestmark = pytest.mark.integration
TEST_TOKENS = {}


@pytest.fixture(scope="session", autouse=True)
def cleanup_test_sandboxes():
    """此文件仅创建临时数据库 schema，不创建或清理 Agent 沙盒。"""
    yield


@pytest_asyncio.fixture
async def family_client(monkeypatch):
    """用独立 schema 运行真实路由和数据库，不连接生产服务。"""
    dsn = os.getenv("FAMILY_TEST_POSTGRES_URL") or os.getenv("POSTGRES_URL")
    if not dsn:
        pytest.skip("FAMILY_TEST_POSTGRES_URL 未配置")
    monkeypatch.setenv("API_KEY_DERIVATION_SECRET", "family-integration-synthetic-secret")
    schema = "family_test_" + uuid.uuid4().hex
    bootstrap = create_async_engine(dsn)
    async with bootstrap.begin() as conn:
        await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_async_engine(dsn, connect_args={"server_settings": {"search_path": schema}})
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with sessions() as db:
        dept = Department(name="合成测试部门")
        db.add(dept)
        await db.flush()
        for uid in ("owner", "member", "stranger"):
            user = User(uid=uid, username=uid, password_hash="test-only", role="user", department_id=dept.id)
            db.add(user)
            await db.flush()
            TEST_TOKENS[uid] = AuthUtils.create_access_token({"sub": str(user.id)})
        await db.commit()

    async def database():
        async with sessions() as db:
            yield db

    app = FastAPI()
    app.include_router(router, prefix="/api")
    app.dependency_overrides[get_db] = database
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    server = uvicorn.Server(uvicorn.Config(app, log_level="error", lifespan="off"))
    task = asyncio.create_task(server.serve(sockets=[listener]))
    try:
        for _ in range(100):
            if server.started:
                break
            if task.done():
                await task
            await asyncio.sleep(0.01)
        assert server.started
        async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{listener.getsockname()[1]}") as client:
            yield client, sessions
    finally:
        server.should_exit = True
        await task
        listener.close()
    await engine.dispose()
    async with bootstrap.begin() as conn:
        await conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
    await bootstrap.dispose()


def headers(uid="owner"):
    """构造仅供集成测试的认证身份。"""
    return {"Authorization": f"Bearer {TEST_TOKENS[uid]}"}


async def create_family(client):
    """建立家庭及本人档案。"""
    response = await client.post("/api/family", headers=headers(), json={"name": "合成测试家庭"})
    assert response.status_code == 200, response.text
    return response.json()


async def invite_member(client, family_id, adult=True):
    """创建成员并由另一登录用户认领。"""
    response = await client.post(
        f"/api/family/{family_id}/members", headers=headers(), json={"name": "合成成员", "relationship": "配偶"}
    )
    assert response.status_code == 200, response.text
    member_id = response.json()["id"]
    invitation = await client.post(f"/api/family/{family_id}/members/{member_id}/invite", headers=headers())
    assert invitation.status_code == 200
    claimed = await client.post("/api/family/join", headers=headers("member"), json={"code": invitation.json()["code"]})
    assert claimed.status_code == 200, claimed.text
    if adult:
        await client.put(
            f"/api/family/{family_id}/members/{member_id}",
            headers=headers("member"),
            json={"expected_version": 1, "profile": {"birth_date": "1990-01-01"}},
        )
    return member_id


async def grant(client, family_id, member_id, fields):
    """由本人授予有期限的字段访问权。"""
    return await client.put(
        f"/api/family/{family_id}/members/{member_id}/authorization",
        headers=headers("member"),
        json={"fields": fields, "expires_at": (datetime.now(UTC) + timedelta(days=30)).isoformat()},
    )


@pytest.mark.asyncio
async def test_family_is_private_and_requires_authentication(family_client):
    client, _ = family_client
    assert (await client.get("/api/family")).status_code == 401
    family = await create_family(client)
    assert family["members"][0]["is_self"] is True
    assert (await client.get("/api/family", headers=headers("stranger"))).json() == []
    assert (await client.get(f"/api/family/{family['id']}", headers=headers("stranger"))).status_code == 404


@pytest.mark.asyncio
async def test_owner_needs_subject_authorization_for_fields_and_metrics(family_client):
    client, _ = family_client
    family = await create_family(client)
    fid = family["id"]
    mid = await invite_member(client, fid)
    path = f"/api/family/{fid}/members/{mid}"
    denied = await client.put(path, headers=headers(), json={"expected_version": 1, "profile": {"height_cm": 170}})
    assert denied.status_code == 403
    assert (await grant(client, fid, mid, ["height_cm", "weight"])).status_code == 200
    result = await client.put(path, headers=headers(), json={"expected_version": 2, "profile": {"height_cm": 170}})
    assert result.status_code == 200
    assert result.json()["profile"] == {"height_cm": 170}
    assert (
        await client.put(
            path, headers=headers(), json={"expected_version": 2, "profile": {"medical_history": "合成敏感信息"}}
        )
    ).status_code == 403
    assert (
        await client.put(
            path + "/authorization",
            headers=headers(),
            json={"fields": ["medical_history"], "expires_at": (datetime.now(UTC) + timedelta(days=1)).isoformat()},
        )
    ).status_code == 403


@pytest.mark.asyncio
async def test_measurement_retries_conflicts_and_revocation(family_client):
    client, sessions = family_client
    family = await create_family(client)
    fid = family["id"]
    mid = await invite_member(client, fid)
    await grant(client, fid, mid, ["weight"])
    rid = str(uuid.uuid4())
    measured = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    payload = {
        "id": rid,
        "kind": "weight",
        "values": {"weight": 63.4},
        "measured_at": measured,
        "source": "manual",
        "condition": "",
        "note": "",
    }
    path = f"/api/family/{fid}/members/{mid}/measurements"
    first = await client.post(path, headers=headers(), json=payload)
    assert first.status_code == 200, first.text
    assert (await client.post(path, headers=headers(), json=payload)).json()["id"] == rid
    assert (await client.post(path, headers=headers(), json={**payload, "values": {"weight": 64}})).status_code == 409
    corrected = await client.put(
        path + "/" + rid,
        headers=headers(),
        json={"expected_version": 1, "values": {"weight": 63.5}, "note": "更正合成记录"},
    )
    assert corrected.status_code == 200
    assert corrected.json()["version"] == 2
    assert corrected.json()["previous"][0]["values"] == {"weight": 63.4}
    overview = await client.get(f"/api/family/{fid}/statistics?days=30", headers=headers())
    assert overview.status_code == 200
    assert overview.json()["record_count"] == 1
    await grant(client, fid, mid, [])
    listed = (await client.get(f"/api/family/{fid}", headers=headers())).json()
    member = next(row for row in listed["members"] if row["id"] == mid)
    assert member["profile"] == {}
    assert (await client.get(path, headers=headers())).status_code == 403
    assert (await client.post(path, headers=headers(), json=payload)).status_code == 403
    assert (await client.get(f"/api/family/{fid}/statistics", headers=headers())).json()["record_count"] == 0
    async with sessions() as db:
        count = await db.scalar(text("SELECT count(*) FROM family_measurements"))
        assert count == 1


@pytest.mark.asyncio
async def test_profile_version_and_unknown_values(family_client):
    client, _ = family_client
    family = await create_family(client)
    path = f"/api/family/{family['id']}/members/{family['members'][0]['id']}"
    saved = await client.put(path, headers=headers(), json={"expected_version": 1, "profile": {"height_cm": 165}})
    assert saved.status_code == 200
    assert saved.json()["version"] == 2
    assert "birth_date" in saved.json()["missing_fields"]
    assert (
        await client.put(path, headers=headers(), json={"expected_version": 1, "profile": {"height_cm": 166}})
    ).status_code == 409
    assert (await client.post(path + "/confirm", headers=headers(), json={"expected_version": 2})).status_code == 200
    history = (await client.get(path + "/history", headers=headers())).json()
    assert history[0]["profile"]["height_cm"] == 165


@pytest.mark.asyncio
async def test_metric_shape_time_expiry_and_foreign_member_are_rejected(family_client):
    client, _ = family_client
    family = await create_family(client)
    fid, mid = family["id"], family["members"][0]["id"]
    path = f"/api/family/{fid}/members/{mid}/measurements"
    payload = {
        "id": str(uuid.uuid4()),
        "kind": "blood_pressure",
        "values": {"systolic": 120},
        "measured_at": datetime.now(UTC).isoformat(),
        "source": "manual",
    }
    assert (await client.post(path, headers=headers(), json=payload)).status_code == 422
    payload.update(
        kind="weight", values={"weight": 60}, measured_at=(datetime.now(UTC) + timedelta(days=1)).isoformat()
    )
    assert (await client.post(path, headers=headers(), json=payload)).status_code == 422
    assert (
        await client.get(f"/api/family/{uuid.uuid4()}/members/{mid}/measurements", headers=headers())
    ).status_code == 404
    pending = await invite_member(client, fid)
    expired = await client.put(
        f"/api/family/{fid}/members/{pending}/authorization",
        headers=headers("member"),
        json={"fields": ["weight"], "expires_at": (datetime.now(UTC) - timedelta(hours=1)).isoformat()},
    )
    assert expired.status_code == 422


@pytest.mark.asyncio
async def test_expired_grant_filters_profile_history_and_statistics(family_client):
    """落库授权过期后，所有健康读取路径都重新校验。"""
    client, sessions = family_client
    family = await create_family(client)
    fid = family["id"]
    mid = await invite_member(client, fid)
    path = f"/api/family/{fid}/members/{mid}"
    await client.put(
        path,
        headers=headers("member"),
        json={"expected_version": 2, "profile": {"height_cm": 172, "medical_history": "合成私密信息"}},
    )
    await grant(client, fid, mid, ["height_cm", "weight"])
    history = (await client.get(path + "/history", headers=headers())).json()
    assert history[0]["profile"] == {"height_cm": 172}
    async with sessions() as db:
        member = await db.scalar(select(FamilyMember).where(FamilyMember.id == mid))
        member.grant_expires_at = datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=1)
        await db.commit()
    response = await client.get(f"/api/family/{fid}", headers=headers())
    assert response.headers["cache-control"] == "no-store"
    visible = next(row for row in response.json()["members"] if row["id"] == mid)
    assert visible["profile"] == {} and visible["allowed_fields"] == []
    assert (await client.get(path + "/history", headers=headers())).status_code == 403
    assert (await client.get(path + "/measurements", headers=headers())).status_code == 403
    own = (await client.get(path + "/history", headers=headers("member"))).json()
    assert own[0]["profile"]["medical_history"] == "合成私密信息"


@pytest.mark.asyncio
async def test_concurrent_retries_preserve_one_measurement(family_client):
    """真实并发请求由家庭事务锁串行化，落库仅一条。"""
    client, sessions = family_client
    family = await create_family(client)
    fid, mid = family["id"], family["members"][0]["id"]
    payload = {
        "id": str(uuid.uuid4()),
        "kind": "weight",
        "values": {"weight": 62},
        "measured_at": datetime.now(UTC).isoformat(),
        "source": "manual",
    }
    responses = await asyncio.gather(
        *[
            client.post(f"/api/family/{fid}/members/{mid}/measurements", headers=headers(), json=payload)
            for _ in range(3)
        ]
    )
    assert [response.status_code for response in responses] == [200, 200, 200]
    async with sessions() as db:
        assert await db.scalar(text("SELECT count(*) FROM family_measurements")) == 1


@pytest.mark.asyncio
async def test_member_authorization_requires_adult_profile(family_client):
    """年龄未知或未成年时拒绝开放；本人读写与撤回不受影响。"""
    client, _ = family_client
    family = await create_family(client)
    fid = family["id"]
    mid = await invite_member(client, fid, adult=False)
    path = f"/api/family/{fid}/members/{mid}"
    assert (await grant(client, fid, mid, ["weight"])).status_code == 422
    await client.put(
        path, headers=headers("member"), json={"expected_version": 1, "profile": {"birth_date": "2015-01-01"}}
    )
    assert (await grant(client, fid, mid, ["weight"])).status_code == 422
    assert (await grant(client, fid, mid, [])).status_code == 200


@pytest.mark.asyncio
async def test_invitation_and_claim_retries_do_not_create_new_access(family_client):
    """响应丢失可重放，已认领代码不会让其他账户获得关系。"""
    client, _ = family_client
    family = await create_family(client)
    fid = family["id"]
    created = await client.post(
        f"/api/family/{fid}/members", headers=headers(), json={"name": "合成邀请成员", "relationship": "家人"}
    )
    mid = created.json()["id"]
    path = f"/api/family/{fid}/members/{mid}/invite"
    first = (await client.post(path, headers=headers())).json()
    second = (await client.post(path, headers=headers())).json()
    assert first == second
    payload = {"code": first["code"]}
    assert (await client.post("/api/family/join", headers=headers("member"), json=payload)).status_code == 200
    replay = await client.post("/api/family/join", headers=headers("member"), json=payload)
    assert replay.status_code == 200
    assert len(replay.json()["members"]) == 2
    assert (await client.post("/api/family/join", headers=headers("stranger"), json=payload)).status_code == 410
    assert (await client.post(path, headers=headers())).status_code == 403

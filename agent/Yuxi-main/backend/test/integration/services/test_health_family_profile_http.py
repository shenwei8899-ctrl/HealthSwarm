"""真实 HTTP / PostgreSQL 验证本人档案关联、版本及模型历史失效。"""

import asyncio
from contextlib import asynccontextmanager
import os
import socket
from types import SimpleNamespace
from uuid import uuid4

from fastapi import FastAPI
import httpx
import pytest
import pytest_asyncio
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
import uvicorn

from server.routers import router
from server.utils.auth_middleware import get_db
from yuxi.services.family_schemas import ProfileUpdate
from yuxi.services.family_service import FamilyService
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_business import (
    AgentRun,
    Base,
    Conversation,
    Department,
    FamilyAudit,
    FamilyMember as SourceMember,
    Project,
    User,
)
from yuxi.storage.postgres.models_health import HealthProcessingConsent, HealthProfileSnapshot
from yuxi.utils.auth_utils import AuthUtils

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]
ROOT = "/api/health/v1"
SYNTHETIC_PROFILE = {
    "sex": "female",
    "birth_date": "1990-01-01",
    "height_cm": 165,
    "activity_level": "light",
    "goal": "合成测试：保持规律饮食",
    "medical_history": "合成自述，未经专业编码",
    "medications": None,
    "doctor_instructions": "合成医嘱文本，尚无批准规则编码",
    "allergens": [],
    "avoidances": [],
    "preferences": "合成偏好：清淡",
}


@pytest.fixture(scope="session", autouse=True)
def cleanup_test_sandboxes():
    """本文件仅使用独立数据库 schema，不清理其他任务沙盒。"""
    yield


@pytest.fixture(scope="session", autouse=True)
def cleanup_test_knowledge_resources():
    """合成档案不进入知识库，不调用其他服务的资源清理。"""
    yield


@pytest.fixture(scope="session", autouse=True)
def ensure_live_api_schema():
    """本文件验证独立 schema 与 TCP 应用，不借用正在迁移的主 API。"""


@pytest_asyncio.fixture
async def family_profile_http(monkeypatch):
    """将真实 TCP 路由与 Agent service 会话接入同一独立 PG schema。"""
    dsn = os.getenv("FAMILY_TEST_POSTGRES_URL") or os.getenv("POSTGRES_URL")
    if not dsn:
        pytest.skip("FAMILY_TEST_POSTGRES_URL 未配置")
    monkeypatch.setenv("API_KEY_DERIVATION_SECRET", "family-profile-integration-synthetic-secret")
    schema = "family_profile_test_" + uuid4().hex
    bootstrap = create_async_engine(dsn)
    async with bootstrap.begin() as connection:
        await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_async_engine(dsn, connect_args={"server_settings": {"search_path": schema}})
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    identities = {}
    async with sessions() as session:
        department = Department(name="合成档案接入测试部门")
        session.add(department)
        await session.flush()
        for uid, role in (("self", "user"), ("other", "user"), ("admin", "admin")):
            user = User(uid=uid, username=uid, password_hash="test-only", role=role, department_id=department.id)
            session.add(user)
            await session.flush()
            identities[uid] = {"Authorization": f"Bearer {AuthUtils.create_access_token({'sub': str(user.id)})}"}
        await session.commit()

    async def database():
        """家庭路由使用真实数据库事务。"""
        async with sessions() as session:
            yield session

    @asynccontextmanager
    async def health_database():
        """保持 health service 原有提交与异常回滚语义。"""
        async with sessions() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    monkeypatch.setattr(pg_manager, "get_async_session_context", health_database)
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
        async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{listener.getsockname()[1]}", timeout=10) as client:
            yield client, sessions, identities
    finally:
        server.should_exit = True
        await task
        listener.close()
        await engine.dispose()
        async with bootstrap.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await bootstrap.dispose()


async def create_source(client, headers, *, confirmed=True):
    """经正式接口创建并由本人填写、确认合成档案。"""
    response = await client.post("/api/family", headers=headers, json={"name": "合成家庭"})
    assert response.status_code == 200, response.text
    family = response.json()
    source_id = next(member["id"] for member in family["members"] if member["is_self"])
    path = f"/api/family/{family['id']}/members/{source_id}"
    response = await client.put(path, headers=headers, json={"expected_version": 1, "profile": SYNTHETIC_PROFILE})
    assert response.status_code == 200 and response.json()["version"] == 2, response.text
    if confirmed:
        response = await client.post(path + "/confirm", headers=headers, json={"expected_version": 2})
        assert response.status_code == 200, response.text
    return {"family_id": family["id"], "source_member_id": source_id, "confirmed_identity": True}


async def create_health_member(client, headers, relationship="本人"):
    """仅由当前账号创建明确语义的健康成员。"""
    response = await client.post(
        ROOT + "/members",
        headers=headers,
        json={"display_name": "合成成员", "relationship_label": relationship, "authorized": True},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def linked_self(client, headers, *, confirmed=True):
    """真实接口关联两套成员；保留正式来源身份用于独立断言。"""
    source = await create_source(client, headers, confirmed=confirmed)
    member_id = await create_health_member(client, headers)
    response = await client.post(f"{ROOT}/members/{member_id}/family-profile-link", headers=headers, json=source)
    assert response.status_code in {200, 201}, response.text
    return member_id, source


async def test_link_is_explicit_idempotent_and_persists_one_source(family_profile_http):
    """未关联保持未知，重试只落一条身份关联且回读同一来源。"""
    from yuxi.storage.postgres.models_health import HealthFamilyProfileLink

    client, sessions, identities = family_profile_http
    headers = identities["self"]
    source = await create_source(client, headers)
    member_id = await create_health_member(client, headers)
    profile_path = f"{ROOT}/members/{member_id}/family-profile"
    unlinked = await client.get(profile_path, headers=headers)
    assert unlinked.status_code == 200 and unlinked.json()["status"] == "not_ready", unlinked.text
    assert unlinked.json()["profile"] is None
    path = f"{ROOT}/members/{member_id}/family-profile-link"
    first = await client.post(path, headers=headers, json=source)
    assert first.status_code in {200, 201}, first.text
    assert (await client.post(path, headers=headers, json=source)).json() == first.json()
    current = await client.get(path, headers=headers)
    assert current.status_code == 200, current.text
    assert current.json() == {
        "member_id": member_id,
        "source_member_id": source["source_member_id"],
        "family_id": source["family_id"],
        "scope": "self_confirmed_profile",
    }
    async with sessions() as session:
        rows = (await session.scalars(select(HealthFamilyProfileLink))).all()
        assert len(rows) == 1 and rows[0].member_id == member_id
        assert rows[0].source_member_id == source["source_member_id"]


@pytest.mark.parametrize("linked", [False, True])
async def test_inactive_source_never_links_or_returns_ready_profile(family_profile_http, linked):
    """数据库已有停用来源时，即使家庭仍可见也不能建立或重读正式映射。"""
    client, sessions, identities = family_profile_http
    headers = identities["self"]
    source = await create_source(client, headers)
    member_id = await create_health_member(client, headers)
    link_path = f"{ROOT}/members/{member_id}/family-profile-link"
    if linked:
        response = await client.post(link_path, headers=headers, json=source)
        assert response.status_code == 200, response.text
        before = await client.get(f"{ROOT}/members/{member_id}/family-profile", headers=headers)
        assert before.status_code == 200 and before.json()["status"] == "ready", before.text
    async with sessions() as session:
        row = await session.get(SourceMember, source["source_member_id"])
        row.is_active = False
        await session.commit()
    denied = await client.post(link_path, headers=headers, json=source)
    assert denied.status_code == 404, denied.text
    if linked:
        for suffix in ("family-profile-link", "family-profile", "weight-records", "blood-pressure-records"):
            denied = await client.get(f"{ROOT}/members/{member_id}/{suffix}", headers=headers)
            assert denied.status_code == 404, (suffix, denied.text)


async def test_link_rejects_implicit_confirmation_proxy_and_foreign_family(family_profile_http):
    """确认标志、本人关系及准确家庭归属都是独立入口条件。"""
    client, _, identities = family_profile_http
    headers = identities["self"]
    source = await create_source(client, headers)
    member_id = await create_health_member(client, headers)
    path = f"{ROOT}/members/{member_id}/family-profile-link"
    assert (await client.post(path, headers=headers, json={**source, "confirmed_identity": False})).status_code == 422
    assert (await client.post(path, headers=headers, json={**source, "actor_uid": "other"})).status_code == 422
    wrong_family = await client.post(path, headers=headers, json={**source, "family_id": str(uuid4())})
    assert wrong_family.status_code == 404, wrong_family.text
    foreign = await create_source(client, identities["other"])
    assert (await client.post(path, headers=headers, json=foreign)).status_code == 404
    proxy_id = await create_health_member(client, headers, relationship="配偶")
    proxy = await client.post(f"{ROOT}/members/{proxy_id}/family-profile-link", headers=headers, json=source)
    assert proxy.status_code == 404, proxy.text
    assert (await client.post(path, json=source)).status_code == 401


async def test_source_cannot_be_rebound_or_linked_to_two_health_members(family_profile_http):
    """同一健康身份不可改指另一成员，源成员不得产生重复健康身份。"""
    from yuxi.storage.postgres.models_health import HealthFamilyProfileLink

    client, sessions, identities = family_profile_http
    headers = identities["self"]
    member_id, source = await linked_self(client, headers)
    second_health = await create_health_member(client, headers)
    duplicate = await client.post(f"{ROOT}/members/{second_health}/family-profile-link", headers=headers, json=source)
    assert duplicate.status_code == 409, duplicate.text
    other_source = await create_source(client, identities["other"])
    other_member_id = await create_health_member(client, identities["other"])
    stolen = await client.post(
        f"{ROOT}/members/{other_member_id}/family-profile-link", headers=identities["other"], json=source
    )
    assert stolen.status_code == 404, stolen.text
    altered = await client.post(f"{ROOT}/members/{member_id}/family-profile-link", headers=headers, json=other_source)
    assert altered.status_code in {404, 409}, altered.text
    created = await client.post(
        f"/api/family/{other_source['family_id']}/members",
        headers=identities["other"],
        json={"name": "合成第二本人关系", "relationship": "家人"},
    )
    assert created.status_code == 200, created.text
    alternate_id = created.json()["id"]
    invitation = await client.post(
        f"/api/family/{other_source['family_id']}/members/{alternate_id}/invite", headers=identities["other"]
    )
    assert invitation.status_code == 200, invitation.text
    joined = await client.post("/api/family/join", headers=headers, json={"code": invitation.json()["code"]})
    assert joined.status_code == 200, joined.text
    alternate_source = {**other_source, "source_member_id": alternate_id}
    rebind = await client.post(
        f"{ROOT}/members/{member_id}/family-profile-link", headers=headers, json=alternate_source
    )
    assert rebind.status_code == 409, rebind.text
    async with sessions() as session:
        assert await session.scalar(select(func.count()).select_from(HealthFamilyProfileLink)) == 1
        row = await session.get(HealthFamilyProfileLink, member_id)
        assert row.source_member_id == source["source_member_id"]


async def test_confirmed_profile_preserves_raw_unknowns_without_safety_or_processing_consent(family_profile_http):
    """描述性读取保留空值与明确空数组，不能生成专业编码或处理同意。"""
    client, sessions, identities = family_profile_http
    member_id, _ = await linked_self(client, identities["self"])
    response = await client.get(f"{ROOT}/members/{member_id}/family-profile", headers=identities["self"])
    assert response.status_code == 200, response.text
    assert response.headers["Cache-Control"] == "no-store"
    result = response.json()
    assert result["status"] == "ready" and result["confirmed_version"] == 2
    assert result["profile"] == SYNTHETIC_PROFILE
    assert result["nutrition_safety_ready"] is False and result["full_health_profile_available"] is False
    assert "population_code" not in result["profile"] and "conditions" not in result["profile"]
    async with sessions() as session:
        assert await session.scalar(select(func.count()).select_from(HealthProcessingConsent)) == 0
        assert await session.scalar(select(func.count()).select_from(HealthProfileSnapshot)) == 0
        audits = (
            await session.scalars(
                select(FamilyAudit).where(FamilyAudit.actor_uid == "self", FamilyAudit.action == "agent_profile_read")
            )
        ).all()
        assert len(audits) == 1 and audits[0].version == 2


async def test_update_requires_new_subject_confirmation_before_profile_is_available(family_profile_http):
    """旧确认不覆盖新版本，未经重新确认的内容不会供 Agent 消费。"""
    client, _, identities = family_profile_http
    headers = identities["self"]
    member_id, source = await linked_self(client, headers, confirmed=False)
    profile_path = f"{ROOT}/members/{member_id}/family-profile"
    pending = await client.get(profile_path, headers=headers)
    assert pending.status_code == 200 and pending.json()["status"] == "not_ready", pending.text
    assert pending.json()["profile"] is None and pending.json()["confirmed_version"] is None
    path = f"/api/family/{source['family_id']}/members/{source['source_member_id']}"
    assert (await client.post(path + "/confirm", headers=headers, json={"expected_version": 2})).status_code == 200
    assert (await client.get(profile_path, headers=headers)).json()["confirmed_version"] == 2
    changed = await client.put(path, headers=headers, json={"expected_version": 2, "profile": {"height_cm": 170}})
    assert changed.status_code == 200 and changed.json()["version"] == 3, changed.text
    invalidated = await client.get(profile_path, headers=headers)
    assert invalidated.status_code == 200 and invalidated.json()["status"] == "not_ready", invalidated.text
    assert invalidated.json()["profile"] is None
    assert (await client.post(path + "/confirm", headers=headers, json={"expected_version": 2})).status_code == 409
    assert (await client.post(path + "/confirm", headers=headers, json={"expected_version": 3})).status_code == 200
    latest = (await client.get(profile_path, headers=headers)).json()
    assert latest["confirmed_version"] == 3 and latest["profile"]["height_cm"] == 170


async def test_admin_health_grant_does_not_authorize_another_subjects_formal_profile(family_profile_http):
    """管理员得到健康域 grant 仍不能读取或关联别人的正式档案。"""
    client, _, identities = family_profile_http
    headers = identities["self"]
    member_id, source = await linked_self(client, headers)
    grant = await client.put(
        f"{ROOT}/members/{member_id}/grants",
        headers=headers,
        json={"actor_uid": "admin", "scopes": ["profile_edit", "profile_view", "ai_use"]},
    )
    assert grant.status_code == 200, grant.text
    path = f"{ROOT}/members/{member_id}/family-profile"
    assert (await client.get(path, headers=identities["admin"])).status_code == 404
    assert (await client.get(path + "-link", headers=identities["admin"])).status_code == 404
    assert (await client.post(path + "-link", headers=identities["admin"], json=source)).status_code == 404


async def test_revoked_health_scope_denies_current_profile_and_link_reads(family_profile_http):
    """持久化关联不延续撤回的健康域字段访问权限。"""
    client, _, identities = family_profile_http
    headers = identities["self"]
    member_id, _ = await linked_self(client, headers)
    revoked = await client.put(
        f"{ROOT}/members/{member_id}/grants", headers=headers, json={"actor_uid": "self", "scopes": ["ai_use"]}
    )
    assert revoked.status_code == 200, revoked.text
    path = f"{ROOT}/members/{member_id}/family-profile"
    assert (await client.get(path, headers=headers)).status_code == 404
    assert (await client.get(path + "-link", headers=headers)).status_code == 404


async def test_source_claim_cannot_be_silently_reused_after_identity_changes(family_profile_http):
    """当前来源的本人归属每次复核，历史关联不能替代已变化的身份。"""
    client, sessions, identities = family_profile_http
    member_id, source = await linked_self(client, identities["self"])
    async with sessions() as session:
        source_member = await session.get(SourceMember, source["source_member_id"])
        source_member.subject_uid = "other"
        await session.commit()
    response = await client.get(f"{ROOT}/members/{member_id}/family-profile", headers=identities["self"])
    assert response.status_code == 404, response.text


async def recorded_profile_use(sessions, member_id, uid):
    """持久化真实 Run 与档案读取回执，供历史失效测试独立回读。"""
    from yuxi.repositories.health_family_profile_repository import HealthFamilyProfileRepository
    from yuxi.storage.postgres.models_health import HealthConsultation

    async with sessions() as session:
        project_id, thread_id, run_id = str(uuid4()), str(uuid4()), str(uuid4())
        session.add(
            Project(
                id=project_id,
                uid=uid,
                selection_status="implicit",
                directory_mode="managed",
                workdir_path=f"projects/{project_id}",
            )
        )
        await session.flush()
        conversation = Conversation(uid=uid, thread_id=thread_id, project_id=project_id, agent_id="health-consultation")
        session.add(conversation)
        await session.flush()
        session.add(
            HealthConsultation(
                conversation_id=conversation.id, member_id=member_id, actor_uid=uid, request_id=str(uuid4())
            )
        )
        await session.flush()
        run = AgentRun(
            id=run_id,
            request_id=str(uuid4()),
            uid=uid,
            agent_slug="health-consultation",
            conversation_id=conversation.id,
            conversation_thread_id=thread_id,
            runtime_scope_id=thread_id,
            status="completed",
        )
        session.add(run)
        await session.flush()
        repository = HealthFamilyProfileRepository(session)
        payload = await repository.read(uid, member_id)
        await repository.record_use(run, payload)
        await session.commit()
        return SimpleNamespace(conversation_id=conversation.id, member_id=member_id, actor_uid=uid), payload


async def test_run_history_rechecks_profile_version_and_current_health_permission(family_profile_http):
    """真实历史收据在档案改版与授权撤回后分别因当前事实而拒绝。"""
    from yuxi.repositories.health_family_profile_repository import HealthFamilyProfileRepository
    from yuxi.storage.postgres.models_health import HealthFamilyProfileUse

    client, sessions, identities = family_profile_http
    headers = identities["self"]
    member_id, source = await linked_self(client, headers)
    binding, original = await recorded_profile_use(sessions, member_id, "self")
    async with sessions() as session:
        repository = HealthFamilyProfileRepository(session)
        await repository.validate_history("self", binding)
        await repository.validate_tool_payload("self", binding, original)
        tampered = {**original, "profile": {**original["profile"], "height_cm": 166}}
        assert tampered["source_hash"] == original["source_hash"]
        with pytest.raises(HealthVisionError) as error:
            await repository.validate_tool_payload("self", binding, tampered)
        assert error.value.status == 410
        for changed in (
            {**original, "profile_available": 1},
            {**original, "confirmed_version": float(original["confirmed_version"])},
            {**original, "profile": {**original["profile"], "height_cm": int(original["profile"]["height_cm"])}},
        ):
            assert changed == original
            assert repository.payload_hash(changed) != original["source_hash"]
            with pytest.raises(HealthVisionError, match="profile_source_changed") as error:
                await repository.validate_tool_payload("self", binding, changed)
            assert error.value.status == 410
        current_conversation = await session.get(Conversation, binding.conversation_id)
        other_conversation = Conversation(
            uid="self",
            thread_id=str(uuid4()),
            project_id=current_conversation.project_id,
            agent_id="health-consultation",
        )
        session.add(other_conversation)
        await session.flush()
        other_binding = SimpleNamespace(conversation_id=other_conversation.id, member_id=member_id, actor_uid="self")
        with pytest.raises(HealthVisionError) as error:
            await repository.validate_tool_payload("self", other_binding, original)
        assert error.value.status == 410
        uses = (await session.scalars(select(HealthFamilyProfileUse))).all()
        assert len(uses) == 1 and uses[0].source_member_id == source["source_member_id"]
        assert uses[0].version == original["confirmed_version"] == 2
        await session.commit()
    path = f"/api/family/{source['family_id']}/members/{source['source_member_id']}"
    response = await client.put(path, headers=headers, json={"expected_version": 2, "profile": {"height_cm": 171}})
    assert response.status_code == 200, response.text
    async with sessions() as session:
        with pytest.raises(HealthVisionError) as error:
            await HealthFamilyProfileRepository(session).validate_history("self", binding)
        assert error.value.status == 410
    revoked = await client.put(
        f"{ROOT}/members/{member_id}/grants", headers=headers, json={"actor_uid": "self", "scopes": ["ai_use"]}
    )
    assert revoked.status_code == 200, revoked.text
    async with sessions() as session:
        with pytest.raises(HealthVisionError) as error:
            await HealthFamilyProfileRepository(session).validate_history("self", binding)
        assert error.value.status in {404, 410}


async def test_formal_profile_update_waits_for_agent_read_transaction(family_profile_http):
    """观察真实 PG 锁等待；读事务提交后改版，旧历史立即失效。"""
    from yuxi.repositories.health_family_profile_repository import HealthFamilyProfileRepository

    client, sessions, identities = family_profile_http
    member_id, source = await linked_self(client, identities["self"])
    binding, _ = await recorded_profile_use(sessions, member_id, "self")
    application_name = "profile_update_" + uuid4().hex

    async def update_source():
        """正式服务持有自己的连接，维持原有家庭行锁协议。"""
        async with sessions() as writer:
            await writer.execute(text("SELECT set_config('application_name', :name, true)"), {"name": application_name})
            return await FamilyService(writer, "self").update_profile(
                source["family_id"],
                source["source_member_id"],
                ProfileUpdate(expected_version=2, profile={"height_cm": 172}),
            )

    async with sessions() as reader:
        payload = await HealthFamilyProfileRepository(reader).read("self", member_id)
        assert payload["confirmed_version"] == 2
        writer_task = asyncio.create_task(update_source())
        try:
            async with sessions() as observer:
                for _ in range(100):
                    await observer.execute(text("SELECT pg_stat_clear_snapshot()"))
                    waiting = await observer.scalar(
                        text(
                            "SELECT count(*) FROM pg_stat_activity "
                            "WHERE application_name=:name AND wait_event_type='Lock'"
                        ),
                        {"name": application_name},
                    )
                    if waiting:
                        break
                    await asyncio.sleep(0.02)
            assert waiting == 1, "正式修改必须在 Agent 持有的家庭锁上等待"
            assert not writer_task.done()
            await reader.commit()
            result = await asyncio.wait_for(writer_task, timeout=5)
            assert result["version"] == 3 and result["profile"]["height_cm"] == 172
        finally:
            if not writer_task.done():
                writer_task.cancel()
                await asyncio.gather(writer_task, return_exceptions=True)
    async with sessions() as session:
        with pytest.raises(HealthVisionError) as error:
            await HealthFamilyProfileRepository(session).validate_history("self", binding)
        assert error.value.status == 410


async def test_conversation_locked_history_avoids_member_and_family_lock_inversion(family_profile_http):
    """历史验证绕开逆序锁和审计写入；默认读取负控确实等待成员锁。"""
    from yuxi.repositories.health_family_profile_repository import HealthFamilyProfileRepository
    from yuxi.storage.postgres.models_business import FamilyArchive
    from yuxi.storage.postgres.models_health import FamilyMember as HealthMember

    client, sessions, identities = family_profile_http
    member_id, source = await linked_self(client, identities["self"])
    binding, original = await recorded_profile_use(sessions, member_id, "self")
    application_name = "profile_lock_order_" + uuid4().hex
    history_finished = asyncio.Event()
    start_locked_read = asyncio.Event()
    async with sessions() as observer:
        original_audits = await observer.scalar(select(func.count()).select_from(FamilyAudit))

    async def conversation_owner():
        """模拟队列先锁 Conversation，再重验历史的真实事务。"""
        async with sessions() as session:
            name_query = text("SELECT set_config('application_name', :name, true)")
            await session.execute(name_query, {"name": application_name})
            await session.scalar(
                select(Conversation).where(Conversation.id == binding.conversation_id).with_for_update()
            )
            repository = HealthFamilyProfileRepository(session)
            await repository.validate_history("self", binding, lock=False)
            history_finished.set()
            await start_locked_read.wait()
            current = await repository.read("self", member_id)
            await session.commit()
            return current

    async with sessions() as holder:
        holder_pid = await holder.scalar(text("SELECT pg_backend_pid()"))
        await holder.scalar(select(HealthMember).where(HealthMember.id == member_id).with_for_update())
        # 正式家庭锁也阻止 FK 审计写入，避免只证明 health 锁未取得。
        await holder.scalar(select(FamilyArchive).where(FamilyArchive.id == source["family_id"]).with_for_update())
        owner_task = asyncio.create_task(conversation_owner())
        try:
            await asyncio.wait_for(history_finished.wait(), timeout=5)
            assert not owner_task.done(), "历史验证应在持锁事务未释放时完成"
            async with sessions() as observer:
                assert await observer.scalar(select(func.count()).select_from(FamilyAudit)) == original_audits
                start_locked_read.set()
                waiting = None
                for _ in range(100):
                    await observer.execute(text("SELECT pg_stat_clear_snapshot()"))
                    waiting = (
                        await observer.execute(
                            text(
                                "SELECT wait_event_type, pg_blocking_pids(pid) "
                                "FROM pg_stat_activity WHERE application_name=:name"
                            ),
                            {"name": application_name},
                        )
                    ).first()
                    if waiting and waiting[0] == "Lock":
                        break
                    await asyncio.sleep(0.02)
            assert waiting and waiting[0] == "Lock" and holder_pid in waiting[1]
            assert not owner_task.done(), "默认读取应等待事务A的实际成员锁"
            await holder.commit()
            current = await asyncio.wait_for(owner_task, timeout=5)
            assert current["source_hash"] == original["source_hash"] and current["confirmed_version"] == 2
        finally:
            if not owner_task.done():
                owner_task.cancel()
                await asyncio.gather(owner_task, return_exceptions=True)
    async with sessions() as observer:
        assert await observer.scalar(select(func.count()).select_from(FamilyAudit)) == original_audits + 1

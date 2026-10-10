"""独立 PG schema 与真实 TCP 验证餐单分页、逐页授权及只读边界。"""

import asyncio
from contextlib import asynccontextmanager
from copy import deepcopy
from datetime import date, datetime
import hashlib
import json
import os
from pathlib import Path
import socket
from types import SimpleNamespace
from uuid import UUID, uuid4

from fastapi import FastAPI
import httpx
import pytest
import pytest_asyncio
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
import uvicorn

from server.routers import router
from server.utils.auth_middleware import get_db
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_business import AgentRun, AgentRunRequest, Base, Department, Message, User
from yuxi.storage.postgres.models_health import (
    FamilyMember,
    HealthGrant,
    HealthMealPlan,
    HealthMealPlanAdoption,
    HealthMealPlanAdoptionAction,
    HealthMealPlanAdoptionMember,
    HealthMealPlanRevision,
    HealthProfessionalReview,
    HealthQualityCheck,
    HealthReviewAction,
)
from yuxi.utils.auth_utils import AuthUtils

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]
ROOT = "/api/health/v1"


@pytest.fixture(scope="session", autouse=True)
def cleanup_test_sandboxes():
    """仅清理本文件独立 schema，不接触其他任务沙盒。"""
    yield


@pytest.fixture(scope="session", autouse=True)
def cleanup_test_knowledge_resources():
    """列表测试不创建知识库资源。"""
    yield


@pytest.fixture(scope="session", autouse=True)
def ensure_live_api_schema():
    """独立 schema 由 fixture 建立，不使用共享 API 的启动检查。"""


@pytest_asyncio.fixture
async def meal_pagination_http(monkeypatch, request):
    """shipping 路由、真实认证和健康事务共用本轮独立 PG schema。"""
    dsn = os.getenv("FAMILY_TEST_POSTGRES_URL") or os.getenv("POSTGRES_URL")
    if not dsn:
        pytest.skip("FAMILY_TEST_POSTGRES_URL / POSTGRES_URL 未配置")
    monkeypatch.setenv("JWT_SECRET_KEY", "meal-pagination-integration-synthetic-jwt-secret")
    monkeypatch.setenv("API_KEY_DERIVATION_SECRET", "meal-pagination-integration-synthetic-key-secret")
    schema = "meal_pagination_test_" + uuid4().hex
    bootstrap = create_async_engine(dsn)
    engine = None
    listener = None
    task = None
    server = None
    created = False
    evidence = {"test": request.node.name, "schema": schema, "requests": [], "cleanup_verified": False}
    try:
        async with bootstrap.begin() as connection:
            evidence["database"] = await connection.scalar(text("SELECT current_database()"))
            await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        created = True
        engine = create_async_engine(dsn, connect_args={"server_settings": {"search_path": schema}})
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        current = await seed_pagination_facts(sessions)
        current.sessions = sessions
        current.evidence = evidence
        evidence["expected_plan_ids"] = current.expected_ids
        evidence["seeded_counts"] = current.seeded_counts

        async def database():
            """认证依赖读取同一真实 schema 内的合成账号。"""
            async with sessions() as session:
                yield session

        @asynccontextmanager
        async def health_database():
            """保留 service 提交成功事务及异常回滚的真实语义。"""
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
        for _ in range(100):
            if server.started:
                break
            if task.done():
                await task
            await asyncio.sleep(0.01)
        assert server.started, "真实 TCP 服务未启动"
        async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{listener.getsockname()[1]}", timeout=10) as client:
            current.client = client
            yield current
    finally:
        try:
            if server is not None:
                server.should_exit = True
            if task is not None:
                await asyncio.wait_for(task, timeout=5)
        finally:
            if listener is not None:
                listener.close()
            if engine is not None:
                await engine.dispose()
            try:
                if created:
                    async with bootstrap.begin() as connection:
                        await connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
                    async with bootstrap.connect() as connection:
                        remaining = await connection.scalar(
                            text("SELECT count(*) FROM pg_namespace WHERE nspname = :schema"), {"schema": schema}
                        )
                    assert remaining == 0, "本轮 schema 及所属表必须从 PG catalog 清理"
                    evidence["cleanup_verified"] = True
            finally:
                await bootstrap.dispose()
                output_dir = os.getenv("HEALTH_MEAL_PAGINATION_EVIDENCE_DIR")
                if output_dir:
                    output = Path(output_dir)
                    output.mkdir(parents=True, exist_ok=True)
                    (output / f"{request.node.name}.json").write_text(
                        json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
                    )


async def test_pages_read_all_known_facts_in_date_and_uuid_order_without_writes(meal_pagination_http):
    """61 条明确 oracle 跨越 50 条边界，默认、小页、末尾和空页均只读。"""
    current = meal_pagination_http
    first = await read_page(current)
    assert_page(first, current.expected_ids[:50], truncated=True, next_offset=50)
    explicit = await read_page(current, params={"limit": 50, "offset": 0})
    assert explicit.json() == first.json(), "缺省参数须等于 limit=50、offset=0"
    second = await read_page(current, params={"limit": 50, "offset": 50})
    assert_page(second, current.expected_ids[50:], truncated=False, next_offset=None)
    all_ids = [p["plan_id"] for p in first.json()["plans"] + second.json()["plans"]]
    assert all_ids == current.expected_ids and len(set(all_ids)) == 61
    assert second.json()["plans"][2]["version"] == 2, "分页须返回当前版本事实"
    assert [p["updated_at"] for p in first.json()["plans"]][20:] == ["2026-10-08T10:00:00Z"] * 30
    assert [p["updated_at"] for p in second.json()["plans"]][:-1] == ["2026-10-08T10:00:00Z"] * 10

    collected = []
    offset = 0
    while True:
        response = await read_page(current, params={"limit": 7, "offset": offset})
        expected = current.expected_ids[offset : offset + 7]
        next_offset = offset + 7 if offset + 7 < 61 else None
        assert_page(response, expected, truncated=next_offset is not None, next_offset=next_offset)
        collected.extend(p["plan_id"] for p in response.json()["plans"])
        if next_offset is None:
            break
        offset = next_offset
    assert collected == current.expected_ids and len(set(collected)) == 61
    assert_page(
        await read_page(current, params={"limit": 1, "offset": 60}),
        current.expected_ids[-1:],
        truncated=False,
        next_offset=None,
    )
    for offset in (61, 62, 2147483647):
        assert_page(
            await read_page(current, params={"limit": 50, "offset": offset}),
            [],
            truncated=False,
            next_offset=None,
        )
    assert_page(await read_page(current, member=current.empty_member), [], truncated=False, next_offset=None)


async def test_invalid_query_parameters_are_rejected_without_writes(meal_pagination_http):
    """协议边界拒绝超范围、负数及非整数，而非静默采用默认页。"""
    invalid = [
        {"limit": 0},
        {"limit": -1},
        {"limit": 51},
        {"limit": "1.5"},
        {"limit": "invalid"},
        {"offset": -1},
        {"offset": 2147483648},
        {"offset": "1.5"},
        {"offset": "invalid"},
    ]
    for params in invalid:
        response = await read_page(meal_pagination_http, params=params)
        assert response.status_code == 422, (params, response.text)
        field = next(iter(params))
        assert any(error["loc"] == ["query", field] for error in response.json()["detail"]), response.text


async def test_each_actor_and_member_stays_private_and_primary_revocation_denies_every_page(meal_pagination_http):
    """同成员获授权账号仍只读自己的餐单；主成员撤权后所有页拒绝。"""
    current = meal_pagination_http
    assert_page(await read_page(current, actor="other"), [current.other_plan], truncated=False, next_offset=None)
    assert_page(await read_page(current, actor="admin"), [current.admin_plan], truncated=False, next_offset=None)
    assert_page(
        await read_page(current, member=current.alternate_member),
        [current.alternate_plan],
        truncated=False,
        next_offset=None,
    )
    for actor in ("owner", "admin"):
        response = await read_page(current, actor=actor, member=current.foreign_member)
        assert response.status_code == 404 and response.json()["code"] == "not_found", response.text
    await revoke_grant(current, current.member, "owner")
    for params in ({}, {"limit": 7, "offset": 7}, {"limit": 50, "offset": 50}, {"offset": 2147483647}):
        response = await read_page(current, params=params)
        assert response.status_code == 404 and response.json()["code"] == "not_found", response.text


async def test_second_page_and_lookahead_recheck_family_participants_even_for_admin(meal_pagination_http):
    """第二页家庭成员撤权立即拒绝，读到的 lookahead 及管理员也重验。"""
    current = meal_pagination_http
    assert_page(
        await read_page(current, params={"limit": 50, "offset": 50}),
        current.expected_ids[50:],
        truncated=False,
        next_offset=None,
    )
    await revoke_grant(current, current.second_member, "owner")
    assert_page(
        await read_page(current, params={"limit": 50, "offset": 0}),
        current.expected_ids[:50],
        truncated=True,
        next_offset=50,
    )
    for params in ({"limit": 50, "offset": 50}, {"limit": 1, "offset": 51}, {"limit": 1, "offset": 52}):
        response = await read_page(current, params=params)
        assert response.status_code == 404 and response.json()["code"] == "not_found", (params, response.text)
    await revoke_grant(current, current.second_member, "admin")
    response = await read_page(current, actor="admin", params={"limit": 1, "offset": 0})
    assert response.status_code == 404 and response.json()["code"] == "not_found", response.text


async def seed_pagination_facts(sessions):
    """插入明确合成查询事实；不证明生成、专业审批或采用流程。"""
    current = SimpleNamespace(
        member=str(uuid4()),
        second_member=str(uuid4()),
        alternate_member=str(uuid4()),
        empty_member=str(uuid4()),
        foreign_member=str(uuid4()),
        expected_ids=[str(UUID(int=n)) for n in [*range(300, 320), *range(100, 140), 50]],
        other_plan=str(UUID(int=500)),
        admin_plan=str(UUID(int=501)),
        alternate_plan=str(UUID(int=502)),
        identities={},
    )
    async with sessions() as session:
        department = Department(name="合成餐单分页部门")
        session.add(department)
        await session.flush()
        for actor, role in (("owner", "user"), ("other", "user"), ("admin", "admin")):
            user = User(
                uid=actor, username=actor, role=role, password_hash="synthetic-only", department_id=department.id
            )
            session.add(user)
            await session.flush()
            current.identities[actor] = {
                "Authorization": f"Bearer {AuthUtils.create_access_token({'sub': str(user.id)})}"
            }
        for member_id in (
            current.member,
            current.second_member,
            current.alternate_member,
            current.empty_member,
            current.foreign_member,
        ):
            session.add(
                FamilyMember(
                    id=member_id,
                    owner_uid="other" if member_id == current.foreign_member else "owner",
                    display_name="合成查询成员",
                    relationship_label="合成",
                )
            )
        await session.flush()
        for actor, member_ids in (
            ("owner", [current.member, current.second_member, current.alternate_member, current.empty_member]),
            ("other", [current.member, current.foreign_member]),
            ("admin", [current.member, current.second_member]),
        ):
            for member_id in member_ids:
                session.add(
                    HealthGrant(
                        member_id=member_id, actor_uid=actor, scopes=["diet_edit", "profile_view", "profile_edit"]
                    )
                )
        recipe_id = str(uuid4())
        solo = {
            "plan_date": "2026-10-10",
            "meals": [
                {"meal_type": meal, "dishes": [{"recipe_version_id": recipe_id, "grams": "100"}]}
                for meal in ("breakfast", "lunch", "dinner")
            ],
        }
        family = {
            "kind": "family",
            "plan_date": "2026-10-10",
            "meals": [
                {
                    "meal_type": meal,
                    "participant_ids": [current.member, current.second_member],
                    "dishes": [
                        {
                            "recipe_version_id": recipe_id,
                            "member_portions": [
                                {"member_id": member, "grams": "100"}
                                for member in (current.member, current.second_member)
                            ],
                        }
                    ],
                }
                for meal in ("breakfast", "lunch", "dinner")
            ],
        }
        rows = []
        for index, plan_id in reversed(list(enumerate(current.expected_ids))):
            timestamp = datetime(2026, 10, 9 if index < 20 else 8 if index < 60 else 7, 10)
            rows.append(
                HealthMealPlan(
                    id=plan_id,
                    actor_uid="owner",
                    member_id=current.member,
                    version=2 if index == 52 else 1,
                    spec=deepcopy(family if index == 52 else solo),
                    snapshot={"synthetic_marker": index, "status": "draft", "plan_date": "2026-10-10"},
                    created_at=timestamp,
                    updated_at=timestamp,
                )
            )
        for plan_id, actor, member_id, spec in (
            (current.other_plan, "other", current.member, solo),
            (current.admin_plan, "admin", current.member, family),
            (current.alternate_plan, "owner", current.alternate_member, solo),
        ):
            rows.append(
                HealthMealPlan(
                    id=plan_id,
                    actor_uid=actor,
                    member_id=member_id,
                    version=1,
                    spec=deepcopy(spec),
                    snapshot={"synthetic_marker": "private-decoy", "status": "draft", "plan_date": "2026-10-10"},
                    created_at=datetime(2026, 10, 10, 10),
                    updated_at=datetime(2026, 10, 10, 10),
                )
            )
        session.add_all(rows)
        await session.flush()
        for row in rows:
            for version in range(1, row.version + 1):
                session.add(
                    HealthMealPlanRevision(
                        id=str(uuid4()),
                        plan_id=row.id,
                        actor_uid=row.actor_uid,
                        request_id=str(uuid4()),
                        fingerprint="a" * 64,
                        version=version,
                        reason="合成查询修订",
                        spec=deepcopy(row.spec),
                        snapshot=deepcopy(row.snapshot),
                        created_at=row.created_at,
                    )
                )
        check_id, review_id, adoption_id = (str(uuid4()) for _ in range(3))
        session.add(
            HealthQualityCheck(
                id=check_id,
                actor_uid="owner",
                member_id=current.member,
                plan_id=current.expected_ids[52],
                plan_version=2,
                rule_code="synthetic-pagination-unpublished-rule",
                request_id=str(uuid4()),
                fingerprint="b" * 64,
                snapshot={"synthetic_query_fact": True},
            )
        )
        await session.flush()
        session.add(
            HealthProfessionalReview(
                id=review_id,
                check_id=check_id,
                actor_uid="owner",
                member_id=current.member,
                version=3,
                status="approved",
                reviewer_uid="admin",
                reviewer_version=1,
                updated_at=datetime(2026, 10, 8, 11),
            )
        )
        await session.flush()
        session.add(
            HealthReviewAction(
                id=str(uuid4()),
                review_id=review_id,
                actor_uid="admin",
                request_id=str(uuid4()),
                fingerprint="c" * 64,
                version=3,
                status="approved",
                reason="合成只读状态，不表示专业验收",
                evidence_refs=[],
            )
        )
        session.add(
            HealthMealPlanAdoption(
                id=adoption_id,
                actor_uid="owner",
                member_id=current.member,
                plan_id=current.expected_ids[52],
                plan_version=2,
                plan_date=date(2026, 10, 10),
                review_id=review_id,
                sources={"synthetic_query_fact": True},
                snapshot={"synthetic_query_fact": True},
                status="active",
                version=1,
                reason="合成只读状态，不表示采用验收",
                created_at=datetime(2026, 10, 8, 12),
                updated_at=datetime(2026, 10, 8, 12),
            )
        )
        await session.flush()
        session.add(
            HealthMealPlanAdoptionMember(
                actor_uid="owner", member_id=current.member, plan_date=date(2026, 10, 10), adoption_id=adoption_id
            )
        )
        session.add(
            HealthMealPlanAdoptionAction(
                id=str(uuid4()),
                adoption_id=adoption_id,
                actor_uid="owner",
                request_id=str(uuid4()),
                fingerprint="d" * 64,
                operation="adopt",
                version=1,
                reason="合成只读采用动作",
            )
        )
        await session.commit()
    async with sessions() as session:
        expected_counts = {
            HealthMealPlan: 64,
            HealthMealPlanRevision: 65,
            HealthQualityCheck: 1,
            HealthProfessionalReview: 1,
            HealthReviewAction: 1,
            HealthMealPlanAdoption: 1,
            HealthMealPlanAdoptionMember: 1,
            HealthMealPlanAdoptionAction: 1,
            AgentRun: 0,
            AgentRunRequest: 0,
            Message: 0,
        }
        current.seeded_counts = {}
        for model, expected in expected_counts.items():
            actual = await session.scalar(select(func.count()).select_from(model))
            assert actual == expected, (model.__tablename__, actual, expected)
            current.seeded_counts[model.__tablename__] = actual
    return current


async def read_page(current, *, actor="owner", member=None, params=None):
    """每次实际 TCP GET 前后回读全 schema 行与 xmin，拒绝任何业务写入。"""
    before = await schema_facts(current.sessions)
    path = f"{ROOT}/members/{member or current.member}/meal-plans"
    response = await current.client.get(path, headers=current.identities[actor], params=params)
    after = await schema_facts(current.sessions)
    unchanged = before == after
    current.evidence["requests"].append(
        {
            "actor": actor,
            "path": path,
            "params": params or {},
            "status": response.status_code,
            "response": response.json(),
            "pg_before_sha256": hashlib.sha256(json.dumps(before, sort_keys=True).encode()).hexdigest(),
            "pg_after_sha256": hashlib.sha256(json.dumps(after, sort_keys=True).encode()).hexdigest(),
            "all_rows_and_xmin_unchanged": unchanged,
        }
    )
    assert unchanged, "列表 GET 不得修改任何 schema 行、修订、审核、采用或运行事实"
    return response


def assert_page(response, expected_ids, *, truncated, next_offset):
    """用预先定义的序列与页状态核对公开协议。"""
    assert response.status_code == 200, response.text
    payload = response.json()
    assert [row["plan_id"] for row in payload["plans"]] == expected_ids, payload
    assert payload["truncated"] is truncated, payload
    assert payload["next_offset"] == next_offset, payload
    assert next_offset is None or type(payload["next_offset"]) is int, payload


async def revoke_grant(current, member_id, actor):
    """提交独立合成撤权事实，下一次请求必须从 PG 重查。"""
    async with current.sessions() as session:
        grant = await session.get(HealthGrant, (member_id, actor))
        grant.scopes = []
        grant.revoked_at = datetime(2026, 10, 10, 12)
        await session.commit()
    async with current.sessions() as session:
        grant = await session.get(HealthGrant, (member_id, actor))
        assert grant.scopes == [] and grant.revoked_at == datetime(2026, 10, 10, 12)


async def schema_facts(sessions):
    """全 schema 原始列与事务版本的独立 oracle，不调用被测查询。"""
    queries = [
        f"SELECT '{table.name}' AS table_name, "
        "COALESCE(jsonb_agg(jsonb_build_object('row', to_jsonb(t), 'xmin', t.xmin::text) "
        "ORDER BY to_jsonb(t)::text), '[]'::jsonb)::text AS facts "
        f'FROM "{table.name}" t'
        for table in Base.metadata.sorted_tables
    ]
    async with sessions() as session:
        result = await session.execute(text(" UNION ALL ".join(queries)))
        return dict(result.all())

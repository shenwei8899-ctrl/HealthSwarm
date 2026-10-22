"""独立 PostgreSQL、Redis 与真实 TCP 验证微信身份及家庭引导。"""

import asyncio
import ast
import importlib.util
import os
import socket
import sys
import time
import uuid
from collections import defaultdict, deque
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
import pytest_asyncio
import uvicorn
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from server.utils.auth_middleware import get_db
from yuxi.services import wechat_login_service as service
from yuxi.storage.postgres.models_business import Base, Department, FamilyArchive, User, WechatIdentity
from yuxi.storage.postgres import models_health  # noqa: F401 注册家庭健康表
from yuxi.storage.redis import close_async_redis_client
from yuxi.storage_migrations.v013_wechat_identity import upgrade_wechat_identity
from yuxi.utils.auth_utils import AuthUtils
from yuxi.utils.datetime_utils import utc_now_naive

pytestmark = pytest.mark.integration


@pytest.fixture(scope="session", autouse=True)
def ensure_live_api_schema():
    """本模块自行建立独立 schema 和 TCP 服务，不使用共享 API。"""


@pytest.fixture(scope="session", autouse=True)
def cleanup_test_sandboxes():
    """身份用例不创建沙盒；独立数据库资源由 environment 回收。"""
    yield


@pytest.fixture(scope="session", autouse=True)
def cleanup_test_knowledge_resources():
    """身份用例不创建知识库资源，不连接共享应用做清理。"""
    yield


def route_module(filename):
    """装配生产路由文件，避免无关知识库服务的 eager 包导入。"""
    path = Path(__file__).resolve().parents[3] / "server" / "routers" / filename
    name = "wechat_test_" + path.stem
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def production_login_middleware():
    """执行 shipping 入口原有节流代码，隔离无关 lifespan 与知识库导入。"""
    path = Path(__file__).resolve().parents[3] / "server" / "main.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names = {
        "RATE_LIMIT_MAX_ATTEMPTS",
        "RATE_LIMIT_WINDOW_SECONDS",
        "RATE_LIMIT_ENDPOINTS",
        "_login_attempts",
        "_attempt_lock",
        "_extract_client_ip",
        "LoginRateLimitMiddleware",
    }
    nodes = []
    for node in tree.body:
        if isinstance(node, (ast.ClassDef, ast.FunctionDef)) and node.name in names:
            nodes.append(node)
        elif isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id in names for t in node.targets):
            nodes.append(node)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id in names:
            nodes.append(node)
    namespace = {
        "asyncio": asyncio,
        "time": time,
        "defaultdict": defaultdict,
        "deque": deque,
        "Request": Request,
        "status": status,
        "JSONResponse": JSONResponse,
        "BaseHTTPMiddleware": BaseHTTPMiddleware,
    }
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), "exec"), namespace)
    return namespace["LoginRateLimitMiddleware"]


@pytest_asyncio.fixture
async def environment(monkeypatch):
    """只接入明确命名的独立测试库，运行实际路由和认证依赖。"""
    dsn = os.getenv("WECHAT_TEST_POSTGRES_URL", "")
    if not dsn:
        pytest.skip("WECHAT_TEST_POSTGRES_URL 未配置")
    if dsn.rsplit("/", 1)[-1] != "wechat_login_test":
        raise RuntimeError("微信验收只允许 wechat_login_test 独立数据库")
    if not os.getenv("WECHAT_TEST_REDIS_URL"):
        pytest.skip("WECHAT_TEST_REDIS_URL 未配置")
    monkeypatch.setenv("REDIS_URL", os.environ["WECHAT_TEST_REDIS_URL"])
    monkeypatch.setenv("JWT_SECRET_KEY", "synthetic-wechat-jwt-secret-000000000000")
    monkeypatch.setenv("YUXI_INSTANCE_ID", "synthetic-wechat-instance")
    monkeypatch.setenv("WECHAT_LOGIN_ENABLED", "true")
    monkeypatch.setenv("WECHAT_APP_ID", "wx1234567890abcdef")
    monkeypatch.setenv("WECHAT_APP_SECRET", "synthetic-server-secret")
    monkeypatch.setenv("WECHAT_AUTO_REGISTER", "true")
    schema = "wechat_test_" + uuid.uuid4().hex
    bootstrap = create_async_engine(dsn)
    async with bootstrap.begin() as conn:
        await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_async_engine(dsn, connect_args={"server_settings": {"search_path": schema}})
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(
            lambda sync: Base.metadata.create_all(
                sync, tables=[table for table in Base.metadata.sorted_tables if table.name != "wechat_identities"]
            )
        )
    async with engine.connect() as conn:
        assert await conn.scalar(text("SELECT to_regclass('wechat_identities')")) is None
    async with sessions() as db:
        department = Department(name="合成微信用户部门")
        db.add(department)
        await db.flush()
        dept_id = department.id
        for uid, role in (("synthetic-user", "user"), ("synthetic-other", "user"), ("synthetic-admin", "admin")):
            db.add(
                User(
                    uid=uid,
                    username=uid,
                    role=role,
                    department_id=dept_id,
                    password_hash=AuthUtils.hash_password("synthetic-password"),
                )
            )
        await db.commit()
    await upgrade_wechat_identity(SimpleNamespace(async_engine=engine))
    monkeypatch.setenv("WECHAT_USER_DEPARTMENT_ID", str(dept_id))

    async def exchange(settings, code):
        """唯一替身是外部微信供应商，不替换认证、数据库或家庭服务。"""
        if code == "invalid":
            raise HTTPException(401, {"code": "WECHAT_CODE_INVALID", "message": "凭证失效"})
        return "openid-" + code

    monkeypatch.setattr(service, "exchange_wechat_code", exchange)

    async def database():
        """每个 HTTP 请求使用真实、独立的数据库事务。"""
        async with sessions() as db:
            yield db

    app = FastAPI()
    app.add_middleware(production_login_middleware())
    app.include_router(route_module("wechat_auth_router.py").wechat_auth, prefix="/api")
    app.include_router(route_module("family_router.py").family, prefix="/api")
    app.dependency_overrides[get_db] = database
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    server = uvicorn.Server(uvicorn.Config(app, log_level="error", lifespan="off"))
    task = asyncio.create_task(server.serve(sockets=[listener]))
    try:
        for _ in range(200):
            if server.started:
                break
            if task.done():
                await task
            await asyncio.sleep(0.01)
        assert server.started
        async with httpx.AsyncClient(
            base_url=f"http://127.0.0.1:{listener.getsockname()[1]}", timeout=15, trust_env=False
        ) as client:
            yield client, sessions, monkeypatch, engine
    finally:
        server.should_exit = True
        await task
        await close_async_redis_client()
        await engine.dispose()
        async with bootstrap.begin() as conn:
            await conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
            assert (
                await conn.scalar(text("SELECT count(*) FROM pg_namespace WHERE nspname=:name"), {"name": schema}) == 0
            )
        await bootstrap.dispose()


async def login(client, code="new-user", **binding):
    """提交合成微信身份，返回实际协议响应。"""
    return await client.post("/api/auth/wechat/login", json={"code": code, **binding})


@pytest.mark.asyncio
async def test_first_login_repeat_and_concurrency_have_one_account_and_identity(environment):
    """并发 HTTP 完成后回读 PostgreSQL 确认没有重复用户和绑定。"""
    client, sessions, _, _ = environment
    responses = await asyncio.gather(*(login(client) for _ in range(4)))
    assert [r.status_code for r in responses] == [200] * 4, [r.json() for r in responses]
    ids = {r.json()["account"]["id"] for r in responses}
    assert len(ids) == 1
    assert all(r.json()["families"] == [] for r in responses)
    assert responses[0].headers["cache-control"] == "no-store"
    result = responses[0].json()
    assert "openid" not in result and "session_key" not in result
    claims = AuthUtils.verify_access_token(result["access_token"])
    assert claims["sub"] == str(result["account"]["id"])
    async with sessions() as db:
        assert await db.scalar(select(func.count()).select_from(WechatIdentity)) == 1
        assert await db.scalar(select(func.count()).select_from(User)) == 4
        assert await db.scalar(select(func.count()).select_from(FamilyArchive)) == 0
        user = await db.scalar(select(User).where(User.id == result["account"]["id"]))
        assert user.role == "user" and user.department_id is not None
        identity = await db.scalar(select(WechatIdentity))
        assert "openid-new-user" != identity.openid_hash and len(identity.openid_hash) == 64


@pytest.mark.asyncio
async def test_binding_requires_password_and_does_not_overwrite_existing_identity(environment):
    """错误密码无关联，正确密码关联既有普通账号，同账号第二微信拒绝。"""
    client, sessions, monkeypatch, _ = environment
    monkeypatch.setenv("WECHAT_AUTO_REGISTER", "false")
    unavailable = await login(client)
    assert unavailable.status_code == 503
    assert unavailable.json()["detail"]["code"] == "WECHAT_REGISTRATION_NOT_READY"
    bad = await login(client, identifier="synthetic-user", password="wrong")
    assert bad.status_code == 401
    async with sessions() as db:
        assert await db.scalar(select(func.count()).select_from(WechatIdentity)) == 0
    result = await login(client, identifier="synthetic-user", password="synthetic-password")
    assert result.status_code == 200 and result.json()["account"]["uid"] == "synthetic-user"
    second = await login(client, "another-wechat", identifier="synthetic-user", password="synthetic-password")
    assert second.status_code == 409
    wrong_account = await login(client, identifier="synthetic-other", password="synthetic-password")
    assert wrong_account.status_code == 409
    async with sessions() as db:
        assert await db.scalar(select(func.count()).select_from(WechatIdentity)) == 1


@pytest.mark.asyncio
async def test_unready_config_invalid_code_and_privileged_or_locked_binding_are_rejected(environment):
    """未配置和失效凭证不创建用户；管理员、锁定账号不获得会话。"""
    client, sessions, monkeypatch, _ = environment
    monkeypatch.setenv("WECHAT_LOGIN_ENABLED", "false")
    assert (await client.get("/api/auth/wechat/config")).json() == {"available": False, "appid": None}
    assert (await login(client)).status_code == 503
    monkeypatch.setenv("WECHAT_LOGIN_ENABLED", "true")
    assert (await login(client, "invalid")).status_code == 401
    admin = await login(client, identifier="synthetic-admin", password="synthetic-password")
    assert admin.status_code == 403
    async with sessions() as db:
        user = await db.scalar(select(User).where(User.uid == "synthetic-user"))
        user.login_locked_until = utc_now_naive() + timedelta(minutes=5)
        await db.commit()
    locked = await login(client, identifier="synthetic-user", password="synthetic-password")
    assert locked.status_code == 423
    async with sessions() as db:
        user = await db.scalar(select(User).where(User.uid == "synthetic-user"))
        original_lock = user.login_locked_until
        original_failures = user.login_failed_count
    assert (await login(client, identifier="synthetic-user", password="wrong")).status_code == 423
    async with sessions() as db:
        user = await db.scalar(select(User).where(User.uid == "synthetic-user"))
        assert user.login_locked_until == original_lock
        assert user.login_failed_count == original_failures
    monkeypatch.setenv("WECHAT_USER_DEPARTMENT_ID", "999999")
    assert (await login(client, "registration-unready")).status_code == 503
    async with sessions() as db:
        assert await db.scalar(select(func.count()).select_from(User)) == 3
        assert await db.scalar(select(func.count()).select_from(WechatIdentity)) == 0


@pytest.mark.asyncio
async def test_disabled_user_keeps_identity_and_old_session_is_rejected(environment):
    """软删除后的绑定继续占用身份，重新微信登录不能复活账号。"""
    client, sessions, _, _ = environment
    result = (await login(client)).json()
    async with sessions() as db:
        user = await db.scalar(select(User).where(User.id == result["account"]["id"]))
        user.is_deleted = 1
        await db.commit()
    assert (await login(client)).status_code == 403
    old = await client.get("/api/auth/wechat/session", headers={"Authorization": "Bearer " + result["access_token"]})
    assert old.status_code == 401
    async with sessions() as db:
        assert await db.scalar(select(func.count()).select_from(WechatIdentity)) == 1
        assert await db.scalar(select(func.count()).select_from(User)) == 4


@pytest.mark.asyncio
async def test_family_onboarding_persists_self_profile_and_enforces_cross_account_access(environment):
    """从真实登录到建档、确认和会话恢复，回读本人状态与授权边界。"""
    client, sessions, _, _ = environment
    result = (await login(client)).json()
    headers = {"Authorization": "Bearer " + result["access_token"]}
    created = await client.post("/api/family", json={"name": "合成家庭"}, headers=headers)
    assert created.status_code == 200
    family = created.json()
    repeated = await client.post("/api/family", json={"name": "合成家庭"}, headers=headers)
    assert repeated.json()["id"] == family["id"]
    member = next(m for m in family["members"] if m["is_self"])
    context = (await client.get("/api/auth/wechat/session", headers=headers)).json()
    assert context["families"][0]["onboarding_required"] is True
    profile = {
        "sex": "female",
        "birth_date": "1996-01-01",
        "height_cm": 165,
        "activity_level": "light",
        "goal": "规律饮食",
    }
    path = f"/api/family/{family['id']}/members/{member['id']}"
    saved = await client.put(path, headers=headers, json={"expected_version": member["version"], "profile": profile})
    assert saved.status_code == 200
    current = saved.json()
    assert current["ready"] is False and current["confirmed"] is False
    conflict = await client.put(path, headers=headers, json={"expected_version": member["version"], "profile": profile})
    assert conflict.status_code == 409
    confirmed = await client.post(path + "/confirm", headers=headers, json={"expected_version": current["version"]})
    assert confirmed.json()["ready"] is True
    restored = (await client.get("/api/auth/wechat/session", headers=headers)).json()
    assert restored["wechat_authenticated"] is True
    assert restored["families"][0]["onboarding_required"] is True
    dietary = {
        "healthStatus": "none",
        "allergyStatus": "none",
        "intoleranceStatus": "none",
        "avoidanceStatus": "none",
        "doctorStatus": "none",
        "goals": ["饮食均衡"],
        "tastePreferences": ["不限口味"],
        "cuisines": ["不限菜系"],
    }
    complete = await client.put(
        path, headers=headers, json={"expected_version": current["version"], "profile": {"dietary_details": dietary}}
    )
    assert complete.status_code == 200
    assert (
        await client.post(path + "/confirm", headers=headers, json={"expected_version": complete.json()["version"]})
    ).status_code == 200
    restored = (await client.get("/api/auth/wechat/session", headers=headers)).json()
    assert restored["families"][0]["onboarding_required"] is False
    stranger = (await login(client, "stranger")).json()
    denied = await client.get(
        "/api/family/" + family["id"], headers={"Authorization": "Bearer " + stranger["access_token"]}
    )
    assert denied.status_code == 404
    async with sessions() as db:
        assert await db.scalar(select(func.count()).select_from(FamilyArchive)) == 1


@pytest.mark.asyncio
async def test_migration_is_repeatable_and_constraints_preserve_existing_accounts(environment):
    """在已有用户表上重复正式迁移，约束阻止重复关联且账号保持原值。"""
    _, sessions, _, engine = environment
    async with sessions() as db:
        before = list((await db.execute(select(User.uid, User.role))).all())
    await upgrade_wechat_identity(SimpleNamespace(async_engine=engine))
    await upgrade_wechat_identity(SimpleNamespace(async_engine=engine))
    async with sessions() as db:
        after = list((await db.execute(select(User.uid, User.role))).all())
        assert before == after
        constraints = await db.scalars(
            text("SELECT conname FROM pg_constraint WHERE conrelid='wechat_identities'::regclass")
        )
        assert {"uq_wechat_app_identity", "uq_wechat_app_user"} <= set(constraints)


@pytest.mark.asyncio
async def test_production_attempt_limit_covers_unbound_wechat_login(environment):
    """未启用首次注册返回503仍消耗尝试次数，避免反复交换微信凭证。"""
    client, sessions, monkeypatch, _ = environment
    monkeypatch.setenv("WECHAT_AUTO_REGISTER", "false")
    for _ in range(10):
        assert (await login(client)).status_code == 503
    rejected = await login(client)
    assert rejected.status_code == 429 and int(rejected.headers["retry-after"]) > 0
    async with sessions() as db:
        assert await db.scalar(select(func.count()).select_from(WechatIdentity)) == 0

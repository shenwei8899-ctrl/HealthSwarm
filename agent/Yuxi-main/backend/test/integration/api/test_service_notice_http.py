"""独立 TCP/PostgreSQL 验证声明确认、账号隔离和注册事务。"""

import asyncio
import importlib.util
import os
from pathlib import Path
import socket
import sys
from contextlib import asynccontextmanager
from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import AsyncMock

from fastapi import FastAPI, HTTPException
import httpx
import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
import uvicorn

from server.utils.auth_middleware import get_db
from yuxi.services import wechat_login_service as login_service
from yuxi.services.service_notice_service import NOTICE_HASH, NOTICE_VERSION, require_service_notice
from yuxi.storage.postgres.models_business import (
    Base,
    Conversation,
    Department,
    Project,
    User,
    ServiceNoticeAcknowledgement,
)
from yuxi.storage_migrations.v017_service_notice import upgrade_service_notice
from yuxi.utils.auth_utils import AuthUtils

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.fixture(scope="session", autouse=True)
def ensure_live_api_schema():
    """测试自建数据库 schema，不连接共享 API。"""


@pytest.fixture(scope="session", autouse=True)
def cleanup_test_sandboxes():
    """本测试不创建沙盒。"""
    yield


@pytest.fixture(scope="session", autouse=True)
def cleanup_test_knowledge_resources():
    """本测试不创建知识库。"""
    yield


def route_module(filename):
    """装配真实生产路由而不初始化无关后台服务。"""
    path = Path(__file__).resolve().parents[3] / "server" / "routers" / filename
    spec = importlib.util.spec_from_file_location("notice_test_" + path.stem, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


async def test_notice_http_registration_and_account_isolation(monkeypatch):
    dsn = os.getenv("SERVICE_NOTICE_TEST_POSTGRES_URL", "")
    if not dsn:
        pytest.skip("SERVICE_NOTICE_TEST_POSTGRES_URL 未配置")
    if "@127.0.0.1:55442/" not in dsn or not dsn.endswith("/postgres"):
        raise RuntimeError("只允许本任务 55442 端口的独立 PostgreSQL")
    schema = "service_notice_test_" + uuid4().hex
    bootstrap = create_async_engine(dsn)
    async with bootstrap.begin() as connection:
        await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_async_engine(dsn, connect_args={"server_settings": {"search_path": schema}})
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    server, task = None, None
    try:
        async with engine.begin() as connection:
            await connection.run_sync(
                lambda sync: Base.metadata.create_all(
                    sync,
                    tables=[
                        table for table in Base.metadata.sorted_tables if table.name != "service_notice_acknowledgement"
                    ],
                )
            )
        async with sessions() as db:
            dept = Department(name="合成声明测试部门")
            db.add(dept)
            await db.flush()
            for uid in ("notice-account-a", "notice-account-b"):
                db.add(
                    User(
                        uid=uid,
                        username=uid,
                        role="user",
                        department_id=dept.id,
                        password_hash=AuthUtils.hash_password("synthetic-password"),
                    )
                )
            dept_id = dept.id
            await db.commit()
        # Existing accounts remain unconfirmed; repeated migration preserves them.
        await upgrade_service_notice(SimpleNamespace(async_engine=engine))
        await upgrade_service_notice(SimpleNamespace(async_engine=engine))
        async with sessions() as db:
            assert await db.scalar(select(func.count()).select_from(ServiceNoticeAcknowledgement)) == 0
        monkeypatch.setenv("YUXI_INSTANCE_ID", "synthetic-notice-instance")
        monkeypatch.setenv("JWT_SECRET_KEY", "synthetic-notice-jwt-secret-000000000000")
        monkeypatch.setenv("WECHAT_LOGIN_ENABLED", "true")
        monkeypatch.setenv("WECHAT_APP_ID", "wx1234567890abcdef")
        monkeypatch.setenv("WECHAT_APP_SECRET", "synthetic-secret")
        monkeypatch.setenv("WECHAT_AUTO_REGISTER", "true")
        monkeypatch.setenv("WECHAT_USER_DEPARTMENT_ID", str(dept_id))
        # Mint with the same server secret after setting the environment.
        async with sessions() as db:
            accounts = (await db.execute(select(User))).scalars().all()
            tokens = {user.uid: AuthUtils.create_access_token({"sub": str(user.id)}) for user in accounts}
        monkeypatch.setattr(
            login_service, "exchange_wechat_code", AsyncMock(side_effect=lambda settings, code: "openid-" + code)
        )
        monkeypatch.setattr(login_service, "check_login_rate_limit", AsyncMock(return_value=(True, 0)))
        monkeypatch.setattr(login_service, "clear_login_failures", AsyncMock())

        async def database():
            async with sessions() as db:
                yield db

        app = FastAPI()
        app.include_router(route_module("service_notice_router.py").service_notice, prefix="/api")
        app.include_router(route_module("wechat_auth_router.py").wechat_auth, prefix="/api")
        app.include_router(route_module("health_vision_router.py").health_vision, prefix="/api")
        app.dependency_overrides[get_db] = database
        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        server = uvicorn.Server(uvicorn.Config(app, lifespan="off", log_level="error"))
        task = asyncio.create_task(server.serve(sockets=[listener]))
        for _ in range(200):
            if server.started:
                break
            if task.done():
                await task
            await asyncio.sleep(0.01)
        assert server.started
        async with httpx.AsyncClient(
            base_url=f"http://127.0.0.1:{listener.getsockname()[1]}", trust_env=False
        ) as client:
            document = await client.get("/api/service-notice")
            assert document.status_code == 200 and len(document.json()["sections"]) == 3
            assert document.headers["cache-control"] == "no-store"
            assert (await client.post("/api/account/service-notice", json={})).status_code == 401
            receipt = {"version": NOTICE_VERSION, "content_hash": NOTICE_HASH, "acknowledged": True}
            headers_a = {"Authorization": "Bearer " + tokens["notice-account-a"]}
            headers_b = {"Authorization": "Bearer " + tokens["notice-account-b"]}
            assert (await client.get("/api/account/service-notice", headers=headers_a)).json()["acknowledged"] is False
            async with sessions() as db:
                with pytest.raises(HTTPException):
                    await require_service_notice(db, "notice-account-a")
            rejected = await client.post("/api/auth/wechat/login", json={"code": "missing"})
            assert rejected.status_code == 403 and rejected.json()["detail"]["code"] == "SERVICE_NOTICE_REQUIRED"
            stale = await client.post(
                "/api/auth/wechat/login", json={"code": "stale", "service_notice": {**receipt, "version": "old"}}
            )
            assert stale.status_code == 409
            async with sessions() as db:
                assert await db.scalar(select(func.count()).select_from(User)) == 2
            login = await client.post("/api/auth/wechat/login", json={"code": "new", "service_notice": receipt})
            assert login.status_code == 200, login.text
            assert login.json()["service_notice"]["acknowledged"] is True
            assert (
                await client.get(
                    "/api/auth/wechat/session", headers={"Authorization": "Bearer " + login.json()["access_token"]}
                )
            ).json()["service_notice"]["acknowledged"] is True
            confirmed = await client.post("/api/account/service-notice", headers=headers_a, json=receipt)
            assert confirmed.status_code == 200, confirmed.text
            replay = await client.post("/api/account/service-notice", headers=headers_a, json=receipt)
            assert replay.json()["acknowledged_at"] == confirmed.json()["acknowledged_at"]
            assert (await client.get("/api/account/service-notice", headers=headers_b)).json()["acknowledged"] is False
            assert (
                await client.post(
                    "/api/account/service-notice", headers=headers_b, json={**receipt, "actor_uid": "notice-account-a"}
                )
            ).status_code == 422
            assert (
                await client.post(
                    "/api/account/service-notice", headers=headers_b, json={**receipt, "acknowledged": False}
                )
            ).status_code == 422
            assert (
                await client.post(
                    "/api/account/service-notice", headers=headers_b, json={**receipt, "content_hash": "0" * 64}
                )
            ).status_code == 409
            async with sessions() as db:
                await require_service_notice(db, "notice-account-a")
                with pytest.raises(HTTPException):
                    await require_service_notice(db, "notice-account-b")
                rows = (await db.execute(select(ServiceNoticeAcknowledgement))).scalars().all()
                assert len(rows) == 2
                assert {row.actor_uid for row in rows} >= {"notice-account-a"}
                assert all(row.content_hash == NOTICE_HASH for row in rows)
            # The real chat-intent HTTP handler must reject before claim/model,
            # even for an existing thread and valid authenticated old account.
            from yuxi.services import health_consultation_service as consultation
            from yuxi.services import health_intent_router_service as intent
            from yuxi.storage.postgres.manager import pg_manager

            thread_id = str(uuid4())
            async with sessions() as db:
                db.add(
                    Project(
                        id="synthetic-project",
                        uid="notice-account-b",
                        name="合成声明测试项目",
                        selection_status="implicit",
                        directory_mode="managed",
                        workdir_path="projects/notice-test",
                        status="active",
                    )
                )
                await db.flush()
                conversation = Conversation(
                    thread_id=thread_id,
                    uid="notice-account-b",
                    agent_id="health-consultation",
                    title="合成旧会话",
                    project_id="synthetic-project",
                    extra_metadata={},
                )
                db.add(conversation)
                await db.commit()
                conversation_id = conversation.id

            @asynccontextmanager
            async def isolated_session():
                async with sessions() as db:
                    try:
                        yield db
                        await db.commit()
                    except BaseException:
                        await db.rollback()
                        raise

            monkeypatch.setattr(pg_manager, "get_async_session_context", isolated_session)
            monkeypatch.setattr(
                consultation,
                "require_consultation",
                AsyncMock(return_value=(SimpleNamespace(conversation_id=conversation_id), {})),
            )
            model = AsyncMock(side_effect=AssertionError("未确认不能调用模型"))
            monkeypatch.setattr(intent, "analyze_health_intent", model)
            denied = await client.post(
                "/api/health/v1/chat-intent",
                headers=headers_b,
                json={"text": "合成含糊问题", "thread_id": thread_id, "client_request_id": str(uuid4())},
            )
            assert denied.status_code == 403, denied.text
            assert denied.json()["detail"]["code"] == "SERVICE_NOTICE_REQUIRED"
            model.assert_not_awaited()
            async with sessions() as db:
                assert (await db.get(Conversation, conversation_id)).extra_metadata == {}

    finally:
        if server:
            server.should_exit = True
        if task:
            await task
        await engine.dispose()
        async with bootstrap.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await bootstrap.dispose()

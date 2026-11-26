"""独立 TCP/PostgreSQL 验证注册来源、真实建档和匿名账号隔离。"""

import asyncio
import importlib.util
import os
import socket
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
from test.integration.services.test_onboarding_preparation_http import (
    cleanup_test_sandboxes, cleanup_test_knowledge_resources, ensure_live_api_schema,
)  # noqa: F401

import pytest
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
import uvicorn

from server.utils.auth_middleware import get_db
from yuxi.services import wechat_login_service as login_service
from yuxi.services.service_notice_service import NOTICE_HASH, NOTICE_VERSION
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_business import Base, Department, FriendReferral, User
from yuxi.storage.postgres import models_health  # noqa: F401 注册全部关联表
from yuxi.utils.auth_utils import AuthUtils


def route_module(filename):
    """装配实际路由，避免无关服务启动。"""
    path = Path(__file__).resolve().parents[3] / "server/routers" / filename
    spec = importlib.util.spec_from_file_location("referral_test_" + path.stem, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.mark.asyncio
async def test_real_registration_profile_and_anonymous_records(monkeypatch):
    """外部微信与Redis限流替身不替代认证、档案保存或数据库。"""
    dsn = os.getenv("REFERRAL_TEST_POSTGRES_URL", "")
    if not dsn:
        pytest.skip("REFERRAL_TEST_POSTGRES_URL 未配置")
    if not dsn.endswith("/referral_test") or "@127.0.0.1:" not in dsn:
        raise RuntimeError("只允许本机显式端口的referral_test独立库")
    schema = "referral_http_" + uuid4().hex
    bootstrap = create_async_engine(dsn)
    async with bootstrap.begin() as connection:
        await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_async_engine(dsn, connect_args={"server_settings": {"search_path": schema}})
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    server = task = None
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        monkeypatch.setenv("JWT_SECRET_KEY", "synthetic-referral-jwt-secret-000000000")
        monkeypatch.setenv("API_KEY_DERIVATION_SECRET", "synthetic-referral-derive-secret-000000")
        monkeypatch.setenv("YUXI_INSTANCE_ID", "synthetic-referral-http")
        monkeypatch.setenv("WECHAT_LOGIN_ENABLED", "true")
        monkeypatch.setenv("WECHAT_APP_ID", "wx1234567890abcdef")
        monkeypatch.setenv("WECHAT_APP_SECRET", "synthetic-secret")
        monkeypatch.setenv("WECHAT_AUTO_REGISTER", "true")
        async with sessions.begin() as db:
            dept = Department(name="合成邀请验收")
            db.add(dept)
            await db.flush()
            inviter = User(uid="inviter", username="合成邀请人", department_id=dept.id, password_hash="synthetic")
            db.add(inviter)
            await db.flush()
            token = AuthUtils.create_access_token({"sub": str(inviter.id)})
            dept_id = dept.id
        monkeypatch.setenv("WECHAT_USER_DEPARTMENT_ID", str(dept_id))
        monkeypatch.setattr(
            login_service, "exchange_wechat_code", AsyncMock(side_effect=lambda settings, code: "openid-" + code)
        )
        monkeypatch.setattr(login_service, "check_login_rate_limit", AsyncMock(return_value=(True, 0)))
        monkeypatch.setattr(login_service, "clear_login_failures", AsyncMock())

        @asynccontextmanager
        async def context():
            async with sessions.begin() as db:
                yield db

        async def database():
            async with sessions() as db:
                yield db

        monkeypatch.setattr(pg_manager, "get_async_session_context", context)
        referral = route_module("referral_router.py")
        monkeypatch.setattr(
            referral,
            "get_async_redis_client",
            AsyncMock(return_value=type("Limiter", (), {"incr": AsyncMock(return_value=1), "expire": AsyncMock()})()),
        )
        app = FastAPI()
        for module, name in (
            ("wechat_auth_router.py", "wechat_auth"),
            ("family_router.py", "family"),
            ("daily_arrangement_router.py", "daily_arrangement"),
        ):
            app.include_router(getattr(route_module(module), name), prefix="/api")
        app.include_router(referral.referrals, prefix="/api")
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
            ih = {"Authorization": "Bearer " + token}
            assert (await client.get("/api/referrals/mine/records")).status_code == 401
            prepared = await client.post("/api/referrals/mine", headers=ih)
            assert prepared.status_code == 200, prepared.text
            code = prepared.json()["code"]
            resolved = await client.post("/api/referrals/resolve", json={"code": code, "channel": "share"})
            assert resolved.status_code == 200, resolved.text
            receipt = resolved.json()["receipt"]
            notice = {"version": NOTICE_VERSION, "content_hash": NOTICE_HASH, "acknowledged": True}
            payload = {"code": "new", "service_notice": notice, "referral_receipt": receipt}
            logged = await client.post("/api/auth/wechat/login", json=payload)
            assert logged.status_code == 200, logged.text
            uh = {"Authorization": "Bearer " + logged.json()["access_token"]}
            uid = logged.json()["account"]["uid"]
            assert (await client.get("/api/referrals/mine/records", headers=ih)).json()["total"] == 0
            family = await client.post("/api/family", json={"name": "合成家庭"}, headers=uh)
            assert family.status_code == 200, family.text
            fid = family.json()["id"]
            body = {
                "client_request_id": str(uuid4()),
                "family_version": family.json()["version"],
                "usage_mode": "个人使用",
                "default_diners": ["self"],
                "members": [
                    {
                        "client_ref": "self",
                        "name": "合成本人",
                        "relation": "本人",
                        "birth_date": "1995-01-01",
                        "sex": "female",
                        "height_cm": 165,
                        "weight_kg": 60,
                        "activity_level": "light",
                        "dietary": {
                            "healthStatus": "none",
                            "allergyStatus": "none",
                            "intoleranceStatus": "none",
                            "avoidanceStatus": "none",
                            "doctorStatus": "none",
                            "goals": ["饮食均衡"],
                            "cuisines": [],
                            "tastePreferences": ["不限口味"],
                        },
                    }
                ],
            }
            path = f"/api/family/{fid}/miniapp-profile"
            bad = await client.post(
                path, headers={**uh, "Idempotency-Key": body["client_request_id"]}, json={**body, "members": []}
            )
            assert bad.status_code == 422
            assert (await client.get("/api/referrals/mine/records", headers=ih)).json()["total"] == 0
            for _ in range(2):
                saved = await client.post(path, headers={**uh, "Idempotency-Key": body["client_request_id"]}, json=body)
                assert saved.status_code == 200, saved.text
            result = (await client.get("/api/referrals/mine/records", headers=ih)).json()
            assert result["total"] == 1 and result["items"][0]["label"] == "好友001"
            assert set(result["items"][0]) == {"label", "completed_at"}
            assert (await client.get("/api/referrals/mine/records", headers=uh)).json()["total"] == 0
            replay = await client.post("/api/auth/wechat/login", json=payload)
            assert replay.status_code == 200
            natural = await client.post("/api/auth/wechat/login", json={"code": "natural", "service_notice": notice})
            assert natural.status_code == 200, natural.text
            natural_again = await client.post("/api/auth/wechat/login", json={**payload, "code": "natural"})
            assert natural_again.status_code == 200
            malformed = await client.post(
                "/api/auth/wechat/login",
                json={**payload, "code": "malformed", "referral_receipt": "1000000." + "a" * 24 + ".share.é"},
            )
            assert malformed.status_code == 200, malformed.text
            async with sessions() as db:
                row = await db.get(FriendReferral, uid)
                assert row.inviter_uid == "inviter" and row.completed_at is not None and row.success_number == 1
                assert await db.get(FriendReferral, natural.json()["account"]["uid"]) is None
                assert await db.get(FriendReferral, malformed.json()["account"]["uid"]) is None
    finally:
        if server:
            server.should_exit = True
        if task:
            await task
        await engine.dispose()
        async with bootstrap.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await bootstrap.dispose()

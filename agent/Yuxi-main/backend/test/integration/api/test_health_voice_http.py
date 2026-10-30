"""真实TCP、JWT、隔离PostgreSQL和Redis验证语音输入接口。"""

import asyncio
import hashlib
import importlib.util
import os
import socket
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
import uvicorn
from fastapi import FastAPI
from sqlalchemy import insert, text, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from server.utils.auth_middleware import get_db
from yuxi.services import health_voice_service as service
from yuxi.storage.postgres.models_business import Department, User
from yuxi.storage.redis import close_async_redis_client, get_async_redis_client
from yuxi.utils.auth_utils import AuthUtils

pytestmark = pytest.mark.integration


@pytest.fixture(scope="session", autouse=True)
def ensure_live_api_schema():
    """本模块使用独立schema和TCP应用，不访问共享API。"""


@pytest.fixture(scope="session", autouse=True)
def cleanup_test_sandboxes():
    """此测试不创建沙盒。"""
    yield


@pytest.fixture(scope="session", autouse=True)
def cleanup_test_knowledge_resources():
    """此测试不创建知识库。"""
    yield


@pytest_asyncio.fixture
async def environment(monkeypatch):
    """装配生产路由、认证和存储，仅替换付费ASR调用。"""
    database_url = os.getenv("VOICE_TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("需要显式配置 VOICE_TEST_DATABASE_URL 指向隔离 PostgreSQL")
    schema = "voice_" + uuid4().hex
    engine = create_async_engine(database_url, connect_args={"options": f"-csearch_path={schema},public"})
    async with engine.begin() as connection:
        await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        await connection.run_sync(lambda sync: Department.__table__.create(sync))
        await connection.run_sync(lambda sync: User.__table__.create(sync))
        await connection.execute(insert(Department).values(id=1, name="语音测试"))
        for user_id in (1, 2):
            await connection.execute(
                insert(User).values(
                    id=user_id,
                    uid=f"{schema}-{user_id}",
                    username=f"voice-{user_id}",
                    password_hash="synthetic-unused",
                    department_id=1,
                )
            )
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    async def database():
        """生产认证读取独立数据库中的用户事实。"""
        async with sessions() as session:
            yield session

    path = Path(__file__).resolve().parents[3] / "server/routers/health_voice_router.py"
    spec = importlib.util.spec_from_file_location("voice_http_router", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    app = FastAPI()
    app.include_router(module.health_voice, prefix="/api")
    app.dependency_overrides[get_db] = database
    monkeypatch.setenv("HEALTH_ASR_ENABLED", "1")
    monkeypatch.setenv("HEALTH_ASR_SECRET_ID", "synthetic-id")
    monkeypatch.setenv("HEALTH_ASR_SECRET_KEY", "synthetic-key")
    calls = []
    entered, release = asyncio.Event(), asyncio.Event()
    release.set()

    async def provider(data):
        """合成识别结果允许控制并发，不向第三方发送音频。"""
        calls.append(data)
        entered.set()
        await release.wait()
        return "今天晚饭吃什么"

    monkeypatch.setattr(service, "recognize_pcm", provider)
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    server = uvicorn.Server(uvicorn.Config(app, log_level="error", lifespan="off"))
    running = asyncio.create_task(server.serve(sockets=[listener]))
    for attempt in range(100):
        if server.started:
            break
        await asyncio.sleep(0.02)
    assert server.started
    tokens = {user_id: AuthUtils.create_access_token({"sub": str(user_id)}) for user_id in (1, 2)}
    async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{listener.getsockname()[1]}") as client:
        yield client, tokens, calls, entered, release, schema, engine
    release.set()
    server.should_exit = True
    await running
    redis = await get_async_redis_client()
    for user_id in (1, 2):
        user_key = hashlib.sha256(f"{schema}-{user_id}".encode()).hexdigest()
        keys = [key async for key in redis.scan_iter(match=f"health:voice:{user_key}:*")]
        if keys:
            await redis.delete(*keys)
        await redis.delete(f"health:voice:rate:{user_key}")
    await close_async_redis_client()
    async with engine.begin() as connection:
        await connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
    await engine.dispose()


async def upload(client, token, request_id="voice-http-123", data=b"\1\0" * 8000):
    """通过TCP发送真实multipart文件和原请求键。"""
    return await client.post(
        "/api/health/v1/voice/transcriptions",
        headers={"Authorization": "Bearer " + token, "Idempotency-Key": request_id},
        data={"client_request_id": request_id, "format": "PCM", "sample_rate": "16000", "channels": "1"},
        files={"file": ("voice.pcm", data, "application/octet-stream")},
    )


async def test_auth_replay_conflict_and_account_isolation(environment):
    """失效身份拒绝；原录音可重放，跨用户不能命中别人的结果。"""
    client, tokens, calls, entered, release, schema, engine = environment
    assert (await upload(client, "invalid-token")).status_code == 401
    response = await upload(client, tokens[1])
    assert response.status_code == 200 and response.json()["text"] == "今天晚饭吃什么"
    assert response.headers["Cache-Control"] == "no-store"
    assert (await upload(client, tokens[1])).json() == response.json()
    assert len(calls) == 1
    conflict = await upload(client, tokens[1], data=b"\2\0" * 8000)
    assert conflict.status_code == 409 and conflict.json()["detail"]["code"] == "VOICE_REQUEST_CONFLICT"
    assert (await upload(client, tokens[2])).status_code == 200
    assert len(calls) == 2
    redis = await get_async_redis_client()
    user_key = hashlib.sha256(f"{schema}-1".encode()).hexdigest()
    cached = await redis.get(f"health:voice:{user_key}:voice-http-123")
    assert "今天晚饭吃什么" in cached and "Data" not in cached
    assert 0 < await redis.ttl(f"health:voice:{user_key}:voice-http-123") <= 300
    async with engine.begin() as connection:
        await connection.execute(update(User).where(User.id == 1).values(is_deleted=1))
    assert (await upload(client, tokens[1])).status_code == 401
    assert len(calls) == 2


async def test_concurrent_request_upload_bounds_and_rate_limit(environment):
    """并发请求只识别一次；大文件和超频请求不调用供应商。"""
    client, tokens, calls, entered, release, schema, engine = environment
    release.clear()
    pending = asyncio.create_task(upload(client, tokens[1]))
    await asyncio.wait_for(entered.wait(), 5)
    duplicate = await upload(client, tokens[1])
    assert duplicate.status_code == 409 and duplicate.json()["detail"]["code"] == "VOICE_IN_PROGRESS"
    release.set()
    assert (await pending).status_code == 200 and len(calls) == 1
    assert (await upload(client, tokens[1], data=b"\0" * (service.MAX_AUDIO_BYTES + 2))).status_code == 413
    assert (await upload(client, tokens[1], data=b"\0" * (service.MAX_AUDIO_BYTES + 16385))).status_code == 413
    for index in range(9):
        assert (await upload(client, tokens[1], request_id=f"voice-other-{index}")).status_code == 200
    assert (await upload(client, tokens[1], request_id="voice-too-many")).status_code == 429
    assert len(calls) == 10


async def test_readiness_request_key_and_failure_retry(environment, monkeypatch):
    """未配置、请求键不符和供应商失败不能成为成功结果。"""
    client, tokens, calls, entered, release, schema, engine = environment
    configuration = await client.get(
        "/api/health/v1/voice/configuration", headers={"Authorization": "Bearer " + tokens[1]}
    )
    assert configuration.json() == {"available": True, "processor": "腾讯云语音识别", "max_seconds": 60}
    monkeypatch.setenv("HEALTH_ASR_ENABLED", "0")
    assert (await upload(client, tokens[1])).status_code == 503
    assert calls == []
    monkeypatch.setenv("HEALTH_ASR_ENABLED", "1")
    mismatch = await client.post(
        "/api/health/v1/voice/transcriptions",
        headers={"Authorization": "Bearer " + tokens[1], "Idempotency-Key": "wrong-key"},
        data={"client_request_id": "voice-http-123", "format": "PCM", "sample_rate": "16000", "channels": "1"},
        files={"file": ("voice.pcm", b"\1\0" * 8000)},
    )
    assert mismatch.status_code == 400 and calls == []

    async def unavailable(data):
        """模拟供应商暂时故障。"""
        raise service.VoiceError("VOICE_PROVIDER_UNAVAILABLE", "暂时不可用", 502)

    original = service.recognize_pcm
    monkeypatch.setattr(service, "recognize_pcm", unavailable)
    assert (await upload(client, tokens[1])).status_code == 502
    monkeypatch.setattr(service, "recognize_pcm", original)
    assert (await upload(client, tokens[1])).status_code == 200 and len(calls) == 1

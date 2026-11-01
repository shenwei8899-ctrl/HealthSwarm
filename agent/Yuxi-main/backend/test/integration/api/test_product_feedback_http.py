"""真实 PostgreSQL、MinIO 与 TCP HTTP 验证产品反馈。"""

import asyncio
import importlib.util
import os
import socket
import sys
import uuid
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
import pytest_asyncio
import uvicorn
from fastapi import FastAPI
from PIL import Image
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from server.utils.auth_middleware import get_db
from yuxi.services import product_feedback_service as service
from yuxi.storage.minio.client import MinIOClient
from yuxi.storage.postgres.models_business import Department, ProductFeedback, User
from yuxi.storage_migrations.v014_product_feedback import upgrade_product_feedback
from yuxi.utils.auth_utils import AuthUtils

pytestmark = pytest.mark.integration


@pytest.fixture(scope="session", autouse=True)
def ensure_live_api_schema():
    """本模块只接入独立 schema，不要求共享 API。"""


@pytest.fixture(scope="session", autouse=True)
def cleanup_test_sandboxes():
    """本测试不使用共享 API 沙盒。"""
    yield


@pytest.fixture(scope="session", autouse=True)
def cleanup_test_knowledge_resources():
    """本测试不创建知识库。"""
    yield


def production_router():
    """装配实际协议文件，隔离无关 Agent 路由导入。"""
    path = Path(__file__).resolve().parents[3] / "server/routers/product_feedback_router.py"
    spec = importlib.util.spec_from_file_location("feedback_test_router", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.product_feedback


@pytest_asyncio.fixture
async def environment(monkeypatch):
    """每个测试独占数据库 schema、私有测试桶和真实 TCP 服务。"""
    dsn = os.getenv("PRODUCT_FEEDBACK_TEST_POSTGRES_URL", "")
    if not dsn or not os.getenv("MINIO_URI"):
        pytest.skip("独立 PostgreSQL 与 MinIO 测试服务未配置")
    if dsn.rsplit("/", 1)[-1] != "product_feedback_test":
        raise RuntimeError("仅允许 product_feedback_test 测试数据库")
    monkeypatch.setenv("JWT_SECRET_KEY", "synthetic-feedback-jwt-secret-000000000000")
    monkeypatch.setenv("YUXI_INSTANCE_ID", "synthetic-feedback-instance")
    schema = "feedback_test_" + uuid.uuid4().hex
    bucket = "feedback-test-" + uuid.uuid4().hex
    monkeypatch.setattr(service, "FEEDBACK_BUCKET", bucket)
    bootstrap = create_async_engine(dsn)
    async with bootstrap.begin() as connection:
        await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_async_engine(dsn, connect_args={"server_settings": {"search_path": schema}})
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        for table in [Department.__table__, User.__table__]:
            await connection.run_sync(lambda sync, table=table: table.create(sync))
    manager = SimpleNamespace(async_engine=engine)
    await upgrade_product_feedback(manager)
    await upgrade_product_feedback(manager)
    tokens = {}
    async with sessions() as db:
        department = Department(name="合成反馈测试部门")
        db.add(department)
        await db.flush()
        for name, role in [("owner", "user"), ("other", "user"), ("admin", "admin")]:
            user = User(
                uid="feedback-" + name,
                username=name,
                role=role,
                department_id=department.id,
                password_hash="synthetic-unused",
            )
            db.add(user)
            await db.flush()
            tokens[name] = {"Authorization": "Bearer " + AuthUtils.create_access_token({"sub": str(user.id)})}
        await db.commit()

    async def database():
        """每次 HTTP 请求使用独立的真实事务。"""
        async with sessions() as db:
            yield db

    app = FastAPI()
    app.include_router(production_router(), prefix="/api")
    app.dependency_overrides[get_db] = database
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    server = uvicorn.Server(uvicorn.Config(app, log_level="error", lifespan="off"))
    task = asyncio.create_task(server.serve(sockets=[listener]))
    storage = MinIOClient()
    try:
        for _ in range(200):
            if server.started:
                break
            if task.done():
                await task
            await asyncio.sleep(0.01)
        assert server.started
        async with httpx.AsyncClient(
            base_url=f"http://127.0.0.1:{listener.getsockname()[1]}", timeout=30, trust_env=False
        ) as client:
            yield SimpleNamespace(
                client=client, tokens=tokens, sessions=sessions, engine=engine, storage=storage, bucket=bucket
            )
    finally:
        server.should_exit = True
        await task
        if await asyncio.to_thread(storage.client.bucket_exists, bucket):
            objects = await asyncio.to_thread(lambda: list(storage.client.list_objects(bucket, recursive=True)))
            for item in objects:
                await storage.adelete_file(bucket, item.object_name)
            await asyncio.to_thread(storage.client.remove_bucket, bucket)
        await engine.dispose()
        async with bootstrap.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
            assert (
                await connection.scalar(text("SELECT count(*) FROM pg_namespace WHERE nspname=:n"), {"n": schema}) == 0
            )
        await bootstrap.dispose()


async def test_concurrent_submit_is_persisted_once_and_rejects_changed_replay(environment):
    """并发提交后重新读取数据库，验证幂等与内容冲突。"""
    e = environment
    payload = {"id": str(uuid.uuid4()), "content": "希望增加字号设置", "image_ids": []}
    results = await asyncio.gather(
        *[e.client.post("/api/product-feedback", json=payload, headers=e.tokens["owner"]) for _ in range(4)]
    )
    assert [response.status_code for response in results] == [200] * 4, [r.text for r in results]
    assert len({response.json()["submitted_at"] for response in results}) == 1
    async with e.sessions() as db:
        assert await db.scalar(select(func.count()).select_from(ProductFeedback)) == 1
        row = await db.get(ProductFeedback, payload["id"])
        assert row.content == payload["content"] and row.status == "submitted"
    changed = await e.client.post(
        "/api/product-feedback", json={**payload, "content": "另一条建议"}, headers=e.tokens["owner"]
    )
    assert changed.status_code == 409


async def test_private_images_persist_and_require_owner_or_admin(environment):
    """真实对象回读、重复上传及跨账号访问通过实际路由验证。"""
    e = environment
    feedback_id = str(uuid.uuid4())
    data = BytesIO()
    Image.new("RGB", (40, 30), "blue").save(data, format="PNG")
    path = f"/api/product-feedback/{feedback_id}/images/0"
    upload = await e.client.post(
        path, files={"file": ("image.png", data.getvalue(), "image/png")}, headers=e.tokens["owner"]
    )
    assert upload.status_code == 200, upload.text
    replay = await e.client.post(
        path, files={"file": ("image.png", data.getvalue(), "image/png")}, headers=e.tokens["owner"]
    )
    assert replay.json() == upload.json()
    payload = {"id": feedback_id, "content": "图片加载异常", "image_ids": [upload.json()["upload_id"]]}
    saved = await e.client.post("/api/product-feedback", json=payload, headers=e.tokens["owner"])
    assert saved.status_code == 200, saved.text
    image_path = saved.json()["images"][0]["path"]
    own = await e.client.get(image_path, headers=e.tokens["owner"])
    assert own.status_code == 200 and own.headers["cache-control"] == "private, no-store"
    assert Image.open(BytesIO(own.content)).size == (40, 30)
    assert (await e.client.get(image_path, headers=e.tokens["other"])).status_code == 404
    assert (await e.client.get(image_path)).status_code == 401
    assert (await e.client.get(image_path, headers=e.tokens["admin"])).status_code == 200
    objects = await asyncio.to_thread(lambda: list(e.storage.client.list_objects(e.bucket, recursive=True)))
    assert len(objects) == 1
    stored = await e.storage.adownload_file(e.bucket, objects[0].object_name)
    assert stored == own.content
    with pytest.raises(Exception) as policy:
        await asyncio.to_thread(e.storage.client.get_bucket_policy, e.bucket)
    assert getattr(policy.value, "code", None) == "NoSuchBucketPolicy"
    listed = await e.client.get("/api/product-feedback", headers=e.tokens["admin"])
    assert len(listed.json()["items"]) == 1
    assert (await e.client.get("/api/product-feedback", headers=e.tokens["owner"])).status_code == 403


async def test_bad_content_images_and_foreign_receipts_do_not_submit(environment):
    """错误输入与其他账号编号在产生有效提交之前失败。"""
    e = environment
    feedback_id = str(uuid.uuid4())
    for content in ["  ", "文" * 201]:
        result = await e.client.post(
            "/api/product-feedback", json={"id": feedback_id, "content": content}, headers=e.tokens["owner"]
        )
        assert result.status_code == 422
    for slot in [0, 3]:
        invalid = await e.client.post(
            f"/api/product-feedback/{feedback_id}/images/{slot}",
            files={"file": ("fake.png", b"fake-image", "image/png")},
            headers=e.tokens["owner"],
        )
        assert invalid.status_code == 422
    mismatch = await e.client.post(
        "/api/product-feedback",
        json={"id": feedback_id, "content": "建议", "image_ids": [str(uuid.uuid4())]},
        headers=e.tokens["owner"],
    )
    assert mismatch.status_code == 422
    async with e.sessions() as db:
        assert (
            await db.scalar(
                select(func.count()).select_from(ProductFeedback).where(ProductFeedback.status == "submitted")
            )
            == 0
        )
    payload = {"id": feedback_id, "content": "建议"}
    assert (await e.client.post("/api/product-feedback", json=payload, headers=e.tokens["owner"])).status_code == 200
    assert (await e.client.post("/api/product-feedback", json=payload, headers=e.tokens["other"])).status_code == 404

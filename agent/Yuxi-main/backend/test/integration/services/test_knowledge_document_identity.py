"""使用真实 PostgreSQL 验证知识文档新增的全局身份与冲突隔离。"""

from __future__ import annotations

import asyncio
import os
import re
import socket
from types import MethodType, SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import httpx
import pytest
import uvicorn
from fastapi import FastAPI
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from yuxi.knowledge.base import KnowledgeBase
from yuxi.knowledge.utils import kb_utils
from yuxi.repositories import knowledge_file_repository as repository_module
from yuxi.repositories import knowledge_base_repository as base_repository_module
from yuxi.repositories.knowledge_file_repository import KnowledgeFileRepository
from yuxi.storage.postgres.manager import PostgresManager
from yuxi.storage.postgres.models_knowledge import KnowledgeBase as KnowledgeBaseRecord
from yuxi.storage.postgres.models_knowledge import KnowledgeChunk, KnowledgeFile

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


@pytest.fixture(scope="session", autouse=True)
def ensure_live_api_schema():
    """测试只创建隔离 Schema，不依赖 API 业务 Schema。"""


@pytest.fixture(scope="session", autouse=True)
def cleanup_test_knowledge_resources():
    """本文件没有需要通过 HTTP 清理的知识资源。"""
    yield


@pytest.fixture(scope="session", autouse=True)
def cleanup_test_sandboxes():
    """本文件不创建沙盒。"""
    yield


@pytest.fixture
def knowledge():
    """绑定真实基类持久化方法，使回退到旧 upsert 路径也能触发覆盖反例。"""
    owner = SimpleNamespace(_file_meta_to_record_data=KnowledgeBase._file_meta_to_record_data)
    owner._persist_file_meta = MethodType(KnowledgeBase._persist_file_meta, owner)
    return owner


@pytest.fixture
async def document_schema(monkeypatch):
    """将真实 repository 连接到独立 Schema，结束时只清理该 Schema。"""
    schema = f"pytest_document_identity_{uuid4().hex[:16]}"
    admin_engine = create_async_engine(os.environ["POSTGRES_URL"], pool_pre_ping=True)
    async with admin_engine.begin() as connection:
        await connection.execute(text(f'CREATE SCHEMA "{schema}"'))

    scoped_engine = create_async_engine(
        os.environ["POSTGRES_URL"],
        pool_pre_ping=True,
        connect_args={"server_settings": {"search_path": schema}},
    )
    manager = object.__new__(PostgresManager)
    PostgresManager.__init__(manager)
    manager.async_engine = scoped_engine
    manager.AsyncSession = async_sessionmaker(scoped_engine, class_=AsyncSession, expire_on_commit=False)
    manager._initialized = True
    monkeypatch.setattr(repository_module, "pg_manager", manager)
    monkeypatch.setattr(base_repository_module, "pg_manager", manager)

    try:
        async with scoped_engine.begin() as connection:
            for table in (KnowledgeBaseRecord.__table__, KnowledgeFile.__table__, KnowledgeChunk.__table__):
                await connection.run_sync(table.create)
        async with manager.get_async_session_context() as session:
            session.add_all(
                KnowledgeBaseRecord(kb_id=kb_id, name=kb_id, kb_type="milvus") for kb_id in ("kb-a", "kb-b")
            )
        yield manager
    finally:
        await scoped_engine.dispose()
        async with admin_engine.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        await admin_engine.dispose()


@pytest.fixture
async def document_http(document_schema, monkeypatch, tmp_path):
    """运行真实 HTTP 路由和管理器，只隔离认证、Milvus 连接与 Redis 缓存。"""
    from server.routers import knowledge_router
    from yuxi.knowledge import cache as cache_module
    from yuxi.knowledge.implementations.milvus import MilvusKB
    from yuxi.knowledge.manager import KnowledgeBaseManager
    from yuxi.storage import redis as redis_module

    cache = SimpleNamespace(
        get=AsyncMock(return_value=None),
        set=AsyncMock(return_value=True),
        lock=lambda *args, **kwargs: asyncio.Lock(),
    )
    cache_client = AsyncMock(return_value=cache)
    monkeypatch.setattr(redis_module, "get_async_redis_client", cache_client)
    monkeypatch.setattr(cache_module, "get_async_redis_client", cache_client)
    monkeypatch.setattr(MilvusKB, "_init_connection", lambda self: None)
    manager = KnowledgeBaseManager(str(tmp_path))
    monkeypatch.setattr(knowledge_router, "knowledge_base", manager)
    app = FastAPI()
    app.include_router(knowledge_router.knowledge, prefix="/api")
    app.dependency_overrides[knowledge_router.require_knowledge_base_manage] = lambda: SimpleNamespace(
        uid="identity-tester"
    )
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        server = uvicorn.Server(uvicorn.Config(app, lifespan="off", log_level="error"))
        serving = asyncio.create_task(server.serve(sockets=[listener]))
        try:
            async with asyncio.timeout(10):
                while not server.started:
                    if serving.done():
                        serving.result()
                    await asyncio.sleep(0.01)
            async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{listener.getsockname()[1]}") as client:
                yield client
        finally:
            server.should_exit = True
            await asyncio.wait_for(serving, timeout=10)


async def test_same_named_concurrent_adds_create_distinct_documents(document_schema, knowledge):
    """相同来源路径的并发新增各自得到长 ID，并实际持久化两条记录。"""
    item = "minio://knowledgebases/kb-a/upload/same.md"
    records = await asyncio.gather(
        *(
            KnowledgeBase.add_file_record(
                knowledge,
                "kb-a",
                item,
                params={"content_hashes": {item: "a" * 64}, "file_sizes": {item: 12}},
                additional_params={},
            )
            for _ in range(2)
        )
    )

    assert len({record["file_id"] for record in records}) == 2
    assert all(re.fullmatch(r"file_[0-9a-f]{32}", record["file_id"]) for record in records)
    async with document_schema.get_async_session_context() as session:
        persisted = (await session.scalars(select(KnowledgeFile))).all()
        assert {row.file_id for row in persisted} == {record["file_id"] for record in records}
        assert all(row.path == item and row.content_hash == "a" * 64 and row.filename == "same.md" for row in persisted)


@pytest.mark.parametrize("target_kb", ["kb-a", "kb-b"])
async def test_add_collision_preserves_existing_file_and_chunks(document_schema, knowledge, monkeypatch, target_kb):
    """同库或跨库新增撞到全局 ID 时，原文件全字段和 Chunk 保持原值。"""
    fixed_uuid = UUID("12345678-1234-4234-8234-123456789abc")
    file_id = f"file_{fixed_uuid.hex}"
    repo = KnowledgeFileRepository()
    await repo.create(file_id, _file_data("kb-a", "original"))
    async with document_schema.get_async_session_context() as session:
        session.add(
            KnowledgeChunk(
                chunk_id=f"{file_id}_chunk_0",
                file_id=file_id,
                kb_id="kb-a",
                chunk_index=0,
                content="原文不可被冲突写入覆盖\nquantity: 250 g",
            )
        )
    before = await _snapshot(document_schema)
    monkeypatch.setattr(kb_utils, "uuid4", lambda: fixed_uuid)
    item = f"minio://knowledgebases/{target_kb}/upload/replacement.md"

    with pytest.raises(IntegrityError):
        await KnowledgeBase.add_file_record(
            knowledge,
            target_kb,
            item,
            params={"content_hashes": {item: "b" * 64}, "file_sizes": {item: 99}},
            operator_id="replacement-owner",
            additional_params={},
        )

    assert await _snapshot(document_schema) == before


async def test_concurrent_insert_same_id_has_one_winner_without_overwrite(document_schema):
    """两个事务并发插入同一全局 ID 时仅一个提交，失败事务不能改写胜者。"""
    repo = KnowledgeFileRepository()
    file_id = f"file_{uuid4().hex}"
    payloads = [_file_data("kb-a", "first"), _file_data("kb-b", "second")]
    results = await asyncio.gather(*(repo.create(file_id, data) for data in payloads), return_exceptions=True)

    assert sum(isinstance(result, IntegrityError) for result in results) == 1
    assert sum(isinstance(result, KnowledgeFile) for result in results) == 1
    winner_index = next(index for index, result in enumerate(results) if isinstance(result, KnowledgeFile))
    persisted = await repo.get_by_file_id(file_id)
    assert all(getattr(persisted, key) == value for key, value in payloads[winner_index].items())
    before = await _snapshot(document_schema)
    with pytest.raises(IntegrityError):
        await repo.create(file_id, payloads[1 - winner_index])
    assert await _snapshot(document_schema) == before


@pytest.mark.parametrize("file_id", ["file_aaaaaa", "file_12345678123442348234123456789abc"])
async def test_existing_short_and_long_ids_keep_legal_updates(document_schema, file_id):
    """短 ID 和长 ID 均可沿用合法 upsert、解析和索引状态更新。"""
    repo = KnowledgeFileRepository()
    await repo.upsert(file_id, _file_data("kb-a", "original"))
    await repo.upsert(file_id, {"status": "parsed", "markdown_file": "minio://knowledgebases/kb-a/parsed/result.md"})
    parsed = await repo.get_by_file_id(file_id)
    assert parsed.status == "parsed"
    assert parsed.markdown_file == "minio://knowledgebases/kb-a/parsed/result.md"
    assert await repo.update_fields(file_id=file_id, kb_id="kb-b", data={"status": "indexed"}) is None
    await repo.update_fields(file_id=file_id, kb_id="kb-a", data={"status": "indexed", "chunk_count": 3})

    indexed = await repo.get_by_file_id(file_id)
    assert indexed.status == "indexed"
    assert indexed.chunk_count == 3
    assert indexed.kb_id == "kb-a"
    assert indexed.path == _file_data("kb-a", "original")["path"]
    assert indexed.content_hash == "a" * 64
    assert indexed.markdown_file == parsed.markdown_file


async def test_http_same_named_adds_persist_distinct_long_ids(document_schema, document_http):
    """真实文档添加 HTTP 入口返回两个长 ID，随后读库核对原始元数据。"""
    item = "minio://knowledgebases/kb-a/upload/same.md"
    response = await document_http.post(
        "/api/knowledge/databases/kb-a/documents/add",
        json={
            "items": [item, item],
            "params": {"content_hashes": {item: "a" * 64}, "file_sizes": {item: 12}, "auto_index": False},
        },
    )
    assert response.status_code == 200, response.text
    result = response.json()
    assert (result["status"], result["added"], result["failed"]) == ("success", 2, 0)
    ids = {item["file_id"] for item in result["items"]}
    assert len(ids) == 2
    assert all(re.fullmatch(r"file_[0-9a-f]{32}", file_id) for file_id in ids)
    async with document_schema.get_async_session_context() as session:
        persisted = (await session.scalars(select(KnowledgeFile))).all()
        assert {row.file_id for row in persisted} == ids
        assert all(
            row.kb_id == "kb-a"
            and row.path == item
            and row.content_hash == "a" * 64
            and row.filename == "same.md"
            and row.status == "uploaded"
            and row.file_size == 12
            and row.created_by == "identity-tester"
            for row in persisted
        )


@pytest.mark.parametrize("target_kb", ["kb-a", "kb-b"])
async def test_http_add_collision_reports_failure_and_preserves_original(
    document_schema, document_http, monkeypatch, target_kb
):
    """同库及跨库撞 ID 以逐项失败返回，HTTP 调用不能覆盖原文档和 Chunk。"""
    fixed_uuid = UUID("12345678-1234-4234-8234-123456789abc")
    file_id = f"file_{fixed_uuid.hex}"
    await KnowledgeFileRepository().create(file_id, _file_data("kb-a", "original"))
    async with document_schema.get_async_session_context() as session:
        session.add(
            KnowledgeChunk(
                chunk_id=f"{file_id}_chunk_0",
                file_id=file_id,
                kb_id="kb-a",
                chunk_index=0,
                content="原文不可被 HTTP 冲突覆盖\nquantity: 250 g",
            )
        )
    before = await _snapshot(document_schema)
    monkeypatch.setattr(kb_utils, "uuid4", lambda: fixed_uuid)
    item = f"minio://knowledgebases/{target_kb}/upload/replacement.md"
    response = await document_http.post(
        f"/api/knowledge/databases/{target_kb}/documents/add",
        json={
            "items": [item],
            "params": {"content_hashes": {item: "b" * 64}, "file_sizes": {item: 99}, "auto_index": False},
        },
    )
    assert response.status_code == 200, response.text
    result = response.json()
    assert (result["status"], result["added"], result["failed"]) == ("failed", 0, 1)
    assert result["items"] == []
    assert result["failed_items"][0]["error_type"] == "add_failed"
    assert await _snapshot(document_schema) == before


def _file_data(kb_id: str, name: str) -> dict:
    """构造字段彼此可区分的合成文档，便于发现部分覆盖。"""
    return {
        "kb_id": kb_id,
        "filename": f"{name}.md",
        "path": f"minio://knowledgebases/{kb_id}/upload/{name}.md",
        "content_hash": "a" * 64 if name == "original" else name.ljust(64, "b"),
        "markdown_file": f"minio://knowledgebases/{kb_id}/parsed/{name}.md",
        "chunk_count": 1,
        "file_size": 12,
        "status": "indexed",
    }


async def _snapshot(manager) -> dict:
    """重新读库并比较所有持久化字段，包含 Chunk 正文与文件归属。"""
    async with manager.get_async_session_context() as session:
        return {
            table.name: [dict(row) for row in (await session.execute(select(table).order_by(table.c.id))).mappings()]
            for table in (KnowledgeFile.__table__, KnowledgeChunk.__table__)
        }

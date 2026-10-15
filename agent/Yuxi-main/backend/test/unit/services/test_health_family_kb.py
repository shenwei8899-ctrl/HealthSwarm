"""固定家庭库的一般科普来源不能绕过成员 Run 与当前分片。"""

import json
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID

import pytest

from yuxi.knowledge.implementations.milvus import OrphanedMilvusHitsError
from yuxi.services import health_family_kb_service as service
from yuxi.services.health_vision_types import HealthVisionError

KB_ID = "kb-synthetic-family"


def _source_records():
    file = SimpleNamespace(
        file_id="file-1",
        filename="合成家庭营养资料.md",
        status="indexed",
        content_hash="file-digest",
        updated_at=datetime(2026, 10, 14, tzinfo=UTC),
    )
    chunk = SimpleNamespace(chunk_id="chunk-1", file_id="file-1", content="一般营养概念。")
    return file, chunk


def _payload(source):
    return {
        "status": "ok",
        "scope": "general_education",
        "query": "一般营养",
        "kb_id": KB_ID,
        "sources": [source],
    }


@pytest.mark.asyncio
async def test_search_uses_fixed_id_and_fresh_pg_content(monkeypatch):
    """Milvus 命中须匹配 PG 当前 indexed 文件和真实分片才送模型。"""
    monkeypatch.setenv(service.KB_ID_ENV, KB_ID)
    file, chunk = _source_records()
    session = SimpleNamespace(scalar=AsyncMock(side_effect=[chunk, file]))

    @asynccontextmanager
    async def session_context():
        yield session

    monkeypatch.setattr(service.pg_manager, "get_async_session_context", session_context)
    auth = AsyncMock(return_value=(SimpleNamespace(agent_slug="health-consultation"), SimpleNamespace()))
    monkeypatch.setattr(service, "_authorized_run", auth)
    monkeypatch.setattr(service, "_require_fixed_kb", AsyncMock())
    retrieve = AsyncMock(
        return_value={
            "kb_id": KB_ID,
            "results": [
                {"id": chunk.chunk_id, "file_id": file.file_id, "kb_id": KB_ID, "content": chunk.content},
                {"id": "wrong", "file_id": file.file_id, "kb_id": "other", "content": "private"},
            ],
        }
    )
    monkeypatch.setattr(service.knowledge_base, "retrieve", retrieve)

    result = await service.search_family_nutrition_knowledge(SimpleNamespace(), "一般营养")
    retrieve.assert_awaited_once_with(
        KB_ID,
        "一般营养",
        final_top_k=service.MAX_SOURCES,
        search_mode="keyword",
        use_reranker=False,
        use_graph_retrieval=False,
        read_only=True,
    )
    assert auth.await_count == 2
    assert result["status"] == "ok" and result["scope"] == "general_education"
    assert len(result["sources"]) == 1
    assert result["sources"][0]["content"] == chunk.content
    assert result["sources"][0]["filename"] == file.filename
    assert UUID(result["sources"][0]["source_id"])


@pytest.mark.asyncio
async def test_search_distinguishes_stale_milvus_hit_from_no_hit(monkeypatch):
    """向量残留旧正文按来源失效拒绝，真实零命中才表示资料不足。"""
    monkeypatch.setenv(service.KB_ID_ENV, KB_ID)
    file, chunk = _source_records()
    session = SimpleNamespace(scalar=AsyncMock(side_effect=[chunk, file]))

    @asynccontextmanager
    async def session_context():
        yield session

    monkeypatch.setattr(service.pg_manager, "get_async_session_context", session_context)
    monkeypatch.setattr(service, "_authorized_run", AsyncMock())
    monkeypatch.setattr(service, "_require_fixed_kb", AsyncMock())
    monkeypatch.setattr(
        service.knowledge_base,
        "retrieve",
        AsyncMock(
            return_value={
                "results": [{"id": chunk.chunk_id, "file_id": file.file_id, "kb_id": KB_ID, "content": "旧版正文"}]
            }
        ),
    )

    with pytest.raises(HealthVisionError, match="source_invalidated"):
        await service.search_family_nutrition_knowledge(SimpleNamespace(), "一般营养")
    service.knowledge_base.retrieve.return_value = {"results": []}
    result = await service.search_family_nutrition_knowledge(SimpleNamespace(), "一般营养")
    assert result["status"] == "insufficient_material" and result["sources"] == []


@pytest.mark.asyncio
async def test_search_maps_hydrated_orphan_hits_to_source_invalidated(monkeypatch):
    """真实 Milvus 水合阶段剔除全部孤儿命中时向调用方返回 410。"""
    monkeypatch.setenv(service.KB_ID_ENV, KB_ID)
    session = SimpleNamespace()

    @asynccontextmanager
    async def session_context():
        yield session

    monkeypatch.setattr(service.pg_manager, "get_async_session_context", session_context)
    monkeypatch.setattr(service, "_authorized_run", AsyncMock())
    monkeypatch.setattr(service, "_require_fixed_kb", AsyncMock())
    monkeypatch.setattr(
        service.knowledge_base,
        "retrieve",
        AsyncMock(side_effect=OrphanedMilvusHitsError("all PostgreSQL sources are missing")),
    )

    with pytest.raises(HealthVisionError, match="source_invalidated") as caught:
        await service.search_family_nutrition_knowledge(SimpleNamespace(), "一般营养")
    assert caught.value.status == 410


@pytest.mark.asyncio
async def test_changed_chunk_invalidates_persisted_source(monkeypatch):
    """即便展示片段前缀未变，全文改版也使历史回执失效。"""
    monkeypatch.setenv(service.KB_ID_ENV, KB_ID)
    file, chunk = _source_records()
    source = service._project_source(KB_ID, file, chunk, "11111111-1111-4111-8111-111111111111")
    chunk.content += "已改版"
    session = SimpleNamespace(scalar=AsyncMock(side_effect=[file, chunk]))
    monkeypatch.setattr(service, "_require_fixed_kb", AsyncMock())

    with pytest.raises(HealthVisionError, match="source_invalidated"):
        await service._validate_payload(session, _payload(source))


@pytest.mark.asyncio
async def test_final_marker_must_come_from_completed_same_run_audit(monkeypatch):
    """不接受旧 Run、伪造标识或有检索结果却省略来源。"""
    monkeypatch.setenv(service.KB_ID_ENV, KB_ID)
    file, chunk = _source_records()
    source = service._project_source(KB_ID, file, chunk, "11111111-1111-4111-8111-111111111111")
    run = SimpleNamespace(
        id="run-1", uid="actor", agent_slug="health-consultation", conversation_id=7, request_id="request-1"
    )
    binding = SimpleNamespace(conversation_id=7, actor_uid="actor")
    audit = SimpleNamespace(
        message_type="tool_audit",
        role="tool",
        execution_status="completed",
        conversation_id=7,
        request_id="request-1",
        extra_metadata={"tool_name": service.TOOL_NAME},
        content=json.dumps(_payload(source), ensure_ascii=False),
    )
    monkeypatch.setattr(
        service, "ToolMessageAuditRepository", lambda _: SimpleNamespace(list_for_run=AsyncMock(return_value=[audit]))
    )
    monkeypatch.setattr(service, "_validate_payload", AsyncMock(return_value=[source]))

    valid = f"一般营养概念，参考《{file.filename}》[资料:{source['source_id']}]"
    await service.validate_family_kb_publication(None, run, binding, valid)
    for answer in (
        "没有引用来源",
        f"参考《{file.filename}》[资料:22222222-2222-4222-8222-222222222222]",
        f"一般概念[资料:{source['source_id']}]",
    ):
        with pytest.raises(HealthVisionError, match="citation_invalid"):
            await service.validate_family_kb_publication(None, run, binding, answer)
    audit.execution_status = "failed"
    with pytest.raises(HealthVisionError, match="source_invalidated"):
        await service.validate_family_kb_publication(None, run, binding, valid)


@pytest.mark.asyncio
async def test_model_cannot_use_tool_message_without_persisted_audit(monkeypatch):
    """模型已经看到工具输出时，即使答复没标来源也必须有同 Run 审计。"""
    monkeypatch.setenv(service.KB_ID_ENV, KB_ID)
    run = SimpleNamespace(
        id="run-1", uid="actor", agent_slug="health-consultation", conversation_id=7, request_id="request-1"
    )
    binding = SimpleNamespace(conversation_id=7, actor_uid="actor")
    monkeypatch.setattr(
        service, "ToolMessageAuditRepository", lambda _: SimpleNamespace(list_for_run=AsyncMock(return_value=[]))
    )
    with pytest.raises(HealthVisionError, match="source_invalidated"):
        await service._validate_answer_sources(None, run, binding, "暂无足够资料", require_tool_audit=True)


@pytest.mark.asyncio
async def test_audit_output_must_match_completed_family_tool_content(monkeypatch):
    """调试时间线的 tool_output 必须与已完成家庭工具的当前正文一致。"""
    monkeypatch.setenv(service.KB_ID_ENV, KB_ID)
    file, chunk = _source_records()
    source = service._project_source(KB_ID, file, chunk, "11111111-1111-4111-8111-111111111111")
    content = json.dumps(_payload(source), ensure_ascii=False)
    audit = SimpleNamespace(
        run_id="run-1",
        conversation_id=7,
        request_id="request-1",
        operation_id="call-1",
        message_type="tool_audit",
        role="tool",
        execution_status="completed",
        content=content,
        extra_metadata={
            "tool_name": service.TOOL_NAME,
            "tool_call_id": "call-1",
            "output": {"type": "tool", "status": "success", "content": content},
        },
    )
    session = SimpleNamespace(scalar=AsyncMock(return_value=SimpleNamespace(id="run-1")))
    validate = AsyncMock(return_value=[source])
    monkeypatch.setattr(service, "_validate_payload", validate)
    assert await service.validate_family_kb_audit(session, audit) is True
    validate.assert_awaited_once()
    audit.extra_metadata = {
        **audit.extra_metadata,
        "output": {"type": "tool", "status": "success", "content": "过期或伪造片段"},
    }
    with pytest.raises(HealthVisionError, match="source_invalidated"):
        await service.validate_family_kb_audit(session, audit)


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["running", "failed", "completed", "interrupted", "abandoned"])
async def test_unpublished_family_audit_only_verifies_owner(monkeypatch, status):
    """未完成或错误输出只保留诊断元数据，正文不得作为已核验来源。"""
    audit = SimpleNamespace(
        run_id="run-1",
        conversation_id=7,
        request_id="request-1",
        operation_id="call-1",
        message_type="tool_audit",
        role="tool",
        execution_status=status,
        content="未经校验的知识库正文",
        extra_metadata={
            "tool_name": service.TOOL_NAME,
            "tool_call_id": "call-1",
            "output": {"status": "error", "content": "未经校验的知识库正文"},
        },
    )
    session = SimpleNamespace(scalar=AsyncMock(return_value=SimpleNamespace(id="run-1")))
    validate = AsyncMock()
    monkeypatch.setattr(service, "_validate_payload", validate)

    assert await service.validate_family_kb_audit(session, audit) is False
    session.scalar.assert_awaited_once()
    validate.assert_not_awaited()

    session.scalar = AsyncMock(return_value=None)
    with pytest.raises(HealthVisionError, match="source_invalidated"):
        await service.validate_family_kb_audit(session, audit)


def test_missing_fixed_kb_configuration_is_explicit(monkeypatch):
    """未配置时不搜索同名库，也不回退到普通审核证据。"""
    monkeypatch.delenv(service.KB_ID_ENV, raising=False)
    with pytest.raises(HealthVisionError, match="knowledge_unavailable"):
        service.configured_family_kb_id()

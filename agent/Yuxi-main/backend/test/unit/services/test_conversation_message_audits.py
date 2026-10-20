from datetime import datetime
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from yuxi.repositories.health_consultation_repository import CONSULTATION_SLUG
from yuxi.services import conversation_service
from yuxi.services import health_family_kb_service
from yuxi.services.health_vision_types import HealthVisionError


@pytest.mark.asyncio
async def test_get_thread_message_audits_view_serializes_model_and_tool_facts(monkeypatch):
    model_message = SimpleNamespace(
        id=17,
        role="assistant",
        content="模型输出",
        created_at=datetime(2026, 8, 30, 1, 0, 0),
        run_id="run-1",
        request_id="request-1",
        message_type="model_audit",
        operation_id="model-1",
        started_at=datetime(2026, 8, 30, 1, 0, 1),
        finished_at=datetime(2026, 8, 30, 1, 0, 2),
        duration_ms=875,
        sequence=12,
        execution_status="completed",
        usage={"prompt_tokens": 10, "completion_tokens": 4, "total_tokens": 14},
        extra_metadata={
            "namespace": ["agent", "model"],
            "model_run_id": "langgraph-model-1",
            "finished_sequence": 18,
            "content": [{"type": "text", "text": "模型输出"}],
            "tool_calls": [],
            "private_internal_field": "must-not-leak",
        },
        tool_calls=[],
    )
    tool_message = SimpleNamespace(
        id=18,
        role="tool",
        content="查询结果",
        created_at=datetime(2026, 8, 30, 1, 0, 2),
        run_id="run-1",
        request_id="request-1",
        message_type="tool_audit",
        operation_id="call-1",
        started_at=datetime(2026, 8, 30, 1, 0, 2),
        finished_at=datetime(2026, 8, 30, 1, 0, 3),
        duration_ms=120,
        sequence=14,
        execution_status="completed",
        usage=None,
        extra_metadata={
            "namespace": [],
            "tool_call_id": "call-1",
            "tool_name": "search",
            "input": {"q": "Yuxi"},
            "output": {"type": "tool", "content": "查询结果", "status": "success"},
            "error_message": None,
            "source_model_operation_id": "model-1",
            "finished_sequence": 15,
            "private_internal_field": "must-not-leak",
        },
        tool_calls=[],
    )
    run = SimpleNamespace(
        id="run-1",
        status="completed",
        created_at=datetime(2026, 8, 30, 1, 0, 0),
        started_at=datetime(2026, 8, 30, 1, 0, 1),
        prepared_at=datetime(2026, 8, 30, 1, 0, 1),
        first_output_at=datetime(2026, 8, 30, 1, 0, 2),
        finished_at=datetime(2026, 8, 30, 1, 0, 3),
    )

    class FakeConversationRepository:
        def __init__(self, _db):
            pass

        async def get_conversation_by_thread_id(self, _thread_id):
            return SimpleNamespace(id=7, uid="user-1", status="active", agent_id="default")

        async def list_message_audits(self, conversation_id, *, limit):
            assert conversation_id == 7
            assert limit == conversation_service.MESSAGE_AUDIT_LIMIT
            return [model_message, tool_message], True

        async def list_agent_runs_for_trace(self, conversation_id, *, limit):
            assert conversation_id == 7
            assert limit == conversation_service.AGENT_RUN_TRACE_LIMIT
            return [run], True

    monkeypatch.setattr(conversation_service, "ConversationRepository", FakeConversationRepository)

    result = await conversation_service.get_thread_message_audits_view(
        thread_id="thread-1",
        current_uid="user-1",
        db=object(),
    )

    assert [item["type"] for item in result["audits"]] == ["ai", "tool"]
    assert result["truncated"] is True
    assert result["runs_truncated"] is True
    assert result["runs"] == [
        {
            "run_id": "run-1",
            "status": "completed",
            "timing": {
                "created_at": "2026-08-30T01:00:00Z",
                "started_at": "2026-08-30T01:00:01Z",
                "prepared_at": "2026-08-30T01:00:01Z",
                "first_model_request_at": None,
                "first_output_at": "2026-08-30T01:00:02Z",
                "finished_at": "2026-08-30T01:00:03Z",
                "dispatch_latency_ms": 1000,
                "preparation_latency_ms": 0,
                "first_model_request_latency_ms": None,
                "model_first_output_latency_ms": 1000,
                "first_output_latency_ms": 2000,
                "total_latency_ms": 3000,
            },
        }
    ]
    assert result["audits"][0] == {
        "id": 17,
        "type": "ai",
        "content": "模型输出",
        "created_at": "2026-08-30T01:00:00Z",
        "run_id": "run-1",
        "request_id": "request-1",
        "message_type": "model_audit",
        "operation_id": "model-1",
        "started_at": "2026-08-30T01:00:01Z",
        "finished_at": "2026-08-30T01:00:02Z",
        "duration_ms": 875,
        "sequence": 12,
        "finished_sequence": 18,
        "execution_status": "completed",
        "usage": {"prompt_tokens": 10, "completion_tokens": 4, "total_tokens": 14},
        "namespace": ["agent", "model"],
        "model_run_id": "langgraph-model-1",
        "content_blocks": [{"type": "text", "text": "模型输出"}],
        "reasoning_content": "",
        "tool_calls": [],
    }
    tool = result["audits"][1]
    assert tool == {
        "id": 18,
        "type": "tool",
        "content": "查询结果",
        "created_at": "2026-08-30T01:00:02Z",
        "run_id": "run-1",
        "request_id": "request-1",
        "message_type": "tool_audit",
        "operation_id": "call-1",
        "tool_call_id": "call-1",
        "tool_name": "search",
        "tool_input": {"q": "Yuxi"},
        "tool_output": {"type": "tool", "content": "查询结果", "status": "success"},
        "error_message": None,
        "source_model_operation_id": "model-1",
        "started_at": "2026-08-30T01:00:02Z",
        "finished_at": "2026-08-30T01:00:03Z",
        "duration_ms": 120,
        "sequence": 14,
        "finished_sequence": 15,
        "execution_status": "completed",
        "usage": None,
        "namespace": [],
    }
    assert "private_internal_field" not in str(result)


@pytest.mark.asyncio
async def test_get_thread_message_audits_view_uses_agent_run_terminal_status(monkeypatch):
    audit = SimpleNamespace(
        id=21,
        role="assistant",
        content="",
        created_at=datetime(2026, 8, 30, 1, 0, 0),
        run_id="run-cancelled",
        request_id="request-cancelled",
        message_type="model_audit",
        operation_id="model-cancelled",
        started_at=datetime(2026, 8, 30, 1, 0, 0),
        finished_at=datetime(2026, 8, 30, 1, 0, 1),
        duration_ms=1000,
        sequence=1,
        execution_status="interrupted",
        usage=None,
        extra_metadata={},
        tool_calls=[],
    )
    run = SimpleNamespace(
        id="run-cancelled",
        status="cancelled",
        created_at=datetime(2026, 8, 30, 1, 0, 0),
        started_at=datetime(2026, 8, 30, 1, 0, 0),
        prepared_at=None,
        first_output_at=None,
        finished_at=datetime(2026, 8, 30, 1, 0, 1),
    )

    class FakeConversationRepository:
        def __init__(self, _db):
            pass

        async def get_conversation_by_thread_id(self, _thread_id):
            return SimpleNamespace(id=7, uid="user-1", status="active", agent_id="default")

        async def list_message_audits(self, _conversation_id, *, limit):
            assert limit == conversation_service.MESSAGE_AUDIT_LIMIT
            return [audit], False

        async def list_agent_runs_for_trace(self, _conversation_id, *, limit):
            assert limit == conversation_service.AGENT_RUN_TRACE_LIMIT
            return [run], False

    monkeypatch.setattr(conversation_service, "ConversationRepository", FakeConversationRepository)

    result = await conversation_service.get_thread_message_audits_view(
        thread_id="thread-1",
        current_uid="user-1",
        db=object(),
    )

    assert result["audits"][0]["execution_status"] == "interrupted"
    assert result["runs_truncated"] is False
    assert result["runs"][0]["status"] == "cancelled"
    assert result["runs"][0]["timing"]["total_latency_ms"] == 1000


@pytest.mark.asyncio
async def test_family_knowledge_audits_are_checked_before_truncated_timeline(monkeypatch):
    """即使来源审计不在最新 500 条中，也不能公开旧资料的审计时间线。"""

    class FakeConversationRepository:
        def __init__(self, _db):
            pass

        async def list_message_audits(self, *_args, **_kwargs):
            pytest.fail("stale source must stop serialization")

    class FakeSession:
        async def scalars(self, _statement):
            return SimpleNamespace(all=lambda: [SimpleNamespace(id=1)])

    async def fake_require_user_conversation(_repository, _thread_id, _uid):
        return SimpleNamespace(id=7, agent_id=CONSULTATION_SLUG)

    async def reject_stale_audit(_session, _audit):
        raise HealthVisionError("source_invalidated", "资料版本已失效", 410)

    monkeypatch.setattr(conversation_service, "ConversationRepository", FakeConversationRepository)
    monkeypatch.setattr(conversation_service, "require_user_conversation", fake_require_user_conversation)
    monkeypatch.setattr(health_family_kb_service, "validate_family_kb_audit", reject_stale_audit)

    with pytest.raises(HTTPException) as caught:
        await conversation_service.get_thread_message_audits_view(
            thread_id="thread-1", current_uid="user-1", db=FakeSession()
        )
    assert caught.value.status_code == 410


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["running", "failed", "completed", "interrupted", "abandoned"])
async def test_unpublished_family_knowledge_audit_redacts_whole_run(monkeypatch, status):
    """失败、运行中或错误输出的家庭检索只公开同 Run 的诊断元数据。"""
    poison = "未经校验的家庭库片段"
    now = datetime(2026, 8, 30, 1, 0, 0)
    model_audit = SimpleNamespace(
        id=1,
        role="assistant",
        content=poison,
        created_at=now,
        run_id="run-1",
        request_id="request-1",
        message_type="model_audit",
        operation_id="model-1",
        started_at=now,
        finished_at=now,
        duration_ms=5,
        sequence=1,
        execution_status="completed",
        usage={"provider_note": poison},
        extra_metadata={"content": [{"type": "text", "text": poison}], "reasoning_content": poison},
        tool_calls=[
            SimpleNamespace(
                id=1,
                langgraph_tool_call_id="call-1",
                tool_name=health_family_kb_service.TOOL_NAME,
                tool_input={"query": poison},
                tool_output=poison,
                status="success",
                error_message=poison,
            )
        ],
    )
    family_audit = SimpleNamespace(
        id=2,
        role="tool",
        content=poison,
        created_at=now,
        conversation_id=7,
        run_id="run-1",
        request_id="request-1",
        message_type="tool_audit",
        operation_id="call-1",
        started_at=now,
        finished_at=now,
        duration_ms=10,
        sequence=2,
        execution_status=status,
        extra_metadata={
            "tool_call_id": "call-1",
            "tool_name": health_family_kb_service.TOOL_NAME,
            "input": {"query": poison},
            "output": {"status": "error", "content": poison},
            "error_message": poison,
        },
    )
    other_audit = SimpleNamespace(
        id=3,
        role="tool",
        content="ordinary output",
        created_at=now,
        run_id="run-2",
        request_id="request-2",
        message_type="tool_audit",
        operation_id="call-2",
        started_at=now,
        finished_at=now,
        duration_ms=10,
        sequence=2,
        execution_status="completed",
        extra_metadata={"tool_call_id": "call-2", "tool_name": "other", "output": "ordinary output"},
    )

    class FakeConversationRepository:
        def __init__(self, _db):
            pass

        async def list_message_audits(self, *_args, **_kwargs):
            return [model_audit, family_audit, other_audit], False

        async def list_agent_runs_for_trace(self, *_args, **_kwargs):
            return [], False

    class FakeSession:
        async def scalars(self, _statement):
            return SimpleNamespace(all=lambda: [family_audit])

        async def scalar(self, _statement):
            return SimpleNamespace(id="run-1")

    async def fake_require_user_conversation(_repository, _thread_id, _uid):
        return SimpleNamespace(id=7, agent_id=CONSULTATION_SLUG)

    monkeypatch.setattr(conversation_service, "ConversationRepository", FakeConversationRepository)
    monkeypatch.setattr(conversation_service, "require_user_conversation", fake_require_user_conversation)

    result = await conversation_service.get_thread_message_audits_view(
        thread_id="thread-1", current_uid="user-1", db=FakeSession()
    )

    model, family, other = result["audits"]
    assert poison not in str(result)
    assert model["content"] == ""
    assert model["content_blocks"] == []
    assert model["tool_calls"][0]["args"] == {}
    assert model["tool_calls"][0]["tool_call_result"] is None
    assert family["execution_status"] == status
    assert family["content"] == ""
    assert family["tool_input"] == {}
    assert family["tool_output"] is None
    assert family["error_message"] is None
    assert other["content"] == "ordinary output"

"""模型实际前置入口拒绝保留有效来源ID的伪造健康正文。"""

from contextlib import asynccontextmanager
from copy import deepcopy
from datetime import datetime
import hashlib
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

from langchain_core.messages import HumanMessage, ToolMessage
import pytest

from yuxi.agents.buildin.health_consultation.graph import HealthAuthorizationMiddleware
from yuxi.services import health_consultation_service as service
from yuxi.services import health_memory_service as memory_service
from yuxi.repositories.health_evidence_repository import HealthEvidenceRepository
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.storage.postgres.models_health import HealthObservation, DietLog


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["report", "meal", "evidence"])
async def test_actual_model_entry_rejects_changed_body_with_real_source_identity(monkeypatch, kind):
    """当前来源ID仍有效时，模型调用前拒绝伪造指标、营养或审核证据。"""
    timestamp = datetime(2026, 10, 8)
    record = SimpleNamespace(
        id="synthetic-record",
        member_id="member",
        confirmation_id="synthetic-confirmation",
        created_at=timestamp,
        snapshot={"name": "合成指标", "value_numeric": 5, "unit_raw": "synthetic"},
    )
    if kind == "meal":
        record.snapshot = {
            "meal": {"meal_type": "lunch", "eaten_at": "2026-10-08T12:00:00+08:00", "items": []},
            "nutrition": {
                "totals": {"energy_kcal": "300.00"},
                "complete": True,
                "estimated": True,
                "units": {"energy_kcal": "kcal"},
                "calculation_version": "synthetic",
            },
        }
    source = SimpleNamespace(
        id="synthetic-evidence",
        title="审核通用科普",
        content="合成审核片段仅供通用科普",
        source_ref="https://example.com/nutrition",
        source_version="synthetic-v1",
        reviewed_at=timestamp,
        valid_until=datetime(2099, 1, 1),
        revoked_at=None,
    )
    source.content_hash = hashlib.sha256(source.content.encode()).hexdigest()
    citation = SimpleNamespace(id="synthetic-citation", content_hash=source.content_hash)
    session = SimpleNamespace(get=AsyncMock(), execute=AsyncMock(return_value=[(citation, source)]))
    session.get.side_effect = lambda model, identity: (
        record if model in (HealthObservation, DietLog) else SimpleNamespace(draft_id="synthetic-draft")
    )

    @asynccontextmanager
    async def transaction():
        yield session

    binding = SimpleNamespace(member_id="member", conversation_id=7)
    monkeypatch.setattr(service.pg_manager, "get_async_session_context", transaction)
    monkeypatch.setattr(
        service.HealthConsultationRepository,
        "require_attempt",
        AsyncMock(
            return_value=SimpleNamespace(
                agent_slug="health-consultation", input_payload={"health_processing": {"approved": True}}
            )
        ),
    )
    monkeypatch.setattr(service, "require_consultation", AsyncMock(return_value=(binding, {})))
    monkeypatch.setattr(
        service.HealthVisionRepository, "draft", AsyncMock(return_value=SimpleNamespace(review_status="confirmed"))
    )
    context = SimpleNamespace(uid="actor", thread_id="thread", request_id="request", model="synthetic:fixed")
    middleware = HealthAuthorizationMiddleware(None)
    monkeypatch.setattr("yuxi.agents.buildin.health_consultation.graph.model_cache.get_model_info", lambda _: None)
    if kind == "evidence":
        payload = {
            "status": "ok",
            "query": "营养",
            "citations": [HealthEvidenceRepository.project_citation(citation, source)],
            "personal_meal_plan_available": False,
        }
        tool_name = "query_reviewed_nutrition_knowledge"
    else:
        payload = {
            "records": [service.project_confirmed_record(record, kind)],
            "full_health_profile_available": False,
            "personal_meal_plan_available": False,
        }
        tool_name = "get_confirmed_profile" if kind == "report" else "get_confirmed_diet"

    async def model_guard(body):
        """直接调用shipping图每次外呼的实际前置中间件。"""
        messages = [
            HumanMessage(content="合成问题"),
            ToolMessage(name=tool_name, tool_call_id="synthetic-call", content=json.dumps(body)),
        ]
        await middleware.abefore_model({"messages": messages}, SimpleNamespace(context=context))

    await model_guard(payload)
    forged = deepcopy(payload)
    if kind == "report":
        forged["records"][0]["value_numeric"] = 999
    elif kind == "meal":
        forged["records"][0]["nutrition"]["totals"]["energy_kcal"] = "1.00"
    else:
        forged["citations"][0]["content"] = "每日只摄入500千卡的伪造规则"
    with pytest.raises(HealthVisionError, match="source_invalidated"):
        await model_guard(forged)
    for extra in ("diagnosis", "extra_body"):
        injected = deepcopy(payload)
        target = injected["citations"][0] if kind == "evidence" else injected["records"][0]
        if extra == "diagnosis":
            target[extra] = "未经来源确认的合成诊断"
        else:
            injected[extra] = "未经来源确认的合成诊断"
        with pytest.raises(HealthVisionError, match="source_invalidated"):
            await model_guard(injected)
    for error_tool in [tool_name, *(["get_complete_health_profile"] if kind == "report" else [])]:
        error_messages = [
            HumanMessage(content="合成问题"),
            ToolMessage(name=error_tool, tool_call_id="synthetic-call", status="error", content=json.dumps(forged)),
        ]
        with pytest.raises(HealthVisionError, match="source_invalidated"):
            await middleware.abefore_model({"messages": error_messages}, SimpleNamespace(context=context))


@pytest.mark.asyncio
@pytest.mark.parametrize("tool_name", ["get_member_memories", "remember_member_fact"])
@pytest.mark.parametrize("injection", ["record_extra", "envelope_extra", "error_status"])
async def test_actual_memory_model_wrapper_rejects_extra_body_and_error_bypass(monkeypatch, tool_name, injection):
    """真实wrapper不能把未经核对的记忆字段或错误正文交给模型handler。"""
    from yuxi.services import health_meal_feedback_service

    fact = SimpleNamespace(
        id="fact",
        member_id="member",
        fact_key="avoid_coriander",
        content="我以后不吃香菜",
        kind="preference",
        version=1,
        status="active",
        updated_at=datetime(2026, 10, 8),
    )
    session = object()

    @asynccontextmanager
    async def transaction():
        yield session

    monkeypatch.setattr(service.pg_manager, "get_async_session_context", transaction)
    monkeypatch.setattr(memory_service.HealthMemoryRepository, "history_uses", AsyncMock(return_value=[]))
    monkeypatch.setattr(memory_service.HealthMemoryRepository, "get", AsyncMock(return_value=fact))
    monkeypatch.setattr(memory_service.HealthMemoryRepository, "record_uses", AsyncMock())
    monkeypatch.setattr(
        service.HealthConsultationRepository, "authorize", AsyncMock(return_value=SimpleNamespace(member_id="member"))
    )
    monkeypatch.setattr(
        service.HealthConsultationRepository,
        "require_attempt",
        AsyncMock(return_value=SimpleNamespace(input_payload={"health_processing": {"approved": True}})),
    )
    monkeypatch.setattr(service, "require_consultation", AsyncMock())

    async def keep_feedback(context, messages, **kwargs):
        """隔离其他来源过滤；真实记忆服务及wrapper不替换。"""
        return messages

    monkeypatch.setattr(health_meal_feedback_service, "filter_meal_feedback_history", keep_feedback)
    reference = memory_service.memory_result(fact)
    payload = (
        {"memories": [reference], "truncated": False}
        if tool_name == "get_member_memories"
        else {**reference, "written_version": 1, "replayed": False}
    )
    context = SimpleNamespace(uid="actor", thread_id="thread", model="synthetic:fixed", request_id="request")
    handler = AsyncMock(return_value="called")

    async def model_wrapper(body, status="success"):
        messages = [
            HumanMessage(content="合成问题"),
            ToolMessage(name=tool_name, tool_call_id="synthetic-call", status=status, content=json.dumps(body)),
        ]
        request = SimpleNamespace(
            runtime=SimpleNamespace(context=context),
            messages=messages,
            override=lambda **changes: SimpleNamespace(**changes),
        )
        return await HealthAuthorizationMiddleware(None).awrap_model_call(request, handler)

    assert await model_wrapper(payload) == "called"
    handler.reset_mock()
    forged = deepcopy(payload)
    if injection == "record_extra":
        target = forged["memories"][0] if tool_name == "get_member_memories" else forged
        target["diagnosis"] = "未经来源确认的合成诊断"
    else:
        forged["extra_body"] = "未经来源确认的合成诊断"
    with pytest.raises(HealthVisionError, match="memory_history_invalid"):
        await model_wrapper(forged, "error" if injection == "error_status" else "success")
    handler.assert_not_awaited()

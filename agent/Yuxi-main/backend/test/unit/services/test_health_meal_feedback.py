"""餐后反馈 schema 和模型历史失效的独立负向 oracle。"""

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4
import pytest
from pydantic import ValidationError
from langchain_core.messages import HumanMessage, AIMessage
from yuxi.services.health_meal_feedback_types import MealFeedbackChange, MealFeedbackRevoke
from yuxi.agents.toolkits.health import get_meal_feedback
from yuxi.services.health_vision_types import HealthVisionError


def test_feedback_requires_explicit_bounded_nonempty_self_report():
    """空内容、伪造主体、未知标签及过长说明不能进入持久化。"""
    base = {"client_request_id": str(uuid4()), "version": 0}
    for extra in (
        {},
        {"comment": " "},
        {"tags": ["too_salty", "too_salty"]},
        {"tags": ["diagnosis"]},
        {"comment": "x" * 501},
        {"member_id": "forged"},
    ):
        with pytest.raises(ValidationError):
            MealFeedbackChange.model_validate({**base, **extra})
    value = MealFeedbackChange.model_validate({**base, "comment": "  这顿有点咸  "})
    assert value.comment == "这顿有点咸"
    with pytest.raises(ValidationError):
        MealFeedbackRevoke.model_validate(base)
    assert get_meal_feedback.tool_call_schema.model_json_schema()["properties"] == {}
    with pytest.raises(ValidationError):
        get_meal_feedback.args_schema.model_validate({"runtime": "forged", "member_id": "forged"})


@pytest.mark.asyncio
async def test_feedback_history_drops_derived_turns_and_current_change_aborts(monkeypatch):
    """PG 依赖即使没有工具收据也能过滤旧回答；当前失效拒绝外呼。"""
    from yuxi.services import health_meal_feedback_service as service, health_consultation_service

    @asynccontextmanager
    async def session():
        yield object()

    monkeypatch.setattr(service.pg_manager, "get_async_session_context", session)
    run = SimpleNamespace(id="run", input_payload={"health_processing": {"policy_version": "synthetic"}})
    monkeypatch.setattr(service.HealthConsultationRepository, "require_attempt", AsyncMock(return_value=run))
    monkeypatch.setattr(
        health_consultation_service,
        "require_consultation",
        AsyncMock(return_value=(SimpleNamespace(member_id="member"), {})),
    )
    fact = SimpleNamespace(id="feedback")
    monkeypatch.setattr(
        service.HealthMealFeedbackRepository, "uses", AsyncMock(return_value=[("old", 1, fact), ("derived", 1, fact)])
    )
    invalid = AsyncMock(return_value={"old", "derived"})
    monkeypatch.setattr(service.HealthMealFeedbackRepository, "invalid_requests", invalid)
    recorded = AsyncMock()
    monkeypatch.setattr(service.HealthMealFeedbackRepository, "record_uses", recorded)
    context = SimpleNamespace(uid="actor", thread_id="thread", request_id="new", model="synthetic/fixed")
    current = HumanMessage(content="新问题", additional_kwargs={"health_request_id": "new"})
    messages = [
        HumanMessage(content="旧问题", additional_kwargs={"health_request_id": "old"}),
        AIMessage(content="旧反馈"),
        HumanMessage(content="沿用", additional_kwargs={"health_request_id": "derived"}),
        AIMessage(content="派生旧反馈"),
        current,
    ]
    assert await service.filter_meal_feedback_history(context, messages) == [current]
    assert recorded.await_args.args[1] == []
    invalid.return_value = set()
    assert await service.filter_meal_feedback_history(context, messages) == messages
    assert recorded.await_args.args[1] == [("feedback", 1), ("feedback", 1)]
    recorded.reset_mock()
    invalid.return_value = {"new"}
    with pytest.raises(HealthVisionError, match="meal_feedback_changed"):
        await service.filter_meal_feedback_history(context, messages)
    recorded.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid_kind", ["memory", "feedback"])
async def test_joint_filter_only_records_dependencies_of_final_visible_turns(monkeypatch, invalid_kind):
    """两种实际过滤器联合决定输入，任一旧依赖失效均不传播另一类。"""
    from yuxi.services import (
        health_meal_feedback_service as feedback,
        health_memory_service as memory,
        health_consultation_service,
    )

    owner_session = object()

    @asynccontextmanager
    async def session():
        yield owner_session

    monkeypatch.setattr(feedback.pg_manager, "get_async_session_context", session)
    run = SimpleNamespace(id="run", input_payload={"health_processing": {"policy_version": "synthetic"}})
    monkeypatch.setattr(feedback.HealthConsultationRepository, "require_attempt", AsyncMock(return_value=run))
    monkeypatch.setattr(
        health_consultation_service,
        "require_consultation",
        AsyncMock(return_value=(SimpleNamespace(member_id="member"), {})),
    )
    monkeypatch.setattr(
        feedback.HealthMealFeedbackRepository,
        "uses",
        AsyncMock(return_value=[("old", 1, SimpleNamespace(id="feedback"))]),
    )
    monkeypatch.setattr(
        feedback.HealthMealFeedbackRepository,
        "invalid_requests",
        AsyncMock(return_value={"old"} if invalid_kind == "feedback" else set()),
    )
    monkeypatch.setattr(
        memory.HealthMemoryRepository,
        "history_uses",
        AsyncMock(
            return_value=[
                (
                    "old",
                    "memory",
                    1,
                    "revoked" if invalid_kind == "memory" else "active",
                    2 if invalid_kind == "memory" else 1,
                )
            ]
        ),
    )
    writes_feedback, writes_memory = AsyncMock(), AsyncMock()
    monkeypatch.setattr(feedback.HealthMealFeedbackRepository, "record_uses", writes_feedback)
    monkeypatch.setattr(memory.HealthMemoryRepository, "record_uses", writes_memory)
    context = SimpleNamespace(uid="actor", thread_id="thread", request_id="new", model="synthetic/fixed")
    current = HumanMessage(content="新问题", additional_kwargs={"health_request_id": "new"})
    messages = [
        HumanMessage(content="混合旧问题", additional_kwargs={"health_request_id": "old"}),
        AIMessage(content="旧反馈和旧记忆"),
        current,
    ]
    assert await feedback.filter_health_history(context, messages) == [current]
    assert writes_feedback.await_args.args[1] == []
    writes_memory.assert_not_awaited()
    # 最终输出检查不从 checkpoint 重新传播已过滤依赖。
    writes_feedback.reset_mock()
    assert await feedback.filter_health_history(context, messages, persist_uses=False) == [current]
    writes_feedback.assert_not_awaited()
    writes_memory.assert_not_awaited()

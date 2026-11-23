"""追问的公开协议与有界模型调用，不使用真实健康数据或模型。"""

import time
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from yuxi.services import health_ai_budget_service as budget
from yuxi.services import health_followup_service as service
from yuxi.services.health_followup_types import (
    FOLLOWUPS_KEY,
    ChatFollowupOutput,
    answer_digest,
    public_followup_result,
)
from yuxi.repositories.health_followup_repository import HealthFollowupRepository
from yuxi.services.health_vision_types import HealthVisionError

ITEM = {"label": "只有15分钟怎么做", "question": "刚才建议的清淡晚餐只有15分钟准备，可以怎样调整？"}


def test_public_projection_checks_body_and_hides_raw_metadata():
    message = SimpleNamespace(id=42, content="清淡晚餐建议", extra_metadata={"private": "not public"})
    repo = HealthFollowupRepository(None)
    assert repo.claim(message)
    assert not repo.claim(message)
    assert public_followup_result(message).status == "pending"
    repo.finish(message, ChatFollowupOutput(followups=[ITEM]))
    public = public_followup_result(message).model_dump()
    assert public == {"message_id": 42, "status": "ready", "followups": [ITEM]}
    assert message.extra_metadata["private"] == "not public"
    message.content = "已经变化的正文"
    assert public_followup_result(message).followups == []
    with pytest.raises(HealthVisionError, match="原答案已变化"):
        repo.finish(message, ChatFollowupOutput(followups=[ITEM]))


def test_abandoned_claim_and_malformed_model_output_are_not_public():
    message = SimpleNamespace(id=42, content="答复", extra_metadata={})
    message.extra_metadata[FOLLOWUPS_KEY] = {
        "status": "pending",
        "claimed_at": time.time() - 61,
        "answer_hash": answer_digest(message.content),
    }
    assert public_followup_result(message).status == "unavailable"
    assert not HealthFollowupRepository(None).claim(message)
    for items in [[ITEM, ITEM], [{"label": "", "question": "问题"}], [{"label": "问题", "question": "换行\n"}]]:
        with pytest.raises(ValueError):
            ChatFollowupOutput(followups=items)
    message.extra_metadata[FOLLOWUPS_KEY].update(status="ready", followups=[{"bad": "invalid"}])
    assert public_followup_result(message).status == "unavailable"


@pytest.fixture
def generation(monkeypatch):
    @asynccontextmanager
    async def session():
        yield object()

    model = SimpleNamespace(
        ainvoke=AsyncMock(
            return_value=SimpleNamespace(
                text='{"followups":[{"label":"快速晚餐","question":"这份晚餐怎样在15分钟内完成？"}]}',
                usage_metadata={"input_tokens": 10, "output_tokens": 10},
            )
        )
    )
    reserve, settle = AsyncMock(return_value=object()), AsyncMock()
    monkeypatch.setattr(service.pg_manager, "get_async_session_context", session)
    monkeypatch.setattr(service, "require_consultation", AsyncMock())
    monkeypatch.setattr(budget, "reserve_model", reserve)
    monkeypatch.setattr(budget, "reserved_chat_model", lambda *a, **k: model)
    monkeypatch.setattr(budget, "settle", settle)
    return model, reserve, settle


@pytest.mark.asyncio
async def test_generation_uses_only_this_turn_and_budget_then_validates(generation):
    model, reserve, settle = generation
    result = await service.generate_followups(
        "user", "thread", 42, {"model": "approved"}, "今晚清淡吃什么？", "清蒸鱼配蔬菜。"
    )
    assert result.followups[0].label == "快速晚餐"
    assert reserve.await_args.args == ("consultation", "followup:42", "approved")
    data = model.ainvoke.await_args.args[0][1].content
    assert "今晚清淡吃什么" in data and "清蒸鱼配蔬菜" in data
    assert settle.await_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [TimeoutError(), ValueError("provider failed")])
async def test_optional_generation_failure_does_not_change_original_answer(generation, failure):
    model, _, settle = generation
    model.ainvoke.side_effect = failure
    result = await service.generate_followups("user", "thread", 42, {"model": "approved"}, "原问题", "原答复")
    assert result.followups == []
    assert settle.await_count == 1


@pytest.mark.asyncio
async def test_invalid_generation_is_empty_and_auth_denial_never_calls_model(generation, monkeypatch):
    model, reserve, _ = generation
    model.ainvoke.return_value = SimpleNamespace(text='{"followups":[{"label":"x","question":""}]}')
    result = await service.generate_followups("user", "thread", 42, {"model": "approved"}, "问题", "答复")
    assert result.followups == []
    reserve.reset_mock()
    monkeypatch.setattr(service, "require_consultation", AsyncMock(side_effect=PermissionError("revoked")))
    result = await service.generate_followups("user", "thread", 43, {"model": "approved"}, "问题", "答复")
    assert result.followups == [] and reserve.await_count == 0

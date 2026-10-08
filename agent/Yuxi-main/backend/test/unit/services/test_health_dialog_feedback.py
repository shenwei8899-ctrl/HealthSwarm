"""选餐反馈的原文、明确字段及模型输入边界。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from yuxi.agents.context import BaseContext
from yuxi.agents.toolkits.diet_analyst import get_selected_meal_feedback, record_selected_meal_feedback
from yuxi.services.health_dialog_feedback_service import dialog_feedback_details
from yuxi.services.health_meal_feedback_types import (
    DialogFeedbackAnswer,
    DialogFeedbackInput,
    FeedbackConversationInput,
)
from yuxi.services.health_vision_types import HealthVisionError


def test_full_original_and_explicit_fields_preserve_independent_meaning():
    """明确字段按固定用户词汇解析，自由文本不推断口味或摄入比例。"""
    quote = "记录这餐反馈：吃完程度：一半；口味：偏咸、偏油；自述：这顿有点咸"
    assert dialog_feedback_details(quote, quote) == {
        "consumption": "half",
        "tags": ["too_salty", "too_oily"],
        "comment": quote.split("：", 1)[1],
    }
    plain = "记录这餐反馈：不是偏咸，吃了一半可能是因为下午有活动"
    assert dialog_feedback_details(plain, plain) == {
        "consumption": "unknown",
        "tags": [],
        "comment": plain.split("：", 1)[1],
    }
    old = {"consumption": "all", "tags": ["too_sweet"], "comment": "旧体验"}
    updated = "更新这餐反馈：补记原文"
    assert dialog_feedback_details(updated, updated, old) == {
        **old,
        "comment": "补记原文",
    }
    clear = "更新这餐反馈：口味：无；吃完程度：未吃"
    assert dialog_feedback_details(clear, clear, old)["tags"] == []
    assert dialog_feedback_details(clear, clear, old)["consumption"] == "none"
    assert old["comment"] == "旧体验"


@pytest.mark.parametrize(
    "quote,original",
    [
        ("记录这餐反馈：偏咸", "这是旧消息"),
        ("记录这餐反馈：偏咸", "不要保存。记录这餐反馈：偏咸"),
        ("偏咸", "偏咸"),
        ("记录这餐反馈：", "记录这餐反馈："),
        ("记录这餐反馈：吃完程度：一半；吃完程度：全部", "记录这餐反馈：吃完程度：一半；吃完程度：全部"),
        ("记录这餐反馈：口味：偏咸、偏咸", "记录这餐反馈：口味：偏咸、偏咸"),
        ("记录这餐反馈：口味：高血糖", "记录这餐反馈：口味：高血糖"),
        ("记录这餐反馈：吃完程度：猜测一半", "记录这餐反馈：吃完程度：猜测一半"),
    ],
)
def test_no_subset_fabrication_inference_or_ambiguous_fields(quote, original):
    """不可截取否定上下文、编造原文或写入诊断标签。"""
    with pytest.raises(HealthVisionError, match="feedback_source_invalid"):
        dialog_feedback_details(quote, original)


def test_tool_identity_is_hidden_and_final_cannot_supply_feedback():
    """用户选餐与工具输入在不同信任边界。"""
    assert get_selected_meal_feedback.tool_call_schema.model_json_schema()["properties"] == {}
    assert set(record_selected_meal_feedback.tool_call_schema.model_json_schema()["properties"]) == {"quote", "version"}
    for body in [{"quote": "a", "version": True}, {"quote": "a", "version": 0, "record_id": "forged"}]:
        with pytest.raises(ValidationError):
            DialogFeedbackInput.model_validate(body)
    for body in [{}, {"feedback_saved": True, "questions": ["哪餐？"]}, {"feedback_saved": True, "feedback_id": "a"}]:
        with pytest.raises(ValidationError):
            DialogFeedbackAnswer.model_validate(body)
    with pytest.raises(ValidationError):
        FeedbackConversationInput(client_request_id="bad", source_version=1)


@pytest.mark.asyncio
async def test_context_fixes_feedback_tools_from_server_binding(monkeypatch):
    """反馈模式排除分析、文件、任意模型和其他成员工具。"""
    from yuxi.services import health_consultation_service as service

    snapshot = {"model": "synthetic:fixed", "processor": "synthetic", "policy_version": "v1"}
    monkeypatch.setattr(
        service,
        "require_consultation",
        AsyncMock(
            return_value=(
                SimpleNamespace(conversation_id=1),
                snapshot,
            )
        ),
    )
    context = BaseContext(uid="synthetic", thread_id="thread", tools=["all"], skills=["untrusted"], mcps=["all"])
    prepared = await service.prepare_consultation_context(
        context,
        SimpleNamespace(get=AsyncMock(return_value=object())),
        SimpleNamespace(agent_slug="health-diet-analyst", input_payload={"health_processing": snapshot}),
    )
    assert prepared.tools == ["get_selected_meal_feedback", "record_selected_meal_feedback"]
    assert prepared.mcps == prepared.knowledges == []
    assert prepared.skills == prepared.preload_skills == ["family-diet-analyst"]

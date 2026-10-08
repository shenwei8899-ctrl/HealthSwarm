"""家庭模型资源、发布审批及历史Run身份的拒绝边界。"""

from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from yuxi.agents.toolkits.meal_planner import (
    get_family_plan_context,
    preview_family_plan_swap,
    preview_family_plan_regeneration,
    preview_family_plan_participation,
)
from yuxi.services import health_family_planner_service as service
from yuxi.services.health_family_planner_types import FamilySwapParameters, FamilyParticipationParameters
from yuxi.services.health_nutrition_service import input_fingerprint
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.storage.postgres.models_business import AgentRun, Conversation


def test_fixed_tools_hide_runtime_identity_and_versions():
    """独立列举模型可见参数，禁止身份、目标和来源选择进入工具。"""
    for tool, fields in (
        (get_family_plan_context, set()),
        (preview_family_plan_swap, {"meal_type", "dish_index"}),
        (preview_family_plan_regeneration, set()),
        (preview_family_plan_participation, {"allocations"}),
    ):
        assert set(tool.tool_call_schema.model_json_schema()["properties"]) == fields


@pytest.mark.parametrize("key", ["member_id", "run_id", "rule_version", "personal_target", "professional_review"])
def test_swap_rejects_model_controlled_identity_or_approval(key):
    """额外字段不能被丢弃后作为可信菜位执行。"""
    with pytest.raises(ValidationError):
        FamilySwapParameters.model_validate({"meal_type": "lunch", "dish_index": 0, key: "forged"})


@pytest.mark.parametrize("index", [True, -1, 10, "0"])
def test_swap_requires_actual_bounded_integer(index):
    """模型菜位不能自动转换布尔、字符串或越界数字。"""
    with pytest.raises(ValidationError):
        FamilySwapParameters(meal_type="lunch", dish_index=index)


@pytest.mark.parametrize("extra", ["target", "actor_uid", "nutrition"])
def test_participation_rejects_nested_fabricated_fields(extra):
    """三餐分配也不能夹带营养值、运行账号或医学目标。"""
    member = str(uuid4())
    allocations = [
        {
            "meal_type": meal,
            "participant_ids": [member],
            "dishes": [{"dish_index": 0, "member_portions": [{"member_id": member, "grams": "50"}]}],
        }
        for meal in ("breakfast", "lunch", "dinner")
    ]
    FamilyParticipationParameters(allocations=allocations)
    allocations[0]["dishes"][0]["member_portions"][0][extra] = "forged"
    with pytest.raises(ValidationError):
        FamilyParticipationParameters(allocations=allocations)


@pytest.mark.asyncio
@pytest.mark.parametrize("processing", [None, {}, {"model": "synthetic"}])
async def test_publication_checks_actual_family_binding_when_approval_missing(processing):
    """实际家庭绑定不能被缺失Run审批伪装为单成员绕过发布Owner。"""

    class Session:
        """只返回实际家庭绑定，不模拟上游graph授权。"""

        async def scalar(self, _statement):
            return SimpleNamespace(family_planner_selection={"selection": "synthetic"})

    run = SimpleNamespace(conversation_id=1, input_payload={"health_processing": processing})
    with pytest.raises(HealthVisionError, match="policy_changed"):
        await service.validate_family_planner_publication(Session(), run, '{"questions": ["synthetic"]}')


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["uid", "agent_slug", "conversation_id", "thread", "approval", "missing"])
async def test_checkpoint_rejects_receipt_owned_by_inconsistent_run(change):
    """同账号同会话回执仍须核对所属Run的完整执行身份。"""
    binding = SimpleNamespace(actor_uid="synthetic-owner", conversation_id=3, family_planner_selection={"fixed": True})
    original = SimpleNamespace(
        uid=binding.actor_uid,
        agent_slug="health-meal-planner",
        conversation_id=3,
        conversation_thread_id="synthetic-thread",
        input_payload={
            "health_processing": {"family_selection_hash": input_fingerprint(binding.family_planner_selection)}
        },
    )
    if change == "approval":
        original.input_payload = {"health_processing": None}
    elif change == "thread":
        original.conversation_thread_id = "foreign-thread"
    elif change == "missing":
        original = None
    else:
        setattr(original, change, "foreign")
    receipt = SimpleNamespace(actor_uid=binding.actor_uid, conversation_id=3, operation="swap", run_id="old-run")

    class Session:
        """只返回持久身份，预览重算不能掩盖身份拒绝。"""

        async def get(self, model, _key):
            if model is AgentRun:
                return original
            if model is Conversation:
                return SimpleNamespace(thread_id="synthetic-thread")
            return receipt

    with pytest.raises(HealthVisionError, match="source_invalidated"):
        await service.validate_family_planner_tool_payload(
            Session(), binding, "preview_family_plan_swap", {"preview_id": str(uuid4())}
        )

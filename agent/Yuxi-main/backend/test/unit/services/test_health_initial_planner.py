"""固定初始工具、持久化原Run及发布审批的负控。"""

from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from yuxi.agents.toolkits.meal_planner import get_initial_plan_context, preview_initial_meal_plan
from yuxi.services import health_initial_planner_service as service
from yuxi.services.health_initial_meal_plan_types import InitialPlannerInput
from yuxi.services.health_nutrition_service import input_fingerprint
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.storage.postgres.models_business import AgentRun, Conversation


def test_initial_tools_have_no_model_parameters():
    """没有模型可控日期、身份、营养或规则参数。"""
    for tool in (get_initial_plan_context, preview_initial_meal_plan):
        assert tool.tool_call_schema.model_json_schema()["properties"] == {}


@pytest.mark.parametrize("extra", ["run_id", "uid", "nutrition", "grams", "professional_review"])
def test_initial_entry_rejects_fabricated_parameters(extra):
    """入口只允许明确业务选择，不接受计算或执行Owner。"""
    member = str(uuid4())
    body = {
        "client_request_id": str(uuid4()),
        "kind": "single",
        "plan_date": "2026-10-08",
        "rule_code": "synthetic",
        "rule_version": 1,
        "profile_versions": {member: 1},
        "meals": [{"meal_type": m, "participant_ids": [member]} for m in ("breakfast", "lunch", "dinner")],
    }
    InitialPlannerInput.model_validate(body)
    with pytest.raises(ValidationError):
        InitialPlannerInput.model_validate({**body, extra: "forged"})


@pytest.mark.asyncio
@pytest.mark.parametrize("processing", [None, {}, {"model": "synthetic"}])
async def test_initial_publication_cannot_drop_processing(processing):
    """实际初始绑定不能用缺失处理快照旁路发布。"""

    class Session:
        """仅返回真实初始绑定，模拟绕过上游投影的发布入口。"""

        async def scalar(self, _statement):
            return SimpleNamespace(initial_planner_selection={"fixed": True})

    run = SimpleNamespace(conversation_id=1, input_payload={"health_processing": processing})
    with pytest.raises(HealthVisionError, match="policy_changed"):
        await service.validate_initial_planner_publication(Session(), run, '{"questions":["synthetic"]}')


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["uid", "agent_slug", "conversation_id", "thread", "approval", "missing"])
async def test_initial_checkpoint_checks_original_run_identity(change):
    """历史合法回执也必须证明原Run的账号、角色、线程及固定选择。"""
    binding = SimpleNamespace(actor_uid="synthetic-owner", conversation_id=3, initial_planner_selection={"fixed": True})
    original = SimpleNamespace(
        uid=binding.actor_uid,
        agent_slug="health-meal-planner",
        conversation_id=3,
        conversation_thread_id="synthetic-thread",
        input_payload={
            "health_processing": {"initial_selection_hash": input_fingerprint(binding.initial_planner_selection)}
        },
    )
    if change == "approval":
        original.input_payload = {"health_processing": None}
    elif change == "thread":
        original.conversation_thread_id = "foreign"
    elif change == "missing":
        original = None
    else:
        setattr(original, change, "foreign")
    receipt = SimpleNamespace(actor_uid=binding.actor_uid, conversation_id=3, run_id="old-run")

    class Session:
        """只返回持久化身份，重算不能掩盖身份拒绝。"""

        async def get(self, model, _key):
            if model is AgentRun:
                return original
            if model is Conversation:
                return SimpleNamespace(thread_id="synthetic-thread")
            return receipt

    with pytest.raises(HealthVisionError, match="source_invalidated"):
        await service.validate_initial_planner_tool_payload(
            Session(), binding, "preview_initial_meal_plan", {"preview_id": str(uuid4())}
        )

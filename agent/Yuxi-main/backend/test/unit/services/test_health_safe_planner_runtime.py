"""单成员模式装配及共享历史入口禁止其他模式的负控。"""

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from langchain_core.messages import ToolMessage

from yuxi.agents.base import BaseContext
from yuxi.repositories.health_consultation_repository import HealthConsultationRepository
from yuxi.services import health_consultation_service as consultation
from yuxi.services import health_meal_plan_service as planner
from yuxi.services import health_safe_planner_service as safe
from yuxi.services.health_vision_types import HealthVisionError


@pytest.fixture
def safe_execution(monkeypatch):
    """仅隔离数据库I/O，共享模式路由与checkpoint策略执行真实代码。"""
    binding = SimpleNamespace(
        actor_uid="synthetic-safe-owner",
        member_id="synthetic-safe-member",
        conversation_id=3,
        safe_planner_selection={"selection": {"synthetic": True}},
        family_planner_selection=None,
        initial_planner_selection=None,
    )
    processing = {"model": "synthetic/fixed", "processor": "synthetic", "policy_version": "synthetic"}
    run = SimpleNamespace(
        id="synthetic-safe-run", agent_slug="health-meal-planner", input_payload={"health_processing": processing}
    )
    session = SimpleNamespace()

    @asynccontextmanager
    async def transaction():
        yield session

    monkeypatch.setattr(consultation.pg_manager, "get_async_session_context", transaction)
    monkeypatch.setattr(HealthConsultationRepository, "require_attempt", AsyncMock(return_value=run))
    monkeypatch.setattr(consultation, "require_consultation", AsyncMock(return_value=(binding, processing)))
    monkeypatch.setattr(planner, "require_planner_run", AsyncMock(return_value=(run, binding)))
    context = BaseContext(uid=binding.actor_uid, thread_id="synthetic-thread")
    return context, run, binding, session


@pytest.mark.asyncio
async def test_runtime_discards_user_resources_and_only_installs_three_safe_tools(safe_execution):
    """未受信任工具、Skill、模型与系统文字不能扩大该模式。"""
    context, run, _, session = safe_execution
    context.tools = ["search_meal_plan_recipes", "forged_write_tool"]
    context.skills = context.preload_skills = ["forged-skill"]
    context.knowledges = context.mcps = ["forged-resource"]
    context.system_prompt = "forged prompt"
    context.model = "forged/model"
    await consultation.prepare_consultation_context(context, session, run)
    assert context.tools == ["get_safe_plan_context", "preview_safe_plan_swap", "preview_safe_plan_regeneration"]
    assert context.model == "synthetic/fixed"
    assert context.skills == context.preload_skills == ["family-meal-planner"]
    assert context.knowledges == context.mcps == []
    assert "单成员已保存餐单模式" in context.system_prompt and "forged prompt" not in context.system_prompt


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "name",
    [
        "get_confirmed_profile",
        "get_complete_health_profile",
        "get_confirmed_meals",
        "query_reviewed_nutrition_knowledge",
        "search_meal_plan_recipes",
        "preview_meal_plan",
        "get_initial_plan_context",
        "get_family_plan_context",
        "forged_write_tool",
    ],
)
@pytest.mark.parametrize("status", ["success", "error"])
async def test_checkpoint_rejects_foreign_tools_before_old_health_branches(safe_execution, monkeypatch, name, status):
    """其他旧模式合法工具或错误消息也不能穿过共享history分支。"""
    context, _, _, _ = safe_execution
    verify = AsyncMock()
    monkeypatch.setattr(safe, "validate_safe_planner_tool_payload", verify)
    message = ToolMessage(content='{"records":[]}', name=name, tool_call_id="synthetic", status=status)
    with pytest.raises(HealthVisionError, match="source_invalidated"):
        await consultation.require_consultation_attempt(context, [message])
    verify.assert_not_awaited()


@pytest.mark.asyncio
async def test_checkpoint_sends_original_safe_payload_to_its_complete_validator(safe_execution, monkeypatch):
    """已选模式的真实验证Owner不能被共享旧分支跳过。"""
    context, _, binding, session = safe_execution
    verify = AsyncMock(side_effect=HealthVisionError("source_invalidated", "synthetic changed", 410))
    monkeypatch.setattr(safe, "validate_safe_planner_tool_payload", verify)
    message = ToolMessage(
        content='{"preview_id":"synthetic-receipt"}', name="preview_safe_plan_swap", tool_call_id="synthetic"
    )
    with pytest.raises(HealthVisionError, match="source_invalidated"):
        await consultation.require_consultation_attempt(context, [message])
    verify.assert_awaited_once_with(session, binding, "preview_safe_plan_swap", {"preview_id": "synthetic-receipt"})


@pytest.mark.asyncio
@pytest.mark.parametrize("entry", ["recipes", "preview"])
async def test_generic_planner_business_entry_cannot_bypass_the_saved_plan_mode(safe_execution, entry):
    """直接调用通用工具服务也必须在任何草稿写入前拒绝。"""
    context, _, _, _ = safe_execution
    with pytest.raises(HealthVisionError, match="planner_mode_conflict"):
        if entry == "recipes":
            await planner.meal_plan_recipes_for_run(context, "synthetic")
        else:
            await planner.create_meal_plan_preview(None, None, SimpleNamespace(), context=context)

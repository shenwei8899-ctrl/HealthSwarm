"""菜谱参考不能扩大检索范围、跳过政策或成为可保存菜谱。"""

import json
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from langchain_core.messages import ToolMessage

from test.unit.services.test_health_family_kb import _source_records
from test.unit.services.test_health_safe_planner_runtime import safe_execution  # noqa: F401
from yuxi.services import health_family_kb_service as service
from yuxi.services import health_consultation_service as consultation
from yuxi.services.health_vision_types import HealthVisionError


@pytest.mark.parametrize("configured", ["", "a,b", " "])
def test_recipe_binding_never_falls_back_to_family_library(monkeypatch, configured):
    """缺失或多个菜谱绑定不能回退家庭库。"""
    monkeypatch.setenv(service.KB_ID_ENV, "family")
    monkeypatch.setenv(service.RECIPE_KB_ID_ENV, configured)
    with pytest.raises(HealthVisionError, match="knowledge_unavailable"):
        service.configured_health_kb_ids("health-meal-planner")


async def test_recipe_search_only_returns_current_reference_and_rechecks_auth(monkeypatch):
    """检索前后重验授权且只输出参考来源。"""
    monkeypatch.setenv(service.RECIPE_KB_ID_ENV, "recipes")
    file, chunk = _source_records()
    session = SimpleNamespace(scalar=AsyncMock(side_effect=[chunk, file]))

    @asynccontextmanager
    async def transaction():
        """隔离检索事务依赖。"""
        yield session

    monkeypatch.setattr(service.pg_manager, "get_async_session_context", transaction)
    auth = AsyncMock(return_value=(SimpleNamespace(agent_slug="health-meal-planner"), None))
    monkeypatch.setattr(service, "_authorized_run", auth)
    monkeypatch.setattr(service, "_require_fixed_kb", AsyncMock())
    retrieve = AsyncMock(
        return_value={
            "results": [{"id": chunk.chunk_id, "file_id": file.file_id, "kb_id": "recipes", "content": chunk.content}]
        }
    )
    monkeypatch.setattr(service.knowledge_base, "retrieve", retrieve)
    result = await service.search_family_nutrition_knowledge(SimpleNamespace(), "蒸菜")
    assert result["scope"] == "recipe_reference" and result["kb_ids"] == ["recipes"]
    assert "recipe_version_id" not in json.dumps(result)
    assert auth.await_count == 2 and len(result["sources"]) == 1
    assert retrieve.call_args.kwargs == {
        "final_top_k": 4,
        "search_mode": "keyword",
        "use_reranker": False,
        "use_graph_retrieval": False,
        "read_only": True,
    }
    auth.side_effect = [auth.return_value, HealthVisionError("policy_changed", "撤回", 409)]
    session.scalar.side_effect = [chunk, file]
    with pytest.raises(HealthVisionError, match="policy_changed"):
        await service.search_family_nutrition_knowledge(SimpleNamespace(), "蒸菜")


@pytest.mark.parametrize("mode", [None, "safe", "initial", "family"])
async def test_all_modes_keep_exact_business_tools_and_add_reference(safe_execution, monkeypatch, mode):  # noqa: F811
    """四模式均保留业务工具并为参考检索保留步骤预算。"""
    from yuxi.agents.buildin.health_meal_planner import graph
    from yuxi.services.health_safe_planner_types import SAFE_PLANNER_TOOLS
    from yuxi.services.health_initial_meal_plan_types import INITIAL_PLANNER_TOOLS
    from yuxi.services.health_family_planner_types import FAMILY_PLANNER_TOOLS

    context, run, binding, session = safe_execution
    for key in ["safe", "initial", "family"]:
        setattr(binding, key + "_planner_selection", {"fixed": True} if key == mode else None)
    await consultation.prepare_consultation_context(context, session, run)
    expected = {
        None: ("search_meal_plan_recipes", "preview_meal_plan"),
        "safe": SAFE_PLANNER_TOOLS,
        "initial": INITIAL_PLANNER_TOOLS,
        "family": FAMILY_PLANNER_TOOLS,
    }[mode]
    assert context.tools == [*expected, service.TOOL_NAME]
    assert context.max_execution_steps == 40
    assert "recipe_reference" in context.system_prompt
    context._runtime_prepared = True
    captured = {}
    monkeypatch.setattr(graph, "create_agent", lambda **kw: captured.update(kw) or captured)
    monkeypatch.setattr(graph, "load_chat_model", lambda **kw: object())
    monkeypatch.setattr(graph.model_cache, "get_model_info", lambda name: {})
    monkeypatch.setattr(graph.HealthMealPlannerAgent, "_get_checkpointer", AsyncMock(return_value=None))
    await graph.HealthMealPlannerAgent().get_graph(context=context)
    assert [tool.name for tool in captured["tools"]] == [*expected, service.TOOL_NAME]


async def test_safe_checkpoint_routes_recipe_audit_to_source_validation(safe_execution, monkeypatch):  # noqa: F811
    """安全模式恢复必须核对菜谱参考来源。"""
    context, _, binding, session = safe_execution
    verify = AsyncMock(side_effect=HealthVisionError("source_invalidated", "来源改版", 410))
    monkeypatch.setattr(service, "validate_family_kb_checkpoint", verify)
    message = ToolMessage(content="{}", name=service.TOOL_NAME, tool_call_id="audit")
    with pytest.raises(HealthVisionError, match="source_invalidated"):
        await consultation.require_consultation_attempt(context, [message])
    verify.assert_awaited_once_with(session, context, binding, message)


async def test_missing_policy_denies_recipe_tool_before_retrieval(safe_execution, monkeypatch):  # noqa: F811
    """政策未通过时不触发检索。"""
    context, _, _, _ = safe_execution
    monkeypatch.setattr(
        consultation, "require_consultation", AsyncMock(side_effect=HealthVisionError("policy_changed", "未审批", 409))
    )
    retrieve = AsyncMock()
    monkeypatch.setattr(service.knowledge_base, "retrieve", retrieve)
    with pytest.raises(HealthVisionError, match="policy_changed"):
        await service.search_family_nutrition_knowledge(context, "蒸菜")
    retrieve.assert_not_called()

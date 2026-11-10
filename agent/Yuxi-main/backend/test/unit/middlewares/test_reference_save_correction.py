"""真实 SDK/ToolNode 校验纠正；合成服务不代替供应商、PG 或服务器验收。"""

import copy
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from langchain.agents import create_agent
from langchain.agents.middleware.types import ModelResponse
from langchain_core.messages import AIMessage, ToolMessage
from langgraph.checkpoint.memory import InMemorySaver

from test.unit.middlewares import test_reference_meal_finalization as original
from yuxi.agents.buildin.health_meal_planner.graph import MealPlanResultMiddleware
from yuxi.models.chat import ChatCompletionsAdapter
from yuxi.services import health_meal_plan_service, reference_meal_plan_service, reference_meal_selection_service
from yuxi.services.health_vision_types import HealthVisionError


@pytest.fixture
def services(monkeypatch):
    """服务返回固定独立快照，保存入参仍经过真实工具 Schema。"""
    saved = AsyncMock(return_value=original.snapshot())
    assembled = AsyncMock(return_value=original.ReferencePlanDraft.model_validate(original.DRAFT))
    final = AsyncMock(return_value=original.snapshot())
    monkeypatch.setattr(reference_meal_plan_service, "save_reference_plan", saved)
    monkeypatch.setattr(reference_meal_selection_service, "assemble_reference_selection", assembled)
    monkeypatch.setattr(health_meal_plan_service, "planner_final_result", final)
    return SimpleNamespace(saved=saved, assembled=assembled, final=final)


@pytest.mark.parametrize("scenario", ["recover", "repeat", "other_tool", "final_text"])
def test_legacy_free_form_purchase_mapping_is_rejected_by_tool_schema(scenario, services):
    """旧自由食材对应不能再进入模型工具，无论模型准备如何纠正。"""
    from pydantic import ValidationError

    from yuxi.agents.toolkits.meal_planner import ReferencePlanToolInput

    invalid = copy.deepcopy(original.DRAFT)
    invalid["purchase_gaps"].append(copy.deepcopy(invalid["purchase_gaps"][0]))
    with pytest.raises(ValidationError):
        ReferencePlanToolInput.model_validate(invalid)
    services.saved.assert_not_awaited()
    services.assembled.assert_not_awaited()


@pytest.mark.asyncio
async def test_real_sdk_corrects_unmatched_product_once(services):
    """商品不对应原谱时，模型只可按工具回执重选一次。"""
    services.saved.side_effect = [
        HealthVisionError("reference_ingredient_mismatch", "所选规格未对应任何本次原谱食材", 422),
        original.snapshot(),
    ]
    wires = []

    def respond(request):
        wire = json.loads(request.content)
        wires.append(wire)
        index = len(wires)
        message = {"role": "assistant", "content": ""}
        if index == 1:
            args = original.SAVE_ARGS
        elif index == 2:
            assert wire["tool_choice"] == {"type": "function", "function": {"name": "save_reference_meal_plan"}}
            feedback = next(item for item in wire["messages"] if item["role"] == "tool")
            payload = json.loads(feedback["content"])
            assert payload["error_code"] == "reference_ingredient_mismatch"
            assert payload["retryable"] is True
            assert any(
                "candidate_products" in str(item.get("content"))
                for item in wire["messages"]
                if item["role"] == "system"
            )
            args = original.SAVE_ARGS
        else:
            assert index == 3 and "tools" not in wire
            message["content"] = json.dumps({"preview_id": original.PREVIEW})
            args = None
        if args is not None:
            message["tool_calls"] = [
                {
                    "id": f"save-{index}",
                    "type": "function",
                    "function": {
                        "name": "save_reference_meal_plan",
                        "arguments": json.dumps(args),
                    },
                }
            ]
        return original.sdk_response(message, f"mismatch-{index}", 2, 3, stream=wire.get("stream") is True)

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        model = ChatCompletionsAdapter(
            model="synthetic",
            api_key="synthetic-test-key",
            base_url="https://example.invalid/v1",
            http_async_client=client,
            use_responses_api=False,
            max_retries=0,
        )
        graph = create_agent(
            model,
            tools=original.TOOLS,
            middleware=[MealPlanResultMiddleware()],
            context_schema=original.Context,
            checkpointer=InMemorySaver(),
        )
        context = original.Context()
        state = await graph.ainvoke(
            {"messages": [original.human()]},
            context=context,
            config={"configurable": {"thread_id": context.thread_id}},
        )

    assert len(wires) == 3
    assert services.saved.await_count == 2
    assert services.assembled.await_count == 2
    assert services.assembled.await_args_list[0].kwargs["allow_purchase_fallback"] is False
    assert services.assembled.await_args_list[1].kwargs["allow_purchase_fallback"] is True
    assert json.loads(state["messages"][-1].text) == original.snapshot()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "code",
    [
        "reference_duplicate_meals",
        "reference_duplicate_sku",
        "reference_purchase_coverage_invalid",
        "reference_ingredient_mismatch",
        "recipe_translation_invalid",
    ],
)
async def test_current_validation_failure_cannot_be_ignored_or_retried_twice(code, services):
    """各供应商均受同一次预算约束；已知失败后不能直接输出正文完成。"""
    call = {"id": "first-save", "name": "save_reference_meal_plan", "args": original.SAVE_ARGS}
    messages = [
        original.human(),
        AIMessage("", tool_calls=[call]),
        ToolMessage(
            json.dumps({"error_code": code, "retryable": True}),
            name="save_reference_meal_plan",
            tool_call_id="first-save",
            status="error",
        ),
    ]
    handler = AsyncMock(return_value=ModelResponse(result=[AIMessage("未经保存的完成声明")]))
    middleware = MealPlanResultMiddleware()
    request = original.request_for(messages)
    invalid = (
        "reference_translation_correction_invalid"
        if code == "recipe_translation_invalid"
        else "reference_save_correction_invalid"
    )
    exhausted = (
        "reference_translation_correction_invalid"
        if code == "recipe_translation_invalid"
        else "reference_save_correction_exhausted"
    )
    with pytest.raises(HealthVisionError, match=invalid):
        await middleware.aafter_model({"messages": [*messages, AIMessage("未经保存的完成声明")]}, request.runtime)
    request = original.request_for([*messages, AIMessage("", tool_calls=[{**call, "id": "second-save"}])])
    with pytest.raises(HealthVisionError, match=exhausted):
        await middleware.awrap_model_call(request, handler)
    handler.assert_not_awaited()


def test_context_pruning_keeps_current_tools_and_prior_final_answers():
    """只裁掉旧轮工具流水；当前原文回执与未改动 checkpoint 保持独立。"""
    old = original.human("previous-request")
    old_call = AIMessage("", tool_calls=[{"id": "old", "name": "save_reference_meal_plan", "args": original.DRAFT}])
    old_result = ToolMessage("旧流水", name="save_reference_meal_plan", tool_call_id="old")
    old_final = AIMessage("旧轮最终答复")
    current = original.human()
    current_call = AIMessage("", tool_calls=[{"id": "now", "name": "read_reference_recipe", "args": {}}])
    current_read = ToolMessage("当前原文", name="read_reference_recipe", tool_call_id="now")
    messages = [old, old_call, old_result, old_final, current, current_call, current_read]
    request = original.request_for(messages)
    assert MealPlanResultMiddleware._reference_model_messages(request) == [
        old,
        old_final,
        current,
        current_call,
        current_read,
    ]
    assert request.state["messages"] == messages
    assert (
        MealPlanResultMiddleware._reference_model_messages(
            original.request_for(messages, original.Context(request_id="other"))
        )
        == messages
    )

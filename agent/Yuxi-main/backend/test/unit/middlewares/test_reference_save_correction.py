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
from yuxi.services import health_meal_plan_service, reference_meal_plan_service
from yuxi.services.health_vision_types import HealthVisionError


@pytest.fixture
def services(monkeypatch):
    """服务返回固定独立快照，保存入参仍经过真实工具 Schema。"""
    saved = AsyncMock(return_value=original.snapshot())
    final = AsyncMock(return_value=original.snapshot())
    monkeypatch.setattr(reference_meal_plan_service, "save_reference_plan", saved)
    monkeypatch.setattr(health_meal_plan_service, "planner_final_result", final)
    return SimpleNamespace(saved=saved, final=final)


@pytest.mark.asyncio
@pytest.mark.parametrize("scenario", ["recover", "repeat", "other_tool", "final_text"])
async def test_real_sdk_corrects_duplicate_coverage_only_once(scenario, services):
    """重复食材不得进入服务；真实错误反馈触发一次定向保存，其他响应拒绝。"""
    invalid = copy.deepcopy(original.DRAFT)
    invalid["purchase_gaps"].append(copy.deepcopy(invalid["purchase_gaps"][0]))
    wires = []

    def respond(request):
        wire = json.loads(request.content)
        wires.append(wire)
        index = len(wires)
        message = {"role": "assistant", "content": ""}
        if index == 1:
            args, name = invalid, "save_reference_meal_plan"
        elif index == 2:
            assert wire["tool_choice"] == {"type": "function", "function": {"name": "save_reference_meal_plan"}}
            assert wire["parallel_tool_calls"] is False and wire.get("stream") is False
            failed = next(m for m in wire["messages"] if m["role"] == "tool")
            payload = json.loads(failed["content"])
            assert payload["error_code"] == "reference_purchase_coverage_invalid"
            assert payload["retryable"] is True and payload["message"]
            assert "合成食材" not in failed["content"] and "kwargs" not in failed["content"]
            args = invalid if scenario == "repeat" else original.DRAFT
            name = "read_reference_recipe" if scenario == "other_tool" else "save_reference_meal_plan"
            if scenario == "final_text":
                message["content"] = "未经保存的完成声明"
        else:
            assert scenario == "recover" and index == 3 and "tools" not in wire and "tool_choice" not in wire
            message["content"] = json.dumps({"preview_id": original.PREVIEW})
            args, name = None, None
        if not message["content"]:
            message["tool_calls"] = [
                {"id": f"save-{index}", "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}
            ]
        return original.sdk_response(message, f"validation-{index}", 2, 3, stream=wire.get("stream") is True)

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        model = ChatCompletionsAdapter(
            model="synthetic",
            api_key="synthetic-test-key",
            base_url="https://example.invalid/v1",
            http_async_client=client,
            use_responses_api=False,
            max_retries=0,
        )
        checkpoint = InMemorySaver()
        graph = create_agent(
            model,
            tools=original.TOOLS,
            middleware=[MealPlanResultMiddleware()],
            context_schema=original.Context,
            checkpointer=checkpoint,
        )
        context = original.Context()
        config = {"configurable": {"thread_id": context.thread_id}}
        if scenario == "recover":
            await graph.ainvoke({"messages": [original.human()]}, context=context, config=config)
        else:
            code = (
                "reference_save_correction_exhausted" if scenario == "repeat" else "reference_save_correction_invalid"
            )
            with pytest.raises(HealthVisionError, match=code):
                await graph.ainvoke({"messages": [original.human()]}, context=context, config=config)
        state = await graph.aget_state(config)

    feedback = [m for m in state.values["messages"] if isinstance(m, ToolMessage)]
    assert feedback[0].status == "error" and feedback[0].tool_call_id == "save-1"
    assert len(wires) == (3 if scenario == "recover" else 2)
    if scenario == "recover":
        services.saved.assert_awaited_once()
        assert original.ReferencePlanDraft.model_validate(
            services.saved.await_args.args[1]
        ) == original.ReferencePlanDraft.model_validate(original.DRAFT)
        assert json.loads(state.values["messages"][-1].text) == original.snapshot()
    else:
        services.saved.assert_not_awaited()
        services.final.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "code", ["reference_duplicate_meals", "reference_duplicate_sku", "reference_purchase_coverage_invalid"]
)
async def test_current_validation_failure_cannot_be_ignored_or_retried_twice(code, services):
    """各供应商均受同一次预算约束；已知失败后不能直接输出正文完成。"""
    call = {"id": "first-save", "name": "save_reference_meal_plan", "args": original.DRAFT}
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
    with pytest.raises(HealthVisionError, match="reference_save_correction_invalid"):
        await middleware.aafter_model({"messages": [*messages, AIMessage("未经保存的完成声明")]}, request.runtime)
    request = original.request_for([*messages, AIMessage("", tool_calls=[{**call, "id": "second-save"}])])
    with pytest.raises(HealthVisionError, match="reference_save_correction_exhausted"):
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

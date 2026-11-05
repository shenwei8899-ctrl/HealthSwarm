"""真实工具执行器验证保存校验反馈，不连接数据库或供应商。"""

import json
from dataclasses import dataclass
from unittest.mock import AsyncMock

import pytest
from langchain.agents import create_agent
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode
from langgraph.prebuilt.tool_node import ToolRuntime
from pydantic import Field, ValidationError

from yuxi.agents.buildin.health_meal_planner.graph import MealPlanResultMiddleware
from yuxi.agents.toolkits.meal_planner import (
    read_reference_recipe,
    reference_quote_failure_index,
    reference_save_failure_index,
    save_reference_meal_plan,
)
from yuxi.services import health_meal_plan_service, reference_meal_plan_service
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.services.reference_meal_plan_types import REFERENCE_TOOLS, ReferencePlanDraft


@dataclass
class SaveContext:
    """运行身份均为合成值，真实 ToolNode 负责注入。"""

    uid: str = "synthetic-owner"
    request_id: str = "synthetic-save-request"
    tools: tuple = REFERENCE_TOOLS


class FeedbackSaveModel(GenericFakeChatModel):
    """只在真实错误回执已到达模型后才发出预定的纠正调用。"""

    observed_feedback: list[dict] = Field(default_factory=list)
    generated_count: int = 0

    def bind_tools(self, tools, **kwargs):
        """保留真实 create_agent 工具执行器。"""
        return self

    def _generate(self, messages, *args, **kwargs):
        """核对纠正前收到的安全反馈。"""
        self.generated_count += 1
        if isinstance(messages[-1], ToolMessage) and messages[-1].status == "error":
            payload = json.loads(messages[-1].content)
            assert payload["message"]
            assert payload.get("retryable") is True or payload.get("error_code") == "reference_quote_invalid"
            self.observed_feedback.append(payload)
        return super()._generate(messages, *args, **kwargs)


def draft():
    """一条食材只对应一个明确采购决定。"""
    return {
        "meals": [
            {
                "meal_type": "breakfast",
                "dishes": [
                    {
                        "file_id": "synthetic-file",
                        "chunk_id": "synthetic-chunk",
                        "name": "合成清粥",
                        "ingredients": ["合成大米原文"],
                        "steps": ["合成煮粥步骤"],
                    }
                ],
            }
        ],
        "purchase_items": [],
        "purchase_gaps": [{"ingredient": "合成大米原文", "reason": "needs_confirmation", "detail": "合成包装待确认"}],
    }


def invalid_draft(kind):
    """保持全部字段完整，仅破坏指定业务不变量。"""
    value = draft()
    if kind == "duplicate_meals":
        value["meals"] *= 2
    elif kind == "duplicate_sku":
        value["purchase_items"] = [{"sku_id": "synthetic-sku", "quantity": 1, "ingredient_refs": ["合成大米原文"]}] * 2
    elif kind == "duplicate_decision":
        value["purchase_gaps"] *= 2
    elif kind == "missing_decision":
        value["purchase_gaps"] = []
    else:
        raise AssertionError(kind)
    return value


def declared(call_id, payload=None):
    """创建标准模型工具声明。"""
    return AIMessage(
        content="", tool_calls=[{"id": call_id, "name": save_reference_meal_plan.name, "args": payload or {}}]
    )


def failure(call_id="invalid", *, quote=False, **updates):
    """创建合成真实类型回执，供身份与预算边界负控。"""
    payload = (
        {"error_code": "reference_quote_invalid", "request_id": SaveContext().request_id}
        if quote
        else {"error_code": "reference_purchase_coverage_invalid", "retryable": True}
    )
    payload.update(updates)
    return ToolMessage(
        name=save_reference_meal_plan.name, tool_call_id=call_id, status="error", content=json.dumps(payload)
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kind,code",
    [
        ("duplicate_meals", "reference_duplicate_meals"),
        ("duplicate_sku", "reference_duplicate_sku"),
        ("duplicate_decision", "reference_purchase_coverage_invalid"),
        ("missing_decision", "reference_purchase_coverage_invalid"),
    ],
)
async def test_real_tool_node_returns_safe_root_validation_feedback(monkeypatch, kind, code):
    """三类模型级错误仍拒绝，但不会被公共过滤器清空原因。"""
    service = AsyncMock()
    monkeypatch.setattr(reference_meal_plan_service, "save_reference_plan", service)
    bad = invalid_draft(kind)
    with pytest.raises(ValidationError):
        ReferencePlanDraft.model_validate(bad)
    graph = StateGraph(MessagesState, context_schema=SaveContext)
    graph.add_node("tools", ToolNode([save_reference_meal_plan]))
    graph.add_edge(START, "tools")
    graph.add_edge("tools", END)
    result = await graph.compile().ainvoke({"messages": [declared("invalid", bad)]}, context=SaveContext())
    receipt = result["messages"][-1]
    assert isinstance(receipt, ToolMessage)
    assert receipt.status == "error" and receipt.tool_call_id == "invalid"
    payload = json.loads(receipt.content)
    assert payload["error_code"] == code and payload["retryable"] is True and payload["message"]
    assert "合成大米原文" not in receipt.content and "with kwargs" not in receipt.content
    service.assert_not_awaited()


@pytest.mark.asyncio
async def test_real_create_agent_receives_feedback_then_only_saves_the_corrected_draft(monkeypatch):
    """真实图把失败送回模型，纠正后的服务只执行一次。"""
    service = AsyncMock(return_value={"preview_id": "synthetic-saved-preview"})
    monkeypatch.setattr(reference_meal_plan_service, "save_reference_plan", service)
    model = FeedbackSaveModel(
        messages=iter(
            [
                declared("invalid", invalid_draft("duplicate_decision")),
                declared("corrected", draft()),
                AIMessage(content="合成最终结果"),
            ]
        )
    )
    graph = create_agent(model, tools=[save_reference_meal_plan], context_schema=SaveContext)
    result = await graph.ainvoke({"messages": [HumanMessage("合成保存请求")]}, context=SaveContext())
    receipts = [item for item in result["messages"] if isinstance(item, ToolMessage)]
    assert [(item.tool_call_id, item.status) for item in receipts] == [("invalid", "error"), ("corrected", "success")]
    assert [item["error_code"] for item in model.observed_feedback] == ["reference_purchase_coverage_invalid"]
    service.assert_awaited_once()
    context, saved = service.await_args.args
    assert context == SaveContext()
    assert ReferencePlanDraft.model_validate(saved) == ReferencePlanDraft.model_validate(draft())
    assert "synthetic-saved-preview" in receipts[-1].content


@pytest.mark.parametrize("kind", ["unknown_root", "runtime", "nested", "missing", "extra"])
def test_other_validation_failures_do_not_echo_input_or_invite_a_retry(kind):
    """未知和运行对象错误保持失败，任何输入或异常上下文均不回显。"""
    secret = "synthetic-secret-sentinel-password-never-echo"
    if kind == "unknown_root":
        error = ValidationError.from_exception_data(
            "SyntheticModel",
            [{"type": "value_error", "loc": (), "input": {"password": secret}, "ctx": {"error": ValueError(secret)}}],
        )
    else:
        value = {**draft(), "runtime": ToolRuntime({}, SaveContext(), {}, lambda _: None, "invalid", None)}
        if kind == "runtime":
            value["runtime"] = {"password": secret}
        elif kind == "nested":
            value["meals"][0]["meal_type"] = secret
        elif kind == "missing":
            del value["purchase_gaps"]
        else:
            value["secret"] = secret
        with pytest.raises(ValidationError) as caught:
            save_reference_meal_plan.args_schema.model_validate(value)
        error = caught.value
    payload_text = save_reference_meal_plan.handle_validation_error(error)
    payload = json.loads(payload_text)
    assert payload["retryable"] is False and payload["message"]
    assert payload["error_code"] == (
        "reference_runtime_invalid" if kind == "runtime" else "reference_plan_validation_failed"
    )
    assert secret not in payload_text and "input" not in payload and "ctx" not in payload


@pytest.mark.parametrize("quote", [False, True])
@pytest.mark.parametrize(
    "boundary",
    [
        "current",
        "old_request",
        "no_marker",
        "unbound",
        "duplicate_before",
        "duplicate_after",
        "future_declaration",
        "wrong_name",
        "success",
        "wrong_payload_request",
        "empty_call_id",
        "non_object",
    ],
)
def test_save_failure_index_requires_current_unique_prior_call(quote, boundary):
    """不接受旧请求、无声明、重复声明或失败前不存在的调用。"""
    context = SaveContext()
    human = HumanMessage("合成保存", additional_kwargs={"health_request_id": context.request_id})
    messages = [human, declared("invalid"), failure(quote=quote)]
    if boundary == "old_request":
        human.additional_kwargs["health_request_id"] = "old-request"
    elif boundary == "no_marker":
        human.additional_kwargs.clear()
    elif boundary == "unbound":
        messages.pop(1)
    elif boundary == "duplicate_before":
        messages.insert(2, declared("invalid"))
    elif boundary == "duplicate_after":
        messages.append(declared("invalid"))
    elif boundary == "future_declaration":
        messages[1], messages[2] = messages[2], messages[1]
    elif boundary == "wrong_name":
        messages[-1].name = "read_reference_recipe"
    elif boundary == "success":
        messages[-1].status = "success"
    elif boundary == "wrong_payload_request":
        messages[-1] = failure(quote=quote, request_id="other-request")
    elif boundary == "empty_call_id":
        messages[1] = declared("")
        messages[2] = failure("", quote=quote)
    elif boundary == "non_object":
        messages[-1].content = "[]"
    if boundary in {"duplicate_before", "duplicate_after", "empty_call_id"}:
        with pytest.raises(HealthVisionError, match="reference_save_correction_invalid"):
            reference_save_failure_index(messages, context.request_id)
        with pytest.raises(HealthVisionError, match="reference_save_correction_invalid"):
            reference_quote_failure_index(messages, context.request_id)
        return
    expected = 2 if boundary == "current" else None
    assert reference_save_failure_index(messages, context.request_id) == expected
    assert reference_quote_failure_index(messages, context.request_id) == (expected if quote else None)


@pytest.mark.parametrize("retryable", [False, 1, "true", None])
def test_save_failure_index_rejects_non_true_validation_flags(retryable):
    """只有布尔True能开启参数纠正，不接受数字或字符串。"""
    context = SaveContext()
    messages = [
        HumanMessage("合成保存", additional_kwargs={"health_request_id": context.request_id}),
        declared("invalid"),
        failure(retryable=retryable),
    ]
    assert reference_save_failure_index(messages, context.request_id) is None


@pytest.mark.asyncio
async def test_validation_then_quote_failure_has_one_separate_bounded_correction(monkeypatch):
    """采购和引文各有一次修正，同类引文再次失败必须抛出。"""
    context = SaveContext()
    messages = [
        HumanMessage("合成保存", additional_kwargs={"health_request_id": context.request_id}),
        declared("invalid"),
        failure(),
        declared("corrected"),
    ]
    error = HealthVisionError("reference_quote_invalid", "合成引文拒绝", 422)
    service = AsyncMock(side_effect=error)
    monkeypatch.setattr(reference_meal_plan_service, "save_reference_plan", service)
    runtime = ToolRuntime({"messages": messages}, context, {}, lambda _: None, "corrected", None)
    feedback = await save_reference_meal_plan.coroutine(runtime=runtime, meals=[], purchase_items=[], purchase_gaps=[])
    assert isinstance(feedback, ToolMessage) and feedback.status == "error"
    assert json.loads(feedback.content)["error_code"] == "reference_quote_invalid"
    messages.extend([feedback, declared("second-quote")])
    runtime = ToolRuntime({"messages": messages}, context, {}, lambda _: None, "second-quote", None)
    with pytest.raises(HealthVisionError) as caught:
        await save_reference_meal_plan.coroutine(runtime=runtime, meals=[], purchase_items=[], purchase_gaps=[])
    assert caught.value is error
    assert reference_save_failure_index(messages, context.request_id) == 4


@pytest.mark.asyncio
@pytest.mark.parametrize("scenario", ["duplicate_before", "after_validation", "after_quote", "empty_call_id"])
async def test_real_middleware_stops_reused_save_call_ids_before_another_service_call(monkeypatch, scenario):
    """空或重复调用身份明确中止，不能擦掉失败或进入后续服务及模型调用。"""
    service = AsyncMock(return_value={"preview_id": "must-not-be-saved"})
    if scenario == "after_quote":
        service.side_effect = HealthVisionError("reference_quote_invalid", "合成引文拒绝", 422)
    final = AsyncMock()
    read = AsyncMock()
    monkeypatch.setattr(reference_meal_plan_service, "save_reference_plan", service)
    monkeypatch.setattr(reference_meal_plan_service, "read_reference_recipe", read)
    monkeypatch.setattr(health_meal_plan_service, "planner_final_result", final)
    if scenario == "duplicate_before":
        messages = [AIMessage(content="", tool_calls=[*declared("reused", draft()).tool_calls] * 2)]
    elif scenario == "empty_call_id":
        messages = [
            declared("", draft()),
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "id": "must-not-run",
                        "name": "read_reference_recipe",
                        "args": {"file_id": "synthetic-file", "chunk_id": "synthetic-chunk"},
                    }
                ],
            ),
        ]
    else:
        first = draft() if scenario == "after_quote" else invalid_draft("duplicate_decision")
        messages = [declared("reused", first), declared("reused", draft())]
    model = FeedbackSaveModel(messages=iter(messages))
    graph = create_agent(
        model,
        tools=[save_reference_meal_plan, read_reference_recipe],
        middleware=[MealPlanResultMiddleware()],
        context_schema=SaveContext,
    )
    context = SaveContext()
    human = HumanMessage("合成保存", additional_kwargs={"health_request_id": context.request_id})
    with pytest.raises(HealthVisionError, match="reference_save_correction_invalid"):
        await graph.ainvoke({"messages": [human]}, context=context)
    if scenario == "after_quote":
        service.assert_awaited_once()
    else:
        service.assert_not_awaited()
    read.assert_not_awaited()
    final.assert_not_awaited()
    before_tools = scenario in {"duplicate_before", "empty_call_id"}
    assert len(model.observed_feedback) == (0 if before_tools else 1)
    assert model.generated_count == (1 if before_tools else 2)

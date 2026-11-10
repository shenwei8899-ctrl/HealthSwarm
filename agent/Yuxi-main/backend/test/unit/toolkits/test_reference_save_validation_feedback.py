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
    ReferencePlanToolInput,
    read_reference_recipe,
    reference_quote_failure_index,
    reference_save_failure_index,
    save_reference_meal_plan,
)
from yuxi.services import health_meal_plan_service, reference_meal_plan_service, reference_meal_selection_service
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.services.reference_meal_plan_types import REFERENCE_TOOLS, ReferencePlanDraft
from yuxi.services.reference_meal_selection_service import apply_reference_translation_correction


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


def read_selection():
    """三餐首次选择与译文修正测试仅使用合成来源。"""
    return {
        "use_read_recipes": True,
        "auto_purchase_matches": True,
        "meals": [
            {
                "meal_type": meal,
                "dishes": [{"file_id": f"file-{meal}", "chunk_id": "chunk", "cooking_minutes": 15}],
            }
            for meal in ("breakfast", "lunch", "dinner")
        ],
        "product_matches": [
            {"product_id": "synthetic-product", "candidate_keys": ["ingredient:synthetic"]}
        ],
    }


def translation_patch(meal="lunch"):
    """只提交一份既有菜谱的展示译文。"""
    return {
        "file_id": f"file-{meal}",
        "chunk_id": "chunk",
        "display_zh": {
            "name": "合成菜谱",
            "ingredients": ["合成食材 1 份"],
            "steps": ["合成制作 15 分钟"],
        },
    }


def test_translation_patch_keeps_first_meals_and_purchase():
    """修正只改变指定译文，遗漏早餐或改 SKU 都不能重写首次选择。"""
    original = read_selection()
    corrected = apply_reference_translation_correction(original, [translation_patch()])
    assert [meal["meal_type"] for meal in corrected["meals"]] == ["breakfast", "lunch", "dinner"]
    assert corrected["product_matches"] == original["product_matches"]
    assert corrected["meals"][1]["dishes"][0]["display_zh"]["name"] == "合成菜谱"
    assert "display_zh" not in original["meals"][1]["dishes"][0]
    with pytest.raises(HealthVisionError, match="reference_translation_correction_invalid"):
        apply_reference_translation_correction(original, [translation_patch("snack")])
    with pytest.raises(HealthVisionError, match="reference_translation_correction_invalid"):
        apply_reference_translation_correction(original, [translation_patch(), translation_patch()])
    runtime = ToolRuntime({}, SaveContext(), {}, lambda _: None, "synthetic", None)
    ReferencePlanToolInput.model_validate({"runtime": runtime, "translation_correction": [translation_patch()]})
    with pytest.raises(ValidationError):
        ReferencePlanToolInput.model_validate(
            {"runtime": runtime, "read_selection": original, "translation_correction": [translation_patch()]}
        )


@pytest.mark.asyncio
async def test_real_tool_node_repairs_malformed_first_translation_without_changing_meals(monkeypatch):
    """首次译文缺步骤时工具回执可修正，原三餐与采购保持首次选择。"""
    original = read_selection()
    original["meals"][1]["dishes"][0]["display_zh"] = {
        "name": "合成菜谱",
        "ingredients": ["合成食材 1 份"],
        "steps": [],
    }
    context = SaveContext()
    graph = StateGraph(MessagesState, context_schema=SaveContext)
    graph.add_node("tools", ToolNode([save_reference_meal_plan]))
    graph.add_edge(START, "tools")
    graph.add_edge("tools", END)
    compiled = graph.compile()
    assemble = AsyncMock(return_value={"synthetic": "draft"})
    save = AsyncMock(return_value={"preview_id": "synthetic-preview"})
    monkeypatch.setattr(reference_meal_selection_service, "assemble_reference_selection", assemble)
    monkeypatch.setattr(reference_meal_plan_service, "save_reference_plan", save)

    first = await compiled.ainvoke(
        {
            "messages": [
                HumanMessage("合成三餐", additional_kwargs={"health_request_id": context.request_id}),
                declared("first", {"read_selection": original}),
            ]
        },
        context=context,
    )
    failed = first["messages"][-1]
    assert failed.status == "error"
    assert json.loads(failed.content)["error_code"] == "recipe_translation_invalid"
    save.assert_not_awaited()

    second = await compiled.ainvoke(
        {"messages": [*first["messages"], declared("retry", {"translation_correction": [translation_patch()]})]},
        context=context,
    )
    assert json.loads(second["messages"][-1].content) == {"preview_id": "synthetic-preview"}
    corrected = assemble.await_args.args[1]
    assert [meal["meal_type"] for meal in corrected["meals"]] == ["breakfast", "lunch", "dinner"]
    assert corrected["product_matches"] == original["product_matches"]
    assert corrected["meals"][1]["dishes"][0]["display_zh"]["steps"] == ["合成制作 15 分钟"]
    save.assert_awaited_once()


@pytest.mark.asyncio
async def test_translation_retry_uses_first_selection_only(monkeypatch):
    """实际 ToolRuntime 修正路径从同一请求失败声明取回首次三餐。"""
    context = SaveContext()
    patch = translation_patch()
    messages = [
        HumanMessage("合成三餐", additional_kwargs={"health_request_id": context.request_id}),
        declared("first", {"read_selection": read_selection()}),
        failure("first", error_code="recipe_translation_invalid", request_id=context.request_id, retryable=True),
        declared("retry", {"translation_correction": [patch]}),
    ]
    assemble = AsyncMock(return_value={"synthetic": "draft"})
    save = AsyncMock(return_value={"preview_id": "synthetic-preview"})
    monkeypatch.setattr(reference_meal_selection_service, "assemble_reference_selection", assemble)
    monkeypatch.setattr(reference_meal_plan_service, "save_reference_plan", save)
    runtime = ToolRuntime({"messages": messages}, context, {}, lambda _: None, "retry", None)
    result = await save_reference_meal_plan.coroutine(runtime=runtime, translation_correction=[patch])
    assert result == {"preview_id": "synthetic-preview"}
    assert [meal["meal_type"] for meal in assemble.call_args.args[1]["meals"]] == ["breakfast", "lunch", "dinner"]
    assert assemble.call_args.args[1]["product_matches"] == read_selection()["product_matches"]
    save.assert_awaited_once()


@pytest.mark.asyncio
async def test_translation_retry_preserves_prior_purchase_fallback(monkeypatch):
    """包装纠正已降级为自行购买后，译文修正不能恢复严格 SKU 校验。"""
    context = SaveContext()
    selected = read_selection()
    patch = translation_patch()
    messages = [
        HumanMessage("合成保存", additional_kwargs={"health_request_id": context.request_id}),
        declared("first", {"read_selection": selected}),
        failure(
            "first",
            error_code="reference_ingredient_mismatch",
            request_id=context.request_id,
            retryable=True,
        ),
        declared("fallback", {"read_selection": selected}),
        failure(
            "fallback",
            error_code="recipe_translation_invalid",
            request_id=context.request_id,
            retryable=True,
        ),
        declared("translation", {"translation_correction": [patch]}),
    ]
    assembled = AsyncMock(return_value=ReferencePlanDraft.model_validate(draft()))
    saved = AsyncMock(return_value={"preview_id": "synthetic-preview"})
    monkeypatch.setattr(reference_meal_selection_service, "assemble_reference_selection", assembled)
    monkeypatch.setattr(reference_meal_plan_service, "save_reference_plan", saved)
    runtime = ToolRuntime({"messages": messages}, context, {}, lambda _: None, "translation", None)

    result = await save_reference_meal_plan.coroutine(runtime=runtime, translation_correction=[patch])

    assert result == {"preview_id": "synthetic-preview"}
    assert assembled.await_args.kwargs["allow_purchase_fallback"] is True
    display = assembled.await_args.args[1]["meals"][1]["dishes"][0]["display_zh"]
    assert display["name"] == patch["display_zh"]["name"]
    assert display["ingredients"] == patch["display_zh"]["ingredients"]
    assert display["steps"] == patch["display_zh"]["steps"]
    saved.assert_awaited_once()


@pytest.mark.asyncio
async def test_legacy_translation_retry_cannot_restore_removed_free_form_mode(monkeypatch):
    """历史自由原文失败不能借译文修正重新进入已移除的 Agent 模式。"""
    original = draft()
    original["meals"][0]["dishes"][0]["display_zh"] = {
        "name": "合成清粥",
        "ingredients": ["合成大米"],
        "steps": [],
    }
    patch = {
        "file_id": "synthetic-file",
        "chunk_id": "synthetic-chunk",
        "display_zh": {"name": "合成清粥", "ingredients": ["合成大米"], "steps": ["合成煮粥"]},
    }
    context = SaveContext()
    messages = [
        HumanMessage("合成早餐", additional_kwargs={"health_request_id": context.request_id}),
        declared("first", {**original, "read_selection": None, "translation_correction": None}),
        failure("first", error_code="recipe_translation_invalid", request_id=context.request_id, retryable=True),
        declared("retry", {"translation_correction": [patch]}),
    ]
    save = AsyncMock(return_value={"preview_id": "synthetic-preview"})
    monkeypatch.setattr(reference_meal_plan_service, "save_reference_plan", save)
    runtime = ToolRuntime({"messages": messages}, context, {}, lambda _: None, "retry", None)
    with pytest.raises(HealthVisionError, match="reference_translation_correction_invalid"):
        await save_reference_meal_plan.coroutine(runtime=runtime, translation_correction=[patch])
    save.assert_not_awaited()


@pytest.mark.asyncio
async def test_second_semantic_translation_failure_is_typed_terminal_error(monkeypatch):
    """修正后仍不符原文时返回固定终态，不退回模糊执行失败。"""
    context = SaveContext()
    patch = translation_patch()
    messages = [
        HumanMessage("合成三餐", additional_kwargs={"health_request_id": context.request_id}),
        declared("first", {"read_selection": read_selection()}),
        failure("first", error_code="recipe_translation_invalid", request_id=context.request_id, retryable=True),
        declared("retry", {"translation_correction": [patch]}),
    ]
    monkeypatch.setattr(reference_meal_selection_service, "assemble_reference_selection", AsyncMock(return_value={}))
    monkeypatch.setattr(
        reference_meal_plan_service,
        "save_reference_plan",
        AsyncMock(side_effect=HealthVisionError("recipe_translation_invalid", "synthetic private detail", 422)),
    )
    runtime = ToolRuntime({"messages": messages}, context, {}, lambda _: None, "retry", None)
    with pytest.raises(HealthVisionError, match="reference_translation_correction_invalid"):
        await save_reference_meal_plan.coroutine(runtime=runtime, translation_correction=[patch])


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kind,legacy_code",
    [
        ("duplicate_meals", "reference_duplicate_meals"),
        ("duplicate_sku", "reference_duplicate_sku"),
        ("duplicate_decision", "reference_purchase_coverage_invalid"),
        ("missing_decision", "reference_purchase_coverage_invalid"),
    ],
)
async def test_real_tool_node_rejects_legacy_root_fields_without_retry(monkeypatch, kind, legacy_code):
    """旧模型级错误在新的 schema 边界统一终止，不能邀请模型重写服务端事实。"""
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
    assert payload["error_code"] == "reference_plan_validation_failed"
    assert payload["retryable"] is False and payload["message"] and legacy_code
    assert "合成大米原文" not in receipt.content and "with kwargs" not in receipt.content
    service.assert_not_awaited()


@pytest.mark.asyncio
async def test_real_create_agent_receives_feedback_then_only_saves_the_corrected_draft(monkeypatch):
    """候选不匹配反馈只允许同一已读选择再纠正一次。"""
    assembled = AsyncMock(return_value=ReferencePlanDraft.model_validate(draft()))
    service = AsyncMock(
        side_effect=[
            HealthVisionError("reference_ingredient_mismatch", "合成候选不匹配", 422),
            {"preview_id": "synthetic-saved-preview"},
        ]
    )
    monkeypatch.setattr(reference_meal_selection_service, "assemble_reference_selection", assembled)
    monkeypatch.setattr(reference_meal_plan_service, "save_reference_plan", service)
    monkeypatch.setattr(
        health_meal_plan_service,
        "planner_final_result",
        AsyncMock(return_value={"preview_id": "synthetic-saved-preview"}),
    )
    model = FeedbackSaveModel(
        messages=iter(
            [
                declared("invalid", {"read_selection": read_selection()}),
                declared("corrected", {"read_selection": read_selection()}),
                AIMessage(content="合成最终结果"),
            ]
        )
    )
    graph = create_agent(
        model,
        tools=[save_reference_meal_plan],
        middleware=[MealPlanResultMiddleware()],
        context_schema=SaveContext,
    )
    human = HumanMessage(
        "合成保存请求",
        additional_kwargs={"health_request_id": SaveContext().request_id},
    )
    result = await graph.ainvoke({"messages": [human]}, context=SaveContext())
    receipts = [item for item in result["messages"] if isinstance(item, ToolMessage)]
    assert [(item.tool_call_id, item.status) for item in receipts] == [("invalid", "error"), ("corrected", "success")]
    assert [item["error_code"] for item in model.observed_feedback] == ["reference_ingredient_mismatch"]
    assert service.await_count == 2 and assembled.await_count == 2
    context, saved = service.await_args_list[-1].args
    assert context == SaveContext()
    assert ReferencePlanDraft.model_validate(saved) == ReferencePlanDraft.model_validate(draft())
    assert assembled.await_args_list[-1].kwargs["allow_purchase_fallback"] is True
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
        declared("invalid", {"read_selection": read_selection()}),
        failure(),
        declared("corrected", {"read_selection": read_selection()}),
    ]
    error = HealthVisionError("reference_quote_invalid", "合成引文拒绝", 422)
    service = AsyncMock(side_effect=error)
    monkeypatch.setattr(
        reference_meal_selection_service,
        "assemble_reference_selection",
        AsyncMock(return_value=ReferencePlanDraft.model_validate(draft())),
    )
    monkeypatch.setattr(reference_meal_plan_service, "save_reference_plan", service)
    runtime = ToolRuntime({"messages": messages}, context, {}, lambda _: None, "corrected", None)
    feedback = await save_reference_meal_plan.coroutine(runtime=runtime, read_selection=read_selection())
    assert isinstance(feedback, ToolMessage) and feedback.status == "error"
    assert json.loads(feedback.content)["error_code"] == "reference_quote_invalid"
    messages.extend([feedback, declared("second-quote", {"read_selection": read_selection()})])
    runtime = ToolRuntime({"messages": messages}, context, {}, lambda _: None, "second-quote", None)
    with pytest.raises(HealthVisionError) as caught:
        await save_reference_meal_plan.coroutine(runtime=runtime, read_selection=read_selection())
    assert caught.value is error
    assert reference_save_failure_index(messages, context.request_id) == 4


@pytest.mark.asyncio
@pytest.mark.parametrize("scenario", ["duplicate_before", "after_validation", "after_quote", "empty_call_id"])
async def test_real_middleware_stops_reused_save_call_ids_before_another_service_call(monkeypatch, scenario):
    """空或重复调用身份明确中止，不能擦掉失败或进入后续服务及模型调用。"""
    service = AsyncMock(return_value={"preview_id": "must-not-be-saved"})
    if scenario == "after_quote":
        service.side_effect = HealthVisionError("reference_quote_invalid", "合成引文拒绝", 422)
    elif scenario == "after_validation":
        service.side_effect = HealthVisionError("reference_ingredient_mismatch", "合成候选不匹配", 422)
    final = AsyncMock()
    read = AsyncMock()
    monkeypatch.setattr(reference_meal_plan_service, "save_reference_plan", service)
    monkeypatch.setattr(
        reference_meal_selection_service,
        "assemble_reference_selection",
        AsyncMock(return_value=ReferencePlanDraft.model_validate(draft())),
    )
    monkeypatch.setattr(reference_meal_plan_service, "read_reference_recipe", read)
    monkeypatch.setattr(health_meal_plan_service, "planner_final_result", final)
    if scenario == "duplicate_before":
        messages = [
            AIMessage(content="", tool_calls=[*declared("reused", {"read_selection": read_selection()}).tool_calls] * 2)
        ]
    elif scenario == "empty_call_id":
        messages = [
            declared("", {"read_selection": read_selection()}),
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
        args = {"read_selection": read_selection()}
        messages = [declared("reused", args), declared("reused", args)]
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
    if scenario in {"after_quote", "after_validation"}:
        service.assert_awaited_once()
    else:
        service.assert_not_awaited()
    read.assert_not_awaited()
    final.assert_not_awaited()
    before_tools = scenario in {"duplicate_before", "empty_call_id"}
    assert len(model.observed_feedback) == (0 if before_tools else 1)
    assert model.generated_count == (1 if before_tools else 2)

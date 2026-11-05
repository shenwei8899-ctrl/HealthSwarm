"""真实工具装配与保存完成边界；合成会话不代表数据库或 Worker 验收。"""
# ruff: noqa: F811 -- 复用仅隔离服务依赖的 assembly fixture。

import ast
import asyncio
from contextlib import asynccontextmanager
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
import hashlib
import json
import re
import runpy
import sys
from types import ModuleType, SimpleNamespace
from typing import Annotated, Any
from unittest.mock import AsyncMock
from uuid import NAMESPACE_URL, uuid5

import pytest
from langchain.agents import create_agent
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import InjectedToolArg
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode
from langgraph.prebuilt.tool_node import ToolRuntime
from pydantic import Field, ValidationError, field_validator, model_validator

from test.unit.services.test_reference_meal_selection import CHINESE, assembly, payload  # noqa: F401
from yuxi.services import reference_meal_selection_service as selection
from yuxi.services.health_nutrition_service import input_fingerprint
from yuxi.services.health_vision_types import HealthDTO, HealthVisionError, NUTRIENTS
from yuxi.services.recipe_translation_service import checked_chinese_display
from yuxi.services.reference_meal_plan_types import (
    REFERENCE_CATALOG_CHAIN_VERSION,
    REFERENCE_TOOLS,
    ReferenceMeal,
    ReferencePlanDraft,
    ReferencePurchaseGap,
    ReferencePurchaseItem,
)
from yuxi.services.reference_meal_selection_service import ReferenceReadSelection
from yuxi.services.reference_recipe_matching import ingredient_food, parse_reference_recipe, product_food

BACKEND = Path(__file__).resolve().parents[3]
SERVICE = BACKEND / "package/yuxi/services/reference_meal_plan_service.py"


def load_nodes(path, names, namespace):
    """只执行当前真实定义，避开 Windows 不支持的应用启动导入。"""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    nodes = [node for node in tree.body if getattr(node, "name", None) in names]
    assert {node.name for node in nodes} == set(names)
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), "exec"), namespace)
    return namespace


@dataclass
class SaveContext:
    """仅合成运行身份，ToolNode 负责实际注入。"""

    uid: str = "synthetic-owner"
    request_id: str = "synthetic-selection-request"
    tools: tuple = REFERENCE_TOOLS


@pytest.fixture
def selected_tool():
    """执行真实注册装饰器、输入模型和保存工具，不导入整套 Agent。"""
    registry = runpy.run_path(str(BACKEND / "package/yuxi/agents/toolkits/registry.py"))
    namespace = {
        "__name__": "reference_selection_tool_test",
        "Annotated": Annotated,
        "Any": Any,
        "InjectedToolArg": InjectedToolArg,
        "ToolRuntime": ToolRuntime,
        "HealthDTO": HealthDTO,
        "HealthVisionError": HealthVisionError,
        "Field": Field,
        "field_validator": field_validator,
        "model_validator": model_validator,
        "ValidationError": ValidationError,
        "ReferenceMeal": ReferenceMeal,
        "ReferencePurchaseItem": ReferencePurchaseItem,
        "ReferencePurchaseGap": ReferencePurchaseGap,
        "ReferencePlanDraft": ReferencePlanDraft,
        "ReferenceReadSelection": ReferenceReadSelection,
        "REFERENCE_TOOLS": REFERENCE_TOOLS,
        "AIMessage": AIMessage,
        "HumanMessage": HumanMessage,
        "ToolMessage": ToolMessage,
        "json": json,
        "tool": registry["tool"],
    }
    load_nodes(BACKEND / "package/yuxi/agents/toolkits/health.py", ["HealthReadInput"], namespace)
    load_nodes(
        BACKEND / "package/yuxi/agents/toolkits/meal_planner.py",
        [
            "ReferencePlanToolInput",
            "save_reference_meal_plan",
            "reference_save_failure_index",
            "_reference_save_failure_index",
            "reference_save_error_group",
            "_reference_save_validation_error",
            "reference_coverage_feedback",
        ],
        namespace,
    )
    tree = ast.parse((BACKEND / "package/yuxi/agents/toolkits/meal_planner.py").read_text(encoding="utf-8"))
    assignment = next(
        node
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Attribute) and target.attr == "handle_validation_error" for target in node.targets
        )
    )
    exec(compile(ast.Module(body=[assignment], type_ignores=[]), "<production-validation-handler>", "exec"), namespace)
    return SimpleNamespace(
        schema=namespace["ReferencePlanToolInput"], tool=namespace["save_reference_meal_plan"], namespace=namespace
    )


def runtime():
    """schema 定向测试也使用真实 ToolRuntime，不伪造 JSON 上下文。"""
    return ToolRuntime(
        state={}, context=SaveContext(), config={}, stream_writer=lambda value: None, tool_call_id="schema", store=None
    )


def explicit_draft():
    """完整引句入口继续使用原参考稿与采购覆盖协议。"""
    return {
        "meals": [
            {
                "meal_type": "breakfast",
                "dishes": [
                    {
                        "file_id": "rice-file",
                        "chunk_id": "rice-chunk",
                        "name": "Rice",
                        "ingredients": ["100 g rice", "1 cup water"],
                        "steps": ["Boil rice and water."],
                        "display_zh": CHINESE,
                    }
                ],
            }
        ],
        "purchase_items": [{"sku_id": "rice-sku", "quantity": 2, "ingredient_refs": ["100 g rice"]}],
        "purchase_gaps": [{"ingredient": "1 cup water", "reason": "not_sold", "detail": "原谱烹饪用水。"}],
    }


@pytest.mark.parametrize("mode", ["selected", "explicit"])
def test_tool_schema_accepts_each_complete_mode(selected_tool, mode):
    """新旧完整请求分别通过，运行对象由服务端给出。"""
    body = {"read_selection": payload()} if mode == "selected" else explicit_draft()
    result = selected_tool.schema.model_validate({**body, "runtime": runtime()})
    assert (result.read_selection is not None) == (mode == "selected")


@pytest.mark.parametrize("field", ["meals", "purchase_items", "purchase_gaps"])
def test_tool_schema_rejects_mixed_quote_and_selection_fields(selected_tool, field):
    """即使旧字段为空，也不能进入新分支后被静默覆盖。"""
    body = {"read_selection": payload(), field: explicit_draft()[field], "runtime": runtime()}
    with pytest.raises(ValidationError):
        selected_tool.schema.model_validate(body)


@pytest.mark.parametrize("missing", ["meals", "purchase_items", "purchase_gaps"])
def test_legacy_schema_keeps_required_fields_and_coverage(selected_tool, missing):
    """旧入口缺字段或漏采购对应仍被原 DTO 拒绝。"""
    body = explicit_draft()
    body.pop(missing)
    with pytest.raises(ValidationError):
        selected_tool.schema.model_validate({**body, "runtime": runtime()})


def test_tool_schema_does_not_allow_forged_runtime_or_missing_purchase_coverage(selected_tool):
    """新分支不放宽运行注入，旧分支不放宽食材覆盖。"""
    with pytest.raises(ValidationError):
        selected_tool.schema.model_validate({"read_selection": payload(), "runtime": {"uid": "invented"}})
    body = explicit_draft()
    body["purchase_gaps"] = []
    with pytest.raises(ValidationError):
        selected_tool.schema.model_validate({**body, "runtime": runtime()})


async def execute_tool(selected_tool, args, context, *, handle_tool_errors=False):
    """真实 ToolNode 注入上下文并执行当前生产工具。"""
    graph = StateGraph(MessagesState, context_schema=SaveContext)
    graph.add_node("tools", ToolNode([selected_tool.tool], handle_tool_errors=handle_tool_errors))
    graph.add_edge(START, "tools")
    graph.add_edge("tools", END)
    return await graph.compile().ainvoke(
        {
            "messages": [
                HumanMessage("安排早餐", additional_kwargs={"health_request_id": context.request_id}),
                AIMessage("", tool_calls=[{"id": "save-selected", "name": selected_tool.tool.name, "args": args}]),
            ]
        },
        context=context,
    )


@pytest.mark.asyncio
async def test_real_tool_node_assembles_parsed_source_before_original_save(selected_tool, assembly, monkeypatch):  # noqa: F811
    """执行真实新装配函数，再将其完整标准稿送入旧保存 Owner。"""
    body = payload()
    body["meals"][0]["dishes"][0]["display_zh"] = CHINESE
    context = SaveContext()
    assembly.context = context
    assemble = AsyncMock(wraps=selection.assemble_reference_selection)
    monkeypatch.setattr(selection, "assemble_reference_selection", assemble)
    accepted = []

    async def save(received_context, draft):
        """只隔离保存副作用，输出必须是实际装配的完整原 DTO。"""
        assert received_context is context and isinstance(draft, ReferencePlanDraft)
        assert draft.meals[0].dishes[0].ingredients == ["100 g rice", "1 cup water"]
        assert draft.purchase_items[0].ingredient_refs == ["100 g rice"]
        accepted.append(draft.model_dump())
        return {"preview_id": "synthetic-saved", "nutrition_status": "not_calculated"}

    monkeypatch.setattr(
        sys.modules["yuxi.services.reference_meal_plan_service"], "save_reference_plan", save, raising=False
    )
    result = await execute_tool(selected_tool, {"read_selection": body}, context)
    receipt = result["messages"][-1]
    assert isinstance(receipt, ToolMessage) and receipt.status == "success"
    assert json.loads(receipt.content) == {"preview_id": "synthetic-saved", "nutrition_status": "not_calculated"}
    assert len(accepted) == 1
    assert assemble.await_args.args[0] is context
    assert (
        ReferenceReadSelection.model_validate(assemble.await_args.args[1]).model_dump()
        == ReferenceReadSelection.model_validate(body).model_dump()
    )


@pytest.mark.asyncio
async def test_real_tool_node_legacy_branch_keeps_quotes_and_never_assembles(selected_tool, assembly, monkeypatch):  # noqa: F811
    """显式原文仍原样进入原保存，不借选择装配改写引句。"""
    body, context = explicit_draft(), SaveContext()
    assemble = AsyncMock(side_effect=AssertionError("旧原文入口不能装配替换"))
    save = AsyncMock(return_value={"preview_id": "synthetic-legacy"})
    monkeypatch.setattr(selection, "assemble_reference_selection", assemble)
    monkeypatch.setattr(
        sys.modules["yuxi.services.reference_meal_plan_service"], "save_reference_plan", save, raising=False
    )
    result = await execute_tool(selected_tool, body, context)
    assert json.loads(result["messages"][-1].content)["preview_id"] == "synthetic-legacy"
    assert (
        ReferencePlanDraft.model_validate(save.await_args.args[1]).model_dump()
        == ReferencePlanDraft.model_validate(body).model_dump()
    )
    assemble.assert_not_awaited()


@pytest.mark.asyncio
async def test_mixed_real_tool_call_never_reaches_assembly_or_save(selected_tool, assembly, monkeypatch):  # noqa: F811
    """真实执行器拒绝混合输入，两个业务分支都不能产生副作用。"""
    assemble, save = AsyncMock(), AsyncMock()
    monkeypatch.setattr(selection, "assemble_reference_selection", assemble)
    monkeypatch.setattr(
        sys.modules["yuxi.services.reference_meal_plan_service"], "save_reference_plan", save, raising=False
    )
    result = await execute_tool(selected_tool, {"read_selection": payload(), "purchase_gaps": []}, SaveContext())
    receipt = result["messages"][-1]
    assert receipt.status == "error"
    assert json.loads(receipt.content)["retryable"] is False
    assemble.assert_not_awaited()
    save.assert_not_awaited()


@pytest.mark.asyncio
async def test_legacy_missing_gap_returns_retryable_coverage_feedback_without_side_effects(
    selected_tool, assembly, monkeypatch
):
    """旧引句遗漏水对应时，真实执行器返回字段路径而非 TypeError。"""
    assemble, save = AsyncMock(), AsyncMock()
    monkeypatch.setattr(selection, "assemble_reference_selection", assemble)
    monkeypatch.setattr(
        sys.modules["yuxi.services.reference_meal_plan_service"], "save_reference_plan", save, raising=False
    )
    body = explicit_draft()
    body["purchase_gaps"] = []
    result = await execute_tool(selected_tool, body, SaveContext(), handle_tool_errors=True)
    receipt = result["messages"][-1]
    assert receipt.status == "error" and receipt.tool_call_id == "save-selected"
    feedback = json.loads(receipt.content)
    assert feedback["error_code"] == "reference_purchase_coverage_invalid" and feedback["retryable"] is True
    assert feedback["issues"] == {
        "missing_ingredient_paths": ["meals[0].dishes[0].ingredients[1]"],
        "extra_decision_paths": [],
        "duplicate_decision_paths": [],
        "counts": {"missing_ingredient_paths": 1, "extra_decision_paths": 0, "duplicate_decision_paths": 0},
    }
    assert "100 g rice" not in receipt.content and "1 cup water" not in receipt.content
    assemble.assert_not_awaited()
    save.assert_not_awaited()


@pytest.mark.asyncio
async def test_restoring_model_objects_reproduces_broken_legacy_coverage_feedback(selected_tool, assembly, monkeypatch):
    """负控恢复模型对象输入，证明相同 ToolNode 请求会失去结构化纠错。"""
    assemble, save = AsyncMock(), AsyncMock()
    monkeypatch.setattr(selection, "assemble_reference_selection", assemble)
    monkeypatch.setattr(
        sys.modules["yuxi.services.reference_meal_plan_service"], "save_reference_plan", save, raising=False
    )
    source = BACKEND / "package/yuxi/agents/toolkits/meal_planner.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    schema = deepcopy(
        next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "ReferencePlanToolInput")
    )
    call = next(
        node
        for node in ast.walk(schema)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "ReferencePlanDraft"
    )
    assert isinstance(call.args[0], ast.Dict)
    call.args[0].values = [
        ast.Attribute(value=ast.Name(id="self", ctx=ast.Load()), attr=key.value, ctx=ast.Load())
        for key in call.args[0].keys
    ]
    namespace = dict(selected_tool.namespace)
    node = deepcopy(
        next(
            node
            for node in tree.body
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "save_reference_meal_plan"
        )
    )
    exec(
        compile(ast.fix_missing_locations(ast.Module(body=[schema, node], type_ignores=[])), str(source), "exec"),
        namespace,
    )
    mutant = namespace["save_reference_meal_plan"]
    mutant.handle_validation_error = namespace["_reference_save_validation_error"]
    body = explicit_draft()
    body["purchase_gaps"] = []
    result = await execute_tool(SimpleNamespace(tool=mutant), body, SaveContext(), handle_tool_errors=True)
    receipt = result["messages"][-1]
    assert receipt.status == "error" and "not subscriptable" in receipt.content
    with pytest.raises(json.JSONDecodeError):
        json.loads(receipt.content)
    assemble.assert_not_awaited()
    save.assert_not_awaited()


@pytest.mark.asyncio
async def test_assembled_agent_receives_production_prompt_and_can_use_selection_tool(
    selected_tool, assembly, monkeypatch
):  # noqa: F811
    """固定回放只证明真实提示与工具契约送达，不声称供应商语义遵循。"""
    tree = ast.parse((BACKEND / "package/yuxi/services/health_consultation_service.py").read_text(encoding="utf-8"))
    prompt = ast.literal_eval(
        next(
            node.value
            for node in tree.body
            if isinstance(node, ast.Assign)
            and any(getattr(target, "id", "") == "REFERENCE_MEAL_PROMPT" for target in node.targets)
        )
    )
    seen = []

    class ObservedModel(GenericFakeChatModel):
        """保留实际模型请求，观察生产提示而非自行拼接说明。"""

        def bind_tools(self, tools, **kwargs):
            """保留真实 Agent 的工具执行节点。"""
            return self

        def _generate(self, messages, *args, **kwargs):
            """记录真正传入模型的 system 消息。"""
            seen.append(messages[0].content)
            return super()._generate(messages, *args, **kwargs)

    save = AsyncMock(return_value={"preview_id": "synthetic-prompt"})
    monkeypatch.setattr(
        sys.modules["yuxi.services.reference_meal_plan_service"], "save_reference_plan", save, raising=False
    )
    model = ObservedModel(
        messages=iter(
            [
                AIMessage(
                    "",
                    tool_calls=[
                        {"id": "save-prompt", "name": selected_tool.tool.name, "args": {"read_selection": payload()}}
                    ],
                ),
                AIMessage('{"preview_id":"synthetic-prompt"}'),
            ]
        )
    )
    graph = create_agent(model, tools=[selected_tool.tool], context_schema=SaveContext, system_prompt=prompt)
    result = await graph.ainvoke({"messages": [HumanMessage("安排早餐")]}, context=SaveContext())
    assert seen and all(value == prompt for value in seen)
    assert json.loads(result["messages"][-1].content) == {"preview_id": "synthetic-prompt"}
    assert isinstance(save.await_args.args[1], ReferencePlanDraft)


@pytest.fixture
def save_owner(monkeypatch):
    """执行真实保存和纯校验，只隔离会话、授权、对象、商品与图片外部边界。"""
    raw = "# 米饭\n\n## 食材\n- 大米100克\n- 水适量\n\n## 做法\n1. 将大米和水煮熟。\n"
    document = {
        "scope": "reference_recipe",
        "file_id": "rice",
        "chunk_id": "chunk",
        "kb_id": "recipes",
        "filename": "米饭.md",
        "file_hash": "raw",
        "chunks_hash": "chunks",
        "content": raw,
    }
    sku = {
        "sku_id": "rice-sku",
        "product_id": "rice",
        "product_name": "大米",
        "sku_name": "一袋",
        "category_code": "grain",
        "available_quantity": 5,
        "sale_status": "available",
        "ingredients": ["大米"],
        "allergen_codes": [],
        "data_completeness": "complete",
        "price_cent": 800,
    }
    state = SimpleNamespace(rows={}, committed=False, image_entered=asyncio.Event(), image_release=asyncio.Event())
    session = SimpleNamespace()

    async def get(model, row_id):
        """仅回读本合成会话中的预览。"""
        return state.rows.get(row_id)

    session.get = get
    session.add = lambda row: state.rows.__setitem__(row.id, row)

    @asynccontextmanager
    async def transaction():
        """记录事务退出，不能据此声称真实提交通过。"""
        yield session
        state.committed = True

    async def images(meals):
        """模拟可选图片供应商卡住，直到测试精确释放。"""
        state.image_entered.set()
        await state.image_release.wait()

    presentation = ModuleType("yuxi.services.reference_recipe_presentation")
    presentation.__dict__.update(
        load_nodes(
            BACKEND / "package/yuxi/services/reference_recipe_presentation.py",
            ["check_recipe_nutrition", "recipe_pairing_summary"],
            {"HealthVisionError": HealthVisionError},
        )
    )
    presentation.prepare_recipe_images = images
    monkeypatch.setitem(sys.modules, presentation.__name__, presentation)
    namespace = {
        "json": json,
        "hashlib": hashlib,
        "re": re,
        "uuid5": uuid5,
        "NAMESPACE_URL": NAMESPACE_URL,
        "HealthVisionError": HealthVisionError,
        "ReferencePlanDraft": ReferencePlanDraft,
        "NUTRIENTS": NUTRIENTS,
        "REFERENCE_CATALOG_CHAIN_VERSION": REFERENCE_CATALOG_CHAIN_VERSION,
        "parse_reference_recipe": parse_reference_recipe,
        "checked_chinese_display": checked_chinese_display,
        "ingredient_food": ingredient_food,
        "product_food": product_food,
        "input_fingerprint": input_fingerprint,
        "pg_manager": SimpleNamespace(get_async_session_context=transaction),
        "HealthInitialPlanPreview": SimpleNamespace,
        "require_planner_run": AsyncMock(
            return_value=(
                SimpleNamespace(id="run", conversation_id="conversation"),
                SimpleNamespace(member_id="member", conversation_id="conversation"),
            )
        ),
        "bound_reference_context": AsyncMock(
            return_value={
                "selection": {
                    "mode": "reference",
                    "family_id": "family",
                    "plan_date": "2099-01-01",
                    "meal_types": ["breakfast"],
                },
                "members": [],
                "sources": {"family_id": "family"},
            }
        ),
        "recipe_document": AsyncMock(return_value=document),
        "current_reference_catalog": AsyncMock(return_value={"version": "catalog-v1", "items": [sku]}),
        "save_chinese_display": AsyncMock(),
    }
    names = [
        "save_reference_plan",
        "product_facts",
        "reference_product",
        "same_reference_document",
        "checked_reference_meals",
        "reference_recipe_media",
        "products_cover_reference_dishes",
        "checked_reference_gaps",
        "cooking_water_ingredient",
        "reference_member_restrictions",
        "unverified_reference_restrictions",
        "reference_product_composition",
        "reference_restriction_conflict",
    ]
    load_nodes(SERVICE, names, namespace)
    receipts = {
        "read_reference_recipe": [document],
        "get_reference_plan_context": [{"commerce_notice": None}],
        "find_reference_products": [{"catalog": [namespace["reference_product"](sku)]}],
    }
    namespace["tool_payloads"] = AsyncMock(side_effect=lambda db, run, tool: receipts[tool])
    state.namespace = namespace
    state.context = SimpleNamespace(uid="owner")
    state.draft = {
        "meals": [
            {
                "meal_type": "breakfast",
                "dishes": [
                    {
                        "file_id": "rice",
                        "chunk_id": "chunk",
                        "name": "米饭",
                        "ingredients": ["大米100克", "水适量"],
                        "steps": ["将大米和水煮熟。"],
                        "cooking_minutes": 20,
                    }
                ],
            }
        ],
        "purchase_items": [{"sku_id": "rice-sku", "quantity": 1, "ingredient_refs": ["大米100克"]}],
        "purchase_gaps": [{"ingredient": "水适量", "reason": "not_sold", "detail": "烹饪用水无需商城购买。"}],
    }
    return state


@pytest.mark.asyncio
async def test_current_save_finishes_with_recipe_even_if_image_service_never_returns(save_owner):
    """图片永久阻塞时保存仍立即形成准确结果，不等待或生成图片。"""
    result = await asyncio.wait_for(
        save_owner.namespace["save_reference_plan"](save_owner.context, save_owner.draft), timeout=1
    )
    assert save_owner.committed and result["preview_id"] in save_owner.rows
    assert result["meals"][0]["dishes"][0]["steps"] == ["将大米和水煮熟。"]
    assert result["nutrition_status"] == "not_calculated" and result["professional_status"] == "not_reviewed"
    assert not save_owner.image_entered.is_set()


@pytest.mark.asyncio
async def test_restoring_original_image_wait_reproduces_post_commit_completion_block(save_owner):
    """恢复删除的历史等待片段后，预览已保存却无法返回，证明正向 oracle 能捕获旧缺陷。"""
    tree = ast.parse(SERVICE.read_text(encoding="utf-8"))
    node = next(
        item for item in tree.body if isinstance(item, ast.AsyncFunctionDef) and item.name == "save_reference_plan"
    )
    original_wait = ast.parse(
        "if any(d.get('cooking_minutes') for m in meals for d in m['dishes']):\n"
        "    from yuxi.services.reference_recipe_presentation import prepare_recipe_images\n"
        "    await prepare_recipe_images(meals)\n"
    ).body[0]
    node.body.insert(len(node.body) - 1, original_wait)
    exec(
        compile(ast.fix_missing_locations(ast.Module(body=[node], type_ignores=[])), str(SERVICE), "exec"),
        save_owner.namespace,
    )
    pending = asyncio.create_task(save_owner.namespace["save_reference_plan"](save_owner.context, save_owner.draft))
    try:
        await asyncio.wait_for(save_owner.image_entered.wait(), timeout=1)
        assert save_owner.committed and len(save_owner.rows) == 1 and not pending.done()
    finally:
        save_owner.image_release.set()
        result = await asyncio.wait_for(pending, timeout=1)
    assert result["preview_id"] in save_owner.rows

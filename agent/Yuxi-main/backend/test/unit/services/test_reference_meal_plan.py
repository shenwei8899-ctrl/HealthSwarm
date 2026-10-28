"""参考模式拒绝虚构数值和来源，明确缺失与正式状态的分界。"""

from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from yuxi.services.reference_meal_plan_service import (
    checked_reference_meals,
    product_facts,
    reference_binding,
    select_reference_purchase_items,
)
from yuxi.services.reference_meal_plan_types import ReferencePlanDraft, ReferenceSelection
from yuxi.services.health_vision_types import HealthVisionError


def draft(**dish_updates):
    """独立合成原文对应的单餐。"""
    return {
        "purchase_items": [],
        "purchase_gaps": [
            {"ingredient": i, "reason": "needs_confirmation", "detail": "需核对商品包装"}
            for i in dish_updates.get("ingredients", ["大米100克"])
        ],
        "meals": [
            {
                "meal_type": "breakfast",
                "dishes": [
                    {
                        "file_id": "recipe",
                        "chunk_id": "chunk",
                        "name": "清粥",
                        "ingredients": ["大米100克"],
                        "steps": ["加水煮熟"],
                        **dish_updates,
                    }
                ],
            }
        ],
    }


def document(content="清粥 大米100克 加水煮熟 原食谱供两人食用"):
    """来源由存储事实提供。"""
    return {
        ("recipe", "chunk"): {
            "file_id": "recipe",
            "chunk_id": "chunk",
            "kb_id": "recipes",
            "filename": "清粥.md",
            "file_hash": "a",
            "chunks_hash": "b",
            "content": content,
        }
    }


@pytest.mark.parametrize("field", ["nutrition", "professional_review", "calories", "portion_note", "uid"])
def test_model_cannot_supply_nutrition_approval_or_free_portion_claim(field):
    """不接收模型自行给出的营养或适用性声明。"""
    with pytest.raises(ValidationError):
        ReferencePlanDraft.model_validate(draft(**{field: "每人500kcal，过敏者放心食用"}))


@pytest.mark.parametrize(
    "changes",
    [
        {"name": "不存在的菜"},
        {"ingredients": ["虚构食材"]},
        {"steps": ["编造步骤"]},
        {"nutrition_quote": "每人500kcal"},
        {"portion_quote": "个人达标"},
    ],
)
def test_every_model_quote_requires_the_opened_source(changes):
    """不能用真实文件ID包裹虚构正文。"""
    with pytest.raises(HealthVisionError, match="reference_quote_invalid"):
        checked_reference_meals(ReferencePlanDraft.model_validate(draft(**changes)), document(), [])


def test_unknown_nutrition_is_null_and_portion_is_a_server_statement():
    """原文份量只作引句，个人营养量保持未核算。"""
    result = checked_reference_meals(
        ReferencePlanDraft.model_validate(draft(portion_quote="原食谱供两人食用")), document(), []
    )
    dish = result[0]["dishes"][0]
    assert set(dish["nutrition"].values()) == {None}
    assert dish["nutrition_status"] == "not_calculated"
    assert "尚未核定" in dish["portion_note"]
    assert dish["source"]["filename"] == "清粥.md"


def test_omitting_an_allergen_from_selected_quotes_cannot_hide_it():
    """已知限制针对整份打开正文，不能只选安全食材片段。"""
    with pytest.raises(HealthVisionError, match="reference_restriction_conflict"):
        checked_reference_meals(
            ReferencePlanDraft.model_validate(draft()),
            document("清粥 大米100克 加水煮熟 花生"),
            [{"allergens": ["花生"]}],
        )


def test_unopened_document_cannot_be_used():
    """未有当前Run读取回执的文件不形成餐单。"""
    with pytest.raises(HealthVisionError, match="reference_receipt_invalid"):
        checked_reference_meals(ReferencePlanDraft.model_validate(draft()), {}, [])


def test_composition_changes_invalidate_selected_product_without_requiring_complete_mapping():
    """价格库存可以重报，成分来源变化须重选。"""
    before = {"sku_id": "1", "ingredients": [], "allergen_codes": [], "data_completeness": "partial"}
    assert product_facts(before) == product_facts({**before, "price_cent": 999, "available_quantity": 3})
    assert product_facts(before) != product_facts({**before, "allergen_codes": ["花生"]})


def test_reference_discriminator_does_not_accept_malformed_or_neighbor_modes():
    """旧数据的非参考选择不被误认。"""
    for selection in (None, {"selection": "server"}, {"selection": {"mode": "initial"}}):
        assert not reference_binding(SimpleNamespace(initial_planner_selection=selection))
    assert reference_binding(SimpleNamespace(initial_planner_selection={"selection": {"mode": "reference"}}))


def test_partial_current_plan_purchases_only_selected_meal_ingredients():
    plan = {
        "meals": [
            {"meal_type": "breakfast", "dishes": [{"ingredients": ["大米", "鸡蛋"]}]},
            {"meal_type": "dinner", "dishes": [{"ingredients": ["鱼", "鸡蛋"]}]},
        ],
        "purchase_items": [
            {"sku_id": "rice", "quantity": 1, "ingredient_refs": ["大米"]},
            {"sku_id": "fish", "quantity": 2, "ingredient_refs": ["鱼"]},
            {"sku_id": "egg", "quantity": 3, "ingredient_refs": ["鸡蛋"]},
        ],
    }
    selected = select_reference_purchase_items(plan, ["breakfast"])
    assert [item["sku_id"] for item in selected] == ["rice", "egg"]
    assert selected[1]["quantity"] == 3
    assert selected[1]["ingredient_refs"] == ["鸡蛋"]
    assert select_reference_purchase_items(plan, ["lunch"]) == []


def test_reference_selection_rejects_duplicate_members_or_meals():
    """去重不悄悄改变用户处理范围。"""
    member = str(uuid4())
    with pytest.raises(ValidationError):
        ReferenceSelection(family_id=uuid4(), plan_date="2026-10-26", participant_ids=[member, member])


@pytest.mark.asyncio
async def test_real_tool_node_injects_runtime_into_reference_save(monkeypatch):
    """实际 ToolNode 接受服务端 runtime，不能在 DTO 边界被当成额外字段。"""
    from langchain_core.messages import AIMessage
    from langgraph.graph import StateGraph, MessagesState, START, END
    from langgraph.prebuilt import ToolNode
    from yuxi.agents.base import BaseContext
    from yuxi.agents.toolkits.meal_planner import save_reference_meal_plan
    from yuxi.services import reference_meal_plan_service

    called = []

    async def save(context, value):
        called.append((context.uid, ReferencePlanDraft.model_validate(value)))
        return {"preview_id": "synthetic-receipt"}

    monkeypatch.setattr(reference_meal_plan_service, "save_reference_plan", save)
    graph = StateGraph(MessagesState, context_schema=BaseContext)
    graph.add_node("tools", ToolNode([save_reference_meal_plan], handle_tool_errors=False))
    graph.add_edge(START, "tools")
    graph.add_edge("tools", END)
    result = await graph.compile().ainvoke(
        {
            "messages": [
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "save_reference_meal_plan",
                            "args": draft(),
                            "id": "synthetic-call",
                            "type": "tool_call",
                        }
                    ],
                )
            ]
        },
        context=BaseContext(uid="synthetic-owner"),
    )
    assert called[0][0] == "synthetic-owner"
    assert called[0][1].meals[0].meal_type == "breakfast"
    assert "synthetic-receipt" in result["messages"][-1].content
    assert "runtime" not in save_reference_meal_plan.tool_call_schema.model_json_schema()["properties"]


def test_model_json_cannot_forge_the_injected_reference_runtime():
    """可隐藏的字段仍有后端运行对象校验。"""
    from yuxi.agents.toolkits.meal_planner import ReferencePlanToolInput

    with pytest.raises(ValidationError):
        ReferencePlanToolInput.model_validate({**draft(), "runtime": {"uid": "forged"}})


def test_empty_procurement_cannot_silently_omit_ingredient_decisions():
    value = draft()
    value.update(purchase_items=[], purchase_gaps=[])
    with pytest.raises(ValidationError, match="食材"):
        ReferencePlanDraft.model_validate(value)


def test_catalog_description_reaches_agent_and_changes_selection_fingerprint():
    from yuxi.services.reference_meal_plan_service import reference_product

    sku = {"sku_id": "56", "product_description": "鸡蛋10枚，包装声明见标签"}
    first = reference_product(sku)
    assert first["product_description"] == sku["product_description"]
    assert first["facts_hash"] != reference_product({**sku, "product_description": "含花生成分"})["facts_hash"]


@pytest.mark.parametrize(
    "changes",
    [
        {"purchase_items": [{"sku_id": "56", "quantity": 1, "ingredient_refs": ["鸡蛋"]}], "purchase_gaps": []},
        {"purchase_items": [], "purchase_gaps": []},
        {
            "purchase_items": [],
            "purchase_gaps": [{"ingredient": "大米100克", "reason": "needs_confirmation", "detail": "  "}],
        },
    ],
)
def test_procurement_requires_actual_ingredients_and_visible_reasons(changes):
    with pytest.raises(ValidationError):
        ReferencePlanDraft.model_validate({**draft(), **changes})


def test_partial_selection_keeps_missing_ingredient_explicit():
    value = draft(ingredients=["大米100克", "水适量"])
    value.update(
        purchase_items=[{"sku_id": "rice", "quantity": 1, "ingredient_refs": ["大米100克"]}],
        purchase_gaps=[{"ingredient": "水适量", "reason": "not_sold", "detail": "饮用水自行准备"}],
    )
    result = ReferencePlanDraft.model_validate(value)
    assert result.purchase_items[0].quantity == 1
    assert result.purchase_gaps[0].ingredient == "水适量"

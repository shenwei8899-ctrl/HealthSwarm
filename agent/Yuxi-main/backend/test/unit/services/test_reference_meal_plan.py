"""参考模式拒绝虚构数值和来源，明确缺失与正式状态的分界。"""

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from pydantic import ValidationError

from yuxi.services.reference_meal_plan_service import (
    checked_reference_gaps,
    checked_reference_meals,
    product_facts,
    reference_binding,
    reference_restriction_conflict,
    save_reference_plan,
    select_reference_purchase_items,
    reference_purchase_items,
)
from yuxi.services.reference_meal_plan_types import ReferencePlanDraft, ReferencePurchaseGap, ReferenceSelection
from yuxi.services.reference_meal_selection_service import ReferenceReadSelection
from yuxi.services.health_vision_types import HealthVisionError


def draft(**dish_updates):
    """独立合成原文对应的单餐。"""
    return {
        "product_matches": [],
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


def document(content=None):
    """结构化完整原谱由存储边界提供，附加限制仍针对整份正文。"""
    original = "# 清粥\n\n## 食材\n- 大米100克\n\n## 做法\n1. 加水煮熟\n\n## 份量\n原食谱供两人食用\n"
    if content is None:
        content = original
    elif content.startswith("清粥 大米100克 加水煮熟"):
        content = original + content.removeprefix("清粥 大米100克 加水煮熟").strip()
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


def test_unresolved_matched_packaging_projects_as_self_purchase_without_price():
    """有同名商品但 Agent 无法可靠定包装时，餐单保留且商品不进入订单。"""
    gaps = [ReferencePurchaseGap(ingredient="大米100克", reason="needs_confirmation", detail="无法可靠定包装")]
    products = [
        {
            "sku_id": "rice",
            "product_name": "大米",
            "sale_status": "available",
            "available_quantity": 5,
        }
    ]
    assert checked_reference_gaps(gaps, products) == [
        {
            "ingredient": "大米100克",
            "reason": "needs_confirmation",
            "detail": "无法可靠定包装",
            "purchase_mode": "self_purchase",
            "sku_id": None,
            "price_cent": None,
        }
    ]


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


@pytest.mark.parametrize(
    ("restriction", "ingredient"),
    [
        ("牛肉", "beef broth"),
        ("牛肉", "VEAL"),
        ("羊肉", "lamb"),
        ("羊肉", "mutton"),
        ("羊肉", "goat meat"),
        ("牛羊肉", "beef"),
        ("牛羊肉", "lamb"),
        ("牛羊肉", "goat\nmeat"),
        ("beef", "牛肉"),
        ("beef", "beef"),
        ("beef", "beef broth"),
        ("veal", "veal"),
        ("lamb", "羊肉"),
        ("lamb", "lamb"),
        ("mutton", "mutton"),
        ("goat\nmeat", "goat meat"),
    ],
)
def test_known_meat_restrictions_apply_to_the_whole_bilingual_source(restriction, ingredient):
    """不能省略原文中的牛羊肉或通过中英文名称差异规避忌口。"""
    assert reference_restriction_conflict(ingredient, [restriction]) is True
    with pytest.raises(HealthVisionError, match="reference_restriction_conflict"):
        checked_reference_meals(
            ReferencePlanDraft.model_validate(draft()),
            document("清粥 大米100克 加水煮熟\n" + ingredient),
            [{"avoidances": [restriction]}],
        )


@pytest.mark.parametrize(
    ("restriction", "ingredient"),
    [
        ("牛羊肉", "milk"),
        ("牛羊肉", "goat milk"),
        ("牛羊肉", "beefsteak tomato"),
        ("牛羊肉", "lambsquarters"),
        ("beef", "beefsteak tomato"),
        ("lamb", "lambsquarters"),
        ("goat\nmeat", "goat milk"),
    ],
)
def test_meat_aliases_do_not_reject_milk_or_words_containing_the_alias(restriction, ingredient):
    """牛羊肉名称按英文整词识别，不把牛奶或相似单词认作肉类。"""
    assert reference_restriction_conflict(ingredient, [restriction]) is False
    result = checked_reference_meals(
        ReferencePlanDraft.model_validate(draft()),
        document("清粥 大米100克 加水煮熟\n" + ingredient),
        [{"avoidances": [restriction]}],
    )
    assert result[0]["dishes"][0]["name"] == "清粥"


@pytest.mark.parametrize(
    ("restriction", "ingredient"),
    [
        ("鸡蛋", "eggs"),
        ("牛奶", "milk"),
        ("大豆", "soybeans"),
        ("麸质", "wheat flour"),
        ("牛羊肉和鸡蛋", "rice"),
        ("牛肉、羊肉", "milk"),
        ("不吃牛肉，且不能有坚果", "rice"),
    ],
)
def test_unsupported_restriction_is_unverified_instead_of_clear(restriction, ingredient):
    """有限词汇不能解释其他限制或自由句时，原文未命中也不能通过。"""
    with pytest.raises(HealthVisionError, match="reference_restriction_unverified"):
        reference_restriction_conflict(ingredient, [restriction])
    with pytest.raises(HealthVisionError, match="reference_restriction_unverified"):
        checked_reference_meals(
            ReferencePlanDraft.model_validate(draft()),
            document("清粥 大米100克 加水煮熟\n" + ingredient),
            [{"allergens": [restriction]}],
        )


@pytest.mark.parametrize("restriction", ["鸡蛋", "牛奶", "大豆", "麸质", "花生"])
def test_literal_conflict_remains_positive_even_when_other_names_are_unverified(restriction):
    """已有明确原文冲突仍报冲突，不被未核实状态改写为可通过。"""
    assert reference_restriction_conflict("配料含" + restriction, [restriction, "待核实限制"]) is True


def test_doctor_instruction_cannot_be_ignored_when_not_interpretable():
    """自由医嘱没有受控解释，不能只因食材未命中文字就保存。"""
    with pytest.raises(HealthVisionError, match="reference_restriction_unverified"):
        checked_reference_meals(
            ReferencePlanDraft.model_validate(draft()), document(), [{"doctor_instructions": "避免生食"}]
        )


@pytest.mark.parametrize("fault", ["quote", "unopened"])
def test_source_errors_precede_unverified_restrictions(fault):
    """原引文和读取回执的具体失败不被无关的未核实限制遮蔽。"""
    with pytest.raises(
        HealthVisionError, match="reference_quote_invalid" if fault == "quote" else "reference_receipt_invalid"
    ):
        checked_reference_meals(
            ReferencePlanDraft.model_validate(draft(name="不存在"))
            if fault == "quote"
            else ReferencePlanDraft.model_validate(draft()),
            document() if fault == "quote" else {},
            [{"allergens": ["鸡蛋"]}],
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
    from yuxi.services import reference_meal_plan_service, reference_meal_selection_service

    called = []

    async def save(context, value):
        called.append((context.uid, ReferencePlanDraft.model_validate(value)))
        return {"preview_id": "synthetic-receipt"}

    monkeypatch.setattr(reference_meal_plan_service, "save_reference_plan", save)
    monkeypatch.setattr(
        reference_meal_selection_service,
        "assemble_reference_selection",
        AsyncMock(return_value=ReferencePlanDraft.model_validate(draft())),
    )
    read_selection = {
        "use_read_recipes": True,
        "auto_purchase_matches": True,
        "meals": [
            {
                "meal_type": "breakfast",
                "dishes": [{"file_id": "recipe", "chunk_id": "chunk"}],
            }
        ],
        "product_matches": [],
    }
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
                            "args": {"read_selection": read_selection},
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
        ReferencePlanToolInput.model_validate(
            {
                "read_selection": {
                    "use_read_recipes": True,
                    "auto_purchase_matches": True,
                    "meals": [
                        {
                            "meal_type": "breakfast",
                            "dishes": [{"file_id": "recipe", "chunk_id": "chunk"}],
                        }
                    ],
                    "product_matches": [],
                },
                "runtime": {"uid": "forged"},
            }
        )


def test_empty_procurement_cannot_silently_omit_ingredient_decisions():
    value = draft()
    value.update(purchase_items=[], purchase_gaps=[])
    with pytest.raises(ValidationError, match="食材"):
        ReferencePlanDraft.model_validate(value)


def test_full_product_facts_keep_description_and_issues_in_selection_fingerprint():
    """上下文裁剪不改变完整商品事实和保存时使用的来源指纹。"""
    from yuxi.services.reference_meal_plan_service import reference_product

    sku = {"sku_id": "56", "product_description": "鸡蛋10枚，包装声明见标签", "data_issues": ["待核对包装"]}
    first = reference_product(sku)
    assert first["product_description"] == sku["product_description"]
    assert first["data_issues"] == sku["data_issues"]
    assert first["facts_hash"] != reference_product({**sku, "product_description": "含花生成分"})["facts_hash"]
    assert first["facts_hash"] != reference_product({**sku, "data_issues": []})["facts_hash"]


@pytest.mark.asyncio
async def test_saved_reference_accepts_only_verified_demo_display_rewrite(monkeypatch):
    """旧演示文案改写可回读，同一商品的安全事实仍须逐项核对。"""
    from yuxi.services import reference_meal_plan_service as service

    old = {
        "sku_id": "sku-rice",
        "product_id": "rice",
        "product_name": "示例·大米",
        "sku_name": "500克",
        "net_content": {"value": "500", "unit": "g"},
        "ingredients": ["大米"],
        "allergen_codes": [],
        "data_completeness": "partial",
        "data_issues": ["过敏原待核对"],
        "category_code": "grain",
        "product_description": "示例·大米\n\n【商品资料】配料及过敏原以包装为准。",
        "image_url": "https://example.test/old.png",
        "sale_status": "available",
        "available_quantity": 5,
    }
    saved = service.reference_product(old)
    current = {
        **old,
        "product_name": "大米",
        "image_url": "https://example.test/current.png",
        "product_description": "【供货说明】演示商品，非真实供货；图片仅供食材示意。\n\n"
        + old["product_description"].removeprefix("示例·"),
    }
    monkeypatch.setattr(service, "current_reference_catalog", AsyncMock(return_value={"items": [current]}))

    assert saved["facts_hash"] != service.reference_product(current)["facts_hash"]
    assert await service.current_reference_items([saved]) == {"sku-rice": current}
    plan = {"purchase_items": [saved], "meals": []}
    displayed = await service.reference_plan_display(None, plan)
    assert displayed["purchase_items"][0]["product_name"] == "大米"
    assert displayed["purchase_items"][0]["product_description"] == current["product_description"]
    assert displayed["purchase_items"][0]["image_url"] == current["image_url"]
    assert plan["purchase_items"][0]["product_name"] == "示例·大米"
    long_description = service.current_reference_display_item(saved, {**current, "product_description": "x" * 4001})
    assert len(long_description["product_description"]) == 4000 and long_description["description_truncated"] is True
    for change in (
        {"product_name": "花生米"},
        {"product_description": current["product_description"] + "含花生"},
        {"allergen_codes": ["花生"]},
        {"ingredients": ["大米", "花生"]},
        {"sku_name": "一公斤"},
        {"net_content": {"value": "1000", "unit": "g"}},
        {"category_code": "snack"},
        {"sale_status": "unavailable"},
        {"available_quantity": 0},
    ):
        monkeypatch.setattr(
            service, "current_reference_catalog", AsyncMock(return_value={"items": [{**current, **change}]})
        )
        with pytest.raises(HealthVisionError, match="reference_product_changed"):
            await service.current_reference_items([saved])


@pytest.mark.asyncio
async def test_reference_context_limits_categories_then_preserves_selected_product_facts(monkeypatch):
    """先给分类再读商品，裁剪展示详情仍保留完整事实哈希与保存重验。"""
    from yuxi.services import reference_meal_plan_service as service

    monkeypatch.setattr(service, "queue_reference_images", AsyncMock(return_value=(None, False)))

    sku = {
        "sku_id": "synthetic-rice",
        "product_id": "synthetic-product",
        "product_name": "大米",
        "sku_name": "500克包装",
        "category_code": "grain",
        "net_content": "500g",
        "ingredients": ["大米"],
        "allergen_codes": ["待核对"],
        "data_completeness": "partial",
        "data_issues": ["包装成分尚待核对"],
        "product_description": "合成营销说明" * 100,
        "price_cent": 500,
        "available_quantity": 3,
        "sale_status": "available",
    }
    session = SimpleNamespace()

    @asynccontextmanager
    async def session_context():
        yield session

    monkeypatch.setattr(service.pg_manager, "get_async_session_context", session_context)
    monkeypatch.setattr(
        service,
        "require_planner_run",
        AsyncMock(
            return_value=(
                SimpleNamespace(id="synthetic-run"),
                SimpleNamespace(member_id="synthetic-member", conversation_id="synthetic-conversation"),
            )
        ),
    )
    monkeypatch.setattr(
        service,
        "bound_reference_context",
        AsyncMock(
            return_value={
                "selection": {"meal_types": ["breakfast"], "plan_date": "2026-11-09"},
                "members": [],
                "sources": {},
            }
        ),
    )
    monkeypatch.setattr(
        service,
        "commerce_request",
        AsyncMock(
            return_value={
                "catalog_version": "v1",
                "items": [{"category_code": "grain", "name": "米面", "product_count": 1}],
            }
        ),
    )
    monkeypatch.setattr(service, "current_catalog", AsyncMock(return_value={"version": "v1", "items": [sku]}))
    context = SimpleNamespace(uid="synthetic-owner")
    result = await service.get_reference_context(context)
    assert result["categories"] == [{"category_code": "grain", "name": "米面", "product_count": 1}]
    assert "catalog" not in result and result["commerce_notice"] is None
    receipts = {"get_reference_plan_context": [result], "read_reference_recipe": [document()[("recipe", "chunk")]]}

    async def tool_payloads(session, run, name):
        return receipts[name]

    monkeypatch.setattr(service, "tool_payloads", tool_payloads)
    read = await service.find_reference_products(context, ["grain"])
    receipts["find_reference_products"] = [read]
    product = read["catalog"][0]
    assert product["product_description"] == sku["product_description"][:320]
    assert product["description_truncated"] is True
    assert product["data_issues"] == sku["data_issues"]
    assert product["facts_hash"] == service.reference_product(sku)["facts_hash"]
    for field in (
        "sku_id",
        "product_id",
        "product_name",
        "sku_name",
        "category_code",
        "net_content",
        "ingredients",
        "allergen_codes",
        "data_completeness",
        "price_cent",
        "available_quantity",
    ):
        assert product[field] == sku[field]
    assert "image_url" not in product

    second = {**sku, "sku_id": "57", "product_id": "57"}
    monkeypatch.setattr(service, "current_catalog", AsyncMock(return_value={"version": "v1", "items": [sku, second]}))
    shared = await service.find_reference_products(context, ["grain"])
    assert shared["shared_data_issues"] == sku["data_issues"]
    assert all("data_issues" not in item and "image_url" not in item for item in shared["catalog"])
    assert [item["facts_hash"] for item in shared["catalog"]] == [
        service.reference_product(item)["facts_hash"] for item in (sku, second)
    ]

    second["data_issues"] = ["另一种待核对项"]
    mixed = await service.find_reference_products(context, ["grain"])
    assert "shared_data_issues" not in mixed
    assert [item["data_issues"] for item in mixed["catalog"]] == [sku["data_issues"], second["data_issues"]]

    monkeypatch.setattr(service, "recipe_document", AsyncMock(return_value=document()[("recipe", "chunk")]))
    value = draft()
    value.update(
        product_matches=[{"product_id": sku["product_id"], "ingredient_refs": ["大米100克"]}],
        purchase_items=[],
        purchase_gaps=[],
    )
    monkeypatch.setattr(
        service,
        "current_catalog",
        AsyncMock(return_value={"version": "v1", "items": [{**sku, "product_name": "身份已变化"}]}),
    )
    with pytest.raises(HealthVisionError, match="reference_product_changed"):
        await service.save_reference_plan(context, value)

    session.get = AsyncMock(return_value=None)
    session.add = lambda row: None
    monkeypatch.setattr(
        service,
        "current_catalog",
        AsyncMock(return_value={"version": "v2", "items": [{**sku, "available_quantity": 0}]}),
    )
    result = await service.save_reference_plan(context, value)
    assert result["purchase_items"] == []
    assert result["purchase_status"] == "product_selected"
    assert result["product_matches"][0]["product_id"] == sku["product_id"]
    assert result["product_matches"][0]["skus"][0]["available_quantity"] == 0

    product_value = draft()
    product_value.update(
        product_matches=[{"product_id": sku["product_id"], "ingredient_refs": ["大米100克"]}],
        purchase_items=[],
        purchase_gaps=[],
    )
    product_result = await service.save_reference_plan(context, product_value)
    assert product_result["purchase_status"] == "product_selected"
    assert product_result["purchase_items"] == []
    assert product_result["product_matches"][0]["product_id"] == sku["product_id"]
    assert product_result["product_matches"][0]["skus"][0]["available_quantity"] == 0


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


def test_product_level_selection_does_not_require_sku_price_or_stock():
    value = draft()
    value.update(
        product_matches=[{"product_id": "rice-product", "ingredient_refs": ["大米100克"]}],
        purchase_items=[],
        purchase_gaps=[],
    )

    result = ReferencePlanDraft.model_validate(value)
    selected = ReferenceReadSelection.model_validate(
        {
            "use_read_recipes": True,
            "auto_purchase_matches": True,
            "meals": [
                {
                    "meal_type": "breakfast",
                    "dishes": [{"file_id": "recipe", "chunk_id": "chunk"}],
                }
            ],
            "product_matches": [{"product_id": "rice-product", "candidate_keys": ["ingredient:rice"]}],
        }
    )

    assert result.product_matches[0].product_id == "rice-product"
    assert selected.product_matches[0].product_id == "rice-product"


@pytest.mark.asyncio
async def test_new_reference_save_rejects_legacy_sku_level_draft_before_database_access():
    """旧快照可继续读取，但新的保存边界不能再写固定 SKU。"""
    value = draft()
    value.update(
        product_matches=[],
        purchase_items=[{"sku_id": "rice-500", "quantity": 1, "ingredient_refs": ["大米100克"]}],
        purchase_gaps=[],
    )

    with pytest.raises(HealthVisionError) as failed:
        await save_reference_plan(None, value)

    assert failed.value.code == "reference_purchase_schema_legacy"


@pytest.mark.asyncio
async def test_purchase_stage_requires_user_sku_choice_and_rechecks_live_stock(monkeypatch):
    from yuxi.services import reference_meal_plan_service as service

    sku = {
        "product_id": "rice-product",
        "sku_id": "rice-500",
        "product_name": "大米",
        "sku_name": "500克",
        "category_code": "grain",
        "sale_status": "available",
        "available_quantity": 5,
        "price_cent": 800,
        "ingredients": [],
        "allergen_codes": [],
        "data_completeness": "partial",
        "data_issues": [],
    }
    monkeypatch.setattr(service, "current_catalog", AsyncMock(return_value={"version": "v2", "items": [sku]}))
    plan = {
        "members": [],
        "catalog_version": "v1",
        "meals": [{"meal_type": "breakfast", "dishes": [{"ingredients": ["大米100克"]}]}],
        "product_matches": [
            service.reference_product_group({**sku, "skus": [sku]}, ["大米100克"])
        ],
        "purchase_items": [],
        "purchase_gaps": [],
    }

    with pytest.raises(HealthVisionError, match="reference_purchase_choice_invalid"):
        await reference_purchase_items(plan, ["breakfast"], [])
    items, version = await reference_purchase_items(
        plan,
        ["breakfast"],
        [{"product_id": "rice-product", "sku_id": "rice-500", "quantity": 2}],
    )

    assert version == "v2"
    assert [(item["sku_id"], item["quantity"], item["ingredient_refs"]) for item in items] == [
        ("rice-500", 2, ["大米100克"])
    ]
    sku["price_cent"] = 900
    sku["available_quantity"] = 6
    items, _ = await reference_purchase_items(
        plan, ["breakfast"], [{"product_id": "rice-product", "sku_id": "rice-500", "quantity": 2}]
    )
    assert items[0]["price_cent"] == 900
    sku["product_name"] = "花生"
    with pytest.raises(HealthVisionError, match="reference_product_changed"):
        await reference_purchase_items(
            plan, ["breakfast"], [{"product_id": "rice-product", "sku_id": "rice-500", "quantity": 2}]
        )


@pytest.mark.asyncio
async def test_purchase_stage_allows_buying_only_selected_products(monkeypatch):
    """餐单返回全部商品，但用户可只购买其中有需要且有库存的规格。"""
    from yuxi.services import reference_meal_plan_service as service

    catalog = [
        {
            "product_id": "rice-product",
            "sku_id": "rice-500",
            "product_name": "大米",
            "sale_status": "available",
            "available_quantity": 5,
            "price_cent": 800,
            "ingredients": [],
            "allergen_codes": [],
        },
        {
            "product_id": "egg-product",
            "sku_id": "egg-6",
            "product_name": "鸡蛋",
            "sale_status": "unavailable",
            "available_quantity": 0,
            "price_cent": 1200,
            "ingredients": [],
            "allergen_codes": [],
        },
    ]
    monkeypatch.setattr(service, "current_catalog", AsyncMock(return_value={"version": "v3", "items": catalog}))
    plan = {
        "members": [],
        "catalog_version": "v2",
        "meals": [{"meal_type": "breakfast", "dishes": [{"ingredients": ["大米100克", "鸡蛋1个"]}]}],
        "product_matches": [
            service.reference_product_group({**catalog[0], "skus": [catalog[0]]}, ["大米100克"]),
            service.reference_product_group({**catalog[1], "skus": [catalog[1]]}, ["鸡蛋1个"]),
        ],
        "purchase_items": [],
        "purchase_gaps": [],
    }

    items, version = await reference_purchase_items(
        plan,
        ["breakfast"],
        [{"product_id": "rice-product", "sku_id": "rice-500", "quantity": 1}],
    )

    assert version == "v3"
    assert [(item["sku_id"], item["quantity"]) for item in items] == [("rice-500", 1)]

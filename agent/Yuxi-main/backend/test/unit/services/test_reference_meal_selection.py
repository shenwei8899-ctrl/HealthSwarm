"""原谱选择装配的 schema、匹配及拒绝；不代替 PG、对象和 Worker 验收。"""

from contextlib import asynccontextmanager
from copy import deepcopy
from dataclasses import dataclass
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock
import sys

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode
from pydantic import ValidationError

from yuxi.agents.toolkits.meal_planner import save_reference_meal_plan
from yuxi.services import recipe_translation_service as translations, reference_meal_selection_service as selection
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.services.reference_meal_plan_types import REFERENCE_TOOLS, ReferencePlanDraft
from yuxi.services.reference_recipe_matching import reference_candidate_key, reference_ingredient_candidates

RAW = "# Rice\n\n## Ingredients\n- 100 g rice\n- 1 cup water\n\n## Directions\n1. Boil rice and water.\n"
SOURCE = {
    "file_id": "rice-file",
    "chunk_id": "rice-chunk",
    "kb_id": "recipe-kb",
    "filename": "Rice.md",
    "file_hash": "original-file-hash",
    "chunks_hash": "original-chunks-hash",
}
CHINESE = {
    "name": "米饭",
    "ingredients": ["100 g 大米", "1杯水"],
    "steps": ["将大米和水煮熟。"],
    "portion_quote": None,
    "nutrition_quote": None,
}


def payload():
    """模型只作来源选择，不重写原始字段。"""
    return {
        "use_read_recipes": True,
        "auto_purchase_matches": True,
        "meals": [{"meal_type": "breakfast", "dishes": [{"file_id": "rice-file", "chunk_id": "rice-chunk"}]}],
        "purchase_items": [
            {"sku_id": "rice-sku", "quantity": 2, "candidate_keys": [reference_candidate_key("100 g rice")]}
        ],
    }


def product(sku_id="rice-sku", name="大米", price=800):
    """仅为词法匹配提供合成已读商品，价格不是营养事实。"""
    return {
        "sku_id": sku_id,
        "product_name": name,
        "price_cent": price,
        "available_quantity": 10,
        "sale_status": "available",
    }


@pytest.mark.parametrize("flag", ["use_read_recipes", "auto_purchase_matches"])
@pytest.mark.parametrize("value", [None, False, 1, "true"])
def test_source_selection_requires_explicit_boolean_flags(flag, value):
    """两个分支开关都必须由调用方明确给出布尔真。"""
    body = payload()
    if value is None:
        body.pop(flag)
    else:
        body[flag] = value
    with pytest.raises(ValidationError):
        selection.ReferenceReadSelection.model_validate(body)


@pytest.mark.parametrize(
    "field,value",
    [("name", "invented"), ("ingredients", ["invented"]), ("steps", ["invented"]), ("portion_quote", "one")],
)
def test_selection_cannot_overwrite_source_quotes(field, value):
    """新分支不接受任何用来改写原文的字段。"""
    body = payload()
    body["meals"][0]["dishes"][0][field] = value
    with pytest.raises(ValidationError):
        selection.ReferenceReadSelection.model_validate(body)


@pytest.mark.parametrize("value", [True, 0, 100, "2", 1.5])
def test_packaging_quantity_is_explicit_bounded_integer(value):
    """布尔、字符串和越界数量不能作为包装选择。"""
    body = payload()
    body["purchase_items"][0]["quantity"] = value
    with pytest.raises(ValidationError):
        selection.ReferenceReadSelection.model_validate(body)


@pytest.mark.parametrize("target", ["meals", "purchase_items"])
def test_duplicate_meal_or_sku_cannot_hide_choices(target):
    """餐次与商品不能通过重复项覆盖已有决定。"""
    body = payload()
    body[target].append(deepcopy(body[target][0]))
    with pytest.raises(ValidationError):
        selection.ReferenceReadSelection.model_validate(body)


def test_ingredient_references_are_exact_and_gaps_preserve_real_status():
    """原文完整对应，水、缺货、待确认和可选缺口分别保存。"""
    ingredients = ["100 g rice", "1 cup water", "1 tomato", "1 tablespoon soy sauce", "parsley (optional)"]
    meals = [{"dishes": [{"ingredients": ingredients}]}]
    choices = selection.ReferenceReadSelection.model_validate(payload()).purchase_items
    items, gaps = selection._purchase_choices(meals, choices, {"rice-sku": product()})
    assert items == [{"sku_id": "rice-sku", "quantity": 2, "ingredient_refs": ["100 g rice"]}]
    assert [(gap["ingredient"], gap["reason"]) for gap in gaps] == [
        ("1 cup water", "not_sold"),
        ("1 tomato", "no_match"),
        ("1 tablespoon soy sauce", "needs_confirmation"),
        ("parsley (optional)", "optional_not_selected"),
    ]
    assert ingredients == ["100 g rice", "1 cup water", "1 tomato", "1 tablespoon soy sauce", "parsley (optional)"]


def test_available_required_product_without_quantity_cannot_be_called_a_gap():
    """已知有对应商品时不能为省略包装选择伪造无匹配。"""
    meals = [{"dishes": [{"ingredients": ["100 g rice", "1 tomato"]}]}]
    choices = selection.ReferenceReadSelection.model_validate(payload()).purchase_items
    seen = {"rice-sku": product(), "tomato-sku": product("tomato-sku", "番茄")}
    with pytest.raises(HealthVisionError) as failed:
        selection._purchase_choices(meals, choices, seen)
    assert failed.value.code == "reference_ingredient_mismatch"


def test_retry_turns_unresolved_candidate_into_self_purchase_instead_of_guessing():
    """Agent 修正后仍漏选时，后台保留餐单但不擅自选商品或包装数量。"""
    meals = [{"dishes": [{"ingredients": ["100 g rice", "1 tomato"]}]}]
    body = payload()
    body["purchase_items"].append(
        {"sku_id": "unknown-sku", "quantity": 3, "candidate_keys": ["ingredient:invalid"]}
    )
    choices = selection.ReferenceReadSelection.model_validate(body).purchase_items
    seen = {
        "rice-sku": product(),
        "tomato-expensive": product("tomato-expensive", "番茄", 900),
        "tomato-cheap": product("tomato-cheap", "番茄", 500),
        "unknown-sku": product("unknown-sku", "未识别原料", 100),
    }
    items, gaps = selection._purchase_choices(meals, choices, seen, allow_purchase_fallback=True)
    assert items == [{"sku_id": "rice-sku", "quantity": 2, "ingredient_refs": ["100 g rice"]}]
    assert [(gap["ingredient"], gap["reason"]) for gap in gaps] == [("1 tomato", "needs_confirmation")]


def test_optional_product_can_remain_unselected_even_when_available():
    """原谱可选食材不因商城有货变成强制采购。"""
    meals = [{"dishes": [{"ingredients": ["100 g rice", "1 tomato (optional)"]}]}]
    choices = selection.ReferenceReadSelection.model_validate(payload()).purchase_items
    seen = {"rice-sku": product(), "tomato-sku": product("tomato-sku", "番茄")}
    items, gaps = selection._purchase_choices(meals, choices, seen)
    assert len(items) == 1 and gaps[0]["reason"] == "optional_not_selected"


def test_explicit_valid_alternative_sku_is_used_instead_of_guessing_cheapest():
    """相同食材的合法已读规格尊重明确选择及数量。"""
    meals = [{"dishes": [{"ingredients": ["100 g rice"]}]}]
    body = payload()
    body["purchase_items"] = [
        {"sku_id": "chosen", "quantity": 3, "candidate_keys": [reference_candidate_key("100 g rice")]}
    ]
    seen = {"cheap": product("cheap", price=100), "chosen": product("chosen", price=200)}
    items, gaps = selection._purchase_choices(
        meals, selection.ReferenceReadSelection.model_validate(body).purchase_items, seen
    )
    assert items == [{"sku_id": "chosen", "quantity": 3, "ingredient_refs": ["100 g rice"]}]
    assert gaps == []


def test_selected_sku_must_belong_to_candidate_group_issued_in_recipe_receipt():
    """即使后来读取到同名 SKU，也不能越过菜谱回执原先签发的候选边界。"""
    ingredient = "100 g rice"
    key = reference_candidate_key(ingredient)
    meals = [{"dishes": [{"ingredients": [ingredient]}]}]
    body = payload()
    body["purchase_items"] = [{"sku_id": "rice-new", "quantity": 1, "candidate_keys": [key]}]
    choices = selection.ReferenceReadSelection.model_validate(body).purchase_items
    seen = {"rice-old": product("rice-old"), "rice-new": product("rice-new")}
    with pytest.raises(HealthVisionError) as failed:
        selection._purchase_choices(meals, choices, seen, issued_candidates={key: {"rice-old"}})
    assert failed.value.code == "reference_ingredient_mismatch"


def test_unused_sku_is_rejected_from_model_purchase_selection():
    """模型附带的多余规格没有服务端候选键，正常保存不能静默接受。"""
    meals = [{"dishes": [{"ingredients": ["100 g rice"]}]}]
    body = payload()
    body["purchase_items"].append(
        {"sku_id": "tomato-sku", "quantity": 1, "candidate_keys": ["ingredient:unrelated"]}
    )
    seen = {"rice-sku": product(), "tomato-sku": product("tomato-sku", "番茄")}
    with pytest.raises(HealthVisionError) as failed:
        selection._purchase_choices(meals, selection.ReferenceReadSelection.model_validate(body).purchase_items, seen)
    assert failed.value.code == "reference_ingredient_mismatch"


def test_two_valid_skus_for_one_ingredient_still_fail():
    """同一食材的第二个有效规格不能被当作无关选品静默删掉。"""
    body = payload()
    body["purchase_items"].append(
        {"sku_id": "rice-alt", "quantity": 3, "candidate_keys": [reference_candidate_key("100 g rice")]}
    )
    with pytest.raises(ValidationError):
        selection.ReferenceReadSelection.model_validate(body)


def test_out_of_stock_same_food_cannot_become_self_prepare_gap():
    """目录已读的零库存同类规格不能被当成无关商品剔除。"""
    meals = [{"dishes": [{"ingredients": ["100 g rice", "1 tomato"]}]}]
    body = payload()
    body["purchase_items"].append(
        {"sku_id": "tomato-sku", "quantity": 1, "candidate_keys": [reference_candidate_key("1 tomato")]}
    )
    seen = {"rice-sku": product(), "tomato-sku": {**product("tomato-sku", "番茄"), "available_quantity": 0}}
    with pytest.raises(HealthVisionError) as failed:
        selection._purchase_choices(meals, selection.ReferenceReadSelection.model_validate(body).purchase_items, seen)
    assert failed.value.code == "reference_ingredient_mismatch"


def test_unrecognized_product_cannot_be_assumed_unrelated():
    """商品身份无法识别时不能擅自删除明确选择。"""
    meals = [{"dishes": [{"ingredients": ["100 g rice"]}]}]
    body = payload()
    body["purchase_items"].append(
        {"sku_id": "unknown-sku", "quantity": 1, "candidate_keys": ["ingredient:unknown"]}
    )
    seen = {"rice-sku": product(), "unknown-sku": product("unknown-sku", "未识别原料")}
    with pytest.raises(HealthVisionError) as failed:
        selection._purchase_choices(meals, selection.ReferenceReadSelection.model_validate(body).purchase_items, seen)
    assert failed.value.code == "reference_ingredient_mismatch"


def test_unrelated_sku_cannot_replace_required_product():
    """多余规格不能使缺少已知必需商品的餐单通过。"""
    meals = [{"dishes": [{"ingredients": ["100 g rice"]}]}]
    body = payload()
    body["purchase_items"] = [
        {"sku_id": "tomato-sku", "quantity": 1, "candidate_keys": [reference_candidate_key("100 g rice")]}
    ]
    seen = {"rice-sku": product(), "tomato-sku": product("tomato-sku", "番茄")}
    with pytest.raises(HealthVisionError) as failed:
        selection._purchase_choices(meals, selection.ReferenceReadSelection.model_validate(body).purchase_items, seen)
    assert failed.value.code == "reference_ingredient_mismatch"


def test_no_matched_sku_becomes_self_purchase_instead_of_failing_plan():
    """没有同名商城商品时仍保存菜谱，并把原料明确标成自行购买。"""
    meals = [{"dishes": [{"ingredients": ["100 g rice"]}]}]
    body = payload()
    body["purchase_items"] = []
    items, gaps = selection._purchase_choices(
        meals,
        selection.ReferenceReadSelection.model_validate(body).purchase_items,
        {"tomato-sku": product("tomato-sku", "番茄")},
    )
    assert items == []
    assert gaps == [
        {
            "ingredient": "100 g rice",
            "reason": "no_match",
            "detail": "需自行购买：本轮已查询的商城商品名称中未找到对应食材。",
        }
    ]


def test_product_name_owns_candidate_matching_and_returns_every_available_sku():
    """候选只由商品名决定；详情冲突不改变同名候选，多规格全部交给 Agent 选择。"""
    products = [
        {
            **product("rice-small", "大米", 500),
            "sku_name": "500克",
            "net_content": {"value": 500, "unit": "g"},
            "product_description": "写着番茄也不能改变商品名身份",
            "ingredients": ["番茄"],
            "allergen_codes": ["花生"],
        },
        {
            **product("rice-large", "大米", 800),
            "sku_name": "1千克",
            "net_content": {"value": 1, "unit": "kg"},
        },
    ]
    groups = reference_ingredient_candidates(("100 g rice",), products)
    assert groups == [
        {
            "candidate_key": reference_candidate_key("100 g rice"),
            "ingredient": "100 g rice",
            "food": "大米",
            "status": "matched",
            "candidate_skus": [
                {
                    "sku_id": "rice-small",
                    "product_name": "大米",
                    "sku_name": "500克",
                    "net_content": {"value": 500, "unit": "g"},
                    "price_cent": 500,
                    "available_quantity": 10,
                },
                {
                    "sku_id": "rice-large",
                    "product_name": "大米",
                    "sku_name": "1千克",
                    "net_content": {"value": 1, "unit": "kg"},
                    "price_cent": 800,
                    "available_quantity": 10,
                },
            ],
        }
    ]


def test_ambiguous_recipe_ingredient_does_not_guess_a_product_name():
    """菜谱写替代关系时不猜商城商品，保持自行购买待核对。"""
    groups = reference_ingredient_candidates(("1 tbsp vegetable or peanut oil",), [product("oil", "橄榄油")])
    assert groups == [
        {
            "candidate_key": reference_candidate_key("1 tbsp vegetable or peanut oil"),
            "ingredient": "1 tbsp vegetable or peanut oil",
            "food": None,
            "status": "needs_confirmation",
            "candidate_skus": [],
        }
    ]


@pytest.fixture
def assembly(monkeypatch):
    """隔离数据库和授权依赖，保留真实 parser、DTO 与采购匹配。"""
    document = {"scope": "reference_recipe", **SOURCE, "content": RAW}
    opened = {
        **deepcopy(document),
        "recipe_check": {
            "ingredient_matches": reference_ingredient_candidates(("100 g rice", "1 cup water"), [product()])
        },
    }
    state = SimpleNamespace(
        document=document,
        opened=[opened],
        selected_meals=["breakfast"],
        products=[product()],
        context=SimpleNamespace(uid="synthetic-user"),
        cached=None,
    )
    run = SimpleNamespace(id="synthetic-run")

    @asynccontextmanager
    async def session():
        """只提供合成会话，不接触真实数据库。"""
        yield "synthetic-session"

    async def current(*args):
        """当前餐次选择由合成服务边界提供。"""
        return {"selection": {"meal_types": state.selected_meals}}

    async def receipts(db, selected_run, tool):
        """不同工具的成功回执只属于所选合成 Run。"""
        assert db == "synthetic-session" and selected_run is run
        return state.opened if tool == "read_reference_recipe" else [{"catalog": state.products}]

    async def fresh(db, file_id, chunk_id):
        """模拟对象重读，不替代真实原始字节验收。"""
        assert (file_id, chunk_id) == ("rice-file", "rice-chunk")
        return deepcopy(state.document)

    fake_service = ModuleType("yuxi.services.reference_meal_plan_service")
    fake_service.bound_reference_context = current
    fake_service.tool_payloads = receipts
    fake_service.recipe_document = fresh
    fake_service.same_reference_document = lambda doc, receipt: all(
        receipt.get(key) == value for key, value in doc.items()
    )
    fake_planner = ModuleType("yuxi.services.health_meal_plan_service")
    fake_planner.require_planner_run = AsyncMock(return_value=(run, "synthetic-binding"))
    fake_manager = ModuleType("yuxi.storage.postgres.manager")
    fake_manager.pg_manager = SimpleNamespace(get_async_session_context=session)
    monkeypatch.setitem(sys.modules, fake_service.__name__, fake_service)
    monkeypatch.setitem(sys.modules, fake_planner.__name__, fake_planner)
    monkeypatch.setitem(sys.modules, fake_manager.__name__, fake_manager)
    monkeypatch.setattr(translations, "cached_chinese_display", AsyncMock(side_effect=lambda *args: state.cached))
    return state


@dataclass
class SaveContext:
    """合成保存请求的身份与工具配置。"""

    uid: str = "synthetic-user"
    request_id: str = "synthetic-request"
    tools: tuple = REFERENCE_TOOLS


@pytest.mark.asyncio
async def test_read_selection_unconfirmed_chicken_sku_keeps_real_gap(assembly):
    """未证实的加工规格不进入采购，原谱食材保留待确认缺口。"""
    assembly.document["content"] = (
        "# Pan-Seared Chicken Breast\n\n## Ingredients\n"
        "- 2 boneless skinless chicken breasts\n- 1 clove garlic\n\n"
        "## Directions\n1. Cook chicken and garlic.\n"
    )
    assembly.products = [product("garlic-sku", "大蒜"), product("chicken-sku", "鸡胸肉")]
    assembly.opened = [
        {
            **deepcopy(assembly.document),
            "recipe_check": {
                "ingredient_matches": reference_ingredient_candidates(
                    ("2 boneless skinless chicken breasts", "1 clove garlic"), assembly.products
                )
            },
        }
    ]
    context = SaveContext()
    saved = AsyncMock(return_value={"preview_id": "synthetic-preview"})
    sys.modules["yuxi.services.reference_meal_plan_service"].save_reference_plan = saved
    graph = StateGraph(MessagesState, context_schema=SaveContext)
    graph.add_node("tools", ToolNode([save_reference_meal_plan]))
    graph.add_edge(START, "tools")
    graph.add_edge("tools", END)
    compiled = graph.compile()
    chosen = payload()
    chosen["purchase_items"] = [
        {
            "sku_id": "garlic-sku",
            "quantity": 1,
            "candidate_keys": [reference_candidate_key("1 clove garlic")],
        },
    ]
    result = await compiled.ainvoke(
        {
            "messages": [
                HumanMessage("合成晚餐", additional_kwargs={"health_request_id": context.request_id}),
                AIMessage(
                    "",
                    tool_calls=[
                        {
                            "id": "first-save",
                            "name": "save_reference_meal_plan",
                            "args": {"read_selection": chosen},
                        }
                    ],
                ),
            ]
        },
        context=context,
    )
    assert result["messages"][-1].content == '{"preview_id": "synthetic-preview"}'
    saved.assert_awaited_once()
    draft = saved.await_args.args[1]
    assert [item.model_dump() for item in draft.purchase_items] == [
        {
            "sku_id": "garlic-sku",
            "quantity": 1,
            "ingredient_refs": ["1 clove garlic"],
        }
    ]
    assert [(gap.ingredient, gap.reason) for gap in draft.purchase_gaps] == [
        ("2 boneless skinless chicken breasts", "needs_confirmation"),
    ]


@pytest.mark.asyncio
async def test_assembly_copies_full_parsed_source_and_keeps_missing_translation(assembly):
    """标准稿直接使用 parser 的完整字段，不伪造英文译文。"""
    from yuxi.services.recipe_translation_service import checked_chinese_display

    original = payload()
    result = await selection.assemble_reference_selection(assembly.context, original)
    assert isinstance(result, ReferencePlanDraft)
    dish = result.meals[0].dishes[0]
    assert (dish.name, dish.ingredients, dish.steps) == (
        "Rice",
        ["100 g rice", "1 cup water"],
        ["Boil rice and water."],
    )
    assert dish.display_zh is None
    assert result.purchase_items[0].model_dump() == {
        "sku_id": "rice-sku",
        "quantity": 2,
        "ingredient_refs": ["100 g rice"],
    }
    assert [(gap.ingredient, gap.reason) for gap in result.purchase_gaps] == [("1 cup water", "not_sold")]
    assert original == payload()
    with pytest.raises(HealthVisionError) as failed:
        checked_chinese_display(dish.model_dump(exclude={"display_zh"}), None)
    assert failed.value.code == "recipe_translation_missing"


@pytest.mark.asyncio
async def test_assembly_allows_every_ingredient_to_be_self_purchased(assembly):
    """商城没有同名商品时，仍装配完整菜谱并保留全部自行购买缺口。"""
    body = payload()
    body["purchase_items"] = []
    assembly.products = [product("tomato-sku", "番茄")]
    result = await selection.assemble_reference_selection(assembly.context, body)
    assert result.purchase_items == []
    assert [(gap.ingredient, gap.reason) for gap in result.purchase_gaps] == [
        ("100 g rice", "no_match"),
        ("1 cup water", "not_sold"),
    ]


@pytest.mark.asyncio
async def test_assembly_rejects_same_name_sku_not_issued_by_opened_recipe(assembly):
    """后来读到的同名 SKU 不能越过已打开菜谱当时签发的候选集合。"""
    key = reference_candidate_key("100 g rice")
    assembly.opened[0]["recipe_check"] = {
        "ingredient_matches": [{"candidate_key": key, "candidate_skus": [{"sku_id": "rice-old"}]}]
    }
    assembly.products = [product("rice-old"), product("rice-new")]
    body = payload()
    body["purchase_items"] = [{"sku_id": "rice-new", "quantity": 1, "candidate_keys": [key]}]
    with pytest.raises(HealthVisionError) as failed:
        await selection.assemble_reference_selection(assembly.context, body)
    assert failed.value.code == "reference_ingredient_mismatch"


@pytest.mark.asyncio
async def test_all_three_meals_are_assembled_and_explicit_translation_is_preserved(assembly):
    """明确三餐得到完整标准稿，食材采购只映射一次。"""
    body = payload()
    body["meals"][0]["dishes"][0]["display_zh"] = CHINESE
    body["meals"][0]["dishes"][0]["cooking_minutes"] = 25
    body["meals"] = [{**deepcopy(body["meals"][0]), "meal_type": kind} for kind in ["breakfast", "lunch", "dinner"]]
    assembly.selected_meals = ["breakfast", "lunch", "dinner"]
    result = await selection.assemble_reference_selection(assembly.context, body)
    assert [meal.meal_type for meal in result.meals] == ["breakfast", "lunch", "dinner"]
    assert all(meal.dishes[0].display_zh.model_dump() == CHINESE for meal in result.meals)
    assert all(meal.dishes[0].cooking_minutes == 25 for meal in result.meals)
    translations.cached_chinese_display.assert_not_awaited()
    assert result.purchase_items[0].quantity == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure,code",
    [
        ("unopened", "reference_receipt_invalid"),
        ("source", "source_invalidated"),
        ("review", "reference_quote_invalid"),
        ("parse", "reference_quote_invalid"),
        ("meal", "reference_meals_mismatch"),
        ("unread_sku", "reference_product_changed"),
        ("no_products", "reference_product_required"),
        ("missing_candidates", "reference_receipt_invalid"),
    ],
)
async def test_assembly_rejects_missing_or_changed_authority(assembly, failure, code):
    """来源、餐次与商品边界失败时不产生可保存稿。"""
    body = payload()
    if failure == "unopened":
        assembly.opened = []
    elif failure == "source":
        assembly.document["file_hash"] = "changed"
    elif failure == "review":
        assembly.document["content"] += "\n## Notes\nAdd butter.\n"
        assembly.opened = [{**deepcopy(assembly.document), "recipe_check": {"ingredient_matches": []}}]
    elif failure == "parse":
        assembly.document["content"] = "only a directory"
        assembly.opened = [{**deepcopy(assembly.document), "recipe_check": {"ingredient_matches": []}}]
    elif failure == "meal":
        assembly.selected_meals = ["dinner"]
    elif failure == "unread_sku":
        body["purchase_items"][0]["sku_id"] = "unread"
    elif failure == "missing_candidates":
        assembly.opened[0].pop("recipe_check")
    else:
        assembly.products = []
    with pytest.raises(HealthVisionError) as failed:
        await selection.assemble_reference_selection(assembly.context, body)
    assert failed.value.code == code


@pytest.mark.asyncio
async def test_cached_translation_is_only_filled_when_input_did_not_supply_one(assembly):
    """只有未提交译文时才补充已验证缓存结果。"""
    assembly.cached = CHINESE
    result = await selection.assemble_reference_selection(assembly.context, payload())
    assert result.meals[0].dishes[0].display_zh.model_dump() == CHINESE


@pytest.mark.asyncio
async def test_explicit_invalid_translation_cannot_be_silently_replaced_by_valid_cache(assembly):
    """坏的显式译文仍交原校验拒绝，不能由缓存静默改为成功。"""
    body = payload()
    body["meals"][0]["dishes"][0]["display_zh"] = deepcopy(CHINESE)
    body["meals"][0]["dishes"][0]["display_zh"]["steps"][0] = "Boil rice and water."
    assembly.cached = CHINESE
    result = await selection.assemble_reference_selection(assembly.context, body)
    dish = result.meals[0].dishes[0]
    assert dish.display_zh.steps == ["Boil rice and water."]
    translations.cached_chinese_display.assert_not_awaited()
    with pytest.raises(HealthVisionError) as failed:
        translations.checked_chinese_display(dish.model_dump(exclude={"display_zh"}), dish.display_zh.model_dump())
    assert failed.value.code == "recipe_translation_invalid"


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid", ["missing", "source", "quantity", "english", "schema"])
async def test_invalid_cache_never_becomes_an_approved_translation(monkeypatch, invalid):
    """坏缓存、变源、改数量和未译英文保持译文缺失。"""
    dish = {
        "name": "Rice",
        "ingredients": ["100 g rice", "1 cup water"],
        "steps": ["Boil rice and water."],
        "portion_quote": None,
        "nutrition_quote": None,
    }
    record = SimpleNamespace(source=deepcopy(SOURCE), display=deepcopy(CHINESE))
    if invalid == "missing":
        record = None
    elif invalid == "source":
        record.source["file_hash"] = "wrong-source"
    elif invalid == "quantity":
        record.display["ingredients"][0] = "200 g 大米"
    elif invalid == "english":
        record.display["steps"][0] = "Boil rice and water."
    else:
        record.display = {"name": "米饭"}
    repository = ModuleType("yuxi.repositories.recipe_translation_repository")
    repository.RecipeTranslationRepository = lambda db: SimpleNamespace(get=AsyncMock(return_value=record))
    monkeypatch.setitem(sys.modules, repository.__name__, repository)
    assert await translations.cached_chinese_display("synthetic-session", {**dish, "source": SOURCE}) is None


@pytest.mark.asyncio
async def test_valid_cache_uses_current_source_and_canonical_quote_key(monkeypatch):
    """实际译文校验通过后，只按当前来源和标准引句键复用。"""
    from yuxi.services.recipe_translation_service import translation_key

    dish = {
        "name": "Rice",
        "ingredients": ["100 g rice", "1 cup water"],
        "steps": ["Boil rice and water."],
        "portion_quote": None,
        "nutrition_quote": None,
    }
    get = AsyncMock(return_value=SimpleNamespace(source=deepcopy(SOURCE), display=deepcopy(CHINESE)))
    repository = ModuleType("yuxi.repositories.recipe_translation_repository")
    repository.RecipeTranslationRepository = lambda db: SimpleNamespace(get=get)
    monkeypatch.setitem(sys.modules, repository.__name__, repository)
    result = await translations.cached_chinese_display("synthetic-session", {**dish, "source": SOURCE})
    assert result == CHINESE
    get.assert_awaited_once_with(translation_key({**dish, "source": SOURCE}))

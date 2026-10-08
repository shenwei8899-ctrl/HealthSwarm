"""食谱成品、份量参考与油糖去重的独立手算 oracle。"""

from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from yuxi.services.health_nutrition_service import calculate_nutrition, recipe_nutrients
from yuxi.services.health_vision_types import NUTRIENTS, HealthVisionError, MealPayload, PortionInput, RecipeInput


def fixture_recipe():
    """200g 原料 600kcal、20g 油 180kcal、10g 糖 40kcal，净成品 600g。"""
    foods = []
    for name, energy in (("合成原料", 300), ("合成油", 900), ("合成糖", 400)):
        foods.append(
            SimpleNamespace(
                id=str(uuid4()),
                name=name,
                source="独立合成手算",
                license="仅测试",
                edition="synthetic",
                dataset_version="test-1",
                cooking_state="原料",
                recipe_estimated=False,
                nutrients={code: str(energy if code == "energy_kcal" else 0) for code in NUTRIENTS},
            )
        )
    ingredients = [
        {"food": vars(food), "grams": grams, "role": role}
        for food, grams, role in zip(foods, ("200", "20", "10"), ("food", "oil", "sugar"))
    ]
    recipe = SimpleNamespace(
        id=str(uuid4()),
        name="合成菜谱",
        source="独立合成手算",
        license="仅测试",
        edition="synthetic",
        dataset_version="test-1",
        cooking_state="熟",
        ingredients=ingredients,
        yield_grams=Decimal(600),
    )
    return {food.id: food for food in foods}, recipe


def payload(recipe, **kwargs):
    """所有量和比例均明确填写，不使用默认份量。"""
    return MealPayload(
        meal_type="lunch",
        eaten_at="2026-10-04T12:00:00+08:00",
        items=[
            {
                "item_id": uuid4(),
                "name": "合成成品",
                "recipe_version_id": recipe.id,
                "grams": "300",
                "share_ratio": "0.5",
                "portion_source": "weighed",
                **kwargs,
            }
        ],
    )


@pytest.mark.parametrize(
    "mode,grams,oil_grams,expected",
    [(None, "300", None, "205.00"), ("append", "310", "10", "250.00"), ("replace", "295", "5", "182.50")],
)
def test_recipe_cooked_yield_and_oil_count_once(mode, grams, oil_grams, expected):
    foods, recipe = fixture_recipe()
    oil = next(food for food in foods.values() if food.name == "合成油")
    adjustments = [] if mode is None else [{"role": "oil", "mode": mode, "food_id": oil.id, "grams": oil_grams}]
    result = calculate_nutrition(payload(recipe, grams=grams, adjustments=adjustments), foods, {recipe.id: recipe})
    assert result["totals"]["energy_kcal"] == expected
    assert result["complete"] and result["estimated"]
    assert result["sources"][0]["yield_grams"] == "600"
    assert result["sources"][0]["ingredients"][0]["food"]["license"] == "仅测试"
    # 原料总重 230g 不是净成品重；每百克结果应为 820/6。
    assert Decimal(recipe_nutrients(recipe.ingredients, recipe.yield_grams)["energy_kcal"]) == Decimal(820) / 6


def test_portion_server_mapping_quantity_and_estimate():
    foods, recipe = fixture_recipe()
    portion = SimpleNamespace(
        id=str(uuid4()),
        food_id=None,
        recipe_version_id=recipe.id,
        grams_per_unit=Decimal(300),
        unit_label="合成实测碗",
        source="合成秤测",
        license="仅测试",
        edition="test",
        dataset_version="portion-1",
        applicable_scope="合成容器平装",
    )
    meal = payload(recipe, grams=None, portion_source="estimated", portion_reference_id=portion.id, portion_count="0.5")
    result = calculate_nutrition(meal, foods, {recipe.id: recipe}, {portion.id: portion})
    assert result["items"][0]["eaten_grams"] == "75.00"
    assert result["totals"]["energy_kcal"] == "102.50"
    assert result["sources"][-1]["dataset_version"] == "portion-1"
    for wrong in ({}, {portion.id: SimpleNamespace(**{**vars(portion), "recipe_version_id": str(uuid4())})}):
        with pytest.raises(HealthVisionError) as caught:
            calculate_nutrition(meal, foods, {recipe.id: recipe}, wrong)
        assert caught.value.code in {"portion_not_found", "portion_mapping_mismatch"}
    meal.items[0].portion_count = Decimal(100)
    with pytest.raises(HealthVisionError, match="portion_limit"):
        calculate_nutrition(meal, foods, {recipe.id: recipe}, {portion.id: portion})


def test_missing_recipe_nutrient_preserves_known_subtotal():
    foods, recipe = fixture_recipe()
    recipe.ingredients[0]["food"]["nutrients"]["energy_kcal"] = None
    assert recipe_nutrients(recipe.ingredients, recipe.yield_grams)["energy_kcal"] is None
    result = calculate_nutrition(payload(recipe), foods, {recipe.id: recipe})
    assert result["totals"]["energy_kcal"] is None and not result["complete"]
    assert result["known_subtotals"]["energy_kcal"] == "55.00"  # (180+40)*300/600*0.5


def test_estimated_adjustment_cannot_be_hidden_by_weighed_main_food():
    """主食品称重不意味着追加成分的配方营养也是实测。"""
    foods, recipe = fixture_recipe()
    base, oil, _ = list(foods.values())
    oil.recipe_estimated = True
    meal = payload(
        recipe,
        recipe_version_id=None,
        food_id=base.id,
        grams="110",
        share_ratio="1",
        adjustments=[{"role": "oil", "mode": "append", "food_id": oil.id, "grams": "10"}],
    )
    result = calculate_nutrition(meal, foods)
    assert result["complete"] and result["estimated"]
    assert result["totals"]["energy_kcal"] == "390.00"  # 100g*300/100 + 10g*900/100
    assert result["sources"][1]["recipe_estimated"]


def test_explicit_zero_share_is_distinct_from_unknown_share():
    """设计允许明确未食用比例零；空比例仍不可计算。"""
    foods, recipe = fixture_recipe()
    result = calculate_nutrition(payload(recipe, share_ratio="0"), foods, {recipe.id: recipe})
    assert result["complete"] and result["totals"]["energy_kcal"] == "0.00"
    unknown = calculate_nutrition(payload(recipe, share_ratio=None), foods, {recipe.id: recipe})
    assert not unknown["complete"] and unknown["totals"]["energy_kcal"] is None


@pytest.mark.parametrize(
    "defect,code",
    [
        ("unknown_food", "adjustment_food_not_found"),
        ("overweight", "adjustment_weight_invalid"),
        ("unknown_role", "replacement_role_missing"),
        ("bad_yield", "replacement_yield_invalid"),
    ],
)
def test_oil_replacement_refuses_ambiguous_or_invalid_inputs(defect, code):
    foods, recipe = fixture_recipe()
    oil = next(food for food in foods.values() if food.name == "合成油")
    adjustment = {"role": "oil", "mode": "replace", "food_id": oil.id, "grams": "5"}
    if defect == "unknown_food":
        adjustment["food_id"] = str(uuid4())
    elif defect == "overweight":
        adjustment["grams"] = "300"
    elif defect == "unknown_role":
        recipe.ingredients[1]["role"] = "food"
    else:
        recipe.yield_grams = Decimal(20)
    with pytest.raises(HealthVisionError) as caught:
        calculate_nutrition(payload(recipe, adjustments=[adjustment]), foods, {recipe.id: recipe})
    assert caught.value.code == code


@pytest.mark.parametrize(
    "extra",
    [
        {"food_id": uuid4()},
        {"portion_count": "1"},
        {"portion_reference_id": uuid4(), "portion_count": "1"},
        {"grams": None, "portion_reference_id": uuid4(), "portion_count": "1"},
        {"grams": None, "portion_source": "estimated", "portion_reference_id": uuid4()},
        {
            "recipe_version_id": None,
            "adjustments": [{"role": "oil", "mode": "replace", "food_id": uuid4(), "grams": 5}],
        },
        {"adjustments": [{"role": "oil", "mode": "append", "food_id": uuid4(), "grams": 5}] * 2},
    ],
)
def test_conflicting_mapping_portion_and_adjustment_rejected(extra):
    _, recipe = fixture_recipe()
    with pytest.raises(ValidationError):
        payload(recipe, **extra)


def test_published_recipe_and_portion_require_traceable_valid_versions():
    _, recipe = fixture_recipe()
    source = {
        "record_code": "synthetic",
        "name": "合成",
        "cooking_state": "熟",
        "source": "合成",
        "license": "仅测试",
        "edition": "test",
        "dataset_version": "test",
    }
    for yield_grams in ("0", "NaN", "0.0000001"):
        with pytest.raises(ValidationError):
            RecipeInput(**source, yield_grams=yield_grams, ingredients=[{"food_id": uuid4(), "grams": "1"}])
    with pytest.raises(ValidationError):
        RecipeInput(**source, yield_grams="1", ingredients=[], nutrients={"energy_kcal": 999})
    base = {key: value for key, value in source.items() if key not in {"record_code", "name", "cooking_state"}}
    for mapping in ({}, {"food_id": uuid4(), "recipe_version_id": recipe.id}):
        with pytest.raises(ValidationError):
            PortionInput(**base, **mapping, unit_label="碗", grams_per_unit="300", applicable_scope="平装")
    with pytest.raises(ValidationError):
        PortionInput(**base, food_id=uuid4(), unit_label="碗", grams_per_unit="0.0000001", applicable_scope="平装")

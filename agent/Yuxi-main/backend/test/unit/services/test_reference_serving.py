"""逐人成员身份、食材守恒及确定性营养的负向边界。"""

from copy import deepcopy
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from yuxi.services.health_vision_types import HealthVisionError
from yuxi.services.reference_meal_plan_types import ReferenceServingSuggestion
from yuxi.services.reference_serving import checked_member_servings
from yuxi.services.reference_serving_nutrition import calculate_reference_nutrition

A = "00000000-0000-4000-8000-000000000001"
B = "00000000-0000-4000-8000-000000000002"


def suggestion():
    """合成两人对肉菜作不同分配，原料与熟重不等同。"""
    return {
        "ingredient_amounts": [
            {"position": 0, "amount": 100, "unit": "克"},
            {"position": 1, "amount": 200, "unit": "克"},
        ],
        "members": [
            {
                "member_id": A,
                "cooked_grams": 120,
                "description": "分取肉和蔬菜",
                "ingredient_amounts": [
                    {"position": 0, "amount": 80, "unit": "克"},
                    {"position": 1, "amount": 50, "unit": "克"},
                ],
            },
            {
                "member_id": B,
                "cooked_grams": 160,
                "description": "蔬菜为主，分取余下的肉",
                "ingredient_amounts": [
                    {"position": 0, "amount": 20, "unit": "克"},
                    {"position": 1, "amount": 150, "unit": "克"},
                ],
            },
        ],
    }


def test_member_allocations_preserve_identity_basis_and_estimate():
    value = ReferenceServingSuggestion.model_validate(suggestion())
    people = checked_member_servings(value, {A, B}, {A: "成员甲", B: "成员乙"}, required=True)
    assert [(p["name"], p["cooked_grams"]) for p in people] == [("成员甲", 120), ("成员乙", 160)]
    assert all(p["source"] == "model_estimate" and p["basis"] == "cooked_edible" for p in people)


@pytest.mark.parametrize("fault", ["missing", "other_member", "unit", "amount", "position"])
def test_invalid_or_incomplete_allocations_are_rejected(fault):
    raw = suggestion()
    if fault == "missing":
        raw["members"] = []
    elif fault == "other_member":
        raw["members"][1]["member_id"] = "00000000-0000-4000-8000-000000000003"
    elif fault == "unit":
        raw["members"][0]["ingredient_amounts"][0]["unit"] = "个"
    elif fault == "amount":
        raw["members"][0]["ingredient_amounts"][0]["amount"] = 90
    else:
        raw["members"][0]["ingredient_amounts"][0]["position"] = 2
    with pytest.raises(HealthVisionError, match="reference_amounts_invalid"):
        checked_member_servings(
            ReferenceServingSuggestion.model_validate(raw), {A, B}, {A: "甲", B: "乙"}, required=True
        )


@pytest.mark.parametrize("fault", ["duplicate", "nan", "blank", "duplicate_ingredient", "model_nutrition"])
def test_model_cannot_submit_invalid_servings_or_nutrition(fault):
    raw = suggestion()
    if fault == "duplicate":
        raw["members"][1]["member_id"] = A
    elif fault == "nan":
        raw["members"][0]["cooked_grams"] = float("nan")
    elif fault == "blank":
        raw["members"][0]["description"] = "  "
    elif fault == "model_nutrition":
        raw["members"][0]["nutrition"] = {"energyKcal": 100}
    else:
        raw["members"][0]["ingredient_amounts"].append(deepcopy(raw["members"][0]["ingredient_amounts"][0]))
    with pytest.raises(ValidationError):
        ReferenceServingSuggestion.model_validate(raw)


def test_legacy_missing_servings_remain_readable_without_new_save_requirement():
    assert checked_member_servings(None, {A}, {A: "甲"}) == []


def test_whole_nutrition_uses_original_recipe_grams_and_preserves_unknown():
    recipe = SimpleNamespace(
        ingredients=[
            {"food": {"id": "meat"}, "grams": "100"},
            {"food": {"id": "vegetable"}, "grams": "200"},
        ],
        yield_grams=280,
    )
    foods = {
        "meat": SimpleNamespace(nutrients={"energy_kcal": 200, "protein_g": 20, "sodium_mg": 0}),
        "vegetable": SimpleNamespace(nutrients={"energy_kcal": 20, "protein_g": 2, "sodium_mg": 0}),
    }
    total = calculate_reference_nutrition(recipe, foods)
    assert total["energyKcal"] == 240
    assert total["proteinG"] == 24
    assert total["sodiumMg"] == 0
    assert total["fatG"] is None and total["fiberG"] is None
    assert total["basis"] == "whole_dish" and total["quantity_basis"] == "source_recipe"
    recipe.yield_grams = 1000
    assert calculate_reference_nutrition(recipe, foods) == total


def test_incomplete_recipe_ingredients_cannot_be_reported_as_whole_dish_nutrition():
    for ingredients in [[], [{"food": {"id": "unknown"}}]]:
        assert calculate_reference_nutrition(SimpleNamespace(ingredients=ingredients), {}) is None


def test_archive_preserves_nutrition_quantity_basis_without_mutating_legacy_data():
    """旧计划量保持原样，原食谱总量标记随公开快照保留。"""
    from yuxi.services.meal_archive_projection import archive_meal

    old = {"name": "旧菜", "nutrition_total": {"basis": "whole_dish", "energyKcal": 240}}
    current = {
        "name": "原谱菜",
        "nutrition_total": {"basis": "whole_dish", "quantity_basis": "source_recipe", "energyKcal": 580},
    }
    meal = {"meal_type": "dinner", "dishes": [old, current]}
    before = deepcopy(meal)
    saved = archive_meal(meal)
    assert saved["dishes"][0]["nutrition_total"] == old["nutrition_total"]
    assert saved["dishes"][1]["nutrition_total"]["quantity_basis"] == "source_recipe"
    assert meal == before


def test_shared_archive_never_contains_model_health_reasoning():
    """归档仅展示程序生成的原料分配，不复制模型接触过的健康资料。"""
    import json
    from yuxi.services.meal_archive_projection import archive_meal
    from yuxi.services.daily_meal_plan_service import shared_meal_view

    raw = suggestion()
    raw["members"][0]["description"] = "合成私密诊断及医嘱，不应出现在共享页"
    value = ReferenceServingSuggestion.model_validate(raw)
    people = checked_member_servings(value, {A, B}, {A: "甲", B: "乙"}, ingredient_labels=["公开原料甲", "公开原料乙"])
    dish = {"name": "合成菜", "serving_suggestion": value.model_dump(mode="json"), "member_servings": people}
    meal = {"meal_type": "dinner", "members": [{"id": A, "name": "甲"}], "dishes": [dish]}
    for public in [archive_meal(meal), shared_meal_view(meal, meal["members"])]:
        assert "合成私密诊断" not in json.dumps(public, ensure_ascii=False)
        assert "公开原料甲" in json.dumps(public, ensure_ascii=False)
    assert raw["members"][0]["description"] == value.members[0].description

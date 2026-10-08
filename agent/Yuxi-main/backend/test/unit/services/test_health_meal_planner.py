"""基础配餐的手算oracle、结构边界与模型最终输出约束。"""

from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from yuxi.agents.toolkits.meal_planner import preview_meal_plan, search_meal_plan_recipes
from yuxi.services.health_meal_plan_service import calculate_meal_plan, planner_final_result
from yuxi.services.health_meal_plan_types import MealPlanSpec, MealPlanSwap
from yuxi.services.health_vision_types import HealthVisionError


def synthetic_recipe():
    """固定每百克合成数据，避免引用真实营养或临床材料。"""
    food_id, recipe_id = str(uuid4()), str(uuid4())
    nutrients = {"energy_kcal": "100", "protein_g": "10", "fat_g": "2", "carbohydrate_g": "20", "sodium_mg": "50"}
    return SimpleNamespace(
        id=recipe_id,
        name="合成菜谱",
        yield_grams=Decimal(200),
        nutrients=nutrients,
        ingredients=[
            {"food": {"id": food_id, "name": "合成原料", "nutrients": nutrients}, "grams": "200", "role": "food"}
        ],
        cooking_state="合成熟制",
        source="synthetic-source",
        license="synthetic-license",
        edition="synthetic-edition",
        dataset_version="synthetic-v1",
    )


def spec_input(recipe_id):
    """三餐计划量依次为50、100、150克，不是个人推荐量。"""
    return {
        "plan_date": "2026-10-06",
        "meals": [
            {"meal_type": kind, "dishes": [{"recipe_version_id": recipe_id, "grams": str(grams)}]}
            for kind, grams in zip(("breakfast", "lunch", "dinner"), (50, 100, 150))
        ],
    }


def test_three_meals_match_manual_arithmetic_and_declared_boundaries():
    """手算300克产生300kcal，不把草稿标为个体审核方案。"""
    recipe = synthetic_recipe()
    result = calculate_meal_plan(MealPlanSpec.model_validate(spec_input(recipe.id)), {recipe.id: recipe}, {})
    assert [m["nutrition"]["totals"]["energy_kcal"] for m in result["meals"]] == ["50.00", "100.00", "150.00"]
    assert result["nutrition"]["totals"] == {
        "energy_kcal": "300.00",
        "protein_g": "30.00",
        "fat_g": "6.00",
        "carbohydrate_g": "60.00",
        "sodium_mg": "150.00",
    }
    assert [m["dishes"][0]["ingredients"][0]["planned_grams"] for m in result["meals"]] == ["50", "100", "150"]
    assert result["nutrition"]["complete"] is True and result["nutrition"]["estimated"] is True
    assert result["personalized"] is False and result["personal_target"] is None
    assert result["adoption_available"] is False and result["purchase_available"] is False
    assert result["profile_owner"] == "健康档案服务" and result["profile_status"] == "not_ready"


def test_missing_portion_and_nutrient_are_not_zero_or_known_totals():
    """一种缺失不能被其他餐次掩盖为完整全天摄入。"""
    recipe = synthetic_recipe()
    value = spec_input(recipe.id)
    value["meals"][0]["dishes"][0]["grams"] = None
    result = calculate_meal_plan(MealPlanSpec.model_validate(value), {recipe.id: recipe}, {})
    assert result["nutrition"]["totals"]["energy_kcal"] is None
    assert result["nutrition"]["complete"] is False
    assert result["meals"][0]["dishes"][0]["planned_grams"] is None
    recipe.ingredients[0]["food"]["nutrients"]["sodium_mg"] = None
    result = calculate_meal_plan(MealPlanSpec.model_validate(spec_input(recipe.id)), {recipe.id: recipe}, {})
    assert result["nutrition"]["totals"]["energy_kcal"] == "300.00"
    assert result["nutrition"]["totals"]["sodium_mg"] is None


@pytest.mark.parametrize("change", ["duplicate", "extra_member", "nutrition", "negative", "both_portions", "infinite"])
def test_plan_rejects_ambiguous_or_fabricated_input(change):
    """协议拒绝伪造成员、营养、重复餐次和无效份量。"""
    value = spec_input(str(uuid4()))
    if change == "duplicate":
        value["meals"][1]["meal_type"] = "breakfast"
    elif change == "extra_member":
        value["member_id"] = str(uuid4())
    elif change == "nutrition":
        value["meals"][0]["dishes"][0]["energy_kcal"] = "10"
    elif change == "both_portions":
        value["meals"][0]["dishes"][0].update(portion_reference_id=str(uuid4()), portion_count="1")
    else:
        value["meals"][0]["dishes"][0]["grams"] = "-1" if change == "negative" else "Infinity"
    with pytest.raises(ValidationError):
        MealPlanSpec.model_validate(value)


def test_invalid_recipe_and_portion_mapping_fail_in_calculation():
    """存在份量参考也不能跨菜谱使用。"""
    recipe = synthetic_recipe()
    with pytest.raises(HealthVisionError, match="recipe_not_found"):
        calculate_meal_plan(MealPlanSpec.model_validate(spec_input(recipe.id)), {}, {})
    value = spec_input(recipe.id)
    portion_id = str(uuid4())
    value["meals"][0]["dishes"][0].update(grams=None, portion_reference_id=portion_id, portion_count="2")
    portion = SimpleNamespace(id=portion_id, recipe_version_id=str(uuid4()), grams_per_unit=Decimal(80))
    with pytest.raises(HealthVisionError, match="portion_mapping_mismatch"):
        calculate_meal_plan(MealPlanSpec.model_validate(value), {recipe.id: recipe}, {portion_id: portion})


def test_recipe_tool_schemas_hide_injected_identity_and_swap_is_strict():
    """模型只选菜谱及计划量，无法提供actor或运行身份。"""
    assert set(search_meal_plan_recipes.tool_call_schema.model_json_schema()["properties"]) == {"query"}
    assert set(preview_meal_plan.tool_call_schema.model_json_schema()["properties"]) == {"plan_date", "meals"}
    with pytest.raises(ValidationError):
        MealPlanSwap.model_validate(
            {
                "version": True,
                "client_request_id": str(uuid4()),
                "meal_type": "lunch",
                "dish_index": 0,
                "replacement": {"recipe_version_id": str(uuid4())},
                "reason": "换菜",
            }
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "text",
    [
        '{"energy_kcal":10}',
        '{"preview_id":"bad"}',
        "可直接购买",
        "{}",
        '{"questions":["" ]}',
        '{"questions":["需要哪天？"],"personalized":true}',
    ],
)
async def test_model_free_text_and_fabricated_final_values_fail(text):
    """最终结果必须来自回执，格式非法时不访问PG。"""
    with pytest.raises(HealthVisionError, match="planner_output_invalid"):
        await planner_final_result(None, text)

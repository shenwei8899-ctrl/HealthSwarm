"""家庭逐人份量与覆盖范围的独立手算和非法输入。"""

from copy import deepcopy
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from test.unit.services.test_health_meal_planner import synthetic_recipe
from test.unit.services.test_health_quality import profile_payload, rules_payload, FOOD
from test.unit.services.test_health_personal_targets import target_formula
from yuxi.services.health_family_meal_plan import calculate_family_meal_plan
from yuxi.services.health_family_meal_plan_types import FamilyMealPlanSpec, plan_member_ids
from yuxi.services.health_quality_service import quality_snapshot
from yuxi.services.health_quality_types import QualityRules
from yuxi.services.health_vision_types import NUTRIENTS, HealthVisionError


def family_spec(recipe_id, first, second):
    """A三餐50/100/150克，B仅早餐60克，家庭总量360克。"""
    return {
        "kind": "family",
        "plan_date": "2026-10-07",
        "meals": [
            {
                "meal_type": meal,
                "participant_ids": [first, second] if meal == "breakfast" else [first],
                "dishes": [
                    {
                        "recipe_version_id": recipe_id,
                        "member_portions": [{"member_id": first, "grams": str(grams)}]
                        + ([{"member_id": second, "grams": "60"}] if meal == "breakfast" else []),
                    }
                ],
            }
            for meal, grams in zip(("breakfast", "lunch", "dinner"), (50, 100, 150))
        ],
    }


def meal_shares():
    """合成批准三餐比例0.2/0.3/0.5，不作为生产配餐口径。"""
    return {
        meal: {code: share for code in NUTRIENTS}
        for meal, share in zip(("breakfast", "lunch", "dinner"), ("0.2", "0.3", "0.5"))
    }


def family_context():
    """质量检查直接使用分开的五项手算数值，不用受测计算器产生oracle。"""
    rules = {**rules_payload(), "meal_target_shares": meal_shares(), "personal_targets": [target_formula()]}
    profile = {
        **profile_payload(),
        "sex_code": "synthetic_sex",
        "weight_kg": "54",
        "activity_code": "synthetic_activity",
    }
    return {
        "sources": {},
        "rules": {"status": "ready", "payload": rules},
        "profiles": {member: {"status": "ready", "payload": deepcopy(profile)} for member in ("a", "b")},
        "member_ingredients": {
            member: {FOOD: {"content_hash": "a" * 64, "source_current": True}} for member in ("a", "b")
        },
        "plan_snapshot": {
            "nutrition": {"totals": {"energy_kcal": "360"}},
            "members": {
                "a": {
                    "nutrition": {"totals": dict(zip(NUTRIENTS, ("300", "30", "6", "60", "150")))},
                    "covered_meals": ["breakfast", "lunch", "dinner"],
                },
                "b": {
                    "nutrition": {"totals": dict(zip(NUTRIENTS, ("60", "6", "1.2", "12", "30")))},
                    "covered_meals": ["breakfast"],
                },
            },
        },
    }


def test_allocations_cover_only_participating_meals_and_preserve_common_dish_index():
    """A300和B60由明确份量产生，家庭360不均分成180。"""
    recipe = synthetic_recipe()
    first, second = str(uuid4()), str(uuid4())
    spec = FamilyMealPlanSpec.model_validate(family_spec(recipe.id, first, second))
    result = calculate_family_meal_plan(spec, {recipe.id: recipe}, {})
    assert result["scope"] == "family_recipe_draft" and result["personalized"] is False
    assert result["members"][first]["nutrition"]["totals"] == dict(
        zip(NUTRIENTS, ("300.00", "30.00", "6.00", "60.00", "150.00"))
    )
    assert result["members"][second]["nutrition"]["totals"] == dict(
        zip(NUTRIENTS, ("60.00", "6.00", "1.20", "12.00", "30.00"))
    )
    assert result["members"][second]["covered_meals"] == ["breakfast"]
    assert result["members"][second]["full_day_covered"] is False
    assert [Decimal(m["nutrition"]["totals"]["energy_kcal"]) for m in result["meals"]] == [110, 100, 150]
    assert Decimal(result["nutrition"]["totals"]["energy_kcal"]) == 360
    value = family_spec(recipe.id, first, second)
    breakfast = value["meals"][0]
    breakfast["dishes"][0]["member_portions"] = [{"member_id": first, "grams": "50"}]
    breakfast["dishes"].append(
        {"recipe_version_id": recipe.id, "member_portions": [{"member_id": second, "grams": "60"}]}
    )
    result = calculate_family_meal_plan(FamilyMealPlanSpec.model_validate(value), {recipe.id: recipe}, {})
    assert result["members"][second]["meals"][0]["dishes"][0]["family_dish_index"] == 1


def test_unknown_and_reference_portions_remain_member_specific():
    """参考单位属于单一菜谱；B缺量不改变A，家庭总量未知。"""
    recipe = synthetic_recipe()
    first, second, reference = str(uuid4()), str(uuid4()), str(uuid4())
    value = family_spec(recipe.id, first, second)
    allocation = next(p for p in value["meals"][0]["dishes"][0]["member_portions"] if p["member_id"] == second)
    allocation["grams"] = None
    result = calculate_family_meal_plan(FamilyMealPlanSpec.model_validate(value), {recipe.id: recipe}, {})
    assert result["members"][first]["nutrition"]["totals"]["energy_kcal"] == "300.00"
    assert result["members"][second]["nutrition"]["totals"]["energy_kcal"] is None
    assert result["nutrition"]["totals"]["energy_kcal"] is None
    allocation.update(portion_reference_id=reference, portion_count="2")
    portion = SimpleNamespace(
        id=reference,
        recipe_version_id=recipe.id,
        food_id=None,
        grams_per_unit=Decimal(30),
        dataset_version="synthetic-v1",
        unit_label="合成份",
        source="synthetic",
        license="synthetic",
        edition="synthetic",
        applicable_scope="synthetic",
    )
    result = calculate_family_meal_plan(
        FamilyMealPlanSpec.model_validate(value), {recipe.id: recipe}, {reference: portion}
    )
    assert result["members"][second]["nutrition"]["totals"]["energy_kcal"] == "60.00"
    portion.recipe_version_id = str(uuid4())
    with pytest.raises(HealthVisionError, match="portion_mapping_mismatch"):
        calculate_family_meal_plan(FamilyMealPlanSpec.model_validate(value), {recipe.id: recipe}, {reference: portion})


@pytest.mark.parametrize(
    "change",
    [
        "duplicate_participant",
        "duplicate_allocation",
        "outside_member",
        "unallocated",
        "duplicate_meal",
        "negative",
        "forged_nutrition",
        "too_many_members",
    ],
)
def test_family_inputs_reject_ambiguous_allocation_and_fabrication(change):
    """解析边界拒绝重复、餐外成员、未分配成员及伪造结果。"""
    value = family_spec(str(uuid4()), str(uuid4()), str(uuid4()))
    meal = value["meals"][0]
    if change == "duplicate_participant":
        meal["participant_ids"].append(meal["participant_ids"][0])
    elif change == "duplicate_allocation":
        meal["dishes"][0]["member_portions"].append(deepcopy(meal["dishes"][0]["member_portions"][0]))
    elif change == "outside_member":
        meal["dishes"][0]["member_portions"][1]["member_id"] = str(uuid4())
    elif change == "unallocated":
        meal["participant_ids"].append(str(uuid4()))
    elif change == "duplicate_meal":
        value["meals"][1]["meal_type"] = "breakfast"
    elif change == "negative":
        meal["dishes"][0]["member_portions"][0]["grams"] = "-1"
    elif change == "forged_nutrition":
        meal["dishes"][0]["member_portions"][0]["nutrition"] = {}
    else:
        for index, meal in enumerate(value["meals"]):
            ids = [str(uuid4()) for _ in range(8)]
            meal["participant_ids"] = ids
            meal["dishes"][0]["member_portions"] = [{"member_id": member, "grams": "1"} for member in ids]
    with pytest.raises(ValidationError):
        FamilyMealPlanSpec.model_validate(value)


def test_anchor_and_canonical_order_require_actual_participation():
    """入口成员必须实际参加，输入重排不改变归一化份量。"""
    first, second = str(uuid4()), str(uuid4())
    value = family_spec(str(uuid4()), first, second)
    assert plan_member_ids(first, value) == sorted([first, second])
    with pytest.raises(HealthVisionError, match="plan_member_required"):
        plan_member_ids(str(uuid4()), value)
    original = FamilyMealPlanSpec.model_validate(value).model_dump(mode="json")
    value["meals"].reverse()
    value["meals"][-1]["participant_ids"].reverse()
    value["meals"][-1]["dishes"][0]["member_portions"].reverse()
    assert FamilyMealPlanSpec.model_validate(value).model_dump(mode="json") == original


def test_family_quality_uses_individual_targets_and_explicit_partial_coverage():
    """A300/B60均满足各自范围，360家庭总量不作个人目标比较。"""
    result = quality_snapshot(family_context())
    assert result["scope"] == "family_saved_plan" and result["safety_check"]["status"] == "passed"
    assert result["safety_check"]["members"]["b"]["coverage"] == {
        "covered_meals": ["breakfast"],
        "full_day_covered": False,
        "range_scope": "participating_meals",
    }
    current = family_context()
    current["profiles"]["b"]["payload"]["weight_kg"] = "60"
    result = quality_snapshot(current)
    assert result["safety_check"]["members"]["a"]["status"] == "passed"
    assert result["safety_check"]["status"] == "conflict"
    assert any(
        c["member_id"] == "b" and c["path"] == "nutrition.energy_kcal" for c in result["safety_check"]["conflicts"]
    )


@pytest.mark.parametrize("missing", ["shares", "profile", "portion"])
def test_unknown_second_member_cannot_be_hidden_by_primary_member(missing):
    """批准分餐范围、档案、份量任何一项缺失保持未知。"""
    current = family_context()
    if missing == "shares":
        del current["rules"]["payload"]["meal_target_shares"]
    elif missing == "profile":
        current["profiles"]["b"] = {"status": "not_ready", "reason": "missing", "payload": None}
    else:
        current["plan_snapshot"]["members"]["b"]["nutrition"]["totals"]["protein_g"] = None
    result = quality_snapshot(current)["safety_check"]
    assert result["members"]["a"]["status"] == "passed" and result["status"] == "unknown"
    assert result["missing"] and all(item["member_id"] == "b" for item in result["missing"])


def test_restriction_checks_apply_to_foods_allocated_to_each_member():
    """A不吃B的食物时不误报，B明确过敏仍为家庭冲突。"""
    current = family_context()
    second_food = str(uuid4())
    current["rules"]["payload"]["ingredient_classifications"].append(
        {**current["rules"]["payload"]["ingredient_classifications"][0], "food_id": second_food, "allergen_codes": []}
    )
    current["member_ingredients"]["a"] = {second_food: {"content_hash": "a" * 64, "source_current": True}}
    current["profiles"]["a"]["payload"]["allergies"] = {"state": "specified", "codes": ["synthetic_allergen"]}
    assert quality_snapshot(current)["safety_check"]["status"] == "passed"
    current["profiles"]["b"]["payload"]["allergies"] = {"state": "specified", "codes": ["synthetic_allergen"]}
    result = quality_snapshot(current)["safety_check"]
    assert result["status"] == "conflict" and result["conflicts"][0]["member_id"] == "b"


def test_zero_meal_share_cannot_erase_incompatible_daily_medical_bounds():
    """钠100..200与医嘱300..400无交集，早餐比例零也不能通过。"""
    current = family_context()
    rules = current["rules"]["payload"]
    del rules["personal_targets"]
    rules["doctor_requirement_rules"] = [
        {
            "code": "contra",
            "excluded_food_ids": [],
            "excluded_food_categories": [],
            "daily_bounds": {"sodium_mg": {"minimum": "300", "maximum": "400"}},
        }
    ]
    current["profiles"]["b"]["payload"]["doctor_requirements"] = {"state": "specified", "codes": ["contra"]}
    for meal, share in zip(("breakfast", "lunch", "dinner"), ("0", "0.5", "0.5")):
        rules["meal_target_shares"][meal]["sodium_mg"] = share
    current["plan_snapshot"]["members"]["b"]["nutrition"]["totals"]["sodium_mg"] = "0"
    result = quality_snapshot(current)["safety_check"]
    assert result["members"]["a"]["status"] == "passed" and result["members"]["b"]["status"] == "conflict"
    assert {
        "member_id": "b",
        "path": "nutrition.sodium_mg",
        "code": "doctor_requirements_conflict",
        "reason": "多条批准医嘱无法同时满足，须专业复核",
    } in result["conflicts"]


def test_two_meal_coverage_uses_each_nutrient_approved_share_sum():
    """午晚能量0.8/蛋白0.5份额，240kcal与15g合格，蛋白21g不合格。"""
    current = family_context()
    snapshot = current["plan_snapshot"]["members"]["b"]
    snapshot["covered_meals"] = ["lunch", "dinner"]
    snapshot["nutrition"]["totals"] = dict(zip(NUTRIENTS, ("240", "15", "4.8", "48", "120")))
    for meal, share in zip(("breakfast", "lunch", "dinner"), ("0.5", "0.2", "0.3")):
        current["rules"]["payload"]["meal_target_shares"][meal]["protein_g"] = share
    result = quality_snapshot(current)["safety_check"]
    assert result["status"] == "passed"
    snapshot["nutrition"]["totals"]["protein_g"] = "21"
    result = quality_snapshot(current)["safety_check"]
    assert result["status"] == "conflict" and any(
        c["member_id"] == "b" and c["path"] == "nutrition.protein_g" for c in result["conflicts"]
    )


@pytest.mark.parametrize("change", ["missing_meal", "missing_nutrient", "wrong_sum", "extra_nutrient", "negative"])
def test_approved_shares_are_complete_and_sum_to_one_per_nutrient(change):
    """不接受缺餐、缺营养、负数或总量不一致的批准分配。"""
    value = {**rules_payload(), "meal_target_shares": meal_shares()}
    shares = value["meal_target_shares"]
    if change == "missing_meal":
        del shares["dinner"]
    elif change == "missing_nutrient":
        del shares["breakfast"]["fat_g"]
    elif change == "extra_nutrient":
        shares["breakfast"]["other"] = "0.2"
    else:
        shares["breakfast"]["fat_g"] = "-0.2" if change == "negative" else "0.3"
    with pytest.raises(ValidationError):
        QualityRules.model_validate(value)

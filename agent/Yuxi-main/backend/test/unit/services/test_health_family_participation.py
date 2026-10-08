"""家庭参与调整的非法协议、菜位边界及独立营养对照。"""

from copy import deepcopy
from uuid import uuid4

import pytest
from pydantic import ValidationError

from test.unit.services.test_health_family_meal_plan import family_spec
from test.unit.services.test_health_meal_planner import synthetic_recipe
from yuxi.services.health_family_meal_plan import calculate_family_meal_plan
from yuxi.services.health_family_meal_plan_types import FamilyMealPlanSpec, FamilyParticipationSelection
from yuxi.services.health_family_participation_service import apply_family_allocations
from yuxi.services.health_vision_types import HealthVisionError


def participation_body(spec, profiles):
    """明确原三餐菜位，不在调整协议中复制菜谱或营养。"""
    return {
        "version": 1,
        "rule_code": "synthetic-participation",
        "rule_version": 1,
        "profile_versions": profiles,
        "allocations": [
            {
                "meal_type": meal["meal_type"],
                "participant_ids": meal["participant_ids"],
                "dishes": [
                    {"dish_index": index, "member_portions": dish["member_portions"]}
                    for index, dish in enumerate(meal["dishes"])
                ],
            }
            for meal in spec["meals"]
        ],
    }


def fixture_body():
    """使用独立发布配方与三个成员标识。"""
    recipe = synthetic_recipe()
    a, b, c = [str(uuid4()) for _ in range(3)]
    raw = family_spec(recipe.id, a, b)
    return recipe, a, b, c, raw, participation_body(deepcopy(raw), {a: 1, b: 1})


def test_member_changes_recompute_individual_coverage_preserve_recipes_and_original():
    """A310、B仅晚餐150、C仅午餐90，家庭550，不默认均分。"""
    recipe, a, b, c, raw, body = fixture_body()
    body["profile_versions"][c] = 1
    for meal, members, amounts in zip(body["allocations"], [[a], [a, c], [a, b]], [[60], [100, 90], [150, 150]]):
        meal["participant_ids"] = members
        meal["dishes"][0]["member_portions"] = [
            {"member_id": mid, "grams": str(grams)} for mid, grams in zip(members, amounts)
        ]
    original = FamilyMealPlanSpec.model_validate(raw)
    before = original.model_dump(mode="json")
    data = FamilyParticipationSelection.model_validate(body)
    trial = apply_family_allocations(a, original, data.allocations)
    calculated = calculate_family_meal_plan(trial, {recipe.id: recipe}, {})
    assert [calculated["members"][mid]["nutrition"]["totals"]["energy_kcal"] for mid in (a, b, c)] == [
        "310.00",
        "150.00",
        "90.00",
    ]
    assert calculated["nutrition"]["totals"]["energy_kcal"] == "550.00"
    assert calculated["members"][b]["covered_meals"] == ["dinner"]
    assert calculated["members"][c]["covered_meals"] == ["lunch"]
    assert trial.plan_date == original.plan_date
    assert [str(d.recipe_version_id) for m in trial.meals for d in m.dishes] == [recipe.id] * 3
    assert original.model_dump(mode="json") == before


@pytest.mark.parametrize("fault", ["extra_slot", "missing_slot", "anchor_removed", "unchanged"])
def test_existing_slot_and_anchor_guards(fault):
    """调整不能隐式增删菜、移除入口成员或制造空修订。"""
    _, a, b, _, raw, body = fixture_body()
    if fault == "missing_slot":
        raw["meals"][0]["dishes"].append(deepcopy(raw["meals"][0]["dishes"][0]))
    elif fault == "extra_slot":
        body["allocations"][0]["dishes"].append({**deepcopy(body["allocations"][0]["dishes"][0]), "dish_index": 1})
    elif fault == "anchor_removed":
        for meal in body["allocations"]:
            meal["participant_ids"] = [b]
            meal["dishes"][0]["member_portions"] = [{"member_id": b, "grams": "100"}]
    data = FamilyParticipationSelection.model_validate(body)
    with pytest.raises(HealthVisionError) as error:
        apply_family_allocations(a, FamilyMealPlanSpec.model_validate(raw), data.allocations)
    assert (
        error.value.code
        == {
            "extra_slot": "allocation_slots_conflict",
            "missing_slot": "allocation_slots_conflict",
            "anchor_removed": "plan_member_required",
            "unchanged": "participation_unchanged",
        }[fault]
    )


@pytest.mark.parametrize(
    "fault",
    [
        "duplicate_meal",
        "duplicate_slot",
        "duplicate_member",
        "duplicate_participant",
        "unallocated_participant",
        "outside_participant",
        "recipe",
        "date",
        "nutrition",
        "approval",
        "bool_version",
        "string_profile_version",
    ],
)
def test_untrusted_allocation_protocol_rejects_ambiguous_or_authoritative_fields(fault):
    """重复分配与服务器专属字段在HTTP/模型输入边界拒绝。"""
    recipe, a, _, c, _, body = fixture_body()
    meal = body["allocations"][0]
    if fault == "duplicate_meal":
        body["allocations"][1]["meal_type"] = "breakfast"
    elif fault == "duplicate_slot":
        meal["dishes"].append(deepcopy(meal["dishes"][0]))
    elif fault == "duplicate_member":
        meal["dishes"][0]["member_portions"].append(deepcopy(meal["dishes"][0]["member_portions"][0]))
    elif fault == "duplicate_participant":
        meal["participant_ids"].append(a)
    elif fault == "unallocated_participant":
        meal["participant_ids"].append(c)
    elif fault == "outside_participant":
        meal["dishes"][0]["member_portions"].append({"member_id": c, "grams": "60"})
    elif fault == "recipe":
        meal["dishes"][0]["recipe_version_id"] = recipe.id
    elif fault == "date":
        body["plan_date"] = "2026-10-08"
    elif fault == "nutrition":
        body["nutrition"] = {"energy_kcal": 0}
    elif fault == "approval":
        body["professional_review"] = "approved"
    elif fault == "bool_version":
        body["version"] = True
    else:
        body["profile_versions"][a] = "1"
    with pytest.raises(ValidationError):
        FamilyParticipationSelection.model_validate(body)

"""家庭安全槽位的独立手算与第二成员负向约束。"""

from copy import deepcopy
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from test.unit.services.test_health_family_meal_plan import family_context, family_spec
from test.unit.services.test_health_meal_planner import synthetic_recipe
from yuxi.services.health_family_meal_plan import calculate_family_meal_plan
from yuxi.services.health_family_meal_plan_types import FamilyMealPlanSpec, FamilySafeRegenerationInput
from yuxi.services.health_family_safe_plan_service import family_dish_choices, check_family_trial, family_dish_nutrition
from yuxi.services.health_quality_types import QualityRules
from yuxi.services.health_vision_types import NUTRIENTS


def fixtures():
    """100与110合成菜，A早餐50g/B60g；所有规则都显式批准。"""
    first, second = str(uuid4()), str(uuid4())
    old, new = synthetic_recipe(), synthetic_recipe()
    new.nutrients["energy_kcal"] = "110"
    context = family_context()
    context["profiles"] = {first: context["profiles"]["a"], second: context["profiles"]["b"]}
    rules = context["rules"]["payload"]
    rules["personal_targets"][0]["nutrient_ranges"]["energy_kcal"].update(
        minimum_per_energy="0.8", maximum_per_energy="1.2"
    )
    refs, foods = {}, {}
    rules["ingredient_classifications"] = []
    for recipe in (old, new):
        fid = recipe.ingredients[0]["food"]["id"]
        refs[recipe.id] = "a" * 64
        foods[recipe.id] = {fid: {"content_hash": "b" * 64, "source_current": True}}
        rules["ingredient_classifications"].append(
            {
                "food_id": fid,
                "food_hash": "b" * 64,
                "complete": True,
                "allergen_codes": [],
                "intolerance_codes": [],
                "food_categories": [],
            }
        )
    rules["meal_swap"] = {
        "recipe_classifications": [
            {
                "recipe_version_id": r.id,
                "recipe_hash": refs[r.id],
                "dish_type_code": "synthetic",
                "allowed_meal_types": ["breakfast", "lunch", "dinner"],
            }
            for r in (old, new)
        ],
        "maximum_nutrient_differences": {code: "50" if code == "energy_kcal" else "0" for code in NUTRIENTS},
    }
    spec = FamilyMealPlanSpec.model_validate(family_spec(old.id, first, second))
    recipes = {r.id: r for r in (old, new)}
    context.update(
        sources={"recipes": {old.id: refs[old.id]}}, plan_snapshot=calculate_family_meal_plan(spec, recipes, {})
    )
    return first, second, spec, context, recipes, foods, refs, old, new


def choices(values):
    """只调用纯候选计算，所有期望数值独立写出。"""
    _, _, spec, current, recipes, foods, refs, _, _ = values
    return family_dish_choices(
        spec, current, 0, 0, recipes, {}, foods, refs, QualityRules.model_validate(current["rules"]["payload"])
    )


def test_member_differences_and_family_trial_are_independent():
    """A5、B6、家庭增加11；保持50/60克和其他餐次。"""
    values = fixtures()
    first, second, spec, current, recipes, foods, refs, _, new = values
    _, _, dish, differences = next(c for c in choices(values) if c[1] == new.id)
    assert Decimal(differences[first]["energy_kcal"]) == 5
    assert Decimal(differences[second]["energy_kcal"]) == 6
    assert {str(p.member_id): p.grams for p in dish.member_portions} == {first: Decimal(50), second: Decimal(60)}
    trial = spec.model_copy(deep=True)
    trial.meals[0].dishes[0] = dish
    snapshot = calculate_family_meal_plan(trial, recipes, {})
    assert Decimal(snapshot["nutrition"]["totals"]["energy_kcal"]) == 371
    assert Decimal(snapshot["members"][first]["nutrition"]["totals"]["energy_kcal"]) == 305
    assert Decimal(snapshot["members"][second]["nutrition"]["totals"]["energy_kcal"]) == 66
    assert trial.meals[1:] == spec.meals[1:]
    check, sources = check_family_trial(current, trial, snapshot, foods, refs)
    assert check["status"] == "passed" and set(check["members"]) == {first, second}
    assert set(sources["recipes"]) == set(recipes)


def test_second_member_difference_cannot_be_hidden_by_first():
    """上限5时A通过但B增加6，整道菜必须拒绝。"""
    values = fixtures()
    values[3]["rules"]["payload"]["meal_swap"]["maximum_nutrient_differences"]["energy_kcal"] = "5"
    assert values[-1].id not in {c[1] for c in choices(values)}


@pytest.mark.parametrize("broken", ["second_allergy", "hash", "type", "meal", "food_source", "food_unknown"])
def test_candidate_source_and_actual_consumer_guards(broken):
    """每个批准条款与食品来源分别制造明确失败。"""
    values = fixtures()
    _, second, _, current, _, foods, refs, _, new = values
    rules = current["rules"]["payload"]
    classification = rules["meal_swap"]["recipe_classifications"][1]
    if broken == "second_allergy":
        current["profiles"][second]["payload"]["allergies"] = {"state": "specified", "codes": ["synthetic_allergen"]}
        rules["ingredient_classifications"][1]["allergen_codes"] = ["synthetic_allergen"]
    elif broken == "hash":
        refs[new.id] = "f" * 64
    elif broken == "type":
        classification["dish_type_code"] = "other"
    elif broken == "meal":
        classification["allowed_meal_types"] = ["dinner"]
    elif broken == "food_source":
        next(iter(foods[new.id].values()))["source_current"] = False
    else:
        rules["ingredient_classifications"].pop()
    assert new.id not in {c[1] for c in choices(values)}


def test_nonconsumer_allergy_and_subset_index_remain_distinct():
    """B只吃共同菜位1，对菜位0的过敏不影响A候选。"""
    values = fixtures()
    first, second, spec, current, recipes, foods, refs, old, new = values
    original = spec.meals[0].dishes[0]
    second_portion = next(p for p in original.member_portions if str(p.member_id) == second)
    original.member_portions = [p for p in original.member_portions if str(p.member_id) == first]
    spec.meals[0].dishes.append(original.model_copy(update={"member_portions": [second_portion]}))
    current["plan_snapshot"] = calculate_family_meal_plan(spec, recipes, {})
    current["profiles"][second]["payload"]["allergies"] = {"state": "specified", "codes": ["synthetic_allergen"]}
    current["rules"]["payload"]["ingredient_classifications"][1]["allergen_codes"] = ["synthetic_allergen"]
    assert new.id in {c[1] for c in choices(values)}
    assert set(family_dish_nutrition(current["plan_snapshot"], "breakfast", 0)) == {first}
    assert set(family_dish_nutrition(current["plan_snapshot"], "breakfast", 1)) == {second}
    assert family_dish_nutrition(current["plan_snapshot"], "breakfast", 1)[second]["recipe_version_id"] == old.id


def test_all_member_target_check_rejects_second_member_even_when_first_passes():
    """A310在250..350内，B72超过早餐上限70，家庭候选不能通过。"""
    first, second, spec, current, recipes, foods, refs, _, new = fixtures()
    new.nutrients["energy_kcal"] = "120"
    trial = spec.model_copy(deep=True)
    trial.meals[0].dishes[0].recipe_version_id = new.id
    snapshot = calculate_family_meal_plan(trial, recipes, {})
    check, _ = check_family_trial(current, trial, snapshot, foods, refs)
    assert Decimal(snapshot["members"][first]["nutrition"]["totals"]["energy_kcal"]) == 310
    assert Decimal(snapshot["members"][second]["nutrition"]["totals"]["energy_kcal"]) == 72
    assert check["members"][first]["status"] == "passed" and check["members"][second]["status"] == "conflict"
    assert check["status"] == "conflict"


def test_member_reference_portion_becomes_actual_grams_only_for_replaced_dish():
    """B明确参考30g×2=60g，换菜不把A50g均分给B。"""
    first, second, spec, current, recipes, foods, refs, old, new = fixtures()
    reference = uuid4()
    portion = next(p for p in spec.meals[0].dishes[0].member_portions if str(p.member_id) == second)
    portion.grams, portion.portion_reference_id, portion.portion_count = None, reference, Decimal(2)
    published = SimpleNamespace(
        id=str(reference),
        recipe_version_id=old.id,
        food_id=None,
        grams_per_unit=Decimal(30),
        unit_label="synthetic",
        source="synthetic",
        license="synthetic",
        edition="v1",
        dataset_version="v1",
        applicable_scope="synthetic",
    )
    current["plan_snapshot"] = calculate_family_meal_plan(spec, recipes, {str(reference): published})
    selected = family_dish_choices(
        spec,
        current,
        0,
        0,
        recipes,
        {str(reference): published},
        foods,
        refs,
        QualityRules.model_validate(current["rules"]["payload"]),
    )
    replacement = next(c[2] for c in selected if c[1] == new.id)
    assert {str(p.member_id): p.grams for p in replacement.member_portions} == {first: Decimal(50), second: Decimal(60)}
    assert all(p.portion_reference_id is None and p.portion_count is None for p in replacement.member_portions)
    assert (
        next(p for p in spec.meals[0].dishes[0].member_portions if str(p.member_id) == second).portion_reference_id
        == reference
    )


@pytest.mark.parametrize(
    "update",
    [
        {"profile_versions": {}},
        {"profile_versions": {str(uuid4()): True}},
        {"profile_versions": {str(uuid4()): "1"}},
        {"profile_versions": {"invalid": 1}},
        {"plan_spec": {}},
        {"professional_review": "approved"},
        {"preview_hash": "invalid"},
    ],
)
def test_family_confirmation_rejects_forged_content_and_versions(update):
    """边界只接收完整版本选择和摘要，布尔/字符串版本不能冒充确认。"""
    body = {
        "version": 1,
        "rule_code": "synthetic",
        "rule_version": 1,
        "profile_versions": {str(uuid4()): 1},
        "client_request_id": str(uuid4()),
        "preview_hash": "a" * 64,
    }
    with pytest.raises(ValidationError):
        FamilySafeRegenerationInput.model_validate({**body, **deepcopy(update)})

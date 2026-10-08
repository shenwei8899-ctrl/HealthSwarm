"""初始三餐的独立手算、全员限制与有限搜索负控。"""

from copy import deepcopy
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from test.unit.services.test_health_meal_planner import synthetic_recipe
from test.unit.services.test_health_quality import profile_payload, rules_payload
from test.unit.services.test_health_family_meal_plan import meal_shares
from yuxi.services.health_initial_meal_generation import generate_initial_plan
from yuxi.services.health_initial_meal_plan_types import InitialPlanSelection
from yuxi.services.health_quality_types import QualityRules
from yuxi.services.health_meal_plan_service import initial_generation_snapshot
from yuxi.services.health_vision_types import HealthVisionError


def initial_fixture(*, family=False):
    """100/110每百克，批准全天330；B仅早餐目标66，与旧餐单无关。"""
    first, second = str(uuid4()), str(uuid4())
    old, new = synthetic_recipe(), synthetic_recipe()
    old.id, new.id = str(UUID(int=1)), str(UUID(int=2))
    new.nutrients["energy_kcal"] = "110"
    recipes = {r.id: r for r in (old, new)}
    rules = rules_payload()
    rules["daily_bounds"]["energy_kcal"] = {"minimum": "330", "maximum": "330"}
    rules["meal_target_shares"] = meal_shares()
    rules["ingredient_classifications"] = [
        {
            "food_id": r.ingredients[0]["food"]["id"],
            "food_hash": "a" * 64,
            "complete": True,
            "allergen_codes": [],
            "intolerance_codes": [],
            "food_categories": [],
        }
        for r in recipes.values()
    ]
    rules["meal_generation"] = {
        "recipe_classifications": [
            {
                "recipe_version_id": r.id,
                "recipe_hash": "b" * 64,
                "dish_type_code": "synthetic",
                "allowed_meal_types": ["breakfast", "lunch", "dinner"],
            }
            for r in recipes.values()
        ],
        "profile_menus": [
            {
                "population_code": "synthetic_adult",
                "condition_codes": [],
                "meals": [
                    {
                        "meal_type": m,
                        "dishes": [
                            {
                                "dish_type_code": "synthetic",
                                "grams_options": ["60", "100"] if m == "breakfast" else ["100"],
                            }
                        ],
                    }
                    for m in ("breakfast", "lunch", "dinner")
                ],
            }
        ],
    }
    selected = {
        "kind": "family" if family else "single",
        "plan_date": "2026-10-08",
        "rule_code": "synthetic",
        "rule_version": 1,
        "profile_versions": {first: 1, **({second: 1} if family else {})},
        "meals": [
            {"meal_type": m, "participant_ids": [first, second] if family and m == "breakfast" else [first]}
            for m in ("breakfast", "lunch", "dinner")
        ],
    }
    context = {
        "member_id": first,
        "sources": {},
        "profiles": {
            mid: {"status": "ready", "payload": deepcopy(profile_payload())} for mid in selected["profile_versions"]
        },
        "rules": {"status": "ready", "payload": rules},
    }
    foods = {
        r.id: {r.ingredients[0]["food"]["id"]: {"content_hash": "a" * 64, "source_current": True}}
        for r in recipes.values()
    }
    return (
        InitialPlanSelection.model_validate(selected),
        context,
        recipes,
        foods,
        {rid: "b" * 64 for rid in recipes},
        first,
        second,
    )


def generated(values, **kwargs):
    """调用当前纯生成Owner，oracle由各测试独立写出。"""
    return generate_initial_plan(*values[:5], **kwargs)


@pytest.mark.parametrize("family", [False, True])
def test_initial_result_separates_confirmed_projection_from_full_profile(family):
    """公开结果说明真实依据，完整建档及专业采用仍未交付。"""
    values = initial_fixture(family=family)
    result = generated(values)
    result["sources"] = {
        "profiles": {str(mid): {"version": 1} for mid in values[0].profile_versions},
        "rules": {"version": 7},
    }
    canonical = deepcopy(result["plan_snapshot"])
    current = initial_generation_snapshot(canonical, result, current=True)
    assert current["profile_status"] == "ready" and current["rules_status"] == "ready"
    assert current["full_health_profile_available"] is False
    assert current["confirmed_rule_version"] == 7 and current["professional_review"] == "not_reviewed"
    assert current["adoption_available"] is False and current["purchase_available"] is False
    assert current["nutrition"] == canonical["nutrition"] and result["plan_snapshot"] == canonical
    stored = {**canonical, "generation_origin": result}
    history = initial_generation_snapshot(stored, result)
    assert history["profile_status"] == "requires_current_validation"
    assert history["rules_status"] == "requires_current_validation" and "generation_origin" not in history
    assert history["generation_sources"] == result["sources"]


@pytest.mark.parametrize("bad", [None, {"sources": {"profiles": [], "rules": {"version": 1}}, "safety_check": {}}])
def test_malformed_persisted_origin_has_stable_failure(bad):
    """持久化依据形状无效时明确失效，不返回就绪或内部异常。"""
    with pytest.raises(HealthVisionError, match="source_invalidated"):
        initial_generation_snapshot({"nutrition": {}}, bad)


def test_initial_single_generates_without_old_plan_and_searches_complete_day():
    """所有110菜且每餐100克才满足330，不能用第一道默认菜凑数。"""
    values = initial_fixture()
    result = generated(values)
    assert result["status"] == "ready" and result["safety_check"]["status"] == "passed"
    assert result["plan_snapshot"]["nutrition"]["totals"] == {
        "energy_kcal": "330.00",
        "protein_g": "30.00",
        "fat_g": "6.00",
        "carbohydrate_g": "60.00",
        "sodium_mg": "150.00",
    }
    assert [m["dishes"][0]["recipe_version_id"] for m in result["plan_spec"]["meals"]] == [str(UUID(int=2))] * 3
    assert [Decimal(m["dishes"][0]["grams"]) for m in result["plan_spec"]["meals"]] == [100] * 3
    assert result["professional_review"] == "not_a_professional_decision" and result["adoption_available"] is False
    assert result["search"]["examined"] > 1 and generated(values) == result


def test_family_portions_share_recipe_but_each_member_meets_covered_target():
    """A330+B早餐66=396；早餐A100g/B60g不取平均。"""
    values = initial_fixture(family=True)
    result = generated(values)
    first, second = values[-2:]
    assert result["status"] == "ready" and result["safety_check"]["status"] == "passed"
    snapshot = result["plan_snapshot"]
    assert snapshot["nutrition"]["totals"]["energy_kcal"] == "396.00"
    assert snapshot["members"][first]["nutrition"]["totals"]["energy_kcal"] == "330.00"
    assert snapshot["members"][second]["nutrition"]["totals"]["energy_kcal"] == "66.00"
    assert snapshot["members"][second]["covered_meals"] == ["breakfast"]
    dish = result["plan_spec"]["meals"][0]["dishes"][0]
    assert {p["member_id"]: Decimal(p["grams"]) for p in dish["member_portions"]} == {
        first: Decimal(100),
        second: Decimal(60),
    }


@pytest.mark.parametrize(
    "broken",
    [
        "missing_rules",
        "missing_profile",
        "no_generation",
        "unknown_allergy",
        "no_shares",
        "bad_hash",
        "unknown_nutrient",
        "stale_food",
        "second_allergy",
        "impossible_target",
    ],
)
def test_dependency_and_second_member_failures_never_return_ready_plan(broken):
    """每项单独撤掉有效依据，不能保存不合格结果。"""
    values = initial_fixture(family=True)
    _, current, recipes, foods, refs, _, second = values
    rules = current["rules"]["payload"]
    if broken == "missing_rules":
        current["rules"]["status"] = "not_ready"
    elif broken == "missing_profile":
        current["profiles"][second]["status"] = "not_ready"
    elif broken == "no_generation":
        rules.pop("meal_generation")
    elif broken == "unknown_allergy":
        current["profiles"][second]["payload"]["allergies"] = {"state": "unknown", "codes": []}
    elif broken == "no_shares":
        rules.pop("meal_target_shares")
    elif broken == "bad_hash":
        refs.update({rid: "f" * 64 for rid in refs})
    elif broken == "unknown_nutrient":
        for r in recipes.values():
            r.nutrients["sodium_mg"] = None
    elif broken == "stale_food":
        for fs in foods.values():
            next(iter(fs.values()))["source_current"] = False
    elif broken == "second_allergy":
        current["profiles"][second]["payload"]["allergies"] = {"state": "specified", "codes": ["synthetic_allergen"]}
        for c in rules["ingredient_classifications"]:
            c["allergen_codes"] = ["synthetic_allergen"]
    else:
        rules["daily_bounds"]["energy_kcal"] = {"minimum": "333", "maximum": "333"}
    result = generated(values)
    assert result["status"] == "not_ready" and result["reason"] and "plan_spec" not in result


def test_search_budget_is_distinct_from_exhausted_no_solution():
    """有限预算不能把可行330方案判成无解；恢复预算可找到。"""
    values = initial_fixture()
    result = generated(values, max_states=1)
    assert result["reason"] == "search_limit_reached" and result["search"]["limited"]
    assert generated(values)["status"] == "ready"
    values[1]["rules"]["payload"]["daily_bounds"]["energy_kcal"] = {"minimum": "333", "maximum": "333"}
    result = generated(values)
    assert result["reason"] == "no_eligible_plan" and result["search"]["limited"] is False


@pytest.mark.parametrize(
    "bad", ["nutrition", "missing_member", "duplicate_meal", "single_two", "duplicate_participant"]
)
def test_generation_input_refuses_model_facts_or_ambiguous_member_selection(bad):
    """真实parser拒绝营养字段、缺成员和不完整三餐。"""
    values = initial_fixture(family=True)
    payload = values[0].model_dump(mode="json")
    if bad == "nutrition":
        payload["nutrition"] = {"energy_kcal": 1}
    elif bad == "missing_member":
        payload["profile_versions"].pop(values[-1])
    elif bad == "duplicate_meal":
        payload["meals"][1]["meal_type"] = "breakfast"
    elif bad == "single_two":
        payload["kind"] = "single"
    else:
        payload["meals"][0]["participant_ids"].append(values[-1])
    with pytest.raises(ValidationError):
        InitialPlanSelection.model_validate(payload)


@pytest.mark.parametrize(
    "bad",
    ["duplicate_recipe", "duplicate_grams", "zero_grams", "missing_meal", "unknown_type", "unsupported_population"],
)
def test_generation_rules_require_explicit_and_unambiguous_approved_catalog(bad):
    """批准资料不能留下代码默认的份量、餐次或目录。"""
    rules = initial_fixture()[1]["rules"]["payload"]
    g = rules["meal_generation"]
    menu = g["profile_menus"][0]
    if bad == "duplicate_recipe":
        g["recipe_classifications"].append(deepcopy(g["recipe_classifications"][0]))
    elif bad == "duplicate_grams":
        menu["meals"][0]["dishes"][0]["grams_options"] = ["100", "100"]
    elif bad == "zero_grams":
        menu["meals"][0]["dishes"][0]["grams_options"] = ["0"]
    elif bad == "missing_meal":
        menu["meals"].pop()
    elif bad == "unknown_type":
        menu["meals"][0]["dishes"][0]["dish_type_code"] = "unknown"
    else:
        menu["population_code"] = "other"
    with pytest.raises(ValidationError):
        QualityRules.model_validate(rules)

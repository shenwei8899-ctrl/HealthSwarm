"""营养准备情况的纯计算，不创建方案或作出专业批准。"""

from yuxi.services.health_personal_targets import calculate_personal_targets
from yuxi.services.health_quality_checks import evaluate_plan_quality
from yuxi.services.health_quality_types import ProfileProjection, QualityRules
from yuxi.services.health_vision_types import NUTRIENTS


def nutrition_readiness(profile, rules, recipes, ingredients, references):
    """复用目标和质量计算，仅将可满足菜单菜位的候选标为可尝试预览。"""
    fields = ("id", "version", "content_hash", "status", "reason")
    result = {
        "scope": "current_single_member_dependencies",
        "sources": {
            name: {key: value[key] for key in fields} for name, value in (("profile", profile), ("rules", rules))
        },
        "personal_targets": {"status": "not_ready", "reason": "confirmed_profile_or_approved_rules_required"},
        "meal_preview": {"status": "not_ready", "reason": "confirmed_profile_or_approved_rules_required"},
        "missing": [],
        "conflicts": [],
        "professional_review": "not_a_professional_decision",
        "plan_saved": False,
    }
    if profile["status"] != "ready" or rules["status"] != "ready":
        return result
    p = ProfileProjection.model_validate(profile["payload"])
    r = QualityRules.model_validate(rules["payload"])
    targets = calculate_personal_targets(
        p,
        r,
        weight_source_missing=bool(profile["attestation"].get("family_profile_source"))
        and not profile["attestation"].get("weight_measurement_source"),
    )
    result["personal_targets"] = {key: targets[key] for key in ("status", "reason")}
    # 零值只用于检查器的占位输入，营养范围与配料缺失由各候选另行检查。
    baseline = evaluate_plan_quality({"nutrition": {"totals": dict.fromkeys(NUTRIENTS, "0")}}, profile, rules, {})
    for field in ("missing", "conflicts"):
        result[field] = [
            item
            for item in baseline[field]
            if item["path"].startswith("profile.") or item.get("code") == "doctor_requirements_conflict"
        ]
    if result["missing"] or result["conflicts"]:
        result["meal_preview"]["reason"] = (
            "approved_target_ranges_conflict"
            if any(item.get("code") == "doctor_requirements_conflict" for item in result["conflicts"])
            else "complete_supported_profile_required"
        )
        return result
    if r.meal_generation is None:
        result["meal_preview"]["reason"] = "initial_catalog_not_approved"
        return result
    menu = next(
        (
            entry
            for entry in r.meal_generation.profile_menus
            if entry.population_code == p.population_code and set(entry.condition_codes) == set(p.conditions.codes)
        ),
        None,
    )
    if menu is None:
        result["meal_preview"]["reason"] = "profile_menu_not_approved"
        return result
    available = set()
    rejected = []
    for item in r.meal_generation.recipe_classifications:
        rid = str(item.recipe_version_id)
        recipe = recipes.get(rid)
        if recipe is None or references.get(rid) != item.recipe_hash:
            rejected.append({"recipe_version_id": rid, "reason": "recipe_source_missing_or_changed"})
            continue
        check = evaluate_plan_quality(
            {"nutrition": {"totals": recipe.nutrients}}, profile, rules, ingredients.get(rid, {})
        )
        missing = check["missing"]
        conflicts = [
            value
            for value in check["conflicts"]
            if not value["path"].startswith("nutrition.") or value.get("code") == "doctor_requirements_conflict"
        ]
        if missing or conflicts:
            rejected.append({"recipe_version_id": rid, "reason": "recipe_incomplete_or_restricted"})
            continue
        available.update((meal, item.dish_type_code) for meal in item.allowed_meal_types)
    missing_slots = [
        {"meal_type": meal.meal_type, "dish_type_code": dish.dish_type_code}
        for meal in menu.meals
        for dish in meal.dishes
        if (meal.meal_type, dish.dish_type_code) not in available
    ]
    result["meal_preview"] = {
        "status": "not_ready" if missing_slots else "can_attempt_preview",
        "reason": "eligible_recipe_missing" if missing_slots else None,
        "missing_slots": missing_slots,
        "rejected_candidates": rejected,
        "combination_checked": False,
    }
    return result

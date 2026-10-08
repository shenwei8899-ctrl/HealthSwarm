"""批准布局和份量驱动初始三餐，不继承既有餐单。"""

from decimal import Decimal

from yuxi.services.health_family_meal_plan import calculate_family_meal_plan
from yuxi.services.health_family_meal_plan_types import FamilyMealPlanSpec
from yuxi.services.health_family_safe_plan_service import check_family_trial
from yuxi.services.health_meal_plan_service import calculate_meal_plan
from yuxi.services.health_meal_plan_types import MealPlanSpec
from yuxi.services.health_quality_checks import evaluate_plan_quality
from yuxi.services.health_quality_types import ProfileProjection, QualityRules
from yuxi.services.health_safe_plan_regeneration_service import MAX_SEARCH_STATES, search_plan_combinations
from yuxi.services.health_vision_types import NUTRIENTS


def generate_initial_plan(selection, current, recipes, by_recipe, refs, *, max_states=MAX_SEARCH_STATES):
    """有界搜索共同菜谱与独立份量，只有全部实际参加者通过才返回方案。"""
    result = {
        "status": "not_ready",
        "reason": None,
        "scope": "initial_family_plan" if selection.kind == "family" else "initial_single_plan",
        "sources": current["sources"],
        "professional_review": "not_a_professional_decision",
        "adoption_available": False,
        "purchase_available": False,
        "units": NUTRIENTS,
    }
    if current["rules"]["status"] != "ready" or any(p["status"] != "ready" for p in current["profiles"].values()):
        return {**result, "reason": "confirmed_profiles_or_approved_rules_required"}
    rules = QualityRules.model_validate(current["rules"]["payload"])
    if rules.meal_generation is None:
        return {**result, "reason": "initial_generation_rules_not_approved"}
    parsed_rules = {**current["rules"], "payload": rules}
    profiles = {
        mid: {**p, "payload": ProfileProjection.model_validate(p["payload"])} for mid, p in current["profiles"].items()
    }
    zero = {"nutrition": {"totals": {code: "0" for code in NUTRIENTS}}}
    menus, preflight = {}, {}
    for mid, profile in profiles.items():
        covered = [m.meal_type for m in selection.meals if mid in {str(p) for p in m.participant_ids}]
        check = evaluate_plan_quality(zero, profile, parsed_rules, {}, covered_meals=covered)
        # 此处只判档案与批准约束是否完整；营养量由实际组合复算后判断。
        if any(not m["path"].startswith("ingredients") for m in check["missing"]) or any(
            not c["path"].startswith("nutrition.") or c["code"] == "doctor_requirements_conflict"
            for c in check["conflicts"]
        ):
            preflight[mid] = check
        p = profile["payload"]
        menu = next(
            (
                m
                for m in rules.meal_generation.profile_menus
                if m.population_code == p.population_code and m.condition_codes == p.conditions.codes
            ),
            None,
        )
        if menu is None:
            return {**result, "reason": "profile_menu_not_approved", "member_id": mid}
        menus[mid] = menu
    if preflight:
        return {**result, "reason": "complete_profiles_and_coverage_rules_required", "member_checks": preflight}

    catalog = {str(c.recipe_version_id): c for c in rules.meal_generation.recipe_classifications}
    options, layout = [], []
    for meal in selection.meals:
        members = sorted(str(p) for p in meal.participant_ids)
        dish_rules = {}
        for mid in members:
            menu = next(m for m in menus[mid].meals if m.meal_type == meal.meal_type)
            for dish in menu.dishes:
                dish_rules.setdefault(dish.dish_type_code, {})[mid] = dish
        if len(dish_rules) > 10:
            return {**result, "reason": "family_layout_exceeds_supported_dishes", "meal_type": meal.meal_type}
        slots = []
        for dish_type, member_rules in sorted(dish_rules.items()):
            candidates = []
            for rid, classification in sorted(catalog.items()):
                if (
                    rid not in recipes
                    or classification.recipe_hash != refs.get(rid)
                    or classification.dish_type_code != dish_type
                    or meal.meal_type not in classification.allowed_meal_types
                    or any(recipes[rid].nutrients.get(code) is None for code in NUTRIENTS)
                ):
                    continue
                eligible = True
                for mid in member_rules:
                    check = evaluate_plan_quality(zero, profiles[mid], parsed_rules, by_recipe[rid])
                    if check["missing"] or any(not c["path"].startswith("nutrition.") for c in check["conflicts"]):
                        eligible = False
                        break
                if eligible:
                    candidates.append((Decimal(0), rid, rid))
            if not candidates:
                return {
                    **result,
                    "reason": "no_eligible_dish_candidates",
                    "meal_type": meal.meal_type,
                    "dish_type_code": dish_type,
                }
            recipe_index = len(options)
            options.append(candidates)
            portions = {}
            for mid, dish in sorted(member_rules.items()):
                portions[mid] = len(options)
                options.append([(Decimal(0), str(g), g) for g in dish.grams_options])
            slots.append((recipe_index, portions))
        layout.append((meal, slots))

    def evaluate(indices):
        """每个完整组合独立复算逐人成品营养与当前配料来源。"""
        meals = []
        for meal, slots in layout:
            dishes = []
            for recipe_index, portion_indexes in slots:
                rid = options[recipe_index][indices[recipe_index]][2]
                portions = [
                    {"member_id": mid, "grams": options[i][indices[i]][2]} for mid, i in portion_indexes.items()
                ]
                dishes.append(
                    {"recipe_version_id": rid, "member_portions": portions}
                    if selection.kind == "family"
                    else {"recipe_version_id": rid, "grams": portions[0]["grams"]}
                )
            meals.append(
                {"meal_type": meal.meal_type, "participant_ids": meal.participant_ids, "dishes": dishes}
                if selection.kind == "family"
                else {"meal_type": meal.meal_type, "dishes": dishes}
            )
        values = {"plan_date": selection.plan_date, "meals": meals}
        if selection.kind == "family":
            spec = FamilyMealPlanSpec.model_validate({"kind": "family", **values})
            snapshot = calculate_family_meal_plan(spec, recipes, {})
            check, sources = check_family_trial(current, spec, snapshot, by_recipe, refs)
        else:
            spec = MealPlanSpec.model_validate(values)
            snapshot = calculate_meal_plan(spec, recipes, {})
            used = {str(d.recipe_version_id) for m in spec.meals for d in m.dishes}
            ingredients = {}
            for rid in used:
                for fid, food in by_recipe[rid].items():
                    entry = ingredients.setdefault(fid, dict(food))
                    entry["source_current"] = entry["source_current"] and food["source_current"]
            check = evaluate_plan_quality(snapshot, next(iter(profiles.values())), parsed_rules, ingredients)
            sources = {"recipes": {rid: refs[rid] for rid in used}, "ingredients": ingredients}
        return (spec, snapshot, check, sources) if check["status"] == "passed" else None

    selected, search = search_plan_combinations(options, evaluate, max_states=max_states)
    if selected is None:
        return {
            **result,
            "search": search,
            "reason": "search_limit_reached" if search["limited"] else "no_eligible_plan",
        }
    spec, snapshot, check, sources = selected
    return {
        **result,
        "status": "ready",
        "search": search,
        "plan_spec": spec.model_dump(mode="json"),
        "plan_snapshot": snapshot,
        "safety_check": check,
        "candidate_sources": sources,
    }

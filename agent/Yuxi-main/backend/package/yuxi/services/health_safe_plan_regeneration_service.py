"""批准目录驱动的整份三餐组合搜索与用户确认保存。"""

from decimal import Decimal
from heapq import heappop, heappush
from types import SimpleNamespace
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import ValidationError

from yuxi.repositories.health_meal_plan_repository import HealthMealPlanRepository
from yuxi.repositories.health_quality_repository import HealthQualityRepository
from yuxi.services.health_meal_plan_service import calculate_meal_plan, plan_result
from yuxi.services.health_meal_plan_types import MealPlanSpec, PlannedDish
from yuxi.services.health_meal_plan_service import require_single_member_plan
from yuxi.services.health_nutrition_service import input_fingerprint
from yuxi.services.health_quality_checks import evaluate_plan_quality
from yuxi.services.health_quality_service import quality_context_in_session, quality_result, review_case_in_session
from yuxi.services.health_quality_types import QualityRules, ProfileProjection
from yuxi.services.health_safe_meal_swap_service import nutrient_differences, save_safe_revision_in_session
from yuxi.services.health_vision_types import HealthVisionError, NUTRIENTS
from yuxi.storage.postgres.manager import pg_manager

# HTTP搜索的运行预算，不是医学或营养阈值；达到上限不声明无解。
MAX_SEARCH_STATES = 10000


async def preview_safe_regeneration(uid, plan_id, data):
    """整份预览不写入修订、饮食、记忆或专业决定。"""
    async with pg_manager.get_async_session_context() as session:
        _, result = await regeneration_in_session(session, uid, plan_id, data)
        return result


async def regenerate_meal_plan(uid, plan_id, data):
    """重新生成并比对用户确认摘要，一次提交完整三餐修订。"""
    fingerprint = input_fingerprint(
        {"operation": "safe_regeneration", "plan_id": plan_id, **data.model_dump(mode="json")}
    )
    check_key = str(uuid5(NAMESPACE_URL, f"health-safe-regeneration:{uid}:{data.client_request_id}"))
    async with pg_manager.get_async_session_context() as session:
        repo, quality = HealthMealPlanRepository(session), HealthQualityRepository(session)
        await quality.lock_request(uid, check_key)
        await repo.lock_request(uid, str(data.client_request_id))
        plan = await repo.plan(uid, plan_id, lock=True)
        require_single_member_plan(plan)
        receipt = await repo.receipt(uid, str(data.client_request_id))
        if receipt is not None:
            if receipt.fingerprint != fingerprint:
                raise HealthVisionError("request_conflict", "同一请求不能改变重生成对象或内容", 409)
            check = await quality.check_receipt(uid, check_key)
            case = await quality.case_for_check(check.id)
            case, _, _ = await review_case_in_session(session, uid, case.id)
            return {
                **plan_result(plan),
                "applied_version": receipt.version,
                "quality_check": {**quality_result(check), "current": case.status != "invalidated"},
            }
        spec, preview = await regeneration_in_session(session, uid, plan_id, data)
        if preview["status"] != "ready":
            raise HealthVisionError("safe_regeneration_unavailable", "当前依赖或搜索结果不能提供安全整份餐单", 409)
        if preview["preview_hash"] != data.preview_hash:
            raise HealthVisionError("preview_changed", "整份预览或来源已变化，请重新确认", 409)
        return await save_safe_revision_in_session(
            session, uid, plan, spec, preview["plan_snapshot"], data, fingerprint, check_key, "用户按批准规则重生成三餐"
        )


async def regeneration_in_session(session, uid, plan_id, data):
    """全槽位候选共同搜索，只有全天检查通过才产生可确认预览。"""
    quality, repo = HealthQualityRepository(session), HealthMealPlanRepository(session)
    current = await quality_context_in_session(
        session, uid, SimpleNamespace(plan_id=plan_id, plan_version=data.version, rule_code=data.rule_code)
    )
    plan = await repo.plan(uid, plan_id)
    require_single_member_plan(plan)
    spec = MealPlanSpec.model_validate(plan.spec)
    result = {
        "status": "not_ready",
        "reason": None,
        "sources": current["sources"],
        "professional_review": "not_a_professional_decision",
        "units": NUTRIENTS,
    }
    if current["profile"]["status"] != "ready" or current["rules"]["status"] != "ready":
        result["reason"] = "confirmed_profile_or_approved_rules_required"
        return spec, result
    if current["profile"]["version"] != data.profile_version or current["rules"]["version"] != data.rule_version:
        raise HealthVisionError("source_version_conflict", "档案或规则版本已变化，请刷新重生成预览", 409)
    rules = QualityRules.model_validate(current["rules"]["payload"])
    profile = {**current["profile"], "payload": ProfileProjection.model_validate(current["profile"]["payload"])}
    parsed_rules = {**current["rules"], "payload": rules}
    if rules.meal_swap is None:
        result["reason"] = "swap_rules_not_approved"
        return spec, result
    base_check = evaluate_plan_quality(current["plan_snapshot"], profile, parsed_rules, current["ingredients"])
    if any(not m["path"].startswith("ingredients") for m in base_check["missing"]) or any(
        c["path"].startswith("profile.") or c["code"] == "doctor_requirements_conflict" for c in base_check["conflicts"]
    ):
        result.update(reason="complete_profile_and_daily_rules_required", safety_check=base_check)
        return spec, result
    catalog = {str(c.recipe_version_id): c for c in rules.meal_swap.recipe_classifications}
    old_ids = {str(d.recipe_version_id) for m in spec.meals for d in m.dishes}
    ids = set(catalog) | old_ids
    recipes = await repo.recipes(ids)
    by_recipe, refs = await quality.recipe_sources_by_recipe(ids)
    portions = await repo.portions(
        {str(d.portion_reference_id) for m in spec.meals for d in m.dishes if d.portion_reference_id}
    )
    food_classes = {str(c.food_id): c for c in rules.ingredient_classifications}
    allowed = {}
    for rid, classification in catalog.items():
        if rid not in recipes or classification.recipe_hash != refs.get(rid):
            continue
        check = evaluate_plan_quality(
            current["plan_snapshot"], profile, parsed_rules, by_recipe[rid], classifications=food_classes
        )
        if not check["missing"] and not any(not c["path"].startswith("nutrition.") for c in check["conflicts"]):
            allowed[rid] = classification
    slots, options = [], []
    for meal_index, meal in enumerate(spec.meals):
        for dish_index, dish in enumerate(meal.dishes):
            original = current["plan_snapshot"]["meals"][meal_index]["dishes"][dish_index]
            old_id = str(dish.recipe_version_id)
            old_class = catalog.get(old_id)
            if old_class is None or old_class.recipe_hash != current["sources"]["recipes"].get(old_id):
                result["reason"] = "current_recipe_classification_not_approved"
                return spec, result
            try:
                grams = Decimal(original["planned_grams"])
                replacement = PlannedDish(recipe_version_id=old_id, grams=grams)
            except (ValidationError, TypeError):
                result["reason"] = "known_supported_portion_required"
                return spec, result
            choices = []
            for rid, classification in allowed.items():
                if (
                    classification.dish_type_code != old_class.dish_type_code
                    or meal.meal_type not in classification.allowed_meal_types
                ):
                    continue
                trial = spec.model_copy(deep=True)
                candidate = replacement.model_copy(update={"recipe_version_id": UUID(rid)})
                trial.meals[meal_index].dishes[dish_index] = candidate
                snapshot = calculate_meal_plan(trial, recipes, portions)
                nutrition = snapshot["meals"][meal_index]["dishes"][dish_index]["nutrition"]
                differences = nutrient_differences(
                    original["nutrition"], nutrition, rules.meal_swap.maximum_nutrient_differences
                )
                if differences is not None:
                    choices.append((differences[1], rid, dish if rid == old_id else candidate))
            if not choices:
                result.update(reason="no_eligible_dish_candidates", meal_type=meal.meal_type, dish_index=dish_index)
                return spec, result
            choices.sort(key=lambda choice: (choice[0], choice[1]))
            slots.append((meal_index, dish_index))
            options.append(choices)

    def evaluate(indices):
        trial = spec.model_copy(deep=True)
        for (mi, di), choices, index in zip(slots, options, indices):
            trial.meals[mi].dishes[di] = choices[index][2]
        if trial == spec:
            return None
        snapshot = calculate_meal_plan(trial, recipes, portions)
        used_ids = {str(d.recipe_version_id) for m in trial.meals for d in m.dishes}
        ingredients = {}
        for rid in used_ids:
            for fid, food in by_recipe[rid].items():
                entry = ingredients.setdefault(fid, dict(food))
                entry["source_current"] = entry["source_current"] and food["source_current"]
        check = evaluate_plan_quality(snapshot, profile, parsed_rules, ingredients, classifications=food_classes)
        if check["status"] != "passed":
            return None
        return trial, snapshot, check, {"recipes": {rid: refs[rid] for rid in used_ids}, "ingredients": ingredients}

    selected, search = search_plan_combinations(options, evaluate)
    result["search"] = search
    if selected is None:
        result["reason"] = "search_limit_reached" if search["limited"] else "no_eligible_plan"
        return spec, result
    trial, snapshot, check, sources = selected
    confirmed = {
        "spec": trial.model_dump(mode="json"),
        "snapshot": snapshot,
        "sources": result["sources"],
        "candidate_sources": sources,
    }
    result.update(
        status="ready",
        plan_spec=confirmed["spec"],
        plan_snapshot=snapshot,
        safety_check=check,
        candidate_sources=sources,
        preview_hash=input_fingerprint(confirmed),
    )
    return trial, result


def search_plan_combinations(options, evaluate, *, max_states=MAX_SEARCH_STATES):
    """按总差异确定性探索笛卡尔积；预算耗尽与穷尽无解明确区分。"""
    initial = (0,) * len(options)

    def rank(indices):
        return sum((choices[i][0] for choices, i in zip(options, indices)), Decimal(0)), tuple(
            choices[i][1] for choices, i in zip(options, indices)
        )

    queue = [(*rank(initial), initial)]
    seen, examined = {initial}, 0
    while queue:
        _, _, indices = heappop(queue)
        examined += 1
        result = evaluate(indices)
        if result is not None:
            return result, {"examined": examined, "limited": False, "max_states": max_states}
        for position, choices in enumerate(options):
            if indices[position] + 1 >= len(choices):
                continue
            neighbor = indices[:position] + (indices[position] + 1,) + indices[position + 1 :]
            if neighbor in seen:
                continue
            if len(seen) >= max_states:
                return None, {"examined": examined, "limited": True, "max_states": max_states}
            seen.add(neighbor)
            heappush(queue, (*rank(neighbor), neighbor))
    return None, {"examined": examined, "limited": False, "max_states": max_states}

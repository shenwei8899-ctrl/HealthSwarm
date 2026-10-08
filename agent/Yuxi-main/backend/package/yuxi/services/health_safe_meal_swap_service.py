"""单成员批准规则候选及只替换一道菜的安全事务。"""

from copy import deepcopy
from decimal import Decimal
from types import SimpleNamespace
from uuid import NAMESPACE_URL, uuid4, uuid5

from pydantic import ValidationError

from yuxi.repositories.health_meal_plan_repository import HealthMealPlanRepository
from yuxi.repositories.health_quality_repository import HealthQualityRepository
from yuxi.services.health_meal_plan_service import calculate_meal_plan, plan_result
from yuxi.services.health_meal_plan_types import MealPlanSpec, PlannedDish
from yuxi.services.health_meal_plan_service import require_single_member_plan
from yuxi.services.health_nutrition_service import input_fingerprint
from yuxi.services.health_quality_checks import evaluate_plan_quality
from yuxi.services.health_quality_service import (
    check_plan_in_session,
    quality_context_in_session,
    quality_result,
    review_case_in_session,
)
from yuxi.services.health_quality_types import QualityCheckInput, QualityRules, ProfileProjection
from yuxi.services.health_vision_types import HealthVisionError, NUTRIENTS
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_health import HealthMealPlanRevision
from yuxi.utils.datetime_utils import utc_now_naive


async def read_safe_swap_candidates(uid, plan_id, data):
    """读取最多三道当前合格候选，不保存或写入用户喜恶。"""
    async with pg_manager.get_async_session_context() as session:
        _, result = await candidates_in_session(session, uid, plan_id, data)
        return result


async def safe_swap_meal_plan_dish(uid, plan_id, data):
    """重筛当前候选后提交新修订及检查收据，旧批准与采用失效。"""
    fingerprint = input_fingerprint({"operation": "safe_swap", "plan_id": plan_id, **data.model_dump(mode="json")})
    check_key = str(uuid5(NAMESPACE_URL, f"health-safe-swap:{uid}:{data.client_request_id}"))
    async with pg_manager.get_async_session_context() as session:
        repo, quality = HealthMealPlanRepository(session), HealthQualityRepository(session)
        # 与独立质量入口同序：检查请求锁在成员锁之前，后续复用同一检查事务。
        await quality.lock_request(uid, check_key)
        await repo.lock_request(uid, str(data.client_request_id))
        plan = await repo.plan(uid, plan_id, lock=True)
        require_single_member_plan(plan)
        receipt = await repo.receipt(uid, str(data.client_request_id))
        if receipt is not None:
            if receipt.fingerprint != fingerprint:
                raise HealthVisionError("request_conflict", "同一请求不能改变换菜对象或内容", 409)
            check = await quality.check_receipt(uid, check_key)
            case = await quality.case_for_check(check.id)
            case, _, _ = await review_case_in_session(session, uid, case.id)
            return {
                **plan_result(plan),
                "applied_version": receipt.version,
                "quality_check": {**quality_result(check), "current": case.status != "invalidated"},
            }
        spec, candidates = await candidates_in_session(session, uid, plan_id, data)
        selected = next(
            (c for c in candidates["candidates"] if c["recipe_version_id"] == str(data.recipe_version_id)), None
        )
        if selected is None:
            raise HealthVisionError("safe_candidate_required", "请选择当前合格候选，缺依赖或冲突时不能换菜", 409)
        meal = next(m for m in spec.meals if m.meal_type == data.meal_type)
        meal.dishes[data.dish_index] = PlannedDish(
            recipe_version_id=data.recipe_version_id, grams=Decimal(selected["planned_grams"])
        )
        return await save_safe_revision_in_session(
            session, uid, plan, spec, selected["plan_snapshot"], data, fingerprint, check_key, "用户按批准规则换菜"
        )


async def save_safe_revision_in_session(session, uid, plan, spec, snapshot, data, fingerprint, check_key, reason):
    """安全单菜及整份重生成共用修订和末次检查事务，不继承旧专业批准。"""
    quality = HealthQualityRepository(session)
    plan.version += 1
    plan.spec = spec.model_dump(mode="json")
    plan.snapshot = snapshot
    plan.updated_at = utc_now_naive()
    await quality.invalidate(plan_id=plan.id, reason="plan_changed")
    session.add(
        HealthMealPlanRevision(
            id=str(uuid4()),
            plan_id=plan.id,
            actor_uid=uid,
            request_id=str(data.client_request_id),
            fingerprint=fingerprint,
            version=plan.version,
            reason=reason,
            spec=deepcopy(plan.spec),
            snapshot=deepcopy(plan.snapshot),
        )
    )
    await session.flush()
    check = await check_plan_in_session(
        session,
        uid,
        plan.id,
        QualityCheckInput(client_request_id=check_key, version=plan.version, rule_code=data.rule_code),
    )
    if check.snapshot["safety_check"]["status"] != "passed":
        raise HealthVisionError("quality_not_passed", "当前来源不能通过安全复核，原餐单保留", 409)
    return {
        **plan_result(plan),
        "applied_version": plan.version,
        "quality_check": {**quality_result(check), "current": True},
    }


async def candidates_in_session(session, uid, plan_id, data):
    """当前对象和来源持锁，目录批量复算后筛选完整全天安全候选。"""
    quality, repo = HealthQualityRepository(session), HealthMealPlanRepository(session)
    current = await quality_context_in_session(
        session, uid, SimpleNamespace(plan_id=plan_id, plan_version=data.version, rule_code=data.rule_code)
    )
    plan = await repo.plan(uid, plan_id)
    require_single_member_plan(plan)
    spec = MealPlanSpec.model_validate(plan.spec)
    meal = next(m for m in spec.meals if m.meal_type == data.meal_type)
    if data.dish_index >= len(meal.dishes):
        raise HealthVisionError("dish_not_found", "所选餐次没有这道菜", 404)
    result = {
        "status": "not_ready",
        "reason": None,
        "candidates": [],
        "sources": current["sources"],
        "meal_type": data.meal_type,
        "dish_index": data.dish_index,
        "professional_review": "not_a_professional_decision",
        "units": NUTRIENTS,
    }
    if current["profile"]["status"] != "ready" or current["rules"]["status"] != "ready":
        result["reason"] = "confirmed_profile_or_approved_rules_required"
        return spec, result
    if current["profile"]["version"] != data.profile_version or current["rules"]["version"] != data.rule_version:
        raise HealthVisionError("source_version_conflict", "档案或规则版本已变化，请刷新候选", 409)
    rules = QualityRules.model_validate(current["rules"]["payload"])
    if rules.meal_swap is None:
        result["reason"] = "swap_rules_not_approved"
        return spec, result
    parsed_profile = {**current["profile"], "payload": ProfileProjection.model_validate(current["profile"]["payload"])}
    parsed_rules = {**current["rules"], "payload": rules}
    food_classifications = {str(c.food_id): c for c in rules.ingredient_classifications}
    original = next(m for m in current["plan_snapshot"]["meals"] if m["meal_type"] == data.meal_type)["dishes"][
        data.dish_index
    ]
    if original["planned_grams"] is None or any(v is None for v in original["nutrition"].values()):
        result["reason"] = "known_portion_and_nutrition_required"
        return spec, result
    catalog = {str(c.recipe_version_id): c for c in rules.meal_swap.recipe_classifications}
    old_id = original["recipe_version_id"]
    old_class = catalog.get(old_id)
    if old_class is None or old_class.recipe_hash != current["sources"]["recipes"].get(old_id):
        result["reason"] = "current_recipe_classification_not_approved"
        return spec, result
    ids = set(catalog) | {str(d.recipe_version_id) for m in spec.meals for d in m.dishes}
    recipes = await repo.recipes(ids)
    by_recipe, refs = await quality.recipe_sources_by_recipe(ids)
    portion_ids = {str(d.portion_reference_id) for m in spec.meals for d in m.dishes if d.portion_reference_id}
    portions = await repo.portions(portion_ids)
    grams = Decimal(original["planned_grams"])
    try:
        PlannedDish(recipe_version_id=old_id, grams=grams)
    except ValidationError:
        result["reason"] = "portion_outside_supported_swap_range"
        return spec, result
    ranked = []
    for recipe_id, classification in catalog.items():
        if (
            recipe_id == old_id
            or recipe_id not in recipes
            or classification.dish_type_code != old_class.dish_type_code
            or data.meal_type not in classification.allowed_meal_types
            or classification.recipe_hash != refs.get(recipe_id)
        ):
            continue
        trial = spec.model_copy(deep=True)
        next(m for m in trial.meals if m.meal_type == data.meal_type).dishes[data.dish_index] = PlannedDish(
            recipe_version_id=recipe_id, grams=grams
        )
        snapshot = calculate_meal_plan(trial, recipes, portions)
        replacement = next(m for m in snapshot["meals"] if m["meal_type"] == data.meal_type)["dishes"][data.dish_index]
        differences = nutrient_differences(
            original["nutrition"], replacement["nutrition"], rules.meal_swap.maximum_nutrient_differences
        )
        if differences is None:
            continue
        used_ids = {str(d.recipe_version_id) for m in trial.meals for d in m.dishes}
        used_ingredients = {}
        for rid in used_ids:
            for fid, food in by_recipe[rid].items():
                entry = used_ingredients.setdefault(fid, dict(food))
                entry["source_current"] = entry["source_current"] and food["source_current"]
        check = evaluate_plan_quality(
            snapshot, parsed_profile, parsed_rules, used_ingredients, classifications=food_classifications
        )
        if check["status"] != "passed":
            continue
        delta, score = differences
        ranked.append(
            (
                score,
                recipe_id,
                {
                    "recipe_version_id": recipe_id,
                    "name": recipes[recipe_id].name,
                    "dish_type_code": classification.dish_type_code,
                    "planned_grams": str(grams),
                    "nutrition_difference": delta,
                    "plan_snapshot": snapshot,
                    "safety_check": check,
                    "candidate_sources": {
                        "recipes": {rid: refs[rid] for rid in used_ids},
                        "ingredients": used_ingredients,
                    },
                },
            )
        )
        ranked.sort(key=lambda x: (x[0], x[1]))
        del ranked[3:]
    result.update(
        status="ready", candidates=[c for _, _, c in ranked[:3]], reason=None if ranked else "no_eligible_candidates"
    )
    return spec, result


def nutrient_differences(original, replacement, limits):
    """独立按批准绝对差异筛选，零上限不除零，未知不作为相近。"""
    delta, score = {}, Decimal(0)
    for code in NUTRIENTS:
        if original.get(code) is None or replacement.get(code) is None:
            return None
        difference = Decimal(replacement[code]) - Decimal(original[code])
        limit = limits[code]
        if abs(difference) > limit:
            return None
        delta[code] = str(difference)
        if limit:
            score += abs(difference) / limit
    return delta, score

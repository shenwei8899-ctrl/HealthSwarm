"""家庭共餐的逐人安全候选与共同组合重生成。"""

from decimal import Decimal
from types import SimpleNamespace
from uuid import NAMESPACE_URL, uuid5

from pydantic import ValidationError

from yuxi.repositories.health_meal_plan_repository import HealthMealPlanRepository
from yuxi.repositories.health_quality_repository import HealthQualityRepository
from yuxi.services.health_family_meal_plan import calculate_family_meal_plan
from yuxi.services.health_family_meal_plan_types import FamilyMealPlanSpec, FamilyMemberPortion, FamilyPlannedDish
from yuxi.services.health_meal_plan_service import plan_result
from yuxi.services.health_nutrition_service import input_fingerprint
from yuxi.services.health_quality_checks import evaluate_plan_quality
from yuxi.services.health_quality_service import (
    quality_context_in_session,
    quality_snapshot,
    quality_result,
    review_case_in_session,
)
from yuxi.services.health_quality_types import QualityRules
from yuxi.services.health_safe_meal_swap_service import nutrient_differences, save_safe_revision_in_session
from yuxi.services.health_safe_plan_regeneration_service import search_plan_combinations
from yuxi.services.health_vision_types import HealthVisionError, NUTRIENTS
from yuxi.storage.postgres.manager import pg_manager


async def read_family_safe_candidates(uid, plan_id, data):
    """当前来源下返回最多三道逐人合格共同菜品，不写业务事实。"""
    async with pg_manager.get_async_session_context() as session:
        _, result = await family_safe_preview_in_session(session, uid, plan_id, data, swap=True)
        return result


async def preview_family_regeneration(uid, plan_id, data):
    """共同修复三餐的只读预览，预算耗尽不能声称无解。"""
    async with pg_manager.get_async_session_context() as session:
        _, result = await family_safe_preview_in_session(session, uid, plan_id, data, swap=False)
        return result


async def change_family_safe_plan(uid, plan_id, data, *, swap):
    """重新选择当前候选或摘要，修订与末次逐人检查同事务提交。"""
    operation = "family_safe_swap" if swap else "family_safe_regeneration"
    fingerprint = input_fingerprint({"operation": operation, "plan_id": plan_id, **data.model_dump(mode="json")})
    check_key = str(uuid5(NAMESPACE_URL, f"health-{operation}:{uid}:{data.client_request_id}"))
    async with pg_manager.get_async_session_context() as session:
        repo, quality = HealthMealPlanRepository(session), HealthQualityRepository(session)
        await quality.lock_request(uid, check_key)
        await repo.lock_request(uid, str(data.client_request_id))
        receipt = await repo.receipt(uid, str(data.client_request_id))
        plan = await repo.plan(uid, plan_id, lock=receipt is None)
        require_family_plan(plan)
        if receipt is not None:
            if receipt.fingerprint != fingerprint:
                raise HealthVisionError("request_conflict", "同一请求不能改变家庭改版对象或内容", 409)
            await repo.lock_member_change(uid, plan, receipt.spec)
            check = await quality.check_receipt(uid, check_key)
            case = await quality.case_for_check(check.id)
            case, _, _ = await review_case_in_session(session, uid, case.id)
            return {
                **plan_result(plan),
                "applied_version": receipt.version,
                "quality_check": {**quality_result(check), "current": case.status != "invalidated"},
            }
        spec, preview = await family_safe_preview_in_session(session, uid, plan_id, data, swap=swap)
        if swap:
            selected = next(
                (c for c in preview["candidates"] if c["recipe_version_id"] == str(data.recipe_version_id)), None
            )
            if selected is None:
                raise HealthVisionError("safe_candidate_required", "请选择当前逐人检查合格的家庭候选", 409)
            spec = FamilyMealPlanSpec.model_validate(selected["plan_spec"])
            snapshot = selected["plan_snapshot"]
        else:
            if preview["status"] != "ready":
                raise HealthVisionError("safe_regeneration_unavailable", "当前依赖或搜索不能提供安全家庭餐单", 409)
            if preview["preview_hash"] != data.preview_hash:
                raise HealthVisionError("preview_changed", "家庭预览或来源已变化，请重新确认", 409)
            snapshot = preview["plan_snapshot"]
        return await save_safe_revision_in_session(
            session,
            uid,
            plan,
            spec,
            snapshot,
            data,
            fingerprint,
            check_key,
            "用户按批准规则更换家庭菜品" if swap else "用户按批准规则重生成家庭三餐",
        )


async def family_safe_preview_in_session(session, uid, plan_id, data, *, swap):
    """锁定全部成员与规则，以共同槽位搜索逐人份量保持的方案。"""
    repo, quality = HealthMealPlanRepository(session), HealthQualityRepository(session)
    current = await quality_context_in_session(
        session, uid, SimpleNamespace(plan_id=plan_id, plan_version=data.version, rule_code=data.rule_code)
    )
    plan = await repo.plan(uid, plan_id)
    require_family_plan(plan)
    spec = FamilyMealPlanSpec.model_validate(plan.spec)
    result = {
        "status": "not_ready",
        "reason": None,
        "sources": current["sources"],
        "professional_review": "not_a_professional_decision",
        "units": NUTRIENTS,
    }
    if swap:
        result.update(candidates=[], meal_type=data.meal_type, dish_index=data.dish_index)
        mi = next(i for i, m in enumerate(spec.meals) if m.meal_type == data.meal_type)
        if data.dish_index >= len(spec.meals[mi].dishes):
            raise HealthVisionError("dish_not_found", "所选家庭餐次没有这道菜", 404)
        slots = [(mi, data.dish_index)]
    else:
        slots = [(mi, di) for mi, m in enumerate(spec.meals) for di in range(len(m.dishes))]
    if current["rules"]["status"] != "ready" or any(p["status"] != "ready" for p in current["profiles"].values()):
        result["reason"] = "confirmed_profiles_or_approved_rules_required"
        return spec, result
    if current["rules"]["version"] != data.rule_version or {
        str(member): version for member, version in data.profile_versions.items()
    } != {member: profile["version"] for member, profile in current["profiles"].items()}:
        raise HealthVisionError("source_version_conflict", "须确认全部参与者的当前档案和规则版本", 409)
    rules = QualityRules.model_validate(current["rules"]["payload"])
    if rules.meal_swap is None:
        result["reason"] = "swap_rules_not_approved"
        return spec, result
    base = quality_snapshot(current)["safety_check"]
    if any(not item["path"].startswith("ingredients") for item in base["missing"]) or any(
        item["path"].startswith("profile.") or item["code"] == "doctor_requirements_conflict"
        for item in base["conflicts"]
    ):
        result.update(reason="complete_profiles_and_coverage_rules_required", safety_check=base)
        return spec, result
    catalog = {str(c.recipe_version_id): c for c in rules.meal_swap.recipe_classifications}
    ids = set(catalog) | {str(d.recipe_version_id) for m in spec.meals for d in m.dishes}
    recipes = await repo.recipes(ids)
    by_recipe, refs = await quality.recipe_sources_by_recipe(ids)
    portions = await repo.portions(
        {
            str(p.portion_reference_id)
            for m in spec.meals
            for d in m.dishes
            for p in d.member_portions
            if p.portion_reference_id
        }
    )
    options = []
    for mi, di in slots:
        try:
            choices = family_dish_choices(spec, current, mi, di, recipes, portions, by_recipe, refs, rules)
        except (ValidationError, TypeError):
            result["reason"] = "known_supported_member_portions_required"
            return spec, result
        if not choices:
            result.update(reason="no_eligible_dish_candidates", meal_type=spec.meals[mi].meal_type, dish_index=di)
            return spec, result
        options.append(choices)

    def evaluate(indices):
        """完整共同组合必须全部成员通过，不借用原审核结论。"""
        trial = spec.model_copy(deep=True)
        for (mi, di), choices, index in zip(slots, options, indices):
            trial.meals[mi].dishes[di] = choices[index][2]
        if trial == spec:
            return None
        snapshot = calculate_family_meal_plan(trial, recipes, portions)
        check, sources = check_family_trial(current, trial, snapshot, by_recipe, refs)
        return (trial, snapshot, check, sources) if check["status"] == "passed" else None

    if swap:
        candidates = []
        mi, di = slots[0]
        for index, (_, rid, dish, differences) in enumerate(options[0]):
            evaluated = evaluate((index,))
            if evaluated is None:
                continue
            trial, snapshot, check, sources = evaluated
            candidates.append(
                {
                    "recipe_version_id": rid,
                    "name": recipes[rid].name,
                    "dish_type_code": catalog[rid].dish_type_code,
                    "member_portions": [p.model_dump(mode="json") for p in dish.member_portions],
                    "member_nutrition_differences": differences,
                    "plan_spec": trial.model_dump(mode="json"),
                    "plan_snapshot": snapshot,
                    "safety_check": check,
                    "candidate_sources": sources,
                }
            )
            if len(candidates) == 3:
                break
        result.update(status="ready", reason=None if candidates else "no_eligible_candidates", candidates=candidates)
        return spec, result
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


def family_dish_choices(spec, current, meal_index, dish_index, recipes, portions, by_recipe, refs, rules):
    """按实际食用成员独立筛类型、份量差异与配料限制，营养总目标留给组合检查。"""
    meal = spec.meals[meal_index]
    original_dish = meal.dishes[dish_index]
    old_id = str(original_dish.recipe_version_id)
    catalog = {str(c.recipe_version_id): c for c in rules.meal_swap.recipe_classifications}
    old_class = catalog.get(old_id)
    if old_class is None or old_class.recipe_hash != current["sources"]["recipes"].get(old_id):
        return []
    original = family_dish_nutrition(current["plan_snapshot"], meal.meal_type, dish_index)
    member_portions = [
        FamilyMemberPortion(member_id=mid, grams=Decimal(d["planned_grams"])) for mid, d in original.items()
    ]
    choices = []
    for rid, classification in catalog.items():
        if (
            rid not in recipes
            or classification.recipe_hash != refs.get(rid)
            or classification.dish_type_code != old_class.dish_type_code
            or meal.meal_type not in classification.allowed_meal_types
        ):
            continue
        # 只给实际吃此菜的成员筛配料，未食用者的过敏不应阻止该菜。
        if any(
            check["missing"] or any(not c["path"].startswith("nutrition.") for c in check["conflicts"])
            for mid in original
            for check in [
                evaluate_plan_quality(
                    current["plan_snapshot"]["members"][mid],
                    current["profiles"][mid],
                    current["rules"],
                    by_recipe[rid],
                    covered_meals=current["plan_snapshot"]["members"][mid]["covered_meals"],
                )
            ]
        ):
            continue
        replacement = FamilyPlannedDish(recipe_version_id=rid, member_portions=member_portions)
        trial = spec.model_copy(deep=True)
        trial.meals[meal_index].dishes[dish_index] = replacement
        snapshot = calculate_family_meal_plan(trial, recipes, portions)
        nutrition = family_dish_nutrition(snapshot, meal.meal_type, dish_index)
        differences, score = {}, Decimal(0)
        for mid in original:
            delta = nutrient_differences(
                original[mid]["nutrition"], nutrition[mid]["nutrition"], rules.meal_swap.maximum_nutrient_differences
            )
            if delta is None:
                break
            differences[mid], score = delta[0], score + delta[1]
        else:
            choices.append((score, rid, original_dish if rid == old_id else replacement, differences))
    return sorted(choices, key=lambda c: (c[0], c[1]))


def family_dish_nutrition(snapshot, meal_type, dish_index):
    """按家庭菜位取得个人菜品，个人子集索引不能用于共同菜位。"""
    return {
        mid: dish
        for mid, member in snapshot["members"].items()
        for meal in member["meals"]
        if meal["meal_type"] == meal_type
        for dish in meal["dishes"]
        if dish["family_dish_index"] == dish_index
    }


def check_family_trial(current, spec, snapshot, by_recipe, refs):
    """试算只使用实际分配的配料来源，保留逐人检查结果。"""
    member_ingredients, ingredients = {}, {}
    used = {str(d.recipe_version_id) for m in spec.meals for d in m.dishes}
    for mid in snapshot["members"]:
        foods = {}
        for meal in spec.meals:
            for dish in meal.dishes:
                if not any(str(p.member_id) == mid for p in dish.member_portions):
                    continue
                for fid, food in by_recipe[str(dish.recipe_version_id)].items():
                    entry = foods.setdefault(fid, dict(food))
                    entry["source_current"] = entry["source_current"] and food["source_current"]
                    total = ingredients.setdefault(fid, dict(food))
                    total["source_current"] = total["source_current"] and food["source_current"]
        member_ingredients[mid] = foods
    check = quality_snapshot({**current, "plan_snapshot": snapshot, "member_ingredients": member_ingredients})[
        "safety_check"
    ]
    return check, {"recipes": {rid: refs[rid] for rid in used}, "ingredients": ingredients}


def require_family_plan(plan):
    """专用协议仅用于明确家庭对象，避免绕过单成员来源选择。"""
    if plan.spec.get("kind") != "family":
        raise HealthVisionError("family_plan_required", "此入口仅处理家庭餐单", 409)

"""家庭既有菜位的参加成员和份量调整，安全检查与版本提交同一事务。"""

from uuid import NAMESPACE_URL, uuid5

from yuxi.repositories.health_meal_plan_repository import HealthMealPlanRepository
from yuxi.repositories.health_quality_repository import HealthQualityRepository
from yuxi.services.health_family_meal_plan_types import FamilyMealPlanSpec, plan_member_ids
from yuxi.services.health_family_safe_plan_service import check_family_trial, require_family_plan
from yuxi.services.health_meal_plan_service import calculate_in_session, plan_result
from yuxi.services.health_nutrition_service import input_fingerprint
from yuxi.services.health_quality_checks import external_projection
from yuxi.services.health_quality_service import quality_result, review_case_in_session
from yuxi.services.health_safe_meal_swap_service import save_safe_revision_in_session
from yuxi.services.health_vision_types import HealthVisionError, NUTRIENTS
from yuxi.storage.postgres.manager import pg_manager


async def preview_family_participation(uid, plan_id, data):
    """只读试算新参与覆盖，确认前不改原计划、采用或审核。"""
    async with pg_manager.get_async_session_context() as session:
        _, _, result = await participation_preview_in_session(session, uid, plan_id, data)
        return result


async def change_family_participation(uid, plan_id, data):
    """重新试算确认摘要，保存新版本并整体失效旧专业决定和采用。"""
    fingerprint = input_fingerprint(
        {"operation": "family_participation", "plan_id": plan_id, **data.model_dump(mode="json")}
    )
    check_key = str(uuid5(NAMESPACE_URL, f"health-family-participation:{uid}:{data.client_request_id}"))
    async with pg_manager.get_async_session_context() as session:
        repo, quality = HealthMealPlanRepository(session), HealthQualityRepository(session)
        await quality.lock_request(uid, check_key)
        await repo.lock_request(uid, str(data.client_request_id))
        receipt = await repo.receipt(uid, str(data.client_request_id))
        if receipt is not None:
            if receipt.fingerprint != fingerprint:
                raise HealthVisionError("request_conflict", "同一请求不能改变家庭参与调整对象或内容", 409)
            plan = await repo.plan(uid, plan_id)
            await repo.lock_member_change(uid, plan, receipt.spec)
            check = await quality.check_receipt(uid, check_key)
            case = await quality.case_for_check(check.id)
            case, _, _ = await review_case_in_session(session, uid, case.id)
            return {
                **plan_result(plan),
                "applied_version": receipt.version,
                "quality_check": {**quality_result(check), "current": case.status != "invalidated"},
            }
        plan, spec, preview = await participation_preview_in_session(session, uid, plan_id, data)
        if preview["status"] != "ready":
            raise HealthVisionError("participation_not_safe", "参与调整缺少当前来源或存在逐人冲突，原计划保留", 409)
        if preview["preview_hash"] != data.preview_hash:
            raise HealthVisionError("preview_changed", "参与调整内容或来源已变化，请重新确认", 409)
        return await save_safe_revision_in_session(
            session,
            uid,
            plan,
            spec,
            preview["plan_snapshot"],
            data,
            fingerprint,
            check_key,
            data.reason,
        )


def apply_family_allocations(anchor_id, original, allocations):
    """只替换现有菜位的成员分配，保留原日期和菜谱。"""
    spec = original.model_copy(deep=True)
    for meal, allocation in zip(spec.meals, allocations):
        if {d.dish_index for d in allocation.dishes} != set(range(len(meal.dishes))):
            raise HealthVisionError("allocation_slots_conflict", "须明确原餐次所有菜位的分配，不能增删菜", 409)
        meal.participant_ids = allocation.participant_ids
        for dish, assigned in zip(meal.dishes, allocation.dishes):
            dish.member_portions = assigned.member_portions
    spec = FamilyMealPlanSpec.model_validate(spec.model_dump())
    plan_member_ids(anchor_id, spec.model_dump(mode="json"))
    if spec == original:
        raise HealthVisionError("participation_unchanged", "参与关系和份量没有变化，无须新增版本", 409)
    return spec


async def participation_preview_in_session(session, uid, plan_id, data):
    """在全部新旧成员锁与规则来源锁内重算新增成员及覆盖范围。"""
    repo, quality = HealthMealPlanRepository(session), HealthQualityRepository(session)
    plan = await repo.plan(uid, plan_id)
    require_family_plan(plan)
    spec = apply_family_allocations(plan.member_id, FamilyMealPlanSpec.model_validate(plan.spec), data.allocations)
    await repo.lock_member_change(uid, plan, spec.model_dump(mode="json"))
    if plan.version != data.version:
        raise HealthVisionError("version_conflict", "餐单版本已变化，请刷新参与调整", 409)
    original = await calculate_in_session(session, FamilyMealPlanSpec.model_validate(plan.spec))
    calculated_snapshot = {k: v for k, v in plan.snapshot.items() if k != "generation_origin"}
    if input_fingerprint(original) != input_fingerprint(calculated_snapshot):
        raise HealthVisionError("source_invalidated", "原餐单营养来源已变化，请刷新", 410)
    profiles = {
        member_id: external_projection(await quality.profile(member_id), "profile", member_id)
        for member_id in plan_member_ids(plan.member_id, spec.model_dump(mode="json"))
    }
    rules = external_projection(await quality.rules(data.rule_code, lock=True), "rules", data.rule_code)
    snapshot = await calculate_in_session(session, spec)
    ids = {str(d.recipe_version_id) for m in spec.meals for d in m.dishes}
    by_recipe, refs = await quality.recipe_sources_by_recipe(ids)
    if set(refs) != ids:
        raise HealthVisionError("source_invalidated", "家庭菜谱来源无法核对", 410)
    sources = {
        "plan": {
            "id": plan.id,
            "version": plan.version,
            "content_hash": input_fingerprint({"spec": plan.spec, "snapshot": plan.snapshot}),
        },
        "profiles": {
            member_id: {k: profile[k] for k in ("id", "version", "content_hash", "status", "reason")}
            for member_id, profile in profiles.items()
        },
        "rules": {
            "rule_code": data.rule_code,
            **{k: rules[k] for k in ("id", "version", "content_hash", "status", "reason")},
        },
    }
    current = {"sources": sources, "profiles": profiles, "rules": rules}
    check, candidate_sources = check_family_trial(current, spec, snapshot, by_recipe, refs)
    result = {
        "status": "not_ready",
        "reason": "confirmed_profiles_or_approved_rules_required",
        "plan_spec": spec.model_dump(mode="json"),
        "plan_snapshot": snapshot,
        "sources": sources,
        "candidate_sources": candidate_sources,
        "safety_check": check,
        "preview_hash": None,
        "professional_review": "not_a_professional_decision",
        "units": NUTRIENTS,
    }
    if rules["status"] != "ready" or any(p["status"] != "ready" for p in profiles.values()):
        return plan, spec, result
    if rules["version"] != data.rule_version or {str(m): v for m, v in data.profile_versions.items()} != {
        m: p["version"] for m, p in profiles.items()
    }:
        raise HealthVisionError("source_version_conflict", "须确认全部新参与者的当前档案和规则版本", 409)
    if check["status"] != "passed":
        result["reason"] = "member_quality_not_passed"
        return plan, spec, result
    confirmed = {
        "spec": result["plan_spec"],
        "snapshot": snapshot,
        "sources": sources,
        "candidate_sources": candidate_sources,
        "safety_check": check,
    }
    result.update(status="ready", reason=None, preview_hash=input_fingerprint(confirmed))
    return plan, spec, result

"""三餐预览、显式保存和换菜的事务用例。"""

from copy import deepcopy
from datetime import datetime, time
from decimal import Decimal
from uuid import NAMESPACE_URL, uuid4, uuid5
from zoneinfo import ZoneInfo

from pydantic import ValidationError
from sqlalchemy import select

from yuxi.repositories.health_consultation_repository import HealthConsultationRepository, PLANNER_SLUG
from yuxi.repositories.health_meal_plan_repository import HealthMealPlanRepository
from yuxi.repositories.health_vision_repository import HealthVisionRepository
from yuxi.services.health_meal_plan_types import MealPlanSpec, PlannerAnswer
from yuxi.services.health_family_meal_plan_types import FamilyMealPlanSpec, parse_meal_plan_spec
from yuxi.services.health_nutrition_service import calculate_nutrition, input_fingerprint
from yuxi.services.health_vision_types import HealthVisionError, MealItem, MealPayload, NUTRIENTS
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_health import (
    HealthMealPlan,
    HealthMealPlanPreview,
    HealthMealPlanRevision,
    PortionReference,
    RecipeVersion,
)
from yuxi.utils.datetime_utils import format_utc_datetime, utc_now_naive

PLANNER_BOUNDARY = {
    "status": "draft",
    "scope": "single_member_recipe_draft",
    "personalized": False,
    "full_health_profile_available": False,
    "profile_status": "not_ready",
    "profile_owner": "健康档案服务",
    "confirmed_profile_version": None,
    "personal_target": None,
    "professional_review": "not_reviewed",
    "rules_status": "not_ready",
    "adoption_available": False,
    "purchase_available": False,
}


def calculate_meal_plan(spec, recipes, portions):
    """服务端重建菜名与配方，按计划量复算三餐和全天营养。"""
    results = []
    for meal in spec.meals:
        items, dishes = [], []
        for index, dish in enumerate(meal.dishes):
            recipe = recipes.get(str(dish.recipe_version_id))
            if recipe is None:
                raise HealthVisionError("recipe_not_found", "餐单须选择已发布菜谱版本")
            item_id = uuid5(NAMESPACE_URL, f"meal-plan:{meal.meal_type}:{index}:{recipe.id}")
            item = MealItem(
                item_id=item_id,
                name=recipe.name,
                recipe_version_id=dish.recipe_version_id,
                grams=dish.grams,
                portion_reference_id=dish.portion_reference_id,
                portion_count=dish.portion_count,
                share_ratio=Decimal(1),
                portion_source="estimated" if dish.grams is not None or dish.portion_reference_id else "unknown",
            )
            items.append(item)
            grams = dish.grams
            if dish.portion_reference_id:
                portion = portions.get(str(dish.portion_reference_id))
                if portion is None or portion.recipe_version_id != recipe.id:
                    raise HealthVisionError("portion_mapping_mismatch", "份量参考须属于所选菜谱版本")
                grams = Decimal(str(portion.grams_per_unit)) * dish.portion_count
            dishes.append(
                {
                    "dish_index": index,
                    "name": recipe.name,
                    "recipe_version_id": recipe.id,
                    "planned_grams": str(grams) if grams is not None else None,
                    "portion_source": "planned_estimate" if grams is not None else "unknown",
                    "cooking_state": recipe.cooking_state,
                    "dataset_version": recipe.dataset_version,
                    "source": recipe.source,
                    "license": recipe.license,
                    "edition": recipe.edition,
                    "ingredients": [
                        {
                            "name": ingredient["food"]["name"],
                            "food_id": ingredient["food"]["id"],
                            "role": ingredient["role"],
                            "planned_grams": str(
                                Decimal(ingredient["grams"]) * grams / Decimal(str(recipe.yield_grams))
                            )
                            if grams is not None
                            else None,
                        }
                        for ingredient in recipe.ingredients
                    ],
                }
            )
        payload = MealPayload(
            meal_type=meal.meal_type,
            eaten_at=datetime.combine(spec.plan_date, time(12), ZoneInfo("Asia/Shanghai")),
            items=items,
        )
        nutrition = calculate_nutrition(payload, {}, recipes, portions)
        for dish, item in zip(dishes, items):
            calculated = next((r for r in nutrition["items"] if r["item_id"] == str(item.item_id)), None)
            dish["nutrition"] = calculated["nutrients"] if calculated else {key: None for key in NUTRIENTS}
        results.append({"meal_type": meal.meal_type, "dishes": dishes, "nutrition": nutrition})
    totals = {}
    for nutrient in NUTRIENTS:
        values = [meal["nutrition"]["totals"][nutrient] for meal in results]
        totals[nutrient] = None if any(value is None for value in values) else str(sum(map(Decimal, values)))
    return {
        **PLANNER_BOUNDARY,
        "plan_date": spec.plan_date.isoformat(),
        "meals": results,
        "nutrition": {
            "totals": totals,
            "units": NUTRIENTS,
            "complete": all(meal["nutrition"]["complete"] for meal in results),
            "estimated": True,
            "calculation_version": "three-meals-v1",
        },
        "notice": "计划份量与营养仅供核对；完整健康档案和专业配餐规则未接入，尚未评估个体适用性。",
    }


async def calculate_in_session(session, spec):
    """仅加载实际存在的不可变已发布版本。"""
    recipe_ids = {str(d.recipe_version_id) for m in spec.meals for d in m.dishes}
    allocations = (
        [p for m in spec.meals for d in m.dishes for p in d.member_portions]
        if isinstance(spec, FamilyMealPlanSpec)
        else [d for m in spec.meals for d in m.dishes]
    )
    portion_ids = {str(p.portion_reference_id) for p in allocations if p.portion_reference_id}
    recipes = {
        r.id: r for r in (await session.scalars(select(RecipeVersion).where(RecipeVersion.id.in_(recipe_ids)))).all()
    }
    portions = {
        r.id: r
        for r in (await session.scalars(select(PortionReference).where(PortionReference.id.in_(portion_ids)))).all()
    }
    if isinstance(spec, FamilyMealPlanSpec):
        from yuxi.services.health_family_meal_plan import calculate_family_meal_plan

        return calculate_family_meal_plan(spec, recipes, portions)
    return calculate_meal_plan(spec, recipes, portions)


async def require_planner_run(session, context):
    """每个工具与最终输出检查实际Run、固定成员和独立用途审批。"""
    from yuxi.services.health_consultation_service import require_consultation

    run = await HealthConsultationRepository(session).require_attempt(context, lock=True)
    if run.agent_slug != PLANNER_SLUG:
        raise HealthVisionError("execution_not_owned", "此工具只用于成员配餐师运行", 409)
    snapshot = (run.input_payload or {}).get("health_processing")
    if not snapshot:
        raise HealthVisionError("policy_changed", "配餐运行缺少处理审批快照", 409)
    binding, _ = await require_consultation(
        session,
        context.uid,
        context.thread_id,
        context.model,
        expected=snapshot,
        lock=True,
    )
    # 授权可能等待成员/规则锁，已持Run锁阻止续租；等待后重新核对当前租约。
    await HealthConsultationRepository(session).require_attempt(context)
    return run, binding


async def meal_plan_recipes_for_run(context, query):
    """固定成员校验后提供有界的已发布菜谱，不发送成员病历。"""
    async with pg_manager.get_async_session_context() as session:
        _, binding = await require_planner_run(session, context)
        if (
            getattr(binding, "family_planner_selection", None) is not None
            or getattr(binding, "initial_planner_selection", None) is not None
            or getattr(binding, "safe_planner_selection", None) is not None
        ):
            raise HealthVisionError("planner_mode_conflict", "当前配餐模式只使用其固定工具", 409)
        rows = await HealthVisionRepository(session).recipes(query)
        return {
            "recipes": [
                {
                    "recipe_version_id": r.id,
                    "name": r.name,
                    "yield_grams": str(r.yield_grams),
                    "dataset_version": r.dataset_version,
                    "source": r.source,
                    "ingredients": [
                        {"name": ingredient["food"]["name"], "role": ingredient["role"]} for ingredient in r.ingredients
                    ],
                }
                for r in rows[:20]
            ],
            "truncated": len(rows) > 20,
            **PLANNER_BOUNDARY,
        }


async def create_meal_plan_preview(uid, member_id, spec, *, context=None):
    """计算与预览回执同事务提交，模型身份来自有效worker上下文。"""
    async with pg_manager.get_async_session_context() as session:
        run_id = None
        if context is not None:
            if isinstance(spec, FamilyMealPlanSpec):
                raise HealthVisionError("family_agent_not_ready", "家庭模型处理须先接入所有成员审批", 409)
            run, binding = await require_planner_run(session, context)
            if (
                getattr(binding, "family_planner_selection", None) is not None
                or getattr(binding, "initial_planner_selection", None) is not None
                or getattr(binding, "safe_planner_selection", None) is not None
            ):
                raise HealthVisionError("planner_mode_conflict", "当前配餐模式只使用其固定工具", 409)
            uid, member_id, run_id = context.uid, binding.member_id, run.id
        else:
            await HealthVisionRepository(session).authorize_plan_members(
                member_id, uid, spec.model_dump(mode="json"), ["diet_edit"], lock=True
            )
        snapshot = await calculate_in_session(session, spec)
        preview = HealthMealPlanPreview(
            id=str(uuid4()),
            actor_uid=uid,
            member_id=member_id,
            run_id=run_id,
            spec=spec.model_dump(mode="json"),
            snapshot=snapshot,
        )
        session.add(preview)
        await session.flush()
        return {"preview_id": preview.id, "member_id": member_id, **snapshot}


def initial_generation_snapshot(snapshot, evidence, *, current=False):
    """初始来源与计算分开投影；历史来源不声明仍有效或完整建档。"""
    result = deepcopy(snapshot)
    result.pop("generation_origin", None)
    try:
        profiles = evidence["sources"]["profiles"]
        versions = {mid: source["version"] for mid, source in profiles.items()}
        rule_version = evidence["sources"]["rules"]["version"]
        safety = evidence["safety_check"]
        if "members" in snapshot:
            targets = {
                mid: check["personal_targets"]
                for mid, check in safety["members"].items()
                if "personal_targets" in check
            }
        else:
            targets = safety.get("personal_targets")
        if not versions:
            raise ValueError("缺来源")
    except (KeyError, TypeError, ValueError, AttributeError):
        raise HealthVisionError("source_invalidated", "初始生成来源记录无法核对", 410) from None
    result.update(
        personalized=True,
        full_health_profile_available=False,
        profile_status="ready" if current else "requires_current_validation",
        rules_status="ready" if current else "requires_current_validation",
        confirmed_profile_versions=versions,
        confirmed_rule_version=rule_version,
        generation_sources=deepcopy(evidence["sources"]),
        notice="该初版按列明的营养安全投影与批准目录生成；完整档案仍待联调，当前适用性须核对来源并经专业审核。",
    )
    if "members" in snapshot:
        result["personal_targets"] = targets
    else:
        result["confirmed_profile_version"] = next(iter(versions.values()))
        result["personal_target"] = targets
    return result


def plan_result(plan):
    """当前版本与权威快照一同返回，所有计划仍是未审核草稿。"""
    snapshot = plan.snapshot
    if "generation_origin" in snapshot:
        snapshot = initial_generation_snapshot(snapshot, snapshot["generation_origin"])
    return {
        "plan_id": plan.id,
        "member_id": plan.member_id,
        "version": plan.version,
        "updated_at": format_utc_datetime(plan.updated_at),
        **snapshot,
    }


async def save_meal_plan(uid, member_id, data):
    """用户显式保存预览，成员锁内提交初版和幂等收据。"""
    fingerprint = input_fingerprint({"member": member_id, "operation": "save", **data.model_dump(mode="json")})
    async with pg_manager.get_async_session_context() as session:
        repo = HealthMealPlanRepository(session)
        await repo.lock_request(uid, str(data.client_request_id))
        preview = await repo.preview(uid, str(data.preview_id), lock=True)
        if preview.member_id != member_id:
            raise HealthVisionError("not_found", "预览不属于此成员", 404)
        receipt = await repo.receipt(uid, str(data.client_request_id))
        if receipt:
            if receipt.fingerprint != fingerprint:
                raise HealthVisionError("request_conflict", "同一请求不能改变餐单保存内容", 409)
            return plan_result(await repo.plan(uid, receipt.plan_id))
        snapshot = await calculate_in_session(session, parse_meal_plan_spec(preview.spec))
        plan = HealthMealPlan(
            id=str(uuid4()),
            actor_uid=uid,
            member_id=member_id,
            version=1,
            spec=deepcopy(preview.spec),
            snapshot=snapshot,
            updated_at=utc_now_naive(),
        )
        session.add(plan)
        await session.flush()
        session.add(
            HealthMealPlanRevision(
                id=str(uuid4()),
                plan_id=plan.id,
                actor_uid=uid,
                request_id=str(data.client_request_id),
                fingerprint=fingerprint,
                version=1,
                reason="用户保存餐单草稿",
                spec=deepcopy(plan.spec),
                snapshot=snapshot,
            )
        )
        return plan_result(plan)


async def swap_meal_plan_dish(uid, plan_id, data):
    """当前版本换一道菜，服务端重算三餐及全天并保留原版。"""
    fingerprint = input_fingerprint({"plan": plan_id, "operation": "swap", **data.model_dump(mode="json")})
    async with pg_manager.get_async_session_context() as session:
        repo = HealthMealPlanRepository(session)
        await repo.lock_request(uid, str(data.client_request_id))
        plan = await repo.plan(uid, plan_id, lock=True)
        require_single_member_plan(plan)
        receipt = await repo.receipt(uid, str(data.client_request_id))
        if receipt:
            if receipt.fingerprint != fingerprint:
                raise HealthVisionError("request_conflict", "同一请求不能改变换菜内容", 409)
            return plan_result(plan)
        if plan.version != data.version:
            raise HealthVisionError("version_conflict", "餐单版本已变化，请刷新后换菜", 409)
        spec = MealPlanSpec.model_validate(plan.spec)
        meal = next(m for m in spec.meals if m.meal_type == data.meal_type)
        if data.dish_index >= len(meal.dishes):
            raise HealthVisionError("dish_not_found", "所选餐次没有这道菜", 404)
        meal.dishes[data.dish_index] = data.replacement
        snapshot = await calculate_in_session(session, spec)
        plan.version += 1
        plan.spec, plan.snapshot, plan.updated_at = spec.model_dump(mode="json"), snapshot, utc_now_naive()
        from yuxi.repositories.health_quality_repository import HealthQualityRepository

        await HealthQualityRepository(session).invalidate(plan_id=plan.id, reason="plan_changed")
        session.add(
            HealthMealPlanRevision(
                id=str(uuid4()),
                plan_id=plan.id,
                actor_uid=uid,
                request_id=str(data.client_request_id),
                fingerprint=fingerprint,
                version=plan.version,
                reason=data.reason,
                spec=deepcopy(plan.spec),
                snapshot=snapshot,
            )
        )
        return plan_result(plan)


async def read_meal_plan(uid, plan_id):
    """读取当前草稿及不可变修订，不向同成员其他账号共享。"""
    async with pg_manager.get_async_session_context() as session:
        repo = HealthMealPlanRepository(session)
        plan = await repo.plan(uid, plan_id)
        return {
            **plan_result(plan),
            "revisions": [
                {
                    "version": r.version,
                    "reason": r.reason,
                    "snapshot": initial_generation_snapshot(r.snapshot, r.snapshot["generation_origin"])
                    if "generation_origin" in r.snapshot
                    else r.snapshot,
                    "created_at": format_utc_datetime(r.created_at),
                }
                for r in await repo.revisions(uid, plan)
            ],
        }


async def list_meal_plans(uid, member_id, *, limit=50, offset=0):
    """投影当前账号成员的一页餐单，额外一行只用于判断后续页。"""
    async with pg_manager.get_async_session_context() as session:
        rows = await HealthMealPlanRepository(session).list_plans(uid, member_id, limit=limit, offset=offset)
        truncated = len(rows) > limit
        return {
            "plans": [plan_result(row) for row in rows[:limit]],
            "truncated": truncated,
            "next_offset": offset + limit if truncated else None,
        }


def require_single_member_plan(plan):
    """单成员用例尚未实现家庭语义时明确拒绝。"""
    if plan.spec.get("kind") == "family":
        raise HealthVisionError("family_operation_not_ready", "此用例的家庭成员流程尚未接入", 409)


async def planner_final_result(context, text):
    """最终餐单由本Run的PG回执投影，拒绝模型伪造数值和审核标记。"""
    try:
        answer = PlannerAnswer.model_validate_json(text)
    except ValidationError:
        raise HealthVisionError("planner_output_invalid", "配餐输出须为预览回执或补充问题", 422) from None
    async with pg_manager.get_async_session_context() as session:
        run, binding = await require_planner_run(session, context)
        if getattr(binding, "safe_planner_selection", None) is not None:
            from yuxi.services.health_safe_planner_service import safe_answer_in_session

            return await safe_answer_in_session(session, run, binding, answer)
        if getattr(binding, "initial_planner_selection", None) is not None:
            from yuxi.services.health_initial_planner_service import initial_answer_in_session

            return await initial_answer_in_session(session, run, binding, answer)
        if getattr(binding, "family_planner_selection", None) is not None:
            from yuxi.services.health_family_planner_service import family_answer_in_session

            return await family_answer_in_session(session, run, binding, answer)
        if answer.questions:
            return {"questions": answer.questions, **PLANNER_BOUNDARY, "status": "needs_input"}
        preview = await HealthMealPlanRepository(session).preview(context.uid, str(answer.preview_id))
        if preview.run_id != run.id or preview.member_id != binding.member_id:
            raise HealthVisionError("planner_receipt_invalid", "配餐回执不属于当前运行", 409)
        current = await calculate_in_session(session, MealPlanSpec.model_validate(preview.spec))
        if input_fingerprint(current) != input_fingerprint(preview.snapshot):
            raise HealthVisionError("planner_receipt_invalid", "餐单来源或回执已变化，请重新生成", 409)
        return {"preview_id": preview.id, "member_id": preview.member_id, **preview.snapshot}

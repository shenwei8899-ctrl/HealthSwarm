"""初始批准配餐的全员来源验证、独立预览及确认保存。"""

from copy import deepcopy
from uuid import NAMESPACE_URL, uuid4, uuid5

from pydantic import ValidationError

from yuxi.repositories.health_meal_plan_repository import HealthMealPlanRepository
from yuxi.repositories.health_quality_repository import HealthQualityRepository
from yuxi.repositories.health_vision_repository import HealthVisionRepository
from yuxi.services.health_initial_meal_generation import generate_initial_plan
from yuxi.services.health_initial_meal_plan_types import InitialPlanSelection
from yuxi.services.health_meal_plan_service import plan_result, initial_generation_snapshot
from yuxi.services.health_nutrition_service import input_fingerprint
from yuxi.services.health_quality_checks import external_projection
from yuxi.services.health_quality_service import check_plan_in_session, quality_result, validate_quality_check
from yuxi.services.health_quality_types import QualityCheckInput, QualityRules
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_health import HealthInitialPlanPreview, HealthMealPlan, HealthMealPlanRevision
from yuxi.utils.datetime_utils import utc_now_naive


async def initial_context_in_session(session, uid, member_id, selection):
    """全员排序授权后读取最新确认来源，等待锁不能保留旧投影。"""
    ids = sorted(str(m) for m in selection.profile_versions)
    if member_id not in ids:
        raise HealthVisionError("plan_member_required", "入口成员须参加至少一餐", 422)
    health, quality = HealthVisionRepository(session), HealthQualityRepository(session)
    for mid in ids:
        await health.authorize(mid, uid, "diet_edit", lock=True)
        await health.authorize(mid, uid, "profile_view")
    await quality.lock_profile_sources(ids)
    profiles = {mid: await quality.profile_projection(mid) for mid in ids}
    rules = external_projection(await quality.rules(selection.rule_code, lock=True), "rules", selection.rule_code)
    selected_versions = {str(mid): version for mid, version in selection.profile_versions.items()}
    if any(p["status"] == "ready" and p["version"] != selected_versions[mid] for mid, p in profiles.items()) or (
        rules["status"] == "ready" and rules["version"] != selection.rule_version
    ):
        raise HealthVisionError("source_version_conflict", "须确认全部当前档案和规则版本", 409)
    fields = ("id", "version", "content_hash", "status", "reason")
    return {
        "member_id": member_id,
        "profiles": profiles,
        "rules": rules,
        "sources": {
            "profiles": {mid: {k: p[k] for k in fields} for mid, p in profiles.items()},
            "rules": {"rule_code": selection.rule_code, **{k: rules[k] for k in fields}},
        },
    }


async def initial_catalog_in_session(session, uid, member_id, selection):
    """按明确批准目录批量加载真实发布来源，未就绪不猜目录。"""
    current = await initial_context_in_session(session, uid, member_id, selection)
    generation = (
        QualityRules.model_validate(current["rules"]["payload"]).meal_generation
        if current["rules"]["status"] == "ready"
        else None
    )
    ids = {str(c.recipe_version_id) for c in generation.recipe_classifications} if generation else set()
    quality = HealthQualityRepository(session)
    recipes = await HealthMealPlanRepository(session).recipes(ids)
    foods, refs = await quality.recipe_sources_by_recipe(ids)
    current["sources"]["catalog"] = {
        rid: {"recipe_hash": refs.get(rid), "ingredients": foods.get(rid)} for rid in sorted(ids)
    }
    return current, recipes, foods, refs


async def initial_generation_in_session(session, uid, member_id, selection):
    """生成与输出之间重新核对固定当前投影，跨有效期不能写结果。"""
    current, recipes, foods, refs = await initial_catalog_in_session(session, uid, member_id, selection)
    result = generate_initial_plan(selection, current, recipes, foods, refs)
    # 搜索可能跨越外部资料有效期；输出或写回执前重读当前投影。
    fresh = await initial_context_in_session(session, uid, member_id, selection)
    if any(fresh["sources"][k] != current["sources"][k] for k in ("profiles", "rules")):
        raise HealthVisionError("source_invalidated", "初始生成期间来源已变化，请重新选择", 410)
    return result


def initial_preview_result(preview):
    """返回完整服务器结果，确认身份仅为私有回执ID。"""
    result = deepcopy(preview.snapshot)
    if "plan_snapshot" in result:
        result["plan_snapshot"] = initial_generation_snapshot(result["plan_snapshot"], result, current=True)
    return {"preview_id": preview.id, "member_id": preview.member_id, **result}


async def create_initial_plan_preview(uid, member_id, selection):
    """合格结果保存独立回执；不创建餐单、检查或饮食记录。"""
    async with pg_manager.get_async_session_context() as session:
        result = await initial_generation_in_session(session, uid, member_id, selection)
        if result["status"] != "ready":
            return result
        preview = HealthInitialPlanPreview(
            id=str(uuid4()),
            actor_uid=uid,
            member_id=member_id,
            selection=selection.model_dump(mode="json"),
            snapshot=result,
        )
        session.add(preview)
        await session.flush()
        return initial_preview_result(preview)


async def validate_initial_preview(session, uid, preview_id, *, member_id=None):
    """历史或确认回执重查当前来源及全量结果，旧回执不降为通用草稿。"""
    preview = await HealthMealPlanRepository(session).initial_preview(uid, preview_id)
    if member_id is not None and preview.member_id != member_id:
        raise HealthVisionError("not_found", "初始预览不属于此成员", 404)
    try:
        selection = InitialPlanSelection.model_validate(preview.selection)
    except (ValidationError, TypeError):
        raise HealthVisionError("source_invalidated", "初始预览选择无法核对", 410) from None
    try:
        result = await initial_generation_in_session(session, uid, preview.member_id, selection)
    except HealthVisionError as error:
        if error.code != "source_version_conflict":
            raise
        raise HealthVisionError("source_invalidated", "初始预览选定版本已失效，请重新生成", 410) from None
    if result != preview.snapshot:
        raise HealthVisionError("source_invalidated", "初始预览来源或内容已变化，请重新生成", 410)
    return preview, selection


async def read_initial_plan_preview(uid, preview_id):
    """私有读取与确认共享全员授权及当前完整结果核验。"""
    async with pg_manager.get_async_session_context() as session:
        preview, _ = await validate_initial_preview(session, uid, preview_id)
        return initial_preview_result(preview)


async def save_initial_plan(uid, member_id, data):
    """初版、不可变幂等收据、检查和专业草稿同事务提交。"""
    fingerprint = input_fingerprint(
        {"operation": "initial_generation_save", "member_id": member_id, **data.model_dump(mode="json")}
    )
    check_key = str(uuid5(NAMESPACE_URL, f"health-initial-generation:{uid}:{data.client_request_id}"))
    async with pg_manager.get_async_session_context() as session:
        repo, quality = HealthMealPlanRepository(session), HealthQualityRepository(session)
        await quality.lock_request(uid, check_key)
        await repo.lock_request(uid, str(data.client_request_id))
        preview, selection = await validate_initial_preview(session, uid, str(data.preview_id), member_id=member_id)
        if preview.snapshot["status"] != "ready":
            raise HealthVisionError("initial_plan_not_ready", "此预览尚无可保存初版", 409)
        snapshot = {
            **deepcopy(preview.snapshot["plan_snapshot"]),
            "generation_origin": {k: deepcopy(preview.snapshot[k]) for k in ("sources", "safety_check")},
        }
        receipt = await repo.receipt(uid, str(data.client_request_id))
        if receipt is not None:
            if receipt.fingerprint != fingerprint:
                raise HealthVisionError("request_conflict", "同一请求不能改变初始餐单确认", 409)
            plan = await repo.plan(uid, receipt.plan_id)
            if plan.version != 1 or plan.spec != preview.snapshot["plan_spec"] or plan.snapshot != snapshot:
                raise HealthVisionError("source_invalidated", "已保存初版发生变化，请查看当前餐单", 410)
            check = await quality.check_receipt(uid, check_key)
        else:
            plan = HealthMealPlan(
                id=str(uuid4()),
                actor_uid=uid,
                member_id=member_id,
                version=1,
                spec=deepcopy(preview.snapshot["plan_spec"]),
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
                    reason="用户确认批准目录初始餐单",
                    spec=deepcopy(plan.spec),
                    snapshot=deepcopy(plan.snapshot),
                )
            )
            check = await check_plan_in_session(
                session,
                uid,
                plan.id,
                QualityCheckInput(client_request_id=check_key, version=1, rule_code=selection.rule_code),
            )
            if check.snapshot["safety_check"]["status"] != "passed":
                raise HealthVisionError("quality_not_passed", "初始餐单当前来源复核未通过", 409)
        await validate_quality_check(session, uid, check)
        return {
            **plan_result(plan),
            **initial_generation_snapshot(plan.snapshot, plan.snapshot["generation_origin"], current=True),
            "applied_version": 1,
            "quality_check": {**quality_result(check), "current": True},
        }

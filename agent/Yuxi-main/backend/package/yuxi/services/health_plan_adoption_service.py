"""明确用户动作下的次日提议、当前批准采用与使用状态复核。"""

from copy import deepcopy
from datetime import date, timedelta
from uuid import uuid4

from pydantic import ValidationError
from yuxi.repositories.health_meal_plan_repository import HealthMealPlanRepository
from yuxi.repositories.health_plan_adoption_repository import HealthPlanAdoptionRepository, adoption_member_ids
from yuxi.repositories.health_quality_repository import HealthQualityRepository
from yuxi.repositories.health_vision_repository import HealthVisionRepository
from yuxi.services.health_daily_service import business_date
from yuxi.services.health_meal_plan_service import calculate_in_session, initial_generation_snapshot
from yuxi.services.health_meal_plan_types import MealPlanSpec
from yuxi.services.health_family_meal_plan_types import plan_member_ids
from yuxi.services.health_meal_plan_service import require_single_member_plan
from yuxi.services.health_nutrition_service import input_fingerprint
from yuxi.services.health_quality_service import approved_plan_state_in_session
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_health import (
    HealthNextDayProposal,
    HealthMealPlanAdoption,
    HealthMealPlanAdoptionAction,
)
from yuxi.utils.datetime_utils import format_utc_datetime, utc_now_naive


async def proposal_source(session, preview):
    """预览、配方及实际食品来源共同复算，原内容变化不继续使用。"""
    require_single_member_plan(preview)
    try:
        spec = MealPlanSpec.model_validate(preview.spec)
        snapshot = await calculate_in_session(session, spec)
        ingredients, recipes = await HealthQualityRepository(session).ingredients(spec)
    except (ValidationError, ValueError, KeyError, TypeError):
        raise HealthVisionError("source_invalidated", "提议来源无法复算", 410) from None
    if snapshot != preview.snapshot or any(not f["source_current"] for f in ingredients.values()):
        raise HealthVisionError("source_invalidated", "提议预览或食品来源已变化", 410)
    return input_fingerprint(
        {"spec": preview.spec, "snapshot": snapshot, "ingredients": ingredients, "recipes": recipes}
    )


async def proposal_result(session, uid, row):
    """失效提议返回历史快照及明确状态，不伪装为可用正式餐单。"""
    preview = await HealthMealPlanRepository(session).preview(uid, row.preview_id, lock=True)
    reason = "date_expired" if business_date() > row.plan_date else None
    try:
        if await proposal_source(session, preview) != row.source_hash or row.snapshot != preview.snapshot:
            reason = "source_changed"
    except HealthVisionError as error:
        if error.code != "source_invalidated":
            raise
        reason = "source_changed"
    return {
        "proposal_id": row.id,
        "preview_id": row.preview_id,
        "member_id": row.member_id,
        "source_date": row.source_date.isoformat(),
        "plan_date": row.plan_date.isoformat(),
        "status": "proposed" if reason is None else "invalidated",
        "current": reason is None,
        "reason": reason,
        "formal_plan_saved": False,
        "snapshot": deepcopy(row.snapshot),
        "created_at": format_utc_datetime(row.created_at),
    }


async def create_next_day_proposal(uid, member_id, data):
    """只登记今天提出的明日预览，不创建餐单或采用记录。"""
    async with pg_manager.get_async_session_context() as session:
        repo = HealthPlanAdoptionRepository(session)
        await repo.lock_request(uid, str(data.client_request_id), proposal=True)
        preview = await HealthMealPlanRepository(session).preview(uid, str(data.preview_id), lock=True)
        require_single_member_plan(preview)
        if preview.member_id != member_id:
            raise HealthVisionError("not_found", "预览不属于此成员", 404)
        fingerprint = input_fingerprint({"member_id": member_id, **data.model_dump(mode="json")})
        existing = await repo.receipt(uid, str(data.client_request_id), proposal=True)
        if existing is not None:
            if existing.fingerprint != fingerprint:
                raise HealthVisionError("request_conflict", "同一请求不能改变次日提议", 409)
            return await proposal_result(session, uid, existing)
        spec = MealPlanSpec.model_validate(preview.spec)
        if data.source_date != business_date() or spec.plan_date != data.source_date + timedelta(days=1):
            raise HealthVisionError("proposal_date_invalid", "次日提议须以北京时间今天为来源、明天为计划日", 409)
        row = HealthNextDayProposal(
            id=str(uuid4()),
            actor_uid=uid,
            member_id=member_id,
            preview_id=preview.id,
            source_date=data.source_date,
            plan_date=spec.plan_date,
            request_id=str(data.client_request_id),
            fingerprint=fingerprint,
            source_hash=await proposal_source(session, preview),
            snapshot=deepcopy(preview.snapshot),
        )
        session.add(row)
        await session.flush()
        return await proposal_result(session, uid, row)


async def read_next_day_proposal(uid, proposal_id):
    """回读提议时复核授权、日期及不可变来源。"""
    async with pg_manager.get_async_session_context() as session:
        row = await HealthPlanAdoptionRepository(session).proposal(uid, proposal_id)
        return await proposal_result(session, uid, row)


async def adoption_result(session, uid, row):
    """唯一消费入口在事务内复核批准，不恢复失效采用。"""
    await session.flush()
    await session.refresh(row)
    approval = None
    if row.status == "active":
        try:
            approval = await approved_plan_state_in_session(
                session, uid, row.plan_id, row.plan_version, review_id=row.review_id
            )
            valid = approval["available"] and approval["sources"] == row.sources
            if valid:
                plan = await HealthMealPlanRepository(session).plan(uid, row.plan_id)
                valid = (
                    row.member_id == plan.member_id
                    and row.plan_date.isoformat() == plan.snapshot["plan_date"]
                    and row.snapshot == plan.snapshot
                )
        except HealthVisionError as error:
            if error.code not in {"version_conflict", "source_invalidated"}:
                raise
            valid = False
        # 来源锁取得后刷新外部失效事务已提交的状态，避免覆盖旧版本/原因。
        await session.refresh(row)
        if not valid and row.status == "active":
            row.status, row.version = "invalidated", row.version + 1
            row.reason, row.updated_at = "approval_or_sources_unavailable", utc_now_naive()
    await session.flush()
    snapshot = deepcopy(row.snapshot)
    if "generation_origin" in snapshot:
        snapshot = initial_generation_snapshot(snapshot, snapshot["generation_origin"], current=row.status == "active")
    return {
        "adoption_id": row.id,
        "member_id": row.member_id,
        "member_ids": adoption_member_ids(row),
        "plan_id": row.plan_id,
        "plan_version": row.plan_version,
        "plan_date": row.plan_date.isoformat(),
        "review_id": row.review_id,
        "version": row.version,
        "status": row.status,
        "current": row.status == "active",
        "reason": row.reason,
        "sources": deepcopy(row.sources),
        "snapshot": snapshot,
        "professional_approval_current": row.status == "active",
        "updated_at": format_utc_datetime(row.updated_at),
    }


def adoption_action(session, uid, data, row, fingerprint, operation, reason):
    """保存用户动作的不可变幂等证据。"""
    session.add(
        HealthMealPlanAdoptionAction(
            id=str(uuid4()),
            adoption_id=row.id,
            actor_uid=uid,
            request_id=str(data.client_request_id),
            fingerprint=fingerprint,
            operation=operation,
            version=row.version,
            reason=reason,
        )
    )


async def adopt_meal_plan(uid, plan_id, data):
    """明确当前批准与档案版本后正式采用，同日替换须匹配原采用。"""
    selected_input = data.model_dump(mode="json")
    if not selected_input["replaces_adoptions"]:
        selected_input.pop("replaces_adoptions")
    fingerprint = input_fingerprint({"operation": "adopt", "plan_id": plan_id, **selected_input})
    async with pg_manager.get_async_session_context() as session:
        repo = HealthPlanAdoptionRepository(session)
        await repo.lock_request(uid, str(data.client_request_id))
        receipt = await repo.receipt(uid, str(data.client_request_id))
        if receipt is not None:
            if receipt.fingerprint != fingerprint:
                raise HealthVisionError("request_conflict", "同一请求不能改变采用动作或对象", 409)
            return await adoption_result(session, uid, await repo.adoption(uid, receipt.adoption_id))
        plan = await repo.lock_plan_occupancies(uid, plan_id)
        approval = await approved_plan_state_in_session(
            session, uid, plan_id, data.version, review_id=str(data.review_id)
        )
        if not approval["available"]:
            raise HealthVisionError("professional_approval_required", "须选定当前有效专业批准后采用", 409)
        expected = {str(key): version for key, version in data.profile_versions.items()}
        actual = {key: source["version"] for key, source in approval["sources"]["profiles"].items()}
        if expected != actual:
            raise HealthVisionError("profile_version_conflict", "采用所选档案版本已变化", 409)
        plan_date = date.fromisoformat(plan.snapshot["plan_date"])
        previous = await repo.overlapping(uid, plan_member_ids(plan.member_id, plan.spec), plan_date, lock=True)
        selected = {str(key): version for key, version in data.replaces_adoptions.items()}
        if data.replaces_adoption_id is not None:
            selected[str(data.replaces_adoption_id)] = data.replaces_version
        if selected != {row.id: row.version for row in previous}:
            raise HealthVisionError("adoption_version_conflict", "须选择全部当日重叠采用及其当前版本", 409)
        # 只替代已排序锁定成员的占用；不在新来源锁内取得旧规则/资格锁。
        for old in previous:
            old.status, old.version = "superseded", old.version + 1
            old.reason, old.updated_at = "user_selected_replacement", utc_now_naive()
        await session.flush()
        row = HealthMealPlanAdoption(
            id=str(uuid4()),
            actor_uid=uid,
            member_id=plan.member_id,
            plan_id=plan.id,
            plan_version=plan.version,
            plan_date=plan_date,
            review_id=approval["review_id"],
            sources=deepcopy(approval["sources"]),
            snapshot=deepcopy(plan.snapshot),
            status="active",
            version=1,
        )
        session.add(row)
        await session.flush()
        await repo.assign_members(row)
        adoption_action(session, uid, data, row, fingerprint, "adopt", "用户正式采用当前批准的餐单")
        return await adoption_result(session, uid, row)


async def read_adoption(uid, adoption_id):
    """读取原快照与当前可使用状态。"""
    async with pg_manager.get_async_session_context() as session:
        row = await HealthPlanAdoptionRepository(session).adoption(uid, adoption_id)
        return await adoption_result(session, uid, row)


async def current_adopted_plan(uid, member_id, plan_date):
    """今日来源与后续采购读取当天唯一有效采用，不猜测其他草稿。"""
    async with pg_manager.get_async_session_context() as session:
        await HealthVisionRepository(session).authorize(member_id, uid, "diet_edit")
        repo = HealthPlanAdoptionRepository(session)
        row = await repo.active(uid, member_id, plan_date)
        if row is None:
            return {"status": "not_adopted", "member_id": member_id, "plan_date": plan_date.isoformat(), "plan": None}
        row = await repo.adoption(uid, row.id)
        locked_ids = set(adoption_member_ids(row))
        latest = await repo.active(uid, member_id, plan_date)
        if latest is None:
            return {"status": "not_adopted", "member_id": member_id, "plan_date": plan_date.isoformat(), "plan": None}
        if not set(adoption_member_ids(latest)) <= locked_ids:
            raise HealthVisionError("adoption_version_conflict", "当日采用参与者已变化，请刷新", 409)
        row = latest
        result = await adoption_result(session, uid, row)
        return {
            "status": "ready" if result["current"] else "invalidated",
            "member_id": member_id,
            "plan_date": plan_date.isoformat(),
            "plan": result if result["current"] else None,
            "member_plan": (
                deepcopy(result["snapshot"].get("members", {}).get(member_id, result["snapshot"]))
                if result["current"]
                else None
            ),
        }


async def withdraw_adoption(uid, adoption_id, data):
    """取消有效采用保持原计划、快照和饮食记录不变。"""
    fingerprint = input_fingerprint(
        {"operation": "withdraw", "adoption_id": adoption_id, **data.model_dump(mode="json")}
    )
    async with pg_manager.get_async_session_context() as session:
        repo = HealthPlanAdoptionRepository(session)
        await repo.lock_request(uid, str(data.client_request_id))
        row = await repo.adoption(uid, adoption_id)
        receipt = await repo.receipt(uid, str(data.client_request_id))
        if receipt is not None:
            if receipt.fingerprint != fingerprint:
                raise HealthVisionError("request_conflict", "同一请求不能改变取消动作或对象", 409)
            return await adoption_result(session, uid, row)
        await adoption_result(session, uid, row)
        if row.version != data.version or row.status != "active":
            raise HealthVisionError("adoption_version_conflict", "采用版本或状态已变化，请刷新", 409)
        row.status, row.version = "withdrawn", row.version + 1
        row.reason, row.updated_at = data.reason, utc_now_naive()
        adoption_action(session, uid, data, row, fingerprint, "withdraw", data.reason)
        return await adoption_result(session, uid, row)

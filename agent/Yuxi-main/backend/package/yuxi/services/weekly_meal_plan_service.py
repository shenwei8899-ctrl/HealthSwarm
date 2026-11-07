"""多日对话餐单组织已有每日安排，并固定每一天的来源版本。"""

import re
from datetime import date, datetime, timedelta
from types import SimpleNamespace
from uuid import NAMESPACE_URL, uuid4, uuid5
from zoneinfo import ZoneInfo

from sqlalchemy import select, text

from yuxi.repositories.health_consultation_repository import CONSULTATION_SLUG, HealthConsultationRepository
from yuxi.services.daily_arrangement_service import read_daily_arrangement, start_daily_arrangement
from yuxi.services.daily_arrangement_tasks import request_daily_resume
from yuxi.services.family_service import FamilyService
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_business import Conversation
from yuxi.storage.postgres.models_health import HealthDailyArrangement, HealthFamilyProfileLink, HealthWeeklyMealPlan
from yuxi.utils.datetime_utils import utc_now_naive

CANONICAL_WEEKLY_REQUEST = re.compile(
    r"(?:请|麻烦)?(?:为我们|给全家|为全家|帮全家)?"
    r"(?:安排|生成|制定|规划|设计|做一份)(?P<tomorrow>明天|明日)?(?:起|开始)?"
    r"(?P<count>一(?:个)?星期|一周|七天|七日|7天|7日|[2-7二两三四五六](?:天|日))"
    r"(?:的)?(?:三餐|一日三餐|完整餐单|每天的?餐单)[。！？]?"
)


async def start_weekly_meal_plan(uid, family_id, data):
    """登记多日请求并逐日记录唯一安排版本，重复提交复用原组。"""
    today = datetime.now(ZoneInfo("Asia/Shanghai")).date()
    if data.start_date < today or data.start_date > today + timedelta(days=30):
        raise HealthVisionError("weekly_date_invalid", "请选择未来三十天内开始的多日餐单", 422)
    canonical = CANONICAL_WEEKLY_REQUEST.fullmatch(data.question.strip())
    if canonical is None:
        raise HealthVisionError(
            "weekly_profile_review_required",
            "请先在家庭档案核对限制和成员，再单独发送“安排一周三餐”；指定个人或附加忌口暂不能自动安排",
            422,
        )
    count_text = canonical.group("count")
    expected_count = (
        7
        if count_text in {"一星期", "一个星期", "一周", "七天", "七日", "7天", "7日"}
        else {"二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6}.get(
            count_text[0], int(count_text[0]) if count_text[0].isdigit() else 0
        )
    )
    expected_start = today + timedelta(days=bool(canonical.group("tomorrow")))
    if data.day_count != expected_count or data.start_date != expected_start:
        raise HealthVisionError("weekly_request_mismatch", "多日餐单的日期或天数与原问题不一致", 422)

    async with pg_manager.get_async_session_context() as session:
        binding = await _authorize_consultation(session, uid, family_id, str(data.thread_id))
        await session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
            {"key": f"weekly-meal:{uid}:{data.client_request_id}"},
        )
        row = await session.scalar(
            select(HealthWeeklyMealPlan).where(
                HealthWeeklyMealPlan.actor_uid == uid,
                HealthWeeklyMealPlan.request_id == str(data.client_request_id),
            )
        )
        if row is not None and (
            row.family_id != family_id
            or row.conversation_id != binding.conversation_id
            or row.start_date != data.start_date
            or row.day_count != data.day_count
            or row.question != data.question
        ):
            raise HealthVisionError("idempotency_conflict", "多日餐单请求内容已变化", 409)
        if row is None:
            row = HealthWeeklyMealPlan(
                id=str(uuid4()),
                actor_uid=uid,
                family_id=family_id,
                conversation_id=binding.conversation_id,
                request_id=str(data.client_request_id),
                start_date=data.start_date,
                day_count=data.day_count,
                question=data.question,
                status="initializing",
                day_refs={},
                updated_at=utc_now_naive(),
            )
            session.add(row)
            await session.flush()
        group_id, status, refs = row.id, row.status, dict(row.day_refs or {})

    if status in {"active", "failed"}:
        return await read_weekly_meal_plan(uid, family_id, str(data.thread_id), group_id)
    try:
        for offset in range(data.day_count):
            day = data.start_date + timedelta(days=offset)
            if day.isoformat() in refs:
                continue
            daily_key = uuid5(NAMESPACE_URL, f"weekly-meal:{group_id}:{day.isoformat()}")
            await start_daily_arrangement(uid, family_id, SimpleNamespace(client_request_id=daily_key, date=day))
            await _record_day_ref(uid, family_id, group_id, day)
        await _set_group_status(uid, family_id, group_id, "active")
    except Exception:
        await _set_group_status(uid, family_id, group_id, "failed")
        raise
    return await read_weekly_meal_plan(uid, family_id, str(data.thread_id), group_id)


async def read_weekly_meal_plan(uid, family_id, thread_id, group_id):
    """逐日重验来源和固定版本，完整就绪后才投影菜名摘要。"""
    async with pg_manager.get_async_session_context() as session:
        row = await _authorized_group(session, uid, family_id, thread_id, group_id)
        start_date, day_count, question = row.start_date, row.day_count, row.question
        created_at, request_id = row.created_at, row.request_id
        refs, group_status, updated_at = dict(row.day_refs or {}), row.status, row.updated_at

    days = []
    for offset in range(day_count):
        day = start_date + timedelta(days=offset)
        ref = refs.get(day.isoformat())
        days.append(await _bound_day(uid, family_id, day, ref) if ref else None)
    if any(result and result["status"] == "stale" for result in days):
        status = "stale"
    elif group_status == "failed" or group_status == "active" and any(result is None for result in days):
        status = "failed"
    elif (
        group_status == "initializing"
        and any(result is None for result in days)
        and (utc_now_naive() - updated_at > timedelta(seconds=90))
    ):
        status = "failed"
    elif any(result and result["status"] == "failed" for result in days):
        status = "failed"
    elif all(result and result["status"] == "ready" for result in days):
        status = "ready"
    else:
        status = "generating"

    summary = []
    if status == "ready":
        for result in days:
            meals = [
                {"meal_type": meal["type"], "dishes": [dish["name"] for dish in meal["dishes"]]}
                for meal in result["meals"]
            ]
            if {meal["meal_type"] for meal in meals} != {"breakfast", "lunch", "dinner"}:
                raise HealthVisionError("weekly_plan_incomplete", "多日餐单仍有缺失餐次", 409)
            summary.append({"date": result["date"], "meals": meals})
    return {
        "group_id": group_id,
        "request_id": request_id,
        "start_date": start_date.isoformat(),
        "day_count": day_count,
        "question": question,
        "created_at": created_at.isoformat() + "Z",
        "status": status,
        "completed_days": sum(result is not None and result["status"] == "ready" for result in days),
        "total_days": day_count,
        "days": summary,
    }


async def list_weekly_meal_plans(uid, family_id, thread_id):
    """仅恢复当前咨询最近的多日请求。"""
    async with pg_manager.get_async_session_context() as session:
        binding = await _authorize_consultation(session, uid, family_id, thread_id)
        group_ids = list(
            (
                await session.scalars(
                    select(HealthWeeklyMealPlan.id)
                    .where(
                        HealthWeeklyMealPlan.actor_uid == uid,
                        HealthWeeklyMealPlan.family_id == family_id,
                        HealthWeeklyMealPlan.conversation_id == binding.conversation_id,
                    )
                    .order_by(HealthWeeklyMealPlan.created_at.desc(), HealthWeeklyMealPlan.id.desc())
                    .limit(5)
                )
            ).all()
        )
    return {"items": [await read_weekly_meal_plan(uid, family_id, thread_id, group_id) for group_id in group_ids]}


async def retry_weekly_meal_plan(uid, family_id, thread_id, group_id):
    """用户明确重试失败或缺失日期，已绑定版本不重新生成。"""
    result = await read_weekly_meal_plan(uid, family_id, thread_id, group_id)
    if result["status"] == "stale":
        raise HealthVisionError("weekly_plan_stale", "餐单依据已变化，请重新发起", 409)
    async with pg_manager.get_async_session_context() as session:
        row = await _authorized_group(session, uid, family_id, thread_id, group_id)
        refs = dict(row.day_refs or {})
    start_date = date.fromisoformat(result["start_date"])
    for offset in range(result["day_count"]):
        day = start_date + timedelta(days=offset)
        ref = refs.get(day.isoformat())
        if ref:
            current = await _bound_day(uid, family_id, day, ref)
            if current["status"] == "failed":
                await request_daily_resume(uid, family_id, day, retry_failed=True)
            continue
        daily_key = uuid5(NAMESPACE_URL, f"weekly-meal:{group_id}:{day.isoformat()}")
        await start_daily_arrangement(uid, family_id, SimpleNamespace(client_request_id=daily_key, date=day))
        await _record_day_ref(uid, family_id, group_id, day)
    await _set_group_status(uid, family_id, group_id, "active")
    return await read_weekly_meal_plan(uid, family_id, thread_id, group_id)


async def read_weekly_meal_day(uid, family_id, thread_id, group_id, plan_date):
    """详情只返回该组原本绑定的每日安排版本。"""
    async with pg_manager.get_async_session_context() as session:
        row = await _authorized_group(session, uid, family_id, thread_id, group_id)
        if not row.start_date <= plan_date < row.start_date + timedelta(days=row.day_count):
            raise HealthVisionError("not_found", "日期不属于此多日餐单", 404)
        ref = dict(row.day_refs or {}).get(plan_date.isoformat())
    result = await _bound_day(uid, family_id, plan_date, ref) if ref else None
    if not result or result["status"] != "ready":
        raise HealthVisionError("weekly_plan_stale", "餐单依据已变化，请刷新后重新核对", 409)
    return result


async def _authorize_consultation(session, uid, family_id, thread_id):
    """把对话成员关联到当前家庭的正式来源。"""
    binding = await HealthConsultationRepository(session).authorize(uid, thread_id, lock=True)
    conversation = await session.get(Conversation, binding.conversation_id)
    if conversation.agent_id != CONSULTATION_SLUG:
        raise HealthVisionError("not_found", "请使用营养咨询对话安排多日餐单", 404)
    await FamilyService(session, uid).context(family_id)
    link = await session.scalar(
        select(HealthFamilyProfileLink.member_id).where(
            HealthFamilyProfileLink.family_id == family_id,
            HealthFamilyProfileLink.member_id == binding.member_id,
            HealthFamilyProfileLink.actor_uid == uid,
        )
    )
    if link is None:
        raise HealthVisionError("not_found", "咨询成员不属于当前家庭", 404)
    return binding


async def _authorized_group(session, uid, family_id, thread_id, group_id):
    """账号、家庭和对话同时匹配才能读取多日组。"""
    binding = await _authorize_consultation(session, uid, family_id, thread_id)
    row = await session.scalar(
        select(HealthWeeklyMealPlan).where(
            HealthWeeklyMealPlan.id == group_id,
            HealthWeeklyMealPlan.actor_uid == uid,
            HealthWeeklyMealPlan.family_id == family_id,
            HealthWeeklyMealPlan.conversation_id == binding.conversation_id,
        )
    )
    if row is None:
        raise HealthVisionError("not_found", "多日餐单不存在或无权访问", 404)
    return row


async def _record_day_ref(uid, family_id, group_id, day):
    """每日任务提交后固定该组所用的安排标识和版本。"""
    async with pg_manager.get_async_session_context() as session:
        row = await session.get(HealthWeeklyMealPlan, group_id, with_for_update=True)
        daily = await session.scalar(
            select(HealthDailyArrangement).where(
                HealthDailyArrangement.actor_uid == uid,
                HealthDailyArrangement.family_id == family_id,
                HealthDailyArrangement.plan_date == day,
            )
        )
        if row is None or row.actor_uid != uid or row.family_id != family_id or daily is None:
            raise HealthVisionError("weekly_plan_source_missing", "每日安排尚未登记，请重试", 503)
        refs = dict(row.day_refs or {})
        refs.setdefault(day.isoformat(), {"id": daily.id, "version": daily.version})
        row.day_refs = refs
        row.updated_at = utc_now_naive()


async def _set_group_status(uid, family_id, group_id, status):
    """独立提交初始化结局，便于中途失败后按原组恢复。"""
    async with pg_manager.get_async_session_context() as session:
        row = await session.get(HealthWeeklyMealPlan, group_id, with_for_update=True)
        if row is None or row.actor_uid != uid or row.family_id != family_id:
            raise HealthVisionError("not_found", "多日餐单不存在或无权访问", 404)
        row.status = status
        row.updated_at = utc_now_naive()


async def _bound_day(uid, family_id, day, ref):
    """来源失效或版本变化时拒绝旧组展示新结果。"""
    current = await read_daily_arrangement(uid, family_id, day)
    version = current.get("update", {}).get("version", current.get("version"))
    if current.get("id") != ref["id"] or version != ref["version"] or current["status"] == "stale":
        return {"status": "stale", "date": day.isoformat()}
    effective_status = current.get("update", {}).get("status", current["status"])
    if effective_status != "ready":
        return {"status": effective_status, "date": day.isoformat()}
    return current

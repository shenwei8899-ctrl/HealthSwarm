"""复盘来源按成员、日期、当前确认版本聚合，不把计划当实际。"""

from datetime import datetime, time, timedelta
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

from sqlalchemy import select

from yuxi.repositories.family_repository import FamilyRepository
from yuxi.repositories.health_diet_analysis_repository import HealthDietAnalysisRepository
from yuxi.repositories.health_memory_repository import HealthMemoryRepository
from yuxi.repositories.health_vision_repository import HealthVisionRepository
from yuxi.services.diet_stage_types import stage_today
from yuxi.services.health_nutrition_service import input_fingerprint
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.storage.postgres.models_health import HealthObservation, VisionConfirmation

ZONE = ZoneInfo("Asia/Shanghai")


async def generation_sources(repo, data, *, as_of=None, for_read=False):
    """读取前和发布前均走相同的有权来源投影。"""
    family, member = await repo.context()
    hid = await FamilyRepository(repo.session).linked_health_member(family.id, member.id)
    if not hid:
        raise HealthVisionError("stage_binding_required", "请先完成成员健康档案", 409)
    health = HealthVisionRepository(repo.session)
    for scope in ("ai_use", "profile_view", "diet_edit", "report_view"):
        await health.authorize(hid, repo.uid, scope)
    from yuxi.services.health_vision_service import health_vision_service

    config = await health_vision_service.configuration(repo.session)
    model = config["consultation"]
    if not model["available"] and not for_read:
        raise HealthVisionError("stage_model_unavailable", "分析服务暂未就绪", 503)
    processing = {"model": model["model"], "processor": model["processor"], "policy_version": config["policy_version"]}
    await health.require_consent(hid, repo.uid, "consultation", processing)
    stage = await repo.stage(data.stage_id) if data.stage_id else await repo.active()
    day = as_of or min(stage_today(), stage.review_on - timedelta(days=1)) if stage else as_of or stage_today()
    start = stage.starts_on if stage else day - timedelta(days=89)
    stop = min(day + timedelta(days=1), stage.review_on if stage else day + timedelta(days=1))
    sources, feedback, excluded = await HealthDietAnalysisRepository(repo.session).period_sources(
        repo.uid, hid, datetime.combine(start, time(), ZONE), datetime.combine(stop, time(), ZONE)
    )
    reports = await report_sources(repo.session, repo.uid, hid)
    conversations = await conversation_sources(repo.session, repo.uid, hid, start, stop)
    memories = await HealthMemoryRepository(repo.session).list_account(
        repo.uid, member_ids=[hid], limit=300, recallable_only=True
    )
    weeks = await repo.weeks(stage.id) if stage else []
    from yuxi.storage.postgres.models_diet_stage import DietStageWrite

    history = (
        list(
            (
                await repo.session.scalars(
                    select(DietStageWrite)
                    .where(
                        DietStageWrite.stage_id == stage.id,
                        DietStageWrite.snapshot["response"]["stage"]["id"].as_string() == stage.id,
                    )
                    .order_by(DietStageWrite.created_at)
                )
            ).all()
        )
        if stage
        else []
    )
    return {
        "as_of": day.isoformat(),
        "member_id": member.id,
        "subject": {
            "name": member.name,
            "is_speaker": member.subject_uid == repo.uid,
            "relationship": member.relationship,
        },
        "profile_version": member.version,
        "profile": member.profile,
        "processing": processing,
        "health_member_id": hid,
        "stage": {"id": stage.id, "version": stage.version, "goals": stage.goals} if stage else None,
        "window": {"start_date": start.isoformat(), "end_date": (stop - timedelta(days=1)).isoformat()},
        "records": [
            {
                "id": record.id,
                "version": record.version or confirmation.draft_version,
                "eaten_at": record.snapshot["meal"]["eaten_at"],
                "foods": [item["name"] for item in record.snapshot["meal"]["items"] if not item.get("excluded")],
            }
            for record, confirmation in sources
        ],
        "feedback": [{"id": item.id, "version": item.version, "details": item.details} for item in feedback],
        "excluded_records": excluded,
        "reports": reports,
        "conversations": conversations,
        "memories": [
            {"id": row.id, "version": row.version, "kind": row.kind, "content": row.content}
            for row in memories
            if row.provenance.get("family_id") == family.id and row.provenance.get("source_member_id") == member.id
        ],
        "weeks": [
            {
                "id": row.id,
                "version": row.version,
                "goal_version": row.goal_version,
                "starts_on": row.starts_on.isoformat(),
                "ends_on": row.ends_on.isoformat(),
                "actions": row.actions,
            }
            for row in weeks
        ],
        "goal_history": [
            {
                "version": row.snapshot["version"],
                "goals": row.snapshot["goals"],
                "effective_at": row.created_at.isoformat(),
            }
            for row in history
        ],
        "requested_goals": data.goals,
        "note": data.note,
    }


async def conversation_sources(session, uid, hid, start, stop):
    """只收当前账号有权日常会话中的用户原话，失效轮次沿用原过滤。"""
    from yuxi.repositories.health_daily_repository import HealthDailyRepository
    from yuxi.repositories.health_consultation_repository import HealthConsultationRepository
    from yuxi.storage.postgres.models_health import HealthDailyConversation

    repo = HealthDailyRepository(session)
    rows = (
        await session.execute(
            repo.visible()
            .where(
                HealthDailyConversation.actor_uid == uid,
                HealthDailyConversation.member_id == hid,
                HealthDailyConversation.business_date >= start,
                HealthDailyConversation.business_date < stop,
            )
            .order_by(HealthDailyConversation.business_date)
        )
    ).all()
    result = []
    for daily, thread in rows:
        await HealthConsultationRepository(session).authorize(uid, thread)
        messages = await repo.source_messages(daily, thread)
        if messages is None:
            continue
        if len(messages) > 1000:
            raise HealthVisionError("stage_conversation_limit", "单日对话过多，请先整理该日记录", 422)
        result.extend(
            {"id": message.id, "date": daily.business_date.isoformat(), "text": message.content}
            for message in messages
            if message.role == "user"
        )
    return sorted(result, key=lambda message: message["id"])


async def report_sources(session, uid, hid):
    """无100指标截断；确认失效后的指标不进入比较。"""
    rows = list(
        (
            await session.scalars(
                select(HealthObservation).where(HealthObservation.member_id == hid).order_by(HealthObservation.id)
            )
        ).all()
    )
    checked, result = {}, []
    for row in rows:
        if row.confirmation_id not in checked:
            confirmation = await session.get(VisionConfirmation, row.confirmation_id)
            valid = False
            if confirmation is not None:
                try:
                    draft = await HealthVisionRepository(session).draft(confirmation.draft_id, uid, "report")
                    valid = draft.review_status == "confirmed" and draft.version == confirmation.draft_version
                except HealthVisionError as error:
                    if error.status not in (403, 404, 410):
                        raise
            checked[row.confirmation_id] = valid
        if checked[row.confirmation_id]:
            result.append({"id": row.id, "confirmation_id": row.confirmation_id, **row.snapshot})
    return result


def report_comparisons(reports, window):
    """只对相同编码、原单位和已知采样条件计算差值。"""
    grouped = {}
    for item in reports:
        code, day = item.get("observation_code"), item.get("observed_at")
        if code in (None, "unknown") or not day or day > window["end_date"]:
            continue
        grouped.setdefault(code, []).append(item)
    result = []
    for code, values in sorted(grouped.items()):
        ordered = sorted(values, key=lambda value: (value["observed_at"], value["id"]))
        # 同一天多条结果不擅自选其一。
        dates = sorted({item["observed_at"] for item in ordered})
        if not dates or dates[-1] < window["start_date"]:
            continue
        latest = [item for item in ordered if item["observed_at"] == dates[-1]]
        current = latest[0]
        baseline = [day for day in dates[:-1] if day <= window["start_date"]]
        baseline_day = baseline[-1] if baseline else dates[0] if len(dates) > 1 else None
        previous = [item for item in ordered if item["observed_at"] == baseline_day]
        comparable = len(latest) == 1 and len(previous) == 1 and bool(current.get("unit_raw"))
        old = previous[0] if len(previous) == 1 else None
        comparable = (
            comparable
            and current.get("unit_raw") == old.get("unit_raw")
            and (current.get("fasting") in ("yes", "no") and current["fasting"] == old.get("fasting"))
        )
        delta = None
        if comparable:
            try:
                delta = str(Decimal(str(current["value_numeric"])) - Decimal(str(old["value_numeric"])))
            except (InvalidOperation, KeyError, TypeError):
                comparable = False
        result.append(
            {
                "code": code,
                "name": current["name"],
                "current": current,
                "previous": old,
                "delta": delta if comparable else None,
                "note": "原单位及已知采样条件一致的数值差；不代表临床改善或恶化，机构和方法差异需另核对"
                if comparable
                else "资料或采样条件不足，仅展示原始结果",
            }
        )
    return result


def source_hash(sources):
    """哈希包含实际使用的来源版本，正文不进入公开页面。"""
    return input_fingerprint(sources)


def frozen_review_valid(stored, current):
    """已结束正文冻结；撤回或更正原始事实仍使旧正文不可见。"""
    for key in ("records", "reports", "memories", "conversations", "feedback"):
        available = {str(item["id"]): item for item in current[key]}
        for item in stored[key]:
            if available.get(str(item["id"])) != item:
                return False
    return True

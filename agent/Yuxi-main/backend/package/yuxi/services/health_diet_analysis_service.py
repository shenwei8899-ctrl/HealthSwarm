"""单餐事实分析来自有效确认快照，模型仅选择来源。"""

from copy import deepcopy
from collections import Counter
from datetime import datetime, time, timedelta
from decimal import Decimal
import json
from zoneinfo import ZoneInfo

from pydantic import ValidationError

from yuxi.repositories.health_consultation_repository import ANALYST_SLUG, HealthConsultationRepository
from yuxi.repositories.health_diet_analysis_repository import HealthDietAnalysisRepository
from yuxi.repositories.health_vision_repository import HealthVisionRepository
from yuxi.services.health_diet_analysis_types import DietAnalysisAnswer, DietAnalysisPeriod, DietAnalysisSelection
from yuxi.services.health_vision_types import HealthVisionError, NUTRIENTS
from yuxi.storage.postgres.manager import pg_manager
from yuxi.utils.datetime_utils import format_utc_datetime

ANALYSIS_BOUNDARY = {
    "scope": "confirmed_single_meal",
    "analysis_version": "single-meal-facts-v1",
    "personalized": False,
    "full_health_profile_available": False,
    "personal_target": None,
    "professional_review": "not_reviewed",
    "rules_status": "not_ready",
}


def analyze_confirmed_meal(record, confirmation):
    """保留五项原营养值与缺失项，按实际已计算食物说明覆盖。"""
    meal, nutrition = record.snapshot["meal"], record.snapshot["nutrition"]
    calculated = {item["item_id"]: item for item in nutrition["items"]}
    items = []
    for item in meal["items"]:
        if item.get("excluded"):
            continue
        value = calculated.get(item["item_id"], {})
        items.append(
            {
                "item_id": item["item_id"],
                "name": item["name"],
                "grams": item.get("grams"),
                "portion_source": item.get("portion_source"),
                "portion_reference_id": item.get("portion_reference_id"),
                "portion_count": item.get("portion_count"),
                "share_ratio": item.get("share_ratio"),
                "eaten_grams": value.get("eaten_grams"),
                "nutrients": {code: value.get("nutrients", {}).get(code) for code in NUTRIENTS},
            }
        )
    totals = {code: nutrition["totals"].get(code) for code in NUTRIENTS}
    missing = deepcopy(nutrition["missing"])
    findings = [f"本餐已确认{len(items)}项食物；营养值沿用确认时的计算快照。"]
    if missing:
        findings.append("存在食物、份量或营养缺失；未知值保持空，不以零代替，也不按已知部分判断整餐达标。")
    if nutrition["estimated"]:
        findings.append("本餐含估算份量或配方营养，确认记录不代表精确实测。")
    findings.append("个人目标和专业规则尚未接入，本结果不判断营养是否达标或疾病适用性。")
    return {
        **ANALYSIS_BOUNDARY,
        "result_type": "diet_analysis",
        "status": "completed",
        "member_id": record.member_id,
        "records": [{"record_id": record.id, "source_version": confirmation.draft_version}],
        "source": {
            "record_id": record.id,
            "confirmation_id": confirmation.id,
            "draft_id": confirmation.draft_id,
            "source_version": confirmation.draft_version,
            "confirmed_at": format_utc_datetime(record.created_at),
        },
        "meal_type": meal["meal_type"],
        "eaten_at": meal["eaten_at"],
        "items": items,
        "nutrition": {
            "totals": totals,
            "units": deepcopy(nutrition["units"]),
            "complete": nutrition["complete"],
            "estimated": nutrition["estimated"],
            "missing": missing,
            "calculation_version": nutrition["calculation_version"],
            "sources": deepcopy(nutrition["sources"]),
        },
        "coverage": {
            "recorded_items": len(items),
            "calculated_items": sum(item["item_id"] in calculated for item in items),
            "known_nutrients": sum(value is not None for value in totals.values()),
            "supported_nutrients": len(NUTRIENTS),
            "meaning": "仅描述本次已确认记录的覆盖，不能代表实际吃过的全部食物。",
        },
        "findings": findings,
    }


def analyze_confirmed_period(member_id, period, sources, feedback, invalidated=0):
    """逐日覆盖与已知和独立展示，缺失及未记录天数不补零。"""
    start_date = period.end_date - timedelta(days=period.period_days - 1)
    analyses = [analyze_confirmed_meal(record, confirmation) for record, confirmation in sources]
    days = []
    for offset in range(period.period_days):
        day = start_date + timedelta(days=offset)
        meals = [
            meal
            for meal in analyses
            if datetime.fromisoformat(meal["eaten_at"]).astimezone(ZoneInfo("Asia/Shanghai")).date() == day
        ]
        daily = {}
        for code in NUTRIENTS:
            values = [meal["nutrition"]["totals"][code] for meal in meals]
            known = [Decimal(value) for value in values if value is not None]
            daily[code] = {
                "recorded_total": str(sum(known, Decimal(0))) if values and len(known) == len(values) else None,
                "known_sum": str(sum(known, Decimal(0))) if known else None,
                "known_records": len(known),
                "missing_records": len(values) - len(known),
            }
        days.append({"date": day.isoformat(), "record_count": len(meals), "nutrition": daily})
    totals = {}
    for code in NUTRIENTS:
        values = [meal["nutrition"]["totals"][code] for meal in analyses]
        known = [Decimal(value) for value in values if value is not None]
        totals[code] = {
            "recorded_total": str(sum(known, Decimal(0))) if values and len(known) == len(values) else None,
            "known_sum": str(sum(known, Decimal(0))) if known else None,
            "known_records": len(known),
            "missing_records": len(values) - len(known),
        }
    tags = Counter(tag for item in feedback for tag in item.details.get("tags", []))
    consumption = Counter(item.details.get("consumption", "unknown") for item in feedback)
    return {
        **ANALYSIS_BOUNDARY,
        "scope": "confirmed_period",
        "analysis_version": "period-facts-v1",
        "result_type": "diet_analysis",
        "status": "completed",
        "member_id": member_id,
        "window": {
            "start_date": start_date.isoformat(),
            "end_date": period.end_date.isoformat(),
            "period_days": period.period_days,
            "timezone": "Asia/Shanghai",
        },
        "records": [ref for meal in analyses for ref in meal["records"]],
        "feedback_sources": [{"feedback_id": item.id, "version": item.version} for item in feedback],
        "nutrition": {
            "totals": totals,
            "units": {code: NUTRIENTS[code] for code in NUTRIENTS},
            "estimated": any(meal["nutrition"]["estimated"] for meal in analyses),
            "missing": [
                {"record_id": meal["source"]["record_id"], "items": meal["nutrition"]["missing"]}
                for meal in analyses
                if meal["nutrition"]["missing"]
            ],
        },
        "days": days,
        "coverage": {
            "window_days": period.period_days,
            "days_with_records": sum(day["record_count"] > 0 for day in days),
            "dates_without_records": [day["date"] for day in days if not day["record_count"]],
            "record_count": len(analyses),
            "excluded_invalidated_records": invalidated,
            "expected_meal_count": None,
            "meaning": "分母为窗口自然日和有效确认记录；未记录不代表未进食，不能据此计算实际餐次达成率。",
        },
        "feedback": {
            "count": len(feedback),
            "record_denominator": len(analyses),
            "records_without_feedback": len(analyses) - len(feedback),
            "tag_counts": dict(sorted(tags.items())),
            "consumption_counts": dict(sorted(consumption.items())),
            "source_type": "user_self_report",
            "nutrition_recalculated": False,
        },
        "trend": {
            "status": "rules_not_ready",
            "direction": None,
            "rule_version": None,
            "reason": "趋势分类、最低样本及个人目标尚未批准；当前仅展示统计事实。",
        },
        "findings": [
            "记录总和仅代表已确认记录；已知部分之和单列，不填补缺失值或未记录天数。",
            "单餐反馈为用户自述，计数不改变摄入量，也不构成健康变化或病情判断。",
        ],
    }


async def period_analysis_in_session(session, uid, member_id, period):
    """当前事务读取自然日窗口及有效反馈，不使用创建日期代替进食时间。"""
    zone = ZoneInfo("Asia/Shanghai")
    if period.end_date > datetime.now(zone).date():
        raise HealthVisionError("period_in_future", "分析结束日期不能晚于北京时间今天", 422)
    start_date = period.end_date - timedelta(days=period.period_days - 1)
    start = datetime.combine(start_date, time.min, tzinfo=zone)
    stop = datetime.combine(period.end_date + timedelta(days=1), time.min, tzinfo=zone)
    sources, feedback, invalidated = await HealthDietAnalysisRepository(session).period_sources(
        uid, member_id, start, stop
    )
    return analyze_confirmed_period(member_id, period, sources, feedback, invalidated)


async def read_period_analysis(uid, member_id, period, *, context=None):
    """后台纯读取及分析工具复用同一事实投影，工具另核对执行归属。"""
    async with pg_manager.get_async_session_context() as session:
        if context is not None:
            binding = await require_analyst_run(session, context)
            uid, member_id = context.uid, binding.member_id
        else:
            await HealthVisionRepository(session).authorize(member_id, uid, "diet_edit", lock=True)
        return await period_analysis_in_session(session, uid, member_id, period)


async def require_analyst_run(session, context, *, allow_feedback=False):
    """执行身份、独立用途审批和成员授权均由服务器核对。"""
    from yuxi.services.health_consultation_service import require_consultation

    run = await HealthConsultationRepository(session).require_attempt(context, lock=True)
    if run.agent_slug != ANALYST_SLUG:
        raise HealthVisionError("execution_not_owned", "单餐分析工具仅用于饮食分析师运行", 409)
    expected = (run.input_payload or {}).get("health_processing")
    if not expected:
        raise HealthVisionError("policy_changed", "分析运行缺少处理审批快照", 409)
    binding, _ = await require_consultation(
        session, context.uid, context.thread_id, context.model, expected=expected, lock=True
    )
    if not allow_feedback:
        from yuxi.repositories.health_dialog_feedback_repository import HealthDialogFeedbackRepository

        if await HealthDialogFeedbackRepository(session).selection(binding) is not None:
            raise HealthVisionError("feedback_mode_only", "选餐反馈会话不能调用分析工具", 409)
    return binding


async def read_diet_analysis(uid, member_id, selection, *, context=None):
    """纯读取无需外发模型；工具调用另核对当前运行归属。"""
    async with pg_manager.get_async_session_context() as session:
        if context is not None:
            binding = await require_analyst_run(session, context)
            uid, member_id = context.uid, binding.member_id
        else:
            await HealthVisionRepository(session).authorize(member_id, uid, "diet_edit", lock=True)
        record, confirmation = await HealthDietAnalysisRepository(session).source(
            uid, member_id, str(selection.record_id), selection.source_version
        )
        return analyze_confirmed_meal(record, confirmation)


async def analyst_meal_records(context):
    """只列有效确认餐次与版本，排除原图、OCR和个人病史。"""
    async with pg_manager.get_async_session_context() as session:
        binding = await require_analyst_run(session, context)
        repo = HealthDietAnalysisRepository(session)
        rows = await HealthVisionRepository(session).list_records(binding.member_id, "meal")
        records = []
        for row in rows:
            try:
                record, confirmation = await repo.source(context.uid, binding.member_id, row.id)
            except HealthVisionError as exc:
                if exc.status != 410:
                    raise
                continue
            records.append(
                {
                    "record_id": record.id,
                    "source_version": confirmation.draft_version,
                    "meal_type": record.snapshot["meal"]["meal_type"],
                    "eaten_at": record.snapshot["meal"]["eaten_at"],
                    "names": [item["name"] for item in record.snapshot["meal"]["items"] if not item.get("excluded")],
                }
            )
        return {"records": records, **ANALYSIS_BOUNDARY}


async def analyst_final_result(context, text):
    """模型仅指定来源；最终营养、缺失和说明全部重新投影。"""
    from yuxi.services.health_dialog_feedback_service import feedback_final_result, is_feedback_conversation

    try:
        answer = DietAnalysisAnswer.model_validate_json(text)
    except ValidationError:
        from yuxi.services.health_meal_feedback_types import DialogFeedbackAnswer

        try:
            DialogFeedbackAnswer.model_validate_json(text)
        except ValidationError:
            raise HealthVisionError("analyst_output_invalid", "分析输出须为确认来源、反馈收据或补充问题", 422) from None
        if await is_feedback_conversation(context):
            return await feedback_final_result(context, text)
        raise HealthVisionError("analyst_output_invalid", "普通分析不能发布反馈结果", 422)
    if await is_feedback_conversation(context):
        return await feedback_final_result(context, text)
    if answer.questions:
        async with pg_manager.get_async_session_context() as session:
            await require_analyst_run(session, context)
        return {
            "result_type": "diet_analysis",
            "status": "needs_input",
            "questions": answer.questions,
            **ANALYSIS_BOUNDARY,
        }
    if answer.period_days is not None:
        period = DietAnalysisPeriod(period_days=answer.period_days, end_date=answer.end_date)
        return await read_period_analysis(None, None, period, context=context)
    return await read_diet_analysis(None, None, answer, context=context)


async def validate_analyst_publication(session, run, content):
    """输出事务持有成员锁至提交，重查同意和来源并核对服务器投影。"""
    from yuxi.services.health_consultation_service import require_consultation

    expected = (run.input_payload or {}).get("health_processing")
    if not expected:
        raise HealthVisionError("policy_changed", "分析运行缺少处理审批快照", 409)
    binding, _ = await require_consultation(
        session, run.uid, run.conversation_thread_id, expected["model"], expected=expected, lock=True
    )
    from yuxi.repositories.health_dialog_feedback_repository import HealthDialogFeedbackRepository
    from yuxi.services.health_dialog_feedback_service import dialog_feedback_final
    from yuxi.services.health_meal_feedback_types import DialogFeedbackAnswer

    selection = await HealthDialogFeedbackRepository(session).selection(binding)
    if selection is not None:
        try:
            payload = json.loads(content)
            answer = DialogFeedbackAnswer.model_validate(
                {"questions": payload["questions"]} if payload["status"] == "needs_input" else {"feedback_saved": True}
            )
            authoritative = await dialog_feedback_final(session, run.uid, binding, selection, run.id, answer)
        except (KeyError, TypeError, ValueError):
            raise HealthVisionError("feedback_output_invalid", "最终反馈无法核对", 422) from None
        if payload != authoritative:
            raise HealthVisionError("feedback_output_invalid", "最终反馈与当前服务器收据不一致", 422)
        return
    try:
        payload = json.loads(content)
        if payload["status"] == "needs_input":
            answer = DietAnalysisAnswer.model_validate({"questions": payload["questions"]})
            authoritative = {
                "result_type": "diet_analysis",
                "status": "needs_input",
                "questions": answer.questions,
                **ANALYSIS_BOUNDARY,
            }
        elif payload.get("scope") == "confirmed_period":
            period = DietAnalysisPeriod(
                period_days=payload["window"]["period_days"], end_date=payload["window"]["end_date"]
            )
            authoritative = await period_analysis_in_session(session, run.uid, binding.member_id, period)
        else:
            selection = DietAnalysisSelection.model_validate(payload["records"][0])
            record, confirmation = await HealthDietAnalysisRepository(session).source(
                run.uid, binding.member_id, str(selection.record_id), selection.source_version
            )
            authoritative = analyze_confirmed_meal(record, confirmation)
    except (KeyError, IndexError, TypeError, ValueError):
        raise HealthVisionError("analyst_output_invalid", "最终分析无法核对", 422) from None
    if payload != authoritative:
        raise HealthVisionError("analyst_output_invalid", "最终分析与当前确认快照不一致", 422)

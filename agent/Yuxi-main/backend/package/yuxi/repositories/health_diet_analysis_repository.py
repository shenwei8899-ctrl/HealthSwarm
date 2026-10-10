"""单餐分析读取有效确认来源，成员锁由用例持有。"""

import json

from sqlalchemy import DateTime, and_, cast, or_, select

from yuxi.repositories.health_vision_repository import HealthVisionRepository
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.storage.postgres.models_health import DietLog, MealFeedback, VisionConfirmation
from yuxi.storage.postgres.models_business import TOOL_AUDIT_MESSAGE_TYPE, AgentRun, Message


class HealthDietAnalysisRepository:
    """确认记录和源草稿共同决定当前可分析性。"""

    def __init__(self, session):
        self.session = session

    async def source(self, uid, member_id, record_id, source_version=None):
        """跨成员及不可见资源统一404，已撤回来源410，版本冲突409。"""
        record = await self.session.scalar(
            select(DietLog).where(DietLog.id == record_id, DietLog.member_id == member_id)
        )
        if record is None:
            raise HealthVisionError("not_found", "已确认餐次不存在或无权访问", 404)
        confirmation = await self.session.get(VisionConfirmation, record.confirmation_id)
        if confirmation is None:
            raise HealthVisionError("source_invalidated", "餐次确认来源已失效", 410)
        draft = await HealthVisionRepository(self.session).draft(confirmation.draft_id, uid, "meal")
        if draft.review_status != "confirmed" or draft.version != confirmation.draft_version:
            raise HealthVisionError("source_invalidated", "餐次已更正或撤回，请选择当前确认记录", 410)
        if source_version is not None and confirmation.draft_version != source_version:
            raise HealthVisionError("version_conflict", "确认来源版本不一致，请刷新餐次", 409)
        return record, confirmation

    async def period_sources(self, uid, member_id, start, stop):
        """按实际进食时间取完整有界窗口，失效来源明确计入排除范围。"""
        eaten_at = cast(DietLog.snapshot["meal"]["eaten_at"].as_string(), DateTime(timezone=True))
        rows = list(
            (
                await self.session.scalars(
                    select(DietLog)
                    .where(DietLog.member_id == member_id, eaten_at >= start, eaten_at < stop)
                    .order_by(eaten_at, DietLog.id)
                    .limit(1001)
                )
            ).all()
        )
        if len(rows) > 1000:
            raise HealthVisionError("period_limit_exceeded", "窗口记录超过1000条，请使用较短窗口", 422)
        sources, invalidated = [], 0
        for row in rows:
            try:
                sources.append(await self.source(uid, member_id, row.id))
            except HealthVisionError as exc:
                if exc.status != 410:
                    raise
                invalidated += 1
        ids = [record.id for record, _ in sources]
        feedback = list(
            (
                await self.session.scalars(
                    select(MealFeedback)
                    .where(
                        MealFeedback.actor_uid == uid,
                        MealFeedback.member_id == member_id,
                        MealFeedback.diet_log_id.in_(ids),
                        MealFeedback.status == "active",
                    )
                    .order_by(MealFeedback.diet_log_id, MealFeedback.id)
                )
            ).all()
        )
        return sources, feedback, invalidated

    async def validate_history(self, uid, binding):
        """撤回来源的旧分析线程不继续展示或外发，需重新进入分析。"""
        messages = await self.session.scalars(
            select(Message)
            .join(AgentRun, AgentRun.id == Message.run_id)
            .where(
                AgentRun.conversation_id == binding.conversation_id,
                or_(
                    and_(AgentRun.status == "completed", AgentRun.output_message_id == Message.id),
                    and_(
                        Message.message_type == TOOL_AUDIT_MESSAGE_TYPE,
                        Message.execution_status == "completed",
                        Message.extra_metadata["tool_name"]
                        .as_string()
                        .in_(["list_analysis_meals", "analyze_confirmed_meal", "analyze_confirmed_period"]),
                    ),
                ),
            )
        )
        for message in messages:
            try:
                payload = json.loads(message.content)
                if message.message_type == TOOL_AUDIT_MESSAGE_TYPE and "records" not in payload:
                    raise ValueError("工具结果缺少来源")
            except (KeyError, TypeError, ValueError, AttributeError):
                raise HealthVisionError("source_invalidated", "历史单餐分析来源无法核对，请重新进入分析", 410) from None
            if message.message_type != TOOL_AUDIT_MESSAGE_TYPE:
                from yuxi.services.health_agent_personal_target_service import attach_current_personal_targets

                expected = attach_current_personal_targets(binding, {})
                if payload.get("current_personal_targets") != expected.get("current_personal_targets") or (
                    "current_personal_targets" in payload
                ) != ("current_personal_targets" in expected):
                    raise HealthVisionError("source_invalidated", "历史分析的当前个人目标无法核对", 410)
                payload = {key: value for key, value in payload.items() if key != "current_personal_targets"}
            await self.validate_payload(
                uid,
                binding.member_id,
                payload,
                period_required=(message.extra_metadata or {}).get("tool_name") == "analyze_confirmed_period",
            )
        from yuxi.services.health_agent_personal_target_service import validate_personal_target_tool_payload

        target_audits = await self.session.execute(
            select(Message, AgentRun)
            .join(AgentRun, AgentRun.id == Message.run_id)
            .where(
                or_(
                    AgentRun.conversation_id == binding.conversation_id,
                    Message.conversation_id == binding.conversation_id,
                ),
                Message.message_type == TOOL_AUDIT_MESSAGE_TYPE,
                Message.execution_status == "completed",
                Message.extra_metadata["tool_name"].as_string() == "get_bound_personal_targets",
            )
        )
        for message, run in target_audits:
            try:
                if (
                    run.uid != uid
                    or run.agent_slug != "health-diet-analyst"
                    or run.conversation_id != binding.conversation_id
                    or message.conversation_id != binding.conversation_id
                    or message.request_id != run.request_id
                ):
                    raise ValueError("工具执行不属于当前线程")
                payload = json.loads(message.content)
            except (TypeError, ValueError):
                raise HealthVisionError("source_invalidated", "历史个人目标工具来源无法核对", 410) from None
            await validate_personal_target_tool_payload(self.session, binding, payload)

    async def validate_payload(self, uid, member_id, payload, *, period_required=False):
        """PG历史与即时checkpoint共同核对记录、反馈版本及完整周期投影。"""
        from yuxi.services.health_diet_analysis_types import (
            DietAnalysisFeedbackSource,
            DietAnalysisPeriod,
            DietAnalysisSelection,
        )

        try:
            if "current_personal_targets" in payload:
                raise ValueError("分析工具不能附加个人目标")
            refs = payload.get("records", [])
            if not isinstance(refs, list):
                raise ValueError("无效来源")
            selections = [
                DietAnalysisSelection.model_validate(
                    {"record_id": ref["record_id"], "source_version": ref["source_version"]}
                )
                for ref in refs
            ]
            feedback_refs = [
                DietAnalysisFeedbackSource.model_validate(ref) for ref in payload.get("feedback_sources", [])
            ]
        except (KeyError, TypeError, ValueError, AttributeError):
            raise HealthVisionError("source_invalidated", "历史分析来源无法核对", 410) from None
        for selection in selections:
            await self.source(uid, member_id, str(selection.record_id), selection.source_version)
        for ref in feedback_refs:
            feedback = await self.session.get(MealFeedback, str(ref.feedback_id), populate_existing=True)
            if (
                feedback is None
                or feedback.actor_uid != uid
                or feedback.member_id != member_id
                or feedback.status != "active"
                or feedback.version != ref.version
            ):
                raise HealthVisionError("source_invalidated", "历史分析反馈已变化，请重新进入分析", 410)
        if payload.get("scope") == "confirmed_period" or period_required:
            from yuxi.services.health_diet_analysis_service import period_analysis_in_session

            try:
                window = DietAnalysisPeriod(
                    period_days=payload["window"]["period_days"], end_date=payload["window"]["end_date"]
                )
            except (KeyError, TypeError, ValueError):
                raise HealthVisionError("source_invalidated", "历史周期窗口无法核对", 410) from None
            current = await period_analysis_in_session(self.session, uid, member_id, window)
            if payload != current:
                raise HealthVisionError("source_invalidated", "周期记录或反馈集合已变化，请重新进入分析", 410)

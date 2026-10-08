"""餐次反馈、修订及模型依赖的账号隔离查询。"""

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from yuxi.repositories.health_vision_repository import HealthVisionRepository
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.storage.postgres.models_business import AgentRun
from yuxi.storage.postgres.models_health import (
    DietLog,
    VisionConfirmation,
    VisionDraft,
    MealFeedback,
    MealFeedbackRevision,
    MealFeedbackUse,
    HealthFeedbackWrite,
)


class HealthMealFeedbackRepository:
    """事务由 service 拥有，写操作持有成员锁。"""

    def __init__(self, session):
        self.session = session

    async def require_record(self, uid, record_id, *, lock=False):
        """只有仍有效的已确认餐次可读取或填写反馈。"""
        record = await self.session.get(DietLog, record_id, populate_existing=True)
        if record is None:
            raise HealthVisionError("not_found", "餐次不存在或无权访问", 404)
        health = HealthVisionRepository(self.session)
        await health.authorize(record.member_id, uid, "diet_edit", lock=lock)
        confirmation = await self.session.get(VisionConfirmation, record.confirmation_id)
        if confirmation is None:
            raise HealthVisionError("source_invalidated", "餐次确认来源已失效", 410)
        draft = await self.session.get(VisionDraft, confirmation.draft_id, populate_existing=True)
        await health.draft(confirmation.draft_id, uid, "meal")
        if (
            draft.review_status != "confirmed"
            or draft.version != confirmation.draft_version
            or confirmation.member_id != record.member_id
        ):
            raise HealthVisionError("source_invalidated", "原餐次已失效，请先核对饮食记录", 410)
        return record

    async def slot(self, uid, record_id):
        """一个账号在同一餐次维护一个当前反馈。"""
        return await self.session.scalar(
            select(MealFeedback)
            .where(MealFeedback.actor_uid == uid, MealFeedback.diet_log_id == record_id)
            .execution_options(populate_existing=True)
        )

    async def receipt(self, uid, request_id):
        """账号级不可变请求收据用于冲突检测。"""
        return await self.session.scalar(
            select(MealFeedbackRevision).where(
                MealFeedbackRevision.actor_uid == uid, MealFeedbackRevision.request_id == request_id
            )
        )

    async def revisions(self, feedback_id):
        """返回有序修订供后台核对。"""
        return list(
            (
                await self.session.scalars(
                    select(MealFeedbackRevision)
                    .where(MealFeedbackRevision.feedback_id == feedback_id)
                    .order_by(MealFeedbackRevision.version)
                )
            ).all()
        )

    async def dialog_sources(self, feedback_id):
        """回读对话写入的消息和Run来源，旧管理修订没有该来源。"""
        rows = await self.session.scalars(
            select(HealthFeedbackWrite)
            .join(MealFeedbackRevision, MealFeedbackRevision.id == HealthFeedbackWrite.revision_id)
            .where(MealFeedbackRevision.feedback_id == feedback_id)
        )
        return {row.revision_id: row for row in rows}

    async def active(self, uid, member_id):
        """按最近更新时间返回有界候选，来源由调用方逐条核对。"""
        return list(
            (
                await self.session.scalars(
                    select(MealFeedback)
                    .where(
                        MealFeedback.actor_uid == uid,
                        MealFeedback.member_id == member_id,
                        MealFeedback.status == "active",
                    )
                    .order_by(MealFeedback.updated_at.desc(), MealFeedback.id)
                    .limit(101)
                )
            ).all()
        )

    async def uses(self, uid, *, thread_id=None, member_id=None):
        """只返回当前账号和指定线程或成员的持久依赖。"""
        stmt = (
            select(AgentRun.request_id, MealFeedbackUse.version, MealFeedback)
            .join(MealFeedbackUse, MealFeedbackUse.run_id == AgentRun.id)
            .join(MealFeedback, MealFeedback.id == MealFeedbackUse.feedback_id)
            .where(AgentRun.uid == uid, MealFeedback.actor_uid == uid)
        )
        if thread_id is not None:
            stmt = stmt.where(AgentRun.conversation_thread_id == thread_id)
        if member_id is not None:
            stmt = stmt.where(MealFeedback.member_id == member_id)
        return list((await self.session.execute(stmt.execution_options(populate_existing=True))).all())

    async def invalid_requests(self, uid, member_id):
        """来源失效或反馈版本变化使读取和派生轮次失效。"""
        invalid, checked = set(), {}
        for request, version, feedback in await self.uses(uid, member_id=member_id):
            if feedback.id not in checked:
                checked[feedback.id] = await self.valid_source(uid, feedback)
            if feedback.status != "active" or version != feedback.version or not checked[feedback.id]:
                invalid.add(request)
        return invalid

    async def valid_source(self, uid, feedback):
        """已删除来源不再用于咨询及摘要，明确业务错误视为失效。"""
        try:
            record = await self.require_record(uid, feedback.diet_log_id)
        except HealthVisionError as exc:
            if exc.status in (404, 410):
                return False
            raise
        return record.member_id == feedback.member_id

    async def record_uses(self, run, references):
        """外呼前提交依赖；重复模型调用保持幂等。"""
        for feedback_id, version in set(references):
            await self.session.execute(
                insert(MealFeedbackUse)
                .values(run_id=run.id, feedback_id=feedback_id, version=version)
                .on_conflict_do_nothing()
            )

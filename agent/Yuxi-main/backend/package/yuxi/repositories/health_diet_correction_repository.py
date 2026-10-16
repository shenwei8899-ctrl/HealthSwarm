"""已确认饮食更正查询；成员锁与提交边界由服务拥有。"""

import json

from sqlalchemy import select

from yuxi.repositories.health_vision_repository import HealthVisionRepository
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.storage.postgres.models_health import (
    DietLog,
    DietLogRevision,
    FoodRecord,
    RecipeVersion,
    PortionReference,
    MealFeedback,
)
from yuxi.storage.postgres.models_business import AgentRun, Message, TOOL_AUDIT_MESSAGE_TYPE


class HealthDietCorrectionRepository:
    """当前事实、修订收据与计算依赖共用同一会话。"""

    def __init__(self, session):
        """接收用例的事务会话。"""
        self.session = session

    async def record(self, uid, record_id, *, lock=False):
        """先授权并锁成员，再刷新餐次，防止等待锁后仍使用旧版本。"""
        member_id = await self.session.scalar(select(DietLog.member_id).where(DietLog.id == record_id))
        if member_id is None:
            raise HealthVisionError("not_found", "餐次不存在或无权访问", 404)
        await HealthVisionRepository(self.session).authorize(member_id, uid, "diet_edit", lock=lock)
        stmt = select(DietLog).where(DietLog.id == record_id).execution_options(populate_existing=True)
        return await self.session.scalar(stmt.with_for_update() if lock else stmt)

    async def receipt(self, uid, request_id):
        """账号级幂等收据不依赖客户端当前版本。"""
        return await self.session.scalar(
            select(DietLogRevision).where(DietLogRevision.actor_uid == uid, DietLogRevision.request_id == request_id)
        )

    async def revisions(self, record_id):
        """按版本读取不可变的记录历史。"""
        return list(
            (
                await self.session.scalars(
                    select(DietLogRevision)
                    .where(DietLogRevision.diet_log_id == record_id)
                    .order_by(DietLogRevision.version)
                )
            ).all()
        )

    async def nutrition_inputs(self, meal):
        """只查询客户端明确选定的已发布数据版本。"""
        food_ids = {str(item.food_id) for item in meal.items if item.food_id}
        food_ids.update(str(entry.food_id) for item in meal.items for entry in item.adjustments)
        mappings = []
        for model, ids in (
            (FoodRecord, food_ids),
            (RecipeVersion, {str(item.recipe_version_id) for item in meal.items if item.recipe_version_id}),
            (PortionReference, {str(item.portion_reference_id) for item in meal.items if item.portion_reference_id}),
        ):
            mappings.append(
                {row.id: row for row in (await self.session.scalars(select(model).where(model.id.in_(ids)))).all()}
            )
        return mappings

    async def active_feedback(self, record_id):
        """更正影响该餐次所有账号的旧反馈依赖。"""
        return list(
            (
                await self.session.scalars(
                    select(MealFeedback).where(MealFeedback.diet_log_id == record_id, MealFeedback.status == "active")
                )
            ).all()
        )

    async def validate_consultation_history(self, uid, binding):
        """公开历史、摘要与新执行都拒绝依赖旧饮食快照的咨询线程。"""
        from yuxi.repositories.health_diet_analysis_repository import HealthDietAnalysisRepository
        from yuxi.services.health_consultation_service import project_confirmed_record

        messages = await self.session.scalars(
            select(Message)
            .join(AgentRun, AgentRun.id == Message.run_id)
            .where(
                AgentRun.uid == uid,
                AgentRun.conversation_id == binding.conversation_id,
                Message.message_type == TOOL_AUDIT_MESSAGE_TYPE,
                Message.execution_status == "completed",
                Message.extra_metadata["tool_name"].as_string() == "get_confirmed_diet",
            )
        )
        for message in messages.all():
            try:
                payload = json.loads(message.content)
                refs = payload["records"]
                if not isinstance(refs, list):
                    raise ValueError("无效记录列表")
                expected = []
                for ref in refs:
                    record, confirmation = await HealthDietAnalysisRepository(self.session).source(
                        uid, binding.member_id, ref["record_id"]
                    )
                    current = project_confirmed_record(record, "meal")
                    if "source_version" not in ref:
                        if (record.version or confirmation.draft_version) != confirmation.draft_version:
                            raise ValueError("旧版工具来源已更正")
                        current.pop("source_version", None)
                    expected.append(current)
                if payload != {
                    "records": expected,
                    "full_health_profile_available": False,
                    "personal_meal_plan_available": False,
                }:
                    raise ValueError("历史来源已变化")
            except (KeyError, TypeError, ValueError, AttributeError):
                raise HealthVisionError("source_invalidated", "历史饮食引用已更正，请重新进入咨询", 410) from None

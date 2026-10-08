"""对话选餐、不可变写入来源及历史结果的当前有效性查询。"""

import json

from sqlalchemy import and_, or_, select

from yuxi.repositories.health_diet_analysis_repository import HealthDietAnalysisRepository
from yuxi.repositories.health_meal_feedback_repository import HealthMealFeedbackRepository
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.storage.postgres.models_business import AgentRun, Message, TOOL_AUDIT_MESSAGE_TYPE
from yuxi.storage.postgres.models_health import HealthFeedbackConversation, HealthFeedbackWrite, MealFeedbackRevision


class HealthDialogFeedbackRepository:
    """成员及执行授权由调用用例持有，来源查询不再次进入咨询授权。"""

    def __init__(self, session):
        self.session = session

    async def selection(self, binding):
        """冻结来源不能由模型选择或客户端metadata替换。"""
        return await self.session.get(HealthFeedbackConversation, binding.conversation_id)

    async def source(self, uid, binding, selection):
        """每次读取、写入和发布都复核选定确认版本。"""
        return await HealthDietAnalysisRepository(self.session).source(
            uid, binding.member_id, selection.diet_log_id, selection.source_version
        )

    async def write(self, conversation_id):
        """每个选餐会话最多保存一个写入请求，后续修改重新进入。"""
        return await self.session.scalar(
            select(HealthFeedbackWrite).where(HealthFeedbackWrite.conversation_id == conversation_id)
        )

    async def result(self, uid, binding, selection, write):
        """从不可变修订和当前反馈共同投影，旧版本禁止作为现有结果。"""
        from yuxi.services.health_meal_feedback_service import feedback_result

        await self.source(uid, binding, selection)
        revision = await self.session.get(MealFeedbackRevision, write.revision_id)
        feedback = await HealthMealFeedbackRepository(self.session).slot(uid, selection.diet_log_id)
        source = await self.session.get(Message, write.source_message_id, populate_existing=True)
        run = await self.session.get(AgentRun, write.run_id)
        if (
            revision is None
            or revision.actor_uid != uid
            or feedback is None
            or revision.feedback_id != feedback.id
            or feedback.member_id != binding.member_id
            or feedback.status != "active"
            or feedback.version != revision.version
            or feedback.details != revision.details
            or source is None
            or run is None
            or run.uid != uid
            or run.conversation_id != binding.conversation_id
            or source.conversation_id != binding.conversation_id
            or source.request_id != run.request_id
            or source.role != "user"
            or not source.content.strip().startswith(("记录这餐反馈：", "更新这餐反馈："))
            or source.content.strip().split("：", 1)[1].strip() != revision.details["comment"]
        ):
            raise HealthVisionError("source_invalidated", "餐后反馈已修改或撤回，请重新选择餐次", 410)
        return {
            "result_type": "meal_feedback",
            "status": "saved",
            "scope": "single_meal_feedback",
            "records": [{"record_id": selection.diet_log_id, "source_version": selection.source_version}],
            "feedback": feedback_result(feedback),
            "source_message_id": write.source_message_id,
            "source_run_id": write.run_id,
            "nutrition_recalculated": False,
        }

    async def validate_history(self, uid, binding, selection):
        """成功写入工具与最终结果均受当前反馈版本约束。"""
        await self.source(uid, binding, selection)
        write = await self.write(binding.conversation_id)
        current = await self.result(uid, binding, selection, write) if write else None
        rows = await self.session.scalars(
            select(Message)
            .join(AgentRun, AgentRun.id == Message.run_id)
            .where(
                AgentRun.conversation_id == binding.conversation_id,
                or_(
                    and_(AgentRun.status == "completed", AgentRun.output_message_id == Message.id),
                    and_(
                        Message.message_type == TOOL_AUDIT_MESSAGE_TYPE,
                        Message.execution_status == "completed",
                        Message.extra_metadata["tool_name"].as_string() == "record_selected_meal_feedback",
                    ),
                ),
            )
        )
        for message in rows:
            try:
                payload = json.loads(message.content)
                if payload["status"] == "needs_input":
                    if payload["records"] != [
                        {"record_id": selection.diet_log_id, "source_version": selection.source_version}
                    ]:
                        raise ValueError("提问来源不符")
                elif current is None or payload != current:
                    raise ValueError("反馈结果不符")
            except (KeyError, TypeError, ValueError):
                raise HealthVisionError("source_invalidated", "历史反馈来源无法核对", 410) from None

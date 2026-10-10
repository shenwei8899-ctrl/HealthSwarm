"""健康任务只读取当前请求的执行Owner与权威最终消息。"""

from yuxi.repositories.agent_run_output_repository import AgentRunOutputRepository
from yuxi.repositories.agent_run_repository import AgentRunRepository
from yuxi.repositories.agent_run_request_repository import AgentRunRequestRepository
from yuxi.repositories.health_consultation_repository import HEALTH_AGENT_BACKENDS, HealthConsultationRepository
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.storage.postgres.models_business import AUDIT_MESSAGE_TYPES, Conversation


class HealthTaskRepository:
    """复用既有持久化结果，不引入健康任务状态。"""

    def __init__(self, session):
        """读取与来源复核共用事务。"""
        self.session = session

    async def request_context(self, uid, request_id):
        """先重验当前成员权限，再核对 Request 与线程固定角色。"""
        request = await AgentRunRequestRepository(self.session).get_by_request_id(request_id)
        if request is None or request.uid != uid or request.agent_slug not in HEALTH_AGENT_BACKENDS:
            raise HealthVisionError("not_found", "健康任务不存在或无权访问", 404)
        binding = await HealthConsultationRepository(self.session).authorize(
            uid, request.conversation_thread_id, lock=True, preview_history=True
        )
        conversation = await self.session.get(Conversation, binding.conversation_id)
        if conversation.agent_id != request.agent_slug or binding.actor_uid != uid:
            raise HealthVisionError("source_invalidated", "健康任务与固定角色绑定不符", 410)
        run = None
        if request.dispatched_run_id is not None:
            run = await AgentRunRepository(self.session).get_run(request.dispatched_run_id)
            if (
                run is None
                or run.uid != uid
                or run.request_id != request.request_id
                or run.agent_slug != request.agent_slug
                or run.conversation_id != binding.conversation_id
                or run.conversation_thread_id != request.conversation_thread_id
                or run.run_type != "chat"
            ):
                raise HealthVisionError("source_invalidated", "健康任务执行关联无法核对", 410)
        elif request.status == "dispatched":
            raise HealthVisionError("source_invalidated", "已派发任务缺少执行关联", 410)
        return request, binding, run

    async def final_message(self, run):
        """只认同 Run、Request 的完成正文指针，拒绝猜测性兼容读取。"""
        if run.output_message_id is None or run.conversation_id is None:
            raise HealthVisionError("answer_unavailable", "健康任务缺少权威最终结果", 409)
        message = await AgentRunOutputRepository(self.session).get_output_message(
            run_id=run.id,
            conversation_id=run.conversation_id,
            output_message_id=run.output_message_id,
            allow_legacy_fallback=False,
        )
        if (
            message is None
            or message.request_id != run.request_id
            or message.message_type in AUDIT_MESSAGE_TYPES
            or message.delivery_status != "complete"
        ):
            raise HealthVisionError("answer_unavailable", "健康任务缺少有效最终结果", 409)
        return message

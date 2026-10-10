"""普通配餐完成结果到用户显式次日提议的事务桥接。"""

import json

from pydantic import ValidationError

from yuxi.repositories.agent_run_repository import AgentRunRepository
from yuxi.repositories.health_consultation_repository import PLANNER_SLUG
from yuxi.repositories.health_plan_adoption_repository import HealthPlanAdoptionRepository
from yuxi.repositories.health_task_repository import HealthTaskRepository
from yuxi.services.health_consultation_service import require_consultation
from yuxi.services.health_next_day_agent_types import AgentNextDayProposalInput
from yuxi.services.health_plan_adoption_service import create_next_day_proposal_in_session
from yuxi.services.health_task_service import validate_task_business_result
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.storage.postgres.manager import pg_manager


async def create_agent_next_day_proposal(uid: str, member_id: str, run_id: str, data: AgentNextDayProposalInput):
    """只登记用户选中且当前有效的普通单成员明日回执。"""
    async with pg_manager.get_async_session_context() as session:
        # 幂等锁在成员锁之前取得，与原提议入口保持相同锁序。
        await HealthPlanAdoptionRepository(session).lock_request(uid, str(data.client_request_id), proposal=True)
        repo = HealthTaskRepository(session)
        request, binding, run = await repo.request_context(uid, data.request_id)
        if request.agent_slug != PLANNER_SLUG or binding.member_id != member_id:
            raise HealthVisionError("not_found", "普通成员配餐任务不存在或无权访问", 404)
        if run is None:
            raise HealthVisionError("answer_not_completed", "须选择已完成的配餐运行", 409)
        if run.id != run_id:
            raise HealthVisionError("request_run_conflict", "所选运行不属于当前请求", 409)
        # 活跃 Worker 工具按 Run→Member 加锁；持成员锁时不等待其 Run 锁。
        if run.status != "completed":
            raise HealthVisionError("answer_not_completed", "须选择已完成的配餐运行", 409)
        if any(
            selection is not None
            for selection in (
                binding.initial_planner_selection,
                binding.family_planner_selection,
                binding.safe_planner_selection,
            )
        ):
            raise HealthVisionError("planner_mode_not_supported", "此入口仅登记普通单成员明日预览", 409)
        # request_context 已锁成员，随后锁 Run 固定当前终态和正文指针。
        run = await AgentRunRepository(session).lock_run_for_user(run.id, uid)
        if run is None:
            raise HealthVisionError("not_found", "配餐运行不存在或无权访问", 404)
        await session.refresh(run)
        if run.status != "completed":
            raise HealthVisionError("answer_not_completed", "须选择已完成的配餐运行", 409)
        message = await repo.final_message(run)
        if message.id != data.final_message_id:
            raise HealthVisionError("answer_unavailable", "所选消息不是当前运行的最终结果", 409)
        processing = (run.input_payload or {}).get("health_processing")
        if not isinstance(processing, dict):
            raise HealthVisionError("policy_changed", "配餐运行缺少处理审批快照", 409)
        current_binding, _ = await require_consultation(
            session, uid, run.conversation_thread_id, expected=processing, lock=True
        )
        if current_binding.conversation_id != run.conversation_id or current_binding.member_id != member_id:
            raise HealthVisionError("source_invalidated", "配餐运行的成员来源绑定已变化", 410)
        try:
            payload = json.loads(message.content)
            if not isinstance(payload, dict):
                raise ValueError("配餐结果不是业务对象")
            if payload.get("preview_id") != str(data.preview_id):
                raise HealthVisionError("planner_receipt_invalid", "须选择当前完成结果中的预览回执", 409)
            await validate_task_business_result(session, run, current_binding, payload, message.content)
        except (ValueError, TypeError, KeyError, ValidationError):
            raise HealthVisionError("source_invalidated", "配餐结果或预览来源无法核对", 410) from None
        origin = {"agent_run_id": run.id, "request_id": run.request_id, "final_message_id": message.id}
        result = await create_next_day_proposal_in_session(session, uid, member_id, data, agent_origin=origin)
        return {**result, **origin}

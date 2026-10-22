"""用户确认的最小跨角色交接；源任务与目标用途分别校验。"""

from copy import deepcopy
from typing import Literal
from uuid import UUID

from pydantic import Field

from yuxi.repositories.health_consultation_repository import (
    ANALYST_SLUG,
    CONSULTATION_SLUG,
    GLUCOSE_SLUG,
    LIPIDS_SLUG,
    PRESSURE_SLUG,
    PLANNER_SLUG,
)
from yuxi.repositories.health_task_repository import HealthTaskRepository
from yuxi.repositories.agent_run_request_repository import AgentRunRequestRepository
from yuxi.services.health_vision_types import HealthDTO, HealthVisionError, ConsultationInput
from yuxi.services.health_nutrition_service import input_fingerprint
from yuxi.storage.postgres.manager import pg_manager

TARGETS = {
    GLUCOSE_SLUG: CONSULTATION_SLUG,
    LIPIDS_SLUG: CONSULTATION_SLUG,
    PRESSURE_SLUG: CONSULTATION_SLUG,
    ANALYST_SLUG: PLANNER_SLUG,
}


class HandoffConfirmation(HealthDTO):
    """确认只接受当前服务端预览摘要，不接受客户端健康正文或任意目标。"""

    client_request_id: UUID
    source_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    confirmed: Literal[True]


async def preview_handoff(uid, request_id):
    """读取最小摘要不会创建会话或向模型发送内容。"""
    async with pg_manager.get_async_session_context() as session:
        return await handoff_source_in_session(session, uid, request_id)


async def confirm_handoff(uid, request_id, data):
    """创建与来源复验由同一会话事务执行，确认不派发模型请求。"""
    from yuxi.services.health_consultation_service import create_consultation

    preview = await preview_handoff(uid, request_id)
    return await create_consultation(
        uid,
        preview["member_id"],
        ConsultationInput(client_request_id=data.client_request_id),
        agent_slug=preview["target_agent"],
        handoff_selection={"source_request_id": request_id, "source_hash": data.source_hash},
    )


async def handoff_source_in_session(session, uid, request_id):
    """仅接受独立源角色的有效完成结果，拒绝交接环和模型自由摘要。"""
    from yuxi.services.health_task_service import read_health_task_in_session
    from yuxi.services.health_indicator_review_service import read_indicator_in_session

    requested = await AgentRunRequestRepository(session).get_by_request_id(request_id)
    if requested is None or requested.uid != uid:
        raise HealthVisionError("not_found", "来源任务不存在或无权访问", 404)
    if requested.agent_slug not in TARGETS:
        raise HealthVisionError("handoff_not_supported", "该角色不支持作为交接来源", 409)
    request, binding, run = await HealthTaskRepository(session).request_context(uid, request_id)
    target = TARGETS.get(request.agent_slug)
    if target is None or getattr(binding, "handoff_selection", None) is not None:
        raise HealthVisionError("handoff_not_supported", "该角色或交接来源不支持继续交接", 409)
    task = await read_health_task_in_session(session, uid, request_id)
    if run is None or task.execution_status != "completed" or task.result is None:
        raise HealthVisionError("handoff_source_not_ready", "请等待来源任务有效完成后再交接", 409)
    if request.agent_slug == ANALYST_SLUG:
        if task.result.result_type != "diet_analysis":
            raise HealthVisionError("handoff_source_not_ready", "需要已核对饮食记录的分析结果", 409)
        payload = task.result.data
        # 不复制自由反馈或建议，仅传递已验证的记录版本、计算值和覆盖边界。
        summary = {
            k: deepcopy(payload[k])
            for k in (
                "scope",
                "records",
                "meal_type",
                "eaten_at",
                "window",
                "nutrition",
                "coverage",
            )
            if k in payload
        }
        summary["notice"] = "已记录饮食事实仅作参考；配餐仍需当前已发布菜谱和规则，不据此推定个人目标。"
    else:
        kind = request.agent_slug.removeprefix("health-").replace("-", "_")
        receipt = await HealthTaskRepository(session).indicator_receipt(run.id, kind)
        facts = await read_indicator_in_session(
            session,
            uid,
            binding.member_id,
            kind,
            binding.indicator_selection,
            period={
                "start_date": receipt.start_date.isoformat(),
                "end_date": receipt.end_date.isoformat(),
                "timezone": "Asia/Shanghai",
            },
        )
        if receipt.payload_hash != facts["source_hash"]:
            raise HealthVisionError("source_invalidated", "原任务实测范围或记录已变化", 410)
        summary = {k: deepcopy(facts[k]) for k in ("kind", "period", "records", "truncated") if k in facts}
        summary["kind"] = kind
        summary["notice"] = "仅解释所选指标事实与一般科普；不推断诊断，不生成正式个体化建议。"
    source_hash = input_fingerprint(
        {
            "task": task.model_dump(mode="json"),
            "summary": summary,
            "target_agent": target,
        }
    )
    return {
        "source_request_id": request_id,
        "source_run_id": run.id,
        "source_message_id": task.final_message_id,
        "source_agent": request.agent_slug,
        "member_id": binding.member_id,
        "target_agent": target,
        "target_purpose": "meal_plan" if target == PLANNER_SLUG else "consultation",
        "source_hash": source_hash,
        "summary": summary,
    }


async def validate_handoff_selection(session, uid, member_id, target_agent, selected):
    """确认、外发、恢复、历史与结果读取共用来源重验。"""
    if not isinstance(selected, dict) or not isinstance(selected.get("source_request_id"), str):
        raise HealthVisionError("source_invalidated", "交接来源无法核对", 410)
    source = await handoff_source_in_session(session, uid, selected["source_request_id"])
    if source["member_id"] != member_id or source["target_agent"] != target_agent:
        raise HealthVisionError("handoff_scope_mismatch", "交接成员或目标角色不匹配", 409)
    if source["source_hash"] != selected.get("source_hash"):
        raise HealthVisionError("source_invalidated", "来源已变化，请重新预览并确认交接", 410)
    return source

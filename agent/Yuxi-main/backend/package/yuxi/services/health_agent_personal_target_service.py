"""饮食分析师只读明确绑定的当前个人目标，不计算记录差额或趋势。"""

from copy import deepcopy

from pydantic import ValidationError

from yuxi.services.health_agent_personal_target_types import PersonalTargetBinding
from yuxi.services.health_nutrition_service import input_fingerprint
from yuxi.services.health_personal_target_service import personal_targets_in_session
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.storage.postgres.manager import pg_manager


def target_public_projection(current):
    """模型只读取已计算目标与来源，排除身体输入、公式及专业审核正文。"""
    return {
        "scope": "current_personal_targets",
        "status": "ready",
        "energy_kcal": current["energy_kcal"],
        "bounds": deepcopy(current["bounds"]),
        "units": deepcopy(current["units"]),
        "sources": deepcopy(current["sources"]),
        "source_hash": input_fingerprint(current),
        "professional_review": "not_a_professional_decision",
        "applied_to_record_window": False,
    }


async def target_context_in_session(session, uid, member_id, selected):
    """批准、适用性与计算沿用原Owner及调用方事务。"""
    current = await personal_targets_in_session(session, uid, member_id, selected)
    if current.get("status") != "ready":
        raise HealthVisionError("target_dependencies_not_ready", "当前批准个人目标尚未就绪", 503)
    return current


async def authorize_personal_target_binding(session, binding):
    """当前来源变化不回退或静默去掉目标，授权错误沿用原Owner。"""
    try:
        stored = PersonalTargetBinding.model_validate(getattr(binding, "personal_target_selection", None))
    except ValidationError:
        raise HealthVisionError("source_invalidated", "固定个人目标选择无法核对，请重新进入分析", 410) from None
    try:
        current = await target_context_in_session(session, binding.actor_uid, binding.member_id, stored.selection)
    except HealthVisionError as error:
        if error.code in {"source_version_conflict", "target_dependencies_not_ready"}:
            raise HealthVisionError("source_invalidated", "固定个人目标来源已变化，请重新进入分析", 410) from None
        raise
    if current.get("status") != "ready" or input_fingerprint(current) != stored.source_hash:
        raise HealthVisionError("source_invalidated", "固定个人目标来源已变化，请重新进入分析", 410)
    binding._personal_target_current = current
    return current


async def validate_personal_target_tool_payload(session, binding, payload):
    """合法来源ID不能授权篡改数字或附带原始身体数据。"""
    current = await authorize_personal_target_binding(session, binding)
    if payload != target_public_projection(current):
        raise HealthVisionError("source_invalidated", "历史个人目标投影无法核对，请重新进入分析", 410)


def attach_current_personal_targets(binding, result):
    """最终事实与当前目标并列；保持原分析未应用目标及不完整摄入边界。"""
    if getattr(binding, "personal_target_selection", None) is None:
        return result
    current = getattr(binding, "_personal_target_current", None)
    if current is None:
        raise HealthVisionError("source_invalidated", "固定个人目标未获当前授权", 410)
    return {**result, "current_personal_targets": target_public_projection(current)}


async def bound_personal_targets(context):
    """工具身份、选择和来源均从当前执行及PG绑定获得。"""
    from yuxi.services.health_diet_analysis_service import require_analyst_run

    async with pg_manager.get_async_session_context() as session:
        binding = await require_analyst_run(session, context)
        if getattr(binding, "personal_target_selection", None) is None:
            raise HealthVisionError("target_selection_required", "本线程没有用户选择的个人目标", 409)
        return target_public_projection(binding._personal_target_current)


async def is_personal_target_conversation(context):
    """构图资源取当前服务端绑定，不能依赖模型或用户传入的工具清单。"""
    from yuxi.services.health_diet_analysis_service import require_analyst_run

    async with pg_manager.get_async_session_context() as session:
        binding = await require_analyst_run(session, context, allow_feedback=True)
        return getattr(binding, "personal_target_selection", None) is not None

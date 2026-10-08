"""固定初始选择的全员同意、Run回执及最终发布复核。"""

import json
from copy import deepcopy
from uuid import uuid4

from pydantic import ValidationError
from sqlalchemy import select

from yuxi.repositories.health_consultation_repository import HealthConsultationRepository, PLANNER_SLUG
from yuxi.repositories.health_vision_repository import HealthVisionRepository
from yuxi.services.health_initial_meal_plan_service import (
    initial_catalog_in_session,
    initial_generation_in_session,
    initial_preview_result,
)
from yuxi.services.health_initial_meal_plan_types import InitialPlanSelection, INITIAL_PLANNER_TOOLS
from yuxi.services.health_meal_plan_types import PlannerAnswer
from yuxi.services.health_nutrition_service import input_fingerprint
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_business import AgentRun, Conversation
from yuxi.storage.postgres.models_health import HealthConsultation, HealthInitialPlanPreview


async def initial_planner_context_in_session(session, uid, anchor_id, selected):
    """全部参与者排序锁定并独立同意，再读取批准来源与实际目录。"""
    from yuxi.services.health_vision_service import health_vision_service

    health = HealthVisionRepository(session)
    ids = sorted(str(mid) for mid in selected.profile_versions)
    for mid in ids:
        for index, scope in enumerate(("ai_use", "diet_edit", "profile_view")):
            await health.authorize(mid, uid, scope, lock=index == 0)
    configured = await health_vision_service.configuration(session)
    approved = configured["meal_plan"]
    if not approved["available"]:
        raise HealthVisionError("consultation_unavailable", "配餐处理用途尚未审批", 503)
    processing = {
        "model": approved["model"],
        "processor": approved["processor"],
        "policy_version": configured["policy_version"],
    }
    for mid in ids:
        await health.require_consent(mid, uid, "meal_plan", processing)
    current, _, _, _ = await initial_catalog_in_session(session, uid, anchor_id, selected)
    if current["rules"]["status"] != "ready" or any(p["status"] != "ready" for p in current["profiles"].values()):
        raise HealthVisionError("initial_dependencies_not_ready", "全部营养安全投影与批准规则须先就绪", 503)
    if not current["rules"]["payload"].get("meal_generation"):
        raise HealthVisionError("initial_dependencies_not_ready", "初始配餐目录尚未批准", 503)
    return current


async def authorize_initial_planner_binding(session, binding):
    """初始历史与运行始终绑定同一全员选择，不能降为通用草稿。"""
    try:
        stored = binding.initial_planner_selection
        selected = InitialPlanSelection.model_validate(stored["selection"])
        current = await initial_planner_context_in_session(session, binding.actor_uid, binding.member_id, selected)
        if input_fingerprint(current["sources"]) != stored["source_hash"]:
            raise HealthVisionError("source_invalidated", "初始线程来源已变化，请重新选择", 410)
    except (ValidationError, KeyError, TypeError):
        raise HealthVisionError("source_invalidated", "初始线程选择无法核对", 410) from None
    except HealthVisionError as error:
        if error.code != "source_version_conflict":
            raise
        raise HealthVisionError("source_invalidated", "初始线程来源版本已变化，请重新选择", 410) from None
    binding._initial_planner_current = current
    return selected, current


def initial_context_result(binding):
    """只投影本事务核对的营养投影、批准规则和用户固定选择。"""
    current = binding._initial_planner_current
    return {
        "scope": "initial_plan",
        "member_id": binding.member_id,
        "member_ids": sorted(current["profiles"]),
        "selection": deepcopy(binding.initial_planner_selection["selection"]),
        **{k: deepcopy(current[k]) for k in ("profiles", "rules", "sources")},
        "full_health_profile_available": False,
        "professional_review": "not_a_professional_decision",
    }


def require_initial_binding(binding):
    """其它配餐模式不能调用固定初始工具。"""
    if binding.initial_planner_selection is None:
        raise HealthVisionError("initial_selection_required", "须从用户明确选定初始范围的入口创建线程", 409)


async def read_initial_context_for_run(context):
    """身份由当前worker注入，读取全体同意后的来源。"""
    from yuxi.services.health_meal_plan_service import require_planner_run

    async with pg_manager.get_async_session_context() as session:
        _, binding = await require_planner_run(session, context)
        require_initial_binding(binding)
        return initial_context_result(binding)


async def preview_initial_for_run(context):
    """执行固定选择的批准生成，只写本Run只读回执。"""
    from yuxi.services.health_meal_plan_service import require_planner_run

    async with pg_manager.get_async_session_context() as session:
        run, binding = await require_planner_run(session, context)
        require_initial_binding(binding)
        selected = InitialPlanSelection.model_validate(binding.initial_planner_selection["selection"])
        result = await initial_generation_in_session(session, context.uid, binding.member_id, selected)
        if result["sources"] != binding._initial_planner_current["sources"]:
            raise HealthVisionError("source_invalidated", "初始生成期间目录来源已变化", 410)
        await HealthConsultationRepository(session).require_attempt(context)
        preview = HealthInitialPlanPreview(
            id=str(uuid4()),
            actor_uid=context.uid,
            member_id=binding.member_id,
            conversation_id=binding.conversation_id,
            run_id=run.id,
            selection=selected.model_dump(mode="json"),
            snapshot=result,
        )
        session.add(preview)
        await session.flush()
        return initial_preview_result(preview)


async def validate_initial_receipt(session, binding, preview):
    """持久化身份、固定选择和完整结果在历史读取或发布前一致。"""
    selected = InitialPlanSelection.model_validate(binding.initial_planner_selection["selection"])
    if preview.member_id != binding.member_id or preview.selection != selected.model_dump(mode="json"):
        raise HealthVisionError("source_invalidated", "初始预览选择不属于固定线程", 410)
    current = await initial_generation_in_session(session, binding.actor_uid, binding.member_id, selected)
    if current != preview.snapshot:
        raise HealthVisionError("source_invalidated", "初始预览来源或内容已变化", 410)


async def initial_answer_in_session(session, run, binding, answer):
    """最终只能选择当前运行的真实回执，完整内容重新生成核对。"""
    if answer.questions:
        return {
            "scope": "initial_plan",
            "member_id": binding.member_id,
            "member_ids": sorted(binding._initial_planner_current["profiles"]),
            "status": "needs_input",
            "questions": answer.questions,
            "professional_review": "not_a_professional_decision",
        }
    preview = await session.get(HealthInitialPlanPreview, str(answer.preview_id))
    if (
        preview is None
        or preview.actor_uid != run.uid
        or preview.run_id != run.id
        or preview.conversation_id != binding.conversation_id
    ):
        raise HealthVisionError("planner_receipt_invalid", "初始预览回执不属于当前运行", 409)
    await validate_initial_receipt(session, binding, preview)
    return initial_preview_result(preview)


async def validate_initial_planner_publication(session, run, text):
    """Message发布事务复核全员同意、当前来源及服务器完整结果。"""
    from yuxi.services.health_consultation_service import require_consultation

    stored = await session.scalar(
        select(HealthConsultation).where(HealthConsultation.conversation_id == run.conversation_id)
    )
    processing = (run.input_payload or {}).get("health_processing")
    if (stored is None or stored.initial_planner_selection is None) and not (
        isinstance(processing, dict) and processing.get("initial_selection_hash")
    ):
        return
    if not isinstance(processing, dict) or not processing.get("initial_selection_hash"):
        raise HealthVisionError("policy_changed", "初始运行缺少固定选择的处理审批快照", 409)
    binding, _ = await require_consultation(
        session, run.uid, run.conversation_thread_id, expected=processing, lock=True
    )
    if binding.initial_planner_selection is None or binding.conversation_id != run.conversation_id:
        raise HealthVisionError("source_invalidated", "初始运行绑定已变化", 410)
    try:
        payload = json.loads(text)
        answer = PlannerAnswer(preview_id=payload.get("preview_id"), questions=payload.get("questions", []))
    except (ValueError, TypeError):
        raise HealthVisionError("planner_output_invalid", "初始待发布结果无法解析", 409) from None
    if await initial_answer_in_session(session, run, binding, answer) != payload:
        raise HealthVisionError("source_invalidated", "初始待发布结果与当前服务器回执不符", 410)


async def validate_initial_planner_tool_payload(session, binding, name, payload):
    """checkpoint只接纳本线程真实历史Run回执，并重查完整来源。"""
    if name == INITIAL_PLANNER_TOOLS[0]:
        if payload != initial_context_result(binding):
            raise HealthVisionError("source_invalidated", "初始上下文历史已变化", 410)
        return
    try:
        preview = await session.get(HealthInitialPlanPreview, str(payload["preview_id"]))
        if (
            preview is None
            or preview.actor_uid != binding.actor_uid
            or preview.conversation_id != binding.conversation_id
        ):
            raise HealthVisionError("source_invalidated", "初始checkpoint回执身份不符", 410)
        original = await session.get(AgentRun, preview.run_id)
        conversation = await session.get(Conversation, binding.conversation_id)
        processing = (original.input_payload or {}).get("health_processing") if original is not None else None
        if (
            original is None
            or original.uid != binding.actor_uid
            or original.agent_slug != PLANNER_SLUG
            or original.conversation_id != binding.conversation_id
            or conversation is None
            or original.conversation_thread_id != conversation.thread_id
            or not isinstance(processing, dict)
            or processing.get("initial_selection_hash") != input_fingerprint(binding.initial_planner_selection)
        ):
            raise HealthVisionError("source_invalidated", "初始checkpoint所属运行或选择不符", 410)
        await validate_initial_receipt(session, binding, preview)
        if payload != initial_preview_result(preview):
            raise HealthVisionError("source_invalidated", "初始checkpoint完整结果已变化", 410)
    except (ValidationError, KeyError, TypeError):
        raise HealthVisionError("source_invalidated", "初始checkpoint无法核对", 410) from None

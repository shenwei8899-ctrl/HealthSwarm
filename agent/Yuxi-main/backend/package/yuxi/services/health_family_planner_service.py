"""固定家庭范围的当前来源、只读工具收据和发布复核。"""

import json
from copy import deepcopy
from types import SimpleNamespace
from uuid import uuid4

from pydantic import ValidationError
from sqlalchemy import select

from yuxi.repositories.health_quality_repository import HealthQualityRepository
from yuxi.repositories.health_vision_repository import HealthVisionRepository
from yuxi.services.health_family_meal_plan_types import (
    FamilySafeSelection,
    FamilySafeSwapSelection,
    FamilyParticipationSelection,
    plan_member_ids,
)
from yuxi.services.health_family_planner_types import (
    FamilyPlannerSelection,
    FamilySwapParameters,
    FamilyParticipationParameters,
)
from yuxi.services.health_family_safe_plan_service import family_safe_preview_in_session, require_family_plan
from yuxi.services.health_family_participation_service import participation_preview_in_session
from yuxi.services.health_meal_plan_types import PlannerAnswer
from yuxi.services.health_nutrition_service import input_fingerprint
from yuxi.services.health_quality_service import quality_context_in_session, quality_snapshot
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_health import HealthMealPlan, HealthFamilyPlannerPreview
from yuxi.storage.postgres.models_health import HealthConsultation
from yuxi.storage.postgres.models_business import AgentRun, Conversation
from yuxi.repositories.health_consultation_repository import PLANNER_SLUG


async def family_planner_context_in_session(session, uid, anchor_id, selected):
    """全范围排序授权锁、独立同意及固定来源在同一事务内核对。"""
    from yuxi.services.health_vision_service import health_vision_service

    plan = await session.scalar(
        select(HealthMealPlan).where(
            HealthMealPlan.id == str(selected.plan_id),
            HealthMealPlan.actor_uid == uid,
            HealthMealPlan.member_id == anchor_id,
        )
    )
    if plan is None:
        raise HealthVisionError("not_found", "家庭餐单不存在或无权访问", 404)
    require_family_plan(plan)
    ids = sorted(str(m) for m in selected.profile_versions)
    if not set(plan_member_ids(anchor_id, plan.spec)) <= set(ids):
        raise HealthVisionError("family_members_required", "须明确选择全部原参与者的当前档案版本", 409)
    health = HealthVisionRepository(session)
    for member_id in ids:
        for index, scope in enumerate(("ai_use", "diet_edit", "profile_view")):
            await health.authorize(member_id, uid, scope, lock=index == 0)
    # 等待成员锁期间计划可被改版；在质量Owner读取当前参与者前拒绝扩张锁集合。
    await session.refresh(plan)
    if plan.version != selected.version or not set(plan_member_ids(anchor_id, plan.spec)) <= set(ids):
        raise HealthVisionError("source_invalidated", "家庭餐单版本或参与范围已变化，请重新选择", 410)
    configuration = await health_vision_service.configuration(session)
    approved = configuration["meal_plan"]
    if not approved["available"]:
        raise HealthVisionError("consultation_unavailable", "配餐处理用途尚未审批或配置已变化", 503)
    processing = {
        "model": approved["model"],
        "processor": approved["processor"],
        "policy_version": configuration["policy_version"],
    }
    for member_id in ids:
        await health.require_consent(member_id, uid, "meal_plan", processing)
    quality = HealthQualityRepository(session)
    await quality.lock_profile_sources(ids)
    current = await quality_context_in_session(
        session,
        uid,
        SimpleNamespace(plan_id=str(selected.plan_id), plan_version=selected.version, rule_code=selected.rule_code),
    )
    # 全部当前参与者已持锁；质量Owner仍复核计划版本和当前来源。
    if not set(current["profiles"]) <= set(ids):
        raise HealthVisionError("source_invalidated", "家庭参与范围已变化，请重新选择", 410)
    for member_id in ids:
        if member_id not in current["profiles"]:
            profile = await quality.profile_projection(member_id)
            current["profiles"][member_id] = profile
            current["sources"]["profiles"][member_id] = {
                k: profile[k] for k in ("id", "version", "content_hash", "status", "reason")
            }
    if current["rules"]["status"] != "ready" or any(p["status"] != "ready" for p in current["profiles"].values()):
        raise HealthVisionError("family_dependencies_not_ready", "全部选定档案及批准规则须先就绪", 503)
    if current["rules"]["version"] != selected.rule_version or {
        str(m): version for m, version in selected.profile_versions.items()
    } != {m: profile["version"] for m, profile in current["profiles"].items()}:
        raise HealthVisionError("source_invalidated", "选定档案或规则版本已变化，请重新选择", 410)
    current["plan_spec"] = deepcopy(plan.spec)
    return current


async def authorize_family_planner_binding(session, binding):
    """私有历史和运行授权共同验证持久化家庭选择，不能降为单成员。"""
    try:
        stored = binding.family_planner_selection
        selected = FamilyPlannerSelection.model_validate(stored["selection"])
        current = await family_planner_context_in_session(session, binding.actor_uid, binding.member_id, selected)
        if input_fingerprint(current["sources"]) != stored["source_hash"]:
            raise HealthVisionError("source_invalidated", "家庭选择来源已变化，请重新选择", 410)
    except (ValidationError, KeyError, TypeError):
        raise HealthVisionError("source_invalidated", "家庭线程选择无法核对", 410) from None
    binding._family_planner_current = current
    return selected, current


def family_context_result(binding):
    """只投影已在当前事务核对的全部选定来源和逐人检查。"""
    current = binding._family_planner_current
    return {
        "scope": "family_saved_plan",
        "member_id": binding.member_id,
        "member_ids": sorted(current["profiles"]),
        "selection": deepcopy(binding.family_planner_selection["selection"]),
        "plan_spec": deepcopy(current["plan_spec"]),
        "plan_snapshot": deepcopy(current["plan_snapshot"]),
        "profiles": deepcopy(current["profiles"]),
        "rules": deepcopy(current["rules"]),
        "sources": deepcopy(current["sources"]),
        "safety_check": quality_snapshot(current)["safety_check"],
        "professional_review": "not_a_professional_decision",
    }


async def read_family_context_for_run(context):
    """固定工具读取全体同意后的当前方案及档案，身份由worker注入。"""
    from yuxi.services.health_meal_plan_service import require_planner_run

    async with pg_manager.get_async_session_context() as session:
        _, binding = await require_planner_run(session, context)
        require_family_binding(binding)
        return family_context_result(binding)


def require_family_binding(binding):
    """单成员线程不能调用家庭工具或接受家庭身份参数。"""
    if binding.family_planner_selection is None:
        raise HealthVisionError("family_selection_required", "请从明确选择全部家庭成员的入口创建线程", 409)


async def family_preview_in_session(session, binding, operation, parameters):
    """来源版本只从线程取得，复用原家庭业务Owner且不写正式事实。"""
    selected = FamilyPlannerSelection.model_validate(binding.family_planner_selection["selection"])
    current = binding._family_planner_current
    values = selected.model_dump(mode="json", exclude={"plan_id"})
    members = set(current["plan_snapshot"]["members"])
    if operation == "participation":
        parameters = FamilyParticipationParameters.model_validate(parameters).model_dump(mode="json")
        members = {p for m in parameters["allocations"] for p in m["participant_ids"]}
        if not members <= set(current["profiles"]):
            raise HealthVisionError("family_member_not_selected", "不能添加线程未明确选定的成员", 409)
        values["profile_versions"] = {m: values["profile_versions"][m] for m in members}
        data = FamilyParticipationSelection.model_validate({**values, **parameters})
        _, _, result = await participation_preview_in_session(session, binding.actor_uid, str(selected.plan_id), data)
    else:
        values["profile_versions"] = {m: values["profile_versions"][m] for m in members}
        if operation == "swap":
            parameters = FamilySwapParameters.model_validate(parameters).model_dump(mode="json")
            data = FamilySafeSwapSelection.model_validate({**values, **parameters})
        elif operation == "regeneration" and parameters == {}:
            data = FamilySafeSelection.model_validate(values)
        else:
            raise HealthVisionError("planner_receipt_invalid", "家庭预览操作或参数无法核对", 409)
        _, result = await family_safe_preview_in_session(
            session, binding.actor_uid, str(selected.plan_id), data, swap=operation == "swap"
        )
    return parameters, result


def family_preview_result(binding, preview):
    """回执的全部结果由服务器投影，明确家庭范围和预览操作。"""
    return {
        "preview_id": preview.id,
        "scope": "family_saved_plan",
        "member_id": binding.member_id,
        "member_ids": sorted(binding._family_planner_current["profiles"]),
        "operation": preview.operation,
        "result": deepcopy(preview.snapshot),
    }


async def preview_family_for_run(context, operation, parameters):
    """只保存本运行只读预览收据，不保存计划、检查、采用或饮食。"""
    from yuxi.services.health_meal_plan_service import require_planner_run

    async with pg_manager.get_async_session_context() as session:
        run, binding = await require_planner_run(session, context)
        require_family_binding(binding)
        parameters, snapshot = await family_preview_in_session(session, binding, operation, parameters)
        from yuxi.repositories.health_consultation_repository import HealthConsultationRepository

        # 候选搜索也可能耗时；在回执写入边界重新检查已锁定Run的当前有效租约。
        await HealthConsultationRepository(session).require_attempt(context)
        receipt = HealthFamilyPlannerPreview(
            id=str(uuid4()),
            actor_uid=context.uid,
            conversation_id=binding.conversation_id,
            run_id=run.id,
            operation=operation,
            parameters=parameters,
            snapshot=snapshot,
        )
        session.add(receipt)
        await session.flush()
        return family_preview_result(binding, receipt)


async def family_answer_in_session(session, run, binding, answer):
    """最终只选择当前Run回执或澄清问题，重算原参数核对全部结果。"""
    if answer.questions:
        return {
            "scope": "family_saved_plan",
            "member_id": binding.member_id,
            "member_ids": sorted(binding._family_planner_current["profiles"]),
            "status": "needs_input",
            "questions": answer.questions,
            "professional_review": "not_a_professional_decision",
        }
    preview = await session.get(HealthFamilyPlannerPreview, str(answer.preview_id))
    if (
        preview is None
        or preview.actor_uid != run.uid
        or preview.run_id != run.id
        or preview.conversation_id != binding.conversation_id
    ):
        raise HealthVisionError("planner_receipt_invalid", "家庭预览回执不属于当前运行", 409)
    _, current = await family_preview_in_session(session, binding, preview.operation, preview.parameters)
    if current != preview.snapshot:
        raise HealthVisionError("source_invalidated", "家庭预览来源或结果已变化，请重新生成", 410)
    return family_preview_result(binding, preview)


async def validate_family_planner_publication(session, run, text):
    """Message发布事务重新检查全员权限、同意及预览完整内容。"""
    from yuxi.services.health_consultation_service import require_consultation

    stored = await session.scalar(
        select(HealthConsultation).where(HealthConsultation.conversation_id == run.conversation_id)
    )
    processing = (run.input_payload or {}).get("health_processing")
    if (stored is None or stored.family_planner_selection is None) and not (
        isinstance(processing, dict) and processing.get("family_selection_hash")
    ):
        return
    if not isinstance(processing, dict) or not processing.get("family_selection_hash"):
        raise HealthVisionError("policy_changed", "家庭运行缺少固定选择的处理审批快照", 409)
    binding, _ = await require_consultation(
        session,
        run.uid,
        run.conversation_thread_id,
        expected=processing,
        lock=True,
    )
    if binding.family_planner_selection is None or binding.conversation_id != run.conversation_id:
        raise HealthVisionError("source_invalidated", "家庭运行绑定已变化", 410)
    try:
        payload = json.loads(text)
        answer = PlannerAnswer(preview_id=payload.get("preview_id"), questions=payload.get("questions", []))
    except (ValueError, TypeError):
        raise HealthVisionError("planner_output_invalid", "家庭待发布结果无法解析", 409) from None
    if await family_answer_in_session(session, run, binding, answer) != payload:
        raise HealthVisionError("source_invalidated", "家庭待发布结果与当前服务器回执不符", 410)


async def validate_family_planner_tool_payload(session, binding, name, payload):
    """checkpoint仅接受同线程的真实历史回执，并重验当前全体来源。"""
    if name == "get_family_plan_context":
        if payload != family_context_result(binding):
            raise HealthVisionError("source_invalidated", "家庭上下文历史已变化", 410)
        return
    expected_operation = {
        "preview_family_plan_swap": "swap",
        "preview_family_plan_regeneration": "regeneration",
        "preview_family_plan_participation": "participation",
    }[name]
    try:
        preview = await session.get(HealthFamilyPlannerPreview, str(payload["preview_id"]))
        if (
            preview is None
            or preview.actor_uid != binding.actor_uid
            or preview.conversation_id != binding.conversation_id
            or preview.operation != expected_operation
        ):
            raise HealthVisionError("source_invalidated", "家庭checkpoint回执身份不符", 410)
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
            or processing.get("family_selection_hash") != input_fingerprint(binding.family_planner_selection)
        ):
            raise HealthVisionError("source_invalidated", "家庭checkpoint所属运行身份或选择不符", 410)
        _, current = await family_preview_in_session(session, binding, preview.operation, preview.parameters)
        if current != preview.snapshot or payload != family_preview_result(binding, preview):
            raise HealthVisionError("source_invalidated", "家庭checkpoint预览结果已变化", 410)
    except (ValidationError, KeyError, TypeError):
        raise HealthVisionError("source_invalidated", "家庭checkpoint无法核对", 410) from None

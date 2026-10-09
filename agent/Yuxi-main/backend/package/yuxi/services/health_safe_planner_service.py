"""单成员安全改版的固定来源、只读回执和发布边界。"""

import json
from copy import deepcopy
from types import SimpleNamespace
from uuid import uuid4

from pydantic import ValidationError
from sqlalchemy import and_, or_, select

from yuxi.repositories.health_consultation_repository import HealthConsultationRepository, PLANNER_SLUG
from yuxi.repositories.health_quality_repository import HealthQualityRepository
from yuxi.repositories.health_vision_repository import HealthVisionRepository
from yuxi.services.health_meal_plan_types import (
    MealPlanSpec,
    PlannerAnswer,
    SafeRegenerationSelection,
    SafeSwapSelection,
)
from yuxi.services.health_nutrition_service import input_fingerprint
from yuxi.services.health_quality_service import quality_context_in_session, quality_snapshot
from yuxi.services.health_safe_meal_swap_service import candidates_in_session
from yuxi.services.health_safe_plan_regeneration_service import regeneration_in_session
from yuxi.services.health_safe_planner_types import SafePlannerSelection, SafeSwapParameters
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_business import AgentRun, Conversation, Message, TOOL_AUDIT_MESSAGE_TYPE
from yuxi.storage.postgres.models_health import HealthConsultation, HealthMealPlan, HealthSafePlannerPreview


async def safe_planner_context_in_session(session, uid, member_id, selected):
    """成员授权和同意先于专业来源读取，锁序沿用质量Owner。"""
    from yuxi.services.health_vision_service import health_vision_service

    plan = await session.scalar(
        select(HealthMealPlan).where(
            HealthMealPlan.id == str(selected.plan_id),
            HealthMealPlan.actor_uid == uid,
            HealthMealPlan.member_id == member_id,
        )
    )
    _require_single_selected_plan(plan, uid, member_id)
    health = HealthVisionRepository(session)
    for index, scope in enumerate(("ai_use", "diet_edit", "profile_view")):
        await health.authorize(member_id, uid, scope, lock=index == 0)
    # 等待成员锁时原对象可能改版；拒绝家庭扩张后再交质量Owner锁来源。
    await session.refresh(plan)
    _require_single_selected_plan(plan, uid, member_id)
    if plan.version != selected.version:
        raise HealthVisionError("source_invalidated", "餐单版本已变化，请重新选择", 410)
    configuration = await health_vision_service.configuration(session)
    approved = configuration["meal_plan"]
    if not approved["available"]:
        raise HealthVisionError("consultation_unavailable", "配餐处理用途尚未审批或配置已变化", 503)
    processing = {
        "model": approved["model"],
        "processor": approved["processor"],
        "policy_version": configuration["policy_version"],
    }
    await health.require_consent(member_id, uid, "meal_plan", processing)
    await HealthQualityRepository(session).lock_profile_sources([member_id])
    current = await quality_context_in_session(
        session,
        uid,
        SimpleNamespace(plan_id=str(selected.plan_id), plan_version=selected.version, rule_code=selected.rule_code),
    )
    if current["member_id"] != member_id or "profiles" in current:
        raise HealthVisionError("source_invalidated", "餐单成员范围已变化，请重新选择", 410)
    if current["profile"]["status"] != "ready" or current["rules"]["status"] != "ready":
        raise HealthVisionError("safe_dependencies_not_ready", "选定专业档案及批准规则须先就绪", 503)
    if (
        current["profile"]["version"] != selected.profile_version
        or current["rules"]["version"] != selected.rule_version
    ):
        raise HealthVisionError("source_invalidated", "选定档案或规则版本已变化，请重新选择", 410)
    current["plan_spec"] = deepcopy(plan.spec)
    return current


async def authorize_safe_planner_binding(session, binding):
    """运行和私有历史共同复核唯一单成员模式及不可变来源摘要。"""
    require_safe_binding(binding)
    try:
        stored = binding.safe_planner_selection
        selected = SafePlannerSelection.model_validate(stored["selection"])
        current = await safe_planner_context_in_session(session, binding.actor_uid, binding.member_id, selected)
        if input_fingerprint(current["sources"]) != stored["source_hash"]:
            raise HealthVisionError("source_invalidated", "单成员选择来源已变化，请重新选择", 410)
    except (ValidationError, KeyError, TypeError):
        raise HealthVisionError("source_invalidated", "单成员线程选择无法核对", 410) from None
    binding._safe_planner_current = current
    return selected, current


async def validate_safe_planner_history(session, binding):
    """私有输出、成功工具审计及候选来源在同次事务完整复核。"""
    from yuxi.services.health_safe_planner_types import SAFE_PLANNER_TOOLS

    preview_cache = {}
    previews = (
        await session.scalars(
            select(HealthSafePlannerPreview).where(HealthSafePlannerPreview.conversation_id == binding.conversation_id)
        )
    ).all()
    for preview in previews:
        name = {
            "swap": "preview_safe_plan_swap",
            "regeneration": "preview_safe_plan_regeneration",
        }.get(preview.operation)
        await validate_safe_planner_tool_payload(
            session, binding, name, safe_preview_result(binding, preview), preview_cache=preview_cache
        )
    rows = (
        await session.execute(
            select(Message, AgentRun)
            .join(AgentRun, AgentRun.id == Message.run_id)
            .where(
                AgentRun.conversation_id == binding.conversation_id,
                or_(
                    and_(AgentRun.status == "completed", AgentRun.output_message_id == Message.id),
                    and_(Message.message_type == TOOL_AUDIT_MESSAGE_TYPE, Message.execution_status == "completed"),
                ),
            )
        )
    ).all()
    conversation = await session.get(Conversation, binding.conversation_id)
    for message, run in rows:
        processing = (run.input_payload or {}).get("health_processing")
        if (
            run.uid != binding.actor_uid
            or run.agent_slug != PLANNER_SLUG
            or run.conversation_id != binding.conversation_id
            or conversation is None
            or run.conversation_thread_id != conversation.thread_id
            or message.conversation_id != binding.conversation_id
            or not isinstance(processing, dict)
            or processing.get("safe_selection_hash") != input_fingerprint(binding.safe_planner_selection)
        ):
            raise HealthVisionError("source_invalidated", "单成员历史所属运行身份或选择不符", 410)
        try:
            payload = json.loads(message.content)
            if message.message_type == TOOL_AUDIT_MESSAGE_TYPE:
                name = (message.extra_metadata or {}).get("tool_name")
                if name not in SAFE_PLANNER_TOOLS:
                    raise HealthVisionError("source_invalidated", "单成员历史工具不属于固定模式", 410)
                await validate_safe_planner_tool_payload(
                    session, binding, name, payload, preview_cache=preview_cache, receipt_run_id=run.id
                )
            else:
                answer = PlannerAnswer(preview_id=payload.get("preview_id"), questions=payload.get("questions", []))
                expected = await safe_answer_in_session(session, run, binding, answer, preview_cache=preview_cache)
                if input_fingerprint(payload) != input_fingerprint(expected):
                    raise HealthVisionError("source_invalidated", "单成员历史正文与服务器回执不符", 410)
        except (ValidationError, ValueError, TypeError, AttributeError):
            raise HealthVisionError("source_invalidated", "单成员历史正文无法核对", 410) from None


async def read_safe_context_for_run(context):
    """固定工具只读取已授权绑定，运行身份由worker提供。"""
    from yuxi.services.health_meal_plan_service import require_planner_run

    async with pg_manager.get_async_session_context() as session:
        _, binding = await require_planner_run(session, context)
        require_safe_binding(binding)
        return safe_context_result(binding)


async def preview_safe_for_run(context, operation, parameters):
    """仅当前有效attempt保存本Run回执，不写正式餐单或审核事实。"""
    from yuxi.services.health_meal_plan_service import require_planner_run

    async with pg_manager.get_async_session_context() as session:
        run, binding = await require_planner_run(session, context)
        require_safe_binding(binding)
        parameters, snapshot = await safe_preview_in_session(session, binding, operation, parameters)
        # 候选搜索耗时后在唯一回执写入边界重新核对持锁Run的租约。
        await HealthConsultationRepository(session).require_attempt(context)
        receipt = HealthSafePlannerPreview(
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
        return safe_preview_result(binding, receipt)


async def safe_answer_in_session(session, run, binding, answer, *, preview_cache=None):
    """最终只接受本Run回执或追问，按原参数重算完整业务结果。"""
    require_safe_binding(binding)
    if answer.questions:
        return {
            "scope": "single_member_saved_plan",
            "member_id": binding.member_id,
            "status": "needs_input",
            "questions": answer.questions,
            "professional_review": "not_a_professional_decision",
        }
    preview = await session.get(HealthSafePlannerPreview, str(answer.preview_id))
    if (
        preview is None
        or preview.actor_uid != run.uid
        or preview.run_id != run.id
        or preview.conversation_id != binding.conversation_id
    ):
        raise HealthVisionError("planner_receipt_invalid", "单成员预览回执不属于当前运行", 409)
    current = await _preview_for_validation(session, binding, preview, preview_cache)
    if input_fingerprint(current) != input_fingerprint(preview.snapshot):
        raise HealthVisionError("source_invalidated", "单成员预览来源或结果已变化，请重新生成", 410)
    return safe_preview_result(binding, preview)


async def validate_safe_planner_publication(session, run, text):
    """发布事务覆盖实际绑定与Run快照两种入口并核对完整回执。"""
    from yuxi.services.health_consultation_service import require_consultation

    stored = await session.scalar(
        select(HealthConsultation).where(HealthConsultation.conversation_id == run.conversation_id)
    )
    processing = (run.input_payload or {}).get("health_processing")
    if (stored is None or stored.safe_planner_selection is None) and not (
        isinstance(processing, dict) and processing.get("safe_selection_hash")
    ):
        return
    if not isinstance(processing, dict) or not processing.get("safe_selection_hash"):
        raise HealthVisionError("policy_changed", "单成员运行缺少固定选择的处理审批快照", 409)
    binding, _ = await require_consultation(
        session, run.uid, run.conversation_thread_id, expected=processing, lock=True
    )
    require_safe_binding(binding)
    if binding.conversation_id != run.conversation_id:
        raise HealthVisionError("source_invalidated", "单成员运行绑定已变化", 410)
    try:
        payload = json.loads(text)
        answer = PlannerAnswer(preview_id=payload.get("preview_id"), questions=payload.get("questions", []))
    except (ValidationError, ValueError, TypeError, AttributeError):
        raise HealthVisionError("planner_output_invalid", "单成员待发布结果无法解析", 409) from None
    expected = await safe_answer_in_session(session, run, binding, answer)
    if input_fingerprint(expected) != input_fingerprint(payload):
        raise HealthVisionError("source_invalidated", "单成员待发布结果与当前服务器回执不符", 410)


async def validate_safe_planner_tool_payload(
    session, binding, name, payload, *, preview_cache=None, receipt_run_id=None
):
    """checkpoint验证原Run执行身份、处理选择和当前完整业务结果。"""
    require_safe_binding(binding)
    if name == "get_safe_plan_context":
        if input_fingerprint(payload) != input_fingerprint(safe_context_result(binding)):
            raise HealthVisionError("source_invalidated", "单成员上下文历史已变化", 410)
        return
    expected_operation = {
        "preview_safe_plan_swap": "swap",
        "preview_safe_plan_regeneration": "regeneration",
    }.get(name)
    if expected_operation is None:
        raise HealthVisionError("source_invalidated", "单成员checkpoint工具不属于固定模式", 410)
    try:
        preview = await session.get(HealthSafePlannerPreview, str(payload["preview_id"]))
        if (
            preview is None
            or preview.actor_uid != binding.actor_uid
            or preview.conversation_id != binding.conversation_id
            or preview.operation != expected_operation
            or (receipt_run_id is not None and preview.run_id != receipt_run_id)
        ):
            raise HealthVisionError("source_invalidated", "单成员checkpoint回执身份不符", 410)
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
            or processing.get("safe_selection_hash") != input_fingerprint(binding.safe_planner_selection)
        ):
            raise HealthVisionError("source_invalidated", "单成员checkpoint所属运行身份或选择不符", 410)
        current = await _preview_for_validation(session, binding, preview, preview_cache)
        expected = safe_preview_result(binding, preview)
        snapshot_matches = input_fingerprint(current) == input_fingerprint(preview.snapshot)
        payload_matches = input_fingerprint(payload) == input_fingerprint(expected)
        if not snapshot_matches or not payload_matches:
            raise HealthVisionError("source_invalidated", "单成员checkpoint预览结果已变化", 410)
    except (ValidationError, KeyError, TypeError):
        raise HealthVisionError("source_invalidated", "单成员checkpoint无法核对", 410) from None


def require_safe_binding(binding):
    """单成员安全选择必须存在且不能混用家庭或初始模式。"""
    if getattr(binding, "safe_planner_selection", None) is None:
        raise HealthVisionError("safe_selection_required", "请从明确选定单成员餐单的入口创建线程", 409)
    if (
        getattr(binding, "family_planner_selection", None) is not None
        or getattr(binding, "initial_planner_selection", None) is not None
    ):
        raise HealthVisionError("source_invalidated", "单成员安全选择不属于唯一配餐模式", 410)


def safe_context_result(binding):
    """只投影当前事务已核对的餐单、专业来源及安全检查。"""
    require_safe_binding(binding)
    current = binding._safe_planner_current
    return {
        "scope": "single_member_saved_plan",
        "member_id": binding.member_id,
        "selection": deepcopy(binding.safe_planner_selection["selection"]),
        "plan_spec": deepcopy(current["plan_spec"]),
        "plan_snapshot": deepcopy(current["plan_snapshot"]),
        "profile": deepcopy(current["profile"]),
        "rules": deepcopy(current["rules"]),
        "sources": deepcopy(current["sources"]),
        "safety_check": quality_snapshot(current)["safety_check"],
        "professional_review": "not_a_professional_decision",
    }


async def safe_preview_in_session(session, binding, operation, parameters):
    """身份和版本仅取线程，候选和整份搜索直接复用业务Owner。"""
    require_safe_binding(binding)
    try:
        selected = SafePlannerSelection.model_validate(binding.safe_planner_selection["selection"])
        values = selected.model_dump(mode="json", exclude={"plan_id"})
        if operation == "swap":
            parameters = SafeSwapParameters.model_validate(parameters).model_dump(mode="json")
            data = SafeSwapSelection.model_validate({**values, **parameters})
            _, result = await candidates_in_session(session, binding.actor_uid, str(selected.plan_id), data)
        elif operation == "regeneration" and parameters == {}:
            data = SafeRegenerationSelection.model_validate(values)
            _, result = await regeneration_in_session(session, binding.actor_uid, str(selected.plan_id), data)
        else:
            raise HealthVisionError("planner_receipt_invalid", "单成员预览操作或参数无法核对", 409)
    except (ValidationError, KeyError, TypeError):
        raise HealthVisionError("planner_receipt_invalid", "单成员预览操作或参数无法核对", 409) from None
    return parameters, result


def safe_preview_result(binding, preview):
    """回执身份、操作和全部预览内容均由服务器投影。"""
    return {
        "preview_id": preview.id,
        "scope": "single_member_saved_plan",
        "member_id": binding.member_id,
        "operation": preview.operation,
        "result": deepcopy(preview.snapshot),
    }


def _require_single_selected_plan(plan, uid, member_id):
    """持久对象必须属于当前账号和选定成员，拒绝家庭及非法规格。"""
    if plan is None or plan.actor_uid != uid or plan.member_id != member_id:
        raise HealthVisionError("not_found", "单成员餐单不存在或无权访问", 404)
    from yuxi.services.health_meal_plan_service import require_single_member_plan

    require_single_member_plan(plan)
    try:
        MealPlanSpec.model_validate(plan.spec)
    except ValidationError:
        raise HealthVisionError("source_invalidated", "单成员餐单规格无法核对", 410) from None


async def _preview_for_validation(session, binding, preview, cache):
    """同次历史事务相同操作/参数只复算一次，每份回执仍独立验身份和全文。"""
    key = (preview.operation, input_fingerprint(preview.parameters))
    if cache is not None and key in cache:
        return cache[key]
    _, current = await safe_preview_in_session(session, binding, preview.operation, preview.parameters)
    if cache is not None:
        cache[key] = current
    return current

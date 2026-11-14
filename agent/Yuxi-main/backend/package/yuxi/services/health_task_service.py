"""明确角色入口与既有健康 Request/Run 的只读业务投影。"""

import json

from pydantic import ValidationError

from yuxi.repositories.health_consultation_repository import (
    ANALYST_SLUG,
    CONSULTATION_SLUG,
    EDUCATION_HEALTH_AGENTS,
    GLUCOSE_SLUG,
    LIPIDS_SLUG,
    PRESSURE_SLUG,
    PLANNER_SLUG,
    PURCHASE_SLUG,
    QUALITY_SLUG,
)
from yuxi.repositories.health_meal_plan_repository import HealthMealPlanRepository
from yuxi.repositories.health_quality_repository import HealthQualityRepository
from yuxi.repositories.health_task_repository import HealthTaskRepository
from yuxi.repositories.health_vision_repository import HealthVisionRepository
from yuxi.services.health_consultation_service import create_consultation, require_consultation
from yuxi.services.health_agent_personal_target_types import TargetAwareAnalystInput
from yuxi.services.health_diet_analysis_service import validate_analyst_publication
from yuxi.services.health_family_planner_service import validate_family_planner_publication
from yuxi.services.health_initial_planner_service import validate_initial_planner_publication
from yuxi.services.health_meal_plan_service import PLANNER_BOUNDARY, calculate_in_session
from yuxi.services.health_meal_plan_types import MealPlanSpec, PlannerAnswer
from yuxi.services.health_nutrition_service import input_fingerprint
from yuxi.services.health_quality_service import create_quality_conversation, validate_quality_publication
from yuxi.services.health_quality_types import QualityCheckInput
from yuxi.services.health_purchase_service import validate_purchase_publication
from yuxi.services.health_purchase_types import PurchaseInput
from yuxi.services.health_safe_planner_service import validate_safe_planner_publication
from yuxi.services.health_readiness_service import health_task_runtime_blockers
from yuxi.services.health_task_types import (
    HealthTaskEntryInput,
    HealthTaskEntryResult,
    HealthTaskError,
    HealthTaskGeneralAnswer,
    HealthTaskNeedsInput,
    HealthTaskResult,
    HealthTaskValidatedResult,
)
from yuxi.services.health_vision_types import ConsultationInput, HealthVisionError
from yuxi.storage.postgres.manager import pg_manager


async def create_health_task_entry(uid: str, member_id: str, data: HealthTaskEntryInput) -> HealthTaskEntryResult:
    """创建固定模式线程，缺选择或外部契约时不写入任何任务。"""
    chosen = data.root
    base = {"task_type": chosen.task_type, "member_id": member_id, "client_request_id": chosen.client_request_id}
    unsupported = chosen.task_type in {"glucose_plan", "automatic_family_coordination"}
    needs_selection = (
        chosen.task_type
        in {
            "initial_meal_preview",
            "reference_meal_preview",
            "family_meal_revision",
            "safe_meal_revision",
            "quality_check",
            "purchase_requirements",
            "multi_day_plan",
        }
        and chosen.selection is None
    )
    if unsupported or needs_selection:
        async with pg_manager.get_async_session_context() as session:
            await HealthVisionRepository(session).authorize(member_id, uid, "ai_use", lock=True)
        if unsupported:
            return HealthTaskEntryResult(
                **base, entry_status="dependency_not_ready", reason_code="external_contract_required"
            )
        return HealthTaskEntryResult(
            **base,
            entry_status="needs_input",
            reason_code="selection_required",
            questions=["请明确选择本任务的对象、当前版本和批准来源。"],
        )

    missing_runtime = await health_task_runtime_blockers(uid, member_id)
    if missing_runtime:
        return HealthTaskEntryResult(
            **base,
            entry_status="dependency_not_ready",
            reason_code="runtime_dependency_unavailable",
            missing_dependencies=missing_runtime,
        )

    if chosen.task_type == "multi_day_plan":
        from yuxi.services.exclusive_plan_service import start_exclusive_plan
        from yuxi.services.exclusive_plan_types import ExclusivePlanInput

        group = await start_exclusive_plan(
            uid,
            str(chosen.selection.family_id),
            ExclusivePlanInput(client_request_id=chosen.client_request_id),
            required_member=member_id,
        )
        return HealthTaskEntryResult(**base, entry_status="ready", exclusive_plan=group)
    if chosen.task_type == "purchase_requirements":
        selected = PurchaseInput(client_request_id=chosen.client_request_id, **chosen.selection.model_dump(mode="json"))
        entry = await create_consultation(
            uid,
            member_id,
            ConsultationInput(client_request_id=selected.client_request_id),
            agent_slug=PURCHASE_SLUG,
            purchase_selection=selected.model_dump(mode="json", exclude={"client_request_id"}),
        )
    elif chosen.task_type == "diet_analysis":
        selected = TargetAwareAnalystInput(
            client_request_id=chosen.client_request_id, target_selection=chosen.target_selection
        )
        entry = await create_consultation(
            uid, member_id, selected, agent_slug=ANALYST_SLUG, target_selection=selected.target_selection
        )
    elif chosen.task_type == "quality_check":
        selected = chosen.selection
        async with pg_manager.get_async_session_context() as session:
            plan = await HealthQualityRepository(session).plan(uid, str(selected.plan_id))
            if plan.member_id != member_id:
                raise HealthVisionError("not_found", "质量检查对象不属于所选成员", 404)
        entry = await create_quality_conversation(
            uid,
            str(selected.plan_id),
            QualityCheckInput(
                client_request_id=chosen.client_request_id, version=selected.version, rule_code=selected.rule_code
            ),
        )
    else:
        slug = {
            "consultation": CONSULTATION_SLUG,
            "blood_glucose_review": GLUCOSE_SLUG,
            "blood_lipids_review": LIPIDS_SLUG,
            "blood_pressure_review": PRESSURE_SLUG,
            "meal_preview": PLANNER_SLUG,
            "initial_meal_preview": PLANNER_SLUG,
            "reference_meal_preview": PLANNER_SLUG,
            "family_meal_revision": PLANNER_SLUG,
            "safe_meal_revision": PLANNER_SLUG,
        }[chosen.task_type]
        selections = {}
        if chosen.task_type == "reference_meal_preview" and chosen.root_thread_id is not None:
            selections["root_thread_id"] = str(chosen.root_thread_id)
        if chosen.selection is not None:
            keyword = {
                "initial_meal_preview": "initial_selection",
                "reference_meal_preview": "initial_selection",
                "family_meal_revision": "family_selection",
                "safe_meal_revision": "safe_selection",
                "blood_glucose_review": "indicator_selection",
                "blood_lipids_review": "indicator_selection",
                "blood_pressure_review": "indicator_selection",
            }[chosen.task_type]
            selections[keyword] = chosen.selection.model_dump(mode="json")
        entry = await create_consultation(
            uid,
            member_id,
            ConsultationInput(client_request_id=chosen.client_request_id),
            agent_slug=slug,
            **selections,
        )
    return HealthTaskEntryResult(
        **base,
        entry_status="ready",
        thread_id=entry["thread_id"],
        agent_slug=entry["agent_slug"],
        request_submit_url="/api/agent/runs",
    )


async def read_health_task(uid: str, request_id: str) -> HealthTaskResult:
    """查询既有 Request 的当前执行事实，只公开完成且当前来源有效的结果。"""
    async with pg_manager.get_async_session_context() as session:
        return await read_health_task_in_session(session, uid, request_id)


async def read_health_task_in_session(session, uid: str, request_id: str) -> HealthTaskResult:
    """交接与普通结果读取在所属事务中共享同一校验。"""
    repo = HealthTaskRepository(session)
    request, binding, run = await repo.request_context(uid, request_id)
    task_type = task_type_for_binding(request.agent_slug, binding)
    response = HealthTaskResult(
        request_id=request.request_id,
        task_type=task_type,
        agent_slug=request.agent_slug,
        thread_id=request.conversation_thread_id,
        member_id=binding.member_id,
        request_status=request.status,
        execution_status=run.status if run else "not_dispatched",
        run_id=run.id if run else None,
        request_events_url=f"/api/agent/requests/{request.request_id}/events" if request.status == "queued" else None,
        run_events_url=f"/api/agent/runs/{run.id}/events" if run else None,
        query_url=f"/api/health/v1/tasks/{request.request_id}",
    )
    if request.agent_slug == CONSULTATION_SLUG:
        from yuxi.services.health_chat_meal_service import chat_meal_receipts

        response.recorded_meals = await chat_meal_receipts(session, uid, {"request_id": request_id})
    terminal = run.status if run else request.status
    error_codes = {
        "failed": "execution_failed",
        "rejected": "request_rejected",
        "cancelled": "execution_cancelled",
        "interrupted": "execution_interrupted",
    }
    if terminal in error_codes:
        code = (
            run.error_type
            if run is not None
            and run.error_type
            in {
                "budget_price_unavailable",
                "budget_exceeded",
                "reference_translation_correction_invalid",
                "reference_save_correction_exhausted",
                "reference_recipe_repeated",
                "reference_menu_repeated",
                "reference_variety_exhausted",
                "reference_meal_incomplete",
                "reference_coverage_unavailable",
                "reference_search_exhausted",
                "daily_plan_version_changed",
            }
            else error_codes[terminal]
        )
        message = None
        if code == "reference_coverage_unavailable":
            from yuxi.services.reference_meal_plan_service import tool_payloads
            from yuxi.services.reference_menu_candidates import reference_coverage_message

            receipts = await tool_payloads(session, run, "search_reference_recipes")
            message = reference_coverage_message(receipts[-1].get("coverage_gaps", []) if receipts else [])
        elif code == "reference_search_exhausted":
            message = "本轮未能在允许的检索与原文核对次数内完成所选餐次。"
        response.result = HealthTaskError(code=code, message=message)
        return response
    if run is None or run.status != "completed":
        return response

    message = await repo.final_message(run)
    processing = (run.input_payload or {}).get("health_processing")
    if not isinstance(processing, dict):
        raise HealthVisionError("policy_changed", "健康任务缺少处理审批快照", 409)
    current_binding, _ = await require_consultation(
        session, uid, run.conversation_thread_id, expected=processing, lock=True
    )
    if current_binding.conversation_id != run.conversation_id or current_binding.member_id != binding.member_id:
        raise HealthVisionError("source_invalidated", "健康任务来源绑定已变化", 410)
    response.final_message_id = message.id
    if run.agent_slug in EDUCATION_HEALTH_AGENTS:
        from yuxi.services.health_evidence_service import resolve_consultation_citations, stored_consultation_refs

        titles, citations = await resolve_consultation_citations(
            session, run, current_binding, message.content, stored_consultation_refs(message)
        )
        from yuxi.services.conversation_purchase_service import offers_for_answer

        answer, offers = await offers_for_answer(session, run, current_binding, message.content)
        response.result = HealthTaskGeneralAnswer(
            answer=answer,
            citations=citations,
            source_titles=titles,
            purchase_offers=offers,
        )
        return response

    try:
        payload = json.loads(message.content)
        if not isinstance(payload, dict):
            raise ValueError("结果不是业务对象")
    except (TypeError, ValueError):
        raise HealthVisionError("answer_unavailable", "健康任务最终结果无法解析", 409) from None
    await validate_task_business_result(session, run, current_binding, payload, message.content)
    if payload.get("status") == "needs_input" or payload.get("result_type") == "needs_input":
        response.result = HealthTaskNeedsInput(questions=payload["questions"])
    else:
        result_type = {
            PLANNER_SLUG: "meal_plan_preview",
            ANALYST_SLUG: "diet_analysis",
            QUALITY_SLUG: "quality_check",
            PURCHASE_SLUG: "ingredient_requirements",
        }[run.agent_slug]
        if payload.get("result_type") == "meal_feedback":
            result_type = "meal_feedback"
        if payload.get("status") == "reference_candidates" and payload.get("scope") == "cooking_reference":
            result_type = "meal_plan_candidates"
        if payload.get("scope") == "daily_reference" and payload.get("preview_id"):
            from yuxi.services.reference_meal_plan_service import reference_plan_display

            payload = await reference_plan_display(session, payload)
        response.result = HealthTaskValidatedResult(result_type=result_type, data=payload)
    return response


def task_type_for_binding(slug, binding):
    """任务类型来自服务器线程事实，模型文字不能改变模式。"""
    education_tasks = {
        CONSULTATION_SLUG: "consultation",
        GLUCOSE_SLUG: "blood_glucose_review",
        LIPIDS_SLUG: "blood_lipids_review",
        PRESSURE_SLUG: "blood_pressure_review",
    }
    if slug in education_tasks:
        return education_tasks[slug]
    if slug == ANALYST_SLUG:
        return "diet_analysis"
    if slug == QUALITY_SLUG:
        return "quality_check"
    if slug == PURCHASE_SLUG:
        return "purchase_requirements"
    if slug != PLANNER_SLUG:
        raise HealthVisionError("not_found", "此角色尚未接入健康任务投影", 404)
    from yuxi.services.reference_meal_plan_service import reference_binding

    modes = [
        (
            "reference_meal_preview" if reference_binding(binding) else "initial_meal_preview",
            getattr(binding, "initial_planner_selection", None),
        ),
        ("family_meal_revision", getattr(binding, "family_planner_selection", None)),
        ("safe_meal_revision", getattr(binding, "safe_planner_selection", None)),
    ]
    selected = [name for name, value in modes if value is not None]
    if len(selected) > 1:
        raise HealthVisionError("source_invalidated", "配餐任务不是唯一固定模式", 410)
    return selected[0] if selected else "meal_preview"


async def validate_task_business_result(session, run, binding, payload, content):
    """复用无lease的发布校验Owner，普通草稿另核对同Run回执与复算全文。"""
    if run.agent_slug == PLANNER_SLUG:
        from yuxi.services.health_family_kb_service import validate_family_kb_answer

        await validate_family_kb_answer(session, run, binding, content)
    if run.agent_slug == ANALYST_SLUG:
        await validate_analyst_publication(session, run, content)
        return
    if run.agent_slug == QUALITY_SLUG:
        await validate_quality_publication(session, run, content)
        return
    if run.agent_slug == PURCHASE_SLUG:
        await validate_purchase_publication(session, run, content)
        return
    from yuxi.services.reference_meal_plan_service import reference_binding, validate_reference_publication

    if reference_binding(binding):
        await validate_reference_publication(session, run, binding, content)
        return
    if binding.initial_planner_selection is not None:
        await validate_initial_planner_publication(session, run, content)
        return
    if binding.family_planner_selection is not None:
        await validate_family_planner_publication(session, run, content)
        return
    if binding.safe_planner_selection is not None:
        await validate_safe_planner_publication(session, run, content)
        return
    try:
        answer = PlannerAnswer(preview_id=payload.get("preview_id"), questions=payload.get("questions", []))
    except ValidationError:
        raise HealthVisionError("planner_output_invalid", "普通配餐结果无法核对", 409) from None
    if answer.questions:
        current = {"questions": answer.questions, **PLANNER_BOUNDARY, "status": "needs_input"}
    else:
        preview = await HealthMealPlanRepository(session).preview(run.uid, str(answer.preview_id))
        if preview.run_id != run.id or preview.member_id != binding.member_id:
            raise HealthVisionError("planner_receipt_invalid", "普通配餐回执不属于当前运行", 409)
        current_snapshot = await calculate_in_session(session, MealPlanSpec.model_validate(preview.spec))
        if input_fingerprint(current_snapshot) != input_fingerprint(preview.snapshot):
            raise HealthVisionError("source_invalidated", "普通配餐来源或回执已变化", 410)
        current = {"preview_id": preview.id, "member_id": preview.member_id, **current_snapshot}
    if input_fingerprint(current) != input_fingerprint(payload):
        raise HealthVisionError("source_invalidated", "普通配餐最终结果与当前回执不一致", 410)

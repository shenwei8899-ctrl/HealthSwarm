"""独立质量检查、版本绑定与专业审核的事务用例。"""

from copy import deepcopy
import json
from types import SimpleNamespace
from uuid import NAMESPACE_URL, uuid4, uuid5

from pydantic import ValidationError
from sqlalchemy import select

from yuxi.repositories.health_consultation_repository import HealthConsultationRepository, QUALITY_SLUG
from yuxi.repositories.health_quality_repository import HealthQualityRepository
from yuxi.repositories.health_vision_repository import HealthVisionRepository
from yuxi.services.health_meal_plan_service import calculate_in_session, require_single_member_plan
from yuxi.services.health_family_meal_plan_types import FamilyMealPlanSpec, parse_meal_plan_spec, plan_member_ids
from yuxi.services.health_nutrition_service import input_fingerprint
from yuxi.services.health_quality_checks import external_projection, evaluate_plan_quality
from yuxi.services.health_quality_types import QualityAnswer, QualityCheckInput
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_health import HealthQualityCheck, HealthProfessionalReview, HealthReviewAction
from yuxi.utils.datetime_utils import format_utc_datetime, utc_now_naive


async def quality_context_in_session(session, uid, selection, *, review=False):
    """成员、对象与规则锁持至提交，当前来源变化不能在检查后插入。"""
    repo = HealthQualityRepository(session)
    plan = await repo.plan(uid, selection.plan_id, review=review, lock=True)
    if plan.version != selection.plan_version:
        raise HealthVisionError("source_invalidated", "餐单版本已变化，请重新选定并检查", 410)
    try:
        spec = parse_meal_plan_spec(plan.spec)
        recalculated = await calculate_in_session(session, spec)
        # 初始来源是单独的历史证据，营养仍只与原计算快照比较；plan来源摘要包含该证据。
        saved_calculation = {k: v for k, v in plan.snapshot.items() if k != "generation_origin"}
        if input_fingerprint(recalculated) != input_fingerprint(saved_calculation):
            raise ValueError("已存营养与当前来源不符")
        ingredients, recipes = await repo.ingredients(spec)
    except (ValidationError, ValueError, KeyError, TypeError):
        raise HealthVisionError("source_invalidated", "餐单或营养来源无法复算", 410) from None
    member_ids = plan_member_ids(plan.member_id, plan.spec)
    await repo.lock_profile_sources(member_ids)
    profiles = {member_id: await repo.profile_projection(member_id) for member_id in member_ids}
    profile = profiles[plan.member_id]
    rules = external_projection(await repo.rules(selection.rule_code, lock=True), "rules", selection.rule_code)
    sources = {
        "plan": {
            "id": plan.id,
            "version": plan.version,
            "content_hash": input_fingerprint({"spec": plan.spec, "snapshot": plan.snapshot}),
        },
        "profiles": {
            member_id: {key: projection[key] for key in ("id", "version", "content_hash", "status", "reason")}
            for member_id, projection in profiles.items()
        },
        "rules": {
            "rule_code": selection.rule_code,
            **{key: rules[key] for key in ("id", "version", "content_hash", "status", "reason")},
        },
        "recipes": recipes,
        "ingredients": ingredients,
    }
    current = {
        "member_id": plan.member_id,
        "sources": sources,
        "plan_snapshot": recalculated,
        "profile": profile,
        "rules": rules,
        "ingredients": ingredients,
    }
    if isinstance(spec, FamilyMealPlanSpec):
        by_recipe, _ = await repo.recipe_sources_by_recipe(recipes)
        member_ingredients = {}
        for member_id in profiles:
            selected_ids = {
                str(d.recipe_version_id)
                for m in spec.meals
                for d in m.dishes
                if any(str(p.member_id) == member_id for p in d.member_portions)
            }
            foods = {}
            for recipe_id in selected_ids:
                for food_id, food in by_recipe[recipe_id].items():
                    entry = foods.setdefault(food_id, dict(food))
                    entry["source_current"] = entry["source_current"] and food["source_current"]
            member_ingredients[member_id] = foods
        current.update(profiles=profiles, member_ingredients=member_ingredients)
    return current


def quality_snapshot(current):
    """最终检查来自当前服务端复算，专业批准始终另查业务流程。"""
    if "profiles" in current:
        members = {
            member_id: evaluate_plan_quality(
                snapshot,
                current["profiles"][member_id],
                current["rules"],
                current["member_ingredients"][member_id],
                covered_meals=snapshot["covered_meals"],
            )
            for member_id, snapshot in current["plan_snapshot"]["members"].items()
        }
        statuses = {check["status"] for check in members.values()}
        safety = {
            "status": "conflict" if "conflict" in statuses else "unknown" if "unknown" in statuses else "passed",
            "checks_version": "family-quality-v1",
            "members": members,
            **{
                field: [
                    {"member_id": member_id, **item} for member_id, check in members.items() for item in check[field]
                ]
                for field in ("missing", "conflicts")
            },
        }
        return {
            "scope": "family_saved_plan",
            "sources": current["sources"],
            "safety_check": safety,
            "nutrition": current["plan_snapshot"]["nutrition"],
            "nutrition_recalculated": True,
            "professional_review": "not_a_professional_decision",
        }
    return {
        "scope": "single_member_saved_plan",
        "sources": current["sources"],
        "safety_check": evaluate_plan_quality(
            current["plan_snapshot"], current["profile"], current["rules"], current["ingredients"]
        ),
        "nutrition": current["plan_snapshot"]["nutrition"],
        "nutrition_recalculated": True,
        "professional_review": "not_a_professional_decision",
    }


def quality_result(check):
    """回执身份与不可变服务器快照合并。"""
    return {"result_type": "quality_check", "check_id": check.id, **deepcopy(check.snapshot)}


async def validate_quality_check(session, uid, check, *, review=False):
    """历史、发布、审核和采用共用当前版本验证，不继承旧检查。"""
    if check is None or (not review and check.actor_uid != uid):
        raise HealthVisionError("not_found", "质量检查不存在或无权访问", 404)
    selected = SimpleNamespace(plan_id=check.plan_id, plan_version=check.plan_version, rule_code=check.rule_code)
    current = await quality_context_in_session(session, uid, selected, review=review)
    if quality_snapshot(current) != check.snapshot:
        raise HealthVisionError("source_invalidated", "档案、规则、配料或检查内容已变化，请重新检查", 410)
    return current


async def check_plan_in_session(session, uid, plan_id, data, *, run_id=None):
    """HTTP与固定工具共享检查事务及幂等收据。"""
    repo = HealthQualityRepository(session)
    await repo.lock_request(uid, str(data.client_request_id))
    selected = SimpleNamespace(plan_id=plan_id, plan_version=data.version, rule_code=data.rule_code)
    current = await quality_context_in_session(session, uid, selected)
    fingerprint = input_fingerprint({"plan_id": plan_id, **data.model_dump(mode="json")})
    if await repo.action_receipt(uid, str(data.client_request_id)):
        raise HealthVisionError("request_conflict", "此幂等键已用于审核动作", 409)
    check = await repo.check_receipt(uid, str(data.client_request_id))
    if check is not None:
        if check.fingerprint != fingerprint or check.run_id != run_id:
            raise HealthVisionError("request_conflict", "此幂等键不能改变检查对象或执行来源", 409)
        await validate_quality_check(session, uid, check)
        return check
    check = HealthQualityCheck(
        id=str(uuid4()),
        actor_uid=uid,
        member_id=current["member_id"],
        plan_id=plan_id,
        plan_version=data.version,
        rule_code=data.rule_code,
        rule_id=current["rules"]["id"],
        request_id=str(data.client_request_id),
        fingerprint=fingerprint,
        run_id=run_id,
        snapshot=quality_snapshot(current),
    )
    session.add(check)
    await session.flush()
    session.add(
        HealthProfessionalReview(
            id=str(uuid4()), check_id=check.id, actor_uid=uid, member_id=check.member_id, version=1, status="draft"
        )
    )
    return check


async def check_saved_plan(uid, plan_id, data):
    """无需外呼模型即可执行同一质量Owner检查。"""
    async with pg_manager.get_async_session_context() as session:
        return quality_result(await check_plan_in_session(session, uid, plan_id, data))


async def review_case_in_session(session, uid, case_id):
    """申请人或当前资格与成员审核授权均满足的审核人可查看。"""
    case = await session.get(HealthProfessionalReview, case_id, populate_existing=True)
    if case is None:
        raise HealthVisionError("not_found", "审核对象不存在或无权访问", 404)
    reviewer = uid != case.actor_uid
    check = await session.get(HealthQualityCheck, case.check_id)
    repo = HealthQualityRepository(session)
    plan = await repo.plan(
        uid, check.plan_id, review=reviewer, lock=True, historical_member_ids=check.snapshot["sources"]["profiles"]
    )
    await repo.lock_profile_sources(
        set(plan_member_ids(plan.member_id, plan.spec)) | set(check.snapshot["sources"]["profiles"])
    )
    await session.refresh(case)
    await repo.rules(check.rule_code, lock=True)
    qualification_uids = ({uid} if reviewer else set()) | ({case.reviewer_uid} if case.status == "approved" else set())
    for reviewer_uid in sorted(qualification_uids):
        await repo.lock_key(f"health-reviewer:{reviewer_uid}")
    if reviewer:
        await repo.reviewer(uid)
    if case.status == "approved":
        try:
            qualification = await repo.reviewer(case.reviewer_uid)
            if qualification.version != case.reviewer_version:
                raise HealthVisionError("source_invalidated", "批准所用资格版本已变化", 410)
            for member_id in sorted(check.snapshot["sources"]["profiles"]):
                await HealthVisionRepository(session).authorize(member_id, case.reviewer_uid, "professional_review")
                await HealthVisionRepository(session).authorize(member_id, case.reviewer_uid, "profile_view")
        except HealthVisionError:
            await repo.invalidate(reviewer_uid=case.reviewer_uid, reason="reviewer_unavailable")
    try:
        await validate_quality_check(session, uid, check, review=reviewer)
    except HealthVisionError as error:
        if error.code != "source_invalidated":
            raise
        if case.status != "invalidated":
            await repo.invalidate(review_id=case.id, reason="source_changed_or_expired")
    await session.flush()
    await session.refresh(case)
    return case, check, reviewer


async def review_case_result(session, case, check):
    """当前状态与全部不可变提交和专业动作一起回读。"""
    actions = list(
        (
            await session.scalars(
                select(HealthReviewAction)
                .where(HealthReviewAction.review_id == case.id)
                .order_by(HealthReviewAction.version)
            )
        ).all()
    )
    return {
        "review_id": case.id,
        "check_id": case.check_id,
        "version": case.version,
        "status": case.status,
        "member_id": case.member_id,
        "plan_id": check.plan_id,
        "plan_version": check.plan_version,
        "safety_status": check.snapshot["safety_check"]["status"],
        "invalidation_reason": case.invalidation_reason,
        "reviewer_uid": case.reviewer_uid,
        "reviewer_version": case.reviewer_version,
        "actions": [
            {
                "version": a.version,
                "status": a.status,
                "actor_uid": a.actor_uid,
                "reason": a.reason,
                "evidence_refs": a.evidence_refs,
                "reviewer_attestation": a.reviewer_attestation,
                "created_at": format_utc_datetime(a.created_at),
            }
            for a in actions
        ],
    }


async def read_quality_check(uid, check_id):
    """自有检查即使失效仍可读明确失效状态，不返回当前可用标签。"""
    async with pg_manager.get_async_session_context() as session:
        check = await session.get(HealthQualityCheck, check_id)
        if check is None or check.actor_uid != uid:
            raise HealthVisionError("not_found", "质量检查不存在或无权访问", 404)
        case = await HealthQualityRepository(session).case_for_check(check_id)
        case, _, _ = await review_case_in_session(session, uid, case.id)
        return {
            **quality_result(check),
            "current": case.status != "invalidated",
            "review": await review_case_result(session, case, check),
        }


async def read_professional_review(uid, case_id):
    """读取也校验有效来源、资格与授权，过期流程显式失效。"""
    async with pg_manager.get_async_session_context() as session:
        case, check, _ = await review_case_in_session(session, uid, case_id)
        return await review_case_result(session, case, check)


async def change_professional_review(uid, case_id, action, data):
    """提交、退回和批准在相同版本与幂等边界内执行。"""
    async with pg_manager.get_async_session_context() as session:
        repo = HealthQualityRepository(session)
        await repo.lock_request(uid, str(data.client_request_id))
        case, check, reviewer = await review_case_in_session(session, uid, case_id)
        fingerprint = input_fingerprint({"review_id": case_id, "action": action, **data.model_dump(mode="json")})
        receipt = await repo.action_receipt(uid, str(data.client_request_id))
        if await repo.check_receipt(uid, str(data.client_request_id)) or (
            receipt and receipt.fingerprint != fingerprint
        ):
            raise HealthVisionError("request_conflict", "同一请求不能改变审核动作或对象", 409)
        if receipt is not None:
            return await review_case_result(session, case, check)
        if case.status == "invalidated":
            raise HealthVisionError("review_invalidated", "审核来源已失效，需要新检查后提交", 409)
        if case.version != data.version:
            raise HealthVisionError("version_conflict", "审核版本已变化，请刷新", 409)
        qualification = None
        if action == "submit":
            if reviewer or case.status not in {"draft", "returned"}:
                raise HealthVisionError("review_transition_invalid", "只有申请人可提交待提交或退回的方案", 409)
            status = "pending_review"
        else:
            if not reviewer:
                raise HealthVisionError("self_review_forbidden", "申请人不能审核自己的方案", 403)
            if action not in {"return", "approve"} or case.status != "pending_review":
                raise HealthVisionError("review_transition_invalid", "专业决定只用于当前待审核方案", 409)
            qualification = await repo.reviewer(uid, lock=True)
            if action == "approve" and check.snapshot["safety_check"]["status"] != "passed":
                raise HealthVisionError("quality_not_passed", "工程检查有冲突或未知，不能批准", 409)
            status = "returned" if action == "return" else "approved"
        case.status, case.version, case.updated_at = status, case.version + 1, utc_now_naive()
        case.reviewer_uid = uid if qualification is not None else None
        case.reviewer_version = qualification.version if qualification is not None else None
        session.add(
            HealthReviewAction(
                id=str(uuid4()),
                review_id=case.id,
                actor_uid=uid,
                request_id=str(data.client_request_id),
                fingerprint=fingerprint,
                version=case.version,
                status=status,
                reason=data.reason,
                evidence_refs=data.evidence_refs,
                reviewer_attestation=deepcopy(qualification.attestation) if qualification is not None else None,
            )
        )
        await session.flush()
        return await review_case_result(session, case, check)


async def approved_plan_state(uid, plan_id, version):
    """公开查询复用事务内门禁，不把历史批准继承到新版。"""
    async with pg_manager.get_async_session_context() as session:
        return await approved_plan_state_in_session(session, uid, plan_id, version)


async def approved_plan_state_in_session(session, uid, plan_id, version, *, review_id=None):
    """采用与结算在自身Owner事务内复核当前选定批准。"""
    repo = HealthQualityRepository(session)
    plan = await repo.plan(uid, plan_id, lock=True)
    if plan.version != version:
        raise HealthVisionError("version_conflict", "方案版本已变化", 409)
    cases = list(
        (
            await session.scalars(
                select(HealthProfessionalReview)
                .join(HealthQualityCheck, HealthQualityCheck.id == HealthProfessionalReview.check_id)
                .where(
                    HealthQualityCheck.plan_id == plan_id,
                    HealthQualityCheck.plan_version == version,
                    HealthProfessionalReview.actor_uid == uid,
                    HealthProfessionalReview.status == "approved",
                )
                .order_by(HealthProfessionalReview.updated_at.desc())
            )
        ).all()
    )
    for candidate in cases:
        if review_id is not None and candidate.id != review_id:
            continue
        case, check, _ = await review_case_in_session(session, uid, candidate.id)
        if case.status == "approved" and check.snapshot["safety_check"]["status"] == "passed":
            return {
                "available": True,
                "plan_id": plan_id,
                "version": version,
                "review_id": case.id,
                "check_id": check.id,
                "sources": check.snapshot["sources"],
            }
    latest = await repo.latest_plan_review(uid, plan_id, version)
    if latest is not None:
        latest, _, _ = await review_case_in_session(session, uid, latest.id)
    return {
        "available": False,
        "reason": "current_professional_approval_required",
        "plan_id": plan_id,
        "version": version,
        "professional_review": latest.status if latest is not None else "not_reviewed",
        "invalidation_reason": latest.invalidation_reason if latest is not None else None,
        "review_id": latest.id if latest is not None else None,
        "check_id": latest.check_id if latest is not None else None,
    }


async def create_quality_conversation(uid, plan_id, data):
    """业务选定当前保存对象，不由模型在对话中指定对象或规则。"""
    from yuxi.services.health_consultation_service import create_consultation
    from yuxi.services.health_vision_types import ConsultationInput

    async with pg_manager.get_async_session_context() as session:
        plan = await HealthQualityRepository(session).plan(uid, plan_id)
        require_single_member_plan(plan)
        if plan.version != data.version:
            raise HealthVisionError("version_conflict", "餐单版本已变化", 409)
        member_id = plan.member_id
    return await create_consultation(
        uid,
        member_id,
        ConsultationInput(client_request_id=data.client_request_id),
        agent_slug=QUALITY_SLUG,
        quality_selection=(plan_id, data.version, data.rule_code),
    )


async def require_quality_run(session, context):
    """工具身份从当前PG执行Owner、成员绑定和独立用途取得。"""
    from yuxi.services.health_consultation_service import require_consultation

    run = await HealthConsultationRepository(session).require_attempt(context, lock=True)
    if run.agent_slug != QUALITY_SLUG:
        raise HealthVisionError("execution_not_owned", "此工具仅用于质量检查运行", 409)
    expected = (run.input_payload or {}).get("health_processing")
    if expected is None:
        raise HealthVisionError("policy_changed", "质量检查缺少处理审批快照", 409)
    binding, _ = await require_consultation(
        session, context.uid, context.thread_id, context.model, expected=expected, lock=True
    )
    selected = await HealthQualityRepository(session).selected(binding)
    require_single_member_plan(await HealthQualityRepository(session).plan(context.uid, selected.plan_id))
    return run, binding, selected


def quality_tool_context(current):
    """仅发送选定方案所需的分类及条款，避免整份全局目录进入模型。"""
    rules = deepcopy(current["rules"])
    if rules["payload"] is not None:
        rules["payload"]["ingredient_classifications"] = [
            c for c in rules["payload"]["ingredient_classifications"] if c["food_id"] in current["ingredients"]
        ]
    return {
        "scope": "quality_context",
        "sources": current["sources"],
        "plan": current["plan_snapshot"],
        "profile": current["profile"],
        "rules": rules,
        "professional_review": "not_a_professional_decision",
    }


async def selected_quality_context(context):
    """固定读取工具无模型提供的身份或版本参数。"""
    async with pg_manager.get_async_session_context() as session:
        _, _, selected = await require_quality_run(session, context)
        return quality_tool_context(await quality_context_in_session(session, context.uid, selected))


async def check_selected_quality(context):
    """本Request派生幂等键，在业务绑定内保存工程检查回执。"""
    async with pg_manager.get_async_session_context() as session:
        key = uuid5(NAMESPACE_URL, f"health-quality-run:{context.uid}:{context.request_id}")
        # 请求锁先于成员锁，与HTTP检查/专业动作顺序一致。
        await HealthQualityRepository(session).lock_request(context.uid, str(key))
        run, _, selected = await require_quality_run(session, context)
        data = QualityCheckInput(client_request_id=key, version=selected.plan_version, rule_code=selected.rule_code)
        return quality_result(await check_plan_in_session(session, context.uid, selected.plan_id, data, run_id=run.id))


async def quality_answer_in_session(session, uid, run, binding, selected, answer):
    """最终正文是本Run回执投影或带当前来源的澄清问题。"""
    current = await quality_context_in_session(session, uid, selected)
    if answer.questions:
        return {
            "result_type": "needs_input",
            "sources": current["sources"],
            "questions": answer.questions,
            "professional_review": "not_a_professional_decision",
        }
    check = await session.get(HealthQualityCheck, str(answer.check_id))
    if (
        check is None
        or check.actor_uid != uid
        or check.run_id != run.id
        or check.plan_id != selected.plan_id
        or check.plan_version != selected.plan_version
        or check.rule_code != selected.rule_code
    ):
        raise HealthVisionError("quality_receipt_invalid", "只能使用本Run选定对象的检查回执", 409)
    await validate_quality_check(session, uid, check)
    return quality_result(check)


async def quality_final_result(context, text):
    """模型最终选择器严格解析，任意批准字段拒绝。"""
    try:
        answer = QualityAnswer.model_validate_json(text)
    except (ValidationError, ValueError, TypeError):
        raise HealthVisionError("quality_answer_invalid", "质量结果须选择本轮检查收据或补充问题", 409) from None
    async with pg_manager.get_async_session_context() as session:
        run, binding, selected = await require_quality_run(session, context)
        return await quality_answer_in_session(session, context.uid, run, binding, selected, answer)


async def validate_quality_tool_payload(session, uid, binding, run, name, payload, *, allow_history=False):
    """checkpoint和PG审计共享完整投影核对，不能只保留相同来源伪造内容。"""
    repo = HealthQualityRepository(session)
    selected = await repo.selected(binding)
    current = await quality_context_in_session(session, uid, selected)
    try:
        if name == "get_quality_review_context":
            expected = quality_tool_context(current)
        elif name == "final" and payload.get("result_type") == "needs_input":
            answer = QualityAnswer(questions=payload["questions"])
            expected = await quality_answer_in_session(session, uid, run, binding, selected, answer)
        else:
            check = await session.get(HealthQualityCheck, payload["check_id"])
            receipt_run_matches = check is not None and check.run_id == run.id
            if check is not None and not receipt_run_matches and allow_history and check.run_id is not None:
                from yuxi.storage.postgres.models_business import AgentRun

                original = await session.get(AgentRun, check.run_id)
                receipt_run_matches = (
                    original is not None
                    and original.uid == uid
                    and original.agent_slug == QUALITY_SLUG
                    and original.conversation_id == binding.conversation_id
                )
            if (
                check is None
                or check.actor_uid != uid
                or not receipt_run_matches
                or check.plan_id != selected.plan_id
                or check.plan_version != selected.plan_version
                or check.rule_code != selected.rule_code
            ):
                raise ValueError("收据归属不符")
            await validate_quality_check(session, uid, check)
            expected = quality_result(check)
        if payload != expected:
            raise ValueError("投影内容不符")
    except (KeyError, TypeError, ValueError):
        raise HealthVisionError("source_invalidated", "质量检查来源或收据无法核对", 410) from None


async def validate_quality_publication(session, run, text):
    """发布Owner事务复核当前来源、审批同意与收据后才发布Message。"""
    from yuxi.services.health_consultation_service import require_consultation

    binding, _ = await require_consultation(
        session,
        run.uid,
        run.conversation_thread_id,
        expected=(run.input_payload or {}).get("health_processing"),
        lock=True,
    )
    selected = await HealthQualityRepository(session).selected(binding)
    try:
        payload = json.loads(text)
        answer = QualityAnswer(check_id=payload.get("check_id"), questions=payload.get("questions", []))
    except (ValueError, TypeError):
        raise HealthVisionError("quality_answer_invalid", "待发布质量结果无法解析", 409) from None
    current = await quality_answer_in_session(session, run.uid, run, binding, selected, answer)
    if current != payload:
        raise HealthVisionError("source_invalidated", "质量来源或最终检查内容已变化", 410)

"""有效采用、用户库存及独立用途构成受控采购需求与Run回执。"""

import json
from copy import deepcopy
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from uuid import uuid4

from pydantic import ValidationError
from sqlalchemy import and_, or_, select

from yuxi.repositories.health_consultation_repository import HealthConsultationRepository, PURCHASE_SLUG
from yuxi.repositories.health_plan_adoption_repository import HealthPlanAdoptionRepository, adoption_member_ids
from yuxi.repositories.health_purchase_repository import HealthPurchaseRepository
from yuxi.repositories.health_vision_repository import HealthVisionRepository
from yuxi.services.health_nutrition_service import input_fingerprint
from yuxi.services.health_plan_adoption_service import adoption_result
from yuxi.services.health_purchase_types import PURCHASE_TOOLS, PurchaseAnswer, PurchaseSelection
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_business import AgentRun, Conversation, Message, TOOL_AUDIT_MESSAGE_TYPE
from yuxi.storage.postgres.models_health import HealthMealPlanAdoption, HealthPurchasePreview

EXTERNAL_PURCHASE_DEPENDENCIES = [
    "purchase_weight_conversion",
    "sku_catalog",
    "merchant_inventory_delivery_price",
    "shopping_cart_order_payment_refund",
]


async def purchase_requirements(uid, member_id, selected):
    """普通业务读取无需模型处理同意，仍核对全部参与者与当前采用。"""
    async with pg_manager.get_async_session_context() as session:
        current = await purchase_context_in_session(session, uid, member_id, selected, model_use=False)
        return current


async def purchase_context_in_session(session, uid, member_id, selected, *, model_use=True):
    """先排序锁全体成员，再核对独立采购同意和专业采用来源。"""
    row = await session.get(HealthMealPlanAdoption, str(selected.adoption_id), populate_existing=True)
    if row is None or row.actor_uid != uid or member_id not in adoption_member_ids(row):
        raise HealthVisionError("not_found", "采用餐单不存在或无权访问", 404)
    ids = adoption_member_ids(row)
    health = HealthVisionRepository(session)
    for item in ids:
        await health.authorize(item, uid, "diet_edit", lock=True)
        if model_use:
            await health.authorize(item, uid, "ai_use")
    await session.refresh(row)
    if adoption_member_ids(row) != ids:
        raise HealthVisionError("source_invalidated", "采用参与者已变化，请重新选择", 410)
    if model_use:
        from yuxi.services.health_vision_service import health_vision_service

        configuration = await health_vision_service.configuration(session)
        approved = configuration["purchase"]
        if not approved["available"]:
            raise HealthVisionError("purchase_unavailable", "采购处理用途尚未审批或配置已变化", 503)
        processing = {
            "model": approved["model"],
            "processor": approved["processor"],
            "policy_version": configuration["policy_version"],
        }
        for item in ids:
            await health.require_consent(item, uid, "purchase", processing)
    row = await HealthPlanAdoptionRepository(session).adoption(uid, row.id)
    current = await adoption_result(session, uid, row)
    if (
        not current["current"]
        or current["version"] != selected.adoption_version
        or current["plan_version"] != selected.plan_version
    ):
        raise HealthVisionError("source_invalidated", "采用、餐单版本或专业来源已变化，请重新选择", 410)
    requirements = calculate_purchase_requirements(current["snapshot"], selected)
    sources = {key: current[key] for key in ("adoption_id", "version", "plan_id", "plan_version", "plan_date")}
    sources["adoption_version"] = sources.pop("version")
    source_hash = input_fingerprint(
        {"sources": current["sources"], "snapshot": current["snapshot"], "selection": selected.model_dump(mode="json")}
    )
    return {
        "scope": "adopted_plan_ingredient_requirements",
        "member_id": member_id,
        "member_ids": ids,
        "sources": sources,
        "source_hash": source_hash,
        **requirements,
    }


async def authorize_purchase_binding(session, binding):
    """私有运行和历史都重验不可变采用、库存选择及全部来源。"""
    require_purchase_binding(binding)
    try:
        stored = binding.purchase_selection
        selected = PurchaseSelection.model_validate(stored["selection"])
        current = await purchase_context_in_session(session, binding.actor_uid, binding.member_id, selected)
        if current["source_hash"] != stored["source_hash"]:
            raise HealthVisionError("source_invalidated", "采购来源已变化，请重新选择", 410)
    except (ValidationError, KeyError, TypeError):
        raise HealthVisionError("source_invalidated", "采购线程选择无法核对", 410) from None
    binding._purchase_current = current
    return selected, current


async def read_purchase_for_run(context):
    """模型只看到净需求和采用版本，不接收专业档案或病历。"""
    async with pg_manager.get_async_session_context() as session:
        _, binding = await require_purchase_run(session, context)
        return purchase_context_result(binding)


async def preview_purchase_for_run(context):
    """唯一有效attempt原子保存同Run回执，重复调用不重复生成。"""
    async with pg_manager.get_async_session_context() as session:
        run, binding = await require_purchase_run(session, context)
        repo = HealthPurchaseRepository(session)
        receipt = await repo.for_run(run.id)
        current = purchase_context_result(binding)
        if receipt is None:
            await HealthConsultationRepository(session).require_attempt(context)
            receipt = HealthPurchasePreview(
                id=str(uuid4()),
                actor_uid=context.uid,
                conversation_id=binding.conversation_id,
                run_id=run.id,
                snapshot=current,
            )
            session.add(receipt)
            await session.flush()
        if (
            receipt.actor_uid != context.uid
            or receipt.conversation_id != binding.conversation_id
            or receipt.snapshot != current
        ):
            raise HealthVisionError("source_invalidated", "采购回执来源已变化", 410)
        return purchase_preview_result(receipt)


async def purchase_final_result(context, text):
    """最终模型正文只选择本Run回执或有限补充问题。"""
    try:
        answer = PurchaseAnswer.model_validate_json(text)
    except (ValidationError, TypeError):
        raise HealthVisionError("purchase_output_invalid", "采购回答须引用当前运行回执或补充问题", 409) from None
    async with pg_manager.get_async_session_context() as session:
        run, binding = await require_purchase_run(session, context)
        return await purchase_answer_in_session(session, run, binding, answer)


async def require_purchase_run(session, context):
    """工具身份来自worker，授权与等待后租约共同检查。"""
    from yuxi.services.health_consultation_service import require_consultation

    repo = HealthConsultationRepository(session)
    run = await repo.require_attempt(context, lock=True)
    if run.agent_slug != PURCHASE_SLUG:
        raise HealthVisionError("execution_not_owned", "此工具只用于采购助手运行", 409)
    expected = (run.input_payload or {}).get("health_processing")
    if not expected:
        raise HealthVisionError("policy_changed", "采购运行缺少独立处理审批快照", 409)
    binding, _ = await require_consultation(
        session, context.uid, context.thread_id, context.model, expected=expected, lock=True
    )
    await repo.require_attempt(context)
    require_purchase_binding(binding)
    return run, binding


async def purchase_answer_in_session(session, run, binding, answer):
    """发布结果来自权威PG回执且完整内容仍等于当前净需求。"""
    if answer.questions:
        return {
            "scope": "adopted_plan_ingredient_requirements",
            "member_id": binding.member_id,
            "status": "needs_input",
            "questions": answer.questions,
            "purchase_available": False,
            "order_available": False,
        }
    receipt = await session.get(HealthPurchasePreview, str(answer.preview_id))
    if (
        receipt is None
        or receipt.actor_uid != run.uid
        or receipt.run_id != run.id
        or receipt.conversation_id != binding.conversation_id
    ):
        raise HealthVisionError("purchase_receipt_invalid", "采购回执不属于当前运行", 409)
    if receipt.snapshot != purchase_context_result(binding):
        raise HealthVisionError("source_invalidated", "采购回执与当前来源不符", 410)
    return purchase_preview_result(receipt)


async def validate_purchase_publication(session, run, text):
    """最终Message事务再次核对独立用途、采用和完整结果。"""
    from yuxi.services.health_consultation_service import require_consultation

    processing = (run.input_payload or {}).get("health_processing")
    if not isinstance(processing, dict) or not processing.get("purchase_selection_hash"):
        raise HealthVisionError("policy_changed", "采购运行缺少固定选择快照", 409)
    binding, _ = await require_consultation(
        session, run.uid, run.conversation_thread_id, expected=processing, lock=True
    )
    if binding.conversation_id != run.conversation_id or run.agent_slug != PURCHASE_SLUG:
        raise HealthVisionError("source_invalidated", "采购发布所属线程或角色不符", 410)
    try:
        payload = json.loads(text)
        answer = PurchaseAnswer(preview_id=payload.get("preview_id"), questions=payload.get("questions", []))
    except (ValidationError, ValueError, TypeError, AttributeError):
        raise HealthVisionError("purchase_output_invalid", "采购待发布结果无法解析", 409) from None
    expected = await purchase_answer_in_session(session, run, binding, answer)
    if expected != payload:
        raise HealthVisionError("source_invalidated", "采购待发布结果与服务器回执不符", 410)


async def validate_purchase_tool_payload(session, binding, name, payload, *, receipt_run_id=None):
    """旧checkpoint工具必须是固定范围内真实回执及当前完整投影。"""
    if name == PURCHASE_TOOLS[0]:
        if payload != purchase_context_result(binding):
            raise HealthVisionError("source_invalidated", "采购上下文历史已变化", 410)
        return
    if name != PURCHASE_TOOLS[1]:
        raise HealthVisionError("source_invalidated", "采购历史工具不属于固定模式", 410)
    try:
        receipt = await session.get(HealthPurchasePreview, payload["preview_id"])
        original = await session.get(AgentRun, receipt.run_id) if receipt is not None else None
        conversation = await session.get(Conversation, binding.conversation_id)
        processing = (original.input_payload or {}).get("health_processing") if original else None
        if (
            receipt is None
            or receipt.actor_uid != binding.actor_uid
            or receipt.conversation_id != binding.conversation_id
            or (receipt_run_id is not None and receipt.run_id != receipt_run_id)
            or original is None
            or original.uid != binding.actor_uid
            or original.agent_slug != PURCHASE_SLUG
            or original.conversation_id != binding.conversation_id
            or conversation is None
            or original.conversation_thread_id != conversation.thread_id
            or not isinstance(processing, dict)
            or processing.get("purchase_selection_hash") != input_fingerprint(binding.purchase_selection)
            or receipt.snapshot != purchase_context_result(binding)
            or payload != purchase_preview_result(receipt)
        ):
            raise HealthVisionError("source_invalidated", "采购历史回执身份、来源或内容不符", 410)
    except (KeyError, TypeError):
        raise HealthVisionError("source_invalidated", "采购checkpoint无法核对", 410) from None


async def validate_purchase_history(session, binding):
    """所有历史成功工具与最终输出均复核原Run和不可变选择。"""
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
            not isinstance(processing, dict)
            or processing.get("purchase_selection_hash") != input_fingerprint(binding.purchase_selection)
            or run.uid != binding.actor_uid
            or run.agent_slug != PURCHASE_SLUG
            or conversation is None
            or run.conversation_thread_id != conversation.thread_id
            or message.conversation_id != binding.conversation_id
        ):
            raise HealthVisionError("source_invalidated", "采购历史运行选择不符", 410)
        try:
            payload = json.loads(message.content)
            if message.message_type == TOOL_AUDIT_MESSAGE_TYPE:
                await validate_purchase_tool_payload(
                    session, binding, (message.extra_metadata or {}).get("tool_name"), payload, receipt_run_id=run.id
                )
            else:
                answer = PurchaseAnswer(preview_id=payload.get("preview_id"), questions=payload.get("questions", []))
                if payload != await purchase_answer_in_session(session, run, binding, answer):
                    raise HealthVisionError("source_invalidated", "采购历史正文与服务器回执不符", 410)
        except (ValidationError, ValueError, TypeError, AttributeError):
            raise HealthVisionError("source_invalidated", "采购历史正文无法核对", 410) from None


def purchase_context_result(binding):
    """移除内部专业来源摘要，仅向模型开放最小食材需求。"""
    require_purchase_binding(binding)
    return deepcopy({key: value for key, value in binding._purchase_current.items() if key != "source_hash"})


def purchase_preview_result(receipt):
    """同Run回执与需求结果一起由服务器投影。"""
    return {"preview_id": receipt.id, "run_id": receipt.run_id, "result": deepcopy(receipt.snapshot)}


def require_purchase_binding(binding):
    """采购选择不能与任何配餐模式混用。"""
    if getattr(binding, "purchase_selection", None) is None or any(
        getattr(binding, name, None) is not None
        for name in ("family_planner_selection", "initial_planner_selection", "safe_planner_selection")
    ):
        raise HealthVisionError("purchase_selection_required", "请从明确选定采用与库存的采购入口创建线程", 409)


def calculate_purchase_requirements(snapshot, selected):
    """只汇总既有配方可食克数，家庭逐人成品份量不重复计公共菜。"""
    try:
        plans = list(snapshot["members"].values()) if snapshot.get("scope") == "family_recipe_draft" else [snapshot]
        grouped = {}
        for plan in plans:
            for meal in plan["meals"]:
                food_states = {}
                for source in meal["nutrition"]["sources"]:
                    for ingredient in source.get("ingredients", []):
                        food = ingredient["food"]
                        food_states[food["id"]] = food["cooking_state"]
                for dish in meal["dishes"]:
                    for ingredient in dish["ingredients"]:
                        food_id, name = ingredient["food_id"], ingredient["name"]
                        state = food_states[food_id]
                        key = (food_id, state)
                        if key not in grouped:
                            grouped[key] = {
                                "food_id": food_id,
                                "name": name,
                                "cooking_state": state,
                                "required": Decimal(0),
                            }
                        raw = ingredient["planned_grams"]
                        grams = Decimal(raw) if raw is not None else None
                        if grams is not None and (not grams.is_finite() or grams < 0):
                            raise ValueError("invalid source quantity")
                        grouped[key]["required"] = (
                            None
                            if grams is None or grouped[key]["required"] is None
                            else grouped[key]["required"] + grams
                        )
        inventory = {(str(item.food_id), item.cooking_state): item.edible_grams for item in selected.inventory}
        if set(inventory) - set(grouped):
            raise HealthVisionError("inventory_mapping_mismatch", "库存须属于当前需求的同食品版本及烹饪状态", 409)
        if not grouped:
            raise ValueError("empty adopted ingredients")
    except (KeyError, TypeError, ValueError, InvalidOperation):
        raise HealthVisionError("source_invalidated", "采用配方的食材需求无法核对", 410) from None
    items, missing = [], []
    if not selected.inventory_confirmed:
        missing.append("inventory_confirmation")
    for key, item in sorted(grouped.items()):
        required = item.pop("required")
        available = inventory.get(key, Decimal(0)) if selected.inventory_confirmed else None
        net = max(Decimal(0), required - available) if required is not None and available is not None else None
        if required is None:
            missing.append(f"ingredient_quantity:{key[0]}")
        items.append(
            {
                **item,
                "unit": "edible_g",
                "required_grams": quantity(required),
                "inventory_grams": quantity(available),
                "net_required_grams": quantity(net),
            }
        )
    return {
        "status": "needs_input" if missing else "requirements_ready",
        "inventory_confirmed": selected.inventory_confirmed,
        "items": items,
        "missing_fields": missing,
        "missing_dependencies": list(EXTERNAL_PURCHASE_DEPENDENCIES),
        "sku_candidates": [],
        "purchase_available": False,
        "order_available": False,
    }


def quantity(value):
    """已知可食量按六位小数公开，未知保持为空。"""
    return str(value.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)) if value is not None else None

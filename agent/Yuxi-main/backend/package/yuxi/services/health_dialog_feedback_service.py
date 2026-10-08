"""从显式业务选餐及本轮原文保存单餐反馈，不由模型猜测来源。"""

from uuid import NAMESPACE_URL, uuid5

from yuxi.repositories.health_dialog_feedback_repository import HealthDialogFeedbackRepository
from yuxi.repositories.health_meal_feedback_repository import HealthMealFeedbackRepository
from yuxi.repositories.health_memory_repository import HealthMemoryRepository
from yuxi.services.health_meal_feedback_service import save_feedback_in_session
from yuxi.services.health_meal_feedback_types import DialogFeedbackAnswer, MealFeedbackChange
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_health import HealthFeedbackWrite

CONSUMPTION_LABELS = {
    "未知": "unknown",
    "全部": "all",
    "大部分": "most",
    "一半": "half",
    "少量": "little",
    "未吃": "none",
}
TAG_LABELS = {
    "偏咸": "too_salty",
    "偏油": "too_oily",
    "偏甜": "too_sweet",
    "偏辣": "too_spicy",
    "份量多": "portion_large",
    "份量少": "portion_small",
    "餐后不适": "discomfort",
}


async def create_feedback_conversation(uid, record_id, data):
    """业务入口验证用户选餐后创建固定分析用途的反馈会话。"""
    from yuxi.repositories.health_consultation_repository import ANALYST_SLUG
    from yuxi.services.health_consultation_service import create_consultation

    async with pg_manager.get_async_session_context() as session:
        record = await HealthMealFeedbackRepository(session).require_record(uid, record_id)
        member_id = record.member_id
    return await create_consultation(
        uid,
        member_id,
        data,
        agent_slug=ANALYST_SLUG,
        feedback_selection=(record_id, data.source_version),
    )


def dialog_feedback_details(quote, original, current=None):
    """只接受本轮完整原文及明确结构字段，自由自述不推断标签。"""
    if quote != original.strip() or not quote.startswith(("记录这餐反馈：", "更新这餐反馈：")):
        raise HealthVisionError("feedback_source_invalid", "请用本轮完整原文明确记录或更新这餐反馈", 422)
    body = quote.split("：", 1)[1].strip()
    if not body:
        raise HealthVisionError("feedback_source_invalid", "请填写这餐的反馈内容", 422)
    values = dict(current or {"consumption": "unknown", "tags": []})
    values["comment"] = body
    seen = set()
    for part in body.split("；"):
        key, separator, value = part.strip().partition("：")
        if not separator or key not in {"吃完程度", "口味", "自述"}:
            continue
        if key in seen:
            raise HealthVisionError("feedback_source_invalid", "反馈字段不能重复", 422)
        seen.add(key)
        if key == "吃完程度":
            if value not in CONSUMPTION_LABELS:
                raise HealthVisionError("feedback_source_invalid", "请明确填写吃完程度", 422)
            values["consumption"] = CONSUMPTION_LABELS[value]
        elif key == "口味":
            labels = value.split("、") if value != "无" else []
            if len(set(labels)) != len(labels) or any(label not in TAG_LABELS for label in labels):
                raise HealthVisionError("feedback_source_invalid", "请核对口味标签", 422)
            values["tags"] = [TAG_LABELS[label] for label in labels]
    return values


async def selected_feedback_context(session, context):
    """当前分析执行须属于服务器选餐会话，普通分析不能写反馈。"""
    from yuxi.services.health_diet_analysis_service import require_analyst_run

    binding = await require_analyst_run(session, context, allow_feedback=True)
    repo = HealthDialogFeedbackRepository(session)
    selection = await repo.selection(binding)
    if selection is None:
        raise HealthVisionError("feedback_selection_required", "请先明确选择这餐再进入反馈会话", 409)
    record, _ = await repo.source(context.uid, binding, selection)
    return binding, selection, record


async def is_feedback_conversation(context):
    """构图及最终输出模式以当前PG绑定为准。"""
    from yuxi.services.health_diet_analysis_service import require_analyst_run

    async with pg_manager.get_async_session_context() as session:
        binding = await require_analyst_run(session, context, allow_feedback=True)
        return await HealthDialogFeedbackRepository(session).selection(binding) is not None


async def selected_meal_feedback(context):
    """只读取用户所选来源及当前编辑版本，不解释旧反馈正文。"""
    async with pg_manager.get_async_session_context() as session:
        _, selection, record = await selected_feedback_context(session, context)
        feedback = await HealthMealFeedbackRepository(session).slot(context.uid, record.id)
        return {
            "records": [{"record_id": record.id, "source_version": selection.source_version}],
            "meal_type": record.snapshot["meal"]["meal_type"],
            "eaten_at": record.snapshot["meal"]["eaten_at"],
            "feedback_version": feedback.version if feedback else 0,
            "selection_source": "user_business_selection",
            "nutrition_recalculated": False,
        }


async def record_selected_feedback(context, data):
    """运行和成员锁内原子保存反馈、不可变修订与当前原消息来源。"""
    async with pg_manager.get_async_session_context() as session:
        from yuxi.repositories.health_consultation_repository import HealthConsultationRepository

        request_key = uuid5(NAMESPACE_URL, f"health-dialog-feedback:{context.uid}:{context.request_id}")
        # 与管理入口保持Request→Member锁序，不能在持成员锁后等待同一请求键。
        await HealthConsultationRepository(session).lock_request(context.uid, str(request_key))
        binding, selection, record = await selected_feedback_context(session, context)
        run = await HealthConsultationRepository(session).require_attempt(context, lock=True)
        source = await HealthMemoryRepository(session).source_message(run)
        if source is None or source.conversation_id != binding.conversation_id:
            raise HealthVisionError("feedback_source_invalid", "当前服务器用户消息无法核对", 409)
        repo = HealthDialogFeedbackRepository(session)
        prior = await repo.write(binding.conversation_id)
        if prior and prior.run_id != run.id:
            raise HealthVisionError("feedback_session_used", "请重新选择这餐以修改反馈", 409)
        feedback_repo = HealthMealFeedbackRepository(session)
        feedback = await feedback_repo.slot(context.uid, record.id)
        # 重放以不可变原收据为基础，不能把当前编辑后的字段拼成另一操作。
        receipt = await feedback_repo.receipt(context.uid, str(request_key))
        details = dialog_feedback_details(
            data.quote,
            source.content,
            receipt.details if receipt else (feedback.details if feedback and feedback.status == "active" else None),
        )
        change = MealFeedbackChange(client_request_id=request_key, version=data.version, **details)
        await save_feedback_in_session(session, context.uid, record.id, change)
        receipt = await feedback_repo.receipt(context.uid, str(request_key))
        if prior is None:
            prior = HealthFeedbackWrite(
                revision_id=receipt.id,
                source_message_id=source.id,
                run_id=run.id,
                conversation_id=binding.conversation_id,
            )
            session.add(prior)
            await session.flush()
        if prior.revision_id != receipt.id or prior.source_message_id != source.id:
            raise HealthVisionError("request_conflict", "本轮反馈来源不一致", 409)
        return await repo.result(context.uid, binding, selection, prior)


async def dialog_feedback_final(session, uid, binding, selection, run_id, answer):
    """提问保留选餐来源，成功必须有当前Run的服务器写入凭据。"""
    repo = HealthDialogFeedbackRepository(session)
    await repo.source(uid, binding, selection)
    write = await repo.write(binding.conversation_id)
    if write is not None and write.run_id == run_id:
        # 副作用已提交时展示真实收据，模型提问不能掩盖已保存状态。
        return await repo.result(uid, binding, selection, write)
    if answer.questions:
        return {
            "result_type": "meal_feedback",
            "status": "needs_input",
            "scope": "single_meal_feedback",
            "records": [{"record_id": selection.diet_log_id, "source_version": selection.source_version}],
            "questions": answer.questions,
            "nutrition_recalculated": False,
        }
    if write is None or write.run_id != run_id:
        raise HealthVisionError("feedback_receipt_invalid", "本轮没有可核对的反馈写入", 409)
    return await repo.result(uid, binding, selection, write)


async def feedback_final_result(context, text):
    """模型选择收据或提问，反馈正文始终来自服务器来源。"""
    try:
        answer = DialogFeedbackAnswer.model_validate_json(text)
    except ValueError:
        raise HealthVisionError("feedback_output_invalid", "反馈输出必须选择本轮收据或提出问题", 422) from None
    async with pg_manager.get_async_session_context() as session:
        binding, selection, _ = await selected_feedback_context(session, context)
        return await dialog_feedback_final(session, context.uid, binding, selection, context.run_id, answer)

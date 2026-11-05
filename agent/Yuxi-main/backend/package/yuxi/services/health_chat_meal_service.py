"""咨询工具中的实际饮食自动保存、真实回执和保留历史的撤销。"""

from copy import deepcopy
from uuid import uuid4

from yuxi.repositories.health_chat_meal_repository import HealthChatMealRepository
from yuxi.repositories.health_consultation_repository import HealthConsultationRepository
from yuxi.repositories.health_diet_correction_repository import HealthDietCorrectionRepository
from yuxi.repositories.health_memory_repository import HealthMemoryRepository
from yuxi.repositories.health_vision_repository import HealthVisionRepository
from yuxi.services.health_chat_meal_types import ChatMealRecordingInput, meal_from_statement
from yuxi.services.health_meal_recording_service import record_meal
from yuxi.services.health_nutrition_service import input_fingerprint
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_health import DietLogRevision, MealFeedbackRevision, VisionConfirmation, VisionDraft
from yuxi.utils.datetime_utils import format_utc_datetime, utc_now_naive


async def record_chat_meal(context, statement):
    """仅有效咨询 Worker 可把本轮已吃原文原子写入正式记录。"""
    from yuxi.services.health_consultation_service import require_consultation

    async with pg_manager.get_async_session_context() as session:
        run = await HealthConsultationRepository(session).require_attempt(context, lock=True)
        snapshot = (run.input_payload or {}).get("health_processing")
        if not snapshot:
            raise HealthVisionError("policy_changed", "咨询缺少处理审批快照", 409)
        await require_consultation(session, context.uid, context.thread_id, context.model, expected=snapshot)
        if run.agent_slug != "health-consultation":
            raise HealthVisionError("meal_context_invalid", "实际记餐仅在营养咨询中提供", 409)
        source = await HealthMemoryRepository(session).source_message(run)
        if source is None or not isinstance(source.content, str):
            raise HealthVisionError("meal_source_invalid", "当前用户消息无法核对", 409)
        repo = HealthVisionRepository(session)
        access = await repo.list_member_access(context.uid)
        members = [member for member, scopes in access if {"ai_use", "diet_edit"} <= scopes]
        aliases = {"妈妈": "母亲", "爸爸": "父亲", "老公": "配偶", "老婆": "配偶"}
        if statement.subject == "我":
            candidates = [m for m in members if m.owner_uid == context.uid and m.relationship_label == "本人"]
        else:
            candidates = [
                m
                for m in members
                if statement.subject in {m.display_name, m.relationship_label}
                or aliases.get(statement.subject) == m.relationship_label
            ]
        if len(candidates) != 1:
            raise HealthVisionError("meal_subject_unclear", "无法唯一对应家庭成员，请先明确是哪位成员", 422)
        member = candidates[0]
        # 跨成员记餐仍分别校验目标成员的 AI 使用及实际饮食编辑授权。
        await repo.authorize(member.id, context.uid, "ai_use")
        await repo.authorize(member.id, context.uid, "diet_edit")
        await repo.require_consent(member.id, context.uid, "consultation", snapshot)
        sources = await HealthChatMealRepository(session).user_sources(run, source)
        request_id, meal = meal_from_statement(statement, sources, member.id)
        await record_meal(
            context.uid,
            ChatMealRecordingInput(member_id=member.id, client_request_id=request_id, meal=meal),
            session=session,
            recording={
                "source": "chat_actual_intake",
                "time_known": False,
                "source_message_ids": [row.id for row in sources if row.content.strip() in statement.source_quotes],
                "references": [{"thread_id": context.thread_id, "request_id": run.request_id}],
            },
        )
        # 提交前重新核对本轮的处理授权，工具不能绕开咨询审批。
        await require_consultation(session, context.uid, context.thread_id, context.model, expected=snapshot)
        await repo.authorize(member.id, context.uid, "ai_use")
        await repo.require_consent(member.id, context.uid, "consultation", snapshot)
        records = await chat_meal_receipts(session, context.uid, {"request_id": run.request_id})
        return {"recorded_meals": records, "notice": "只按真实状态说明已保存或已撤销；缺失份量和营养保持未知。"}


async def chat_meal_receipts(session, uid, reference):
    """任务和历史共用当前授权及记录回读，模型正文不拥有保存状态。"""
    result = []
    for record in await HealthChatMealRepository(session).receipts(uid, reference):
        try:
            member = await HealthVisionRepository(session).authorize(record.member_id, uid, "diet_edit")
        except HealthVisionError as error:
            if error.status == 404:
                continue
            raise
        item = chat_meal_receipt(record, member)
        item["request_ids"] = [
            row["request_id"]
            for row in record.snapshot["recording"]["references"]
            if all(row.get(key) == value for key, value in reference.items())
        ]
        result.append(item)
    return result


async def read_chat_meal(uid, record_id):
    """卡片重新打开时核对当前状态，撤回记录仍可读取撤回收据。"""
    async with pg_manager.get_async_session_context() as session:
        record, member, _ = await require_chat_meal(session, uid, record_id)
        return chat_meal_receipt(record, member)


async def withdraw_chat_meal(uid, record_id, data):
    """成员锁、版本和账号级收据保证撤销可重试，保留原事实与修订。"""
    request_id = str(data.client_request_id)
    fingerprint = input_fingerprint(
        {"operation": "withdraw_chat_meal", "record_id": record_id, **data.model_dump(mode="json")}
    )
    async with pg_manager.get_async_session_context() as session:
        await HealthConsultationRepository(session).lock_request(uid, request_id)
        record, member, confirmation = await require_chat_meal(session, uid, record_id, lock=True)
        repo = HealthDietCorrectionRepository(session)
        receipt = await repo.receipt(uid, request_id)
        if receipt:
            if receipt.fingerprint != fingerprint:
                raise HealthVisionError("idempotency_conflict", "同一撤销请求不能修改内容", 409)
            return chat_meal_receipt(record, member)
        if record.version != data.expected_version or record.snapshot["recording"].get("withdrawn_at"):
            raise HealthVisionError("version_conflict", "这条饮食记录已变化，请刷新后操作", 409)
        if not await repo.revisions(record.id):
            session.add(
                DietLogRevision(
                    id=str(uuid4()),
                    diet_log_id=record.id,
                    version=record.version,
                    calculation_id=record.calculation_id,
                    actor_uid=confirmation.actor_uid,
                    reason="原确认快照",
                    snapshot=deepcopy(record.snapshot),
                    created_at=record.created_at,
                )
            )
        now = utc_now_naive()
        record.version += 1
        record.snapshot = {
            **record.snapshot,
            "recording": {
                **record.snapshot["recording"],
                "withdrawn_at": format_utc_datetime(now),
                "withdrawn_by": uid,
            },
        }
        draft = await session.get(VisionDraft, confirmation.draft_id, populate_existing=True)
        draft.review_status = "withdrawn"
        session.add(
            DietLogRevision(
                id=str(uuid4()),
                diet_log_id=record.id,
                version=record.version,
                calculation_id=record.calculation_id,
                actor_uid=uid,
                request_id=request_id,
                fingerprint=fingerprint,
                reason="用户撤销对话记餐",
                snapshot=deepcopy(record.snapshot),
            )
        )
        for feedback in await repo.active_feedback(record.id):
            feedback.version += 1
            feedback.status = "invalidated"
            feedback.updated_at = now
            session.add(
                MealFeedbackRevision(
                    id=str(uuid4()),
                    feedback_id=feedback.id,
                    actor_uid=feedback.actor_uid,
                    request_id=str(uuid4()),
                    fingerprint=fingerprint,
                    version=feedback.version,
                    details=deepcopy(feedback.details),
                    status="invalidated",
                )
            )
        await session.flush()
        return chat_meal_receipt(record, member)


async def require_chat_meal(session, uid, record_id, *, lock=False):
    """可撤销范围限本账号创建且仍有当前成员饮食权限的对话记录。"""
    record = await HealthDietCorrectionRepository(session).record(uid, record_id, lock=lock)
    confirmation = await session.get(VisionConfirmation, record.confirmation_id)
    if (
        confirmation is None
        or confirmation.actor_uid != uid
        or record.snapshot.get("recording", {}).get("source") != "chat_actual_intake"
    ):
        raise HealthVisionError("not_found", "对话记餐不存在或无权访问", 404)
    member = await HealthVisionRepository(session).authorize(record.member_id, uid, "diet_edit")
    return record, member, confirmation


def chat_meal_receipt(record, member):
    """卡片只公开成员、菜品与当前状态，不泄露来源消息和账号元数据。"""
    meal = record.snapshot["meal"]
    return {
        "id": record.id,
        "member_id": record.member_id,
        "member_name": member.display_name,
        "source_version": record.version,
        "status": "withdrawn" if record.snapshot["recording"].get("withdrawn_at") else "saved",
        "meal_type": meal["meal_type"],
        "eaten_at": meal["eaten_at"],
        "time_known": False,
        "items": [
            {
                "name": item["name"],
                "grams": item.get("grams"),
                "quantity_text": next(
                    (
                        text.removeprefix("本人份量原文：")
                        for text in item.get("uncertainties", [])
                        if text.startswith("本人份量原文：")
                    ),
                    "未知",
                ),
            }
            for item in meal["items"]
            if not item.get("excluded")
        ],
    }

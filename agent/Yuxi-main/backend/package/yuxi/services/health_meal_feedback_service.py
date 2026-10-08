"""已确认餐次的用户反馈及撤回后的模型输入隔离。"""

from contextlib import nullcontext
import hashlib
import json
from uuid import uuid4
from langchain_core.messages import HumanMessage
from yuxi.repositories.health_consultation_repository import HealthConsultationRepository
from yuxi.repositories.health_meal_feedback_repository import HealthMealFeedbackRepository
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_health import MealFeedback, MealFeedbackRevision
from yuxi.utils.datetime_utils import format_utc_datetime, utc_now_naive


def feedback_result(feedback):
    """自述来源与单餐范围显式返回，不改变原营养结果。"""
    return {
        "feedback_id": feedback.id,
        "diet_log_id": feedback.diet_log_id,
        "version": feedback.version,
        "status": feedback.status,
        "details": feedback.details if feedback.status == "active" else None,
        "source_type": "user_self_report",
        "scope": "single_meal",
        "professional_review": "not_reviewed",
        "formal_profile": False,
        "updated_at": format_utc_datetime(feedback.updated_at),
    }


async def meal_feedback(uid, record_id):
    """后台读取当前反馈及修订，撤回正文仅在历史中展示。"""
    async with pg_manager.get_async_session_context() as session:
        repo = HealthMealFeedbackRepository(session)
        await repo.require_record(uid, record_id)
        feedback = await repo.slot(uid, record_id)
        if feedback is None:
            return {"diet_log_id": record_id, "feedback": None, "revisions": []}
        sources = await repo.dialog_sources(feedback.id)
        return {
            "diet_log_id": record_id,
            "feedback": feedback_result(feedback),
            "revisions": [
                {
                    "version": row.version,
                    "status": row.status,
                    "details": row.details,
                    "created_at": format_utc_datetime(row.created_at),
                    "source_message_id": sources[row.id].source_message_id if row.id in sources else None,
                    "source_run_id": sources[row.id].run_id if row.id in sources else None,
                }
                for row in await repo.revisions(feedback.id)
            ],
        }


async def change_meal_feedback(uid, record_id, data, *, revoke=False):
    """成员锁内原子保存当前版本、不可变修订和幂等收据。"""
    async with pg_manager.get_async_session_context() as session:
        return await save_feedback_in_session(session, uid, record_id, data, revoke=revoke)


async def save_feedback_in_session(session, uid, record_id, data, *, revoke=False):
    """同一业务事务保存反馈，供管理入口与受控对话来源复用。"""
    repo = HealthMealFeedbackRepository(session)
    await HealthConsultationRepository(session).lock_request(uid, str(data.client_request_id))
    record = await repo.require_record(uid, record_id, lock=True)
    feedback = await repo.slot(uid, record_id)
    request_id = str(data.client_request_id)
    details = None if revoke else data.model_dump(mode="json", exclude={"version", "client_request_id"})
    fingerprint = hashlib.sha256(
        json.dumps(
            {"record": record_id, "version": data.version, "revoke": revoke, "details": details},
            sort_keys=True,
            ensure_ascii=False,
        ).encode()
    ).hexdigest()
    receipt = await repo.receipt(uid, request_id)
    if receipt:
        if receipt.fingerprint != fingerprint:
            raise HealthVisionError("request_conflict", "同一请求不能改变反馈操作", 409)
        return feedback_result(feedback)
    version = feedback.version if feedback else 0
    if version != data.version or (revoke and (feedback is None or feedback.status != "active")):
        raise HealthVisionError("version_conflict", "反馈版本已变化，请刷新后操作", 409)
    if feedback is None:
        feedback = MealFeedback(
            id=str(uuid4()), actor_uid=uid, member_id=record.member_id, diet_log_id=record_id, version=0
        )
        session.add(feedback)
    feedback.version += 1
    feedback.status = "revoked" if revoke else "active"
    # 显式新请求可重新填写；重放旧请求只返回当前状态。
    if not revoke:
        feedback.details = details
    feedback.updated_at = utc_now_naive()
    await session.flush()
    session.add(
        MealFeedbackRevision(
            id=str(uuid4()),
            feedback_id=feedback.id,
            actor_uid=uid,
            request_id=request_id,
            fingerprint=fingerprint,
            version=feedback.version,
            details=feedback.details,
            status=feedback.status,
        )
    )
    await session.flush()
    return feedback_result(feedback)


async def meal_feedback_for_run(context):
    """固定账号成员及用途，读取有效来源并先提交版本依赖。"""
    from yuxi.services.health_consultation_service import require_consultation

    async with pg_manager.get_async_session_context() as session:
        run = await HealthConsultationRepository(session).require_attempt(context, lock=True)
        if not run.input_payload.get("health_processing"):
            raise HealthVisionError("policy_changed", "咨询缺少处理审批快照", 409)
        binding, _ = await require_consultation(
            session,
            context.uid,
            context.thread_id,
            context.model,
            expected=run.input_payload.get("health_processing"),
            lock=True,
        )
        repo = HealthMealFeedbackRepository(session)
        rows = await repo.active(context.uid, binding.member_id)
        results, references = [], []
        for feedback in rows[:100]:
            if not await repo.valid_source(context.uid, feedback):
                continue
            record = await repo.require_record(context.uid, feedback.diet_log_id)
            results.append(
                {
                    **feedback_result(feedback),
                    "meal": {
                        "meal_type": record.snapshot["meal"]["meal_type"],
                        "eaten_at": record.snapshot["meal"]["eaten_at"],
                    },
                }
            )
            references.append((feedback.id, feedback.version))
        await repo.record_uses(run, references)
        return {"feedback": results, "truncated": len(rows) > 100, "nutrition_recalculated": False}


async def filter_meal_feedback_history(context, messages, *, session=None, persist_uses=True):
    """排除失效反馈及派生轮次；模型依赖在调用前再次持久化。"""
    from yuxi.services.health_consultation_service import require_consultation

    chunks, chunk = [], []
    for message in messages:
        if isinstance(message, HumanMessage) and chunk:
            chunks.append(chunk)
            chunk = []
        chunk.append(message)
    if chunk:
        chunks.append(chunk)
    async with nullcontext(session) if session is not None else pg_manager.get_async_session_context() as session:
        run = await HealthConsultationRepository(session).require_attempt(context, lock=True)
        if not run.input_payload.get("health_processing"):
            raise HealthVisionError("policy_changed", "咨询缺少处理审批快照", 409)
        binding, _ = await require_consultation(
            session,
            context.uid,
            context.thread_id,
            context.model,
            expected=run.input_payload.get("health_processing"),
            lock=True,
        )
        repo = HealthMealFeedbackRepository(session)
        uses = await repo.uses(context.uid, thread_id=context.thread_id, member_id=binding.member_id)
        invalid = await repo.invalid_requests(context.uid, binding.member_id)
        if context.request_id in invalid:
            raise HealthVisionError("meal_feedback_changed", "本轮餐后反馈已变化，请重新提交问题", 409)
        result, references = [], []
        for chunk in chunks:
            requests = {
                message.additional_kwargs.get("health_request_id")
                for message in chunk
                if isinstance(message, HumanMessage)
            }
            if requests & invalid:
                continue
            result.extend(chunk)
            references.extend((feedback.id, version) for request, version, feedback in uses if request in requests)
        if persist_uses:
            await repo.record_uses(run, references)
        return result


async def filter_health_history(context, messages, *, persist_uses=True):
    """同一成员锁内联合筛选，只有最终可见轮次传播两类版本依赖。"""
    from yuxi.services.health_memory_service import filter_memory_history

    async with pg_manager.get_async_session_context() as session:
        # 第一轮只决定可见输入；成员锁从反馈过滤取得并保持至统一提交。
        messages = await filter_meal_feedback_history(context, messages, session=session, persist_uses=False)
        messages = await filter_memory_history(context, messages, session=session, persist_uses=False)
        if persist_uses:
            messages = await filter_meal_feedback_history(context, messages, session=session)
            messages = await filter_memory_history(context, messages, session=session)
        return messages

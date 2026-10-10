"""审核证据发布、撤回与固定成员运行内检索。"""

import hashlib
import json
import re
from uuid import uuid4

from langchain_core.messages import HumanMessage, ToolMessage
from sqlalchemy import select

from yuxi.repositories.agent_run_repository import AgentRunRepository
from yuxi.repositories.health_consultation_repository import CONSULTATION_SLUG, HealthConsultationRepository
from yuxi.repositories.health_evidence_repository import HealthEvidenceRepository
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_business import User
from yuxi.storage.postgres.models_health import NutritionEvidence, NutritionEvidenceCitation
from yuxi.utils.datetime_utils import utc_now_naive


async def read_consultation_citations(uid, run_id):
    """重验当前成员授权与完成答复，只公开该答复实际采用的本Run引用。"""
    async with pg_manager.get_async_session_context() as session:
        run = await AgentRunRepository(session).get_run_for_user(run_id, uid)
        if run is None or run.agent_slug != CONSULTATION_SLUG:
            raise HealthVisionError("not_found", "专属咨询运行不存在或无权访问", 404)
        if run.status != "completed":
            raise HealthVisionError("answer_not_completed", "仅已完成的咨询答复可读取引用", 409)
        binding = await HealthConsultationRepository(session).authorize(
            uid, run.conversation_thread_id, lock=True, preview_history=True
        )
        if binding.conversation_id != run.conversation_id or binding.actor_uid != uid:
            raise HealthVisionError("not_found", "专属咨询运行与成员绑定不符", 404)
        repo = HealthEvidenceRepository(session)
        answer = await repo.final_answer(run)
        ids = answer_citation_ids(answer.content)
        citations = await repo.validate_citations(ids, binding, uid, run_id=run.id)
        return {
            "result_type": "nutrition_citations",
            "status": "cited" if ids else "not_cited",
            "agent_run_id": run.id,
            "request_id": run.request_id,
            "thread_id": run.conversation_thread_id,
            "member_id": binding.member_id,
            "final_message_id": answer.id,
            "citations": [citations[citation_id] for citation_id in ids],
        }


async def validate_evidence_publication(session, run, content):
    """最终发布事务锁住实际采用的当前来源，图校验不能替代提交边界。"""
    from yuxi.services.health_consultation_service import require_consultation

    snapshot = (run.input_payload or {}).get("health_processing")
    if not snapshot:
        raise HealthVisionError("policy_changed", "咨询缺少处理审批快照", 409)
    binding, _ = await require_consultation(session, run.uid, run.conversation_thread_id, expected=snapshot, lock=True)
    if binding.conversation_id != run.conversation_id or binding.actor_uid != run.uid:
        raise HealthVisionError("citation_invalid", "引用与当前咨询线程不符", 409)
    ids = answer_citation_ids(content)
    if not ids:
        retrieved = await session.scalar(
            select(NutritionEvidenceCitation.id).where(NutritionEvidenceCitation.run_id == run.id).limit(1)
        )
        if retrieved is not None:
            raise HealthVisionError("citation_invalid", "答复缺少有效的本轮证据引用", 409)
        return
    await HealthEvidenceRepository(session).validate_citations(ids, binding, run.uid, run_id=run.id, lock=True)


async def read_public_consultation_answer(session, run, uid, *, binding=None):
    """正文读取只校验权威最终回答实际采用的同Run来源，不扩大模型用途。"""
    if run.agent_slug != CONSULTATION_SLUG or run.uid != uid or run.status != "completed":
        raise HealthVisionError("answer_unavailable", "咨询缺少可公开的最终答复", 409)
    if binding is None:
        binding = await HealthConsultationRepository(session).authorize(
            uid, run.conversation_thread_id, lock=True, preview_history=True
        )
    if binding.conversation_id != run.conversation_id or binding.actor_uid != uid:
        raise HealthVisionError("not_found", "咨询运行与当前成员绑定不符", 404)
    repo = HealthEvidenceRepository(session)
    answer = await repo.final_answer(run)
    ids = answer_citation_ids(answer.content)
    await repo.validate_citations(ids, binding, uid, run_id=run.id, lock=True)
    return answer


async def require_evidence_admin(session, uid):
    """替代调用路径也重查管理权限；管理员只登记外部审核凭据。"""
    user = await session.scalar(select(User).where(User.uid == uid, User.is_deleted == 0))
    if user is None or user.role not in {"admin", "superadmin"}:
        raise HealthVisionError("forbidden", "需要审核证据管理权限", 403)


async def publish_evidence(uid, data):
    """发布不可变版本，不允许覆盖已被引用的片段。"""
    async with pg_manager.get_async_session_context() as session:
        await require_evidence_admin(session, uid)
        source = NutritionEvidence(
            id=str(uuid4()),
            **data.model_dump(),
            content_hash=hashlib.sha256(data.content.encode()).hexdigest(),
            published_by=uid,
        )
        session.add(source)
        await session.flush()
        return {"evidence_id": source.id, "source_version": source.source_version, "scope": "general_education"}


async def revoke_evidence(uid, source_id):
    """撤回与当前检索共享行锁；撤回后的历史也不能继续外呼。"""
    async with pg_manager.get_async_session_context() as session:
        await require_evidence_admin(session, uid)
        source = await session.scalar(
            select(NutritionEvidence).where(NutritionEvidence.id == source_id).with_for_update()
        )
        if source is None:
            raise HealthVisionError("not_found", "审核证据不存在", 404)
        source.revoked_at = source.revoked_at or utc_now_naive()
        return {"evidence_id": source.id, "revoked": True}


async def search_nutrition_evidence(context, query):
    """用途、成员和执行所有权通过后创建同一运行的引用回执。"""
    from yuxi.services.health_consultation_service import require_consultation

    async with pg_manager.get_async_session_context() as session:
        run = await HealthConsultationRepository(session).require_attempt(context)
        snapshot = (run.input_payload or {}).get("health_processing")
        if not snapshot:
            raise HealthVisionError("policy_changed", "咨询运行缺少处理审批快照", 409)
        binding, _ = await require_consultation(
            session, context.uid, context.thread_id, context.model, expected=snapshot, lock=True
        )
        sources = await HealthEvidenceRepository(session).search(query)
        # 后台纯索引结束后再次核对当前 attempt；取消或接管不能继续创建引用。
        await HealthConsultationRepository(session).require_attempt(context)
        results = []
        for source in sources:
            if hashlib.sha256(source.content.encode()).hexdigest() != source.content_hash:
                raise HealthVisionError("source_invalidated", "审核证据内容已变化", 410)
            citation = NutritionEvidenceCitation(
                id=str(uuid4()),
                evidence_id=source.id,
                run_id=run.id,
                conversation_id=binding.conversation_id,
                member_id=binding.member_id,
                actor_uid=context.uid,
                content_hash=source.content_hash,
            )
            session.add(citation)
            results.append(HealthEvidenceRepository.project_citation(citation, source))
        return {
            "status": "ok" if results else "insufficient_evidence",
            "query": query,
            "citations": results,
            "personal_meal_plan_available": False,
        }


async def validate_nutrition_answer(context, content, messages):
    """验证最终答复引用；检索有证据时不能省略引用，拒绝历史回执冒充本轮来源。"""
    from yuxi.services.health_consultation_service import require_consultation

    start = next((i for i in range(len(messages) - 1, -1, -1) if isinstance(messages[i], HumanMessage)), 0)
    retrieved = False
    for message in messages[start:]:
        if (
            isinstance(message, ToolMessage)
            and message.name == "query_reviewed_nutrition_knowledge"
            and message.status != "error"
        ):
            try:
                retrieved = retrieved or bool(json.loads(message.content)["citations"])
            except (ValueError, TypeError, KeyError):
                raise HealthVisionError("citation_invalid", "本次检索结果无法校验", 409) from None
    ids = answer_citation_ids(content)
    if retrieved and not ids:
        raise HealthVisionError("citation_invalid", "答复缺少有效的本轮证据引用", 409)
    if not ids:
        return
    async with pg_manager.get_async_session_context() as session:
        run = await HealthConsultationRepository(session).require_attempt(context)
        snapshot = (run.input_payload or {}).get("health_processing")
        if not snapshot:
            raise HealthVisionError("policy_changed", "咨询运行缺少处理审批快照", 409)
        binding, _ = await require_consultation(
            session, context.uid, context.thread_id, context.model, expected=snapshot, lock=True
        )
        await HealthEvidenceRepository(session).validate_citations(ids, binding, context.uid, run_id=run.id)


def answer_citation_ids(content):
    """按正文顺序取得规范UUID，格式异常拒绝，重复引用只保留一次。"""
    if not isinstance(content, str):
        raise HealthVisionError("answer_invalid", "营养咨询答复必须为文本", 409)
    ids = re.findall(r"\[证据:([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\]", content)
    if content.count("[证据:") != len(ids):
        raise HealthVisionError("citation_invalid", "答复包含无法校验的证据引用", 409)
    return list(dict.fromkeys(ids))

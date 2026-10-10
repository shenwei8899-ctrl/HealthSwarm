"""健康专属审核证据检索与引用归属，排除通用用户知识库。"""

import hashlib
import json

from sqlalchemy import func, select

from yuxi.repositories.agent_run_output_repository import AgentRunOutputRepository
from yuxi.services.health_evidence_index import (
    MAX_EVIDENCE_INDEX_DOCUMENT_CHARACTERS,
    MAX_EVIDENCE_INDEX_SOURCES,
    EvidenceIndexDocument,
    search_evidence_index,
)
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.storage.postgres.models_business import AUDIT_MESSAGE_TYPES, Conversation
from yuxi.storage.postgres.models_health import NutritionEvidence, NutritionEvidenceCitation
from yuxi.utils.datetime_utils import format_utc_datetime, utc_now_naive


class HealthEvidenceRepository:
    """持久化授权通过后的公开科普证据与私有运行回执。"""

    def __init__(self, session):
        """共享调用用例的事务。"""
        self.session = session

    async def final_answer(self, run):
        """新增引用入口只认当前权威指针，拒绝历史猜测与审计消息。"""
        if run.output_message_id is None or run.conversation_id is None:
            raise HealthVisionError("answer_unavailable", "咨询运行缺少权威最终答复", 409)
        conversation = await self.session.get(Conversation, run.conversation_id)
        if (
            conversation is None
            or conversation.thread_id != run.conversation_thread_id
            or conversation.uid != run.uid
            or conversation.agent_id != "health-consultation"
        ):
            raise HealthVisionError("not_found", "咨询运行与专属线程不符", 404)
        answer = await AgentRunOutputRepository(self.session).get_output_message(
            run_id=run.id,
            conversation_id=run.conversation_id,
            output_message_id=run.output_message_id,
            allow_legacy_fallback=False,
        )
        if (
            answer is None
            or answer.message_type in AUDIT_MESSAGE_TYPES
            or answer.delivery_status != "complete"
            or answer.request_id != run.request_id
        ):
            raise HealthVisionError("answer_unavailable", "咨询运行缺少有效最终答复", 409)
        return answer

    async def search(self, query):
        """当前审核片段重建有界词法索引，命中后锁读 fresh PG 事实。"""
        rows = await self.session.execute(
            select(
                NutritionEvidence.id,
                NutritionEvidence.source_version,
                NutritionEvidence.content_hash,
                NutritionEvidence.title,
                func.left(NutritionEvidence.content, MAX_EVIDENCE_INDEX_DOCUMENT_CHARACTERS + 1),
            )
            .where(NutritionEvidence.revoked_at.is_(None), NutritionEvidence.valid_until > utc_now_naive())
            .order_by(NutritionEvidence.id)
            .limit(MAX_EVIDENCE_INDEX_SOURCES + 1)
        )
        documents = [EvidenceIndexDocument(*row) for row in rows]
        hits = await search_evidence_index(documents, query)
        if not hits:
            return []
        expected = {document.evidence_id: document for document in documents}
        if len({hit.evidence_id for hit in hits}) != len(hits) or any(
            hit.evidence_id not in expected
            or (expected[hit.evidence_id].source_version, expected[hit.evidence_id].content_hash)
            != (hit.source_version, hit.content_hash)
            for hit in hits
        ):
            raise HealthVisionError("source_invalidated", "词法命中缺少审核来源证明", 410)
        sources = list(
            await self.session.scalars(
                select(NutritionEvidence)
                .where(NutritionEvidence.id.in_([hit.evidence_id for hit in hits]))
                .order_by(NutritionEvidence.id)
                .with_for_update(read=True)
                .execution_options(populate_existing=True)
            )
        )
        by_id = {source.id: source for source in sources}
        now = utc_now_naive()
        for hit in hits:
            source = by_id.get(hit.evidence_id)
            if (
                source is None
                or source.title != expected[hit.evidence_id].title
                or source.source_version != hit.source_version
                or source.content_hash != hit.content_hash
                or hashlib.sha256(source.content.encode()).hexdigest() != source.content_hash
                or source.revoked_at is not None
                or source.valid_until <= now
            ):
                raise HealthVisionError("source_invalidated", "审核证据已撤回、过期或变化", 410)
        return [by_id[hit.evidence_id] for hit in hits]

    async def validate_citations(self, ids, binding, uid, *, run_id=None, lock=False):
        """历史允许同线程回执，最终输出必须来自本次运行。"""
        if not ids:
            return {}
        statement = (
            select(NutritionEvidenceCitation, NutritionEvidence)
            .join(NutritionEvidence, NutritionEvidence.id == NutritionEvidenceCitation.evidence_id)
            .where(
                NutritionEvidenceCitation.id.in_(ids),
                NutritionEvidenceCitation.conversation_id == binding.conversation_id,
                NutritionEvidenceCitation.member_id == binding.member_id,
                NutritionEvidenceCitation.actor_uid == uid,
            )
        )
        if lock:
            statement = (
                statement.order_by(NutritionEvidence.id, NutritionEvidenceCitation.id)
                .with_for_update(read=True)
                .execution_options(populate_existing=True)
            )
        rows = list(await self.session.execute(statement))
        if len(rows) != len(set(ids)):
            raise HealthVisionError("citation_invalid", "营养知识引用不属于当前咨询", 409)
        for citation, source in rows:
            if run_id is not None and citation.run_id != run_id:
                raise HealthVisionError("citation_invalid", "引用必须来自本次运行的检索", 409)
            if (
                source.revoked_at is not None
                or source.valid_until <= utc_now_naive()
                or citation.content_hash != source.content_hash
                or hashlib.sha256(source.content.encode()).hexdigest() != source.content_hash
            ):
                raise HealthVisionError("source_invalidated", "营养证据已撤回、过期或变更，请重新咨询", 410)
        return {citation.id: self.project_citation(citation, source) for citation, source in rows}

    async def validate_tool_payload(self, payload, binding, uid):
        """模型历史逐条核对真实引用正文，标识有效不授权伪造证据。"""
        try:
            refs = payload["citations"]
            ids = [reference["citation_id"] for reference in refs]
            projections = await self.validate_citations(ids, binding, uid)
            expected = {
                "status": "ok" if refs else "insufficient_evidence",
                "query": payload["query"],
                "citations": [projections[citation_id] for citation_id in ids],
                "personal_meal_plan_available": False,
            }
            if not isinstance(payload["query"], str) or json.dumps(payload, sort_keys=True) != json.dumps(
                expected, sort_keys=True
            ):
                raise ValueError("证据投影不符")
        except (KeyError, TypeError, ValueError):
            raise HealthVisionError("source_invalidated", "历史营养证据正文无法核对", 410) from None

    @staticmethod
    def project_citation(citation, source):
        """检索生产与历史消费共用原始公开片段，不复制患者资料。"""
        return {
            "citation_id": citation.id,
            "evidence_id": source.id,
            "title": source.title,
            "content": source.content,
            "source_ref": source.source_ref,
            "source_version": source.source_version,
            "reviewed_at": format_utc_datetime(source.reviewed_at),
            "scope": "general_education",
        }

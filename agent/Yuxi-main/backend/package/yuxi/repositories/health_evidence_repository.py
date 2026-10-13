"""健康专属审核证据检索与引用归属，排除通用用户知识库。"""

import hashlib
import json

from pydantic import ValidationError
from sqlalchemy import and_, func, or_, select

from yuxi.repositories.agent_run_output_repository import AgentRunOutputRepository
from yuxi.repositories.health_consultation_repository import EDUCATION_HEALTH_AGENTS
from yuxi.services.health_evidence_index import (
    MAX_EVIDENCE_INDEX_DOCUMENT_CHARACTERS,
    MAX_EVIDENCE_INDEX_SOURCES,
    EvidenceIndexDocument,
    search_evidence_index,
)
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.services.health_evidence_types import ReviewedKnowledgeScope
from yuxi.storage.postgres.models_business import AUDIT_MESSAGE_TYPES, AgentRun, Conversation
from yuxi.storage.postgres.models_health import NutritionEvidence, NutritionEvidenceCitation
from yuxi.utils.datetime_utils import format_utc_datetime, utc_now_naive

EVIDENCE_AGENT_DOMAINS = {
    "health-consultation": "nutrition",
    "health-blood-glucose": "blood_glucose",
    "health-blood-lipids": "blood_lipids",
    "health-blood-pressure": "blood_pressure",
}


class HealthEvidenceRepository:
    """持久化授权通过后的公开科普证据与私有运行回执。"""

    def __init__(self, session):
        """共享调用用例的事务。"""
        self.session = session

    async def has_current_sources(self):
        """映射后的审核片段目录存在性，不替代检索命中和引用版本校验。"""
        return (
            await self.session.scalar(
                select(NutritionEvidence.id)
                .where(NutritionEvidence.revoked_at.is_(None), NutritionEvidence.valid_until > utc_now_naive())
                .limit(1)
            )
            is not None
        )

    async def final_answer(self, run):
        """新增引用入口只认当前权威指针，拒绝历史猜测与审计消息。"""
        if run.output_message_id is None or run.conversation_id is None:
            raise HealthVisionError("answer_unavailable", "咨询运行缺少权威最终答复", 409)
        conversation = await self.session.get(Conversation, run.conversation_id)
        if (
            conversation is None
            or conversation.thread_id != run.conversation_thread_id
            or conversation.uid != run.uid
            or conversation.agent_id not in EDUCATION_HEALTH_AGENTS
            or conversation.agent_id != run.agent_slug
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

    async def search(self, query, *, agent_slug):
        """当前审核片段重建有界词法索引，命中后锁读 fresh PG 事实。"""
        rows = await self.session.execute(
            select(
                NutritionEvidence.id,
                NutritionEvidence.source_version,
                NutritionEvidence.content_hash,
                NutritionEvidence.title,
                func.left(NutritionEvidence.content, MAX_EVIDENCE_INDEX_DOCUMENT_CHARACTERS + 1),
                NutritionEvidence.scope_hash,
            )
            .where(
                NutritionEvidence.revoked_at.is_(None),
                NutritionEvidence.valid_until > utc_now_naive(),
                self.scope_filter(agent_slug),
            )
            .order_by(NutritionEvidence.id)
            .limit(MAX_EVIDENCE_INDEX_SOURCES + 1)
        )
        rows = list(rows)
        documents = [EvidenceIndexDocument(*row[:5]) for row in rows]
        scope_hashes = {row[0]: row[5] for row in rows}
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
                or source.scope_hash != scope_hashes[hit.evidence_id]
            ):
                raise HealthVisionError("source_invalidated", "审核证据已撤回、过期或变化", 410)
            self.validate_source_scope(source, agent_slug)
        return [by_id[hit.evidence_id] for hit in hits]

    async def validate_citations(self, ids, binding, uid, *, agent_slug, run_id=None, lock=False):
        """历史允许同线程回执，最终输出必须来自本次运行。"""
        if not ids:
            return {}
        statement = (
            select(NutritionEvidenceCitation, NutritionEvidence)
            .join(NutritionEvidence, NutritionEvidence.id == NutritionEvidenceCitation.evidence_id)
            .join(AgentRun, AgentRun.id == NutritionEvidenceCitation.run_id)
            .join(Conversation, Conversation.id == NutritionEvidenceCitation.conversation_id)
            .where(
                NutritionEvidenceCitation.id.in_(ids),
                NutritionEvidenceCitation.conversation_id == binding.conversation_id,
                NutritionEvidenceCitation.member_id == binding.member_id,
                NutritionEvidenceCitation.actor_uid == uid,
                AgentRun.uid == uid,
                AgentRun.conversation_id == binding.conversation_id,
                AgentRun.agent_slug == agent_slug,
                Conversation.uid == uid,
                Conversation.agent_id == agent_slug,
            )
            .execution_options(populate_existing=True)
        )
        if lock:
            statement = statement.order_by(NutritionEvidence.id, NutritionEvidenceCitation.id).with_for_update(
                read=True, of=(NutritionEvidence, NutritionEvidenceCitation)
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
            self.validate_source_scope(source, agent_slug)
            if citation.scope_hash != source.scope_hash:
                raise HealthVisionError("source_invalidated", "营养证据审核范围已变更，请重新咨询", 410)
        return {citation.id: self.project_citation(citation, source) for citation, source in rows}

    async def validate_tool_payload(self, payload, binding, uid, *, agent_slug):
        """模型历史逐条核对真实引用正文，标识有效不授权伪造证据。"""
        try:
            refs = payload["citations"]
            ids = [reference["citation_id"] for reference in refs]
            projections = await self.validate_citations(ids, binding, uid, agent_slug=agent_slug)
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
        projection = {
            "citation_id": citation.id,
            "evidence_id": source.id,
            "title": source.title,
            "content": source.content,
            "source_ref": source.source_ref,
            "source_version": source.source_version,
            "reviewed_at": format_utc_datetime(source.reviewed_at),
            "scope": "general_education",
        }
        if source.reviewed_scope is not None:
            projection.update(reviewed_scope=source.reviewed_scope, scope_hash=citation.scope_hash)
        return projection

    @staticmethod
    def scope_digest(reviewed_scope):
        """摘要绑定全部专业登记字段，空值保留旧来源语义。"""
        if reviewed_scope is None:
            return None
        canonical = json.dumps(reviewed_scope, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()

    @staticmethod
    def scope_filter(agent_slug):
        """索引前只送入本角色可用通用片段，旧资料仅留原普通咨询。"""
        domain = EVIDENCE_AGENT_DOMAINS.get(agent_slug)
        if domain is None:
            raise HealthVisionError("source_invalidated", "当前角色不支持审核科普", 410)
        registered = and_(
            NutritionEvidence.reviewed_scope["domains"].contains([domain]),
            NutritionEvidence.reviewed_scope["population_category"].astext == "general_education",
            NutritionEvidence.reviewed_scope["exclusion_conditions"] == [],
        )
        if agent_slug == "health-consultation":
            return or_(
                and_(NutritionEvidence.reviewed_scope.is_(None), NutritionEvidence.scope_hash.is_(None)), registered
            )
        return registered

    @classmethod
    def validate_source_scope(cls, source, agent_slug):
        """fresh事实决定领域与可用性，登记损坏和未有专业匹配规则时关闭正文。"""
        if source.reviewed_scope is None:
            if source.scope_hash is None and agent_slug == "health-consultation":
                return
            raise HealthVisionError("source_invalidated", "该科普未登记当前角色的审核范围", 410)
        try:
            reviewed_scope = ReviewedKnowledgeScope.model_validate(source.reviewed_scope).model_dump()
        except ValidationError:
            raise HealthVisionError("source_invalidated", "科普审核范围无法核对", 410) from None
        if (
            reviewed_scope != source.reviewed_scope
            or cls.scope_digest(reviewed_scope) != source.scope_hash
            or EVIDENCE_AGENT_DOMAINS.get(agent_slug) not in reviewed_scope["domains"]
            or reviewed_scope["population_category"] != "general_education"
            or reviewed_scope["exclusion_conditions"]
        ):
            raise HealthVisionError("source_invalidated", "科普审核范围不适用于当前教育流程", 410)

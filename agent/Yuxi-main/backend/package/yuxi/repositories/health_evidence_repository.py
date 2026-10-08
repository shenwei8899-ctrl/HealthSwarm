"""健康专属审核证据检索与引用归属，排除通用用户知识库。"""

import hashlib
import json

from sqlalchemy import or_, select

from yuxi.services.health_vision_types import HealthVisionError
from yuxi.storage.postgres.models_health import NutritionEvidence, NutritionEvidenceCitation
from yuxi.utils.datetime_utils import format_utc_datetime, utc_now_naive


class HealthEvidenceRepository:
    """持久化授权通过后的公开科普证据与私有运行回执。"""

    def __init__(self, session):
        """共享调用用例的事务。"""
        self.session = session

    async def search(self, query):
        """精确关键词匹配至多五个有效片段；查询通配符按字面处理。"""
        return list(
            await self.session.scalars(
                select(NutritionEvidence)
                .where(
                    NutritionEvidence.revoked_at.is_(None),
                    NutritionEvidence.valid_until > utc_now_naive(),
                    or_(
                        NutritionEvidence.content.contains(query, autoescape=True),
                        NutritionEvidence.title.contains(query, autoescape=True),
                    ),
                )
                .order_by(NutritionEvidence.created_at.desc(), NutritionEvidence.id)
                .limit(5)
                .with_for_update(read=True)
            )
        )

    async def validate_citations(self, ids, binding, uid, *, run_id=None):
        """历史允许同线程回执，最终输出必须来自本次运行。"""
        if not ids:
            return {}
        rows = list(
            await self.session.execute(
                select(NutritionEvidenceCitation, NutritionEvidence)
                .join(NutritionEvidence, NutritionEvidence.id == NutritionEvidenceCitation.evidence_id)
                .where(
                    NutritionEvidenceCitation.id.in_(ids),
                    NutritionEvidenceCitation.conversation_id == binding.conversation_id,
                    NutritionEvidenceCitation.member_id == binding.member_id,
                    NutritionEvidenceCitation.actor_uid == uid,
                )
            )
        )
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

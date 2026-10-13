"""审核证据发布契约；只支持通用科普，不授权个人临床方案。"""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, model_serializer, model_validator

from yuxi.services.health_vision_types import HealthDTO
from yuxi.utils.datetime_utils import utc_now_naive


class ReviewedKnowledgeScope(HealthDTO):
    """专业发布者登记的使用范围，不推导个人临床适用性。"""

    domains: list[Literal["nutrition", "blood_glucose", "blood_lipids", "blood_pressure"]] = Field(
        min_length=1, max_length=4
    )
    population_category: Literal["general_education", "professional_selection_required"]
    population_description: str = Field(min_length=1, max_length=1000)
    exclusion_conditions: list[Annotated[str, Field(min_length=1, max_length=500)]] = Field(max_length=20)
    license_ref: str = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def canonical_domains(self):
        """显式领域必须唯一，统一顺序以稳定版本摘要。"""
        if len(set(self.domains)) != len(self.domains):
            raise ValueError("审核领域不可重复")
        if not self.population_description.strip() or not self.license_ref.strip():
            raise ValueError("人群说明与许可依据不能为空白")
        if any(not item.strip() for item in self.exclusion_conditions):
            raise ValueError("排除条件不能为空白")
        self.domains = sorted(self.domains)
        return self


class NutritionCitation(HealthDTO):
    """只投影最终答复实际采用的审核科普片段及来源。"""

    citation_id: UUID
    evidence_id: UUID
    title: str
    content: str
    source_ref: str
    source_version: str
    reviewed_at: datetime
    scope: Literal["general_education"]
    reviewed_scope: ReviewedKnowledgeScope | None = None
    scope_hash: str | None = None

    @model_serializer(mode="wrap")
    def serialize_registered_scope(self, handler):
        """旧引用保留原协议形状，不删除其它结果的显式空字段。"""
        data = handler(self)
        if self.reviewed_scope is None:
            data.pop("reviewed_scope", None)
            data.pop("scope_hash", None)
        return data


class NutritionCitationsResult(HealthDTO):
    """当前授权下的同Run引用结果，不携带咨询正文或工具审计。"""

    result_type: Literal["nutrition_citations"] = "nutrition_citations"
    status: Literal["cited", "not_cited"]
    agent_run_id: str
    request_id: str | None
    thread_id: UUID
    member_id: UUID
    final_message_id: int
    citations: list[NutritionCitation]


class NutritionEvidenceInput(HealthDTO):
    """管理员登记专业审核结果，审核人与凭据不由模型生成。"""

    source_ref: str = Field(min_length=1, max_length=500)
    source_version: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=4000)
    review_ref: str = Field(min_length=1, max_length=500)
    reviewed_by: str = Field(min_length=1, max_length=100)
    reviewed_at: datetime
    valid_until: datetime
    reviewed_scope: ReviewedKnowledgeScope | None = None

    @model_validator(mode="after")
    def review_dates(self):
        """边界统一 UTC，拒绝未来审核与已过期发布。"""
        from datetime import UTC

        for key in ("reviewed_at", "valid_until"):
            value = getattr(self, key)
            if value.tzinfo is None:
                raise ValueError("审核日期必须带时区")
            setattr(self, key, value.astimezone(UTC).replace(tzinfo=None))
        now = utc_now_naive()
        if self.reviewed_at > now or self.valid_until <= now or self.valid_until <= self.reviewed_at:
            raise ValueError("审核或有效日期无效")
        return self

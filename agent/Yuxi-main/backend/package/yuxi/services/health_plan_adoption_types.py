"""次日提议、正式采用及取消的用户动作边界。"""

from datetime import date
from uuid import UUID

from pydantic import Field, model_validator

from yuxi.services.health_quality_types import Version
from yuxi.services.health_vision_types import HealthDTO


class NextDayProposalInput(HealthDTO):
    """选用实际预览，明确来源日，不由模型伪造正式计划。"""

    client_request_id: UUID
    preview_id: UUID
    source_date: date


class PlanAdoptionInput(HealthDTO):
    """采用选定当前专业批准，并明确被替代计划。"""

    client_request_id: UUID
    version: Version
    review_id: UUID
    profile_versions: dict[UUID, Version] = Field(min_length=1, max_length=20)
    replaces_adoption_id: UUID | None = None
    replaces_version: Version | None = None
    replaces_adoptions: dict[UUID, Version] = Field(default_factory=dict, max_length=20)

    @model_validator(mode="after")
    def replacement_pair(self):
        """替换必须同时提供对象和当前版本。"""
        if (self.replaces_adoption_id is None) != (self.replaces_version is None):
            raise ValueError("替代采用须同时提供对象与版本")
        if self.replaces_adoptions and self.replaces_adoption_id is not None:
            raise ValueError("单对象替代与多对象替代不能同时选择")
        return self


class PlanAdoptionWithdraw(HealthDTO):
    """取消采用保留历史快照，不能改写客观饮食记录。"""

    client_request_id: UUID
    version: Version
    reason: str = Field(min_length=1, max_length=500)

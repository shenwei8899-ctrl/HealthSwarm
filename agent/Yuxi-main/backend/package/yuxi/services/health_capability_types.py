"""成员入口提示的最小只读协议，不代表任务执行或专业批准。"""

from typing import Literal
from uuid import UUID

from pydantic import Field

from yuxi.services.health_task_types import HealthTaskType
from yuxi.services.health_vision_types import HealthDTO

ConfigurationReasonCode = Literal[
    "policy_not_approved",
    "model_unavailable",
    "meal_model_version_required",
    "ocr_credentials_missing",
    "ocr_not_configured",
    "processor_approval_changed",
]


class HealthTaskCapability(HealthDTO):
    """查询时的公共前置状态，提交、执行和发布仍须重新校验。"""

    task_type: HealthTaskType | Literal["glucose_plan", "multi_day_plan", "automatic_family_coordination"]
    purpose: Literal["consultation", "meal_plan", "diet_analysis", "quality_review", "purchase"] | None = None
    status: Literal["available", "needs_input", "unavailable"]
    reason_code: (
        Literal[
            "missing_scopes",
            "agent_unavailable",
            "skill_unavailable",
            "configuration_unavailable",
            "consent_required",
            "selection_required",
            "external_contract_required",
        ]
        | None
    ) = None
    configuration_reason_code: ConfigurationReasonCode | None = None
    missing_scopes: list[str] = Field(default_factory=list)
    required_inputs: list[str] = Field(
        default_factory=list, description="入口selection或后续interaction需明确提供的选择"
    )


class ProfileCapabilityDependency(HealthDTO):
    """仅表达授权内安全投影状态，不能表示完整健康档案已交付。"""

    status: Literal["ready", "not_ready", "not_authorized"]
    reason: str | None = None
    version: int | None = None


class RulesCapabilityDependency(HealthDTO):
    """规则须明确选择，不能猜测默认来源或适用范围。"""

    status: Literal["needs_input"] = "needs_input"
    reason: Literal["selection_required"] = "selection_required"
    version: None = None


class HealthCapabilityDependencies(HealthDTO):
    """依赖摘要不返回健康内容、证明或专业规则。"""

    profile_projection: ProfileCapabilityDependency
    published_recipes: bool = Field(description="仅表示已发布菜谱目录存在记录，不证明专业适用性")
    rules: RulesCapabilityDependency = Field(default_factory=RulesCapabilityDependency)


class MemberCapabilities(HealthDTO):
    """当前账号与成员的入口提示，不创建业务对象或模型运行。"""

    member_id: UUID
    tasks: list[HealthTaskCapability]
    dependencies: HealthCapabilityDependencies

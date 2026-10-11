"""成员业务诊断的只读快照；目录存在不能替代选定来源的校验。"""

from typing import Literal

from pydantic import Field

from yuxi.services.health_capability_types import ConfigurationReasonCode, MemberCapabilities
from yuxi.services.health_task_types import HealthTaskType
from yuxi.services.health_vision_types import HealthDTO


class HealthRuntimeDependency(HealthDTO):
    """底层故障仅返回固定状态，不输出异常、地址或凭据。"""

    status: Literal["available", "unavailable"]


class HealthEntryReadiness(HealthDTO):
    """客户端按入口展示阻断项，后续操作仍使用原业务门禁。"""

    entry_type: (
        HealthTaskType
        | Literal[
            "glucose_plan",
            "multi_day_plan",
            "automatic_family_coordination",
            "report_photo",
            "meal_photo",
            "manual_report",
            "manual_meal",
        ]
    )
    status: Literal["available", "needs_input", "unavailable"]
    reason_code: str | None = None
    configuration_reason_code: ConfigurationReasonCode | None = None
    missing_dependencies: list[str] = Field(default_factory=list)
    allowed_actions: list[Literal["retry", "manual_report", "manual_meal", "complete_selection"]] = Field(
        default_factory=list
    )


class HealthMemberReadiness(HealthDTO):
    """授权、运行事实与目录缺项共同组成入口快照，不产生健康写入。"""

    capabilities: MemberCapabilities
    runtime: dict[Literal["postgres", "redis", "worker", "object_storage"], HealthRuntimeDependency]
    catalogue: dict[Literal["nutrition", "rules", "knowledge_mapping"], bool]
    entries: list[HealthEntryReadiness]
    role_versions: dict[str, "HealthRoleVersion"]


class HealthRoleVersion(HealthDTO):
    """发布源码和PG登记版本的对应关系，不表示全部Worker部署已验收。"""

    published_version: str
    registered_version: str | None
    status: Literal["available", "unavailable"]

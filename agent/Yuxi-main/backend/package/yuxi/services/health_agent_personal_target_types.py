"""用户选择当前批准版本，模型不能选择目标来源或输入身体参数。"""

from typing import Annotated

from pydantic import Field

from yuxi.services.health_quality_types import PersonalTargetSelection
from yuxi.services.health_vision_types import ConsultationInput, HealthDTO


class TargetAwareAnalystInput(ConsultationInput):
    """普通分析入口可显式绑定当前目标，旧无目标入口仍有效。"""

    target_selection: PersonalTargetSelection | None = None


class PersonalTargetBinding(HealthDTO):
    """服务器保存批准来源的不可变选择和完整Owner投影摘要。"""

    selection: PersonalTargetSelection
    source_hash: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]

"""专属计划入口只接受任务身份，不接受客户端价格、菜单或营养值。"""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ExclusivePlanInput(BaseModel):
    """首次复用、明确重试和主动换一套是独立动作。"""

    model_config = ConfigDict(extra="forbid")
    client_request_id: UUID
    action: Literal["ensure", "retry", "regenerate"] = "ensure"
    group_id: UUID | None = None

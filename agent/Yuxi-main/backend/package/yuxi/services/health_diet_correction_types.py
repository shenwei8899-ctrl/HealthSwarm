"""已确认饮食更正的显式版本、幂等及不完整计算确认。"""

from uuid import UUID

from pydantic import Field

from yuxi.services.health_vision_types import HealthDTO, MealPayload


class DietLogCorrection(HealthDTO):
    """仅接收食物和份量；营养数值由服务端计算。"""

    expected_version: int = Field(ge=1)
    client_request_id: UUID
    reason: str = Field(min_length=1, max_length=500)
    meal: MealPayload
    accept_incomplete: bool = False

"""单成员已保存餐单选择和模型菜位参数的严格边界。"""

from typing import Literal
from uuid import UUID

from pydantic import Field

from yuxi.services.health_meal_plan_types import SafeRegenerationSelection
from yuxi.services.health_vision_types import HealthDTO

SAFE_PLANNER_TOOLS = (
    "get_safe_plan_context",
    "preview_safe_plan_swap",
    "preview_safe_plan_regeneration",
)


class SafePlannerSelection(SafeRegenerationSelection):
    """用户明确固定单成员餐单及当前批准专业来源。"""

    plan_id: UUID


class SafePlannerInput(SafePlannerSelection):
    """线程幂等键不能修改既有对象和来源版本。"""

    client_request_id: UUID


class SafeSwapParameters(HealthDTO):
    """模型只选原菜位，不提供身份、来源或营养值。"""

    meal_type: Literal["breakfast", "lunch", "dinner"]
    dish_index: int = Field(ge=0, le=9, strict=True)

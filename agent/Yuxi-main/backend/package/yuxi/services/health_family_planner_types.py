"""家庭配餐线程选择和模型可见参数的严格边界。"""

from typing import Literal
from uuid import UUID

from pydantic import Field

from yuxi.agents.toolkits.health import HealthReadInput
from yuxi.services.health_family_meal_plan_types import FamilySafeSelection, FamilyMealAllocation
from yuxi.services.health_vision_types import HealthDTO

FAMILY_PLANNER_TOOLS = (
    "get_family_plan_context",
    "preview_family_plan_swap",
    "preview_family_plan_regeneration",
    "preview_family_plan_participation",
)


class FamilyPlannerSelection(FamilySafeSelection):
    """用户固定方案、规则及包含拟加入者的全部档案版本。"""

    plan_id: UUID


class FamilyPlannerInput(FamilyPlannerSelection):
    """创建线程的幂等键不能修改已选对象和成员范围。"""

    client_request_id: UUID


class FamilySwapParameters(HealthDTO):
    """模型只选择原共同菜位，版本与身份由线程绑定。"""

    meal_type: Literal["breakfast", "lunch", "dinner"]
    dish_index: int = Field(ge=0, le=9, strict=True)


class FamilyParticipationParameters(HealthDTO):
    """模型只提供三餐分配，参与者仍受线程选定范围约束。"""

    allocations: list[FamilyMealAllocation] = Field(min_length=3, max_length=3)


class FamilySwapToolInput(FamilySwapParameters, HealthReadInput):
    """ToolNode注入运行身份，参数与只读菜位协议一致。"""


class FamilyParticipationToolInput(FamilyParticipationParameters, HealthReadInput):
    """ToolNode注入运行身份，参数与三餐分配协议一致。"""

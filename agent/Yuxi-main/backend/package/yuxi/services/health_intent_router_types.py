"""聊天输入的无副作用意图分类协议。"""

from datetime import date
from typing import Literal
from uuid import UUID
from pydantic import Field, model_validator

from yuxi.services.health_vision_types import HealthDTO


class HealthIntentInput(HealthDTO):
    """只接收待分类的用户文本，不接收健康资料或任务选择。"""

    text: str = Field(min_length=1, max_length=4000)
    client_request_id: UUID
    thread_id: UUID
    awaiting_meal_details: bool = False
    previous_date: date | None = None
    previous_meals: list[Literal["breakfast", "lunch", "dinner"]] = Field(default_factory=list, max_length=3)


class HealthIntentResult(HealthDTO):
    """分类只描述入口，不代表已授权或已创建任务。"""

    route: Literal["nutrition_consultation", "single_day_meal", "exclusive_plan", "needs_clarification"]
    action: Literal["generate", "view", "change", "continue", "handoff", "ask"]
    business_date: date | None = None
    meal_types: list[Literal["breakfast", "lunch", "dinner"]] = Field(default_factory=list)
    day_count: int | None = Field(default=None, ge=2, le=21)
    message: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def valid_route(self):
        """模型输出必须满足入口和动作的对应关系。"""
        if self.route == "single_day_meal":
            if (
                self.action not in {"generate", "view", "change", "continue"}
                or self.business_date is None
                or not self.meal_types
            ):
                raise ValueError("单日餐单缺少日期、餐次或有效动作")
            if len(self.meal_types) != len(set(self.meal_types)):
                raise ValueError("餐次不能重复")
        elif self.route == "exclusive_plan":
            if self.action != "handoff":
                raise ValueError("专属计划只能交接入口")
        elif self.route == "needs_clarification":
            if self.action != "ask":
                raise ValueError("追问不能创建任务")
        elif self.action != "generate":
            raise ValueError("咨询动作无效")
        return self

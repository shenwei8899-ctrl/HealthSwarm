"""初始配餐只接收当前来源和明确参加者。"""

from datetime import date
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from yuxi.services.health_vision_types import HealthDTO

INITIAL_PLANNER_TOOLS = ("get_initial_plan_context", "preview_initial_meal_plan")


class InitialMealParticipation(HealthDTO):
    """用户明确哪位成员参加本餐，不提供菜谱或营养。"""

    meal_type: Literal["breakfast", "lunch", "dinner"]
    participant_ids: list[UUID] = Field(min_length=1, max_length=20)

    @field_validator("participant_ids")
    @classmethod
    def distinct_members(cls, values):
        """拒绝重复参加者，排序稳定确认来源。"""
        if len(values) != len(set(values)):
            raise ValueError("餐次参加者重复")
        return sorted(values, key=str)


class InitialPlanSelection(HealthDTO):
    """日期、全员档案版本和批准规则均由明确业务选择提供。"""

    kind: Literal["single", "family"]
    plan_date: date
    rule_code: str = Field(min_length=1, max_length=80, pattern=r"^[a-zA-Z0-9_.:-]+$")
    rule_version: int = Field(gt=0, strict=True)
    profile_versions: dict[UUID, Annotated[int, Field(gt=0, strict=True)]] = Field(min_length=1, max_length=20)
    meals: list[InitialMealParticipation] = Field(min_length=3, max_length=3)

    @model_validator(mode="after")
    def complete_selection(self):
        """所有参与者恰好有已选来源；个人模式完整参加三餐。"""
        if {m.meal_type for m in self.meals} != {"breakfast", "lunch", "dinner"}:
            raise ValueError("须各选择一次早餐、午餐和晚餐")
        ids = {p for m in self.meals for p in m.participant_ids}
        if ids != set(self.profile_versions):
            raise ValueError("档案版本须恰好覆盖全部参加者")
        if self.kind == "single" and (len(ids) != 1 or any(set(m.participant_ids) != ids for m in self.meals)):
            raise ValueError("个人模式仅支持一位成员完整三餐")
        self.meals.sort(key=lambda m: ("breakfast", "lunch", "dinner").index(m.meal_type))
        return self


class InitialPlannerInput(InitialPlanSelection):
    """显式选定初始配餐范围，幂等创建固定线程。"""

    client_request_id: UUID

"""家庭共餐明确餐次、参与者与逐菜份量。"""

from datetime import date
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, model_validator

from yuxi.services.health_meal_plan_types import MealPlanSpec, PlannedPortion
from yuxi.services.health_vision_types import HealthDTO, HealthVisionError


class FamilyMemberPortion(PlannedPortion):
    """只记录明确吃该菜的成员，缺量不推断平均份量。"""

    member_id: UUID


class FamilyPlannedDish(HealthDTO):
    """一份实际配方分别分配给有限个成员。"""

    recipe_version_id: UUID
    member_portions: list[FamilyMemberPortion] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def distinct_members(self):
        """同菜同成员只有一次份量，顺序归一化。"""
        ids = [p.member_id for p in self.member_portions]
        if len(ids) != len(set(ids)):
            raise ValueError("同一道菜成员份量重复")
        self.member_portions.sort(key=lambda p: str(p.member_id))
        return self


class FamilyPlannedMeal(HealthDTO):
    """参与者须有至少一道菜，菜的成员只能属于本餐。"""

    meal_type: Literal["breakfast", "lunch", "dinner"]
    participant_ids: list[UUID] = Field(min_length=1, max_length=20)
    dishes: list[FamilyPlannedDish] = Field(min_length=1, max_length=10)

    @model_validator(mode="after")
    def complete_allocation(self):
        """明确参与关系必须与实际菜品分配一致。"""
        allocated = {p.member_id for d in self.dishes for p in d.member_portions}
        if len(self.participant_ids) != len(set(self.participant_ids)) or allocated != set(self.participant_ids):
            raise ValueError("本餐参与者重复、未分配菜品或包含餐外成员")
        self.participant_ids.sort(key=str)
        return self


class FamilyMealPlanSpec(HealthDTO):
    """每日家庭三餐，允许成员只参加其中明确的餐次。"""

    kind: Literal["family"]
    plan_date: date
    meals: list[FamilyPlannedMeal] = Field(min_length=3, max_length=3)

    @model_validator(mode="after")
    def three_meals(self):
        """家庭完整三餐与成员个人全天覆盖分别判断。"""
        if {m.meal_type for m in self.meals} != {"breakfast", "lunch", "dinner"}:
            raise ValueError("家庭须各包含一次早餐、午餐、晚餐")
        if len({p for m in self.meals for p in m.participant_ids}) > 20:
            raise ValueError("家庭参与成员超过支持范围")
        self.meals.sort(key=lambda m: ("breakfast", "lunch", "dinner").index(m.meal_type))
        return self


class FamilySafeSelection(HealthDTO):
    """家庭选择全部参与者版本，不接受身体参数或安全结论。"""

    version: int = Field(gt=0, strict=True)
    rule_code: str = Field(min_length=1, max_length=80, pattern=r"^[a-zA-Z0-9_.:-]+$")
    rule_version: int = Field(gt=0, strict=True)
    profile_versions: dict[UUID, Annotated[int, Field(gt=0, strict=True)]] = Field(min_length=1, max_length=20)


class FamilySafeSwapSelection(FamilySafeSelection):
    """选择明确共同菜品位置，不改变参与成员或份量。"""

    meal_type: Literal["breakfast", "lunch", "dinner"]
    dish_index: int = Field(ge=0, le=9, strict=True)


class FamilySafeSwapInput(FamilySafeSwapSelection):
    """只接受当前合格候选的菜谱版本。"""

    client_request_id: UUID
    recipe_version_id: UUID


class FamilySafeRegenerationInput(FamilySafeSelection):
    """确认服务端完整组合摘要，不提交客户端重生成方案。"""

    client_request_id: UUID
    preview_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


class FamilyDishAllocation(HealthDTO):
    """只选择既有菜位和个人份量，不接受替换菜谱。"""

    dish_index: int = Field(ge=0, le=9, strict=True)
    member_portions: list[FamilyMemberPortion] = Field(min_length=1, max_length=20)


class FamilyMealAllocation(HealthDTO):
    """提交一餐完整分配，重复菜位或成员不能叠加。"""

    meal_type: Literal["breakfast", "lunch", "dinner"]
    participant_ids: list[UUID] = Field(min_length=1, max_length=20)
    dishes: list[FamilyDishAllocation] = Field(min_length=1, max_length=10)

    @model_validator(mode="after")
    def complete_allocation(self):
        """餐次成员与各菜实际分配一致，顺序归一化。"""
        indexes = [d.dish_index for d in self.dishes]
        allocated = {p.member_id for d in self.dishes for p in d.member_portions}
        if len(indexes) != len(set(indexes)):
            raise ValueError("本餐菜位重复")
        if len(self.participant_ids) != len(set(self.participant_ids)) or allocated != set(self.participant_ids):
            raise ValueError("本餐参与者重复或与实际分配不符")
        for dish in self.dishes:
            ids = [p.member_id for p in dish.member_portions]
            if len(ids) != len(set(ids)):
                raise ValueError("同菜成员份量重复")
            dish.member_portions.sort(key=lambda p: str(p.member_id))
        self.participant_ids.sort(key=str)
        self.dishes.sort(key=lambda d: d.dish_index)
        return self


class FamilyParticipationSelection(FamilySafeSelection):
    """只调整原三餐参加者与份量，明确新参与者的全部档案版本。"""

    allocations: list[FamilyMealAllocation] = Field(min_length=3, max_length=3)

    @model_validator(mode="after")
    def three_allocations(self):
        """三餐各出现一次，家庭总成员不超过已支持范围。"""
        if {m.meal_type for m in self.allocations} != {"breakfast", "lunch", "dinner"}:
            raise ValueError("须各调整一次早餐、午餐、晚餐")
        if len({p for m in self.allocations for p in m.participant_ids}) > 20:
            raise ValueError("家庭参与成员超过支持范围")
        self.allocations.sort(key=lambda m: ("breakfast", "lunch", "dinner").index(m.meal_type))
        return self


class FamilyParticipationInput(FamilyParticipationSelection):
    """用户明确确认试算摘要，不提交营养或批准结果。"""

    client_request_id: UUID
    preview_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    reason: str = Field(min_length=1, max_length=500)


def parse_meal_plan_spec(payload):
    """持久化边界按明确类型解析，不把家庭对象当单成员。"""
    return (FamilyMealPlanSpec if payload.get("kind") == "family" else MealPlanSpec).model_validate(payload)


def plan_member_ids(anchor_id, payload):
    """返回所有实际参与者，入口成员必须属于计划。"""
    if payload.get("kind") != "family":
        return [anchor_id]
    spec = FamilyMealPlanSpec.model_validate(payload)
    ids = sorted({str(p) for m in spec.meals for p in m.participant_ids})
    if anchor_id not in ids:
        raise HealthVisionError("plan_member_required", "入口成员须参加至少一餐", 422)
    return ids

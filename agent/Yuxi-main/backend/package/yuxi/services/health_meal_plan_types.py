"""三餐计划只接受菜谱版本和拟用份量，不接收模型营养值。"""

from datetime import date
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from yuxi.services.health_vision_types import HealthDTO


class PlannedPortion(HealthDTO):
    """个人或共餐分配共用明确计划份量，不作为实际摄入。"""

    grams: Decimal | None = Field(default=None, gt=0, le=10000, decimal_places=6)
    portion_reference_id: UUID | None = None
    portion_count: Decimal | None = Field(default=None, gt=0, le=1000, decimal_places=6)

    @model_validator(mode="after")
    def valid_portion(self):
        """克数与已发布份量参考互斥，未知份量保留为空。"""
        if self.portion_reference_id:
            if self.grams is not None or self.portion_count is None:
                raise ValueError("参考份量须填写数量并留空克数")
        elif self.portion_count is not None:
            raise ValueError("份量数量须关联参考版本")
        return self


class PlannedDish(PlannedPortion):
    """明确已发布菜谱版本的计划份量。"""

    recipe_version_id: UUID


class PlannedMeal(HealthDTO):
    """一个明确餐次包含有限个已发布菜谱。"""

    meal_type: Literal["breakfast", "lunch", "dinner"]
    dishes: list[PlannedDish] = Field(min_length=1, max_length=10)


class MealPlanSpec(HealthDTO):
    """单日三餐候选，不含档案、审核标记或营养目标。"""

    plan_date: date
    meals: list[PlannedMeal] = Field(min_length=3, max_length=3)

    @model_validator(mode="after")
    def three_meals(self):
        """重复餐次或缺少一餐不能计为完整三餐结构。"""
        if {meal.meal_type for meal in self.meals} != {"breakfast", "lunch", "dinner"}:
            raise ValueError("须各包含一次早餐、午餐和晚餐")
        self.meals.sort(key=lambda meal: ("breakfast", "lunch", "dinner").index(meal.meal_type))
        return self


class MealPlanSave(HealthDTO):
    """用户选择服务器预览保存，不提交自行计算的快照。"""

    client_request_id: UUID
    preview_id: UUID


class MealPlanSwap(HealthDTO):
    """换菜以当前版本及餐次位置确定唯一目标。"""

    client_request_id: UUID
    version: int = Field(gt=0, strict=True)
    meal_type: Literal["breakfast", "lunch", "dinner"]
    dish_index: int = Field(ge=0, le=9, strict=True)
    replacement: PlannedDish
    reason: str = Field(min_length=1, max_length=500)


class PlannerAnswer(HealthDTO):
    """模型最终输出只能引用运行回执或提出补充问题。"""

    preview_id: UUID | None = None
    questions: list[str] = Field(default_factory=list, max_length=3)

    @model_validator(mode="after")
    def one_result(self):
        """回执与澄清问题只选一种，拒绝自由编造餐单字段。"""
        if bool(self.preview_id) == bool(self.questions):
            raise ValueError("选择一个预览回执或补充问题")
        if any(not q.strip() or len(q) > 200 for q in self.questions):
            raise ValueError("补充问题长度无效")
        return self


class SafeSwapSelection(HealthDTO):
    """明确选定版本与一道菜，不接受客户端营养和安全结论。"""

    version: int = Field(gt=0, strict=True)
    rule_code: str = Field(min_length=1, max_length=80, pattern=r"^[a-zA-Z0-9_.:-]+$")
    rule_version: int = Field(gt=0, strict=True)
    profile_version: int = Field(gt=0, strict=True)
    meal_type: Literal["breakfast", "lunch", "dinner"]
    dish_index: int = Field(ge=0, le=9, strict=True)


class SafeSwapInput(SafeSwapSelection):
    """用户只选择服务器当前三候选中的实际菜谱版本。"""

    client_request_id: UUID
    recipe_version_id: UUID


class SafeRegenerationSelection(HealthDTO):
    """整份餐单选择当前来源，不接收客户端份量和营养目标。"""

    version: int = Field(gt=0, strict=True)
    rule_code: str = Field(min_length=1, max_length=80, pattern=r"^[a-zA-Z0-9_.:-]+$")
    rule_version: int = Field(gt=0, strict=True)
    profile_version: int = Field(gt=0, strict=True)


class SafeRegenerationInput(SafeRegenerationSelection):
    """用户确认服务端预览摘要，不能提交自行编造的方案。"""

    client_request_id: UUID
    preview_hash: str = Field(pattern=r"^[0-9a-f]{64}$")

"""日常参考餐单只接收可核对原文和真实规格，不接收营养或审核结论。"""

from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from yuxi.services.health_vision_types import HealthDTO

REFERENCE_TOOLS = (
    "get_reference_plan_context",
    "search_reference_recipes",
    "read_reference_recipe",
    "save_reference_meal_plan",
)


class ReferenceSelection(HealthDTO):
    """用户明确选择的日期、家庭及就餐成员。"""

    mode: Literal["reference"] = "reference"
    family_id: UUID
    plan_date: date
    participant_ids: list[UUID] = Field(min_length=1, max_length=20)
    meal_types: list[Literal["breakfast", "lunch", "dinner"]] = Field(
        default_factory=lambda: ["breakfast", "lunch", "dinner"], min_length=1, max_length=3
    )
    daily_base_version: int | None = Field(default=None, ge=0, strict=True)

    @model_validator(mode="after")
    def unique_members(self):
        """重复身份不扩大处理范围。"""
        if len(set(self.participant_ids)) != len(self.participant_ids) or len(set(self.meal_types)) != len(
            self.meal_types
        ):
            raise ValueError("就餐成员不能重复")
        self.participant_ids.sort(key=str)
        return self


class ReferenceDish(HealthDTO):
    """菜名和食材、步骤来自本 Run 打开的原食谱。"""

    file_id: str = Field(min_length=1, max_length=64)
    chunk_id: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=120)
    ingredients: list[str] = Field(min_length=1, max_length=30)
    steps: list[str] = Field(min_length=1, max_length=20)
    portion_quote: str | None = Field(default=None, max_length=400)
    nutrition_quote: str | None = Field(default=None, max_length=1200)


class ReferenceMeal(HealthDTO):
    """三餐使用当前已选成员，模型不能另选家庭或日期。"""

    meal_type: Literal["breakfast", "lunch", "dinner"]
    dishes: list[ReferenceDish] = Field(min_length=1, max_length=5)


class ReferencePurchaseItem(HealthDTO):
    """Agent 从已读取目录选择商品的包装数量。"""

    sku_id: str = Field(min_length=1, max_length=80)
    quantity: int = Field(ge=1, le=99, strict=True)
    ingredient_refs: list[str] = Field(min_length=1, max_length=450)


class ReferencePurchaseGap(HealthDTO):
    """未选商品必须指向菜谱中的食材并说明实际原因。"""

    ingredient: str = Field(min_length=1, max_length=1200)
    reason: Literal["no_match", "needs_confirmation", "not_sold", "catalog_unavailable"]
    detail: str = Field(min_length=2, max_length=300, pattern=r"\S")


class ReferencePlanDraft(HealthDTO):
    """模型只提交参考菜单与规格选择，服务端补齐来源与缺失状态。"""

    meals: list[ReferenceMeal] = Field(min_length=1, max_length=3)
    purchase_items: list[ReferencePurchaseItem] = Field(max_length=30)
    purchase_gaps: list[ReferencePurchaseGap] = Field(max_length=450)

    @model_validator(mode="after")
    def complete_day(self):
        """缺餐和重复规格均显式拒绝。"""
        if len({m.meal_type for m in self.meals}) != len(self.meals):
            raise ValueError("参考餐次不能重复")
        if len({i.sku_id for i in self.purchase_items}) != len(self.purchase_items):
            raise ValueError("相同规格须合并数量")
        ingredients = {i for m in self.meals for d in m.dishes for i in d.ingredients}
        decisions = [i for item in self.purchase_items for i in item.ingredient_refs]
        decisions.extend(gap.ingredient for gap in self.purchase_gaps)
        if set(decisions) != ingredients or len(decisions) != len(set(decisions)):
            raise ValueError("每种食材原文必须且只能对应一个采购商品或一条未选原因")
        return self

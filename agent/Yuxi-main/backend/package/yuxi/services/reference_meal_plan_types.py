"""日常参考餐单只接收可核对原文和真实规格，不接收营养或审核结论。"""

from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from yuxi.services.health_vision_types import HealthDTO
from yuxi.services.reference_meal_composition import MAX_REFERENCE_DISHES
from yuxi.services.recipe_translation_types import RecipeChineseDisplay

REFERENCE_TOOLS = (
    "get_reference_plan_context",
    "find_reference_products",
    "search_reference_recipes",
    "read_reference_recipe",
    "save_reference_meal_plan",
)

REFERENCE_CATALOG_CHAIN_VERSION = 3


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
    requested_dish_count: int | None = Field(default=None, ge=1, le=MAX_REFERENCE_DISHES, strict=True)
    simple_meal: Literal[True] | None = None

    @model_validator(mode="after")
    def unique_members(self):
        """重复身份不扩大处理范围。"""
        if len(set(self.participant_ids)) != len(self.participant_ids) or len(set(self.meal_types)) != len(
            self.meal_types
        ):
            raise ValueError("就餐成员不能重复")
        self.participant_ids.sort(key=str)
        return self


class RecipeNutritionHighlight(HealthDTO):
    """只摘录本轮商城商品实际提供的营养说明。"""

    product_id: str | None = Field(default=None, min_length=1, max_length=80)
    sku_id: str | None = Field(default=None, min_length=1, max_length=80)
    quote: str = Field(min_length=2, max_length=800)

    @model_validator(mode="after")
    def one_product_identity(self):
        """新回执使用商品身份，旧快照仍可按 SKU 读取。"""
        if bool(self.product_id) == bool(self.sku_id):
            raise ValueError("营养摘录须且只能引用一个商品身份")
        return self


class ReferenceDishAssignment(HealthDTO):
    """替代菜须明确对应的本餐成员和原共用菜。"""

    alternative_for: list[UUID] = Field(default_factory=list, max_length=20)
    replaces_file_id: str | None = Field(default=None, min_length=1, max_length=64)

    @model_validator(mode="after")
    def paired_assignment(self):
        """拒绝缺项和重复成员。"""
        if bool(self.alternative_for) != bool(self.replaces_file_id) or len(set(self.alternative_for)) != len(
            self.alternative_for
        ):
            raise ValueError("替代菜须提供共用菜来源和不重复的就餐成员")
        self.alternative_for.sort(key=str)
        return self


class ReferenceDish(ReferenceDishAssignment):
    """菜名和食材、步骤来自本 Run 打开的原食谱。"""

    file_id: str = Field(min_length=1, max_length=64)
    chunk_id: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=120)
    ingredients: list[str] = Field(min_length=1, max_length=30)
    steps: list[str] = Field(min_length=1, max_length=20)
    portion_quote: str | None = Field(default=None, max_length=400)
    nutrition_quote: str | None = Field(default=None, max_length=1200)
    display_zh: RecipeChineseDisplay | None = None
    cooking_minutes: int | None = Field(
        default=None, ge=1, le=1440, strict=True, description="预计总制作分钟数，包含备菜；按原文步骤估算，不是商品事实"
    )
    nutrition_highlights: list[RecipeNutritionHighlight] = Field(default_factory=list, max_length=8)


class ReferenceMeal(HealthDTO):
    """三餐使用当前已选成员，模型不能另选家庭或日期。"""

    meal_type: Literal["breakfast", "lunch", "dinner"]
    dishes: list[ReferenceDish] = Field(min_length=1, max_length=MAX_REFERENCE_DISHES)


class ReferencePurchaseItem(HealthDTO):
    """服务端核对商品名后，保存 Agent 选择的规格与包装数量。"""

    sku_id: str = Field(min_length=1, max_length=80)
    quantity: int = Field(ge=1, le=99, strict=True)
    ingredient_refs: list[str] = Field(min_length=1, max_length=450)


class ReferenceProductMatch(HealthDTO):
    """菜谱食材只绑定商城商品，规格由用户购买时再选择。"""

    product_id: str = Field(min_length=1, max_length=80)
    ingredient_refs: list[str] = Field(min_length=1, max_length=450)


class ReferencePurchaseGap(HealthDTO):
    """未选商品必须指向菜谱中的食材并说明实际原因。"""

    ingredient: str = Field(min_length=1, max_length=1200)
    reason: Literal[
        "no_match",
        "needs_confirmation",
        "not_sold",
        "catalog_unavailable",
        "optional_not_selected",
        "selection_pending",
    ]
    detail: str = Field(min_length=2, max_length=300, pattern=r"\S")


class ReferencePlanDraft(HealthDTO):
    """模型只提交参考菜单与商品选择，服务端补齐来源与规格列表。"""

    meals: list[ReferenceMeal] = Field(min_length=1, max_length=3)
    product_matches: list[ReferenceProductMatch] = Field(default_factory=list, max_length=30)
    purchase_items: list[ReferencePurchaseItem] = Field(default_factory=list, max_length=30)
    purchase_gaps: list[ReferencePurchaseGap] = Field(default_factory=list, max_length=450)

    @model_validator(mode="after")
    def complete_day(self):
        """缺餐和重复规格均显式拒绝。"""
        if len({m.meal_type for m in self.meals}) != len(self.meals):
            raise ValueError("参考餐次不能重复")
        if len({i.sku_id for i in self.purchase_items}) != len(self.purchase_items):
            raise ValueError("相同规格须合并数量")
        if len({i.product_id for i in self.product_matches}) != len(self.product_matches):
            raise ValueError("相同商品须合并食材引用")
        ingredients = {i for m in self.meals for d in m.dishes for i in d.ingredients}
        decisions = [i for item in self.product_matches for i in item.ingredient_refs]
        decisions.extend(i for item in self.purchase_items for i in item.ingredient_refs)
        decisions.extend(gap.ingredient for gap in self.purchase_gaps)
        if set(decisions) != ingredients or len(decisions) != len(set(decisions)):
            raise ValueError("每种食材原文必须且只能对应一个采购商品或一条未选原因")
        return self

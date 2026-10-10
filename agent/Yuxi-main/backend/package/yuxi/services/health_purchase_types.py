"""采购只接受有效采用版本与用户明确确认的同状态可食库存。"""

from decimal import Decimal
from uuid import UUID

from pydantic import Field, model_validator

from yuxi.services.health_vision_types import HealthDTO

PURCHASE_TOOLS = ("get_purchase_requirements", "preview_purchase_requirements")


class PurchaseInventory(HealthDTO):
    """库存为明确食品版本及烹饪状态的可食克数，不是商品毛重。"""

    food_id: UUID
    cooking_state: str = Field(min_length=1, max_length=40)
    edible_grams: Decimal = Field(ge=0, le=1000000, decimal_places=6)


class PurchaseSelection(HealthDTO):
    """采用与库存选择由用户业务入口固定，模型不能修改。"""

    adoption_id: UUID
    adoption_version: int = Field(gt=0, strict=True)
    plan_version: int = Field(gt=0, strict=True)
    inventory_confirmed: bool = Field(default=False, strict=True)
    inventory: list[PurchaseInventory] = Field(default_factory=list, max_length=200)

    @model_validator(mode="after")
    def consistent_inventory(self):
        """拒绝重复库存以及尚未确认的扣减输入。"""
        keys = [(item.food_id, item.cooking_state) for item in self.inventory]
        if len(keys) != len(set(keys)):
            raise ValueError("同食品版本和状态的库存只能填写一次")
        if self.inventory and not self.inventory_confirmed:
            raise ValueError("填写库存后须明确确认库存")
        return self


class PurchaseInput(PurchaseSelection):
    """业务入口用独立幂等键创建采购专属线程。"""

    client_request_id: UUID


class PurchaseAnswer(HealthDTO):
    """模型最终只引用当前Run回执或提出具体补充问题。"""

    preview_id: UUID | None = None
    questions: list[str] = Field(default_factory=list, max_length=3)

    @model_validator(mode="after")
    def one_answer(self):
        """拒绝自造食材、营养、商品和交易字段。"""
        if bool(self.preview_id) == bool(self.questions):
            raise ValueError("请选择一个回执或补充问题")
        if any(not text.strip() or len(text) > 200 for text in self.questions):
            raise ValueError("补充问题长度无效")
        return self

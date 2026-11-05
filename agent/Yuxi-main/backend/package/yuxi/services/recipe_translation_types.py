"""菜谱辅助译文的有界展示结构，不承载营养或采购事实。"""

from pydantic import Field

from yuxi.services.health_vision_types import HealthDTO


class RecipeChineseDisplay(HealthDTO):
    """每条译文与同位置原文对应，原始数量及计量范围保留。"""

    name: str = Field(min_length=1, max_length=240)
    ingredients: list[str] = Field(min_length=1, max_length=30)
    steps: list[str] = Field(min_length=1, max_length=20)
    portion_quote: str | None = Field(default=None, max_length=800)
    nutrition_quote: str | None = Field(default=None, max_length=2400)

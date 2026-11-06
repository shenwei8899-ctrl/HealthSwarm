"""参考菜谱保存与单菜采购共用烹饪用水判定。"""

import pytest

from yuxi.services.health_vision_types import HealthVisionError
from yuxi.services.meal_dish_service import _scoped_reference_gaps
from yuxi.services.reference_cooking_water import cooking_water
from yuxi.services.reference_meal_plan_service import checked_reference_gaps
from yuxi.services.reference_meal_plan_types import ReferencePurchaseGap
from yuxi.services.reference_recipe_matching import cooking_water_ingredient, reference_ingredient_matches


@pytest.mark.parametrize(
    "ingredient",
    [
        "1 ½ cups water",
        "1 cup water",
        "1 c water",
        "cup water",
        "1/2 water",
        "1/2-cup water",
        "1-2 cups water",
        "Water, 1 cup",
        "water, as needed",
        "water适量",
        "1 cup water, as needed",
        "1杯水",
        "水适量",
        "热水",
        "热 水",
        "清 水",
        "凉水",
        "冷水",
        "沸水",
    ],
)
def test_saved_water_gap_is_accepted_by_single_dish_purchase(ingredient):
    """已保存的纯用水缺口在读取采购时保持同一判断。"""
    gap = ReferencePurchaseGap(ingredient=ingredient, reason="not_sold", detail="烹饪用水自行准备")
    saved = checked_reference_gaps([gap], [])
    projected = _scoped_reference_gaps({"ingredients": [ingredient]}, {"purchase_gaps": saved})

    assert cooking_water(ingredient) and cooking_water_ingredient(ingredient)
    assert reference_ingredient_matches((ingredient,), [])[0]["status"] == "cooking_water"
    assert projected[0]["reason"] == "not_sold"


@pytest.mark.parametrize("ingredient", ["1 ½ cups chicken broth", "water and sugar", "1 cup water with salt"])
def test_composite_ingredient_cannot_be_marked_as_free_water(ingredient):
    """混合食材不能以烹饪用水的理由跳过采购。"""
    gap = ReferencePurchaseGap(ingredient=ingredient, reason="not_sold", detail="烹饪用水自行准备")

    assert not cooking_water(ingredient) and not cooking_water_ingredient(ingredient)
    with pytest.raises(HealthVisionError, match="reference_purchase_reason_invalid"):
        checked_reference_gaps([gap], [])
    with pytest.raises(HealthVisionError, match="dish_ingredients_missing"):
        _scoped_reference_gaps({"ingredients": [ingredient]}, {"purchase_gaps": [gap.model_dump()]})

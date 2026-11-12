"""真实失败形态的候选完整性、曝光分散和合法商品默认选择回归。"""

from yuxi.services.reference_recipe_index import rank_reference_recipes
from yuxi.services.reference_recipe_variety import variety_context
from yuxi.services.reference_meal_selection_service import _product_choices
from yuxi.services.reference_recipe_matching import reference_candidate_key


def recipe(name, extra=""):
    """构造可独立判断完整性的合成原谱。"""
    return (name, "kb", f"家常菜谱_{name}.md", "hash", name,
            f"# {name}\n## 食材\n- 鸡蛋1个\n## 做法\n1. 蒸熟\n{extra}")


def test_exact_name_cannot_promote_unusable_recipe():
    rows = [recipe("鸡蛋蒸熟示例", "## Notes\nAdd butter."), recipe("鸡蛋羹")]
    result = rank_reference_recipes(rows, [], "鸡蛋蒸熟示例")
    assert all(item["file_id"] != "鸡蛋蒸熟示例" for item in result)


def test_household_and_date_disperse_equal_candidates_without_random_retries():
    rows = [recipe(f"鸡蛋做法{index}") for index in range(12)]
    def first(family, day):
        policy = variety_context([], {"family_id": family, "plan_date": day})
        return rank_reference_recipes(rows, [], "鸡蛋", variety=policy)[0]["file_id"]
    assert first("family-a", "2026-11-11") == first("family-a", "2026-11-11")
    assert len({first(str(i), "2026-11-11") for i in range(12)}) >= 4
    assert len({first("family-a", f"2026-11-{i:02}") for i in range(1, 13)}) >= 4


def test_popular_recipe_does_not_win_only_for_a_small_coverage_advantage():
    rows = [recipe("鸡蛋热门"), recipe("鸡蛋新菜")]
    rows[1] = (*rows[1][:-1], rows[1][-1].replace("- 鸡蛋1个", "- 鸡蛋1个\n- 1 tomato"))
    products = [{"sku_id": "egg", "product_name": "鸡蛋", "sale_status": "available", "available_quantity": 5}]
    history = [("other", "2026-11-11", [{"dishes": [{"name": "鸡蛋热门", "file_id": "鸡蛋热门"}]}])]
    policy = variety_context(history, {"family_id": "new", "plan_date": "2026-11-11"})
    assert rank_reference_recipes(rows, products, "鸡蛋", variety=policy)[0]["file_id"] == "鸡蛋新菜"


def test_household_rotation_is_not_erased_by_minor_purchase_coverage_differences():
    rows = [recipe(f"鸡蛋做法{index}") for index in range(12)]
    for index in range(1, len(rows)):
        rows[index] = (*rows[index][:-1], rows[index][-1].replace("- 鸡蛋1个", "- 鸡蛋1个\n- 1 tomato"))
    products = [{"sku_id": "egg", "product_name": "鸡蛋", "sale_status": "available", "available_quantity": 5}]
    choices = {
        rank_reference_recipes(rows, products, "鸡蛋", variety=variety_context(
            [], {"family_id": str(index), "plan_date": "2026-11-11"}))[0]["file_id"]
        for index in range(12)
    }
    assert len(choices) >= 4


def test_automatic_product_uses_only_current_issued_candidates_without_price_bias():
    ingredient = "100 g rice"
    key = reference_candidate_key(ingredient)
    def product(pid, price):
        return {"product_id": pid, "product_name": "大米", "skus": [
            {"sku_id": pid, "product_id": pid, "product_name": "大米", "price_cent": price,
             "available_quantity": 10, "sale_status": "available"}]}
    seen = {pid: product(pid, price) for pid, price in [("a", 900), ("b", 100), ("unissued", 1)]}
    meals = [{"dishes": [{"ingredients": [ingredient]}]}]
    chosen, gaps = _product_choices(meals, [], seen, issued_candidates={key: {"a", "b", "deleted"}})
    assert chosen == [{"product_id": "a", "ingredient_refs": [ingredient]}]
    assert gaps == []


def test_generic_fish_queries_recall_english_source_without_product_identity_guessing():
    from yuxi.services.reference_recipe_index import recall_foods
    from yuxi.services.reference_recipe_matching import reference_food_mentions

    assert "鱼" in recall_foods("清蒸鱼") & recall_foods("Steamed Tilapia")
    assert "虾" in recall_foods("虾仁") & recall_foods("Shrimp")
    assert "鱼" not in reference_food_mentions("清蒸鱼")


def test_translation_geometry_is_not_a_quantity_and_length_units_still_match():
    from yuxi.services.recipe_translation_service import quantity_signature

    assert quantity_signature("Slice onion into 1 cm half-rings.") == quantity_signature("洋葱切成1厘米半圆环。")
    assert quantity_signature("1 cm") != quantity_signature("1毫米")
    assert quantity_signature("half cup water") == quantity_signature("1/2杯水")


def test_translation_reports_all_fields_and_rejects_added_temperature():
    import pytest
    from yuxi.services.recipe_translation_service import checked_chinese_display
    from yuxi.services.health_vision_types import HealthVisionError

    original = {"name": "Salad", "ingredients": ["1 tomato"], "steps": ["Preheat to 400 °F."]}
    display = {"name": "沙拉（Salad）", "ingredients": ["2个番茄"], "steps": ["预热到400°F（200°C）。"]}
    with pytest.raises(HealthVisionError) as caught:
        checked_chinese_display(original, display)
    assert all(part in caught.value.message for part in ("name", "ingredients[0]", "steps[0]"))


def test_negative_spice_preference_never_promotes_spicy_recipe():
    from yuxi.services.reference_recipe_variety import candidate_priority

    for preference in ("不吃辣", "不喜欢辣", "忌辣", "不辣"):
        variety = {"preferences": [preference], "recent": {}, "popular": {}}
        assert candidate_priority(set(), "Spicy chicken with chilli", variety) <= candidate_priority(
            set(), "Poached chicken", variety
        )


def test_translation_chinese_count_words_keep_original_quantity_and_fraction():
    from yuxi.services.recipe_translation_service import quantity_signature

    assert quantity_signature("one of flavoring packets") == quantity_signature("其中一包调味料")
    assert quantity_signature("four dinner plates (about 1 cup each), one-fourth") == quantity_signature(
        "四个餐盘（每份约1杯），四分之一"
    )
    assert quantity_signature("four plates") != quantity_signature("三个餐盘")
    assert quantity_signature("20 plates") != quantity_signature("一百二十个餐盘")
    from yuxi.services.health_vision_types import HealthVisionError
    import pytest

    for unsupported in ("一百四分之一杯", "一百零四分之一杯", "百分之一杯", "三分之1杯",
                        "四分之一百零四", "四分之一百", "四分之一点五", "四分之一點五"):
        with pytest.raises(HealthVisionError, match="recipe_translation_invalid"):
            quantity_signature(unsupported)
    assert quantity_signature("salmon") == quantity_signature("三文鱼")

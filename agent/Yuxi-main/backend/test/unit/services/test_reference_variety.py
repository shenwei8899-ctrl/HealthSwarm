"""菜品差异、均衡召回和版本缓存的业务结果回归。"""

import pytest

from yuxi.services.reference_recipe_variety import (
    balanced_candidates,
    dish_keys,
    validate_variety,
    variety_context,
)
from yuxi.services.reference_recipe_index import rank_reference_recipes, cached_ingredient_matches, prepared_content
from yuxi.services.health_vision_types import HealthVisionError


def meals(names):
    return [
        {"meal_type": kind, "dishes": [{"name": name, "source": {"file_id": name}}]}
        for kind, name in zip(("breakfast", "lunch", "dinner"), names)
    ]


def test_four_queries_get_equal_opportunity():
    ranked = [[{"file_id": f"{group}-{n}"} for n in range(8)] for group in range(4)]
    result = balanced_candidates(ranked)
    assert len(result) == 24
    assert [item["file_id"] for item in result[:4]] == [f"{group}-0" for group in range(4)]
    assert {
        group: sum(item["file_id"].startswith(str(group)) for item in result) for group in range(4)
    } == dict.fromkeys(range(4), 6)


def test_family_history_is_cross_date_and_other_family_only_affects_popularity():
    policy = variety_context(
        [
            ("a", "2026-11-10", meals(["eggs"])),
            ("a", "2026-11-02", meals(["fish"])),
            ("b", "2026-11-11", meals(["rice"])),
        ],
        {"family_id": "a", "plan_date": "2026-11-11"},
    )
    assert policy["excluded"] == dish_keys({"name": "eggs", "file_id": "eggs"})
    assert policy["recent"]["file:fish"] == 1
    assert policy["popular"]["file:rice"] == 1
    assert "file:rice" not in policy["excluded"]


@pytest.mark.parametrize("day", ["2026-11-10", "2026-11-11", "2026-11-12"])
def test_same_dish_cannot_bypass_history_with_new_file_or_punctuation(day):
    with pytest.raises(HealthVisionError) as error:
        validate_variety(
            [("a", day, meals(["Chicken Breast"]))],
            {"family_id": "a", "plan_date": "2026-11-11"},
            meals(["CHICKEN-BREAST"]),
        )
    assert error.value.code == "reference_recipe_repeated"


def test_different_family_can_share_dish_but_not_complete_daily_menu():
    history = [("b", "2026-11-11", meals(["rice", "fish", "greens"]))]
    selection = {"family_id": "a", "plan_date": "2026-11-11"}
    validate_variety(history, selection, meals(["rice", "beef", "greens"]))
    with pytest.raises(HealthVisionError) as error:
        validate_variety(history, selection, meals(["greens", "rice", "fish"]))
    assert error.value.code == "reference_menu_repeated"


def test_partial_save_checks_combined_menu():
    history = [("b", "2026-11-11", meals(["rice", "fish", "greens"])), ("a", "2026-11-11", meals(["rice", "fish"]))]
    with pytest.raises(HealthVisionError) as error:
        validate_variety(
            history,
            {"family_id": "a", "plan_date": "2026-11-11"},
            [meals(["rice", "fish", "greens"])[2]],
            current_menus=[("a", "self", meals(["rice", "fish"]))],
            actor_uid="self",
        )
    assert error.value.code == "reference_menu_repeated"


def test_history_cannot_invent_menu_from_different_accounts():
    validate_variety(
        [("a", "2026-11-11", meals(["D"])), ("a", "2026-11-11", meals(["A", "B", "C"]))],
        {"family_id": "b", "plan_date": "2026-11-11"},
        meals(["D", "B", "C"]),
        current_menus=[("a", "first", meals(["A", "B", "C"])), ("a", "second", meals(["D"]))],
        actor_uid="self",
    )


def test_same_household_cannot_reuse_complete_menu_after_alternating_day():
    history = [("a", "2026-11-08", meals(["rice", "fish", "greens"]))]
    selection = {"family_id": "a", "plan_date": "2026-11-11"}
    validate_variety(history, selection, meals(["rice", "beef", "greens"]))
    with pytest.raises(HealthVisionError, match="reference_menu_repeated"):
        validate_variety(history, selection, meals(["greens", "rice", "fish"]))


def test_content_and_catalog_change_invalidate_cached_results():
    rows = [("egg", "kb", "家常菜谱_蒸鸡蛋.md", "hash", "chunk", "# 蒸鸡蛋\n## 食材\n- 鸡蛋 1个\n## 做法\n1. 蒸熟")]
    products = [{"sku_id": "1", "product_name": "鸡蛋", "available_quantity": 5, "sale_status": "available"}]
    prepared_content.cache_clear()
    cached_ingredient_matches.cache_clear()
    first = rank_reference_recipes(rows, products, "鸡蛋")
    assert first[0]["ingredient_matches"][0]["status"] == "matched"
    assert rank_reference_recipes(rows, products, "鸡蛋") == first
    assert cached_ingredient_matches.cache_info().hits > 0
    products[0]["available_quantity"] = 0
    products[0]["sale_status"] = "unavailable"
    assert rank_reference_recipes(rows, products, "鸡蛋")[0]["ingredient_matches"][0]["status"] == "missing_product"
    changed = [(*rows[0][:-1], rows[0][-1].replace("蒸鸡蛋", "鸡蛋羹"))]
    assert rank_reference_recipes(changed, products, "鸡蛋")[0]["name"] == "鸡蛋羹"


def test_preferences_and_history_change_equal_quality_candidates():
    rows = [
        (
            name,
            "kb",
            f"家常菜谱_{name}.md",
            name,
            name,
            f"# {name}\n## 食材\n- 鸡蛋1个\n## 做法\n1. 蒸熟\n菜系：{cuisine}",
        )
        for name, cuisine in (("鸡蛋甲", "粤菜"), ("鸡蛋乙", "湘菜"))
    ]
    policy = variety_context([], {"family_id": "a", "plan_date": "2026-11-11"}, [{"dietary": {"cuisines": ["湘菜"]}}])
    assert rank_reference_recipes(rows, [], "鸡蛋", variety=policy)[0]["file_id"] == "鸡蛋乙"
    policy["preferences"] = []
    policy["popular"]["file:鸡蛋甲"] = 10
    assert rank_reference_recipes(rows, [], "鸡蛋", variety=policy)[0]["file_id"] == "鸡蛋乙"

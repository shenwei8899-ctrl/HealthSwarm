"""验证参考菜数、组合餐与个人替代。"""

from unittest import TestCase

from yuxi.services.health_vision_types import HealthVisionError
from yuxi.services.reference_meal_composition import (
    meal_age_band,
    reference_meal_targets,
    validate_reference_meal_composition,
)


def selection(count, **overrides):
    """构造已验证的餐次和名单。"""
    return {"participant_ids": [str(index) for index in range(count)], "meal_types": ["lunch"], **overrides}


def dish(file_id, *ingredients, **assignment):
    """构造保存入口解析后的原谱。"""
    return {"file_id": file_id, "ingredients": ingredients, **assignment}


COMBO = dish("bowl", "大米100克", "鸡蛋1个", "菠菜100克")
SHARED = [
    dish("rice", "大米100克"),
    dish("egg", "鸡蛋1个"),
    dish("spinach", "菠菜100克"),
    dish("broccoli", "西兰花100克"),
    dish("carrot", "胡萝卜100克"),
]


class TestReferenceMealComposition(TestCase):
    """覆盖人数分档、简餐和替代对个人搭配的影响。"""

    def test_default_targets(self):
        for count, breakfast, lunch in [
            (1, (2, 2), 2),
            (2, (2, 2), 3),
            (3, (3, 3), 4),
            (4, (3, 3), 4),
            (5, (3, 4), 5),
            (20, (3, 4), 5),
        ]:
            with self.subTest(count=count):
                targets = reference_meal_targets(selection(count, meal_types=["breakfast", "lunch", "dinner"]))
                self.assertEqual((targets["breakfast"]["shared_min"], targets["breakfast"]["shared_max"]), breakfast)
                self.assertEqual(targets["lunch"]["shared_min"], lunch)
                self.assertEqual(targets["dinner"], targets["lunch"])

    def test_four_person_lunch_cannot_save_one_dish(self):
        with self.assertRaisesRegex(HealthVisionError, "需安排4道共用菜，目前1道"):
            validate_reference_meal_composition([{"meal_type": "lunch", "dishes": [COMBO]}], selection(4))

    def test_one_person_explicit_simple_meal_requires_all_lunch_groups(self):
        lunch = {"meal_type": "lunch", "dishes": [COMBO]}
        validate_reference_meal_composition([lunch], selection(1, simple_meal=True))
        validate_reference_meal_composition([lunch], selection(1, requested_dish_count=1))
        with self.assertRaisesRegex(HealthVisionError, "缺少可核对"):
            validate_reference_meal_composition([{**lunch, "dishes": [SHARED[0]]}], selection(1, simple_meal=True))
        with self.assertRaisesRegex(HealthVisionError, "需安排3道"):
            validate_reference_meal_composition([lunch], selection(2, simple_meal=True))

    def test_alternative_keeps_individual_coverage_without_counting_as_shared(self):
        tofu = dish("tofu", "豆腐100克", alternative_for=["1"], replaces_file_id="egg")
        lunch = {"meal_type": "lunch", "dishes": [*SHARED, tofu]}
        validate_reference_meal_composition([lunch], selection(5))
        with self.assertRaisesRegex(HealthVisionError, "需安排5道共用菜，目前4道"):
            validate_reference_meal_composition([{**lunch, "dishes": [*SHARED[:-1], tofu]}], selection(5))
        wrong = dish("wrong", "番茄100克", alternative_for=["1"], replaces_file_id="egg")
        with self.assertRaisesRegex(HealthVisionError, "蛋白质类食物"):
            validate_reference_meal_composition([{**lunch, "dishes": [*SHARED, wrong]}], selection(5))
        with self.assertRaisesRegex(HealthVisionError, "本餐部分就餐成员"):
            validate_reference_meal_composition(
                [{**lunch, "dishes": [*SHARED, {**tofu, "alternative_for": ["not-a-diner"]}]}], selection(5)
            )

    def test_duplicate_source_cannot_pad_count(self):
        with self.assertRaisesRegex(HealthVisionError, "重复菜谱"):
            validate_reference_meal_composition([{"meal_type": "lunch", "dishes": [COMBO, COMBO]}], selection(1))

    def test_seasonings_do_not_fill_a_dish_slot(self):
        seasoning = dish("dip", "盐1克", "糖2克")
        with self.assertRaisesRegex(HealthVisionError, "调味料不能单独作为一道菜"):
            validate_reference_meal_composition(
                [{"meal_type": "lunch", "dishes": [COMBO, seasoning]}], selection(1)
            )

    def test_age_band_uses_meal_date(self):
        self.assertEqual(meal_age_band("2020-11-13", "2026-11-12"), "3–5岁")
        self.assertEqual(meal_age_band("2020-11-13", "2026-11-13"), "6–11岁")
        self.assertIsNone(meal_age_band(None, "2026-11-12"))

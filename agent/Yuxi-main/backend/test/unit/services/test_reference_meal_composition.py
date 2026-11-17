"""验证参考菜数、组合餐与个人替代。"""

from unittest import TestCase

from yuxi.services.health_vision_types import HealthVisionError
from yuxi.services.reference_meal_composition import (
    FOOD_GROUP_MEAL_POLICY_VERSION,
    is_plain_reference_staple,
    meal_age_band,
    recipe_food_groups,
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

    def test_one_person_explicit_simple_meal_can_use_one_recipe_without_all_food_groups(self):
        lunch = {"meal_type": "lunch", "dishes": [SHARED[1]]}
        validate_reference_meal_composition([lunch], selection(1, simple_meal=True))
        validate_reference_meal_composition([lunch], selection(1, requested_dish_count=1))
        with self.assertRaisesRegex(HealthVisionError, "缺少可核对"):
            validate_reference_meal_composition(
                [lunch], selection(1, simple_meal=True), policy_version=FOOD_GROUP_MEAL_POLICY_VERSION,
            )
        with self.assertRaisesRegex(HealthVisionError, "需安排3道"):
            validate_reference_meal_composition([lunch], selection(2, simple_meal=True))

    def test_alternative_keeps_assignment_without_counting_as_shared(self):
        tofu = dish("tofu", "豆腐100克", alternative_for=["1"], replaces_file_id="egg")
        lunch = {"meal_type": "lunch", "dishes": [*SHARED, tofu]}
        validate_reference_meal_composition([lunch], selection(5))
        with self.assertRaisesRegex(HealthVisionError, "需安排5道共用菜，目前4道"):
            validate_reference_meal_composition([{**lunch, "dishes": [*SHARED[:-1], tofu]}], selection(5))
        wrong = dish("wrong", "番茄100克", alternative_for=["1"], replaces_file_id="egg")
        replacement = [{**lunch, "dishes": [*SHARED, wrong]}]
        validate_reference_meal_composition(replacement, selection(5))
        with self.assertRaisesRegex(HealthVisionError, "蛋白质类食物"):
            validate_reference_meal_composition(
                replacement, selection(5), policy_version=FOOD_GROUP_MEAL_POLICY_VERSION,
            )
        with self.assertRaisesRegex(HealthVisionError, "本餐部分就餐成员"):
            validate_reference_meal_composition(
                [{**lunch, "dishes": [*SHARED, {**tofu, "alternative_for": ["not-a-diner"]}]}],
                selection(5),
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

    def test_explicit_staple_aliases_preserve_meal_composition(self):
        for raw in ("白米", "白飯（蓬萊米）", "材料｜十谷饭（糙米、小米）：200克", "烏龍麵", "A. 燕麥片 30克"):
            with self.subTest(raw=raw):
                breakfast = {"meal_type": "breakfast", "dishes": [dish("staple", raw), SHARED[1]]}
                validate_reference_meal_composition(
                    [breakfast], selection(1, meal_types=["breakfast"]), policy_version=FOOD_GROUP_MEAL_POLICY_VERSION,
                )

    def test_plain_rice_cannot_fill_a_slot_but_an_old_menu_still_passes(self):
        rice = dish("rice", "白米", "水", "白米及水的比例為1：1.5", name="白飯")
        breakfast = [{"meal_type": "breakfast", "dishes": [rice, SHARED[1]]}]
        chosen = selection(1, meal_types=["breakfast"])
        validate_reference_meal_composition(breakfast, chosen, policy_version=FOOD_GROUP_MEAL_POLICY_VERSION)
        with self.assertRaisesRegex(HealthVisionError, "白飯.*自行准备"):
            validate_reference_meal_composition(breakfast, chosen)

    def test_only_plain_staples_are_excluded(self):
        for name, ingredients in (
            ("白米飯", ["白米 200 克", "水"]),
            ("清水煮白米", ["白米", "水"]),
            ("雜糧飯", ["糙米半杯", "小米30克", "水"]),
            ("小米粥", ["小米", "清水"]),
        ):
            with self.subTest(name=name):
                self.assertTrue(is_plain_reference_staple(name, ingredients))
        for name, ingredients in (
            ("排骨稀飯", ["大米100克", "排骨200克", "水"]),
            ("蛋炒饭", ["大米100克", "鸡蛋1个"]),
            ("法式吐司", ["吐司", "鸡蛋1个"]),
            ("雜糧飯", ["糙米半杯", "腊肠100克"]),
        ):
            with self.subTest(name=name):
                self.assertFalse(is_plain_reference_staple(name, ingredients))

    def test_condiments_and_recipe_notes_do_not_become_staples(self):
        for raw in ("米酒", "米醋", "小米辣", "糯米粉", "白米及水的比例為1：1.5", "白米（可选）"):
            with self.subTest(raw=raw):
                self.assertNotIn("staple", recipe_food_groups([raw]))

    def test_age_band_uses_meal_date(self):
        self.assertEqual(meal_age_band("2020-11-13", "2026-11-12"), "3–5岁")
        self.assertEqual(meal_age_band("2020-11-13", "2026-11-13"), "6–11岁")
        self.assertIsNone(meal_age_band(None, "2026-11-12"))

class TestReferenceMenuCandidates(TestCase):
    def test_full_day_checks_each_meal_and_supplies_only_usable_options(self):
        from yuxi.services.reference_menu_candidates import reference_menu_options

        def item(name, *groups):
            return {"file_id": name, "chunk_id": name, "name": name, "food_groups": groups, "seasoning_only": False}

        pool = [item("白飯", "staple"), item("芙蓉汤", "protein", "vegetable"), item("鸡蛋", "protein"),
                item("乌龙面", "staple"), item("清炒菠菜", "vegetable")]
        chosen = selection(1, meal_types=["breakfast", "lunch", "dinner"], family_id="family", plan_date="2026-11-13")
        legacy = {"policy_version": FOOD_GROUP_MEAL_POLICY_VERSION}
        outcome = reference_menu_options([pool], chosen, [], [], "owner", **legacy)
        self.assertTrue(outcome["menus"])
        self.assertFalse(outcome["coverage_gaps"])
        self.assertNotIn("清炒菠菜", [candidate["name"] for candidate in outcome["items"]])
        for menu in outcome["menus"]:
            self.assertEqual([meal["meal_type"] for meal in menu], chosen["meal_types"])
            for meal in menu:
                self.assertEqual(len(meal["dishes"]), 2)
                groups = set().union(*(set(d["food_groups"]) for d in meal["dishes"]))
                required = reference_meal_targets(chosen, **legacy)[meal["meal_type"]]["food_groups"]
                self.assertGreaterEqual(groups, set(required))

        outcome = reference_menu_options([[pool[0], pool[2], pool[4]]], chosen, [], [], "owner", **legacy)
        self.assertFalse(outcome["menus"])
        self.assertEqual([gap["meal_type"] for gap in outcome["coverage_gaps"]], ["lunch", "dinner"])
        self.assertTrue(all(gap["reason"] == "combination" for gap in outcome["coverage_gaps"]))

        current = reference_menu_options([[pool[2], pool[4]]], chosen, [], [], "owner")
        self.assertTrue(current["menus"])
        self.assertFalse(current["coverage_gaps"])
        self.assertEqual({item["name"] for item in current["items"]}, {"鸡蛋", "清炒菠菜"})
        current = reference_menu_options([[pool[4], {**pool[4], "file_id": "same-title"}]], chosen, [], [], "owner")
        self.assertEqual(
            current["coverage_gaps"],
            [
                {"meal_type": meal_type, "reason": "dish_count", "missing_count": 1}
                for meal_type in chosen["meal_types"]
            ],
        )

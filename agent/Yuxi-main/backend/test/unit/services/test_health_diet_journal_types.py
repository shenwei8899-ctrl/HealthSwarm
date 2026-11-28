"""日记中的未注明餐次保留原话，继续拒绝计划和伪造餐次。"""
import unittest
from datetime import datetime
from types import SimpleNamespace
from uuid import uuid4

from yuxi.services.health_chat_meal_types import ChatMealStatement, meal_from_statement
from yuxi.services.health_vision_types import HealthVisionError


class DietJournalTypesTest(unittest.TestCase):
    def statement(self, text, meal_type="unknown"):
        """构造独立的用户已吃陈述。"""
        source = SimpleNamespace(content=text, created_at=datetime(2026, 11, 23, 2))
        statement = ChatMealStatement(source_quotes=[text], meal_type=meal_type,
                                      items=[{"name": "饼干", "quantity_text": "几块"}])
        return statement, [source]

    def test_unknown_meal_is_saved_without_guessing(self):
        statement, sources = self.statement("我刚吃了几块饼干")
        _, meal = meal_from_statement(statement, sources, str(uuid4()))
        self.assertEqual(meal.meal_type, "unknown")
        self.assertIsNone(meal.items[0].grams)
        self.assertIn("本人份量原文：几块", meal.items[0].uncertainties)

    def test_unknown_does_not_override_explicit_lunch(self):
        statement, sources = self.statement("我中午吃了几块饼干")
        with self.assertRaises(HealthVisionError):
            meal_from_statement(statement, sources, str(uuid4()))

    def test_planned_food_is_not_actual_intake(self):
        statement, sources = self.statement("我准备吃几块饼干")
        with self.assertRaises(HealthVisionError):
            meal_from_statement(statement, sources, str(uuid4()))

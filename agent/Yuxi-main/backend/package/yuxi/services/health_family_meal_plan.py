"""共餐营养从逐人成品份量复算，不默认均分。"""

from decimal import Decimal
from types import SimpleNamespace

from yuxi.services.health_meal_plan_service import calculate_meal_plan
from yuxi.services.health_meal_plan_types import PlannedMeal, PlannedDish
from yuxi.services.health_vision_types import NUTRIENTS


def calculate_family_meal_plan(spec, recipes, portions):
    """逐人只计算参加餐次，家庭汇总不替代个人全天结论。"""
    ids = sorted({str(p) for m in spec.meals for p in m.participant_ids})
    members = {}
    for member_id in ids:
        meals = []
        for meal in spec.meals:
            if member_id not in {str(p) for p in meal.participant_ids}:
                continue
            dishes = [
                PlannedDish(recipe_version_id=d.recipe_version_id, **p.model_dump(exclude={"member_id"}))
                for d in meal.dishes
                for p in d.member_portions
                if str(p.member_id) == member_id
            ]
            meals.append(PlannedMeal(meal_type=meal.meal_type, dishes=dishes))
        calculated = calculate_meal_plan(SimpleNamespace(plan_date=spec.plan_date, meals=meals), recipes, portions)
        for meal in calculated["meals"]:
            original = next(m for m in spec.meals if m.meal_type == meal["meal_type"])
            indexes = [
                index
                for index, dish in enumerate(original.dishes)
                if any(str(p.member_id) == member_id for p in dish.member_portions)
            ]
            for dish, index in zip(meal["dishes"], indexes):
                dish["family_dish_index"] = index
        members[member_id] = {
            "member_id": member_id,
            "covered_meals": [m.meal_type for m in meals],
            "full_day_covered": len(meals) == 3,
            "meals": calculated["meals"],
            "nutrition": {**calculated["nutrition"], "calculation_version": "family-covered-meals-v1"},
        }
    family_meals = []
    for meal in spec.meals:
        allocated = [
            next(m for m in members[str(p)]["meals"] if m["meal_type"] == meal.meal_type) for p in meal.participant_ids
        ]
        totals = sum_nutrients([m["nutrition"]["totals"] for m in allocated])
        family_meals.append(
            {
                "meal_type": meal.meal_type,
                "participant_ids": [str(p) for p in meal.participant_ids],
                "nutrition": {
                    "totals": totals,
                    "units": NUTRIENTS,
                    "complete": all(v is not None for v in totals.values()),
                },
            }
        )
    totals = sum_nutrients([m["nutrition"]["totals"] for m in members.values()])
    return {
        "status": "draft",
        "scope": "family_recipe_draft",
        "personalized": False,
        "plan_date": spec.plan_date.isoformat(),
        "meals": family_meals,
        "members": members,
        "nutrition": {
            "totals": totals,
            "units": NUTRIENTS,
            "complete": all(v is not None for v in totals.values()),
            "estimated": True,
            "calculation_version": "family-covered-meals-v1",
        },
        "professional_review": "not_reviewed",
        "adoption_available": False,
        "purchase_available": False,
        "notice": "按各成员明确计划份量复算；个人覆盖餐次另列，家庭总量不是个人全天营养目标或实际摄入。",
    }


def sum_nutrients(values):
    """任一参与份量未知时保持对应汇总未知。"""
    return {
        code: None if any(v[code] is None for v in values) else str(sum((Decimal(v[code]) for v in values), Decimal(0)))
        for code in NUTRIENTS
    }

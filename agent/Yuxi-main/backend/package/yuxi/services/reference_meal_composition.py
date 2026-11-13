"""本餐人数和已核对原谱共同决定参考餐单是否配齐。"""

from datetime import date

from yuxi.services.health_vision_types import HealthVisionError
from yuxi.services.reference_recipe_matching import ingredient_food, optional_reference_ingredient

REFERENCE_MEAL_POLICY_VERSION = 1
MAX_REFERENCE_DISHES = 10
MEAL_NAMES = {"breakfast": "早餐", "lunch": "午餐", "dinner": "晚餐"}

FOOD_GROUPS = {
    "staple": {"大米", "红薯", "土豆", "燕麦"},
    "protein": {"鸡蛋", "豆腐", "鸡肉", "鸡胸肉", "牛肉", "猪肉", "三文鱼", "鳕鱼", "牛奶", "鹰嘴豆"},
    "vegetable": {
        "番茄",
        "菠菜",
        "西兰花",
        "花菜",
        "胡萝卜",
        "西葫芦",
        "黄瓜",
        "圆白菜",
        "大白菜",
        "蘑菇",
        "香菇",
        "金针菇",
        "茄子",
        "彩椒",
        "芦笋",
        "西芹",
        "生菜",
    },
}
GROUP_NAMES = {"staple": "主食", "protein": "蛋白质类食物", "vegetable": "蔬菜"}
SEASONINGS = {"水", "盐", "糖", "橄榄油", "黑胡椒", "姜", "大蒜"}


def reference_meal_targets(selection):
    """从授权名单计算每餐共用菜数，显式要求优先。"""
    count = len(selection["participant_ids"])
    requested = selection.get("requested_dish_count")
    simple = selection.get("simple_meal") and count == 1
    result = {}
    for meal_type in selection["meal_types"]:
        breakfast = meal_type == "breakfast"
        if requested is not None:
            lower = upper = requested
        elif simple:
            lower = upper = 1
        elif breakfast:
            lower, upper = (2, 2) if count <= 2 else (3, 3) if count <= 4 else (3, 4)
        else:
            lower = upper = count + 1 if count <= 2 else 4 if count <= 4 else 5
        result[meal_type] = {
            "shared_min": lower,
            "shared_max": upper,
            "food_groups": ["staple", "protein"] if breakfast else ["staple", "protein", "vegetable"],
        }
    return result


def meal_age_band(birth_date, plan_date):
    """仅向配餐模型提供已授权出生日期对应的年龄段。"""
    if not birth_date:
        return None
    try:
        born, day = date.fromisoformat(birth_date), date.fromisoformat(plan_date)
    except (TypeError, ValueError):
        return None
    age = day.year - born.year - ((day.month, day.day) < (born.month, born.day))
    if age < 0:
        return None
    return next(
        band
        for limit, band in (
            (3, "0–2岁"),
            (6, "3–5岁"),
            (12, "6–11岁"),
            (18, "12–17岁"),
            (65, "18–64岁"),
            (float("inf"), "65岁及以上"),
        )
        if age < limit
    )


def validate_reference_meal_composition(meals, selection):
    """拒绝重复、少配及成员实际可吃搭配缺项的整餐。"""
    targets = reference_meal_targets(selection)
    diners = set(selection["participant_ids"])
    for meal in meals:
        target = targets[meal["meal_type"]]
        name = MEAL_NAMES[meal["meal_type"]]
        shared = {dish["file_id"]: dish for dish in meal["dishes"] if not dish.get("alternative_for")}
        alternatives = [dish for dish in meal["dishes"] if dish.get("alternative_for")]
        recipes = meal["dishes"]
        names = ["".join(dish["name"].casefold().split()) for dish in recipes if dish.get("name")]
        if len({dish["file_id"] for dish in recipes}) != len(recipes) or len(set(names)) != len(names):
            raise HealthVisionError("reference_meal_incomplete", f"{name}含重复菜谱，请选择不同的菜品")
        if any(all(ingredient_food(item) in SEASONINGS for item in dish["ingredients"]) for dish in recipes):
            raise HealthVisionError("reference_meal_incomplete", f"{name}的调味料不能单独作为一道菜，请补查菜品")
        lower, upper = target["shared_min"], target["shared_max"]
        if not lower <= len(shared) <= upper:
            expected = str(lower) if lower == upper else f"{lower}–{upper}"
            raise HealthVisionError(
                "reference_meal_incomplete", f"{name}需安排{expected}道共用菜，目前{len(shared)}道。请补查或调整菜品"
            )

        served = {member_id: dict(shared) for member_id in diners}
        for dish in alternatives:
            replaced = dish.get("replaces_file_id")
            members = set(dish["alternative_for"])
            if not members < diners or replaced not in shared or any(replaced not in served[mid] for mid in members):
                raise HealthVisionError(
                    "reference_meal_incomplete",
                    f"{name}替代菜须对应一道共用菜和本餐部分就餐成员，同一成员同一道菜只替代一次",
                )
            for mid in members:
                del served[mid][replaced]
                served[mid][dish["file_id"]] = dish

        if not shared.keys() <= set().union(*(member_dishes.keys() for member_dishes in served.values())):
            raise HealthVisionError("reference_meal_incomplete", f"{name}有共用菜未分配给任何成员，请调整替代菜")

        required = set(target["food_groups"])
        groups_by_recipe = {dish["file_id"]: recipe_food_groups(dish["ingredients"]) for dish in meal["dishes"]}
        for member_id in selection["participant_ids"]:
            groups = set().union(*(groups_by_recipe[key] for key in served[member_id]))
            if missing := required - groups:
                labels = "、".join(GROUP_NAMES[key] for key in sorted(missing))
                raise HealthVisionError(
                    "reference_meal_incomplete", f"{name}有就餐成员的搭配缺少可核对的{labels}，请调整共用菜或替代菜"
                )


def recipe_food_groups(ingredients):
    """根据可识别的原谱食材归类，未知食材不充当搭配证据。"""
    foods = {ingredient_food(ingredient) for ingredient in ingredients if not optional_reference_ingredient(ingredient)}
    return {group for group, supported in FOOD_GROUPS.items() if foods & supported}

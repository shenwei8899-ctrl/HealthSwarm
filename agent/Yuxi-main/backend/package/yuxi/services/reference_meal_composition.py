"""本餐人数和已核对原谱共同决定参考餐单是否配齐。"""

import re
from unicodedata import normalize
from datetime import date

from yuxi.services.health_vision_types import HealthVisionError
from yuxi.services.reference_recipe_matching import ingredient_food, optional_reference_ingredient

FOOD_GROUP_MEAL_POLICY_VERSION = 1
REFERENCE_MEAL_POLICY_VERSION = 2
BATCH_REFERENCE_MEAL_POLICY_VERSIONS = frozenset({FOOD_GROUP_MEAL_POLICY_VERSION, REFERENCE_MEAL_POLICY_VERSION})
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


# 这些词用于搭配归类。商品匹配继续核对具体品种、加工形态和原文。
_CHINESE_STAPLE = re.compile(
    r"^(?:白米|白[飯饭]|糙米|蓬[萊莱]米|小米(?!辣)|燕[麥麦](?:片)?|"
    r"[烏乌][龍龙][麵面]|[麵面][條条]|[馬马][鈴铃]薯|地瓜|[紅红]薯|"
    r"[十五]穀[飯饭]|[十五]谷[飯饭])(?=$|[\s\d（(:：]|適量|适量|少許|少许)"
)
_INGREDIENT_PREFIX = re.compile(r"^(?:材料[｜|]\s*|[A-Za-z][.．、]\s*)")
_PLAIN_STAPLE_NAME = re.compile(
    r"(?:清水煮|清煮|白煮|蒸|煮)?(?:白米?[飯饭]|米[飯饭]|糙米[飯饭]|"
    r"[五十][榖穀谷][飯饭]|[雜杂][糧粮][飯饭]|[清白米]粥|小米粥|白(?:米)?稀[飯饭])"
    r"|(?:清水煮|清煮|白煮|蒸|煮)(?:白米|大米|糙米|[雜杂][糧粮]米?)"
)
_PLAIN_GRAIN = re.compile(
    r"(?:白米|蓬[萊莱]米|糙米|小米|粳米|[糯稻]米|黑米|紫米|"
    r"(?:[五十][榖穀谷]|[雜杂][糧粮])米?|燕[麥麦])"
    r"(?:\s*[:：]?\s*[\d./一二兩两三四五六七八九十半]+\s*(?:克|公克|公斤|毫升|杯|碗|[gG]|[kK][gG])?\s*)?"
    r"|(?:白米|米)及水的比例[為为]?\s*\d+(?:\.\d+)?\s*:\s*\d+(?:\.\d+)?"
)


def reference_meal_targets(selection, *, policy_version=REFERENCE_MEAL_POLICY_VERSION):
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
        }
        if policy_version == FOOD_GROUP_MEAL_POLICY_VERSION:
            result[meal_type]["food_groups"] = ["staple", "protein"]
            if not breakfast:
                result[meal_type]["food_groups"].append("vegetable")
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


def validate_reference_meal_composition(meals, selection, *, policy_version=REFERENCE_MEAL_POLICY_VERSION):
    """按任务绑定的规则核对菜品、道数和替代。"""
    targets = reference_meal_targets(selection, policy_version=policy_version)
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
        if policy_version == REFERENCE_MEAL_POLICY_VERSION:
            for dish in recipes:
                validate_reference_dish(dish.get("name", ""), dish["ingredients"])
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

        required = set(target.get("food_groups", ()))
        if not required:
            continue
        groups_by_recipe = {dish["file_id"]: recipe_food_groups(dish["ingredients"]) for dish in meal["dishes"]}
        for member_id in selection["participant_ids"]:
            groups = set().union(*(groups_by_recipe[key] for key in served[member_id]))
            if missing := required - groups:
                labels = "、".join(GROUP_NAMES[key] for key in sorted(missing))
                raise HealthVisionError(
                    "reference_meal_incomplete", f"{name}有就餐成员的搭配缺少可核对的{labels}，请调整共用菜或替代菜"
                )


def validate_reference_dish(name, ingredients):
    """拦截占用一道菜名额的单独基础主食。"""
    if is_plain_reference_staple(name, ingredients):
        raise HealthVisionError("reference_meal_incomplete", f"「{name}」由用户自行准备，请换一道菜谱")


def is_plain_reference_staple(name, ingredients):
    """菜名和原料均指向单独米饭或白粥时才排除。"""
    title = normalize("NFKC", "".join(name.split()))
    if not _PLAIN_STAPLE_NAME.fullmatch(title):
        return False
    foods = [
        normalize("NFKC", _INGREDIENT_PREFIX.sub("", item.strip()))
        for item in ingredients
        if ingredient_food(item) not in {"水", "盐"}
    ]
    if not foods:
        return False
    return all(ingredient_food(food) == "大米" or _PLAIN_GRAIN.fullmatch(food) for food in foods)


def recipe_food_groups(ingredients):
    """根据可识别的原谱食材归类，未知食材不充当搭配证据。"""
    required = [ingredient for ingredient in ingredients if not optional_reference_ingredient(ingredient)]
    foods = {ingredient_food(ingredient) for ingredient in required}
    groups = {group for group, supported in FOOD_GROUPS.items() if foods & supported}
    if any(_CHINESE_STAPLE.match(_INGREDIENT_PREFIX.sub("", ingredient.strip())) for ingredient in required):
        groups.add("staple")
    return groups

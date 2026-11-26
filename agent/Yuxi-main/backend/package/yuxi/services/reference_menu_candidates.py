"""从已授权且可解析的原谱组装共用菜候选。"""

from heapq import nlargest
from itertools import combinations, islice, product

from yuxi.services.health_vision_types import HealthVisionError
from yuxi.services.reference_meal_composition import (
    GROUP_NAMES,
    MEAL_NAMES,
    REFERENCE_MEAL_POLICY_VERSION,
    reference_meal_targets,
)
from yuxi.services.reference_recipe_variety import balanced_candidates, dish_keys, validate_variety

MAX_REFERENCE_SEARCHES = 2
_MENU_OPTIONS = 3
_MEAL_OPTIONS = 32
_COMBINATION_BUDGET = 12000


def reference_menu_options(
    ranked,
    selection,
    history,
    current_menus,
    actor_uid,
    *,
    policy_version=REFERENCE_MEAL_POLICY_VERSION,
):
    """返回符合本次道数及去重要求的组合，或具体餐次缺口。"""
    pool = [item for item in balanced_candidates(ranked, limit=sum(map(len, ranked))) if not item["seasoning_only"]]
    targets = reference_meal_targets(selection, policy_version=policy_version)
    by_meal = {}
    gaps = []
    total_groups = set().union(*(set(item["food_groups"]) for item in pool))
    distinct = {}
    for item in pool:
        name_key = next((key for key in dish_keys(item) if key.startswith("name:")), item["file_id"])
        distinct.setdefault(name_key, item)
    choices_by_count = {}
    for meal, target in targets.items():
        required = set(target.get("food_groups", ()))
        missing = sorted(required - total_groups)
        if required:
            choices = [] if missing else list(islice(_meal_combinations(pool, target, required), _MEAL_OPTIONS))
            if not choices:
                gaps.append(
                    {
                        "meal_type": meal,
                        "missing_groups": missing,
                        "reason": "food_groups" if missing else "combination",
                    }
                )
        else:
            count = target["shared_min"]
            if count not in choices_by_count:
                choices_by_count[count] = _rank_meal_combinations(list(distinct.values()), count)
            choices = choices_by_count[count]
            if not choices:
                gaps.append({"meal_type": meal, "reason": "dish_count", "missing_count": count - len(distinct)})
        by_meal[meal] = choices

    menus = []
    if not gaps:
        products = list(islice(product(*by_meal.values()), _COMBINATION_BUDGET))
        products.sort(key=lambda picked: -len({dish["file_id"] for meal in picked for dish in meal}))
        for picked in products:
            meals = [{"meal_type": meal, "dishes": list(dishes)} for meal, dishes in zip(by_meal, picked, strict=True)]
            try:
                validate_variety(history, selection, meals, current_menus=current_menus, actor_uid=actor_uid)
            except HealthVisionError as error:
                if error.code not in {"reference_recipe_repeated", "reference_menu_repeated"}:
                    raise
                continue
            menus.append(meals)
            if len(menus) == _MENU_OPTIONS:
                break
        if not menus:
            gaps = [{"meal_type": meal, "missing_groups": [], "reason": "variety"} for meal in targets]
    ids = {dish["file_id"] for menu in menus for meal in menu for dish in meal["dishes"]}
    return {
        "items": [item for item in pool if item["file_id"] in ids],
        "menus": [
            [
                {
                    "meal_type": meal["meal_type"],
                    "dishes": [
                        {key: dish[key] for key in ("file_id", "chunk_id", "name", "food_groups")}
                        for dish in meal["dishes"]
                    ],
                }
                for meal in menu
            ]
            for menu in menus
        ],
        "coverage_gaps": gaps,
    }


def _rank_meal_combinations(pool, count):
    """从排在前面的菜开始试配，食物组仅用于排序。"""
    positions = {dish["file_id"]: index for index, dish in enumerate(pool)}

    def score(dishes):
        groups = set().union(*(set(dish["food_groups"]) for dish in dishes))
        return len(groups) - sum(positions[dish["file_id"]] for dish in dishes)

    # 按组合中最后一道菜的排名逐步扩展，避免搜索预算全花在首选菜上。
    choices = ((*head, dish) for index, dish in enumerate(pool) for head in combinations(pool[:index], count - 1))
    return nlargest(_MEAL_OPTIONS, islice(choices, _COMBINATION_BUDGET), key=score)


def _meal_combinations(pool, target, required):
    """先覆盖所需食物组，再补足共用菜道数。"""
    cores = [item for item in pool if required.intersection(item["food_groups"])]
    checks = 0
    seen = set()
    keys_by_file = {item["file_id"]: dish_keys(item) for item in pool}
    for size in range(1, min(len(required), target["shared_max"]) + 1):
        for core in combinations(cores, size):
            checks += 1
            if checks > _COMBINATION_BUDGET:
                return
            if not required <= set().union(*(set(dish["food_groups"]) for dish in core)):
                continue
            core_keys = [keys_by_file[dish["file_id"]] for dish in core]
            keys = set().union(*core_keys)
            if sum(map(len, core_keys)) != len(keys):
                continue
            fill = [item for item in pool if not keys_by_file[item["file_id"]] & keys]
            for extra in combinations(fill, max(0, target["shared_min"] - size)):
                checks += 1
                if checks > _COMBINATION_BUDGET:
                    return
                extra_keys = [keys_by_file[dish["file_id"]] for dish in extra]
                if len(set().union(*extra_keys)) != sum(map(len, extra_keys)):
                    continue
                choice = (*core, *extra)
                identity = frozenset(dish["file_id"] for dish in choice)
                if identity not in seen:
                    seen.add(identity)
                    yield choice


def reference_coverage_message(gaps):
    """把结构化缺项投影为用户可见的固定文案。"""
    messages = []
    for gap in gaps:
        name = MEAL_NAMES[gap["meal_type"]]
        if gap["reason"] == "food_groups":
            missing = "、".join(GROUP_NAMES[group] for group in gap["missing_groups"])
            messages.append(f"{name}缺少可核对的{missing}菜谱")
        elif gap["reason"] == "combination":
            messages.append(f"{name}未找到同时满足道数和搭配要求的组合")
        elif gap["reason"] == "dish_count":
            messages.append(f"{name}还缺{gap['missing_count']}道可核对的不同菜品")
        elif gap["reason"] == "market_supply":
            ingredients = "、".join(gap.get("missing_ingredients", []))
            detail = f"；例如以下食材没有确认有货的匹配：{ingredients}" if ingredients else ""
            messages.append(f"{name}未找到能从商城买齐必需食材且符合要求的搭配{detail}；可换菜或选择自备")
    if gaps and not messages:
        return "所选餐次未找到符合近期去重要求的组合。"
    return "；".join(messages) + "。" if messages else "未能完成餐单，请重新安排。"

"""家庭历史、已读偏好和公共菜品曝光参与参考选菜，保存再次验重。"""

import re
import unicodedata
from hashlib import sha256
from collections import Counter
from datetime import date

from yuxi.services.health_vision_types import HealthVisionError


def dish_keys(dish):
    """来源身份和规范菜名同时识别重复，不依赖模型改写的中文译名。"""
    name = re.sub(r"[\W_]+", "", unicodedata.normalize("NFKC", dish.get("name", "")).casefold())
    file_id = (dish.get("source") or {}).get("file_id") or dish.get("file_id")
    return ({"name:" + name} if name else set()) | ({"file:" + str(file_id)} if file_id else set())


def variety_context(history, selection, members=()):
    """同家庭跨账号邻日排除，十四天重复与公共曝光降权。"""
    day = date.fromisoformat(selection["plan_date"])
    excluded, recent, popular = set(), Counter(), Counter()
    for family, saved_day, meals in history:
        age = (day - date.fromisoformat(saved_day)).days
        keys = set().union(*(dish_keys(d) for m in meals for d in m.get("dishes", [])))
        popular.update(keys)
        if family == selection["family_id"]:
            if abs(age) <= 1:
                excluded.update(keys)
            elif 1 < age <= 14:
                recent.update(keys)
    preferences = []
    for member in members:
        dietary = member.get("dietary") or {}
        for field in ("cuisines", "flavors", "tastePreferences"):
            preferences.extend(str(value) for value in dietary.get(field, []) if value)
    return {"excluded": excluded, "recent": recent, "popular": popular, "preferences": preferences,
            "seed": f"{selection['family_id']}:{selection['plan_date']}"}


def candidate_priority(keys, content, variety):
    """合格相关候选先尊重偏好，再减少近期与公共重复。"""
    if not variety:
        return ()
    text = content.casefold()
    preference = sum(word.casefold() in text for word in variety["preferences"])
    # 只用于口味排序，不声明医学适用性，也不改写原谱食材。
    if any("清淡" in word for word in variety["preferences"]):
        preference += bool(re.search(r"清蒸|水煮|白灼|\b(?:steam\w*|poach\w*|boil\w*)\b", text))
        preference -= bool(re.search(r"油炸|油煎|\bdeep[- ]fr\w*\b", text))
    if any(re.fullmatch(r"(?:微辣|中辣|重辣|特辣|香辣|麻辣|辣)", word.strip()) for word in variety["preferences"]):
        preference += bool(re.search(r"辣椒|\b(?:chill?i|spicy|sichuan|szechuan)\b", text))
    return (
        preference,
        -max((variety["recent"][key] for key in keys), default=0),
        -max((variety["popular"][key] for key in keys), default=0),
    )


def candidate_rotation(keys, variety):
    """同等候选按家庭和日期稳定打散，重试不抽签且不共享最终餐单。"""
    if not variety or not variety.get("seed"):
        return 0
    value = variety["seed"] + ":" + ":".join(sorted(keys))
    return int.from_bytes(sha256(value.encode()).digest()[:8], "big")


def balanced_candidates(ranked, limit=24):
    """轮流取各关键词的命中，第四类食材不会被前面候选截断。"""
    result, seen = [], set()
    for position in range(max(map(len, ranked), default=0)):
        for matches in ranked:
            if position >= len(matches):
                continue
            item = matches[position]
            if item["file_id"] in seen:
                continue
            result.append(item)
            seen.add(item["file_id"])
            if len(result) == limit:
                return result
    return result


def validate_variety(history, selection, meals, *, current_menus=(), actor_uid=None):
    """邻日单菜、家庭十四天整套、跨家庭同日整套验重；分餐按当前账号合并。"""
    policy = variety_context(history, selection)
    if any(dish_keys(d) & policy["excluded"] for m in meals for d in m["dishes"]):
        raise HealthVisionError(
            "reference_recipe_repeated", "所选菜品在本家庭当天或相邻日期已安排，请检索其他菜谱", 422
        )
    own = {}
    if actor_uid is not None:
        own = next(
            (
                {m["meal_type"]: m for m in saved}
                for family, actor, saved in current_menus
                if family == selection["family_id"] and actor == actor_uid
            ),
            {},
        )
    own.update({meal["meal_type"]: meal for meal in meals})
    if set(own) != {"breakfast", "lunch", "dinner"}:
        return
    alternatives = [
        {m["meal_type"]: m for m in saved} for family, actor, saved in current_menus if family != selection["family_id"]
    ]
    # 保存成功但尚未发布的完整预览作为保留组合，避免并发生成穿过发布间隙。
    alternatives.extend(
        {m["meal_type"]: m for m in saved}
        for family, day, saved in history
        if day == selection["plan_date"] or family == selection["family_id"]
    )
    for other in alternatives:
        if set(other) != set(own):
            continue
        if any(menu_signature(own, kind) == menu_signature(other, kind) for kind in ("name:", "file:")):
            raise HealthVisionError("reference_menu_repeated", "本次三餐组合重复，请从合格候选中更换菜品后保存", 422)


def menu_signature(meals, kind):
    """忽略菜品排列和餐次交换，避免同一套菜仅换位置。"""
    return tuple(
        sorted(
            key for meal in meals.values() for dish in meal["dishes"] for key in dish_keys(dish) if key.startswith(kind)
        )
    )

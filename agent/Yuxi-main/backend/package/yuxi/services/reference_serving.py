"""核对参考餐单的逐成员备菜分配和熟食份量建议。"""

from decimal import Decimal
from copy import deepcopy

from yuxi.services.health_vision_types import HealthVisionError


def checked_member_servings(suggestion, diners, member_names, *, required=False, ingredient_labels=()):
    """只接受实际就餐成员，并逐项核对分配与家庭备菜总量。"""
    people = suggestion.members if suggestion else []
    if not people:
        if required:
            raise HealthVisionError("reference_amounts_invalid", "请为本菜每位就餐成员规划份量", 422)
        return []
    if {str(person.member_id) for person in people} != set(diners):
        raise HealthVisionError("reference_amounts_invalid", "成员份量须与本菜实际就餐成员一致", 422)
    totals = {item.position: item for item in suggestion.ingredient_amounts}
    allocated = {position: Decimal(0) for position in totals}
    for person in people:
        for item in person.ingredient_amounts:
            total = totals.get(item.position)
            if total is None or item.unit != total.unit:
                raise HealthVisionError("reference_amounts_invalid", "个人食材用量须对应家庭备菜项目及相同单位", 422)
            allocated[item.position] += Decimal(str(item.amount))
    if any(abs(allocated[pos] - Decimal(str(item.amount))) > Decimal("0.001") for pos, item in totals.items()):
        raise HealthVisionError("reference_amounts_invalid", "成员食材分配合计须等于本菜备菜总量", 422)
    return [
        {
            "member_id": str(person.member_id),
            "name": member_names[str(person.member_id)],
            "cooked_grams": person.cooked_grams,
            "description": (
                "备菜原料分配："
                + "；".join(
                    f"〔{ingredient_labels[item.position]}〕分配{item.amount:g}{item.unit}"
                    for item in person.ingredient_amounts
                    if item.position < len(ingredient_labels)
                )
                if ingredient_labels
                else f"按重量分取熟食约{person.cooked_grams:g}克。"
            ),
            "ingredient_amounts": [item.model_dump() for item in person.ingredient_amounts],
            "basis": "cooked_edible",
            "source": "model_estimate",
        }
        for person in people
    ]


def public_serving_suggestion(value):
    """共享菜谱只保留分餐事实，不传播可能夹带健康信息的模型自由描述。"""
    result = deepcopy(value)
    if result:
        for person in result.get("members", []):
            person.pop("description", None)
    return result

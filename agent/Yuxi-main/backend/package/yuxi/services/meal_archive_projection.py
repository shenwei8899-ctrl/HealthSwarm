"""餐单归档只保存共餐展示字段，不复制个人健康档案和采购凭据。"""

from copy import deepcopy

from yuxi.services.recipe_image_identity import recipe_image_key


def archive_meal(meal, members=()):
    """从成功餐次提取可供家庭查看的菜谱和成员姓名。"""
    dish_fields = {
        "serving_suggestion",
        "member_servings",
        "portion_note",
        "nutrition_total",
        "nutrition_status",
        "nutrition_reference",
        "id",
        "recipe_ref",
        "recipeVersion",
        "name",
        "display_name",
        "display_zh",
        "translation_status",
        "ingredients",
        "steps",
        "nutrition",
        "nutritionSource",
        "portion_quote",
        "nutrition_quote",
        "cooking_minutes",
        "image_url",
        "image_source",
        "step_images",
        "cover",
        "file_id",
        "chunk_id",
        "recipe_image_key",
    }
    kind = meal.get("meal_type", meal.get("type"))
    dishes = []
    for dish in meal.get("dishes", []):
        saved = {key: deepcopy(value) for key, value in dish.items() if key in dish_fields}
        if saved.get("serving_suggestion"):
            from yuxi.services.reference_serving import public_serving_suggestion

            saved["serving_suggestion"] = public_serving_suggestion(saved["serving_suggestion"])
        source = dish.get("source") or {}
        if all(source.get(key) for key in ("kb_id", "file_id", "file_hash")):
            saved["recipe_image_key"] = recipe_image_key(dish)
        dishes.append(saved)
    return {
        "meal_type": kind,
        "members": [
            {"id": person["id"], "name": person.get("name", "共餐成员")} for person in meal.get("members", members)
        ],
        "dishes": dishes,
    }


def merge_archive(row, meals, members=()):
    """同一事务仅替换成功的餐次，保留其他最新成功内容。"""
    saved = dict(row.archive_meals or {})
    for meal in meals:
        projected = archive_meal(meal, members)
        saved[projected["meal_type"]] = projected
    row.archive_meals = saved

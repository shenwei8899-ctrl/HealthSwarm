"""由明确绑定的已发布配方和食品数据计算参考餐单营养。"""

from decimal import Decimal

from yuxi.repositories.health_source_repository import HealthSourceRepository
from yuxi.repositories.reference_recipe_catalog_repository import catalog_nutrition_recipe, catalog_nutrition_foods
from yuxi.services.health_nutrition_service import recipe_nutrients


async def attach_reference_nutrition(session, meals, documents):
    """配方按目录编号和正文指纹绑定；缺少任何对应原料时保持未核算。"""
    for meal in meals:
        for dish in meal["dishes"]:
            document = documents[dish["file_id"], dish["chunk_id"]]
            if not document.get("recipe_id") or not dish.get("member_servings"):
                continue
            recipe = await catalog_nutrition_recipe(session, document["recipe_id"], document["file_hash"])
            if recipe is None or len(recipe.ingredients) != len(dish["ingredients"]):
                continue
            ids = [item.get("food", {}).get("id") for item in recipe.ingredients]
            if not all(ids):
                continue
            foods = await catalog_nutrition_foods(session, ids)
            if set(ids) != set(foods):
                continue
            sources = [recipe.source, *(food.source for food in foods.values())]
            if not all((await HealthSourceRepository(session).current_sources(sources)).values()):
                continue
            result = calculate_reference_nutrition(dish, [foods[fid] for fid in ids])
            if result is None:
                continue
            per100, total, people = result
            if not any(isinstance(value, (int, float)) for value in total.values()):
                continue
            dish.update(
                nutrition=per100,
                nutrition_total=total,
                nutrition_status="calculated",
                nutrition_reference={"recipe_version_id": recipe.id, "dataset_version": recipe.dataset_version},
            )
            for person, nutrients in zip(dish["member_servings"], people):
                person["nutrition"] = nutrients


def calculate_reference_nutrition(dish, foods):
    """只计算有完整克数分配的原料；缺失营养保留空值，单位不作猜测。"""
    people = dish["member_servings"]
    amounts = dish["serving_suggestion"]["ingredient_amounts"]
    if {item["position"] for item in amounts} != set(range(len(foods))):
        return None
    if any(item["unit"] != "克" for item in amounts):
        return None
    ingredients = [
        {"food": {"nutrients": foods[item["position"]].nutrients}, "grams": str(item["amount"])} for item in amounts
    ]
    cooked = sum(Decimal(str(person["cooked_grams"])) for person in people)
    per100 = recipe_nutrients(ingredients, cooked)
    totals = recipe_nutrients(ingredients, Decimal(100))
    allocated = [
        recipe_nutrients(
            [
                {"food": {"nutrients": foods[item["position"]].nutrients}, "grams": str(item["amount"])}
                for item in person["ingredient_amounts"]
            ],
            Decimal(100),
        )
        for person in people
    ]
    names = {
        "energy_kcal": "energyKcal",
        "protein_g": "proteinG",
        "fat_g": "fatG",
        "carbohydrate_g": "carbohydrateG",
        "sodium_mg": "sodiumMg",
    }

    def display(values):
        return {
            **{target: float(values[code]) if values.get(code) is not None else None for code, target in names.items()},
            "fiberG": None,
        }

    metadata = {
        "basis": "per_100g",
        "foodState": "recipe_edible",
        "cookingStateLabel": "按建议成品重量估算",
        "source": "calculated",
        "sourceReference": "已发布食品数据；成品份量为建议估算",
    }
    return (
        {**metadata, **display(per100)},
        {"basis": "whole_dish", **display(totals)},
        [{"basis": "per_serving", **display(values)} for values in allocated],
    )

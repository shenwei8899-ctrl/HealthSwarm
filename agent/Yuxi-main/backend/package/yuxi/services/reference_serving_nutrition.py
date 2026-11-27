"""由已发布的原食谱用量和食品数据计算整道菜营养。"""

from decimal import Decimal

from yuxi.repositories.health_source_repository import HealthSourceRepository
from yuxi.repositories.reference_recipe_catalog_repository import catalog_nutrition_recipe, catalog_nutrition_foods
from yuxi.services.health_nutrition_service import recipe_nutrients


async def attach_reference_nutrition(session, meals, documents):
    """配方按目录编号和正文指纹绑定；缺少任何对应原料时保持未核算。"""
    for meal in meals:
        for dish in meal["dishes"]:
            document = documents[dish["file_id"], dish["chunk_id"]]
            if not document.get("recipe_id"):
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
            total = calculate_reference_nutrition(recipe, foods)
            if total is None:
                continue
            if not any(isinstance(value, (int, float)) for value in total.values()):
                continue
            dish.update(
                nutrition_total=total,
                nutrition_status="calculated",
                nutrition_reference={"recipe_version_id": recipe.id, "dataset_version": recipe.dataset_version},
            )


def calculate_reference_nutrition(recipe, foods):
    """原食谱克数决定整道菜总量，计划分餐和熟重不参与缩放。"""
    if not recipe.ingredients or any(item.get("grams") is None for item in recipe.ingredients):
        return None
    ingredients = [
        {"food": {"nutrients": foods[item["food"]["id"]].nutrients}, "grams": item["grams"]}
        for item in recipe.ingredients
    ]
    totals = recipe_nutrients(ingredients, Decimal(100))
    names = {
        "energy_kcal": "energyKcal",
        "protein_g": "proteinG",
        "fat_g": "fatG",
        "carbohydrate_g": "carbohydrateG",
        "sodium_mg": "sodiumMg",
    }

    return {
        "basis": "whole_dish",
        "quantity_basis": "source_recipe",
        **{target: float(totals[code]) if totals.get(code) is not None else None for code, target in names.items()},
        "fiberG": None,
    }

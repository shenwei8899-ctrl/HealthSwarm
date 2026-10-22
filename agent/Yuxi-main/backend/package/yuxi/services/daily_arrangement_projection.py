"""从同一保存版本装配菜单、逐人份量、营养依据与采购需求。"""

from collections import defaultdict
from decimal import Decimal

from sqlalchemy import select

from yuxi.services.daily_commerce_service import current_catalog, match_meal_requirements
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.storage.postgres.models_health import (
    HealthRecipeCommerceSource,
    RecipeVersion,
    HealthPublishedRecipeClassification,
)
from yuxi.storage.postgres.manager import pg_manager
from yuxi.repositories.health_quality_repository import HealthQualityRepository


async def save_recipe_commerce_source(uid, rid, data):
    """发布准确配方版本的不可变步骤和食材映射。"""
    async with pg_manager.get_async_session_context() as db:
        recipe = await db.get(RecipeVersion, rid)
        if recipe is None:
            raise HealthVisionError("recipe_not_found", "菜谱版本不存在", 404)
        _, hashes = await HealthQualityRepository(db).recipe_sources_by_recipe({rid})
        codes = {str(key): value for key, value in data.ingredient_codes.items()}
        if (
            hashes.get(rid) != data.recipe_hash
            or set(codes) != {item["food"]["id"] for item in recipe.ingredients}
            or any(not value.strip() or len(value) > 100 for value in codes.values())
            or any(not step.strip() or len(step) > 2000 for step in data.steps)
        ):
            raise HealthVisionError("recipe_source_invalid", "步骤、配料映射或配方版本不一致", 422)
        row = await db.get(HealthRecipeCommerceSource, rid)
        if row is not None:
            if (
                row.recipe_hash != data.recipe_hash
                or row.steps != data.steps
                or row.ingredient_codes != codes
                or row.source_ref != data.source_ref
            ):
                raise HealthVisionError(
                    "recipe_source_immutable", "已发布做法和食材映射不能覆盖，请创建新的菜谱版本", 409
                )
            await publish_recipe_classification(db, uid, rid, data)
            return {"saved": True, "recipe_version_id": rid}
        if row is None:
            row = HealthRecipeCommerceSource(recipe_version_id=rid)
            db.add(row)
        row.recipe_hash, row.steps, row.ingredient_codes, row.source_ref, row.published_by = (
            data.recipe_hash,
            data.steps,
            codes,
            data.source_ref,
            uid,
        )
        await publish_recipe_classification(db, uid, rid, data)
        return {"saved": True, "recipe_version_id": rid}


async def publish_recipe_classification(session, uid, rid, data):
    """管理员以同一配方hash发布不可变分类及来源。"""
    if not data.dish_type_code:
        return
    row = await session.get(HealthPublishedRecipeClassification, rid)
    values = {
        "recipe_hash": data.recipe_hash,
        "dish_type_code": data.dish_type_code,
        "allowed_meal_types": sorted(data.allowed_meal_types),
        "source_ref": data.source_ref,
    }
    if row is not None:
        if any(getattr(row, key) != value for key, value in values.items()):
            raise HealthVisionError("recipe_classification_immutable", "已发布配方分类不能覆盖，请创建新版本", 409)
    else:
        session.add(HealthPublishedRecipeClassification(recipe_version_id=rid, published_by=uid, **values))


async def purchase_catalog(session, recipes, hashes):
    """只过滤缺少真实步骤/映射的版本，搜索遍历全部已发布批准目录。"""
    mappings = {
        row.recipe_version_id: row
        for row in (
            await session.scalars(
                select(HealthRecipeCommerceSource).where(HealthRecipeCommerceSource.recipe_version_id.in_(recipes))
            )
        ).all()
    }
    usable = {
        rid: recipe
        for rid, recipe in recipes.items()
        if rid in mappings
        and mappings[rid].recipe_hash == hashes.get(rid)
        and mappings[rid].steps
        and all(entry["food"]["id"] in mappings[rid].ingredient_codes for entry in recipe.ingredients)
    }
    catalog = await current_catalog()

    def eligible(snapshot):
        """每餐分别凑整包，再共同扣减库存，与逐餐发布的采购单位一致。"""
        requirements = {
            meal: ingredient_requirements(snapshot, mappings, meal) for meal in ("breakfast", "lunch", "dinner")
        }
        return match_meal_requirements(requirements, catalog) is not None

    return usable, eligible


def allocated_meals(snapshot):
    """个人和家庭快照共用逐人成品量，不能按人数均分。"""
    if snapshot.get("members"):
        return [(mid, meal) for mid, member in snapshot["members"].items() for meal in member["meals"]]
    return [(None, meal) for meal in snapshot["meals"]]


def ingredient_requirements(snapshot, mappings, meal_type=None):
    """按明确映射汇总原料需求；没有映射不能按名称猜配料。"""
    totals = defaultdict(Decimal)
    for _, meal in allocated_meals(snapshot):
        if meal_type and meal["meal_type"] != meal_type:
            continue
        for dish in meal["dishes"]:
            mapping = mappings.get(dish["recipe_version_id"])
            if mapping is None:
                return []
            for ingredient in dish["ingredients"]:
                code = mapping.ingredient_codes.get(ingredient["food_id"])
                if not code or ingredient.get("planned_grams") is None:
                    return []
                totals[code] += Decimal(ingredient["planned_grams"])
    return [
        {"ingredient_id": code, "ingredient_code": code, "required_value": str(value), "required_unit": "g"}
        for code, value in sorted(totals.items())
    ]


def nutrition_view(values):
    """使用确定性结果，未知纤维保留为空。"""
    names = {
        "energy_kcal": "kcal",
        "protein_g": "protein",
        "fat_g": "fat",
        "carbohydrate_g": "carbs",
        "sodium_mg": "sodium",
    }
    return {
        **{label: float(values[key]) if values.get(key) is not None else None for key, label in names.items()},
        "fiber": None,
    }


def meal_views(snapshot, mappings, members, anchor_id, recipes=None):
    """卡片与详情公用同一保存快照，做法与配方版本明确关联。"""
    result = []
    for meal_type in ("breakfast", "lunch", "dinner"):
        allocated = [
            (mid or anchor_id, meal) for mid, meal in allocated_meals(snapshot) if meal["meal_type"] == meal_type
        ]
        if not allocated:
            raise HealthVisionError("daily_incomplete", "三餐尚未全部完成，系统将重新核对", 503)
        dishes, notes, totals = {}, [], defaultdict(Decimal)
        for mid, meal in allocated:
            person = members[mid]
            portions = []
            for dish in meal["dishes"]:
                rid = dish["recipe_version_id"]
                mapping = mappings[rid]
                recipe = (recipes or {}).get(rid)
                nutrients = recipe.nutrients if recipe else {}
                if not mapping.steps or dish["planned_grams"] is None:
                    raise HealthVisionError("daily_incomplete", "菜谱或建议份量尚未完整，系统将重新核对", 503)
                dishes.setdefault(
                    rid,
                    {
                        "id": rid,
                        "recipeVersion": rid,
                        "name": dish["name"],
                        "ingredients": [],
                        "steps": mapping.steps,
                        "nutrition": {
                            "basis": "per_100g",
                            "foodState": "recipe_edible" if recipe else "unknown",
                            "cookingStateLabel": recipe.cooking_state if recipe else None,
                            "energyKcal": float(nutrients["energy_kcal"])
                            if nutrients.get("energy_kcal") is not None
                            else None,
                            "proteinG": float(nutrients["protein_g"])
                            if nutrients.get("protein_g") is not None
                            else None,
                            "fatG": float(nutrients["fat_g"]) if nutrients.get("fat_g") is not None else None,
                            "carbohydrateG": float(nutrients["carbohydrate_g"])
                            if nutrients.get("carbohydrate_g") is not None
                            else None,
                            "sodiumMg": float(nutrients["sodium_mg"])
                            if nutrients.get("sodium_mg") is not None
                            else None,
                            "fiberG": None,
                            "source": "calculated",
                            "sourceReference": recipe.source if recipe else None,
                        },
                        "nutritionSource": {
                            "source": dish["source"],
                            "edition": dish["edition"],
                            "dataset_version": dish["dataset_version"],
                        },
                    },
                )
                for ingredient in dish["ingredients"]:
                    existing = next(
                        (item for item in dishes[rid]["ingredients"] if item["food_id"] == ingredient["food_id"]), None
                    )
                    if existing is None:
                        dishes[rid]["ingredients"].append(dict(ingredient))
                    else:
                        existing["planned_grams"] = str(
                            Decimal(existing["planned_grams"]) + Decimal(ingredient["planned_grams"])
                        )
                portions.append(
                    {
                        "name": dish["name"],
                        "dishId": rid,
                        "grams": float(dish["planned_grams"]),
                        "source": "planned_estimate",
                    }
                )
            values = meal["nutrition"]["totals"]
            if not meal["dishes"] or any(value is None for value in values.values()):
                raise HealthVisionError("daily_incomplete", "本餐营养依据尚未完整，系统将重新核对", 503)
            for key, value in values.items():
                totals[key] += Decimal(value)
            notes.append(
                {
                    "memberId": person["id"],
                    "name": person["name"],
                    "dishes": portions,
                    "nutrition": nutrition_view(values),
                }
            )
        result.append(
            {
                "type": meal_type,
                "detail_ref": meal_type,
                "members": [members[mid] for mid, _ in allocated],
                "dishes": list(dishes.values()),
                "memberNotes": notes,
                "nutrition": nutrition_view(totals),
                "nutritionSource": snapshot.get("generation_origin", {}).get("sources", {}),
            }
        )
    return result

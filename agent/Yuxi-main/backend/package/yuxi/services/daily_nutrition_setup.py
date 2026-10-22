"""管理端配餐来源准备状态与不可变配方映射读取。"""

import os

from sqlalchemy import func, select

from yuxi.repositories.health_quality_repository import HealthQualityRepository
from yuxi.services.health_quality_checks import external_projection
from yuxi.services.health_vision_service import health_vision_service
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_health import (
    FoodRecord,
    RecipeVersion,
    HealthRuleSnapshot,
    HealthRecipeCommerceSource,
    HealthPublishedRecipeClassification,
)


async def daily_setup_readiness():
    """只报告资料和配置是否存在，不将这些状态冒充完整流程验收。"""
    async with pg_manager.get_async_session_context() as session:
        counts = {
            name: int(await session.scalar(select(func.count()).select_from(model)) or 0)
            for name, model in (
                ("foods", FoodRecord),
                ("recipes", RecipeVersion),
                ("rule_versions", HealthRuleSnapshot),
                ("recipe_sources", HealthRecipeCommerceSource),
                ("recipe_classifications", HealthPublishedRecipeClassification),
            )
        }
        config = await health_vision_service.configuration(session)
        rule_code = os.environ.get("HEALTH_DAILY_RULE_CODE", "")
        rule = external_projection(await HealthQualityRepository(session).rules(rule_code), "rules", rule_code)
    return {
        "counts": counts,
        "meal_plan": {key: config["meal_plan"][key] for key in ("available", "reason_code", "model")},
        "policy_configured": bool(config["policy_version"]),
        "rules_ready": rule["status"] == "ready",
        "commerce_configured": bool(os.environ.get("HEALTH_COMMERCE_URL") or os.environ.get("HEALTH_COMMERCE_API_URL"))
        and all(os.environ.get(key) for key in ("HEALTH_COMMERCE_CLIENT_ID", "HEALTH_COMMERCE_CLIENT_SECRET"))
        and len(os.environ.get("HEALTH_COMMERCE_SOURCE_SECRET", "")) >= 32,
        "knowledge_configured": bool(os.environ.get("HEALTH_FAMILY_NUTRITION_KB_ID")),
    }


async def read_recipe_commerce_source(rid):
    """读取准确版本，不按同名菜谱或食材猜测映射。"""
    async with pg_manager.get_async_session_context() as session:
        recipe = await session.get(RecipeVersion, rid)
        if recipe is None:
            raise HealthVisionError("recipe_not_found", "菜谱版本不存在", 404)
        _, refs = await HealthQualityRepository(session).recipe_sources_by_recipe({rid})
        source = await session.get(HealthRecipeCommerceSource, rid)
        classification = await session.get(HealthPublishedRecipeClassification, rid)
        return {
            "recipe_version_id": rid,
            "recipe_hash": refs[rid],
            "name": recipe.name,
            "ingredients": [
                {"food_id": item["food"]["id"], "name": item["food"]["name"]} for item in recipe.ingredients
            ],
            "published": source is not None,
            "source_ref": source.source_ref if source else "",
            "steps": source.steps if source else [],
            "ingredient_codes": source.ingredient_codes if source else {},
            "dish_type_code": classification.dish_type_code if classification else None,
            "allowed_meal_types": classification.allowed_meal_types if classification else [],
        }

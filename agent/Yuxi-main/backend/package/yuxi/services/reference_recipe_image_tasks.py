"""参考餐单成品图的持久后台任务；不阻塞餐单保存。"""

from yuxi.services.health_vision_types import HealthVisionError
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_health import HealthInitialPlanPreview


async def run_reference_recipe_images(context):
    """只读取已提交预览中的菜谱事实，图片缓存失败明确记为任务失败，重试复用已有图片。"""
    preview_id = str(context.payload.get("preview_id") or "")
    if not preview_id:
        raise HealthVisionError("reference_preview_invalid", "菜品图片任务缺少餐单标识", 422)
    async with pg_manager.get_async_session_context() as session:
        preview = await session.get(HealthInitialPlanPreview, preview_id)
        if preview is None or (preview.snapshot or {}).get("scope") != "daily_reference":
            raise HealthVisionError("reference_preview_missing", "菜品图片任务对应的餐单不存在", 410)
        meals = (preview.snapshot or {}).get("meals") or []
    from yuxi.services.reference_recipe_presentation import prepare_recipe_images

    results = await prepare_recipe_images(meals)
    if not all(results):
        raise RuntimeError("Recipe image generation incomplete; retry missing images")
    return {"preview_id": preview_id, "dish_count": sum(len(meal.get("dishes") or []) for meal in meals)}

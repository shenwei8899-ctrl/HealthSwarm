"""识别任务的菜品来源由当前授权餐单解析，不接收客户端名称或计划摄入。"""

from yuxi.services.daily_meal_plan_service import read_current_plan
from yuxi.services.health_vision_types import HealthVisionError, MealPhotoSource
from yuxi.services.meal_dish_service import dish_key
from yuxi.storage.postgres.models_health import HealthFamilyProfileLink


async def resolve_meal_photo_source(session, uid: str, member_id: str, source: MealPhotoSource):
    """在任务创建事务中核对成员家庭、餐单版本和菜品，再冻结最小识别提示。"""
    family_id = str(source.family_id)
    link = await session.get(HealthFamilyProfileLink, member_id, populate_existing=True)
    if link is None or link.family_id != family_id:
        raise HealthVisionError("meal_source_forbidden", "记餐成员不属于该菜品的来源家庭", 403)
    plan = await read_current_plan(uid, family_id, source.plan_date, session=session)
    if plan["version"] != source.plan_version or source.meal_type in plan.get("needs_regeneration", []):
        raise HealthVisionError("meal_source_changed", "来源餐单已更新，请返回菜品详情重新进入拍照", 409)
    meal = next((item for item in plan["meals"] if item["meal_type"] == source.meal_type), None)
    dish = (
        next((item for item in meal["meal"].get("dishes", []) if dish_key(item) == source.dish_key), None)
        if meal
        else None
    )
    if dish is None:
        raise HealthVisionError("meal_source_changed", "来源菜品已变化，请返回菜品详情重新进入拍照", 409)
    return {"version": 1, "dish_name": dish["name"]}

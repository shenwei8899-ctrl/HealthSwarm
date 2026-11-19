"""我的餐单按当前家庭权限读取最新成功日快照。"""

from yuxi.repositories.meal_archive_repository import archive_rows
from yuxi.services.daily_meal_plan_service import current_row, MEALS
from yuxi.services.family_service import FamilyService
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.storage.postgres.manager import pg_manager


async def list_meal_archive(uid, family_id, *, before=None, limit=20):
    """读取日期倒序的成功餐单，不触发生成或专业采用。"""
    async with pg_manager.get_async_session_context() as session:
        await FamilyService(session, uid).context(family_id)
        rows = await archive_rows(session, family_id, before=before, limit=limit)
        return {
            "plans": [archive_response(row) for row in rows[:limit]],
            "next_before": rows[limit - 1].plan_date.isoformat() if len(rows) > limit else None,
        }


async def read_meal_archive(uid, family_id, day):
    """历史展示不受商品库存和当前模型状态影响。"""
    async with pg_manager.get_async_session_context() as session:
        row = await current_row(session, uid, family_id, day)
        if row is None or not row.archive_meals:
            raise HealthVisionError("meal_archive_absent", "这一天还没有已生成的餐单", 404)
        return archive_response(row)


def archive_response(row):
    """响应只含归档展示，不暴露来源证明、请求或健康档案。"""
    return {
        "id": row.id,
        "family_id": row.family_id,
        "plan_date": str(row.plan_date),
        "version": row.version,
        "meals": [row.archive_meals[kind] for kind in MEALS if kind in row.archive_meals],
    }

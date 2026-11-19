"""共享每日餐单的最新成功展示快照。"""

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from yuxi.storage.postgres.models_health import HealthDailyMealPlan


async def upgrade_meal_archive(manager, *, refresh_existing=False):
    """幂等补列并从成功发布的来源回填，无法恢复的来源保留空缺。"""
    from yuxi.repositories.meal_archive_repository import stored_meal
    from yuxi.services.meal_archive_projection import merge_archive
    from yuxi.services.recipe_translation_service import cached_chinese_display

    async with manager.async_engine.begin() as connection:
        await connection.execute(
            text(
                "ALTER TABLE health_daily_meal_plan ADD COLUMN IF NOT EXISTS "
                "archive_meals JSONB NOT NULL DEFAULT '{}'::jsonb"
            )
        )
        async with AsyncSession(bind=connection, expire_on_commit=False) as session:
            rows = await session.scalars(select(HealthDailyMealPlan).where(HealthDailyMealPlan.is_shared.is_(True)))
            for row in rows:
                for kind, ref in row.meal_sources.items():
                    if not refresh_existing and kind in (row.archive_meals or {}):
                        continue
                    meal = await stored_meal(session, row.family_id, row.plan_date, ref, kind)
                    if meal:
                        if ref.get("kind") == "reference":
                            from copy import deepcopy

                            meal = deepcopy(meal)
                            for dish in meal["dishes"]:
                                dish.pop("display_zh", None)
                                display = await cached_chinese_display(session, dish)
                                if display is not None:
                                    dish["display_zh"] = display
                        merge_archive(row, [meal])
            await session.flush()

"""专属菜单按日浏览的来源校验回执迁移。"""

from yuxi.storage.postgres.models_health import HealthExclusiveDayValidation


async def upgrade_exclusive_day_validation(manager):
    """幂等创建来源回执表，保留推荐组与原有菜单快照。"""
    async with manager.async_engine.begin() as connection:
        await connection.run_sync(lambda conn: HealthExclusiveDayValidation.__table__.create(conn, checkfirst=True))

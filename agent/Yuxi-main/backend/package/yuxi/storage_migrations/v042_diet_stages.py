"""增量创建阶段表，保留原档案和餐单。"""

from yuxi.storage.postgres.models_diet_stage import DIET_STAGE_TABLES


async def upgrade_diet_stages(manager):
    """迁移器幂等建表，不自动开启用户阶段。"""
    async with manager.async_engine.begin() as connection:
        for table in DIET_STAGE_TABLES:
            await connection.run_sync(lambda conn, target=table: target.create(conn, checkfirst=True))

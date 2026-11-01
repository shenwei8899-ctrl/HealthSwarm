"""产品反馈表的非破坏性、幂等业务迁移。"""

from yuxi.storage.postgres.models_business import ProductFeedback


async def upgrade_product_feedback(manager):
    """仅创建产品反馈表和索引，不修改账号、家庭及已有健康资料。"""
    async with manager.async_engine.begin() as connection:
        await connection.run_sync(lambda sync: ProductFeedback.__table__.create(sync, checkfirst=True))

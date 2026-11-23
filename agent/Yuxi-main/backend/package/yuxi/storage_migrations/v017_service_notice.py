"""账号级声明确认的可重入增量迁移。"""

from yuxi.storage.postgres.models_business import ServiceNoticeAcknowledgement


async def upgrade_service_notice(manager):
    """既有用户保持未确认，不推断或回填任何接受事实。"""
    async with manager.async_engine.begin() as connection:
        await connection.run_sync(lambda conn: ServiceNoticeAcknowledgement.__table__.create(conn, checkfirst=True))

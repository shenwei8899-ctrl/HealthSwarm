"""用数据库事务锁串行化价格变更、预留与结算。"""

from sqlalchemy import select, text

from yuxi.storage.postgres.models_health_budget import HealthAiCall, HealthAiMonth, HealthAiOpening, HealthAiPrice


class HealthAiBudgetRepository:
    """预算查询只依赖 PostgreSQL，不读取缓存余额。"""

    def __init__(self, session):
        """事务由预算业务服务持有。"""
        self.session = session

    async def lock(self):
        """同一数据库的全部健康用途共用一把短事务锁。"""
        await self.session.execute(text("SELECT pg_advisory_xact_lock(734092601023)"))

    async def now(self):
        """取得锁后读取数据库时间，避免等待跨月和主机时钟差。"""
        return await self.session.scalar(text("SELECT clock_timestamp() AT TIME ZONE 'UTC'"))

    async def price(self, target, now):
        """仅接受仍有效的最新批准。"""
        return await self.session.scalar(
            select(HealthAiPrice)
            .where(HealthAiPrice.target == target, HealthAiPrice.enabled.is_(True), HealthAiPrice.valid_until > now)
            .order_by(HealthAiPrice.approved_at.desc(), HealthAiPrice.id.desc())
            .limit(1)
        )

    async def prices(self, target):
        """替换时保留旧价格版本供账本引用。"""
        return list(
            (
                await self.session.scalars(
                    select(HealthAiPrice).where(HealthAiPrice.target == target, HealthAiPrice.enabled.is_(True))
                )
            ).all()
        )

    async def month(self, month):
        """只在显式预留时创建月份。"""
        return await self.session.get(HealthAiMonth, month)

    async def opening(self):
        """项目只允许一次明确的启用期初确认。"""
        return await self.session.get(HealthAiOpening, 1)

    async def call(self, call_id):
        """调用标识全局唯一，不随月切换失效。"""
        return await self.session.get(HealthAiCall, call_id)

    async def calls(self, month, limit=100):
        """管理端只返回当前月份有界账本。"""
        return list(
            (
                await self.session.scalars(
                    select(HealthAiCall)
                    .where(HealthAiCall.month == month)
                    .order_by(HealthAiCall.created_at.desc(), HealthAiCall.id)
                    .limit(limit)
                )
            ).all()
        )

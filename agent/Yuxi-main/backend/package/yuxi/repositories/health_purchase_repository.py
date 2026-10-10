"""采购同Run只读回执的PG查询。"""

from sqlalchemy import select

from yuxi.storage.postgres.models_health import HealthPurchasePreview


class HealthPurchaseRepository:
    """事务与执行租约由采购用例持有，repository只查询回执。"""

    def __init__(self, session):
        """复用所属业务事务。"""
        self.session = session

    async def for_run(self, run_id):
        """同运行重复工具调用复用唯一不可变回执。"""
        return await self.session.scalar(select(HealthPurchasePreview).where(HealthPurchasePreview.run_id == run_id))

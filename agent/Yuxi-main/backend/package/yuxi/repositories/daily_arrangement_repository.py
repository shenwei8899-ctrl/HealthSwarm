"""今日安排的家庭授权、数据库唯一性和持久请求引用。"""

from sqlalchemy import select, text

from yuxi.services.family_service import FamilyService
from yuxi.storage.postgres.models_health import HealthDailyArrangement


class DailyArrangementRepository:
    """所有查询先验证当前家庭成员关系，不接受客户端账号归属。"""

    def __init__(self, session, uid, fid):
        """绑定调用方事务。"""
        self.session, self.uid, self.fid = session, uid, fid

    async def context(self, day, *, lock=False):
        """并发首开和恢复按账号、家庭、日期串行。"""
        if lock:
            await self.session.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                {"key": f"daily-arrangement:{self.uid}:{self.fid}:{day}"},
            )
        service = FamilyService(self.session, self.uid)
        family, _ = await service.context(self.fid)
        row = await self.session.scalar(
            select(HealthDailyArrangement).where(
                HealthDailyArrangement.actor_uid == self.uid,
                HealthDailyArrangement.family_id == self.fid,
                HealthDailyArrangement.plan_date == day,
            )
        )
        return family, row

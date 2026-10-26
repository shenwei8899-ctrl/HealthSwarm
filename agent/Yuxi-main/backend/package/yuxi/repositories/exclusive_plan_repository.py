"""推荐组的家庭授权、并发去重和持久化查询。"""

from sqlalchemy import select, text

from yuxi.services.family_service import FamilyService
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.storage.postgres.models_health import HealthExclusivePlanGroup


class ExclusivePlanRepository:
    """查询始终绑定当前账号和家庭。"""

    def __init__(self, session, uid, fid):
        """使用调用方的事务。"""
        self.session, self.uid, self.fid = session, uid, fid

    async def context(self, *, lock=False):
        """序列化同一家庭的首次进入、重试和主动换一套。"""
        if lock:
            await self.session.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                {"key": f"exclusive-plan:{self.uid}:{self.fid}"},
            )
        family, _ = await FamilyService(self.session, self.uid).context(self.fid)
        return family

    async def find(self, *, group_id=None, request_id=None, basis_hash=None, lock=False):
        """不从其他账号、家庭或推荐组猜测结果。"""
        query = select(HealthExclusivePlanGroup).where(
            HealthExclusivePlanGroup.actor_uid == self.uid,
            HealthExclusivePlanGroup.family_id == self.fid,
        )
        for field, value in (("id", group_id), ("request_id", request_id), ("basis_hash", basis_hash)):
            if value is not None:
                query = query.where(getattr(HealthExclusivePlanGroup, field) == value)
        row = await self.session.scalar(
            query.order_by(HealthExclusivePlanGroup.created_at.desc()).limit(1).with_for_update()
            if lock
            else query.order_by(HealthExclusivePlanGroup.created_at.desc()).limit(1)
        )
        if group_id and row is None:
            raise HealthVisionError("not_found", "专属计划不存在", 404)
        return row

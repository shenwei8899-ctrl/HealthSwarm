"""账号服务声明确认的 PostgreSQL 持久化边界。"""

from sqlalchemy.dialects.postgresql import insert

from yuxi.storage.postgres.models_business import ServiceNoticeAcknowledgement
from yuxi.utils.datetime_utils import utc_now_naive


class ServiceNoticeRepository:
    """账号与版本共同确定一条不可覆盖的确认记录。"""

    def __init__(self, session):
        self.session = session

    async def current(self, uid, version):
        """直接读取当前账号，不接受家庭成员替代。"""
        return await self.session.get(ServiceNoticeAcknowledgement, (uid, version), populate_existing=True)

    async def acknowledge(self, uid, version, content_hash):
        """唯一约束处理并发，重放不修改原确认时间。"""
        await self.session.execute(
            insert(ServiceNoticeAcknowledgement)
            .values(
                actor_uid=uid,
                notice_version=version,
                content_hash=content_hash,
                acknowledged_at=utc_now_naive(),
            )
            .on_conflict_do_nothing(index_elements=["actor_uid", "notice_version"])
        )

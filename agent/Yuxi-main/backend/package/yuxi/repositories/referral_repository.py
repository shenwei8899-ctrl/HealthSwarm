"""账号邀请的唯一归因、成功转移与匿名查询。"""

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert

from yuxi.storage.postgres.models_business import FriendReferral, FriendReferralCode, User
from yuxi.utils.datetime_utils import utc_now_naive


class ReferralRepository:
    """事务由注册或建档用例拥有。"""

    def __init__(self, db):
        """复用调用方会话。"""
        self.db = db

    async def prepare(self, uid, code):
        """并发准备只保留一个账号邀请码。"""
        await self.db.execute(insert(FriendReferralCode).values(inviter_uid=uid, code=code).on_conflict_do_nothing())
        return await self.db.get(FriendReferralCode, uid)

    async def valid_code(self, code):
        """只接受有效邀请码及仍可使用的邀请账号。"""
        return await self.db.scalar(
            select(FriendReferralCode)
            .join(User, User.uid == FriendReferralCode.inviter_uid)
            .where(FriendReferralCode.code == code, FriendReferralCode.enabled.is_(True), User.is_deleted == 0)
        )

    async def bind(self, invitee_uid, row, channel):
        """新账号关联写入当前注册事务。"""
        self.db.add(
            FriendReferral(invitee_uid=invitee_uid, inviter_uid=row.inviter_uid, code=row.code, channel=channel)
        )
        await self.db.flush()

    async def complete(self, uid):
        """邀请人行锁串行分配稳定匿名编号，重复建档不改变成功事实。"""
        relation = await self.db.get(FriendReferral, uid)
        if relation is None or relation.completed_at is not None:
            return
        await self.db.scalar(
            select(FriendReferralCode).where(FriendReferralCode.inviter_uid == relation.inviter_uid).with_for_update()
        )
        number = (
            await self.db.scalar(
                select(func.max(FriendReferral.success_number)).where(
                    FriendReferral.inviter_uid == relation.inviter_uid
                )
            )
            or 0
        ) + 1
        await self.db.execute(
            update(FriendReferral)
            .where(FriendReferral.invitee_uid == uid, FriendReferral.completed_at.is_(None))
            .values(completed_at=utc_now_naive(), success_number=number)
        )

    async def records(self, uid, before, limit):
        """结果不投影受邀账号和健康信息。"""
        base = select(FriendReferral).where(FriendReferral.inviter_uid == uid, FriendReferral.completed_at.is_not(None))
        total = await self.db.scalar(select(func.count()).select_from(base.subquery()))
        if before:
            base = base.where(FriendReferral.success_number < before)
        rows = list(await self.db.scalars(base.order_by(FriendReferral.success_number.desc()).limit(limit + 1)))
        return total, rows[:limit], len(rows) > limit

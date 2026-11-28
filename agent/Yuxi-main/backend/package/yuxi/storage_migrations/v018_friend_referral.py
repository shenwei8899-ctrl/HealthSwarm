"""好友邀请增量表，不追溯归因历史账号。"""

from yuxi.storage.postgres.models_business import FriendReferral, FriendReferralCode


async def upgrade_friend_referral(manager):
    """可重复创建邀请表及数据库唯一约束。"""
    async with manager.async_engine.begin() as connection:
        for table in (FriendReferralCode.__table__, FriendReferral.__table__):
            await connection.run_sync(lambda conn, table=table: table.create(conn, checkfirst=True))

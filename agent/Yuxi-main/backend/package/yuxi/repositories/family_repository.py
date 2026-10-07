"""家庭档案持久化与带身份范围的查询。"""

from sqlalchemy import exists, or_, select
from yuxi.storage.postgres.models_business import (
    FamilyArchive,
    FamilyAudit,
    FamilyMeasurement,
    FamilyMember,
    FamilyProfileRevision,
)


class FamilyRepository:
    """所有操作使用调用方拥有的事务。"""

    def __init__(self, db):
        self.db = db

    def visible_families(self, uid):
        """仅查询自己管理或本人已加入的家庭。"""
        membership = exists().where(FamilyMember.family_id == FamilyArchive.id, FamilyMember.subject_uid == uid)
        return select(FamilyArchive).where(or_(FamilyArchive.owner_uid == uid, membership))

    async def list_families(self, uid):
        """列出可访问家庭。"""
        return list((await self.db.scalars(self.visible_families(uid).order_by(FamilyArchive.created_at))).all())

    async def get_family(self, fid, uid):
        """锁定家庭，将授权撤回与受控读写串行化。"""
        return await self.db.scalar(self.visible_families(uid).where(FamilyArchive.id == fid).with_for_update())

    async def owned_family(self, uid):
        """读取用户唯一管理的家庭。"""
        return await self.db.scalar(select(FamilyArchive).where(FamilyArchive.owner_uid == uid))

    async def members(self, fid):
        """按稳定顺序读取成员。"""
        return list(
            (
                await self.db.scalars(
                    select(FamilyMember)
                    .where(FamilyMember.family_id == fid)
                    .order_by(FamilyMember.updated_at, FamilyMember.id)
                )
            ).all()
        )

    async def member(self, fid, mid):
        """成员 ID 必须属于当前家庭。"""
        return await self.db.scalar(select(FamilyMember).where(FamilyMember.id == mid, FamilyMember.family_id == fid))

    async def invitation(self, code_hash):
        """只查找邀请的归属，调用方随后锁定家庭并重新核对。"""
        return await self.db.scalar(select(FamilyMember).where(FamilyMember.invite_hash == code_hash))

    async def subject_member(self, fid, uid):
        """防止同一账户在同一家庭认领多个身份。"""
        return await self.db.scalar(
            select(FamilyMember).where(FamilyMember.family_id == fid, FamilyMember.subject_uid == uid)
        )

    async def measurements(self, mids, kinds=None, since=None, until=None, limit=None):
        """读取当前已授权成员和指标的记录。"""
        query = select(FamilyMeasurement).where(FamilyMeasurement.member_id.in_(mids))
        if kinds is not None:
            query = query.where(FamilyMeasurement.kind.in_(kinds))
        if since is not None:
            query = query.where(FamilyMeasurement.measured_at >= since)
        if until is not None:
            query = query.where(FamilyMeasurement.measured_at < until)
        query = query.order_by(FamilyMeasurement.measured_at.desc(), FamilyMeasurement.id)
        if limit:
            query = query.limit(limit)
        return list((await self.db.scalars(query)).all())

    async def measurement(self, rid):
        """读取幂等记录。调用方必须先校验目标成员权限。"""
        return await self.db.scalar(select(FamilyMeasurement).where(FamilyMeasurement.id == rid))

    async def revisions(self, mid):
        """查询历史快照，输出仍由服务层当前权限过滤。"""
        return list(
            (
                await self.db.scalars(
                    select(FamilyProfileRevision)
                    .where(FamilyProfileRevision.member_id == mid)
                    .order_by(FamilyProfileRevision.version.desc())
                    .limit(100)
                )
            ).all()
        )

    async def audit(self, fid, mid, uid, action, version=None):
        """记录元信息，不把健康数值写入日志。"""
        self.db.add(FamilyAudit(family_id=fid, member_id=mid, actor_uid=uid, action=action, version=version))
        await self.db.flush()

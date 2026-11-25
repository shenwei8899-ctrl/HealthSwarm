"""阶段查询、操作收据和版本快照；事务属于业务服务。"""

from copy import deepcopy
from uuid import uuid4

from sqlalchemy import select

from yuxi.services.family_service import FamilyService, guardian_active
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.storage.postgres.models_diet_stage import DietActionWeek, DietStage, DietStageReview, DietStageWrite


class DietStageRepository:
    """阶段归属必须先与当前家庭身份共同核对。"""

    def __init__(self, session, uid, family_id, member_id):
        self.session, self.uid = session, str(uid)
        self.family_id, self.member_id = str(family_id), str(member_id)

    async def context(self, *, write=False):
        """普通清单沿用档案权限，AI来源另核对健康服务授权。"""
        family, member = await FamilyService(self.session, self.uid).context(self.family_id, self.member_id)
        FamilyService(self.session, self.uid).require_fields(family, member, {"goal", "dietary_details"}, write=write)
        if write and not (
            family.owner_uid == self.uid or member.subject_uid == self.uid or guardian_active(member, self.uid)
        ):
            raise HealthVisionError("not_authorized", "当前成员资料为只读", 403)
        return family, member

    async def active(self):
        """同一成员的未结束阶段由唯一索引保证。"""
        return await self.session.scalar(
            select(DietStage).where(
                DietStage.family_id == self.family_id,
                DietStage.member_id == self.member_id,
                DietStage.status == "active",
            )
        )

    async def stage(self, stage_id):
        """不允许跨成员借用阶段编号。"""
        row = await self.session.scalar(
            select(DietStage).where(
                DietStage.id == str(stage_id),
                DietStage.family_id == self.family_id,
                DietStage.member_id == self.member_id,
            )
        )
        if row is None:
            raise HealthVisionError("not_found", "阶段不存在或无权访问", 404)
        return row

    async def week(self, stage_id, starts_on):
        """读取确定日期区间而非不稳定的周序号。"""
        return await self.session.scalar(
            select(DietActionWeek).where(DietActionWeek.stage_id == stage_id, DietActionWeek.starts_on == starts_on)
        )

    async def weeks(self, stage_id):
        """阶段最多约十四周，无需逐周回查。"""
        return list(
            (
                await self.session.scalars(
                    select(DietActionWeek).where(DietActionWeek.stage_id == stage_id).order_by(DietActionWeek.starts_on)
                )
            ).all()
        )

    async def replay(self, request_id, fingerprint):
        """锁内先回读收据，再判断当前版本。"""
        row = await self.session.scalar(
            select(DietStageWrite).where(
                DietStageWrite.actor_uid == self.uid, DietStageWrite.request_id == str(request_id)
            )
        )
        if row is None:
            return None
        await self.stage(row.stage_id)
        if row.fingerprint != fingerprint:
            raise HealthVisionError("idempotency_conflict", "同一请求的内容已变化", 409)
        return deepcopy(row.snapshot["response"])

    def receipt(self, stage, request_id, fingerprint, response):
        """目标修订和绝对次数写入与收据在同一事务提交。"""
        self.session.add(
            DietStageWrite(
                id=str(uuid4()),
                stage_id=stage.id,
                actor_uid=self.uid,
                request_id=str(request_id),
                fingerprint=fingerprint,
                snapshot={"goals": deepcopy(stage.goals), "version": stage.version, "response": response},
            )
        )

    async def job(self, job_id):
        """模型正文只对发起操作者可见。"""
        row = await self.session.scalar(
            select(DietStageReview).where(
                DietStageReview.id == str(job_id),
                DietStageReview.actor_uid == self.uid,
                DietStageReview.family_id == self.family_id,
                DietStageReview.member_id == self.member_id,
            )
        )
        if row is None:
            raise HealthVisionError("not_found", "结果不存在或无权访问", 404)
        return row


def stage_view(row):
    """返回阶段事实，不推断医学达标。"""
    return {
        "id": row.id,
        "version": row.version,
        "goals": row.goals,
        "status": row.status,
        "starts_on": row.starts_on.isoformat(),
        "review_on": row.review_on.isoformat(),
    }


def week_view(row):
    """完成数仅由用户确认的行动状态得出。"""
    return {
        "id": row.id,
        "version": row.version,
        "goal_version": row.goal_version,
        "starts_on": row.starts_on.isoformat(),
        "ends_on": row.ends_on.isoformat(),
        "actions": row.actions,
        "completed": sum(item["count"] >= item["target"] for item in row.actions),
        "total": len(row.actions),
    }

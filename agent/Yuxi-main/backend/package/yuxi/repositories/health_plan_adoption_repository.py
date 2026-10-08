"""次日提议、单日唯一采用及动作收据的PG查询。"""

from datetime import date

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert

from yuxi.repositories.health_meal_plan_repository import HealthMealPlanRepository
from yuxi.repositories.health_vision_repository import HealthVisionRepository
from yuxi.services.health_family_meal_plan_types import plan_member_ids
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.storage.postgres.models_health import (
    HealthNextDayProposal,
    HealthMealPlanAdoption,
    HealthMealPlanAdoptionMember,
    HealthMealPlanAdoptionAction,
)


def adoption_member_ids(row):
    """历史参与者由采用不可变快照拥有，不从当前草稿推断。"""
    return sorted(row.snapshot["members"]) if row.snapshot.get("scope") == "family_recipe_draft" else [row.member_id]


class HealthPlanAdoptionRepository:
    """对象仍为账号私有，所有使用状态由当前事务拥有。"""

    def __init__(self, session):
        """复用业务Owner事务。"""
        self.session = session

    async def lock_request(self, uid, request_id, *, proposal=False):
        """采用与取消共享请求锁，提议拥有独立操作命名空间。"""
        namespace = "health-next-day" if proposal else "health-plan-adoption"
        await self.session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
            {"key": f"{namespace}:{uid}:{request_id}"},
        )

    async def receipt(self, uid, request_id, *, proposal=False):
        """从不可变收据查询，不以当前状态推测原动作。"""
        model = HealthNextDayProposal if proposal else HealthMealPlanAdoptionAction
        return await self.session.scalar(select(model).where(model.actor_uid == uid, model.request_id == request_id))

    async def adoption(self, uid, adoption_id, *, lock=True):
        """先检查私有归属，再锁成员并刷新，取消不依赖未失效的方案。"""
        row = await self.session.get(HealthMealPlanAdoption, adoption_id, populate_existing=True)
        if row is None or row.actor_uid != uid:
            raise HealthVisionError("not_found", "采用记录不存在或无权访问", 404)
        for member_id in adoption_member_ids(row):
            await HealthVisionRepository(self.session).authorize(member_id, uid, "diet_edit", lock=lock)
        if lock:
            await self.session.refresh(row)
        return row

    async def active(self, uid, member_id, plan_date, *, lock=False):
        """成员锁持有后查询当天唯一有效采用。"""
        stmt = (
            select(HealthMealPlanAdoption)
            .join(HealthMealPlanAdoptionMember, HealthMealPlanAdoptionMember.adoption_id == HealthMealPlanAdoption.id)
            .where(
                HealthMealPlanAdoption.actor_uid == uid,
                HealthMealPlanAdoptionMember.actor_uid == uid,
                HealthMealPlanAdoptionMember.member_id == member_id,
                HealthMealPlanAdoptionMember.plan_date == plan_date,
                HealthMealPlanAdoption.plan_date == plan_date,
                HealthMealPlanAdoption.status == "active",
            )
            .execution_options(populate_existing=True)
        )
        if lock:
            stmt = stmt.with_for_update()
        return await self.session.scalar(stmt)

    async def lock_plan_occupancies(self, uid, plan_id):
        """先预读新旧成员并排序锁全体；出现新成员时要求刷新而不逆序追加锁。"""
        plan = await HealthMealPlanRepository(self.session).plan(uid, plan_id)
        ids = plan_member_ids(plan.member_id, plan.spec)
        plan_date = date.fromisoformat(plan.snapshot["plan_date"])
        previous = await self.overlapping(uid, ids, plan_date)
        locked_ids = sorted(set(ids).union(*(adoption_member_ids(row) for row in previous)))
        for member_id in locked_ids:
            await HealthVisionRepository(self.session).authorize(member_id, uid, "diet_edit", lock=True)
        await self.session.refresh(plan)
        if plan_member_ids(plan.member_id, plan.spec) != ids or plan.snapshot["plan_date"] != plan_date.isoformat():
            raise HealthVisionError("source_invalidated", "计划参与者或日期已变化，请刷新", 410)
        previous = await self.overlapping(uid, ids, plan_date)
        if any(not set(adoption_member_ids(row)) <= set(locked_ids) for row in previous):
            raise HealthVisionError("adoption_version_conflict", "当日占用参与者已变化，请刷新", 409)
        return plan

    async def overlapping(self, uid, member_ids, plan_date, *, lock=False):
        """按指针查询当前参与者重叠的有效采用，并去重共同对象。"""
        pointers = select(HealthMealPlanAdoptionMember.adoption_id).where(
            HealthMealPlanAdoptionMember.actor_uid == uid,
            HealthMealPlanAdoptionMember.member_id.in_(member_ids),
            HealthMealPlanAdoptionMember.plan_date == plan_date,
        )
        stmt = (
            select(HealthMealPlanAdoption)
            .where(
                HealthMealPlanAdoption.id.in_(pointers),
                HealthMealPlanAdoption.actor_uid == uid,
                HealthMealPlanAdoption.plan_date == plan_date,
                HealthMealPlanAdoption.status == "active",
            )
            .order_by(HealthMealPlanAdoption.id)
            .execution_options(populate_existing=True)
        )
        if lock:
            stmt = stmt.with_for_update()
        return list((await self.session.scalars(stmt)).all())

    async def assign_members(self, row):
        """关联同一采用；旧失效指针被覆盖，状态不在指针表复制。"""
        for member_id in adoption_member_ids(row):
            stmt = insert(HealthMealPlanAdoptionMember).values(
                actor_uid=row.actor_uid, member_id=member_id, plan_date=row.plan_date, adoption_id=row.id
            )
            await self.session.execute(
                stmt.on_conflict_do_update(
                    index_elements=["actor_uid", "member_id", "plan_date"], set_={"adoption_id": row.id}
                )
            )

    async def proposal(self, uid, proposal_id):
        """提议读取保持成员编辑授权与账号归属。"""
        row = await self.session.get(HealthNextDayProposal, proposal_id)
        if row is None or row.actor_uid != uid:
            raise HealthVisionError("not_found", "次日提议不存在或无权访问", 404)
        await HealthVisionRepository(self.session).authorize(row.member_id, uid, "diet_edit", lock=True)
        return row

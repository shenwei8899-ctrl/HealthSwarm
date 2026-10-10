"""餐单草稿、不可变修订及运行预览回执的PG查询。"""

from sqlalchemy import select, text

from yuxi.repositories.health_vision_repository import HealthVisionRepository
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.services.health_family_meal_plan_types import plan_member_ids
from yuxi.storage.postgres.models_health import (
    HealthMealPlan,
    HealthMealPlanPreview,
    HealthInitialPlanPreview,
    HealthMealPlanRevision,
    RecipeVersion,
    PortionReference,
)


class HealthMealPlanRepository:
    """账号私有的成员餐单，管理员没有读取旁路。"""

    def __init__(self, session):
        """绑定当前业务用例的数据库事务。"""
        self.session = session

    async def lock_request(self, uid, request_id):
        """保存和换菜使用同账号同键锁，防止跨对象复用请求。"""
        await self.session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
            {"key": f"health-meal-plan:{uid}:{request_id}"},
        )

    async def preview(self, uid, preview_id, *, lock=False):
        """只读取当前账号回执，并重查对应成员编辑授权。"""
        row = await self.session.get(HealthMealPlanPreview, preview_id)
        if row is None or row.actor_uid != uid:
            raise HealthVisionError("not_found", "餐单预览不存在或无权访问", 404)
        await HealthVisionRepository(self.session).authorize_plan_members(
            row.member_id, uid, row.spec, ["diet_edit"], lock=lock
        )
        return row

    async def initial_preview(self, uid, preview_id):
        """初始回执与通用回执分表，来源和全员授权由生成Owner重验。"""
        row = await self.session.get(HealthInitialPlanPreview, preview_id)
        if row is None or row.actor_uid != uid:
            raise HealthVisionError("not_found", "初始餐单预览不存在或无权访问", 404)
        return row

    async def plan(self, uid, plan_id, *, lock=False):
        """写用例先锁成员再刷新当前计划，避免缓存旧版本。"""
        row = await self.session.get(HealthMealPlan, plan_id)
        if row is None or row.actor_uid != uid:
            raise HealthVisionError("not_found", "餐单不存在或无权访问", 404)
        ids = await HealthVisionRepository(self.session).authorize_plan_members(
            row.member_id, uid, row.spec, ["diet_edit"], lock=lock
        )
        if lock:
            await self.session.refresh(row)
            if plan_member_ids(row.member_id, row.spec) != ids:
                raise HealthVisionError("source_invalidated", "计划参与者已变化，请刷新", 410)
        return row

    async def receipt(self, uid, request_id):
        """不可变修订同时保存幂等指纹，不依赖可修改的当前行。"""
        return await self.session.scalar(
            select(HealthMealPlanRevision).where(
                HealthMealPlanRevision.actor_uid == uid, HealthMealPlanRevision.request_id == request_id
            )
        )

    async def lock_member_change(self, uid, plan, proposed_spec):
        """排序锁定新旧成员并集，刷新后拒绝计划在等待时改变。"""
        old_ids = plan_member_ids(plan.member_id, plan.spec)
        old_version = plan.version
        ids = sorted(set(old_ids) | set(plan_member_ids(plan.member_id, proposed_spec)))
        vision = HealthVisionRepository(self.session)
        for member_id in ids:
            await vision.authorize(member_id, uid, "diet_edit", lock=True)
            await vision.authorize(member_id, uid, "profile_view")
        await self.session.refresh(plan)
        if plan.version != old_version or plan_member_ids(plan.member_id, plan.spec) != old_ids:
            raise HealthVisionError("source_invalidated", "参与者或计划版本已变化，请刷新", 410)

    async def revisions(self, uid, plan):
        """历史各版本也重查所有参与者授权。"""
        rows = list(
            (
                await self.session.scalars(
                    select(HealthMealPlanRevision)
                    .where(HealthMealPlanRevision.plan_id == plan.id)
                    .order_by(HealthMealPlanRevision.version)
                )
            ).all()
        )
        for row in rows:
            await HealthVisionRepository(self.session).authorize_plan_members(
                plan.member_id, uid, row.spec, ["diet_edit"]
            )
        return rows

    async def list_plans(self, uid, member_id, *, limit=50, offset=0):
        """按稳定顺序读取一页及后续标记行，并重验全部参与者授权。"""
        await HealthVisionRepository(self.session).authorize(member_id, uid, "diet_edit")
        rows = list(
            (
                await self.session.scalars(
                    select(HealthMealPlan)
                    .where(HealthMealPlan.actor_uid == uid, HealthMealPlan.member_id == member_id)
                    .order_by(HealthMealPlan.updated_at.desc(), HealthMealPlan.id)
                    .limit(limit + 1)
                    .offset(offset)
                )
            ).all()
        )
        for row in rows:
            await HealthVisionRepository(self.session).authorize_plan_members(
                row.member_id, uid, row.spec, ["diet_edit"]
            )
        return rows

    async def recipes(self, recipe_ids):
        """一次加载批准目录和当前餐单的实际发布版本。"""
        return {
            r.id: r
            for r in (await self.session.scalars(select(RecipeVersion).where(RecipeVersion.id.in_(recipe_ids)))).all()
        }

    async def portions(self, portion_ids):
        """候选批量计算保留原菜的已发布参考份量输入。"""
        return {
            r.id: r
            for r in (
                await self.session.scalars(select(PortionReference).where(PortionReference.id.in_(portion_ids)))
            ).all()
        }

"""默认就餐名单变化后重建未执行的专属计划，保留历史及已确认餐次。"""

import asyncio
from copy import deepcopy
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select

from yuxi.services.health_vision_types import HealthVisionError
from yuxi.storage.postgres.models_health import HealthDailyMealPlan, HealthExclusivePlanGroup


def preserve_executed_meals(original, generated, protected):
    """保留已执行原菜谱，不把保留内容作为新成员适用性或采购依据。"""
    result = deepcopy(generated)
    result["meals"] = [
        deepcopy(meal)
        for kind in ("breakfast", "lunch", "dinner")
        for meal in (original["meals"] if kind in protected else generated["meals"])
        if meal["meal_type"] == kind
    ]
    result["roster_preserved_meals"] = sorted(protected)
    return result


async def schedule_exclusive_roster(session, uid, family, *, group_id=None):
    """家庭事务内登记推荐更新，订单导出保持不可变。"""
    from yuxi.services.exclusive_plan_service import PREVIEW_POLICY
    from yuxi.services.task_service import tasker

    today = datetime.now(ZoneInfo("Asia/Shanghai")).date()
    rows = (
        await session.scalars(
            select(HealthExclusivePlanGroup)
            .where(
                HealthExclusivePlanGroup.family_id == family.id,
            )
            .with_for_update()
        )
    ).all()
    for row in rows:
        if group_id is not None and row.id != group_id:
            continue
        if row.policy != PREVIEW_POLICY or row.progress.get("receipts"):
            continue
        start = date.fromisoformat(row.selection["plan_date"])
        if start + timedelta(days=row.policy["day_count"]) <= today:
            continue
        row.attempt += 1
        revision = row.attempt
        row.progress = {
            **row.progress,
            "roster_update": {"revision": revision, "original_tiers": deepcopy(row.progress.get("tiers", {}))},
        }
        row.status = "generating"
        payload = {"uid": row.actor_uid, "family_id": family.id, "group_id": row.id, "revision": revision}
        task, _ = await tasker.create_unique_in_session(
            session,
            name="更新家庭专属计划成员",
            task_type="exclusive_roster_v1",
            payload=payload,
            payload_match=payload,
            timeout_seconds=1800,
        )
        session.info.setdefault("meal_roster_tasks", []).append(task)


async def run_exclusive_roster(context):
    """复用原谱生成和逐日校验，在任务租约事务中发布更新。"""
    from yuxi.services.meal_roster_service import current_roster
    from yuxi.services.exclusive_plan_service import exclusive_context
    from yuxi.services.exclusive_reference_plan import (
        generate_reference_day,
        optional_exclusive_catalog,
        prepare_reference_day,
    )
    from yuxi.services.exclusive_plan_generation import TIERS
    from yuxi.services.family_service import FamilyService
    from yuxi.storage.postgres.manager import pg_manager

    p = context.payload
    async with pg_manager.get_async_session_context() as session:
        await FamilyService(session, p["uid"]).context(p["family_id"])
        row = await session.get(HealthExclusivePlanGroup, p["group_id"])
        if row.attempt != p["revision"]:
            return {"status": "superseded"}
        if row.status == "ready" and row.progress.get("roster_update", {}).get("status") == "ready":
            return {"status": "ready"}
        original = deepcopy(row.progress["roster_update"]["original_tiers"])
        start = date.fromisoformat(row.selection["plan_date"])
        policy = row.policy
    catalog = await optional_exclusive_catalog()
    today = datetime.now(ZoneInfo("Asia/Shanghai")).date()
    tiers = {}
    basis_hash = None
    for tier in TIERS:
        previous = []
        for number in range(1, policy["day_count"] + 1):
            await context.raise_if_cancelled()
            day = start + timedelta(days=number - 1)
            saved = next((entry for entry in original.get(tier, []) if entry["day"]["day_no"] == number), None)
            async with pg_manager.get_async_session_context() as session:
                await FamilyService(session, p["uid"]).context(p["family_id"])
                row = await session.get(HealthExclusivePlanGroup, p["group_id"])
                if row.attempt != p["revision"]:
                    return {"status": "superseded"}
                inputs = await exclusive_context(
                    session, p["uid"], p["family_id"], policy, day=day, start_date=str(start)
                )
                if basis_hash is None:
                    basis_hash = inputs["basis_hash"]
                elif inputs["basis_hash"] != basis_hash:
                    raise HealthVisionError("roster_changed", "成员资料在生成期间变化，请重试", 409)
                daily = await session.scalar(
                    select(HealthDailyMealPlan).where(
                        HealthDailyMealPlan.family_id == p["family_id"],
                        HealthDailyMealPlan.plan_date == day,
                        HealthDailyMealPlan.is_shared.is_(True),
                    )
                )
                protected = {
                    m
                    for m, value in (await current_roster(session, daily, lock=True)).items()
                    if m in {"breakfast", "lunch", "dinner"}
                    and (value.get("execution_locked") or value.get("mode") == "explicit")
                }
            if saved and day < today:
                entry = preserve_executed_meals(saved, saved, {"breakfast", "lunch", "dinner"})
            else:
                entry = await asyncio.to_thread(
                    generate_reference_day, inputs, tier, previous, f"{p['group_id']}:{p['revision']}", catalog
                )
                async with pg_manager.get_async_session_context() as session:
                    await prepare_reference_day(session, inputs, entry, catalog)
                if saved and protected:
                    entry = preserve_executed_meals(saved, entry, protected)
            previous.append(entry)
        tiers[tier] = previous

    async def publish(session, _record):
        """提交前重新核对名单和用餐确认，拒绝生成期间的新确认。"""
        await FamilyService(session, p["uid"]).context(p["family_id"])
        row = await session.get(HealthExclusivePlanGroup, p["group_id"], with_for_update=True)
        if row.attempt != p["revision"]:
            raise HealthVisionError("roster_changed", "计划名单再次变化，保留新任务", 409)
        fresh = await exclusive_context(
            session, p["uid"], p["family_id"], policy, day=start, start_date=str(start), load_documents=False
        )
        if fresh["basis_hash"] != basis_hash:
            raise HealthVisionError("roster_changed", "成员资料已更新，请重新核对计划", 409)
        # 发布时再次保留最新确认餐次，不能由生成开始时的名单覆盖。
        for tier, entries in tiers.items():
            for index, entry in enumerate(entries):
                day = date.fromisoformat(entry["day"]["plan_date"])
                daily = await session.scalar(
                    select(HealthDailyMealPlan).where(
                        HealthDailyMealPlan.family_id == p["family_id"],
                        HealthDailyMealPlan.plan_date == day,
                        HealthDailyMealPlan.is_shared.is_(True),
                    )
                )
                locked = {
                    m
                    for m, v in (await current_roster(session, daily, lock=True)).items()
                    if m in {"breakfast", "lunch", "dinner"}
                    and (v.get("execution_locked") or v.get("mode") == "explicit")
                }
                old = next((e for e in original.get(tier, []) if e["day"]["day_no"] == entry["day"]["day_no"]), None)
                if day < datetime.now(ZoneInfo("Asia/Shanghai")).date():
                    locked = {"breakfast", "lunch", "dinner"}
                if locked and old:
                    entries[index] = preserve_executed_meals(
                        old, entry, locked | set(entry.get("roster_preserved_meals", []))
                    )
        from yuxi.services.exclusive_reference_plan import validate_reference_days

        for entries in tiers.values():
            await validate_reference_days(session, fresh, entries)
        row.selection = fresh["selection"].model_dump(mode="json")
        row.sources, row.basis_hash, row.status = fresh["sources"], fresh["basis_hash"], "ready"
        row.progress = {
            **row.progress,
            "tiers": tiers,
            "catalog_snapshot": catalog,
            "roster_update": {"revision": p["revision"], "status": "ready"},
        }

    await context.run_owned_transaction(publish)
    return {"status": "ready"}


async def fail_exclusive_roster(session, record, error):
    """失败保留原快照，状态明确可重新准备。"""
    row = await session.get(HealthExclusivePlanGroup, record.payload["group_id"], with_for_update=True)
    if row is not None and row.attempt == record.payload["revision"] and row.status != "ready":
        row.status = "failed"
        row.progress = {
            **row.progress,
            "error": {"code": "roster_update_failed", "message": "成员更新未完成，原计划已保留", "retryable": True},
        }


async def retry_exclusive_roster(uid, fid, group_id):
    """失败重试继续原推荐组和历史保留语义，不先用旧依据阻断。"""
    from yuxi.repositories.exclusive_plan_repository import ExclusivePlanRepository
    from yuxi.services.exclusive_plan_service import project_group
    from yuxi.services.task_service import tasker
    from yuxi.storage.postgres.manager import pg_manager

    async with pg_manager.get_async_session_context() as session:
        repo = ExclusivePlanRepository(session, uid, fid)
        family = await repo.context(lock=True)
        row = await repo.find(group_id=str(group_id), lock=True)
        if not row.progress.get("roster_update") or row.status not in {"failed", "generating"}:
            return None
        if row.status == "failed":
            await schedule_exclusive_roster(session, uid, family, group_id=row.id)
        tasks = session.info.get("meal_roster_tasks", [])
        result = project_group(row, row.sources)
    for task in tasks:
        await tasker.publish(task)
    return result

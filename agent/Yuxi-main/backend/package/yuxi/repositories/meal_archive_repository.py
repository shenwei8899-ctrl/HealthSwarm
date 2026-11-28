"""按共享每日事实读取餐单归档和迁移所需的已发布来源。"""

from sqlalchemy import select

from yuxi.repositories.family_repository import FamilyRepository
from yuxi.storage.postgres.models_business import FamilyArchive
from yuxi.storage.postgres.models_health import (
    HealthDailyMealPlan,
    HealthDailyArrangement,
    HealthInitialPlanPreview,
)


async def archive_family_visible(session, uid, family_id):
    """只读检查有效家庭身份，不申请家庭排他锁。"""
    return (
        await session.scalar(
            FamilyRepository(session)
            .visible_families(str(uid))
            .with_only_columns(FamilyArchive.id)
            .where(FamilyArchive.id == family_id)
        )
        is not None
    )


async def archive_rows(session, uid, family_id, *, before=None, limit=20):
    """日期游标保持翻页稳定，只列出具有成功餐次的共享日。"""
    query = visible_archive_query(session, uid, family_id)
    if before is not None:
        query = query.where(HealthDailyMealPlan.plan_date < before)
    return list((await session.scalars(query.order_by(HealthDailyMealPlan.plan_date.desc()).limit(limit + 1))).all())


async def archive_row(session, uid, family_id, day):
    """详情在读取快照的同一条 SQL 中核对有效成员关系。"""
    return await session.scalar(
        visible_archive_query(session, uid, family_id).where(HealthDailyMealPlan.plan_date == day)
    )


def visible_archive_query(session, uid, family_id):
    """权限和快照共用语句快照，已提交的退出或归档立即阻断读取。"""
    families = FamilyRepository(session).visible_families(str(uid)).with_only_columns(FamilyArchive.id)
    return select(HealthDailyMealPlan).where(
        HealthDailyMealPlan.family_id == family_id,
        HealthDailyMealPlan.family_id.in_(families),
        HealthDailyMealPlan.is_shared.is_(True),
        HealthDailyMealPlan.archive_meals != {},
    )


async def stored_meal(session, family_id, day, ref, kind, *, cache=None):
    """迁移仅解析已发布索引，不调用模型、商城或当前策略校验。"""
    if ref.get("kind") == "reference":
        from yuxi.storage.postgres.models_business import AgentRun

        preview = await _source_row(session, HealthInitialPlanPreview, ref["id"], cache)
        run = await _source_row(session, AgentRun, preview.run_id, cache) if preview else None
        if (
            not preview
            or not run
            or run.status != "completed"
            or preview.actor_uid != run.uid
            or preview.selection.get("family_id") != family_id
            or preview.selection.get("plan_date") != str(day)
        ):
            return None
        source = preview.snapshot
    elif ref.get("kind") == "formal":
        row = await _source_row(session, HealthDailyArrangement, ref["id"], cache)
        if (
            not row
            or row.family_id != family_id
            or row.plan_date != day
            or (row.snapshot or {}).get("version") != ref.get("version")
        ):
            return None
        source = row.snapshot
    elif ref.get("kind") == "selection":
        dishes, members = [], []
        for origin in ref.get("dish_sources", []):
            if origin.get("date") != str(day):
                return None
            meal = origin.get("frozen", {}).get("meal")
            if meal is None:
                meal = await stored_meal(
                    session,
                    family_id,
                    day,
                    origin["source"],
                    origin["meal_type"],
                    cache=cache,
                )
            selected = next(
                (
                    dish
                    for dish in (meal or {}).get("dishes", [])
                    if str(
                        dish.get("dish_key")
                        or dish.get("id")
                        or dish.get("recipe_ref")
                        or ":".join(str(dish[k]) for k in ("file_id", "chunk_id", "name") if dish.get(k))
                    )
                    == origin["dish_key"]
                ),
                None,
            )
            if selected is None:
                return None
            dishes.append(selected)
            members = meal.get("members", [])
        return {"meal_type": kind, "dishes": dishes, "members": members} if dishes else None
    else:
        return None
    meal = next(
        (meal for meal in source.get("meals", []) if meal.get("meal_type", meal.get("type")) == kind),
        None,
    )
    return {**meal, "members": meal.get("members", source.get("members", []))} if meal else None


async def archive_source_cache(session, rows):
    """批量读取归档对应的保存来源，避免每道菜重新查询预览。"""
    from yuxi.storage.postgres.models_business import AgentRun

    references = [ref for row in rows for kind, ref in (row.meal_sources or {}).items() if kind != "_roster"]
    index = 0
    while index < len(references):
        ref = references[index]
        if ref.get("kind") == "selection":
            references.extend(
                origin["source"] for origin in ref.get("dish_sources", []) if not origin.get("frozen", {}).get("meal")
            )
        index += 1
    cache = {}
    for model, kind in (
        (HealthInitialPlanPreview, "reference"),
        (HealthDailyArrangement, "formal"),
    ):
        ids = {ref["id"] for ref in references if ref.get("kind") == kind}
        if ids:
            for source in (await session.scalars(select(model).where(model.id.in_(ids)))).all():
                cache[(model, source.id)] = source
    run_ids = {source.run_id for (model, _), source in cache.items() if model is HealthInitialPlanPreview}
    if run_ids:
        for run in (await session.scalars(select(AgentRun).where(AgentRun.id.in_(run_ids)))).all():
            cache[(AgentRun, run.id)] = run
    return cache


async def _source_row(session, model, identity, cache):
    """批量读取时缺失来源保持缺失，迁移调用仍按原路径读取。"""
    return cache.get((model, identity)) if cache is not None else await session.get(model, identity)

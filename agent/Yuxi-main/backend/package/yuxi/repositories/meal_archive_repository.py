"""按共享每日事实读取餐单归档和迁移所需的已发布来源。"""

from sqlalchemy import select

from yuxi.storage.postgres.models_health import HealthDailyMealPlan, HealthDailyArrangement, HealthInitialPlanPreview


async def archive_rows(session, family_id, *, before=None, limit=20):
    """日期游标保持翻页稳定，只列出具有成功餐次的共享日。"""
    query = select(HealthDailyMealPlan).where(
        HealthDailyMealPlan.family_id == family_id,
        HealthDailyMealPlan.is_shared.is_(True),
        HealthDailyMealPlan.archive_meals != {},
    )
    if before is not None:
        query = query.where(HealthDailyMealPlan.plan_date < before)
    return list((await session.scalars(query.order_by(HealthDailyMealPlan.plan_date.desc()).limit(limit + 1))).all())


async def stored_meal(session, family_id, day, ref, kind):
    """迁移仅解析已发布索引，不调用模型、商城或当前策略校验。"""
    if ref.get("kind") == "reference":
        from yuxi.storage.postgres.models_business import AgentRun

        preview = await session.get(HealthInitialPlanPreview, ref["id"])
        run = await session.get(AgentRun, preview.run_id) if preview else None
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
        row = await session.get(HealthDailyArrangement, ref["id"])
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
                meal = await stored_meal(session, family_id, day, origin["source"], origin["meal_type"])
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
    meal = next((meal for meal in source.get("meals", []) if meal.get("meal_type", meal.get("type")) == kind), None)
    return {**meal, "members": meal.get("members", source.get("members", []))} if meal else None

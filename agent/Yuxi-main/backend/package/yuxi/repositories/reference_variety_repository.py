"""参考餐单差异检查只投影菜品身份，不读取其他家庭的健康资料。"""

from datetime import date, timedelta

from sqlalchemy import or_, select, text

from yuxi.storage.postgres.models_health import HealthInitialPlanPreview, HealthDailyMealPlan
from yuxi.storage.postgres.models_business import AgentRun


async def reference_history(session, selection, *, lock=False, run_id=None):
    """保存持有事务锁至提交，使同时生成的餐单可见并重新核对。"""
    if lock:
        await session.execute(text("SELECT pg_advisory_xact_lock(hashtextextended('reference-variety-save', 0))"))
    day = date.fromisoformat(selection["plan_date"])
    model = HealthInitialPlanPreview
    rows = (
        await session.execute(
            select(
                model.selection["family_id"].as_string(),
                model.selection["plan_date"].as_string(),
                model.snapshot["meals"],
                model.run_id,
            )
            .outerjoin(AgentRun, AgentRun.id == model.run_id)
            .where(
                or_(AgentRun.id.is_(None), AgentRun.status.notin_(("failed", "cancelled", "interrupted"))),
                model.selection["mode"].as_string() == "reference",
                model.selection["plan_date"].as_string() >= (day - timedelta(days=14)).isoformat(),
                model.selection["plan_date"].as_string() <= (day + timedelta(days=1)).isoformat(),
            )
            .order_by(model.created_at.desc(), model.id.desc())
        )
    ).all()
    return [
        (family, saved_day, meals or [])
        for family, saved_day, meals, saved_run in rows
        if run_id is None or saved_run != run_id
    ]


async def current_reference_menus(session, selection):
    """按每日计划真实引用逐账号还原餐次，其他账号的预览不能遮盖当前结果。"""
    rows = (
        await session.execute(
            select(
                HealthDailyMealPlan.family_id,
                HealthDailyMealPlan.actor_uid,
                HealthDailyMealPlan.meal_sources,
            ).where(HealthDailyMealPlan.plan_date == date.fromisoformat(selection["plan_date"]))
        )
    ).all()
    ids = {ref["id"] for _, _, sources in rows for ref in (sources or {}).values() if ref.get("kind") == "reference"}
    previews = (
        dict(
            (
                await session.execute(
                    select(
                        HealthInitialPlanPreview.id,
                        HealthInitialPlanPreview.snapshot["meals"],
                    ).where(HealthInitialPlanPreview.id.in_(ids))
                )
            ).all()
        )
        if ids
        else {}
    )
    result = []
    for family, actor, sources in rows:
        meals = []
        for kind, ref in (sources or {}).items():
            if ref.get("kind") == "reference":
                meals.extend(m for m in previews.get(ref["id"], []) if m["meal_type"] == kind)
        result.append((family, actor, meals))
    return result

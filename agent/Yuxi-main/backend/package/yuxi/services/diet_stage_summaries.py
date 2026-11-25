"""我的家批量读取阶段进度，不在首页调用模型。"""

from sqlalchemy import and_, select

from yuxi.services.diet_stage_types import stage_today
from yuxi.storage.postgres.models_diet_stage import DietActionWeek, DietStage


async def family_stage_summaries(session, family_id):
    """单次查询当前家庭所有未结束阶段及本周行动。"""
    today = stage_today()
    rows = await session.execute(
        select(DietStage, DietActionWeek)
        .outerjoin(
            DietActionWeek,
            and_(
                DietActionWeek.stage_id == DietStage.id,
                DietActionWeek.starts_on <= today,
                DietActionWeek.ends_on > today,
            ),
        )
        .where(DietStage.family_id == family_id, DietStage.status == "active")
    )
    return {
        stage.member_id: {
            "goals": stage.goals,
            "elapsed": max(0, (today - stage.starts_on).days) + 1,
            "due": today >= stage.review_on,
            "completed": sum(item["count"] >= item["target"] for item in week.actions) if week else 0,
            "total": len(week.actions) if week else 0,
        }
        for stage, week in rows
    }

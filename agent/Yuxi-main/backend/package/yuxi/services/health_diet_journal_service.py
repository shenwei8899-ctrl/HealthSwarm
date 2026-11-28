"""饮食日历按实际用餐日期读取同一套已确认记录。"""

from datetime import datetime, time, timedelta, timezone

from yuxi.repositories.health_diet_analysis_repository import HealthDietAnalysisRepository
from yuxi.repositories.health_vision_repository import HealthVisionRepository
from yuxi.storage.postgres.manager import pg_manager
from yuxi.utils.datetime_utils import format_utc_datetime


async def read_diet_journal(uid, member_id, day):
    """完整读取所选日所在周，保留来源校验并排除已撤销记录。"""
    start_day = day - timedelta(days=day.weekday())
    start = datetime.combine(start_day, time(), timezone(timedelta(hours=8)))
    async with pg_manager.get_async_session_context() as session:
        await HealthVisionRepository(session).authorize(member_id, uid, "diet_edit")
        sources, _feedback, invalidated = await HealthDietAnalysisRepository(session).period_sources(
            uid, member_id, start, start + timedelta(days=7)
        )
        dates = set()
        records = []
        for record, confirmation in sources:
            eaten = datetime.fromisoformat(record.snapshot["meal"]["eaten_at"].replace("Z", "+00:00"))
            eaten_day = eaten.astimezone(start.tzinfo).date()
            dates.add(eaten_day.isoformat())
            if eaten_day == day:
                records.append(
                    {
                        "id": record.id,
                        "member_id": record.member_id,
                        "source_version": record.version or confirmation.draft_version,
                        "snapshot": record.snapshot,
                        "created_at": format_utc_datetime(record.created_at),
                    }
                )
        return {"records": records, "recorded_dates": sorted(dates), "excluded_count": invalidated}

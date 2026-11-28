"""以现有有效记餐确认投影餐单保护状态，不新增全家用餐事实。"""

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import DateTime, cast, func, select
from sqlalchemy.dialects.postgresql import JSONB

from yuxi.storage.postgres.models_business import FamilyArchive
from yuxi.storage.postgres.models_health import DietLog, HealthFamilyProfileLink, VisionConfirmation, VisionDraft


class MealExecutionRepository:
    """调用方先核对家庭权限；仅返回本餐是否有记录，不公开个人摄入。"""

    def __init__(self, session):
        self.session = session

    async def protected_meals(self, family_id, day, archive, *, lock=False):
        """有效日记按上海日期及原餐单成员匹配，写入与既有记餐共用家庭锁。"""
        if lock:
            await self.session.scalar(select(FamilyArchive).where(FamilyArchive.id == family_id).with_for_update())
        members = {
            kind: {str(m["id"]) for m in meal.get("members", [])}
            for kind, meal in archive.items()
            if kind in {"breakfast", "lunch", "dinner"}
        }
        ids = set().union(*members.values()) if members else set()
        if not ids:
            return set()
        start = datetime.combine(day, time(), ZoneInfo("Asia/Shanghai"))
        eaten_at = cast(DietLog.snapshot["meal"]["eaten_at"].as_string(), DateTime(timezone=True))
        kind = DietLog.snapshot["meal"]["meal_type"].as_string()
        rows = await self.session.execute(
            select(kind, HealthFamilyProfileLink.source_member_id)
            .join(VisionConfirmation, DietLog.confirmation_id == VisionConfirmation.id)
            .join(VisionDraft, VisionConfirmation.draft_id == VisionDraft.id)
            .join(HealthFamilyProfileLink, DietLog.member_id == HealthFamilyProfileLink.member_id)
            .where(
                HealthFamilyProfileLink.family_id == family_id,
                HealthFamilyProfileLink.source_member_id.in_(ids),
                eaten_at >= start,
                eaten_at < start + timedelta(days=1),
                kind.in_(members),
                VisionConfirmation.kind == "meal",
                VisionDraft.kind == "meal",
                VisionConfirmation.member_id == DietLog.member_id,
                VisionDraft.member_id == DietLog.member_id,
                VisionDraft.review_status == "confirmed",
                VisionDraft.version == VisionConfirmation.draft_version,
                cast(VisionConfirmation.target_ids, JSONB).contains(func.jsonb_build_array(DietLog.id)),
            )
            .distinct()
        )
        return {meal for meal, member_id in rows if member_id in members.get(meal, set())}

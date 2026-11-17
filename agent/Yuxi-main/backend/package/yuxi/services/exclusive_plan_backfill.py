"""从已确认的家庭档案自动准备首次专属计划。"""

from uuid import NAMESPACE_URL, uuid5

from fastapi import HTTPException
from loguru import logger
from sqlalchemy import and_, or_, select

from yuxi.services.exclusive_plan_service import PREVIEW_POLICY, start_exclusive_plan
from yuxi.services.exclusive_plan_types import ExclusivePlanInput
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.services.miniapp_profile_types import miniapp_onboarding_ready
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_business import FamilyArchive, FamilyMember
from yuxi.storage.postgres.models_health import HealthExclusivePlanGroup

PAGE_SIZE = 50
START_LIMIT = 8


async def prepare_missing_exclusive_plans(ctx):
    """首次建档和存量家庭共用按主键分页的任务入口。"""
    cursor, started = "", 0
    while started < START_LIMIT:
        owners, cursor = await eligible_owners(cursor)
        if cursor is None:
            return
        for fid, uid in owners:
            request_id = uuid5(NAMESPACE_URL, f"exclusive-plan:{PREVIEW_POLICY['version']}:first:{fid}:{uid}")
            try:
                result = await start_exclusive_plan(
                    uid,
                    fid,
                    ExclusivePlanInput(client_request_id=request_id),
                    only_missing=True,
                )
            except HealthVisionError as error:
                if error.status >= 500 and error.code not in {
                    "daily_member_sources_unavailable",
                    "daily_profile_source_unavailable",
                    "daily_rules_unavailable",
                    "exclusive_plan_rules_missing",
                    "daily_dependencies_not_ready",
                    "consultation_unavailable",
                }:
                    raise
                logger.debug("Exclusive plan backfill skipped: code={}", error.code)
                continue
            except HTTPException as error:
                if error.status_code not in {403, 404}:
                    raise
                continue
            if result is not None:
                started += 1
                if started == START_LIMIT:
                    return


async def eligible_owners(cursor):
    """已确认本人档案是补跑依据，实际生成仍校验该家庭全部就餐成员。"""
    existing = select(HealthExclusivePlanGroup.id).where(
        HealthExclusivePlanGroup.actor_uid == FamilyArchive.owner_uid,
        HealthExclusivePlanGroup.family_id == FamilyArchive.id,
        or_(
            HealthExclusivePlanGroup.policy["version"].as_string() == PREVIEW_POLICY["version"],
            and_(
                HealthExclusivePlanGroup.policy["version"].as_string() != "agent-preview-v1",
                HealthExclusivePlanGroup.status.notin_(("failed", "stale")),
            ),
        ),
    )
    async with pg_manager.get_async_session_context() as session:
        rows = (
            await session.execute(
                select(FamilyArchive.id, FamilyArchive.owner_uid, FamilyMember)
                .join(
                    FamilyMember,
                    and_(
                        FamilyMember.family_id == FamilyArchive.id,
                        FamilyMember.subject_uid == FamilyArchive.owner_uid,
                    ),
                )
                .where(
                    FamilyArchive.id > cursor,
                    FamilyArchive.archived_at.is_(None),
                    FamilyMember.is_active.is_(True),
                    FamilyMember.confirmed_version == FamilyMember.version,
                    ~existing.exists(),
                )
                .order_by(FamilyArchive.id)
                .limit(PAGE_SIZE)
            )
        ).all()
        owners = [(fid, uid) for fid, uid, member in rows if miniapp_onboarding_ready(member, None)]
        return owners, rows[-1][0] if rows else None

"""专业导入入口的当前投影与受权原始来源上下文。"""

from yuxi.repositories.health_family_profile_repository import HealthFamilyProfileRepository
from yuxi.repositories.health_quality_repository import HealthQualityRepository
from yuxi.repositories.health_vision_repository import HealthVisionRepository
from yuxi.services.health_evidence_service import require_evidence_admin
from yuxi.storage.postgres.manager import pg_manager


async def read_profile_import_context(uid, member_id, *, limit=20, offset=0):
    """同一事务分别核对专业投影权限与当前操作者的原始字段授权。"""
    async with pg_manager.get_async_session_context() as session:
        await require_evidence_admin(session, uid)
        health_repo = HealthVisionRepository(session)
        await health_repo.authorize(member_id, uid, "profile_edit", lock=True)
        await health_repo.authorize(member_id, uid, "profile_view")
        sources = await HealthFamilyProfileRepository(session).read_import_source(
            uid, member_id, limit=limit, offset=offset
        )
        profile = await HealthQualityRepository(session).profile_projection(member_id)
        return {
            "member_id": member_id,
            "current_profile": {
                "scope": "nutrition_safety_projection",
                **profile,
                "next_version": (profile["version"] or 0) + 1,
            },
            **sources,
        }

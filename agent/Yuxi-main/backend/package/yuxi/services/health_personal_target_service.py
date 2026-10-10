"""成员目标读取的当前投影、权限及版本事务。"""

from yuxi.repositories.health_quality_repository import HealthQualityRepository
from yuxi.repositories.health_vision_repository import HealthVisionRepository
from yuxi.services.health_quality_checks import external_projection
from yuxi.services.health_quality_types import ProfileProjection, QualityRules
from yuxi.services.health_personal_targets import calculate_personal_targets
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.storage.postgres.manager import pg_manager


async def read_personal_targets(uid, member_id, data):
    """来源最高版本在成员与规则锁下读取，不储存新的健康事实。"""
    async with pg_manager.get_async_session_context() as session:
        return await personal_targets_in_session(session, uid, member_id, data)


async def personal_targets_in_session(session, uid, member_id, data):
    """HTTP及Agent用例共享来源锁、当前版本和原计算Owner，不开嵌套事务。"""
    await HealthVisionRepository(session).authorize(member_id, uid, "profile_view", lock=True)
    repo = HealthQualityRepository(session)
    profile = await repo.profile_projection(member_id)
    rules = external_projection(await repo.rules(data.rule_code, lock=True), "rules", data.rule_code)
    sources = {
        "profile": {k: profile[k] for k in ("id", "version", "content_hash", "status", "reason")},
        "rules": {
            "rule_code": data.rule_code,
            **{k: rules[k] for k in ("id", "version", "content_hash", "status", "reason")},
        },
    }
    if profile["status"] != "ready" or rules["status"] != "ready":
        return {"status": "not_ready", "reason": "confirmed_profile_or_approved_rules_required", "sources": sources}
    if profile["version"] != data.profile_version or rules["version"] != data.rule_version:
        raise HealthVisionError("source_version_conflict", "档案或规则版本已变化，请刷新个人目标", 409)
    result = calculate_personal_targets(
        ProfileProjection.model_validate(profile["payload"]),
        QualityRules.model_validate(rules["payload"]),
        weight_source_missing=bool(profile["attestation"].get("family_profile_source"))
        and not profile["attestation"].get("weight_measurement_source"),
    )
    return {
        **result,
        "sources": sources,
        "attestations": {"profile": profile["attestation"], "rules": rules["attestation"]},
        "professional_review": "not_a_professional_decision",
    }

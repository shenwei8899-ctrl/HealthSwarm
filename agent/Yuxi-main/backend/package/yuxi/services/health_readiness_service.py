"""按已实现用途汇总诊断；执行授权和专业判断由原业务Owner继续拥有。"""

import asyncio

from yuxi.repositories.health_evidence_repository import HealthEvidenceRepository
from yuxi.repositories.health_quality_repository import HealthQualityRepository
from yuxi.repositories.health_vision_repository import HealthVisionRepository
from yuxi.repositories.skill_repository import SkillRepository
from yuxi.services.health_agent_roles import (
    CONSULTATION_SKILLS,
    PLANNER_SKILLS,
    ANALYST_SKILLS,
    QUALITY_SKILLS,
    PURCHASE_SKILLS,
    consultation_skill_snapshot,
)
from yuxi.services.health_capability_service import member_capabilities
from yuxi.services.health_readiness_types import (
    HealthEntryReadiness,
    HealthMemberReadiness,
    HealthRuntimeDependency,
    HealthRoleVersion,
)
from yuxi.services.health_vision_service import health_vision_service
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.services.readiness_service import READINESS_PROBE_TIMEOUT_SECONDS, get_readiness
from yuxi.storage.minio import get_minio_client
from yuxi.storage.postgres.manager import pg_manager


async def member_readiness(uid: str, member_id: str) -> HealthMemberReadiness:
    """先验证成员可见性，再返回当前账号的入口降级和允许路径。"""
    capabilities = await member_capabilities(uid, member_id)
    runtime = await health_runtime_readiness(include_storage=True)
    async with pg_manager.get_async_session_context() as session:
        health = HealthVisionRepository(session)
        _, scopes = await health.visible_member_scopes(member_id, uid)
        catalogue = {
            "nutrition": await health.has_published_nutrition(),
            "rules": await HealthQualityRepository(session).has_current_rules(),
            "knowledge_mapping": await HealthEvidenceRepository(session).has_current_sources(),
        }
        configuration = await health_vision_service.configuration(session)
        purpose_skills = {
            "consultation": CONSULTATION_SKILLS,
            "meal_plan": PLANNER_SKILLS,
            "diet_analysis": ANALYST_SKILLS,
            "quality_review": QUALITY_SKILLS,
            "purchase": PURCHASE_SKILLS,
        }
        role_versions = {}
        for required in purpose_skills.values():
            metadata = consultation_skill_snapshot(required)["skill_metadata"]
            for slug, source in metadata.items():
                registered = await SkillRepository(session).get_by_slug(slug)
                matching = (
                    registered is not None
                    and registered.source_type == "builtin"
                    and registered.enabled
                    and registered.version == source["version"]
                    and registered.content_hash == source["content_hash"]
                )
                role_versions[slug] = HealthRoleVersion(
                    published_version=source["version"],
                    registered_version=registered.version if registered else None,
                    status="available" if matching else "unavailable",
                )
        manual = {
            "manual_report": "profile_edit" in scopes and runtime["postgres"].status == "available",
            "manual_meal": "diet_edit" in scopes and runtime["postgres"].status == "available",
        }
        entries = []
        for task in capabilities.tasks:
            entry = HealthEntryReadiness(entry_type=task.task_type, status=task.status, reason_code=task.reason_code)
            # 未授权、配置或外部契约原因优先，避免用运行摘要覆盖真正门禁。
            if task.status != "unavailable":
                entry.missing_dependencies = [
                    key for key in ("postgres", "redis", "worker") if runtime[key].status == "unavailable"
                ]
                if any(role_versions[slug].status == "unavailable" for slug in purpose_skills[task.purpose]):
                    entry.missing_dependencies.append("role_version")
                if task.task_type in {
                    "meal_preview",
                    "initial_meal_preview",
                    "family_meal_revision",
                    "safe_meal_revision",
                    "quality_check",
                }:
                    if not capabilities.dependencies.published_recipes:
                        entry.missing_dependencies.append("published_recipes")
                    if not catalogue["nutrition"]:
                        entry.missing_dependencies.append("nutrition")
                if task.task_type in {
                    "initial_meal_preview",
                    "family_meal_revision",
                    "safe_meal_revision",
                    "quality_check",
                }:
                    if capabilities.dependencies.profile_projection.status != "ready":
                        entry.missing_dependencies.append("profile_projection")
                    if not catalogue["rules"]:
                        entry.missing_dependencies.append("rules")
                if entry.missing_dependencies:
                    entry.status, entry.reason_code = "unavailable", "dependency_not_ready"
                    if any(key in entry.missing_dependencies for key in ("postgres", "redis", "worker")):
                        entry.allowed_actions.append("retry")
                elif entry.status == "needs_input":
                    entry.allowed_actions.append("complete_selection")
            entries.append(entry)

        for kind, required_scopes in (("report", {"report_upload", "ai_use"}), ("meal", {"diet_edit", "ai_use"})):
            entry = HealthEntryReadiness(entry_type=f"{kind}_photo", status="unavailable")
            authorized = required_scopes.issubset(scopes)
            if authorized:
                entry.missing_dependencies = [key for key, value in runtime.items() if value.status == "unavailable"]
            if not authorized:
                entry.reason_code = "missing_scopes"
            elif not configuration[kind]["available"]:
                entry.reason_code = "configuration_unavailable"
                entry.configuration_reason_code = configuration[kind]["reason_code"]
            else:
                try:
                    await health.require_consent(
                        member_id,
                        uid,
                        kind,
                        {
                            "processor": configuration[kind]["processor"],
                            "policy_version": configuration["policy_version"],
                        },
                    )
                except HealthVisionError as error:
                    if error.code != "consent_required":
                        raise
                    entry.reason_code = "consent_required"
                else:
                    entry.status = "unavailable" if entry.missing_dependencies else "available"
                    entry.reason_code = "dependency_not_ready" if entry.missing_dependencies else None
                    if entry.missing_dependencies:
                        entry.allowed_actions.append("retry")
            if entry.status == "unavailable" and manual[f"manual_{kind}"]:
                entry.allowed_actions.append(f"manual_{kind}")
            entries.append(entry)
        for entry_type, allowed in manual.items():
            entries.append(
                HealthEntryReadiness(
                    entry_type=entry_type,
                    status="available" if allowed else "unavailable",
                    reason_code=None
                    if allowed
                    else "missing_scopes"
                    if runtime["postgres"].status == "available"
                    else "dependency_not_ready",
                )
            )
    return HealthMemberReadiness(
        capabilities=capabilities, runtime=runtime, catalogue=catalogue, entries=entries, role_versions=role_versions
    )


async def health_runtime_readiness(*, include_storage: bool = False) -> dict[str, HealthRuntimeDependency]:
    """复用核心短缓存探针；存储只在真正消费照片的诊断中探测。"""
    core = await get_readiness(startup_complete=True)
    result = {
        key: HealthRuntimeDependency(status="available" if core["checks"][key]["status"] == "ok" else "unavailable")
        for key in ("postgres", "redis", "worker")
    }
    if include_storage:
        try:
            await asyncio.wait_for(
                get_minio_client().probe_access(READINESS_PROBE_TIMEOUT_SECONDS),
                timeout=READINESS_PROBE_TIMEOUT_SECONDS * 2 + 0.1,
            )
        except Exception:
            result["object_storage"] = HealthRuntimeDependency(status="unavailable")
        else:
            result["object_storage"] = HealthRuntimeDependency(status="available")
    return result


async def health_task_runtime_blockers(uid: str, member_id: str) -> list[str]:
    """创建Agent线程前重验成员AI授权；故障诊断本身不授予执行权限。"""
    async with pg_manager.get_async_session_context() as session:
        await HealthVisionRepository(session).authorize(member_id, uid, "ai_use")
    runtime = await health_runtime_readiness()
    return [key for key, value in runtime.items() if value.status == "unavailable"]

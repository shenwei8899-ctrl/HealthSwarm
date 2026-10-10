"""从现有Owner读取成员任务公共前置，不调用会修复状态的业务读取。"""

from yuxi.repositories.agent_repository import AgentRepository
from yuxi.repositories.health_consultation_repository import (
    ANALYST_SLUG,
    CONSULTATION_SLUG,
    HEALTH_AGENT_BACKENDS,
    PLANNER_SLUG,
    PURCHASE_SLUG,
    QUALITY_SLUG,
)
from yuxi.repositories.health_quality_repository import HealthQualityRepository
from yuxi.repositories.health_vision_repository import HealthVisionRepository
from yuxi.repositories.skill_repository import SkillRepository
from yuxi.services.health_agent_roles import (
    ANALYST_SKILLS,
    CONSULTATION_SKILLS,
    PLANNER_SKILLS,
    PURCHASE_SKILLS,
    QUALITY_SKILLS,
)
from yuxi.services.health_capability_types import (
    HealthCapabilityDependencies,
    HealthTaskCapability,
    MemberCapabilities,
    ProfileCapabilityDependency,
)
from yuxi.services.health_vision_service import health_vision_service
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.storage.postgres.manager import pg_manager


async def member_capabilities(uid: str, member_id: str) -> MemberCapabilities:
    """先证明成员可见性，再汇总本账号授权内的只读入口条件。"""
    async with pg_manager.get_async_session_context() as session:
        health = HealthVisionRepository(session)
        user, scopes = await health.visible_member_scopes(member_id, uid)
        configuration = await health_vision_service.configuration(session)
        agents, skills, purposes = {}, {}, {}
        tasks = []
        ordinary_scopes = ("ai_use", "report_view", "diet_edit")
        professional_scopes = ("ai_use", "diet_edit", "profile_view")
        selection_fields = {
            "initial_meal_preview": ("kind", "plan_date", "rule_code", "rule_version", "profile_versions", "meals"),
            "family_meal_revision": ("plan_id", "version", "rule_code", "rule_version", "profile_versions"),
            "safe_meal_revision": ("plan_id", "version", "rule_code", "rule_version", "profile_version"),
            "quality_check": ("plan_id", "version", "rule_code"),
            "purchase_requirements": ("adoption_id", "adoption_version", "plan_version"),
        }
        entries = (
            ("consultation", CONSULTATION_SLUG, CONSULTATION_SKILLS, "consultation", ordinary_scopes),
            ("meal_preview", PLANNER_SLUG, PLANNER_SKILLS, "meal_plan", ordinary_scopes),
            ("diet_analysis", ANALYST_SLUG, ANALYST_SKILLS, "diet_analysis", ("ai_use", "diet_edit")),
            ("initial_meal_preview", PLANNER_SLUG, PLANNER_SKILLS, "meal_plan", professional_scopes),
            ("family_meal_revision", PLANNER_SLUG, PLANNER_SKILLS, "meal_plan", professional_scopes),
            ("safe_meal_revision", PLANNER_SLUG, PLANNER_SKILLS, "meal_plan", professional_scopes),
            ("quality_check", QUALITY_SLUG, QUALITY_SKILLS, "quality_review", professional_scopes),
            ("purchase_requirements", PURCHASE_SLUG, PURCHASE_SKILLS, "purchase", ("ai_use", "diet_edit")),
        )
        for task_type, slug, required_skills, purpose, required_scopes in entries:
            missing = sorted(set(required_scopes) - scopes)
            inputs = [f"selection.{field}" for field in selection_fields.get(task_type, ())]
            if task_type == "diet_analysis":
                inputs = ["interaction.confirmed_meal_or_period"]
            elif task_type == "purchase_requirements":
                inputs.append("interaction.inventory_confirmation")
            capability = HealthTaskCapability(
                task_type=task_type,
                purpose=purpose,
                status="unavailable",
                missing_scopes=missing,
                required_inputs=inputs,
            )
            if missing:
                capability.reason_code = "missing_scopes"
                tasks.append(capability)
                continue

            if slug not in agents:
                agent = await AgentRepository(session).get_visible_by_slug(slug=slug, user=user, kind="main")
                agents[slug] = agent is not None and agent.backend_id == HEALTH_AGENT_BACKENDS[slug]
            if not agents[slug]:
                capability.reason_code = "agent_unavailable"
                tasks.append(capability)
                continue

            for skill_slug in required_skills:
                if skill_slug not in skills:
                    skill = await SkillRepository(session).get_by_slug(skill_slug)
                    skills[skill_slug] = skill is not None and skill.source_type == "builtin" and skill.enabled
            if not all(skills[skill_slug] for skill_slug in required_skills):
                capability.reason_code = "skill_unavailable"
                tasks.append(capability)
                continue

            approved = configuration[purpose]
            if not approved["available"]:
                capability.reason_code = "configuration_unavailable"
                capability.configuration_reason_code = approved["reason_code"]
                tasks.append(capability)
                continue

            if purpose not in purposes:
                try:
                    await health.require_consent(
                        member_id,
                        uid,
                        purpose,
                        {"processor": approved["processor"], "policy_version": configuration["policy_version"]},
                    )
                except HealthVisionError as error:
                    if error.code != "consent_required":
                        raise
                    purposes[purpose] = False
                else:
                    purposes[purpose] = True
            if not purposes[purpose]:
                capability.reason_code = "consent_required"
            elif task_type in selection_fields:
                capability.status = "needs_input"
                capability.reason_code = "selection_required"
            else:
                capability.status = "available"
            tasks.append(capability)

        for task_type in ("glucose_plan", "multi_day_plan", "automatic_family_coordination"):
            tasks.append(
                HealthTaskCapability(
                    task_type=task_type, status="unavailable", reason_code="external_contract_required"
                )
            )

        profile = ProfileCapabilityDependency(status="not_authorized", reason="missing_scopes")
        if "profile_view" in scopes:
            await health.authorize(member_id, uid, "profile_view")
            projection = await HealthQualityRepository(session).profile_projection(member_id)
            profile = ProfileCapabilityDependency(**{key: projection[key] for key in ("status", "reason", "version")})
        return MemberCapabilities(
            member_id=member_id,
            tasks=tasks,
            dependencies=HealthCapabilityDependencies(
                profile_projection=profile, published_recipes=await health.has_published_recipes()
            ),
        )

"""独立指标咨询的固定数据范围与技能就绪边界。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from test.unit.services.test_health_readiness import readiness_sources  # noqa: F401
from test.unit.services.test_health_capabilities import capability_sources  # noqa: F401
from yuxi.agents.context import BaseContext
from yuxi.services import health_consultation_service as consultation
from yuxi.services import health_readiness_service as readiness
from yuxi.services import health_capability_service as capabilities
from yuxi.services.health_agent_roles import INDICATOR_AGENT_SKILLS
from yuxi.services.health_vision_types import HealthVisionError


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "slug,tool,skill",
    [
        ("health-blood-glucose", "get_member_blood_glucose_records", "family-blood-glucose"),
        ("health-blood-lipids", "get_member_blood_lipids_records", "family-blood-lipids"),
        ("health-blood-pressure", "get_member_blood_pressure_records", "family-blood-pressure"),
    ],
)
async def test_indicator_context_discards_other_data_and_user_resources(monkeypatch, slug, tool, skill):
    """角色范围从服务固定，不接受前端或个人配置增加读写工具。"""
    approved = {"model": "synthetic/fixed", "processor": "synthetic", "policy_version": "synthetic"}
    monkeypatch.setattr(consultation, "require_consultation", AsyncMock(return_value=(SimpleNamespace(), approved)))
    context = BaseContext(
        uid="actor",
        thread_id="thread",
        tools=["remember_member_fact"],
        skills=["family-nutritionist"],
        preload_skills=["family-nutritionist"],
        system_prompt="任意用户覆盖",
        knowledges=["private"],
        mcps=["private"],
    )
    run = SimpleNamespace(agent_slug=slug, input_payload={"health_processing": approved})
    result = await consultation.prepare_consultation_context(context, None, run)
    assert result.tools == [tool, "query_reviewed_nutrition_knowledge", "query_family_nutrition_knowledge"]
    assert result.skills == result.preload_skills == [skill]
    assert result.system_prompt == consultation.INDICATOR_PROMPTS[slug]
    assert result.knowledges == result.mcps == []
    assert result._skill_runtime_snapshot["effective_skills"] == [skill]
    assert result.model == "synthetic/fixed" and result._runtime_prepared


@pytest.mark.asyncio
@pytest.mark.parametrize("slug", list(INDICATOR_AGENT_SKILLS))
async def test_indicator_requires_its_own_enabled_builtin_skill(monkeypatch, slug):
    """综合咨询技能可用不能代替被停用的专用角色技能。"""
    binding = SimpleNamespace(member_id="member", conversation_id=1)
    monkeypatch.setattr(consultation.HealthConsultationRepository, "authorize", AsyncMock(return_value=binding))
    approved = {"available": True, "model": "synthetic/fixed", "processor": "synthetic"}
    monkeypatch.setattr(
        consultation.health_vision_service,
        "configuration",
        AsyncMock(return_value={"policy_version": "synthetic", "consultation": approved}),
    )
    monkeypatch.setattr(consultation.HealthVisionRepository, "require_consent", AsyncMock())
    lookup = AsyncMock(return_value=SimpleNamespace(source_type="builtin", enabled=False))
    monkeypatch.setattr(consultation.SkillRepository, "get_by_slug", lookup)
    session = SimpleNamespace(get=AsyncMock(return_value=SimpleNamespace(agent_id=slug)))
    with pytest.raises(HealthVisionError, match="skill_unavailable"):
        await consultation.require_consultation(session, "actor", "thread")
    lookup.assert_awaited_once_with(INDICATOR_AGENT_SKILLS[slug][0])


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "task_type,skill",
    [
        ("blood_glucose_review", "family-blood-glucose"),
        ("blood_lipids_review", "family-blood-lipids"),
        ("blood_pressure_review", "family-blood-pressure"),
    ],
)
async def test_indicator_version_mismatch_only_disables_selected_role(readiness_sources, task_type, skill):  # noqa: F811
    """每个独立入口按其发布版本判断，不依赖综合咨询版本。"""
    sources = readiness_sources
    sources.skills[skill].version = "obsolete"
    result = await readiness.member_readiness(sources.uid, sources.member_id)
    entries = {entry.entry_type: entry for entry in result.entries}
    assert entries[task_type].status == "unavailable"
    assert entries[task_type].missing_dependencies == ["role_version"]
    assert entries["consultation"].status == "available"
    for other in {"blood_glucose_review", "blood_lipids_review", "blood_pressure_review"} - {task_type}:
        assert entries[other].status == "available"


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["missing_scope", "foreign_owner", "relative"])
async def test_indicator_capability_rejects_unreadable_measurement_scope(capability_sources, case):  # noqa: F811
    """入口提示与本人实测读取的权限一致，不把无权成员显示为可用。"""
    sources = capability_sources
    if case == "missing_scope":
        user, scopes = sources.health.visible_member_scopes.return_value
        sources.health.visible_member_scopes.return_value = (user, set(scopes) - {"profile_view"})
    else:
        member = sources.health.authorize.return_value
        if case == "foreign_owner":
            member.owner_uid = "other"
        else:
            member.relationship_label = "母亲"
    result = await capabilities.member_capabilities(sources.uid, sources.member_id)
    tasks = {task.task_type: task for task in result.tasks}
    for task_type in ("blood_glucose_review", "blood_lipids_review", "blood_pressure_review"):
        assert tasks[task_type].status == "unavailable"
        assert tasks[task_type].reason_code == ("missing_scopes" if case == "missing_scope" else "self_member_required")
    assert tasks["consultation"].status == "available"

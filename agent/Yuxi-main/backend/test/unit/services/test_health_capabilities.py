"""成员能力公共前置的正负控，不以入口提示代替真实授权证据。"""

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from yuxi.repositories.health_consultation_repository import HEALTH_AGENT_BACKENDS
from yuxi.repositories.health_vision_repository import HealthVisionRepository
from yuxi.services import health_capability_service as service_module
from yuxi.services.health_vision_types import HEALTH_SCOPES, HealthVisionError


@pytest.fixture
def capability_sources(monkeypatch):
    """固定合成来源，能力逻辑仍实际执行并产生公开DTO。"""
    user = object()
    health = SimpleNamespace(
        visible_member_scopes=AsyncMock(return_value=(user, HEALTH_SCOPES)),
        require_consent=AsyncMock(),
        authorize=AsyncMock(),
        has_published_recipes=AsyncMock(return_value=False),
    )
    agents = {slug: SimpleNamespace(backend_id=backend) for slug, backend in HEALTH_AGENT_BACKENDS.items()}
    agent_repository = SimpleNamespace(
        get_visible_by_slug=AsyncMock(side_effect=lambda **kwargs: agents[kwargs["slug"]])
    )
    skills = {
        slug: SimpleNamespace(source_type="builtin", enabled=True)
        for slug in (
            "family-nutritionist",
            "family-meal-planner",
            "family-diet-analyst",
            "family-quality-review",
            "family-purchase",
        )
    }
    skill_repository = SimpleNamespace(get_by_slug=AsyncMock(side_effect=lambda slug: skills[slug]))
    configuration = {
        "policy_version": "synthetic-policy-1",
        "model_options": [{"spec": "must-not-leak"}],
        **{
            kind: {
                "available": True,
                "reason": None,
                "reason_code": None,
                "model": "synthetic:model-must-not-leak",
                "processor": f"synthetic-private-{kind}",
            }
            for kind in ("report", "meal", "consultation", "meal_plan", "diet_analysis", "quality_review", "purchase")
        },
    }
    configured = AsyncMock(return_value=configuration)
    quality = SimpleNamespace(
        profile_projection=AsyncMock(
            return_value={
                "status": "not_ready",
                "reason": "not_delivered",
                "version": None,
                "payload": {"private-health": "must-not-leak"},
                "attestation": {"proof": "must-not-leak"},
            }
        )
    )

    @asynccontextmanager
    async def session_context():
        """会话无写入方法，误调用业务写入口会直接失败。"""
        yield object()

    monkeypatch.setattr(service_module.pg_manager, "get_async_session_context", session_context)
    monkeypatch.setattr(service_module, "HealthVisionRepository", Mock(return_value=health))
    monkeypatch.setattr(service_module, "AgentRepository", Mock(return_value=agent_repository))
    monkeypatch.setattr(service_module, "SkillRepository", Mock(return_value=skill_repository))
    monkeypatch.setattr(service_module, "HealthQualityRepository", Mock(return_value=quality))
    monkeypatch.setattr(service_module.health_vision_service, "configuration", configured)
    return SimpleNamespace(
        health=health,
        user=user,
        agents=agents,
        agent_repository=agent_repository,
        skills=skills,
        configuration=configuration,
        configured=configured,
        quality=quality,
        member_id=str(uuid4()),
        uid="synthetic-actor",
    )


async def test_missing_professional_sources_keep_ordinary_available_and_selection_explicit(capability_sources):
    """缺安全投影与菜谱的普通入口仍按自己的门禁判断。"""
    sources = capability_sources
    result = await service_module.member_capabilities(sources.uid, sources.member_id)
    tasks = {task.task_type: task for task in result.tasks}
    assert {task_type for task_type, task in tasks.items() if task.status == "available"} == {
        "consultation",
        "meal_preview",
        "diet_analysis",
    }
    assert {task_type for task_type, task in tasks.items() if task.status == "needs_input"} == {
        "initial_meal_preview",
        "family_meal_revision",
        "safe_meal_revision",
        "quality_check",
        "purchase_requirements",
    }
    assert all(task.reason_code == "selection_required" for task in result.tasks if task.status == "needs_input")
    assert {task_type for task_type, task in tasks.items() if task.reason_code == "external_contract_required"} == {
        "glucose_plan",
        "multi_day_plan",
        "automatic_family_coordination",
    }
    assert len(tasks) == 11
    assert {task_type: (task.purpose, task.required_inputs) for task_type, task in tasks.items()} == {
        "consultation": ("consultation", []),
        "meal_preview": ("meal_plan", []),
        "diet_analysis": ("diet_analysis", ["interaction.confirmed_meal_or_period"]),
        "initial_meal_preview": (
            "meal_plan",
            [
                "selection.kind",
                "selection.plan_date",
                "selection.rule_code",
                "selection.rule_version",
                "selection.profile_versions",
                "selection.meals",
            ],
        ),
        "family_meal_revision": (
            "meal_plan",
            [
                "selection.plan_id",
                "selection.version",
                "selection.rule_code",
                "selection.rule_version",
                "selection.profile_versions",
            ],
        ),
        "safe_meal_revision": (
            "meal_plan",
            [
                "selection.plan_id",
                "selection.version",
                "selection.rule_code",
                "selection.rule_version",
                "selection.profile_version",
            ],
        ),
        "quality_check": ("quality_review", ["selection.plan_id", "selection.version", "selection.rule_code"]),
        "purchase_requirements": (
            "purchase",
            [
                "selection.adoption_id",
                "selection.adoption_version",
                "selection.plan_version",
                "interaction.inventory_confirmation",
            ],
        ),
        "glucose_plan": (None, []),
        "multi_day_plan": (None, []),
        "automatic_family_coordination": (None, []),
    }
    assert result.dependencies.model_dump() == {
        "profile_projection": {"status": "not_ready", "reason": "not_delivered", "version": None},
        "published_recipes": False,
        "rules": {"status": "needs_input", "reason": "selection_required", "version": None},
    }
    assert "must-not-leak" not in result.model_dump_json()
    assert {call.kwargs["kind"] for call in sources.agent_repository.get_visible_by_slug.await_args_list} == {"main"}
    assert all(
        call.kwargs["user"] is sources.user for call in sources.agent_repository.get_visible_by_slug.await_args_list
    )
    assert {call.args[2] for call in sources.health.require_consent.await_args_list} == {
        "consultation",
        "meal_plan",
        "diet_analysis",
        "quality_review",
        "purchase",
    }


async def test_invisible_member_fails_before_configuration_or_private_dependencies(capability_sources):
    """不可见成员不给本账号缺权明细，也不能触发私有来源读取。"""
    sources = capability_sources
    sources.health.visible_member_scopes.side_effect = HealthVisionError("not_found", "不可见", 404)
    with pytest.raises(HealthVisionError) as error:
        await service_module.member_capabilities(sources.uid, sources.member_id)
    assert (error.value.code, error.value.status) == ("not_found", 404)
    sources.configured.assert_not_awaited()
    sources.quality.profile_projection.assert_not_awaited()
    sources.health.has_published_recipes.assert_not_awaited()


async def test_visible_member_missing_scopes_precede_resources_and_profile_is_unread(capability_sources):
    """有效但不足的授权只公开本人缺口，不借管理员或角色资源补权。"""
    sources = capability_sources
    sources.health.visible_member_scopes.return_value = (sources.user, {"diet_edit"})
    result = await service_module.member_capabilities(sources.uid, sources.member_id)
    tasks = {task.task_type: task for task in result.tasks}
    assert tasks["consultation"].missing_scopes == ["ai_use", "report_view"]
    assert tasks["diet_analysis"].missing_scopes == ["ai_use"]
    assert tasks["quality_check"].missing_scopes == ["ai_use", "profile_view"]
    assert all(task.reason_code == "missing_scopes" for task in result.tasks[:8])
    assert result.dependencies.profile_projection.model_dump() == {
        "status": "not_authorized",
        "reason": "missing_scopes",
        "version": None,
    }
    sources.agent_repository.get_visible_by_slug.assert_not_awaited()
    sources.quality.profile_projection.assert_not_awaited()
    sources.health.authorize.assert_not_awaited()


@pytest.mark.parametrize("agent", [None, SimpleNamespace(backend_id="GenericAgent")])
async def test_missing_or_wrong_fixed_agent_blocks_only_its_tasks(capability_sources, agent):
    """普通角色资源不能冒充固定健康后端。"""
    sources = capability_sources
    sources.agents["health-consultation"] = agent
    tasks = {
        task.task_type: task
        for task in (await service_module.member_capabilities(sources.uid, sources.member_id)).tasks
    }
    assert (tasks["consultation"].status, tasks["consultation"].reason_code) == ("unavailable", "agent_unavailable")
    assert tasks["meal_preview"].status == tasks["diet_analysis"].status == "available"


@pytest.mark.parametrize(
    "skill",
    [
        None,
        SimpleNamespace(source_type="personal", enabled=True),
        SimpleNamespace(source_type="builtin", enabled=False),
    ],
)
async def test_missing_nonbuiltin_or_disabled_skill_blocks_role(capability_sources, skill):
    """同名个人技能和禁用内置技能不能使当前角色可进入。"""
    sources = capability_sources
    sources.skills["family-nutritionist"] = skill
    tasks = {
        task.task_type: task
        for task in (await service_module.member_capabilities(sources.uid, sources.member_id)).tasks
    }
    assert (tasks["consultation"].status, tasks["consultation"].reason_code) == ("unavailable", "skill_unavailable")
    assert tasks["meal_preview"].status == "available"


async def test_configuration_reason_is_stable_and_purpose_specific(capability_sources):
    """一个用途审批变化只关闭相关任务，不把内部配置当能力响应。"""
    sources = capability_sources
    sources.configuration["meal_plan"].update(
        available=False, reason="synthetic-private-message", reason_code="processor_approval_changed"
    )
    result = await service_module.member_capabilities(sources.uid, sources.member_id)
    tasks = {task.task_type: task for task in result.tasks}
    assert tasks["consultation"].status == tasks["diet_analysis"].status == "available"
    for task_type in ("meal_preview", "initial_meal_preview", "family_meal_revision", "safe_meal_revision"):
        assert (tasks[task_type].status, tasks[task_type].reason_code, tasks[task_type].configuration_reason_code) == (
            "unavailable",
            "configuration_unavailable",
            "processor_approval_changed",
        )
    assert "synthetic-private-message" not in result.model_dump_json()


async def test_independent_consent_missing_blocks_only_its_purpose(capability_sources):
    """咨询同意不代替配餐同意，处理方和政策使用当前用途快照。"""
    sources = capability_sources

    async def consent(member_id, uid, purpose, processing):
        """独立用途缺同意，其他用途保留正控。"""
        assert (member_id, uid) == (sources.member_id, sources.uid)
        assert processing == {
            "processor": sources.configuration[purpose]["processor"],
            "policy_version": "synthetic-policy-1",
        }
        if purpose == "meal_plan":
            raise HealthVisionError("consent_required", "需要当前用途同意", 403)

    sources.health.require_consent.side_effect = consent
    tasks = {
        task.task_type: task
        for task in (await service_module.member_capabilities(sources.uid, sources.member_id)).tasks
    }
    assert (tasks["meal_preview"].status, tasks["meal_preview"].reason_code) == ("unavailable", "consent_required")
    assert tasks["consultation"].status == tasks["diet_analysis"].status == "available"
    assert tasks["purchase_requirements"].reason_code == "selection_required"


async def test_unexpected_consent_error_is_not_presented_as_missing_consent(capability_sources):
    """来源或授权错误不能被汇总器降成可解释但不真实的同意状态。"""
    sources = capability_sources
    sources.health.require_consent.side_effect = HealthVisionError("not_found", "撤权", 404)
    with pytest.raises(HealthVisionError) as error:
        await service_module.member_capabilities(sources.uid, sources.member_id)
    assert error.value.code == "not_found"


async def test_ready_profile_does_not_skip_selection_and_revoked_latest_is_preserved(capability_sources):
    """就绪投影不代表选定规则；最高撤回版本不能显示旧就绪状态。"""
    sources = capability_sources
    sources.quality.profile_projection.return_value.update(status="ready", reason=None, version=5)
    sources.health.has_published_recipes.return_value = True
    ready = await service_module.member_capabilities(sources.uid, sources.member_id)
    assert ready.dependencies.profile_projection.version == 5
    assert ready.dependencies.published_recipes is True
    assert all(task.reason_code == "selection_required" for task in ready.tasks if task.status == "needs_input")
    sources.quality.profile_projection.return_value.update(status="not_ready", reason="revoked", version=6)
    revoked = await service_module.member_capabilities(sources.uid, sources.member_id)
    assert revoked.dependencies.profile_projection.model_dump() == {
        "status": "not_ready",
        "reason": "revoked",
        "version": 6,
    }
    assert {task.task_type for task in revoked.tasks if task.status == "available"} == {
        "consultation",
        "meal_preview",
        "diet_analysis",
    }
    sources.health.authorize.assert_awaited_with(sources.member_id, sources.uid, "profile_view")


@pytest.mark.parametrize("scopes", [[], ["unknown"], ["ai_use", "unknown"], ["ai_use", 1], None, "ai_use"])
async def test_visibility_repository_rejects_empty_or_invalid_stored_scope(scopes):
    """持久化损坏或空授权不产生成员可见性。"""
    session = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(one_or_none=lambda: (object(), scopes))))
    with pytest.raises(HealthVisionError) as error:
        await HealthVisionRepository(session).visible_member_scopes(str(uuid4()), "synthetic-actor")
    assert (error.value.code, error.value.status) == ("not_found", 404)


async def test_visibility_repository_valid_scope_is_returned_without_implicit_owner_scope():
    """有效的最小授权原样返回，不自动扩成建档人或管理员权限。"""
    user = object()
    session = SimpleNamespace(
        execute=AsyncMock(return_value=SimpleNamespace(one_or_none=lambda: (user, ["diet_edit"])))
    )
    assert await HealthVisionRepository(session).visible_member_scopes(str(uuid4()), "synthetic-actor") == (
        user,
        {"diet_edit"},
    )


async def test_visibility_repository_no_matching_current_grant_is_not_found():
    """不存在、删除账号与已撤权都没有可见查询行，统一无权响应。"""
    session = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(one_or_none=lambda: None)))
    with pytest.raises(HealthVisionError) as error:
        await HealthVisionRepository(session).visible_member_scopes(str(uuid4()), "synthetic-actor")
    assert (error.value.code, error.value.status) == ("not_found", 404)

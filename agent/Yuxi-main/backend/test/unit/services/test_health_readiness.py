"""业务依赖诊断按入口的正负边界，复用现有授权和配置Owner。"""

import inspect
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from test.unit.services.test_health_capabilities import capability_sources  # noqa: F401
from yuxi.services import health_readiness_service as service
from yuxi.services import health_task_service as tasks
from yuxi.services.health_readiness_types import HealthRuntimeDependency
from yuxi.services.health_task_types import HealthTaskEntryInput
from yuxi.services.health_vision_types import HealthVisionError


@pytest.fixture
def readiness_sources(capability_sources, monkeypatch):  # noqa: F811
    """固定只读来源与运行快照，真正的能力和诊断代码继续执行。"""
    sources = capability_sources
    sources.health.has_published_nutrition = AsyncMock(return_value=False)
    sources.quality.has_current_rules = AsyncMock(return_value=False)
    evidence = SimpleNamespace(has_current_sources=AsyncMock(return_value=False))
    monkeypatch.setattr(service, "HealthVisionRepository", lambda _: sources.health)
    monkeypatch.setattr(service, "HealthQualityRepository", lambda _: sources.quality)
    monkeypatch.setattr(service, "HealthEvidenceRepository", lambda _: evidence)
    monkeypatch.setattr(
        service,
        "SkillRepository",
        lambda _: SimpleNamespace(get_by_slug=AsyncMock(side_effect=lambda slug: sources.skills[slug])),
    )
    for slug, metadata in service.consultation_skill_snapshot(tuple(sources.skills))["skill_metadata"].items():
        sources.skills[slug].version = metadata["version"]
        sources.skills[slug].content_hash = metadata["content_hash"]
    runtime = {
        key: HealthRuntimeDependency(status="available") for key in ("postgres", "redis", "worker", "object_storage")
    }
    sources.runtime = AsyncMock(return_value=runtime)
    monkeypatch.setattr(service, "health_runtime_readiness", sources.runtime)
    from yuxi.services import health_ai_budget_service, health_vision_service

    monkeypatch.setattr(health_vision_service, "current_health_model_info", AsyncMock(return_value=object()))

    monkeypatch.setattr(
        health_ai_budget_service,
        "model_budget_readiness",
        AsyncMock(return_value={"available": True, "reason_code": None, "reason": None}),
    )
    return sources


async def test_missing_catalogue_only_blocks_its_consumers(readiness_sources):
    """普通咨询和人工录入可用，专业规则缺失不冒充已交付。"""
    sources = readiness_sources
    result = await service.member_readiness(sources.uid, sources.member_id)
    entries = {entry.entry_type: entry for entry in result.entries}
    assert entries["consultation"].status == entries["diet_analysis"].status == "available"
    assert entries["manual_report"].status == entries["manual_meal"].status == "available"
    assert entries["meal_preview"].missing_dependencies == ["published_recipes", "nutrition"]
    assert entries["initial_meal_preview"].missing_dependencies == [
        "published_recipes",
        "nutrition",
        "profile_projection",
        "rules",
    ]
    assert entries["initial_meal_preview"].status == "unavailable"
    assert result.catalogue == {"nutrition": False, "rules": False, "knowledge_mapping": False}
    public = result.model_dump_json()
    assert "must-not-leak" not in public and "synthetic-private" not in public


@pytest.mark.parametrize("failed", ["object_storage", "redis", "worker", "postgres"])
async def test_runtime_failure_keeps_only_independent_entries(readiness_sources, failed):
    """对象存储不影响文本；队列故障不取消合法人工路径。"""
    sources = readiness_sources
    sources.runtime.return_value[failed] = HealthRuntimeDependency(status="unavailable")
    result = await service.member_readiness(sources.uid, sources.member_id)
    entries = {entry.entry_type: entry for entry in result.entries}
    assert entries["report_photo"].status == entries["meal_photo"].status == "unavailable"
    assert entries["meal_photo"].missing_dependencies == [failed]
    assert entries["consultation"].status == ("available" if failed == "object_storage" else "unavailable")
    assert entries["manual_meal"].status == ("unavailable" if failed == "postgres" else "available")
    assert entries["meal_photo"].allowed_actions == (["retry"] if failed == "postgres" else ["retry", "manual_meal"])


async def test_manual_path_requires_its_own_scope(readiness_sources):
    """只有AI使用权不能获得人工饮食或报告写入提示。"""
    sources = readiness_sources
    sources.health.visible_member_scopes.return_value = (sources.user, {"ai_use"})
    result = await service.member_readiness(sources.uid, sources.member_id)
    entries = {entry.entry_type: entry for entry in result.entries}
    assert entries["manual_meal"].status == entries["manual_report"].status == "unavailable"
    assert entries["report_photo"].reason_code == "missing_scopes"
    assert entries["report_photo"].allowed_actions == []
    sources.quality.profile_projection.assert_not_awaited()


async def test_selected_professional_sources_remain_explicit(readiness_sources):
    """目录存在只能进入选择，不能给出规则适用或方案批准。"""
    sources = readiness_sources
    sources.health.has_published_recipes.return_value = True
    sources.health.has_published_nutrition.return_value = True
    sources.quality.has_current_rules.return_value = True
    sources.quality.profile_projection.return_value = {"status": "ready", "reason": None, "version": 3}
    result = await service.member_readiness(sources.uid, sources.member_id)
    entry = next(entry for entry in result.entries if entry.entry_type == "initial_meal_preview")
    assert entry.status == "needs_input" and entry.reason_code == "selection_required"
    assert entry.allowed_actions == ["complete_selection"] and entry.missing_dependencies == []


async def test_role_version_mismatch_only_disables_its_role(readiness_sources):
    """PG登记与发布版本不一致时明确缺项，其他角色仍按自己的条件判断。"""
    sources = readiness_sources
    sources.skills["family-nutritionist"].version = "obsolete-version"
    result = await service.member_readiness(sources.uid, sources.member_id)
    entries = {entry.entry_type: entry for entry in result.entries}
    assert entries["consultation"].status == "unavailable" and entries["consultation"].missing_dependencies == [
        "role_version"
    ]
    assert entries["diet_analysis"].status == "available"
    assert result.role_versions["family-nutritionist"].status == "unavailable"
    assert result.role_versions["family-nutritionist"].registered_version == "obsolete-version"


async def test_invisible_member_never_probes_dependencies(readiness_sources):
    """跨账号和未知成员在任何运行或目录诊断前拒绝。"""
    sources = readiness_sources
    sources.health.visible_member_scopes.side_effect = HealthVisionError("not_found", "不可见", 404)
    with pytest.raises(HealthVisionError, match="不可见"):
        await service.member_readiness(sources.uid, sources.member_id)
    sources.runtime.assert_not_awaited()
    sources.health.has_published_nutrition.assert_not_awaited()


async def test_photo_consent_is_independent_and_configuration_is_sanitized(readiness_sources):
    """识图同意缺失时返回合法人工录入，不输出处理方或密钥。"""
    sources = readiness_sources

    async def consent(member, uid, purpose, snapshot):
        """只撤回饮食识图用途，普通用途维持原授权。"""
        if purpose == "meal":
            raise HealthVisionError("consent_required", "需同意", 403)

    sources.health.require_consent.side_effect = consent
    result = await service.member_readiness(sources.uid, sources.member_id)
    entry = next(entry for entry in result.entries if entry.entry_type == "meal_photo")
    assert entry.reason_code == "consent_required" and entry.allowed_actions == ["manual_meal"]


@pytest.mark.parametrize("storage_failure", [False, True])
async def test_storage_probe_returns_only_fixed_status(monkeypatch, storage_failure):
    """探针异常不透出地址和secret，且健康文本任务不探测存储。"""
    monkeypatch.setattr(
        service,
        "get_readiness",
        AsyncMock(return_value={"checks": {key: {"status": "ok"} for key in ("postgres", "redis", "worker")}}),
    )
    probe = AsyncMock(side_effect=RuntimeError("secret-private-endpoint") if storage_failure else None)
    monkeypatch.setattr(service, "get_minio_client", lambda: SimpleNamespace(probe_access=probe))
    text_runtime = await service.health_runtime_readiness()
    assert "object_storage" not in text_runtime
    probe.assert_not_awaited()
    runtime = await service.health_runtime_readiness(include_storage=True)
    assert runtime["object_storage"].status == ("unavailable" if storage_failure else "available")
    assert "secret" not in str(runtime)


async def test_task_entry_fault_is_readonly_and_guard_removal_is_detected(monkeypatch):
    """队列故障不创建线程；移除guard的负控必须命中同一个业务oracle。"""
    member, thread = str(uuid4()), str(uuid4())
    data = HealthTaskEntryInput.model_validate({"task_type": "consultation", "client_request_id": uuid4()})
    monkeypatch.setattr(tasks, "health_task_runtime_blockers", AsyncMock(return_value=["worker"]))
    creator = AsyncMock(return_value={"thread_id": thread, "agent_slug": "health-consultation"})
    monkeypatch.setattr(tasks, "create_consultation", creator)
    result = await tasks.create_health_task_entry("actor", member, data)

    def oracle(receipt):
        """独立要求故障终态和空线程，不能仅依赖mock调用次数。"""
        assert receipt.entry_status == "dependency_not_ready" and receipt.thread_id is None, (
            "runtime fault created a thread"
        )
        assert receipt.missing_dependencies == ["worker"]

    oracle(result)
    creator.assert_not_awaited()
    source = inspect.getsource(tasks.create_health_task_entry).replace("if missing_runtime:", "if False:", 1)
    namespace = dict(tasks.__dict__)
    exec(compile(source, "<removed-runtime-guard>", "exec"), namespace)
    with pytest.raises(AssertionError, match="runtime fault created a thread"):
        oracle(await namespace["create_health_task_entry"]("actor", member, data))


async def test_task_runtime_auth_precedes_probe(readiness_sources):
    """撤权不因读取就绪快照获得新的执行入口。"""
    sources = readiness_sources
    sources.health.authorize.side_effect = HealthVisionError("forbidden", "已撤权", 403)
    with pytest.raises(HealthVisionError, match="已撤权"):
        await service.health_task_runtime_blockers(sources.uid, sources.member_id)
    sources.runtime.assert_not_awaited()


def test_published_recipe_readiness_uses_actual_catalog_classifications():
    """独立发布目录不写回规则，缺失或改hash仍明确不能预览。"""
    from copy import deepcopy
    from test.unit.services.test_health_initial_meal_generation import initial_fixture
    from yuxi.services.health_quality_types import SwapRecipeClassification
    from yuxi.services.health_readiness import nutrition_readiness

    _, current, recipes, ingredients, references, _, _ = initial_fixture()
    profile = next(iter(current["profiles"].values()))
    rules = current["rules"]
    for row in (profile, rules):
        row.update(id="synthetic", version=1, content_hash="a" * 64, reason=None, attestation={})
    entries = deepcopy(rules["payload"]["meal_generation"]["recipe_classifications"])
    rules["payload"]["meal_generation"].update(catalog_mode="published", recipe_classifications=[])
    published = [SwapRecipeClassification.model_validate(item) for item in entries]
    ready = nutrition_readiness(profile, rules, recipes, ingredients, references, classifications=published)
    assert ready["meal_preview"]["status"] == "can_attempt_preview"
    assert rules["payload"]["meal_generation"]["recipe_classifications"] == []
    unavailable = nutrition_readiness(profile, rules, recipes, ingredients, references, classifications=[])
    assert unavailable["meal_preview"]["reason"] == "eligible_recipe_missing"
    for entry in published:
        entry.recipe_hash = "c" * 64
    assert (
        nutrition_readiness(profile, rules, recipes, ingredients, references, classifications=published)[
            "meal_preview"
        ]["status"]
        == "not_ready"
    )

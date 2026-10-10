"""隔离真实HTTP/PG验证成员能力、当前门禁及查询无写入。"""

import hashlib
import json
import os
from copy import deepcopy
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import JSON, Text, delete, or_, select, text

from test.integration.services import test_health_vision_http as health_fixture_owner
from test.integration.services.test_health_plan_adoption_http import adopt_body, approve
from test.integration.services.test_health_quality_http import setup_quality
from test.integration.services.test_health_vision_http import (  # noqa: F401
    ROOT,
    cleanup_test_knowledge_resources,
    cleanup_test_sandboxes,
    create_member,
    ensure_live_api_schema,
    health_http,
)
from yuxi.config.options import health_vision_opts, invalidate_option_cache
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_business import (
    Agent,
    AgentRun,
    Base,
    ConfigOption,
    Conversation,
    Department,
    Message,
    ModelProvider,
    OperationLog,
    Skill,
    User,
)
from yuxi.storage.postgres.models_health import (
    FamilyMember,
    HealthGrant,
    HealthMealPlanAdoption,
    HealthProcessingConsent,
    HealthProfessionalReview,
    HealthProfileSnapshot,
    RecipeVersion,
)
from yuxi.utils.datetime_utils import utc_now_naive

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio,
    pytest.mark.skipif(
        os.getenv("HEALTH_CONSULTATION_E2E_ISOLATED") != "true",
        reason="能力HTTP验收只在独立健康合成槽位修改临时配置",
    ),
]
PURPOSES = ("consultation", "meal_plan", "diet_analysis", "quality_review", "purchase")
BASIC_TASKS = ("consultation", "meal_preview", "diet_analysis")
SELECTED_TASKS = (
    "initial_meal_preview",
    "family_meal_revision",
    "safe_meal_revision",
    "quality_check",
    "purchase_requirements",
)
UNSUPPORTED_TASKS = ("glucose_plan", "multi_day_plan", "automatic_family_coordination")
AGENTS = ("health-consultation", "health-meal-planner", "health-diet-analyst", "health-quality", "health-purchase")
SKILLS = (
    "family-nutritionist",
    "family-meal-planner",
    "family-diet-analyst",
    "family-quality-review",
    "family-purchase",
)
REPORT_DIR = Path(os.getenv("HEALTH_CAPABILITIES_RECEIPT_DIR", "/app/health-capabilities-receipts"))


@pytest.fixture(autouse=True)
def verified_capability_cleanup(monkeypatch, request):
    """复用精确清理Owner，随后独立PG回查本轮全部关联表归零。"""
    original = health_fixture_owner.cleanup_health_test_resources

    async def cleanup_and_verify(identities, department_id):
        uids = [identity["uid"] for identity in identities]
        async with pg_manager.get_async_session_context() as session:
            scope = await owned_scope(session, uids, department_id)
            # 配置和provider的管理审计属于随机测试账号，按精确user_id清理。
            await session.execute(delete(OperationLog).where(OperationLog.user_id.in_(scope["users"])))
        await original(identities, department_id)
        async with pg_manager.get_async_session_context() as session:
            readback = await scoped_pg_snapshot(session, scope)
        assert all(item["count"] == 0 for item in readback.values()), {
            name: item["count"] for name, item in readback.items() if item["count"]
        }
        write_receipt("cleanup", request.node.nodeid, {name: item["count"] for name, item in readback.items()})

    monkeypatch.setattr(health_fixture_owner, "cleanup_health_test_resources", cleanup_and_verify)
    yield


@pytest_asyncio.fixture
async def capability_runtime(health_http, request):  # noqa: F811
    """临时处理方不运行模型；所有全局配置及内置行恢复原始PG字节。"""
    client, users = health_http
    assert os.getenv("HEALTH_CONSULTATION_E2E_ISOLATED") == "true"
    assert str(client.base_url).rstrip("/") == "http://localhost:5050"
    async with pg_manager.get_async_session_context() as session:
        assert await session.scalar(text("SELECT current_database()")) == "health_consultation_e2e"
        original = await capture_rows(session, ConfigOption, ConfigOption.key == health_vision_opts.key)
        agents = await capture_rows(session, Agent, Agent.slug.in_(AGENTS))
        skills = await capture_rows(session, Skill, Skill.slug.in_(SKILLS))
        assert len(agents) == len(AGENTS) and len(skills) == len(SKILLS), "shipping固定Agent和Skill必须存在"
    provider_id = f"health-capabilities-{uuid4().hex[:12]}"
    model_id = "synthetic-capabilities-20261010"
    provider = await client.post(
        "/api/system/model-providers",
        headers=users[2]["headers"],
        json={
            "provider_id": provider_id,
            "display_name": "Synthetic capability gate only",
            "provider_type": "openai",
            "base_url": "http://127.0.0.1:1/v1",
            "api_key": "synthetic-capabilities-no-model-call",
            "capabilities": ["chat"],
            "enabled_models": [{"id": model_id, "display_name": "synthetic", "type": "chat", "source": "manual"}],
            "is_enabled": True,
        },
    )
    assert provider.status_code == 200, provider.text
    body = {
        **{f"{purpose}_model": f"{provider_id}:{model_id}" for purpose in PURPOSES},
        "policy_version": "synthetic-capabilities-v1",
        "cloud_processing_reviewed": True,
    }
    try:
        configured = await client.put(f"{ROOT}/configuration", headers=users[2]["headers"], json=body)
        assert configured.status_code == 200, configured.text
        assert all(configured.json()[purpose]["available"] for purpose in PURPOSES)
        yield client, users, configured.json(), body, provider_id
    finally:
        # 不使用configure({})覆盖原配置，也保留原来不存在的key状态。
        async with pg_manager.get_async_session_context() as session:
            await restore_rows(session, Agent, Agent.slug.in_(AGENTS), agents)
            await restore_rows(session, Skill, Skill.slug.in_(SKILLS), skills)
            await restore_rows(session, ConfigOption, ConfigOption.key == health_vision_opts.key, original)
        await invalidate_option_cache(health_vision_opts.key)
        deleted = await client.delete(f"/api/system/model-providers/{provider_id}", headers=users[2]["headers"])
        assert deleted.status_code == 200, deleted.text
        async with pg_manager.get_async_session_context() as session:
            assert await capture_rows(session, Agent, Agent.slug.in_(AGENTS)) == agents
            assert await capture_rows(session, Skill, Skill.slug.in_(SKILLS)) == skills
            assert await capture_rows(session, ConfigOption, ConfigOption.key == health_vision_opts.key) == original
            assert await session.scalar(select(ModelProvider).where(ModelProvider.provider_id == provider_id)) is None
        write_receipt(
            "runtime_restore", request.node.nodeid, {"config": True, "agents": True, "skills": True, "provider": 0}
        )


async def test_invisible_member_missing_foreign_and_admin_return_same_404(capability_runtime):
    """现有账号和admin不继承成员权限，错误投影不可区分是否存在。"""
    client, users, _config, _body, _provider = capability_runtime
    member = await create_member(client, users[0]["headers"])
    foreign = await create_member(client, users[1]["headers"])
    before = await query_snapshot(users)
    responses = [
        await client.get(f"{ROOT}/members/{target}/capabilities", headers=actor["headers"])
        for target, actor in ((member, users[1]), (member, users[2]), (foreign, users[0]), (str(uuid4()), users[0]))
    ]
    assert all(response.status_code == 404 for response in responses), [response.status_code for response in responses]
    bodies = [response.json() for response in responses]
    assert all(set(body) == {"detail", "code", "message", "trace_id", "retryable"} for body in bodies)
    assert len({body["trace_id"] for body in bodies}) == len(bodies)
    public_errors = [{key: value for key, value in body.items() if key != "trace_id"} for body in bodies]
    assert all(error == public_errors[0] for error in public_errors)
    assert public_errors[0]["code"] == "not_found" and public_errors[0]["retryable"] is False
    assert all(response.headers["Cache-Control"] == "no-store" for response in responses)
    assert_no_query_writes(before, await query_snapshot(users))


@pytest.mark.parametrize("grant_state", ["empty_scopes", "revoked", "missing_grant"])
async def test_empty_revoked_or_missing_grant_hides_member(capability_runtime, grant_state):
    """直接准备合法PG边界，空scope即使revoked_at缺失也不得可见。"""
    client, users, _config, _body, _provider = capability_runtime
    member = await create_member(client, users[0]["headers"])
    async with pg_manager.get_async_session_context() as session:
        grant = await session.get(HealthGrant, (member, users[0]["uid"]))
        if grant_state == "missing_grant":
            await session.delete(grant)
        elif grant_state == "revoked":
            grant.revoked_at = utc_now_naive()
        else:
            grant.scopes, grant.revoked_at = [], None
    before = await query_snapshot(users)
    denied = await client.get(f"{ROOT}/members/{member}/capabilities", headers=users[0]["headers"])
    assert denied.status_code == 404 and denied.json()["code"] == "not_found", denied.text
    assert_no_query_writes(before, await query_snapshot(users))


async def test_visible_member_reports_own_missing_scopes_without_private_profile(capability_runtime):
    """仅diet_edit使成员可见；响应不得带出未授权的安全档案内容。"""
    client, users, _config, _body, _provider = capability_runtime
    current = await setup_quality(client, users)
    member = current["member"]
    granted = await client.put(
        f"{ROOT}/members/{member}/grants",
        headers=users[0]["headers"],
        json={"actor_uid": users[0]["uid"], "scopes": ["diet_edit"]},
    )
    assert granted.status_code == 200, granted.text
    before = await query_snapshot(users)
    result = await capabilities(client, users[0], member)
    assert result["dependencies"]["profile_projection"] == {
        "status": "not_authorized",
        "reason": "missing_scopes",
        "version": None,
    }
    tasks = task_map(result)
    assert set(tasks["consultation"]["missing_scopes"]) == {"ai_use", "report_view"}
    assert tasks["diet_analysis"]["missing_scopes"] == ["ai_use"]
    assert set(tasks["quality_check"]["missing_scopes"]) == {"ai_use", "profile_view"}
    assert all(tasks[kind]["reason_code"] == "missing_scopes" for kind in BASIC_TASKS + SELECTED_TASKS)
    assert_no_query_writes(before, await query_snapshot(users))


async def test_no_professional_profile_keeps_three_basic_entries_and_five_selections(capability_runtime):
    """普通任务无专业档案仍可进入；五类对象选择和三未实现状态保持明确。"""
    client, users, config, _body, _provider = capability_runtime
    member = await create_member(client, users[0]["headers"])
    await consent_to(client, users[0], member, config, PURPOSES)
    before = await query_snapshot(users)
    first = await capabilities(client, users[0], member)
    assert_ready_entries(first)
    assert first["dependencies"]["profile_projection"] == {
        "status": "not_ready",
        "reason": "not_delivered",
        "version": None,
    }
    async with pg_manager.get_async_session_context() as session:
        assert (
            await session.scalar(select(HealthProfileSnapshot.id).where(HealthProfileSnapshot.member_id == member))
            is None
        )
        exists = await session.scalar(select(RecipeVersion.id).limit(1))
    assert first["dependencies"]["published_recipes"] is (exists is not None)
    for _ in range(3):
        assert await capabilities(client, users[0], member) == first
    assert_no_query_writes(before, await query_snapshot(users))


async def test_same_processor_different_purpose_consent_does_not_open_other_tasks(capability_runtime):
    """所有用途有相同处理方，仍只能按用途同意通过各自门禁。"""
    client, users, config, _body, _provider = capability_runtime
    member = await create_member(client, users[0]["headers"])
    assert len({config[purpose]["processor"] for purpose in PURPOSES}) == 1
    await consent_to(client, users[0], member, config, ("meal_plan",))
    before = await query_snapshot(users)
    tasks = task_map(await capabilities(client, users[0], member))
    assert tasks["meal_preview"]["status"] == "available"
    for kind in ("initial_meal_preview", "family_meal_revision", "safe_meal_revision"):
        assert tasks[kind]["status"] == "needs_input" and tasks[kind]["reason_code"] == "selection_required"
    for kind in ("consultation", "diet_analysis", "quality_check", "purchase_requirements"):
        assert tasks[kind]["status"] == "unavailable" and tasks[kind]["reason_code"] == "consent_required"
    async with pg_manager.get_async_session_context() as session:
        rows = list(
            await session.scalars(select(HealthProcessingConsent).where(HealthProcessingConsent.member_id == member))
        )
        assert [row.purpose for row in rows] == ["meal_plan"]
    assert_no_query_writes(before, await query_snapshot(users))


async def test_policy_change_rejects_old_consent_and_new_consent_restores_entries(capability_runtime):
    """真实HTTP更新政策后旧同意失效，GET只提示且不修订同意行。"""
    client, users, config, body, _provider = capability_runtime
    member = await create_member(client, users[0]["headers"])
    await consent_to(client, users[0], member, config, PURPOSES)
    assert_ready_entries(await capabilities(client, users[0], member))
    changed = await client.put(
        f"{ROOT}/configuration",
        headers=users[2]["headers"],
        json={**body, "policy_version": "synthetic-capabilities-v2"},
    )
    assert changed.status_code == 200, changed.text
    before = await query_snapshot(users)
    tasks = task_map(await capabilities(client, users[0], member))
    assert all(tasks[kind]["reason_code"] == "consent_required" for kind in BASIC_TASKS + SELECTED_TASKS)
    assert_no_query_writes(before, await query_snapshot(users))
    await consent_to(client, users[0], member, changed.json(), PURPOSES)
    assert_ready_entries(await capabilities(client, users[0], member))


@pytest.mark.parametrize("change,reason", [("policy", "policy_not_approved"), ("provider", "model_unavailable")])
async def test_fresh_unapproved_configuration_or_disabled_provider_closes_tasks(capability_runtime, change, reason):
    """上次GET可用不能替代当前审批和PG供应商启用状态。"""
    client, users, config, _body, provider = capability_runtime
    member = await create_member(client, users[0]["headers"])
    await consent_to(client, users[0], member, config, PURPOSES)
    assert_ready_entries(await capabilities(client, users[0], member))
    if change == "policy":
        changed = await client.put(f"{ROOT}/configuration", headers=users[2]["headers"], json={})
        assert changed.status_code == 200, changed.text
    else:
        async with pg_manager.get_async_session_context() as session:
            row = await session.scalar(select(ModelProvider).where(ModelProvider.provider_id == provider))
            row.is_enabled = False
    before = await query_snapshot(users)
    tasks = task_map(await capabilities(client, users[0], member))
    for kind in BASIC_TASKS + SELECTED_TASKS:
        assert tasks[kind]["status"] == "unavailable" and tasks[kind]["reason_code"] == "configuration_unavailable"
        assert tasks[kind]["configuration_reason_code"] == reason
    assert_no_query_writes(before, await query_snapshot(users))


async def test_processor_change_needs_reapproval_then_new_consent(capability_runtime):
    """当前PG端点变化先使审批无效，重新审批仍不复用旧处理方同意。"""
    client, users, config, body, provider = capability_runtime
    member = await create_member(client, users[0]["headers"])
    await consent_to(client, users[0], member, config, PURPOSES)
    assert_ready_entries(await capabilities(client, users[0], member))
    changed = await client.put(
        f"/api/system/model-providers/{provider}",
        headers=users[2]["headers"],
        json={"base_url": "http://127.0.0.1:1/changed/v1"},
    )
    assert changed.status_code == 200, changed.text
    async with pg_manager.get_async_session_context() as session:
        row = await session.scalar(select(ModelProvider).where(ModelProvider.provider_id == provider))
        assert row.base_url == "http://127.0.0.1:1/changed/v1"
    before = await query_snapshot(users)
    tasks = task_map(await capabilities(client, users[0], member))
    for kind in BASIC_TASKS + SELECTED_TASKS:
        assert tasks[kind]["reason_code"] == "configuration_unavailable"
        assert tasks[kind]["configuration_reason_code"] == "processor_approval_changed"
    assert_no_query_writes(before, await query_snapshot(users))
    approved = await client.put(f"{ROOT}/configuration", headers=users[2]["headers"], json=body)
    assert approved.status_code == 200, approved.text
    assert approved.json()["consultation"]["processor"] != config["consultation"]["processor"]
    tasks = task_map(await capabilities(client, users[0], member))
    assert all(tasks[kind]["reason_code"] == "consent_required" for kind in BASIC_TASKS + SELECTED_TASKS)
    await consent_to(client, users[0], member, approved.json(), PURPOSES)
    assert_ready_entries(await capabilities(client, users[0], member))


@pytest.mark.parametrize("change", ["disabled", "source_type"])
async def test_builtin_skill_fresh_drift_closes_only_its_role(capability_runtime, change):
    """GET每次读取当前内置身份和启用；其他普通用途保持可用。"""
    client, users, config, _body, _provider = capability_runtime
    member = await create_member(client, users[0]["headers"])
    await consent_to(client, users[0], member, config, PURPOSES)
    assert_ready_entries(await capabilities(client, users[0], member))
    async with pg_manager.get_async_session_context() as session:
        skill = await session.scalar(select(Skill).where(Skill.slug == "family-nutritionist"))
        if change == "disabled":
            skill.enabled = False
        else:
            skill.source_type = "upload"
    before = await query_snapshot(users)
    tasks = task_map(await capabilities(client, users[0], member))
    assert (
        tasks["consultation"]["status"] == "unavailable" and tasks["consultation"]["reason_code"] == "skill_unavailable"
    )
    assert tasks["meal_preview"]["status"] == tasks["diet_analysis"]["status"] == "available"
    assert_no_query_writes(before, await query_snapshot(users))


@pytest.mark.parametrize("change", ["backend", "visibility", "subagent"])
async def test_current_fixed_agent_backend_and_permission_are_checked(capability_runtime, change):
    """同slug的错误backend或不可读Agent不能被能力发现放行。"""
    client, users, config, _body, _provider = capability_runtime
    member = await create_member(client, users[0]["headers"])
    await consent_to(client, users[0], member, config, PURPOSES)
    assert_ready_entries(await capabilities(client, users[0], member))
    async with pg_manager.get_async_session_context() as session:
        agent = await session.scalar(select(Agent).where(Agent.slug == "health-consultation"))
        if change == "backend":
            agent.backend_id = "DefaultAgent"
        elif change == "visibility":
            agent.share_config = {
                "version": 2,
                "read_scope": {"access_level": "user", "department_ids": [], "user_uids": [users[1]["uid"]]},
                "manage_scope": None,
            }
        else:
            agent.is_subagent = True
    before = await query_snapshot(users)
    tasks = task_map(await capabilities(client, users[0], member))
    assert (
        tasks["consultation"]["status"] == "unavailable" and tasks["consultation"]["reason_code"] == "agent_unavailable"
    )
    assert tasks["meal_preview"]["status"] == tasks["diet_analysis"]["status"] == "available"
    assert_no_query_writes(before, await query_snapshot(users))


async def test_expired_highest_profile_and_stale_approval_adoption_get_never_repairs_pg(capability_runtime):
    """过期最高档案不能回退旧版，查询不失效现有批准和采用、不写任何业务审计。"""
    client, users, config, _body, _provider = capability_runtime
    current = await setup_quality(client, users)
    member = current["member"]
    await approve(client, users, current)
    adopted = await client.post(
        f"{ROOT}/meal-plans/{current['plan']}/adopt", headers=users[0]["headers"], json=adopt_body(current)
    )
    assert adopted.status_code == 201 and adopted.json()["status"] == "active", adopted.text
    await consent_to(client, users[0], member, config, PURPOSES)
    ready = await capabilities(client, users[0], member)
    assert ready["dependencies"]["profile_projection"] == {"status": "ready", "reason": None, "version": 1}
    assert ready["dependencies"]["published_recipes"] is True
    assert_ready_entries(ready)
    # PG直接构造迟到失效源；不调用会永久失效审核/采用的读取Owner。
    async with pg_manager.get_async_session_context() as session:
        old = await session.scalar(select(HealthProfileSnapshot).where(HealthProfileSnapshot.member_id == member))
        expiry = utc_now_naive() - timedelta(minutes=1)
        proof = {
            **deepcopy(old.attestation),
            "version": 2,
            "source_version": "v2",
            "valid_until": expiry.isoformat() + "Z",
        }
        payload = deepcopy(old.payload)
        session.add(
            HealthProfileSnapshot(
                id=str(uuid4()),
                member_id=member,
                version=2,
                payload=payload,
                attestation=proof,
                content_hash=independent_digest(
                    {"kind": "profile", "key": member, "version": 2, "payload": payload, "attestation": proof}
                ),
                attested_at=old.attested_at,
                valid_until=expiry,
                imported_by=users[2]["uid"],
            )
        )
        review = await session.get(HealthProfessionalReview, current["case"]["review_id"])
        adoption = await session.get(HealthMealPlanAdoption, adopted.json()["adoption_id"])
        assert (review.status, review.version, adoption.status, adoption.version) == ("approved", 3, "active", 1)
    before = await query_snapshot(users)
    for _ in range(4):
        result = await capabilities(client, users[0], member)
        assert result["dependencies"]["profile_projection"] == {
            "status": "not_ready",
            "reason": "expired",
            "version": 2,
        }
        assert_ready_entries(result)
    after = await query_snapshot(users)
    assert_no_query_writes(before, after)
    assert before["health_professional_review"]["states"] == after["health_professional_review"]["states"]
    assert before["health_meal_plan_adoption"]["states"] == after["health_meal_plan_adoption"]["states"]
    # 同一PG oracle的内存负控模拟错误读取Owner的状态修复，必须因状态/版本变化拒绝。
    mutated = deepcopy(after)
    changed_review = json.loads(mutated["health_professional_review"]["states"][0])
    changed_review.update(status="invalidated", version=changed_review["version"] + 1)
    mutated["health_professional_review"]["states"] = [json.dumps(changed_review, sort_keys=True)]
    with pytest.raises(AssertionError, match="health_professional_review"):
        assert_no_query_writes(before, mutated)


async def capabilities(client, actor, member):
    """实际HTTP200之外核对业务协议白名单，避免私有字段意外透传。"""
    response = await client.get(f"{ROOT}/members/{member}/capabilities", headers=actor["headers"])
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["member_id"] == member
    assert set(result) == {"member_id", "tasks", "dependencies"}
    assert set(result["dependencies"]) == {"profile_projection", "published_recipes", "rules"}
    assert set(result["dependencies"]["profile_projection"]) == {"status", "reason", "version"}
    assert result["dependencies"]["rules"] == {"status": "needs_input", "reason": "selection_required", "version": None}
    for item in result["tasks"]:
        assert set(item) == {
            "task_type",
            "purpose",
            "status",
            "reason_code",
            "configuration_reason_code",
            "missing_scopes",
            "required_inputs",
        }
    forbidden = {
        "payload",
        "attestation",
        "content_hash",
        "processor",
        "model",
        "model_options",
        "api_key",
        "base_url",
        "age_years",
        "population_code",
        "nutrition",
        "sources",
        "proof",
        "source_ref",
    }
    assert forbidden.isdisjoint(json_keys(result)), f"能力协议泄漏私有或处理配置字段：{forbidden & json_keys(result)}"
    return result


async def consent_to(client, actor, member, configuration, purposes):
    """用途同意通过真实接口保存，再独立PG核对处理方和政策。"""
    for purpose in purposes:
        consent = await client.post(
            f"{ROOT}/members/{member}/processing-consents",
            headers=actor["headers"],
            json={
                "purpose": purpose,
                "accepted": True,
                "processor": configuration[purpose]["processor"],
                "policy_version": configuration["policy_version"],
            },
        )
        assert consent.status_code == 200, consent.text
        async with pg_manager.get_async_session_context() as session:
            row = await session.get(HealthProcessingConsent, (member, actor["uid"], purpose))
            assert row.processor == configuration[purpose]["processor"]
            assert row.policy_version == configuration["policy_version"] and row.revoked_at is None


def assert_ready_entries(result):
    """显式期望由业务契约提供，不使用生产任务表生成oracle。"""
    tasks = task_map(result)
    assert set(tasks) == set(BASIC_TASKS + SELECTED_TASKS + UNSUPPORTED_TASKS)
    expected_purposes = {
        "consultation": "consultation",
        "meal_preview": "meal_plan",
        "diet_analysis": "diet_analysis",
        "initial_meal_preview": "meal_plan",
        "family_meal_revision": "meal_plan",
        "safe_meal_revision": "meal_plan",
        "quality_check": "quality_review",
        "purchase_requirements": "purchase",
    }
    expected_selections = {
        "initial_meal_preview": ["kind", "plan_date", "rule_code", "rule_version", "profile_versions", "meals"],
        "family_meal_revision": ["plan_id", "version", "rule_code", "rule_version", "profile_versions"],
        "safe_meal_revision": ["plan_id", "version", "rule_code", "rule_version", "profile_version"],
        "quality_check": ["plan_id", "version", "rule_code"],
        "purchase_requirements": ["adoption_id", "adoption_version", "plan_version"],
    }
    for kind, purpose in expected_purposes.items():
        assert tasks[kind]["purpose"] == purpose
        assert tasks[kind]["configuration_reason_code"] is None
    for kind in BASIC_TASKS:
        assert tasks[kind]["status"] == "available" and tasks[kind]["reason_code"] is None, tasks[kind]
        expected_inputs = ["interaction.confirmed_meal_or_period"] if kind == "diet_analysis" else []
        assert tasks[kind]["missing_scopes"] == [] and tasks[kind]["required_inputs"] == expected_inputs
    for kind in SELECTED_TASKS:
        assert tasks[kind]["status"] == "needs_input" and tasks[kind]["reason_code"] == "selection_required", tasks[
            kind
        ]
        expected_inputs = [f"selection.{field}" for field in expected_selections[kind]]
        if kind == "purchase_requirements":
            expected_inputs.append("interaction.inventory_confirmation")
        assert tasks[kind]["missing_scopes"] == [] and tasks[kind]["required_inputs"] == expected_inputs
    for kind in UNSUPPORTED_TASKS:
        assert tasks[kind]["status"] == "unavailable" and tasks[kind]["reason_code"] == "external_contract_required", (
            tasks[kind]
        )
        assert tasks[kind]["purpose"] is None and tasks[kind]["required_inputs"] == []


def task_map(result):
    """拒绝重复任务，同时将稳定task_type映射用于独立断言。"""
    tasks = {item["task_type"]: item for item in result["tasks"]}
    assert len(tasks) == len(result["tasks"])
    return tasks


async def query_snapshot(users):
    """读取所属PG完整行hash、计数和状态版本，覆盖零行创建及旧行写入。"""
    async with pg_manager.get_async_session_context() as session:
        scope = await owned_scope(session, [actor["uid"] for actor in users])
        return await scoped_pg_snapshot(session, scope)


def assert_no_query_writes(before, after):
    """任何行新增、删除或字段变化均使相同只读验收失败。"""
    changed = sorted(name for name in before.keys() | after.keys() if before.get(name) != after.get(name))
    assert not changed, f"能力GET改变PostgreSQL业务事实：{changed}"


async def owned_scope(session, uids, department_id=None):
    """冻结本轮精确标识，删用户后仍能回查所有外键关联。"""
    scope = {"uids": uids}
    scope["users"] = list(await session.scalars(select(User.id).where(User.uid.in_(uids))))
    scope["members"] = list(await session.scalars(select(FamilyMember.id).where(FamilyMember.owner_uid.in_(uids))))
    scope["conversations"] = list(await session.scalars(select(Conversation.id).where(Conversation.uid.in_(uids))))
    scope["runs"] = list(await session.scalars(select(AgentRun.id).where(AgentRun.uid.in_(uids))))
    scope["messages"] = list(
        await session.scalars(select(Message.id).where(Message.conversation_id.in_(scope["conversations"])))
    )
    scope["department"] = department_id
    return scope


async def scoped_pg_snapshot(session, scope):
    """独立SQL投影覆盖ownership、成员和Conversation/Run/Message关联表。"""
    result = {}
    uid_columns = {
        "uid",
        "actor_uid",
        "owner_uid",
        "subject_uid",
        "reviewer_uid",
        "registered_by",
        "imported_by",
        "published_by",
        "created_by",
        "updated_by",
    }
    foreign_columns = {
        "member_id": "members",
        "conversation_id": "conversations",
        "run_id": "runs",
        "parent_run_id": "runs",
        "message_id": "messages",
        "user_id": "users",
    }
    for table in sorted(Base.metadata.tables.values(), key=lambda item: item.name):
        clauses = [column.in_(scope["uids"]) for column in table.c if column.name in uid_columns]
        clauses += [table.c[column].in_(scope[key]) for column, key in foreign_columns.items() if column in table.c]
        if table.name == Department.__tablename__ and scope["department"] is not None:
            clauses.append(table.c.id == scope["department"])
        if not clauses:
            continue
        condition = or_(*clauses)
        rows = (await session.execute(select(table).where(condition))).mappings().all()
        canonical = sorted(json.dumps(dict(row), sort_keys=True, default=str, ensure_ascii=False) for row in rows)
        state_columns = [
            name
            for name in (
                "id",
                "status",
                "version",
                "plan_version",
                "invalidation_reason",
                "reason",
                "revoked_at",
                "updated_at",
            )
            if name in table.c
        ]
        states = sorted(
            json.dumps({name: row[name] for name in state_columns}, sort_keys=True, default=str) for row in rows
        )
        result[table.name] = {"count": len(rows), "digest": independent_digest(canonical), "states": states}
    return result


async def capture_rows(session, model, condition):
    """保留JSON原始text和所有列值，恢复后比较同一数据库字节投影。"""
    columns = [
        column.cast(type_=Text()).label(column.name) if isinstance(column.type, JSON) else column
        for column in model.__table__.c
    ]
    rows = (await session.execute(select(*columns).where(condition))).mappings().all()
    return sorted([dict(row) for row in rows], key=lambda row: row["id"])


async def restore_rows(session, model, condition, rows):
    """准确恢复原行或原来缺失的配置key；JSON不重新序列化。"""
    if not rows:
        await session.execute(delete(model).where(condition))
        return
    table = model.__table__
    assignments = ", ".join(
        f'"{column.name}" = CAST(:{column.name} AS json)'
        if isinstance(column.type, JSON)
        else f'"{column.name}" = :{column.name}'
        for column in table.c
        if column.name != "id"
    )
    for row in rows:
        await session.execute(text(f'UPDATE "{table.name}" SET {assignments} WHERE id = :id'), row)


def independent_digest(value):
    """固定规范化摘要独立于生产fingerprint计算。"""
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()


def json_keys(value):
    """递归核对响应字段白名单，不依赖私有值恰好存在。"""
    if isinstance(value, dict):
        return set(value) | set().union(*(json_keys(item) for item in value.values()))
    if isinstance(value, list):
        return set().union(*(json_keys(item) for item in value))
    return set()


def write_receipt(kind, test, data):
    """回执只包含合成测试名和计数，不输出账号Token、配置或健康内容。"""
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    with (REPORT_DIR / f"{kind}.jsonl").open("a", encoding="utf-8") as stream:
        stream.write(json.dumps({"test": test, "result": data}, ensure_ascii=False) + "\n")

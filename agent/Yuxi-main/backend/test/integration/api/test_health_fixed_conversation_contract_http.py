"""真实HTTP及PG验证四个固定健康会话入口的成功响应契约。"""

import os
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import select

from test.integration.services.test_health_capabilities_http import (  # noqa: F401
    assert_no_query_writes,
    capability_runtime,
    consent_to,
    independent_digest,
    query_snapshot,
    verified_capability_cleanup,
    write_receipt,
)
from test.integration.services.test_health_diet_analysis_http import confirm_analysis_meal
from test.integration.services.test_health_personal_targets_http import import_targets, read_targets
from test.integration.services.test_health_quality_http import setup_quality
from test.integration.services.test_health_vision_http import (  # noqa: F401
    ROOT,
    cleanup_test_knowledge_resources,
    cleanup_test_sandboxes,
    create_member,
    ensure_live_api_schema,
    health_http,
)
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_business import AgentRun, AgentRunRequest, Conversation, Message, Project
from yuxi.storage.postgres.models_health import HealthConsultation, HealthFeedbackConversation, VisionDraft

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio,
    pytest.mark.skipif(
        os.getenv("HEALTH_CONSULTATION_E2E_ISOLATED") != "true",
        reason="固定会话HTTP契约只在独立健康合成槽位使用临时配置",
    ),
]


@pytest.mark.parametrize(
    "entry,slug", [("meal-planner", "health-meal-planner"), ("diet-analyst", "health-diet-analyst")]
)
async def test_ordinary_conversation_exact_wire_idempotency_and_member_role_isolation(capability_runtime, entry, slug):  # noqa: F811
    """普通入口不要求幂等Header，重放保留原线程及缺省选择投影。"""
    client, users, _configuration, _body, _provider = capability_runtime
    owner = users[0]["headers"]
    member = await create_member(client, owner)
    other_member = await create_member(client, owner)
    path = f"{ROOT}/members/{member}/{entry}"
    body = {"client_request_id": str(uuid4())}

    response = await client.post(path, headers=owner, json=body)
    result = assert_conversation_wire(response, member, slug)
    await assert_pg_binding(users, body, result, expected_count=1)
    baseline = await query_snapshot(users)
    repeated = await client.post(path, headers=owner, json=body)
    assert repeated.status_code == 201 and repeated.json() == result, repeated.text
    await assert_rejection_unchanged(
        client, users, baseline, f"{ROOT}/members/{other_member}/{entry}", owner, body, 409, "request_conflict"
    )
    other_role = "diet-analyst" if entry == "meal-planner" else "meal-planner"
    await assert_rejection_unchanged(
        client, users, baseline, f"{ROOT}/members/{member}/{other_role}", owner, body, 409, "request_conflict"
    )
    for actor in users[1:]:
        await assert_rejection_unchanged(client, users, baseline, path, actor["headers"], body, 404, "not_found")
    await revoke_and_assert_denied(client, users, member, path, body)


async def test_targeted_analyst_exact_wire_and_immutable_pg_source_binding(capability_runtime):  # noqa: F811
    """明确个人目标增加selection，去除或改变同键选择均拒绝且不写业务事实。"""
    client, users, _configuration, _body, _provider = capability_runtime
    owner = users[0]["headers"]
    current = await setup_quality(client, users)
    await import_targets(client, users, current)
    target = await read_targets(client, owner, current)
    assert target.status_code == 200 and target.json()["energy_kcal"] == "330", target.text
    selected = {"rule_code": current["rules"]["rule_code"], "rule_version": 2, "profile_version": 2}
    body = {"client_request_id": str(uuid4()), "target_selection": selected}
    path = f"{ROOT}/members/{current['member']}/diet-analyst"

    response = await client.post(path, headers=owner, json=body)
    result = assert_conversation_wire(response, current["member"], "health-diet-analyst", target_selection=selected)
    await assert_pg_binding(users, body, result, expected_count=1, target_hash=independent_digest(target.json()))
    baseline = await query_snapshot(users)
    repeated = await client.post(path, headers=owner, json=body)
    assert repeated.status_code == 201 and repeated.json() == result, repeated.text
    for changed in (
        {"client_request_id": body["client_request_id"]},
        {**body, "target_selection": {**selected, "rule_version": 1}},
        {**body, "target_selection": {**selected, "profile_version": 1}},
    ):
        await assert_rejection_unchanged(client, users, baseline, path, owner, changed, 409, "request_conflict")
    await assert_rejection_unchanged(
        client,
        users,
        baseline,
        path,
        owner,
        {"client_request_id": str(uuid4()), "target_selection": {**selected, "profile_version": 1}},
        409,
        "source_version_conflict",
    )
    for actor in users[1:]:
        await assert_rejection_unchanged(client, users, baseline, path, actor["headers"], body, 404, "not_found")
    await revoke_and_assert_denied(client, users, current["member"], path, body)


async def test_feedback_exact_selected_meal_wire_pg_binding_and_source_version_conflicts(capability_runtime):  # noqa: F811
    """反馈响应仅携带显式选餐，PG保存确认版本而不同选餐与模式不能复用同键。"""
    client, users, _configuration, _body, _provider = capability_runtime
    owner, admin = users[0]["headers"], users[2]["headers"]
    member = await create_member(client, owner)
    record, draft_id = await confirm_analysis_meal(client, owner, admin, member, revised=True)
    other_record, _draft = await confirm_analysis_meal(client, owner, admin, member)
    assert record["source_version"] == 2
    selected = {"record_id": record["id"], "source_version": 2}
    path = f"{ROOT}/diet-logs/{record['id']}/feedback-conversation"
    body = {"client_request_id": str(uuid4()), "source_version": 2}

    response = await client.post(path, headers=owner, json=body)
    result = assert_conversation_wire(response, member, "health-diet-analyst", feedback_selection=selected)
    await assert_pg_binding(users, body, result, expected_count=1)
    baseline = await query_snapshot(users)
    repeated = await client.post(path, headers=owner, json=body)
    assert repeated.status_code == 201 and repeated.json() == result, repeated.text
    await assert_rejection_unchanged(
        client,
        users,
        baseline,
        f"{ROOT}/diet-logs/{other_record['id']}/feedback-conversation",
        owner,
        {**body, "source_version": 1},
        409,
        "request_conflict",
    )
    await assert_rejection_unchanged(
        client,
        users,
        baseline,
        f"{ROOT}/members/{member}/diet-analyst",
        owner,
        {"client_request_id": body["client_request_id"]},
        409,
        "request_conflict",
    )
    await assert_rejection_unchanged(
        client,
        users,
        baseline,
        path,
        owner,
        {"client_request_id": str(uuid4()), "source_version": 1},
        409,
        "version_conflict",
    )
    for actor in users[1:]:
        await assert_rejection_unchanged(client, users, baseline, path, actor["headers"], body, 404, "not_found")
    async with pg_manager.get_async_session_context() as session:
        (await session.get(VisionDraft, draft_id)).version += 1
    stale_baseline = await query_snapshot(users)
    await assert_rejection_unchanged(client, users, stale_baseline, path, owner, body, 410, "source_invalidated")
    await revoke_and_assert_denied(client, users, member, path, body)


async def test_safe_planner_exact_selection_wire_pg_binding_and_current_authorization(capability_runtime):  # noqa: F811
    """安全入口保留唯一成员和当前专业版本，重放与拒绝不会改正式餐单。"""
    client, users, configuration, _body, _provider = capability_runtime
    owner = users[0]["headers"]
    current = await setup_quality(client, users)
    other_member = await create_member(client, owner)
    await consent_to(client, users[0], current["member"], configuration, ("meal_plan",))
    selected = {
        "plan_id": current["plan"],
        "version": 1,
        "rule_code": current["rules"]["rule_code"],
        "rule_version": 1,
        "profile_version": 1,
    }
    body = {"client_request_id": str(uuid4()), **selected}
    path = f"{ROOT}/members/{current['member']}/safe-meal-plan-conversations"
    before = await query_snapshot(users)

    response = await client.post(path, headers=owner, json=body)
    result = assert_conversation_wire(response, current["member"], "health-meal-planner", safe_selection=selected)
    await assert_pg_binding(users, body, result, expected_count=1)
    baseline = await query_snapshot(users)
    for table in (
        "health_meal_plan",
        "health_meal_plan_revision",
        "health_quality_check",
        "health_professional_review",
    ):
        assert baseline[table] == before[table], table
    repeated = await client.post(path, headers=owner, json=body)
    assert repeated.status_code == 201 and repeated.json() == result, repeated.text
    for field in ("version", "rule_version", "profile_version"):
        await assert_rejection_unchanged(
            client, users, baseline, path, owner, {**body, field: 2}, 409, "request_conflict"
        )
        await assert_rejection_unchanged(
            client,
            users,
            baseline,
            path,
            owner,
            {**body, "client_request_id": str(uuid4()), field: 2},
            410,
            "source_invalidated",
        )
    await assert_rejection_unchanged(
        client,
        users,
        baseline,
        f"{ROOT}/members/{current['member']}/meal-planner",
        owner,
        {"client_request_id": body["client_request_id"]},
        409,
        "request_conflict",
    )
    await assert_rejection_unchanged(
        client,
        users,
        baseline,
        f"{ROOT}/members/{other_member}/safe-meal-plan-conversations",
        owner,
        body,
        404,
        "not_found",
    )
    for actor in users[1:]:
        await assert_rejection_unchanged(client, users, baseline, path, actor["headers"], body, 404, "not_found")
    revoked = await client.post(
        f"{ROOT}/members/{current['member']}/processing-consents",
        headers=owner,
        json={
            "purpose": "meal_plan",
            "accepted": False,
            "processor": configuration["meal_plan"]["processor"],
            "policy_version": configuration["policy_version"],
        },
    )
    assert revoked.status_code == 200, revoked.text
    consent_baseline = await query_snapshot(users)
    await assert_rejection_unchanged(client, users, consent_baseline, path, owner, body, 403, "consent_required")
    await revoke_and_assert_denied(client, users, current["member"], path, body)


async def test_four_http_entries_keep_request_validation_and_authentication(capability_runtime):  # noqa: F811
    """新增成功DTO不扩张现有请求模型，验证失败与未登录请求都不创建会话。"""
    client, users, _configuration, _body, _provider = capability_runtime
    member, record, plan = str(uuid4()), str(uuid4()), str(uuid4())
    entries = [
        (f"{ROOT}/members/{member}/meal-planner", {"client_request_id": str(uuid4())}),
        (f"{ROOT}/members/{member}/diet-analyst", {"client_request_id": str(uuid4())}),
        (f"{ROOT}/diet-logs/{record}/feedback-conversation", {"client_request_id": str(uuid4()), "source_version": 1}),
        (
            f"{ROOT}/members/{member}/safe-meal-plan-conversations",
            {
                "client_request_id": str(uuid4()),
                "plan_id": plan,
                "version": 1,
                "rule_code": "synthetic-contract",
                "rule_version": 1,
                "profile_version": 1,
            },
        ),
    ]
    baseline = await query_snapshot(users)
    for path, body in entries:
        anonymous = await client.post(path, json=body)
        assert anonymous.status_code == 401, anonymous.text
        for invalid in ({**body, "uid": "forged"}, {**body, "client_request_id": "not-a-uuid"}, {}):
            rejected = await client.post(path, headers=users[0]["headers"], json=invalid)
            assert rejected.status_code == 422, rejected.text
        invalid_path = path.replace(member if "/members/" in path else record, "not-a-uuid")
        rejected = await client.post(invalid_path, headers=users[0]["headers"], json=body)
        assert rejected.status_code == 422, rejected.text
        assert_no_query_writes(baseline, await query_snapshot(users))


async def test_live_openapi_declares_four_response_shapes_and_analyst_selection_union(capability_runtime):  # noqa: F811
    """读取真实应用OpenAPI，五个成功形状均只公开现有协议字段。"""
    client, _users, _configuration, _body, _provider = capability_runtime
    response = await client.get("/openapi.json")
    assert response.status_code == 200, response.text
    document = response.json()
    schemas = document["components"]["schemas"]
    ordinary = {"thread_id", "member_id", "agent_slug", "business_date", "feedback_selection"}
    expected = {
        "MealPlannerConversationResult": (ordinary, "health-meal-planner"),
        "DietAnalystConversationResult": (ordinary, "health-diet-analyst"),
        "TargetedDietAnalystConversationResult": (ordinary | {"target_selection"}, "health-diet-analyst"),
        "FeedbackConversationResult": (ordinary, "health-diet-analyst"),
        "SafeMealPlannerConversationResult": (ordinary | {"safe_selection"}, "health-meal-planner"),
    }
    for name, (keys, slug) in expected.items():
        schema = schemas[name]
        assert set(schema["properties"]) == keys, name
        assert set(schema["required"]) == keys, name
        assert schema["additionalProperties"] is False, name
        assert schema["properties"]["agent_slug"]["const"] == slug, name
        assert schema["properties"]["business_date"]["type"] == "null", name
        if name != "FeedbackConversationResult":
            assert schema["properties"]["feedback_selection"]["type"] == "null", name
    paths = {
        f"{ROOT}/members/{{member_id}}/meal-planner": ["MealPlannerConversationResult"],
        f"{ROOT}/members/{{member_id}}/diet-analyst": [
            "DietAnalystConversationResult",
            "TargetedDietAnalystConversationResult",
        ],
        f"{ROOT}/diet-logs/{{record_id}}/feedback-conversation": ["FeedbackConversationResult"],
        f"{ROOT}/members/{{member_id}}/safe-meal-plan-conversations": ["SafeMealPlannerConversationResult"],
    }
    for path, names in paths.items():
        schema = document["paths"][path]["post"]["responses"]["201"]["content"]["application/json"]["schema"]
        references = schema.get("anyOf", [schema])
        assert sorted(item["$ref"].rsplit("/", 1)[1] for item in references) == sorted(names), path


@pytest_asyncio.fixture(autouse=True)
async def no_agent_execution_side_effects(verified_capability_cleanup, health_http, request):  # noqa: F811
    """每项回读执行事实为零；显式依赖保证清理patch覆盖health_http卸载。"""
    _client, users = health_http
    yield
    snapshot = await query_snapshot(users)
    counts = {
        model.__tablename__: snapshot[model.__tablename__]["count"] for model in (AgentRun, AgentRunRequest, Message)
    }
    assert all(count == 0 for count in counts.values()), counts
    counts.update(
        {
            model.__tablename__: snapshot[model.__tablename__]["count"]
            for model in (Conversation, Project, HealthConsultation, HealthFeedbackConversation)
        }
    )
    write_receipt("fixed_conversation_pg", request.node.nodeid, counts)


def assert_conversation_wire(
    response, member_id, slug, *, feedback_selection=None, target_selection=None, safe_selection=None
):
    """独立列出现有响应字段，缺省目标及安全选择不得新增null。"""
    assert response.status_code == 201, response.text
    result = response.json()
    assert str(UUID(result["thread_id"])) == result["thread_id"]
    expected = {
        "thread_id": result["thread_id"],
        "member_id": member_id,
        "agent_slug": slug,
        "business_date": None,
        "feedback_selection": feedback_selection,
    }
    if target_selection is not None:
        expected["target_selection"] = target_selection
    if safe_selection is not None:
        expected["safe_selection"] = safe_selection
    assert result == expected
    return result


async def assert_pg_binding(users, body, result, *, expected_count, target_hash=None):
    """独立读取Conversation与专属绑定，核对角色、成员、请求ID及唯一项目。"""
    async with pg_manager.get_async_session_context() as session:
        bindings = list(
            await session.scalars(select(HealthConsultation).where(HealthConsultation.actor_uid == users[0]["uid"]))
        )
        assert len(bindings) == expected_count
        binding = next(item for item in bindings if item.request_id == body["client_request_id"])
        conversation = await session.get(Conversation, binding.conversation_id)
        assert conversation.thread_id == result["thread_id"] and conversation.uid == users[0]["uid"]
        assert conversation.agent_id == result["agent_slug"] and binding.member_id == result["member_id"]
        projects = list(await session.scalars(select(Project).where(Project.uid == users[0]["uid"])))
        assert len(projects) == expected_count and conversation.project_id in {item.id for item in projects}
        feedback = await session.get(HealthFeedbackConversation, binding.conversation_id)
        if result["feedback_selection"] is None:
            assert feedback is None
        else:
            assert {"record_id": feedback.diet_log_id, "source_version": feedback.source_version} == result[
                "feedback_selection"
            ]
        if "target_selection" in result:
            assert binding.personal_target_selection == {
                "selection": result["target_selection"],
                "source_hash": target_hash,
            }
        else:
            assert binding.personal_target_selection is None
        if "safe_selection" in result:
            assert binding.safe_planner_selection["selection"] == result["safe_selection"]
            assert len(binding.safe_planner_selection["source_hash"]) == 64
        else:
            assert binding.safe_planner_selection is None
        assert binding.family_planner_selection is None and binding.initial_planner_selection is None
        assert binding.purchase_selection is None


async def assert_rejection_unchanged(client, users, baseline, path, headers, body, status, code):
    """拒绝原因必须准确且所有所属PG行与原业务版本保持一致。"""
    response = await client.post(path, headers=headers, json=body)
    assert response.status_code == status and response.json()["code"] == code, response.text
    assert_no_query_writes(baseline, await query_snapshot(users))


async def revoke_and_assert_denied(client, users, member, path, body):
    """实际撤回成员授权后，同键重放也不能恢复成功响应。"""
    revoked = await client.put(
        f"{ROOT}/members/{member}/grants",
        headers=users[0]["headers"],
        json={"actor_uid": users[0]["uid"], "scopes": []},
    )
    assert revoked.status_code == 200, revoked.text
    await assert_rejection_unchanged(
        client, users, await query_snapshot(users), path, users[0]["headers"], body, 404, "not_found"
    )

"""真实 HTTP 和 PostgreSQL 验证成员、授权及用途同意的现有响应契约。"""

import os
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import func, select

from test.integration.services.test_health_capabilities_http import (  # noqa: F401
    assert_no_query_writes,
    capability_runtime,
    query_snapshot,
    verified_capability_cleanup,
    write_receipt,
)
from test.integration.services.test_health_vision_http import (  # noqa: F401
    ROOT,
    cleanup_test_knowledge_resources,
    cleanup_test_sandboxes,
    create_member,
    ensure_live_api_schema,
    health_http,
)
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_business import (
    AgentRun,
    AgentRunRequest,
    Conversation,
    Message,
    ModelProvider,
    Project,
    TaskRecord,
)
from yuxi.storage.postgres.models_health import (
    FamilyMember,
    HealthConsultation,
    HealthGrant,
    HealthProcessingConsent,
    PrivateUpload,
    VisionJob,
)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio,
    pytest.mark.skipif(
        os.getenv("HEALTH_CONSULTATION_E2E_ISOLATED") != "true",
        reason="成员契约HTTP验收只在独立健康合成槽位使用临时处理配置",
    ),
]


async def test_create_member_returns_only_new_id_and_initial_owner_grant(capability_runtime):  # noqa: F811
    """相同建档输入每次产生新ID，初始授权事实仅属于建档账号。"""
    client, users, _config, _body, _provider = capability_runtime
    body = {"display_name": "合成成员甲", "relationship_label": "本人", "authorized": True}
    created_ids = []
    for _ in range(2):
        response = await client.post(f"{ROOT}/members", headers=users[0]["headers"], json=body)
        assert response.status_code == 201, response.text
        assert set(response.json()) == {"id"}
        member_id = response.json()["id"]
        assert str(UUID(member_id)) == member_id
        created_ids.append(member_id)

        async with pg_manager.get_async_session_context() as session:
            member = await session.get(FamilyMember, member_id)
            assert member is not None
            assert (member.owner_uid, member.display_name, member.relationship_label) == (
                users[0]["uid"],
                "合成成员甲",
                "本人",
            )
            grants = list(await session.scalars(select(HealthGrant).where(HealthGrant.member_id == member_id)))
            assert len(grants) == 1
            assert grants[0].actor_uid == users[0]["uid"] and grants[0].revoked_at is None
            assert grants[0].scopes == [
                "ai_use",
                "diet_edit",
                "professional_review",
                "profile_edit",
                "profile_view",
                "report_upload",
                "report_view",
            ]
    assert created_ids[0] != created_ids[1]


async def test_member_list_is_bare_array_and_preserves_actor_scopes_order(capability_runtime):  # noqa: F811
    """空列表、本人和受委托列表保持精确字段，管理员只看到自身显式授权。"""
    client, users, _config, _body, _provider = capability_runtime
    before = await query_snapshot(users)
    for user in users:
        response = await client.get(f"{ROOT}/members", headers=user["headers"])
        assert response.status_code == 200 and response.json() == [], response.text
    assert_no_query_writes(before, await query_snapshot(users))

    owner_member = await create_member(client, users[0]["headers"])
    foreign_member = await create_member(client, users[1]["headers"])
    scopes = ["report_view", "ai_use", "diet_edit"]
    granted = await client.put(
        f"{ROOT}/members/{owner_member}/grants",
        headers=users[0]["headers"],
        json={"actor_uid": users[1]["uid"], "scopes": scopes},
    )
    assert granted.status_code == 200 and granted.json() == {"saved": True}, granted.text
    initial_scopes = [
        "ai_use",
        "diet_edit",
        "professional_review",
        "profile_edit",
        "profile_view",
        "report_upload",
        "report_view",
    ]
    expected = [
        [
            {
                "id": owner_member,
                "display_name": "合成测试成员",
                "relationship_label": "本人",
                "is_owner": True,
                "scopes": initial_scopes,
            }
        ],
        [
            {
                "id": owner_member,
                "display_name": "合成测试成员",
                "relationship_label": "本人",
                "is_owner": False,
                "scopes": scopes,
            },
            {
                "id": foreign_member,
                "display_name": "合成测试成员",
                "relationship_label": "本人",
                "is_owner": True,
                "scopes": initial_scopes,
            },
        ],
        [],
    ]
    before = await query_snapshot(users)
    for user, items in zip(users, expected, strict=True):
        response = await client.get(f"{ROOT}/members", headers=user["headers"])
        assert response.status_code == 200 and response.json() == items, response.text
    assert_no_query_writes(before, await query_snapshot(users))


async def test_grant_overwrites_current_slot_and_empty_scopes_revoke_access(capability_runtime):  # noqa: F811
    """授权保存返回固定true，覆盖和撤回均回读当前唯一PG槽位。"""
    client, users, _config, _body, _provider = capability_runtime
    member = await create_member(client, users[0]["headers"])
    for scopes in (["report_view", "ai_use"], ["diet_edit", "profile_view"], [], ["ai_use"]):
        response = await client.put(
            f"{ROOT}/members/{member}/grants",
            headers=users[0]["headers"],
            json={"actor_uid": users[1]["uid"], "scopes": scopes},
        )
        assert response.status_code == 200 and response.json() == {"saved": True}, response.text
        async with pg_manager.get_async_session_context() as session:
            grants = list(
                await session.scalars(
                    select(HealthGrant).where(HealthGrant.member_id == member, HealthGrant.actor_uid == users[1]["uid"])
                )
            )
            assert len(grants) == 1 and grants[0].scopes == scopes
            assert (grants[0].revoked_at is not None) is (scopes == [])
        before = await query_snapshot(users)
        visible = await client.get(f"{ROOT}/members", headers=users[1]["headers"])
        assert visible.status_code == 200, visible.text
        assert visible.json() == (
            [
                {
                    "id": member,
                    "display_name": "合成测试成员",
                    "relationship_label": "本人",
                    "is_owner": False,
                    "scopes": scopes,
                }
            ]
            if scopes
            else []
        )
        assert_no_query_writes(before, await query_snapshot(users))


async def test_non_owner_admin_and_unknown_uid_cannot_change_grants(capability_runtime):  # noqa: F811
    """profile_edit授权不替代建档人身份，管理员和不存在账号不能旁路写入。"""
    client, users, _config, _body, _provider = capability_runtime
    member = await create_member(client, users[0]["headers"])
    for actor in users[1:]:
        response = await client.put(
            f"{ROOT}/members/{member}/grants",
            headers=users[0]["headers"],
            json={"actor_uid": actor["uid"], "scopes": ["profile_edit", "ai_use"]},
        )
        assert response.status_code == 200 and response.json() == {"saved": True}, response.text
    before = await query_snapshot(users)
    for actor in users[1:]:
        response = await client.put(
            f"{ROOT}/members/{member}/grants",
            headers=actor["headers"],
            json={"actor_uid": users[0]["uid"], "scopes": []},
        )
        assert response.status_code == 404 and response.json()["code"] == "not_found", response.text
    for target, actor_uid in ((member, f"missing-{uuid4().hex}"), (str(uuid4()), users[1]["uid"])):
        response = await client.put(
            f"{ROOT}/members/{target}/grants",
            headers=users[0]["headers"],
            json={"actor_uid": actor_uid, "scopes": ["ai_use"]},
        )
        assert response.status_code == 404 and response.json()["code"] == "not_found", response.text
    assert_no_query_writes(before, await query_snapshot(users))


async def test_processing_consent_returns_boolean_and_updates_unique_current_slot(capability_runtime):  # noqa: F811
    """各用途独立记录同意，重复接受更新时间，撤回和再次接受覆盖同一行。"""
    client, users, config, _body, _provider = capability_runtime
    member = await create_member(client, users[0]["headers"])
    for purpose in ("consultation", "meal_plan", "diet_analysis", "quality_review", "purchase"):
        body = {
            "purpose": purpose,
            "processor": config[purpose]["processor"],
            "policy_version": config["policy_version"],
            "accepted": True,
        }
        previous_time = None
        for accepted in (True, True, False, True):
            response = await client.post(
                f"{ROOT}/members/{member}/processing-consents",
                headers=users[0]["headers"],
                json={**body, "accepted": accepted},
            )
            assert response.status_code == 200 and response.json() == {"accepted": accepted}, response.text
            async with pg_manager.get_async_session_context() as session:
                records = list(
                    await session.scalars(
                        select(HealthProcessingConsent).where(
                            HealthProcessingConsent.member_id == member,
                            HealthProcessingConsent.actor_uid == users[0]["uid"],
                            HealthProcessingConsent.purpose == purpose,
                        )
                    )
                )
                assert len(records) == 1
                record = records[0]
                assert (record.processor, record.policy_version) == (body["processor"], body["policy_version"])
                assert (record.revoked_at is None) is accepted
                if previous_time is not None:
                    assert record.granted_at > previous_time
                previous_time = record.granted_at


async def test_processing_consent_rejects_policy_drift_unavailable_and_missing_ai_scope(capability_runtime):  # noqa: F811
    """配置漂移拒绝接受；撤回同样受当前ai_use授权约束且失败不改变PG。"""
    client, users, config, configuration_body, provider = capability_runtime
    member = await create_member(client, users[0]["headers"])
    body = {
        "purpose": "consultation",
        "processor": config["consultation"]["processor"],
        "policy_version": config["policy_version"],
        "accepted": True,
    }
    before = await query_snapshot(users)
    invalid = [
        {**body, "policy_version": "old-synthetic-policy"},
        {**body, "processor": "obsolete-synthetic-processor"},
    ]
    for request_body in invalid:
        response = await client.post(
            f"{ROOT}/members/{member}/processing-consents", headers=users[0]["headers"], json=request_body
        )
        assert response.status_code == 409 and response.json()["code"] == "policy_changed", response.text
    for actor, target in ((users[1], member), (users[2], member), (users[0], str(uuid4()))):
        response = await client.post(
            f"{ROOT}/members/{target}/processing-consents", headers=actor["headers"], json=body
        )
        assert response.status_code == 404 and response.json()["code"] == "not_found", response.text
    assert_no_query_writes(before, await query_snapshot(users))

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
    current = await client.get(f"{ROOT}/configuration", headers=users[0]["headers"])
    assert current.status_code == 200, current.text
    assert current.json()["consultation"]["available"] is False
    assert current.json()["consultation"]["reason_code"] == "processor_approval_changed"
    current_processor = current.json()["consultation"]["processor"]
    assert current_processor and current_processor != body["processor"]
    body = {**body, "processor": current_processor}
    unavailable = await client.post(
        f"{ROOT}/members/{member}/processing-consents", headers=users[0]["headers"], json=body
    )
    assert unavailable.status_code == 409 and unavailable.json()["code"] == "policy_changed", unavailable.text
    assert_no_query_writes(before, await query_snapshot(users))
    reapproved = await client.put(f"{ROOT}/configuration", headers=users[2]["headers"], json=configuration_body)
    assert reapproved.status_code == 200 and reapproved.json()["consultation"]["available"] is True, reapproved.text

    accepted = await client.post(f"{ROOT}/members/{member}/processing-consents", headers=users[0]["headers"], json=body)
    assert accepted.status_code == 200 and accepted.json() == {"accepted": True}, accepted.text
    granted = await client.put(
        f"{ROOT}/members/{member}/grants",
        headers=users[0]["headers"],
        json={"actor_uid": users[0]["uid"], "scopes": ["profile_edit"]},
    )
    assert granted.status_code == 200 and granted.json() == {"saved": True}, granted.text
    before = await query_snapshot(users)
    for request_body in (body, {**body, "accepted": False}):
        response = await client.post(
            f"{ROOT}/members/{member}/processing-consents", headers=users[0]["headers"], json=request_body
        )
        assert response.status_code == 404 and response.json()["code"] == "not_found", response.text
    assert_no_query_writes(before, await query_snapshot(users))


async def test_four_operations_require_authentication_and_validate_existing_requests(capability_runtime):  # noqa: F811
    """四个操作拒绝匿名；非法输入不建立成员、grant、同意或执行事实。"""
    client, users, config, _body, _provider = capability_runtime
    member = await create_member(client, users[0]["headers"])
    create_body = {"display_name": "合成输入校验成员", "authorized": True}
    grant_body = {"actor_uid": users[1]["uid"], "scopes": ["ai_use"]}
    consent_body = {
        "purpose": "consultation",
        "processor": config["consultation"]["processor"],
        "policy_version": config["policy_version"],
        "accepted": True,
    }
    before = await query_snapshot(users)
    anonymous = [
        await client.get(f"{ROOT}/members"),
        await client.post(f"{ROOT}/members", json=create_body),
        await client.put(f"{ROOT}/members/{member}/grants", json=grant_body),
        await client.post(f"{ROOT}/members/{member}/processing-consents", json=consent_body),
    ]
    assert all(response.status_code == 401 for response in anonymous), [response.status_code for response in anonymous]
    invalid_requests = [
        ("POST", "/members", {**create_body, "authorized": False}),
        ("POST", "/members", {"display_name": "合成输入校验成员"}),
        ("POST", "/members", {**create_body, "display_name": ""}),
        ("POST", "/members", {**create_body, "client_request_id": str(uuid4())}),
        ("PUT", f"/members/{member}/grants", {**grant_body, "scopes": ["all"]}),
        ("PUT", f"/members/{member}/grants", {**grant_body, "actor_uid": ""}),
        ("PUT", "/members/not-a-uuid/grants", grant_body),
        ("POST", f"/members/{member}/processing-consents", {**consent_body, "purpose": "unknown"}),
        ("POST", f"/members/{member}/processing-consents", {**consent_body, "processor": ""}),
        ("POST", f"/members/{member}/processing-consents", {**consent_body, "policy_version": ""}),
        (
            "POST",
            f"/members/{member}/processing-consents",
            {key: value for key, value in consent_body.items() if key != "accepted"},
        ),
        ("POST", f"/members/{member}/processing-consents", {**consent_body, "client_request_id": str(uuid4())}),
        ("POST", "/members/not-a-uuid/processing-consents", consent_body),
    ]
    for method, path, request_body in invalid_requests:
        response = await client.request(method, f"{ROOT}{path}", headers=users[0]["headers"], json=request_body)
        assert response.status_code == 422, (method, path, response.text)
    assert_no_query_writes(before, await query_snapshot(users))


@pytest_asyncio.fixture(autouse=True)
async def no_agent_execution_side_effects(verified_capability_cleanup, health_http, request):  # noqa: F811
    """每项验收直接回读PG，成员操作不得产生Agent、线程、上传或Task。"""
    # 显式依赖使清理patch晚于health_http卸载，保证独立归零回查确实执行。
    _client, users = health_http
    yield
    snapshot = await query_snapshot(users)
    execution_tables = tuple(
        model.__tablename__
        for model in (
            AgentRun,
            AgentRunRequest,
            Conversation,
            Message,
            Project,
            HealthConsultation,
            VisionJob,
            PrivateUpload,
        )
    )
    counts = {name: snapshot[name]["count"] for name in execution_tables}
    async with pg_manager.get_async_session_context() as session:
        counts[TaskRecord.__tablename__] = await session.scalar(
            select(func.count(TaskRecord.id))
            .join(VisionJob, VisionJob.task_id == TaskRecord.id)
            .where(VisionJob.actor_uid.in_([user["uid"] for user in users]))
        )
    assert all(count == 0 for count in counts.values()), counts
    counts.update(
        {
            model.__tablename__: snapshot[model.__tablename__]["count"]
            for model in (FamilyMember, HealthGrant, HealthProcessingConsent)
        }
    )
    write_receipt("member_access_pg", request.node.nodeid, counts)

"""正式本人来源经真实质量Worker读取，改版及未知状态阻止旧结果继续使用。"""

import json
import os
from copy import deepcopy
from types import SimpleNamespace
from uuid import uuid4

import pytest
import pytest_asyncio
from langchain_core.messages import AIMessage, ToolMessage
from sqlalchemy import delete, select

from test.e2e.test_health_consultation_e2e import collect_sse, drain_requests, isolated_health  # noqa: F401
from test.e2e.test_health_quality_e2e import approve_quality, bind_quality, seed_quality_run
from test.integration.services.test_health_quality_http import action, proof, setup_quality
from test.integration.services.test_health_vision_http import ROOT, health_http  # noqa: F401
from yuxi.repositories.conversation_repository import ConversationRepository
from yuxi.services.chat_service import save_messages_from_langgraph_state
from yuxi.services.health_consultation_service import require_consultation_attempt
from yuxi.services.health_quality_service import check_selected_quality
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_business import (
    AgentRun,
    AgentRunRequest,
    FamilyArchive,
    FamilyAudit,
    FamilyMember,
    FamilyProfileRevision,
    Message,
    TOOL_AUDIT_MESSAGE_TYPE,
)
from yuxi.storage.postgres.models_health import HealthFamilyProfileLink, HealthProfileSnapshot, HealthQualityCheck
from yuxi.storage.postgres.models_health import HealthProfessionalReview

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.slow,
    pytest.mark.asyncio,
    pytest.mark.skipif(os.getenv("HEALTH_CONSULTATION_E2E_ISOLATED") != "true", reason="仅独立合成槽位"),
]


@pytest_asyncio.fixture
async def family_quality(isolated_health):  # noqa: F811
    """通过真实HTTP登记本人来源与专业投影，只清理本轮明确家庭。"""
    client, users, configuration, _ = isolated_health
    owner, admin = users[0]["headers"], users[2]["headers"]
    current = await setup_quality(client, users)
    created = await client.post("/api/family", headers=owner, json={"name": "合成本人安全来源E2E"})
    assert created.status_code == 200, created.text
    family_id = created.json()["id"]
    source = next(member for member in created.json()["members"] if member["is_self"])
    path = f"/api/family/{family_id}/members/{source['id']}"
    try:
        edited = await client.put(
            path,
            headers=owner,
            json={
                "expected_version": source["version"],
                "profile": {
                    "sex": "female",
                    "birth_date": "1996-01-02",
                    "height_cm": 171,
                    "activity_level": "light",
                    "goal": "合成均衡饮食",
                },
            },
        )
        assert edited.status_code == 200 and edited.json()["version"] == 2, edited.text
        confirmed = await client.post(path + "/confirm", headers=owner, json={"expected_version": 2})
        assert confirmed.status_code == 200, confirmed.text
        linked = await client.post(
            f"{ROOT}/members/{current['member']}/family-profile-link",
            headers=owner,
            json={"family_id": family_id, "source_member_id": source["id"], "confirmed_identity": True},
        )
        assert linked.status_code == 200, linked.text
        binding = {"family_id": family_id, "source_member_id": source["id"], "confirmed_version": 2}
        profile = {**current["profile"], **proof(2), "family_profile_source": binding}
        imported = await client.post(
            f"{ROOT}/members/{current['member']}/external-profile-versions", headers=admin, json=profile
        )
        assert imported.status_code == 201 and imported.json()["status"] == "ready", imported.text
        attested = imported.json()["attestation"]["family_profile_source"]
        assert {key: attested[key] for key in binding} == binding
        assert len(attested["source_hash"]) == 64
        current.update(profile=profile, family_path=path, professional_source=attested, projection=imported.json())
        yield client, users, configuration, current
    finally:
        async with pg_manager.get_async_session_context() as session:
            await session.execute(
                delete(HealthFamilyProfileLink).where(HealthFamilyProfileLink.member_id == current["member"])
            )
            await session.execute(delete(FamilyAudit).where(FamilyAudit.family_id == family_id))
            await session.execute(delete(FamilyProfileRevision).where(FamilyProfileRevision.member_id == source["id"]))
            await session.execute(delete(FamilyMember).where(FamilyMember.family_id == family_id))
            await session.execute(
                delete(FamilyArchive).where(FamilyArchive.id == family_id, FamilyArchive.owner_uid == users[0]["uid"])
            )


async def test_family_source_worker_two_turns_and_profile_change_rejects_old_checkpoint(family_quality):
    """真实工具和检查均保留专业来源；正式改版拒绝旧线程、checkpoint及发布。"""
    client, users, configuration, current = family_quality
    owner, admin = users[0]["headers"], users[2]["headers"]
    provider = "family-safety-replay-" + uuid4().hex[:12]
    created = await client.post(
        "/api/system/model-providers",
        headers=admin,
        json={
            "provider_id": provider,
            "display_name": "Synthetic family safety quality only",
            "provider_type": "openai",
            "base_url": "http://api:8771/v1",
            "api_key": "synthetic-quality-key",
            "capabilities": ["chat"],
            "enabled_models": [
                {
                    "id": "deterministic-quality-20261007",
                    "display_name": "synthetic",
                    "type": "chat",
                    "source": "manual",
                }
            ],
            "is_enabled": True,
        },
    )
    assert created.status_code == 200, created.text
    model = f"{provider}:deterministic-quality-20261007"
    requests, worker_checks, context = [], [], None
    try:
        processing, _ = await approve_quality(
            client, owner, admin, current["member"], model, configuration["policy_version"]
        )
        thread = await bind_quality(client, owner, current)
        for _ in range(2):
            request = str(uuid4())
            requests.append(request)
            submitted = await client.post(
                "/api/agent/runs",
                headers=owner,
                json={
                    "agent_slug": "health-quality",
                    "thread_id": thread,
                    "query": f"QUALITY_E2E:{uuid4().hex}:valid",
                    "meta": {"request_id": request},
                },
            )
            assert submitted.status_code == 200, submitted.text
            run_id = submitted.json()["run_id"]
            events = await collect_sse(client, owner, run_id)
            assert events[-1][0] == "end" and not any("message_delta" in str(event) for _, event in events)
            response = await client.get(f"/api/agent/runs/{run_id}/result", headers=owner)
            assert response.status_code == 200 and response.json()["status"] == "completed", response.text
            result = json.loads(response.json()["output"])
            async with pg_manager.get_async_session_context() as session:
                run = await session.get(AgentRun, run_id)
                check = await session.scalar(select(HealthQualityCheck).where(HealthQualityCheck.run_id == run_id))
                assert check is not None and result["check_id"] == check.id
                assert check.actor_uid == users[0]["uid"] and check.snapshot["safety_check"]["status"] == "passed"
                assert result["professional_review"] == "not_a_professional_decision"
                assert (
                    result["sources"]["profiles"][current["member"]]["content_hash"]
                    == current["projection"]["content_hash"]
                )
                assert result["sources"]["profiles"][current["member"]]["version"] == 2
                message = await session.get(Message, run.output_message_id)
                assert message.run_id == run_id and json.loads(message.content) == result
                tool = await session.scalar(
                    select(Message).where(
                        Message.run_id == run_id,
                        Message.message_type == TOOL_AUDIT_MESSAGE_TYPE,
                        Message.extra_metadata["tool_name"].as_string() == "get_quality_review_context",
                    )
                )
                assert tool is not None
                professional = json.loads(tool.content)["profile"]
                assert professional["status"] == "ready" and professional["version"] == 2
                assert professional["attestation"]["family_profile_source"] == current["professional_source"]
                row = await session.get(HealthProfileSnapshot, professional["id"])
                assert row.attestation["family_profile_source"] == current["professional_source"]
                worker_checks.append(check.id)
        assert worker_checks[0] != worker_checks[1]
        checkpoint = await pg_manager.get_langgraph_checkpointer().aget_tuple({"configurable": {"thread_id": thread}})
        assert checkpoint is not None
        history = checkpoint.checkpoint["channel_values"]["messages"]
        assert any(
            isinstance(message, ToolMessage) and message.name == "get_quality_review_context" for message in history
        )

        # 使用真实PG执行Owner验证发布边界，区别于上面两次实际Worker执行。
        context = await seed_quality_run(users[0]["uid"], thread, processing)
        await require_consultation_attempt(context, history)
        late = await check_selected_quality(context)
        changed = await client.put(
            current["family_path"], headers=owner, json={"expected_version": 2, "profile": {"height_cm": 172}}
        )
        assert changed.status_code == 200 and changed.json()["version"] == 3, changed.text
        unavailable = await client.get(
            f"{ROOT}/members/{current['member']}/external-profile-versions/current", headers=owner
        )
        assert unavailable.status_code == 200 and unavailable.json()["reason"] == "family_profile_unconfirmed"
        assert unavailable.json()["payload"] is None
        with pytest.raises(HealthVisionError, match="source_invalidated"):
            await require_consultation_attempt(context, history)
        async with pg_manager.get_async_session_context() as session:
            with pytest.raises(HealthVisionError, match="source_invalidated"):
                await save_messages_from_langgraph_state(
                    SimpleNamespace(values={"messages": [AIMessage(id=str(uuid4()), content=json.dumps(late))]}),
                    thread,
                    ConversationRepository(session),
                    run_id=context.run_id,
                    request_id=context.request_id,
                    worker_id=context.worker_id,
                    complete_run=True,
                )
        rejected_request = str(uuid4())
        rejected = await client.post(
            "/api/agent/runs",
            headers=owner,
            json={
                "agent_slug": "health-quality",
                "thread_id": thread,
                "query": f"QUALITY_E2E:{uuid4().hex}:valid",
                "meta": {"request_id": rejected_request},
            },
        )
        assert rejected.status_code == 410, rejected.text
        async with pg_manager.get_async_session_context() as session:
            run = await session.get(AgentRun, context.run_id)
            assert run.status == "running" and run.output_message_id is None
            assert (
                await session.scalar(select(Message).where(Message.run_id == run.id, Message.role == "assistant"))
                is None
            )
            for model_class in (AgentRun, AgentRunRequest, Message):
                assert (
                    await session.scalar(select(model_class).where(model_class.request_id == rejected_request)) is None
                )
            for check_id in [*worker_checks, late["check_id"]]:
                case = await session.scalar(
                    select(HealthProfessionalReview).where(HealthProfessionalReview.check_id == check_id)
                )
                assert case.status == "invalidated" and case.invalidation_reason == "family_profile_changed"
    finally:
        if context is not None:
            async with pg_manager.get_async_session_context() as session:
                run = await session.get(AgentRun, context.run_id)
                run.status, run.worker_id, run.lease_expires_at = "failed", None, None
        await drain_requests(client, owner, requests)
        assert (await client.put(f"{ROOT}/configuration", headers=admin, json={})).status_code == 200
        assert (await client.delete(f"/api/system/model-providers/{provider}", headers=admin)).status_code == 200


async def test_professionally_unknown_family_projection_persists_unknown_quality(family_quality):
    """工程来源有效不替代未知过敏资料，真实检查落库且不能专业批准。"""
    client, users, _, current = family_quality
    owner, reviewer, admin = [user["headers"] for user in users]
    profile = {**deepcopy(current["profile"]), **proof(3)}
    profile["payload"]["allergies"] = {"state": "unknown", "codes": []}
    imported = await client.post(
        f"{ROOT}/members/{current['member']}/external-profile-versions", headers=admin, json=profile
    )
    assert imported.status_code == 201 and imported.json()["status"] == "ready", imported.text
    checked = await client.post(
        f"{ROOT}/meal-plans/{current['plan']}/quality-checks",
        headers=owner,
        json={**current["body"], "client_request_id": str(uuid4())},
    )
    assert checked.status_code == 201, checked.text
    result = checked.json()
    assert result["safety_check"]["status"] == "unknown"
    assert {"path": "profile.allergies", "reason": "not_filled"} in result["safety_check"]["missing"]
    async with pg_manager.get_async_session_context() as session:
        check = await session.get(HealthQualityCheck, result["check_id"])
        assert check.snapshot["safety_check"]["status"] == "unknown" and check.run_id is None
        projection = await session.get(HealthProfileSnapshot, imported.json()["id"])
        assert projection.payload["allergies"] == {"state": "unknown", "codes": []}
        assert projection.attestation["family_profile_source"] == current["professional_source"]
        case = await session.scalar(
            select(HealthProfessionalReview).where(HealthProfessionalReview.check_id == check.id)
        )
        case_id = case.id
    await action(client, owner, case_id, "submit", 1)
    denied = await action(client, reviewer, case_id, "approve", 2, expected=409)
    assert denied["code"] == "quality_not_passed"
    async with pg_manager.get_async_session_context() as session:
        assert (await session.get(HealthProfessionalReview, case_id)).status == "pending_review"

"""隔离真实 API/Worker/SSE/PG 证明明确体重来源与旧质量 checkpoint 失效。"""

import json
import os
from copy import deepcopy
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
import pytest_asyncio
from langchain_core.messages import AIMessage, ToolMessage
from sqlalchemy import delete, select

from test.e2e.test_health_consultation_e2e import collect_sse, drain_requests, isolated_health  # noqa: F401
from test.e2e.test_health_family_safety_e2e import family_quality  # noqa: F401
from test.e2e.test_health_quality_e2e import approve_quality, bind_quality, seed_quality_run
from test.integration.services.test_health_quality_http import proof
from test.integration.services.test_health_vision_http import ROOT, health_http  # noqa: F401
from test.integration.services.test_health_weight_http import add_weight
from test.unit.services.test_health_personal_targets import target_formula
from yuxi.repositories.conversation_repository import ConversationRepository
from yuxi.services.chat_service import save_messages_from_langgraph_state
from yuxi.services.health_consultation_service import require_consultation_attempt
from yuxi.services.health_quality_service import check_selected_quality
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_business import (
    AgentRun,
    AgentRunRequest,
    FamilyMeasurement,
    Message,
    TOOL_AUDIT_MESSAGE_TYPE,
)
from yuxi.storage.postgres.models_health import HealthProfessionalReview, HealthProfileSnapshot, HealthQualityCheck

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.slow,
    pytest.mark.asyncio,
    pytest.mark.skipif(os.getenv("HEALTH_CONSULTATION_E2E_ISOLATED") != "true", reason="仅禁止外联的独立合成槽位"),
]


@pytest_asyncio.fixture
async def weight_quality(family_quality):  # noqa: F811
    """测量行单独精确清理，任何准备失败也不遗留正式家庭依赖。"""
    client, users, _, current = family_quality
    subject = SimpleNamespace(
        client=client, headers=users[0]["headers"], measurement_path=current["family_path"] + "/measurements"
    )
    record = await add_weight(subject)
    try:
        yield (*family_quality, subject, record)
    finally:
        async with pg_manager.get_async_session_context() as session:
            await session.execute(delete(FamilyMeasurement).where(FamilyMeasurement.id == record["id"]))


async def test_selected_weight_worker_two_turns_and_correction_reject_old_checkpoint(weight_quality):
    """实际两轮读取60/v1算330；61/v2后旧结果与checkpoint拒绝，fresh335不继承专业批准。"""
    client, users, configuration, current, subject, record = weight_quality
    owner, admin = users[0]["headers"], users[2]["headers"]
    profile = {**deepcopy(current["profile"]), **proof(3)}
    profile["payload"].update(sex_code="synthetic_sex", weight_kg="60", activity_code="synthetic_activity")
    profile["weight_measurement_source"] = {"record_id": record["id"], "version": 1}
    imported = await client.post(
        f"{ROOT}/members/{current['member']}/external-profile-versions", headers=admin, json=profile
    )
    assert imported.status_code == 201 and imported.json()["status"] == "ready", imported.text
    selected_source = imported.json()["attestation"]["weight_measurement_source"]
    assert selected_source["record_id"] == record["id"] and selected_source["version"] == 1
    assert selected_source["unit"] == "kg" and len(selected_source["source_hash"]) == 64
    rules = {**deepcopy(current["rules"]), **proof(2)}
    rules["payload"]["personal_targets"] = [target_formula()]
    published = await client.post(f"{ROOT}/approved-quality-rules", headers=admin, json=rules)
    assert published.status_code == 201, published.text
    provider = "selected-weight-quality-" + uuid4().hex[:12]
    created = await client.post(
        "/api/system/model-providers",
        headers=admin,
        json={
            "provider_id": provider,
            "display_name": "Synthetic selected weight quality only",
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
    requests, runs, checks, context = [], [], [], None
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
                    "query": f"QUALITY_E2E:{uuid4().hex}:valid:personal",
                    "meta": {"request_id": request},
                },
            )
            assert submitted.status_code == 200, submitted.text
            run_id = submitted.json()["run_id"]
            runs.append(run_id)
            events = await collect_sse(client, owner, run_id)
            assert events[-1][0] == "end" and not any("message_delta" in str(event) for _, event in events)
            response = await client.get(f"/api/agent/runs/{run_id}/result", headers=owner)
            assert response.status_code == 200 and response.json()["status"] == "completed", response.text
            result = json.loads(response.json()["output"])
            assert result["safety_check"]["status"] == "conflict"
            assert Decimal(result["safety_check"]["personal_targets"]["energy_kcal"]) == Decimal("330")
            assert result["safety_check"]["personal_targets"]["bounds"]["energy_kcal"] == {
                "minimum": "330",
                "maximum": "330",
            }
            async with pg_manager.get_async_session_context() as session:
                run = await session.get(AgentRun, run_id)
                check = await session.scalar(select(HealthQualityCheck).where(HealthQualityCheck.run_id == run_id))
                assert check.id == result["check_id"] and check.actor_uid == users[0]["uid"]
                assert check.snapshot["sources"]["profiles"][current["member"]]["version"] == 3
                assert check.snapshot["sources"]["rules"]["version"] == 2
                message = await session.get(Message, run.output_message_id)
                assert message.run_id == run_id and json.loads(message.content) == result
                assert run.status == "completed" and run.worker_id is None and not run.runtime_cleanup_pending
                tool = await session.scalar(
                    select(Message).where(
                        Message.run_id == run_id,
                        Message.message_type == TOOL_AUDIT_MESSAGE_TYPE,
                        Message.extra_metadata["tool_name"].as_string() == "get_quality_review_context",
                    )
                )
                assert tool is not None
                professional = json.loads(tool.content)["profile"]
                assert professional["attestation"]["weight_measurement_source"] == selected_source
                projection = await session.get(HealthProfileSnapshot, professional["id"])
                assert projection.payload["weight_kg"] == "60"
                assert projection.attestation["weight_measurement_source"] == selected_source
                checks.append(check.id)
        assert len(set(runs)) == len(set(checks)) == 2
        checkpoint = await pg_manager.get_langgraph_checkpointer().aget_tuple({"configurable": {"thread_id": thread}})
        assert checkpoint is not None
        history = checkpoint.checkpoint["channel_values"]["messages"]
        assert any(
            isinstance(message, ToolMessage) and message.name == "get_quality_review_context" for message in history
        )

        # 单独的真实PG执行Owner补证晚发布边界；上面的两轮才是实际Worker执行证据。
        context = await seed_quality_run(users[0]["uid"], thread, processing)
        await require_consultation_attempt(context, history)
        late = await check_selected_quality(context)
        corrected = await client.put(
            subject.measurement_path + "/" + record["id"],
            headers=owner,
            json={"expected_version": 1, "values": {"weight": 61}, "note": record["note"]},
        )
        assert corrected.status_code == 200 and corrected.json()["version"] == 2, corrected.text
        async with pg_manager.get_async_session_context() as session:
            actual = await session.get(FamilyMeasurement, record["id"])
            assert actual.version == 2 and actual.values == {"weight": 61}
            assert actual.previous[0]["values"] == {"weight": 60}
            for check_id in [*checks, late["check_id"]]:
                review = await session.scalar(
                    select(HealthProfessionalReview).where(HealthProfessionalReview.check_id == check_id)
                )
                assert review.status == "invalidated" and review.invalidation_reason == "weight_measurement_changed"
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
        rejected_key = str(uuid4())
        rejected = await client.post(
            "/api/agent/runs",
            headers=owner,
            json={
                "agent_slug": "health-quality",
                "thread_id": thread,
                "query": f"QUALITY_E2E:{uuid4().hex}:valid:personal",
                "meta": {"request_id": rejected_key},
            },
        )
        assert rejected.status_code == 410, rejected.text
        history_read = await client.get(f"/api/chat/thread/{thread}/history", headers=owner)
        assert history_read.status_code == 404, history_read.text
        for run_id in runs:
            result = await client.get(f"/api/agent/runs/{run_id}/result", headers=owner)
            assert result.status_code == 200 and result.json()["error"]["type"] == "run_not_found", result.text
            assert result.json()["output"] == ""
        async with pg_manager.get_async_session_context() as session:
            run = await session.get(AgentRun, context.run_id)
            assert run.status == "running" and run.output_message_id is None
            assert (
                await session.scalar(select(Message).where(Message.run_id == run.id, Message.role == "assistant"))
                is None
            )
            for model_class in (AgentRun, AgentRunRequest, Message):
                assert await session.scalar(select(model_class).where(model_class.request_id == rejected_key)) is None
        fresh = {**deepcopy(profile), **proof(4)}
        fresh["payload"]["weight_kg"] = "61"
        fresh["weight_measurement_source"]["version"] = 2
        imported_fresh = await client.post(
            f"{ROOT}/members/{current['member']}/external-profile-versions", headers=admin, json=fresh
        )
        assert imported_fresh.status_code == 201 and imported_fresh.json()["status"] == "ready", imported_fresh.text
        targets = await client.post(
            f"{ROOT}/members/{current['member']}/nutrition-targets",
            headers=owner,
            json={"profile_version": 4, "rule_version": 2, "rule_code": rules["rule_code"]},
        )
        assert targets.status_code == 200 and Decimal(targets.json()["energy_kcal"]) == Decimal("335"), targets.text
        async with pg_manager.get_async_session_context() as session:
            for check_id in checks:
                review = await session.scalar(
                    select(HealthProfessionalReview).where(HealthProfessionalReview.check_id == check_id)
                )
                assert review.status == "invalidated"
    finally:
        if context is not None:
            async with pg_manager.get_async_session_context() as session:
                run = await session.get(AgentRun, context.run_id)
                run.status, run.worker_id, run.lease_expires_at = "failed", None, None
        await drain_requests(client, owner, requests)
        assert (await client.put(f"{ROOT}/configuration", headers=admin, json={})).status_code == 200
        assert (await client.delete(f"/api/system/model-providers/{provider}", headers=admin)).status_code == 200

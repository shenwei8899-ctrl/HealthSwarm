"""独立API/worker/PG验证分析用途、固定工具与权威输出。"""

import json
import os
from datetime import date, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import select
from langchain_core.messages import AIMessage, ToolMessage

from test.e2e.test_health_consultation_e2e import isolated_health, collect_sse, drain_requests  # noqa: F401
from test.integration.services.test_health_vision_http import ROOT, create_member, health_http  # noqa: F401
from test.integration.services.test_health_diet_analysis_http import confirm_analysis_meal
from yuxi.agents.context import BaseContext
from yuxi.services.health_diet_analysis_service import analyst_meal_records, read_diet_analysis, read_period_analysis
from yuxi.services.health_diet_analysis_types import DietAnalysisPeriod, DietAnalysisSelection
from yuxi.services.chat_service import save_messages_from_langgraph_state
from yuxi.services.health_consultation_service import require_consultation_attempt
from yuxi.repositories.conversation_repository import ConversationRepository
from yuxi.repositories.health_consultation_repository import HealthConsultationRepository
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_business import TOOL_AUDIT_MESSAGE_TYPE, AgentRun, AgentRunRequest, Message
from yuxi.storage.postgres.models_health import DietLog, VisionDraft
from yuxi.utils.datetime_utils import utc_now_naive

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.slow,
    pytest.mark.asyncio,
    pytest.mark.skipif(os.getenv("HEALTH_CONSULTATION_E2E_ISOLATED") != "true", reason="仅独立合成槽位"),
]


@pytest.mark.parametrize(
    "withdrawal",
    [
        "consent",
        "source",
        "failed_audit",
        "questions_audit",
        "unselected_audit",
        "feedback",
        "feedback_audit",
        "new_meal_audit",
        "new_feedback_audit",
        "checkpoint_feedback",
    ],
)
async def test_analysis_withdrawal_blocks_publication_and_all_successful_audits(isolated_health, withdrawal):  # noqa: F811
    """真实PG在投影后撤回，禁止完成发布；非最终来源的成功工具审计同样失效。"""
    client, users, configuration, model = isolated_health
    headers, admin = users[0]["headers"], users[2]["headers"]
    member = await create_member(client, headers)
    record, draft_id = await confirm_analysis_meal(client, headers, admin, member)
    configured = await client.put(
        f"{ROOT}/configuration",
        headers=admin,
        json={
            "diet_analysis_model": model,
            "policy_version": configuration["policy_version"],
            "cloud_processing_reviewed": True,
        },
    )
    assert configured.status_code == 200, configured.text
    approved = configured.json()["diet_analysis"]
    snapshot = {"model": model, "processor": approved["processor"], "policy_version": configuration["policy_version"]}
    consent_data = {
        "accepted": True,
        "purpose": "diet_analysis",
        **{k: snapshot[k] for k in ("processor", "policy_version")},
    }
    assert (
        await client.post(f"{ROOT}/members/{member}/processing-consents", headers=headers, json=consent_data)
    ).status_code == 200
    bound = await client.post(
        f"{ROOT}/members/{member}/diet-analyst", headers=headers, json={"client_request_id": str(uuid4())}
    )
    assert bound.status_code == 201, bound.text
    thread, run_id, request_id = bound.json()["thread_id"], str(uuid4()), str(uuid4())
    feedback_url = f"{ROOT}/diet-logs/{record['id']}/feedback"
    period_modes = {"feedback", "feedback_audit", "new_meal_audit", "new_feedback_audit", "checkpoint_feedback"}
    if withdrawal in {"feedback", "feedback_audit", "checkpoint_feedback"}:
        key = str(uuid4())
        written = await client.put(
            feedback_url,
            headers={**headers, "Idempotency-Key": key, "If-Match": '"0"'},
            json={
                "client_request_id": key,
                "version": 0,
                "tags": ["too_salty"],
            },
        )
        assert written.status_code == 200, written.text
    if withdrawal in period_modes:
        analysis = await read_period_analysis(
            users[0]["uid"], member, DietAnalysisPeriod(period_days=7, end_date=date(2026, 10, 7))
        )
    else:
        analysis = await read_diet_analysis(
            users[0]["uid"], member, DietAnalysisSelection(record_id=record["id"], source_version=1)
        )
    async with pg_manager.get_async_session_context() as session:
        binding = await HealthConsultationRepository(session).authorize(users[0]["uid"], thread)
        run = AgentRun(
            id=run_id,
            request_id=request_id,
            uid=users[0]["uid"],
            agent_slug="health-diet-analyst",
            conversation_id=binding.conversation_id,
            conversation_thread_id=thread,
            runtime_scope_id=thread,
            worker_id="synthetic-publication-owner",
            status="running" if withdrawal in {"consent", "source", "feedback", "checkpoint_feedback"} else "failed",
            lease_expires_at=utc_now_naive() + timedelta(minutes=1),
            input_payload={"health_processing": snapshot},
        )
        session.add(run)
        await session.flush()
        if withdrawal.endswith("audit"):
            audit_content = {"records": [{"record_id": record["id"], "source_version": 1, "names": ["合成分析食品"]}]}
            if withdrawal in period_modes:
                audit_content = analysis
            session.add(
                Message(
                    conversation_id=binding.conversation_id,
                    run_id=run_id,
                    request_id=request_id,
                    role="tool",
                    content=json.dumps(audit_content),
                    message_type=TOOL_AUDIT_MESSAGE_TYPE,
                    execution_status="completed",
                    extra_metadata={
                        "tool_name": "analyze_confirmed_period" if withdrawal in period_modes else "list_analysis_meals"
                    },
                )
            )
            if withdrawal != "failed_audit":
                run.status = "completed"
                output = Message(
                    conversation_id=binding.conversation_id,
                    run_id=run_id,
                    request_id=request_id,
                    role="assistant",
                    content=json.dumps(
                        {"status": "needs_input"} if withdrawal == "questions_audit" else {"records": []}
                    ),
                )
                session.add(output)
                await session.flush()
                run.output_message_id = output.id
    if withdrawal in {"feedback", "feedback_audit", "checkpoint_feedback", "new_feedback_audit"}:
        key = str(uuid4())
        changed = await client.put(
            feedback_url,
            headers={
                **headers,
                "Idempotency-Key": key,
                "If-Match": '"0"' if withdrawal == "new_feedback_audit" else '"1"',
            },
            json={
                "client_request_id": key,
                "version": 0 if withdrawal == "new_feedback_audit" else 1,
                "tags": ["too_oily"],
            },
        )
        assert changed.status_code == 200, changed.text
    elif withdrawal == "new_meal_audit":
        await confirm_analysis_meal(client, headers, admin, member, eaten_at="2026-10-07T18:00:00+08:00")
    elif withdrawal == "consent":
        revoked = await client.post(
            f"{ROOT}/members/{member}/processing-consents", headers=headers, json={**consent_data, "accepted": False}
        )
        assert revoked.status_code == 200, revoked.text
    else:
        async with pg_manager.get_async_session_context() as session:
            (await session.get(VisionDraft, draft_id)).review_status = "retracted"
    if withdrawal.endswith("audit"):
        async with pg_manager.get_async_session_context() as session:
            with pytest.raises(HealthVisionError, match="source_invalidated"):
                await HealthConsultationRepository(session).authorize(users[0]["uid"], thread)
        return
    try:
        if withdrawal == "checkpoint_feedback":
            context = BaseContext(
                uid=users[0]["uid"],
                thread_id=thread,
                run_id=run_id,
                request_id=request_id,
                worker_id="synthetic-publication-owner",
                model=model,
            )
            with pytest.raises(HealthVisionError, match="source_invalidated"):
                await require_consultation_attempt(
                    context,
                    [
                        ToolMessage(
                            content=json.dumps(analysis),
                            name="analyze_confirmed_period",
                            tool_call_id=str(uuid4()),
                        )
                    ],
                )
            async with pg_manager.get_async_session_context() as session:
                assert await session.scalar(select(Message).where(Message.run_id == run_id)) is None
            return
        async with pg_manager.get_async_session_context() as session:
            error = {"consent": "consent_required", "feedback": "analyst_output_invalid"}.get(
                withdrawal, "source_invalidated"
            )
            with pytest.raises(HealthVisionError, match=error):
                await save_messages_from_langgraph_state(
                    SimpleNamespace(values={"messages": [AIMessage(id=str(uuid4()), content=json.dumps(analysis))]}),
                    thread,
                    ConversationRepository(session),
                    run_id=run_id,
                    request_id=request_id,
                    worker_id="synthetic-publication-owner",
                    complete_run=True,
                )
        async with pg_manager.get_async_session_context() as session:
            persisted = await session.get(AgentRun, run_id)
            assert persisted.status == "running" and persisted.output_message_id is None
            assert (
                await session.scalar(select(Message).where(Message.run_id == run_id, Message.role == "assistant"))
                is None
            )
    finally:
        async with pg_manager.get_async_session_context() as session:
            (await session.get(AgentRun, run_id)).status = "failed"


async def test_analysis_worker_independent_consent_and_authoritative_result(isolated_health):  # noqa: F811
    """模型伪造营养、跨成员选择和旧版本均失败，撤回阻止旧结果读取。"""
    client, users, configuration, consultation_model = isolated_health
    headers, admin = users[0]["headers"], users[2]["headers"]
    member = await create_member(client, headers)
    record, draft_id = await confirm_analysis_meal(client, headers, admin, member)
    other_member = await create_member(client, headers)
    other_record, _ = await confirm_analysis_meal(client, headers, admin, other_member)
    provider = f"analyst-replay-{uuid4().hex[:12]}"
    created = await client.post(
        "/api/system/model-providers",
        headers=admin,
        json={
            "provider_id": provider,
            "display_name": "Synthetic diet analysis only",
            "provider_type": "openai",
            "base_url": "http://api:8769/v1",
            "api_key": "synthetic-analyst-key",
            "capabilities": ["chat"],
            "enabled_models": [
                {
                    "id": "deterministic-diet-analysis-20261007",
                    "display_name": "synthetic",
                    "type": "chat",
                    "source": "manual",
                }
            ],
            "is_enabled": True,
        },
    )
    assert created.status_code == 200, created.text
    binding = await client.post(
        f"{ROOT}/members/{member}/diet-analyst", headers=headers, json={"client_request_id": str(uuid4())}
    )
    assert binding.status_code == 201, binding.text
    thread = binding.json()["thread_id"]
    body = {"agent_slug": "health-diet-analyst", "thread_id": thread, "query": "synthetic"}
    requests, valid_run = [], None
    try:
        unavailable = await client.post(
            "/api/agent/runs", headers=headers, json={**body, "meta": {"request_id": str(uuid4())}}
        )
        assert unavailable.status_code == 503, unavailable.text
        configured = await client.put(
            f"{ROOT}/configuration",
            headers=admin,
            json={
                "consultation_model": consultation_model,
                "diet_analysis_model": f"{provider}:deterministic-diet-analysis-20261007",
                "policy_version": configuration["policy_version"],
                "cloud_processing_reviewed": True,
            },
        )
        assert configured.status_code == 200 and configured.json()["diet_analysis"]["available"], configured.text
        config = configured.json()
        consent_fields = {"accepted": True, "policy_version": config["policy_version"]}
        assert (
            await client.post(
                f"{ROOT}/members/{member}/processing-consents",
                headers=headers,
                json={**consent_fields, "purpose": "consultation", "processor": config["consultation"]["processor"]},
            )
        ).status_code == 200
        denied_key = str(uuid4())
        denied = await client.post(
            "/api/agent/runs", headers=headers, json={**body, "meta": {"request_id": denied_key}}
        )
        assert denied.status_code == 403, denied.text
        async with pg_manager.get_async_session_context() as session:
            for model in (AgentRunRequest, AgentRun, Message):
                assert await session.scalar(select(model).where(model.request_id == denied_key)) is None
        consent = await client.post(
            f"{ROOT}/members/{member}/processing-consents",
            headers=headers,
            json={**consent_fields, "purpose": "diet_analysis", "processor": config["diet_analysis"]["processor"]},
        )
        assert consent.status_code == 200, consent.text
        for mode in ("valid", "invalid", "foreign", "stale", "questions", "period"):
            request, token = str(uuid4()), uuid4().hex
            requests.append(request)
            query = f"HEALTH_DIET_ANALYSIS_E2E:{token}:{mode}" + (f":{other_record['id']}" if mode == "foreign" else "")
            started = await client.post(
                "/api/agent/runs", headers=headers, json={**body, "query": query, "meta": {"request_id": request}}
            )
            assert started.status_code == 200, started.text
            run_id = started.json()["run_id"]
            events = await collect_sse(client, headers, run_id)
            assert events[-1][0] == "end" and events[-1][1]["request_id"] == request
            assert not any("message_delta" in str(event) for _, event in events)
            result = await client.get(f"/api/agent/runs/{run_id}/result", headers=headers)
            assert result.json()["status"] == ("completed" if mode in {"valid", "questions", "period"} else "failed"), (
                result.text
            )
            async with pg_manager.get_async_session_context() as session:
                run = await session.get(AgentRun, run_id)
                message = await session.get(Message, run.output_message_id)
                assert message.run_id == run_id and message.id == result.json()["final_message_id"]
                if mode == "valid":
                    valid_run = run_id
                    final = json.loads(message.content)
                    assert final == json.loads(result.json()["output"])
                    assert final["nutrition"]["totals"]["energy_kcal"] == "120.00"
                    assert final["nutrition"]["totals"]["sodium_mg"] is None
                    assert final["records"] == [{"record_id": record["id"], "source_version": 1}]
                    assert run.input_payload["health_processing"]["processor"] == config["diet_analysis"]["processor"]
                    resources = run.manifest["resources"]
                    assert resources["tools"] == [
                        "list_analysis_meals",
                        "analyze_confirmed_meal",
                        "analyze_confirmed_period",
                    ]
                    assert [skill["slug"] for skill in resources["skills"]] == ["family-diet-analyst"]
                elif mode == "questions":
                    assert json.loads(message.content)["status"] == "needs_input"
                elif mode == "period":
                    final = json.loads(message.content)
                    assert final["scope"] == "confirmed_period"
                    assert final["nutrition"]["totals"]["energy_kcal"]["recorded_total"] == "120.00"
                    assert len(final["coverage"]["dates_without_records"]) == 6
                    assert final["nutrition"]["totals"]["sodium_mg"]["recorded_total"] is None
                else:
                    assert {"invalid": "analyst_output_invalid", "foreign": "not_found", "stale": "version_conflict"}[
                        mode
                    ] in run.error_message
                assert (await session.get(DietLog, record["id"])).snapshot == record["snapshot"]
        stale = BaseContext(
            uid=users[0]["uid"],
            thread_id=thread,
            run_id=valid_run,
            request_id=requests[0],
            worker_id="expired-worker",
            model=config["diet_analysis"]["model"],
        )
        with pytest.raises(HealthVisionError, match="execution_not_owned"):
            await analyst_meal_records(stale)
        async with pg_manager.get_async_session_context() as session:
            draft = await session.get(VisionDraft, draft_id)
            draft.review_status = "retracted"
        hidden = await client.get(f"/api/agent/runs/{valid_run}/result", headers=headers)
        assert hidden.status_code == 200 and hidden.json()["status"] == "failed", hidden.text
        assert hidden.json()["error"]["type"] == "run_not_found" and not hidden.json().get("output")
    finally:
        await drain_requests(client, headers, requests)
        assert (await client.put(f"{ROOT}/configuration", headers=admin, json={})).status_code == 200
        assert (await client.delete(f"/api/system/model-providers/{provider}", headers=admin)).status_code == 200

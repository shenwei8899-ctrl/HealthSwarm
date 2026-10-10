"""隔离API/Worker/SSE/PG证明固定四工具目标只读与历史事实独立。"""

import hashlib
import json
import os
from copy import deepcopy
from uuid import uuid4

import pytest
from sqlalchemy import or_, select

from test.e2e.test_health_consultation_e2e import collect_sse, drain_requests, isolated_health  # noqa: F401
from test.integration.services.test_health_agent_personal_targets_http import bound_targets
from test.integration.services.test_health_diet_analysis_http import confirm_analysis_meal
from test.integration.services.test_health_vision_http import ROOT, health_http  # noqa: F401
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_business import AUDIT_MESSAGE_TYPES, AgentRun, Message, TOOL_AUDIT_MESSAGE_TYPE
from yuxi.storage.postgres.models_health import DietLog, HealthConsultation, HealthRuleSnapshot
from yuxi.utils.datetime_utils import utc_now_naive

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.slow,
    pytest.mark.asyncio,
    pytest.mark.skipif(os.getenv("HEALTH_CONSULTATION_E2E_ISOLATED") != "true", reason="仅独立合成槽位"),
]


def digest(value):
    """规范化hash独立于生产函数，目标数字由手写oracle330验证。"""
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()


async def test_bound_target_real_worker_current_reference_and_source_withdrawal(isolated_health):  # noqa: F811
    client, users, configuration, consultation_model = isolated_health
    headers, admin = users[0]["headers"], users[2]["headers"]
    current, target, entry, _, created = await bound_targets(client, users)
    member, thread = current["member"], created["thread_id"]
    record, _ = await confirm_analysis_meal(client, headers, admin, member)
    provider = f"bound-target-replay-{uuid4().hex[:12]}"
    response = await client.post(
        "/api/system/model-providers",
        headers=admin,
        json={
            "provider_id": provider,
            "display_name": "Synthetic target analyst only",
            "provider_type": "openai",
            "base_url": "http://api:8775/v1",
            "api_key": "synthetic-target-key",
            "capabilities": ["chat"],
            "enabled_models": [
                {
                    "id": "deterministic-bound-target-20261010",
                    "display_name": "synthetic",
                    "type": "chat",
                    "source": "manual",
                }
            ],
            "is_enabled": True,
        },
    )
    assert response.status_code == 200, response.text
    requests, completed = [], []
    try:
        response = await client.put(
            f"{ROOT}/configuration",
            headers=admin,
            json={
                "consultation_model": consultation_model,
                "diet_analysis_model": f"{provider}:deterministic-bound-target-20261010",
                "policy_version": configuration["policy_version"],
                "cloud_processing_reviewed": True,
            },
        )
        assert response.status_code == 200 and response.json()["diet_analysis"]["available"], response.text
        approved = response.json()["diet_analysis"]
        consent = await client.post(
            f"{ROOT}/members/{member}/processing-consents",
            headers=headers,
            json={
                "accepted": True,
                "purpose": "diet_analysis",
                "processor": approved["processor"],
                "policy_version": configuration["policy_version"],
            },
        )
        assert consent.status_code == 200, consent.text
        for mode in ("single", "invalid", "period1", "period7", "period30", "questions", "no_target"):
            request = str(uuid4())
            requests.append(request)
            started = await client.post(
                "/api/agent/runs",
                headers=headers,
                json={
                    "agent_slug": "health-diet-analyst",
                    "thread_id": thread,
                    "query": f"HEALTH_AGENT_TARGET_E2E:{uuid4().hex}:{mode}",
                    "meta": {"request_id": request},
                },
            )
            assert started.status_code == 200, started.text
            run_id = started.json()["run_id"]
            events = await collect_sse(client, headers, run_id)
            assert events[-1][0] == "end" and events[-1][1]["request_id"] == request
            assert not any("message_delta" in str(event) for _, event in events)
            read = await client.get(f"/api/agent/runs/{run_id}/result", headers=headers)
            assert read.status_code == 200 and read.json()["status"] == (
                "failed" if mode == "invalid" else "completed"
            ), read.text
            async with pg_manager.get_async_session_context() as session:
                run = await session.get(AgentRun, run_id)
                binding = await session.get(HealthConsultation, run.conversation_id)
                assert run.input_payload["health_processing"]["personal_target_selection_hash"] == digest(
                    binding.personal_target_selection
                )
                assert binding.personal_target_selection["selection"] == entry["target_selection"]
                assert run.manifest["resources"]["tools"] == [
                    "list_analysis_meals",
                    "analyze_confirmed_meal",
                    "analyze_confirmed_period",
                    "get_bound_personal_targets",
                ]
                if mode == "invalid":
                    assert run.output_message_id is None and "analyst_output_invalid" in run.error_message
                    assert read.json()["final_message_id"] is None and not read.json().get("output")
                    assert (
                        await session.scalar(
                            select(Message).where(
                                Message.run_id == run_id,
                                Message.role == "assistant",
                                or_(Message.message_type.is_(None), Message.message_type.notin_(AUDIT_MESSAGE_TYPES)),
                            )
                        )
                        is None
                    )
                    continue
                completed.append(run_id)
                message = await session.get(Message, run.output_message_id)
                assert message.run_id == run_id and message.request_id == request
                assert message.id == read.json()["final_message_id"]
                final = json.loads(message.content)
                assert final == json.loads(read.json()["output"])
                referenced = final["current_personal_targets"]
                assert referenced["energy_kcal"] == "330" and referenced["source_hash"] == digest(target)
                assert referenced["applied_to_record_window"] is False
                assert referenced["bounds"]["energy_kcal"] == {"minimum": "330", "maximum": "330"}
                assert not {"inputs", "formula", "formula_bounds", "attestations", "difference", "trend"} & set(
                    referenced
                )
                assert final["personal_target"] is None and final["personalized"] is False
                assert "difference" not in final and "daily_complete" not in final
                if mode == "questions":
                    assert final["status"] == "needs_input"
                elif mode.startswith("period"):
                    days = int(mode.removeprefix("period"))
                    assert final["nutrition"]["totals"]["energy_kcal"]["recorded_total"] == "120.00"
                    assert final["nutrition"]["totals"]["sodium_mg"]["recorded_total"] is None
                    assert final["coverage"]["window_days"] == days and final["coverage"]["days_with_records"] == 1
                    assert len(final["coverage"]["dates_without_records"]) == days - 1
                    assert final["trend"]["direction"] is None
                else:
                    assert final["nutrition"]["totals"]["energy_kcal"] == "120.00"
                    assert final["nutrition"]["totals"]["sodium_mg"] is None
                if mode == "no_target":
                    assert (
                        await session.scalar(
                            select(Message.id).where(
                                Message.run_id == run_id,
                                Message.message_type == TOOL_AUDIT_MESSAGE_TYPE,
                                Message.extra_metadata["tool_name"].as_string() == "get_bound_personal_targets",
                            )
                        )
                        is None
                    )
                assert (await session.get(DietLog, record["id"])).snapshot == record["snapshot"]
        async with pg_manager.get_async_session_context() as session:
            row = await session.get(HealthRuleSnapshot, target["sources"]["rules"]["id"])
            original = row.revoked_at
            row.revoked_at = utc_now_naive()
        try:
            for run_id in completed:
                hidden = await client.get(f"/api/agent/runs/{run_id}/result", headers=headers)
                assert hidden.json()["status"] == "failed" and not hidden.json().get("output"), hidden.text
        finally:
            async with pg_manager.get_async_session_context() as session:
                (await session.get(HealthRuleSnapshot, target["sources"]["rules"]["id"])).revoked_at = original
        async with pg_manager.get_async_session_context() as session:
            binding = await session.get(HealthConsultation, run.conversation_id)
            original = deepcopy(binding.personal_target_selection)
            binding.personal_target_selection = None
        try:
            hidden = await client.get(f"/api/agent/runs/{completed[-1]}/result", headers=headers)
            assert hidden.json()["status"] == "failed" and not hidden.json().get("output"), hidden.text
        finally:
            async with pg_manager.get_async_session_context() as session:
                (await session.get(HealthConsultation, run.conversation_id)).personal_target_selection = original
    finally:
        await drain_requests(client, headers, requests)
        assert (await client.put(f"{ROOT}/configuration", headers=admin, json={})).status_code == 200
        assert (await client.delete(f"/api/system/model-providers/{provider}", headers=admin)).status_code == 200

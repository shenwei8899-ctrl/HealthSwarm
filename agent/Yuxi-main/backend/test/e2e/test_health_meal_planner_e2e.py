"""隔离API、worker、PG和SSE的配餐师发布与最终输出验收。"""

import json
import os
from uuid import uuid4

import pytest
from sqlalchemy import select

from test.e2e.test_health_consultation_e2e import collect_sse, drain_requests, isolated_health  # noqa: F401
from test.integration.services.test_health_vision_http import ROOT, create_member, health_http  # noqa: F401
from test.integration.services.test_health_meal_planner_http import publish_planner_recipe
from yuxi.agents.context import BaseContext
from yuxi.services.health_meal_plan_service import meal_plan_recipes_for_run
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_business import AgentRun, AgentRunRequest, Message
from yuxi.storage.postgres.models_health import DietLog, HealthMealPlan, HealthMealPlanPreview

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.e2e,
    pytest.mark.slow,
    pytest.mark.skipif(os.getenv("HEALTH_CONSULTATION_E2E_ISOLATED") != "true", reason="仅独立合成槽位"),
]


async def test_planner_worker_authoritative_result_independent_consent_and_forged_receipts(isolated_health):  # noqa: F811
    """当前Run回执成功投影；伪造审核字段和跨Run回执都不能成功。"""
    client, users, configuration, consultation_model = isolated_health
    headers, admin = users[0]["headers"], users[2]["headers"]
    provider = f"planner-replay-{uuid4().hex[:12]}"
    created = await client.post(
        "/api/system/model-providers",
        headers=admin,
        json={
            "provider_id": provider,
            "display_name": "Synthetic planner only",
            "provider_type": "openai",
            "base_url": "http://api:8768/v1",
            "api_key": "synthetic-planner-key",
            "capabilities": ["chat"],
            "enabled_models": [
                {
                    "id": "deterministic-meal-plan-20261006",
                    "display_name": "synthetic",
                    "type": "chat",
                    "source": "manual",
                }
            ],
            "is_enabled": True,
        },
    )
    assert created.status_code == 200, created.text
    requests = []
    member = await create_member(client, headers)
    key = str(uuid4())
    bound = await client.post(f"{ROOT}/members/{member}/meal-planner", headers=headers, json={"client_request_id": key})
    assert bound.status_code == 201, bound.text
    thread = bound.json()["thread_id"]
    body = {"agent_slug": "health-meal-planner", "thread_id": thread, "query": "synthetic"}
    try:
        assert not configuration["meal_plan"]["available"]
        unavailable = await client.post(
            "/api/agent/runs", headers=headers, json={**body, "meta": {"request_id": str(uuid4())}}
        )
        assert unavailable.status_code == 503, unavailable.text
        configured = await client.put(
            f"{ROOT}/configuration",
            headers=admin,
            json={
                "consultation_model": consultation_model,
                "meal_plan_model": f"{provider}:deterministic-meal-plan-20261006",
                "policy_version": configuration["policy_version"],
                "cloud_processing_reviewed": True,
            },
        )
        assert configured.status_code == 200 and configured.json()["meal_plan"]["available"], configured.text
        config = configured.json()
        accepted = await client.post(
            f"{ROOT}/members/{member}/processing-consents",
            headers=headers,
            json={
                "purpose": "consultation",
                "accepted": True,
                "processor": config["consultation"]["processor"],
                "policy_version": config["policy_version"],
            },
        )
        assert accepted.status_code == 200
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
            json={
                "purpose": "meal_plan",
                "accepted": True,
                "processor": config["meal_plan"]["processor"],
                "policy_version": config["policy_version"],
            },
        )
        assert consent.status_code == 200, consent.text
        first_preview = None
        for mode, expected_status in (
            ("valid", "completed"),
            ("invalid", "failed"),
            ("foreign", "failed"),
            ("questions", "completed"),
        ):
            token, request = uuid4().hex, str(uuid4())
            requests.append(request)
            await publish_planner_recipe(client, admin, f"合成配餐E2E-{token}")
            query = f"HEALTH_MEAL_PLANNER_E2E:{token}:{mode}" + (f":{first_preview}" if mode == "foreign" else "")
            started = await client.post(
                "/api/agent/runs", headers=headers, json={**body, "query": query, "meta": {"request_id": request}}
            )
            assert started.status_code == 200, started.text
            run_id = started.json()["run_id"]
            events = await collect_sse(client, headers, run_id)
            assert events[-1][0] == "end" and events[-1][1]["request_id"] == request
            assert not any("message_delta" in str(event) for _, event in events)
            result = await client.get(f"/api/agent/runs/{run_id}/result", headers=headers)
            assert result.json()["status"] == expected_status, result.text
            async with pg_manager.get_async_session_context() as session:
                run = await session.get(AgentRun, run_id)
                output = (
                    await session.get(Message, run.output_message_id) if run.output_message_id is not None else None
                )
                if expected_status == "completed":
                    assert output.run_id == run_id and output.id == result.json()["final_message_id"]
                if mode == "valid":
                    final = json.loads(output.content)
                    assert final == json.loads(result.json()["output"])
                    assert final["nutrition"]["totals"]["energy_kcal"] == "300.00"
                    assert final["personalized"] is False and final["professional_review"] == "not_reviewed"
                    first_preview = final["preview_id"]
                    preview = await session.get(HealthMealPlanPreview, first_preview)
                    assert (
                        preview.run_id == run_id
                        and preview.actor_uid == users[0]["uid"]
                        and preview.member_id == member
                    )
                    assert preview.snapshot["nutrition"] == final["nutrition"]
                    assert run.input_payload["health_processing"]["processor"] == config["meal_plan"]["processor"]
                    stale = BaseContext(
                        uid=users[0]["uid"],
                        thread_id=thread,
                        run_id=run_id,
                        request_id=request,
                        worker_id="expired-worker",
                        model=run.input_payload["health_processing"]["model"],
                    )
                elif mode == "questions":
                    assert json.loads(output.content)["status"] == "needs_input"
                else:
                    expected_error = "planner_output_invalid" if mode == "invalid" else "planner_receipt_invalid"
                    assert expected_error in run.error_message
                    assert output is None and result.json()["output"] == ""
                    assert (
                        await session.scalar(
                            select(Message).where(
                                Message.run_id == run_id, Message.role == "assistant", Message.message_type == "text"
                            )
                        )
                        is None
                    )
                assert await session.scalar(select(DietLog).where(DietLog.member_id == member)) is None
                assert await session.scalar(select(HealthMealPlan).where(HealthMealPlan.member_id == member)) is None
            if mode == "valid":
                with pytest.raises(HealthVisionError, match="execution_not_owned"):
                    await meal_plan_recipes_for_run(stale, "合成配餐")
        save_key = str(uuid4())
        saved = await client.post(
            f"{ROOT}/members/{member}/meal-plans",
            headers={**headers, "Idempotency-Key": save_key},
            json={"client_request_id": save_key, "preview_id": first_preview},
        )
        assert saved.status_code == 201 and saved.json()["version"] == 1, saved.text
    finally:
        await drain_requests(client, headers, requests)
        reset = await client.put(
            f"{ROOT}/configuration",
            headers=admin,
            json={
                "consultation_model": consultation_model,
                "policy_version": configuration["policy_version"],
                "cloud_processing_reviewed": True,
            },
        )
        assert reset.status_code == 200 and not reset.json()["meal_plan"]["available"]
        assert (await client.delete(f"/api/system/model-providers/{provider}", headers=admin)).status_code == 200

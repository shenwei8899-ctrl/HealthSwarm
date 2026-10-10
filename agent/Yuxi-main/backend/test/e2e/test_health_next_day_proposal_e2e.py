"""真实 HTTP、PG、Worker 验收显式次日提议及零正式副作用。"""

import json
import os
from copy import deepcopy
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select

from test.e2e.test_health_consultation_e2e import collect_sse, drain_requests, isolated_health  # noqa: F401
from test.integration.services.test_health_meal_planner_http import publish_planner_recipe
from test.integration.services.test_health_vision_http import ROOT, create_member, health_http  # noqa: F401
from test.support.health_next_day_planner_replay_server import MODEL
from yuxi.services.health_daily_service import business_date
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_business import AgentRun, AgentRunRequest, Message
from yuxi.storage.postgres.models_health import (
    DietLog,
    FoodRecord,
    HealthMealPlan,
    HealthMealPlanAdoption,
    HealthMealPlanPreview,
    HealthNextDayProposal,
    RecipeVersion,
)

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.e2e,
    pytest.mark.slow,
    pytest.mark.skipif(os.getenv("HEALTH_CONSULTATION_E2E_ISOLATED") != "true", reason="仅独立合成槽位"),
]


async def test_worker_tomorrow_proposal_exact_identity_sources_and_user_only_write(isolated_health):  # noqa: F811
    """Worker 只产生预览，用户登记的每项关联与来源均由 PG 回读。"""
    client, users, configuration, consultation_model = isolated_health
    owner, admin = users[0], users[2]["headers"]
    headers = owner["headers"]
    provider = f"next-day-replay-{uuid4().hex[:12]}"
    created = await client.post(
        "/api/system/model-providers",
        headers=admin,
        json={
            "provider_id": provider,
            "display_name": "Synthetic next day planner only",
            "provider_type": "openai",
            "base_url": "http://api:8774/v1",
            "api_key": "synthetic-next-day-key",
            "capabilities": ["chat"],
            "enabled_models": [{"id": MODEL, "display_name": MODEL, "type": "chat", "source": "manual"}],
            "is_enabled": True,
        },
    )
    assert created.status_code == 200, created.text
    requests = []
    try:
        active_configuration = {
            "consultation_model": consultation_model,
            "meal_plan_model": f"{provider}:{MODEL}",
            "policy_version": configuration["policy_version"],
            "cloud_processing_reviewed": True,
        }
        configured = await client.put(f"{ROOT}/configuration", headers=admin, json=active_configuration)
        assert configured.status_code == 200 and configured.json()["meal_plan"]["available"], configured.text
        config = configured.json()
        member = await create_member(client, headers)
        other_member = await create_member(client, headers)
        bound = await client.post(
            f"{ROOT}/members/{member}/meal-planner", headers=headers, json={"client_request_id": str(uuid4())}
        )
        assert bound.status_code == 201, bound.text
        thread = bound.json()["thread_id"]
        consent = {
            "purpose": "meal_plan",
            "accepted": True,
            "processor": config["meal_plan"]["processor"],
            "policy_version": config["policy_version"],
        }
        assert (
            await client.post(f"{ROOT}/members/{member}/processing-consents", headers=headers, json=consent)
        ).status_code == 200
        results = []
        for mode in ("tomorrow", "tomorrow", "today", "questions", "invalid"):
            token, request_id = uuid4().hex, str(uuid4())
            requests.append(request_id)
            recipe_id = await publish_planner_recipe(client, admin, f"合成次日E2E-{token}")
            started = await client.post(
                "/api/agent/runs",
                headers=headers,
                json={
                    "agent_slug": "health-meal-planner",
                    "thread_id": thread,
                    "query": f"HEALTH_NEXT_DAY_E2E:{token}:{mode}",
                    "meta": {"request_id": request_id},
                },
            )
            assert started.status_code == 200, started.text
            run_id = started.json()["run_id"]
            events = await collect_sse(client, headers, run_id)
            assert events[-1][0] == "end" and events[-1][1]["request_id"] == request_id
            result = await client.get(f"/api/agent/runs/{run_id}/result", headers=headers)
            expected = "failed" if mode == "invalid" else "completed"
            assert result.json()["status"] == expected, result.text
            async with pg_manager.get_async_session_context() as session:
                run = await session.get(AgentRun, run_id)
                request = await session.scalar(select(AgentRunRequest).where(AgentRunRequest.request_id == request_id))
                assert request.dispatched_run_id == run.id and run.request_id == request_id
                assert run.uid == owner["uid"] and run.status == expected
                if mode == "invalid":
                    assert "planner_output_invalid" in run.error_message and run.output_message_id is None
                    payload, message_id = {}, 1
                else:
                    output = await session.get(Message, run.output_message_id)
                    assert output.run_id == run.id and output.request_id == request_id
                    assert output.id == result.json()["final_message_id"] and output.content == result.json()["output"]
                    payload, message_id = json.loads(output.content), output.id
                    if mode != "questions":
                        preview = await session.get(HealthMealPlanPreview, payload["preview_id"])
                        assert (
                            preview.run_id == run.id
                            and preview.member_id == member
                            and preview.actor_uid == owner["uid"]
                        )
                        assert payload["nutrition"]["totals"]["energy_kcal"] == "300.00"
                results.append(
                    {
                        "run_id": run_id,
                        "request_id": request_id,
                        "final_message_id": message_id,
                        "payload": payload,
                        "recipe_id": recipe_id,
                    }
                )
                assert (
                    await session.scalar(
                        select(HealthNextDayProposal).where(HealthNextDayProposal.actor_uid == owner["uid"])
                    )
                    is None
                )
                for model in (HealthMealPlan, HealthMealPlanAdoption, DietLog):
                    assert await session.scalar(select(model).where(model.member_id == member)) is None

        first, neighbor, today, questions, invalid = results
        endpoint = f"{ROOT}/members/{member}/meal-planner-runs/{first['run_id']}/next-day-proposals"
        body = {
            "client_request_id": str(uuid4()),
            "preview_id": first["payload"]["preview_id"],
            "source_date": business_date().isoformat(),
            "request_id": first["request_id"],
            "final_message_id": first["final_message_id"],
        }
        for actor in users[1:]:
            denied = await client.post(endpoint, headers=actor["headers"], json=body)
            assert denied.status_code == 404, denied.text
        for changed in (
            {"request_id": neighbor["request_id"]},
            {"final_message_id": neighbor["final_message_id"]},
            {"preview_id": neighbor["payload"]["preview_id"]},
            {"source_date": (business_date() - timedelta(days=1)).isoformat()},
        ):
            denied = await client.post(endpoint, headers=headers, json={**body, **changed})
            assert denied.status_code in {409, 410}, denied.text
        wrong_member = await client.post(endpoint.replace(member, other_member), headers=headers, json=body)
        assert wrong_member.status_code == 404, wrong_member.text
        for selected, expected_code in (
            (today, "proposal_date_invalid"),
            (questions, "planner_receipt_invalid"),
            (invalid, "answer_not_completed"),
        ):
            rejected = await client.post(
                f"{ROOT}/members/{member}/meal-planner-runs/{selected['run_id']}/next-day-proposals",
                headers=headers,
                json={
                    **body,
                    "request_id": selected["request_id"],
                    "final_message_id": selected["final_message_id"],
                    "preview_id": selected["payload"].get("preview_id", body["preview_id"]),
                },
            )
            assert rejected.status_code == 409 and rejected.json()["code"] == expected_code, rejected.text

        async with pg_manager.get_async_session_context() as session:
            (await session.get(AgentRun, first["run_id"])).output_message_id = neighbor["final_message_id"]
        try:
            wrong_pointer = await client.post(endpoint, headers=headers, json=body)
            assert wrong_pointer.status_code == 409 and wrong_pointer.json()["code"] == "answer_unavailable", (
                wrong_pointer.text
            )
        finally:
            async with pg_manager.get_async_session_context() as session:
                (await session.get(AgentRun, first["run_id"])).output_message_id = first["final_message_id"]

        async with pg_manager.get_async_session_context() as session:
            request = await session.scalar(
                select(AgentRunRequest).where(AgentRunRequest.request_id == first["request_id"])
            )
            request.dispatched_run_id = neighbor["run_id"]
        try:
            wrong_owner = await client.post(endpoint, headers=headers, json=body)
            assert wrong_owner.status_code == 410 and wrong_owner.json()["code"] == "source_invalidated", (
                wrong_owner.text
            )
        finally:
            async with pg_manager.get_async_session_context() as session:
                request = await session.scalar(
                    select(AgentRunRequest).where(AgentRunRequest.request_id == first["request_id"])
                )
                request.dispatched_run_id = first["run_id"]

        original_snapshot = deepcopy(first["payload"])
        async with pg_manager.get_async_session_context() as session:
            message = await session.get(Message, first["final_message_id"])
            original_content = message.content
            forged = deepcopy(original_snapshot)
            forged["nutrition"]["totals"]["energy_kcal"] = "0.00"
            message.content = json.dumps(forged)
        try:
            forged_result = await client.post(endpoint, headers=headers, json=body)
            assert forged_result.status_code == 410 and forged_result.json()["code"] == "source_invalidated", (
                forged_result.text
            )
        finally:
            async with pg_manager.get_async_session_context() as session:
                (await session.get(Message, first["final_message_id"])).content = original_content

        revoked = await client.post(
            f"{ROOT}/members/{member}/processing-consents", headers=headers, json={**consent, "accepted": False}
        )
        assert revoked.status_code == 200
        denied = await client.post(endpoint, headers=headers, json=body)
        assert denied.status_code == 403, denied.text
        assert (
            await client.post(f"{ROOT}/members/{member}/processing-consents", headers=headers, json=consent)
        ).status_code == 200

        changed_configuration = await client.put(
            f"{ROOT}/configuration",
            headers=admin,
            json={**active_configuration, "policy_version": "synthetic-next-day-changed-v2"},
        )
        assert changed_configuration.status_code == 200
        try:
            changed_policy = await client.post(endpoint, headers=headers, json=body)
            assert changed_policy.status_code == 409 and changed_policy.json()["code"] == "policy_changed", (
                changed_policy.text
            )
        finally:
            restored = await client.put(f"{ROOT}/configuration", headers=admin, json=active_configuration)
            assert restored.status_code == 200

        async with pg_manager.get_async_session_context() as session:
            recipe = await session.get(RecipeVersion, first["recipe_id"])
            food_id = recipe.ingredients[0]["food"]["id"]
            food = await session.get(FoodRecord, food_id)
            original_name = food.name
            food.name = "合成来源变化"
        try:
            changed_source = await client.post(endpoint, headers=headers, json=body)
            assert changed_source.status_code == 410 and changed_source.json()["code"] == "source_invalidated", (
                changed_source.text
            )
        finally:
            async with pg_manager.get_async_session_context() as session:
                (await session.get(FoodRecord, food_id)).name = original_name

        async with pg_manager.get_async_session_context() as session:
            assert (
                await session.scalar(
                    select(HealthNextDayProposal).where(HealthNextDayProposal.actor_uid == owner["uid"])
                )
                is None
            )
        registered = await client.post(endpoint, headers=headers, json=body)
        assert registered.status_code == 201, registered.text
        result = registered.json()
        assert result["agent_run_id"] == first["run_id"] and result["request_id"] == first["request_id"]
        assert result["final_message_id"] == first["final_message_id"] and result["preview_id"] == body["preview_id"]
        assert result["formal_plan_saved"] is False and result["current"] is True and result["status"] == "proposed"
        assert (await client.post(endpoint, headers=headers, json=body)).json() == result
        plain = await client.post(
            f"{ROOT}/members/{member}/next-day-proposals",
            headers=headers,
            json={key: body[key] for key in ("client_request_id", "preview_id", "source_date")},
        )
        assert plain.status_code == 409 and plain.json()["code"] == "request_conflict", plain.text
        read = await client.get(f"{ROOT}/next-day-proposals/{result['proposal_id']}", headers=headers)
        assert read.status_code == 200 and read.json()["snapshot"] == result["snapshot"], read.text
        async with pg_manager.get_async_session_context() as session:
            proposals = list(
                (
                    await session.scalars(
                        select(HealthNextDayProposal).where(HealthNextDayProposal.actor_uid == owner["uid"])
                    )
                ).all()
            )
            assert len(proposals) == 1 and proposals[0].id == result["proposal_id"]
            assert proposals[0].preview_id == body["preview_id"] and proposals[0].member_id == member
            assert proposals[0].snapshot["nutrition"]["totals"]["energy_kcal"] == "300.00"
            for model in (HealthMealPlan, HealthMealPlanAdoption, DietLog):
                assert await session.scalar(select(model).where(model.member_id == member)) is None
        revoked = await client.put(
            f"{ROOT}/members/{member}/grants", headers=headers, json={"actor_uid": owner["uid"], "scopes": []}
        )
        assert revoked.status_code == 200
        denied_replay = await client.post(endpoint, headers=headers, json=body)
        assert denied_replay.status_code == 404 and "300.00" not in denied_replay.text, denied_replay.text
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

"""真实API/worker/SSE两轮家庭配餐和独立PG结果证明。"""

import json
import os
from uuid import uuid4

import pytest
from sqlalchemy import select, func

from test.e2e.test_health_consultation_e2e import collect_sse, drain_requests, isolated_health  # noqa: F401
from test.integration.services.test_health_vision_http import health_http  # noqa: F401
from test.integration.services.test_health_family_planner_http import family_runtime, bind_family  # noqa: F401
from test.integration.services.test_health_family_safe_plan_http import assert_original
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_business import AgentRun, Message
from yuxi.storage.postgres.models_health import HealthFamilyPlannerPreview, HealthProcessingConsent

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.slow,
    pytest.mark.asyncio,
    pytest.mark.skipif(os.getenv("HEALTH_CONSULTATION_E2E_ISOLATED") != "true", reason="仅独立合成槽位"),
]


async def test_family_worker_two_turns_four_tools_and_final_selector_guards(family_runtime):  # noqa: F811
    """家庭运行仅装配四工具，旧checkpoint可读但最终只选本Run收据。"""
    client, users, current, _ = family_runtime
    headers = users[0]["headers"]
    bound, _ = await bind_family(client, users, current)
    assert bound.status_code == 201, bound.text
    thread = bound.json()["thread_id"]
    requests, valid_receipts, last_run, completed_run = [], [], None, None
    try:
        for mode, status in (
            ("participation", "completed"),
            ("participation", "completed"),
            ("swap", "completed"),
            ("regeneration", "completed"),
            ("questions", "completed"),
            ("invalid", "failed"),
            ("foreign", "failed"),
        ):
            key = str(uuid4())
            requests.append(key)
            query = f"FAMILY_PLANNER_E2E:{uuid4().hex}:{mode}" + (f":{valid_receipts[0]}" if mode == "foreign" else "")
            submitted = await client.post(
                "/api/agent/runs",
                headers=headers,
                json={
                    "agent_slug": "health-meal-planner",
                    "thread_id": thread,
                    "query": query,
                    "meta": {"request_id": key},
                },
            )
            assert submitted.status_code == 200, submitted.text
            last_run = submitted.json()["run_id"]
            events = await collect_sse(client, headers, last_run)
            assert events[-1][0] == "end" and not any("message_delta" in str(event) for _, event in events)
            result = await client.get(f"/api/agent/runs/{last_run}/result", headers=headers)
            assert result.status_code == 200 and result.json()["status"] == status, result.text
            async with pg_manager.get_async_session_context() as session:
                run = await session.get(AgentRun, last_run)
                assert run.request_id == key and run.agent_slug == "health-meal-planner"
                assert run.manifest["resources"]["tools"] == [
                    "get_family_plan_context",
                    "preview_family_plan_swap",
                    "preview_family_plan_regeneration",
                    "preview_family_plan_participation",
                ]
                assert [s["slug"] for s in run.manifest["resources"]["skills"]] == ["family-meal-planner"]
                assert run.input_payload["health_processing"]["family_selection_hash"]
                if status == "completed":
                    message = await session.get(Message, run.output_message_id)
                    final = json.loads(message.content)
                    assert message.run_id == last_run and final == json.loads(result.json()["output"])
                    if completed_run is None:
                        completed_run = last_run
                    if mode == "questions":
                        assert final["status"] == "needs_input"
                        assert (
                            await session.scalar(
                                select(func.count())
                                .select_from(HealthFamilyPlannerPreview)
                                .where(HealthFamilyPlannerPreview.run_id == last_run)
                            )
                            == 0
                        )
                    else:
                        receipt = await session.get(HealthFamilyPlannerPreview, final["preview_id"])
                        assert receipt.run_id == last_run and receipt.actor_uid == users[0]["uid"]
                        assert final["result"] == receipt.snapshot and final["scope"] == "family_saved_plan"
                        if mode == "participation":
                            assert final["result"]["plan_snapshot"]["nutrition"]["totals"]["energy_kcal"] == "365.00"
                            valid_receipts.append(receipt.id)
                else:
                    assert not result.json().get("output")
                    assert (
                        "planner_output_invalid" if mode == "invalid" else "planner_receipt_invalid"
                    ) in run.error_message
        assert valid_receipts[0] != valid_receipts[1]
        checkpoint = await pg_manager.get_langgraph_checkpointer().aget_tuple({"configurable": {"thread_id": thread}})
        assert checkpoint is not None and checkpoint.checkpoint["channel_values"]["messages"]
        await assert_original(current)
        # 完成后第二成员撤回独立配餐同意，结果/事件/历史及新请求均不能继续访问。
        async with pg_manager.get_async_session_context() as session:
            consent = await session.get(HealthProcessingConsent, (current["second"], users[0]["uid"], "meal_plan"))
            from yuxi.utils.datetime_utils import utc_now_naive

            consent.revoked_at = utc_now_naive()
        denied = await client.get(f"/api/agent/runs/{completed_run}/result", headers=headers)
        assert denied.status_code == 200 and denied.json()["error"]["type"] == "run_not_found", denied.text
        assert denied.json()["output"] == ""
        events = await client.get(f"/api/agent/runs/{completed_run}/events", headers=headers)
        assert events.status_code == 200 and "event: error" in events.text, events.text
        event_payloads = [json.loads(line[6:]) for line in events.text.splitlines() if line.startswith("data: ")]
        assert event_payloads == [{"run_id": completed_run, "message": "运行任务不存在"}]
        history = await client.get(
            f"/api/agent/thread/{thread}/requests", headers=headers, params={"agent_slug": "health-meal-planner"}
        )
        assert history.status_code == 404, history.text
        denied_key = str(uuid4())
        queued = await client.post(
            "/api/agent/runs",
            headers=headers,
            json={
                "agent_slug": "health-meal-planner",
                "thread_id": thread,
                "query": "synthetic",
                "meta": {"request_id": denied_key},
            },
        )
        assert queued.status_code == 403, queued.text
        from yuxi.storage.postgres.models_business import AgentRunRequest

        async with pg_manager.get_async_session_context() as session:
            for model in (AgentRun, AgentRunRequest, Message):
                assert await session.scalar(select(model).where(model.request_id == denied_key)) is None
    finally:
        await drain_requests(client, headers, requests)

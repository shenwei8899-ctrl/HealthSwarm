"""初始个人/家庭真实worker、SSE、两轮checkpoint与PG结果。"""

import json
import os
from uuid import uuid4

import pytest
from sqlalchemy import select, func

from test.e2e.test_health_consultation_e2e import collect_sse, drain_requests, isolated_health  # noqa: F401
from test.integration.services.test_health_vision_http import ROOT, health_http  # noqa: F401
from test.integration.services.test_health_initial_planner_http import initial_runtime, bind_initial  # noqa: F401
from test.integration.services.test_health_initial_meal_plan_http import assert_no_plan, save
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_business import AgentRun, AgentRunRequest, Message
from yuxi.storage.postgres.models_health import HealthInitialPlanPreview, HealthProcessingConsent, HealthMealPlan
from yuxi.utils.datetime_utils import utc_now_naive

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.slow,
    pytest.mark.asyncio,
    pytest.mark.skipif(os.getenv("HEALTH_CONSULTATION_E2E_ISOLATED") != "true", reason="仅独立合成槽位"),
]


@pytest.mark.parametrize("family", [False, True])
async def test_initial_worker_two_turns_receipts_and_final_guards(initial_runtime, family):  # noqa: F811
    """固定两工具首次生成，跨Run和伪造选择失败，用户确认才有Plan。"""
    client, users, current, consent = initial_runtime
    headers = users[0]["headers"]
    bound, _ = await bind_initial(client, users, current, family=family)
    assert bound.status_code == 201, bound.text
    thread, requests, receipts, completed = bound.json()["thread_id"], [], [], None
    try:
        for mode, status in (
            ("ready", "completed"),
            ("ready", "completed"),
            ("questions", "completed"),
            ("invalid", "failed"),
            ("foreign", "failed"),
        ):
            key = str(uuid4())
            requests.append(key)
            query = f"INITIAL_PLANNER_E2E:{uuid4().hex}:{mode}" + (f":{receipts[0]}" if mode == "foreign" else "")
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
            run_id = submitted.json()["run_id"]
            events = await collect_sse(client, headers, run_id)
            assert events[-1][0] == "end" and not any("message_delta" in str(event) for _, event in events)
            assert "UNVERIFIED_INITIAL_MODEL_TEXT" not in json.dumps(events)
            result = await client.get(f"/api/agent/runs/{run_id}/result", headers=headers)
            assert result.status_code == 200 and result.json()["status"] == status, result.text
            assert "UNVERIFIED_INITIAL_MODEL_TEXT" not in result.text
            history = await client.get(f"/api/chat/thread/{thread}/history", headers=headers)
            assert history.status_code == 200 and "UNVERIFIED_INITIAL_MODEL_TEXT" not in history.text, history.text
            async with pg_manager.get_async_session_context() as session:
                run = await session.get(AgentRun, run_id)
                assert run.request_id == key and run.agent_slug == "health-meal-planner"
                assert run.manifest["resources"]["tools"] == ["get_initial_plan_context", "preview_initial_meal_plan"]
                assert [s["slug"] for s in run.manifest["resources"]["skills"]] == ["family-meal-planner"]
                assert run.input_payload["health_processing"]["initial_selection_hash"]
                if status == "completed":
                    message = await session.get(Message, run.output_message_id)
                    final = json.loads(message.content)
                    assert message.run_id == run_id and final == json.loads(result.json()["output"])
                    completed = completed or run_id
                    if mode == "questions":
                        assert final["status"] == "needs_input"
                        assert (
                            await session.scalar(
                                select(func.count())
                                .select_from(HealthInitialPlanPreview)
                                .where(HealthInitialPlanPreview.run_id == run_id)
                            )
                            == 0
                        )
                    else:
                        receipt = await session.get(HealthInitialPlanPreview, final["preview_id"])
                        assert (
                            receipt.run_id == run_id
                            and receipt.actor_uid == users[0]["uid"]
                            and receipt.conversation_id == run.conversation_id
                        )
                        assert final["plan_snapshot"]["nutrition"]["totals"]["energy_kcal"] == (
                            "396.00" if family else "330.00"
                        )
                        assert final["plan_snapshot"]["full_health_profile_available"] is False
                        assert final["professional_review"] == "not_a_professional_decision"
                        receipts.append(receipt.id)
                else:
                    assert not result.json().get("output")
                    assert run.output_message_id is None
                    assert (
                        await session.scalar(
                            select(Message).where(
                                Message.run_id == run_id, Message.role == "assistant", Message.message_type == "text"
                            )
                        )
                        is None
                    )
                    assert (
                        "planner_output_invalid" if mode == "invalid" else "planner_receipt_invalid"
                    ) in run.error_message
        assert receipts[0] != receipts[1]
        checkpoint = await pg_manager.get_langgraph_checkpointer().aget_tuple({"configurable": {"thread_id": thread}})
        assert checkpoint is not None and checkpoint.checkpoint["channel_values"]["messages"]
        await assert_no_plan(users[0]["uid"])
        # 私有输出在独立用途同意撤回后不可见，恢复后允许用户显式确认保存。
        mid = current["second"] if family else current["member"]
        async with pg_manager.get_async_session_context() as session:
            (
                await session.get(HealthProcessingConsent, (mid, users[0]["uid"], "meal_plan"))
            ).revoked_at = utc_now_naive()
        denied = await client.get(f"/api/agent/runs/{completed}/result", headers=headers)
        assert (
            denied.status_code == 200
            and denied.json()["error"]["type"] == "run_not_found"
            and denied.json()["output"] == ""
        ), denied.text
        history = await client.get(
            f"/api/agent/thread/{thread}/requests", headers=headers, params={"agent_slug": "health-meal-planner"}
        )
        assert history.status_code == 404, history.text
        key = str(uuid4())
        denied = await client.post(
            "/api/agent/runs",
            headers=headers,
            json={
                "agent_slug": "health-meal-planner",
                "thread_id": thread,
                "query": "synthetic",
                "meta": {"request_id": key},
            },
        )
        assert denied.status_code == 403, denied.text
        async with pg_manager.get_async_session_context() as session:
            for model in (AgentRun, AgentRunRequest, Message):
                assert await session.scalar(select(model).where(model.request_id == key)) is None
        restored = await client.post(f"{ROOT}/members/{mid}/processing-consents", headers=headers, json=consent)
        assert restored.status_code == 200
        saved = await save(client, headers, current, receipts[1])
        assert saved.status_code == 201 and saved.json()["quality_check"]["safety_check"]["status"] == "passed", (
            saved.text
        )
        async with pg_manager.get_async_session_context() as session:
            assert (await session.get(HealthMealPlan, saved.json()["plan_id"])).version == 1
    finally:
        await drain_requests(client, headers, requests)

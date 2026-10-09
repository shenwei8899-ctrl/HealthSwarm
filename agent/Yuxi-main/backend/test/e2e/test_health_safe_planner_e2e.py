"""隔离API/worker/SSE及PG证明单成员安全预览、checkpoint和撤销。"""

import asyncio
import json
import os
from copy import deepcopy
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import func, select

from test.e2e.test_health_consultation_e2e import collect_sse, drain_requests, isolated_health, wait_until  # noqa: F401
from test.integration.services.test_health_safe_planner_http import (
    assert_safe_private_denied,
    bind_safe,
    safe_business_facts,
    safe_runtime,  # noqa: F401
)
from test.integration.services.test_health_vision_http import ROOT, health_http  # noqa: F401
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_business import AgentRun, AgentRunAttempt, Message
from yuxi.storage.postgres.models_health import HealthConsultation, HealthSafePlannerPreview, RecipeVersion

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.slow,
    pytest.mark.asyncio,
    pytest.mark.skipif(os.getenv("HEALTH_CONSULTATION_E2E_ISOLATED") != "true", reason="仅独立合成槽位"),
]


async def submit_safe_run(client, headers, thread, token, mode, request_id, *, foreign=None):
    """真实入口提交一轮，身份、来源与工具不由测试请求传给模型。"""
    query = f"SAFE_PLANNER_E2E:{token}:{mode}" + (f":{foreign}" if foreign else "")
    response = await client.post(
        "/api/agent/runs",
        headers=headers,
        json={
            "agent_slug": "health-meal-planner",
            "thread_id": thread,
            "query": query,
            "meta": {"request_id": request_id},
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["run_id"]


async def collect_safe_revocable_sse(client, headers, run_id):
    """真实撤销流以明确error或end结束，网络EOF本身不能作为终态证据。"""
    response = await client.get(f"/api/agent/runs/{run_id}/events?verbose=false", headers=headers)
    assert response.status_code == 200, response.text
    events = []
    for block in response.text.split("\n\n"):
        lines = block.splitlines()
        event = next((line[6:].strip() for line in lines if line.startswith("event:")), "message")
        data = [line[5:].strip() for line in lines if line.startswith("data:")]
        if data:
            events.append((event, json.loads("\n".join(data))))
    assert events and events[-1][0] in {"error", "end"}, response.text
    return events


async def record_safe_worker_evidence(run_id, case):
    """输出当前真实PG终态与持久化数量，日志不包含请求头或健康正文。"""
    async with pg_manager.get_async_session_context() as session:
        run = await session.get(AgentRun, run_id)
        evidence = {
            "case": case,
            "run_id": run.id,
            "status": run.status,
            "output_message_id": run.output_message_id,
            "owner_released": run.worker_id is None,
            "lease_released": run.lease_expires_at is None,
            "tool_audits": await session.scalar(
                select(func.count())
                .select_from(Message)
                .where(Message.run_id == run_id, Message.message_type == "tool_audit")
            ),
            "previews": await session.scalar(
                select(func.count())
                .select_from(HealthSafePlannerPreview)
                .where(HealthSafePlannerPreview.run_id == run_id)
            ),
        }
    print("safe_planner_worker_evidence=" + json.dumps(evidence, ensure_ascii=False, sort_keys=True))


async def test_safe_worker_two_turn_checkpoint_three_tools_and_current_receipt_selectors(safe_runtime):  # noqa: F811
    """真实两轮可恢复旧checkpoint，最终不能选其它Run或虚构回执。"""
    client, users, current, _ = safe_runtime
    headers = users[0]["headers"]
    before = await safe_business_facts(current)
    bound, _ = await bind_safe(client, users, current)
    assert bound.status_code == 201, bound.text
    thread, requests, receipts = bound.json()["thread_id"], [], []
    try:
        for mode, expected in (
            ("swap", "completed"),
            ("swap_second", "completed"),
            ("regeneration", "completed"),
            ("questions", "completed"),
            ("invalid", "failed"),
            ("forged", "failed"),
            ("foreign", "failed"),
        ):
            key = str(uuid4())
            requests.append(key)
            run_id = await submit_safe_run(
                client, headers, thread, uuid4().hex, mode, key, foreign=receipts[0] if mode == "foreign" else None
            )
            events = await collect_sse(client, headers, run_id)
            assert events[-1][0] == "end" and not any("message_delta" in str(event) for _, event in events)
            result = await client.get(f"/api/agent/runs/{run_id}/result", headers=headers)
            assert result.status_code == 200 and result.json()["status"] == expected, result.text
            await record_safe_worker_evidence(run_id, mode)
            async with pg_manager.get_async_session_context() as session:
                run = await session.get(AgentRun, run_id)
                assert run.request_id == key and run.agent_slug == "health-meal-planner"
                assert run.worker_id is None and run.lease_expires_at is None
                assert run.manifest["resources"]["tools"] == [
                    "get_safe_plan_context",
                    "preview_safe_plan_swap",
                    "preview_safe_plan_regeneration",
                ]
                assert [skill["slug"] for skill in run.manifest["resources"]["skills"]] == ["family-meal-planner"]
                assert len(run.input_payload["health_processing"]["safe_selection_hash"]) == 64
                assert "family_selection_hash" not in run.input_payload["health_processing"]
                attempts = (
                    await session.scalars(select(AgentRunAttempt).where(AgentRunAttempt.run_id == run_id))
                ).all()
                assert len(attempts) == 1 and attempts[0].outcome == expected and attempts[0].finished_at
                if expected == "failed":
                    assert not result.json().get("output") and run.output_message_id is None
                    code = "planner_output_invalid" if mode == "invalid" else "planner_receipt_invalid"
                    assert code in run.error_message, f"{mode}: {run.error_message}"
                    continue
                message = await session.get(Message, run.output_message_id)
                final = json.loads(message.content)
                assert message.run_id == run_id and final == json.loads(result.json()["output"])
                assert final["scope"] == "single_member_saved_plan" and final["member_id"] == current["member"]
                if mode == "questions":
                    assert final["status"] == "needs_input" and final["questions"] == ["合成：要调整哪一餐？"]
                    assert (
                        await session.scalar(
                            select(func.count())
                            .select_from(HealthSafePlannerPreview)
                            .where(HealthSafePlannerPreview.run_id == run_id)
                        )
                        == 0
                    )
                    continue
                receipt = await session.get(HealthSafePlannerPreview, final["preview_id"])
                assert (
                    receipt.run_id == run_id
                    and receipt.actor_uid == users[0]["uid"]
                    and receipt.conversation_id == run.conversation_id
                )
                assert receipt.operation == final["operation"] and receipt.snapshot == final["result"]
                if mode in {"swap", "swap_second"}:
                    candidate = final["result"]["candidates"][0]
                    assert candidate["recipe_version_id"] == current["eligible"][0]
                    assert candidate["plan_snapshot"]["nutrition"]["totals"]["energy_kcal"] == "310.00"
                else:
                    assert final["result"]["plan_snapshot"]["nutrition"]["totals"]["energy_kcal"] == "305.00"
                receipts.append(receipt.id)
        assert len(receipts) == 3 and len(set(receipts)) == 3
        checkpoint = await pg_manager.get_langgraph_checkpointer().aget_tuple({"configurable": {"thread_id": thread}})
        assert checkpoint is not None
        messages = checkpoint.checkpoint["channel_values"]["messages"]
        assert len([message for message in messages if getattr(message, "type", None) == "human"]) >= 2
        assert await safe_business_facts(current) == before
    finally:
        await drain_requests(client, headers, requests)


@pytest.mark.parametrize("changed", ["profile", "consent", "grant", "candidate_recipe"])
async def test_safe_worker_late_publication_and_previous_result_blocked_after_source_or_permission_change(
    safe_runtime,  # noqa: F811
    changed,
):
    """工具已读后暂停响应，来源/撤权变化必须在真实worker发布前拒绝。"""
    client, users, current, consent = safe_runtime
    headers, requests = users[0]["headers"], []
    bound, _ = await bind_safe(client, users, current)
    assert bound.status_code == 201, bound.text
    thread = bound.json()["thread_id"]
    before = await safe_business_facts(current)
    token, stream = uuid4().hex, None
    async with httpx.AsyncClient(base_url="http://localhost:8766", timeout=10) as replay:
        try:
            first = str(uuid4())
            requests.append(first)
            completed = await submit_safe_run(client, headers, thread, uuid4().hex, "swap", first)
            await collect_sse(client, headers, completed)
            first_result = await client.get(f"/api/agent/runs/{completed}/result", headers=headers)
            assert first_result.status_code == 200 and first_result.json()["status"] == "completed", first_result.text
            audits = await client.get(f"/api/chat/thread/{thread}/audits", headers=headers)
            assert audits.status_code == 200 and any(row["run_id"] == completed for row in audits.json()["audits"]), (
                audits.text
            )
            key = str(uuid4())
            requests.append(key)
            gated = await submit_safe_run(client, headers, thread, token, "safe_gate", key)
            stream = asyncio.create_task(collect_safe_revocable_sse(client, headers, gated))

            async def observations():
                """等待真实模型取得服务器预览回执，失败时立即报告Owner状态。"""
                async with pg_manager.get_async_session_context() as session:
                    run = await session.get(AgentRun, gated)
                    if run.status in {"failed", "cancelled"}:
                        pytest.fail(f"安全预览在gate前终止：{run.error_type}: {run.error_message}")
                return (await replay.get("/observations", params={"token": token})).json()

            await wait_until(
                observations,
                lambda state: any(call["step"] == "safe_gate" and call["phase"] == "answer" for call in state["calls"]),
            )
            async with pg_manager.get_async_session_context() as session:
                assert (
                    await session.scalar(
                        select(func.count())
                        .select_from(HealthSafePlannerPreview)
                        .where(HealthSafePlannerPreview.run_id == gated)
                    )
                    == 1
                )
            if changed == "profile":
                profile = deepcopy(current["profile"])
                profile.update(version=2, source_version="v2")
                changed_response = await client.post(
                    f"{ROOT}/members/{current['member']}/external-profile-versions",
                    headers=users[2]["headers"],
                    json=profile,
                )
                assert changed_response.status_code == 201, changed_response.text
                submit = 410
            elif changed == "consent":
                changed_response = await client.post(
                    f"{ROOT}/members/{current['member']}/processing-consents",
                    headers=headers,
                    json={**consent, "accepted": False},
                )
                assert changed_response.status_code == 200, changed_response.text
                submit = 403
            elif changed == "grant":
                changed_response = await client.put(
                    f"{ROOT}/members/{current['member']}/grants",
                    headers=headers,
                    json={"actor_uid": users[0]["uid"], "scopes": ["profile_view", "profile_edit", "diet_edit"]},
                )
                assert changed_response.status_code == 200, changed_response.text
                submit = 404
            else:
                async with pg_manager.get_async_session_context() as session:
                    recipe = await session.get(RecipeVersion, current["eligible"][0])
                    assert recipe.id != current["old"]
                    recipe.nutrients = {**recipe.nutrients, "energy_kcal": "180"}
                assert await safe_business_facts(current) == before
                submit = 410
            assert (await replay.get("/release", params={"token": token})).status_code == 200
            events = await stream
            assert not any("message_delta" in str(payload) for _, payload in events)
            if events[-1][0] == "error":
                assert events[-1][1] in (
                    {"run_id": gated, "message": "运行任务不存在"},
                    {"run_id": gated, "message": "运行任务不存在或无权访问"},
                )

            async def terminal_status():
                """SSE权限撤销可以先结束，Worker仍须实际收敛至失败终态。"""
                async with pg_manager.get_async_session_context() as session:
                    return (await session.get(AgentRun, gated)).status

            await wait_until(terminal_status, lambda status: status in {"completed", "failed", "cancelled"})
            async with pg_manager.get_async_session_context() as session:
                run = await session.get(AgentRun, gated)
                assert run.status == "failed" and run.output_message_id is None
                assert run.worker_id is None and run.lease_expires_at is None
                reason = {"consent": "consent_required", "grant": "not_found"}.get(changed, "source_invalidated")
                assert reason in run.error_message, f"{changed}: {run.error_type}: {run.error_message}"
                assert not (
                    await session.scalars(
                        select(Message).where(
                            Message.run_id == gated, Message.role == "assistant", Message.message_type == "text"
                        )
                    )
                ).all()
            await record_safe_worker_evidence(gated, f"late_{changed}")
            await assert_safe_private_denied(client, users, thread, completed, expected_submit=submit)
            assert await safe_business_facts(current) == before
        finally:
            await replay.get("/release", params={"token": token})
            if stream is not None and not stream.done():
                await asyncio.gather(stream, return_exceptions=True)
            await drain_requests(client, headers, requests)


@pytest.mark.parametrize(
    "tampered", ["message_approval", "message_nutrition", "message_preview", "tool_audit", "binding_deleted"]
)
async def test_completed_safe_run_rejects_changed_persisted_projection_or_binding(safe_runtime, tampered):  # noqa: F811
    """本轮Message/审计/绑定被篡改时，私有四入口仍须核对原Run安全事实。"""
    client, users, current, _ = safe_runtime
    headers, requests = users[0]["headers"], []
    before = await safe_business_facts(current)
    bound, _ = await bind_safe(client, users, current)
    assert bound.status_code == 201, bound.text
    thread = bound.json()["thread_id"]
    try:
        key = str(uuid4())
        requests.append(key)
        run_id = await submit_safe_run(client, headers, thread, uuid4().hex, "swap", key)
        await collect_sse(client, headers, run_id)
        visible = await client.get(f"/api/agent/runs/{run_id}/result", headers=headers)
        assert visible.status_code == 200 and visible.json()["status"] == "completed", visible.text
        final = json.loads(visible.json()["output"])
        assert final["result"]["candidates"][0]["plan_snapshot"]["nutrition"]["totals"]["energy_kcal"] == "310.00"
        audit_response = await client.get(f"/api/chat/thread/{thread}/audits", headers=headers)
        assert audit_response.status_code == 200 and any(
            row["run_id"] == run_id for row in audit_response.json()["audits"]
        ), audit_response.text
        async with pg_manager.get_async_session_context() as session:
            run = await session.get(AgentRun, run_id)
            assert run.status == "completed" and run.worker_id is None
            if tampered == "binding_deleted":
                binding = await session.get(HealthConsultation, run.conversation_id)
                assert (
                    binding.safe_planner_selection is not None
                    and run.input_payload["health_processing"]["safe_selection_hash"]
                )
                binding.safe_planner_selection = None
            elif tampered == "tool_audit":
                audits = (
                    await session.scalars(
                        select(Message).where(
                            Message.run_id == run_id,
                            Message.message_type == "tool_audit",
                            Message.execution_status == "completed",
                        )
                    )
                ).all()
                audit = next(row for row in audits if row.extra_metadata["tool_name"] == "preview_safe_plan_swap")
                payload = json.loads(audit.content)
                assert payload["preview_id"] == final["preview_id"]
                payload["result"] = {"status": "ready", "nutrition": {"energy_kcal": "999.00"}}
                audit.content = json.dumps(payload)
            else:
                message = await session.get(Message, run.output_message_id)
                payload = json.loads(message.content)
                if tampered == "message_approval":
                    payload["professional_review"] = "approved"
                elif tampered == "message_nutrition":
                    payload["result"]["candidates"][0]["plan_snapshot"]["nutrition"]["totals"]["energy_kcal"] = "999.00"
                else:
                    payload["preview_id"] = str(uuid4())
                message.content = json.dumps(payload)
            receipt = await session.get(HealthSafePlannerPreview, final["preview_id"])
            assert receipt.snapshot["candidates"][0]["plan_snapshot"]["nutrition"]["totals"]["energy_kcal"] == "310.00"
        assert await safe_business_facts(current) == before
        await assert_safe_private_denied(
            client, users, thread, run_id, expected_submit=409 if tampered == "message_preview" else 410
        )
        await record_safe_worker_evidence(run_id, f"tamper_{tampered}")
    finally:
        await drain_requests(client, headers, requests)

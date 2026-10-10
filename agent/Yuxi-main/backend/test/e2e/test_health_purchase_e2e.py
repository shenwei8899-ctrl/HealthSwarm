"""实际HTTP→Request→ARQ worker→固定图→工具→PG→Message采购闭环。"""

import json
import os
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import func, select

from test.e2e.test_health_consultation_e2e import collect_sse, drain_requests, isolated_health, wait_until  # noqa: F401
from test.integration.services.test_health_purchase_http import (
    adopted_purchase,
    bind_purchase,
    consent_purchase,
    purchase_runtime,  # noqa: F401
)
from test.integration.services.test_health_vision_http import health_http, ROOT  # noqa: F401
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_business import AgentRun, AgentRunAttempt, AgentRunRequest, Message
from yuxi.storage.postgres.models_health import HealthPurchasePreview

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.slow,
    pytest.mark.asyncio,
    pytest.mark.skipif(os.getenv("HEALTH_CONSULTATION_E2E_ISOLATED") != "true", reason="仅独立本地采购replay槽位"),
]


async def test_purchase_worker_current_receipt_checkpoint_and_negative_final_outputs(purchase_runtime):  # noqa: F811
    client, users, consent = purchase_runtime
    current = await adopted_purchase(client, users)
    await consent_purchase(client, users, current, consent)
    response, _ = await bind_purchase(client, users, current)
    assert response.status_code == 201, response.text
    thread, requests, previous = response.json()["thread_id"], [], None
    try:
        for mode, expected in (
            ("normal", "completed"),
            ("repeat", "completed"),
            ("questions", "completed"),
            ("invalid", "failed"),
            ("forged", "failed"),
            ("foreign", "failed"),
        ):
            key, token = str(uuid4()), uuid4().hex
            query = f"PURCHASE_E2E:{token}:{mode}" + (f":{previous}" if mode == "foreign" else "")
            submitted = await client.post(
                "/api/agent/runs",
                headers=users[0]["headers"],
                json={
                    "agent_slug": "health-purchase",
                    "thread_id": thread,
                    "query": query,
                    "meta": {"request_id": key},
                },
            )
            assert submitted.status_code == 200, submitted.text
            requests.append(key)
            run_id = submitted.json()["run_id"]
            events = await collect_sse(client, users[0]["headers"], run_id)
            assert events[-1][0] == "end" and not any("message_delta" in str(event) for _, event in events)
            result = await client.get(f"/api/agent/runs/{run_id}/result", headers=users[0]["headers"])
            assert result.status_code == 200 and result.json()["status"] == expected, result.text
            async with pg_manager.get_async_session_context() as session:
                run = await session.get(AgentRun, run_id)
                assert run.request_id == key and run.worker_id is None and run.lease_expires_at is None
                assert run.agent_slug == "health-purchase"
                request = await session.scalar(select(AgentRunRequest).where(AgentRunRequest.request_id == key))
                assert request.status == "dispatched" and request.dispatched_run_id == run_id
                assert request.uid == users[0]["uid"] and request.conversation_thread_id == thread
                assert request.input_payload["health_processing"] == run.input_payload["health_processing"]
                assert run.manifest["resources"]["tools"] == [
                    "get_purchase_requirements",
                    "preview_purchase_requirements",
                ]
                assert [skill["slug"] for skill in run.manifest["resources"]["skills"]] == ["family-purchase"]
                assert "purchase_selection_hash" in run.input_payload["health_processing"]
                assert "family_selection_hash" not in run.input_payload["health_processing"]
                attempts = (
                    await session.scalars(select(AgentRunAttempt).where(AgentRunAttempt.run_id == run_id))
                ).all()
                assert len(attempts) == 1 and attempts[0].outcome == expected and attempts[0].finished_at
                if expected == "failed":
                    assert run.output_message_id is None and not result.json().get("output")
                    assert (
                        "purchase_output_invalid" if mode == "invalid" else "purchase_receipt_invalid"
                    ) in run.error_message
                    print(
                        "purchase_worker_evidence="
                        + json.dumps(
                            {
                                "mode": mode,
                                "run_id": run_id,
                                "request_id": key,
                                "status": expected,
                                "message_id": None,
                                "error_type": run.error_type,
                            }
                        )
                    )
                    continue
                message = await session.get(Message, run.output_message_id)
                final = json.loads(message.content)
                assert message.run_id == run_id and final == json.loads(result.json()["output"])
                count = await session.scalar(
                    select(func.count())
                    .select_from(HealthPurchasePreview)
                    .where(HealthPurchasePreview.run_id == run_id)
                )
                if mode == "questions":
                    assert final["status"] == "needs_input" and count == 0
                else:
                    assert count == 1
                    receipt = await session.get(HealthPurchasePreview, final["preview_id"])
                    assert receipt.run_id == run_id and receipt.actor_uid == users[0]["uid"]
                    assert final["result"] == receipt.snapshot and final["result"]["status"] == "requirements_ready"
                    assert final["result"]["items"][0]["net_required_grams"] == "260.000000"
                    assert (
                        final["result"]["purchase_available"] is False and final["result"]["order_available"] is False
                    )
                    previous = receipt.id
                message_id = message.id
            print(
                "purchase_worker_evidence="
                + json.dumps(
                    {"mode": mode, "run_id": run_id, "request_id": key, "status": expected, "message_id": message_id}
                )
            )
    finally:
        await drain_requests(client, users[0]["headers"], requests)


async def test_purchase_worker_rejects_revoked_purpose_before_new_request(purchase_runtime):  # noqa: F811
    client, users, consent = purchase_runtime
    current = await adopted_purchase(client, users)
    await consent_purchase(client, users, current, consent)
    response, _ = await bind_purchase(client, users, current)
    assert response.status_code == 201
    revoked = await client.post(
        f"{ROOT}/members/{current['member']}/processing-consents",
        headers=users[0]["headers"],
        json={**consent, "accepted": False},
    )
    assert revoked.status_code == 200
    denied = await client.post(
        "/api/agent/runs",
        headers=users[0]["headers"],
        json={
            "agent_slug": "health-purchase",
            "thread_id": response.json()["thread_id"],
            "query": f"PURCHASE_E2E:{uuid4().hex}:normal",
            "meta": {"request_id": str(uuid4())},
        },
    )
    assert denied.status_code == 403, denied.text


@pytest.mark.parametrize("change", ["consent", "adoption", "professional_source", "member_grant"])
async def test_purchase_worker_revalidates_after_model_response_before_message(purchase_runtime, change):  # noqa: F811
    """本Run已存工具回执后撤销来源，迟到模型答复仍不得成为Message。"""
    client, users, consent = purchase_runtime
    current = await adopted_purchase(client, users, family=change == "member_grant")
    await consent_purchase(client, users, current, consent, family=change == "member_grant")
    response, _ = await bind_purchase(client, users, current)
    assert response.status_code == 201, response.text
    key, token = str(uuid4()), uuid4().hex
    submitted = await client.post(
        "/api/agent/runs",
        headers=users[0]["headers"],
        json={
            "agent_slug": "health-purchase",
            "thread_id": response.json()["thread_id"],
            "query": f"PURCHASE_E2E:{token}:gate",
            "meta": {"request_id": key},
        },
    )
    assert submitted.status_code == 200, submitted.text
    run_id = submitted.json()["run_id"]
    async with httpx.AsyncClient(base_url="http://localhost:8776", timeout=10) as replay:
        try:

            async def observed():
                return (await replay.get("/calls")).json()

            await wait_until(observed, lambda result: token in result["gated"])
            async with pg_manager.get_async_session_context() as session:
                assert (
                    await session.scalar(
                        select(func.count())
                        .select_from(HealthPurchasePreview)
                        .where(HealthPurchasePreview.run_id == run_id)
                    )
                    == 1
                )
            if change == "consent":
                changed = await client.post(
                    f"{ROOT}/members/{current['member']}/processing-consents",
                    headers=users[0]["headers"],
                    json={**consent, "accepted": False},
                )
                assert changed.status_code == 200, changed.text
            elif change == "adoption":
                changed = await client.post(
                    f"{ROOT}/meal-plan-adoptions/{current['adoption']['adoption_id']}/withdraw",
                    headers=users[0]["headers"],
                    json={"client_request_id": str(uuid4()), "version": 1, "reason": "合成迟到采购来源撤销"},
                )
                assert changed.status_code == 200, changed.text
            elif change == "professional_source":
                changed = await client.post(
                    f"{ROOT}/approved-quality-rules",
                    headers=users[2]["headers"],
                    json={**current["rules"], "version": 2, "source_version": "v2"},
                )
                assert changed.status_code == 201, changed.text
            else:
                changed = await client.put(
                    f"{ROOT}/members/{current['second']}/grants",
                    headers=users[0]["headers"],
                    json={"actor_uid": users[0]["uid"], "scopes": []},
                )
                assert changed.status_code == 200, changed.text
            released = await replay.post(f"/release/{token}", json={})
            assert released.status_code == 200

            async def terminal():
                async with pg_manager.get_async_session_context() as session:
                    row = await session.get(AgentRun, run_id)
                    return row.status

            await wait_until(terminal, lambda status: status in {"failed", "cancelled", "completed"})
            async with pg_manager.get_async_session_context() as session:
                run = await session.get(AgentRun, run_id)
                assert run.status == "failed" and run.output_message_id is None, run.error_message
                code = {"consent": "consent_required", "member_grant": "not_found"}.get(change, "source_invalidated")
                assert code in run.error_message
                assert not await session.scalar(
                    select(func.count())
                    .select_from(Message)
                    .where(Message.run_id == run_id, Message.role == "assistant", Message.message_type == "text")
                )
            print(
                "purchase_late_source_evidence=" + json.dumps({"change": change, "run_id": run_id, "status": "failed"})
            )
        finally:
            await replay.post(f"/release/{token}", json={})
            await drain_requests(client, users[0]["headers"], [key])

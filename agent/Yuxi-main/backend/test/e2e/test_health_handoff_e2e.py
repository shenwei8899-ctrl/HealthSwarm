"""显式交接经过真实HTTP/Worker/PG，确认本身绝不自动创建Run。"""

import asyncio
import os
from uuid import uuid4

import pytest
from sqlalchemy import delete, select

from test.e2e.test_health_consultation_e2e import isolated_health, drain_requests  # noqa: F401
from test.e2e.test_health_indicator_agents_e2e import indicator_runtime, indicator_entry, CASES  # noqa: F401
from test.e2e.test_health_task_e2e import run_task
from test.integration.services.test_health_vision_http import ROOT, health_http  # noqa: F401
from test.integration.services.test_health_task_http import owned_counts, verified_task_cleanup  # noqa: F401
from test.integration.services.test_health_weight_http import create_weight_subject, cleanup_weight_subject
from test.integration.services.test_health_vision_http import create_member
from test.integration.services.test_health_diet_analysis_http import confirm_analysis_meal
from test.integration.services.test_health_meal_planner_http import publish_planner_recipe
from test.integration.services.test_health_task_http import entry
from test.support.health_indicator_replay_server import MODEL
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_health import HealthConsultation, VisionDraft

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.e2e,
    pytest.mark.slow,
    pytest.mark.skipif(os.getenv("HEALTH_CONSULTATION_E2E_ISOLATED") != "true", reason="仅独立合成槽位"),
]


@pytest.mark.parametrize("kind,add_record,correct_record,use_model", CASES)
async def test_explicit_handoff_worker_replay_and_source_invalidation(
    indicator_runtime,  # noqa: F811
    kind,
    add_record,
    correct_record,
    use_model,
):
    """预览无写入、并发确认一次、独立目标Run、源更正关闭目标历史和继续运行。"""
    runtime = indicator_runtime
    client = runtime.client
    subject = await create_weight_subject(client, runtime.users)
    owner = subject.headers
    try:
        consent = await client.post(
            f"{ROOT}/members/{subject.member_id}/processing-consents",
            headers=owner,
            json={
                "purpose": "consultation",
                "accepted": True,
                "processor": runtime.configuration["consultation"]["processor"],
                "policy_version": runtime.configuration["policy_version"],
            },
        )
        assert consent.status_code == 200, consent.text
        record = await add_record(subject)
        bound = await indicator_entry(subject, f"{kind}_review", f"health-{kind.replace('_', '-')}")
        token = uuid4().hex
        request, source_run, task = await run_task(
            client, owner, bound, f"INDICATOR_E2E:{token}:{kind}:read", runtime.requests
        )
        assert task["execution_status"] == "completed", task
        before = await owned_counts(subject.uid)
        url = f"{ROOT}/tasks/{request}"
        preview = await client.get(url + "/handoff-preview", headers=owner)
        assert preview.status_code == 200, preview.text
        assert preview.headers["Cache-Control"] == "no-store"
        data = preview.json()
        assert data["target_agent"] == "health-consultation"
        assert data["summary"]["records"][0]["record_id"] == record["id"]
        assert "answer" not in data["summary"] and "profile" not in data["summary"]
        assert await owned_counts(subject.uid) == before
        assert (await client.get(url + "/handoff-preview", headers=runtime.users[2]["headers"])).status_code == 404
        body = {"client_request_id": str(uuid4()), "source_hash": data["source_hash"], "confirmed": True}
        confirmed_headers = {**owner, "Idempotency-Key": body["client_request_id"]}
        assert (
            await client.post(url + "/handoffs", headers=owner, json={**body, "confirmed": False})
        ).status_code == 422
        assert (
            await client.post(url + "/handoffs", headers=confirmed_headers, json={**body, "source_hash": "a" * 64})
        ).status_code == 410
        assert await owned_counts(subject.uid) == before
        responses = await asyncio.gather(
            *[
                client.post(
                    url + "/handoffs", headers={**owner, "Idempotency-Key": body["client_request_id"]}, json=body
                )
                for _ in range(2)
            ]
        )
        assert all(r.status_code == 201 for r in responses), [r.text for r in responses]
        target = responses[0].json()
        assert responses[1].json() == target and target["thread_id"] != bound["thread_id"]
        after = await owned_counts(subject.uid)
        assert after[3:] == before[3:] and after[1] == before[1] + 1, after
        async with pg_manager.get_async_session_context() as session:
            bindings = list(
                await session.scalars(select(HealthConsultation).where(HealthConsultation.actor_uid == subject.uid))
            )
            assert len([b for b in bindings if b.handoff_selection]) == 1
        target_request, target_run, result = await run_task(
            client, owner, target, f"HANDOFF_E2E:{token}", runtime.requests
        )
        assert result["execution_status"] == "completed", result
        assert "合成指标记录" in result["result"]["answer"]
        assert (await client.get(f"{ROOT}/tasks/{target_request}/handoff-preview", headers=owner)).status_code == 409
        assert (await client.get(f"/api/chat/thread/{target['thread_id']}/history", headers=owner)).status_code == 200
        await correct_record(subject, record["id"])
        assert (await client.get(url + "/handoff-preview", headers=owner)).status_code == 410
        assert (await client.post(url + "/handoffs", headers=confirmed_headers, json=body)).status_code == 410
        assert (await client.get(f"/api/chat/thread/{target['thread_id']}/history", headers=owner)).status_code == 404
        rejected = await client.post(
            "/api/agent/runs",
            headers=owner,
            json={
                "agent_slug": target["agent_slug"],
                "thread_id": target["thread_id"],
                "query": f"HANDOFF_E2E:{token}",
                "meta": {"request_id": str(uuid4())},
            },
        )
        assert rejected.status_code == 410, rejected.text
    finally:
        await drain_requests(client, owner, runtime.requests)
        async with pg_manager.get_async_session_context() as session:
            await session.execute(delete(use_model).where(use_model.member_id == subject.member_id))
        await cleanup_weight_subject(subject)


async def test_period_analysis_to_planner_has_independent_policy_consent_and_no_duplicate_runs(indicator_runtime):  # noqa: F811
    """真实期间分析→独立配餐预览；目标未配、缺同意及源撤回均不越界。"""
    runtime = indicator_runtime
    client, users = runtime.client, runtime.users
    owner, admin = users[0]["headers"], users[2]["headers"]
    member = await create_member(client, owner)
    record, draft_id = await confirm_analysis_meal(client, owner, admin, member)
    model = runtime.configuration["consultation"]["model"]
    assert model.endswith(MODEL)
    settings = {
        "consultation_model": model,
        "diet_analysis_model": model,
        "policy_version": runtime.configuration["policy_version"],
        "cloud_processing_reviewed": True,
    }
    configured = await client.put(f"{ROOT}/configuration", headers=admin, json=settings)
    assert configured.status_code == 200, configured.text
    policy = configured.json()["policy_version"]
    consent = await client.post(
        f"{ROOT}/members/{member}/processing-consents",
        headers=owner,
        json={
            "purpose": "diet_analysis",
            "accepted": True,
            "processor": configured.json()["diet_analysis"]["processor"],
            "policy_version": policy,
        },
    )
    assert consent.status_code == 200, consent.text
    bound = await entry(client, owner, member, "diet_analysis")
    token = uuid4().hex
    try:
        source, _, task = await run_task(
            client, owner, bound.json(), f"HEALTH_DIET_ANALYSIS_E2E:{token}:period", runtime.requests
        )
        assert task["execution_status"] == "completed", task
        url = f"{ROOT}/tasks/{source}"
        preview = await client.get(url + "/handoff-preview", headers=owner)
        assert preview.status_code == 200, preview.text
        summary = preview.json()["summary"]
        assert summary["window"]["start_date"] == "2026-10-01"
        assert summary["nutrition"]["totals"]["energy_kcal"]["recorded_total"] == "120.00"
        assert summary["nutrition"]["totals"]["sodium_mg"]["recorded_total"] is None
        assert summary["coverage"]["days_with_records"] == 1
        assert summary["records"] == [{"record_id": record["id"], "source_version": 1}]
        body = {"client_request_id": str(uuid4()), "source_hash": preview.json()["source_hash"], "confirmed": True}
        headers = {**owner, "Idempotency-Key": body["client_request_id"]}
        before = await owned_counts(users[0]["uid"])
        blocked = await client.post(url + "/handoffs", headers=headers, json=body)
        assert blocked.status_code == 503, blocked.text
        assert await owned_counts(users[0]["uid"]) == before
        configured = await client.put(
            f"{ROOT}/configuration", headers=admin, json={**settings, "meal_plan_model": model}
        )
        assert configured.status_code == 200
        denied = await client.post(url + "/handoffs", headers=headers, json=body)
        assert denied.status_code == 403, denied.text
        assert await owned_counts(users[0]["uid"]) == before
        agreed = await client.post(
            f"{ROOT}/members/{member}/processing-consents",
            headers=owner,
            json={
                "purpose": "meal_plan",
                "accepted": True,
                "processor": configured.json()["meal_plan"]["processor"],
                "policy_version": policy,
            },
        )
        assert agreed.status_code == 200
        accepted = await client.post(url + "/handoffs", headers=headers, json=body)
        assert accepted.status_code == 201, accepted.text
        target = accepted.json()
        assert (await owned_counts(users[0]["uid"]))[3:] == before[3:]
        # 普通入口不能用同一个键剥离交接来源。
        removed = await client.post(
            f"{ROOT}/members/{member}/meal-planner",
            headers=owner,
            json={"client_request_id": body["client_request_id"]},
        )
        assert removed.status_code == 409, removed.text
        await publish_planner_recipe(client, admin, f"合成配餐E2E-{token}")
        target_request, _, result = await run_task(
            client, owner, target, f"HEALTH_MEAL_PLANNER_E2E:{token}:valid", runtime.requests
        )
        assert result["execution_status"] == "completed", result
        assert result["result"]["data"]["nutrition"]["totals"]["energy_kcal"] == "300.00"
        async with pg_manager.get_async_session_context() as session:
            (await session.get(VisionDraft, draft_id)).review_status = "retracted"
        assert (await client.get(f"{ROOT}/tasks/{target_request}", headers=owner)).status_code == 410
        assert (await client.get(f"/api/chat/thread/{target['thread_id']}/history", headers=owner)).status_code == 404
    finally:
        await drain_requests(client, owner, runtime.requests)
        restored = await client.put(
            f"{ROOT}/configuration",
            headers=admin,
            json={"consultation_model": model, "policy_version": policy, "cloud_processing_reviewed": True},
        )
        assert restored.status_code == 200, restored.text

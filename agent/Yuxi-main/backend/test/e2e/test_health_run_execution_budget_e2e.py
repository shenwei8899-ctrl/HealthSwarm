"""独立短预算槽位的真实HTTP、ARQ、PG终态与当前授权验收。"""

import asyncio
import json
import os
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from arq.constants import default_queue_name, in_progress_key_prefix
from arq.jobs import Job
from yuxi.services.arq_worker import YuxiWorker
from sqlalchemy import select, text

from test.e2e.test_health_consultation_e2e import (
    collect_sse,
    drain_requests,
    isolated_health,  # noqa: F401
    wait_until,
)
from test.integration.services.test_health_task_http import entry, verified_task_cleanup  # noqa: F401
from test.integration.services.test_health_vision_http import ROOT, create_member, health_http  # noqa: F401
from test.support.health_run_budget_replay_server import MODEL
from yuxi.repositories.agent_run_repository import AgentRunRepository
from yuxi.services import run_worker
from yuxi.services.run_queue_service import close_queue_clients, get_arq_pool
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_business import AgentRun, AgentRunAttempt, AgentRunRequest, Message
from yuxi.utils.datetime_utils import utc_now_naive

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.slow,
    pytest.mark.asyncio,
    pytest.mark.skipif(os.getenv("HEALTH_RUN_BUDGET_E2E") != "true", reason="仅明确启用的合成3秒预算槽位"),
]


@pytest_asyncio.fixture
async def budget_runtime(isolated_health):  # noqa: F811
    """审批只在原有独立合成槽位，provider和政策在退出时恢复。"""
    assert os.getenv("HEALTH_CONSULTATION_E2E_ISOLATED") == "true"
    assert run_worker.WorkerSettings.health_execution_timeout == 3, "只能在部署预算3秒的独立测试进程运行"
    client, users, configuration, original_spec = isolated_health
    provider = f"health-budget-replay-{uuid4().hex[:12]}"
    response = await client.post(
        "/api/system/model-providers",
        headers=users[2]["headers"],
        json={
            "provider_id": provider,
            "display_name": "Synthetic health execution budget only",
            "provider_type": "openai",
            "base_url": "http://api:8778/v1",
            "api_key": "synthetic-health-budget-key",
            "capabilities": ["chat"],
            "enabled_models": [{"id": MODEL, "display_name": MODEL, "type": "chat", "source": "manual"}],
            "is_enabled": True,
        },
    )
    assert response.status_code == 200, response.text
    try:
        configured = await client.put(
            f"{ROOT}/configuration",
            headers=users[2]["headers"],
            json={
                "consultation_model": f"{provider}:{MODEL}",
                "policy_version": configuration["policy_version"],
                "cloud_processing_reviewed": True,
            },
        )
        assert configured.status_code == 200, configured.text
        async with httpx.AsyncClient(base_url="http://localhost:8778", timeout=5) as replay:
            yield client, users, configured.json(), replay
    finally:
        restored = await client.put(
            f"{ROOT}/configuration",
            headers=users[2]["headers"],
            json={
                "consultation_model": original_spec,
                "policy_version": configuration["policy_version"],
                "cloud_processing_reviewed": True,
            },
        )
        assert restored.status_code == 200, restored.text
        deleted = await client.delete(f"/api/system/model-providers/{provider}", headers=users[2]["headers"])
        assert deleted.status_code == 200, deleted.text
        await close_queue_clients()


async def create_budget_run(client, owner, configuration, mode, requests):
    """真实固定咨询入口和普通Request创建，不伪造持久运行。"""
    member = await create_member(client, owner["headers"])
    consent = await client.post(
        f"{ROOT}/members/{member}/processing-consents",
        headers=owner["headers"],
        json={
            "purpose": "consultation",
            "accepted": True,
            "processor": configuration["consultation"]["processor"],
            "policy_version": configuration["policy_version"],
        },
    )
    assert consent.status_code == 200, consent.text
    created = await entry(client, owner["headers"], member, "consultation")
    assert created.status_code == 200, created.text
    bound = created.json()
    token, request_id = uuid4().hex, str(uuid4())
    requests.append(request_id)
    submitted = await client.post(
        "/api/agent/runs",
        headers=owner["headers"],
        json={
            "agent_slug": bound["agent_slug"],
            "thread_id": bound["thread_id"],
            "query": f"HEALTH_BUDGET_E2E:{token}:{mode}",
            "meta": {"request_id": request_id},
        },
    )
    assert submitted.status_code == 200, submitted.text
    return member, token, request_id, submitted.json()["run_id"], bound


async def read_budget_run(run_id):
    """读取当前Worker拥有的事实，最终消息只认权威指针。"""
    async with pg_manager.get_async_session_context() as session:
        run = await session.get(AgentRun, run_id)
        attempts = list(
            await session.scalars(
                select(AgentRunAttempt).where(AgentRunAttempt.run_id == run_id).order_by(AgentRunAttempt.attempt_no)
            )
        )
        regular = list(
            await session.scalars(
                select(Message).where(
                    Message.run_id == run_id, Message.role == "assistant", Message.message_type == "text"
                )
            )
        )
        return run, attempts, regular


@pytest.mark.parametrize("mode", ["slow", "cancel", "revoke", "lease"])
async def test_external_worker_budget_cancel_consent_and_lease_keep_distinct_final_facts(budget_runtime, mode):
    """真实外部Worker慢模型失败、取消、撤同意和lease终态保持各自事实。"""
    client, users, configuration, replay = budget_runtime
    owner, requests = users[0], []
    redis = await get_arq_pool()
    run_id, token, duplicate_job = None, None, None
    try:
        member, token, request_id, run_id, bound = await create_budget_run(client, owner, configuration, mode, requests)

        async def model_calls():
            response = await replay.get("/state", params={"token": token})
            assert response.status_code == 200
            return response.json()["requests"]

        await wait_until(model_calls, lambda count: count == 1, timeout=10)
        first, attempts, regular = await read_budget_run(run_id)
        assert first.started_at is not None and first.worker_id and first.status == "running"
        assert len(attempts) == 1 and not regular
        if mode == "cancel":
            cancelled = await client.post(f"/api/agent/runs/{run_id}/cancel", headers=owner["headers"])
            assert cancelled.status_code == 200, cancelled.text
        elif mode == "revoke":
            revoked = await client.post(
                f"{ROOT}/members/{member}/processing-consents",
                headers=owner["headers"],
                json={
                    "purpose": "consultation",
                    "accepted": False,
                    "processor": configuration["consultation"]["processor"],
                    "policy_version": configuration["policy_version"],
                },
            )
            assert revoked.status_code == 200, revoked.text
            assert (await replay.post(f"/release/{token}")).status_code == 200
        elif mode == "lease":
            async with pg_manager.get_async_session_context() as session:
                assert await AgentRunRepository(session).renew_lease(
                    run_id, worker_id=first.worker_id, lease_seconds=0.025
                )
            await asyncio.sleep(0.05)
            assert run_id in await run_worker.reconcile_expired_run_leases(now=utc_now_naive())
            assert (await replay.post(f"/release/{token}")).status_code == 200
        events = await collect_sse(client, owner["headers"], run_id)
        assert events[-1][0] == "end" and events[-1][1]["run_id"] == run_id
        if mode != "lease":
            assert events[-1][1]["request_id"] == request_id

        async def worker_closed():
            return await redis.get(in_progress_key_prefix + f"run:{run_id}")

        await wait_until(worker_closed, lambda value: value is None)
        final, attempts, regular = await read_budget_run(run_id)
        expected_status = "cancelled" if mode == "cancel" else "failed"
        assert final.status == expected_status and final.started_at == first.started_at
        assert final.worker_id is None and final.lease_expires_at is None and not final.runtime_cleanup_pending
        assert final.output_message_id is None and not regular
        assert attempts and all(attempt.finished_at is not None for attempt in attempts)
        assert events[-1][1]["payload"]["status"] == final.status
        if mode == "slow":
            assert final.error_type == "health_execution_timeout"
            assert final.token_usage == {"available": False}
            assert (final.finished_at - final.started_at).total_seconds() < 10
            # 刻意独立队列作业ID，证明再次投递同一个终态Run不会重新产生attempt或外呼。
            duplicate_job = await redis.enqueue_job(
                "process_agent_run", run_id, _job_id=f"health-budget-redelivery-{uuid4().hex}"
            )
            assert duplicate_job is not None
            await duplicate_job.result(timeout=15, poll_delay=0.05)
            again, again_attempts, again_regular = await read_budget_run(run_id)
            assert again.status == "failed" and again.started_at == first.started_at and not again_regular
            assert [attempt.id for attempt in again_attempts] == [attempt.id for attempt in attempts]
        elif mode == "lease":
            assert final.error_type == "worker_lease_expired"
        elif mode == "revoke":
            assert final.error_type != "health_execution_timeout"
            projection = await client.get(f"{ROOT}/tasks/{request_id}", headers=owner["headers"])
            assert projection.status_code == 200, projection.text
            assert projection.json()["run_id"] == run_id and projection.json()["request_id"] == request_id
            assert projection.json()["execution_status"] == "failed" and projection.json()["final_message_id"] is None
            assert projection.json()["result"] == {
                "result_type": "error",
                "code": "execution_failed",
                "retryable": False,
            }
        assert await model_calls() == 1
        async with pg_manager.get_async_session_context() as session:
            request = await session.scalar(select(AgentRunRequest).where(AgentRunRequest.request_id == request_id))
            assert request.dispatched_run_id == run_id and request.uid == owner["uid"]
            assert await session.scalar(text("SELECT current_database()")) == "health_consultation_e2e"
        report = Path("test/.tmp/health-run-budget/runtime.jsonl")
        report.parent.mkdir(parents=True, exist_ok=True)
        with report.open("a", encoding="utf-8") as stream:
            stream.write(
                json.dumps(
                    {
                        "mode": mode,
                        "request_id": request_id,
                        "run_id": run_id,
                        "thread_id": bound["thread_id"],
                        "attempt_ids": [attempt.id for attempt in attempts],
                        "status": final.status,
                        "error_type": final.error_type,
                        "sdk_requests": 1,
                        "final_message_id": None,
                        "runtime_cleanup_pending": False,
                    }
                )
                + "\n"
            )
    finally:
        if token is not None:
            await replay.post(f"/release/{token}")
        await drain_requests(client, owner["headers"], requests)
        if run_id is not None:
            await wait_until(lambda: redis.get(in_progress_key_prefix + f"run:{run_id}"), lambda value: value is None)
        if duplicate_job is not None:
            keys = [key async for key in redis.scan_iter(match=f"*{duplicate_job.job_id}*")]
            if keys:
                await redis.delete(*keys)


@pytest.mark.skipif(os.getenv("HEALTH_BUDGET_CONTROLLED_WORKER") != "true", reason="需要宿主先暂停准确隔离Worker")
async def test_real_arq_pending_retry_keeps_first_start_and_refuses_second_external_call(budget_runtime):
    """真实HTTP、PG和YuxiWorker双attempt，跨pending恢复不能重新取得预算。"""
    client, users, configuration, replay = budget_runtime
    owner, requests = users[0], []
    redis = await get_arq_pool()
    baseline = await redis.zrange(default_queue_name, 0, -1, withscores=True)
    namespace = f"health-budget-controlled-{uuid4().hex}"
    queue_name, run_id, token, job_id, worker = f"arq:{namespace}:queue", None, None, None, None
    try:
        member, token, request_id, run_id, bound = await create_budget_run(
            client, owner, configuration, "retry", requests
        )
        del member
        job_id = f"run:{run_id}"
        score = await wait_until(lambda: redis.zscore(default_queue_name, job_id), lambda value: value is not None)
        assert await redis.zrem(default_queue_name, job_id) == 1
        assert await redis.zadd(queue_name, {job_id: score}) == 1
        assert await redis.zrange(default_queue_name, 0, -1, withscores=True) == baseline
        worker = YuxiWorker(
            functions=[run_worker.process_agent_run],
            redis_pool=redis,
            queue_name=queue_name,
            health_check_key=f"arq:{namespace}:health",
            handle_signals=False,
            max_tries=2,
            job_timeout=60,
            ctx={"redis": redis, "worker_id": namespace},
        )
        await worker.start_jobs([job_id.encode()])

        async def model_calls():
            response = await replay.get("/state", params={"token": token})
            assert response.status_code == 200
            return response.json()["requests"]

        await wait_until(model_calls, lambda count: count == 1, timeout=10)
        first, first_attempts, regular = await read_budget_run(run_id)
        assert first.status == "running" and first.started_at is not None and len(first_attempts) == 1 and not regular
        worker.tasks[job_id].cancel("controlled infrastructure interruption")
        await asyncio.wait_for(worker.tasks[job_id], timeout=10)
        pending, pending_attempts, regular = await read_budget_run(run_id)
        assert pending.status == "pending" and pending.started_at == first.started_at and not regular
        assert pending.worker_id is None and pending.lease_expires_at is None
        assert len(pending_attempts) == 1 and pending_attempts[0].outcome == "retry_released"
        assert pending_attempts[0].finished_at is not None
        # 重试等待在首attempt起点之后，必须计入绝对预算。
        remaining = 3 - (utc_now_naive() - first.started_at).total_seconds()
        await asyncio.sleep(max(0, remaining) + 0.15)
        await worker.start_jobs([job_id.encode()])
        assert await Job(job_id, redis, _queue_name=queue_name).result(timeout=15, poll_delay=0.05) is None
        final, attempts, regular = await read_budget_run(run_id)
        assert final.status == "failed" and final.error_type == "health_execution_timeout" and not regular
        assert final.started_at == first.started_at and final.output_message_id is None
        assert final.worker_id is None and final.lease_expires_at is None and not final.runtime_cleanup_pending
        assert len(attempts) == 2 and attempts[0].id == first_attempts[0].id
        assert [attempt.outcome for attempt in attempts] == ["retry_released", "failed"]
        assert attempts[1].started_at > attempts[0].started_at and attempts[1].worker_id != attempts[0].worker_id
        assert final.token_usage == {"available": False} and await model_calls() == 1
        events = await collect_sse(client, owner["headers"], run_id)
        assert events[-1][0] == "end" and events[-1][1]["payload"]["status"] == "failed"
        assert events[-1][1]["request_id"] == request_id
        report = Path("test/.tmp/health-run-budget/runtime.jsonl")
        with report.open("a", encoding="utf-8") as stream:
            stream.write(
                json.dumps(
                    {
                        "mode": "pending_retry",
                        "request_id": request_id,
                        "run_id": run_id,
                        "thread_id": bound["thread_id"],
                        "attempt_ids": [attempt.id for attempt in attempts],
                        "attempt_outcomes": [attempt.outcome for attempt in attempts],
                        "first_start_preserved": True,
                        "status": final.status,
                        "error_type": final.error_type,
                        "sdk_requests": 1,
                        "final_message_id": None,
                        "runtime_cleanup_pending": False,
                    }
                )
                + "\n"
            )
    finally:
        if worker is not None:
            tasks = list(worker.tasks.values())
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), timeout=15)
        if token is not None:
            await replay.post(f"/release/{token}")
        if run_id is not None:
            run, _, _ = await read_budget_run(run_id)
            if run.status not in {"completed", "failed", "cancelled", "interrupted"}:
                # 失败时仅收敛本测试Run，不伪造本测试通过证据。
                await run_worker.process_agent_run({"job_try": 2, "worker_id": namespace}, run_id)
        await drain_requests(client, owner["headers"], requests)
        if job_id is not None:
            await redis.zrem(default_queue_name, job_id)
            await redis.zrem(queue_name, job_id)
            keys = [key async for key in redis.scan_iter(match=f"*{job_id}*")]
            if keys:
                await redis.delete(*keys)
        keys = [key async for key in redis.scan_iter(match=f"*{namespace}*")]
        if keys:
            await redis.delete(*keys)
        assert await redis.zrange(default_queue_name, 0, -1, withscores=True) == baseline

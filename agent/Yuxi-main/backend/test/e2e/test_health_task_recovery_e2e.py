"""真实健康Request重订阅、Run游标恢复与当前结果查询。"""

import asyncio
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select

from test.e2e.test_health_consultation_e2e import drain_requests, isolated_health, wait_until  # noqa: F401
from test.integration.services.test_health_task_http import entry, verified_task_cleanup  # noqa: F401
from test.integration.services.test_health_vision_http import (  # noqa: F401
    ROOT,
    confirmation,
    create_member,
    field,
    health_http,
)
from yuxi.services.run_queue_service import get_redis_client
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_business import AgentRun, AgentRunAttempt, AgentRunRequest, Message
from yuxi.storage.redis import close_async_redis_client

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.e2e,
    pytest.mark.slow,
    pytest.mark.skipif(os.getenv("HEALTH_CONSULTATION_E2E_ISOLATED") != "true", reason="仅独立合成槽位"),
]


async def test_queued_disconnect_run_cursors_and_authoritative_task(recovery_runtime):
    """断流只重读与订阅，两个真实Worker结果不因恢复增加执行。"""
    client, users, configuration, _, replay = recovery_runtime
    owner = users[0]
    headers = owner["headers"]
    member = await create_member(client, headers)
    consent = {
        "purpose": "consultation",
        "accepted": True,
        "processor": configuration["consultation"]["processor"],
        "policy_version": configuration["policy_version"],
    }
    assert (
        await client.post(f"{ROOT}/members/{member}/processing-consents", headers=headers, json=consent)
    ).status_code == 200
    bound = await entry(client, headers, member, "consultation")
    assert bound.status_code == 200 and bound.json()["entry_status"] == "ready", bound.text
    thread = bound.json()["thread_id"]
    draft = await client.post(
        f"{ROOT}/manual-drafts",
        headers=headers,
        json={"member_id": member, "kind": "report", "report": {"fields": [field()]}},
    )
    assert draft.status_code == 201, draft.text
    data, confirmation_headers = confirmation()
    confirmed = await client.post(
        f"{ROOT}/report-extractions/{draft.json()['id']}/confirm",
        headers={**headers, **confirmation_headers},
        json=data,
    )
    assert confirmed.status_code == 200, confirmed.text
    token, requests = uuid4().hex, []
    try:
        bodies = [
            {
                "agent_slug": "health-consultation",
                "thread_id": thread,
                "query": f"HEALTH_CONSULTATION_E2E:{token}:{mode}",
                "meta": {"request_id": str(uuid4())},
            }
            for mode in ("one", "two", "neutral")
        ]
        requests.append(bodies[0]["meta"]["request_id"])
        first = await client.post("/api/agent/runs", headers=headers, json=bodies[0])
        assert first.status_code == 200 and first.json()["status"] == "dispatched", first.text
        first_run = first.json()["run_id"]

        async def observations():
            """重放门闩证明真实Worker已进入模型调用。"""
            return (await replay.get("/observations", params={"token": token})).json()

        await wait_until(
            observations, lambda value: value["calls"] == [{"step": "one", "phase": "read", "record_ids": []}]
        )
        running = await task_get(client, headers, requests[0])
        assert running["execution_status"] == "running" and running["run_id"] == first_run and running["result"] is None
        initial = await read_events(client, headers, f"/api/agent/runs/{first_run}/events", first_only=True)
        first_cursor = initial[0][2]
        assert first_cursor, "运行断线必须保存实际Redis事件ID"
        for body in bodies[1:]:
            requests.append(body["meta"]["request_id"])
            submitted = await client.post("/api/agent/runs", headers=headers, json=body)
            assert submitted.status_code == 200 and submitted.json()["status"] == "queued", submitted.text
            assert submitted.json()["run_id"] is None
        queued = await task_get(client, headers, requests[1])
        assert queued["request_status"] == "queued" and queued["execution_status"] == "not_dispatched"
        assert queued["run_id"] is None and queued["result"] is None
        for _ in range(2):
            snapshot = await read_events(client, headers, queued["request_events_url"], first_only=True)
            assert snapshot == [("queued", {"request_id": requests[1], "status": "queued", "position": 1}, None)]
        cancelled = await client.post(f"/api/agent/requests/{requests[2]}/cancel", headers=headers)
        assert cancelled.status_code == 200 and cancelled.json()["status"] == "cancelled"
        cancelled_task = await task_get(client, headers, requests[2])
        assert (
            cancelled_task["request_status"] == "cancelled" and cancelled_task["execution_status"] == "not_dispatched"
        )
        assert cancelled_task["run_id"] is None and cancelled_task["final_message_id"] is None
        assert cancelled_task["result"] == {"result_type": "error", "code": "execution_cancelled", "retryable": False}
        terminal_request = await read_events(client, headers, f"/api/agent/requests/{requests[2]}/events")
        assert terminal_request == [("cancelled", {"request_id": requests[2], "status": "cancelled"}, None)]
        assert (await replay.get("/release", params={"token": token})).status_code == 200
        first_recovered = await read_events(
            client,
            headers,
            f"/api/agent/runs/{first_run}/events",
            params={"after_seq": first_cursor},
        )
        assert_run_replay(first_recovered, first_cursor, first_run, requests[0], thread)

        async def second_task():
            """只从当前Request投影取得派发后的Run。"""
            return await task_get(client, headers, requests[1])

        dispatched = await wait_until(second_task, lambda value: value["run_id"] is not None)
        second_run = dispatched["run_id"]
        handoff = await read_events(client, headers, f"/api/agent/requests/{requests[1]}/events")
        assert handoff == [
            (
                "run_created",
                {"request_id": requests[1], "run_id": second_run, "stream_url": f"/api/agent/runs/{second_run}/events"},
                None,
            )
        ]
        second_initial = await read_events(client, headers, handoff[0][1]["stream_url"], first_only=True)
        second_cursor = second_initial[0][2]
        assert second_cursor
        second_recovered = await read_events(
            client,
            {**headers, "Last-Event-ID": second_cursor},
            handoff[0][1]["stream_url"],
            params={"after_seq": "0-0"},
        )
        assert_run_replay(second_recovered, second_cursor, second_run, requests[1], thread)

        # 真正重连回零会重放已消费帧；独立消费oracle必须因重复ID拒绝。
        rewound = await read_events(
            client, headers, handoff[0][1]["stream_url"], first_only=True, params={"after_seq": "0-0"}
        )
        with pytest.raises(AssertionError, match="已消费事件被重放"):
            assert_run_replay(rewound, second_cursor, second_run, requests[1], thread, terminal=False)
        write_evidence(
            "negative-control",
            {"run_id": second_run, "saved_cursor": second_cursor, "replayed_id": rewound[0][2], "rejected": True},
        )

        redis = await get_redis_client()
        results = {}
        for request_id, run_id, events in (
            (requests[0], first_run, first_recovered),
            (requests[1], second_run, second_recovered),
        ):
            result = await task_get(client, headers, request_id)
            results[run_id] = result
            assert result["execution_status"] == "completed" and result["request_status"] == "dispatched"
            assert result["run_id"] == run_id and result["thread_id"] == thread
            expected = f"HEALTH_CONSULTATION_E2E_OK:{token}:{'one' if request_id == requests[0] else 'two'}"
            assert result["result"] == {
                "result_type": "general_education_answer",
                "scope": "general_education",
                "answer": expected,
                "citations": [],
            }
            real_ids = [event_id for _, _, event_id in events if event_id]
            tail = real_ids[-1]
            for _ in range(2):
                resumed_tail = await read_events(
                    client, headers, f"/api/agent/runs/{run_id}/events", params={"after_seq": tail}
                )
                assert resumed_tail == [
                    (
                        "end",
                        {
                            "run_id": run_id,
                            "thread_id": thread,
                            "request_id": request_id,
                            "payload": {"status": "completed"},
                        },
                        None,
                    )
                ]
            rows = await redis.xrange(f"run:events:{run_id}")
            assert any(event_id == tail for event_id, _ in rows), "游标来自本Run实际Redis行"
            write_evidence("redis", {"run_id": run_id, "rows": rows})
            assert await redis.delete(f"run:events:{run_id}") == 1
            missing = await read_events(client, headers, f"/api/agent/runs/{run_id}/events", params={"after_seq": tail})
            assert missing == resumed_tail and not await redis.exists(f"run:events:{run_id}")
            assert await task_get(client, headers, request_id) == result

        async with pg_manager.get_async_session_context() as session:
            request_rows = list(
                await session.scalars(
                    select(AgentRunRequest).where(AgentRunRequest.request_id.in_(requests)).order_by(AgentRunRequest.id)
                )
            )
            run_rows = list(
                await session.scalars(
                    select(AgentRun).where(AgentRun.request_id.in_(requests)).order_by(AgentRun.created_at)
                )
            )
            assert [row.request_id for row in request_rows] == requests
            assert [row.status for row in request_rows] == ["dispatched", "dispatched", "cancelled"]
            assert [row.id for row in run_rows] == [first_run, second_run]
            facts = []
            for request, run in zip(request_rows, run_rows, strict=False):
                message = await session.get(Message, run.output_message_id)
                attempts = list(await session.scalars(select(AgentRunAttempt).where(AgentRunAttempt.run_id == run.id)))
                assert request.dispatched_run_id == run.id and run.request_id == request.request_id
                assert (
                    message.id == results[run.id]["final_message_id"]
                    and message.content == results[run.id]["result"]["answer"]
                    and run.conversation_thread_id == thread
                    and message.run_id == run.id
                    and message.request_id == request.request_id
                    and message.delivery_status == "complete"
                )
                assert len(attempts) == 1 and attempts[0].worker_id and attempts[0].outcome == "completed"
                assert run.worker_id is None and run.lease_expires_at is None and not run.runtime_cleanup_pending
                facts.append(
                    {
                        "request": request.to_dict(),
                        "run": run.to_dict(),
                        "message_id": message.id,
                        "message_request_id": message.request_id,
                        "message_run_id": message.run_id,
                        "message_content": message.content,
                        "attempt_id": attempts[0].id,
                        "worker_id": attempts[0].worker_id,
                        "outcome": attempts[0].outcome,
                    }
                )
            write_evidence("pg-final", {"facts": facts, "request_count": 3, "run_count": 2})
        assert (await observations())["calls"] == [
            {"step": "one", "phase": "read", "record_ids": []},
            {"step": "one", "phase": "finalize", "record_ids": confirmed.json()["target_ids"]},
            {"step": "one", "phase": "answer", "record_ids": confirmed.json()["target_ids"]},
            {"step": "two", "phase": "read", "record_ids": []},
            {"step": "two", "phase": "finalize", "record_ids": confirmed.json()["target_ids"]},
            {"step": "two", "phase": "answer", "record_ids": confirmed.json()["target_ids"]},
        ]
        for other in users[1:]:
            await task_get(client, other["headers"], requests[1], expected_status=404)
        async with pg_manager.get_async_session_context() as session:
            request = await session.scalar(select(AgentRunRequest).where(AgentRunRequest.request_id == requests[1]))
            request.dispatched_run_id = first_run
        try:
            assert (await task_get(client, headers, requests[1], expected_status=410))["code"] == "source_invalidated"
        finally:
            async with pg_manager.get_async_session_context() as session:
                request = await session.scalar(select(AgentRunRequest).where(AgentRunRequest.request_id == requests[1]))
                request.dispatched_run_id = second_run
        async with pg_manager.get_async_session_context() as session:
            run = await session.get(AgentRun, second_run)
            pointer = run.output_message_id
            run.output_message_id = None
        try:
            assert (await task_get(client, headers, requests[1], expected_status=409))["code"] == "answer_unavailable"
        finally:
            async with pg_manager.get_async_session_context() as session:
                (await session.get(AgentRun, second_run)).output_message_id = pointer
        assert (
            await client.post(
                f"{ROOT}/members/{member}/processing-consents", headers=headers, json={**consent, "accepted": False}
            )
        ).status_code == 200
        assert (await task_get(client, headers, requests[1], expected_status=403))["code"] == "consent_required"
        assert (
            await client.put(
                f"{ROOT}/members/{member}/grants", headers=headers, json={"actor_uid": owner["uid"], "scopes": []}
            )
        ).status_code == 200
        await task_get(client, headers, requests[1], expected_status=404)
    finally:
        await replay.get("/release", params={"token": token})
        await drain_requests(client, headers, requests)
        async with pg_manager.get_async_session_context() as session:
            run_ids = list(await session.scalars(select(AgentRun.id).where(AgentRun.request_id.in_(requests))))
        redis = await get_redis_client()
        for run_id in run_ids:
            await redis.delete(f"run:events:{run_id}", f"run:cancel:{run_id}")
            assert not await redis.exists(f"run:events:{run_id}", f"run:cancel:{run_id}")
        write_evidence("redis-cleanup", {"run_ids": run_ids, "remaining_keys": 0})


@pytest_asyncio.fixture
async def recovery_runtime(isolated_health):  # noqa: F811
    """只拥有本fixture启动的本地重放进程，已有监听直接拒绝。"""
    try:
        with socket.create_connection(("127.0.0.1", 8766), timeout=1):
            pass
    except OSError:
        pass
    else:
        raise RuntimeError("8766已有服务，拒绝接管重放")
    output = evidence_directory()
    with (output / "replay.log").open("w", encoding="utf-8") as log:
        process = subprocess.Popen(
            [sys.executable, "test/support/health_consultation_replay_server.py"], stdout=log, stderr=log
        )
        try:
            async with httpx.AsyncClient(base_url="http://localhost:8766", timeout=10) as replay:

                async def ready():
                    """只轮询所属进程的合成健康端点。"""
                    if process.poll() is not None:
                        raise RuntimeError("所属重放提前退出")
                    try:
                        return (await replay.get("/health")).status_code == 200
                    except httpx.ConnectError:
                        return False

                await wait_until(ready, bool)
                yield (*isolated_health, replay)
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
            assert process.poll() is not None
            write_evidence("replay-cleanup", {"pid": process.pid, "exit_code": process.returncode})
            await close_async_redis_client()


async def task_get(client, headers, request_id, *, expected_status=200):
    """保存每次真实查询响应，错误响应不得含健康结果或最终消息。"""
    response = await client.get(f"{ROOT}/tasks/{request_id}", headers=headers)
    assert response.status_code == expected_status, response.text
    payload = response.json()
    if expected_status == 200:
        assert response.headers["Cache-Control"] == "no-store"
    else:
        assert "result" not in payload and "final_message_id" not in payload
    write_evidence("task-get", {"request_id": request_id, "status_code": response.status_code, "payload": payload})
    return payload


async def read_events(client, headers, url, *, first_only=False, params=None):
    """保留真实event/data/id，首帧退出主动关闭网络连接。"""
    events, event, event_id, lines = [], "message", None, []
    async with asyncio.timeout(60):
        async with client.stream(
            "GET", url, headers=headers, params={"verbose": "false", **(params or {})}
        ) as response:
            assert response.status_code == 200
            async for line in response.aiter_lines():
                if line.startswith("event:"):
                    event = line[6:].strip()
                elif line.startswith("id:"):
                    event_id = line[3:].strip()
                elif line.startswith("data:"):
                    lines.append(line[5:].strip())
                elif not line and lines:
                    events.append((event, json.loads("\n".join(lines)), event_id))
                    lines, event, event_id = [], "message", None
                    if first_only or events[-1][0] in {
                        "end",
                        "error",
                        "run_created",
                        "cancelled",
                        "rejected",
                        "failed",
                    }:
                        break
    write_evidence(
        "sse",
        {
            "url": url,
            "after_seq": (params or {}).get("after_seq"),
            "last_event_id": headers.get("Last-Event-ID"),
            "events": events,
        },
    )
    assert events, "真实SSE没有业务帧"
    return events


def assert_run_replay(events, cursor, run_id, request_id, thread, *, terminal=True):
    """独立oracle按数值游标核对同Run事件与终态，不依赖实现投影。"""
    previous = tuple(map(int, cursor.split("-")))
    for _, payload, event_id in events:
        assert payload["run_id"] == run_id and payload["thread_id"] == thread
        if "request_id" in payload:
            assert payload["request_id"] == request_id
        if event_id is not None:
            current = tuple(map(int, event_id.split("-")))
            assert current > previous, "已消费事件被重放"
            previous = current
    if terminal:
        assert events[-1][0] == "end" and events[-1][1]["request_id"] == request_id
        assert events[-1][1]["payload"]["status"] == "completed"


def write_evidence(kind, data):
    """只保存本轮合成数据，不写身份凭据或全局配置正文。"""
    with (evidence_directory() / f"{kind}.jsonl").open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(data, ensure_ascii=False, default=str) + "\n")


def evidence_directory():
    """允许runner指定容器临时证据目录。"""
    directory = Path(os.getenv("HEALTH_TASK_RECOVERY_OUTPUT", "test/.tmp/health-task-recovery"))
    directory.mkdir(parents=True, exist_ok=True)
    return directory

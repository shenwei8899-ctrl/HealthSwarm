"""隔离 Compose 中的真实 API、ARQ worker、FIFO、SSE 和 PG 咨询链路。"""

import asyncio
import hashlib
import json
import os
import shutil
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select, text

from test.integration.services.test_health_vision_http import (
    ROOT,
    confirmation,
    create_member,
    field,
    health_http,  # noqa: F401
)
from yuxi.config import get_user_data_dir
from yuxi.services.agent_run_manifest_service import compute_manifest_fingerprint
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_business import AgentRun, AgentRunAttempt, AgentRunRequest, Message, Skill
from yuxi.workspace.paths import global_user_data_dir

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.e2e,
    pytest.mark.slow,
    pytest.mark.skipif(
        os.getenv("HEALTH_CONSULTATION_E2E_ISOLATED") != "true",
        reason="健康咨询合成 E2E 仅在专用 Compose 隔离槽位运行",
    ),
]
MODEL = "deterministic-health-20261004"


@pytest_asyncio.fixture
async def isolated_health(health_http):  # noqa: F811
    """同时校验启动标记和实际数据库，禁止在原开发槽位开启审批。"""
    assert os.getenv("HEALTH_CONSULTATION_E2E_ISOLATED") == "true", "必须使用独立合成 Compose 槽位"
    async with pg_manager.get_async_session_context() as session:
        assert await session.scalar(text("SELECT current_database()")) == "health_consultation_e2e"
    client, users = health_http
    assert str(client.base_url).rstrip("/") == "http://localhost:5050", "隔离测试必须访问同槽位 API"
    original = await client.get(f"{ROOT}/configuration", headers=users[2]["headers"])
    assert original.status_code == 200 and not original.json()["consultation"]["available"]
    assert not original.json()["policy_version"], "测试不能覆盖已有审批配置"
    provider_id = f"health-replay-{uuid4().hex[:12]}"
    payload = {
        "provider_id": provider_id,
        "display_name": "Synthetic health replay only",
        "provider_type": "openai",
        "base_url": "http://api:8766/v1",
        "api_key": "synthetic-health-replay-key",
        "capabilities": ["chat"],
        "enabled_models": [{"id": MODEL, "display_name": MODEL, "type": "chat", "source": "manual"}],
        "is_enabled": True,
    }
    created = await client.post("/api/system/model-providers", headers=users[2]["headers"], json=payload)
    assert created.status_code == 200, created.text
    model_spec = f"{provider_id}:{MODEL}"
    try:
        configured = await client.put(
            f"{ROOT}/configuration",
            headers=users[2]["headers"],
            json={
                "consultation_model": model_spec,
                "policy_version": "synthetic-local-only-v1",
                "cloud_processing_reviewed": True,
            },
        )
        assert configured.status_code == 200 and configured.json()["consultation"]["available"], configured.text
        yield client, users, configured.json(), model_spec
    finally:
        reset = await client.put(f"{ROOT}/configuration", headers=users[2]["headers"], json={})
        assert reset.status_code == 200 and not reset.json()["consultation"]["available"]
        deleted = await client.delete(f"/api/system/model-providers/{provider_id}", headers=users[2]["headers"])
        assert deleted.status_code == 200
        root = get_user_data_dir().resolve()
        for actor in users:
            target = global_user_data_dir(actor["uid"])
            target.resolve().relative_to(root)
            assert target.name == actor["uid"] and actor["uid"].startswith("pytest_health_")
            if target.exists():
                shutil.rmtree(target)


async def collect_sse(client, headers, run_id):
    """真实网络 SSE 保留最终 end 与 request/run 标识供结果对照。"""
    events, event, lines = [], "message", []
    async with client.stream("GET", f"/api/agent/runs/{run_id}/events?verbose=false", headers=headers) as response:
        assert response.status_code == 200
        async for line in response.aiter_lines():
            if line.startswith("event:"):
                event = line[6:].strip()
            elif line.startswith("data:"):
                lines.append(line[5:].strip())
            elif not line and lines:
                payload = json.loads("\n".join(lines))
                events.append((event, payload))
                lines, event = [], "message"
                if events[-1][0] == "end":
                    return events
    pytest.fail("真实 SSE 未产生终态 end")


async def wait_until(read, predicate, timeout=35):
    """只轮询明确的业务事实；超时保留最终响应用于诊断。"""
    async with asyncio.timeout(timeout):
        while True:
            value = await read()
            if predicate(value):
                return value
            await asyncio.sleep(0.1)


async def test_bound_consultation_fifo_preserves_confirmed_records_and_own_outputs(isolated_health):
    """两个请求真实排队并依次执行，工具、checkpoint、审计和输出均回读。"""
    client, users, configuration, model_spec = isolated_health
    owner = users[0]
    headers = owner["headers"]
    published = await client.get(
        "/api/system/skills/family-nutritionist/file", headers=headers, params={"path": "SKILL.md"}
    )
    assert published.status_code == 200
    skill_text = published.json()["data"]["content"]
    assert "## 咨询流程" in skill_text and "## 日常反馈与记忆边界" in skill_text
    assert "餐次反馈保存入口尚未接入" not in skill_text
    async with pg_manager.get_async_session_context() as session:
        skill = await session.scalar(select(Skill).where(Skill.slug == "family-nutritionist"))
        assert skill is not None and skill.version == "2026.10.08.4"
        expected_skill = {
            "slug": "family-nutritionist",
            "version": skill.version,
            "content_hash": skill.content_hash,
            "preload_content_hash": hashlib.sha256(skill_text.encode()).hexdigest(),
        }
    member_id = await create_member(client, headers)
    request_key = str(uuid4())
    bound = await client.post(
        f"{ROOT}/members/{member_id}/consultations",
        headers={**headers, "Idempotency-Key": request_key},
        json={"client_request_id": request_key},
    )
    assert bound.status_code == 201
    thread_id = bound.json()["thread_id"]
    token = uuid4().hex
    draft = await client.post(
        f"{ROOT}/manual-drafts",
        headers=headers,
        json={"member_id": member_id, "kind": "report", "report": {"fields": [field()]}},
    )
    assert draft.status_code == 201
    data, key = confirmation()
    confirmed = await client.post(
        f"{ROOT}/report-extractions/{draft.json()['id']}/confirm", headers={**headers, **key}, json=data
    )
    assert confirmed.status_code == 200
    record_id = confirmed.json()["target_ids"][0]
    pending = await client.post(
        f"{ROOT}/manual-drafts",
        headers=headers,
        json={
            "member_id": member_id,
            "kind": "report",
            "report": {"fields": [{**field(), "name": "不得外发的未确认草稿"}]},
        },
    )
    assert pending.status_code == 201
    requests = [str(uuid4()), str(uuid4())]
    stream_tasks = []
    submitted_requests = []
    async with httpx.AsyncClient(base_url="http://localhost:8766", timeout=10) as replay:
        try:
            for denied_thread, expected_status, expected_detail in (
                (str(uuid4()), 404, "专属咨询不存在或无权访问"),
                (thread_id, 403, "请先同意当前用途、处理方及政策"),
            ):
                denied_request = str(uuid4())
                submitted_requests.append(denied_request)
                denied = await client.post(
                    "/api/agent/runs",
                    headers=headers,
                    json={
                        "query": f"HEALTH_CONSULTATION_E2E:{token}:one",
                        "agent_slug": "health-consultation",
                        "thread_id": denied_thread,
                        "meta": {"request_id": denied_request},
                    },
                )
                assert denied.status_code == expected_status and denied.json()["detail"] == expected_detail
                async with pg_manager.get_async_session_context() as session:
                    for model in (Message, AgentRunRequest, AgentRun):
                        assert await session.scalar(select(model).where(model.request_id == denied_request)) is None
            consent = await client.post(
                f"{ROOT}/members/{member_id}/processing-consents",
                headers=headers,
                json={
                    "purpose": "consultation",
                    "accepted": True,
                    "processor": configuration["consultation"]["processor"],
                    "policy_version": configuration["policy_version"],
                },
            )
            assert consent.status_code == 200, consent.text

            skill_endpoint = "/api/system/skills/family-nutritionist/enabled"
            try:
                disabled = await client.put(skill_endpoint, headers=users[2]["headers"], json={"enabled": False})
                assert disabled.status_code == 200, disabled.text
                denied_request = str(uuid4())
                submitted_requests.append(denied_request)
                denied = await client.post(
                    "/api/agent/runs",
                    headers=headers,
                    json={
                        "query": f"HEALTH_CONSULTATION_E2E:{token}:one",
                        "agent_slug": "health-consultation",
                        "thread_id": thread_id,
                        "meta": {"request_id": denied_request},
                    },
                )
                assert denied.status_code == 503 and denied.json()["detail"] == "家庭营养师 Skill 未启用，请联系管理员"
                async with pg_manager.get_async_session_context() as session:
                    for model in (Message, AgentRunRequest, AgentRun):
                        assert await session.scalar(select(model).where(model.request_id == denied_request)) is None
            finally:
                enabled = await client.put(skill_endpoint, headers=users[2]["headers"], json={"enabled": True})
                assert enabled.status_code == 200, enabled.text

            async def stats():
                """直接读取本轮外部协议入口的调用记录。"""
                async with pg_manager.get_async_session_context() as session:
                    run = await session.scalar(select(AgentRun).where(AgentRun.request_id == requests[0]))
                    if run is not None and run.status in {"failed", "cancelled"}:
                        pytest.fail(f"合成咨询在协议调用前终止：{run.error_type}: {run.error_message}")
                return (await replay.get("/observations", params={"token": token})).json()

            assert (await stats())["calls"] == []
            first_body = {
                "query": f"HEALTH_CONSULTATION_E2E:{token}:one",
                "agent_slug": "health-consultation",
                "thread_id": thread_id,
                "model_spec": None,
                "meta": {"request_id": requests[0]},
            }
            submitted_requests.append(requests[0])
            first = await client.post("/api/agent/runs", headers=headers, json=first_body)
            assert first.status_code == 200, first.text
            first_run = first.json()["run_id"]
            await wait_until(stats, lambda result: len(result["calls"]) == 1)
            duplicate = await client.post("/api/agent/runs", headers=headers, json=first_body)
            assert duplicate.status_code == 200 and duplicate.json()["run_id"] == first_run
            submitted_requests.append(requests[1])
            second = await client.post(
                "/api/agent/runs",
                headers=headers,
                json={
                    **first_body,
                    "query": f"HEALTH_CONSULTATION_E2E:{token}:two",
                    "meta": {"request_id": requests[1]},
                },
            )
            assert second.status_code == 200 and second.json()["status"] == "queued", second.text
            async with pg_manager.get_async_session_context() as session:
                rows = list(
                    (
                        await session.scalars(
                            select(AgentRunRequest)
                            .where(AgentRunRequest.request_id.in_(requests))
                            .order_by(AgentRunRequest.id)
                        )
                    ).all()
                )
                assert [row.request_id for row in rows] == requests
                assert (
                    rows[0].status == "dispatched" and rows[1].status == "queued" and rows[1].dispatched_run_id is None
                )
                assert (await session.get(AgentRun, first_run)).status == "running"
            stream_tasks.append(asyncio.create_task(collect_sse(client, headers, first_run)))
            await replay.get("/release", params={"token": token})

            async def dispatched():
                """排队 Request 的 run_id 只从 PG owning 行取得。"""
                async with pg_manager.get_async_session_context() as session:
                    return await session.scalar(
                        select(AgentRunRequest.dispatched_run_id).where(AgentRunRequest.request_id == requests[1])
                    )

            second_run = await wait_until(dispatched, bool)
            stream_tasks.append(asyncio.create_task(collect_sse(client, headers, second_run)))
            events = await asyncio.wait_for(asyncio.gather(*stream_tasks), 35)
            for index, run_id in enumerate((first_run, second_run)):
                end = events[index][-1]
                assert end[0] == "end" and end[1]["request_id"] == requests[index]
                result = await client.get(f"/api/agent/runs/{run_id}/result", headers=headers)
                assert result.status_code == 200 and result.json()["status"] == "completed", result.text
                assert result.json()["output"] == f"HEALTH_CONSULTATION_E2E_OK:{token}:{('one', 'two')[index]}"
            observed = await stats()
            assert [(call["step"], call["phase"]) for call in observed["calls"]] == [
                ("one", "read"),
                ("one", "answer"),
                ("two", "read"),
                ("two", "answer"),
            ]
            assert [call["record_ids"] for call in observed["calls"]] == [[], [record_id], [], [record_id]]
            async with pg_manager.get_async_session_context() as session:
                runs = [await session.get(AgentRun, run_id) for run_id in (first_run, second_run)]
                assert runs[1].started_at >= runs[0].finished_at
                for index, run in enumerate(runs):
                    assert run.status == "completed" and run.worker_id is None and not run.runtime_cleanup_pending
                    assert run.manifest["model"]["spec"] == model_spec
                    assert run.manifest["resources"] == {
                        "tools": [
                            "get_confirmed_profile",
                            "get_confirmed_diet",
                            "get_complete_health_profile",
                            "get_member_weight_records",
                            "get_member_blood_pressure_records",
                            "query_reviewed_nutrition_knowledge",
                            "get_member_memories",
                            "remember_member_fact",
                            "get_meal_feedback",
                        ],
                        "mcps": [],
                        "skills": [expected_skill],
                    }
                    assert run.manifest_fingerprint == compute_manifest_fingerprint(run.manifest)
                    attempts = list(
                        (await session.scalars(select(AgentRunAttempt).where(AgentRunAttempt.run_id == run.id))).all()
                    )
                    assert len(attempts) == 1 and attempts[0].outcome == "completed" and attempts[0].finished_at
                    output = await session.get(Message, run.output_message_id)
                    assert (
                        output.run_id == run.id
                        and output.request_id == requests[index]
                        and output.message_type == "text"
                    )
                    assert output.content == f"HEALTH_CONSULTATION_E2E_OK:{token}:{('one', 'two')[index]}"
                    assert run.langfuse_trace_id is None
            checkpoint = await pg_manager.get_langgraph_checkpointer().aget_tuple(
                {"configurable": {"thread_id": thread_id}}
            )
            saved = checkpoint.checkpoint["channel_values"]["messages"]
            assert saved[-1].text == f"HEALTH_CONSULTATION_E2E_OK:{token}:two"
            tool_messages = [message for message in saved if message.type == "tool"]
            assert len(tool_messages) == 2 and all(
                json.loads(message.content)["records"][0]["record_id"] == record_id for message in tool_messages
            )
        finally:
            try:
                await replay.get("/release", params={"token": token})
            finally:
                for task in stream_tasks:
                    task.cancel()
                await asyncio.gather(*stream_tasks, return_exceptions=True)
                await drain_requests(client, headers, submitted_requests)


async def drain_requests(client, headers, request_ids):
    """失败路径也等待本轮 worker 收敛，避免清理后继续写入业务行。"""
    async with pg_manager.get_async_session_context() as session:
        queued = list(
            (
                await session.scalars(
                    select(AgentRunRequest.request_id).where(
                        AgentRunRequest.request_id.in_(request_ids), AgentRunRequest.status == "queued"
                    )
                )
            ).all()
        )
    for request_id in queued:
        await client.post(f"/api/agent/requests/{request_id}/cancel", headers=headers)
    async with pg_manager.get_async_session_context() as session:
        active = list(
            (
                await session.scalars(
                    select(AgentRun.id).where(
                        AgentRun.request_id.in_(request_ids),
                        AgentRun.status.notin_(("completed", "failed", "cancelled", "interrupted")),
                    )
                )
            ).all()
        )
    for run_id in active:
        await client.post(f"/api/agent/runs/{run_id}/cancel", headers=headers)

    async def settled():
        """终态和 runtime 清理均从数据库核对，不猜测 worker 是否停止。"""
        async with pg_manager.get_async_session_context() as session:
            rows = list((await session.scalars(select(AgentRun).where(AgentRun.request_id.in_(request_ids)))).all())
            return all(
                row.status in {"completed", "failed", "cancelled", "interrupted"}
                and row.worker_id is None
                and not row.runtime_cleanup_pending
                for row in rows
            )

    await wait_until(settled, bool)

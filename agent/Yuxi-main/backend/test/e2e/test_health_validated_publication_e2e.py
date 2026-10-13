"""健康解释在真实Worker完成校验提交前仅公开固定状态，恢复也拒绝原始事件。"""

import asyncio
import json
import os
import socket
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import delete, select

from test.e2e.test_health_blood_glucose_e2e import add_blood_glucose, correct_blood_glucose
from test.e2e.test_health_blood_lipids_e2e import add_blood_lipids
from test.e2e.test_health_blood_pressure_e2e import add_blood_pressure
from test.e2e.test_health_consultation_e2e import drain_requests, isolated_health, wait_until  # noqa: F401
from test.integration.services.test_health_task_http import entry, verified_task_cleanup  # noqa: F401
from test.integration.services.test_health_vision_http import ROOT, health_http  # noqa: F401
from test.integration.services.test_health_weight_http import cleanup_weight_subject, create_weight_subject
from test.support.health_validated_publication_replay_server import MODEL, PORT
from yuxi.services.agent_run_service import get_agent_run_progress
from yuxi.services.health_evidence_service import validate_evidence_publication
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.services.run_queue_service import append_run_stream_event, get_redis_client
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_business import AgentRun, AgentRunAttempt, Message, User
from yuxi.storage.postgres.models_health import (
    HealthBloodGlucoseUse,
    HealthBloodLipidsUse,
    HealthBloodPressureUse,
    NutritionEvidenceCitation,
)
from yuxi.storage.redis import close_async_redis_client
from yuxi.utils.auth_utils import AuthUtils

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.e2e,
    pytest.mark.slow,
    pytest.mark.skipif(os.getenv("HEALTH_CONSULTATION_E2E_ISOLATED") != "true", reason="仅在独立合成槽位运行"),
]
CASES = (
    ("consultation", add_blood_glucose, ("scope", "consent", "withdrawn")),
    ("blood_glucose", add_blood_glucose, ("source",)),
    ("blood_lipids", add_blood_lipids, ("cancel",)),
    ("blood_pressure", add_blood_pressure, ("failure",)),
)


@pytest.mark.parametrize("role,add_record,negative_modes", CASES)
async def test_education_publication_live_reconnect_and_authoritative_results(
    publication_runtime, role, add_record, negative_modes
):
    """四角色每例成功和伪引证，并覆盖更正、撤权、取消及模型失败。"""
    runtime = publication_runtime
    for mode in ("success", "forged", *negative_modes):
        subject = await create_weight_subject(runtime.client, runtime.users)
        record = await add_record(subject)
        token = uuid4().hex
        streams = []
        requests = []
        try:
            consent = await grant_consent(subject, runtime.configuration, accepted=True)
            evidence = await publish_evidence(runtime, token)
            task_type = "consultation" if role == "consultation" else f"{role}_review"
            response = await entry(subject.client, subject.headers, subject.member_id, task_type)
            assert response.status_code == 200 and response.json()["entry_status"] == "ready", response.text
            bound = response.json()
            request_id = str(uuid4())
            runtime.requests.append(request_id)
            requests.append(request_id)
            submitted = await subject.client.post(
                "/api/agent/runs",
                headers=subject.headers,
                json={
                    "agent_slug": bound["agent_slug"],
                    "thread_id": bound["thread_id"],
                    "query": f"PUBLICATION_E2E:{token}:{role}:{mode}",
                    "meta": {"request_id": request_id},
                },
            )
            assert submitted.status_code == 200 and submitted.json()["status"] == "dispatched", submitted.text
            run_id = submitted.json()["run_id"]
            live = []
            streams.append(asyncio.create_task(collect_public_events(subject, run_id, live)))

            async def delta_sent():
                """协议门闩证明真实Worker已消费两项服务工具并进入最终模型流。"""
                async with pg_manager.get_async_session_context() as session:
                    run = await session.get(AgentRun, run_id)
                    if run.status in {"failed", "cancelled"}:
                        pytest.fail(f"合成模型在最终delta前终止：{run.error_type}: {run.error_message}")
                return (await runtime.replay.get("/observations", params={"token": token})).json()

            observation = await wait_until(delta_sent, lambda value: value["delta_sent"], timeout=60)
            assert [call["phase"] for call in observation["calls"]] == ["records", "knowledge", "answer"]
            await wait_until(
                lambda: async_value(
                    any(
                        event == "custom" and payload.get("payload", {}).get("name") == "yuxi.init"
                        for event, payload, _ in live
                    )
                ),
                bool,
            )
            legacy_ids = await inject_legacy_raw_events(run_id, bound["thread_id"], request_id, token)
            await wait_until(lambda: async_value(live), bool)
            await assert_pending_views(subject, bound, request_id, run_id, token)
            assert_status_only(live, token)
            cursor = next(event_id for _, _, event_id in reversed(live) if event_id)
            streams[0].cancel()
            await asyncio.gather(streams[0], return_exceptions=True)
            recovered = []
            streams.append(
                asyncio.create_task(collect_public_events(subject, run_id, recovered, after_seq=cursor, verbose=True))
            )
            if mode == "source":
                corrected = await correct_blood_glucose(subject, record["id"])
                assert corrected["version"] == 2
            elif mode == "scope":
                revoked = await subject.client.put(
                    f"{ROOT}/members/{subject.member_id}/grants",
                    headers=subject.headers,
                    json={"actor_uid": subject.uid, "scopes": ["profile_view", "report_view", "diet_edit"]},
                )
                assert revoked.status_code == 200, revoked.text
                await probe_private_audit(subject, bound["thread_id"], token, revoked=True)
            elif mode == "consent":
                await grant_consent(subject, runtime.configuration, accepted=False)
            elif mode == "withdrawn":
                withdrawn = await subject.client.delete(
                    f"{ROOT}/nutrition-evidence/{evidence}", headers=runtime.users[2]["headers"]
                )
                assert withdrawn.status_code == 200, withdrawn.text
            elif mode == "cancel":
                cancelled = await subject.client.post(f"/api/agent/runs/{run_id}/cancel", headers=subject.headers)
                assert cancelled.status_code == 200, cancelled.text
            assert (await runtime.replay.get("/release", params={"token": token})).status_code == 200
            await wait_until(lambda: run_settled(run_id), bool, timeout=60)
            redis_rows = await (await get_redis_client()).xrange(f"run:events:{run_id}")
            for event_id, fields in redis_rows:
                if event_id not in legacy_ids:
                    assert_no_candidate(fields, token)
            if mode == "failure":
                failed_stream = (await runtime.replay.get("/observations", params={"token": token})).json()
                assert failed_stream["stream_failed"] is True
            await asyncio.wait_for(streams[-1], 60)
            assert_status_only(live + recovered, token)
            rewind = []
            await collect_public_events(subject, run_id, rewind, verbose=False)
            assert_status_only(rewind, token)
            assert any(
                event == "custom" and payload["payload"]["name"] == "yuxi.init" and event_id not in legacy_ids
                for event, payload, event_id in rewind
            ) or mode in {"source", "scope"}
            write_evidence("sse", {"role": role, "mode": mode, "live": live, "recovered": recovered, "rewind": rewind})
            if mode == "success":
                assert recovered[-1][0] == rewind[-1][0] == "end"
                assert recovered[-1][1]["payload"]["status"] == "completed"
                await assert_committed_answer(subject, bound, request_id, run_id, token)
            else:
                await assert_rejected_answer(subject, bound, request_id, run_id, token, mode)
            if mode == "success":
                # 完成后撤回来源，重连仍只有状态；最终正文读取必须fresh拒绝。
                withdrawn = await subject.client.delete(
                    f"{ROOT}/nutrition-evidence/{evidence}", headers=runtime.users[2]["headers"]
                )
                assert withdrawn.status_code == 200
                stale = await subject.client.get(f"/api/agent/runs/{run_id}/result", headers=subject.headers)
                assert stale.status_code in {409, 410}, stale.text
                assert f"PUBLICATION_BODY:{token}" not in stale.text
                stale_history = await subject.client.get(
                    f"/api/chat/thread/{bound['thread_id']}/history", headers=subject.headers
                )
                assert stale_history.status_code == 200
                assert not any(item["type"] == "ai" for item in stale_history.json()["history"])
                stale_task = await subject.client.get(f"{ROOT}/tasks/{request_id}", headers=subject.headers)
                stale_citations = await subject.client.get(
                    f"{ROOT}/consultation-runs/{run_id}/citations", headers=subject.headers
                )
                assert stale_task.status_code == stale_citations.status_code == 410
                for stale_read in (stale_task, stale_citations):
                    assert_no_candidate(stale_read.json(), token)
                stale_events = []
                await collect_public_events(subject, run_id, stale_events, verbose=True)
                assert_status_only(stale_events, token)
            assert consent["accepted"] is True
        finally:
            await runtime.replay.get("/release", params={"token": token})
            for task in streams:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*streams, return_exceptions=True)
            await drain_requests(subject.client, subject.headers, requests)
            async with pg_manager.get_async_session_context() as session:
                for model in (HealthBloodGlucoseUse, HealthBloodLipidsUse, HealthBloodPressureUse):
                    await session.execute(delete(model).where(model.member_id == subject.member_id))
            await cleanup_weight_subject(subject)


async def assert_pending_views(subject, bound, request_id, run_id, token):
    """PG output尚未绑定；普通状态、消息、Task和进度均无模型候选。"""
    async with pg_manager.get_async_session_context() as session:
        run = await session.get(AgentRun, run_id)
        assert run.status == "running" and run.output_message_id is None
        assert run.first_output_at is not None and run.prepared_at <= run.first_output_at
        public = list(
            await session.scalars(
                select(Message).where(
                    Message.run_id == run_id, Message.message_type == "text", Message.role == "assistant"
                )
            )
        )
        assert public == []
        audits = list(
            await session.scalars(
                select(Message).where(Message.run_id == run_id, Message.message_type == "model_audit")
            )
        )
        assert any(f"PRIVATE_TOOL_PREAMBLE:{token}" in message.content for message in audits)
    progress = await get_agent_run_progress(run_id, agent_slug=bound["agent_slug"])
    assert progress["messages"] == [] and progress["last_seq"] != "0-0"
    await probe_private_audit(subject, bound["thread_id"], token)
    for path in (
        f"/api/agent/runs/{run_id}",
        f"/api/agent/runs/{run_id}/result",
        f"/api/chat/thread/{bound['thread_id']}/state?include_messages=true",
        f"/api/chat/thread/{bound['thread_id']}/history",
        f"{ROOT}/tasks/{request_id}",
    ):
        response = await subject.client.get(path, headers=subject.headers)
        assert response.status_code == 200, response.text
        assert_no_candidate(response.json(), token)
        if "/state?" in path:
            state = response.json()["agent_state"]
            for key in ("todos", "files", "artifacts", "subagent_runs"):
                assert not state.get(key), state
            assert not state.get("token_usage"), state
            assert not any(item["type"] == "ai" for item in response.json()["messages"])
        elif "/tasks/" in path:
            assert response.json()["result"] is None and response.json()["final_message_id"] is None
        elif path.endswith("/result"):
            assert response.json()["output"] == "" and response.json()["final_message_id"] is None


async def assert_committed_answer(subject, bound, request_id, run_id, token):
    """正式输出只能来自已提交的同Run Message，Task/history/state深等。"""
    task = await subject.client.get(f"{ROOT}/tasks/{request_id}", headers=subject.headers)
    result = await subject.client.get(f"/api/agent/runs/{run_id}/result", headers=subject.headers)
    assert task.status_code == result.status_code == 200
    assert task.json()["execution_status"] == result.json()["status"] == "completed"
    expected = task.json()["result"]["answer"]
    assert expected.startswith(f"PUBLICATION_BODY:{token}") and "[证据:" in expected
    assert result.json()["output"] == expected
    async with pg_manager.get_async_session_context() as session:
        run = await session.get(AgentRun, run_id)
        message = await session.get(Message, run.output_message_id)
        owner = await session.scalar(select(User).where(User.uid == run.uid))
        assert owner.role == "user"
        attempts = list(await session.scalars(select(AgentRunAttempt).where(AgentRunAttempt.run_id == run_id)))
        assert run.status == "completed" and run.worker_id is None and run.lease_expires_at is None
        assert run.prepared_at <= run.first_model_request_at <= run.first_output_at <= run.finished_at
        assert message.content == expected and message.delivery_status == "complete"
        assert message.run_id == run_id and message.request_id == request_id and message.message_type == "text"
        assert message.id == task.json()["final_message_id"] == result.json()["final_message_id"]
        assert len(attempts) == 1 and attempts[0].outcome == "completed"
        write_evidence(
            "pg",
            {
                "run_id": run_id,
                "request_id": request_id,
                "status": run.status,
                "output_message_id": message.id,
                "output": message.content,
            },
        )
    history = await subject.client.get(f"/api/chat/thread/{bound['thread_id']}/history", headers=subject.headers)
    state = await subject.client.get(
        f"/api/chat/thread/{bound['thread_id']}/state?include_messages=true", headers=subject.headers
    )
    assert history.status_code == state.status_code == 200
    assert [item["content"] for item in history.json()["history"] if item["type"] == "ai"] == [expected]
    assert [item["content"] for item in state.json()["messages"] if item["type"] == "ai"] == [expected]
    for payload in (task.json(), result.json(), history.json(), state.json()):
        assert_no_candidate(payload, token, allow_body=True)


async def assert_rejected_answer(subject, bound, request_id, run_id, token, mode):
    """失败原因来自PG；所有普通读取与重连不得暴露候选正文或内部错误。"""
    async with pg_manager.get_async_session_context() as session:
        run = await session.get(AgentRun, run_id)
        owner = await session.scalar(select(User).where(User.uid == run.uid))
        assert owner.role == "user"
        assert run.status == ("cancelled" if mode == "cancel" else "failed"), run.to_dict()
        assert run.output_message_id is None and run.worker_id is None and run.lease_expires_at is None
        public = list(
            await session.scalars(
                select(Message).where(
                    Message.run_id == run_id, Message.message_type == "text", Message.role == "assistant"
                )
            )
        )
        assert not public or all("PUBLICATION_BODY:" not in message.content for message in public)
        expected_guard = {
            "forged": "citation_invalid",
            "source": "blood_glucose_source_changed",
            "scope": "not_found",
            "consent": "consent_required",
            "withdrawn": "source_invalidated",
        }
        if mode in expected_guard:
            citations = list(
                await session.scalars(
                    select(NutritionEvidenceCitation).where(NutritionEvidenceCitation.run_id == run_id)
                )
            )
            assert len(citations) == 1
            citation_id = "00000000-0000-0000-0000-000000000000" if mode == "forged" else citations[0].id
            with pytest.raises(HealthVisionError) as denied:
                await validate_evidence_publication(session, run, f"PUBLICATION_BODY:{token} [证据:{citation_id}]")
            assert denied.value.code == expected_guard[mode]
        elif mode == "failure":
            assert run.error_type == "unexpected_error", run.to_dict()
        write_evidence(
            "pg",
            {
                "run_id": run_id,
                "request_id": request_id,
                "mode": mode,
                "status": run.status,
                "output_message_id": run.output_message_id,
                "error_type": run.error_type,
            },
        )
    for path in (
        f"/api/agent/runs/{run_id}",
        f"/api/agent/runs/{run_id}/result",
        f"/api/chat/thread/{bound['thread_id']}/state?include_messages=true",
        f"/api/chat/thread/{bound['thread_id']}/history",
        f"{ROOT}/tasks/{request_id}",
    ):
        response = await subject.client.get(path, headers=subject.headers)
        assert response.status_code in {200, 403, 404, 409, 410}, response.text
        assert_no_candidate(response.json(), token)
        if path.endswith("/result") and response.status_code == 200:
            assert response.json()["output"] == ""


async def collect_public_events(subject, run_id, events, *, after_seq="0-0", verbose=False):
    """实际网络订阅保留ID；结束或权限错误后关闭本次连接。"""
    event, event_id, lines = "message", None, []
    async with asyncio.timeout(70):
        async with subject.client.stream(
            "GET",
            f"/api/agent/runs/{run_id}/events",
            headers=subject.headers,
            params={"after_seq": after_seq, "verbose": str(verbose).lower()},
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
                    lines, event_id = [], None
                    if event in {"end", "error"}:
                        return
                    event = "message"
    assert events, "真实SSE没有状态事件"


async def probe_private_audit(subject, thread_id, token, *, revoked=False):
    """仅探针窗口提升本轮两账号，独立审计后恢复普通运行身份。"""
    actors = subject.users[:2]
    privileged_headers = []
    async with pg_manager.get_async_session_context() as session:
        for actor in actors:
            user = await session.scalar(select(User).where(User.uid == actor["uid"]))
            assert user.role == "user"
            user.role = "superadmin"
            privileged_headers.append(
                {"Authorization": f"Bearer {AuthUtils.create_access_token({'sub': str(user.id)})}"}
            )
    path = f"/api/chat/thread/{thread_id}/audits"
    try:
        audit = await subject.client.get(path, headers=privileged_headers[0])
        assert audit.status_code == (404 if revoked else 200), audit.text
        if revoked:
            assert "PRIVATE_TOOL_PREAMBLE" not in audit.text
        else:
            assert f"PRIVATE_TOOL_PREAMBLE:{token}" in audit.text
        other = await subject.client.get(path, headers=privileged_headers[1])
        assert other.status_code == 404 and "PRIVATE_TOOL_PREAMBLE" not in other.text, other.text
    finally:
        privileged_headers.clear()
        async with pg_manager.get_async_session_context() as session:
            for actor in actors:
                user = await session.scalar(select(User).where(User.uid == actor["uid"]))
                user.role = "user"
    ordinary = await subject.client.get(path, headers=subject.headers)
    assert ordinary.status_code == 403 and "PRIVATE_TOOL_PREAMBLE" not in ordinary.text, ordinary.text


def assert_status_only(events, token):
    """公开帧名单手写，工具、messages及模型state不可透传。"""
    for event, payload, _ in events:
        assert event in {"metadata", "status", "custom", "end", "error", "interrupt"}, event
        if event == "custom":
            data = payload["payload"]
            assert set(data) == {"name", "chunk"}, data
            chunk = data["chunk"]
            identity = {"run_id", "thread_id", "request_id", "status"}
            if data["name"] == "yuxi.init":
                assert set(chunk) == identity and chunk["status"] == "init", chunk
            else:
                assert data["name"] == "yuxi.health_progress", data
                assert set(chunk) == identity | {"phase", "message"} and chunk["status"] == "health_progress", chunk
                expected_message = {
                    "running": "正在回顾记录与审核知识",
                    "validating": "正在校验答复来源与引用",
                }
                assert chunk["phase"] in expected_message and chunk["message"] == expected_message[chunk["phase"]]
        assert_no_candidate(payload, token)


def assert_no_candidate(payload, token, *, allow_body=False):
    """独立哨兵覆盖正文、reasoning、工具前言和错误正文。"""
    encoded = json.dumps(payload, ensure_ascii=False)
    forbidden = [
        "PRIVATE_REASONING",
        "PRIVATE_TOOL_PREAMBLE",
        "PRIVATE_MODEL_FAILURE",
        "LEGACY_RAW",
        "synthetic-blood-",
    ]
    if not allow_body:
        forbidden.append(f"PUBLICATION_BODY:{token}")
    assert not any(marker in encoded for marker in forbidden), encoded


async def inject_legacy_raw_events(run_id, thread_id, request_id, token):
    """注入独立旧事件负控，证明consumer不依赖新producer已过滤。"""
    injected_ids = []
    for event, payload in (
        (
            "custom",
            {
                "name": "yuxi.init",
                "chunk": {
                    "status": "init",
                    "msg": f"LEGACY_RAW:{token}",
                    "meta": {"private": f"PRIVATE_REASONING:{token}"},
                },
            },
        ),
        (
            "messages",
            {
                "chunk": {
                    "request_id": request_id,
                    "stream_event": {
                        "type": "message_delta",
                        "content": f"LEGACY_RAW:{token}",
                        "reasoning_content": f"PRIVATE_REASONING:{token}",
                    },
                }
            },
        ),
        ("messages", {"chunk": {"request_id": request_id, "msg": {"type": "tool", "content": f"LEGACY_RAW:{token}"}}}),
        (
            "custom",
            {
                "name": "yuxi.agent_state",
                "agent_state": {"todos": [f"LEGACY_RAW:{token}"], "files": {"private": f"LEGACY_RAW:{token}"}},
            },
        ),
        (
            "custom",
            {
                "name": "yuxi.health_progress",
                "chunk": {"phase": "running", "message": f"LEGACY_RAW:{token}", "request_id": request_id},
            },
        ),
    ):
        injected_ids.append(await append_run_stream_event(run_id, event, payload, thread_id=thread_id))
    return injected_ids


async def grant_consent(subject, configuration, *, accepted):
    """合成用途同意经正式接口记录及撤销。"""
    response = await subject.client.post(
        f"{ROOT}/members/{subject.member_id}/processing-consents",
        headers=subject.headers,
        json={
            "purpose": "consultation",
            "accepted": accepted,
            "processor": configuration["consultation"]["processor"],
            "policy_version": configuration["policy_version"],
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


async def publish_evidence(runtime, token):
    """只发布唯一合成科普来源，不包含专业医学规则。"""
    response = await runtime.client.post(
        f"{ROOT}/nutrition-evidence",
        headers=runtime.users[2]["headers"],
        json={
            "source_ref": f"synthetic://publication/{token}",
            "source_version": "synthetic-v1",
            "title": f"合成发布验收 publication{token}",
            "content": f"publication{token} 仅用于验证来源协议，不提供医学建议。",
            "review_ref": f"synthetic://review/{token}",
            "reviewed_by": "synthetic-reviewer",
            "reviewed_at": (datetime.now(UTC) - timedelta(days=1)).isoformat(),
            "valid_until": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
            "reviewed_scope": {
                "domains": ["nutrition", "blood_glucose", "blood_lipids", "blood_pressure"],
                "population_category": "general_education",
                "population_description": "合成四角色共享通用教育，仅发布协议验收",
                "exclusion_conditions": [],
                "license_ref": f"synthetic://publication-license/{token}",
            },
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["evidence_id"]


async def async_value(value):
    """等待网络读取器已消费至少一帧。"""
    return value


async def run_settled(run_id):
    """等待正常执行收敛，不主动取消成功验证的运行。"""
    async with pg_manager.get_async_session_context() as session:
        run = await session.get(AgentRun, run_id)
        return (
            run.status in {"completed", "failed", "cancelled", "interrupted"}
            and run.worker_id is None
            and not run.runtime_cleanup_pending
        )


def write_evidence(kind, payload):
    """证据只含本轮合成Run，不保存账号Token或供应商配置。"""
    output = Path("test/.tmp/health-validated-publication")
    output.mkdir(parents=True, exist_ok=True)
    with (output / f"{kind}.jsonl").open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")


@pytest_asyncio.fixture
async def publication_runtime(isolated_health):  # noqa: F811
    """固定合成模型审批、回放及Redis事件只属于本fixture。"""
    client, users, configuration, original_model = isolated_health
    try:
        with socket.create_connection(("127.0.0.1", PORT), timeout=1):
            pass
    except OSError:
        pass
    else:
        raise RuntimeError("8779已有服务，拒绝接管发布验收回放")
    output = Path("test/.tmp/health-validated-publication")
    output.mkdir(parents=True, exist_ok=True)
    provider = f"publication-replay-{uuid4().hex[:12]}"
    requests = []
    with (output / f"replay-{provider}.log").open("w", encoding="utf-8") as log:
        process = subprocess.Popen(
            [sys.executable, "-m", "test.support.health_validated_publication_replay_server"], stdout=log, stderr=log
        )
        created = False
        try:
            async with httpx.AsyncClient(base_url=f"http://localhost:{PORT}", timeout=10) as replay:

                async def ready():
                    """所属回放退出明确失败，不接管别人的端口。"""
                    if process.poll() is not None:
                        raise RuntimeError("发布验收回放提前退出")
                    try:
                        return (await replay.get("/health")).status_code == 200
                    except httpx.ConnectError:
                        return False

                await wait_until(ready, bool)
                registered = await client.post(
                    "/api/system/model-providers",
                    headers=users[2]["headers"],
                    json={
                        "provider_id": provider,
                        "display_name": "Synthetic publication replay only",
                        "provider_type": "openai",
                        "base_url": f"http://api:{PORT}/v1",
                        "api_key": "synthetic-health-publication-key",
                        "capabilities": ["chat"],
                        "is_enabled": True,
                        "enabled_models": [{"id": MODEL, "display_name": MODEL, "type": "chat", "source": "manual"}],
                    },
                )
                assert registered.status_code == 200, registered.text
                created = True
                approved = await client.put(
                    f"{ROOT}/configuration",
                    headers=users[2]["headers"],
                    json={
                        "consultation_model": f"{provider}:{MODEL}",
                        "policy_version": configuration["policy_version"],
                        "cloud_processing_reviewed": True,
                    },
                )
                assert approved.status_code == 200 and approved.json()["consultation"]["available"], approved.text
                yield SimpleNamespace(
                    client=client, users=users, configuration=approved.json(), replay=replay, requests=requests
                )
        finally:
            try:
                await drain_requests(client, users[0]["headers"], requests)
                redis = await get_redis_client()
                async with pg_manager.get_async_session_context() as session:
                    run_ids = list(await session.scalars(select(AgentRun.id).where(AgentRun.request_id.in_(requests))))
                for run_id in run_ids:
                    await redis.delete(f"run:events:{run_id}")
                    assert not await redis.exists(f"run:events:{run_id}")
                if created:
                    restored = await client.put(
                        f"{ROOT}/configuration",
                        headers=users[2]["headers"],
                        json={
                            "consultation_model": original_model,
                            "policy_version": configuration["policy_version"],
                            "cloud_processing_reviewed": True,
                        },
                    )
                    assert restored.status_code == 200, restored.text
                    removed = await client.delete(
                        f"/api/system/model-providers/{provider}", headers=users[2]["headers"]
                    )
                    assert removed.status_code == 200, removed.text
            finally:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=5)
                assert process.poll() is not None
                await close_async_redis_client()

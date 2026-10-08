"""隔离实际API、Worker、SSE与PG证明独立体重更正和迟到发布拒绝。"""

import asyncio
import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select

from test.e2e.test_health_consultation_e2e import collect_sse, drain_requests, isolated_health, wait_until  # noqa: F401
from test.integration.services.test_health_vision_http import ROOT, health_http  # noqa: F401
from test.integration.services.test_health_weight_http import (
    add_weight,
    cleanup_weight_subject,
    correct_weight,
    create_weight_subject,
    read_weight,
)
from yuxi.services.health_family_profile_service import validate_profile_publication
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_business import AgentRun, AgentRunRequest, FamilyMeasurement, FamilyMember, Message
from yuxi.storage.postgres.models_health import HealthWeightUse
from yuxi.utils.datetime_utils import format_utc_datetime

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.e2e,
    pytest.mark.slow,
    pytest.mark.skipif(
        os.getenv("HEALTH_CONSULTATION_E2E_ISOLATED") != "true", reason="仅在禁止外联的隔离合成槽位运行"
    ),
]


@pytest_asyncio.fixture
async def weight_worker_subject(isolated_health):  # noqa: F811
    """仅临时审批本地回放，为真实Worker准备本人映射与独立用途同意。"""
    client, users, configuration, _ = isolated_health
    subject = await create_weight_subject(client, users)
    subject.requests = []
    consent = await client.post(
        f"{ROOT}/members/{subject.member_id}/processing-consents",
        headers=subject.headers,
        json={
            "purpose": "consultation",
            "accepted": True,
            "processor": configuration["consultation"]["processor"],
            "policy_version": configuration["policy_version"],
        },
    )
    assert consent.status_code == 200, consent.text
    try:
        yield subject
    finally:
        await drain_requests(client, subject.headers, subject.requests)
        await cleanup_weight_subject(subject)


async def test_weight_worker_correction_requires_fresh_consultation(weight_worker_subject):
    """两次实际工具读取60/v1与61/v2，旧daily、历史及结果不再公开。"""
    subject = weight_worker_subject
    measured = datetime.now(UTC).replace(microsecond=0) - timedelta(hours=1)
    record = await add_weight(subject, measured_at=measured)
    thread = await weight_thread(subject, daily=True)
    token = uuid4().hex
    first = await start_weight_run(subject, thread, token, "weight_read")
    await collect_sse(subject.client, subject.headers, first)
    before = await assert_weight_run(subject, first, 60, record["id"], 1)
    await correct_weight(subject, record["id"])
    await assert_old_weight_thread_denied(subject, thread, first)
    fresh = await weight_thread(subject)
    assert fresh != thread
    second = await start_weight_run(subject, fresh, token, "weight_updated")
    await collect_sse(subject.client, subject.headers, second)
    after = await assert_weight_run(subject, second, 61, record["id"], 2)
    assert before.payload_hash != after.payload_hash
    async with pg_manager.get_async_session_context() as session:
        source = await session.get(FamilyMember, subject.source_id)
        assert source.version == 1 and source.confirmed_version is None and source.profile == {}
        actual = await session.get(FamilyMeasurement, record["id"])
        assert actual.version == 2 and actual.values == {"weight": 61}
        assert actual.previous[0]["values"] == {"weight": 60}
        assert actual.measured_at == measured.replace(tzinfo=None) and actual.source == "synthetic-weight-scale"
    ordinary = await read_weight(subject)
    assert ordinary["records"][0]["unit"] == "kg"
    assert ordinary["records"][0]["measured_at"] == format_utc_datetime(measured)
    async with httpx.AsyncClient(base_url="http://localhost:8766", timeout=10) as replay:
        calls = (await replay.get("/observations", params={"token": token})).json()["calls"]
        assert calls == [
            {"step": step, "phase": phase, "record_ids": [record["id"]] if phase == "answer" else []}
            for step in ("weight_read", "weight_updated")
            for phase in ("read", "answer")
        ]


async def test_weight_worker_missing_use_blocks_old_gap_after_new_record(weight_worker_subject):
    """实际空集工具回执保存独立Use，新增测量后旧缺口不可沿用。"""
    subject = weight_worker_subject
    thread, token = await weight_thread(subject, daily=True), uuid4().hex
    run_id = await start_weight_run(subject, thread, token, "weight_missing")
    await collect_sse(subject.client, subject.headers, run_id)
    async with pg_manager.get_async_session_context() as session:
        run = await session.get(AgentRun, run_id)
        assert run.status == "completed", (run.error_type, run.error_message)
        message = await session.get(Message, run.output_message_id)
        assert message.content == "当前没有体重实测记录；请补充测量记录"
        uses = list((await session.scalars(select(HealthWeightUse).where(HealthWeightUse.run_id == run_id))).all())
        assert len(uses) == 1 and uses[0].member_id == subject.member_id
        assert uses[0].source_member_id == subject.source_id and uses[0].record_refs == []
    record = await add_weight(subject)
    await assert_old_weight_thread_denied(subject, thread, run_id)
    fresh = await weight_thread(subject)
    current = await start_weight_run(subject, fresh, token, "weight_read")
    await collect_sse(subject.client, subject.headers, current)
    await assert_weight_run(subject, current, 60, record["id"], 1)


@pytest.mark.parametrize("step", ["weight_gate", "weight_derived_gate"])
async def test_weight_worker_late_publication_rechecks_direct_and_derived_reads(weight_worker_subject, step):
    """更正发生在实际模型回包前，两种路径均无普通迟到输出。"""
    subject = weight_worker_subject
    record = await add_weight(subject)
    original = await weight_thread(subject, daily=True)
    token, gate_token = uuid4().hex, uuid4().hex
    first = await start_weight_run(subject, original, token, "weight_read")
    await collect_sse(subject.client, subject.headers, first)
    await assert_weight_run(subject, first, 60, record["id"], 1)
    gate_thread = await weight_thread(subject) if step == "weight_gate" else original
    pending = None
    async with httpx.AsyncClient(base_url="http://localhost:8766", timeout=10) as replay:
        try:
            gated = await start_weight_run(subject, gate_thread, gate_token, step)
            pending = asyncio.create_task(collect_sse(subject.client, subject.headers, gated))
            await wait_until(
                lambda: replay.get("/observations", params={"token": gate_token}),
                lambda response: any(call["phase"] == "answer" for call in response.json()["calls"]),
            )
            await correct_weight(subject, record["id"])
            assert (await replay.get("/release", params={"token": gate_token})).status_code == 200
            await asyncio.gather(pending, return_exceptions=True)
            pending = None

            async def terminal():
                """从PG owning行读取终态，不用SSE断流冒充拒绝成功。"""
                async with pg_manager.get_async_session_context() as session:
                    return (await session.get(AgentRun, gated)).status

            await wait_until(terminal, lambda status: status == "failed")
            async with pg_manager.get_async_session_context() as session:
                run = await session.get(AgentRun, gated)
                assert run.output_message_id is None
                assert run.error_type in {"unexpected_error", "output_persistence_error"}
                if run.error_type == "unexpected_error":
                    assert "weight_source_changed" in run.error_message
                assert not list(
                    (
                        await session.scalars(
                            select(Message).where(
                                Message.run_id == gated, Message.role == "assistant", Message.message_type == "text"
                            )
                        )
                    ).all()
                )
                with pytest.raises(HealthVisionError) as final_guard:
                    await validate_profile_publication(session, run)
                assert final_guard.value.code == "weight_source_changed" and final_guard.value.status == 410
                direct_uses = list(
                    (await session.scalars(select(HealthWeightUse).where(HealthWeightUse.run_id == gated))).all()
                )
                if step == "weight_gate":
                    assert len(direct_uses) == 1 and direct_uses[0].record_refs == [
                        {"record_id": record["id"], "version": 1}
                    ]
            calls = (await replay.get("/observations", params={"token": gate_token})).json()["calls"]
            assert [(call["step"], call["phase"]) for call in calls] == (
                [(step, "read"), (step, "answer")] if step == "weight_gate" else [(step, "answer")]
            )
            await assert_old_weight_thread_denied(subject, original, first)
            before = (await replay.get("/observations", params={"token": token})).json()["calls"]
            denied_key = str(uuid4())
            subject.requests.append(denied_key)
            rejected = await subject.client.post(
                "/api/agent/runs",
                headers=subject.headers,
                json={
                    "agent_slug": "health-consultation",
                    "thread_id": original,
                    "query": f"HEALTH_CONSULTATION_E2E:{token}:weight_read",
                    "meta": {"request_id": denied_key},
                },
            )
            assert rejected.status_code == 410, rejected.text
            assert "体重" in rejected.json()["detail"]
            assert (await replay.get("/observations", params={"token": token})).json()["calls"] == before
            async with pg_manager.get_async_session_context() as session:
                assert (
                    await session.scalar(select(AgentRunRequest).where(AgentRunRequest.request_id == denied_key))
                    is None
                )
        finally:
            await replay.get("/release", params={"token": gate_token})
            if pending is not None:
                await asyncio.gather(pending, return_exceptions=True)


async def weight_thread(subject, *, daily=False):
    """真实创建每日或明确新咨询，成员绑定由服务端拥有。"""
    key = str(uuid4())
    path = f"{ROOT}/members/{subject.member_id}/" + ("daily-consultations" if daily else "consultations")
    response = await subject.client.post(
        path,
        headers=subject.headers if daily else {**subject.headers, "Idempotency-Key": key},
        json=None if daily else {"client_request_id": key},
    )
    assert response.status_code == 201, response.text
    return response.json()["thread_id"]


async def start_weight_run(subject, thread, token, step):
    """仅提交固定合成文本，交真实队列和Worker执行。"""
    key = str(uuid4())
    subject.requests.append(key)
    response = await subject.client.post(
        "/api/agent/runs",
        headers=subject.headers,
        json={
            "agent_slug": "health-consultation",
            "thread_id": thread,
            "query": f"HEALTH_CONSULTATION_E2E:{token}:{step}",
            "meta": {"request_id": key},
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["run_id"]


async def assert_weight_run(subject, run_id, value, record_id, version, *, public=True):
    """普通结果、同Run消息和独立来源回执一起回读。"""
    expected = f"合成本人体重{value} kg；实测记录，不是确认档案或专业配餐依据"
    if public:
        result = await subject.client.get(f"/api/agent/runs/{run_id}/result", headers=subject.headers)
        assert result.status_code == 200 and result.json()["status"] == "completed", result.text
        assert result.json()["output"] == expected
    async with pg_manager.get_async_session_context() as session:
        run = await session.get(AgentRun, run_id)
        assert (
            run.status == "completed"
            and run.uid == subject.uid
            and run.worker_id is None
            and not run.runtime_cleanup_pending
        )
        message = await session.get(Message, run.output_message_id)
        assert message.run_id == run_id and message.role == "assistant" and message.content == expected
        uses = list((await session.scalars(select(HealthWeightUse).where(HealthWeightUse.run_id == run_id))).all())
        assert len(uses) == 1
        use = uses[0]
        assert use.member_id == subject.member_id and use.source_member_id == subject.source_id
        assert use.record_refs == [{"record_id": record_id, "version": version}]
        assert len(use.payload_hash) == 64 and use.end_date - use.start_date == timedelta(days=29)
        return use


async def assert_old_weight_thread_denied(subject, thread, run_id):
    """旧daily和历史拒绝复用，结果查询仍沿既有受保护错误契约。"""
    daily = await subject.client.post(
        f"{ROOT}/members/{subject.member_id}/daily-consultations", headers=subject.headers
    )
    assert daily.status_code == 410 and daily.json()["code"] == "weight_source_changed", daily.text
    assert (await subject.client.get(f"/api/chat/thread/{thread}/history", headers=subject.headers)).status_code == 404
    result = await subject.client.get(f"/api/agent/runs/{run_id}/result", headers=subject.headers)
    assert result.status_code == 200 and result.json()["error"]["type"] == "run_not_found"
    assert result.json()["output"] == ""

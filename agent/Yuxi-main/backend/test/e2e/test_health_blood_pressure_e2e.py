"""隔离真实API、Worker、checkpoint与PG验证本人成对血压实测来源。"""

import asyncio
import json
import os
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import delete, select

from test.e2e.test_health_consultation_e2e import collect_sse, drain_requests, isolated_health, wait_until  # noqa: F401
from test.integration.services.test_health_vision_http import ROOT, create_member, health_http  # noqa: F401
from test.integration.services.test_health_weight_http import cleanup_weight_subject
from yuxi.repositories.health_blood_pressure_repository import HealthBloodPressureRepository
from yuxi.services.health_family_profile_service import validate_profile_publication
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_business import AgentRun, AgentRunRequest, FamilyMeasurement, FamilyMember, Message
from yuxi.storage.postgres.models_health import (
    HealthBloodPressureUse,
    HealthConsultation,
    HealthFamilyProfileLink,
    HealthFamilyProfileUse,
    HealthWeightUse,
)
from yuxi.utils.datetime_utils import format_utc_datetime

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.e2e,
    pytest.mark.slow,
    pytest.mark.skipif(os.getenv("HEALTH_CONSULTATION_E2E_ISOLATED") != "true", reason="仅在隔离合成槽位运行"),
]


@pytest_asyncio.fixture
async def blood_pressure_subject(isolated_health):  # noqa: F811
    """临时审批仅本地回放，独立用途同意后交实际Worker运行。"""
    client, users, configuration, _ = isolated_health
    subject = await create_blood_pressure_subject(client, users)
    subject.requests = []
    try:
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
        yield subject
    finally:
        await drain_requests(client, subject.headers, subject.requests)
        await cleanup_blood_pressure_subject(subject)


async def test_blood_pressure_worker_preserves_pair_and_requires_fresh_consultation(blood_pressure_subject):
    """真实工具读取120/80→122/82，原时间来源不改，未确认档案不冒充就绪。"""
    subject = blood_pressure_subject
    measured = datetime.now(UTC).replace(microsecond=0) - timedelta(hours=1)
    record = await add_blood_pressure(subject, measured_at=measured)
    other = await subject.client.post(
        subject.measurement_path,
        headers=subject.headers,
        json={
            "id": str(uuid4()),
            "kind": "weight",
            "values": {"weight": 60},
            "measured_at": measured.isoformat(),
            "source": "synthetic-other-metric",
        },
    )
    assert other.status_code == 200
    old, token = await blood_pressure_thread(subject, daily=True), uuid4().hex
    first = await start_blood_pressure_run(subject, old, token, "bp_read")
    await collect_sse(subject.client, subject.headers, first)
    before = await assert_blood_pressure_run(subject, first, (120, 80), record["id"], 1)
    await correct_blood_pressure(subject, record["id"])
    await assert_old_blood_pressure_thread_denied(subject, old, first)
    fresh = await blood_pressure_thread(subject)
    assert fresh != old
    second = await start_blood_pressure_run(subject, fresh, token, "bp_updated")
    await collect_sse(subject.client, subject.headers, second)
    after = await assert_blood_pressure_run(subject, second, (122, 82), record["id"], 2)
    assert before.payload_hash != after.payload_hash
    async with pg_manager.get_async_session_context() as session:
        actual = await session.get(FamilyMeasurement, record["id"])
        assert actual.values == {"systolic": 122, "diastolic": 82} and actual.version == 2
        assert actual.previous[0]["values"] == {"systolic": 120, "diastolic": 80}
        assert (
            actual.measured_at == measured.replace(tzinfo=None) and actual.source == "synthetic-blood-pressure-device"
        )
        source = await session.get(FamilyMember, subject.source_id)
        assert source.version == 1 and source.confirmed_version is None and source.profile == {}
        for model in (HealthWeightUse, HealthFamilyProfileUse):
            assert await session.scalar(select(model).where(model.run_id.in_([first, second]))) is None
    payload = await read_blood_pressure(subject)
    assert payload["records"] == [
        {
            "record_id": record["id"],
            "systolic": 122,
            "diastolic": 82,
            "unit": "mmHg",
            "measured_at": format_utc_datetime(measured),
            "source": "synthetic-blood-pressure-device",
            "version": 2,
        }
    ]
    async with httpx.AsyncClient(base_url="http://localhost:8766", timeout=10) as replay:
        assert (await replay.get("/observations", params={"token": token})).json()["calls"] == [
            {"step": step, "phase": phase, "record_ids": [record["id"]] if phase == "answer" else []}
            for step in ("bp_read", "bp_updated")
            for phase in ("read", "answer")
        ]


@pytest.mark.parametrize("linked", [True, False])
async def test_blood_pressure_empty_or_unlinked_use_blocks_old_gap_after_source_changes(blood_pressure_subject, linked):
    """两类实际缺口均保存Use，新增记录或关联后旧daily、历史与结果失效。"""
    subject = blood_pressure_subject
    if not linked:
        async with pg_manager.get_async_session_context() as session:
            await session.execute(
                delete(HealthFamilyProfileLink).where(HealthFamilyProfileLink.member_id == subject.member_id)
            )
    thread, token = await blood_pressure_thread(subject, daily=True), uuid4().hex
    step = "bp_missing" if linked else "bp_not_linked"
    first = await start_blood_pressure_run(subject, thread, token, step)
    await collect_sse(subject.client, subject.headers, first)
    async with pg_manager.get_async_session_context() as session:
        run = await session.get(AgentRun, first)
        assert run.status == "completed", (run.error_type, run.error_message)
        message = await session.get(Message, run.output_message_id)
        assert message.content == (
            "当前没有血压实测记录；请补充成对测量记录" if linked else "当前未关联本人血压来源；请明确关联本人档案"
        )
        uses = list(
            (await session.scalars(select(HealthBloodPressureUse).where(HealthBloodPressureUse.run_id == first))).all()
        )
        assert len(uses) == 1 and uses[0].record_refs == [] and uses[0].member_id == subject.member_id
        assert uses[0].source_member_id == (subject.source_id if linked else None)
    if not linked:
        await link_blood_pressure_subject(subject)
    record = await add_blood_pressure(subject)
    await assert_old_blood_pressure_thread_denied(subject, thread, first)
    fresh = await blood_pressure_thread(subject)
    second = await start_blood_pressure_run(subject, fresh, token, "bp_read")
    await collect_sse(subject.client, subject.headers, second)
    await assert_blood_pressure_run(subject, second, (120, 80), record["id"], 1)


@pytest.mark.parametrize("step", ["bp_gate", "bp_derived_gate"])
async def test_blood_pressure_late_direct_and_derived_publication_has_no_ordinary_output(blood_pressure_subject, step):
    """实际模型回包前更正，两种来源路径都在PG失败且没有普通迟到回答。"""
    subject = blood_pressure_subject
    record = await add_blood_pressure(subject)
    original, token = await blood_pressure_thread(subject, daily=True), uuid4().hex
    first = await start_blood_pressure_run(subject, original, token, "bp_read")
    await collect_sse(subject.client, subject.headers, first)
    await assert_blood_pressure_run(subject, first, (120, 80), record["id"], 1)
    thread = await blood_pressure_thread(subject) if step == "bp_gate" else original
    gate_token, pending = uuid4().hex, None
    async with httpx.AsyncClient(base_url="http://localhost:8766", timeout=10) as replay:
        try:
            gated = await start_blood_pressure_run(subject, thread, gate_token, step)
            pending = asyncio.create_task(collect_sse(subject.client, subject.headers, gated))
            await wait_until(
                lambda: replay.get("/observations", params={"token": gate_token}),
                lambda response: any(call["phase"] == "answer" for call in response.json()["calls"]),
            )
            await correct_blood_pressure(subject, record["id"])
            assert (await replay.get("/release", params={"token": gate_token})).status_code == 200
            await asyncio.gather(pending, return_exceptions=True)
            pending = None

            async def terminal():
                """只用 owning Run 行证明失败，SSE断流不构成通过证据。"""
                async with pg_manager.get_async_session_context() as session:
                    return (await session.get(AgentRun, gated)).status

            await wait_until(terminal, lambda status: status == "failed")
            async with pg_manager.get_async_session_context() as session:
                run = await session.get(AgentRun, gated)
                assert run.output_message_id is None and run.error_type in {
                    "unexpected_error",
                    "output_persistence_error",
                }
                if run.error_type == "unexpected_error":
                    assert "blood_pressure_source_changed" in run.error_message
                assert not list(
                    (
                        await session.scalars(
                            select(Message).where(
                                Message.run_id == gated, Message.role == "assistant", Message.message_type == "text"
                            )
                        )
                    ).all()
                )
                with pytest.raises(HealthVisionError) as guard:
                    await validate_profile_publication(session, run)
                assert guard.value.code == "blood_pressure_source_changed" and guard.value.status == 410
                uses = list(
                    (
                        await session.scalars(
                            select(HealthBloodPressureUse).where(HealthBloodPressureUse.run_id == gated)
                        )
                    ).all()
                )
                if step == "bp_gate":
                    assert len(uses) == 1 and uses[0].record_refs == [{"record_id": record["id"], "version": 1}]
            calls = (await replay.get("/observations", params={"token": gate_token})).json()["calls"]
            assert [(call["step"], call["phase"]) for call in calls] == (
                [(step, "read"), (step, "answer")] if step == "bp_gate" else [(step, "answer")]
            )
            await assert_old_blood_pressure_thread_denied(subject, original, first)
            before = (await replay.get("/observations", params={"token": token})).json()["calls"]
            key = str(uuid4())
            rejected = await submit_blood_pressure_request(subject, original, token, "bp_read", request_id=key)
            assert rejected.status_code == 410, rejected.text
            assert (await replay.get("/observations", params={"token": token})).json()["calls"] == before
            async with pg_manager.get_async_session_context() as session:
                assert await session.scalar(select(AgentRunRequest).where(AgentRunRequest.request_id == key)) is None
        finally:
            await replay.get("/release", params={"token": gate_token})
            if pending is not None:
                await asyncio.gather(pending, return_exceptions=True)


async def test_blood_pressure_real_checkpoint_rejects_same_python_value_with_changed_json_type(blood_pressure_subject):
    """实际Worker checkpoint与PG回执一致后，保留摘要的类型替换也必须拒绝。"""
    subject = blood_pressure_subject
    record = await add_blood_pressure(subject)
    thread, token = await blood_pressure_thread(subject), uuid4().hex
    run_id = await start_blood_pressure_run(subject, thread, token, "bp_read")
    await collect_sse(subject.client, subject.headers, run_id)
    await assert_blood_pressure_run(subject, run_id, (120, 80), record["id"], 1)
    checkpoint = await pg_manager.get_langgraph_checkpointer().aget_tuple({"configurable": {"thread_id": thread}})
    assert checkpoint is not None
    tools = [
        message
        for message in checkpoint.checkpoint["channel_values"]["messages"]
        if getattr(message, "name", None) == "get_member_blood_pressure_records"
    ]
    assert len(tools) == 1
    payload = json.loads(tools[0].content)
    assert type(payload["records"][0]["systolic"]) is float
    async with pg_manager.get_async_session_context() as session:
        run = await session.get(AgentRun, run_id)
        binding = await session.get(HealthConsultation, run.conversation_id)
        repo = HealthBloodPressureRepository(session)
        await repo.validate_tool_payload(subject.uid, binding, payload)
        for case in ("bool_version", "integer_systolic", "float_limit", "integer_flag"):
            forged = json.loads(json.dumps(payload))
            if case == "bool_version":
                forged["records"][0]["version"] = True
            elif case == "integer_systolic":
                forged["records"][0]["systolic"] = int(forged["records"][0]["systolic"])
            elif case == "float_limit":
                forged["limit"] = 20.0
            else:
                forged["nutrition_safety_ready"] = 0
            assert forged == payload and json.dumps(forged) != json.dumps(payload)
            with pytest.raises(HealthVisionError) as denied:
                await repo.validate_tool_payload(subject.uid, binding, forged)
            assert denied.value.code == "blood_pressure_source_changed" and denied.value.status == 410
        wrong = SimpleNamespace(conversation_id=-1, member_id=subject.member_id, actor_uid=subject.uid)
        with pytest.raises(HealthVisionError) as crossed:
            await repo.validate_tool_payload(subject.uid, wrong, payload)
        assert crossed.value.status == 410


async def test_blood_pressure_revoked_health_access_blocks_history_and_next_outbound(blood_pressure_subject):
    """真实读取后撤回profile_view，旧来源与后续外呼都被拒绝。"""
    subject = blood_pressure_subject
    record = await add_blood_pressure(subject)
    thread, token = await blood_pressure_thread(subject, daily=True), uuid4().hex
    first = await start_blood_pressure_run(subject, thread, token, "bp_read")
    await collect_sse(subject.client, subject.headers, first)
    await assert_blood_pressure_run(subject, first, (120, 80), record["id"], 1)
    revoked = await subject.client.put(
        f"{ROOT}/members/{subject.member_id}/grants",
        headers=subject.headers,
        json={"actor_uid": subject.uid, "scopes": ["ai_use", "report_view", "diet_edit"]},
    )
    assert revoked.status_code == 200
    assert (
        await subject.client.get(f"{ROOT}/members/{subject.member_id}/blood-pressure-records", headers=subject.headers)
    ).status_code == 404
    async with pg_manager.get_async_session_context() as session:
        run = await session.get(AgentRun, first)
        binding = await session.get(HealthConsultation, run.conversation_id)
        with pytest.raises(HealthVisionError) as changed:
            await HealthBloodPressureRepository(session).validate_history(subject.uid, binding)
        assert changed.value.code == "blood_pressure_source_changed" and changed.value.status == 410
    async with httpx.AsyncClient(base_url="http://localhost:8766", timeout=10) as replay:
        before = (await replay.get("/observations", params={"token": token})).json()["calls"]
        rejected = await submit_blood_pressure_request(subject, thread, token, "bp_read")
        assert rejected.status_code == 410, rejected.text
        assert (await replay.get("/observations", params={"token": token})).json()["calls"] == before
    assert (await subject.client.get(f"/api/chat/thread/{thread}/history", headers=subject.headers)).status_code == 404


async def test_blood_pressure_ordinary_read_needs_no_model_consent_but_outbound_does(isolated_health):  # noqa: F811
    """普通接口保留配对字段，他人grant不代理本人，未同意的Run不持久化或外呼。"""
    client, users, _, _ = isolated_health
    subject = await create_blood_pressure_subject(client, users)
    subject.requests = []
    try:
        await add_blood_pressure(subject)
        payload = await read_blood_pressure(subject)
        assert payload["status"] == "ready" and payload["records"][0]["unit"] == "mmHg"
        assert payload["full_health_profile_available"] is payload["nutrition_safety_ready"] is False
        for actor in users[1:]:
            granted = await client.put(
                f"{ROOT}/members/{subject.member_id}/grants",
                headers=subject.headers,
                json={"actor_uid": actor["uid"], "scopes": ["profile_view", "ai_use", "profile_edit"]},
            )
            assert granted.status_code == 200
            assert (
                await client.get(f"{ROOT}/members/{subject.member_id}/blood-pressure-records", headers=actor["headers"])
            ).status_code == 404
        thread, token = await blood_pressure_thread(subject), uuid4().hex
        key = str(uuid4())
        rejected = await submit_blood_pressure_request(subject, thread, token, "bp_read", request_id=key)
        assert rejected.status_code == 403 and "同意" in rejected.json()["detail"], rejected.text
        async with httpx.AsyncClient(base_url="http://localhost:8766", timeout=10) as replay:
            assert (await replay.get("/observations", params={"token": token})).json()["calls"] == []
        async with pg_manager.get_async_session_context() as session:
            assert await session.scalar(select(AgentRunRequest).where(AgentRunRequest.request_id == key)) is None
            assert (
                await session.scalar(
                    select(HealthBloodPressureUse).where(HealthBloodPressureUse.member_id == subject.member_id)
                )
                is None
            )
    finally:
        await drain_requests(client, subject.headers, subject.requests)
        await cleanup_blood_pressure_subject(subject)


async def create_blood_pressure_subject(client, users):
    """正式接口创建合成健康本人及空档案来源，明确关联但不确认档案。"""
    headers, uid = users[0]["headers"], users[0]["uid"]
    member_id = await create_member(client, headers)
    created = await client.post("/api/family", headers=headers, json={"name": "合成本人血压测试家庭"})
    assert created.status_code == 200, created.text
    family_id = created.json()["id"]
    source_id = next(row["id"] for row in created.json()["members"] if row["is_self"])
    subject = SimpleNamespace(
        client=client,
        users=users,
        headers=headers,
        uid=uid,
        member_id=member_id,
        family_id=family_id,
        source_id=source_id,
        measurement_path=f"/api/family/{family_id}/members/{source_id}/measurements",
    )
    await link_blood_pressure_subject(subject)
    return subject


async def link_blood_pressure_subject(subject):
    """关联身份与实测读取独立于基础档案确认。"""
    response = await subject.client.post(
        f"{ROOT}/members/{subject.member_id}/family-profile-link",
        headers=subject.headers,
        json={"family_id": subject.family_id, "source_member_id": subject.source_id, "confirmed_identity": True},
    )
    assert response.status_code == 200, response.text


async def add_blood_pressure(subject, *, measured_at=None):
    """创建成对原始实测，条件和备注只在家庭域保留。"""
    measured_at = measured_at or datetime.now(UTC).replace(microsecond=0) - timedelta(hours=1)
    response = await subject.client.post(
        subject.measurement_path,
        headers=subject.headers,
        json={
            "id": str(uuid4()),
            "kind": "blood_pressure",
            "values": {"systolic": 120, "diastolic": 80},
            "measured_at": measured_at.isoformat(),
            "source": "synthetic-blood-pressure-device",
            "condition": "不得外发的合成测量条件",
            "note": "不得外发的合成血压备注",
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


async def correct_blood_pressure(subject, record_id):
    """真实更正两项值并保留原记录身份、时间与来源。"""
    response = await subject.client.put(
        subject.measurement_path + "/" + record_id,
        headers=subject.headers,
        json={
            "expected_version": 1,
            "values": {"systolic": 122, "diastolic": 82},
            "note": "合成配对测量更正，不作专业判断",
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


async def read_blood_pressure(subject):
    """只经普通HTTP读取当前配对投影，验证禁止缓存。"""
    response = await subject.client.get(
        f"{ROOT}/members/{subject.member_id}/blood-pressure-records", headers=subject.headers
    )
    assert response.status_code == 200 and response.headers["Cache-Control"] == "no-store", response.text
    payload = response.json()
    assert set(payload) == {
        "status",
        "code",
        "owner",
        "member_id",
        "source_member_id",
        "period",
        "limit",
        "records",
        "truncated",
        "full_health_profile_available",
        "nutrition_safety_ready",
        "source_hash",
    }
    assert all(
        set(row) == {"record_id", "systolic", "diastolic", "unit", "measured_at", "source", "version"}
        for row in payload["records"]
    )
    return payload


async def blood_pressure_thread(subject, *, daily=False):
    """服务端固定本人绑定，明确新建与每日入口使用不同的稳定请求键。"""
    key = str(uuid4())
    response = await subject.client.post(
        f"{ROOT}/members/{subject.member_id}/" + ("daily-consultations" if daily else "consultations"),
        headers=subject.headers if daily else {**subject.headers, "Idempotency-Key": key},
        json=None if daily else {"client_request_id": key},
    )
    assert response.status_code == 201, response.text
    return response.json()["thread_id"]


async def start_blood_pressure_run(subject, thread, token, step):
    """提交固定合成请求，输出必须来自实际队列和Worker。"""
    response = await submit_blood_pressure_request(subject, thread, token, step)
    assert response.status_code == 200, response.text
    return response.json()["run_id"]


async def submit_blood_pressure_request(subject, thread, token, step, *, request_id=None):
    """记录本轮请求便于终态清理，不把拒绝请求当成Run。"""
    key = request_id or str(uuid4())
    subject.requests.append(key)
    return await subject.client.post(
        "/api/agent/runs",
        headers=subject.headers,
        json={
            "agent_slug": "health-consultation",
            "thread_id": thread,
            "query": f"HEALTH_CONSULTATION_E2E:{token}:{step}",
            "meta": {"request_id": key},
        },
    )


async def assert_blood_pressure_run(subject, run_id, pair, record_id, version, *, public=True):
    """同Run终态、普通消息与独立引用回执共同证明实际读取。"""
    expected = f"合成本人血压{pair[0]}/{pair[1]} mmHg；实测记录，不作为临床诊断或专业配餐依据"
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
        uses = list(
            (await session.scalars(select(HealthBloodPressureUse).where(HealthBloodPressureUse.run_id == run_id))).all()
        )
        assert len(uses) == 1
        use = uses[0]
        assert use.member_id == subject.member_id and use.source_member_id == subject.source_id
        assert use.record_refs == [{"record_id": record_id, "version": version}]
        assert len(use.payload_hash) == 64 and use.end_date - use.start_date == timedelta(days=29)
        return use


async def assert_old_blood_pressure_thread_denied(subject, thread, run_id):
    """来源更正后的每日、历史与公开结果各自守住读取边界。"""
    daily = await subject.client.post(
        f"{ROOT}/members/{subject.member_id}/daily-consultations", headers=subject.headers
    )
    assert daily.status_code == 410 and daily.json()["code"] == "blood_pressure_source_changed", daily.text
    assert (await subject.client.get(f"/api/chat/thread/{thread}/history", headers=subject.headers)).status_code == 404
    result = await subject.client.get(f"/api/agent/runs/{run_id}/result", headers=subject.headers)
    assert (
        result.status_code == 200
        and result.json()["error"]["type"] == "run_not_found"
        and result.json()["output"] == ""
    )


async def cleanup_blood_pressure_subject(subject):
    """先删本轮血压与档案依赖，再交既有精确家庭清理；账号归isolated fixture。"""
    async with pg_manager.get_async_session_context() as session:
        await session.execute(
            delete(HealthBloodPressureUse).where(HealthBloodPressureUse.member_id == subject.member_id)
        )
        await session.execute(
            delete(HealthFamilyProfileUse).where(HealthFamilyProfileUse.member_id == subject.member_id)
        )
    await cleanup_weight_subject(subject)

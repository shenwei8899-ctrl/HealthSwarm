"""真实浏览器录入、更正实测体重的隔离夹具及独立PG验收。"""

import asyncio
import hashlib
import json
import os
from pathlib import Path
from uuid import NAMESPACE_URL, uuid4, uuid5

import httpx
import pytest
from sqlalchemy import select

from test.e2e.test_health_consultation_e2e import drain_requests, isolated_health  # noqa: F401
from test.e2e.test_health_family_profile_ui import write_control
from test.e2e.test_health_weight_e2e import assert_old_weight_thread_denied, assert_weight_run
from test.integration.services.test_health_vision_http import ROOT, health_http  # noqa: F401
from test.integration.services.test_health_weight_http import cleanup_weight_subject, create_weight_subject, read_weight
from yuxi.services.health_daily_service import business_date
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_business import (
    AgentRun,
    AgentRunRequest,
    Conversation,
    FamilyMeasurement,
    FamilyMember,
)
from yuxi.storage.postgres.models_business import Message
from yuxi.storage.postgres.models_health import (
    HealthConsultation,
    HealthDailyConversation,
    HealthFamilyProfileLink,
    HealthFamilyProfileUse,
    HealthProcessingConsent,
)
from yuxi.utils.datetime_utils import format_utc_datetime

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.e2e,
    pytest.mark.slow,
    pytest.mark.skipif(os.getenv("HEALTH_CONSULTATION_E2E_ISOLATED") != "true", reason="仅在隔离合成槽位运行"),
    pytest.mark.skipif(not os.getenv("HEALTH_WEIGHT_UI_CONTROL_DIR"), reason="需要真实浏览器验收控制目录"),
]


async def test_browser_weight_measurement_correction_and_fresh_consultation(isolated_health):  # noqa: F811
    """只准备空本人映射，真实表单与实际Worker完成后才生成验收通过回执。"""
    client, users, _, _ = isolated_health
    control = Path(os.environ["HEALTH_WEIGHT_UI_CONTROL_DIR"])
    control.mkdir(parents=True, exist_ok=True)
    assert not any(
        (control / name).exists() for name in ("context.json", "done.json", "failure.json", "verified.json")
    ), "UI控制目录必须为本轮新建的空目录"
    subject = await create_weight_subject(client, users)
    token = uuid4().hex
    try:
        async with pg_manager.get_async_session_context() as session:
            source = await session.get(FamilyMember, subject.source_id)
            assert source.version == 1 and source.confirmed_version is None and source.profile == {}
            assert not list(
                (await session.scalars(select(FamilyMeasurement).where(FamilyMeasurement.member_id == source.id))).all()
            )
            assert (
                await session.scalar(
                    select(HealthProcessingConsent).where(HealthProcessingConsent.member_id == subject.member_id)
                )
                is None
            )
        write_control(
            control / "context.json",
            {
                "access_token": subject.headers["Authorization"].removeprefix("Bearer "),
                "health_member_id": subject.member_id,
                "family_id": subject.family_id,
                "source_id": subject.source_id,
                "replay_token": token,
                "uid": subject.uid,
            },
        )
        receipt = await wait_for_weight_browser(control)
        assert isinstance(receipt, dict) and set(receipt) == {
            "old_thread",
            "new_thread",
            "old_run_id",
            "new_run_id",
            "record_id",
        }, "浏览器回执字段不符合体重验收协议"
        old_thread, new_thread = receipt["old_thread"], receipt["new_thread"]
        old_run, new_run, record_id = receipt["old_run_id"], receipt["new_run_id"], receipt["record_id"]
        assert old_thread != new_thread and old_run != new_run
        old_use = await assert_weight_run(subject, old_run, 60, record_id, 1, public=False)
        new_use = await assert_weight_run(subject, new_run, 61, record_id, 2)
        assert old_use.payload_hash != new_use.payload_hash
        async with pg_manager.get_async_session_context() as session:
            source = await session.get(FamilyMember, subject.source_id)
            assert source.version == 1 and source.confirmed_version is None and source.profile == {}
            records = list(
                (await session.scalars(select(FamilyMeasurement).where(FamilyMeasurement.member_id == source.id))).all()
            )
            assert len(records) == 1
            record = records[0]
            assert record.id == record_id and record.kind == "weight" and record.values == {"weight": 61}
            assert record.version == 2 and record.source == "device" and record.created_by == subject.uid
            assert len(record.previous) == 1
            assert record.previous[0]["version"] == 1 and record.previous[0]["values"] == {"weight": 60}
            old_value, current_value = record.previous[0]["values"]["weight"], record.values["weight"]
            assert old_value == 60 and current_value == 61
            original_time = format_utc_datetime(record.measured_at)
            assert original_time.endswith("Z") and record.creation_intent["measured_at"] == original_time
            assert record.creation_intent["values"] == {"weight": 60} and record.creation_intent["source"] == "device"
            links = list(
                (
                    await session.scalars(
                        select(HealthFamilyProfileLink).where(HealthFamilyProfileLink.actor_uid == subject.uid)
                    )
                ).all()
            )
            assert len(links) == 1 and links[0].source_member_id == subject.source_id
            bindings = list(
                (
                    await session.scalars(select(HealthConsultation).where(HealthConsultation.actor_uid == subject.uid))
                ).all()
            )
            assert len(bindings) == 2
            by_thread = {
                (await session.get(Conversation, binding.conversation_id)).thread_id: binding for binding in bindings
            }
            assert set(by_thread) == {old_thread, new_thread}
            daily_key = str(
                uuid5(NAMESPACE_URL, f"health-daily:{subject.uid}:{subject.member_id}:{business_date().isoformat()}")
            )
            assert by_thread[old_thread].request_id == daily_key
            daily = await session.get(HealthDailyConversation, by_thread[old_thread].conversation_id)
            assert daily is not None and daily.business_date == business_date()
            assert await session.get(HealthDailyConversation, by_thread[new_thread].conversation_id) is None
            for run_id, thread, step in ((old_run, old_thread, "weight_read"), (new_run, new_thread, "weight_updated")):
                run = await session.get(AgentRun, run_id)
                assert run.conversation_id == by_thread[thread].conversation_id
                query = await session.scalar(
                    select(Message).where(Message.request_id == run.request_id, Message.role == "user")
                )
                assert query.content == f"HEALTH_CONSULTATION_E2E:{token}:{step}"
                assert (
                    await session.scalar(select(HealthFamilyProfileUse).where(HealthFamilyProfileUse.run_id == run_id))
                    is None
                )
        payload = await read_weight(subject)
        assert payload["records"] == [
            {
                "record_id": record_id,
                "value": 61,
                "unit": "kg",
                "measured_at": original_time,
                "source": "device",
                "version": 2,
            }
        ]
        for use, value, version in ((old_use, old_value, 1), (new_use, current_value, 2)):
            frozen = json.loads(json.dumps(payload))
            frozen["period"]["start_date"] = use.start_date.isoformat()
            frozen["period"]["end_date"] = use.end_date.isoformat()
            frozen["records"][0].update(value=value, version=version)
            frozen.pop("source_hash")
            assert (
                use.payload_hash
                == hashlib.sha256(
                    json.dumps(frozen, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
                ).hexdigest()
            )
        await assert_old_weight_thread_denied(subject, old_thread, old_run)
        async with httpx.AsyncClient(base_url="http://localhost:8766", timeout=10) as replay:
            observed = await replay.get("/observations", params={"token": token})
            assert observed.status_code == 200
            assert observed.json()["calls"] == [
                {"step": step, "phase": phase, "record_ids": [record_id] if phase == "answer" else []}
                for step in ("weight_read", "weight_updated")
                for phase in ("read", "answer")
            ]
        write_control(
            control / "verified.json", {"status": "passed", **receipt, "versions": [1, 2], "source": "device"}
        )
    finally:
        async with pg_manager.get_async_session_context() as session:
            requests = list(
                (
                    await session.scalars(select(AgentRunRequest.request_id).where(AgentRunRequest.uid == subject.uid))
                ).all()
            )
        await drain_requests(client, subject.headers, requests)
        await cleanup_weight_subject(subject)


async def wait_for_weight_browser(control):
    """只读取完成或失败信号，600秒后失败且不输出token或健康正文。"""
    try:
        async with asyncio.timeout(600):
            while True:
                if (control / "failure.json").exists():
                    pytest.fail("真实体重浏览器验收失败，请检查本地报告")
                done = control / "done.json"
                if done.exists():
                    return json.loads(done.read_text(encoding="utf-8"))
                await asyncio.sleep(1)
    except TimeoutError:
        pytest.fail("真实体重浏览器验收回执超时；未形成通过证据")

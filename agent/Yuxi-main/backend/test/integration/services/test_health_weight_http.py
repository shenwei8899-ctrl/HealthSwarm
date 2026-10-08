"""真实JWT、HTTP及PG验证本人实测体重和独立版本依赖。"""

import asyncio
import hashlib
import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
import pytest_asyncio
from sqlalchemy import delete, select, text

from test.integration.services.test_health_vision_http import ROOT, create_member, health_http  # noqa: F401
from yuxi.repositories.health_weight_repository import HealthWeightRepository
from yuxi.services.family_schemas import MeasurementUpdate
from yuxi.services.family_service import FamilyService
from yuxi.services.health_daily_service import business_date
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_business import (
    AgentRun,
    Conversation,
    FamilyArchive,
    FamilyAudit,
    FamilyMeasurement,
    FamilyMember,
    FamilyProfileRevision,
    Project,
)
from yuxi.storage.postgres.models_health import (
    HealthConsultation,
    HealthFamilyProfileLink,
    HealthProcessingConsent,
    HealthWeightUse,
)
from yuxi.utils.datetime_utils import format_utc_datetime

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest_asyncio.fixture
async def weight_subject(health_http):  # noqa: F811
    """只准备本轮合成成员及明确本人映射，精确清理正式家庭资源。"""
    client, users = health_http
    subject = await create_weight_subject(client, users)
    try:
        yield subject
    finally:
        await cleanup_weight_subject(subject)


async def test_weight_read_distinguishes_unlinked_missing_and_independent_measurement(health_http):  # noqa: F811
    """普通读取不签模型同意，空档案也可读取独立实测并明确缺口。"""
    client, users = health_http
    member_id = await create_member(client, users[0]["headers"])
    response = await client.get(f"{ROOT}/members/{member_id}/weight-records", headers=users[0]["headers"])
    assert response.status_code == 200 and response.headers["Cache-Control"] == "no-store", response.text
    empty = response.json()
    assert empty["status"] == "not_ready" and empty["code"] == "weight_not_linked"
    assert empty["source_member_id"] is None and empty["records"] == []
    subject = await create_weight_subject(client, users, member_id=member_id)
    try:
        missing = await read_weight(subject)
        assert missing["status"] == "not_ready" and missing["code"] == "weight_missing" and missing["records"] == []
        assert missing["source_member_id"] == subject.source_id
        expected_period = {
            "start_date": (business_date() - timedelta(days=29)).isoformat(),
            "end_date": business_date().isoformat(),
            "timezone": "Asia/Shanghai",
        }
        assert missing["period"] == expected_period
        measured = datetime.now(UTC).replace(microsecond=0) - timedelta(hours=1)
        record = await add_weight(subject, measured_at=measured)
        payload = await read_weight(subject)
        assert payload["status"] == "ready" and payload["code"] == "self_weight_records"
        assert payload["records"] == [
            {
                "record_id": record["id"],
                "value": 60,
                "unit": "kg",
                "measured_at": format_utc_datetime(measured),
                "source": "synthetic-weight-scale",
                "version": 1,
            }
        ]
        assert payload["period"] == expected_period and payload["limit"] == 20 and payload["truncated"] is False
        assert payload["full_health_profile_available"] is False and payload["nutrition_safety_ready"] is False
        assert "profile" not in payload and "confirmed_version" not in payload
        assert set(payload["records"][0]) == {"record_id", "value", "unit", "measured_at", "source", "version"}
        assert (
            payload["source_hash"]
            == hashlib.sha256(
                json.dumps(
                    {key: value for key, value in payload.items() if key != "source_hash"},
                    sort_keys=True,
                    ensure_ascii=False,
                    separators=(",", ":"),
                ).encode()
            ).hexdigest()
        )
        async with pg_manager.get_async_session_context() as session:
            source = await session.get(FamilyMember, subject.source_id)
            assert source.version == 1 and source.confirmed_version is None and source.profile == {}
            assert (
                await session.scalar(
                    select(HealthProcessingConsent).where(HealthProcessingConsent.member_id == member_id)
                )
                is None
            )
            assert await session.scalar(select(HealthWeightUse).where(HealthWeightUse.member_id == member_id)) is None
    finally:
        await cleanup_weight_subject(subject)


async def test_weight_correction_keeps_time_source_and_profile_version(weight_subject):
    """真实更正只推进测量版本，旧值保留且不会变成档案确认。"""
    subject = weight_subject
    measured = datetime.now(UTC).replace(microsecond=0) - timedelta(hours=1)
    record = await add_weight(subject, measured_at=measured)
    before = await read_weight(subject)
    corrected = await correct_weight(subject, record["id"])
    assert corrected["version"] == 2 and corrected["previous"][0]["values"] == {"weight": 60}
    after = await read_weight(subject)
    assert after["source_hash"] != before["source_hash"]
    assert after["records"] == [
        {
            "record_id": record["id"],
            "value": 61,
            "unit": "kg",
            "measured_at": format_utc_datetime(measured),
            "source": "synthetic-weight-scale",
            "version": 2,
        }
    ]
    async with pg_manager.get_async_session_context() as session:
        persisted = await session.get(FamilyMeasurement, record["id"])
        assert persisted.values == {"weight": 61} and persisted.version == 2
        assert persisted.measured_at == measured.replace(tzinfo=None) and persisted.source == "synthetic-weight-scale"
        assert persisted.previous[0]["values"] == {"weight": 60}
        source = await session.get(FamilyMember, subject.source_id)
        assert source.version == 1 and source.confirmed_version is None
    stale = await subject.client.put(
        subject.measurement_path + "/" + record["id"],
        headers=subject.headers,
        json={"expected_version": 1, "values": {"weight": 62}, "note": "合成旧版本更正"},
    )
    assert stale.status_code == 409


async def test_voided_weight_is_excluded_and_invalidates_recorded_history(weight_subject):
    """正式作废保留原始事实，普通读取与旧模型依赖均不可再使用。"""
    subject = weight_subject
    record = await add_weight(subject)
    binding, payload, _ = await record_weight_use(subject)
    response = await subject.client.post(
        subject.measurement_path + "/" + record["id"] + "/void",
        headers=subject.headers,
        json={"expected_version": 1, "reason": "合成测试：误录作废"},
    )
    assert response.status_code == 200, response.text
    current = await read_weight(subject)
    assert current["records"] == [] and current["code"] == "weight_missing"
    assert current["truncated"] is False and current["source_hash"] != payload["source_hash"]
    async with pg_manager.get_async_session_context() as session:
        persisted = await session.get(FamilyMeasurement, record["id"])
        assert persisted.voided_at is not None and persisted.values == {"weight": 60} and persisted.version == 2
        with pytest.raises(HealthVisionError) as changed:
            await HealthWeightRepository(session).validate_history(subject.uid, binding)
        assert changed.value.code == "weight_source_changed" and changed.value.status == 410
        with pytest.raises(HealthVisionError) as stale:
            await HealthWeightRepository(session).validate_tool_payload(subject.uid, binding, payload)
        assert stale.value.status == 410


async def test_weight_period_filters_other_metrics_caps_twenty_and_orders_stably(weight_subject):
    """独立30自然日边界排除前一天及其他指标，最多20条并明确截断。"""
    subject = weight_subject
    start = business_date() - timedelta(days=29)
    boundary = datetime.combine(start, datetime.min.time(), ZoneInfo("Asia/Shanghai"))
    older = await add_weight(subject, value=90, measured_at=boundary - timedelta(seconds=1))
    included = await add_weight(subject, value=59, measured_at=boundary)
    boundary_result = await read_weight(subject)
    assert boundary_result["truncated"] is False
    assert [row["record_id"] for row in boundary_result["records"]] == [included["id"]]
    now = datetime.now(UTC).replace(microsecond=0) - timedelta(hours=1)
    ids = []
    for index in range(21):
        row = await add_weight(subject, value=60 + index / 10, measured_at=now)
        ids.append(row["id"])
    other = await subject.client.post(
        subject.measurement_path,
        headers=subject.headers,
        json={
            "id": str(uuid4()),
            "kind": "blood_pressure",
            "values": {"systolic": 120, "diastolic": 80},
            "measured_at": now.isoformat(),
            "source": "synthetic-other-metric",
        },
    )
    assert other.status_code == 200
    result = await read_weight(subject)
    assert result["truncated"] is True and len(result["records"]) == 20
    assert [row["record_id"] for row in result["records"]] == sorted(ids)[:20]
    assert older["id"] not in {row["record_id"] for row in result["records"]}
    assert included["id"] not in {row["record_id"] for row in result["records"]}
    assert all(row["unit"] == "kg" for row in result["records"])


async def test_weight_read_denies_foreign_and_admin_proxy_after_health_grant(weight_subject):
    """健康域grant不授予其他人的正式体重来源，当前本人字段撤回立即拒绝。"""
    subject = weight_subject
    await add_weight(subject)
    path = f"{ROOT}/members/{subject.member_id}/weight-records"
    for actor in subject.users[1:]:
        grant = await subject.client.put(
            f"{ROOT}/members/{subject.member_id}/grants",
            headers=subject.headers,
            json={"actor_uid": actor["uid"], "scopes": ["profile_view", "ai_use", "profile_edit"]},
        )
        assert grant.status_code == 200
        denied = await subject.client.get(path, headers=actor["headers"])
        assert denied.status_code == 404, denied.text
    assert (await subject.client.get(path)).status_code == 401
    revoke = await subject.client.put(
        f"{ROOT}/members/{subject.member_id}/grants",
        headers=subject.headers,
        json={"actor_uid": subject.uid, "scopes": ["ai_use"]},
    )
    assert revoke.status_code == 200
    assert (await subject.client.get(path, headers=subject.headers)).status_code == 404


async def test_weight_empty_use_is_persisted_and_new_record_invalidates_history(weight_subject):
    """空集也保存来源回执，新增范围内记录后旧缺口及checkpoint不可重用。"""
    subject = weight_subject
    binding, payload, run_id = await record_weight_use(subject)
    assert payload["records"] == [] and payload["code"] == "weight_missing"
    async with pg_manager.get_async_session_context() as session:
        use = await session.get(HealthWeightUse, (run_id, payload["source_hash"]))
        assert use is not None and use.record_refs == [] and use.source_member_id == subject.source_id
        assert use.start_date.isoformat() == payload["period"]["start_date"]
        assert use.end_date.isoformat() == payload["period"]["end_date"]
        await HealthWeightRepository(session).validate_history(subject.uid, binding)
        await HealthWeightRepository(session).validate_tool_payload(subject.uid, binding, payload)
    await add_weight(subject)
    async with pg_manager.get_async_session_context() as session:
        with pytest.raises(HealthVisionError) as changed:
            await HealthWeightRepository(session).validate_history(subject.uid, binding)
        assert changed.value.code == "weight_source_changed" and changed.value.status == 410
        with pytest.raises(HealthVisionError) as stale:
            await HealthWeightRepository(session).validate_tool_payload(subject.uid, binding, payload)
        assert stale.value.status == 410


async def test_weight_unlinked_use_invalidates_when_source_is_later_linked(weight_subject):
    """未关联回执也真实落库，随后明确映射不能沿用旧缺口。"""
    subject = weight_subject
    async with pg_manager.get_async_session_context() as session:
        await session.execute(
            delete(HealthFamilyProfileLink).where(HealthFamilyProfileLink.member_id == subject.member_id)
        )
    binding, payload, run_id = await record_weight_use(subject)
    assert payload["code"] == "weight_not_linked" and payload["source_member_id"] is None
    async with pg_manager.get_async_session_context() as session:
        use = await session.get(HealthWeightUse, (run_id, payload["source_hash"]))
        assert use.source_member_id is None and use.record_refs == []
        await HealthWeightRepository(session).validate_history(subject.uid, binding)
        await HealthWeightRepository(session).validate_tool_payload(subject.uid, binding, payload)
    response = await subject.client.post(
        f"{ROOT}/members/{subject.member_id}/family-profile-link",
        headers=subject.headers,
        json={"family_id": subject.family_id, "source_member_id": subject.source_id, "confirmed_identity": True},
    )
    assert response.status_code == 200
    async with pg_manager.get_async_session_context() as session:
        with pytest.raises(HealthVisionError) as changed:
            await HealthWeightRepository(session).validate_history(subject.uid, binding)
        assert changed.value.code == "weight_source_changed" and changed.value.status == 410


async def test_weight_history_ignores_profile_edit_but_rechecks_current_permission(weight_subject):
    """基础档案更改不改变体重摘要，当前profile_view撤回仍阻止历史读取。"""
    subject = weight_subject
    await add_weight(subject)
    binding, payload, _ = await record_weight_use(subject)
    edited = await subject.client.put(
        f"/api/family/{subject.family_id}/members/{subject.source_id}",
        headers=subject.headers,
        json={"expected_version": 1, "profile": {"height_cm": 171}},
    )
    assert edited.status_code == 200, edited.text
    assert (await read_weight(subject))["source_hash"] == payload["source_hash"]
    async with pg_manager.get_async_session_context() as session:
        source = await session.get(FamilyMember, subject.source_id)
        assert source.version == 2 and source.confirmed_version is None
        await HealthWeightRepository(session).validate_history(subject.uid, binding)
        await HealthWeightRepository(session).validate_tool_payload(subject.uid, binding, payload)
    revoked = await subject.client.put(
        f"{ROOT}/members/{subject.member_id}/grants",
        headers=subject.headers,
        json={"actor_uid": subject.uid, "scopes": ["ai_use"]},
    )
    assert revoked.status_code == 200
    async with pg_manager.get_async_session_context() as session:
        with pytest.raises(HealthVisionError) as changed:
            await HealthWeightRepository(session).validate_history(subject.uid, binding)
        assert changed.value.code == "weight_source_changed" and changed.value.status == 410


async def test_weight_use_rejects_tampering_cross_thread_and_correction(weight_subject):
    """摘要不代替真实正文或线程来源，更正后冻结范围依赖失效。"""
    subject = weight_subject
    record = await add_weight(subject)
    binding, payload, run_id = await record_weight_use(subject)
    async with pg_manager.get_async_session_context() as session:
        use = await session.get(HealthWeightUse, (run_id, payload["source_hash"]))
        assert use.member_id == subject.member_id and use.source_member_id == subject.source_id
        assert use.record_refs == [{"record_id": record["id"], "version": 1}]
        for field, value in (("value", 99), ("version", True)):
            tampered = json.loads(json.dumps(payload))
            tampered["records"][0][field] = value
            with pytest.raises(HealthVisionError) as forged:
                await HealthWeightRepository(session).validate_tool_payload(subject.uid, binding, tampered)
            assert forged.value.status == 410
        wrong_binding = SimpleNamespace(conversation_id=-1, member_id=subject.member_id, actor_uid=subject.uid)
        with pytest.raises(HealthVisionError) as crossed:
            await HealthWeightRepository(session).validate_tool_payload(subject.uid, wrong_binding, payload)
        assert crossed.value.status == 410
    await correct_weight(subject, record["id"])
    async with pg_manager.get_async_session_context() as session:
        with pytest.raises(HealthVisionError) as changed:
            await HealthWeightRepository(session).validate_history(subject.uid, binding)
        assert changed.value.code == "weight_source_changed" and changed.value.status == 410


async def test_weight_correction_waits_for_real_read_transaction(weight_subject):
    """真实PG家庭锁串行化体重读取与更正，发布事务不得读到混合来源。"""
    subject = weight_subject
    record = await add_weight(subject)
    application_name = "weight_update_" + uuid4().hex

    async def writer():
        """正式更正服务使用另一连接并持有原家庭锁。"""
        async with pg_manager.get_async_session_context() as session:
            await session.execute(
                text("SELECT set_config('application_name', :name, true)"), {"name": application_name}
            )
            return await FamilyService(session, subject.uid).correct_measurement(
                subject.family_id,
                subject.source_id,
                record["id"],
                MeasurementUpdate(expected_version=1, values={"weight": 61}, note="合成锁等待更正"),
            )

    async with pg_manager.get_async_session_context() as reader:
        payload = await HealthWeightRepository(reader).read(subject.uid, subject.member_id)
        assert payload["records"][0]["value"] == 60
        pending = asyncio.create_task(writer())
        try:
            async with pg_manager.get_async_session_context() as observer:
                async with asyncio.timeout(5):
                    while True:
                        await observer.execute(text("SELECT pg_stat_clear_snapshot()"))
                        blocked = await observer.scalar(
                            text(
                                "SELECT count(*) FROM pg_stat_activity WHERE application_name=:name "
                                "AND wait_event_type='Lock'"
                            ),
                            {"name": application_name},
                        )
                        if blocked:
                            break
                        await asyncio.sleep(0.02)
            assert not pending.done()
            await reader.commit()
            assert (await asyncio.wait_for(pending, 5))["version"] == 2
        finally:
            await reader.rollback()
            if not pending.done():
                pending.cancel()
            await asyncio.gather(pending, return_exceptions=True)


async def create_weight_subject(client, users, *, member_id=None):
    """真实接口准备唯一健康本人及空档案来源，不确认基础档案。"""
    headers, uid = users[0]["headers"], users[0]["uid"]
    member_id = member_id or await create_member(client, headers)
    response = await client.post("/api/family", headers=headers, json={"name": "合成本人体重测试家庭"})
    assert response.status_code == 200, response.text
    family_id = response.json()["id"]
    source_id = next(row["id"] for row in response.json()["members"] if row["is_self"])
    linked = await client.post(
        f"{ROOT}/members/{member_id}/family-profile-link",
        headers=headers,
        json={"family_id": family_id, "source_member_id": source_id, "confirmed_identity": True},
    )
    assert linked.status_code == 200, linked.text
    return SimpleNamespace(
        client=client,
        users=users,
        headers=headers,
        uid=uid,
        member_id=member_id,
        family_id=family_id,
        source_id=source_id,
        measurement_path=f"/api/family/{family_id}/members/{source_id}/measurements",
    )


async def add_weight(subject, *, value=60, measured_at=None):
    """真实保存合成测量，备注和条件用于验证最小投影不外发。"""
    measured_at = measured_at or datetime.now(UTC).replace(microsecond=0) - timedelta(hours=1)
    response = await subject.client.post(
        subject.measurement_path,
        headers=subject.headers,
        json={
            "id": str(uuid4()),
            "kind": "weight",
            "values": {"weight": value},
            "measured_at": measured_at.isoformat(),
            "source": "synthetic-weight-scale",
            "condition": "不得外发的合成测量条件",
            "note": "不得外发的合成私人备注",
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


async def correct_weight(subject, record_id):
    """经家庭正式更正接口改为61kg，保留原测量时间及来源。"""
    response = await subject.client.put(
        subject.measurement_path + "/" + record_id,
        headers=subject.headers,
        json={"expected_version": 1, "values": {"weight": 61}, "note": "合成体重更正，不是临床判断"},
    )
    assert response.status_code == 200, response.text
    return response.json()


async def read_weight(subject):
    """普通接口读取当前本人投影，不调用模型或建立处理同意。"""
    response = await subject.client.get(f"{ROOT}/members/{subject.member_id}/weight-records", headers=subject.headers)
    assert response.status_code == 200 and response.headers["Cache-Control"] == "no-store", response.text
    return response.json()


async def record_weight_use(subject, *, repository=HealthWeightRepository):
    """只为历史集成测试创建终态Run，实际Worker执行由E2E独立证明。"""
    async with pg_manager.get_async_session_context() as session:
        project_id, thread_id, run_id = str(uuid4()), str(uuid4()), str(uuid4())
        session.add(
            Project(
                id=project_id,
                uid=subject.uid,
                selection_status="implicit",
                directory_mode="managed",
                workdir_path=f"projects/{project_id}",
            )
        )
        await session.flush()
        conversation = Conversation(
            uid=subject.uid, thread_id=thread_id, project_id=project_id, agent_id="health-consultation"
        )
        session.add(conversation)
        await session.flush()
        binding = HealthConsultation(
            conversation_id=conversation.id, member_id=subject.member_id, actor_uid=subject.uid, request_id=str(uuid4())
        )
        session.add(binding)
        await session.flush()
        run = AgentRun(
            id=run_id,
            request_id=str(uuid4()),
            uid=subject.uid,
            agent_slug="health-consultation",
            conversation_id=conversation.id,
            conversation_thread_id=thread_id,
            runtime_scope_id=thread_id,
            status="completed",
        )
        session.add(run)
        await session.flush()
        repo = repository(session)
        payload = await repo.read(subject.uid, subject.member_id)
        await repo.record_use(run, payload)
        return (
            SimpleNamespace(conversation_id=conversation.id, member_id=subject.member_id, actor_uid=subject.uid),
            payload,
            run_id,
        )


async def cleanup_weight_subject(subject):
    """仅删除本轮家庭、映射及体重依赖，账号和健康对象交原fixture清理。"""
    async with pg_manager.get_async_session_context() as session:
        await session.execute(delete(HealthWeightUse).where(HealthWeightUse.member_id == subject.member_id))
        await session.execute(
            delete(HealthFamilyProfileLink).where(HealthFamilyProfileLink.member_id == subject.member_id)
        )
        await session.execute(delete(FamilyAudit).where(FamilyAudit.family_id == subject.family_id))
        for model in (FamilyMeasurement, FamilyProfileRevision):
            await session.execute(delete(model).where(model.member_id == subject.source_id))
        await session.execute(delete(FamilyMember).where(FamilyMember.family_id == subject.family_id))
        await session.execute(
            delete(FamilyArchive).where(FamilyArchive.id == subject.family_id, FamilyArchive.owner_uid == subject.uid)
        )

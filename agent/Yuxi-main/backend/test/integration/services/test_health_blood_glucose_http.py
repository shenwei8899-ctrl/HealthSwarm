"""真实HTTP与PG验证本人血糖与测量条件、空依赖、更正及体重兼容。"""

from copy import deepcopy
from datetime import UTC, datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
import pytest_asyncio
from sqlalchemy import delete, select, update

from test.integration.services.test_health_vision_http import ROOT, create_member, health_http  # noqa: F401
from test.integration.services.test_health_weight_http import (
    add_weight,
    cleanup_weight_subject,
    correct_weight,
    create_weight_subject,
    record_weight_use,
)
from yuxi.repositories.health_blood_glucose_repository import HealthBloodGlucoseRepository
from yuxi.repositories.health_weight_repository import HealthWeightRepository
from yuxi.services.health_daily_service import business_date
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_business import FamilyMeasurement, FamilyMember
from yuxi.storage.postgres.models_health import HealthBloodGlucoseUse, HealthFamilyProfileLink, HealthProcessingConsent
from yuxi.utils.datetime_utils import format_utc_datetime

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest_asyncio.fixture
async def glucose_subject(health_http):  # noqa: F811
    """复用两种实测共同本人身份的真实fixture，清理新增血糖回执。"""
    client, users = health_http
    subject = await create_weight_subject(client, users)
    try:
        yield subject
    finally:
        async with pg_manager.get_async_session_context() as session:
            await session.execute(
                delete(HealthBloodGlucoseUse).where(HealthBloodGlucoseUse.member_id == subject.member_id)
            )
        await cleanup_weight_subject(subject)


async def test_blood_glucose_missing_and_independent_measurement_need_no_profile_confirmation(glucose_subject):
    """未签模型处理同意、基础档案未确认，也可经普通接口读原始血糖。"""
    subject = glucose_subject
    missing = await read_glucose(subject)
    assert missing["code"] == "blood_glucose_missing" and missing["status"] == "not_ready"
    measured = datetime.now(UTC).replace(microsecond=0) - timedelta(hours=1)
    record = await add_glucose(subject, measured_at=measured)
    payload = await read_glucose(subject)
    assert payload["code"] == "self_blood_glucose_records" and payload["status"] == "ready"
    assert payload["records"] == [
        {
            "record_id": record["id"],
            "glucose": 5.5,
            "condition": "fasting",
            "unit": "mmol/L",
            "measured_at": format_utc_datetime(measured),
            "source": "synthetic-glucose-device",
            "version": 1,
        }
    ]
    assert payload["full_health_profile_available"] is payload["nutrition_safety_ready"] is False
    assert "note" not in str(payload) and "previous" not in payload["records"][0]
    async with pg_manager.get_async_session_context() as session:
        source = await session.get(FamilyMember, subject.source_id)
        assert (source.version, source.confirmed_version, source.profile) == (1, None, {})
        assert (
            await session.scalar(
                select(HealthProcessingConsent).where(HealthProcessingConsent.member_id == subject.member_id)
            )
            is None
        )
        assert (
            await session.scalar(
                select(HealthBloodGlucoseUse).where(HealthBloodGlucoseUse.member_id == subject.member_id)
            )
            is None
        )


async def test_voided_blood_glucose_is_excluded_and_invalidates_history(glucose_subject):
    """血糖作废与体重独立，旧血糖回执不能继续授权历史或checkpoint。"""
    subject = glucose_subject
    record = await add_glucose(subject)
    weight = await add_weight(subject)
    binding, payload, _ = await record_weight_use(subject, repository=HealthBloodGlucoseRepository)
    response = await subject.client.post(
        subject.measurement_path + "/" + record["id"] + "/void",
        headers=subject.headers,
        json={"expected_version": 1, "reason": "合成血糖误录作废"},
    )
    assert response.status_code == 200, response.text
    current = await read_glucose(subject)
    assert current["records"] == [] and current["code"] == "blood_glucose_missing"
    weight_read = await subject.client.get(
        f"{ROOT}/members/{subject.member_id}/weight-records", headers=subject.headers
    )
    assert weight_read.status_code == 200, weight_read.text
    assert [row["record_id"] for row in weight_read.json()["records"]] == [weight["id"]]
    async with pg_manager.get_async_session_context() as session:
        persisted = await session.get(FamilyMeasurement, record["id"])
        assert persisted.voided_at is not None and persisted.values == {"glucose": 5.5}
        assert persisted.version == 2
        with pytest.raises(HealthVisionError) as changed:
            await HealthBloodGlucoseRepository(session).validate_history(subject.uid, binding)
        assert changed.value.code == "blood_glucose_source_changed" and changed.value.status == 410
        with pytest.raises(HealthVisionError) as stale:
            await HealthBloodGlucoseRepository(session).validate_tool_payload(subject.uid, binding, payload)
        assert stale.value.status == 410


async def test_blood_glucose_thirty_days_twenty_cap_and_weight_selection_are_independent(glucose_subject):
    """上海自然日边界、稳定排序及截断独立；体重不混入血糖结果。"""
    subject = glucose_subject
    boundary = datetime.combine(business_date() - timedelta(days=29), datetime.min.time(), ZoneInfo("Asia/Shanghai"))
    await add_glucose(subject, measured_at=boundary - timedelta(seconds=1))
    included = await add_glucose(subject, measured_at=boundary)
    assert [row["record_id"] for row in (await read_glucose(subject))["records"]] == [included["id"]]
    now = datetime.now(UTC).replace(microsecond=0) - timedelta(hours=1)
    identifiers = [(await add_glucose(subject, measured_at=now))["id"] for _ in range(21)]
    await add_weight(subject)
    result = await read_glucose(subject)
    assert result["truncated"] is True and result["limit"] == 20
    assert [row["record_id"] for row in result["records"]] == sorted(identifiers)[:20]
    assert result["period"] == {
        "start_date": (business_date() - timedelta(days=29)).isoformat(),
        "end_date": business_date().isoformat(),
        "timezone": "Asia/Shanghai",
    }
    async with pg_manager.get_async_session_context() as session:
        weight = await HealthWeightRepository(session).read(subject.uid, subject.member_id)
        assert len(weight["records"]) == 1 and weight["records"][0]["unit"] == "kg" and weight["truncated"] is False


@pytest.mark.parametrize("linked", [False, True])
async def test_blood_glucose_empty_or_unlinked_receipt_invalidates_new_source(glucose_subject, linked):
    """真实空集回执含冻结日期；未关联新建来源或范围内新增使历史与checkpoint失效。"""
    subject = glucose_subject
    if not linked:
        async with pg_manager.get_async_session_context() as session:
            await session.execute(
                delete(HealthFamilyProfileLink).where(HealthFamilyProfileLink.member_id == subject.member_id)
            )
        assert (await read_glucose(subject))["code"] == "blood_glucose_not_linked"
    binding, payload, run_id = await record_weight_use(subject, repository=HealthBloodGlucoseRepository)
    assert payload["code"] == ("blood_glucose_missing" if linked else "blood_glucose_not_linked")
    async with pg_manager.get_async_session_context() as session:
        receipt = await session.get(HealthBloodGlucoseUse, (run_id, payload["source_hash"]))
        assert receipt.record_refs == [] and receipt.source_member_id == (subject.source_id if linked else None)
        assert receipt.start_date.isoformat() == payload["period"]["start_date"]
        assert receipt.end_date.isoformat() == payload["period"]["end_date"]
        await HealthBloodGlucoseRepository(session).validate_history(subject.uid, binding)
        await HealthBloodGlucoseRepository(session).validate_tool_payload(subject.uid, binding, payload)
    if linked:
        await add_glucose(subject)
    else:
        response = await subject.client.post(
            f"{ROOT}/members/{subject.member_id}/family-profile-link",
            headers=subject.headers,
            json={"family_id": subject.family_id, "source_member_id": subject.source_id, "confirmed_identity": True},
        )
        assert response.status_code == 200, response.text
    async with pg_manager.get_async_session_context() as session:
        repo = HealthBloodGlucoseRepository(session)
        for checkpoint in (False, True):
            with pytest.raises(HealthVisionError, match="blood_glucose_source_changed") as changed:
                if checkpoint:
                    await repo.validate_tool_payload(subject.uid, binding, payload)
                else:
                    await repo.validate_history(subject.uid, binding)
            assert changed.value.status == 410


async def test_blood_glucose_correction_invalidates_own_history_and_keeps_weight_receipt(glucose_subject):
    """仅更正测量条件也推进版本并使旧血糖失效；同源体重旧回执仍有效，伪造与跨线程不能复用。"""
    subject = glucose_subject
    record = await add_glucose(subject)
    await add_weight(subject)
    glucose_binding, payload, run_id = await record_weight_use(subject, repository=HealthBloodGlucoseRepository)
    weight_binding, weight_payload, _ = await record_weight_use(subject)
    async with pg_manager.get_async_session_context() as session:
        receipt = await session.get(HealthBloodGlucoseUse, (run_id, payload["source_hash"]))
        assert receipt.record_refs == [{"record_id": record["id"], "version": 1}]
        forged = deepcopy(payload)
        forged["records"][0]["version"] = True
        with pytest.raises(HealthVisionError, match="blood_glucose_source_changed"):
            await HealthBloodGlucoseRepository(session).validate_tool_payload(subject.uid, glucose_binding, forged)
        with pytest.raises(HealthVisionError, match="blood_glucose_source_changed"):
            await HealthBloodGlucoseRepository(session).validate_tool_payload(subject.uid, weight_binding, payload)
    corrected = await subject.client.put(
        subject.measurement_path + "/" + record["id"],
        headers=subject.headers,
        json={
            "expected_version": 1,
            "values": {"glucose": 5.5},
            "condition": "after_meal_2h",
            "note": "synthetic-private-correction",
        },
    )
    assert corrected.status_code == 200 and corrected.json()["version"] == 2, corrected.text
    current = await read_glucose(subject)
    assert current["records"][0] == {**payload["records"][0], "condition": "after_meal_2h", "version": 2}
    async with pg_manager.get_async_session_context() as session:
        persisted = await session.get(FamilyMeasurement, record["id"])
        assert persisted.previous[0]["values"] == {"glucose": 5.5}
        assert persisted.measured_at.isoformat() == record["measured_at"].replace("Z", "")
        source = await session.get(FamilyMember, subject.source_id)
        assert source.version == 1 and source.confirmed_version is None
        await HealthWeightRepository(session).validate_history(subject.uid, weight_binding)
        await HealthWeightRepository(session).validate_tool_payload(subject.uid, weight_binding, weight_payload)
        with pytest.raises(HealthVisionError, match="blood_glucose_source_changed"):
            await HealthBloodGlucoseRepository(session).validate_history(subject.uid, glucose_binding)


async def test_weight_correction_keeps_blood_glucose_dependency_but_current_access_is_required(glucose_subject):
    """编辑基础档案或另一个指标不误伤血糖；本人权限撤回仍使原依赖失效。"""
    subject = glucose_subject
    await add_glucose(subject)
    weight = await add_weight(subject)
    binding, payload, _ = await record_weight_use(subject, repository=HealthBloodGlucoseRepository)
    await correct_weight(subject, weight["id"])
    edited = await subject.client.put(
        f"/api/family/{subject.family_id}/members/{subject.source_id}",
        headers=subject.headers,
        json={"expected_version": 1, "profile": {"height_cm": 171}},
    )
    assert edited.status_code == 200, edited.text
    assert (await read_glucose(subject))["source_hash"] == payload["source_hash"]
    async with pg_manager.get_async_session_context() as session:
        await HealthBloodGlucoseRepository(session).validate_history(subject.uid, binding)
    for actor in subject.users[1:]:
        grant = await subject.client.put(
            f"{ROOT}/members/{subject.member_id}/grants",
            headers=subject.headers,
            json={"actor_uid": actor["uid"], "scopes": ["profile_view", "ai_use", "profile_edit"]},
        )
        assert grant.status_code == 200
        denied = await subject.client.get(
            f"{ROOT}/members/{subject.member_id}/blood-glucose-records", headers=actor["headers"]
        )
        assert denied.status_code == 404
    revoked = await subject.client.put(
        f"{ROOT}/members/{subject.member_id}/grants",
        headers=subject.headers,
        json={"actor_uid": subject.uid, "scopes": ["ai_use"]},
    )
    assert revoked.status_code == 200
    async with pg_manager.get_async_session_context() as session:
        with pytest.raises(HealthVisionError, match="blood_glucose_source_changed"):
            await HealthBloodGlucoseRepository(session).validate_history(subject.uid, binding)


async def test_forged_hash_and_stored_json_reference_types_are_rejected_on_real_pg(glucose_subject):
    """真实PG回执不能让hash对象成为SQL参数，版本true不能冒充整数1。"""
    subject = glucose_subject
    record = await add_glucose(subject)
    binding, payload, run_id = await record_weight_use(subject, repository=HealthBloodGlucoseRepository)
    async with pg_manager.get_async_session_context() as session:
        repo = HealthBloodGlucoseRepository(session)
        for forged_hash in ({"forged": "hash"}, ["forged"], True, None):
            forged = deepcopy(payload)
            forged["source_hash"] = forged_hash
            with pytest.raises(HealthVisionError, match="blood_glucose_source_changed") as error:
                await repo.validate_tool_payload(subject.uid, binding, forged)
            assert error.value.status == 410
        await session.execute(
            update(HealthBloodGlucoseUse)
            .where(HealthBloodGlucoseUse.run_id == run_id, HealthBloodGlucoseUse.payload_hash == payload["source_hash"])
            .values(record_refs=[{"record_id": record["id"], "version": True}])
        )
    async with pg_manager.get_async_session_context() as session:
        receipt = await session.get(HealthBloodGlucoseUse, (run_id, payload["source_hash"]))
        assert receipt.record_refs[0]["version"] is True
        repo = HealthBloodGlucoseRepository(session)
        with pytest.raises(HealthVisionError, match="blood_glucose_source_changed"):
            await repo.validate_history(subject.uid, binding)
        with pytest.raises(HealthVisionError, match="blood_glucose_source_changed"):
            await repo.validate_tool_payload(subject.uid, binding, payload)
        await session.execute(
            update(HealthBloodGlucoseUse)
            .where(HealthBloodGlucoseUse.run_id == run_id, HealthBloodGlucoseUse.payload_hash == payload["source_hash"])
            .values(record_refs=[{"record_id": record["id"], "version": 1}])
        )
        await repo.validate_history(subject.uid, binding)
        await repo.validate_tool_payload(subject.uid, binding, payload)


async def test_correction_beyond_twenty_visible_records_keeps_frozen_projection_valid(glucose_subject):
    """第21条仅决定truncated，未外发的数值更正不使已读20条失效。"""
    subject = glucose_subject
    measured = datetime.now(UTC).replace(microsecond=0) - timedelta(hours=1)
    record_ids = [(await add_glucose(subject, measured_at=measured))["id"] for _ in range(21)]
    binding, payload, _ = await record_weight_use(subject, repository=HealthBloodGlucoseRepository)
    visible_ids = {record["record_id"] for record in payload["records"]}
    assert len(visible_ids) == 20 and payload["truncated"] is True
    excluded = next(identifier for identifier in record_ids if identifier not in visible_ids)
    corrected = await subject.client.put(
        subject.measurement_path + "/" + excluded,
        headers=subject.headers,
        json={
            "expected_version": 1,
            "values": {"glucose": 5.7},
            "note": "synthetic-unread-correction",
        },
    )
    assert corrected.status_code == 200 and corrected.json()["version"] == 2, corrected.text
    assert await read_glucose(subject) == payload
    async with pg_manager.get_async_session_context() as session:
        persisted = await session.get(FamilyMeasurement, excluded)
        assert persisted.version == 2 and persisted.values == {"glucose": 5.7}
        await HealthBloodGlucoseRepository(session).validate_history(subject.uid, binding)
        await HealthBloodGlucoseRepository(session).validate_tool_payload(subject.uid, binding, payload)


async def read_glucose(subject):
    """真实普通接口不签同意，并要求隐私no-store响应。"""
    response = await subject.client.get(
        f"{ROOT}/members/{subject.member_id}/blood-glucose-records", headers=subject.headers
    )
    assert response.status_code == 200 and response.headers["Cache-Control"] == "no-store", response.text
    return response.json()


async def add_glucose(subject, *, measured_at=None):
    """真实家庭测量接口写入原始合成血糖和不外发备注。"""
    measured_at = measured_at or datetime.now(UTC).replace(microsecond=0) - timedelta(hours=1)
    response = await subject.client.post(
        subject.measurement_path,
        headers=subject.headers,
        json={
            "id": str(uuid4()),
            "kind": "blood_glucose",
            "values": {"glucose": 5.5},
            "measured_at": measured_at.isoformat(),
            "source": "synthetic-glucose-device",
            "condition": "fasting",
            "note": "synthetic-private-note",
        },
    )
    assert response.status_code == 200, response.text
    return response.json()

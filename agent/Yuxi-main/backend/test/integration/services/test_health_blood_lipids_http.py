"""真实HTTP与PG验证同条血脂四项、独立版本、最小投影及本人权限。"""

from copy import deepcopy
from datetime import UTC, datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
import pytest_asyncio
from sqlalchemy import delete, select, update

from test.integration.services.test_health_vision_http import ROOT, health_http  # noqa: F401
from test.integration.services.test_health_weight_http import (
    add_weight,
    cleanup_weight_subject,
    correct_weight,
    create_weight_subject,
    record_weight_use,
)
from yuxi.repositories.health_blood_lipids_repository import HealthBloodLipidsRepository
from yuxi.repositories.health_weight_repository import HealthWeightRepository
from yuxi.services.health_daily_service import business_date
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_business import FamilyMeasurement, FamilyMember
from yuxi.storage.postgres.models_health import HealthBloodLipidsUse, HealthFamilyProfileLink, HealthProcessingConsent
from yuxi.utils.datetime_utils import format_utc_datetime

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest_asyncio.fixture
async def lipids_subject(health_http):  # noqa: F811
    """复用真实本人映射，只清理本轮血脂回执及合成家庭。"""
    client, users = health_http
    subject = await create_weight_subject(client, users)
    try:
        yield subject
    finally:
        async with pg_manager.get_async_session_context() as session:
            await session.execute(
                delete(HealthBloodLipidsUse).where(HealthBloodLipidsUse.member_id == subject.member_id)
            )
        await cleanup_weight_subject(subject)


async def test_blood_lipids_raw_four_items_need_no_profile_confirmation_or_model_consent(lipids_subject):
    """空档案未确认且未签模型同意，普通接口仍可读取同条完整四项原值。"""
    subject = lipids_subject
    missing = await read_lipids(subject)
    assert missing["code"] == "blood_lipids_missing" and missing["status"] == "not_ready"
    measured = datetime.now(UTC).replace(microsecond=0) - timedelta(hours=1)
    record = await add_lipids(subject, measured_at=measured)
    payload = await read_lipids(subject)
    assert payload["code"] == "self_blood_lipids_records" and payload["status"] == "ready"
    assert payload["records"] == [
        {
            "record_id": record["id"],
            "tc": 4.5,
            "tg": 1.2,
            "hdl": 1.3,
            "ldl": 2.6,
            "unit": "mmol/L",
            "measured_at": format_utc_datetime(measured),
            "source": "synthetic-lipids-device",
            "version": 1,
        }
    ]
    assert payload["full_health_profile_available"] is payload["nutrition_safety_ready"] is False
    assert set(payload["records"][0]) == {
        "record_id",
        "tc",
        "tg",
        "hdl",
        "ldl",
        "unit",
        "measured_at",
        "source",
        "version",
    }
    assert not {"condition", "note", "previous", "ratio", "classification"} & payload["records"][0].keys()
    async with pg_manager.get_async_session_context() as session:
        source = await session.get(FamilyMember, subject.source_id)
        assert (source.version, source.confirmed_version, source.profile) == (1, None, {})
        persisted = await session.get(FamilyMeasurement, record["id"])
        assert persisted.values == {"tc": 4.5, "tg": 1.2, "hdl": 1.3, "ldl": 2.6}
        assert persisted.condition == "不得外发的合成测量条件" and persisted.note == "synthetic-private-note"
        assert (
            await session.scalar(
                select(HealthProcessingConsent).where(HealthProcessingConsent.member_id == subject.member_id)
            )
            is None
        )
        assert (
            await session.scalar(
                select(HealthBloodLipidsUse).where(HealthBloodLipidsUse.member_id == subject.member_id)
            )
            is None
        )


async def test_voided_blood_lipids_excludes_the_whole_record_and_invalidates_history(lipids_subject):
    """作废保留四项原始事实；旧血脂历史与checkpoint均失效，体重仍独立。"""
    subject = lipids_subject
    record = await add_lipids(subject)
    weight = await add_weight(subject)
    binding, payload, _ = await record_weight_use(subject, repository=HealthBloodLipidsRepository)
    response = await subject.client.post(
        subject.measurement_path + "/" + record["id"] + "/void",
        headers=subject.headers,
        json={"expected_version": 1, "reason": "合成血脂误录作废"},
    )
    assert response.status_code == 200, response.text
    current = await read_lipids(subject)
    assert current["records"] == [] and current["code"] == "blood_lipids_missing"
    weight_read = await subject.client.get(
        f"{ROOT}/members/{subject.member_id}/weight-records", headers=subject.headers
    )
    assert weight_read.status_code == 200, weight_read.text
    assert [row["record_id"] for row in weight_read.json()["records"]] == [weight["id"]]
    async with pg_manager.get_async_session_context() as session:
        persisted = await session.get(FamilyMeasurement, record["id"])
        assert persisted.voided_at is not None and persisted.version == 2
        assert persisted.values == {"tc": 4.5, "tg": 1.2, "hdl": 1.3, "ldl": 2.6}
        repo = HealthBloodLipidsRepository(session)
        with pytest.raises(HealthVisionError, match="blood_lipids_source_changed") as changed:
            await repo.validate_history(subject.uid, binding)
        assert changed.value.status == 410
        with pytest.raises(HealthVisionError, match="blood_lipids_source_changed") as stale:
            await repo.validate_tool_payload(subject.uid, binding, payload)
        assert stale.value.status == 410


async def test_blood_lipids_thirty_days_twenty_cap_excludes_three_other_measurement_kinds(lipids_subject):
    """上海自然日边界和稳定截断独立，不将体重、血压或血糖混入四项记录。"""
    subject = lipids_subject
    boundary = datetime.combine(business_date() - timedelta(days=29), datetime.min.time(), ZoneInfo("Asia/Shanghai"))
    await add_lipids(subject, measured_at=boundary - timedelta(seconds=1))
    included = await add_lipids(subject, measured_at=boundary)
    assert [row["record_id"] for row in (await read_lipids(subject))["records"]] == [included["id"]]
    now = datetime.now(UTC).replace(microsecond=0) - timedelta(hours=1)
    identifiers = [(await add_lipids(subject, measured_at=now))["id"] for _ in range(21)]
    await add_weight(subject)
    for kind, values, condition in (
        ("blood_pressure", {"systolic": 120, "diastolic": 80}, ""),
        ("blood_glucose", {"glucose": 5.5}, "fasting"),
    ):
        other = await subject.client.post(
            subject.measurement_path,
            headers=subject.headers,
            json={
                "id": str(uuid4()),
                "kind": kind,
                "values": values,
                "condition": condition,
                "measured_at": now.isoformat(),
                "source": "synthetic-other-metric",
            },
        )
        assert other.status_code == 200, other.text
    result = await read_lipids(subject)
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
async def test_blood_lipids_empty_or_unlinked_receipt_invalidates_when_source_appears(lipids_subject, linked):
    """空集和未关联也存冻结日期引用，来源补齐后历史及checkpoint须重新读取。"""
    subject = lipids_subject
    if not linked:
        async with pg_manager.get_async_session_context() as session:
            await session.execute(
                delete(HealthFamilyProfileLink).where(HealthFamilyProfileLink.member_id == subject.member_id)
            )
        assert (await read_lipids(subject))["code"] == "blood_lipids_not_linked"
    binding, payload, run_id = await record_weight_use(subject, repository=HealthBloodLipidsRepository)
    assert payload["code"] == ("blood_lipids_missing" if linked else "blood_lipids_not_linked")
    async with pg_manager.get_async_session_context() as session:
        receipt = await session.get(HealthBloodLipidsUse, (run_id, payload["source_hash"]))
        assert receipt.record_refs == [] and receipt.source_member_id == (subject.source_id if linked else None)
        assert receipt.start_date.isoformat() == payload["period"]["start_date"]
        assert receipt.end_date.isoformat() == payload["period"]["end_date"]
        await HealthBloodLipidsRepository(session).validate_history(subject.uid, binding)
        await HealthBloodLipidsRepository(session).validate_tool_payload(subject.uid, binding, payload)
    if linked:
        await add_lipids(subject)
    else:
        response = await subject.client.post(
            f"{ROOT}/members/{subject.member_id}/family-profile-link",
            headers=subject.headers,
            json={"family_id": subject.family_id, "source_member_id": subject.source_id, "confirmed_identity": True},
        )
        assert response.status_code == 200, response.text
    async with pg_manager.get_async_session_context() as session:
        repo = HealthBloodLipidsRepository(session)
        for checkpoint in (False, True):
            with pytest.raises(HealthVisionError, match="blood_lipids_source_changed") as changed:
                if checkpoint:
                    await repo.validate_tool_payload(subject.uid, binding, payload)
                else:
                    await repo.validate_history(subject.uid, binding)
            assert changed.value.status == 410


async def test_single_ldl_correction_invalidates_blood_lipids_and_keeps_other_items_and_weight(lipids_subject):
    """仅改LDL也推进整条版本；其余三项、时间、来源和独立体重回执保持。"""
    subject = lipids_subject
    record = await add_lipids(subject)
    await add_weight(subject)
    binding, payload, run_id = await record_weight_use(subject, repository=HealthBloodLipidsRepository)
    weight_binding, weight_payload, _ = await record_weight_use(subject)
    async with pg_manager.get_async_session_context() as session:
        receipt = await session.get(HealthBloodLipidsUse, (run_id, payload["source_hash"]))
        assert receipt.record_refs == [{"record_id": record["id"], "version": 1}]
        for field, value in (("ldl", 99), ("version", True)):
            forged = deepcopy(payload)
            forged["records"][0][field] = value
            with pytest.raises(HealthVisionError, match="blood_lipids_source_changed"):
                await HealthBloodLipidsRepository(session).validate_tool_payload(subject.uid, binding, forged)
        with pytest.raises(HealthVisionError, match="blood_lipids_source_changed"):
            await HealthBloodLipidsRepository(session).validate_tool_payload(subject.uid, weight_binding, payload)
    corrected = await subject.client.put(
        subject.measurement_path + "/" + record["id"],
        headers=subject.headers,
        json={
            "expected_version": 1,
            "values": {"tc": 4.5, "tg": 1.2, "hdl": 1.3, "ldl": 2.7},
            "note": "synthetic-private-correction",
        },
    )
    assert corrected.status_code == 200 and corrected.json()["version"] == 2, corrected.text
    current = await read_lipids(subject)
    assert current["records"][0] == {**payload["records"][0], "ldl": 2.7, "version": 2}
    assert current["source_hash"] != payload["source_hash"]
    async with pg_manager.get_async_session_context() as session:
        persisted = await session.get(FamilyMeasurement, record["id"])
        assert persisted.values == {"tc": 4.5, "tg": 1.2, "hdl": 1.3, "ldl": 2.7}
        assert persisted.previous[0]["values"] == {"tc": 4.5, "tg": 1.2, "hdl": 1.3, "ldl": 2.6}
        assert persisted.measured_at.isoformat() == record["measured_at"].replace("Z", "")
        assert persisted.source == "synthetic-lipids-device"
        assert persisted.condition == "不得外发的合成测量条件"
        source = await session.get(FamilyMember, subject.source_id)
        assert source.version == 1 and source.confirmed_version is None
        await HealthWeightRepository(session).validate_history(subject.uid, weight_binding)
        await HealthWeightRepository(session).validate_tool_payload(subject.uid, weight_binding, weight_payload)
        repo = HealthBloodLipidsRepository(session)
        with pytest.raises(HealthVisionError, match="blood_lipids_source_changed"):
            await repo.validate_history(subject.uid, binding)
        with pytest.raises(HealthVisionError, match="blood_lipids_source_changed"):
            await repo.validate_tool_payload(subject.uid, binding, payload)


async def test_weight_or_profile_edit_keeps_lipids_but_foreign_grants_and_revocation_cannot_bypass_self(lipids_subject):
    """另一个指标和基础档案版本不误伤血脂；健康grant不能代替本人来源权限。"""
    subject = lipids_subject
    await add_lipids(subject)
    weight = await add_weight(subject)
    binding, payload, _ = await record_weight_use(subject, repository=HealthBloodLipidsRepository)
    await correct_weight(subject, weight["id"])
    edited = await subject.client.put(
        f"/api/family/{subject.family_id}/members/{subject.source_id}",
        headers=subject.headers,
        json={"expected_version": 1, "profile": {"height_cm": 171}},
    )
    assert edited.status_code == 200, edited.text
    assert (await read_lipids(subject))["source_hash"] == payload["source_hash"]
    async with pg_manager.get_async_session_context() as session:
        await HealthBloodLipidsRepository(session).validate_history(subject.uid, binding)
        await HealthBloodLipidsRepository(session).validate_tool_payload(subject.uid, binding, payload)
    path = f"{ROOT}/members/{subject.member_id}/blood-lipids-records"
    assert (await subject.client.get(path)).status_code == 401
    for actor in subject.users[1:]:
        grant = await subject.client.put(
            f"{ROOT}/members/{subject.member_id}/grants",
            headers=subject.headers,
            json={"actor_uid": actor["uid"], "scopes": ["profile_view", "ai_use", "profile_edit"]},
        )
        assert grant.status_code == 200, grant.text
        denied = await subject.client.get(path, headers=actor["headers"])
        assert denied.status_code == 404, denied.text
    revoked = await subject.client.put(
        f"{ROOT}/members/{subject.member_id}/grants",
        headers=subject.headers,
        json={"actor_uid": subject.uid, "scopes": ["ai_use"]},
    )
    assert revoked.status_code == 200, revoked.text
    assert (await subject.client.get(path, headers=subject.headers)).status_code == 404
    async with pg_manager.get_async_session_context() as session:
        repo = HealthBloodLipidsRepository(session)
        with pytest.raises(HealthVisionError, match="blood_lipids_source_changed"):
            await repo.validate_history(subject.uid, binding)
        with pytest.raises(HealthVisionError, match="blood_lipids_source_changed"):
            await repo.validate_tool_payload(subject.uid, binding, payload)


async def test_inactive_source_rejects_current_blood_lipids_and_old_history(lipids_subject):
    """真实PG来源停用后，普通读与旧历史、checkpoint均拒绝，原测量留存。"""
    subject = lipids_subject
    record = await add_lipids(subject)
    binding, payload, _ = await record_weight_use(subject, repository=HealthBloodLipidsRepository)
    async with pg_manager.get_async_session_context() as session:
        await session.execute(update(FamilyMember).where(FamilyMember.id == subject.source_id).values(is_active=False))
    denied = await subject.client.get(
        f"{ROOT}/members/{subject.member_id}/blood-lipids-records", headers=subject.headers
    )
    assert denied.status_code == 404, denied.text
    async with pg_manager.get_async_session_context() as session:
        source = await session.get(FamilyMember, subject.source_id)
        persisted = await session.get(FamilyMeasurement, record["id"])
        assert source.is_active is False and persisted.values == {"tc": 4.5, "tg": 1.2, "hdl": 1.3, "ldl": 2.6}
        repo = HealthBloodLipidsRepository(session)
        with pytest.raises(HealthVisionError, match="blood_lipids_source_changed") as changed:
            await repo.validate_history(subject.uid, binding)
        assert changed.value.status == 410
        with pytest.raises(HealthVisionError, match="blood_lipids_source_changed") as stale:
            await repo.validate_tool_payload(subject.uid, binding, payload)
        assert stale.value.status == 410


async def test_forged_hash_and_json_reference_types_are_rejected_on_real_pg(lipids_subject):
    """hash必须为文本，持久JSON版本true不能冒充整数1授权旧四项。"""
    subject = lipids_subject
    record = await add_lipids(subject)
    binding, payload, run_id = await record_weight_use(subject, repository=HealthBloodLipidsRepository)
    async with pg_manager.get_async_session_context() as session:
        repo = HealthBloodLipidsRepository(session)
        for forged_hash in ({"forged": "hash"}, ["forged"], True, None):
            forged = deepcopy(payload)
            forged["source_hash"] = forged_hash
            with pytest.raises(HealthVisionError, match="blood_lipids_source_changed") as error:
                await repo.validate_tool_payload(subject.uid, binding, forged)
            assert error.value.status == 410
        await session.execute(
            update(HealthBloodLipidsUse)
            .where(HealthBloodLipidsUse.run_id == run_id, HealthBloodLipidsUse.payload_hash == payload["source_hash"])
            .values(record_refs=[{"record_id": record["id"], "version": True}])
        )
    async with pg_manager.get_async_session_context() as session:
        receipt = await session.get(HealthBloodLipidsUse, (run_id, payload["source_hash"]))
        assert receipt.record_refs[0]["version"] is True
        repo = HealthBloodLipidsRepository(session)
        with pytest.raises(HealthVisionError, match="blood_lipids_source_changed"):
            await repo.validate_history(subject.uid, binding)
        with pytest.raises(HealthVisionError, match="blood_lipids_source_changed"):
            await repo.validate_tool_payload(subject.uid, binding, payload)
        await session.execute(
            update(HealthBloodLipidsUse)
            .where(HealthBloodLipidsUse.run_id == run_id, HealthBloodLipidsUse.payload_hash == payload["source_hash"])
            .values(record_refs=[{"record_id": record["id"], "version": 1}])
        )
        await repo.validate_history(subject.uid, binding)
        await repo.validate_tool_payload(subject.uid, binding, payload)


async def test_correction_beyond_twenty_visible_records_keeps_frozen_projection_valid(lipids_subject):
    """未外发第21条的LDL更正不改变已读20条投影，仍须保存正式更正事实。"""
    subject = lipids_subject
    measured = datetime.now(UTC).replace(microsecond=0) - timedelta(hours=1)
    record_ids = [(await add_lipids(subject, measured_at=measured))["id"] for _ in range(21)]
    binding, payload, _ = await record_weight_use(subject, repository=HealthBloodLipidsRepository)
    visible_ids = {record["record_id"] for record in payload["records"]}
    assert len(visible_ids) == 20 and payload["truncated"] is True
    excluded = next(identifier for identifier in record_ids if identifier not in visible_ids)
    corrected = await subject.client.put(
        subject.measurement_path + "/" + excluded,
        headers=subject.headers,
        json={
            "expected_version": 1,
            "values": {"tc": 4.5, "tg": 1.2, "hdl": 1.3, "ldl": 2.7},
            "note": "synthetic-unread-correction",
        },
    )
    assert corrected.status_code == 200 and corrected.json()["version"] == 2, corrected.text
    assert await read_lipids(subject) == payload
    async with pg_manager.get_async_session_context() as session:
        persisted = await session.get(FamilyMeasurement, excluded)
        assert persisted.version == 2 and persisted.values == {"tc": 4.5, "tg": 1.2, "hdl": 1.3, "ldl": 2.7}
        await HealthBloodLipidsRepository(session).validate_history(subject.uid, binding)
        await HealthBloodLipidsRepository(session).validate_tool_payload(subject.uid, binding, payload)


async def read_lipids(subject):
    """经真实普通接口读取四项，要求隐私no-store且不签模型同意。"""
    response = await subject.client.get(
        f"{ROOT}/members/{subject.member_id}/blood-lipids-records", headers=subject.headers
    )
    assert response.status_code == 200 and response.headers["Cache-Control"] == "no-store", response.text
    return response.json()


async def add_lipids(subject, *, measured_at=None):
    """真实保存同条四项，附私人条件和备注用于证明最小外发范围。"""
    measured_at = measured_at or datetime.now(UTC).replace(microsecond=0) - timedelta(hours=1)
    response = await subject.client.post(
        subject.measurement_path,
        headers=subject.headers,
        json={
            "id": str(uuid4()),
            "kind": "blood_lipids",
            "values": {"tc": 4.5, "tg": 1.2, "hdl": 1.3, "ldl": 2.6},
            "measured_at": measured_at.isoformat(),
            "source": "synthetic-lipids-device",
            "condition": "不得外发的合成测量条件",
            "note": "synthetic-private-note",
        },
    )
    assert response.status_code == 200, response.text
    return response.json()

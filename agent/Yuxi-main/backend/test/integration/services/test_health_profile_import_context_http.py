"""真实JWT、TCP HTTP与独立PG验证专业导入上下文及持久化来源。"""

from copy import deepcopy
from datetime import UTC, datetime, timedelta
import hashlib
import json
from types import SimpleNamespace
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import func, select

from test.integration.services.test_health_family_profile_http import (
    ROOT,
    SYNTHETIC_PROFILE,
    cleanup_test_knowledge_resources,  # noqa: F401
    cleanup_test_sandboxes,  # noqa: F401
    create_health_member,
    ensure_live_api_schema,  # noqa: F401
    family_profile_http,  # noqa: F401
    linked_self,
)
from test.integration.services.test_health_family_safety_http import grant_safety_import, safety_body
from test.integration.services.test_health_weight_http import add_weight
from yuxi.services.family_schemas import REQUIRED_PROFILE_FIELDS
from yuxi.storage.postgres.models_business import FamilyAudit, FamilyMeasurement, FamilyMember as SourceMember
from yuxi.storage.postgres.models_health import HealthProcessingConsent, HealthProfileSnapshot
from yuxi.utils.datetime_utils import utc_now_naive

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest_asyncio.fixture
async def owner_context(family_profile_http):  # noqa: F811
    """家庭管理员邀请本人认领、填写并确认；两套读取授权初始独立。"""
    client, sessions, identities = family_profile_http
    response = await client.post("/api/family", headers=identities["admin"], json={"name": "合成专业家庭"})
    assert response.status_code == 200, response.text
    family_id = response.json()["id"]
    response = await client.post(
        f"/api/family/{family_id}/members",
        headers=identities["admin"],
        json={"name": "合成本人", "relationship": "家庭成员"},
    )
    assert response.status_code == 200, response.text
    source_id = response.json()["id"]
    source_path = f"/api/family/{family_id}/members/{source_id}"
    response = await client.post(source_path + "/invite", headers=identities["admin"])
    assert response.status_code == 200, response.text
    response = await client.post("/api/family/join", headers=identities["self"], json={"code": response.json()["code"]})
    assert response.status_code == 200, response.text
    response = await client.put(
        source_path, headers=identities["self"], json={"expected_version": 1, "profile": SYNTHETIC_PROFILE}
    )
    assert response.status_code == 200, response.text
    response = await client.post(source_path + "/confirm", headers=identities["self"], json={"expected_version": 2})
    assert response.status_code == 200, response.text
    member = await create_health_member(client, identities["self"])
    source = {"family_id": family_id, "source_member_id": source_id, "confirmed_identity": True}
    response = await client.post(
        f"{ROOT}/members/{member}/family-profile-link", headers=identities["self"], json=source
    )
    assert response.status_code == 200, response.text
    await grant_safety_import(client, identities["self"], member)
    case = SimpleNamespace(
        client=client,
        sessions=sessions,
        identities=identities,
        headers=identities["self"],
        member=member,
        source=source,
        source_path=source_path,
        measurement_path=source_path + "/measurements",
        context_path=f"{ROOT}/members/{member}/profile-import-context",
    )
    case.record = await add_weight(case)
    return case


async def test_owner_health_scopes_do_not_replace_explicit_family_field_read(owner_context):
    """完整健康授权和家庭owner身份都不提供未经本人授权的档案或体重。"""
    case = owner_context
    hidden = await context_read(case)
    assert hidden["formal_source"]["family_profile_source"] is None and hidden["formal_source"]["profile"] == {}
    assert hidden["weight_candidates"]["items"] == [] and hidden["current_profile"]["next_version"] == 1
    await grant_fields(case, ["height_cm"])
    partial = await context_read(case)
    assert partial["formal_source"]["profile"] == {"height_cm": 165.0}
    assert partial["formal_source"]["reason"] == "family_profile_fields_required"
    assert partial["formal_source"]["family_profile_source"] is None
    assert partial["weight_candidates"]["items"] == []
    await grant_fields(case, [*REQUIRED_PROFILE_FIELDS, "weight", "medical_history"])
    full = await context_read(case)
    assert full["formal_source"]["family_profile_source"] == {
        "family_id": case.source["family_id"],
        "source_member_id": case.source["source_member_id"],
        "confirmed_version": 2,
    }
    assert full["formal_source"]["profile"] == {key: SYNTHETIC_PROFILE[key] for key in REQUIRED_PROFILE_FIELDS}
    assert "medical_history" not in full["formal_source"]["profile"]
    assert full["weight_candidates"]["items"][0]["weight_kg"] == "60.0"
    async with case.sessions() as session:
        audits = list(
            (await session.scalars(select(FamilyAudit).where(FamilyAudit.action.like("profile_import_%")))).all()
        )
        assert audits and {row.actor_uid for row in audits} == {"admin"}
        assert await session.scalar(select(func.count()).select_from(HealthProcessingConsent)) == 0


async def test_self_administrator_reads_without_grant_and_user_cannot_open_admin_entry(family_profile_http):  # noqa: F811
    """管理员自己的本人档案复用自读权；普通本人账号仍不能进入专业导入入口。"""
    client, sessions, identities = family_profile_http
    member, source = await linked_self(client, identities["admin"])
    case = SimpleNamespace(
        client=client,
        sessions=sessions,
        identities=identities,
        headers=identities["admin"],
        member=member,
        source=source,
        measurement_path=f"/api/family/{source['family_id']}/members/{source['source_member_id']}/measurements",
        context_path=f"{ROOT}/members/{member}/profile-import-context",
    )
    await add_weight(case)
    result = await context_read(case)
    assert result["formal_source"]["status"] == result["weight_candidates"]["status"] == "ready"
    user_member, _ = await linked_self(client, identities["self"])
    response = await client.get(f"{ROOT}/members/{user_member}/profile-import-context", headers=identities["self"])
    assert response.status_code == 403, response.text


async def test_health_only_actor_can_read_professional_projection_without_raw_family_access(family_profile_http):  # noqa: F811
    """专业投影的独立查看权不扩张为原始家庭的坐标或正文读取权。"""
    client, sessions, identities = family_profile_http
    member, source = await linked_self(client, identities["self"])
    await grant_safety_import(client, identities["self"], member)
    imported = await client.post(
        f"{ROOT}/members/{member}/external-profile-versions", headers=identities["admin"], json=safety_body(source)
    )
    assert imported.status_code == 201, imported.text
    response = await client.get(f"{ROOT}/members/{member}/profile-import-context", headers=identities["admin"])
    assert response.status_code == 200, response.text
    result = response.json()
    assert (
        result["current_profile"]["status"] == "ready"
        and result["current_profile"]["payload"] == imported.json()["payload"]
    )
    assert result["current_profile"]["next_version"] == 2
    assert result["formal_source"]["reason"] == "family_profile_access_required"
    assert result["formal_source"]["profile"] == {} and result["formal_source"]["family_profile_source"] is None
    assert result["weight_candidates"]["items"] == []


async def test_either_missing_health_scope_denies_before_source_output(owner_context):
    """专业入口分别校验查看与编辑scope，不能由管理员身份补齐。"""
    case = owner_context
    await grant_fields(case, [*REQUIRED_PROFILE_FIELDS, "weight"])
    try:
        for scopes in (["profile_edit"], ["profile_view"], []):
            await grant_safety_import(case.client, case.identities["self"], case.member, scopes=scopes)
            response = await case.client.get(case.context_path, headers=case.identities["admin"])
            assert response.status_code == 404 and response.json()["code"] == "not_found", response.text
            assert "formal_source" not in response.json() and "weight_candidates" not in response.json()
    finally:
        await grant_safety_import(case.client, case.identities["self"], case.member)


@pytest.mark.parametrize("change", ["revoked", "expired", "identity", "inactive"])
async def test_live_family_revocation_and_source_changes_hide_raw_output(owner_context, change):
    """曾可见的实际PG来源在撤回、到期或主体变化后立即不能继续读取。"""
    case = owner_context
    await grant_fields(case, [*REQUIRED_PROFILE_FIELDS, "weight"])
    assert (await context_read(case))["weight_candidates"]["status"] == "ready"
    if change == "revoked":
        await grant_fields(case, [])
    else:
        async with case.sessions() as session:
            source = await session.get(SourceMember, case.source["source_member_id"])
            if change == "expired":
                source.grant_expires_at = utc_now_naive() - timedelta(seconds=1)
            elif change == "identity":
                source.subject_uid = "other"
            else:
                source.is_active = False
            await session.commit()
    result = await context_read(case)
    assert result["formal_source"]["family_profile_source"] is None and result["formal_source"]["profile"] == {}
    assert result["weight_candidates"]["items"] == [] and result["weight_candidates"]["total"] == 0


async def test_pagination_includes_65_day_record_and_excludes_future_voided_wrong_kind(owner_context):
    """分页计数来自同一受权过滤语义，明确较旧候选不会被近期窗口截掉。"""
    case = owner_context
    await grant_fields(case, [*REQUIRED_PROFILE_FIELDS, "weight"])
    old = await add_weight(case, value=55, measured_at=datetime.now(UTC) - timedelta(days=65))
    voided = await add_weight(case, value=70)
    response = await case.client.post(
        case.measurement_path + f"/{voided['id']}/void",
        headers=case.headers,
        json={"expected_version": 1, "reason": "合成作废"},
    )
    assert response.status_code == 200, response.text
    future = await add_weight(case, value=80)
    async with case.sessions() as session:
        row = await session.get(FamilyMeasurement, future["id"])
        row.measured_at = utc_now_naive() + timedelta(days=1)
        session.add(
            FamilyMeasurement(
                id=str(uuid4()),
                member_id=case.source["source_member_id"],
                kind="blood_pressure",
                values={"systolic": 120, "diastolic": 80},
                measured_at=utc_now_naive(),
                source="synthetic",
                created_by="self",
                creation_intent={},
            )
        )
        await session.commit()
    first = await context_read(case, params={"limit": 1, "offset": 0})
    second = await context_read(case, params={"limit": 1, "offset": 1})
    assert first["weight_candidates"]["total"] == second["weight_candidates"]["total"] == 2
    assert first["weight_candidates"]["items"][0]["record_id"] == case.record["id"]
    assert second["weight_candidates"]["items"] == [
        {
            "record_id": old["id"],
            "version": 1,
            "weight_kg": "55.0",
            "unit": "kg",
            "measured_at": old["measured_at"],
            "source": "synthetic-weight-scale",
        }
    ]


async def test_actual_corrupt_candidate_value_or_version_returns_410(owner_context):
    """损坏PG行在解析边界拒绝，不能静默转数或被当作有效候选。"""
    case = owner_context
    await grant_fields(case, [*REQUIRED_PROFILE_FIELDS, "weight"])
    try:
        for bad in ("string", "bool", "zero", "missing", "version"):
            async with case.sessions() as session:
                row = await session.get(FamilyMeasurement, case.record["id"])
                row.version = 0 if bad == "version" else 1
                row.values = {
                    "string": {"weight": "60"},
                    "bool": {"weight": True},
                    "zero": {"weight": 0},
                    "missing": {},
                    "version": {"weight": 60.0},
                }[bad]
                await session.commit()
            response = await case.client.get(case.context_path, headers=case.identities["admin"])
            assert response.status_code == 410 and response.json()["code"] == "weight_measurement_source_changed", (
                response.text
            )
            assert "weight_candidates" not in response.json()
    finally:
        async with case.sessions() as session:
            row = await session.get(FamilyMeasurement, case.record["id"])
            row.version, row.values = 1, {"weight": 60.0}
            await session.commit()


async def test_context_selection_import_preserves_source_hash_and_next_version_in_pg(owner_context):
    """上下文明确候选经现有导入核对数值/版本后，只持久化一份专业投影和独立依据。"""
    case = owner_context
    await grant_fields(case, [*REQUIRED_PROFILE_FIELDS, "weight"])
    context = await context_read(case)
    candidate = context["weight_candidates"]["items"][0]
    body = safety_body()
    body.update(
        version=context["current_profile"]["next_version"],
        family_profile_source=context["formal_source"]["family_profile_source"],
        weight_measurement_source={"record_id": candidate["record_id"], "version": candidate["version"]},
    )
    body["payload"]["weight_kg"] = candidate["weight_kg"]
    path = f"{ROOT}/members/{case.member}/external-profile-versions"
    for fault in ("version", "value"):
        bad = deepcopy(body)
        if fault == "version":
            bad["weight_measurement_source"]["version"] = 2
        else:
            bad["payload"]["weight_kg"] = "61"
        response = await case.client.post(path, headers=case.identities["admin"], json=bad)
        assert response.status_code == 409 and response.json()["code"] == "weight_measurement_source_conflict", (
            response.text
        )
    response = await case.client.post(path, headers=case.identities["admin"], json=body)
    assert response.status_code == 201, response.text
    replay = await case.client.post(path, headers=case.identities["admin"], json=body)
    assert replay.status_code == 201 and replay.json() == response.json(), replay.text
    facts = {
        "family_id": case.source["family_id"],
        "source_member_id": case.source["source_member_id"],
        "record_id": candidate["record_id"],
        "version": candidate["version"],
        "kind": "weight",
        **candidate,
    }
    expected_hash = hashlib.sha256(
        json.dumps(facts, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()
    refreshed = await context_read(case)
    assert refreshed["current_profile"]["next_version"] == 2 and refreshed["current_profile"]["status"] == "ready"
    async with case.sessions() as session:
        rows = list(
            (
                await session.scalars(
                    select(HealthProfileSnapshot).where(HealthProfileSnapshot.member_id == case.member)
                )
            ).all()
        )
        assert len(rows) == 1 and rows[0].payload["weight_kg"] == "60.0"
        assert rows[0].attestation["weight_measurement_source"]["source_hash"] == expected_hash
        assert rows[0].attestation["weight_measurement_source"]["record_id"] == candidate["record_id"]
        source = await session.get(SourceMember, case.source["source_member_id"])
        assert source.version == source.confirmed_version == 2 and "weight_kg" not in source.profile


async def context_read(case, *, params=None):
    """真实上下文响应禁止缓存，接口输出是断言依据。"""
    response = await case.client.get(case.context_path, headers=case.identities["admin"], params=params)
    assert response.status_code == 200 and response.headers["Cache-Control"] == "no-store", response.text
    return response.json()


async def grant_fields(case, fields):
    """由本人通过正式入口授予家庭owner有限期限的字段读取权。"""
    response = await case.client.put(
        case.source_path + "/authorization",
        headers=case.identities["self"],
        json={
            "fields": fields,
            "edit_fields": [],
            "purpose": "family_nutrition",
            "expires_at": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
        },
    )
    assert response.status_code == 200, response.text

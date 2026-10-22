"""真实建档保存和来源读取，保持本人确认、权限与专业边界。"""
# ruff: noqa: F811 -- pytest 按同名 fixture 参数注入。

import pytest
from datetime import datetime
from uuid import uuid4
from sqlalchemy import select

from test.integration.services.test_daily_arrangement_http import source
from test.integration.services.test_health_quality_http import proof
from test.unit.services.test_health_quality import profile_payload, rules_payload
from test.integration.services.test_health_family_safety_http import grant_safety_import, safety_body
from test.integration.services.test_health_family_profile_http import (  # noqa: F401
    family_profile_http,
    ensure_live_api_schema,
    cleanup_test_sandboxes,
    cleanup_test_knowledge_resources,
    create_health_member,
)
from yuxi.services.health_nutrition_service import input_fingerprint
from yuxi.services.health_quality_checks import projection_digest
from yuxi.storage.postgres.models_business import FamilyMember
from yuxi.storage.postgres.models_health import HealthProfileSnapshot, HealthRuleSnapshot
from yuxi.storage.postgres.models_knowledge import Base as KnowledgeSchema, KnowledgeBase, KnowledgeFile
from yuxi.services.health_source_types import knowledge_source_reference
from yuxi.utils.datetime_utils import utc_now_naive

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def onboarded_link(client, users):
    """正式 HTTP 建档后建立本人来源，返回真实持久化版本。"""
    family, path, data, headers = await source(client, users["self"])
    saved = await client.post(path, headers=headers, json=data)
    assert saved.status_code == 200, saved.text
    saved = (await client.get(path, headers=users["self"])).json()
    source_id = saved["selfMemberId"]
    member = next(item for item in saved["members"] if item["id"] == source_id)
    health_id = await create_health_member(client, users["self"])
    link = {"family_id": family["id"], "source_member_id": source_id, "confirmed_identity": True}
    response = await client.post(
        f"/api/health/v1/members/{health_id}/family-profile-link", headers=users["self"], json=link
    )
    assert response.status_code == 200, response.text
    return health_id, link, member["version"]


async def test_first_professional_import_uses_independent_version_after_onboarding(family_profile_http):
    """自述建档版本不占用专业版本；首次导入从 1 开始并持久化。"""
    client, sessions, users = family_profile_http
    health_id, link, version = await onboarded_link(client, users)
    assert version > 1
    await grant_safety_import(client, users["self"], health_id)
    path = f"/api/health/v1/members/{health_id}"
    context = await client.get(path + "/profile-import-context", headers=users["admin"])
    assert context.status_code == 200, context.text
    current = context.json()["current_profile"]
    assert current["next_version"] == 1 and current["version"] is None
    body = safety_body(link, version=current["next_version"], confirmed_version=version)
    response = await client.post(path + "/external-profile-versions", headers=users["admin"], json=body)
    assert response.status_code == 201, response.text
    async with sessions() as db:
        rows = list(
            (await db.scalars(select(HealthProfileSnapshot).where(HealthProfileSnapshot.member_id == health_id))).all()
        )
        assert len(rows) == 1 and rows[0].version == 1
    refreshed = await client.get(path + "/profile-import-context", headers=users["admin"])
    assert refreshed.json()["current_profile"]["next_version"] == 2


@pytest.mark.parametrize("change", ["digest", "deleted"])
async def test_reported_coding_checks_current_knowledge_original(family_profile_http, monkeypatch, change):
    """合成有效编码来源的原件修改或删除后，既有规则不得继续用于自述投影。"""
    client, sessions, users = family_profile_http
    health_id, _, _ = await onboarded_link(client, users)
    code, kb_id, file_id = (str(uuid4()) for _ in range(3))
    monkeypatch.setenv("HEALTH_DAILY_RULE_CODE", code)
    payload, attestation = rules_payload(), proof()
    payload["miniapp_profile_codes"] = {"population_age_ranges": {"18:130": "synthetic_adult"}}
    attestation["source_ref"] = knowledge_source_reference(kb_id, file_id, "a" * 64)
    async with sessions() as db:
        connection = await db.connection()
        await connection.run_sync(KnowledgeSchema.metadata.create_all)
        db.add(KnowledgeBase(kb_id=kb_id, name="合成编码来源", kb_type="milvus", created_by="admin"))
        await db.flush()
        db.add(
            KnowledgeFile(
                kb_id=kb_id,
                file_id=file_id,
                filename="合成规则.md",
                file_size=1,
                status="indexed",
                content_hash="a" * 64,
            )
        )
        db.add(
            HealthRuleSnapshot(
                id=str(uuid4()),
                rule_code=code,
                version=1,
                payload=payload,
                attestation=attestation,
                content_hash=projection_digest("rules", code, 1, payload, attestation),
                attested_at=datetime.fromisoformat(attestation["attested_at"]).replace(tzinfo=None),
                valid_until=datetime.fromisoformat(attestation["valid_until"]).replace(tzinfo=None),
                imported_by="admin",
            )
        )
        await db.commit()
    path = f"/api/health/v1/members/{health_id}/external-profile-versions/current"
    response = await client.get(path, headers=users["self"])
    assert response.status_code == 200 and response.json()["status"] == "ready", response.text
    assert response.json()["source_kind"] == "user_reported"
    async with sessions() as db:
        file = await db.scalar(select(KnowledgeFile).where(KnowledgeFile.file_id == file_id))
        if change == "deleted":
            await db.delete(file)
        else:
            file.content_hash = "b" * 64
        await db.commit()
    response = await client.get(path, headers=users["self"])
    assert response.status_code == 200, response.text
    value = response.json()
    assert value["status"] == "not_ready" and value["reason"] == "profile_coding_rules_unavailable"
    assert value["payload"] is None and value["attestation"] is None


async def test_confirmed_onboarding_without_cuisine_keeps_source_and_rejects_stale_or_foreign(family_profile_http):
    """空菜系原样持久化；自述缺规则不就绪，编辑后旧确认不能继续消费。"""
    client, sessions, users = family_profile_http
    family, path, data, headers = await source(client, users["self"])
    for member in data["members"]:
        member["dietary"]["cuisines"] = []
    result = await client.post(path, headers=headers, json=data)
    assert result.status_code == 200, result.text
    saved = (await client.get(path, headers=users["self"])).json()
    assert saved["onboarded"] is True
    source_id = saved["selfMemberId"]
    async with sessions() as db:
        member = await db.get(FamilyMember, source_id)
        assert member.profile["dietary_details"]["cuisines"] == []
        assert member.version == member.confirmed_version
        version, digest = member.version, input_fingerprint(member.profile)
    health_id = await create_health_member(client, users["self"])
    linked = await client.post(
        f"/api/health/v1/members/{health_id}/family-profile-link",
        headers=users["self"],
        json={
            "family_id": family["id"],
            "source_member_id": source_id,
            "confirmed_identity": True,
        },
    )
    assert linked.status_code == 200, linked.text
    projection = f"/api/health/v1/members/{health_id}/external-profile-versions/current"
    read = await client.get(projection, headers=users["self"])
    assert read.status_code == 200, read.text
    value = read.json()
    assert (value["id"], value["version"], value["content_hash"]) == (source_id, version, digest)
    assert value["status"] == "not_ready" and value["reason"] == "profile_coding_rules_unavailable"
    assert value["source_kind"] == "user_reported" and value["payload"] is None and value["attestation"] is None
    for actor in ["other", "admin"]:
        assert (await client.get(projection, headers=users[actor])).status_code == 404
    edited = await client.put(
        f"/api/family/{family['id']}/members/{source_id}",
        headers=users["self"],
        json={
            "expected_version": version,
            "profile": {"birth_date": "1991-01-01"},
        },
    )
    assert edited.status_code == 200, edited.text
    rejected = await client.get(projection, headers=users["self"])
    assert rejected.status_code == 200 and rejected.json()["reason"] == "family_profile_unconfirmed"
    assert rejected.json()["status"] == "not_ready" and rejected.json()["payload"] is None
    async with sessions() as db:
        assert (
            await db.scalar(select(HealthProfileSnapshot).where(HealthProfileSnapshot.member_id == health_id)) is None
        )


async def test_revoked_professional_snapshot_cannot_fall_back_to_reported_source(family_profile_http):
    """专业快照撤回后仍返回失效，不转为当前自述绕过审核。"""
    client, sessions, users = family_profile_http
    family, path, data, headers = await source(client, users["self"])
    saved = await client.post(path, headers=headers, json=data)
    assert saved.status_code == 200, saved.text
    health_id = await create_health_member(client, users["self"])
    link = await client.post(
        f"/api/health/v1/members/{health_id}/family-profile-link",
        headers=users["self"],
        json={
            "family_id": family["id"],
            "source_member_id": saved.json()["selfMemberId"],
            "confirmed_identity": True,
        },
    )
    assert link.status_code == 200, link.text
    body, attestation = profile_payload(), proof()
    async with sessions() as db:
        db.add(
            HealthProfileSnapshot(
                id=str(uuid4()),
                member_id=health_id,
                version=1,
                payload=body,
                attestation=attestation,
                content_hash=projection_digest("profile", health_id, 1, body, attestation),
                revoked_at=utc_now_naive(),
                attested_at=datetime.fromisoformat(attestation["attested_at"]).replace(tzinfo=None),
                valid_until=datetime.fromisoformat(attestation["valid_until"]).replace(tzinfo=None),
                imported_by="admin",
            )
        )
        await db.commit()
    response = await client.get(
        f"/api/health/v1/members/{health_id}/external-profile-versions/current", headers=users["self"]
    )
    assert response.status_code == 200, response.text
    value = response.json()
    assert value["status"] == "not_ready" and value["reason"] == "revoked"
    assert value["payload"] is None and value["attestation"] is None
    assert value.get("source_kind") != "user_reported"

"""真实 HTTP/PG 验证代建报告不能升级 AI 授权，明确同意才转交来源。"""

# ruff: noqa: F401,F811 -- 复用独立真实 TCP/PG fixture。
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy import select

from test.integration.services.test_health_family_profile_http import (
    cleanup_test_knowledge_resources,
    cleanup_test_sandboxes,
    ensure_live_api_schema,
    family_profile_http,
)
from yuxi.repositories.health_vision_repository import HealthVisionRepository
from yuxi.services.health_vision_types import FAMILY_REPORT_SCOPES, HEALTH_SCOPES, HealthVisionError
from yuxi.services.miniapp_planning_source import bind_submitted_profile
from yuxi.storage.postgres.models_business import FamilyArchive, FamilyMember as SourceMember
from yuxi.storage.postgres.models_health import FamilyMember, HealthFamilyProfileLink, HealthGrant

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def reported_member(fixture, subject_uid):
    """精确模拟已部署的代建关联和旧授权，不假定其代表本人同意。"""
    client, sessions, users = fixture
    response = await client.post("/api/family", headers=users["self"], json={"name": "合成报告家庭"})
    assert response.status_code == 200, response.text
    family_id, source_id, health_id = response.json()["id"], str(uuid4()), str(uuid4())
    async with sessions.begin() as db:
        db.add(
            SourceMember(
                id=source_id,
                family_id=family_id,
                subject_uid=subject_uid,
                name="合成家人",
                relationship="母亲",
                profile={},
                version=1,
            )
        )
        db.add(FamilyMember(id=health_id, owner_uid="self", display_name="合成家人", relationship_label="母亲"))
        await db.flush()
        db.add(
            HealthFamilyProfileLink(
                member_id=health_id,
                source_member_id=source_id,
                family_id=family_id,
                actor_uid="self",
                source_kind="miniapp_reported",
            )
        )
        for actor in ("self", "other", "admin"):
            db.add(HealthGrant(member_id=health_id, actor_uid=actor, scopes=sorted(HEALTH_SCOPES)))
    return family_id, source_id, health_id


@pytest.mark.parametrize("subject_uid", [None, "other"])
async def test_report_creator_cannot_upgrade_or_use_unconfirmed_processing(family_profile_http, subject_uid):
    """未认领及已认领旧对象都拒绝代建者和其历史第三方 AI grant，保留报告访问。"""
    client, sessions, users = family_profile_http
    _, _, health_id = await reported_member(family_profile_http, subject_uid)
    response = await client.put(
        f"/api/health/v1/members/{health_id}/grants",
        headers=users["self"],
        json={"actor_uid": "self", "scopes": ["ai_use"]},
    )
    assert response.status_code == 404, response.text
    async with sessions() as db:
        repo = HealthVisionRepository(db)
        for actor in ("self", "admin"):
            with pytest.raises(HealthVisionError, match="not_found"):
                await repo.authorize(health_id, actor, "ai_use")
        assert (await repo.authorize(health_id, "self", "report_view")).id == health_id
        assert (await db.get(HealthGrant, (health_id, "self"))).scopes == sorted(HEALTH_SCOPES)


async def test_explicit_subject_consent_revokes_every_creator_issued_grant(family_profile_http, monkeypatch):
    """本人明确分析后才转交身份，旧代建者和第三方处理授权均撤销。"""
    _, sessions, _ = family_profile_http
    family_id, source_id, health_id = await reported_member(family_profile_http, "other")
    from yuxi.services.health_vision_service import health_vision_service

    monkeypatch.setattr(
        health_vision_service,
        "configuration",
        AsyncMock(
            return_value={
                "policy_version": "synthetic-v1",
                "consultation": {"available": True, "processor": "synthetic-processor"},
            }
        ),
    )
    async with sessions.begin() as db:
        family = await db.get(FamilyArchive, family_id)
        source = await db.get(SourceMember, source_id)
        await bind_submitted_profile(
            db,
            "other",
            family,
            [source],
            {"purpose": "consultation", "processor": "synthetic-processor", "policy_version": "synthetic-v1"},
        )
    async with sessions() as db:
        member = await db.get(FamilyMember, health_id)
        link = await db.get(HealthFamilyProfileLink, health_id)
        assert member.owner_uid == link.actor_uid == "other"
        assert member.relationship_label == "本人"
        repo = HealthVisionRepository(db)
        assert (await repo.authorize(health_id, "other", "ai_use")).id == health_id
        for actor in ("self", "admin"):
            assert (await db.get(HealthGrant, (health_id, actor))).revoked_at is not None
            with pytest.raises(HealthVisionError, match="not_found"):
                await repo.authorize(health_id, actor, "ai_use")
        assert (await repo.authorize(health_id, "self", "report_view")).id == health_id


async def test_subject_can_explicitly_delegate_after_processing_ownership_matches(family_profile_http):
    """有效来源拥有者仍可显式授权其他账号，不因家庭关系默认加权。"""
    client, sessions, users = family_profile_http
    _, _, health_id = await reported_member(family_profile_http, "other")
    async with sessions.begin() as db:
        (await db.get(FamilyMember, health_id)).owner_uid = "other"
        (await db.get(HealthFamilyProfileLink, health_id)).actor_uid = "other"
    response = await client.put(
        f"/api/health/v1/members/{health_id}/grants",
        headers=users["other"],
        json={"actor_uid": "self", "scopes": ["ai_use"]},
    )
    assert response.status_code == 200, response.text
    async with sessions() as db:
        assert (await HealthVisionRepository(db).authorize(health_id, "self", "ai_use")).id == health_id

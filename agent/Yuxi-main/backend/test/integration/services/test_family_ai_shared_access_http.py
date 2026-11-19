"""真实 HTTP 和 PostgreSQL 验证家庭共享 AI 权限，不调用真实模型。"""

# ruff: noqa: F401,F811 -- 独立 TCP/PG fixture，禁用测试框架的外部资源清理。
import asyncio
from copy import deepcopy
from datetime import date, datetime
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from test.integration.services.test_daily_arrangement_http import source
from test.integration.services.test_onboarding_preparation_http import (
    family_profile_http,
    ensure_live_api_schema,
    cleanup_test_sandboxes,
    cleanup_test_knowledge_resources,
    isolate_delivery,
    POLICY,
)
from yuxi.repositories.health_vision_repository import HealthVisionRepository
from yuxi.repositories.health_consultation_repository import HealthConsultationRepository
from yuxi.repositories.health_family_profile_repository import HealthFamilyProfileRepository
from yuxi.repositories.health_weight_repository import HealthWeightRepository
from yuxi.services.reference_meal_plan_service import reference_context_in_session
from yuxi.services.health_vision_types import HealthVisionError, FAMILY_SHARED_SCOPES
from yuxi.storage.postgres.models_business import FamilyMember as SourceMember
from yuxi.storage.postgres.models_health import (
    FamilyMember,
    HealthFamilyProfileLink,
    HealthGrant,
    HealthProcessingConsent,
)

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.fixture(autouse=True)
def recipe_configuration(monkeypatch, isolate_delivery):
    """使用合成菜谱库配置，不访问生产资料库。"""
    monkeypatch.setenv("HEALTH_RECIPE_KB_ID", "synthetic-family-ai-kb")
    from yuxi.services.health_vision_service import health_vision_service

    original = health_vision_service.configuration

    async def configuration(db=None):
        policy = await original(db)
        policy["meal"] = dict(policy["meal_plan"])
        return policy

    monkeypatch.setattr(health_vision_service, "configuration", configuration)


async def shared_family(fixture, *, adult=False):
    """仅经正式接口保存代建档案、加入家庭；不为目标成员确认 AI 同意。"""
    client, sessions, users = fixture
    family, path, body, headers = await source(client, users["self"])
    for member in body["members"]:
        member["activity_level"] = "light"
    if adult:
        body["members"][1]["birth_date"] = "1960-01-01"
    saved = await client.post(path, headers=headers, json=body)
    assert saved.status_code == 200, saved.text
    target = next(row for row in saved.json()["members"] if not row["isSelf"])
    invite = await client.post(f"/api/family/{family['id']}/invite", headers=users["self"])
    joined = await client.post("/api/family/join", headers=users["other"], json={"code": invite.json()["code"]})
    assert joined.status_code == 200, joined.text
    return family["id"], target, path


@pytest.mark.parametrize("adult", [True, False], ids=["unclaimed-adult", "child-without-guardian"])
async def test_owner_and_ordinary_member_use_unclaimed_archive_without_ai_grants(family_profile_http, adult):
    """代建成人和儿童都可由两位家人配餐，身份和档案归属始终保持。"""
    client, sessions, users = family_profile_http
    fid, target, path = await shared_family(family_profile_http, adult=adult)
    hid, mid = target["healthMemberId"], target["id"]
    async with sessions() as db:
        health = await db.get(FamilyMember, hid)
        owner = health.owner_uid
        assert not await db.scalar(
            select(func.count()).select_from(HealthProcessingConsent).where(HealthProcessingConsent.member_id == hid)
        )
        member = await db.get(SourceMember, mid)
        assert member.subject_uid is None and member.guardian_status != "approved"
    selection = {
        "mode": "reference",
        "family_id": fid,
        "plan_date": date.today().isoformat(),
        "participant_ids": [mid],
        "meal_types": ["breakfast"],
    }
    for uid in ["self", "other", "self"]:
        visible = await client.get("/api/health/v1/members", headers=users[uid])
        assert visible.status_code == 200, visible.text
        entry = next(row for row in visible.json() if row["id"] == hid)
        assert FAMILY_SHARED_SCOPES <= set(entry["scopes"])
        consent = await client.get(
            f"/api/health/v1/members/{hid}/processing-consents",
            headers=users[uid],
            params={"purpose": "meal"},
        )
        assert consent.status_code == 200 and consent.json()["accepted"] is True, consent.text
        profile = await client.get(f"/api/health/v1/members/{hid}/family-profile", headers=users[uid])
        assert profile.status_code == 200 and profile.json()["status"] == "ready", profile.text
        async with sessions.begin() as db:
            context = await reference_context_in_session(db, uid, hid, selection)
            assert [row["id"] for row in context["members"]] == [mid]
            await HealthConsultationRepository(db).authorize_indicator_member(uid, hid)
            weights = await HealthWeightRepository(db).read(uid, hid)
            assert weights["source_member_id"] == mid
            for purpose in ["meal_plan", "diet_analysis", "report", "meal"]:
                await HealthVisionRepository(db).require_consent(hid, uid, purpose, POLICY)
        # 兼容旧客户端的“开始分析”也允许家人操作，不修改档案归属。
        current = (await client.get(path, headers=users[uid])).json()
        member = next(row for row in current["members"] if row["id"] == mid)
        key = str(uuid4())
        response = await client.post(
            path,
            headers={**users[uid], "Idempotency-Key": key},
            json={
                "action": "start_analysis",
                "client_request_id": key,
                "member_id": mid,
                "expected_version": member["version"],
                "accepted": True,
                "purpose": "meal_plan",
                **POLICY,
            },
        )
        assert response.status_code == 200, response.text
        async with sessions() as db:
            assert (await db.get(FamilyMember, hid)).owner_uid == owner
            assert (await db.get(HealthFamilyProfileLink, hid)).member_id == hid
            grants = (await db.scalars(select(HealthGrant).where(HealthGrant.member_id == hid))).all()
            assert all("ai_use" not in row.scopes for row in grants)


async def test_shared_access_rechecks_foreign_account_and_departure(family_profile_http):
    """有旧账号 grant 也不能绕过家庭退出或跨家庭访问。"""
    client, sessions, users = family_profile_http
    fid, target, _ = await shared_family(family_profile_http)
    hid = target["healthMemberId"]
    for uid in ["admin"]:
        denied = await client.get(f"/api/health/v1/members/{hid}/family-profile", headers=users[uid])
        assert denied.status_code == 404, denied.text
    async with sessions.begin() as db:
        actor = await db.scalar(
            select(SourceMember).where(SourceMember.family_id == fid, SourceMember.subject_uid == "other")
        )
        actor.is_active = False
        db.add(HealthGrant(member_id=hid, actor_uid="other", scopes=list(FAMILY_SHARED_SCOPES)))
    denied = await client.get(f"/api/health/v1/members/{hid}/family-profile", headers=users["other"])
    assert denied.status_code == 404, denied.text
    async with sessions() as db:
        with pytest.raises(HealthVisionError):
            await HealthVisionRepository(db).require_consent(hid, "other", "meal_plan", POLICY)


async def test_incomplete_shared_archive_returns_named_profile_error(family_profile_http):
    """资料错误不再伪装为本人未授权。"""
    _, sessions, _ = family_profile_http
    fid, target, _ = await shared_family(family_profile_http)
    async with sessions.begin() as db:
        member = await db.get(SourceMember, target["id"])
        member.profile = {**member.profile, "birth_date": None}
    async with sessions() as db:
        with pytest.raises(HealthVisionError) as error:
            await reference_context_in_session(
                db,
                "other",
                target["healthMemberId"],
                {
                    "mode": "reference",
                    "family_id": fid,
                    "plan_date": date.today().isoformat(),
                    "participant_ids": [target["id"]],
                    "meal_types": ["breakfast"],
                },
            )
        assert error.value.code == "profile_incomplete"
        assert target["name"] in error.value.message and "出生日期" in error.value.message


async def test_legacy_source_survives_creator_departure_and_requires_no_subject_confirmation(family_profile_http):
    """旧 self_confirmed 来源不依赖最初建档人仍在家庭，不代替专业审核。"""
    client, sessions, users = family_profile_http
    fid, target, _ = await shared_family(family_profile_http)
    hid, mid = target["healthMemberId"], target["id"]
    async with sessions.begin() as db:
        link = await db.get(HealthFamilyProfileLink, hid)
        link.source_kind = "self_confirmed"
        member = await db.get(SourceMember, mid)
        member.confirmed_version = None
        creator = await db.scalar(
            select(SourceMember).where(SourceMember.family_id == fid, SourceMember.subject_uid == "self")
        )
        creator.is_active = False
    response = await client.get(f"/api/health/v1/members/{hid}/family-profile", headers=users["other"])
    assert response.status_code == 200 and response.json()["status"] == "ready", response.text
    async with sessions.begin() as db:
        fact = await HealthFamilyProfileRepository(db).confirmed_source(hid)
        assert fact["source_member_id"] == mid
        await reference_context_in_session(
            db,
            "other",
            hid,
            {
                "mode": "reference",
                "family_id": fid,
                "plan_date": date.today().isoformat(),
                "participant_ids": [mid],
                "meal_types": ["breakfast"],
            },
        )
        assert (await db.get(FamilyMember, hid)).owner_uid == "self"


async def test_legacy_missing_link_is_repaired_once_for_two_family_accounts(family_profile_http):
    """并发读取历史代建档案只补一份关联，不要求邀请或重建档案。"""
    client, sessions, users = family_profile_http
    fid, target, path = await shared_family(family_profile_http)
    mid = str(uuid4())
    async with sessions.begin() as db:
        original = await db.get(SourceMember, target["id"])
        db.add(
            SourceMember(
                id=mid, family_id=fid, name="历史代建家人", relationship="家人", profile=original.profile, version=1
            )
        )
    replies = await asyncio.gather(*(client.get(path, headers=users[uid]) for uid in ["self", "other"]))
    assert all(response.status_code == 200 for response in replies), [response.text for response in replies]
    ids = {
        next(row for row in response.json()["members"] if row["id"] == mid)["healthMemberId"] for response in replies
    }
    assert len(ids) == 1 and None not in ids
    async with sessions() as db:
        assert (
            await db.scalar(
                select(func.count())
                .select_from(HealthFamilyProfileLink)
                .where(HealthFamilyProfileLink.source_member_id == mid)
            )
            == 1
        )
    hid = ids.pop()
    async with sessions.begin() as db:
        member = await db.get(SourceMember, mid)
        member.is_active = False
    denied = await client.get(f"/api/health/v1/members/{hid}/family-profile", headers=users["other"])
    assert denied.status_code == 404, denied.text


async def test_real_reference_task_entry_for_unclaimed_relative_from_both_family_accounts(
    family_profile_http, monkeypatch
):
    """真实 task-entries 经固定选择服务创建会话，目标成员没有 AI grant 或用途同意。"""
    from test.integration.services.test_reference_meal_plan_http import setup_reference

    client, sessions, users, _, _, choice = await setup_reference(family_profile_http, monkeypatch)
    fid = choice["family_id"]
    body = deepcopy(sessions.reference_profile_input)
    body["client_request_id"] = str(uuid4())
    relative = deepcopy(body["members"][0])
    relative.pop("member_id")
    relative.pop("version", None)
    relative.update(client_ref="relative", name="代建妈妈", relation="母亲", birth_date="1960-01-01")
    body["members"].append(relative)
    body["default_diners"] = ["relative"]
    saved = await client.post(
        f"/api/family/{fid}/miniapp-profile",
        headers={**users["self"], "Idempotency-Key": body["client_request_id"]},
        json=body,
    )
    assert saved.status_code == 200, saved.text
    target = next(row for row in saved.json()["members"] if row["name"] == "代建妈妈")
    invite = await client.post(f"/api/family/{fid}/invite", headers=users["self"])
    joined = await client.post("/api/family/join", headers=users["other"], json={"code": invite.json()["code"]})
    assert joined.status_code == 200, joined.text
    for uid in ["self", "other"]:
        key = str(uuid4())
        response = await client.post(
            f"/api/health/v1/members/{target['healthMemberId']}/task-entries",
            headers={**users[uid], "Idempotency-Key": key},
            json={
                "task_type": "reference_meal_preview",
                "client_request_id": key,
                "selection": {
                    **choice,
                    "participant_ids": [target["id"]],
                },
            },
        )
        assert response.status_code == 200 and response.json()["entry_status"] == "ready", response.text
        assert response.json()["member_id"] == target["healthMemberId"]
    async with sessions() as db:
        assert not await db.scalar(
            select(func.count())
            .select_from(HealthProcessingConsent)
            .where(HealthProcessingConsent.member_id == target["healthMemberId"])
        )


async def test_automatic_family_link_never_absorbs_an_independent_private_archive(family_profile_http):
    """家庭补关联不复活独立档案已撤回的授权，也不把独立对象分享给家人。"""
    client, sessions, users = family_profile_http
    created = await client.post(
        "/api/health/v1/members",
        headers=users["self"],
        json={
            "display_name": "独立私有本人",
            "relationship_label": "本人",
            "authorized": True,
        },
    )
    assert created.status_code == 201, created.text
    hid = created.json()["id"]
    async with sessions.begin() as db:
        grant = await db.get(HealthGrant, (hid, "self"))
        grant.scopes = []
        grant.revoked_at = datetime(2026, 1, 1)
        db.add(
            HealthProcessingConsent(
                member_id=hid,
                actor_uid="self",
                purpose="meal_plan",
                processor="private-original",
                policy_version="private-policy",
                revoked_at=datetime(2026, 1, 1),
            )
        )
    _, _, path = await shared_family(family_profile_http)
    for uid in ["self", "other"]:
        read = await client.get(path, headers=users[uid])
        assert read.status_code == 200, read.text
        assert hid not in [member["healthMemberId"] for member in read.json()["members"]]
    visible = await client.get("/api/health/v1/members", headers=users["other"])
    assert hid not in [row["id"] for row in visible.json()]
    async with sessions() as db:
        assert await db.get(HealthFamilyProfileLink, hid) is None
        grant = await db.get(HealthGrant, (hid, "self"))
        assert grant.scopes == [] and grant.revoked_at == datetime(2026, 1, 1)
        record = await db.get(HealthProcessingConsent, (hid, "self", "meal_plan"))
        assert record.processor == "private-original" and record.revoked_at == datetime(2026, 1, 1)

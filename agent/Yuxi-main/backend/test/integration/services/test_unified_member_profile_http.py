"""统一成员档案通过真实 HTTP 和独立 PostgreSQL 验证授权、幂等与历史兼容。"""
# ruff: noqa: F811 -- pytest 注入共享隔离 fixture。

import asyncio
from datetime import date, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from test.integration.services.test_health_family_profile_http import (  # noqa: F401
    family_profile_http,
    ensure_live_api_schema,
    cleanup_test_sandboxes,
    cleanup_test_knowledge_resources,
    create_health_member,
)
from test.integration.services.test_daily_arrangement_http import source
from yuxi.services.health_vision_service import health_vision_service
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.services.miniapp_planning_source import submitted_profile_projection
from yuxi.storage.postgres.models_business import FamilyMember as SourceMember
from yuxi.storage.postgres.models_health import (
    FamilyMember,
    HealthFamilyProfileLink,
    HealthGrant,
    HealthProcessingConsent,
    HealthMiniappProfileReceipt,
    HealthProfileSnapshot,
)
from yuxi.utils.datetime_utils import utc_now_naive

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]
POLICY = {"processor": "synthetic-processor", "policy_version": "synthetic-policy"}


@pytest.fixture(autouse=True)
def configured(monkeypatch):
    """不调用真实模型，仅提供已批准处理方的协议替身。"""

    async def config(session=None):
        return {
            "consultation": {"available": True, **POLICY},
            "meal_plan": {"available": True, **POLICY},
            "policy_version": POLICY["policy_version"],
        }

    monkeypatch.setattr(health_vision_service, "configuration", config)


async def saved_source(client, users):
    """普通建档不附加分析同意。"""
    family, path, body, headers = await source(client, users["self"])
    response = await client.post(path, headers=headers, json=body)
    assert response.status_code == 200, response.text
    data = response.json()
    member = next(row for row in data["members"] if row["id"] == data["selfMemberId"])
    return family, path, member, data


def analysis(member, **changes):
    """确认内容仅引用已保存成员及版本。"""
    return {
        "action": "start_analysis",
        "client_request_id": str(uuid4()),
        "member_id": member["id"],
        "expected_version": member["version"],
        "accepted": True,
        "purpose": "consultation",
        **POLICY,
        **changes,
    }


async def submit(client, path, headers, body):
    """使用 HTTP 幂等头提交原请求。"""
    return await client.post(path, headers={**headers, "Idempotency-Key": body["client_request_id"]}, json=body)


async def test_concurrent_confirmation_and_withdrawn_replay(family_profile_http):
    """并发只有一个来源；旧成功请求与普通编辑均不能恢复撤回的用途同意。"""
    client, sessions, users = family_profile_http
    family, path, member, _ = await saved_source(client, users)
    body = analysis(member)
    responses = await asyncio.gather(*(submit(client, path, users["self"], body) for _ in range(2)))
    assert all(r.status_code == 200 for r in responses), [r.text for r in responses]
    health_id = next(m["healthMemberId"] for m in responses[0].json()["members"] if m["id"] == member["id"])
    async with sessions() as db:
        assert await db.scalar(select(func.count()).select_from(FamilyMember)) == 1
        assert await db.scalar(select(func.count()).select_from(HealthFamilyProfileLink)) == 1
        assert await db.scalar(select(func.count()).select_from(HealthProcessingConsent)) == 1
        assert (await db.get(HealthProcessingConsent, (health_id, "self", "consultation"))).revoked_at is None
        assert await db.get(HealthProcessingConsent, (health_id, "self", "meal_plan")) is None
    revoked = await client.post(
        f"/api/health/v1/members/{health_id}/processing-consents",
        headers=users["self"],
        json={"purpose": "consultation", "accepted": False, **POLICY},
    )
    assert revoked.status_code == 200, revoked.text
    assert (await submit(client, path, users["self"], body)).status_code == 200
    changed = await client.put(
        f"/api/family/{family['id']}/members/{member['id']}",
        headers=users["self"],
        json={"expected_version": member["version"], "profile": {"height_cm": 166}},
    )
    assert changed.status_code == 200, changed.text
    assert (await submit(client, path, users["self"], body)).status_code == 200
    async with sessions() as db:
        assert (await db.get(HealthProcessingConsent, (health_id, "self", "consultation"))).revoked_at is not None
        m = await db.get(SourceMember, member["id"])
        assert m.confirmed_version != m.version


@pytest.mark.parametrize("candidate_count", [1, 2])
async def test_old_same_account_self_is_reused_or_conflict(family_profile_http, candidate_count):
    """已有本人只按同账号身份复用；有歧义时不增建或覆盖。"""
    client, sessions, users = family_profile_http
    _, path, member, _ = await saved_source(client, users)
    ids = [await create_health_member(client, users["self"]) for _ in range(candidate_count)]
    response = await submit(client, path, users["self"], analysis(member))
    assert response.status_code == (200 if candidate_count == 1 else 409), response.text
    async with sessions() as db:
        assert await db.scalar(select(func.count()).select_from(FamilyMember)) == candidate_count
        links = list((await db.scalars(select(HealthFamilyProfileLink))).all())
        assert len(links) == (1 if candidate_count == 1 else 0)
        if links:
            assert links[0].member_id == ids[0]


@pytest.mark.parametrize("change", [{"expected_version": 99}, {"policy_version": "obsolete"}])
async def test_wrong_version_or_policy_rolls_back(family_profile_http, change):
    """拒绝过期确认时不留下来源、同意或分析收据。"""
    client, sessions, users = family_profile_http
    _, path, member, _ = await saved_source(client, users)
    response = await submit(client, path, users["self"], analysis(member, **change))
    assert response.status_code == 409, response.text
    async with sessions() as db:
        assert await db.scalar(select(func.count()).select_from(HealthFamilyProfileLink)) == 0
        assert await db.scalar(select(func.count()).select_from(HealthProcessingConsent)) == 0
        assert await db.scalar(select(func.count()).select_from(HealthMiniappProfileReceipt)) == 1


async def test_creator_edits_claimed_relative_without_confirming_or_consent(family_profile_http):
    """创建者保存妈妈只改变妈妈，确认和分析仍由本人完成。"""
    client, sessions, users = family_profile_http
    family, path, own, saved = await saved_source(client, users)
    other = next(m for m in saved["members"] if m["id"] != own["id"])
    async with sessions() as db:
        m = await db.get(SourceMember, other["id"])
        m.subject_uid = "other"
        m.profile = {**m.profile, "birth_date": "1960-01-01"}
        m.confirmed_version = m.version
        before_own = dict((await db.get(SourceMember, own["id"])).profile)
        await db.commit()
    base = f"/api/family/{family['id']}/members/{other['id']}"
    result = await client.put(
        base, headers=users["self"], json={"expected_version": other["version"], "profile": {"height_cm": 158}}
    )
    assert result.status_code == 200, result.text
    assert result.json()["confirmed"] is False
    assert (
        await client.post(base + "/confirm", headers=users["self"], json={"expected_version": other["version"] + 1})
    ).status_code == 403
    denied = await submit(client, path, users["self"], analysis({**other, "version": other["version"] + 1}))
    assert denied.status_code == 403, denied.text
    async with sessions() as db:
        assert (await db.get(SourceMember, own["id"])).profile == before_own
        assert (await db.get(SourceMember, own["id"])).version == own["version"]
        assert await db.scalar(select(func.count()).select_from(HealthProcessingConsent)) == 0
    accepted = await submit(client, path, users["other"], analysis({**other, "version": other["version"] + 1}))
    assert accepted.status_code == 200, accepted.text


async def test_old_top_level_fields_survive_weight_only_save(family_profile_http):
    """老档案只有部分 dietary_details 时仍展示顶层过敏医嘱目标。"""
    client, sessions, users = family_profile_http
    _, path, member, _ = await saved_source(client, users)
    async with sessions() as db:
        m = await db.get(SourceMember, member["id"])
        m.profile = {
            **m.profile,
            "dietary_details": {"statedWeightKg": 58},
            "allergens": ["合成过敏原"],
            "doctor_instructions": "合成医嘱",
            "goal": "保留目标",
        }
        await db.commit()
    response = await client.get(path, headers=users["self"])
    m = next(m for m in response.json()["members"] if m["id"] == member["id"])
    assert m["weight"] == 58 and m["allergies"] == ["合成过敏原"]
    assert m["clinicianGuidance"] == "合成医嘱" and m["goals"] == ["保留目标"]


async def test_revoked_access_is_not_restored_by_analysis(family_profile_http):
    """明确分析同意不等于重新发放已撤回的访问范围。"""
    client, sessions, users = family_profile_http
    _, path, member, _ = await saved_source(client, users)
    result = await submit(client, path, users["self"], analysis(member))
    assert result.status_code == 200, result.text
    health_id = next(m["healthMemberId"] for m in result.json()["members"] if m["id"] == member["id"])
    async with sessions() as db:
        (await db.get(HealthGrant, (health_id, "self"))).revoked_at = utc_now_naive()
        await db.commit()
    assert (await submit(client, path, users["self"], analysis(member))).status_code == 403
    async with sessions() as db:
        assert (await db.get(HealthGrant, (health_id, "self"))).revoked_at is not None


async def test_existing_professional_snapshot_is_not_replaced_by_self_report(family_profile_http):
    """无关联但已有专业快照的本人对象要求核查，不能自动改为自述来源。"""
    client, sessions, users = family_profile_http
    _, path, member, _ = await saved_source(client, users)
    health_id = await create_health_member(client, users["self"])
    snapshot_id = str(uuid4())
    async with sessions() as db:
        db.add(
            HealthProfileSnapshot(
                id=snapshot_id,
                member_id=health_id,
                version=1,
                payload={"synthetic": "professional-profile"},
                content_hash="a" * 64,
                attestation={"synthetic": "professional-source"},
                attested_at=utc_now_naive(),
                valid_until=utc_now_naive() + timedelta(days=1),
                imported_by="self",
            )
        )
        await db.commit()
    response = await submit(client, path, users["self"], analysis(member))
    assert response.status_code == 409, response.text
    async with sessions() as db:
        assert await db.scalar(select(func.count()).select_from(FamilyMember)) == 1
        assert await db.get(HealthFamilyProfileLink, health_id) is None
        assert (await db.get(HealthProfileSnapshot, snapshot_id)).payload == {"synthetic": "professional-profile"}


async def test_plain_onboarding_save_keeps_consent_withdrawn(family_profile_http):
    """普通整家建档保存也不会恢复已撤回的分析同意。"""
    client, sessions, users = family_profile_http
    family, path, body, headers = await source(client, users["self"])
    saved = (await client.post(path, headers=headers, json=body)).json()
    own = next(m for m in saved["members"] if m["id"] == saved["selfMemberId"])
    result = await submit(client, path, users["self"], analysis(own))
    assert result.status_code == 200, result.text
    health_id = next(m["healthMemberId"] for m in result.json()["members"] if m["id"] == own["id"])
    revoked = await client.post(
        f"/api/health/v1/members/{health_id}/processing-consents",
        headers=users["self"],
        json={"purpose": "consultation", "accepted": False, **POLICY},
    )
    assert revoked.status_code == 200, revoked.text
    body.update(client_request_id=str(uuid4()), family_version=saved["familyVersion"])
    for draft, actual in zip(body["members"], sorted(saved["members"], key=lambda m: m["id"] != own["id"])):
        draft.update(member_id=actual["id"], version=actual["version"])
    response = await submit(client, path, users["self"], body)
    assert response.status_code == 200, response.text
    async with sessions() as db:
        assert (await db.get(HealthProcessingConsent, (health_id, "self", "consultation"))).revoked_at is not None


async def test_onboarding_self_consent_does_not_include_guardian_children(family_profile_http):
    """建档页只同意本人咨询，即使创建者也是监护人也不替儿童新增同意。"""
    client, sessions, users = family_profile_http
    _, path, body, headers = await source(client, users["self"])
    saved = (await client.post(path, headers=headers, json=body)).json()
    own = next(m for m in saved["members"] if m["id"] == saved["selfMemberId"])
    child = next(m for m in saved["members"] if m["id"] != own["id"])
    async with sessions() as db:
        m = await db.get(SourceMember, child["id"])
        m.guardian_uid, m.guardian_status, m.guardian_reviewed_by = "self", "approved", "admin"
        m.guardian_birth_date = date(2015, 1, 1)
        m.guardian_expires_at = utc_now_naive() + timedelta(days=1)
        await db.commit()
    body.update(
        client_request_id=str(uuid4()),
        family_version=saved["familyVersion"],
        analysis_consent={"purpose": "consultation", **POLICY},
    )
    for draft, actual in zip(body["members"], [own, child]):
        draft.update(member_id=actual["id"], version=actual["version"])
    response = await submit(client, path, users["self"], body)
    assert response.status_code == 200, response.text
    async with sessions() as db:
        links = list((await db.scalars(select(HealthFamilyProfileLink))).all())
        assert len(links) == 1 and links[0].source_member_id == own["id"]
        assert await db.scalar(select(func.count()).select_from(HealthProcessingConsent)) == 1


@pytest.mark.parametrize("claimed", [False, True])
async def test_guardian_source_requires_current_approval(family_profile_http, claimed):
    """有效监护人可分析已认领或未认领未成年成员，撤回后来源立即失效。"""
    client, sessions, users = family_profile_http
    _, path, own, saved = await saved_source(client, users)
    child = next(m for m in saved["members"] if m["id"] != own["id"])
    async with sessions() as db:
        m = await db.get(SourceMember, child["id"])
        m.subject_uid = "other" if claimed else None
        m.guardian_uid, m.guardian_status, m.guardian_reviewed_by = "self", "approved", "admin"
        m.guardian_birth_date = date(2015, 1, 1)
        m.guardian_expires_at = utc_now_naive() + timedelta(days=1)
        await db.commit()
    result = await submit(client, path, users["self"], analysis(child))
    assert result.status_code == 200, result.text
    async with sessions() as db:
        link = await db.scalar(
            select(HealthFamilyProfileLink).where(HealthFamilyProfileLink.source_member_id == child["id"])
        )
        projection = await submitted_profile_projection(db, link)
        assert projection["reason"] == "profile_coding_rules_unavailable"
        m = await db.get(SourceMember, child["id"])
        m.guardian_status = "revoked"
        await db.commit()
        with pytest.raises(HealthVisionError) as error:
            await submitted_profile_projection(db, link)
        assert error.value.code == "source_invalidated"


async def test_legacy_implicit_consent_rejected_without_saving_or_restoring(family_profile_http):
    """旧客户端自动附加政策不能保存资料或复活已经撤回的餐单同意。"""
    client, sessions, users = family_profile_http
    family, path, body, headers = await source(client, users["self"])
    saved = (await client.post(path, headers=headers, json=body)).json()
    own = next(m for m in saved["members"] if m["id"] == saved["selfMemberId"])
    result = await submit(client, path, users["self"], analysis(own, purpose="meal_plan"))
    assert result.status_code == 200, result.text
    health_id = next(m["healthMemberId"] for m in result.json()["members"] if m["id"] == own["id"])
    revoked = await client.post(
        f"/api/health/v1/members/{health_id}/processing-consents",
        headers=users["self"],
        json={"purpose": "meal_plan", "accepted": False, **POLICY},
    )
    assert revoked.status_code == 200, revoked.text
    async with sessions() as db:
        original = await db.get(SourceMember, own["id"])
        profile_before, version_before = dict(original.profile), original.version
        receipts_before = await db.scalar(select(func.count()).select_from(HealthMiniappProfileReceipt))
    body.update(client_request_id=str(uuid4()), family_version=saved["familyVersion"], analysis_consent=POLICY)
    for draft, actual in zip(body["members"], sorted(saved["members"], key=lambda m: m["id"] != own["id"])):
        draft.update(member_id=actual["id"], version=actual["version"], height_cm=177)
    response = await submit(client, path, users["self"], body)
    assert response.status_code == 409, response.text
    assert "更新小程序" in response.text
    async with sessions() as db:
        actual = await db.get(SourceMember, own["id"])
        assert actual.profile == profile_before and actual.version == version_before
        assert (await db.get(HealthProcessingConsent, (health_id, "self", "meal_plan"))).revoked_at is not None
        assert await db.scalar(select(func.count()).select_from(HealthMiniappProfileReceipt)) == receipts_before


async def test_legacy_completed_receipt_replays_without_restoring_withdrawal(family_profile_http):
    """升级前已完成的旧格式收据仍可回读，不重新保存或恢复已撤回的同意。"""
    from yuxi.services.health_nutrition_service import input_fingerprint
    from yuxi.services.miniapp_profile_types import MiniappProfileInput

    client, sessions, users = family_profile_http
    family, path, body, headers = await source(client, users["self"])
    saved = (await client.post(path, headers=headers, json=body)).json()
    own = next(m for m in saved["members"] if m["id"] == saved["selfMemberId"])
    result = await submit(client, path, users["self"], analysis(own, purpose="meal_plan"))
    assert result.status_code == 200, result.text
    health_id = next(m["healthMemberId"] for m in result.json()["members"] if m["id"] == own["id"])
    revoked = await client.post(
        f"/api/health/v1/members/{health_id}/processing-consents",
        headers=users["self"],
        json={"purpose": "meal_plan", "accepted": False, **POLICY},
    )
    assert revoked.status_code == 200, revoked.text
    body.update(client_request_id=str(uuid4()), analysis_consent=POLICY)
    async with sessions() as db:
        # 移植旧版本成功保存时持久化的收据格式，保留其原始指纹。
        db.add(
            HealthMiniappProfileReceipt(
                actor_uid="self",
                request_id=body["client_request_id"],
                family_id=family["id"],
                fingerprint=input_fingerprint(MiniappProfileInput.model_validate(body).model_dump(mode="json")),
                member_refs={m["id"]: m["id"] for m in saved["members"]},
            )
        )
        await db.commit()
        member = await db.get(SourceMember, own["id"])
        before = dict(member.profile), member.version
    replay = await submit(client, path, users["self"], body)
    assert replay.status_code == 200, replay.text
    async with sessions() as db:
        member = await db.get(SourceMember, own["id"])
        assert (member.profile, member.version) == before
        assert (await db.get(HealthProcessingConsent, (health_id, "self", "meal_plan"))).revoked_at is not None
    changed = {**body, "usage_mode": "个人使用"}
    assert (await submit(client, path, users["self"], changed)).status_code == 409


def automatic_open(member, **changes):
    """应用自动衔接只提交已保存成员和版本，不携带用户勾选或政策确认。"""
    return {
        "action": "open_consultation",
        "client_request_id": str(uuid4()),
        "member_id": member["id"],
        "expected_version": member["version"],
        **changes,
    }


async def test_completed_profile_opens_consultation_without_manual_consent(family_profile_http):
    """已有建档无关联时直接开启本人咨询，重复进入不重复创建或扩及配餐。"""
    client, sessions, users = family_profile_http
    _, path, member, _ = await saved_source(client, users)
    response = await submit(client, path, users["self"], automatic_open(member))
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["completeProfile"] and result["onboarded"]
    own = next(m for m in result["members"] if m["id"] == member["id"])
    assert own["healthMemberId"]
    response = await submit(client, path, users["self"], automatic_open(member))
    assert response.status_code == 200, response.text
    async with sessions() as db:
        assert await db.scalar(select(func.count()).select_from(HealthFamilyProfileLink)) == 1
        record = await db.get(HealthProcessingConsent, (own["healthMemberId"], "self", "consultation"))
        assert record and record.revoked_at is None
        assert await db.get(HealthProcessingConsent, (own["healthMemberId"], "self", "meal_plan")) is None


async def test_automatic_open_preserves_deliberate_stop(family_profile_http):
    """首次自动开启后主动停用，重新进入和普通保存不恢复停用。"""
    client, sessions, users = family_profile_http
    _, path, member, _ = await saved_source(client, users)
    body = automatic_open(member)
    response = await submit(client, path, users["self"], body)
    assert response.status_code == 200, response.text
    own = next(m for m in response.json()["members"] if m["id"] == member["id"])
    health_id = own["healthMemberId"]
    revoked = await client.post(
        f"/api/health/v1/members/{health_id}/processing-consents",
        headers=users["self"],
        json={"purpose": "consultation", "accepted": False, **POLICY},
    )
    assert revoked.status_code == 200, revoked.text
    for payload in [body, automatic_open(member)]:
        assert (await submit(client, path, users["self"], payload)).status_code == 200
    async with sessions() as db:
        assert (await db.get(HealthProcessingConsent, (health_id, "self", "consultation"))).revoked_at is not None


async def test_automatic_open_cannot_enable_another_family_member(family_profile_http):
    """创建者的自动衔接只作用本人，不能顺带为其他家人建关联或启用。"""
    client, sessions, users = family_profile_http
    _, path, own, saved = await saved_source(client, users)
    other = next(m for m in saved["members"] if m["id"] != own["id"])
    response = await submit(client, path, users["self"], automatic_open(other))
    assert response.status_code == 403, response.text
    async with sessions() as db:
        assert await db.scalar(select(func.count()).select_from(HealthFamilyProfileLink)) == 0


async def test_automatic_open_checks_current_saved_profile_and_version(family_profile_http):
    """缺少必填健康信息不能伪装就绪，旧版本也不能创建关联。"""
    client, sessions, users = family_profile_http
    _, path, own, _ = await saved_source(client, users)
    stale = await submit(client, path, users["self"], automatic_open(own, expected_version=99))
    assert stale.status_code == 409, stale.text
    async with sessions() as db:
        m = await db.get(SourceMember, own["id"])
        m.profile = {**m.profile, "birth_date": None}
        await db.commit()
    response = await submit(client, path, users["self"], automatic_open(own))
    assert response.status_code == 422, response.text
    async with sessions() as db:
        assert await db.scalar(select(func.count()).select_from(HealthFamilyProfileLink)) == 0


async def test_automatic_open_reuses_old_profile_and_does_not_override_conflict(family_profile_http):
    """新自动入口也沿用旧本人对象；多个候选时明确冲突，不重复建档。"""
    client, sessions, users = family_profile_http
    _, path, own, _ = await saved_source(client, users)
    ids = [await create_health_member(client, users["self"]) for _ in range(2)]
    response = await submit(client, path, users["self"], automatic_open(own))
    assert response.status_code == 409, response.text
    async with sessions() as db:
        assert await db.scalar(select(func.count()).select_from(FamilyMember)) == len(ids)
        assert await db.scalar(select(func.count()).select_from(HealthFamilyProfileLink)) == 0


async def test_complete_profile_after_edit_returns_to_chat_without_reconfirmation(family_profile_http):
    """本人档案更新后完整性仍满足时自动衔接，不能因旧确认版本而循环回建档。"""
    client, sessions, users = family_profile_http
    family, path, own, _ = await saved_source(client, users)
    response = await submit(client, path, users["self"], automatic_open(own))
    assert response.status_code == 200, response.text
    health_id = next(m["healthMemberId"] for m in response.json()["members"] if m["id"] == own["id"])
    update = await client.put(
        f"/api/family/{family['id']}/members/{own['id']}",
        headers=users["self"],
        json={"expected_version": own["version"], "profile": {"height_cm": 171}},
    )
    assert update.status_code == 200, update.text
    before = (await client.get(path, headers=users["self"])).json()
    assert before["completeProfile"] and not before["onboarded"]
    latest = next(m for m in before["members"] if m["id"] == own["id"])
    reopened = await submit(client, path, users["self"], automatic_open(latest))
    assert reopened.status_code == 200, reopened.text
    assert reopened.json()["onboarded"] and reopened.json()["completeProfile"]
    current = next(m for m in reopened.json()["members"] if m["id"] == own["id"])
    assert current["healthMemberId"] == health_id and current["height"] == 171

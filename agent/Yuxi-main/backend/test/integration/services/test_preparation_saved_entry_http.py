"""既有档案准备入口的真实HTTP与隔离PG回归。"""

# ruff: noqa: F401,F811
import asyncio
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select, func
from test.integration.services.test_onboarding_preparation_http import (
    family_profile_http,
    ensure_live_api_schema,
    cleanup_test_sandboxes,
    cleanup_test_knowledge_resources,
    isolate_delivery,
    input_for,
)
from yuxi.storage.postgres.models_health import HealthOnboardingPreparation, HealthMiniappProfileReceipt
from yuxi.storage.postgres.models_business import TaskRecord, FamilyMember
from yuxi.services.health_daily_service import business_date

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def saved_profile(client, user):
    """通过原HTTP完成一次真实建档，不提前建立准备。"""
    family, path, body, headers = await input_for(client, user)
    body.pop("processing_consents")
    response = await client.post(f"/api/family/{family['id']}/miniapp-profile", json=body, headers=headers)
    assert response.status_code == 200, response.text
    return family, path, body


async def start(client, path, user, key=None):
    """新入口只提交请求身份，客户端没有档案写入通道。"""
    key = key or str(uuid4())
    return await client.post(
        path + "/from-profile", json={"client_request_id": key}, headers={**user, "Idempotency-Key": key}
    )


async def test_saved_profile_parallel_entry_does_not_resave_or_requeue(family_profile_http):
    client, sessions, users = family_profile_http
    family, path, body = await saved_profile(client, users["self"])
    async with sessions() as db:
        before = (await db.get(FamilyMember, body["members"][0]["member_id"])).version
    keys = [str(uuid4()) for _ in range(3)]
    responses = await asyncio.gather(*(start(client, path, users["self"], key) for key in keys))
    assert all(r.status_code == 200 for r in responses), [r.text for r in responses]
    assert len({r.json()["id"] for r in responses}) == 1
    assert (await start(client, path, users["self"], keys[0])).json()["id"] == responses[0].json()["id"]
    for _ in range(2):
        assert (await client.get(path + "/current", headers=users["self"])).status_code == 200
    async with sessions() as db:
        assert (await db.get(FamilyMember, body["members"][0]["member_id"])).version == before
        for model in (HealthMiniappProfileReceipt, TaskRecord):
            assert await db.scalar(select(func.count()).select_from(model)) == 1
    async with sessions() as db:
        assert (
            await db.scalar(
                select(func.count())
                .select_from(HealthOnboardingPreparation)
                .where(HealthOnboardingPreparation.status != "alias")
            )
            == 1
        )
    assert (await start(client, path, users["other"])).status_code == 404


async def test_yesterday_preparation_is_retained_and_new_day_gets_new_record(family_profile_http):
    client, sessions, users = family_profile_http
    _, path, _ = await saved_profile(client, users["self"])
    first = await start(client, path, users["self"])
    old_id = first.json()["id"]
    yesterday = business_date() - timedelta(days=1)
    async with sessions() as db:
        old = await db.get(HealthOnboardingPreparation, old_id)
        old.plan_date = yesterday
        old.status = "ready"
        old.result = {"thread_id": "old-thread", "arrangement_id": "old-arrangement"}
        await db.commit()
    current = await client.get(path + "/current", headers=users["self"])
    assert current.json()["status"] == "stale" and current.json()["error_code"] == "preparation_date_changed"
    assert (await client.post(path + "/" + old_id + "/resume", headers=users["self"])).status_code == 409
    new = await start(client, path, users["self"])
    assert new.status_code == 200, new.text
    assert new.json()["id"] != old_id and new.json()["date"] == business_date().isoformat()
    async with sessions() as db:
        old = await db.get(HealthOnboardingPreparation, old_id)
        assert old.plan_date == yesterday and old.result["arrangement_id"] == "old-arrangement"
        assert await db.scalar(select(func.count()).select_from(HealthMiniappProfileReceipt)) == 1
        assert await db.scalar(select(func.count()).select_from(HealthOnboardingPreparation)) == 2


async def test_changed_saved_profile_starts_new_sources_without_resaving(family_profile_http):
    client, sessions, users = family_profile_http
    _, path, body = await saved_profile(client, users["self"])
    first = await start(client, path, users["self"])
    async with sessions() as db:
        member = await db.get(FamilyMember, body["members"][0]["member_id"])
        member.version += 1
        version = member.version
        await db.commit()
    assert (await client.get(path + "/current", headers=users["self"])).json()["status"] == "stale"
    new = await start(client, path, users["self"])
    assert new.status_code == 200, new.text
    assert new.json()["id"] != first.json()["id"]
    async with sessions() as db:
        assert (await db.get(FamilyMember, body["members"][0]["member_id"])).version == version
        assert await db.scalar(select(func.count()).select_from(HealthMiniappProfileReceipt)) == 1


async def test_saved_entry_rejects_profile_writes_and_wrong_key(family_profile_http):
    client, sessions, users = family_profile_http
    _, path, _ = await saved_profile(client, users["self"])
    key = str(uuid4())
    rejected = await client.post(
        path + "/from-profile",
        json={"client_request_id": key, "members": []},
        headers={**users["self"], "Idempotency-Key": key},
    )
    assert rejected.status_code == 422
    rejected = await client.post(
        path + "/from-profile",
        json={"client_request_id": key},
        headers={**users["self"], "Idempotency-Key": str(uuid4())},
    )
    assert rejected.status_code == 422
    async with sessions() as db:
        assert await db.scalar(select(func.count()).select_from(TaskRecord)) == 0


async def test_saved_entry_rejects_incomplete_profile_before_task_registration(family_profile_http):
    client, sessions, users = family_profile_http
    _, path, _, _ = await input_for(client, users["self"])
    response = await start(client, path, users["self"])
    assert response.status_code == 422, response.text
    assert response.json()["code"] == "profile_incomplete"
    async with sessions() as db:
        assert await db.scalar(select(func.count()).select_from(HealthOnboardingPreparation)) == 0
        assert await db.scalar(select(func.count()).select_from(TaskRecord)) == 0


@pytest.mark.parametrize("change", ["sources", "date", "family"])
async def test_reused_key_remains_bound_after_lost_response_and_context_change(family_profile_http, change):
    """命中复用也登记请求键，响应丢失后不能换档案、日期或家庭另起任务。"""
    client, sessions, users = family_profile_http
    _, path, body = await saved_profile(client, users["self"])
    first = await start(client, path, users["self"])
    key = str(uuid4())
    reused = await start(client, path, users["self"], key)
    assert reused.json()["id"] == first.json()["id"]
    if change == "family":
        from yuxi.storage.postgres.models_business import FamilyArchive

        other_id = str(uuid4())
        async with sessions() as db:
            db.add(FamilyArchive(id=other_id, owner_uid="other", name="第二合成家庭", settings={}))
            await db.flush()
            db.add(
                FamilyMember(
                    id=str(uuid4()),
                    family_id=other_id,
                    name="合成本人",
                    relationship="本人",
                    subject_uid="self",
                    profile={},
                    version=1,
                )
            )
            await db.commit()
        other_path = f"/api/family/{other_id}/onboarding-preparations"
        replay = await start(client, other_path, users["self"], key)
        assert replay.status_code == 409, replay.text
    else:
        async with sessions() as db:
            if change == "sources":
                member = await db.get(FamilyMember, body["members"][0]["member_id"])
                member.version += 1
            else:
                row = await db.get(HealthOnboardingPreparation, first.json()["id"])
                row.plan_date -= timedelta(days=1)
            await db.commit()
        replay = await start(client, path, users["self"], key)
        assert replay.json()["id"] == first.json()["id"] and replay.json()["status"] == "stale"
    async with sessions() as db:
        assert await db.scalar(select(func.count()).select_from(TaskRecord)) == 1


async def test_parallel_saved_entry_and_resume_use_one_lock_order(family_profile_http, monkeypatch):
    """协调真实事务重现旧家庭锁/准备锁倒序，修复后两种入口都正常完成。"""
    from yuxi.services import onboarding_preparation_service as service

    client, sessions, users = family_profile_http
    _, path, _ = await saved_profile(client, users["self"])
    original = await start(client, path, users["self"])
    pid = original.json()["id"]
    async with sessions() as db:
        row = await db.get(HealthOnboardingPreparation, pid)
        row.status = "failed"
        await db.commit()
    first = asyncio.Event()
    second = asyncio.Event()
    release = asyncio.Event()
    calls = 0
    original_lock = service.lock_preparation

    async def lock(db, uid, fid):
        nonlocal calls
        calls += 1
        if calls == 1:
            first.set()
            await release.wait()
            await original_lock(db, uid, fid)
        else:
            await original_lock(db, uid, fid)
            second.set()

    monkeypatch.setattr(service, "lock_preparation", lock)
    entering = asyncio.create_task(start(client, path, users["self"]))
    await asyncio.wait_for(first.wait(), 5)
    resuming = asyncio.create_task(client.post(path + "/" + pid + "/resume", headers=users["self"]))
    try:
        await asyncio.wait_for(second.wait(), 0.2)
    except TimeoutError:
        pass
    release.set()
    replies = await asyncio.wait_for(asyncio.gather(entering, resuming), 10)
    assert all(r.status_code == 200 for r in replies), [r.text for r in replies]


@pytest.mark.parametrize("revoked", [False, True])
async def test_invited_legacy_profile_handoff_preserves_revoked_grants(family_profile_http, monkeypatch, revoked):
    """真实邀请认领后完成旧来源交接；已有本人撤权记录仍拒绝恢复。"""
    from types import SimpleNamespace
    from test.integration.services.test_daily_arrangement_http import source
    from test.integration.services.test_onboarding_preparation_http import execute_preparation
    from yuxi.services import health_consultation_service, daily_arrangement_service
    from yuxi.services.health_vision_types import HealthVisionError
    from yuxi.storage.postgres.models_health import FamilyMember as HealthMember, HealthFamilyProfileLink, HealthGrant
    from yuxi.utils.datetime_utils import utc_now_naive

    client, sessions, users = family_profile_http
    family, profile_path, body, headers = await source(client, users["self"])
    body["members"][1].update(birth_date="1995-01-01", height_cm=160, weight_kg=50, sex="female")
    response = await client.post(profile_path, json=body, headers=headers)
    assert response.status_code == 200, response.text
    relative = next(m for m in response.json()["members"] if m["id"] != response.json()["selfMemberId"])
    hid = str(uuid4())
    async with sessions() as db:
        db.add(HealthMember(id=hid, owner_uid="self", display_name="合成旧来源", relationship_label="家人"))
        await db.flush()
        db.add(
            HealthFamilyProfileLink(
                member_id=hid,
                source_member_id=relative["id"],
                family_id=family["id"],
                actor_uid="self",
                source_kind="miniapp_reported",
            )
        )
        db.add(HealthGrant(member_id=hid, actor_uid="self", scopes=["ai_use", "diet_edit", "profile_view"]))
        if revoked:
            db.add(
                HealthGrant(
                    member_id=hid,
                    actor_uid="other",
                    scopes=["ai_use", "diet_edit", "profile_view"],
                    revoked_at=utc_now_naive(),
                )
            )
        await db.commit()
    invite = await client.post(f"/api/family/{family['id']}/members/{relative['id']}/invite", headers=users["self"])
    assert invite.status_code == 200, invite.text
    joined = await client.post("/api/family/join", headers=users["other"], json={"code": invite.json()["code"]})
    assert joined.status_code == 200, joined.text

    async def consultation(*args, **kwargs):
        return {"thread_id": "synthetic-no-model-thread"}

    async def stop_before_model(*args, **kwargs):
        raise HealthVisionError("daily_rules_unavailable", "合成规则缺失", 503)

    monkeypatch.setattr(health_consultation_service, "create_daily_consultation", consultation)
    monkeypatch.setattr(daily_arrangement_service, "start_daily_arrangement", stop_before_model)
    path = f"/api/family/{family['id']}/onboarding-preparations"
    prepared = await start(client, path, users["other"])
    assert prepared.status_code == 200, prepared.text
    await execute_preparation(prepared.json()["id"], sessions, monkeypatch)
    async with sessions() as db:
        link = await db.get(HealthFamilyProfileLink, hid)
        grant = await db.get(HealthGrant, (hid, "other"))
        row = await db.get(HealthOnboardingPreparation, prepared.json()["id"])
        if revoked:
            assert row.error_code == "processing_consent_revoked"
            assert grant.revoked_at is not None and link.actor_uid == "self"
        else:
            assert row.error_code == "daily_rules_unavailable"
            assert link.actor_uid == "other" and grant.revoked_at is None
            assert (await db.get(HealthMember, hid)).owner_uid == "other"
            assert (await db.get(HealthGrant, (hid, "self"))).revoked_at is not None

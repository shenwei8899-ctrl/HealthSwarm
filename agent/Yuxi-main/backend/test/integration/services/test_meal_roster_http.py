"""真实 TCP 与独立 PostgreSQL 验证名单更新、用餐确认及旧结果拒绝。"""

# ruff: noqa: F401,F811
from copy import deepcopy
from datetime import datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select, func

from test.integration.services.test_daily_arrangement_http import source
from test.integration.services.test_onboarding_preparation_http import (
    family_profile_http,
    ensure_live_api_schema,
    cleanup_test_sandboxes,
    cleanup_test_knowledge_resources,
    isolate_delivery,
)
from yuxi.services.meal_roster_service import verify_roster_publish, roster_targets
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.storage.postgres.models_health import HealthDailyMealPlan
from yuxi.storage.postgres.models_business import TaskRecord

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def setup_rows(fixture):
    """保存两名合成成员，以原本人名单创建历史、今日和未来快照。"""
    client, sessions, users = fixture
    family, path, body, headers = await source(client, users["self"])
    body["default_diners"] = ["self"]
    response = await client.post(path, json=body, headers=headers)
    assert response.status_code == 200, response.text
    profile = response.json()
    today = datetime.now(ZoneInfo("Asia/Shanghai")).date()
    mid = profile["selfMemberId"]
    archive = {
        m: {"meal_type": m, "members": [{"id": mid, "name": "合成本人"}], "dishes": [{"id": "dish", "name": "合成菜"}]}
        for m in ("breakfast", "lunch", "dinner")
    }
    async with sessions.begin() as db:
        for offset in (-1, 0, 1):
            refs = {m: {"kind": "reference", "id": str(uuid4())} for m in archive}
            if offset == 0:
                refs["_roster"] = {"breakfast": {"consumed_at": "confirmed"}, "dinner": {"mode": "explicit"}}
            db.add(
                HealthDailyMealPlan(
                    id=str(uuid4()),
                    actor_uid="self",
                    family_id=family["id"],
                    plan_date=today + timedelta(days=offset),
                    is_shared=True,
                    version=1,
                    archive_meals=deepcopy(archive),
                    meal_sources=refs,
                    pending={},
                )
            )
    return family, path, body, profile, today


async def test_save_updates_only_unconsumed_default_meals_and_replays_once(family_profile_http):
    client, sessions, users = family_profile_http
    family, path, body, profile, today = await setup_rows(family_profile_http)
    body.update(
        client_request_id=str(uuid4()), family_version=profile["familyVersion"], default_diners=["self", "child"]
    )
    for draft in body["members"]:
        member = next(m for m in profile["members"] if m["id"] == profile["memberRefs"][draft["client_ref"]])
        draft.update(member_id=member["id"], version=member["version"])
    headers = {**users["self"], "Idempotency-Key": body["client_request_id"]}
    for _ in range(2):
        response = await client.post(path, json=body, headers=headers)
        assert response.status_code == 200, response.text
    async with sessions() as db:
        rows = (await db.scalars(select(HealthDailyMealPlan).order_by(HealthDailyMealPlan.plan_date))).all()
        assert rows[0].version == 1 and "_roster" not in rows[0].meal_sources
        state = rows[1].meal_sources["_roster"]
        assert state["breakfast"]["status"] == "pending" and "consumed_at" not in state["breakfast"]
        assert state["dinner"] == {"mode": "explicit"}
        assert state["lunch"]["status"] == "pending" and len(state["lunch"]["target_ids"]) == 2
        assert all(rows[2].meal_sources["_roster"][m]["status"] == "pending" for m in ("breakfast", "lunch", "dinner"))
        assert (
            await db.scalar(select(func.count()).select_from(TaskRecord).where(TaskRecord.type == "meal_roster_v1"))
            == 2
        )
        assert rows[1].archive_meals["lunch"]["members"] == rows[0].archive_meals["lunch"]["members"]


async def test_roster_endpoint_cannot_create_a_second_consumption_fact(family_profile_http):
    client, sessions, users = family_profile_http
    family, _, _, profile, today = await setup_rows(family_profile_http)
    path = f"/api/family/{family['id']}/daily-meal-plans/{today}/members"
    request = {"client_request_id": str(uuid4()), "version": 1, "meal_types": ["lunch"], "consumed": True}
    response = await client.post(path, headers=users["self"], json=request)
    assert response.status_code == 409 and response.json()["code"] == "meal_recording_required"
    assert (await client.post(path, headers=users["other"], json=request)).status_code == 404
    async with sessions() as db:
        row = await db.scalar(select(HealthDailyMealPlan).where(HealthDailyMealPlan.plan_date == today))
        assert row.version == 1 and "lunch" not in row.meal_sources["_roster"]


async def test_pending_target_rejects_old_result_and_revert_retargets():
    row = SimpleNamespace(
        plan_date=datetime.now(ZoneInfo("Asia/Shanghai")).date(),
        meal_sources={"_roster": {"lunch": {"target_ids": ["a", "b"], "status": "pending", "mode": "default"}}},
    )
    with pytest.raises(HealthVisionError, match="旧结果"):
        await verify_roster_publish(None, row, ["lunch"], ["a"])
    archive = {"lunch": {"members": [{"id": "a"}]}}
    assert roster_targets(archive, row.meal_sources["_roster"], ["a", "b"], ["a"]) == {"lunch": ["a"]}
    await verify_roster_publish(None, row, ["lunch"], ["a", "b"])
    assert row.meal_sources["_roster"]["lunch"]["status"] == "ready"


async def test_consuming_pending_meal_finishes_that_target(family_profile_http):
    client, sessions, users = family_profile_http
    family, _, _, profile, today = await setup_rows(family_profile_http)
    async with sessions.begin() as db:
        row = await db.scalar(select(HealthDailyMealPlan).where(HealthDailyMealPlan.plan_date == today))
        state = {
            **row.meal_sources["_roster"],
            "lunch": {"status": "pending", "target_ids": [profile["selfMemberId"]], "mode": "default"},
        }
        row.meal_sources = {**row.meal_sources, "_roster": state}
    path = f"/api/family/{family['id']}/daily-meal-plans/{today}/members"
    response = await client.post(
        path,
        headers=users["self"],
        json={"client_request_id": str(uuid4()), "version": 1, "meal_types": ["lunch"], "consumed": True},
    )
    assert response.status_code == 409 and response.json()["code"] == "meal_recording_required"
    async with sessions() as db:
        row = await db.scalar(select(HealthDailyMealPlan).where(HealthDailyMealPlan.plan_date == today))
        assert row.meal_sources["_roster"]["lunch"]["status"] == "pending"


async def test_explicit_single_meal_after_default_update_is_preserved():
    row = SimpleNamespace(
        plan_date=datetime.now(ZoneInfo("Asia/Shanghai")).date(),
        meal_sources={"_roster": {"lunch": {"mode": "default", "target_ids": ["a", "b"], "status": "ready"}}},
    )
    await verify_roster_publish(None, row, ["lunch"], ["a"])
    assert row.meal_sources["_roster"]["lunch"]["mode"] == "explicit"
    assert (
        roster_targets({"lunch": {"members": [{"id": "a"}]}}, row.meal_sources["_roster"], ["a", "b"], ["a", "b", "c"])
        == {}
    )


async def test_exclusive_history_is_preserved_without_aliasing_new_plan():
    from yuxi.services.exclusive_roster_service import preserve_executed_meals

    original = {
        "day": {"day_no": 1, "plan_date": "2026-11-24"},
        "meals": [{"meal_type": m, "dishes": [{"name": "old"}]} for m in ("breakfast", "lunch", "dinner")],
    }
    generated = deepcopy(original)
    for meal in generated["meals"]:
        meal["dishes"][0]["name"] = "new"
    result = preserve_executed_meals(original, generated, {"breakfast"})
    assert [m["dishes"][0]["name"] for m in result["meals"]] == ["old", "new", "new"]
    assert result["roster_preserved_meals"] == ["breakfast"]
    assert original["meals"][1]["dishes"][0]["name"] == "old"


async def test_durable_worker_waits_busy_and_publishes_actual_member_snapshot(family_profile_http, monkeypatch):
    from fastapi import HTTPException
    from yuxi.services import health_task_service, agent_request_service, daily_meal_plan_service
    from yuxi.services.meal_roster_service import run_roster_update, register_roster

    client, sessions, users = family_profile_http
    family, _, _, profile, today = await setup_rows(family_profile_http)
    ids = sorted(m["id"] for m in profile["members"])
    async with sessions.begin() as db:
        row = await db.scalar(select(HealthDailyMealPlan).where(HealthDailyMealPlan.plan_date == today))
        task = await register_roster(db, "self", row, {"lunch": ids}, mode="default")
        payload = task.payload
    selections = []
    submissions = []
    reads = 0

    async def entry(uid, anchor, data):
        selections.append(data.root.selection.model_dump(mode="json"))
        return SimpleNamespace(entry_status="ready", agent_slug="health_meal_planner", thread_id=str(uuid4()))

    async def pending(db, row, **kwargs):
        nonlocal reads
        reads += 1
        return {"status": "running", "request_id": "old"} if reads == 1 else None

    async def submit(*, request_input, current_user, db):
        submissions.append(request_input.request_id)
        if len(submissions) == 1:
            raise HTTPException(423, "old run still finishing")
        row = await daily_meal_plan_service.current_row(db, "self", family["id"], today, lock=True)
        await verify_roster_publish(db, row, ["lunch"], ids)
        saved = deepcopy(row.archive_meals)
        saved["lunch"]["members"] = [{"id": mid, "name": "合成成员"} for mid in ids]
        saved["lunch"]["dishes"] = [{"id": "new-dish", "name": "新名单餐单"}]
        row.archive_meals = saved
        row.version += 1

    async def result(uid, key):
        return SimpleNamespace(
            result=SimpleNamespace(result_type="meal_plan_preview"),
            execution_status="completed",
            request_status="dispatched",
        )

    async def active():
        return None

    monkeypatch.setattr(health_task_service, "create_health_task_entry", entry)
    monkeypatch.setattr(health_task_service, "read_health_task", result)
    monkeypatch.setattr(agent_request_service, "submit_agent_request", submit)
    monkeypatch.setattr(daily_meal_plan_service, "pending_request", pending)
    await run_roster_update(SimpleNamespace(payload=payload, raise_if_cancelled=active))
    assert len(submissions) == 2 and submissions[0] == submissions[1]
    assert selections[0] == selections[1]
    async with sessions() as db:
        row = await db.scalar(select(HealthDailyMealPlan).where(HealthDailyMealPlan.plan_date == today))
        assert row.meal_sources["_roster"]["lunch"]["status"] == "ready"
        assert [m["id"] for m in row.archive_meals["lunch"]["members"]] == ids
        assert row.archive_meals["breakfast"]["dishes"][0]["name"] == "合成菜"
        assert row.archive_meals["lunch"]["dishes"][0]["name"] == "新名单餐单"


async def test_superseded_worker_does_not_submit(family_profile_http, monkeypatch):
    from yuxi.services import health_task_service
    from yuxi.services.meal_roster_service import run_roster_update

    _, _, _, _, today = await setup_rows(family_profile_http)

    async def unexpected(*args, **kwargs):
        raise AssertionError("superseded task submitted")

    async def active():
        return None

    monkeypatch.setattr(health_task_service, "create_health_task_entry", unexpected)
    client, sessions, users = family_profile_http
    async with sessions() as db:
        row = await db.scalar(select(HealthDailyMealPlan).where(HealthDailyMealPlan.plan_date == today))
        fid = row.family_id
    result = await run_roster_update(
        SimpleNamespace(
            payload={"uid": "self", "family_id": fid, "date": str(today), "revision": 99}, raise_if_cancelled=active
        )
    )
    assert result == {"status": "superseded"}


async def test_exclusive_schedule_keeps_account_owner_and_success_survives_task_failure(family_profile_http):
    from yuxi.services.exclusive_roster_service import schedule_exclusive_roster, fail_exclusive_roster
    from yuxi.services.exclusive_plan_service import PREVIEW_POLICY
    from yuxi.services.family_service import FamilyService
    from yuxi.storage.postgres.models_health import HealthExclusivePlanGroup

    client, sessions, users = family_profile_http
    family, _, _, profile, today = await setup_rows(family_profile_http)
    gid = str(uuid4())
    async with sessions.begin() as db:
        row = HealthExclusivePlanGroup(
            id=gid,
            actor_uid="self",
            family_id=family["id"],
            request_id=str(uuid4()),
            basis_hash="old",
            status="ready",
            attempt=0,
            selection={"plan_date": str(today)},
            sources={},
            policy=PREVIEW_POLICY,
            progress={"tiers": {}},
        )
        db.add(row)
        await db.flush()
        archive, _ = await FamilyService(db, "self").context(family["id"])
        await schedule_exclusive_roster(db, "other", archive)
    async with sessions.begin() as db:
        tasks = (await db.scalars(select(TaskRecord).where(TaskRecord.type == "exclusive_roster_v1"))).all()
        assert len(tasks) == 1 and tasks[0].payload["uid"] == "self"
        row = await db.get(HealthExclusivePlanGroup, gid)
        row.status = "ready"
        row.progress = {"roster_update": {"revision": 1, "status": "ready"}}
        await fail_exclusive_roster(db, tasks[0], "worker_lease_expired: synthetic")
        assert row.status == "ready"


async def test_preserved_exclusive_day_remains_readable_when_old_recipe_is_missing(family_profile_http, monkeypatch):
    from yuxi.services import exclusive_plan_browse as browse
    from yuxi.services.exclusive_plan_service import PREVIEW_POLICY
    from yuxi.services.reference_meal_plan_types import ReferenceSelection
    from yuxi.storage.postgres.models_health import HealthExclusivePlanGroup

    _, sessions, _ = family_profile_http
    family, _, _, profile, today = await setup_rows(family_profile_http)
    gid = str(uuid4())
    start = today - timedelta(days=1)
    source_ref = {
        "kb_id": "missing-kb",
        "file_id": "missing-file",
        "chunk_id": "missing-chunk",
        "filename": "saved.md",
        "file_hash": "saved-file-hash",
        "chunks_hash": "saved-chunks-hash",
    }
    entries = []
    for number in range(1, 8):
        entry = {
            "mode": "reference",
            "day": {"day_no": number, "plan_date": str(start + timedelta(days=number - 1))},
            "meals": [
                {
                    "meal_type": m,
                    "dishes": [
                        {
                            "file_id": "missing-file",
                            "chunk_id": "missing-chunk",
                            "name": "保留的原菜谱",
                            "ingredients": ["原食材"],
                            "steps": ["原做法"],
                            "source": deepcopy(source_ref),
                        }
                    ],
                }
                for m in ("breakfast", "lunch", "dinner")
            ],
        }
        if number == 1:
            entry["roster_preserved_meals"] = ["breakfast", "lunch", "dinner"]
        entries.append(entry)
    async with sessions.begin() as db:
        db.add(
            HealthExclusivePlanGroup(
                id=gid,
                actor_uid="self",
                family_id=family["id"],
                request_id=str(uuid4()),
                basis_hash="current",
                status="ready",
                attempt=1,
                selection={"plan_date": str(start)},
                sources={},
                policy=PREVIEW_POLICY,
                progress={"tiers": {"economy": entries}},
            )
        )

    async def context(*args, **kwargs):
        return {
            "basis_hash": "current",
            "selection": ReferenceSelection(
                family_id=family["id"], plan_date=start, participant_ids=[profile["selfMemberId"]]
            ),
            "current": {"members": [], "sources": {"recipe_kb_ids": []}},
            "verified_documents": {},
        }

    monkeypatch.setattr(browse, "exclusive_context", context)
    from yuxi.storage.postgres.models_knowledge import KnowledgeBase, KnowledgeFile, KnowledgeChunk

    async with sessions.begin() as db:
        connection = await db.connection()
        await connection.run_sync(
            lambda conn: KnowledgeBase.metadata.create_all(
                conn, tables=[KnowledgeBase.__table__, KnowledgeFile.__table__, KnowledgeChunk.__table__]
            )
        )
    directory = await browse.read_plan_directory("self", family["id"], gid, "economy")
    assert directory["days"][0]["available"] is True
    assert directory["days"][1]["available"] is False
    day = await browse.read_plan_day("self", family["id"], gid, "economy", 1)
    assert all(d["recipe_name"] == "保留的原菜谱" and d["roster_preserved"] for d in day["day"]["meals"])
    with pytest.raises(HealthVisionError):
        await browse.read_plan_day("self", family["id"], gid, "economy", 2)


@pytest.mark.parametrize("change_basis,record_during_generation", [(False, False), (True, False), (False, True)])
async def test_exclusive_worker_atomic_publication_or_basis_refusal(
    family_profile_http, monkeypatch, change_basis, record_during_generation
):
    from yuxi.services import exclusive_plan_service as plans, exclusive_reference_plan as recipes
    from yuxi.services.exclusive_roster_service import run_exclusive_roster
    from yuxi.services.reference_meal_plan_types import ReferenceSelection
    from yuxi.storage.postgres.models_health import HealthExclusivePlanGroup

    client, sessions, users = family_profile_http
    family, _, _, profile, today = await setup_rows(family_profile_http)
    gid = str(uuid4())
    original = {}
    for tier in ("economy", "standard", "premium"):
        original[tier] = [
            {
                "mode": "reference",
                "day": {"day_no": n, "plan_date": str(today + timedelta(days=n - 1))},
                "meals": [{"meal_type": m, "dishes": [{"name": "old"}]} for m in ("breakfast", "lunch", "dinner")],
                "procurement": {},
            }
            for n in range(1, 8)
        ]
    async with sessions.begin() as db:
        db.add(
            HealthExclusivePlanGroup(
                id=gid,
                actor_uid="self",
                family_id=family["id"],
                request_id=str(uuid4()),
                basis_hash="old",
                status="generating",
                attempt=1,
                selection={"plan_date": str(today)},
                sources={},
                policy=plans.PREVIEW_POLICY,
                progress={"tiers": original, "roster_update": {"revision": 1, "original_tiers": original}},
            )
        )
    calls = 0
    validated = []

    async def context(session, uid, fid, policy, **kwargs):
        nonlocal calls
        calls += 1
        return {
            "basis_hash": "changed" if change_basis and calls > 1 else "current",
            "selection": ReferenceSelection(
                family_id=fid, plan_date=kwargs["day"], participant_ids=[profile["selfMemberId"]]
            ),
            "sources": {},
            "current": {"members": []},
        }

    async def catalog():
        return None

    def generate(inputs, tier, previous, seed, catalog):
        return {
            "mode": "reference",
            "day": {"day_no": len(previous) + 1, "plan_date": str(inputs["selection"].plan_date)},
            "meals": [{"meal_type": m, "dishes": [{"name": "new"}]} for m in ("breakfast", "lunch", "dinner")],
            "procurement": {},
        }

    recorded = False

    async def prepare(*args):
        nonlocal recorded
        if record_during_generation and not recorded:
            from yuxi.storage.postgres.models_health import HealthFamilyProfileLink

            async with sessions() as db:
                health_id = await db.scalar(
                    select(HealthFamilyProfileLink.member_id).where(
                        HealthFamilyProfileLink.source_member_id == profile["selfMemberId"]
                    )
                )
            await record_actual(client, users["self"], health_id, today)
            recorded = True

    async def validate(session, inputs, entries):
        assert inputs["basis_hash"] == "current"
        validated.append(len(entries))

    async def active():
        return None

    async def transaction(operation):
        async with sessions.begin() as db:
            await operation(db, None)

    monkeypatch.setattr(plans, "exclusive_context", context)
    monkeypatch.setattr(recipes, "optional_exclusive_catalog", catalog)
    monkeypatch.setattr(recipes, "generate_reference_day", generate)
    monkeypatch.setattr(recipes, "prepare_reference_day", prepare)
    monkeypatch.setattr(recipes, "validate_reference_days", validate)
    task = SimpleNamespace(
        payload={"uid": "self", "family_id": family["id"], "group_id": gid, "revision": 1},
        raise_if_cancelled=active,
        run_owned_transaction=transaction,
    )
    if change_basis:
        with pytest.raises(HealthVisionError, match="生成期间变化"):
            await run_exclusive_roster(task)
    else:
        assert await run_exclusive_roster(task) == {"status": "ready"}
        assert await run_exclusive_roster(task) == {"status": "ready"}
        assert validated == [7, 7, 7]
    async with sessions() as db:
        row = await db.get(HealthExclusivePlanGroup, gid)
        if change_basis:
            assert row.status == "generating" and row.progress["tiers"] == original
        else:
            assert row.status == "ready" and row.basis_hash == "current"
            assert [m["dishes"][0]["name"] for m in row.progress["tiers"]["economy"][0]["meals"]] == [
                "old" if record_during_generation else "new",
                "new",
                "old",
            ]
            assert all(m["dishes"][0]["name"] == "new" for m in row.progress["tiers"]["premium"][1]["meals"])


async def test_failure_callback_converges_after_request_actor_loses_family_access(family_profile_http):
    from yuxi.services.meal_roster_service import fail_roster_update

    _, sessions, _ = family_profile_http
    family, _, _, profile, today = await setup_rows(family_profile_http)
    async with sessions.begin() as db:
        row = await db.scalar(select(HealthDailyMealPlan).where(HealthDailyMealPlan.plan_date == today))
        state = {"revision": 7, "lunch": {"status": "pending", "target_ids": [profile["selfMemberId"]]}}
        row.meal_sources = {**row.meal_sources, "_roster": state}
    async with sessions.begin() as db:
        await fail_roster_update(
            db,
            SimpleNamespace(
                payload={"uid": "departed-account", "family_id": family["id"], "date": str(today), "revision": 7}
            ),
            "authorization revoked",
        )
    async with sessions() as db:
        row = await db.scalar(select(HealthDailyMealPlan).where(HealthDailyMealPlan.plan_date == today))
        assert row.meal_sources["_roster"]["lunch"]["status"] == "failed"
        assert row.archive_meals["lunch"]["dishes"][0]["name"] == "合成菜"


async def record_actual(client, headers, member_id, day, kind="breakfast"):
    """通过现有真实记餐 HTTP 提交一个人的实际摄入。"""
    from sqlalchemy import select

    request_id = str(uuid4())
    body = {
        "member_id": member_id,
        "client_request_id": request_id,
        "accept_incomplete": True,
        "meal": {
            "meal_type": kind,
            "eaten_at": f"{day}T08:00:00+08:00",
            "items": [
                {
                    "item_id": str(uuid4()),
                    "name": "合成实际摄入",
                    "grams": "50",
                    "portion_source": "manual",
                    "share_ratio": 1,
                }
            ],
        },
    }
    response = await client.post(
        "/api/health/v1/meal-recordings", json=body, headers={**headers, "Idempotency-Key": request_id}
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_existing_recording_owner_protects_meal_and_withdrawal_releases_it(family_profile_http):
    from yuxi.storage.postgres.models_health import HealthFamilyProfileLink
    from yuxi.services.meal_roster_service import current_roster

    client, sessions, users = family_profile_http
    family, _, _, profile, today = await setup_rows(family_profile_http)
    async with sessions.begin() as db:
        row = await db.scalar(select(HealthDailyMealPlan).where(HealthDailyMealPlan.plan_date == today))
        archive = deepcopy(row.archive_meals)
        archive["breakfast"]["members"] = [{"id": m["id"], "name": m["name"]} for m in profile["members"]]
        row.archive_meals = archive
        health_id = await db.scalar(
            select(HealthFamilyProfileLink.member_id).where(
                HealthFamilyProfileLink.source_member_id == profile["selfMemberId"]
            )
        )
        assert health_id
    actual = await record_actual(client, users["self"], health_id, today)
    path = f"/api/family/{family['id']}/daily-meal-plans/{today}/members"
    request = {
        "client_request_id": str(uuid4()),
        "version": 1,
        "meal_types": ["breakfast"],
        "member_ids": [m["id"] for m in profile["members"]],
        "consumed": False,
    }
    response = await client.post(path, headers=users["self"], json=request)
    assert response.status_code == 409 and response.json()["code"] == "meal_has_records"
    async with sessions() as db:
        row = await db.scalar(select(HealthDailyMealPlan).where(HealthDailyMealPlan.plan_date == today))
        policy = await current_roster(db, row)
        assert policy["breakfast"]["execution_locked"] and "consumed_at" not in policy["breakfast"]
        assert len(policy["breakfast"]["target_ids"]) == 2  # 仅一人记餐，不宣称两人均已用餐。
        assert not policy.get("lunch", {}).get("execution_locked")
        with pytest.raises(HealthVisionError, match="已有记餐"):
            await verify_roster_publish(db, row, ["breakfast"], request["member_ids"])
    key = str(uuid4())
    response = await client.post(
        f"/api/health/v1/diet-logs/{actual['id']}/withdraw",
        headers={**users["self"], "Idempotency-Key": key, "If-Match": '"1"'},
        json={"client_request_id": key, "expected_version": 1},
    )
    assert response.status_code == 200, response.text
    request["client_request_id"] = str(uuid4())
    response = await client.post(path, headers=users["self"], json=request)
    assert response.status_code == 200, response.text
    async with sessions() as db:
        row = await db.scalar(select(HealthDailyMealPlan).where(HealthDailyMealPlan.plan_date == today))
        assert row.meal_sources["_roster"]["breakfast"]["status"] == "pending"
        assert "consumed_at" not in row.meal_sources["_roster"]["breakfast"]


async def test_recording_date_meal_and_archived_member_boundaries(family_profile_http):
    from yuxi.storage.postgres.models_health import HealthFamilyProfileLink, DietLog, VisionConfirmation, VisionDraft
    from yuxi.services.meal_roster_service import current_roster

    client, sessions, users = family_profile_http
    family, _, _, profile, today = await setup_rows(family_profile_http)
    async with sessions() as db:
        health_id = await db.scalar(
            select(HealthFamilyProfileLink.member_id).where(
                HealthFamilyProfileLink.source_member_id == profile["selfMemberId"]
            )
        )
    actual = await record_actual(client, users["self"], health_id, today, "lunch")
    async with sessions.begin() as db:
        row = await db.scalar(select(HealthDailyMealPlan).where(HealthDailyMealPlan.plan_date == today))
        policy = await current_roster(db, row)
        assert policy["lunch"]["execution_locked"] and not policy.get("breakfast", {}).get("execution_locked")
        record = await db.get(DietLog, actual["id"])
        confirmation = await db.get(VisionConfirmation, record.confirmation_id)
        draft = await db.get(VisionDraft, confirmation.draft_id)
        draft.version += 1
        await db.flush()
        assert not (await current_roster(db, row)).get("lunch", {}).get("execution_locked")
        draft.version -= 1
        await db.flush()
        from yuxi.repositories.meal_execution_repository import MealExecutionRepository

        assert await MealExecutionRepository(db).protected_meals(str(uuid4()), today, row.archive_meals) == set()
        # 更正后的当前快照决定日期；旧确认时间不能继续保护原日期。
        record = await db.get(DietLog, actual["id"])
        record.snapshot = {
            **record.snapshot,
            "meal": {**record.snapshot["meal"], "eaten_at": f"{today - timedelta(days=1)}T23:59:00+08:00"},
        }
        await db.flush()
        assert not (await current_roster(db, row)).get("lunch", {}).get("execution_locked")
        record.snapshot = {
            **record.snapshot,
            "meal": {**record.snapshot["meal"], "eaten_at": f"{today}T00:00:00+08:00"},
        }
        archive = deepcopy(row.archive_meals)
        archive["lunch"]["members"] = []
        row.archive_meals = archive
        assert not (await current_roster(db, row)).get("lunch", {}).get("execution_locked")


async def test_publish_waits_for_existing_recording_transaction(family_profile_http):
    """真实记餐事务尚未提交时，发布必须等待并看见提交后的保护事实。"""
    import asyncio
    from yuxi.services.health_meal_recording_service import record_meal
    from yuxi.services.health_meal_recording_types import MealRecordingInput
    from yuxi.storage.postgres.models_health import HealthFamilyProfileLink

    client, sessions, users = family_profile_http
    family, _, _, profile, today = await setup_rows(family_profile_http)
    async with sessions() as db:
        health_id = await db.scalar(
            select(HealthFamilyProfileLink.member_id).where(
                HealthFamilyProfileLink.source_member_id == profile["selfMemberId"]
            )
        )
    data = MealRecordingInput.model_validate(
        {
            "member_id": health_id,
            "client_request_id": str(uuid4()),
            "accept_incomplete": True,
            "meal": {
                "meal_type": "lunch",
                "eaten_at": f"{today}T12:00:00+08:00",
                "items": [
                    {
                        "item_id": str(uuid4()),
                        "name": "合成实际摄入",
                        "grams": "50",
                        "portion_source": "manual",
                        "share_ratio": 1,
                    }
                ],
            },
        }
    )

    async def publish():
        async with sessions.begin() as db:
            row = await db.scalar(select(HealthDailyMealPlan).where(HealthDailyMealPlan.plan_date == today))
            await verify_roster_publish(db, row, ["lunch"], [profile["selfMemberId"]])

    async with sessions.begin() as writer:
        await record_meal("self", data, session=writer)
        attempt = asyncio.create_task(publish())
        await asyncio.sleep(0.15)
        assert not attempt.done(), "发布绕过了正在提交的记餐事务"
    with pytest.raises(HealthVisionError, match="已有记餐"):
        await asyncio.wait_for(attempt, 5)


async def test_pending_roster_worker_converges_when_actual_record_arrives(family_profile_http, monkeypatch):
    """真实记餐到达后原目标不再生成，worker 持久收敛而非长期停留更新中。"""
    from yuxi.services import health_task_service
    from yuxi.services.meal_roster_service import register_roster, run_roster_update
    from yuxi.storage.postgres.models_health import HealthFamilyProfileLink

    client, sessions, users = family_profile_http
    family, _, _, profile, today = await setup_rows(family_profile_http)
    async with sessions.begin() as db:
        row = await db.scalar(select(HealthDailyMealPlan).where(HealthDailyMealPlan.plan_date == today))
        task = await register_roster(db, "self", row, {"lunch": [m["id"] for m in profile["members"]]}, mode="default")
        payload = deepcopy(task.payload)
        health_id = await db.scalar(
            select(HealthFamilyProfileLink.member_id).where(
                HealthFamilyProfileLink.source_member_id == profile["selfMemberId"]
            )
        )
        saved = deepcopy(row.archive_meals)
    await record_actual(client, users["self"], health_id, today, "lunch")

    async def forbidden(*args):
        raise AssertionError("已有记餐的餐次不应再提交生成")

    async def active():
        return None

    monkeypatch.setattr(health_task_service, "create_health_task_entry", forbidden)
    assert await run_roster_update(SimpleNamespace(payload=payload, raise_if_cancelled=active)) == {
        "status": "completed"
    }
    async with sessions() as db:
        row = await db.scalar(select(HealthDailyMealPlan).where(HealthDailyMealPlan.plan_date == today))
        assert row.archive_meals == saved
        assert row.meal_sources["_roster"]["lunch"]["status"] == "ready"
        assert row.meal_sources["_roster"]["lunch"]["target_ids"] == [profile["selfMemberId"]]
        assert "execution_locked" not in row.meal_sources["_roster"]["lunch"]

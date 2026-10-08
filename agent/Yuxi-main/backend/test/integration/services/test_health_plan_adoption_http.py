"""真实HTTP/PG验证采用当前批准、并发唯一性及次日提议边界。"""

import asyncio
from copy import deepcopy
from datetime import datetime, timedelta, UTC
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from test.integration.services.test_health_quality_http import setup_quality, action, proof
from test.integration.services.test_health_meal_planner_http import plan_spec, publish_planner_recipe
from test.integration.services.test_health_vision_http import ROOT, create_member, health_http  # noqa: F401
from yuxi.services.health_daily_service import business_date
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_health import (
    HealthMealPlan,
    HealthMealPlanPreview,
    HealthNextDayProposal,
    HealthMealPlanAdoption,
    HealthMealPlanAdoptionAction,
    DietLog,
    HealthProfessionalReview,
)

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


def adopt_body(current):
    """期望版本由明确选定对象提供，不提交批准状态。"""
    return {
        "client_request_id": str(uuid4()),
        "version": 1,
        "review_id": current["case"]["review_id"],
        "profile_versions": {current["member"]: 1},
    }


async def approve(client, users, current):
    """通过实际专业动作建立批准，测试不手写状态。"""
    case = current["case"]["review_id"]
    await action(client, users[0]["headers"], case, "submit", 1)
    await action(client, users[1]["headers"], case, "approve", 2)


async def test_adoption_withdraw_idempotency_private_access_and_immutable_snapshot(health_http):  # noqa: F811
    """采用、取消和重放回读PG；草稿和客观记录不因采用改变。"""
    client, users = health_http
    current = await setup_quality(client, users)
    owner = users[0]["headers"]
    endpoint = f"{ROOT}/meal-plans/{current['plan']}/adopt"
    body = adopt_body(current)
    rejected = await client.post(endpoint, headers=owner, json=body)
    assert rejected.status_code == 409 and rejected.json()["code"] == "professional_approval_required"
    await approve(client, users, current)
    stale = await client.post(endpoint, headers=owner, json={**body, "profile_versions": {current["member"]: 2}})
    assert stale.status_code == 409 and stale.json()["code"] == "profile_version_conflict"
    adopted = await client.post(endpoint, headers=owner, json=body)
    assert adopted.status_code == 201, adopted.text
    initial = adopted.json()
    assert initial["status"] == "active" and initial["professional_approval_current"] is True
    assert initial["snapshot"]["nutrition"]["totals"]["energy_kcal"] == "300.00"
    assert (await client.post(endpoint, headers=owner, json=body)).json() == initial
    changed = await client.post(endpoint, headers=owner, json={**body, "review_id": str(uuid4())})
    assert changed.status_code == 409 and changed.json()["code"] == "request_conflict"
    uid = initial["adoption_id"]
    for other in users[1:]:
        assert (await client.get(f"{ROOT}/meal-plan-adoptions/{uid}", headers=other["headers"])).status_code == 404
        assert (await client.post(endpoint, headers=other["headers"], json=adopt_body(current))).status_code == 404
    effective = f"{ROOT}/members/{current['member']}/adopted-plan?plan_date=2026-10-06"
    assert (await client.get(effective, headers=owner)).json()["plan"]["adoption_id"] == uid
    withdraw = {"client_request_id": str(uuid4()), "version": 1, "reason": "用户取消合成采用"}
    cancelled = await client.post(f"{ROOT}/meal-plan-adoptions/{uid}/withdraw", headers=owner, json=withdraw)
    assert cancelled.status_code == 200 and cancelled.json()["status"] == "withdrawn"
    assert cancelled.json()["snapshot"] == initial["snapshot"]
    assert (
        await client.post(f"{ROOT}/meal-plan-adoptions/{uid}/withdraw", headers=owner, json=withdraw)
    ).json() == cancelled.json()
    replay = await client.post(endpoint, headers=owner, json=body)
    assert replay.json()["status"] == "withdrawn" and replay.json()["current"] is False
    assert (await client.get(effective, headers=owner)).json()["plan"] is None
    async with pg_manager.get_async_session_context() as session:
        row = await session.get(HealthMealPlanAdoption, uid)
        assert (row.status, row.version, row.plan_version) == ("withdrawn", 2, 1)
        assert row.snapshot == initial["snapshot"] and row.sources == initial["sources"]
        actions = list(
            (
                await session.scalars(
                    select(HealthMealPlanAdoptionAction)
                    .where(HealthMealPlanAdoptionAction.adoption_id == uid)
                    .order_by(HealthMealPlanAdoptionAction.version)
                )
            ).all()
        )
        assert [a.operation for a in actions] == ["adopt", "withdraw"]
        assert (await session.get(HealthMealPlan, current["plan"])).version == 1
        assert await session.scalar(select(DietLog).where(DietLog.member_id == current["member"])) is None
        from yuxi.services.health_nutrition_service import input_fingerprint

        assert actions[0].fingerprint == input_fingerprint(
            {
                "operation": "adopt",
                "plan_id": current["plan"],
                **body,
                "replaces_adoption_id": None,
                "replaces_version": None,
            }
        ), "新增空替代集合不得改变Schema11的采用幂等指纹"


@pytest.mark.parametrize("source", ["profile", "rules", "qualification", "grant", "swap"])
async def test_source_changes_permanently_invalidate_formal_adoption(health_http, source):  # noqa: F811
    """源写入事务直接使采用失效，恢复授权及幂等重放不能复活。"""
    client, users = health_http
    current = await setup_quality(client, users)
    await approve(client, users, current)
    owner, admin = users[0]["headers"], users[2]["headers"]
    body = adopt_body(current)
    endpoint = f"{ROOT}/meal-plans/{current['plan']}/adopt"
    initial = (await client.post(endpoint, headers=owner, json=body)).json()
    assert initial["current"] is True
    if source == "profile":
        changed = await client.post(
            f"{ROOT}/members/{current['member']}/external-profile-versions",
            headers=admin,
            json={**current["profile"], "version": 2, "source_version": "v2"},
        )
    elif source == "rules":
        changed = await client.post(
            f"{ROOT}/approved-quality-rules",
            headers=admin,
            json={**current["rules"], "version": 2, "source_version": "v2"},
        )
    elif source == "qualification":
        changed = await client.post(f"{ROOT}/professional-reviewers/{users[1]['uid']}/versions/1/revoke", headers=admin)
    elif source == "grant":
        changed = await client.put(
            f"{ROOT}/members/{current['member']}/grants",
            headers=owner,
            json={"actor_uid": users[1]["uid"], "scopes": []},
        )
        restored = await client.put(
            f"{ROOT}/members/{current['member']}/grants",
            headers=owner,
            json={"actor_uid": users[1]["uid"], "scopes": ["profile_view", "professional_review"]},
        )
        assert restored.status_code == 200
    else:
        async with pg_manager.get_async_session_context() as session:
            recipe = (await session.get(HealthMealPlan, current["plan"])).spec["meals"][0]["dishes"][0][
                "recipe_version_id"
            ]
        key = str(uuid4())
        changed = await client.post(
            f"{ROOT}/meal-plans/{current['plan']}/swap",
            headers={**owner, "Idempotency-Key": key, "If-Match": '"1"'},
            json={
                "client_request_id": key,
                "version": 1,
                "meal_type": "lunch",
                "dish_index": 0,
                "replacement": {"recipe_version_id": recipe, "grams": "110"},
                "reason": "合成换菜",
            },
        )
    assert changed.status_code in {200, 201}, changed.text
    async with pg_manager.get_async_session_context() as session:
        row = await session.get(HealthMealPlanAdoption, initial["adoption_id"])
        assert row.status == "invalidated" and row.version == 2
        assert row.sources == initial["sources"] and row.snapshot == initial["snapshot"]
    result = await client.get(f"{ROOT}/meal-plan-adoptions/{initial['adoption_id']}", headers=owner)
    assert result.status_code == 200 and result.json()["current"] is False
    replay = await client.post(endpoint, headers=owner, json=body)
    assert replay.status_code == 201 and replay.json()["status"] == "invalidated"


async def test_same_day_concurrency_explicit_replacement_and_action_key_conflict(health_http):  # noqa: F811
    """竞争采用只一成功；选定替代不会覆盖原快照，跨动作键重用拒绝。"""
    client, users = health_http
    current = await setup_quality(client, users)
    await approve(client, users, current)
    owner = users[0]["headers"]
    endpoint = f"{ROOT}/meal-plans/{current['plan']}/adopt"
    bodies = [adopt_body(current), adopt_body(current)]
    results = await asyncio.gather(*[client.post(endpoint, headers=owner, json=body) for body in bodies])
    assert sorted(r.status_code for r in results) == [201, 409], [r.text for r in results]
    initial = next(r.json() for r in results if r.status_code == 201)
    replacement = {**adopt_body(current), "replaces_adoption_id": initial["adoption_id"], "replaces_version": 1}
    wrong = await client.post(endpoint, headers=owner, json={**replacement, "replaces_version": 2})
    assert wrong.status_code == 409 and wrong.json()["code"] == "adoption_version_conflict"
    replaced = await client.post(endpoint, headers=owner, json=replacement)
    assert replaced.status_code == 201, replaced.text
    assert replaced.json()["adoption_id"] != initial["adoption_id"]
    old = (await client.get(f"{ROOT}/meal-plan-adoptions/{initial['adoption_id']}", headers=owner)).json()
    assert old["status"] == "superseded" and old["version"] == 2 and old["snapshot"] == initial["snapshot"]
    collision = await client.post(
        f"{ROOT}/meal-plan-adoptions/{replaced.json()['adoption_id']}/withdraw",
        headers=owner,
        json={"client_request_id": replacement["client_request_id"], "version": 1, "reason": "跨动作重复键"},
    )
    assert collision.status_code == 409 and collision.json()["code"] == "request_conflict"
    async with pg_manager.get_async_session_context() as session:
        rows = list(
            (
                await session.scalars(
                    select(HealthMealPlanAdoption).where(HealthMealPlanAdoption.member_id == current["member"])
                )
            ).all()
        )
        assert len(rows) == 2 and sum(row.status == "active" for row in rows) == 1


async def test_next_day_proposal_date_idempotency_sources_and_no_formal_plan(health_http):  # noqa: F811
    """明日提议保持独立，源篡改后只返回失效历史；不产生餐单/采用/饮食记录。"""
    client, users = health_http
    owner, admin = users[0]["headers"], users[2]["headers"]
    member = await create_member(client, owner)
    recipe = await publish_planner_recipe(client, admin, "次日合成菜")
    spec = {**plan_spec(recipe), "plan_date": (business_date() + timedelta(days=1)).isoformat()}
    preview = await client.post(f"{ROOT}/members/{member}/meal-plan-previews", headers=owner, json=spec)
    assert preview.status_code == 201, preview.text
    body = {
        "client_request_id": str(uuid4()),
        "preview_id": preview.json()["preview_id"],
        "source_date": business_date().isoformat(),
    }
    endpoint = f"{ROOT}/members/{member}/next-day-proposals"
    invalid = await client.post(endpoint, headers=owner, json={**body, "source_date": "2000-01-01"})
    assert invalid.status_code == 409 and invalid.json()["code"] == "proposal_date_invalid"
    proposed = await client.post(endpoint, headers=owner, json=body)
    assert proposed.status_code == 201, proposed.text
    initial = proposed.json()
    assert initial["status"] == "proposed" and initial["formal_plan_saved"] is False
    assert initial["snapshot"]["nutrition"]["totals"]["energy_kcal"] == "300.00"
    assert (await client.post(endpoint, headers=owner, json=body)).json() == initial
    for other in users[1:]:
        assert (
            await client.get(f"{ROOT}/next-day-proposals/{initial['proposal_id']}", headers=other["headers"])
        ).status_code == 404
    changed = await client.post(endpoint, headers=owner, json={**body, "source_date": "2000-01-01"})
    assert changed.status_code == 409 and changed.json()["code"] == "request_conflict"
    async with pg_manager.get_async_session_context() as session:
        assert (
            await session.scalar(
                select(func.count()).select_from(HealthNextDayProposal).where(HealthNextDayProposal.member_id == member)
            )
            == 1
        )
        for model in (HealthMealPlan, HealthMealPlanAdoption, DietLog):
            assert await session.scalar(select(func.count()).select_from(model).where(model.member_id == member)) == 0
        row = await session.get(HealthMealPlanPreview, body["preview_id"])
        changed_snapshot = deepcopy(row.snapshot)
        changed_snapshot["meals"][0]["dishes"][0]["name"] = "篡改次日快照"
        row.snapshot = changed_snapshot
    read = await client.get(f"{ROOT}/next-day-proposals/{initial['proposal_id']}", headers=owner)
    assert read.status_code == 200 and read.json()["status"] == "invalidated"
    assert read.json()["snapshot"] == initial["snapshot"] and read.json()["reason"] == "source_changed"


@pytest.mark.parametrize("source", ["profile", "rules", "qualification"])
async def test_reading_expired_professional_review_invalidates_adoption_in_same_transaction(health_http, source):  # noqa: F811
    """来源自然到期后读取审核，即刻PG采用失效，不先读取采用补状态。"""
    client, users = health_http
    current = await setup_quality(client, users)
    owner, admin = users[0]["headers"], users[2]["headers"]
    expires = datetime.now(UTC) + timedelta(seconds=5)
    stamp = {**proof(2), "valid_until": expires.isoformat()}
    if source == "profile":
        endpoint = f"{ROOT}/members/{current['member']}/external-profile-versions"
        payload = {**current["profile"], **stamp}
    elif source == "rules":
        endpoint = f"{ROOT}/approved-quality-rules"
        payload = {**current["rules"], **stamp}
    else:
        endpoint = f"{ROOT}/professional-reviewers"
        payload = {**stamp, "reviewer_uid": users[1]["uid"], "status": "qualified"}
    imported = await client.post(endpoint, headers=admin, json=payload)
    assert imported.status_code == 201, imported.text
    checked = await client.post(
        f"{ROOT}/meal-plans/{current['plan']}/quality-checks",
        headers=owner,
        json={**current["body"], "client_request_id": str(uuid4())},
    )
    assert checked.status_code == 201, checked.text
    current["case"] = (await client.get(f"{ROOT}/quality-checks/{checked.json()['check_id']}", headers=owner)).json()[
        "review"
    ]
    await approve(client, users, current)
    body = adopt_body(current)
    if source == "profile":
        body["profile_versions"][current["member"]] = 2
    response = await client.post(f"{ROOT}/meal-plans/{current['plan']}/adopt", headers=owner, json=body)
    assert response.status_code == 201 and response.json()["current"] is True, response.text
    initial = response.json()
    remaining = (expires - datetime.now(UTC)).total_seconds()
    assert remaining > 0, "先证明采用发生在真实有效期内"
    await asyncio.sleep(remaining + 0.05)
    read = await client.get(f"{ROOT}/professional-reviews/{current['case']['review_id']}", headers=owner)
    assert read.status_code == 200 and read.json()["status"] == "invalidated", read.text
    async with pg_manager.get_async_session_context() as session:
        row = await session.get(HealthMealPlanAdoption, initial["adoption_id"])
        case = await session.get(HealthProfessionalReview, current["case"]["review_id"])
        assert case.status == "invalidated" and case.version == 4
        assert row.status == "invalidated" and row.version == 2
        assert row.snapshot == initial["snapshot"] and row.sources == initial["sources"]
    read = await client.get(f"{ROOT}/meal-plan-adoptions/{initial['adoption_id']}", headers=owner)
    assert read.json()["status"] == "invalidated" and read.json()["version"] == 2


async def approved_clone(client, users, current, member, rule_code):
    """共享实际已发布菜谱，用真实HTTP建立另一成员/规则的独立批准。"""
    owner = users[0]["headers"]
    original = (await client.get(f"{ROOT}/meal-plans/{current['plan']}", headers=owner)).json()
    recipe = original["meals"][0]["dishes"][0]["recipe_version_id"]
    preview = await client.post(f"{ROOT}/members/{member}/meal-plan-previews", headers=owner, json=plan_spec(recipe))
    assert preview.status_code == 201, preview.text
    key = str(uuid4())
    saved = await client.post(
        f"{ROOT}/members/{member}/meal-plans",
        headers={**owner, "Idempotency-Key": key},
        json={"client_request_id": key, "preview_id": preview.json()["preview_id"]},
    )
    assert saved.status_code == 201, saved.text
    cloned = {"member": member, "plan": saved.json()["plan_id"]}
    checked = await client.post(
        f"{ROOT}/meal-plans/{cloned['plan']}/quality-checks",
        headers=owner,
        json={"client_request_id": str(uuid4()), "version": 1, "rule_code": rule_code},
    )
    assert checked.status_code == 201 and checked.json()["safety_check"]["status"] == "passed", checked.text
    cloned["case"] = (await client.get(f"{ROOT}/quality-checks/{checked.json()['check_id']}", headers=owner)).json()[
        "review"
    ]
    await approve(client, users, cloned)
    return cloned


async def wait_for_pg_advisory_wait(waiting_pid, blocking_pid):
    """数据库实际等待证明并发窗口，不把任务启动当作已取得来源锁。"""
    from sqlalchemy import text

    for _ in range(100):
        async with pg_manager.get_async_session_context() as session:
            waiting = await session.scalar(
                text("""
                SELECT EXISTS(SELECT 1 FROM pg_stat_activity WHERE datname=current_database()
                AND pid=:waiting_pid AND wait_event_type='Lock' AND wait_event='advisory'
                AND :blocking_pid=ANY(pg_blocking_pids(pid))
                AND query LIKE '%pg_advisory_xact_lock%')
            """),
                {"waiting_pid": waiting_pid, "blocking_pid": blocking_pid},
            )
        if waiting:
            return
        await asyncio.sleep(0.05)
    raise AssertionError("第二个采用事务没有进入预期来源锁等待窗口")


async def test_two_members_reverse_rule_replacements_do_not_acquire_old_source_locks(health_http, monkeypatch):  # noqa: F811
    """真实PG两成员反向R1/R2替换；旧实现在新来源锁内复核旧来源会死锁。"""
    from sqlalchemy import text
    from yuxi.repositories.health_plan_adoption_repository import HealthPlanAdoptionRepository
    from yuxi.services.health_plan_adoption_service import adopt_meal_plan
    from yuxi.services.health_plan_adoption_types import PlanAdoptionInput

    client, users = health_http
    owner, admin = users[0]["headers"], users[2]["headers"]
    first = await setup_quality(client, users)
    await approve(client, users, first)
    rule1 = first["rules"]["rule_code"]
    rule2 = "synthetic-reverse-" + uuid4().hex
    published = await client.post(
        f"{ROOT}/approved-quality-rules", headers=admin, json={**first["rules"], "rule_code": rule2}
    )
    assert published.status_code == 201, published.text
    member2 = await create_member(client, owner)
    for uid, scopes in [
        (users[2]["uid"], ["profile_edit"]),
        (users[1]["uid"], ["profile_view", "professional_review"]),
    ]:
        granted = await client.put(
            f"{ROOT}/members/{member2}/grants", headers=owner, json={"actor_uid": uid, "scopes": scopes}
        )
        assert granted.status_code == 200
    imported = await client.post(
        f"{ROOT}/members/{member2}/external-profile-versions", headers=admin, json=first["profile"]
    )
    assert imported.status_code == 201
    second = await approved_clone(client, users, first, member2, rule2)
    new_first = await approved_clone(client, users, first, first["member"], rule2)
    new_second = await approved_clone(client, users, first, member2, rule1)
    previous = []
    for current in (first, second):
        response = await client.post(
            f"{ROOT}/meal-plans/{current['plan']}/adopt", headers=owner, json=adopt_body(current)
        )
        assert response.status_code == 201, response.text
        previous.append(response.json())
    reached, release = asyncio.Event(), asyncio.Event()
    original = HealthPlanAdoptionRepository.overlapping
    original_lock = HealthPlanAdoptionRepository.lock_request
    backend_pids = {}
    second_connected = asyncio.Event()

    async def tag_request_connection(self, uid, request_id, **kwargs):
        await original_lock(self, uid, request_id, **kwargs)
        backend_pids[request_id] = await self.session.scalar(text("SELECT pg_backend_pid()"))
        if len(backend_pids) == 2:
            second_connected.set()

    async def pause_before_old_row(self, uid, members, plan_date, **kwargs):
        if first["member"] in members and kwargs.get("lock"):
            reached.set()
            await release.wait()
        return await original(self, uid, members, plan_date, **kwargs)

    monkeypatch.setattr(HealthPlanAdoptionRepository, "overlapping", pause_before_old_row)
    monkeypatch.setattr(HealthPlanAdoptionRepository, "lock_request", tag_request_connection)
    tasks = []
    request_ids = []
    try:
        for index, selected in enumerate((new_first, new_second)):
            data = {
                **adopt_body(selected),
                "replaces_adoption_id": previous[index]["adoption_id"],
                "replaces_version": 1,
            }
            request_ids.append(data["client_request_id"])
            tasks.append(
                asyncio.create_task(adopt_meal_plan(users[0]["uid"], selected["plan"], PlanAdoptionInput(**data)))
            )
            if index == 0:
                await asyncio.wait_for(reached.wait(), 10)
        await asyncio.wait_for(second_connected.wait(), 10)
        await wait_for_pg_advisory_wait(backend_pids[request_ids[1]], backend_pids[request_ids[0]])
        assert not tasks[0].done() and not tasks[1].done()
        release.set()
        results = await asyncio.wait_for(asyncio.gather(*tasks), 15)
        assert all(r["current"] and r["version"] == 1 for r in results)
        async with pg_manager.get_async_session_context() as session:
            old = [await session.get(HealthMealPlanAdoption, r["adoption_id"]) for r in previous]
            assert all((r.status, r.version) == ("superseded", 2) for r in old)
    finally:
        release.set()
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


async def test_replacement_row_lock_serializes_external_rule_revocation(health_http, monkeypatch):  # noqa: F811
    """持有旧采用行后撤旧规则必须等待，新采用只取得其自身规则。"""
    from sqlalchemy import text
    from yuxi.repositories.health_plan_adoption_repository import HealthPlanAdoptionRepository
    from yuxi.services.health_plan_adoption_service import adopt_meal_plan
    from yuxi.services.health_plan_adoption_types import PlanAdoptionInput

    client, users = health_http
    owner, admin = users[0]["headers"], users[2]["headers"]
    current = await setup_quality(client, users)
    await approve(client, users, current)
    initial = (
        await client.post(f"{ROOT}/meal-plans/{current['plan']}/adopt", headers=owner, json=adopt_body(current))
    ).json()
    code = "synthetic-row-lock-" + uuid4().hex
    published = await client.post(
        f"{ROOT}/approved-quality-rules", headers=admin, json={**current["rules"], "rule_code": code}
    )
    assert published.status_code == 201, published.text
    new = await approved_clone(client, users, current, current["member"], code)
    data = {**adopt_body(new), "replaces_adoption_id": initial["adoption_id"], "replaces_version": 1}
    reached, release = asyncio.Event(), asyncio.Event()
    original = HealthPlanAdoptionRepository.overlapping
    replacement_pid = None

    async def pause_after_row(self, *args, **kwargs):
        nonlocal replacement_pid
        row = await original(self, *args, **kwargs)
        if kwargs.get("lock"):
            replacement_pid = await self.session.scalar(text("SELECT pg_backend_pid()"))
            reached.set()
            await release.wait()
        return row

    monkeypatch.setattr(HealthPlanAdoptionRepository, "overlapping", pause_after_row)
    replacement = asyncio.create_task(adopt_meal_plan(users[0]["uid"], new["plan"], PlanAdoptionInput(**data)))
    revoke = None
    try:
        await asyncio.wait_for(reached.wait(), 10)
        revoke = asyncio.create_task(
            client.post(
                f"{ROOT}/approved-quality-rules/{current['rules']['rule_code']}/versions/1/revoke", headers=admin
            )
        )
        for _ in range(100):
            async with pg_manager.get_async_session_context() as session:
                waiting = await session.scalar(
                    text("""
                    SELECT EXISTS(SELECT 1 FROM pg_stat_activity WHERE datname=current_database()
                    AND pid<>pg_backend_pid() AND wait_event_type='Lock'
                    AND :replacement_pid=ANY(pg_blocking_pids(pid))
                    AND query LIKE '%UPDATE health_meal_plan_adoption%')
                """),
                    {"replacement_pid": replacement_pid},
                )
            if waiting:
                break
            await asyncio.sleep(0.05)
        assert waiting and not revoke.done(), "来源撤回须在实际PG采用行上等待"
        release.set()
        adopted, revoked = await asyncio.wait_for(asyncio.gather(replacement, revoke), 15)
        assert adopted["current"] and revoked.status_code == 200
        old = (await client.get(f"{ROOT}/meal-plan-adoptions/{initial['adoption_id']}", headers=owner)).json()
        assert old["status"] == "superseded" and old["version"] == 2
        latest = (await client.get(f"{ROOT}/meal-plan-adoptions/{adopted['adoption_id']}", headers=owner)).json()
        assert latest["current"] is True
    finally:
        release.set()
        for task in (replacement, revoke):
            if task is not None and not task.done():
                task.cancel()
        await asyncio.gather(*(t for t in (replacement, revoke) if t is not None), return_exceptions=True)


async def test_old_rule_invalidated_before_row_lock_rejects_stale_replacement(health_http, monkeypatch):  # noqa: F811
    """读取旧占用后旧规则先撤回，新事务不得覆盖失效版本或保存采用。"""
    from yuxi.repositories.health_plan_adoption_repository import HealthPlanAdoptionRepository
    from yuxi.services.health_plan_adoption_service import adopt_meal_plan
    from yuxi.services.health_plan_adoption_types import PlanAdoptionInput
    from yuxi.services.health_vision_types import HealthVisionError

    client, users = health_http
    owner, admin = users[0]["headers"], users[2]["headers"]
    current = await setup_quality(client, users)
    await approve(client, users, current)
    initial_response = await client.post(
        f"{ROOT}/meal-plans/{current['plan']}/adopt", headers=owner, json=adopt_body(current)
    )
    assert initial_response.status_code == 201, initial_response.text
    initial = initial_response.json()
    code = "synthetic-before-row-" + uuid4().hex
    published = await client.post(
        f"{ROOT}/approved-quality-rules", headers=admin, json={**current["rules"], "rule_code": code}
    )
    assert published.status_code == 201, published.text
    new = await approved_clone(client, users, current, current["member"], code)
    data = {**adopt_body(new), "replaces_adoption_id": initial["adoption_id"], "replaces_version": 1}
    reached, release = asyncio.Event(), asyncio.Event()
    original = HealthPlanAdoptionRepository.overlapping

    async def pause_before_lock(self, *args, **kwargs):
        """新来源已锁定、旧采用行尚未锁定的真实事务窗口。"""
        if kwargs.get("lock"):
            reached.set()
            await release.wait()
        return await original(self, *args, **kwargs)

    monkeypatch.setattr(HealthPlanAdoptionRepository, "overlapping", pause_before_lock)
    task = asyncio.create_task(adopt_meal_plan(users[0]["uid"], new["plan"], PlanAdoptionInput(**data)))
    try:
        await asyncio.wait_for(reached.wait(), timeout=10)
        revoked = await client.post(
            f"{ROOT}/approved-quality-rules/{current['rules']['rule_code']}/versions/1/revoke", headers=admin
        )
        assert revoked.status_code == 200, revoked.text
        release.set()
        with pytest.raises(HealthVisionError) as error:
            await asyncio.wait_for(task, timeout=15)
        assert error.value.code == "adoption_version_conflict"
        async with pg_manager.get_async_session_context() as session:
            rows = (
                await session.scalars(
                    select(HealthMealPlanAdoption).where(HealthMealPlanAdoption.actor_uid == users[0]["uid"])
                )
            ).all()
            assert len(rows) == 1 and (rows[0].id, rows[0].status, rows[0].version) == (
                initial["adoption_id"],
                "invalidated",
                2,
            )
            assert rows[0].snapshot == initial["snapshot"] and rows[0].sources == initial["sources"]
            receipt = await session.scalar(
                select(HealthMealPlanAdoptionAction).where(
                    HealthMealPlanAdoptionAction.request_id == data["client_request_id"]
                )
            )
            assert receipt is None
    finally:
        release.set()
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)


async def test_adopted_snapshot_tampering_and_next_day_expiry_cannot_remain_current(health_http, monkeypatch):  # noqa: F811
    """保留同一来源引用不能伪造已采用营养；跨日提议不能继续使用。"""
    from yuxi.services.health_plan_adoption_service import read_next_day_proposal
    import yuxi.services.health_plan_adoption_service as adoption_service

    client, users = health_http
    owner = users[0]["headers"]
    current = await setup_quality(client, users)
    await approve(client, users, current)
    adopted = await client.post(f"{ROOT}/meal-plans/{current['plan']}/adopt", headers=owner, json=adopt_body(current))
    assert adopted.status_code == 201, adopted.text
    initial = adopted.json()
    async with pg_manager.get_async_session_context() as session:
        row = await session.get(HealthMealPlanAdoption, initial["adoption_id"])
        forged = deepcopy(row.snapshot)
        forged["nutrition"]["totals"]["energy_kcal"] = "0.00"
        row.snapshot = forged
    read = await client.get(f"{ROOT}/meal-plan-adoptions/{initial['adoption_id']}", headers=owner)
    assert read.status_code == 200 and read.json()["current"] is False
    assert read.json()["status"] == "invalidated" and read.json()["version"] == 2
    async with pg_manager.get_async_session_context() as session:
        assert (await session.get(HealthMealPlan, current["plan"])).snapshot == initial["snapshot"]
    recipe = initial["snapshot"]["meals"][0]["dishes"][0]["recipe_version_id"]
    today = business_date()
    spec = {**plan_spec(recipe), "plan_date": (today + timedelta(days=1)).isoformat()}
    preview = await client.post(f"{ROOT}/members/{current['member']}/meal-plan-previews", headers=owner, json=spec)
    assert preview.status_code == 201
    proposed = await client.post(
        f"{ROOT}/members/{current['member']}/next-day-proposals",
        headers=owner,
        json={
            "client_request_id": str(uuid4()),
            "preview_id": preview.json()["preview_id"],
            "source_date": today.isoformat(),
        },
    )
    assert proposed.status_code == 201 and proposed.json()["current"] is True
    monkeypatch.setattr(adoption_service, "business_date", lambda: today + timedelta(days=2))
    expired = await read_next_day_proposal(users[0]["uid"], proposed.json()["proposal_id"])
    assert expired["status"] == "invalidated" and expired["reason"] == "date_expired"
    assert expired["snapshot"] == proposed.json()["snapshot"] and expired["formal_plan_saved"] is False

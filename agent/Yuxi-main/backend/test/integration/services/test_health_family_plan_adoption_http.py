"""家庭正式采用的逐成员占用、共同版本与实际HTTP事务。"""

import asyncio
from copy import deepcopy
from datetime import date
from uuid import uuid4

import pytest
from sqlalchemy import select, text, func

from test.integration.services.test_health_family_meal_plan_http import setup_family
from test.integration.services.test_health_meal_planner_http import plan_spec
from test.integration.services.test_health_quality_http import action
from test.integration.services.test_health_vision_http import ROOT, health_http  # noqa: F401
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_health import (
    FamilyMember,
    HealthMealPlanAdoption,
    HealthMealPlanAdoptionMember,
    HealthMealPlanAdoptionAction,
)

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


def selection(current, **extra):
    """选择全部实际档案版本和真实审核对象。"""
    return {
        "client_request_id": str(uuid4()),
        "version": 1,
        "review_id": current["case"],
        "profile_versions": {current["member"]: 2, current["second"]: 1},
        **extra,
    }


async def approve_family(client, users, current):
    """专业批准全部经真实授权HTTP动作。"""
    await action(client, users[0]["headers"], current["case"], "submit", 1)
    await action(client, users[1]["headers"], current["case"], "approve", 2)


async def save_approved(client, users, current, member, *, family=False):
    """在同一批准规则下另存计划，保留手算300/60营养口径。"""
    spec = deepcopy(current["spec"]) if family else {**plan_spec(current["recipe"]), "plan_date": "2026-10-07"}
    prefix = "family-meal-plan-previews" if family else "meal-plan-previews"
    response = await client.post(f"{ROOT}/members/{member}/{prefix}", headers=users[0]["headers"], json=spec)
    assert response.status_code == 201, response.text
    key = str(uuid4())
    response = await client.post(
        f"{ROOT}/members/{member}/meal-plans",
        headers={**users[0]["headers"], "Idempotency-Key": key},
        json={"client_request_id": key, "preview_id": response.json()["preview_id"]},
    )
    assert response.status_code == 201, response.text
    plan = response.json()["plan_id"]
    response = await client.post(
        f"{ROOT}/meal-plans/{plan}/quality-checks",
        headers=users[0]["headers"],
        json={"client_request_id": str(uuid4()), "version": 1, "rule_code": current["rules"]["rule_code"]},
    )
    assert response.status_code == 201 and response.json()["safety_check"]["status"] == "passed", response.text
    check = response.json()["check_id"]
    response = await client.get(f"{ROOT}/quality-checks/{check}", headers=users[0]["headers"])
    case = response.json()["review"]["review_id"]
    await action(client, users[0]["headers"], case, "submit", 1)
    await action(client, users[1]["headers"], case, "approve", 2)
    profiles = (
        {current["member"]: 2, current["second"]: 1} if family else {member: 2 if member == current["member"] else 1}
    )
    return plan, {"client_request_id": str(uuid4()), "version": 1, "review_id": case, "profile_versions": profiles}


async def test_family_adoption_personal_views_shared_withdrawal_and_private_history(health_http):  # noqa: F811
    """同一采用指向A300/B60；取消共同生效，原快照和资料不被改写。"""
    client, users = health_http
    current = await setup_family(client, users)
    owner = users[0]["headers"]
    endpoint = f"{ROOT}/meal-plans/{current['plan']}/adopt"
    body = selection(current)
    rejected = await client.post(endpoint, headers=owner, json=body)
    assert rejected.status_code == 409 and rejected.json()["code"] == "professional_approval_required"
    await approve_family(client, users, current)
    incomplete = await client.post(endpoint, headers=owner, json={**body, "profile_versions": {current["member"]: 2}})
    assert incomplete.status_code == 409 and incomplete.json()["code"] == "profile_version_conflict"
    response = await client.post(endpoint, headers=owner, json=body)
    assert response.status_code == 201, response.text
    initial = response.json()
    assert initial["member_ids"] == sorted([current["member"], current["second"]])
    assert (await client.post(endpoint, headers=owner, json=body)).json() == initial
    for member, energy, coverage in [(current["member"], "300.00", 3), (current["second"], "60.00", 1)]:
        response = await client.get(f"{ROOT}/members/{member}/adopted-plan?plan_date=2026-10-07", headers=owner)
        value = response.json()
        assert response.status_code == 200 and value["status"] == "ready", response.text
        assert value["plan"]["adoption_id"] == initial["adoption_id"]
        assert value["member_plan"]["nutrition"]["totals"]["energy_kcal"] == energy
        assert len(value["member_plan"]["covered_meals"]) == coverage
    for other in users[1:]:
        assert (
            await client.get(f"{ROOT}/meal-plan-adoptions/{initial['adoption_id']}", headers=other["headers"])
        ).status_code == 404
    async with pg_manager.get_async_session_context() as session:
        pointers = (
            await session.scalars(
                select(HealthMealPlanAdoptionMember).where(HealthMealPlanAdoptionMember.actor_uid == users[0]["uid"])
            )
        ).all()
        assert sorted(p.member_id for p in pointers) == initial["member_ids"]
        assert {p.adoption_id for p in pointers} == {initial["adoption_id"]}
    body = {"client_request_id": str(uuid4()), "version": 1, "reason": "共同餐单取消"}
    response = await client.post(
        f"{ROOT}/meal-plan-adoptions/{initial['adoption_id']}/withdraw", headers=owner, json=body
    )
    assert response.status_code == 200 and response.json()["status"] == "withdrawn"
    assert response.json()["snapshot"] == initial["snapshot"]
    for member in initial["member_ids"]:
        response = await client.get(f"{ROOT}/members/{member}/adopted-plan?plan_date=2026-10-07", headers=owner)
        assert response.json()["plan"] is None


@pytest.mark.parametrize("source", ["profile", "reviewer_grant", "applicant_grant"])
async def test_second_member_changes_invalidate_shared_adoption_permanently(health_http, source):  # noqa: F811
    """第二成员改源或撤权立即使共同使用失效，恢复和重放不复活。"""
    from yuxi.services.health_vision_types import HEALTH_SCOPES

    client, users = health_http
    current = await setup_family(client, users)
    await approve_family(client, users, current)
    owner = users[0]["headers"]
    endpoint = f"{ROOT}/meal-plans/{current['plan']}/adopt"
    body = selection(current)
    response = await client.post(endpoint, headers=owner, json=body)
    assert response.status_code == 201, response.text
    initial = response.json()
    if source == "profile":
        response = await client.post(
            f"{ROOT}/members/{current['second']}/external-profile-versions",
            headers=users[2]["headers"],
            json={**current["profile"], "version": 2, "source_version": "v2"},
        )
        assert response.status_code == 201, response.text
    else:
        target = users[1]["uid"] if source == "reviewer_grant" else users[0]["uid"]
        response = await client.put(
            f"{ROOT}/members/{current['second']}/grants",
            headers=owner,
            json={"actor_uid": target, "scopes": [] if source == "reviewer_grant" else ["profile_edit"]},
        )
        assert response.status_code == 200, response.text
        if source == "applicant_grant":
            assert (
                await client.get(f"{ROOT}/meal-plan-adoptions/{initial['adoption_id']}", headers=owner)
            ).status_code == 404
            today = await client.get(
                f"{ROOT}/members/{current['member']}/adopted-plan?plan_date=2026-10-07", headers=owner
            )
            assert today.status_code == 200 and today.json()["plan"] is None
        response = await client.put(
            f"{ROOT}/members/{current['second']}/grants",
            headers=owner,
            json={
                "actor_uid": target,
                "scopes": ["profile_view", "professional_review"]
                if source == "reviewer_grant"
                else sorted(HEALTH_SCOPES),
            },
        )
        assert response.status_code == 200, response.text
    async with pg_manager.get_async_session_context() as session:
        row = await session.get(HealthMealPlanAdoption, initial["adoption_id"])
        assert (row.status, row.version, row.snapshot, row.sources) == (
            "invalidated",
            2,
            initial["snapshot"],
            initial["sources"],
        )
    response = await client.post(endpoint, headers=owner, json=body)
    assert response.status_code == 201 and response.json()["current"] is False, response.text


async def test_multiple_overlapping_adoptions_require_exact_selection_and_atomic_replacement(health_http):  # noqa: F811
    """两个单人采用合成共同采用，漏选/错版本不改变旧状态。"""
    client, users = health_http
    current = await setup_family(client, users)
    await approve_family(client, users, current)
    owner = users[0]["headers"]
    previous = []
    for member in [current["member"], current["second"]]:
        plan, body = await save_approved(client, users, current, member)
        response = await client.post(f"{ROOT}/meal-plans/{plan}/adopt", headers=owner, json=body)
        assert response.status_code == 201, response.text
        previous.append(response.json())
    endpoint = f"{ROOT}/meal-plans/{current['plan']}/adopt"
    for replacements in [
        {},
        {previous[0]["adoption_id"]: 1},
        {p["adoption_id"]: 2 for p in previous},
        {**{p["adoption_id"]: 1 for p in previous}, str(uuid4()): 1},
    ]:
        response = await client.post(endpoint, headers=owner, json=selection(current, replaces_adoptions=replacements))
        assert response.status_code == 409 and response.json()["code"] == "adoption_version_conflict", response.text
    response = await client.post(
        endpoint, headers=owner, json=selection(current, replaces_adoptions={p["adoption_id"]: 1 for p in previous})
    )
    assert response.status_code == 201, response.text
    active = response.json()
    async with pg_manager.get_async_session_context() as session:
        for old in previous:
            row = await session.get(HealthMealPlanAdoption, old["adoption_id"])
            assert (row.status, row.version, row.snapshot) == ("superseded", 2, old["snapshot"])
        for member in [current["member"], current["second"]]:
            pointer = await session.get(HealthMealPlanAdoptionMember, (users[0]["uid"], member, date(2026, 10, 7)))
            assert pointer.adoption_id == active["adoption_id"]
    # 共同对象整体被单人方案替代，未参加新版的B不会继续使用旧共同方案。
    plan, body = await save_approved(client, users, current, current["member"])
    response = await client.post(
        f"{ROOT}/meal-plans/{plan}/adopt",
        headers=owner,
        json={**body, "replaces_adoption_id": active["adoption_id"], "replaces_version": 1},
    )
    assert response.status_code == 201, response.text
    assert (
        await client.get(f"{ROOT}/members/{current['second']}/adopted-plan?plan_date=2026-10-07", headers=owner)
    ).json()["plan"] is None


async def test_opposite_family_anchors_compete_for_same_member_occupancies(health_http):  # noqa: F811
    """相反入口并发采用同组成员，只一成功且没有死锁或双重占用。"""
    client, users = health_http
    current = await setup_family(client, users)
    await approve_family(client, users, current)
    plan, body = await save_approved(client, users, current, current["second"], family=True)
    responses = await asyncio.wait_for(
        asyncio.gather(
            client.post(
                f"{ROOT}/meal-plans/{current['plan']}/adopt", headers=users[0]["headers"], json=selection(current)
            ),
            client.post(f"{ROOT}/meal-plans/{plan}/adopt", headers=users[0]["headers"], json=body),
        ),
        timeout=20,
    )
    assert sorted(r.status_code for r in responses) == [201, 409], [r.text for r in responses]
    winner = next(r.json() for r in responses if r.status_code == 201)
    async with pg_manager.get_async_session_context() as session:
        rows = (
            await session.scalars(
                select(HealthMealPlanAdoption).where(HealthMealPlanAdoption.actor_uid == users[0]["uid"])
            )
        ).all()
        assert len(rows) == 1 and rows[0].id == winner["adoption_id"]


async def test_pointer_write_failure_rolls_back_replacements_and_action_receipt(health_http):  # noqa: F811
    """真实PG故障发生在指针写入，旧采用及指针不能留下部分替换。"""
    client, users = health_http
    current = await setup_family(client, users)
    await approve_family(client, users, current)
    owner = users[0]["headers"]
    endpoint = f"{ROOT}/meal-plans/{current['plan']}/adopt"
    initial = (await client.post(endpoint, headers=owner, json=selection(current))).json()
    key = uuid4().hex
    function, trigger = f"pytest_adoption_fail_{key}", f"pytest_adoption_trigger_{key}"
    body = selection(current, replaces_adoptions={initial["adoption_id"]: 1})
    try:
        async with pg_manager.get_async_session_context() as session:
            await session.execute(
                text(
                    f"CREATE FUNCTION {function}() RETURNS trigger LANGUAGE plpgsql AS $$ "
                    "BEGIN RAISE EXCEPTION 'synthetic pointer failure'; END $$"
                )
            )
            await session.execute(
                text(
                    f"CREATE TRIGGER {trigger} BEFORE UPDATE ON health_meal_plan_adoption_member "
                    f"FOR EACH ROW WHEN (OLD.member_id = '{max(current['member'], current['second'])}') "
                    f"EXECUTE FUNCTION {function}()"
                )
            )
        response = await client.post(endpoint, headers=owner, json=body)
        assert response.status_code == 500, response.text
        async with pg_manager.get_async_session_context() as session:
            rows = (
                await session.scalars(
                    select(HealthMealPlanAdoption).where(HealthMealPlanAdoption.actor_uid == users[0]["uid"])
                )
            ).all()
            assert len(rows) == 1 and (rows[0].id, rows[0].status, rows[0].version) == (
                initial["adoption_id"],
                "active",
                1,
            )
            pointers = (
                await session.scalars(
                    select(HealthMealPlanAdoptionMember).where(
                        HealthMealPlanAdoptionMember.actor_uid == users[0]["uid"]
                    )
                )
            ).all()
            assert len(pointers) == 2 and {p.adoption_id for p in pointers} == {initial["adoption_id"]}
            receipt = await session.scalar(
                select(HealthMealPlanAdoptionAction).where(
                    HealthMealPlanAdoptionAction.request_id == body["client_request_id"]
                )
            )
            assert receipt is None
    finally:
        async with pg_manager.get_async_session_context() as session:
            await session.execute(text(f"DROP TRIGGER IF EXISTS {trigger} ON health_meal_plan_adoption_member"))
            await session.execute(text(f"DROP FUNCTION IF EXISTS {function}()"))
    response = await client.post(endpoint, headers=owner, json=body)
    assert response.status_code == 201, response.text


async def test_replacing_family_with_one_member_locks_old_union_in_sorted_order(health_http):  # noqa: F811
    """新计划只含较大ID，仍须先等待旧家庭的较小ID，不逆序占有新成员。"""
    client, users = health_http
    current = await setup_family(client, users)
    await approve_family(client, users, current)
    owner = users[0]["headers"]
    response = await client.post(f"{ROOT}/meal-plans/{current['plan']}/adopt", headers=owner, json=selection(current))
    assert response.status_code == 201, response.text
    initial = response.json()
    small, large = sorted([current["member"], current["second"]])
    plan, body = await save_approved(client, users, current, large)
    body.update(replaces_adoption_id=initial["adoption_id"], replaces_version=1)
    blocked = 0
    call = None
    try:
        async with pg_manager.get_async_session_context() as session:
            await session.scalar(select(FamilyMember).where(FamilyMember.id == small).with_for_update())
            blocker = await session.scalar(select(func.pg_backend_pid()))
            call = asyncio.create_task(client.post(f"{ROOT}/meal-plans/{plan}/adopt", headers=owner, json=body))
            for _ in range(100):
                async with pg_manager.get_async_session_context() as observer:
                    blocked = await observer.scalar(
                        text("SELECT count(*) FROM pg_stat_activity WHERE :pid = ANY(pg_blocking_pids(pid))"),
                        {"pid": blocker},
                    )
                if blocked == 1:
                    break
                await asyncio.sleep(0.05)
            async with pg_manager.get_async_session_context() as observer:
                free = await observer.scalar(
                    select(FamilyMember).where(FamilyMember.id == large).with_for_update(nowait=True)
                )
                assert free is not None, "等待旧小成员时不得提前占有新大成员"
        response = await asyncio.wait_for(call, timeout=20)
        assert blocked == 1 and response.status_code == 201, response.text
    finally:
        if call is not None and not call.done():
            await asyncio.wait_for(call, timeout=20)


@pytest.mark.parametrize("expands", [False, True])
async def test_today_reader_rechecks_pointer_after_waiting_for_replacement(health_http, expands):  # noqa: F811
    """实际HTTP读在替代之后取得锁，须读取新版或明确要求刷新额外参与者。"""
    client, users = health_http
    current = await setup_family(client, users)
    await approve_family(client, users, current)
    owner = users[0]["headers"]
    if expands:
        old_plan, old_body = await save_approved(client, users, current, current["member"])
        initial = await client.post(f"{ROOT}/meal-plans/{old_plan}/adopt", headers=owner, json=old_body)
        new_plan, new_body = current["plan"], selection(current)
    else:
        initial = await client.post(
            f"{ROOT}/meal-plans/{current['plan']}/adopt", headers=owner, json=selection(current)
        )
        new_plan, new_body = await save_approved(client, users, current, current["second"], family=True)
    assert initial.status_code == 201, initial.text
    new_body.update(replaces_adoption_id=initial.json()["adoption_id"], replaces_version=1)
    member = current["member"]
    locked = member if expands else min(member, current["second"])
    tasks = []
    waits = []
    try:
        async with pg_manager.get_async_session_context() as session:
            await session.scalar(select(FamilyMember).where(FamilyMember.id == locked).with_for_update())
            blocker = await session.scalar(select(func.pg_backend_pid()))
            for expected in (1, 2):
                tasks.append(
                    asyncio.create_task(
                        client.post(f"{ROOT}/meal-plans/{new_plan}/adopt", headers=owner, json=new_body)
                        if expected == 1
                        else client.get(f"{ROOT}/members/{member}/adopted-plan?plan_date=2026-10-07", headers=owner)
                    )
                )
                blocked = 0
                for _ in range(100):
                    async with pg_manager.get_async_session_context() as observer:
                        blocked = await observer.scalar(
                            text("""WITH RECURSIVE waiting(pid) AS (
                            SELECT pid FROM pg_stat_activity WHERE :pid = ANY(pg_blocking_pids(pid))
                            UNION SELECT a.pid FROM pg_stat_activity a JOIN waiting w
                            ON w.pid = ANY(pg_blocking_pids(a.pid))
                        ) SELECT count(*) FROM waiting"""),
                            {"pid": blocker},
                        )
                    if blocked == expected:
                        break
                    await asyncio.sleep(0.05)
                waits.append(blocked)
        replaced, read = await asyncio.wait_for(asyncio.gather(*tasks), timeout=20)
        assert waits == [1, 2] and replaced.status_code == 201, [r.text for r in (replaced, read)]
        if expands:
            assert read.status_code == 409 and read.json()["code"] == "adoption_version_conflict", read.text
            read = await client.get(f"{ROOT}/members/{member}/adopted-plan?plan_date=2026-10-07", headers=owner)
        assert read.status_code == 200 and read.json()["status"] == "ready", read.text
        assert read.json()["plan"]["adoption_id"] == replaced.json()["adoption_id"]
    finally:
        if tasks:
            await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), timeout=20)

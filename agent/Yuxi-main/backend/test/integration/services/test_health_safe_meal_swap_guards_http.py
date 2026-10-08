"""候选读取后的真实来源变化、幂等及HTTP条件边界。"""

import asyncio
from copy import deepcopy
from datetime import datetime, timedelta, UTC
from uuid import uuid4

import pytest
from sqlalchemy import func, select, text

from test.integration.services.test_health_vision_http import ROOT, health_http  # noqa: F401
from test.integration.services.test_health_quality_http import action
from test.integration.services.test_health_safe_meal_swap_http import setup_swap, selection, candidates, swap
from test.integration.services.test_health_safe_plan_regeneration_http import (
    preview as regeneration_preview,
    save as regeneration_save,
    selection as regeneration_selection,
)
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_health import (
    RecipeVersion,
    HealthMealPlan,
    HealthMealPlanRevision,
    HealthQualityCheck,
    HealthProfessionalReview,
    HealthMealPlanAdoption,
)

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_same_key_concurrent_replay_cross_plan_and_http_input_guards(health_http):  # noqa: F811
    """同键竞争只有一次写入，跨对象复用及伪造HTTP输入全部拒绝。"""
    client, users = health_http
    current = await setup_swap(client, users, count=1)
    owner = users[0]["headers"]
    endpoint = f"{ROOT}/meal-plans/{current['plan']}/safe-swap"
    body = {**selection(current), "client_request_id": str(uuid4()), "recipe_version_id": current["eligible"][0]}
    good_headers = {**owner, "Idempotency-Key": body["client_request_id"], "If-Match": '"1"'}
    for headers, status in [
        (owner, 422),
        ({**good_headers, "Idempotency-Key": str(uuid4())}, 422),
        ({**good_headers, "If-Match": '"2"'}, 409),
        ({**owner, "Idempotency-Key": body["client_request_id"]}, 409),
    ]:
        assert (await client.post(endpoint, headers=headers, json=body)).status_code == status
    for field in ["grams", "nutrition", "safety_check", "professional_review"]:
        assert (await client.post(endpoint, headers=good_headers, json={**body, field: "forged"})).status_code == 422
    responses = await asyncio.gather(
        *(swap(client, owner, current, current["eligible"][0], body=body) for _ in range(2))
    )
    assert [r.status_code for r in responses] == [200, 200], [r.text for r in responses]
    assert responses[0].json()["quality_check"]["check_id"] == responses[1].json()["quality_check"]["check_id"]
    async with pg_manager.get_async_session_context() as session:
        plan = await session.get(HealthMealPlan, current["plan"])
        assert plan.version == 2
        spec = deepcopy(plan.spec)
        assert (
            await session.scalar(
                select(func.count())
                .select_from(HealthMealPlanRevision)
                .where(HealthMealPlanRevision.plan_id == plan.id)
            )
            == 2
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(HealthQualityCheck)
                .where(HealthQualityCheck.plan_id == plan.id, HealthQualityCheck.plan_version == 2)
            )
            == 1
        )
    preview = await client.post(f"{ROOT}/members/{current['member']}/meal-plan-previews", headers=owner, json=spec)
    key = str(uuid4())
    newplan = await client.post(
        f"{ROOT}/members/{current['member']}/meal-plans",
        headers={**owner, "Idempotency-Key": key},
        json={"client_request_id": key, "preview_id": preview.json()["preview_id"]},
    )
    assert newplan.status_code == 201, newplan.text
    cross = await client.post(
        f"{ROOT}/meal-plans/{newplan.json()['plan_id']}/safe-swap", headers=good_headers, json=body
    )
    assert cross.status_code == 409 and cross.json()["code"] == "request_conflict"
    async with pg_manager.get_async_session_context() as session:
        assert (await session.get(HealthMealPlan, newplan.json()["plan_id"])).version == 1


@pytest.mark.parametrize("changed", ["candidate_source", "profile_expiry", "rules_expiry"])
async def test_dependency_changes_after_candidate_read_fail_without_partial_commit(health_http, changed):  # noqa: F811
    """真实候选读后改源或自然过期，失败不会修改计划、审核、采用和检查。"""
    client, users = health_http
    current = await setup_swap(client, users, count=1)
    owner, admin = users[0]["headers"], users[2]["headers"]
    kwargs = {}
    expiry = None
    if changed in {"profile_expiry", "rules_expiry"}:
        expiry = datetime.now(UTC) + timedelta(seconds=8)
        body = deepcopy(current["profile"] if changed == "profile_expiry" else current["rules"])
        version = 2 if changed == "profile_expiry" else 3
        body.update(version=version, source_version=f"v{version}", valid_until=expiry.isoformat())
        endpoint = (
            f"{ROOT}/members/{current['member']}/external-profile-versions"
            if changed == "profile_expiry"
            else f"{ROOT}/approved-quality-rules"
        )
        response = await client.post(endpoint, headers=admin, json=body)
        assert response.status_code == 201, response.text
        kwargs["profile_version" if changed == "profile_expiry" else "rule_version"] = version
    checked = await client.post(
        f"{ROOT}/meal-plans/{current['plan']}/quality-checks",
        headers=owner,
        json={"client_request_id": str(uuid4()), "version": 1, "rule_code": current["rules"]["rule_code"]},
    )
    assert checked.status_code == 201 and checked.json()["safety_check"]["status"] == "passed", checked.text
    read = await client.get(f"{ROOT}/quality-checks/{checked.json()['check_id']}", headers=owner)
    case = read.json()["review"]["review_id"]
    await action(client, owner, case, "submit", 1)
    await action(client, users[1]["headers"], case, "approve", 2)
    adopted = await client.post(
        f"{ROOT}/meal-plans/{current['plan']}/adopt",
        headers=owner,
        json={
            "client_request_id": str(uuid4()),
            "version": 1,
            "review_id": case,
            "profile_versions": {current["member"]: kwargs.get("profile_version", 1)},
        },
    )
    assert adopted.status_code == 201, adopted.text
    aid = adopted.json()["adoption_id"]
    listed = await candidates(client, owner, current, **kwargs)
    assert listed["candidates"] and listed["candidates"][0]["recipe_version_id"] == current["eligible"][0]
    async with pg_manager.get_async_session_context() as session:
        old = deepcopy((await session.get(HealthMealPlan, current["plan"])).snapshot)
        checks = await session.scalar(
            select(func.count()).select_from(HealthQualityCheck).where(HealthQualityCheck.plan_id == current["plan"])
        )
    if changed == "candidate_source":
        async with pg_manager.get_async_session_context() as session:
            row = await session.get(RecipeVersion, current["eligible"][0])
            row.nutrients = {**row.nutrients, "energy_kcal": "999"}
    else:
        await asyncio.sleep(max(0, (expiry - datetime.now(UTC)).total_seconds()) + 0.1)
    body = {
        **selection(current, **kwargs),
        "client_request_id": str(uuid4()),
        "recipe_version_id": current["eligible"][0],
    }
    response = await swap(client, owner, current, current["eligible"][0], body=body)
    assert response.status_code == 409 and response.json()["code"] == "safe_candidate_required", response.text
    async with pg_manager.get_async_session_context() as session:
        plan = await session.get(HealthMealPlan, current["plan"])
        assert plan.version == 1 and plan.snapshot == old
        assert (
            await session.scalar(
                select(func.count())
                .select_from(HealthMealPlanRevision)
                .where(HealthMealPlanRevision.plan_id == plan.id)
            )
            == 1
        )
        assert (
            await session.scalar(
                select(func.count()).select_from(HealthQualityCheck).where(HealthQualityCheck.plan_id == plan.id)
            )
            == checks
        )
        assert (await session.get(HealthProfessionalReview, case)).status == "approved"
        assert (await session.get(HealthMealPlanAdoption, aid)).status == "active"


async def test_grant_revoked_after_read_prevents_swap_and_restoration_allows_fresh_request(health_http):  # noqa: F811
    """共享授权账号维护自己的私有草稿，读后撤权也不能写；恢复须新验证。"""
    client, users = health_http
    current = await setup_swap(client, users, count=1)
    owner, actor = users[0]["headers"], users[1]["headers"]
    grant = {"actor_uid": users[1]["uid"], "scopes": ["diet_edit", "profile_view"]}
    assert (
        await client.put(f"{ROOT}/members/{current['member']}/grants", headers=owner, json=grant)
    ).status_code == 200
    async with pg_manager.get_async_session_context() as session:
        spec = deepcopy((await session.get(HealthMealPlan, current["plan"])).spec)
    preview = await client.post(f"{ROOT}/members/{current['member']}/meal-plan-previews", headers=actor, json=spec)
    key = str(uuid4())
    saved = await client.post(
        f"{ROOT}/members/{current['member']}/meal-plans",
        headers={**actor, "Idempotency-Key": key},
        json={"client_request_id": key, "preview_id": preview.json()["preview_id"]},
    )
    assert saved.status_code == 201, saved.text
    current = {**current, "plan": saved.json()["plan_id"]}
    assert (await candidates(client, actor, current))["candidates"]
    assert (
        await client.put(f"{ROOT}/members/{current['member']}/grants", headers=owner, json={**grant, "scopes": []})
    ).status_code == 200
    response = await swap(client, actor, current, current["eligible"][0])
    assert response.status_code == 404, response.text
    async with pg_manager.get_async_session_context() as session:
        assert (await session.get(HealthMealPlan, current["plan"])).version == 1
        assert (
            await session.scalar(
                select(func.count())
                .select_from(HealthMealPlanRevision)
                .where(HealthMealPlanRevision.plan_id == current["plan"])
            )
            == 1
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(HealthQualityCheck)
                .where(HealthQualityCheck.plan_id == current["plan"])
            )
            == 0
        )
    assert (
        await client.put(f"{ROOT}/members/{current['member']}/grants", headers=owner, json=grant)
    ).status_code == 200
    assert (await swap(client, actor, current, current["eligible"][0])).status_code == 200


@pytest.mark.parametrize("operation", ["swap", "regeneration"])
async def test_expiry_during_final_check_rolls_back_plan_review_and_adoption(health_http, operation):  # noqa: F811
    """真实审核行锁暂停单菜或整份改版，过期后全部写入一起回滚。"""
    client, users = health_http
    current = await setup_swap(client, users, count=1)
    owner, admin = users[0]["headers"], users[2]["headers"]
    expiry = datetime.now(UTC) + timedelta(seconds=15)
    rules = deepcopy(current["rules"])
    rules.update(version=3, source_version="v3", valid_until=expiry.isoformat())
    response = await client.post(f"{ROOT}/approved-quality-rules", headers=admin, json=rules)
    assert response.status_code == 201, response.text
    checked = await client.post(
        f"{ROOT}/meal-plans/{current['plan']}/quality-checks",
        headers=owner,
        json={"client_request_id": str(uuid4()), "version": 1, "rule_code": rules["rule_code"]},
    )
    assert checked.status_code == 201 and checked.json()["safety_check"]["status"] == "passed", checked.text
    read = await client.get(f"{ROOT}/quality-checks/{checked.json()['check_id']}", headers=owner)
    case = read.json()["review"]["review_id"]
    await action(client, owner, case, "submit", 1)
    await action(client, users[1]["headers"], case, "approve", 2)
    adopted = await client.post(
        f"{ROOT}/meal-plans/{current['plan']}/adopt",
        headers=owner,
        json={
            "client_request_id": str(uuid4()),
            "version": 1,
            "review_id": case,
            "profile_versions": {current["member"]: 1},
        },
    )
    assert adopted.status_code == 201, adopted.text
    aid = adopted.json()["adoption_id"]
    generated = (
        await regeneration_preview(client, owner, current, rule_version=3) if operation == "regeneration" else None
    )
    async with pg_manager.get_async_session_context() as session:
        original = deepcopy((await session.get(HealthMealPlan, current["plan"])).snapshot)
        count = await session.scalar(
            select(func.count()).select_from(HealthQualityCheck).where(HealthQualityCheck.plan_id == current["plan"])
        )
    task = None
    try:
        async with pg_manager.get_async_session_context() as blocker:
            await blocker.scalar(
                select(HealthProfessionalReview).where(HealthProfessionalReview.id == case).with_for_update()
            )
            blocker_pid = await blocker.scalar(text("SELECT pg_backend_pid()"))
            body = {
                **selection(current, rule_version=3),
                "recipe_version_id": current["eligible"][0],
                "client_request_id": str(uuid4()),
            }
            if operation == "regeneration":
                body = {
                    **regeneration_selection(current, rule_version=3),
                    "client_request_id": str(uuid4()),
                    "preview_hash": generated["preview_hash"],
                }
                task = asyncio.create_task(regeneration_save(client, owner, current, body))
            else:
                task = asyncio.create_task(swap(client, owner, current, current["eligible"][0], body=body))
            waited = False
            for _ in range(100):
                async with pg_manager.get_async_session_context() as observer:
                    waited = bool(
                        await observer.scalar(
                            text(
                                "SELECT EXISTS(SELECT 1 FROM pg_stat_activity WHERE wait_event_type='Lock' "
                                "AND :blocker=ANY(pg_blocking_pids(pid)) "
                                "AND query LIKE '%UPDATE health_professional_review%')"
                            ),
                            {"blocker": blocker_pid},
                        )
                    )
                if waited:
                    break
                assert not task.done(), "HTTP未在审核失效写入窗口等待"
                await asyncio.sleep(0.05)
            assert waited, "未观察到被当前审核行锁阻塞的换菜UPDATE"
            await asyncio.sleep(max(0, (expiry - datetime.now(UTC)).total_seconds()) + 0.1)
        response = await task
        assert response.status_code == 409 and response.json()["code"] == "quality_not_passed", response.text
    finally:
        if task and not task.done():
            await task
    async with pg_manager.get_async_session_context() as session:
        plan = await session.get(HealthMealPlan, current["plan"])
        assert plan.version == 1 and plan.snapshot == original
        assert (
            await session.scalar(
                select(func.count())
                .select_from(HealthMealPlanRevision)
                .where(HealthMealPlanRevision.plan_id == plan.id)
            )
            == 1
        )
        assert (
            await session.scalar(
                select(func.count()).select_from(HealthQualityCheck).where(HealthQualityCheck.plan_id == plan.id)
            )
            == count
        )
        review = await session.get(HealthProfessionalReview, case)
        adoption = await session.get(HealthMealPlanAdoption, aid)
        assert (review.status, review.version) == ("approved", 3)
        assert (adoption.status, adoption.version) == ("active", 1) and adoption.snapshot == adopted.json()["snapshot"]

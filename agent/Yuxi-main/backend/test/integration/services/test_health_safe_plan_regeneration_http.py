"""真实HTTP/PG证明三餐共同修复及确认保存边界。"""

import asyncio
from copy import deepcopy
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from test.integration.services.test_health_vision_http import ROOT, health_http  # noqa: F401
from test.integration.services.test_health_quality_http import action
from test.integration.services.test_health_safe_meal_swap_http import setup_swap, candidates
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_health import (
    HealthMealPlan,
    HealthMealPlanRevision,
    HealthQualityCheck,
    HealthProfessionalReview,
    HealthMealPlanAdoption,
    DietLog,
    HealthMemoryFact,
    RecipeVersion,
)

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


def selection(current, *, version=1, rule_version=2, profile_version=1):
    """只携带当前版本及批准规则选择。"""
    return {
        "version": version,
        "rule_code": current["rules"]["rule_code"],
        "rule_version": rule_version,
        "profile_version": profile_version,
    }


async def preview(client, owner, current, **kwargs):
    """预览读取实际HTTP结果。"""
    response = await client.post(
        f"{ROOT}/meal-plans/{current['plan']}/regeneration-preview", headers=owner, json=selection(current, **kwargs)
    )
    assert response.status_code == 200, response.text
    return response.json()


async def save(client, owner, current, body):
    """确认摘要经实际条件头边界保存。"""
    return await client.post(
        f"{ROOT}/meal-plans/{current['plan']}/safe-regenerate",
        headers={**owner, "Idempotency-Key": body["client_request_id"], "If-Match": f'"{body["version"]}"'},
        json=body,
    )


async def assert_original(session, current):
    """独立PG事实证明失败与预览没有产生修订或饮食记录。"""
    row = await session.get(HealthMealPlan, current["plan"])
    assert row.version == 1 and row.snapshot["nutrition"]["totals"]["energy_kcal"] == "300.00"
    assert (
        await session.scalar(
            select(func.count()).select_from(HealthMealPlanRevision).where(HealthMealPlanRevision.plan_id == row.id)
        )
        == 1
    )
    assert await session.scalar(select(DietLog).where(DietLog.member_id == current["member"])) is None
    assert await session.scalar(select(HealthMemoryFact).where(HealthMemoryFact.member_id == current["member"])) is None


async def test_three_meals_repair_jointly_where_single_swap_has_no_solution(health_http):  # noqa: F811
    """独立手算全换110kcal/100g才得到330，任何单菜都不合格。"""
    client, users = health_http
    current = await setup_swap(client, users, count=1)
    owner = users[0]["headers"]
    body = deepcopy(current["rules"])
    body.update(version=3, source_version="v3")
    body["payload"]["daily_bounds"]["energy_kcal"] = {"minimum": "330", "maximum": "330"}
    response = await client.post(f"{ROOT}/approved-quality-rules", headers=users[2]["headers"], json=body)
    assert response.status_code == 201, response.text
    assert (await candidates(client, owner, current, rule_version=3))["candidates"] == []
    generated = await preview(client, owner, current, rule_version=3)
    assert generated["status"] == "ready" and generated["safety_check"]["status"] == "passed"
    assert generated["plan_snapshot"]["nutrition"]["totals"]["energy_kcal"] == "330.00"
    assert [m["dishes"][0]["nutrition"]["energy_kcal"] for m in generated["plan_snapshot"]["meals"]] == [
        "55.00",
        "110.00",
        "165.00",
    ]
    assert all(m["dishes"][0]["recipe_version_id"] != current["old"] for m in generated["plan_spec"]["meals"])
    async with pg_manager.get_async_session_context() as session:
        await assert_original(session, current)
    payload = {
        **selection(current, rule_version=3),
        "client_request_id": str(uuid4()),
        "preview_hash": generated["preview_hash"],
    }
    written = await save(client, owner, current, payload)
    assert written.status_code == 200, written.text
    assert written.json()["version"] == 2 and written.json()["nutrition"]["totals"]["energy_kcal"] == "330.00"
    async with pg_manager.get_async_session_context() as session:
        row = await session.get(HealthMealPlan, current["plan"])
        assert row.spec == generated["plan_spec"]
        revisions = list(
            (
                await session.scalars(
                    select(HealthMealPlanRevision)
                    .where(HealthMealPlanRevision.plan_id == row.id)
                    .order_by(HealthMealPlanRevision.version)
                )
            ).all()
        )
        assert len(revisions) == 2 and revisions[0].snapshot["nutrition"]["totals"]["energy_kcal"] == "300.00"
        assert revisions[1].snapshot["nutrition"]["totals"]["energy_kcal"] == "330.00"
        check = await session.get(HealthQualityCheck, written.json()["quality_check"]["check_id"])
        case = await session.scalar(
            select(HealthProfessionalReview).where(HealthProfessionalReview.check_id == check.id)
        )
        assert check.plan_version == 2 and case.status == "draft"
        assert await session.scalar(select(DietLog).where(DietLog.member_id == current["member"])) is None


async def test_confirmed_plan_invalidates_old_approval_adoption_and_same_key_writes_once(health_http):  # noqa: F811
    """当前专业流程走完后重生成，历史不变且幂等竞争只有一次改版。"""
    client, users = health_http
    current = await setup_swap(client, users, count=1)
    owner = users[0]["headers"]
    checked = await client.post(
        f"{ROOT}/meal-plans/{current['plan']}/quality-checks",
        headers=owner,
        json={"client_request_id": str(uuid4()), "version": 1, "rule_code": current["rules"]["rule_code"]},
    )
    assert checked.status_code == 201, checked.text
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
    generated = await preview(client, owner, current)
    assert (
        generated["status"] == "ready" and generated["plan_snapshot"]["nutrition"]["totals"]["energy_kcal"] == "305.00"
    )
    payload = {**selection(current), "client_request_id": str(uuid4()), "preview_hash": generated["preview_hash"]}
    responses = await asyncio.gather(*(save(client, owner, current, payload) for _ in range(2)))
    assert [r.status_code for r in responses] == [200, 200], [r.text for r in responses]
    result = responses[0].json()
    assert result["quality_check"]["check_id"] == responses[1].json()["quality_check"]["check_id"]
    conflict = await save(client, owner, current, {**payload, "preview_hash": "0" * 64})
    assert conflict.status_code == 409 and conflict.json()["code"] == "request_conflict"
    async with pg_manager.get_async_session_context() as session:
        row = await session.get(HealthMealPlan, current["plan"])
        assert row.version == 2 and row.spec == generated["plan_spec"]
        assert (
            await session.scalar(
                select(func.count()).select_from(HealthMealPlanRevision).where(HealthMealPlanRevision.plan_id == row.id)
            )
            == 2
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(HealthQualityCheck)
                .where(HealthQualityCheck.plan_id == row.id, HealthQualityCheck.plan_version == 2)
            )
            == 1
        )
        assert (await session.get(HealthProfessionalReview, case)).status == "invalidated"
        adoption = await session.get(HealthMealPlanAdoption, adopted.json()["adoption_id"])
        assert adoption.status == "invalidated" and adoption.snapshot == adopted.json()["snapshot"]
        assert await session.scalar(select(DietLog).where(DietLog.member_id == current["member"])) is None


@pytest.mark.parametrize("missing", ["swap_rules", "profile", "daily_bounds", "no_plan"])
async def test_missing_dependencies_or_exhaustive_no_solution_keep_original(health_http, missing):  # noqa: F811
    """不同缺依赖与穷尽无解有明确原因，不能通过用户确认强行写入。"""
    client, users = health_http
    current = await setup_swap(client, users, count=1)
    owner = users[0]["headers"]
    body = deepcopy(current["rules"])
    body.update(version=3, source_version="v3")
    if missing == "swap_rules":
        body["payload"].pop("meal_swap")
    elif missing == "daily_bounds":
        body["payload"]["daily_bounds"].pop("sodium_mg")
    elif missing == "no_plan":
        body["payload"]["daily_bounds"]["energy_kcal"] = {"minimum": "999", "maximum": "999"}
    else:
        profile = deepcopy(current["profile"])
        profile.update(version=2, source_version="v2")
        profile["payload"]["allergies"] = {"state": "unknown", "codes": []}
        imported = await client.post(
            f"{ROOT}/members/{current['member']}/external-profile-versions", headers=users[2]["headers"], json=profile
        )
        assert imported.status_code == 201, imported.text
    response = await client.post(f"{ROOT}/approved-quality-rules", headers=users[2]["headers"], json=body)
    assert response.status_code == 201, response.text
    kwargs = {"rule_version": 3, "profile_version": 2 if missing == "profile" else 1}
    generated = await preview(client, owner, current, **kwargs)
    reasons = {
        "swap_rules": "swap_rules_not_approved",
        "profile": "complete_profile_and_daily_rules_required",
        "daily_bounds": "complete_profile_and_daily_rules_required",
        "no_plan": "no_eligible_plan",
    }
    assert generated["status"] == "not_ready" and generated["reason"] == reasons[missing], generated
    if missing == "no_plan":
        assert generated["search"]["limited"] is False
    written = await save(
        client,
        owner,
        current,
        {**selection(current, **kwargs), "client_request_id": str(uuid4()), "preview_hash": "0" * 64},
    )
    assert written.status_code == 409 and written.json()["code"] == "safe_regeneration_unavailable"
    async with pg_manager.get_async_session_context() as session:
        await assert_original(session, current)


async def test_preview_digest_permissions_headers_and_changed_source_do_not_write(health_http):  # noqa: F811
    """摘要伪造、越权、条件头及预览后菜谱篡改均在真实HTTP拒绝。"""
    client, users = health_http
    current = await setup_swap(client, users, count=1)
    owner = users[0]["headers"]
    generated = await preview(client, owner, current)
    payload = {**selection(current), "client_request_id": str(uuid4()), "preview_hash": generated["preview_hash"]}
    endpoint = f"{ROOT}/meal-plans/{current['plan']}/safe-regenerate"
    headers = {**owner, "Idempotency-Key": payload["client_request_id"], "If-Match": '"1"'}
    for bad, status in [
        (owner, 422),
        ({**headers, "Idempotency-Key": str(uuid4())}, 422),
        ({**headers, "If-Match": '"2"'}, 409),
        ({**owner, "Idempotency-Key": payload["client_request_id"]}, 409),
    ]:
        assert (await client.post(endpoint, headers=bad, json=payload)).status_code == status
    for field in ["plan_spec", "nutrition", "safety_check", "professional_review"]:
        assert (await client.post(endpoint, headers=headers, json={**payload, field: "forged"})).status_code == 422
    for other in users[1:]:
        assert (
            await client.post(
                f"{ROOT}/meal-plans/{current['plan']}/regeneration-preview",
                headers=other["headers"],
                json=selection(current),
            )
        ).status_code == 404
        assert (await save(client, other["headers"], current, payload)).status_code == 404
    changed = await save(client, owner, current, {**payload, "preview_hash": "0" * 64})
    assert changed.status_code == 409 and changed.json()["code"] == "preview_changed"
    selected = next(
        d["recipe_version_id"]
        for m in generated["plan_spec"]["meals"]
        for d in m["dishes"]
        if d["recipe_version_id"] != current["old"]
    )
    async with pg_manager.get_async_session_context() as session:
        row = await session.get(RecipeVersion, selected)
        row.nutrients = {**row.nutrients, "energy_kcal": "180"}
    changed = await save(client, owner, current, payload)
    assert changed.status_code == 409 and changed.json()["code"] in {
        "preview_changed",
        "safe_regeneration_unavailable",
    }, changed.text
    async with pg_manager.get_async_session_context() as session:
        await assert_original(session, current)


async def test_joint_allergy_repair_filters_old_recipes_and_keeps_current_profile(health_http):  # noqa: F811
    """已确认过敏命中三餐原料，只替换一餐不能过，整份排除所有原菜。"""
    client, users = health_http
    current = await setup_swap(client, users, count=1)
    owner, admin = users[0]["headers"], users[2]["headers"]
    profile = deepcopy(current["profile"])
    profile.update(version=2, source_version="v2")
    profile["payload"]["allergies"] = {"state": "specified", "codes": ["synthetic_allergen"]}
    response = await client.post(
        f"{ROOT}/members/{current['member']}/external-profile-versions", headers=admin, json=profile
    )
    assert response.status_code == 201, response.text
    rules = deepcopy(current["rules"])
    rules.update(version=3, source_version="v3")
    rules["payload"]["ingredient_classifications"][0]["allergen_codes"] = ["synthetic_allergen"]
    response = await client.post(f"{ROOT}/approved-quality-rules", headers=admin, json=rules)
    assert response.status_code == 201, response.text
    assert (await candidates(client, owner, current, rule_version=3, profile_version=2))["candidates"] == []
    generated = await preview(client, owner, current, rule_version=3, profile_version=2)
    assert generated["status"] == "ready" and generated["safety_check"]["status"] == "passed"
    assert generated["plan_snapshot"]["nutrition"]["totals"]["energy_kcal"] == "330.00"
    assert all(d["recipe_version_id"] != current["old"] for m in generated["plan_spec"]["meals"] for d in m["dishes"])
    result = await save(
        client,
        owner,
        current,
        {
            **selection(current, rule_version=3, profile_version=2),
            "client_request_id": str(uuid4()),
            "preview_hash": generated["preview_hash"],
        },
    )
    assert result.status_code == 200, result.text
    async with pg_manager.get_async_session_context() as session:
        check = await session.get(HealthQualityCheck, result.json()["quality_check"]["check_id"])
        assert check.snapshot["sources"]["profiles"][current["member"]]["version"] == 2
        assert check.snapshot["sources"]["rules"]["version"] == 3 and check.plan_version == 2


async def test_original_classification_required_and_source_version_conflicts(health_http):  # noqa: F811
    """旧版本不能跨规则使用，无原菜批准类型不猜替换类别。"""
    client, users = health_http
    current = await setup_swap(client, users, count=1)
    owner, admin = users[0]["headers"], users[2]["headers"]
    generated = await preview(client, owner, current)
    rules = deepcopy(current["rules"])
    rules.update(version=3, source_version="v3")
    rules["payload"]["meal_swap"]["recipe_classifications"] = [
        c for c in rules["payload"]["meal_swap"]["recipe_classifications"] if c["recipe_version_id"] != current["old"]
    ]
    response = await client.post(f"{ROOT}/approved-quality-rules", headers=admin, json=rules)
    assert response.status_code == 201, response.text
    stale = await save(
        client,
        owner,
        current,
        {**selection(current), "client_request_id": str(uuid4()), "preview_hash": generated["preview_hash"]},
    )
    assert stale.status_code == 409 and stale.json()["code"] == "source_version_conflict"
    missing = await preview(client, owner, current, rule_version=3)
    assert missing["status"] == "not_ready" and missing["reason"] == "current_recipe_classification_not_approved"
    async with pg_manager.get_async_session_context() as session:
        await assert_original(session, current)


async def test_different_keys_cannot_overwrite_and_replay_after_profile_change_stays_invalid(health_http):  # noqa: F811
    """两个确认同旧版本只应用一个；换档案后同键重放不能恢复原检查。"""
    client, users = health_http
    current = await setup_swap(client, users, count=1)
    owner = users[0]["headers"]
    generated = await preview(client, owner, current)
    bodies = [
        {**selection(current), "client_request_id": str(uuid4()), "preview_hash": generated["preview_hash"]}
        for _ in range(2)
    ]
    responses = await asyncio.gather(*(save(client, owner, current, b) for b in bodies))
    assert sorted(r.status_code for r in responses) == [200, 410], [r.text for r in responses]
    winner = next(b for b, r in zip(bodies, responses) if r.status_code == 200)
    response = next(r for r in responses if r.status_code == 200)
    snapshot = await client.get(f"{ROOT}/meal-plans/{current['plan']}", headers=owner)
    spec = generated["plan_spec"]
    other_preview = await client.post(
        f"{ROOT}/members/{current['member']}/meal-plan-previews", headers=owner, json=spec
    )
    key = str(uuid4())
    other = await client.post(
        f"{ROOT}/members/{current['member']}/meal-plans",
        headers={**owner, "Idempotency-Key": key},
        json={"client_request_id": key, "preview_id": other_preview.json()["preview_id"]},
    )
    assert other.status_code == 201, other.text
    cross = await client.post(
        f"{ROOT}/meal-plans/{other.json()['plan_id']}/safe-regenerate",
        headers={**owner, "Idempotency-Key": winner["client_request_id"], "If-Match": '"1"'},
        json=winner,
    )
    assert cross.status_code == 409 and cross.json()["code"] == "request_conflict"
    from test.integration.services.test_health_safe_meal_swap_http import swap, selection as swap_selection

    reused = await swap(
        client,
        owner,
        current,
        current["eligible"][0],
        body={
            **swap_selection(current, version=2),
            "client_request_id": winner["client_request_id"],
            "recipe_version_id": current["eligible"][0],
        },
    )
    assert reused.status_code == 409 and reused.json()["code"] == "request_conflict"
    profile = deepcopy(current["profile"])
    profile.update(version=2, source_version="v2")
    imported = await client.post(
        f"{ROOT}/members/{current['member']}/external-profile-versions", headers=users[2]["headers"], json=profile
    )
    assert imported.status_code == 201, imported.text
    replay = await save(client, owner, current, winner)
    assert replay.status_code == 200 and replay.json()["quality_check"]["current"] is False
    assert replay.json()["quality_check"]["check_id"] == response.json()["quality_check"]["check_id"]
    assert replay.json()["applied_version"] == 2
    async with pg_manager.get_async_session_context() as session:
        row = await session.get(HealthMealPlan, current["plan"])
        assert row.version == 2 and row.snapshot["nutrition"] == snapshot.json()["nutrition"]
        assert (
            await session.scalar(
                select(func.count()).select_from(HealthMealPlanRevision).where(HealthMealPlanRevision.plan_id == row.id)
            )
            == 2
        )
        assert (await session.get(HealthMealPlan, other.json()["plan_id"])).version == 1

"""真实HTTP与PG验证家庭份量、逐人审核、授权和来源失效。"""

import asyncio
from copy import deepcopy
from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select, func, text

from test.integration.services.test_health_vision_http import ROOT, create_member, health_http  # noqa: F401
from test.integration.services.test_health_quality_http import setup_quality, action
from test.unit.services.test_health_family_meal_plan import family_spec, meal_shares
from test.unit.services.test_health_personal_targets import target_formula
from yuxi.services.health_family_meal_plan_types import FamilyMealPlanSpec
from yuxi.services.health_meal_plan_service import calculate_in_session
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_health import (
    FamilyMember,
    HealthMealPlan,
    HealthMealPlanRevision,
    HealthQualityCheck,
    HealthProfessionalReview,
    DietLog,
)

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def setup_family(client, users, *, shares=True, restriction=None):
    """合成双成员批准资料，第二成员只吃早餐60克。"""
    owner, reviewer, admin = [user["headers"] for user in users]
    current = await setup_quality(client, users)
    second = await create_member(client, owner)
    for uid, scopes in [
        (users[2]["uid"], ["profile_edit"]),
        (users[1]["uid"], ["profile_view", "professional_review"]),
    ]:
        response = await client.put(
            f"{ROOT}/members/{second}/grants", headers=owner, json={"actor_uid": uid, "scopes": scopes}
        )
        assert response.status_code == 200, response.text
    profile = deepcopy(current["profile"])
    profile["payload"].update(sex_code="synthetic_sex", weight_kg="54", activity_code="synthetic_activity")
    for member, version in [(current["member"], 2), (second, 1)]:
        body = {**deepcopy(profile), "version": version, "source_version": f"v{version}"}
        if member == second and restriction:
            body["payload"]["allergies"] = {"state": "specified", "codes": ["synthetic_allergen"]}
        response = await client.post(f"{ROOT}/members/{member}/external-profile-versions", headers=admin, json=body)
        assert response.status_code == 201, response.text
    rules = {**deepcopy(current["rules"]), "version": 2, "source_version": "v2"}
    rules["payload"]["personal_targets"] = [target_formula()]
    if shares:
        rules["payload"]["meal_target_shares"] = meal_shares()
    response = await client.post(f"{ROOT}/approved-quality-rules", headers=admin, json=rules)
    assert response.status_code == 201, response.text
    recipe = next(iter(current["check"]["sources"]["recipes"]))
    spec = family_spec(recipe, current["member"], second)
    response = await client.post(
        f"{ROOT}/members/{current['member']}/family-meal-plan-previews", headers=owner, json=spec
    )
    assert response.status_code == 201, response.text
    preview = response.json()
    save_body = {"client_request_id": str(uuid4()), "preview_id": preview["preview_id"]}
    response = await client.post(
        f"{ROOT}/members/{current['member']}/meal-plans",
        headers={**owner, "Idempotency-Key": save_body["client_request_id"]},
        json=save_body,
    )
    assert response.status_code == 201, response.text
    plan = response.json()
    check_body = {"client_request_id": str(uuid4()), "version": 1, "rule_code": rules["rule_code"]}
    response = await client.post(f"{ROOT}/meal-plans/{plan['plan_id']}/quality-checks", headers=owner, json=check_body)
    assert response.status_code == 201, response.text
    check = response.json()
    response = await client.get(f"{ROOT}/quality-checks/{check['check_id']}", headers=owner)
    assert response.status_code == 200, response.text
    return {
        "member": current["member"],
        "second": second,
        "plan": plan["plan_id"],
        "snapshot": plan,
        "spec": spec,
        "preview": preview,
        "save_body": save_body,
        "check": check,
        "case": response.json()["review"]["review_id"],
        "profile": profile,
        "rules": rules,
        "check_body": check_body,
        "recipe": recipe,
    }


async def test_family_persisted_allocations_check_and_professional_approval(health_http):  # noqa: F811
    """独立300+60=360；保存幂等，审核必须逐人通过。"""
    client, users = health_http
    owner = users[0]["headers"]
    current = await setup_family(client, users)
    first, second = current["member"], current["second"]
    snapshot = current["snapshot"]
    assert Decimal(snapshot["nutrition"]["totals"]["energy_kcal"]) == 360
    assert Decimal(snapshot["members"][first]["nutrition"]["totals"]["energy_kcal"]) == 300
    assert Decimal(snapshot["members"][second]["nutrition"]["totals"]["energy_kcal"]) == 60
    assert snapshot["members"][second]["covered_meals"] == ["breakfast"]
    check = current["check"]
    assert check["scope"] == "family_saved_plan" and check["safety_check"]["status"] == "passed"
    assert {member: source["version"] for member, source in check["sources"]["profiles"].items()} == {
        first: 2,
        second: 1,
    }
    assert check["safety_check"]["members"][second]["coverage"]["full_day_covered"] is False
    response = await client.post(
        f"{ROOT}/members/{first}/meal-plans",
        headers={**owner, "Idempotency-Key": current["save_body"]["client_request_id"]},
        json=current["save_body"],
    )
    assert response.status_code == 201 and response.json()["plan_id"] == current["plan"]
    response = await client.get(f"{ROOT}/meal-plans/{current['plan']}", headers=owner)
    assert response.status_code == 200 and len(response.json()["revisions"]) == 1
    assert response.json()["revisions"][0]["snapshot"]["members"] == snapshot["members"]
    await action(client, owner, current["case"], "submit", 1)
    await action(client, users[1]["headers"], current["case"], "approve", 2)
    response = await client.get(f"{ROOT}/meal-plans/{current['plan']}/approval-state?version=1", headers=owner)
    assert response.status_code == 200 and response.json()["available"] is True
    async with pg_manager.get_async_session_context() as session:
        plan = await session.get(HealthMealPlan, current["plan"])
        assert plan.spec == FamilyMealPlanSpec.model_validate(current["spec"]).model_dump(mode="json")
        assert plan.snapshot["members"] == snapshot["members"]
        assert (
            await session.scalar(
                select(func.count())
                .select_from(HealthMealPlanRevision)
                .where(HealthMealPlanRevision.plan_id == plan.id)
            )
            == 1
        )
        assert (await session.get(HealthQualityCheck, check["check_id"])).snapshot["safety_check"] == check[
            "safety_check"
        ]
        assert (await session.get(HealthProfessionalReview, current["case"])).status == "approved"
        assert (
            await session.scalar(
                select(func.count()).select_from(DietLog).where(DietLog.member_id.in_([first, second]))
            )
            == 0
        )


@pytest.mark.parametrize("source", ["second_profile", "second_revoked", "second_reviewer_grant"])
async def test_secondary_member_change_invalidates_old_family_approval(health_http, source):  # noqa: F811
    """第二成员的真实改源入口也永久失效旧审核，不由主成员掩盖。"""
    client, users = health_http
    owner, reviewer, admin = [user["headers"] for user in users]
    current = await setup_family(client, users)
    await action(client, owner, current["case"], "submit", 1)
    await action(client, reviewer, current["case"], "approve", 2)
    if source == "second_profile":
        body = {**deepcopy(current["profile"]), "version": 2, "source_version": "v2"}
        response = await client.post(
            f"{ROOT}/members/{current['second']}/external-profile-versions", headers=admin, json=body
        )
    elif source == "second_revoked":
        response = await client.post(
            f"{ROOT}/members/{current['second']}/external-profile-versions/1/revoke", headers=admin
        )
    else:
        response = await client.put(
            f"{ROOT}/members/{current['second']}/grants",
            headers=owner,
            json={"actor_uid": users[1]["uid"], "scopes": []},
        )
    assert response.status_code in {200, 201}, response.text
    async with pg_manager.get_async_session_context() as session:
        row = await session.get(HealthProfessionalReview, current["case"])
        assert row.status == "invalidated" and row.version == 4
    if source == "second_reviewer_grant":
        response = await client.put(
            f"{ROOT}/members/{current['second']}/grants",
            headers=owner,
            json={"actor_uid": users[1]["uid"], "scopes": ["profile_view", "professional_review"]},
        )
        assert response.status_code == 200, response.text
    response = await client.get(f"{ROOT}/meal-plans/{current['plan']}/approval-state?version=1", headers=owner)
    assert response.status_code == 200 and response.json()["available"] is False
    response = await client.get(f"{ROOT}/quality-checks/{current['check']['check_id']}", headers=owner)
    assert response.status_code == 200 and response.json()["review"]["status"] == "invalidated"
    assert response.json()["current"] is False
    replay = await client.post(
        f"{ROOT}/meal-plans/{current['plan']}/quality-checks", headers=owner, json=current["check_body"]
    )
    if source == "second_reviewer_grant":
        assert replay.status_code == 201
    else:
        assert replay.status_code == 410 and replay.json()["code"] == "source_invalidated"


@pytest.mark.parametrize("missing_shares,restriction,status", [(True, None, "unknown"), (False, "allergy", "conflict")])
async def test_secondary_unknown_or_conflict_blocks_professional_approval(
    health_http,  # noqa: F811
    missing_shares,
    restriction,
    status,  # noqa: F811
):  # noqa: F811
    """A通过不能替代B；仅部分餐次缺规则或已知过敏不能批准。"""
    client, users = health_http
    current = await setup_family(client, users, shares=not missing_shares, restriction=restriction)
    safety = current["check"]["safety_check"]
    assert safety["members"][current["member"]]["status"] == "passed"
    assert safety["status"] == status and safety["members"][current["second"]]["status"] == status
    await action(client, users[0]["headers"], current["case"], "submit", 1)
    assert (await action(client, users[1]["headers"], current["case"], "approve", 2, expected=409))[
        "code"
    ] == "quality_not_passed"


async def test_family_read_save_and_historical_revision_require_all_member_grants(health_http):  # noqa: F811
    """当前和历史都不能只凭主成员授权读取其他参与者。"""
    client, users = health_http
    owner, admin = users[0]["headers"], users[2]["headers"]
    current = await setup_family(client, users)
    response = await client.put(
        f"{ROOT}/members/{current['member']}/grants",
        headers=owner,
        json={"actor_uid": users[2]["uid"], "scopes": ["diet_edit", "profile_view", "profile_edit"]},
    )
    assert response.status_code == 200
    response = await client.post(
        f"{ROOT}/members/{current['member']}/family-meal-plan-previews", headers=admin, json=current["spec"]
    )
    assert response.status_code == 404 and response.json()["code"] == "not_found"
    response = await client.put(
        f"{ROOT}/members/{current['second']}/grants",
        headers=owner,
        json={"actor_uid": users[0]["uid"], "scopes": ["profile_edit"]},
    )
    assert response.status_code == 200
    for path in [
        f"/meal-plans/{current['plan']}",
        f"/members/{current['member']}/meal-plans",
        f"/quality-checks/{current['check']['check_id']}",
    ]:
        response = await client.get(ROOT + path, headers=owner)
        assert response.status_code == 404, response.text
    response = await client.post(
        f"{ROOT}/members/{current['member']}/meal-plans",
        headers={**owner, "Idempotency-Key": current["save_body"]["client_request_id"]},
        json=current["save_body"],
    )
    assert response.status_code == 404
    # 负向持久化状态：当前版移除B，原不可变修订仍须检查B的授权。
    async with pg_manager.get_async_session_context() as session:
        plan = await session.get(HealthMealPlan, current["plan"])
        spec = deepcopy(plan.spec)
        spec["meals"][0]["participant_ids"].remove(current["second"])
        spec["meals"][0]["dishes"][0]["member_portions"] = [
            p for p in spec["meals"][0]["dishes"][0]["member_portions"] if p["member_id"] != current["second"]
        ]
        plan.spec = spec
        plan.snapshot = await calculate_in_session(session, FamilyMealPlanSpec.model_validate(spec))
    response = await client.get(f"{ROOT}/meal-plans/{current['plan']}", headers=owner)
    assert response.status_code == 404 and response.json()["code"] == "not_found"


async def test_single_member_operations_cannot_process_family_plan(health_http):  # noqa: F811
    """未接入家庭语义的旧用例返回明确未就绪，禁止当作单成员处理。"""
    client, users = health_http
    owner = users[0]["headers"]
    current = await setup_family(client, users)
    key = str(uuid4())
    base = {"version": 1, "rule_code": current["rules"]["rule_code"], "rule_version": 2, "profile_version": 2}
    calls = [
        (
            "swap",
            {
                "client_request_id": key,
                "version": 1,
                "meal_type": "breakfast",
                "dish_index": 0,
                "replacement": {"recipe_version_id": current["recipe"], "grams": "80"},
                "reason": "合成换菜",
            },
        ),
        ("swap-candidates", {**base, "meal_type": "breakfast", "dish_index": 0}),
        ("regeneration-preview", base),
        (
            "quality-conversation",
            {"client_request_id": str(uuid4()), "version": 1, "rule_code": current["rules"]["rule_code"]},
        ),
    ]
    for path, body in calls:
        response = await client.post(
            f"{ROOT}/meal-plans/{current['plan']}/{path}",
            headers={**owner, "Idempotency-Key": body.get("client_request_id", key), "If-Match": '"1"'},
            json=body,
        )
        assert response.status_code == 409 and response.json()["code"] == "family_operation_not_ready", (
            path,
            response.text,
        )
    response = await client.post(
        f"{ROOT}/members/{current['member']}/next-day-proposals",
        headers=owner,
        json={
            "client_request_id": str(uuid4()),
            "preview_id": current["preview"]["preview_id"],
            "source_date": date.today().isoformat(),
        },
    )
    assert response.status_code == 409 and response.json()["code"] == "family_operation_not_ready"
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


async def test_opposite_family_anchors_share_sorted_member_locks(health_http):  # noqa: F811
    """相反入口并发实际API事务按同一成员顺序取得锁并完成。"""
    client, users = health_http
    current = await setup_family(client, users)
    async with pg_manager.get_async_session_context() as session:
        await session.scalar(
            select(FamilyMember).where(FamilyMember.id == min(current["member"], current["second"])).with_for_update()
        )
        blocker = await session.scalar(select(func.pg_backend_pid()))
        calls = [
            asyncio.create_task(
                client.post(
                    f"{ROOT}/members/{anchor}/family-meal-plan-previews",
                    headers=users[0]["headers"],
                    json=current["spec"],
                )
            )
            for anchor in (current["member"], current["second"])
        ]
        blocked = 0
        for _ in range(60):
            async with pg_manager.get_async_session_context() as observer:
                blocked = await observer.scalar(
                    text("""WITH RECURSIVE blocked(pid) AS (
                        SELECT pid FROM pg_stat_activity WHERE :blocker = ANY(pg_blocking_pids(pid))
                        UNION
                        SELECT a.pid FROM pg_stat_activity a JOIN blocked b ON b.pid = ANY(pg_blocking_pids(a.pid))
                    ) SELECT count(*) FROM blocked"""),
                    {"blocker": blocker},
                )
            if blocked == 2:
                break
            await asyncio.sleep(0.05)
        if blocked == 2:
            async with pg_manager.get_async_session_context() as observer:
                free_member = await observer.scalar(
                    select(FamilyMember)
                    .where(FamilyMember.id == max(current["member"], current["second"]))
                    .with_for_update(nowait=True)
                )
                assert free_member is not None, "等待首成员时不得先占有后成员"
    responses = await asyncio.wait_for(asyncio.gather(*calls), timeout=20)
    assert blocked == 2, "两个实际HTTP事务须同时等待同一成员行锁"
    assert all(r.status_code == 201 for r in responses), [r.text for r in responses]
    assert [Decimal(r.json()["nutrition"]["totals"]["energy_kcal"]) for r in responses] == [360, 360]


@pytest.mark.parametrize("removed_scope", ["diet_edit", "profile_view"])
async def test_applicant_secondary_grant_revocation_cannot_resurrect_approval(health_http, removed_scope):  # noqa: F811
    """申请人第二成员授权撤回立即持久失效，恢复授权不复活。"""
    from yuxi.services.health_vision_types import HEALTH_SCOPES

    client, users = health_http
    owner = users[0]["headers"]
    current = await setup_family(client, users)
    await action(client, owner, current["case"], "submit", 1)
    await action(client, users[1]["headers"], current["case"], "approve", 2)
    response = await client.put(
        f"{ROOT}/members/{current['second']}/grants",
        headers=owner,
        json={"actor_uid": users[0]["uid"], "scopes": sorted(HEALTH_SCOPES - {removed_scope})},
    )
    assert response.status_code == 200, response.text
    async with pg_manager.get_async_session_context() as session:
        review = await session.get(HealthProfessionalReview, current["case"])
        assert review.status == "invalidated" and review.invalidation_reason == "applicant_grant_revoked"
    response = await client.put(
        f"{ROOT}/members/{current['second']}/grants",
        headers=owner,
        json={"actor_uid": users[0]["uid"], "scopes": sorted(HEALTH_SCOPES)},
    )
    assert response.status_code == 200, response.text
    response = await client.get(f"{ROOT}/meal-plans/{current['plan']}/approval-state?version=1", headers=owner)
    assert response.status_code == 200 and response.json()["available"] is False

"""真实HTTP/PG家庭安全改版、全部来源与原子提交。"""

import asyncio
from copy import deepcopy
from datetime import UTC, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select, func

from test.integration.services.test_health_vision_http import ROOT, health_http  # noqa: F401
from test.integration.services.test_health_family_meal_plan_http import setup_family
from test.integration.services.test_health_meal_planner_http import publish_planner_recipe
from test.integration.services.test_health_quality_http import action
from yuxi.services.health_family_meal_plan_types import FamilyMealPlanSpec, FamilySafeSwapInput, FamilySafeSelection
from yuxi.services.health_nutrition_service import input_fingerprint
from yuxi.services.health_quality_checks import external_projection, projection_digest
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_health import (
    RecipeVersion,
    HealthMealPlan,
    HealthMealPlanRevision,
    HealthQualityCheck,
    HealthProfessionalReview,
    HealthProfileSnapshot,
    DietLog,
    HealthMemoryFact,
)
from yuxi.utils.datetime_utils import utc_now_naive

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def setup_safe_family(client, users, *, energies=(100, 105, 110, 115, 120), shares=True):
    """实际发布和批准合成资料，不把受测结果用作期望营养值。"""
    current = await setup_family(client, users, shares=shares)
    recipes = [await publish_planner_recipe(client, users[2]["headers"], f"合成家庭安全{e}", str(e)) for e in energies]
    rules = {**deepcopy(current["rules"]), "version": 3, "source_version": "v3"}
    rules["payload"]["personal_targets"][0]["nutrient_ranges"]["energy_kcal"].update(
        minimum_per_energy="0.8", maximum_per_energy="1.2"
    )
    classes = []
    rules["payload"]["ingredient_classifications"] = []
    async with pg_manager.get_async_session_context() as session:
        for rid in [current["recipe"], *recipes]:
            row = await session.get(RecipeVersion, rid)
            classes.append(
                {
                    "recipe_version_id": rid,
                    "recipe_hash": input_fingerprint(
                        {
                            "ingredients": row.ingredients,
                            "yield_grams": str(row.yield_grams),
                            "nutrients": row.nutrients,
                            "dataset_version": row.dataset_version,
                        }
                    ),
                    "dish_type_code": "synthetic_main",
                    "allowed_meal_types": ["breakfast", "lunch", "dinner"],
                }
            )
            food = row.ingredients[0]["food"]
            rules["payload"]["ingredient_classifications"].append(
                {
                    "food_id": food["id"],
                    "food_hash": input_fingerprint(food),
                    "complete": True,
                    "allergen_codes": [],
                    "intolerance_codes": [],
                    "food_categories": [],
                }
            )
    rules["payload"]["meal_swap"] = {
        "recipe_classifications": classes,
        "maximum_nutrient_differences": {
            "energy_kcal": "50",
            "protein_g": "0",
            "fat_g": "0",
            "carbohydrate_g": "0",
            "sodium_mg": "0",
        },
    }
    imported = await client.post(f"{ROOT}/approved-quality-rules", headers=users[2]["headers"], json=rules)
    assert imported.status_code == 201, imported.text
    current.update(rules=rules, candidates=recipes)
    return current


def selection(current, *, swap=False, **updates):
    """全部成员版本明确绑定当前家庭对象。"""
    body = {
        "version": 1,
        "rule_code": current["rules"]["rule_code"],
        "rule_version": current["rules"]["version"],
        "profile_versions": {current["member"]: 2, current["second"]: 1},
    }
    if swap:
        body.update(meal_type="breakfast", dish_index=0)
    return {**body, **updates}


async def preview(client, owner, current, *, swap=False, **updates):
    """读取实际薄路由与service结果。"""
    suffix = "family-swap-candidates" if swap else "family-regeneration-preview"
    return await client.post(
        f"{ROOT}/meal-plans/{current['plan']}/{suffix}", headers=owner, json=selection(current, swap=swap, **updates)
    )


async def change(client, owner, current, body, *, swap=False):
    """实际If-Match和幂等边界执行确认。"""
    suffix = "family-safe-swap" if swap else "family-safe-regenerate"
    return await client.post(
        f"{ROOT}/meal-plans/{current['plan']}/{suffix}",
        headers={**owner, "Idempotency-Key": body["client_request_id"], "If-Match": f'"{body["version"]}"'},
        json=body,
    )


async def assert_original(current):
    """独立PG连接证明失败未写修订、检查或饮食/记忆。"""
    async with pg_manager.get_async_session_context() as session:
        row = await session.get(HealthMealPlan, current["plan"])
        assert row.version == 1 and row.spec == FamilyMealPlanSpec.model_validate(current["spec"]).model_dump(
            mode="json"
        )
        assert (
            await session.scalar(
                select(func.count()).select_from(HealthMealPlanRevision).where(HealthMealPlanRevision.plan_id == row.id)
            )
            == 1
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(HealthQualityCheck)
                .where(HealthQualityCheck.plan_id == row.id, HealthQualityCheck.plan_version > 1)
            )
            == 0
        )
        assert (
            await session.scalar(select(DietLog).where(DietLog.member_id.in_([current["member"], current["second"]])))
            is None
        )
        assert (
            await session.scalar(
                select(HealthMemoryFact).where(HealthMemoryFact.member_id.in_([current["member"], current["second"]]))
            )
            is None
        )


async def test_family_three_candidates_and_per_member_totals_read_only(health_http):  # noqa: F811
    """只返回最小三道，A300/302.5/305、B60/63/66独立手算。"""
    client, users = health_http
    current = await setup_safe_family(client, users)
    response = await preview(client, users[0]["headers"], current, swap=True)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["status"] == "ready" and result["professional_review"] == "not_a_professional_decision"
    assert [c["recipe_version_id"] for c in result["candidates"]] == current["candidates"][:3]
    for candidate, a, b in zip(result["candidates"], [300, 302.5, 305], [60, 63, 66]):
        snapshot = candidate["plan_snapshot"]
        assert float(snapshot["members"][current["member"]]["nutrition"]["totals"]["energy_kcal"]) == a
        assert float(snapshot["members"][current["second"]]["nutrition"]["totals"]["energy_kcal"]) == b
        assert float(snapshot["nutrition"]["totals"]["energy_kcal"]) == a + b
        assert {p["member_id"]: float(p["grams"]) for p in candidate["member_portions"]} == {
            current["member"]: 50,
            current["second"]: 60,
        }
        assert candidate["safety_check"]["status"] == "passed"
    await assert_original(current)


async def test_family_swap_persists_new_check_replay_and_invalidates_old_approval(health_http):  # noqa: F811
    """共同菜品改版仍保留逐人克数与原历史，旧批准不能继承。"""
    client, users = health_http
    current = await setup_safe_family(client, users, energies=(110, 115))
    owner = users[0]["headers"]
    checked = await client.post(
        f"{ROOT}/meal-plans/{current['plan']}/quality-checks",
        headers=owner,
        json={**current["check_body"], "client_request_id": str(uuid4())},
    )
    assert checked.status_code == 201, checked.text
    read = await client.get(f"{ROOT}/quality-checks/{checked.json()['check_id']}", headers=owner)
    case = read.json()["review"]["review_id"]
    await action(client, owner, case, "submit", 1)
    await action(client, users[1]["headers"], case, "approve", 2)
    body = {
        **selection(current, swap=True),
        "recipe_version_id": current["candidates"][0],
        "client_request_id": str(uuid4()),
    }
    response = await change(client, owner, current, body, swap=True)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["version"] == 2 and result["quality_check"]["current"] is True
    assert result["quality_check"]["safety_check"]["status"] == "passed"
    replay = await change(client, owner, current, body, swap=True)
    assert (
        replay.status_code == 200 and replay.json()["quality_check"]["check_id"] == result["quality_check"]["check_id"]
    )
    conflicting = await change(
        client, owner, current, {**body, "recipe_version_id": current["candidates"][1]}, swap=True
    )
    assert conflicting.status_code == 409 and conflicting.json()["code"] == "request_conflict"
    async with pg_manager.get_async_session_context() as session:
        row = await session.get(HealthMealPlan, current["plan"])
        assert (
            row.version == 2
            and row.spec["meals"][1:]
            == FamilyMealPlanSpec.model_validate(current["spec"]).model_dump(mode="json")["meals"][1:]
        )
        revisions = list(
            (
                await session.scalars(
                    select(HealthMealPlanRevision)
                    .where(HealthMealPlanRevision.plan_id == row.id)
                    .order_by(HealthMealPlanRevision.version)
                )
            ).all()
        )
        assert len(revisions) == 2 and revisions[0].snapshot["nutrition"]["totals"]["energy_kcal"] == "360.00"
        assert float(revisions[1].snapshot["nutrition"]["totals"]["energy_kcal"]) == 371
        assert (await session.get(HealthProfessionalReview, case)).status == "invalidated"
        newcase = await session.scalar(
            select(HealthProfessionalReview).where(
                HealthProfessionalReview.check_id == result["quality_check"]["check_id"]
            )
        )
        assert newcase.status == "draft"
    changed_profile = {**deepcopy(current["profile"]), "version": 2, "source_version": "v2"}
    imported = await client.post(
        f"{ROOT}/members/{current['second']}/external-profile-versions",
        headers=users[2]["headers"],
        json=changed_profile,
    )
    assert imported.status_code == 201, imported.text
    stale = await change(client, owner, current, body, swap=True)
    assert (
        stale.status_code == 200
        and stale.json()["applied_version"] == 2
        and stale.json()["quality_check"]["current"] is False
    )


async def test_family_joint_regeneration_repairs_all_members_and_confirms_digest(health_http):  # noqa: F811
    """目标A330/B66，单菜不够；三餐共同换110配方才通过。"""
    client, users = health_http
    current = await setup_safe_family(client, users, energies=(110,))
    owner, admin = users[0]["headers"], users[2]["headers"]
    rules = {**deepcopy(current["rules"]), "version": 4, "source_version": "v4"}
    rules["payload"]["personal_targets"][0]["nutrient_ranges"]["energy_kcal"].update(
        minimum_per_energy="1.1", maximum_per_energy="1.1"
    )
    assert (await client.post(f"{ROOT}/approved-quality-rules", headers=admin, json=rules)).status_code == 201
    current["rules"] = rules
    swaps = await preview(client, owner, current, swap=True)
    assert swaps.status_code == 200 and swaps.json()["candidates"] == []
    response = await preview(client, owner, current)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["status"] == "ready", result
    assert result["search"]["limited"] is False and result["search"]["examined"] == 8
    assert float(result["plan_snapshot"]["members"][current["member"]]["nutrition"]["totals"]["energy_kcal"]) == 330
    assert float(result["plan_snapshot"]["members"][current["second"]]["nutrition"]["totals"]["energy_kcal"]) == 66
    assert float(result["plan_snapshot"]["nutrition"]["totals"]["energy_kcal"]) == 396
    assert all(
        d["recipe_version_id"] == current["candidates"][0] for m in result["plan_spec"]["meals"] for d in m["dishes"]
    )
    await assert_original(current)
    badbody = {**selection(current), "preview_hash": "f" * 64, "client_request_id": str(uuid4())}
    rejected = await change(client, owner, current, badbody)
    assert rejected.status_code == 409 and rejected.json()["code"] == "preview_changed"
    await assert_original(current)
    body = {**badbody, "preview_hash": result["preview_hash"], "client_request_id": str(uuid4())}
    saved = await change(client, owner, current, body)
    assert saved.status_code == 200 and saved.json()["version"] == 2, saved.text
    replay = await change(client, owner, current, body)
    assert (
        replay.status_code == 200
        and replay.json()["quality_check"]["check_id"] == saved.json()["quality_check"]["check_id"]
    )
    async with pg_manager.get_async_session_context() as session:
        row = await session.get(HealthMealPlan, current["plan"])
        assert row.version == 2 and row.spec == result["plan_spec"] and row.snapshot == result["plan_snapshot"]


@pytest.mark.parametrize(
    "broken",
    [
        "missing_member",
        "extra_member",
        "second_stale",
        "rule_stale",
        "second_revoked",
        "no_shares",
        "second_unknown",
        "second_allergy",
    ],
)
async def test_family_sources_and_limits_prevent_partial_changes(health_http, broken):  # noqa: F811
    """各成员及条款独立缺失不允许产生新修订。"""
    client, users = health_http
    current = await setup_safe_family(client, users, energies=(110,), shares=broken != "no_shares")
    owner, admin = users[0]["headers"], users[2]["headers"]
    updates = {}
    if broken == "missing_member":
        updates["profile_versions"] = {current["member"]: 2}
    elif broken == "extra_member":
        updates["profile_versions"] = {**selection(current)["profile_versions"], str(uuid4()): 1}
    elif broken == "rule_stale":
        updates["rule_version"] = 2
    elif broken in {"second_stale", "second_revoked", "second_unknown", "second_allergy"}:
        if broken == "second_revoked":
            response = await client.post(
                f"{ROOT}/members/{current['second']}/external-profile-versions/1/revoke", headers=admin
            )
            assert response.status_code == 200, response.text
        else:
            profile = {**deepcopy(current["profile"]), "version": 2, "source_version": "v2"}
            if broken in {"second_unknown", "second_allergy"}:
                profile["payload"]["allergies"] = (
                    {"state": "unknown", "codes": []}
                    if broken == "second_unknown"
                    else {"state": "specified", "codes": ["synthetic_allergen"]}
                )
                updates["profile_versions"] = {current["member"]: 2, current["second"]: 2}
            response = await client.post(
                f"{ROOT}/members/{current['second']}/external-profile-versions", headers=admin, json=profile
            )
            assert response.status_code == 201, response.text
            if broken == "second_allergy":
                rules = {**deepcopy(current["rules"]), "version": 4, "source_version": "v4"}
                rules["payload"]["ingredient_classifications"][1]["allergen_codes"] = ["synthetic_allergen"]
                assert (
                    await client.post(f"{ROOT}/approved-quality-rules", headers=admin, json=rules)
                ).status_code == 201
                current["rules"] = rules
    body = {
        **selection(current, swap=True, **updates),
        "client_request_id": str(uuid4()),
        "recipe_version_id": current["candidates"][0],
    }
    response = await preview(client, owner, current, swap=True, **updates)
    if broken in {"missing_member", "extra_member", "second_stale", "rule_stale"}:
        assert response.status_code == 409 and response.json()["code"] == "source_version_conflict"
    else:
        assert response.status_code == 200 and response.json()["candidates"] == [], response.text
    rejected = await change(client, owner, current, body, swap=True)
    assert rejected.status_code == 409, rejected.text
    await assert_original(current)


async def test_family_concurrent_changes_commit_one_version_and_permissions_hold(health_http):  # noqa: F811
    """独立请求竞争同一版本，所有成员权限仍在副作用前执行。"""
    client, users = health_http
    current = await setup_safe_family(client, users, energies=(110, 115))
    owner = users[0]["headers"]
    bodies = [
        {**selection(current, swap=True), "client_request_id": str(uuid4()), "recipe_version_id": rid}
        for rid in current["candidates"]
    ]
    responses = await asyncio.gather(*(change(client, owner, current, body, swap=True) for body in bodies))
    assert sorted(r.status_code for r in responses) == [200, 410], [r.text for r in responses]
    async with pg_manager.get_async_session_context() as session:
        assert (await session.get(HealthMealPlan, current["plan"])).version == 2
        assert (
            await session.scalar(
                select(func.count())
                .select_from(HealthMealPlanRevision)
                .where(HealthMealPlanRevision.plan_id == current["plan"])
            )
            == 2
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(HealthQualityCheck)
                .where(HealthQualityCheck.plan_id == current["plan"], HealthQualityCheck.plan_version == 2)
            )
            == 1
        )
    granted = await client.put(
        f"{ROOT}/members/{current['second']}/grants",
        headers=owner,
        json={"actor_uid": users[0]["uid"], "scopes": ["profile_edit"]},
    )
    assert granted.status_code == 200
    denied = await change(client, owner, current, bodies[0], swap=True)
    assert denied.status_code == 404


@pytest.mark.parametrize("failure", ["integrity", "expired"])
async def test_last_check_failure_rolls_back_real_pg_changes(health_http, monkeypatch, failure):  # noqa: F811
    """预览后完整性失效或一致的过期来源，末次真实检查失败，所有改版事实回滚。"""
    from yuxi.services import health_family_safe_plan_service as service

    client, users = health_http
    current = await setup_safe_family(client, users, energies=(110,))
    owner = users[0]["headers"]
    fresh = await client.post(
        f"{ROOT}/meal-plans/{current['plan']}/quality-checks",
        headers=owner,
        json={**current["check_body"], "client_request_id": str(uuid4())},
    )
    assert fresh.status_code == 201, fresh.text
    read = await client.get(f"{ROOT}/quality-checks/{fresh.json()['check_id']}", headers=owner)
    case_id = read.json()["review"]["review_id"]
    await action(client, owner, case_id, "submit", 1)
    await action(client, users[1]["headers"], case_id, "approve", 2)
    async with pg_manager.get_async_session_context() as session:
        before_case = await session.get(HealthProfessionalReview, case_id)
        assert before_case.status == "approved"
        before_version = before_case.version
    original = service.family_safe_preview_in_session

    async def expires_after_preview(session, uid, plan_id, data, *, swap):
        """仅制造真实来源失效，独立确认拒绝分支，不替换计算/检查/保存。"""
        result = await original(session, uid, plan_id, data, swap=swap)
        assert result[1]["candidates"]
        projection = await session.scalar(
            select(HealthProfileSnapshot).where(
                HealthProfileSnapshot.member_id == current["second"], HealthProfileSnapshot.version == 1
            )
        )
        projection.valid_until = utc_now_naive() - timedelta(seconds=1)
        if failure == "expired":
            proof = deepcopy(projection.attestation)
            proof["valid_until"] = projection.valid_until.replace(tzinfo=UTC).isoformat()
            projection.attestation = proof
            projection.content_hash = projection_digest(
                "profile", current["second"], projection.version, projection.payload, proof
            )
        assert external_projection(projection, "profile", current["second"])["reason"] == (
            "expired" if failure == "expired" else "integrity_mismatch"
        )
        await session.flush()
        return result

    monkeypatch.setattr(service, "family_safe_preview_in_session", expires_after_preview)
    data = FamilySafeSwapInput.model_validate(
        {
            **selection(current, swap=True),
            "client_request_id": str(uuid4()),
            "recipe_version_id": current["candidates"][0],
        }
    )
    with pytest.raises(HealthVisionError) as exc:
        await service.change_family_safe_plan(users[0]["uid"], current["plan"], data, swap=True)
    assert exc.value.code == "quality_not_passed"
    await assert_original(current)
    async with pg_manager.get_async_session_context() as session:
        case = await session.get(HealthProfessionalReview, case_id)
        assert case.status == "approved" and case.version == before_version
        projection = await session.scalar(
            select(HealthProfileSnapshot).where(
                HealthProfileSnapshot.member_id == current["second"], HealthProfileSnapshot.version == 1
            )
        )
        assert projection.valid_until > utc_now_naive()
        assert external_projection(projection, "profile", current["second"])["status"] == "ready"


async def test_budget_limit_in_real_pg_preview_is_not_exhaustive_no_solution(health_http, monkeypatch):  # noqa: F811
    """缩小真实搜索运行预算，明确停止且不保存。"""
    from yuxi.services import health_family_safe_plan_service as service

    client, users = health_http
    current = await setup_safe_family(client, users, energies=(110,))
    original = service.search_plan_combinations
    monkeypatch.setattr(
        service, "search_plan_combinations", lambda options, evaluate: original(options, evaluate, max_states=1)
    )
    data = FamilySafeSelection.model_validate(selection(current))
    result = await service.preview_family_regeneration(users[0]["uid"], current["plan"], data)
    assert result["status"] == "not_ready" and result["reason"] == "search_limit_reached"
    assert result["search"] == {"examined": 1, "limited": True, "max_states": 1}
    await assert_original(current)

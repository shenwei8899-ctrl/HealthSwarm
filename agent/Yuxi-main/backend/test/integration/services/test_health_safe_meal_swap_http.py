"""实际HTTP与PG证明批准候选、安全单菜替换和失效边界。"""

import asyncio
from copy import deepcopy
from uuid import uuid4

import pytest
from sqlalchemy import select, func

from test.integration.services.test_health_vision_http import ROOT, health_http  # noqa: F401
from test.integration.services.test_health_quality_http import setup_quality, action
from test.integration.services.test_health_meal_planner_http import publish_planner_recipe
from yuxi.services.health_nutrition_service import input_fingerprint
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_health import (
    RecipeVersion,
    HealthMealPlan,
    HealthMealPlanRevision,
    HealthQualityCheck,
    HealthProfessionalReview,
    HealthMealPlanAdoption,
    DietLog,
    HealthMemoryFact,
)

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def setup_swap(client, users, *, count=4):
    """专业合成条款经实际导入，数值对照不从受测候选生成。"""
    current = await setup_quality(client, users)
    original = current["check"]["sources"]["recipes"]
    old = next(iter(original))
    approved = [old]
    for energy in (110, 120, 130, 140)[:count]:
        approved.append(await publish_planner_recipe(client, users[2]["headers"], f"合成安全候选{energy}", str(energy)))
    excluded = []
    for name, energy in [("异类型", 110), ("仅早餐", 110), ("差异过大", 200), ("缺食品分类", 110), ("旧配方摘要", 110)]:
        excluded.append(await publish_planner_recipe(client, users[2]["headers"], "合成排除" + name, str(energy)))
    body = deepcopy(current["rules"])
    body.update(version=2, source_version="v2")
    payload = body["payload"]
    payload["ingredient_classifications"] = []
    classifications = []
    async with pg_manager.get_async_session_context() as session:
        for rid in approved + excluded:
            row = await session.get(RecipeVersion, rid)
            classifications.append(
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
            if rid != excluded[3]:
                food = row.ingredients[0]["food"]
                payload["ingredient_classifications"].append(
                    {
                        "food_id": food["id"],
                        "food_hash": input_fingerprint(food),
                        "complete": True,
                        "allergen_codes": [],
                        "intolerance_codes": [],
                        "food_categories": [],
                    }
                )
    classifications[len(approved)]["dish_type_code"] = "synthetic_other"
    classifications[len(approved) + 1]["allowed_meal_types"] = ["breakfast"]
    classifications[-1]["recipe_hash"] = "0" * 64
    payload["meal_swap"] = {
        "recipe_classifications": classifications,
        "maximum_nutrient_differences": {
            "energy_kcal": "50",
            "protein_g": "0",
            "fat_g": "0",
            "carbohydrate_g": "0",
            "sodium_mg": "0",
        },
    }
    imported = await client.post(f"{ROOT}/approved-quality-rules", headers=users[2]["headers"], json=body)
    assert imported.status_code == 201, imported.text
    current.update(rules=body, old=old, eligible=approved[1:], excluded=excluded)
    return current


def selection(current, version=1, profile_version=1, rule_version=2):
    """明确选择原餐单和当前依赖版本。"""
    return {
        "version": version,
        "rule_code": current["rules"]["rule_code"],
        "rule_version": rule_version,
        "profile_version": profile_version,
        "meal_type": "lunch",
        "dish_index": 0,
    }


async def candidates(client, owner, current, **kwargs):
    """候选是实际HTTP结果，不使用服务mock。"""
    response = await client.post(
        f"{ROOT}/meal-plans/{current['plan']}/swap-candidates", headers=owner, json=selection(current, **kwargs)
    )
    assert response.status_code == 200, response.text
    return response.json()


async def swap(client, owner, current, recipe, *, body=None):
    """换菜使用真实幂等及版本HTTP边界。"""
    body = body or {**selection(current), "recipe_version_id": recipe, "client_request_id": str(uuid4())}
    return await client.post(
        f"{ROOT}/meal-plans/{current['plan']}/safe-swap",
        headers={**owner, "Idempotency-Key": body["client_request_id"], "If-Match": f'"{body["version"]}"'},
        json=body,
    )


async def test_three_candidates_are_ranked_real_safe_and_read_only(health_http):  # noqa: F811
    """只取三道，差异由100克独立手算；排除不合格真实菜谱。"""
    client, users = health_http
    current = await setup_swap(client, users)
    owner = users[0]["headers"]
    result = await candidates(client, owner, current)
    assert result["status"] == "ready" and result["professional_review"] == "not_a_professional_decision"
    assert [c["recipe_version_id"] for c in result["candidates"]] == current["eligible"][:3]
    for c, delta, total in zip(result["candidates"], [10, 20, 30], [310, 320, 330]):
        assert float(c["nutrition_difference"]["energy_kcal"]) == delta
        assert float(c["plan_snapshot"]["nutrition"]["totals"]["energy_kcal"]) == total
        assert c["planned_grams"] == "100" and c["safety_check"]["status"] == "passed"
        assert set(c["candidate_sources"]["recipes"]) == {current["old"], c["recipe_version_id"]}
    for other in users[1:]:
        response = await client.post(
            f"{ROOT}/meal-plans/{current['plan']}/swap-candidates", headers=other["headers"], json=selection(current)
        )
        assert response.status_code == 404
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
        assert await session.scalar(select(DietLog).where(DietLog.member_id == current["member"])) is None
        assert (
            await session.scalar(select(HealthMemoryFact).where(HealthMemoryFact.member_id == current["member"]))
            is None
        )


async def test_safe_swap_rechecks_persists_and_invalidates_previous_approval_adoption(health_http):  # noqa: F811
    """单菜改版、新检查留痕、旧批准/采用失效且原历史不变。"""
    client, users = health_http
    current = await setup_swap(client, users, count=2)
    owner = users[0]["headers"]
    newcheck = await client.post(
        f"{ROOT}/meal-plans/{current['plan']}/quality-checks",
        headers=owner,
        json={"client_request_id": str(uuid4()), "version": 1, "rule_code": current["rules"]["rule_code"]},
    )
    read = await client.get(f"{ROOT}/quality-checks/{newcheck.json()['check_id']}", headers=owner)
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
    async with pg_manager.get_async_session_context() as session:
        old = deepcopy((await session.get(HealthMealPlan, current["plan"])).spec)
    body = {**selection(current), "client_request_id": str(uuid4()), "recipe_version_id": current["eligible"][0]}
    response = await swap(client, owner, current, current["eligible"][0], body=body)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["version"] == 2 and result["quality_check"]["current"] is True
    assert (
        result["quality_check"]["safety_check"]["status"] == "passed"
        and result["quality_check"]["professional_review"] == "not_a_professional_decision"
    )
    assert result["nutrition"]["totals"]["energy_kcal"] == "310.00"
    replay = await swap(client, owner, current, current["eligible"][0], body=body)
    assert (
        replay.status_code == 200 and replay.json()["quality_check"]["check_id"] == result["quality_check"]["check_id"]
    )
    changed = await swap(
        client, owner, current, current["eligible"][1], body={**body, "recipe_version_id": current["eligible"][1]}
    )
    assert changed.status_code == 409 and changed.json()["code"] == "request_conflict"
    async with pg_manager.get_async_session_context() as session:
        row = await session.get(HealthMealPlan, current["plan"])
        expected = deepcopy(old)
        expected["meals"][1]["dishes"][0] = {
            "recipe_version_id": current["eligible"][0],
            "grams": "100",
            "portion_reference_id": None,
            "portion_count": None,
        }
        assert row.spec == expected
        revisions = list(
            (
                await session.scalars(
                    select(HealthMealPlanRevision)
                    .where(HealthMealPlanRevision.plan_id == row.id)
                    .order_by(HealthMealPlanRevision.version)
                )
            ).all()
        )
        assert (
            len(revisions) == 2
            and revisions[0].spec == old
            and revisions[0].snapshot["nutrition"]["totals"]["energy_kcal"] == "300.00"
        )
        assert (await session.get(HealthProfessionalReview, case)).status == "invalidated"
        assert (await session.get(HealthMealPlanAdoption, aid)).status == "invalidated"
        assert (await session.get(HealthMealPlanAdoption, aid)).snapshot == adopted.json()["snapshot"]
        check = await session.get(HealthQualityCheck, result["quality_check"]["check_id"])
        professional = await session.scalar(
            select(HealthProfessionalReview).where(HealthProfessionalReview.check_id == check.id)
        )
        assert (
            check.plan_version == 2
            and check.snapshot["sources"]["rules"]["version"] == 2
            and professional.status == "draft"
        )
        assert await session.scalar(select(DietLog).where(DietLog.member_id == current["member"])) is None
    assert (await client.get(f"{ROOT}/meal-plans/{current['plan']}/approval-state?version=2", headers=owner)).json()[
        "available"
    ] is False


async def test_fewer_candidates_whole_day_rule_and_forbidden_choice(health_http):  # noqa: F811
    """不足三道不补数，差异合格仍须整天通过；列表外无法提交。"""
    client, users = health_http
    current = await setup_swap(client, users, count=2)
    owner = users[0]["headers"]
    assert len((await candidates(client, owner, current))["candidates"]) == 2
    rejected = await swap(client, owner, current, current["excluded"][0])
    assert rejected.status_code == 409 and rejected.json()["code"] == "safe_candidate_required"
    rules = deepcopy(current["rules"])
    rules.update(version=3, source_version="v3")
    rules["payload"]["daily_bounds"]["energy_kcal"]["maximum"] = "315"
    response = await client.post(f"{ROOT}/approved-quality-rules", headers=users[2]["headers"], json=rules)
    assert response.status_code == 201, response.text
    assert [
        c["recipe_version_id"] for c in (await candidates(client, owner, current, rule_version=3))["candidates"]
    ] == current["eligible"][:1]
    stale = await swap(client, owner, current, current["eligible"][0])
    assert stale.status_code == 409 and stale.json()["code"] == "source_version_conflict"
    async with pg_manager.get_async_session_context() as session:
        assert (await session.get(HealthMealPlan, current["plan"])).version == 1


@pytest.mark.parametrize("broken", ["structure", "copied_food"])
async def test_unselected_bad_recipe_does_not_poison_valid_candidates(health_http, broken):  # noqa: F811
    """未选中坏配方逐个拒绝，共享食品旧副本不能污染有效候选。"""
    client, users = health_http
    current = await setup_swap(client, users, count=1)
    owner = users[0]["headers"]
    async with pg_manager.get_async_session_context() as session:
        bad = await session.get(RecipeVersion, current["excluded"][0])
        if broken == "structure":
            bad.ingredients = [{"food": {}}]
        else:
            food = deepcopy((await session.get(RecipeVersion, current["old"])).ingredients[0]["food"])
            food["name"] = "合成错误复制的食品名"
            bad.ingredients = [{"food": food, "grams": "200", "role": "food"}]
    result = await candidates(client, owner, current)
    assert [c["recipe_version_id"] for c in result["candidates"]] == current["eligible"]
    response = await swap(client, owner, current, current["eligible"][0])
    assert response.status_code == 200, response.text
    assert response.json()["quality_check"]["safety_check"]["status"] == "passed"


async def test_reference_portions_other_dishes_and_stale_replay_preserved(health_http):  # noqa: F811
    """目标按原克数换菜，其他参考输入原样保留；改源后重放不复活检查。"""
    client, users = health_http
    current = await setup_swap(client, users, count=1)
    owner, admin = users[0]["headers"], users[2]["headers"]
    response = await client.post(
        f"{ROOT}/portion-references",
        headers=admin,
        json={
            "recipe_version_id": current["old"],
            "unit_label": "合成100克碗",
            "grams_per_unit": "100",
            "source": "synthetic-portions",
            "license": "synthetic-test",
            "edition": "v1",
            "dataset_version": "v1",
            "applicable_scope": "仅隔离合成菜谱及容器",
        },
    )
    assert response.status_code == 201, response.text
    pid = response.json()["id"]
    for version, kind, count in [(1, "dinner", "1.5"), (2, "lunch", "1")]:
        key = str(uuid4())
        response = await client.post(
            f"{ROOT}/meal-plans/{current['plan']}/swap",
            headers={**owner, "Idempotency-Key": key, "If-Match": f'"{version}"'},
            json={
                "version": version,
                "client_request_id": key,
                "meal_type": kind,
                "dish_index": 0,
                "replacement": {
                    "recipe_version_id": current["old"],
                    "portion_reference_id": pid,
                    "portion_count": count,
                },
                "reason": "合成参考份量",
            },
        )
        assert response.status_code == 200, response.text
    async with pg_manager.get_async_session_context() as session:
        old_spec = deepcopy((await session.get(HealthMealPlan, current["plan"])).spec)
    listed = await candidates(client, owner, current, version=3)
    assert float(listed["candidates"][0]["planned_grams"]) == 100
    body = {
        **selection(current, version=3),
        "client_request_id": str(uuid4()),
        "recipe_version_id": current["eligible"][0],
    }
    response = await swap(client, owner, current, current["eligible"][0], body=body)
    assert response.status_code == 200, response.text
    result = response.json()
    # 早餐50 + 午餐替换110 + 晚餐100g×1.5=150，独立期望310 kcal。
    assert result["version"] == 4 and result["nutrition"]["totals"]["energy_kcal"] == "310.00"
    async with pg_manager.get_async_session_context() as session:
        new_spec = (await session.get(HealthMealPlan, current["plan"])).spec
        assert new_spec["meals"][0] == old_spec["meals"][0] and new_spec["meals"][2] == old_spec["meals"][2]
        assert new_spec["meals"][2]["dishes"][0]["portion_reference_id"] == pid
    profile = deepcopy(current["profile"])
    profile.update(version=2, source_version="v2")
    assert (
        await client.post(f"{ROOT}/members/{current['member']}/external-profile-versions", headers=admin, json=profile)
    ).status_code == 201
    replay = await swap(client, owner, current, current["eligible"][0], body=body)
    assert replay.status_code == 200 and replay.json()["applied_version"] == 4
    assert replay.json()["quality_check"]["current"] is False
    assert replay.json()["quality_check"]["check_id"] == result["quality_check"]["check_id"]


@pytest.mark.parametrize(
    "missing", ["swap_rule", "unknown_profile", "allergen", "portion", "old_class", "large_portion"]
)
async def test_missing_or_conflicting_dependencies_cannot_safe_swap(health_http, missing):  # noqa: F811
    """缺条款/完整字段/份量与过敏不放行；原版本保留。"""
    client, users = health_http
    current = await setup_swap(client, users, count=1)
    owner, admin = users[0]["headers"], users[2]["headers"]
    kwargs = {}
    if missing in {"swap_rule", "old_class"}:
        rules = deepcopy(current["rules"])
        rules.update(version=3, source_version="v3")
        if missing == "swap_rule":
            del rules["payload"]["meal_swap"]
        else:
            rules["payload"]["meal_swap"]["recipe_classifications"] = [
                c
                for c in rules["payload"]["meal_swap"]["recipe_classifications"]
                if c["recipe_version_id"] != current["old"]
            ]
        assert (await client.post(f"{ROOT}/approved-quality-rules", headers=admin, json=rules)).status_code == 201
        kwargs["rule_version"] = 3
    elif missing in {"unknown_profile", "allergen"}:
        profile = deepcopy(current["profile"])
        profile.update(version=2, source_version="v2")
        profile["payload"]["allergies"] = (
            {"state": "unknown", "codes": []}
            if missing == "unknown_profile"
            else {"state": "specified", "codes": ["synthetic_allergen"]}
        )
        assert (
            await client.post(
                f"{ROOT}/members/{current['member']}/external-profile-versions", headers=admin, json=profile
            )
        ).status_code == 201
        kwargs["profile_version"] = 2
        if missing == "allergen":
            rules = deepcopy(current["rules"])
            rules.update(version=3, source_version="v3")
            async with pg_manager.get_async_session_context() as session:
                fid = (await session.get(RecipeVersion, current["eligible"][0])).ingredients[0]["food"]["id"]
            next(c for c in rules["payload"]["ingredient_classifications"] if c["food_id"] == fid)["allergen_codes"] = [
                "synthetic_allergen"
            ]
            assert (await client.post(f"{ROOT}/approved-quality-rules", headers=admin, json=rules)).status_code == 201
            kwargs["rule_version"] = 3
    else:
        replacement = {"recipe_version_id": current["old"]}
        if missing == "large_portion":
            published = await client.post(
                f"{ROOT}/portion-references",
                headers=admin,
                json={
                    "recipe_version_id": current["old"],
                    "unit_label": "合成超范围参考",
                    "grams_per_unit": "0.000001",
                    "source": "synthetic-portions",
                    "license": "synthetic-test",
                    "edition": "v1",
                    "dataset_version": "v1",
                    "applicable_scope": "仅隔离工程边界",
                },
            )
            assert published.status_code == 201, published.text
            replacement.update(portion_reference_id=published.json()["id"], portion_count="0.1")
        key = str(uuid4())
        response = await client.post(
            f"{ROOT}/meal-plans/{current['plan']}/swap",
            headers={**owner, "Idempotency-Key": key, "If-Match": '"1"'},
            json={
                "client_request_id": key,
                "version": 1,
                "meal_type": "lunch",
                "dish_index": 0,
                "replacement": replacement,
                "reason": "合成未知份量",
            },
        )
        assert response.status_code == 200, response.text
        kwargs["version"] = 2
    result = await candidates(client, owner, current, **kwargs)
    assert result["candidates"] == []
    if missing == "large_portion":
        assert result["reason"] == "portion_outside_supported_swap_range"
    elif missing == "old_class":
        assert result["reason"] == "current_recipe_classification_not_approved"
    body = {
        **selection(current, **kwargs),
        "recipe_version_id": current["eligible"][0],
        "client_request_id": str(uuid4()),
    }
    response = await swap(client, owner, current, current["eligible"][0], body=body)
    assert response.status_code == 409 and response.json()["code"] == "safe_candidate_required"
    async with pg_manager.get_async_session_context() as session:
        assert (await session.get(HealthMealPlan, current["plan"])).version == kwargs.get("version", 1)


async def test_same_version_concurrent_safe_swaps_only_commit_once(health_http):  # noqa: F811
    """真实HTTP竞争在成员锁下只产生一版及一个检查。"""
    client, users = health_http
    current = await setup_swap(client, users, count=2)
    owner = users[0]["headers"]
    responses = await asyncio.gather(*(swap(client, owner, current, rid) for rid in current["eligible"]))
    assert sorted(r.status_code for r in responses) == [200, 410], [r.text for r in responses]
    async with pg_manager.get_async_session_context() as session:
        row = await session.get(HealthMealPlan, current["plan"])
        assert row.version == 2
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

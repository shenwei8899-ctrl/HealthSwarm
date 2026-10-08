"""初始配餐实际HTTP、全员PG锁与原子确认验证。"""

import asyncio
from copy import deepcopy
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from test.integration.services.test_health_vision_http import ROOT, create_member, health_http  # noqa: F401
from test.integration.services.test_health_meal_planner_http import publish_planner_recipe
from test.integration.services.test_health_quality_http import proof, action
from test.unit.services.test_health_quality import profile_payload, rules_payload
from test.unit.services.test_health_family_meal_plan import meal_shares
from yuxi.services.health_initial_meal_plan_types import InitialPlanSelection
from yuxi.services.health_nutrition_service import input_fingerprint
from yuxi.services.health_quality_checks import projection_digest
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_health import (
    FamilyMember,
    RecipeVersion,
    HealthProfileSnapshot,
    HealthRuleSnapshot,
    HealthInitialPlanPreview,
    HealthMealPlan,
    HealthMealPlanRevision,
    HealthQualityCheck,
    HealthProfessionalReview,
    DietLog,
)

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def setup_initial(client, users):
    """全新成员及批准目录，不建立供生成器读取的旧餐单。"""
    owner, reviewer, admin = [u["headers"] for u in users]
    members = [await create_member(client, owner), await create_member(client, owner)]
    recipe = await publish_planner_recipe(client, admin, "合成初始配餐110", "110")
    profile = {**proof(), "status": "confirmed", "payload": profile_payload()}
    for mid in members:
        for uid, scopes in [
            (users[2]["uid"], ["profile_edit"]),
            (users[1]["uid"], ["profile_view", "professional_review"]),
        ]:
            response = await client.put(
                f"{ROOT}/members/{mid}/grants", headers=owner, json={"actor_uid": uid, "scopes": scopes}
            )
            assert response.status_code == 200, response.text
        response = await client.post(f"{ROOT}/members/{mid}/external-profile-versions", headers=admin, json=profile)
        assert response.status_code == 201, response.text
    async with pg_manager.get_async_session_context() as session:
        row = await session.get(RecipeVersion, recipe)
        recipe_hash = input_fingerprint(
            {
                "ingredients": row.ingredients,
                "yield_grams": str(row.yield_grams),
                "nutrients": row.nutrients,
                "dataset_version": row.dataset_version,
            }
        )
        food = deepcopy(row.ingredients[0]["food"])
        assert (
            await session.scalar(
                select(func.count()).select_from(HealthMealPlan).where(HealthMealPlan.actor_uid == users[0]["uid"])
            )
            == 0
        )
    rules = rules_payload()
    rules["ingredient_classifications"] = [
        {
            "food_id": food["id"],
            "food_hash": input_fingerprint(food),
            "complete": True,
            "allergen_codes": [],
            "intolerance_codes": [],
            "food_categories": [],
        }
    ]
    rules["daily_bounds"]["energy_kcal"] = {"minimum": "330", "maximum": "330"}
    rules["meal_target_shares"] = meal_shares()
    rules["meal_generation"] = {
        "recipe_classifications": [
            {
                "recipe_version_id": recipe,
                "recipe_hash": recipe_hash,
                "dish_type_code": "synthetic",
                "allowed_meal_types": ["breakfast", "lunch", "dinner"],
            }
        ],
        "profile_menus": [
            {
                "population_code": "synthetic_adult",
                "condition_codes": [],
                "meals": [
                    {
                        "meal_type": m,
                        "dishes": [
                            {
                                "dish_type_code": "synthetic",
                                "grams_options": ["60", "100"] if m == "breakfast" else ["100"],
                            }
                        ],
                    }
                    for m in ("breakfast", "lunch", "dinner")
                ],
            }
        ],
    }
    rules_body = {**proof(), "rule_code": "synthetic-initial-" + uuid4().hex, "status": "approved", "payload": rules}
    response = await client.post(f"{ROOT}/approved-quality-rules", headers=admin, json=rules_body)
    assert response.status_code == 201, response.text
    response = await client.post(
        f"{ROOT}/professional-reviewers",
        headers=admin,
        json={**proof(), "status": "qualified", "reviewer_uid": users[1]["uid"]},
    )
    assert response.status_code == 201, response.text
    return {"member": members[0], "second": members[1], "recipe": recipe, "profile": profile, "rules": rules_body}


def selection(current, *, family=False):
    """只选日期、当前来源及餐次参与者。"""
    first, second = current["member"], current["second"]
    return {
        "kind": "family" if family else "single",
        "plan_date": "2026-10-08",
        "rule_code": current["rules"]["rule_code"],
        "rule_version": 1,
        "profile_versions": {first: 1, **({second: 1} if family else {})},
        "meals": [
            {"meal_type": m, "participant_ids": [first, second] if family and m == "breakfast" else [first]}
            for m in ("breakfast", "lunch", "dinner")
        ],
    }


async def preview(client, owner, current, *, family=False):
    """实际薄路由消费批准目录。"""
    response = await client.post(
        f"{ROOT}/members/{current['member']}/initial-meal-plan-previews",
        headers=owner,
        json=selection(current, family=family),
    )
    assert response.status_code == 200, response.text
    return response.json()


async def save(client, owner, current, preview_id, *, request_id=None):
    """明确用户动作确认服务器回执。"""
    key = request_id or str(uuid4())
    return await client.post(
        f"{ROOT}/members/{current['member']}/initial-meal-plans",
        headers={**owner, "Idempotency-Key": key},
        json={"client_request_id": key, "preview_id": preview_id},
    )


async def assert_no_plan(uid):
    """新会话重读PG，失败不留下任何初版或专业草稿。"""
    async with pg_manager.get_async_session_context() as session:
        for model in (HealthMealPlan, HealthMealPlanRevision, HealthQualityCheck, HealthProfessionalReview):
            assert await session.scalar(select(func.count()).select_from(model).where(model.actor_uid == uid)) == 0
        assert (
            await session.scalar(
                select(DietLog)
                .join(FamilyMember, FamilyMember.id == DietLog.member_id)
                .where(FamilyMember.owner_uid == uid)
            )
            is None
        )


@pytest.mark.parametrize("family", [False, True])
async def test_initial_generation_confirm_review_and_idempotent_concurrency(health_http, family):  # noqa: F811
    """A330和B66独立手算；预览零计划，重复确认一个初版，专业批准仍独立。"""
    client, users = health_http
    current = await setup_initial(client, users)
    owner = users[0]["headers"]
    generated = await preview(client, owner, current, family=family)
    assert generated["status"] == "ready" and generated["safety_check"]["status"] == "passed"
    assert generated["plan_snapshot"]["nutrition"]["totals"]["energy_kcal"] == ("396.00" if family else "330.00")
    if family:
        assert (
            generated["plan_snapshot"]["members"][current["member"]]["nutrition"]["totals"]["energy_kcal"] == "330.00"
        )
        assert generated["plan_snapshot"]["members"][current["second"]]["nutrition"]["totals"]["energy_kcal"] == "66.00"
    await assert_no_plan(users[0]["uid"])
    read = await client.get(f"{ROOT}/initial-meal-plan-previews/{generated['preview_id']}", headers=owner)
    assert read.status_code == 200 and read.json() == generated
    key = str(uuid4())
    responses = await asyncio.gather(
        *(save(client, owner, current, generated["preview_id"], request_id=key) for _ in range(2))
    )
    assert all(r.status_code == 201 for r in responses), [r.text for r in responses]
    plan = responses[0].json()
    assert responses[1].json() == plan and plan["version"] == 1 and plan["quality_check"]["current"] is True
    assert plan["quality_check"]["safety_check"]["status"] == "passed"
    async with pg_manager.get_async_session_context() as session:
        row = await session.get(HealthMealPlan, plan["plan_id"])
        from yuxi.services.health_meal_plan_service import initial_generation_snapshot

        assert row.spec == generated["plan_spec"]
        assert (
            initial_generation_snapshot(row.snapshot, row.snapshot["generation_origin"], current=True)
            == generated["plan_snapshot"]
        )
        assert (
            await session.scalar(
                select(func.count()).select_from(HealthMealPlanRevision).where(HealthMealPlanRevision.plan_id == row.id)
            )
            == 1
        )
        check = await session.get(HealthQualityCheck, plan["quality_check"]["check_id"])
        case = await session.scalar(
            select(HealthProfessionalReview).where(HealthProfessionalReview.check_id == check.id)
        )
        assert check.plan_version == 1 and case.status == "draft"
        case_id = case.id
    await action(client, owner, case_id, "submit", 1)
    await action(client, users[1]["headers"], case_id, "approve", 2)
    approved = await client.get(f"{ROOT}/meal-plans/{plan['plan_id']}/approval-state?version=1", headers=owner)
    assert approved.status_code == 200 and approved.json()["available"] is True
    adopted = await client.post(
        f"{ROOT}/meal-plans/{plan['plan_id']}/adopt",
        headers=owner,
        json={
            "client_request_id": str(uuid4()),
            "version": 1,
            "review_id": case_id,
            "profile_versions": selection(current, family=family)["profile_versions"],
        },
    )
    assert adopted.status_code == 201 and adopted.json()["current"] is True, adopted.text
    adopted_snapshot = adopted.json()["snapshot"]
    assert adopted_snapshot["profile_status"] == adopted_snapshot["rules_status"] == "ready"
    assert adopted_snapshot["full_health_profile_available"] is False and "generation_origin" not in adopted_snapshot
    today = await client.get(f"{ROOT}/members/{current['member']}/adopted-plan?plan_date=2026-10-08", headers=owner)
    assert today.status_code == 200 and today.json()["status"] == "ready", today.text
    assert today.json()["plan"]["snapshot"] == adopted_snapshot
    if not family:
        assert today.json()["member_plan"]["profile_status"] == "ready"
    read = await client.get(f"{ROOT}/meal-plans/{plan['plan_id']}", headers=owner)
    assert read.status_code == 200 and read.json()["profile_status"] == "requires_current_validation"
    assert read.json()["revisions"][0]["snapshot"]["profile_status"] == "requires_current_validation"
    assert "generation_origin" not in read.json()["revisions"][0]["snapshot"]
    assert (
        plan["profile_status"] == "ready"
        and plan["rules_status"] == "ready"
        and plan["full_health_profile_available"] is False
    )
    async with pg_manager.get_async_session_context() as session:
        assert (
            await session.scalar(select(DietLog).where(DietLog.member_id.in_([current["member"], current["second"]])))
            is None
        )


async def test_private_identity_input_and_old_endpoint_cannot_save_initial_receipt(health_http):  # noqa: F811
    """跨账号、错成员及自由营养无效；通用保存不能绕过初始检查。"""
    client, users = health_http
    current = await setup_initial(client, users)
    owner = users[0]["headers"]
    generated = await preview(client, owner, current)
    for headers in (users[1]["headers"], users[2]["headers"]):
        assert (
            await client.get(f"{ROOT}/initial-meal-plan-previews/{generated['preview_id']}", headers=headers)
        ).status_code == 404
    assert (
        await save(client, owner, {**current, "member": current["second"]}, generated["preview_id"])
    ).status_code == 404
    key = str(uuid4())
    old = await client.post(
        f"{ROOT}/members/{current['member']}/meal-plans",
        headers={**owner, "Idempotency-Key": key},
        json={"client_request_id": key, "preview_id": generated["preview_id"]},
    )
    assert old.status_code == 404, old.text
    invalid = await client.post(
        f"{ROOT}/members/{current['member']}/initial-meal-plan-previews",
        headers=owner,
        json={**selection(current), "nutrition": {"energy_kcal": "1"}},
    )
    assert invalid.status_code == 422, invalid.text
    await assert_no_plan(users[0]["uid"])


@pytest.mark.parametrize("change", ["profile", "rules", "payload", "recipe"])
async def test_stale_or_forged_preview_cannot_be_read_or_confirmed(health_http, change):  # noqa: F811
    """改第二档案、规则或持久化结果后，新PG连接无初版和检查。"""
    client, users = health_http
    current = await setup_initial(client, users)
    owner = users[0]["headers"]
    generated = await preview(client, owner, current, family=True)
    if change == "profile":
        body = {**deepcopy(current["profile"]), "version": 2, "source_version": "v2"}
        response = await client.post(
            f"{ROOT}/members/{current['second']}/external-profile-versions", headers=users[2]["headers"], json=body
        )
        assert response.status_code == 201, response.text
    elif change == "rules":
        body = {**deepcopy(current["rules"]), "version": 2, "source_version": "v2"}
        response = await client.post(f"{ROOT}/approved-quality-rules", headers=users[2]["headers"], json=body)
        assert response.status_code == 201, response.text
    elif change == "recipe":
        async with pg_manager.get_async_session_context() as session:
            row = await session.get(RecipeVersion, current["recipe"])
            row.nutrients = {**row.nutrients, "energy_kcal": "111"}
    else:
        async with pg_manager.get_async_session_context() as session:
            row = await session.get(HealthInitialPlanPreview, generated["preview_id"])
            altered = deepcopy(row.snapshot)
            altered["professional_review"] = "approved"
            row.snapshot = altered
    for response in (
        await client.get(f"{ROOT}/initial-meal-plan-previews/{generated['preview_id']}", headers=owner),
        await save(client, owner, current, generated["preview_id"]),
    ):
        assert response.status_code == 410 and response.json()["code"] == "source_invalidated", response.text
    await assert_no_plan(users[0]["uid"])


async def test_generation_missing_rules_and_second_allergy_have_no_receipt(health_http):  # noqa: F811
    """批准目录缺失及第二成员限制均不能产生可确认回执。"""
    client, users = health_http
    current = await setup_initial(client, users)
    owner = users[0]["headers"]
    rules = deepcopy(current["rules"])
    rules.update(version=2, source_version="v2")
    rules["payload"].pop("meal_generation")
    response = await client.post(f"{ROOT}/approved-quality-rules", headers=users[2]["headers"], json=rules)
    assert response.status_code == 201, response.text
    payload = selection(current, family=True)
    payload["rule_version"] = 2
    response = await client.post(
        f"{ROOT}/members/{current['member']}/initial-meal-plan-previews", headers=owner, json=payload
    )
    assert response.status_code == 200 and response.json()["reason"] == "initial_generation_rules_not_approved"
    async with pg_manager.get_async_session_context() as session:
        assert (
            await session.scalar(
                select(HealthInitialPlanPreview).where(HealthInitialPlanPreview.actor_uid == users[0]["uid"])
            )
            is None
        )
    rules = deepcopy(current["rules"])
    rules.update(version=3, source_version="v3")
    rules["payload"]["ingredient_classifications"][0]["allergen_codes"] = ["synthetic_allergen"]
    response = await client.post(f"{ROOT}/approved-quality-rules", headers=users[2]["headers"], json=rules)
    assert response.status_code == 201
    profile = deepcopy(current["profile"])
    profile.update(version=2, source_version="v2")
    profile["payload"]["allergies"] = {"state": "specified", "codes": ["synthetic_allergen"]}
    response = await client.post(
        f"{ROOT}/members/{current['second']}/external-profile-versions", headers=users[2]["headers"], json=profile
    )
    assert response.status_code == 201
    payload.update(rule_version=3, profile_versions={current["member"]: 1, current["second"]: 2})
    response = await client.post(
        f"{ROOT}/members/{current['member']}/initial-meal-plan-previews", headers=owner, json=payload
    )
    assert response.status_code == 200 and response.json()["reason"] == "no_eligible_dish_candidates"
    assert "preview_id" not in response.json()
    await assert_no_plan(users[0]["uid"])


async def test_pg_member_wait_reads_new_version_after_lock(health_http, monkeypatch):  # noqa: F811
    """真实PG第二成员锁等待后读到新投影，不使用等待前的档案。"""
    from yuxi.repositories.health_vision_repository import HealthVisionRepository
    from yuxi.services.health_initial_meal_plan_service import initial_context_in_session

    client, users = health_http
    current = await setup_initial(client, users)
    ids = sorted([current["member"], current["second"]])
    waiting, seen = asyncio.Event(), []
    authorize = HealthVisionRepository.authorize

    async def observed(self, mid, uid, scope, *, lock=False):
        """只观察调用时序，真实PG锁和授权保持。"""
        if lock:
            seen.append(mid)
            if mid == ids[1]:
                waiting.set()
        return await authorize(self, mid, uid, scope, lock=lock)

    monkeypatch.setattr(HealthVisionRepository, "authorize", observed)
    selected = InitialPlanSelection.model_validate(selection(current, family=True))

    async def read():
        """在独立实际会话读取生成来源。"""
        async with pg_manager.get_async_session_context() as session:
            return await initial_context_in_session(session, users[0]["uid"], current["member"], selected)

    task = None
    try:
        async with pg_manager.get_async_session_context() as writer:
            await writer.scalar(select(FamilyMember).where(FamilyMember.id == ids[1]).with_for_update())
            task = asyncio.create_task(read())
            await asyncio.wait_for(waiting.wait(), 10)
            assert not task.done()
            row = await writer.scalar(select(HealthProfileSnapshot).where(HealthProfileSnapshot.member_id == ids[1]))
            row.version = 2
            proof_body = {**row.attestation, "version": 2, "source_version": "v2"}
            row.attestation = proof_body
            row.content_hash = projection_digest("profile", row.member_id, 2, row.payload, proof_body)
        with pytest.raises(HealthVisionError, match="source_version_conflict"):
            await asyncio.wait_for(task, 10)
        assert seen == ids
    finally:
        if task is not None and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)


async def test_same_key_different_initial_confirmation_conflicts(health_http):  # noqa: F811
    """同键不同日期回执拒绝，PG只保留首次确认的一组结果。"""
    client, users = health_http
    current = await setup_initial(client, users)
    owner = users[0]["headers"]
    generated = await preview(client, owner, current)
    other = await client.post(
        f"{ROOT}/members/{current['member']}/initial-meal-plan-previews",
        headers=owner,
        json={**selection(current), "plan_date": "2026-10-09"},
    )
    assert other.status_code == 200 and other.json()["status"] == "ready"
    key = str(uuid4())
    saved = await save(client, owner, current, generated["preview_id"], request_id=key)
    assert saved.status_code == 201, saved.text
    conflict = await save(client, owner, current, other.json()["preview_id"], request_id=key)
    assert conflict.status_code == 409 and conflict.json()["code"] == "request_conflict", conflict.text
    async with pg_manager.get_async_session_context() as session:
        for model in (HealthMealPlan, HealthMealPlanRevision, HealthQualityCheck, HealthProfessionalReview):
            assert (
                await session.scalar(select(func.count()).select_from(model).where(model.actor_uid == users[0]["uid"]))
                == 1
            )
        row = await session.get(HealthMealPlan, saved.json()["plan_id"])
        assert row.spec["plan_date"] == "2026-10-08"
    replay = await save(client, owner, current, generated["preview_id"], request_id=key)
    assert replay.status_code == 201 and replay.json() == saved.json()


@pytest.mark.parametrize("withdraw", ["diet_edit", "profile_view"])
async def test_second_member_withdrawal_blocks_all_initial_paths(health_http, withdraw):  # noqa: F811
    """第二成员撤权覆盖新生成、旧预览与确认；恢复授权提供正向反例。"""
    client, users = health_http
    current = await setup_initial(client, users)
    owner = users[0]["headers"]
    generated = await preview(client, owner, current, family=True)
    scopes = [s for s in ("profile_edit", "diet_edit", "profile_view") if s != withdraw]
    response = await client.put(
        f"{ROOT}/members/{current['second']}/grants",
        headers=owner,
        json={"actor_uid": users[0]["uid"], "scopes": scopes},
    )
    assert response.status_code == 200, response.text
    for response in (
        await client.get(f"{ROOT}/initial-meal-plan-previews/{generated['preview_id']}", headers=owner),
        await save(client, owner, current, generated["preview_id"]),
        await client.post(
            f"{ROOT}/members/{current['member']}/initial-meal-plan-previews",
            headers=owner,
            json=selection(current, family=True),
        ),
    ):
        assert response.status_code == 404, response.text
    await assert_no_plan(users[0]["uid"])
    response = await client.put(
        f"{ROOT}/members/{current['second']}/grants",
        headers=owner,
        json={"actor_uid": users[0]["uid"], "scopes": ["profile_edit", "diet_edit", "profile_view"]},
    )
    assert response.status_code == 200, response.text
    read = await client.get(f"{ROOT}/initial-meal-plan-previews/{generated['preview_id']}", headers=owner)
    assert read.status_code == 200 and read.json() == generated
    saved = await save(client, owner, current, generated["preview_id"])
    assert saved.status_code == 201, saved.text


async def test_final_check_failure_rolls_back_entire_initial_confirmation(health_http, monkeypatch):  # noqa: F811
    """最终真实检查读到未知过敏，初版、修订、检查与审核草稿一并回滚。"""
    from yuxi.services import health_initial_meal_plan_service as initial
    from yuxi.services.health_meal_plan_types import MealPlanSave

    client, users = health_http
    current = await setup_initial(client, users)
    generated = await preview(client, users[0]["headers"], current)
    check_owner = initial.check_plan_in_session

    async def changed_source(session, uid, plan_id, data):
        """在实际事务内改变来源，仍执行真实质量Owner和全部持久化。"""
        assert await session.get(HealthMealPlan, plan_id) is not None
        row = await session.scalar(
            select(HealthProfileSnapshot).where(HealthProfileSnapshot.member_id == current["member"])
        )
        row.payload = {**deepcopy(row.payload), "allergies": {"state": "unknown", "codes": []}}
        row.content_hash = projection_digest("profile", row.member_id, row.version, row.payload, row.attestation)
        await session.flush()
        return await check_owner(session, uid, plan_id, data)

    key = str(uuid4())
    data = MealPlanSave(client_request_id=key, preview_id=generated["preview_id"])
    monkeypatch.setattr(initial, "check_plan_in_session", changed_source)
    with pytest.raises(HealthVisionError, match="quality_not_passed"):
        await initial.save_initial_plan(users[0]["uid"], current["member"], data)
    await assert_no_plan(users[0]["uid"])
    async with pg_manager.get_async_session_context() as session:
        row = await session.scalar(
            select(HealthProfileSnapshot).where(HealthProfileSnapshot.member_id == current["member"])
        )
        assert row.payload["allergies"] == current["profile"]["payload"]["allergies"]
    monkeypatch.setattr(initial, "check_plan_in_session", check_owner)
    restored = await save(client, users[0]["headers"], current, generated["preview_id"], request_id=key)
    assert restored.status_code == 201 and restored.json()["quality_check"]["safety_check"]["status"] == "passed"


async def test_legacy_rules_reimport_retains_pre_generation_fingerprint(health_http):  # noqa: F811
    """已有批准规则缺新字段时，同版本重放保持原ID、摘要和唯一行。"""
    client, users = health_http
    current = await setup_initial(client, users)
    legacy = deepcopy(current["rules"])
    legacy["rule_code"] = "synthetic-legacy-" + uuid4().hex
    legacy["payload"].pop("meal_generation")
    first = await client.post(f"{ROOT}/approved-quality-rules", headers=users[2]["headers"], json=legacy)
    assert first.status_code == 201, first.text
    async with pg_manager.get_async_session_context() as session:
        row = await session.scalar(
            select(HealthRuleSnapshot).where(HealthRuleSnapshot.rule_code == legacy["rule_code"])
        )
        # 模拟真实旧版归一化存量：新增可空字段不存在，摘要由旧负载独立计算。
        old_payload = {k: v for k, v in row.payload.items() if k != "meal_generation"}
        row.payload = old_payload
        old_hash = projection_digest("rules", row.rule_code, row.version, old_payload, row.attestation)
        row.content_hash = old_hash
        old_id = row.id
    replay = await client.post(f"{ROOT}/approved-quality-rules", headers=users[2]["headers"], json=legacy)
    assert replay.status_code == 201, replay.text
    assert replay.json()["id"] == old_id and replay.json()["content_hash"] == old_hash
    async with pg_manager.get_async_session_context() as session:
        rows = list(
            (
                await session.scalars(
                    select(HealthRuleSnapshot).where(HealthRuleSnapshot.rule_code == legacy["rule_code"])
                )
            ).all()
        )
        assert len(rows) == 1 and "meal_generation" not in rows[0].payload


async def test_initial_family_can_revise_participation_but_rejects_changed_nutrition(health_http):  # noqa: F811
    """B从早餐66改午餐99，来源记录不妨碍改版，营养篡改仍拒绝。"""
    from test.unit.services.test_health_family_participation import participation_body

    client, users = health_http
    current = await setup_initial(client, users)
    owner = users[0]["headers"]
    generated = await preview(client, owner, current, family=True)
    key = str(uuid4())
    saved = await save(client, owner, current, generated["preview_id"], request_id=key)
    assert saved.status_code == 201, saved.text
    plan_id = saved.json()["plan_id"]
    body = participation_body(deepcopy(generated["plan_spec"]), {current["member"]: 1, current["second"]: 1})
    body["rule_code"] = current["rules"]["rule_code"]
    for meal in body["allocations"]:
        meal["participant_ids"] = [current["member"]]
        meal["dishes"][0]["member_portions"] = [{"member_id": current["member"], "grams": "100"}]
        if meal["meal_type"] == "lunch":
            meal["participant_ids"].append(current["second"])
            meal["dishes"][0]["member_portions"].append({"member_id": current["second"], "grams": "90"})
    async with pg_manager.get_async_session_context() as session:
        row = await session.get(HealthMealPlan, plan_id)
        original = deepcopy(row.snapshot)
        altered = deepcopy(original)
        altered["nutrition"]["totals"]["energy_kcal"] = "1.00"
        row.snapshot = altered
    invalid = await client.post(f"{ROOT}/meal-plans/{plan_id}/family-participation-preview", headers=owner, json=body)
    assert invalid.status_code == 410 and invalid.json()["code"] == "source_invalidated", invalid.text
    async with pg_manager.get_async_session_context() as session:
        row = await session.get(HealthMealPlan, plan_id)
        row.snapshot = original
        assert row.version == 1
        assert (
            await session.scalar(
                select(func.count())
                .select_from(HealthMealPlanRevision)
                .where(HealthMealPlanRevision.plan_id == plan_id)
            )
            == 1
        )
    trial = await client.post(f"{ROOT}/meal-plans/{plan_id}/family-participation-preview", headers=owner, json=body)
    assert trial.status_code == 200 and trial.json()["status"] == "ready", trial.text
    assert trial.json()["plan_snapshot"]["nutrition"]["totals"]["energy_kcal"] == "429.00"
    assert trial.json()["plan_snapshot"]["members"][current["second"]]["nutrition"]["totals"]["energy_kcal"] == "99.00"
    request_id = str(uuid4())
    changed = await client.post(
        f"{ROOT}/meal-plans/{plan_id}/family-participation",
        headers={**owner, "Idempotency-Key": request_id, "If-Match": '"1"'},
        json={
            **body,
            "client_request_id": request_id,
            "preview_hash": trial.json()["preview_hash"],
            "reason": "B明确改为参加午餐",
        },
    )
    assert changed.status_code == 200 and changed.json()["version"] == 2, changed.text
    assert changed.json()["quality_check"]["safety_check"]["status"] == "passed"
    replay = await save(client, owner, current, generated["preview_id"], request_id=key)
    assert replay.status_code == 410 and replay.json()["code"] == "source_invalidated", replay.text
    async with pg_manager.get_async_session_context() as session:
        row = await session.get(HealthMealPlan, plan_id)
        assert row.version == 2 and row.snapshot["nutrition"]["totals"]["energy_kcal"] == "429.00"
        revisions = list(
            (
                await session.scalars(
                    select(HealthMealPlanRevision)
                    .where(HealthMealPlanRevision.plan_id == plan_id)
                    .order_by(HealthMealPlanRevision.version)
                )
            ).all()
        )
        assert len(revisions) == 2 and revisions[0].snapshot == original

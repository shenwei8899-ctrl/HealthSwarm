"""实际HTTP/PG证明个人目标来源、权限及计划消费者。"""

from copy import deepcopy
from decimal import Decimal
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select, func

from test.integration.services.test_health_vision_http import ROOT, health_http  # noqa: F401
from test.integration.services.test_health_quality_http import setup_quality, action
from test.integration.services.test_health_safe_meal_swap_http import setup_swap, candidates
from test.integration.services.test_health_safe_plan_regeneration_http import preview, save, selection, assert_original
from test.unit.services.test_health_personal_targets import target_formula
from yuxi.storage.postgres.manager import pg_manager
from yuxi.services.health_quality_checks import projection_digest
from yuxi.utils.datetime_utils import utc_now_naive
from yuxi.storage.postgres.models_health import (
    HealthProfileSnapshot,
    HealthRuleSnapshot,
    HealthQualityCheck,
    HealthProfessionalReview,
    HealthMealPlanAdoption,
    HealthMealPlan,
    HealthMealPlanRevision,
)

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def import_targets(client, users, current, *, missing_weight=False):
    """实际管理员导入明确外部版本，不由计划请求提交身体参数。"""
    profile = deepcopy(current["profile"])
    profile.update(version=2, source_version="v2")
    profile["payload"].update(sex_code="synthetic_sex", weight_kg="60", activity_code="synthetic_activity")
    if missing_weight:
        profile["payload"].pop("weight_kg")
    response = await client.post(
        f"{ROOT}/members/{current['member']}/external-profile-versions", headers=users[2]["headers"], json=profile
    )
    assert response.status_code == 201, response.text
    rules = deepcopy(current["rules"])
    rules.update(version=rules["version"] + 1, source_version=f"v{rules['version'] + 1}")
    rules["payload"]["personal_targets"] = [target_formula()]
    response = await client.post(f"{ROOT}/approved-quality-rules", headers=users[2]["headers"], json=rules)
    assert response.status_code == 201, response.text
    return profile, rules


async def read_targets(client, headers, current, *, profile_version=2, rule_version=2, extra=None):
    """读取仅指定当前版本与规则。"""
    return await client.post(
        f"{ROOT}/members/{current['member']}/nutrition-targets",
        headers=headers,
        json={
            "profile_version": profile_version,
            "rule_version": rule_version,
            "rule_code": current["rules"]["rule_code"],
            **(extra or {}),
        },
    )


async def test_personal_target_constrains_full_day_repair_and_persisted_check(health_http):  # noqa: F811
    """300通用通过但330个人目标不通过；55+110+165三餐实际共同修复。"""
    client, users = health_http
    owner = users[0]["headers"]
    current = await setup_swap(client, users, count=1)
    profile, rules = await import_targets(client, users, current)
    response = await read_targets(client, owner, current, rule_version=3)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["status"] == "ready" and Decimal(result["energy_kcal"]) == 330
    assert result["professional_review"] == "not_a_professional_decision"
    assert result["attestations"]["profile"]["source_ref"] == profile["source_ref"]
    assert result["sources"]["profile"]["version"] == 2 and result["sources"]["rules"]["version"] == 3
    async with pg_manager.get_async_session_context() as session:
        stored = await session.get(HealthProfileSnapshot, result["sources"]["profile"]["id"])
        assert stored.content_hash == result["sources"]["profile"]["content_hash"]
        assert stored.payload["weight_kg"] == "60"
        stored_rules = await session.get(HealthRuleSnapshot, result["sources"]["rules"]["id"])
        assert stored_rules.payload["personal_targets"][0]["weight_kg_coefficient"] == "5"
        await assert_original(session, current)
    checked = await client.post(
        f"{ROOT}/meal-plans/{current['plan']}/quality-checks",
        headers=owner,
        json={"client_request_id": str(uuid4()), "version": 1, "rule_code": rules["rule_code"]},
    )
    assert checked.status_code == 201, checked.text
    assert checked.json()["safety_check"]["status"] == "conflict"
    read = await client.get(f"{ROOT}/quality-checks/{checked.json()['check_id']}", headers=owner)
    case = read.json()["review"]["review_id"]
    await action(client, owner, case, "submit", 1)
    assert (await action(client, users[1]["headers"], case, "approve", 2, expected=409))["code"] == "quality_not_passed"
    rejected_adoption = await client.post(
        f"{ROOT}/meal-plans/{current['plan']}/adopt",
        headers=owner,
        json={
            "client_request_id": str(uuid4()),
            "version": 1,
            "review_id": case,
            "profile_versions": {current["member"]: 2},
        },
    )
    assert rejected_adoption.status_code == 409, rejected_adoption.text
    assert (await candidates(client, owner, current, rule_version=3, profile_version=2))["candidates"] == []
    generated = await preview(client, owner, current, rule_version=3, profile_version=2)
    assert (
        generated["status"] == "ready" and generated["plan_snapshot"]["nutrition"]["totals"]["energy_kcal"] == "330.00"
    )
    assert generated["safety_check"]["personal_targets"]["energy_kcal"] == result["energy_kcal"]
    response = await save(
        client,
        owner,
        current,
        {
            **selection(current, rule_version=3, profile_version=2),
            "preview_hash": generated["preview_hash"],
            "client_request_id": str(uuid4()),
        },
    )
    assert response.status_code == 200, response.text
    async with pg_manager.get_async_session_context() as session:
        plan = await session.get(HealthMealPlan, current["plan"])
        assert plan.version == 2 and plan.snapshot["nutrition"]["totals"]["energy_kcal"] == "330.00"
        check = await session.get(HealthQualityCheck, response.json()["quality_check"]["check_id"])
        assert check.snapshot["safety_check"]["checks_version"] == "quality-rules-v2-personal"
        assert check.snapshot["safety_check"]["personal_targets"] == generated["safety_check"]["personal_targets"]
        assert check.snapshot["sources"]["profiles"][current["member"]]["version"] == 2
        assert check.snapshot["sources"]["rules"]["version"] == 3
        case = await session.scalar(
            select(HealthProfessionalReview).where(HealthProfessionalReview.check_id == check.id)
        )
        assert case.status == "draft"
        assert (
            await session.scalar(
                select(func.count())
                .select_from(HealthMealPlanRevision)
                .where(HealthMealPlanRevision.plan_id == plan.id)
            )
            == 2
        )


async def test_missing_weight_blocks_check_and_regeneration_without_writes(health_http):  # noqa: F811
    """缺确认体重不能返回默认目标，也不能强行重生成或专业批准。"""
    client, users = health_http
    current = await setup_swap(client, users, count=1)
    owner = users[0]["headers"]
    await import_targets(client, users, current, missing_weight=True)
    response = await read_targets(client, owner, current, rule_version=3)
    assert response.status_code == 200 and response.json()["reason"] == "confirmed_formula_input_required"
    assert response.json()["missing_field"] == "weight_kg" and "bounds" not in response.json()
    generated = await preview(client, owner, current, profile_version=2, rule_version=3)
    assert generated["status"] == "not_ready" and "plan_spec" not in generated
    checked = await client.post(
        f"{ROOT}/meal-plans/{current['plan']}/quality-checks",
        headers=owner,
        json={"client_request_id": str(uuid4()), "version": 1, "rule_code": current["rules"]["rule_code"]},
    )
    assert checked.status_code == 201 and checked.json()["safety_check"]["status"] == "unknown"
    assert checked.json()["safety_check"]["missing"][0]["path"] == "personal_targets"
    read = await client.get(f"{ROOT}/quality-checks/{checked.json()['check_id']}", headers=owner)
    case = read.json()["review"]["review_id"]
    await action(client, owner, case, "submit", 1)
    assert (await action(client, users[1]["headers"], case, "approve", 2, expected=409))["code"] == "quality_not_passed"
    async with pg_manager.get_async_session_context() as session:
        await assert_original(session, current)


async def test_read_requires_current_profile_view_and_does_not_accept_client_inputs(health_http):  # noqa: F811
    """管理员没有读取旁路；撤授权后读取失败，客户端不能替换身体字段。"""
    client, users = health_http
    current = await setup_quality(client, users)
    owner, reviewer, admin = [u["headers"] for u in users]
    await import_targets(client, users, current)
    assert (await read_targets(client, admin, current)).status_code == 404
    assert (await read_targets(client, reviewer, current)).json()["status"] == "ready"
    revoke = await client.put(
        f"{ROOT}/members/{current['member']}/grants", headers=owner, json={"actor_uid": users[1]["uid"], "scopes": []}
    )
    assert revoke.status_code == 200
    assert (await read_targets(client, reviewer, current)).status_code == 404
    for field in ("weight_kg", "formula", "energy_kcal", "bounds"):
        assert (await read_targets(client, owner, current, extra={field: "999"})).status_code == 422
    assert (await read_targets(client, owner, current, profile_version=1)).status_code == 409
    assert (await read_targets(client, owner, current, rule_version=1)).status_code == 409


async def test_changed_profile_recalculates_and_invalidates_approval_and_adoption(health_http):  # noqa: F811
    """旧300计划批准后增加330个人目标，旧专业决定和采用同时失效。"""
    client, users = health_http
    current = await setup_quality(client, users)
    owner = users[0]["headers"]
    case = current["case"]["review_id"]
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
    profile, _ = await import_targets(client, users, current)
    assert Decimal((await read_targets(client, owner, current)).json()["energy_kcal"]) == 330
    profile.update(version=3, source_version="v3")
    profile["payload"]["weight_kg"] = "50"
    changed = await client.post(
        f"{ROOT}/members/{current['member']}/external-profile-versions", headers=users[2]["headers"], json=profile
    )
    assert changed.status_code == 201, changed.text
    assert (await read_targets(client, owner, current)).status_code == 409
    assert Decimal((await read_targets(client, owner, current, profile_version=3)).json()["energy_kcal"]) == 280
    async with pg_manager.get_async_session_context() as session:
        assert (await session.get(HealthProfessionalReview, case)).status == "invalidated"
        adoption = await session.get(HealthMealPlanAdoption, adopted.json()["adoption_id"])
        assert adoption.status == "invalidated" and adoption.snapshot == adopted.json()["snapshot"]
        await assert_original(session, current)


@pytest.mark.parametrize("source", ["profile", "rules"])
async def test_revoked_source_and_old_import_replay_cannot_restore_target(health_http, source):  # noqa: F811
    """读取当前最高版本且撤回后同版本导入不复活可用目标。"""
    client, users = health_http
    current = await setup_quality(client, users)
    profile, rules = await import_targets(client, users, current)
    base = (
        f"{ROOT}/members/{current['member']}/external-profile-versions"
        if source == "profile"
        else f"{ROOT}/approved-quality-rules"
    )
    revoke_url = f"{base}/2/revoke" if source == "profile" else f"{base}/{rules['rule_code']}/versions/2/revoke"
    response = await client.post(revoke_url, headers=users[2]["headers"])
    assert response.status_code == 200, response.text
    replay = await client.post(base, headers=users[2]["headers"], json=profile if source == "profile" else rules)
    assert replay.status_code == 201, replay.text
    response = await read_targets(client, users[0]["headers"], current)
    assert response.status_code == 200 and response.json()["status"] == "not_ready"
    assert response.json()["sources"][source]["reason"] == "revoked"
    assert "bounds" not in response.json()


@pytest.mark.parametrize(
    "source,change", [("profile", "expired"), ("rules", "expired"), ("profile", "tampered"), ("rules", "tampered")]
)
async def test_expired_or_tampered_source_has_no_ready_target(health_http, source, change):  # noqa: F811
    """真实持久化损坏和自然有效期检查分别失败，无其他旧版本回退。"""
    client, users = health_http
    current = await setup_quality(client, users)
    await import_targets(client, users, current)
    ready = (await read_targets(client, users[0]["headers"], current)).json()
    async with pg_manager.get_async_session_context() as session:
        model = HealthProfileSnapshot if source == "profile" else HealthRuleSnapshot
        row = await session.get(model, ready["sources"][source]["id"])
        if change == "expired":
            row.valid_until = utc_now_naive() - timedelta(seconds=1)
            proof = deepcopy(row.attestation)
            proof["valid_until"] = row.valid_until.isoformat() + "Z"
            row.attestation = proof
            kind = "profile" if source == "profile" else "rules"
            key = current["member"] if source == "profile" else current["rules"]["rule_code"]
            row.content_hash = projection_digest(kind, key, row.version, row.payload, proof)
        else:
            payload = deepcopy(row.payload)
            if source == "profile":
                payload["weight_kg"] = "50"
            else:
                payload["personal_targets"][0]["intercept_kcal"] = "0"
            row.payload = payload
    response = await read_targets(client, users[0]["headers"], current)
    assert response.status_code == 200 and response.json()["status"] == "not_ready"
    assert response.json()["sources"][source]["reason"] == ("expired" if change == "expired" else "integrity_mismatch")
    assert "bounds" not in response.json()


async def test_legacy_import_digest_and_same_version_replay_remain_stable(health_http):  # noqa: F811
    """旧持久payload无新增键；空新增字段不改指纹，非空同版本仍冲突。"""
    client, users = health_http
    current = await setup_quality(client, users)
    async with pg_manager.get_async_session_context() as session:
        old_profile = await session.scalar(
            select(HealthProfileSnapshot).where(HealthProfileSnapshot.member_id == current["member"])
        )
        old_rules = await session.scalar(
            select(HealthRuleSnapshot).where(HealthRuleSnapshot.rule_code == current["rules"]["rule_code"])
        )
        # 历史payload由独立旧协议构造，不用当前导入器生成兼容性oracle。
        legacy_profile = deepcopy(current["profile"]["payload"])
        legacy_rules = {**deepcopy(current["rules"]["payload"]), "meal_swap": None}
        for row, body, payload, kind, key in [
            (old_profile, current["profile"], legacy_profile, "profile", current["member"]),
            (old_rules, current["rules"], legacy_rules, "rules", current["rules"]["rule_code"]),
        ]:
            proof = {k: v for k, v in body.items() if k != "payload"}
            for field in ("attested_at", "valid_until"):
                proof[field] = proof[field].replace("+00:00", "Z")
            row.payload, row.attestation = payload, proof
            row.content_hash = projection_digest(kind, key, 1, payload, proof)
        profile_hash, rules_hash = old_profile.content_hash, old_rules.content_hash
    body = deepcopy(current["profile"])
    body["payload"].update(sex_code=None, height_cm=None, weight_kg=None, activity_code=None)
    base = f"{ROOT}/members/{current['member']}/external-profile-versions"
    response = await client.post(base, headers=users[2]["headers"], json=body)
    assert response.status_code == 201 and response.json()["content_hash"] == profile_hash
    rules_body = deepcopy(current["rules"])
    rules_body["payload"]["personal_targets"] = None
    response = await client.post(f"{ROOT}/approved-quality-rules", headers=users[2]["headers"], json=rules_body)
    assert response.status_code == 201 and response.json()["content_hash"] == rules_hash
    body["payload"]["weight_kg"] = "60"
    assert (await client.post(base, headers=users[2]["headers"], json=body)).status_code == 409
    response = await read_targets(client, users[0]["headers"], current, rule_version=1, profile_version=1)
    assert response.json()["reason"] == "personal_target_formula_not_approved"

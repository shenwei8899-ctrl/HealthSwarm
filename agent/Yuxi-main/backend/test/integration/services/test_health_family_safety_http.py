"""真实 HTTP/PG 验证专业安全投影与本人正式档案的当前来源。"""

import asyncio
from copy import deepcopy
from decimal import Decimal
import hashlib
import json
from uuid import uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError

from test.integration.services.test_health_family_profile_http import (
    ROOT,
    SYNTHETIC_PROFILE,
    cleanup_test_knowledge_resources,  # noqa: F401
    cleanup_test_sandboxes,  # noqa: F401
    create_health_member,
    create_source,
    ensure_live_api_schema,  # noqa: F401
    family_profile_http,  # noqa: F401
    linked_self,
)
from test.integration.services.test_health_meal_planner_http import plan_spec, publish_planner_recipe
from test.integration.services.test_health_quality_http import action, proof
from test.unit.services.test_health_personal_targets import target_formula
from test.unit.services.test_health_quality import profile_payload, rules_payload
from yuxi.repositories.family_repository import FamilyRepository
from yuxi.repositories.health_quality_repository import HealthQualityRepository
from yuxi.services.family_schemas import ProfileUpdate
from yuxi.services.family_service import FamilyService
from yuxi.services.health_nutrition_service import input_fingerprint
from yuxi.storage.postgres.models_business import FamilyArchive, FamilyMember as SourceMember
from yuxi.storage.postgres.models_health import (
    FamilyMember as HealthMember,
    HealthMealPlanAdoption,
    HealthProcessingConsent,
    HealthProfileSnapshot,
    HealthProfessionalReview,
    HealthQualityCheck,
    RecipeVersion,
)

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def grant_safety_import(client, headers, member_id, *, scopes=None):
    """管理员导入仍需本人明确授予健康字段维护范围。"""
    response = await client.put(
        f"{ROOT}/members/{member_id}/grants",
        headers=headers,
        json={"actor_uid": "admin", "scopes": scopes if scopes is not None else ["profile_edit", "profile_view"]},
    )
    assert response.status_code == 200, response.text


def safety_body(source=None, *, version=1, confirmed_version=2, unknown=None):
    """专业编码是显式合成输入，不从原始病史和医嘱文本生成。"""
    payload = profile_payload()
    payload.update(age_years=36, sex_code="synthetic_sex", height_cm="165", activity_code="synthetic_activity")
    if unknown:
        payload[unknown] = {"state": "unknown", "codes": []}
    body = {**proof(version), "status": "confirmed", "payload": payload}
    if source is not None:
        body["family_profile_source"] = {
            "family_id": source["family_id"],
            "source_member_id": source["source_member_id"],
            "confirmed_version": confirmed_version,
        }
    return body


async def linked_import(client, identities, *, confirmed=True, unknown=None):
    """复用正式关联入口与管理员外部投影入口。"""
    member_id, source = await linked_self(client, identities["self"], confirmed=confirmed)
    await grant_safety_import(client, identities["self"], member_id)
    body = safety_body(source, unknown=unknown)
    response = await client.post(
        f"{ROOT}/members/{member_id}/external-profile-versions", headers=identities["admin"], json=body
    )
    return member_id, source, body, response


async def publish_safety_rules(client, sessions, identities, *, recipe_id=None):
    """批准合成常数目标 300；不接独立体重，也不新增临床计算公式。"""
    payload = rules_payload()
    formula = target_formula()
    formula.update(intercept_kcal="300", weight_kg_coefficient="0")
    payload["personal_targets"] = [formula]
    if recipe_id is not None:
        async with sessions() as session:
            recipe = await session.get(RecipeVersion, recipe_id)
            food = deepcopy(recipe.ingredients[0]["food"])
        payload["ingredient_classifications"][0].update(food_id=food["id"], food_hash=input_fingerprint(food))
    body = {**proof(), "rule_code": "synthetic-family-" + uuid4().hex, "status": "approved", "payload": payload}
    response = await client.post(f"{ROOT}/approved-quality-rules", headers=identities["admin"], json=body)
    assert response.status_code == 201, response.text
    return body


async def read_target(client, headers, member_id, rules, *, version=1):
    """身体参数不能从目标请求进入，客户端只选明确来源版本。"""
    return await client.post(
        f"{ROOT}/members/{member_id}/nutrition-targets",
        headers=headers,
        json={"profile_version": version, "rule_version": 1, "rule_code": rules["rule_code"]},
    )


async def approved_source_plan(client, sessions, identities, *, linked=True):
    """计划、独立检查、专业批准与采用均通过真实 HTTP 提交。"""
    if linked:
        member_id, source, body, response = await linked_import(client, identities)
    else:
        member_id = await create_health_member(client, identities["self"])
        await grant_safety_import(client, identities["self"], member_id)
        source, body = None, safety_body()
        response = await client.post(
            f"{ROOT}/members/{member_id}/external-profile-versions", headers=identities["admin"], json=body
        )
    assert response.status_code == 201 and response.json()["status"] == "ready", response.text
    recipe = await publish_planner_recipe(client, identities["admin"], "正式来源关联合成菜")
    preview = await client.post(
        f"{ROOT}/members/{member_id}/meal-plan-previews", headers=identities["self"], json=plan_spec(recipe)
    )
    assert preview.status_code == 201 and preview.json()["nutrition"]["totals"]["energy_kcal"] == "300.00"
    request_id = str(uuid4())
    saved = await client.post(
        f"{ROOT}/members/{member_id}/meal-plans",
        headers={**identities["self"], "Idempotency-Key": request_id},
        json={"client_request_id": request_id, "preview_id": preview.json()["preview_id"]},
    )
    assert saved.status_code == 201, saved.text
    plan_id = saved.json()["plan_id"]
    rules = await publish_safety_rules(client, sessions, identities, recipe_id=recipe)
    grant = await client.put(
        f"{ROOT}/members/{member_id}/grants",
        headers=identities["self"],
        json={"actor_uid": "other", "scopes": ["profile_view", "professional_review"]},
    )
    assert grant.status_code == 200, grant.text
    qualified = await client.post(
        f"{ROOT}/professional-reviewers",
        headers=identities["admin"],
        json={**proof(), "status": "qualified", "reviewer_uid": "other"},
    )
    assert qualified.status_code == 201, qualified.text
    checked = await client.post(
        f"{ROOT}/meal-plans/{plan_id}/quality-checks",
        headers=identities["self"],
        json={"client_request_id": str(uuid4()), "version": 1, "rule_code": rules["rule_code"]},
    )
    assert checked.status_code == 201 and checked.json()["safety_check"]["status"] == "passed", checked.text
    read = await client.get(f"{ROOT}/quality-checks/{checked.json()['check_id']}", headers=identities["self"])
    assert read.status_code == 200, read.text
    review_id = read.json()["review"]["review_id"]
    await action(client, identities["self"], review_id, "submit", 1)
    await action(client, identities["other"], review_id, "approve", 2)
    adopted = await client.post(
        f"{ROOT}/meal-plans/{plan_id}/adopt",
        headers=identities["self"],
        json={
            "client_request_id": str(uuid4()),
            "version": 1,
            "review_id": review_id,
            "profile_versions": {member_id: 1},
        },
    )
    assert adopted.status_code == 201 and adopted.json()["status"] == "active", adopted.text
    return {
        "member_id": member_id,
        "source": source,
        "body": body,
        "rules": rules,
        "plan_id": plan_id,
        "check_id": checked.json()["check_id"],
        "review_id": review_id,
        "adoption": adopted.json(),
    }


async def test_source_bound_projection_replays_and_preserves_family_facts(family_profile_http):  # noqa: F811
    """服务器绑定稳定正式事实；重复导入不增行，也不产生模型同意。"""
    client, sessions, identities = family_profile_http
    member_id, source, body, first = await linked_import(client, identities)
    assert first.status_code == 201, first.text
    initial = first.json()
    assert initial["status"] == "ready" and initial["scope"] == "nutrition_safety_projection"
    path = f"{ROOT}/members/{member_id}/external-profile-versions"
    replay = await client.post(path, headers=identities["admin"], json=body)
    assert replay.status_code == 201 and replay.json() == initial, replay.text
    read = await client.get(path + "/current", headers=identities["self"])
    assert read.status_code == 200 and read.json() == initial, read.text
    raw = await client.get(f"{ROOT}/members/{member_id}/family-profile", headers=identities["self"])
    assert raw.json()["profile"] == SYNTHETIC_PROFILE
    assert raw.json()["nutrition_safety_ready"] is raw.json()["full_health_profile_available"] is False
    async with sessions() as session:
        rows = (await session.scalars(select(HealthProfileSnapshot))).all()
        assert len(rows) == 1 and rows[0].imported_by == "admin"
        formal = await session.get(SourceMember, source["source_member_id"])
        expected_facts = {**body["family_profile_source"], "profile": formal.profile}
        expected_hash = hashlib.sha256(
            json.dumps(expected_facts, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
        ).hexdigest()
        assert rows[0].attestation["family_profile_source"] == {
            **body["family_profile_source"],
            "source_hash": expected_hash,
        }
        assert rows[0].content_hash == initial["content_hash"]
        assert formal.version == formal.confirmed_version == 2
        assert await session.scalar(select(func.count()).select_from(HealthProcessingConsent)) == 0
    changed = deepcopy(body)
    changed["payload"]["conditions"] = {"state": "unknown", "codes": []}
    rejected = await client.post(path, headers=identities["admin"], json=changed)
    assert rejected.status_code == 409 and rejected.json()["code"] == "version_conflict", rejected.text


@pytest.mark.parametrize("changed", ["family_id", "source_member_id", "confirmed_version", "missing", "source_hash"])
async def test_import_rejects_forged_or_missing_current_source(family_profile_http, changed):  # noqa: F811
    """坐标、本人确认与服务端摘要不能由外部字符串或客户端替代。"""
    client, sessions, identities = family_profile_http
    member_id, source = await linked_self(client, identities["self"])
    await grant_safety_import(client, identities["self"], member_id)
    body = safety_body(source)
    if changed == "missing":
        body.pop("family_profile_source")
    elif changed == "source_hash":
        body["family_profile_source"][changed] = "a" * 64
    else:
        body["family_profile_source"][changed] = 3 if changed == "confirmed_version" else str(uuid4())
    response = await client.post(
        f"{ROOT}/members/{member_id}/external-profile-versions", headers=identities["admin"], json=body
    )
    assert response.status_code == (422 if changed == "source_hash" else 409), response.text
    if changed != "source_hash":
        expected = "family_profile_source_required" if changed == "missing" else "family_profile_source_conflict"
        assert response.json()["code"] == expected
    async with sessions() as session:
        assert await session.scalar(select(func.count()).select_from(HealthProfileSnapshot)) == 0


async def test_import_requires_subject_confirmation_and_current_admin_scope(family_profile_http):  # noqa: F811
    """后台角色不替代编辑授权；未确认正式版本不得进入专业投影。"""
    client, sessions, identities = family_profile_http
    member_id, source = await linked_self(client, identities["self"], confirmed=False)
    path = f"{ROOT}/members/{member_id}/external-profile-versions"
    body = safety_body(source)
    assert (await client.post(path, headers=identities["admin"], json=body)).status_code == 404
    await grant_safety_import(client, identities["self"], member_id, scopes=["profile_view"])
    assert (await client.post(path, headers=identities["admin"], json=body)).status_code == 404
    await grant_safety_import(client, identities["self"], member_id)
    pending = await client.post(path, headers=identities["admin"], json=body)
    assert pending.status_code == 409 and pending.json()["code"] == "family_profile_unconfirmed", pending.text
    formal_path = f"/api/family/{source['family_id']}/members/{source['source_member_id']}"
    confirmed = await client.post(formal_path + "/confirm", headers=identities["self"], json={"expected_version": 2})
    assert confirmed.status_code == 200, confirmed.text
    assert (await client.post(path, headers=identities["self"], json=body)).status_code == 403
    accepted = await client.post(path, headers=identities["admin"], json=body)
    assert accepted.status_code == 201 and accepted.json()["status"] == "ready", accepted.text
    assert (await client.get(path + "/current", headers=identities["other"])).status_code == 404
    async with sessions() as session:
        assert await session.scalar(select(func.count()).select_from(HealthProfileSnapshot)) == 1


async def test_unlinked_legacy_projection_keeps_contract_but_cannot_claim_family(family_profile_http):  # noqa: F811
    """未关联的受信外部投影仍可重放；不存在的正式关联不能冒充有效来源。"""
    client, sessions, identities = family_profile_http
    member_id = await create_health_member(client, identities["self"])
    await grant_safety_import(client, identities["self"], member_id)
    path = f"{ROOT}/members/{member_id}/external-profile-versions"
    body = safety_body()
    accepted = await client.post(path, headers=identities["admin"], json=body)
    assert accepted.status_code == 201 and accepted.json()["status"] == "ready", accepted.text
    assert "family_profile_source" not in accepted.json()["attestation"]
    assert (await client.post(path, headers=identities["admin"], json=body)).json() == accepted.json()
    source = await create_source(client, identities["self"])
    rejected = await client.post(path, headers=identities["admin"], json=safety_body(source, version=2))
    assert rejected.status_code == 404, rejected.text
    async with sessions() as session:
        assert await session.scalar(select(func.count()).select_from(HealthProfileSnapshot)) == 1


@pytest.mark.parametrize("changed", ["raw_text", "inactive", "subject", "link_missing"])
async def test_read_rechecks_current_formal_source_even_without_projection_import(family_profile_http, changed):  # noqa: F811
    """专业投影未变时仍反查正式事实，身份变化和正文篡改不能继续读旧有效内容。"""
    from yuxi.storage.postgres.models_health import HealthFamilyProfileLink

    client, sessions, identities = family_profile_http
    member_id, source, _, imported = await linked_import(client, identities)
    assert imported.status_code == 201 and imported.json()["status"] == "ready", imported.text
    async with sessions() as session:
        formal = await session.get(SourceMember, source["source_member_id"])
        if changed == "raw_text":
            formal.profile = {**formal.profile, "medical_history": "合成更正正文：不能沿用旧专业依据"}
        elif changed == "inactive":
            formal.is_active = False
        elif changed == "subject":
            formal.subject_uid = "other"
        else:
            await session.delete(await session.get(HealthFamilyProfileLink, member_id))
        await session.commit()
    response = await client.get(
        f"{ROOT}/members/{member_id}/external-profile-versions/current", headers=identities["self"]
    )
    assert response.status_code == 200 and response.json()["status"] == "not_ready", response.text
    assert response.json()["payload"] is response.json()["attestation"] is None
    assert response.json()["reason"] == (
        "family_profile_source_unavailable" if changed in {"inactive", "subject"} else "family_profile_source_changed"
    )
    async with sessions() as session:
        row = await session.scalar(select(HealthProfileSnapshot))
        assert row.content_hash == imported.json()["content_hash"] and row.revoked_at is None


async def test_current_projection_read_loses_access_after_health_scope_withdrawal(family_profile_http):  # noqa: F811
    """撤回访问范围不被专业来源关联替代，空范围不能继续读取本人敏感投影。"""
    client, sessions, identities = family_profile_http
    member_id, _, _, imported = await linked_import(client, identities)
    assert imported.status_code == 201, imported.text
    revoked = await client.put(
        f"{ROOT}/members/{member_id}/grants",
        headers=identities["self"],
        json={"actor_uid": "self", "scopes": []},
    )
    assert revoked.status_code == 200, revoked.text
    denied = await client.get(
        f"{ROOT}/members/{member_id}/external-profile-versions/current", headers=identities["self"]
    )
    assert denied.status_code == 404, denied.text
    async with sessions() as session:
        row = await session.scalar(select(HealthProfileSnapshot))
        assert row.id == imported.json()["id"] and row.revoked_at is None


@pytest.mark.parametrize("state", ["none", "unknown"])
async def test_explicit_none_and_unknown_keep_distinct_target_results(family_profile_http, state):  # noqa: F811
    """来源有效不替代专业字段：明确无可算目标，未知条件不得按无条件公式计算。"""
    client, sessions, identities = family_profile_http
    member_id, _, body, response = await linked_import(
        client, identities, unknown="conditions" if state == "unknown" else None
    )
    assert response.status_code == 201 and response.json()["status"] == "ready", response.text
    assert response.json()["payload"]["conditions"] == {"state": state, "codes": []}
    rules = await publish_safety_rules(client, sessions, identities)
    target = await read_target(client, identities["self"], member_id, rules)
    assert target.status_code == 200, target.text
    if state == "none":
        assert target.json()["status"] == "ready" and Decimal(target.json()["energy_kcal"]) == 300
        assert target.json()["inputs"]["conditions"] == []
    else:
        assert target.json()["status"] == "not_ready"
        assert target.json()["reason"] == "confirmed_conditions_and_requirements_required"
        assert "energy_kcal" not in target.json() and "bounds" not in target.json()
    async with sessions() as session:
        row = await session.scalar(select(HealthProfileSnapshot))
        assert row.payload["conditions"] == body["payload"]["conditions"]


async def test_formal_correction_invalidates_targets_approval_and_adoption_in_write_transaction(
    family_profile_http,  # noqa: F811
):
    """正式改版不等读取就失效批准和采用；重新确认不复活旧专业依据。"""
    client, sessions, identities = family_profile_http
    current = await approved_source_plan(client, sessions, identities)
    member_id, source = current["member_id"], current["source"]
    before = await read_target(client, identities["self"], member_id, current["rules"])
    assert before.status_code == 200 and Decimal(before.json()["energy_kcal"]) == 300, before.text
    formal_path = f"/api/family/{source['family_id']}/members/{source['source_member_id']}"
    changed = await client.put(
        formal_path, headers=identities["self"], json={"expected_version": 2, "profile": {"height_cm": 170}}
    )
    assert changed.status_code == 200 and changed.json()["version"] == 3, changed.text
    # 不调用任何目标、审核或采用读取，直接观察 owning 更正事务的持久状态。
    async with sessions() as session:
        review = await session.get(HealthProfessionalReview, current["review_id"])
        adoption = await session.get(HealthMealPlanAdoption, current["adoption"]["adoption_id"])
        assert review.status == adoption.status == "invalidated"
        assert review.invalidation_reason == adoption.reason == "family_profile_changed"
        assert review.version == 4 and adoption.version == 2
        assert adoption.snapshot == current["adoption"]["snapshot"]
        check = await session.get(HealthQualityCheck, current["check_id"])
        assert check.snapshot["safety_check"]["status"] == "passed"
    stale = await read_target(client, identities["self"], member_id, current["rules"])
    assert stale.status_code == 200 and stale.json()["status"] == "not_ready", stale.text
    assert stale.json()["sources"]["profile"]["status"] == "not_ready" and "energy_kcal" not in stale.json()
    assert (
        await client.post(formal_path + "/confirm", headers=identities["self"], json={"expected_version": 3})
    ).status_code == 200
    unchanged = await client.get(
        f"{ROOT}/members/{member_id}/external-profile-versions/current", headers=identities["self"]
    )
    assert unchanged.status_code == 200 and unchanged.json()["status"] == "not_ready", unchanged.text
    checked = await client.post(
        f"{ROOT}/meal-plans/{current['plan_id']}/quality-checks",
        headers=identities["self"],
        json={"client_request_id": str(uuid4()), "version": 1, "rule_code": current["rules"]["rule_code"]},
    )
    assert checked.status_code == 201 and checked.json()["safety_check"]["status"] == "unknown", checked.text
    assert any(item["path"] == "profile" for item in checked.json()["safety_check"]["missing"])
    fresh_body = safety_body(source, version=2, confirmed_version=3)
    fresh_body["payload"]["height_cm"] = "170"
    imported = await client.post(
        f"{ROOT}/members/{member_id}/external-profile-versions", headers=identities["admin"], json=fresh_body
    )
    assert imported.status_code == 201 and imported.json()["status"] == "ready", imported.text
    fresh_target = await read_target(client, identities["self"], member_id, current["rules"], version=2)
    assert fresh_target.status_code == 200 and Decimal(fresh_target.json()["energy_kcal"]) == 300
    async with sessions() as session:
        assert (await session.get(HealthProfessionalReview, current["review_id"])).status == "invalidated"
        assert (await session.get(HealthMealPlanAdoption, current["adoption"]["adoption_id"])).status == "invalidated"


async def test_link_invalidates_legacy_approval_and_adoption_before_any_read(family_profile_http):  # noqa: F811
    """既有外部批准建立正式来源关联时，即刻失效，不靠查询触发收敛。"""
    client, sessions, identities = family_profile_http
    current = await approved_source_plan(client, sessions, identities, linked=False)
    source = await create_source(client, identities["self"])
    response = await client.post(
        f"{ROOT}/members/{current['member_id']}/family-profile-link", headers=identities["self"], json=source
    )
    assert response.status_code == 200, response.text
    async with sessions() as session:
        review = await session.get(HealthProfessionalReview, current["review_id"])
        adoption = await session.get(HealthMealPlanAdoption, current["adoption"]["adoption_id"])
        assert review.status == adoption.status == "invalidated"
        assert review.invalidation_reason == adoption.reason == "family_profile_linked"
        assert review.version == 4 and adoption.version == 2
        assert adoption.snapshot == current["adoption"]["snapshot"]
    assert (
        await client.post(
            f"{ROOT}/members/{current['member_id']}/family-profile-link", headers=identities["self"], json=source
        )
    ).json() == response.json()
    async with sessions() as session:
        assert (await session.get(HealthProfessionalReview, current["review_id"])).version == 4
        assert (await session.get(HealthMealPlanAdoption, current["adoption"]["adoption_id"])).version == 2
    stale = await client.get(
        f"{ROOT}/members/{current['member_id']}/external-profile-versions/current", headers=identities["self"]
    )
    assert stale.status_code == 200 and stale.json()["status"] == "not_ready", stale.text
    assert stale.json()["reason"] == "family_profile_source_unmapped" and stale.json()["payload"] is None


async def test_profile_noop_and_failed_correction_preserve_approved_state(family_profile_http, monkeypatch):  # noqa: F811
    """无实际更正不失效；更正事务失败时原档案、批准和采用一起保留。"""
    client, sessions, identities = family_profile_http
    current = await approved_source_plan(client, sessions, identities)
    source = current["source"]
    formal_path = f"/api/family/{source['family_id']}/members/{source['source_member_id']}"
    unchanged = await client.put(
        formal_path, headers=identities["self"], json={"expected_version": 2, "profile": {"height_cm": 165}}
    )
    assert unchanged.status_code == 200 and unchanged.json()["version"] == 2, unchanged.text
    original = HealthQualityRepository.invalidate

    async def fail_after_invalidation(repository, **kwargs):
        await original(repository, **kwargs)
        if kwargs.get("reason") == "family_profile_changed":
            raise RuntimeError("合成更正事务失败")

    monkeypatch.setattr(HealthQualityRepository, "invalidate", fail_after_invalidation)
    failed = await client.put(
        formal_path, headers=identities["self"], json={"expected_version": 2, "profile": {"height_cm": 175}}
    )
    assert failed.status_code == 500, failed.text
    async with sessions() as session:
        formal = await session.get(SourceMember, source["source_member_id"])
        assert formal.version == formal.confirmed_version == 2 and formal.profile["height_cm"] == 165
        review = await session.get(HealthProfessionalReview, current["review_id"])
        adoption = await session.get(HealthMealPlanAdoption, current["adoption"]["adoption_id"])
        assert review.status == "approved" and review.version == 3
        assert adoption.status == "active" and adoption.version == 1


async def test_family_lock_reader_waits_then_rechecks_committed_correction(family_profile_http, monkeypatch):  # noqa: F811
    """真实 PG family 行锁让读取等待，更正提交后只能返回新事实下的不可用来源。"""
    client, sessions, identities = family_profile_http
    member_id, source, _, imported = await linked_import(client, identities)
    assert imported.status_code == 201, imported.text
    reached_family = asyncio.Event()
    reader_pid = None
    original = FamilyRepository.get_family

    async def signal_family(repository, fid, uid, **kwargs):
        nonlocal reader_pid
        if fid == source["family_id"]:
            reader_pid = await repository.db.scalar(text("SELECT pg_backend_pid()"))
            reached_family.set()
        return await original(repository, fid, uid, **kwargs)

    monkeypatch.setattr(FamilyRepository, "get_family", signal_family)
    reader = None
    try:
        async with sessions() as writer:
            await writer.scalar(select(FamilyArchive).where(FamilyArchive.id == source["family_id"]).with_for_update())
            reader = asyncio.create_task(
                client.get(f"{ROOT}/members/{member_id}/external-profile-versions/current", headers=identities["self"])
            )
            await asyncio.wait_for(reached_family.wait(), 10)
            for _ in range(100):
                blocked = await writer.scalar(
                    text(
                        "SELECT count(*) FROM pg_stat_activity WHERE wait_event_type = 'Lock' "
                        "AND query LIKE '%family_archives%' AND pid = :pid"
                    ),
                    {"pid": reader_pid},
                )
                if blocked:
                    break
                await asyncio.sleep(0.01)
            assert blocked and not reader.done(), "读取未等待真实 family PostgreSQL 行锁"
            changed = await FamilyService(writer, "self").update_profile(
                source["family_id"],
                source["source_member_id"],
                ProfileUpdate(expected_version=2, profile={"height_cm": 171}),
            )
            assert changed["version"] == 3 and changed["confirmed"] is False
        response = await asyncio.wait_for(reader, 15)
        assert response.status_code == 200 and response.json()["status"] == "not_ready", response.text
        assert response.json()["payload"] is None
        async with sessions() as session:
            row = await session.get(SourceMember, source["source_member_id"])
            assert row.version == 3 and row.profile["height_cm"] == 171
    finally:
        if reader is not None and not reader.done():
            reader.cancel()
            await asyncio.gather(reader, return_exceptions=True)


async def test_shared_families_lock_in_sorted_order_for_disjoint_health_member_sets(family_profile_http):  # noqa: F811
    """不同健康集合共享两家庭时，较小来源先持锁，真实等待后两个事务均完成。"""
    client, sessions, identities = family_profile_http
    first_member, first_source = await linked_self(client, identities["self"])
    second_member, second_source = await linked_self(client, identities["other"])

    async def linked_guest(source, owner, subject):
        created = await client.post(
            f"/api/family/{source['family_id']}/members",
            headers=identities[owner],
            json={"name": "合成交叉本人", "relationship": "家人"},
        )
        assert created.status_code == 200, created.text
        source_id = created.json()["id"]
        invited = await client.post(
            f"/api/family/{source['family_id']}/members/{source_id}/invite", headers=identities[owner]
        )
        assert invited.status_code == 200, invited.text
        joined = await client.post(
            "/api/family/join", headers=identities[subject], json={"code": invited.json()["code"]}
        )
        assert joined.status_code == 200, joined.text
        member_id = await create_health_member(client, identities[subject])
        linked = await client.post(
            f"{ROOT}/members/{member_id}/family-profile-link",
            headers=identities[subject],
            json={"family_id": source["family_id"], "source_member_id": source_id, "confirmed_identity": True},
        )
        assert linked.status_code == 200, linked.text
        return member_id

    first_guest = await linked_guest(first_source, "self", "other")
    second_guest = await linked_guest(second_source, "other", "self")
    if first_source["family_id"] < second_source["family_id"]:
        smaller, larger = first_source["family_id"], second_source["family_id"]
        first_ids, second_ids = [second_member, first_member], [first_guest, second_guest]
    else:
        smaller, larger = second_source["family_id"], first_source["family_id"]
        first_ids, second_ids = [first_member, second_member], [second_guest, first_guest]
    assert set(first_ids).isdisjoint(second_ids)
    started, pids = {name: asyncio.Event() for name in ("first", "second")}, {}

    async def take_locks(name, member_ids):
        async with sessions() as session:
            await session.execute(
                select(HealthMember).where(HealthMember.id.in_(member_ids)).order_by(HealthMember.id).with_for_update()
            )
            pids[name] = await session.scalar(text("SELECT pg_backend_pid()"))
            started[name].set()
            await HealthQualityRepository(session).lock_profile_sources(member_ids)
            await session.commit()
            return True

    tasks = []
    try:
        async with sessions() as blocker:
            await blocker.scalar(select(FamilyArchive).where(FamilyArchive.id == larger).with_for_update())
            tasks.append(asyncio.create_task(take_locks("first", first_ids)))
            await asyncio.wait_for(started["first"].wait(), 10)
            for _ in range(100):
                await blocker.execute(text("SELECT pg_stat_clear_snapshot()"))
                waiting = await blocker.scalar(
                    text("SELECT wait_event_type FROM pg_stat_activity WHERE pid = :pid"), {"pid": pids["first"]}
                )
                if waiting == "Lock":
                    break
                await asyncio.sleep(0.01)
            assert waiting == "Lock" and not tasks[0].done()
            async with sessions() as probe:
                with pytest.raises(DBAPIError) as conflict:
                    await probe.scalar(
                        select(FamilyArchive).where(FamilyArchive.id == smaller).with_for_update(nowait=True)
                    )
                assert conflict.value.orig.sqlstate == "55P03", str(conflict.value)
                await probe.rollback()
            tasks.append(asyncio.create_task(take_locks("second", second_ids)))
            await asyncio.wait_for(started["second"].wait(), 10)
            for _ in range(100):
                await blocker.execute(text("SELECT pg_stat_clear_snapshot()"))
                waiting = await blocker.scalar(
                    text("SELECT wait_event_type FROM pg_stat_activity WHERE pid = :pid"), {"pid": pids["second"]}
                )
                if waiting == "Lock":
                    break
                await asyncio.sleep(0.01)
            assert waiting == "Lock" and not tasks[1].done()
            await blocker.commit()
        assert await asyncio.wait_for(asyncio.gather(*tasks), 15) == [True, True]
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

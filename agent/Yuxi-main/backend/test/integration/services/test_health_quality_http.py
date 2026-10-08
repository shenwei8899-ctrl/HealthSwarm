"""真实HTTP与PG验证外部版本、独立检查及专业状态流。"""

import asyncio
from copy import deepcopy
from datetime import datetime, timedelta, UTC
from uuid import uuid4

import pytest
from sqlalchemy import select

from test.integration.services.test_health_meal_planner_http import publish_planner_recipe, plan_spec
from test.integration.services.test_health_vision_http import ROOT, create_member, health_http  # noqa: F401
from test.unit.services.test_health_quality import profile_payload, rules_payload
from yuxi.services.health_nutrition_service import input_fingerprint
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_health import RecipeVersion, HealthProfessionalReview, HealthReviewAction

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


def proof(version=1):
    """仅隔离测试的外部批准凭据，禁止作为生产内容。"""
    now = datetime.now(UTC)
    return {
        "version": version,
        "source_ref": "synthetic:quality-http",
        "source_version": f"v{version}",
        "authority_ref": "synthetic:approval",
        "attested_by": "synthetic-professional",
        "attested_at": (now - timedelta(minutes=1)).isoformat(),
        "valid_until": (now + timedelta(days=1)).isoformat(),
    }


async def setup_quality(client, users, *, field=None):
    """当前食品摘要由已发布来源读取，期望营养仍独立手算。"""
    owner, reviewer, admin = [user["headers"] for user in users]
    member = await create_member(client, owner)
    recipe = await publish_planner_recipe(client, admin, "独立质量合成菜")
    preview = await client.post(f"{ROOT}/members/{member}/meal-plan-previews", headers=owner, json=plan_spec(recipe))
    assert preview.status_code == 201, preview.text
    key = str(uuid4())
    saved = await client.post(
        f"{ROOT}/members/{member}/meal-plans",
        headers={**owner, "Idempotency-Key": key},
        json={"client_request_id": key, "preview_id": preview.json()["preview_id"]},
    )
    assert saved.status_code == 201, saved.text
    for uid, scopes in [
        (users[2]["uid"], ["profile_edit"]),
        (users[1]["uid"], ["profile_view", "professional_review"]),
    ]:
        grant = await client.put(
            f"{ROOT}/members/{member}/grants", headers=owner, json={"actor_uid": uid, "scopes": scopes}
        )
        assert grant.status_code == 200, grant.text
    profile = profile_payload()
    if field == "unknown":
        profile["allergies"] = {"state": "unknown", "codes": []}
    elif field == "conflict":
        profile["allergies"] = {"state": "specified", "codes": ["synthetic_allergen"]}
    profile_body = {**proof(), "status": "confirmed", "payload": profile}
    imported = await client.post(f"{ROOT}/members/{member}/external-profile-versions", headers=admin, json=profile_body)
    assert imported.status_code == 201, imported.text
    async with pg_manager.get_async_session_context() as session:
        food = deepcopy((await session.get(RecipeVersion, recipe)).ingredients[0]["food"])
    rules = rules_payload()
    rules["ingredient_classifications"][0].update(food_id=food["id"], food_hash=input_fingerprint(food))
    rule_code = "synthetic-" + uuid4().hex
    rules_body = {**proof(), "rule_code": rule_code, "status": "approved", "payload": rules}
    imported = await client.post(f"{ROOT}/approved-quality-rules", headers=admin, json=rules_body)
    assert imported.status_code == 201, imported.text
    credential = {**proof(), "status": "qualified", "reviewer_uid": users[1]["uid"]}
    registered = await client.post(f"{ROOT}/professional-reviewers", headers=admin, json=credential)
    assert registered.status_code == 201, registered.text
    plan_id = saved.json()["plan_id"]
    check_body = {"client_request_id": str(uuid4()), "version": 1, "rule_code": rule_code}
    checked = await client.post(f"{ROOT}/meal-plans/{plan_id}/quality-checks", headers=owner, json=check_body)
    assert checked.status_code == 201, checked.text
    read = await client.get(f"{ROOT}/quality-checks/{checked.json()['check_id']}", headers=owner)
    assert read.status_code == 200, read.text
    return {
        "member": member,
        "plan": plan_id,
        "check": checked.json(),
        "body": check_body,
        "case": read.json()["review"],
        "profile": profile_body,
        "rules": rules_body,
    }


def action_body(version):
    """版本及证据都由明确用户动作提交。"""
    return {
        "client_request_id": str(uuid4()),
        "version": version,
        "reason": "合成工程验收",
        "evidence_refs": ["synthetic:case-evidence"],
    }


async def action(client, headers, case, verb, version, *, expected=200):
    """所有状态经真实HTTP事务并回读。"""
    response = await client.post(
        f"{ROOT}/professional-reviews/{case}/{verb}", headers=headers, json=action_body(version)
    )
    assert response.status_code == expected, response.text
    return response.json()


async def test_review_return_resubmit_concurrency_and_grant_revocation(health_http):  # noqa: F811
    """完整状态流、同版本仅一批准、撤回授权后恢复不能复活旧批准。"""
    client, users = health_http
    owner, reviewer, admin = [u["headers"] for u in users]
    current = await setup_quality(client, users)
    assert current["check"]["safety_check"]["status"] == "passed"
    assert current["check"]["nutrition"]["totals"] == {
        "energy_kcal": "300.00",
        "protein_g": "30.00",
        "fat_g": "6.00",
        "carbohydrate_g": "60.00",
        "sodium_mg": "150.00",
    }
    case = current["case"]["review_id"]
    assert (await action(client, owner, case, "submit", 1))["status"] == "pending_review"
    assert (await action(client, owner, case, "approve", 2, expected=403))["code"] == "self_review_forbidden"
    assert (await action(client, admin, case, "approve", 2, expected=404))["code"] == "not_found"
    granted = await client.put(
        f"{ROOT}/members/{current['member']}/grants",
        headers=owner,
        json={"actor_uid": users[2]["uid"], "scopes": ["profile_edit", "profile_view", "professional_review"]},
    )
    assert granted.status_code == 200
    assert (await action(client, admin, case, "approve", 2, expected=403))["code"] == "reviewer_not_qualified"
    self_qualification = await client.post(
        f"{ROOT}/professional-reviewers",
        headers=admin,
        json={**proof(), "status": "qualified", "reviewer_uid": users[2]["uid"]},
    )
    assert self_qualification.status_code == 403, self_qualification.text
    assert (await action(client, reviewer, case, "return", 2))["status"] == "returned"
    assert (await action(client, owner, case, "submit", 3))["version"] == 4
    bodies = [action_body(4), action_body(4)]
    results = await asyncio.gather(
        *[client.post(f"{ROOT}/professional-reviews/{case}/approve", headers=reviewer, json=b) for b in bodies]
    )
    assert sorted(r.status_code for r in results) == [200, 409], [r.text for r in results]
    winner = next(body for body, result in zip(bodies, results) if result.status_code == 200)
    replay = await client.post(f"{ROOT}/professional-reviews/{case}/approve", headers=reviewer, json=winner)
    assert replay.status_code == 200 and replay.json()["status"] == "approved"
    changed = await client.post(
        f"{ROOT}/professional-reviews/{case}/approve", headers=reviewer, json={**winner, "reason": "同键改变理由"}
    )
    assert changed.status_code == 409 and changed.json()["code"] == "request_conflict"
    gate = f"{ROOT}/meal-plans/{current['plan']}/approval-state?version=1"
    assert (await client.get(gate, headers=owner)).json()["available"] is True
    for scopes in [[], ["profile_view", "professional_review"]]:
        response = await client.put(
            f"{ROOT}/members/{current['member']}/grants",
            headers=owner,
            json={"actor_uid": users[1]["uid"], "scopes": scopes},
        )
        assert response.status_code == 200, response.text
    assert (await client.get(gate, headers=owner)).json()["available"] is False
    async with pg_manager.get_async_session_context() as session:
        row = await session.get(HealthProfessionalReview, case)
        assert row.status == "invalidated" and row.invalidation_reason == "reviewer_grant_revoked"
        actions = list(
            (
                await session.scalars(
                    select(HealthReviewAction)
                    .where(HealthReviewAction.review_id == case)
                    .order_by(HealthReviewAction.version)
                )
            ).all()
        )
        assert [a.status for a in actions] == ["pending_review", "returned", "pending_review", "approved"]
        assert actions[-1].reviewer_attestation["reviewer_uid"] == users[1]["uid"]


@pytest.mark.parametrize(
    "source",
    [
        "profile_version",
        "rules_version",
        "credential_version",
        "credential_revoked",
        "profile_revoked",
        "rules_revoked",
        "plan_swap",
    ],
)
async def test_approved_case_cannot_survive_changed_or_revoked_dependencies(health_http, source):  # noqa: F811
    """每个真实写入入口都永久使旧批准失效，原批准证据仍可追溯。"""
    client, users = health_http
    owner, reviewer, admin = [u["headers"] for u in users]
    current = await setup_quality(client, users)
    case_id = current["case"]["review_id"]
    await action(client, owner, case_id, "submit", 1)
    await action(client, reviewer, case_id, "approve", 2)
    version = 1
    if source == "profile_version":
        response = await client.post(
            f"{ROOT}/members/{current['member']}/external-profile-versions",
            headers=admin,
            json={**current["profile"], "version": 2, "source_version": "v2"},
        )
    elif source == "rules_version":
        response = await client.post(
            f"{ROOT}/approved-quality-rules",
            headers=admin,
            json={**current["rules"], "version": 2, "source_version": "v2"},
        )
    elif source == "credential_version":
        response = await client.post(
            f"{ROOT}/professional-reviewers",
            headers=admin,
            json={**proof(2), "status": "qualified", "reviewer_uid": users[1]["uid"]},
        )
    elif source == "credential_revoked":
        response = await client.post(
            f"{ROOT}/professional-reviewers/{users[1]['uid']}/versions/1/revoke", headers=admin
        )
    elif source == "profile_revoked":
        response = await client.post(
            f"{ROOT}/members/{current['member']}/external-profile-versions/1/revoke", headers=admin
        )
    elif source == "rules_revoked":
        response = await client.post(
            f"{ROOT}/approved-quality-rules/{current['rules']['rule_code']}/versions/1/revoke", headers=admin
        )
    else:
        key = str(uuid4())
        response = await client.post(
            f"{ROOT}/meal-plans/{current['plan']}/swap",
            headers={**owner, "Idempotency-Key": key, "If-Match": '"1"'},
            json={
                "client_request_id": key,
                "version": 1,
                "meal_type": "breakfast",
                "dish_index": 0,
                "replacement": {
                    "recipe_version_id": next(iter(current["check"]["sources"]["recipes"])),
                    "grams": "200",
                },
                "reason": "合成版本失效",
            },
        )
        version = 2
    assert response.status_code in {200, 201}, response.text
    gate = await client.get(f"{ROOT}/meal-plans/{current['plan']}/approval-state?version={version}", headers=owner)
    assert gate.status_code == 200 and gate.json()["available"] is False, gate.text
    case = await client.get(f"{ROOT}/professional-reviews/{case_id}", headers=owner)
    assert case.status_code == 200 and case.json()["status"] == "invalidated", case.text
    async with pg_manager.get_async_session_context() as session:
        row = await session.get(HealthProfessionalReview, case_id)
        assert row.status == "invalidated" and row.version == 4
        actions = list(
            (
                await session.scalars(
                    select(HealthReviewAction)
                    .where(HealthReviewAction.review_id == case_id)
                    .order_by(HealthReviewAction.version)
                )
            ).all()
        )
        assert [a.status for a in actions] == ["pending_review", "approved"]
        assert actions[-1].reviewer_attestation["version"] == 1


@pytest.mark.parametrize("source", ["profile", "rules", "credential"])
async def test_approved_case_expires_with_external_dependency_clock(health_http, source):  # noqa: F811
    """真实有效期先允许批准，随后同版本自然过期使采用门禁失效。"""
    client, users = health_http
    owner, reviewer, admin = [u["headers"] for u in users]
    current = await setup_quality(client, users)
    expires = datetime.now(UTC) + timedelta(seconds=5)
    stamp = {**proof(2), "valid_until": expires.isoformat()}
    if source == "profile":
        response = await client.post(
            f"{ROOT}/members/{current['member']}/external-profile-versions",
            headers=admin,
            json={**current["profile"], **stamp},
        )
    elif source == "rules":
        response = await client.post(
            f"{ROOT}/approved-quality-rules", headers=admin, json={**current["rules"], **stamp}
        )
    else:
        response = await client.post(
            f"{ROOT}/professional-reviewers",
            headers=admin,
            json={**stamp, "status": "qualified", "reviewer_uid": users[1]["uid"]},
        )
    assert response.status_code == 201, response.text
    checked = await client.post(
        f"{ROOT}/meal-plans/{current['plan']}/quality-checks",
        headers=owner,
        json={**current["body"], "client_request_id": str(uuid4())},
    )
    assert checked.status_code == 201, checked.text
    read = await client.get(f"{ROOT}/quality-checks/{checked.json()['check_id']}", headers=owner)
    assert read.status_code == 200, read.text
    case_id = read.json()["review"]["review_id"]
    await action(client, owner, case_id, "submit", 1)
    await action(client, reviewer, case_id, "approve", 2)
    gate = f"{ROOT}/meal-plans/{current['plan']}/approval-state?version=1"
    available = await client.get(gate, headers=owner)
    assert available.status_code == 200 and available.json()["available"] is True, available.text
    remaining = (expires - datetime.now(UTC)).total_seconds()
    assert remaining > 0, "批准正例必须处于真实有效期，避免用已过期失败冒充负控"
    await asyncio.sleep(remaining + 0.05)
    expired = await client.get(gate, headers=owner)
    assert expired.status_code == 200 and expired.json()["available"] is False, expired.text
    async with pg_manager.get_async_session_context() as session:
        row = await session.get(HealthProfessionalReview, case_id)
        assert row.status == "invalidated" and row.version == 4


@pytest.mark.parametrize("source", ["profile", "rules", "credential"])
async def test_revoking_historical_version_keeps_current_version_approval(health_http, source):  # noqa: F811
    """历史v1撤回不波及已依据当前v2重新检查的专业批准。"""
    client, users = health_http
    owner, reviewer, admin = [u["headers"] for u in users]
    current = await setup_quality(client, users)
    if source == "profile":
        response = await client.post(
            f"{ROOT}/members/{current['member']}/external-profile-versions",
            headers=admin,
            json={**current["profile"], "version": 2, "source_version": "v2"},
        )
        revoke = f"{ROOT}/members/{current['member']}/external-profile-versions/1/revoke"
    elif source == "rules":
        response = await client.post(
            f"{ROOT}/approved-quality-rules",
            headers=admin,
            json={**current["rules"], "version": 2, "source_version": "v2"},
        )
        revoke = f"{ROOT}/approved-quality-rules/{current['rules']['rule_code']}/versions/1/revoke"
    else:
        response = await client.post(
            f"{ROOT}/professional-reviewers",
            headers=admin,
            json={**proof(2), "status": "qualified", "reviewer_uid": users[1]["uid"]},
        )
        revoke = f"{ROOT}/professional-reviewers/{users[1]['uid']}/versions/1/revoke"
    assert response.status_code == 201, response.text
    checked = await client.post(
        f"{ROOT}/meal-plans/{current['plan']}/quality-checks",
        headers=owner,
        json={**current["body"], "client_request_id": str(uuid4())},
    )
    assert checked.status_code == 201, checked.text
    read = await client.get(f"{ROOT}/quality-checks/{checked.json()['check_id']}", headers=owner)
    assert read.status_code == 200, read.text
    case_id = read.json()["review"]["review_id"]
    await action(client, owner, case_id, "submit", 1)
    await action(client, reviewer, case_id, "approve", 2)
    response = await client.post(revoke, headers=admin)
    assert response.status_code == 200 and response.json()["revoked"] is True, response.text
    gate = await client.get(f"{ROOT}/meal-plans/{current['plan']}/approval-state?version=1", headers=owner)
    assert gate.status_code == 200 and gate.json()["available"] is True, gate.text
    async with pg_manager.get_async_session_context() as session:
        row = await session.get(HealthProfessionalReview, case_id)
        assert row.status == "approved" and row.version == 3
        if source == "credential":
            assert row.reviewer_version == 2
        else:
            from yuxi.storage.postgres.models_health import HealthQualityCheck

            check = await session.get(HealthQualityCheck, row.check_id)
            version = (
                check.snapshot["sources"]["profiles"][current["member"]]["version"]
                if source == "profile"
                else check.snapshot["sources"]["rules"]["version"]
            )
            assert version == 2


@pytest.mark.parametrize("field", ["unknown", "conflict"])
async def test_unknown_or_conflict_never_gets_professional_approval(health_http, field):  # noqa: F811
    """提交可等待补资料，但未知或冲突的检查不能批准。"""
    client, users = health_http
    current = await setup_quality(client, users, field=field)
    assert current["check"]["safety_check"]["status"] == field
    case = current["case"]["review_id"]
    await action(client, users[0]["headers"], case, "submit", 1)
    error = await action(client, users[1]["headers"], case, "approve", 2, expected=409)
    assert error["code"] == "quality_not_passed"
    async with pg_manager.get_async_session_context() as session:
        row = await session.get(HealthProfessionalReview, case)
        assert row.status == "pending_review" and row.version == 2


async def test_external_versions_and_private_check_access(health_http):  # noqa: F811
    """同版本不可改、撤回不回退，非管理员及他人不能导入或读取成员资料。"""
    client, users = health_http
    owner, reviewer, admin = [u["headers"] for u in users]
    current = await setup_quality(client, users)
    endpoint = f"{ROOT}/members/{current['member']}/external-profile-versions"
    assert (await client.post(endpoint, headers=owner, json=current["profile"])).status_code == 403
    changed = deepcopy(current["profile"])
    changed["payload"]["age_years"] += 1
    assert (await client.post(endpoint, headers=admin, json=changed)).status_code == 409
    assert (
        await client.get(f"{ROOT}/quality-checks/{current['check']['check_id']}", headers=reviewer)
    ).status_code == 404
    assert (await client.post(f"{endpoint}/1/revoke", headers=admin)).status_code == 200
    replay = await client.post(endpoint, headers=admin, json=current["profile"])
    assert replay.status_code == 201 and replay.json()["status"] == "not_ready"
    assert replay.json()["reason"] == "revoked"
    check = await client.get(f"{ROOT}/quality-checks/{current['check']['check_id']}", headers=owner)
    assert check.status_code == 200 and check.json()["current"] is False
    assert check.json()["review"]["status"] == "invalidated"


async def test_review_refreshes_state_after_waiting_for_member_lock(health_http, monkeypatch):  # noqa: F811
    """真实成员锁等待窗口内状态和授权变化，旧pending预读不能返回approved。"""
    from yuxi.repositories.health_quality_repository import HealthQualityRepository
    from yuxi.services.health_quality_service import read_professional_review
    from yuxi.storage.postgres.models_health import FamilyMember, HealthGrant

    client, users = health_http
    current = await setup_quality(client, users)
    case_id = current["case"]["review_id"]
    await action(client, users[0]["headers"], case_id, "submit", 1)
    reached_lock = asyncio.Event()
    original = HealthQualityRepository.plan

    async def signal_plan(self, uid, plan_id, **kwargs):
        reached_lock.set()
        return await original(self, uid, plan_id, **kwargs)

    monkeypatch.setattr(HealthQualityRepository, "plan", signal_plan)
    reader = None
    try:
        async with pg_manager.get_async_session_context() as session:
            await session.scalar(select(FamilyMember).where(FamilyMember.id == current["member"]).with_for_update())
            reader = asyncio.create_task(read_professional_review(users[0]["uid"], case_id))
            await asyncio.wait_for(reached_lock.wait(), 10)
            assert not reader.done()
            # 显式重建旧状态窗口；另一个PG事务的批准及授权变化先于读事务取得成员锁。
            case = await session.get(HealthProfessionalReview, case_id)
            case.status, case.version = "approved", 3
            case.reviewer_uid, case.reviewer_version = users[1]["uid"], 1
            (await session.get(HealthGrant, (current["member"], users[1]["uid"]))).scopes = []
        result = await asyncio.wait_for(reader, 15)
        assert result["status"] == "invalidated" and result["invalidation_reason"] == "reviewer_unavailable"
        async with pg_manager.get_async_session_context() as session:
            assert (await session.get(HealthProfessionalReview, case_id)).status == "invalidated"
    finally:
        if reader is not None and not reader.done():
            reader.cancel()
            await asyncio.gather(reader, return_exceptions=True)


async def test_pg_history_receipts_keep_original_run_and_final_requires_current_run(health_http):  # noqa: F811
    """PG边界核对同会话旧收据；HTTP收据和跨会话收据不能冒充本轮。"""
    from yuxi.repositories.health_quality_repository import HealthQualityRepository
    from yuxi.services.health_quality_service import (
        check_plan_in_session,
        quality_result,
        validate_quality_tool_payload,
        quality_answer_in_session,
    )
    from yuxi.services.health_quality_types import QualityCheckInput, QualityAnswer
    from yuxi.services.health_vision_types import HealthVisionError
    from yuxi.storage.postgres.models_business import AgentRun, Conversation
    from yuxi.storage.postgres.models_health import HealthConsultation

    client, users = health_http
    current = await setup_quality(client, users)
    threads = []
    for _ in range(2):
        response = await client.post(
            f"{ROOT}/meal-plans/{current['plan']}/quality-conversation",
            headers=users[0]["headers"],
            json={**current["body"], "client_request_id": str(uuid4())},
        )
        assert response.status_code == 201, response.text
        threads.append(response.json()["thread_id"])
    async with pg_manager.get_async_session_context() as session:
        conversation = await session.scalar(select(Conversation).where(Conversation.thread_id == threads[0]))
        binding = await session.get(HealthConsultation, conversation.id)
        runs = [
            AgentRun(
                id=str(uuid4()),
                request_id=str(uuid4()),
                uid=users[0]["uid"],
                agent_slug="health-quality",
                conversation_id=conversation.id,
                conversation_thread_id=threads[0],
                runtime_scope_id=threads[0],
                status="failed",
            )
            for _ in range(2)
        ]
        session.add_all(runs)
        await session.flush()
        selected = await HealthQualityRepository(session).selected(binding)
        check = await check_plan_in_session(
            session,
            users[0]["uid"],
            current["plan"],
            QualityCheckInput(**{**current["body"], "client_request_id": str(uuid4())}),
            run_id=runs[0].id,
        )
        payload = quality_result(check)
        await validate_quality_tool_payload(
            session, users[0]["uid"], binding, runs[1], "check_selected_plan_quality", payload, allow_history=True
        )
        with pytest.raises(HealthVisionError, match="quality_receipt_invalid"):
            await quality_answer_in_session(
                session, users[0]["uid"], runs[1], binding, selected, QualityAnswer(check_id=check.id)
            )
        with pytest.raises(HealthVisionError, match="source_invalidated"):
            await validate_quality_tool_payload(
                session,
                users[0]["uid"],
                binding,
                runs[1],
                "check_selected_plan_quality",
                current["check"],
                allow_history=True,
            )
        foreign = await session.scalar(select(Conversation).where(Conversation.thread_id == threads[1]))
        runs[0].conversation_id = foreign.id
        await session.flush()
        with pytest.raises(HealthVisionError, match="source_invalidated"):
            await validate_quality_tool_payload(
                session, users[0]["uid"], binding, runs[1], "check_selected_plan_quality", payload, allow_history=True
            )

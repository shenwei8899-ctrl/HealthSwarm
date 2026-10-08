"""真实HTTP/PG验证家庭参与调整、共同采用失效及历史授权。"""

import asyncio
from copy import deepcopy
from datetime import UTC, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select, func, text

from test.integration.services.test_health_family_meal_plan_http import setup_family
from test.integration.services.test_health_family_plan_adoption_http import approve_family, selection as adopt_selection
from test.integration.services.test_health_family_safe_plan_http import assert_original
from test.integration.services.test_health_vision_http import ROOT, create_member, health_http  # noqa: F401
from test.unit.services.test_health_family_participation import participation_body
from yuxi.services.health_family_meal_plan_types import FamilyParticipationInput
from yuxi.services.health_quality_checks import external_projection, projection_digest
from yuxi.services.health_vision_types import HEALTH_SCOPES, HealthVisionError
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_health import (
    FamilyMember,
    HealthMealPlan,
    HealthMealPlanRevision,
    HealthMealPlanAdoption,
    HealthProfileSnapshot,
    HealthProfessionalReview,
    HealthQualityCheck,
)
from yuxi.utils.datetime_utils import utc_now_naive

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def add_member(client, users, current, *, deliver=True):
    """新成员的明确授权与合成确认档案由真实HTTP写入。"""
    member = await create_member(client, users[0]["headers"])
    response = await client.put(
        f"{ROOT}/members/{member}/grants",
        headers=users[0]["headers"],
        json={"actor_uid": users[2]["uid"], "scopes": ["profile_edit"]},
    )
    assert response.status_code == 200, response.text
    body = {**deepcopy(current["profile"]), "version": 1, "source_version": "participation-v1"}
    if deliver:
        response = await client.post(
            f"{ROOT}/members/{member}/external-profile-versions", headers=users[2]["headers"], json=body
        )
        assert response.status_code == 201, response.text
    return member, body


def selection(current, third, *, remove_second=False):
    """A300、B晚餐150及新增C午餐90来自明确输入。"""
    profiles = {current["member"]: 2, third: 1}
    if not remove_second:
        profiles[current["second"]] = 1
    body = participation_body(deepcopy(current["spec"]), profiles)
    body.update(rule_code=current["rules"]["rule_code"], rule_version=current["rules"]["version"])
    members = [[current["member"]], [current["member"], third], [current["member"]]]
    amounts = [[50], [100, 90], [150]]
    if not remove_second:
        members[2].append(current["second"])
        amounts[2].append(150)
    for meal, mids, grams in zip(body["allocations"], members, amounts):
        meal["participant_ids"] = mids
        meal["dishes"][0]["member_portions"] = [
            {"member_id": mid, "grams": str(value)} for mid, value in zip(mids, grams)
        ]
    return body


async def preview(client, owner, current, body):
    """通过实际薄路由执行只读试算。"""
    return await client.post(
        f"{ROOT}/meal-plans/{current['plan']}/family-participation-preview", headers=owner, json=body
    )


async def change(client, owner, current, body):
    """真实请求头与正文选择一致，允许幂等重放。"""
    return await client.post(
        f"{ROOT}/meal-plans/{current['plan']}/family-participation",
        headers={**owner, "Idempotency-Key": body["client_request_id"], "If-Match": f'"{body["version"]}"'},
        json=body,
    )


def confirm(body, result):
    """用户选择当前摘要并填写改版原因。"""
    return {
        **body,
        "client_request_id": str(uuid4()),
        "preview_hash": result["preview_hash"],
        "reason": "调整参加餐次与份量",
    }


async def test_adjustment_adds_moves_and_removes_members_invalidates_shared_use_and_checks_history(health_http):  # noqa: F811
    """540个人营养独立对照；旧使用整体失效，移出后历史仍核对授权。"""
    client, users = health_http
    current = await setup_family(client, users)
    owner = users[0]["headers"]
    third, _ = await add_member(client, users, current)
    await approve_family(client, users, current)
    response = await client.post(
        f"{ROOT}/meal-plans/{current['plan']}/adopt", headers=owner, json=adopt_selection(current)
    )
    assert response.status_code == 201, response.text
    old = response.json()
    body = selection(current, third)
    response = await preview(client, owner, current, body)
    assert response.status_code == 200 and response.json()["status"] == "ready", response.text
    trial = response.json()
    assert [
        trial["plan_snapshot"]["members"][mid]["nutrition"]["totals"]["energy_kcal"]
        for mid in (current["member"], current["second"], third)
    ] == ["300.00", "150.00", "90.00"]
    assert trial["plan_snapshot"]["nutrition"]["totals"]["energy_kcal"] == "540.00"
    assert trial["plan_snapshot"]["members"][current["second"]]["covered_meals"] == ["dinner"]
    assert trial["plan_snapshot"]["members"][third]["covered_meals"] == ["lunch"]
    await assert_original(current)
    first_input = confirm(body, trial)
    response = await change(client, owner, current, first_input)
    assert response.status_code == 200, response.text
    first = response.json()
    assert first["version"] == first["applied_version"] == 2 and first["quality_check"]["current"] is True
    assert first["quality_check"]["safety_check"]["status"] == "passed"
    assert (await change(client, owner, current, first_input)).json() == first
    changed_key = await change(client, owner, current, {**first_input, "reason": "不同改版原因"})
    assert changed_key.status_code == 409 and changed_key.json()["code"] == "request_conflict"
    async with pg_manager.get_async_session_context() as session:
        plan = await session.get(HealthMealPlan, current["plan"])
        assert plan.spec["plan_date"] == current["spec"]["plan_date"]
        assert [d["recipe_version_id"] for m in plan.spec["meals"] for d in m["dishes"]] == [current["recipe"]] * 3
        adopted = await session.get(HealthMealPlanAdoption, old["adoption_id"])
        assert adopted.status == "invalidated" and adopted.version == 2 and adopted.snapshot == old["snapshot"]
        assert (await session.get(HealthProfessionalReview, current["case"])).status == "invalidated"
        new_case = await session.scalar(
            select(HealthProfessionalReview).where(
                HealthProfessionalReview.check_id == first["quality_check"]["check_id"]
            )
        )
        assert new_case.status == "draft"
        first_case_id = new_case.id
        revised_spec = deepcopy(plan.spec)
    for mid in (current["member"], current["second"]):
        response = await client.get(f"{ROOT}/members/{mid}/adopted-plan?plan_date=2026-10-07", headers=owner)
        assert response.status_code == 200 and response.json()["plan"] is None
    for meal in revised_spec["meals"]:
        meal["participant_ids"] = [mid for mid in meal["participant_ids"] if mid != third]
        for dish in meal["dishes"]:
            dish["member_portions"] = [p for p in dish["member_portions"] if p["member_id"] != third]
    second_body = participation_body(revised_spec, {current["member"]: 2, current["second"]: 1})
    second_body.update(version=2, rule_code=body["rule_code"], rule_version=body["rule_version"])
    response = await preview(client, owner, current, second_body)
    assert response.status_code == 200 and response.json()["status"] == "ready", response.text
    second_input = confirm(second_body, response.json())
    response = await change(client, owner, current, second_input)
    assert response.status_code == 200 and response.json()["version"] == 3, response.text
    assert third not in response.json()["members"]
    replay = await change(client, owner, current, first_input)
    assert (
        replay.status_code == 200
        and replay.json()["applied_version"] == 2
        and replay.json()["quality_check"]["current"] is False
    )
    response = await client.put(
        f"{ROOT}/members/{third}/grants", headers=owner, json={"actor_uid": users[0]["uid"], "scopes": ["profile_edit"]}
    )
    assert response.status_code == 200, response.text
    assert (await change(client, owner, current, first_input)).status_code == 404
    assert (await client.get(f"{ROOT}/meal-plans/{current['plan']}", headers=owner)).status_code == 404
    assert (
        await client.get(f"{ROOT}/quality-checks/{first['quality_check']['check_id']}", headers=owner)
    ).status_code == 404
    assert (await client.get(f"{ROOT}/professional-reviews/{first_case_id}", headers=owner)).status_code == 404
    assert (await change(client, owner, current, second_input)).status_code == 200
    async with pg_manager.get_async_session_context() as session:
        revisions = (
            await session.scalars(
                select(HealthMealPlanRevision)
                .where(HealthMealPlanRevision.plan_id == current["plan"])
                .order_by(HealthMealPlanRevision.version)
            )
        ).all()
        assert [r.version for r in revisions] == [1, 2, 3]
        assert revisions[0].snapshot["members"] == current["snapshot"]["members"]
        assert third in revisions[1].snapshot["members"] and third not in revisions[2].snapshot["members"]


@pytest.mark.parametrize("fault", ["missing_profile", "missing_shares", "unknown_portion", "target_conflict"])
async def test_new_member_unknown_or_conflict_cannot_write(health_http, fault):  # noqa: F811
    """缺来源或新增个人目标冲突不能以家庭总量掩盖。"""
    client, users = health_http
    current = await setup_family(client, users, shares=fault != "missing_shares")
    third, _ = await add_member(client, users, current, deliver=fault != "missing_profile")
    owner = users[0]["headers"]
    body = selection(current, third)
    if fault in ("unknown_portion", "target_conflict"):
        body["allocations"][1]["dishes"][0]["member_portions"][1]["grams"] = (
            None if fault == "unknown_portion" else "120"
        )
    response = await preview(client, owner, current, body)
    assert response.status_code == 200 and response.json()["status"] == "not_ready", response.text
    trial = response.json()
    assert trial["preview_hash"] is None and trial["safety_check"]["status"] != "passed"
    if fault == "target_conflict":
        assert any(c["member_id"] == third for c in trial["safety_check"]["conflicts"])
    response = await change(
        client,
        owner,
        current,
        {**body, "client_request_id": str(uuid4()), "preview_hash": "0" * 64, "reason": "缺依赖不能保存"},
    )
    assert response.status_code == 409 and response.json()["code"] == "participation_not_safe"
    await assert_original(current)


async def test_current_selection_headers_and_changed_preview_sources_are_required(health_http):  # noqa: F811
    """少报/错版、摘要变更与缺请求头均拒绝；新确认可继续。"""
    client, users = health_http
    current = await setup_family(client, users)
    third, third_profile = await add_member(client, users, current)
    owner = users[0]["headers"]
    body = selection(current, third)
    for profiles in [
        {current["member"]: 2},
        {**body["profile_versions"], third: 2},
        {**body["profile_versions"], str(uuid4()): 1},
    ]:
        response = await preview(client, owner, current, {**body, "profile_versions": profiles})
        assert response.status_code == 409 and response.json()["code"] == "source_version_conflict", response.text
    response = await preview(client, owner, current, {**body, "rule_version": 1})
    assert response.status_code == 409 and response.json()["code"] == "source_version_conflict"
    response = await preview(client, owner, current, body)
    assert response.status_code == 200 and response.json()["status"] == "ready", response.text
    initial = confirm(body, response.json())
    endpoint = f"{ROOT}/meal-plans/{current['plan']}/family-participation"
    response = await client.post(endpoint, headers=owner, json=initial)
    assert response.status_code == 422 and response.json()["code"] == "request_key_mismatch"
    response = await client.post(
        endpoint, headers={**owner, "Idempotency-Key": initial["client_request_id"]}, json=initial
    )
    assert response.status_code == 409 and response.json()["code"] == "version_conflict"
    changed = deepcopy(initial)
    changed["allocations"][0]["dishes"][0]["member_portions"][0]["grams"] = "60"
    changed["allocations"][1]["dishes"][0]["member_portions"][0]["grams"] = "90"
    response = await change(client, owner, current, changed)
    assert response.status_code == 409 and response.json()["code"] == "preview_changed"
    updated = {**third_profile, "version": 2, "source_version": "participation-v2"}
    response = await client.post(
        f"{ROOT}/members/{third}/external-profile-versions", headers=users[2]["headers"], json=updated
    )
    assert response.status_code == 201, response.text
    response = await change(client, owner, current, initial)
    assert response.status_code == 409 and response.json()["code"] == "source_version_conflict"
    corrected = deepcopy(initial)
    corrected["profile_versions"][third] = 2
    response = await change(client, owner, current, corrected)
    assert response.status_code == 409 and response.json()["code"] == "preview_changed"
    await assert_original(current)
    fresh = {k: v for k, v in corrected.items() if k not in ("client_request_id", "preview_hash", "reason")}
    response = await preview(client, owner, current, fresh)
    assert response.status_code == 200 and response.json()["status"] == "ready", response.text
    response = await change(client, owner, current, confirm(fresh, response.json()))
    assert response.status_code == 200 and response.json()["version"] == 2, response.text


async def test_old_removed_and_new_members_require_each_scope_and_account_ownership(health_http):  # noqa: F811
    """移出旧成员与新增成员都核对diet_edit/profile_view，无管理员读取旁路。"""
    client, users = health_http
    current = await setup_family(client, users)
    third, _ = await add_member(client, users, current)
    owner = users[0]["headers"]
    body = selection(current, third, remove_second=True)
    for mid in (third, current["second"]):
        for missing in ("diet_edit", "profile_view"):
            response = await client.put(
                f"{ROOT}/members/{mid}/grants",
                headers=owner,
                json={"actor_uid": users[0]["uid"], "scopes": sorted(HEALTH_SCOPES - {missing})},
            )
            assert response.status_code == 200, response.text
            response = await preview(client, owner, current, body)
            assert response.status_code == 404 and response.json()["code"] == "not_found", response.text
            response = await client.put(
                f"{ROOT}/members/{mid}/grants",
                headers=owner,
                json={"actor_uid": users[0]["uid"], "scopes": sorted(HEALTH_SCOPES)},
            )
            assert response.status_code == 200, response.text
    for other in users[1:]:
        assert (await preview(client, other["headers"], current, body)).status_code == 404
    response = await preview(client, owner, current, {**body, "version": 2})
    assert response.status_code == 409 and response.json()["code"] == "version_conflict"
    async with pg_manager.get_async_session_context() as session:
        single = await session.scalar(
            select(HealthMealPlan).where(
                HealthMealPlan.actor_uid == users[0]["uid"], HealthMealPlan.id != current["plan"]
            )
        )
        single_id = single.id
    response = await preview(client, owner, {"plan": single_id}, body)
    assert response.status_code == 409 and response.json()["code"] == "family_plan_required"
    noop = participation_body(deepcopy(current["spec"]), {current["member"]: 2, current["second"]: 1})
    noop.update(rule_code=body["rule_code"], rule_version=body["rule_version"])
    response = await preview(client, owner, current, noop)
    assert response.status_code == 409 and response.json()["code"] == "participation_unchanged"
    await assert_original(current)


@pytest.mark.parametrize("swap", [False, True])
async def test_old_family_safe_replay_and_professional_history_do_not_bypass_removed_member(health_http, swap):  # noqa: F811
    """旧家庭换菜/重生成的检查及专业历史同样核对移出成员，不能逆序追加锁。"""
    from test.integration.services.test_health_family_safe_plan_http import (
        setup_safe_family,
        selection as safe_selection,
    )

    client, users = health_http
    current = await setup_safe_family(client, users, energies=(110,))
    owner = users[0]["headers"]
    selected = safe_selection(current, swap=swap)
    suffix = "family-swap-candidates" if swap else "family-regeneration-preview"
    response = await client.post(f"{ROOT}/meal-plans/{current['plan']}/{suffix}", headers=owner, json=selected)
    assert response.status_code == 200 and response.json()["status"] == "ready", response.text
    old_input = {**selected, "client_request_id": str(uuid4())}
    if swap:
        old_input["recipe_version_id"] = response.json()["candidates"][0]["recipe_version_id"]
    else:
        old_input["preview_hash"] = response.json()["preview_hash"]
    suffix = "family-safe-swap" if swap else "family-safe-regenerate"
    headers = {**owner, "Idempotency-Key": old_input["client_request_id"], "If-Match": '"1"'}
    endpoint = f"{ROOT}/meal-plans/{current['plan']}/{suffix}"
    response = await client.post(endpoint, headers=headers, json=old_input)
    assert response.status_code == 200 and response.json()["version"] == 2, response.text
    check_id = response.json()["quality_check"]["check_id"]
    response = await client.get(f"{ROOT}/quality-checks/{check_id}", headers=owner)
    assert response.status_code == 200, response.text
    case_id = response.json()["review"]["review_id"]
    async with pg_manager.get_async_session_context() as session:
        changed_spec = deepcopy((await session.get(HealthMealPlan, current["plan"])).spec)
    for meal in changed_spec["meals"]:
        meal["participant_ids"] = [current["member"]]
        for dish in meal["dishes"]:
            dish["member_portions"] = [p for p in dish["member_portions"] if p["member_id"] == current["member"]]
    body = participation_body(changed_spec, {current["member"]: 2})
    body.update(version=2, rule_code=selected["rule_code"], rule_version=selected["rule_version"])
    response = await preview(client, owner, current, body)
    assert response.status_code == 200 and response.json()["status"] == "ready", response.text
    response = await change(client, owner, current, confirm(body, response.json()))
    assert response.status_code == 200 and response.json()["version"] == 3, response.text
    response = await client.post(endpoint, headers=headers, json=old_input)
    assert (
        response.status_code == 200
        and response.json()["applied_version"] == 2
        and response.json()["quality_check"]["current"] is False
    ), response.text
    for uid, scopes in [(users[0]["uid"], ["profile_edit"]), (users[1]["uid"], ["professional_review"])]:
        response = await client.put(
            f"{ROOT}/members/{current['second']}/grants", headers=owner, json={"actor_uid": uid, "scopes": scopes}
        )
        assert response.status_code == 200, response.text
    assert (await client.post(endpoint, headers=headers, json=old_input)).status_code == 404
    assert (await client.get(f"{ROOT}/quality-checks/{check_id}", headers=owner)).status_code == 404
    assert (await client.get(f"{ROOT}/professional-reviews/{case_id}", headers=owner)).status_code == 404
    assert (await client.get(f"{ROOT}/professional-reviews/{case_id}", headers=users[1]["headers"])).status_code == 404


@pytest.mark.parametrize("same_key", [False, True])
async def test_concurrent_adjustments_only_create_one_revision(health_http, same_key):  # noqa: F811
    """同键重放相同收据，不同键竞争不能叠加两个新版本。"""
    client, users = health_http
    current = await setup_family(client, users)
    third, _ = await add_member(client, users, current)
    owner = users[0]["headers"]
    body = selection(current, third)
    response = await preview(client, owner, current, body)
    assert response.status_code == 200 and response.json()["status"] == "ready", response.text
    first = confirm(body, response.json())
    second = first if same_key else {**first, "client_request_id": str(uuid4())}
    responses = await asyncio.gather(change(client, owner, current, first), change(client, owner, current, second))
    if same_key:
        assert all(r.status_code == 200 for r in responses) and responses[0].json() == responses[1].json()
    else:
        assert sorted(r.status_code for r in responses) in ([200, 409], [200, 410]), [r.text for r in responses]
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


@pytest.mark.parametrize("fault", ["integrity", "expiry"])
async def test_last_real_pg_check_failure_rolls_back_revision_and_shared_invalidation(health_http, monkeypatch, fault):  # noqa: F811
    """实际试算后改变新成员来源，最后检查失败时原审核/采用及档案全部恢复。"""
    from yuxi.services import health_family_participation_service as service

    client, users = health_http
    current = await setup_family(client, users)
    third, _ = await add_member(client, users, current)
    owner = users[0]["headers"]
    await approve_family(client, users, current)
    response = await client.post(
        f"{ROOT}/meal-plans/{current['plan']}/adopt", headers=owner, json=adopt_selection(current)
    )
    assert response.status_code == 201, response.text
    old = response.json()
    body = selection(current, third)
    response = await preview(client, owner, current, body)
    assert response.status_code == 200 and response.json()["status"] == "ready", response.text
    data = FamilyParticipationInput.model_validate(confirm(body, response.json()))
    original = service.participation_preview_in_session

    async def invalidate_after_trial(session, uid, plan_id, input_data):
        """受控故障位于真实预览与末次真实质量检查之间。"""
        result = await original(session, uid, plan_id, input_data)
        profile = await session.get(HealthProfileSnapshot, result[2]["sources"]["profiles"][third]["id"])
        if fault == "integrity":
            profile.content_hash = "0" * 64
        else:
            profile.valid_until = utc_now_naive() - timedelta(seconds=1)
            profile.attestation = {
                **profile.attestation,
                "valid_until": profile.valid_until.replace(tzinfo=UTC).isoformat(),
            }
            profile.content_hash = projection_digest(
                "profile", third, profile.version, profile.payload, profile.attestation
            )
            assert external_projection(profile, "profile", third)["reason"] == "expired"
        await session.flush()
        return result

    monkeypatch.setattr(service, "participation_preview_in_session", invalidate_after_trial)
    with pytest.raises(HealthVisionError) as error:
        await service.change_family_participation(users[0]["uid"], current["plan"], data)
    assert error.value.code == "quality_not_passed"
    await assert_original(current)
    async with pg_manager.get_async_session_context() as session:
        adoption = await session.get(HealthMealPlanAdoption, old["adoption_id"])
        assert adoption.status == "active" and adoption.version == 1 and adoption.snapshot == old["snapshot"]
        case = await session.get(HealthProfessionalReview, current["case"])
        assert case.status == "approved" and case.version == 3
        profile = await session.scalar(select(HealthProfileSnapshot).where(HealthProfileSnapshot.member_id == third))
        assert external_projection(profile, "profile", third)["status"] == "ready"


async def test_union_member_lock_order_is_visible_in_actual_http_pg_wait(health_http):  # noqa: F811
    """排序首成员持锁时，实际调整等待且末成员尚未被占有。"""
    client, users = health_http
    current = await setup_family(client, users)
    third, _ = await add_member(client, users, current)
    owner = users[0]["headers"]
    body = selection(current, third, remove_second=True)
    response = await preview(client, owner, current, body)
    assert response.status_code == 200 and response.json()["status"] == "ready", response.text
    body = confirm(body, response.json())
    small, _, large = sorted([current["member"], current["second"], third])
    task = None
    try:
        async with pg_manager.get_async_session_context() as session:
            await session.scalar(select(FamilyMember).where(FamilyMember.id == small).with_for_update())
            blocker = await session.scalar(select(func.pg_backend_pid()))
            task = asyncio.create_task(change(client, owner, current, body))
            blocked = 0
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
                assert (
                    await observer.scalar(
                        select(FamilyMember).where(FamilyMember.id == large).with_for_update(nowait=True)
                    )
                    is not None
                )
        response = await asyncio.wait_for(task, timeout=20)
        assert blocked == 1 and response.status_code == 200, response.text
    finally:
        if task is not None and not task.done():
            await asyncio.wait_for(task, timeout=20)

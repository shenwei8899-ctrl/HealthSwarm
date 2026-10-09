"""真实 HTTP/PG 证明显式本人实测来源与批准目标、餐单版本联动。"""

import asyncio
import hashlib
import json
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import func, select, text

from test.integration.services.test_health_family_profile_http import (
    ROOT,
    cleanup_test_knowledge_resources,  # noqa: F401
    cleanup_test_sandboxes,  # noqa: F401
    create_health_member,
    ensure_live_api_schema,  # noqa: F401
    family_profile_http,  # noqa: F401
    linked_self,
)
from test.integration.services.test_health_family_safety_http import grant_safety_import, safety_body
from test.integration.services.test_health_meal_planner_http import publish_planner_recipe
from test.integration.services.test_health_quality_http import action, proof
from test.integration.services.test_health_weight_http import add_weight
from test.unit.services.test_health_family_meal_plan import meal_shares
from test.unit.services.test_health_personal_targets import target_formula
from test.unit.services.test_health_quality import rules_payload
from yuxi.repositories.family_repository import FamilyRepository
from yuxi.repositories.health_family_profile_repository import HealthFamilyProfileRepository
from yuxi.repositories.health_quality_repository import HealthQualityRepository
from yuxi.repositories.health_vision_repository import HealthVisionRepository
from yuxi.services.health_nutrition_service import input_fingerprint
from yuxi.storage.postgres.models_business import FamilyArchive, FamilyMeasurement, FamilyMember as SourceMember
from yuxi.storage.postgres.models_health import (
    HealthMealPlan,
    HealthMealPlanAdoption,
    HealthMealPlanRevision,
    HealthProcessingConsent,
    HealthProfessionalReview,
    HealthProfileSnapshot,
    HealthQualityCheck,
    RecipeVersion,
)

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest_asyncio.fixture
async def selected_weight(family_profile_http):  # noqa: F811
    """独立 schema 内只经正式本人入口建立合成体重和专业来源。"""
    client, sessions, identities = family_profile_http
    member, source = await linked_self(client, identities["self"])
    await grant_safety_import(client, identities["self"], member)
    case = SimpleNamespace(
        client=client,
        sessions=sessions,
        identities=identities,
        headers=identities["self"],
        member=member,
        source=source,
        measurement_path=f"/api/family/{source['family_id']}/members/{source['source_member_id']}/measurements",
    )
    case.record = await add_weight(case)
    case.body = selected_profile_body(source, case.record)
    return case


async def test_selected_old_nonlatest_weight_preserves_independent_hash_and_replays(selected_weight):
    """明确选择65日前60kg；更新的90kg不会替代它，也不产生模型同意。"""
    case = selected_weight
    old = await add_weight(case, measured_at=datetime.now(UTC) - timedelta(days=65))
    await add_weight(case, value=90)
    case.record, case.body = old, selected_profile_body(case.source, old)
    imported = await import_selected_profile(case)
    assert imported["status"] == "ready" and imported["payload"]["weight_kg"] == "60"
    expected_facts = {
        "family_id": case.source["family_id"],
        "source_member_id": case.source["source_member_id"],
        "record_id": old["id"],
        "version": 1,
        "kind": "weight",
        "weight_kg": "60.0",  # 测量HTTP模型将JSON数值保存为float，摘要保留Decimal的精确字符串。
        "unit": "kg",
        "measured_at": old["measured_at"],
        "source": "synthetic-weight-scale",
    }
    expected_hash = hashlib.sha256(
        json.dumps(expected_facts, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()
    expected_attestation = {key: value for key, value in expected_facts.items() if key not in {"kind", "weight_kg"}} | {
        "source_hash": expected_hash
    }
    assert imported["attestation"]["weight_measurement_source"] == expected_attestation
    assert "condition" not in expected_attestation and "note" not in expected_attestation
    assert await import_selected_profile(case) == imported
    current = await case.client.get(profile_path(case) + "/current", headers=case.headers)
    assert current.status_code == 200 and current.json() == imported, current.text
    rules = await publish_weight_rules(case)
    target = await target_read(case, rules)
    assert target["status"] == "ready" and Decimal(target["energy_kcal"]) == Decimal("330")
    assert target["inputs"]["weight_kg"] == "60"
    assert target["attestations"]["profile"]["weight_measurement_source"] == expected_attestation
    async with case.sessions() as session:
        rows = list((await session.scalars(select(HealthProfileSnapshot))).all())
        assert len(rows) == 1 and rows[0].attestation["weight_measurement_source"] == expected_attestation
        formal = await session.get(SourceMember, case.source["source_member_id"])
        assert formal.version == formal.confirmed_version == 2 and "weight_kg" not in formal.profile
        assert await session.scalar(select(func.count()).select_from(HealthProcessingConsent)) == 0


@pytest.mark.parametrize("change", ["value", "version", "missing", "wrong_kind", "foreign", "voided", "future"])
async def test_selected_import_rejects_unavailable_or_conflicting_measurements(selected_weight, change):
    """明确坐标、当前版本、值和本人归属分别被反证，失败不写投影。"""
    case = selected_weight
    body = deepcopy(case.body)
    if change == "value":
        body["payload"]["weight_kg"] = "90"
    elif change == "version":
        body["weight_measurement_source"]["version"] = 2
    elif change == "missing":
        body["weight_measurement_source"]["record_id"] = str(uuid4())
    elif change == "wrong_kind":
        response = await case.client.post(
            case.measurement_path,
            headers=case.headers,
            json={
                "id": str(uuid4()),
                "kind": "blood_pressure",
                "values": {"systolic": 120, "diastolic": 80},
                "measured_at": case.record["measured_at"],
                "source": "synthetic-pressure-scale",
            },
        )
        assert response.status_code == 200, response.text
        body["weight_measurement_source"]["record_id"] = response.json()["id"]
    elif change == "foreign":
        _, foreign = await linked_self(case.client, case.identities["other"])
        foreign_case = SimpleNamespace(
            client=case.client,
            headers=case.identities["other"],
            measurement_path=f"/api/family/{foreign['family_id']}/members/{foreign['source_member_id']}/measurements",
        )
        body["weight_measurement_source"]["record_id"] = (await add_weight(foreign_case))["id"]
    elif change == "voided":
        response = await case.client.post(
            case.measurement_path + "/" + case.record["id"] + "/void",
            headers=case.headers,
            json={"expected_version": 1, "reason": "合成测试误录作废"},
        )
        assert response.status_code == 200, response.text
    else:
        async with case.sessions() as session:
            row = await session.get(FamilyMeasurement, case.record["id"])
            row.measured_at = (datetime.now(UTC) + timedelta(days=1)).replace(tzinfo=None)
            await session.commit()
    response = await case.client.post(profile_path(case), headers=case.identities["admin"], json=body)
    assert response.status_code == (409 if change in {"value", "version"} else 404), response.text
    assert response.json()["code"] == (
        "weight_measurement_source_conflict" if change in {"value", "version"} else "not_found"
    )
    async with case.sessions() as session:
        assert await session.scalar(select(func.count()).select_from(HealthProfileSnapshot)) == 0


@pytest.mark.parametrize(
    "change", ["missing_family", "hash", "unit", "value", "bool_version", "string_version", "zero"]
)
async def test_client_cannot_supply_weight_attestation_or_ambiguous_version(selected_weight, change):
    """外部请求只能选严格记录版本，服务端来源正文与摘要不可注入。"""
    case = selected_weight
    body = deepcopy(case.body)
    if change == "missing_family":
        body.pop("family_profile_source")
    elif change in {"hash", "unit", "value"}:
        field = {"hash": "source_hash", "unit": "unit", "value": "weight_kg"}[change]
        body["weight_measurement_source"][field] = "forged"
    else:
        body["weight_measurement_source"]["version"] = {"bool_version": True, "string_version": "1", "zero": 0}[change]
    response = await case.client.post(profile_path(case), headers=case.identities["admin"], json=body)
    assert response.status_code == 422, response.text
    async with case.sessions() as session:
        assert await session.scalar(select(func.count()).select_from(HealthProfileSnapshot)) == 0


async def test_linked_unselected_weight_blocks_all_weight_consumers_but_zero_and_legacy_remain(selected_weight):
    """专业字段60不能替代实测选择；常数公式和未关联外部契约保持可用。"""
    case = selected_weight
    body = deepcopy(case.body)
    body.pop("weight_measurement_source")
    imported = await import_selected_profile(case, body)
    assert imported["status"] == "ready" and imported["payload"]["weight_kg"] == "60"
    rules = await publish_weight_rules(case)
    target = await target_read(case, rules)
    assert target["status"] == "not_ready" and target["reason"] == "selected_weight_measurement_required"
    assert "energy_kcal" not in target and "bounds" not in target
    saved = await save_weight_plan(case, rules)
    assert saved["check"]["safety_check"]["status"] == "unknown"
    assert {"path": "personal_targets", "reason": "selected_weight_measurement_required"} in saved["check"][
        "safety_check"
    ]["missing"]
    for family in (False, True):
        preview = await initial_weight_preview(case, rules, family=family)
        assert preview["status"] == "not_ready" and "plan_spec" not in preview
    constants = await publish_weight_rules(case, weight_coefficient="0", intercept="300")
    constant = await target_read(case, constants)
    assert constant["status"] == "ready" and Decimal(constant["energy_kcal"]) == Decimal("300")
    legacy = await create_health_member(case.client, case.headers)
    await grant_safety_import(case.client, case.headers, legacy)
    legacy_body = safety_body()
    legacy_body["payload"]["weight_kg"] = "60"
    response = await case.client.post(
        f"{ROOT}/members/{legacy}/external-profile-versions", headers=case.identities["admin"], json=legacy_body
    )
    assert response.status_code == 201, response.text
    legacy_result = await target_read(case, rules, member=legacy)
    assert legacy_result["status"] == "ready" and Decimal(legacy_result["energy_kcal"]) == Decimal("330")


@pytest.mark.parametrize("family", [False, True])
async def test_selected_weight_initial_generation_and_quality_share_independent_330_oracle(selected_weight, family):
    """本人60kg目标330；初始单人和家庭按66+99+165生成并正式保存。"""
    case = selected_weight
    imported = await import_selected_profile(case)
    rules = await publish_weight_rules(case)
    generated = await initial_weight_preview(case, rules, family=family)
    assert generated["status"] == "ready" and generated["safety_check"]["status"] == "passed"
    assert generated["plan_snapshot"]["nutrition"]["totals"]["energy_kcal"] == "330.00"
    check = generated["safety_check"]
    if family:
        check = check["members"][case.member]
        assert generated["plan_snapshot"]["members"][case.member]["nutrition"]["totals"]["energy_kcal"] == "330.00"
    assert Decimal(check["personal_targets"]["energy_kcal"]) == Decimal("330")
    key = str(uuid4())
    response = await case.client.post(
        f"{ROOT}/members/{case.member}/initial-meal-plans",
        headers={**case.headers, "Idempotency-Key": key},
        json={"client_request_id": key, "preview_id": generated["preview_id"]},
    )
    assert response.status_code == 201, response.text
    saved = response.json()
    async with case.sessions() as session:
        plan = await session.get(HealthMealPlan, saved["plan_id"])
        assert plan.version == 1 and plan.spec == generated["plan_spec"]
        stored = await session.get(HealthQualityCheck, saved["quality_check"]["check_id"])
        assert stored.snapshot["sources"]["profiles"][case.member]["content_hash"] == imported["content_hash"]
        assert stored.snapshot["safety_check"]["status"] == "passed"
        assert (
            await session.scalar(
                select(func.count())
                .select_from(HealthMealPlanRevision)
                .where(HealthMealPlanRevision.plan_id == plan.id)
            )
            == 1
        )
    if family:
        await mutate_weight(case, case.record, "correct")
        preview_read = await case.client.get(
            f"{ROOT}/initial-meal-plan-previews/{generated['preview_id']}", headers=case.headers
        )
        assert preview_read.status_code == 410, preview_read.text
        check_read = await case.client.get(
            f"{ROOT}/quality-checks/{saved['quality_check']['check_id']}", headers=case.headers
        )
        assert check_read.status_code == 200 and check_read.json()["current"] is False, check_read.text
        assert check_read.json()["review"]["status"] == "invalidated"
        assert check_read.json()["review"]["invalidation_reason"] == "weight_measurement_changed"
        regeneration = await case.client.post(
            f"{ROOT}/meal-plans/{saved['plan_id']}/family-regeneration-preview",
            headers=case.headers,
            json={
                "version": 1,
                "rule_code": rules["rule_code"],
                "rule_version": 1,
                "profile_versions": {case.member: 1},
            },
        )
        assert regeneration.status_code == 200 and regeneration.json()["status"] == "not_ready", regeneration.text
        assert regeneration.json()["sources"]["profiles"][case.member]["status"] == "not_ready"


@pytest.mark.parametrize("mutation", ["correct", "void"])
async def test_selected_change_invalidates_approval_and_adoption_before_reads_then_requires_new_version(
    selected_weight, mutation
):
    """拥有更正事务直接失效旧专业决定；61kg重选后335只能用新版餐单重新批准。"""
    case = selected_weight
    imported = await import_selected_profile(case)
    rules = await publish_weight_rules(case)
    saved = await save_weight_plan(case, rules)
    adopted = await approve_and_adopt(case, saved)
    old_snapshot = deepcopy(saved["check"])
    changed = await mutate_weight(case, case.record, mutation)
    assert changed["version"] == 2
    # 先独立读PG，不通过GET触发失效收敛。
    async with case.sessions() as session:
        review = await session.get(HealthProfessionalReview, saved["review"])
        adoption = await session.get(HealthMealPlanAdoption, adopted["adoption_id"])
        assert review.status == adoption.status == "invalidated"
        assert review.invalidation_reason == adoption.reason == "weight_measurement_changed"
        assert review.version == 4 and adoption.version == 2 and adoption.snapshot == adopted["snapshot"]
        stored_check = await session.get(HealthQualityCheck, saved["check"]["check_id"])
        assert {"check_id": stored_check.id, "result_type": "quality_check", **stored_check.snapshot} == old_snapshot
        profile = await session.get(HealthProfileSnapshot, imported["id"])
        assert profile.payload["weight_kg"] == "60" and profile.attestation == imported["attestation"]
        formal = await session.get(SourceMember, case.source["source_member_id"])
        assert formal.version == formal.confirmed_version == 2
    stale = await case.client.get(profile_path(case) + "/current", headers=case.headers)
    assert stale.status_code == 200 and stale.json()["reason"] == "weight_measurement_source_changed", stale.text
    assert stale.json()["payload"] is stale.json()["attestation"] is None
    target = await target_read(case, rules)
    assert target["status"] == "not_ready" and "energy_kcal" not in target
    historic = await case.client.get(f"{ROOT}/quality-checks/{saved['check']['check_id']}", headers=case.headers)
    assert historic.status_code == 200 and historic.json()["current"] is False, historic.text
    assert historic.json()["review"]["status"] == "invalidated"
    assert historic.json()["review"]["invalidation_reason"] == "weight_measurement_changed"
    assert {key: historic.json()[key] for key in old_snapshot} == old_snapshot
    if mutation == "void":
        replacement = await add_weight(case, value=61)
    else:
        replacement = changed
    fresh = selected_profile_body(case.source, replacement, version=2, weight="61")
    await import_selected_profile(case, fresh)
    target = await target_read(case, rules, profile_version=2)
    assert target["status"] == "ready" and Decimal(target["energy_kcal"]) == Decimal("335")
    conflict = await quality_check(case, saved["plan"], rules)
    assert conflict["safety_check"]["status"] == "conflict"
    assert Decimal(conflict["safety_check"]["personal_targets"]["energy_kcal"]) == Decimal("335")
    key = str(uuid4())
    swapped = await case.client.post(
        f"{ROOT}/meal-plans/{saved['plan']}/swap",
        headers={**case.headers, "Idempotency-Key": key, "If-Match": '"1"'},
        json={
            "client_request_id": key,
            "version": 1,
            "meal_type": "dinner",
            "dish_index": 0,
            "replacement": {"recipe_version_id": saved["recipe"], "grams": "170"},
            "reason": "合成目标335的新餐单版本",
        },
    )
    assert swapped.status_code == 200 and swapped.json()["version"] == 2, swapped.text
    assert swapped.json()["nutrition"]["totals"]["energy_kcal"] == "335.00"
    renewed = await quality_check(case, saved["plan"], rules, plan_version=2)
    assert renewed["safety_check"]["status"] == "passed"
    new_saved = {**saved, "check": renewed, "version": 2, "profile_version": 2}
    new_saved["review"] = await review_for_check(case, renewed)
    active = await approve_and_adopt(case, new_saved)
    assert active["status"] == "active" and active["adoption_id"] != adopted["adoption_id"]
    async with case.sessions() as session:
        revisions = list(
            (
                await session.scalars(
                    select(HealthMealPlanRevision)
                    .where(HealthMealPlanRevision.plan_id == saved["plan"])
                    .order_by(HealthMealPlanRevision.version)
                )
            ).all()
        )
        assert [row.version for row in revisions] == [1, 2]
        assert [row.snapshot["nutrition"]["totals"]["energy_kcal"] for row in revisions] == ["330.00", "335.00"]
        assert (await session.get(HealthProfessionalReview, saved["review"])).status == "invalidated"
        assert (await session.get(HealthMealPlanAdoption, adopted["adoption_id"])).snapshot == adopted["snapshot"]


async def test_noop_unselected_changes_and_rollback_keep_selected_approval(selected_weight, monkeypatch):
    """无更正、无关记录及事务回滚均不能失效明确的60/v1来源。"""
    case = selected_weight
    await import_selected_profile(case)
    rules = await publish_weight_rules(case)
    saved = await save_weight_plan(case, rules)
    adopted = await approve_and_adopt(case, saved)
    for _ in range(2):
        response = await case.client.put(
            case.measurement_path + "/" + case.record["id"],
            headers=case.headers,
            json={"expected_version": 1, "values": {"weight": 60}, "note": case.record["note"]},
        )
        assert response.status_code == 200 and response.json()["version"] == 1, response.text
    other = await add_weight(case, value=70)
    response = await case.client.put(
        case.measurement_path + "/" + other["id"],
        headers=case.headers,
        json={"expected_version": 1, "values": {"weight": 71}, "note": other["note"]},
    )
    assert response.status_code == 200, response.text
    original = HealthQualityRepository.invalidate

    async def fail_after_invalidation(repository, **kwargs):
        """真实更正事务在其依赖已更改后失败，必须整体回滚。"""
        await original(repository, **kwargs)
        if kwargs.get("reason") == "weight_measurement_changed":
            raise RuntimeError("合成实测更正事务失败")

    monkeypatch.setattr(HealthQualityRepository, "invalidate", fail_after_invalidation)
    response = await case.client.put(
        case.measurement_path + "/" + case.record["id"],
        headers=case.headers,
        json={"expected_version": 1, "values": {"weight": 61}, "note": case.record["note"]},
    )
    assert response.status_code == 500, response.text
    async with case.sessions() as session:
        selected = await session.get(FamilyMeasurement, case.record["id"])
        assert selected.version == 1 and selected.values == {"weight": 60} and selected.previous == []
        assert (await session.get(HealthProfessionalReview, saved["review"])).status == "approved"
        adoption = await session.get(HealthMealPlanAdoption, adopted["adoption_id"])
        assert adoption.status == "active" and adoption.version == 1
    target = await target_read(case, rules)
    assert target["status"] == "ready" and Decimal(target["energy_kcal"]) == Decimal("330")


@pytest.mark.parametrize("change", ["raw_value", "future", "source", "actor"])
async def test_projection_rechecks_persisted_measurement_and_identity_without_write_api(selected_weight, change):
    """无版本递增的持久漂移也拒绝旧来源，不把旧专业批准标记当当前事实。"""
    case = selected_weight
    await import_selected_profile(case)
    async with case.sessions() as session:
        row = await session.get(FamilyMeasurement, case.record["id"])
        if change == "raw_value":
            row.values = {"weight": 61}
        elif change == "future":
            row.measured_at = (datetime.now(UTC) + timedelta(days=1)).replace(tzinfo=None)
        elif change == "source":
            row.source = "synthetic-changed-source"
        else:
            formal = await session.get(SourceMember, case.source["source_member_id"])
            formal.subject_uid = "other"
        await session.commit()
    response = await case.client.get(profile_path(case) + "/current", headers=case.headers)
    assert response.status_code == 200 and response.json()["status"] == "not_ready", response.text
    assert response.json()["payload"] is response.json()["attestation"] is None
    assert response.json()["reason"] == (
        "family_profile_source_unavailable" if change == "actor" else "weight_measurement_source_changed"
    )


async def test_selected_source_does_not_replace_unknown_conditions_or_health_access(selected_weight):
    """体重来源有效不补全专业编码，也不授予管理员目标读取权。"""
    case = selected_weight
    body = deepcopy(case.body)
    body["payload"]["conditions"] = {"state": "unknown", "codes": []}
    await import_selected_profile(case, body)
    rules = await publish_weight_rules(case)
    target = await target_read(case, rules)
    assert target["reason"] == "confirmed_conditions_and_requirements_required" and "energy_kcal" not in target
    revoked = await case.client.put(
        f"{ROOT}/members/{case.member}/grants",
        headers=case.headers,
        json={"actor_uid": "admin", "scopes": []},
    )
    assert revoked.status_code == 200, revoked.text
    for headers in (case.identities["other"], case.identities["admin"]):
        response = await case.client.post(
            f"{ROOT}/members/{case.member}/nutrition-targets",
            headers=headers,
            json={"profile_version": 1, "rule_version": 1, "rule_code": rules["rule_code"]},
        )
        assert response.status_code == 404, response.text
    forged = await case.client.post(
        f"{ROOT}/members/{case.member}/nutrition-targets",
        headers=case.headers,
        json={"profile_version": 1, "rule_version": 1, "rule_code": rules["rule_code"], "weight_kg": "61"},
    )
    assert forged.status_code == 422, forged.text


async def test_target_held_family_lock_blocks_selected_weight_correction(selected_weight, monkeypatch):
    """明确60/v1读取持有真实family锁；更正等待后提交，重选版本才可算335。"""
    case = selected_weight
    await import_selected_profile(case)
    rules = await publish_weight_rules(case)
    reached = asyncio.Event()
    writer_pid = None
    original = FamilyRepository.get_family

    async def signal_family(repository, fid, uid, **kwargs):
        """仅观测真实HTTP更正连接，不替代来源锁或查询结果。"""
        nonlocal writer_pid
        if fid == case.source["family_id"]:
            writer_pid = await repository.db.scalar(text("SELECT pg_backend_pid()"))
            reached.set()
        return await original(repository, fid, uid, **kwargs)

    writer = None
    try:
        async with case.sessions() as reader:
            await HealthVisionRepository(reader).authorize(case.member, "self", "profile_view", lock=True)
            weight, selected = await HealthFamilyProfileRepository(reader).weight_source(case.member, case.record["id"])
            assert weight == Decimal("60") and selected["record_id"] == case.record["id"] and selected["version"] == 1
            reader_pid = await reader.scalar(text("SELECT pg_backend_pid()"))
            monkeypatch.setattr(FamilyRepository, "get_family", signal_family)
            writer = asyncio.create_task(
                case.client.put(
                    case.measurement_path + "/" + case.record["id"],
                    headers=case.headers,
                    json={"expected_version": 1, "values": {"weight": 61}, "note": case.record["note"]},
                )
            )
            await asyncio.wait_for(reached.wait(), 10)
            blockers = []
            for _ in range(200):
                blockers = await reader.scalar(text("SELECT pg_blocking_pids(:pid)"), {"pid": writer_pid})
                if reader_pid in blockers:
                    break
                await asyncio.sleep(0.01)
            assert reader_pid in blockers and not writer.done(), "真实HTTP更正未等待目标持有的family行锁"
            await reader.commit()
        response = await asyncio.wait_for(writer, 10)
        assert response.status_code == 200 and response.json()["version"] == 2, response.text
        result = await target_read(case, rules)
        assert result["status"] == "not_ready" and "energy_kcal" not in result
        assert result["sources"]["profile"]["reason"] == "weight_measurement_source_changed"
        async with case.sessions() as session:
            actual = await session.get(FamilyMeasurement, case.record["id"])
            assert actual.version == 2 and actual.values == {"weight": 61}
        await import_selected_profile(case, selected_profile_body(case.source, response.json(), version=2, weight="61"))
        fresh = await target_read(case, rules, profile_version=2)
        assert fresh["status"] == "ready" and Decimal(fresh["energy_kcal"]) == Decimal("335")
    finally:
        if writer is not None and not writer.done():
            writer.cancel()
            await asyncio.gather(writer, return_exceptions=True)


async def test_member_deactivation_invalidates_adoption_and_restore_does_not_revive_it(selected_weight):
    """真实停用事务立即失效专业流程；恢复可读来源不复活旧批准和采用。"""
    case = selected_weight
    await import_selected_profile(case)
    rules = await publish_weight_rules(case)
    saved = await save_weight_plan(case, rules)
    adopted = await approve_and_adopt(case, saved)
    # 仅合成初始夹具设定非本人家庭管理员，不把数据库准备宣称为所有权转移功能。
    async with case.sessions() as session:
        family = await session.get(FamilyArchive, case.source["family_id"])
        family.owner_uid = "other"
        await session.commit()
    before = await target_read(case, rules)
    assert before["status"] == "ready" and Decimal(before["energy_kcal"]) == Decimal("330")
    path = f"/api/family/{case.source['family_id']}/members/{case.source['source_member_id']}/status"
    stopped = await case.client.put(
        path, headers=case.identities["other"], json={"expected_version": 1, "is_active": False}
    )
    assert stopped.status_code == 200 and stopped.json()["relationship_version"] == 2, stopped.text
    # 未执行目标/专业流程GET，直接读取拥有停用事务写出的事实。
    async with case.sessions() as session:
        review = await session.get(HealthProfessionalReview, saved["review"])
        adoption = await session.get(HealthMealPlanAdoption, adopted["adoption_id"])
        assert review.status == adoption.status == "invalidated"
        assert review.invalidation_reason == adoption.reason == "family_profile_source_unavailable"
        assert review.version == 4 and adoption.version == 2 and adoption.snapshot == adopted["snapshot"]
    stopped_target = await target_read(case, rules)
    assert stopped_target["status"] == "not_ready" and "energy_kcal" not in stopped_target
    assert stopped_target["sources"]["profile"]["reason"] == "family_profile_source_unavailable"
    restored = await case.client.put(
        path, headers=case.identities["other"], json={"expected_version": 2, "is_active": True}
    )
    assert restored.status_code == 200 and restored.json()["relationship_version"] == 3, restored.text
    restored_profile = await case.client.get(profile_path(case) + "/current", headers=case.headers)
    assert restored_profile.status_code == 200 and restored_profile.json()["status"] == "ready", restored_profile.text
    restored_target = await target_read(case, rules)
    assert restored_target["status"] == "ready" and Decimal(restored_target["energy_kcal"]) == Decimal("330")
    async with case.sessions() as session:
        review = await session.get(HealthProfessionalReview, saved["review"])
        adoption = await session.get(HealthMealPlanAdoption, adopted["adoption_id"])
        assert review.status == adoption.status == "invalidated"
        assert review.version == 4 and adoption.version == 2 and adoption.snapshot == adopted["snapshot"]


def selected_profile_body(source, record, *, version=1, weight="60"):
    """专业确认值和明确实测版本同时提交，均为合成资料。"""
    body = safety_body(source, version=version)
    body["payload"]["weight_kg"] = weight
    body["weight_measurement_source"] = {"record_id": record["id"], "version": record["version"]}
    return body


def profile_path(case):
    """当前成员专业投影的正式HTTP入口。"""
    return f"{ROOT}/members/{case.member}/external-profile-versions"


async def import_selected_profile(case, body=None):
    """管理员经授权入口导入并保留真实回执。"""
    response = await case.client.post(profile_path(case), headers=case.identities["admin"], json=body or case.body)
    assert response.status_code == 201, response.text
    return response.json()


async def publish_weight_rules(case, *, weight_coefficient="5", intercept="30"):
    """批准合成线性公式与固定66/99/165克菜单，期望目标由手算给出。"""
    recipe = await publish_planner_recipe(case.client, case.identities["admin"], "显式体重源合成菜")
    async with case.sessions() as session:
        row = await session.get(RecipeVersion, recipe)
        food = deepcopy(row.ingredients[0]["food"])
        recipe_hash = input_fingerprint(
            {
                "ingredients": row.ingredients,
                "yield_grams": str(row.yield_grams),
                "nutrients": row.nutrients,
                "dataset_version": row.dataset_version,
            }
        )
    payload = rules_payload()
    formula = target_formula()
    formula.update(intercept_kcal=intercept, weight_kg_coefficient=weight_coefficient)
    payload["personal_targets"] = [formula]
    payload["ingredient_classifications"][0].update(
        food_id=food["id"],
        food_hash=input_fingerprint(food),
        allergen_codes=[],
        intolerance_codes=[],
        food_categories=[],
    )
    payload["meal_target_shares"] = meal_shares()
    payload["meal_generation"] = {
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
                        "meal_type": meal,
                        "dishes": [{"dish_type_code": "synthetic", "grams_options": [grams]}],
                    }
                    for meal, grams in zip(("breakfast", "lunch", "dinner"), ("66", "99", "165"))
                ],
            }
        ],
    }
    body = {
        **proof(),
        "rule_code": "synthetic-selected-weight-" + uuid4().hex,
        "status": "approved",
        "payload": payload,
    }
    response = await case.client.post(f"{ROOT}/approved-quality-rules", headers=case.identities["admin"], json=body)
    assert response.status_code == 201, response.text
    return {**body, "recipe": recipe}


async def target_read(case, rules, *, profile_version=1, member=None):
    """目标请求只指定来源版本，禁止客户端输入身体参数。"""
    response = await case.client.post(
        f"{ROOT}/members/{member or case.member}/nutrition-targets",
        headers=case.headers,
        json={"profile_version": profile_version, "rule_version": 1, "rule_code": rules["rule_code"]},
    )
    assert response.status_code == 200, response.text
    return response.json()


async def initial_weight_preview(case, rules, *, family=False):
    """单人和家庭入口消费同一明确专业来源及批准目录。"""
    response = await case.client.post(
        f"{ROOT}/members/{case.member}/initial-meal-plan-previews",
        headers=case.headers,
        json={
            "kind": "family" if family else "single",
            "plan_date": "2026-10-08",
            "rule_code": rules["rule_code"],
            "rule_version": 1,
            "profile_versions": {case.member: 1},
            "meals": [
                {"meal_type": meal, "participant_ids": [case.member]} for meal in ("breakfast", "lunch", "dinner")
            ],
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


async def save_weight_plan(case, rules):
    """55+110+165=330，正式保存后经独立质量接口检查。"""
    spec = {
        "plan_date": "2026-10-08",
        "meals": [
            {
                "meal_type": meal,
                "dishes": [{"recipe_version_id": rules["recipe"], "grams": grams}],
            }
            for meal, grams in zip(("breakfast", "lunch", "dinner"), ("55", "110", "165"))
        ],
    }
    response = await case.client.post(
        f"{ROOT}/members/{case.member}/meal-plan-previews", headers=case.headers, json=spec
    )
    assert response.status_code == 201 and response.json()["nutrition"]["totals"]["energy_kcal"] == "330.00", (
        response.text
    )
    key = str(uuid4())
    saved = await case.client.post(
        f"{ROOT}/members/{case.member}/meal-plans",
        headers={**case.headers, "Idempotency-Key": key},
        json={"client_request_id": key, "preview_id": response.json()["preview_id"]},
    )
    assert saved.status_code == 201, saved.text
    plan = saved.json()["plan_id"]
    checked = await quality_check(case, plan, rules)
    return {
        "plan": plan,
        "recipe": rules["recipe"],
        "check": checked,
        "review": await review_for_check(case, checked),
        "version": 1,
        "profile_version": 1,
    }


async def quality_check(case, plan, rules, *, plan_version=1):
    """新幂等键对应一次真实服务端复算。"""
    response = await case.client.post(
        f"{ROOT}/meal-plans/{plan}/quality-checks",
        headers=case.headers,
        json={"client_request_id": str(uuid4()), "version": plan_version, "rule_code": rules["rule_code"]},
    )
    assert response.status_code == 201, response.text
    return response.json()


async def review_for_check(case, check):
    """专业复核ID来自真实检查读取结果。"""
    response = await case.client.get(f"{ROOT}/quality-checks/{check['check_id']}", headers=case.headers)
    assert response.status_code == 200, response.text
    return response.json()["review"]["review_id"]


async def approve_and_adopt(case, saved):
    """独立专业人资格、授权、批准与本人采用均经正式接口。"""
    grant = await case.client.put(
        f"{ROOT}/members/{case.member}/grants",
        headers=case.headers,
        json={"actor_uid": "other", "scopes": ["profile_view", "professional_review"]},
    )
    assert grant.status_code == 200, grant.text
    if not getattr(case, "reviewer_registered", False):
        credential = await case.client.post(
            f"{ROOT}/professional-reviewers",
            headers=case.identities["admin"],
            json={**proof(), "status": "qualified", "reviewer_uid": "other"},
        )
        assert credential.status_code == 201, credential.text
        case.reviewer_registered = True
    await action(case.client, case.headers, saved["review"], "submit", 1)
    await action(case.client, case.identities["other"], saved["review"], "approve", 2)
    adopted = await case.client.post(
        f"{ROOT}/meal-plans/{saved['plan']}/adopt",
        headers=case.headers,
        json={
            "client_request_id": str(uuid4()),
            "version": saved["version"],
            "review_id": saved["review"],
            "profile_versions": {case.member: saved["profile_version"]},
        },
    )
    assert adopted.status_code == 201 and adopted.json()["status"] == "active", adopted.text
    return adopted.json()


async def mutate_weight(case, record, mutation):
    """正式更正或作废所选记录，保留原始时间与来源。"""
    path = case.measurement_path + "/" + record["id"]
    if mutation == "void":
        response = await case.client.post(
            path + "/void",
            headers=case.headers,
            json={"expected_version": record["version"], "reason": "合成测试误录作废"},
        )
    else:
        response = await case.client.put(
            path,
            headers=case.headers,
            json={"expected_version": record["version"], "values": {"weight": 61}, "note": record["note"]},
        )
    assert response.status_code == 200, response.text
    return response.json()

"""实际SKU选择、来源证据及后台恢复的负向验证。"""

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from test.unit.services.test_daily_arrangement import sku
from test.unit.services.test_health_initial_meal_generation import initial_fixture, generated
from yuxi.services.daily_commerce_service import match_meal_requirements, match_requirements
from yuxi.services.health_knowledge_import_service import nutrition_candidates_with_evidence
from yuxi.services.miniapp_profile_coding import validated_profile_mapping
from yuxi.services.health_vision_types import HealthVisionError


def test_pending_mapping_is_not_a_recommendation_source():
    product = sku()
    product["ingredients"][0]["review_status"] = "pending"
    assert match_requirements([{"ingredient_code": "food-A", "required_value": "100"}], {"items": [product]}) is None


def test_three_meals_backtrack_over_actual_shared_stock():
    shared, alternate = sku(stock=1), sku(stock=1, sid="SKU-2")
    alternate["price_cent"] = 200
    needs = {
        "breakfast": [{"ingredient_code": "food-A", "required_value": "200"}],
        "lunch": [{"ingredient_code": "food-A", "required_value": "200"}],
    }
    selected = match_meal_requirements(needs, {"items": [shared, alternate]})
    assert {selected[meal][0]["sku_id"] for meal in needs} == {"SKU-1", "SKU-2"}
    assert match_meal_requirements(needs, {"items": [shared]}) is None


def test_published_recipe_catalog_is_separate_from_rule_embedded_list():
    values = initial_fixture()
    context = values[1]
    generation = context["rules"]["payload"]["meal_generation"]
    context["published_classifications"] = deepcopy(generation["recipe_classifications"])
    generation["recipe_classifications"] = []
    generation["catalog_mode"] = "published"
    assert generated(values)["status"] == "ready"
    for row in context["published_classifications"]:
        row["recipe_hash"] = "c" * 64
    assert generated(values)["status"] == "not_ready"


def profile_and_codes():
    profile = {"dietary_details": {"doctorStatus": "set", "clinicianGuidance": "医生交代清淡少盐"}}
    mapping = {"doctor_requirements": {"限制钠摄入": "low_sodium"}}
    result = {
        "matches": [{"field": "doctor_requirements", "text": "医生交代清淡少盐", "code": "low_sodium", "quote": "少盐"}]
    }
    return profile, mapping, result


def test_profile_interpretation_requires_member_original_and_approved_code():
    profile, mapping, result = profile_and_codes()
    assert (
        validated_profile_mapping(profile, mapping, result)["doctor_requirements"]["医生交代清淡少盐"] == "low_sodium"
    )
    for key, value in (("code", "invented"), ("text", "另一位成员的医嘱"), ("quote", "模型补写的依据")):
        changed = deepcopy(result)
        changed["matches"][0][key] = value
        with pytest.raises(HealthVisionError):
            validated_profile_mapping(profile, mapping, changed)
    with pytest.raises(HealthVisionError):
        validated_profile_mapping(profile, mapping, {"matches": []})


def material_and_candidate():
    content = "每100克可食部分，蛋白质10克。"
    material = {
        "sources": [{"source_id": "source-A", "content": content, "chunk_hash": "a" * 64, "filename": "合成营养依据"}]
    }
    response = {
        "rows": [
            {
                "data": {"name": "合成食材", "nutrients": {"protein_g": "10"}},
                "evidence": [{"field": "nutrients.protein_g", "source_id": "source-A", "quote": content}],
            }
        ]
    }
    return material, response


def test_candidate_retains_missing_license_and_rejects_fabricated_values():
    material, response = material_and_candidate()
    rows, proofs = nutrition_candidates_with_evidence(response, material)
    assert "license" not in rows[0]
    assert proofs[0]["proofs"][0]["quote"] == material["sources"][0]["content"]
    for bad in ("11", "100", "1"):
        response["rows"][0]["data"]["nutrients"]["protein_g"] = bad
        with pytest.raises(HealthVisionError):
            nutrition_candidates_with_evidence(response, material)


def test_candidate_cannot_relabel_energy_units_or_invent_license():
    material, response = material_and_candidate()
    response["rows"][0]["data"]["nutrients"] = {"energy_kcal": "10"}
    response["rows"][0]["evidence"][0]["field"] = "nutrients.energy_kcal"
    with pytest.raises(HealthVisionError):
        nutrition_candidates_with_evidence(response, material)
    material, response = material_and_candidate()
    response["rows"][0]["data"]["license"] = "模型虚构许可"
    with pytest.raises(HealthVisionError):
        nutrition_candidates_with_evidence(response, material)


@pytest.mark.asyncio
async def test_worker_shutdown_recovers_same_business_version_without_new_agent_request(monkeypatch):
    from yuxi.services import daily_arrangement_tasks as jobs

    from datetime import date

    row = SimpleNamespace(
        id="existing",
        actor_uid="synthetic",
        family_id="family",
        plan_date=date(2026, 10, 19),
        status="generating",
        version=2,
        selection={"agent_result": {"preview_id": "existing"}},
    )
    session = SimpleNamespace(scalar=AsyncMock(return_value=row))
    create = AsyncMock(return_value=(SimpleNamespace(id="recovery"), True))
    monkeypatch.setattr(jobs.tasker, "create_unique_in_session", create)
    task = SimpleNamespace(
        payload={
            "arrangement_id": "existing",
            "uid": "synthetic",
            "family_id": "family",
            "version": 2,
            "date": "2026-10-19",
        }
    )
    await jobs.fail_daily_arrangement(session, task, "worker_shutdown: stopped")
    assert row.status == "generating" and row.selection["agent_result"]["preview_id"] == "existing"
    assert create.await_args.kwargs["payload"] == task.payload
    row.selection["recovery_count"] = 2
    await jobs.fail_daily_arrangement(session, task, "worker_shutdown: stopped")
    assert row.status == "failed" and create.await_count == 1


@pytest.mark.asyncio
async def test_signed_daily_source_does_not_require_adopted_plan_mapping(monkeypatch):
    """每日安排复用商城回源签名，校验前拒绝篡改；未发布来源仍失效。"""
    from datetime import date
    from yuxi.repositories.user_repository import UserRepository
    from yuxi.services import daily_arrangement_service as daily
    from yuxi.services.health_commerce_service import SourceProof, validate_source_proof

    monkeypatch.setenv("HEALTH_COMMERCE_SOURCE_SECRET", "synthetic-daily-source-secret-32bytes")
    monkeypatch.delenv("HEALTH_COMMERCE_INGREDIENT_MAP", raising=False)
    monkeypatch.setattr(
        UserRepository,
        "get_by_uid",
        AsyncMock(return_value=SimpleNamespace(is_deleted=False, department_id=1, is_login_locked=lambda: False)),
    )
    breakfast = {
        "type": "breakfast",
        "members": [{"id": "synthetic-member"}],
        "dishes": [{"id": "recipe-A"}],
        "memberNotes": [{"amount": "100"}],
    }
    lunch = {**deepcopy(breakfast), "type": "lunch"}
    snapshot = {"status": "ready", "id": "arrangement-A", "version": 1, "meals": [breakfast, lunch]}
    read = AsyncMock(return_value=snapshot)
    monkeypatch.setattr(daily, "read_daily_arrangement", read)
    # 本用例验证签名及餐次hash；采购组成在独立HTTP/PG测试中执行。
    monkeypatch.setattr(
        daily.DailyArrangementRepository,
        "context",
        AsyncMock(
            side_effect=lambda *a, **k: (
                None,
                SimpleNamespace(version=snapshot["version"], status="ready", selection={"purchase_payloads": {}}),
            )
        ),
    )
    monkeypatch.setattr(daily, "validate_daily_purchase_composition", AsyncMock())
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def source_session():
        yield None

    monkeypatch.setattr(daily.pg_manager, "get_async_session_context", source_session)
    proof = daily.daily_commerce_source("synthetic", "family-A", date(2026, 10, 19), "arrangement-A", breakfast)
    assert await validate_source_proof(SourceProof(**proof)) == {"available": True}
    with pytest.raises(HealthVisionError, match="来源凭据无效"):
        await validate_source_proof(
            SourceProof(**{**proof, "payload": proof["payload"].replace("family-A", "family-B")})
        )
    assert read.await_count == 1
    snapshot["version"] = 2
    lunch["dishes"] = [{"id": "recipe-B"}]
    assert await validate_source_proof(SourceProof(**proof)) == {"available": True}
    breakfast["dishes"] = [{"id": "recipe-C"}]
    with pytest.raises(HealthVisionError, match="本餐安排已更新"):
        await validate_source_proof(SourceProof(**proof))
    snapshot["status"] = "generating"
    with pytest.raises(HealthVisionError, match="尚未保存"):
        await validate_source_proof(SourceProof(**proof))

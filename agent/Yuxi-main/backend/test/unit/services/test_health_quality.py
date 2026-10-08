"""批准合成规则的独立数值、未知及权限输入边界。"""

from copy import deepcopy
from datetime import datetime, timedelta, UTC
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from yuxi.agents.toolkits.quality import get_quality_review_context, check_selected_plan_quality
from yuxi.services.health_quality_checks import evaluate_plan_quality, external_projection, projection_digest
from yuxi.services.health_quality_types import (
    ProfileProjection,
    QualityRules,
    QualityCheckInput,
    QualityAnswer,
    RulesImport,
)

FOOD = "00000000-0000-4000-8000-000000000001"


def profile_payload():
    """合成确认资料不代表实际人员或完整档案交付。"""
    return {
        "population_code": "synthetic_adult",
        "age_years": 30,
        **{
            key: {"state": "none", "codes": []}
            for key in ("conditions", "allergies", "intolerances", "avoidances", "doctor_requirements", "preferences")
        },
    }


def rules_payload():
    """范围只用于工程手算，不是专业营养建议。"""
    return {
        "allowed_population_codes": ["synthetic_adult"],
        "minimum_age_years": 18,
        "maximum_age_years": 130,
        "supported_condition_sets": [[]],
        "allergen_codes": ["synthetic_allergen"],
        "intolerance_codes": ["synthetic_intolerance"],
        "food_categories": ["synthetic_group"],
        "ingredient_classifications": [
            {
                "food_id": FOOD,
                "food_hash": "a" * 64,
                "complete": True,
                "allergen_codes": ["synthetic_allergen"],
                "intolerance_codes": ["synthetic_intolerance"],
                "food_categories": ["synthetic_group"],
            }
        ],
        "doctor_requirement_rules": [],
        "daily_bounds": {
            code: {"minimum": str(lo), "maximum": str(hi)}
            for code, lo, hi in [
                ("energy_kcal", 250, 350),
                ("protein_g", 20, 40),
                ("fat_g", 4, 8),
                ("carbohydrate_g", 50, 70),
                ("sodium_mg", 100, 200),
            ]
        },
    }


def evaluated(profile=None, rules=None, nutrient=None, ingredients=None):
    """期望300/30/6/60/150独立提供，不从受测计算器生成。"""
    snapshot = {
        "nutrition": {
            "totals": {
                "energy_kcal": "300",
                "protein_g": "30",
                "fat_g": "6",
                "carbohydrate_g": "60",
                "sodium_mg": "150",
            }
        }
    }
    if nutrient:
        snapshot["nutrition"]["totals"].update(nutrient)
    return evaluate_plan_quality(
        snapshot,
        {"status": "ready", "payload": profile or profile_payload()},
        {"status": "ready", "payload": rules or rules_payload()},
        ingredients if ingredients is not None else {FOOD: {"content_hash": "a" * 64, "source_current": True}},
    )


def test_quality_uses_approved_bounds_and_preserves_unknown():
    """完整已知合成输入通过，缺钠不变成零。"""
    assert evaluated() == {"status": "passed", "missing": [], "conflicts": [], "checks_version": "quality-rules-v1"}
    result = evaluated(nutrient={"sodium_mg": None})
    assert result["status"] == "unknown" and result["missing"] == [
        {"path": "nutrition.sodium_mg", "reason": "unknown_nutrient_or_portion"}
    ]
    rules = rules_payload()
    del rules["daily_bounds"]["sodium_mg"]
    assert evaluated(rules=rules)["status"] == "unknown"


@pytest.mark.parametrize("field", ["conditions", "allergies", "intolerances", "avoidances", "doctor_requirements"])
def test_unknown_field_is_not_explicit_none(field):
    """每种强制安全资料未填均须报告未知。"""
    profile = profile_payload()
    profile[field] = {"state": "unknown", "codes": []}
    assert evaluated(profile=profile)["status"] == "unknown"


@pytest.mark.parametrize(
    "field,code,expected",
    [
        ("allergies", "synthetic_allergen", "allergy"),
        ("intolerances", "synthetic_intolerance", "intolerance"),
        ("avoidances", "synthetic_group", "avoidance"),
    ],
)
def test_known_restrictions_are_independent_conflicts(field, code, expected):
    """已知冲突不因其他字段完整而放行。"""
    profile = profile_payload()
    profile[field] = {"state": "specified", "codes": [code]}
    result = evaluated(profile=profile)
    assert result["status"] == "conflict" and result["conflicts"][0]["code"] == expected


@pytest.mark.parametrize("change", ["missing", "incomplete", "hash", "source"])
def test_ingredient_classification_must_be_complete_and_current(change):
    """配料不全、分类旧版或食品变更均保留未知。"""
    rules = rules_payload()
    ingredients = {FOOD: {"content_hash": "a" * 64, "source_current": True}}
    if change == "missing":
        rules["ingredient_classifications"][0]["food_id"] = str(uuid4())
    elif change == "incomplete":
        rules["ingredient_classifications"][0]["complete"] = False
    elif change == "hash":
        ingredients[FOOD]["content_hash"] = "b" * 64
    else:
        ingredients[FOOD]["source_current"] = False
    assert evaluated(rules=rules, ingredients=ingredients)["status"] == "unknown"


def test_population_combination_and_unapproved_codes_are_not_guessed():
    """未成年人、多病未批准及未知分类都不能自动适配。"""
    profile = profile_payload()
    profile["age_years"] = 17
    assert evaluated(profile=profile)["conflicts"][0]["code"] == "unsupported_population"
    profile = profile_payload()
    profile["conditions"] = {"state": "specified", "codes": ["a", "b"]}
    rules = rules_payload()
    rules["supported_condition_sets"] = [["a"], ["b"]]
    assert evaluated(profile=profile, rules=rules)["conflicts"][0]["code"] == "unsupported_condition_combination"
    profile = profile_payload()
    profile["allergies"] = {"state": "specified", "codes": ["unknown_catalog_code"]}
    assert evaluated(profile=profile)["status"] == "unknown"


def test_doctor_bounds_intersect_general_and_conflicting_doctors_are_reported():
    """所有批准限制同时满足，不擅自用医嘱扩大一般范围。"""
    rules = rules_payload()
    rules["daily_bounds"]["energy_kcal"] = {"minimum": "100", "maximum": "200"}
    profile = profile_payload()
    profile["doctor_requirements"] = {"state": "specified", "codes": ["doctor_a"]}
    rules["doctor_requirement_rules"] = [
        {"code": "doctor_a", "daily_bounds": {"energy_kcal": {"minimum": "250", "maximum": "350"}}}
    ]
    assert evaluated(profile=profile, rules=rules)["conflicts"][0]["code"] == "doctor_requirements_conflict"
    rules["daily_bounds"]["energy_kcal"] = {"minimum": "250", "maximum": "280"}
    assert evaluated(profile=profile, rules=rules)["conflicts"][0]["code"] == "approved_nutrient_range"
    rules["daily_bounds"]["energy_kcal"] = {"minimum": "250", "maximum": "350"}
    assert evaluated(profile=profile, rules=rules)["status"] == "passed"
    profile["doctor_requirements"]["codes"].append("doctor_b")
    rules["doctor_requirement_rules"].append(
        {"code": "doctor_b", "daily_bounds": {"energy_kcal": {"minimum": "100", "maximum": "200"}}}
    )
    assert evaluated(profile=profile, rules=rules)["conflicts"][0]["code"] == "doctor_requirements_conflict"
    rules["doctor_requirement_rules"][0]["excluded_food_ids"] = [FOOD]
    assert any(c["code"] == "doctor:doctor_a" for c in evaluated(profile=profile, rules=rules)["conflicts"])


def test_approved_age_range_is_data_driven_and_empty_ingredients_are_unknown():
    """批准范围可以明确支持儿童，空配料不能产生安全通过。"""
    profile, rules = profile_payload(), rules_payload()
    profile.update(age_years=10, population_code="synthetic_child")
    rules.update(minimum_age_years=5, maximum_age_years=12, allowed_population_codes=["synthetic_child"])
    assert evaluated(profile=profile, rules=rules)["status"] == "passed"
    profile["age_years"] = 13
    assert evaluated(profile=profile, rules=rules)["status"] == "conflict"
    assert evaluated(ingredients={})["status"] == "unknown"


def test_model_schemas_hide_authority_and_reject_approval_fields():
    """固定两工具无身份或批准参数，最终JSON只能选收据或问题。"""
    for tool in (get_quality_review_context, check_selected_plan_quality):
        assert tool.tool_call_schema.model_json_schema()["properties"] == {}
    assert QualityAnswer(check_id=uuid4()).check_id
    for body in [
        {},
        {"check_id": str(uuid4()), "approved": True},
        {"questions": [" "]},
        {"check_id": str(uuid4()), "questions": ["缺哪项？"]},
    ]:
        with pytest.raises(ValidationError):
            QualityAnswer.model_validate(body)
    with pytest.raises(ValidationError):
        QualityCheckInput(client_request_id=uuid4(), version=True, rule_code="synthetic")
    profile = profile_payload()
    profile["allergies"] = {"state": "unknown", "codes": ["a"]}
    with pytest.raises(ValidationError):
        ProfileProjection.model_validate(profile)
    rules = rules_payload()
    rules["ingredient_classifications"] *= 2
    with pytest.raises(ValidationError):
        QualityRules.model_validate(rules)


@pytest.mark.parametrize(
    "change,reason",
    [
        ("missing", "not_delivered"),
        ("revoked", "revoked"),
        ("expired", "expired"),
        ("future", "future_attestation"),
        ("hash", "integrity_mismatch"),
        ("timestamp", "integrity_mismatch"),
    ],
)
def test_external_projection_cannot_fall_back_or_return_invalid_payload(change, reason):
    """来源时钟、摘要与撤回直接控制可用性。"""
    now = datetime.now(UTC)
    proof = {
        "version": 1,
        "attested_at": (now - timedelta(minutes=1)).isoformat(),
        "valid_until": (now + timedelta(days=1)).isoformat(),
    }
    if change == "expired":
        proof["valid_until"] = (now - timedelta(seconds=1)).isoformat()
    if change == "future":
        proof["attested_at"] = (now + timedelta(minutes=1)).isoformat()
    payload = profile_payload()
    row = SimpleNamespace(
        id="synthetic",
        version=1,
        payload=payload,
        attestation=proof,
        content_hash=projection_digest("profile", "member", 1, payload, proof),
        attested_at=datetime.fromisoformat(proof["attested_at"]).replace(tzinfo=None),
        valid_until=datetime.fromisoformat(proof["valid_until"]).replace(tzinfo=None),
        revoked_at=None,
    )
    if change == "revoked":
        row.revoked_at = now.replace(tzinfo=None)
    if change == "hash":
        row.payload = deepcopy(payload)
        row.payload["age_years"] = 99
    if change == "timestamp":
        row.valid_until += timedelta(days=1)
    result = external_projection(None if change == "missing" else row, "profile", "member")
    assert result["status"] == "not_ready" and result["reason"] == reason and result["payload"] is None


def test_external_input_requires_aware_dates_and_approved_status():
    """未经批准或缺时区的规则不能跨系统导入。"""
    now = datetime.now(UTC)
    body = {
        "version": 1,
        "rule_code": "synthetic",
        "source_ref": "synthetic",
        "source_version": "v1",
        "authority_ref": "synthetic-reviewed",
        "attested_by": "synthetic-content-reviewer",
        "attested_at": now.isoformat(),
        "valid_until": (now + timedelta(days=1)).isoformat(),
        "status": "approved",
        "payload": rules_payload(),
    }
    assert RulesImport.model_validate(body).status == "approved"
    for field, value in [("status", "draft"), ("attested_at", now.replace(tzinfo=None).isoformat())]:
        with pytest.raises(ValidationError):
            RulesImport.model_validate({**body, field: value})

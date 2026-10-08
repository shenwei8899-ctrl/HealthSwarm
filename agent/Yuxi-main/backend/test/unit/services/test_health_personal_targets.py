"""批准合成公式的独立手算、拒绝原因及实际质量消费者。"""

from copy import deepcopy
from decimal import Decimal

import pytest
from pydantic import ValidationError

from test.unit.services.test_health_quality import profile_payload, rules_payload, evaluated
from yuxi.services.health_personal_targets import calculate_personal_targets
from yuxi.services.health_quality_types import ProfileProjection, QualityRules


def target_formula():
    """合成计算域：30+5×60=330，不作为生产医学口径。"""
    return {
        "population_code": "synthetic_adult",
        "sex_code": "synthetic_sex",
        "condition_codes": [],
        "intercept_kcal": "30",
        "weight_kg_coefficient": "5",
        "height_cm_coefficient": "0",
        "age_years_coefficient": "0",
        "activity_factors": {"synthetic_activity": "1"},
        "nutrient_ranges": {
            code: {
                "minimum_per_energy": "1" if code == "energy_kcal" else "0",
                "maximum_per_energy": "1" if code == "energy_kcal" else "0",
                "minimum_constant": "0" if code == "energy_kcal" else bounds["minimum"],
                "maximum_constant": "0" if code == "energy_kcal" else bounds["maximum"],
            }
            for code, bounds in rules_payload()["daily_bounds"].items()
        },
    }


def confirmed_inputs():
    """确认参数仅用于隔离测试。"""
    profile = {
        **profile_payload(),
        "sex_code": "synthetic_sex",
        "weight_kg": "60",
        "activity_code": "synthetic_activity",
    }
    rules = {**rules_payload(), "personal_targets": [target_formula()]}
    return profile, rules


def calculated(profile, rules):
    """消费正式边界模型，不绕过批准目录校验。"""
    return calculate_personal_targets(ProfileProjection.model_validate(profile), QualityRules.model_validate(rules))


def test_signed_formula_activity_and_nutrient_factors_have_independent_oracle():
    """(100+2×60+150−30)×1.5=510；范围459..561，蛋白5.10..10.20。"""
    profile, rules = confirmed_inputs()
    profile["height_cm"] = "150"
    rules["daily_bounds"] = {}
    formula = rules["personal_targets"][0]
    formula.update(
        intercept_kcal="100", weight_kg_coefficient="2", height_cm_coefficient="1", age_years_coefficient="-1"
    )
    formula["activity_factors"]["synthetic_activity"] = "1.5"
    formula["nutrient_ranges"]["energy_kcal"].update(minimum_per_energy="0.9", maximum_per_energy="1.1")
    formula["nutrient_ranges"]["protein_g"].update(
        minimum_per_energy="0.01", maximum_per_energy="0.02", minimum_constant="0", maximum_constant="0"
    )
    result = calculated(profile, rules)
    assert result["status"] == "ready" and Decimal(result["energy_kcal"]) == Decimal("510")
    assert {k: Decimal(v) for k, v in result["bounds"]["energy_kcal"].items()} == {
        "minimum": Decimal("459"),
        "maximum": Decimal("561"),
    }
    assert {k: Decimal(v) for k, v in result["bounds"]["protein_g"].items()} == {
        "minimum": Decimal("5.10"),
        "maximum": Decimal("10.20"),
    }
    assert result["inputs"]["height_cm"] == "150"


@pytest.mark.parametrize(
    "field,value,reason",
    [
        ("population_code", None, "confirmed_population_age_and_sex_required"),
        ("age_years", None, "confirmed_population_age_and_sex_required"),
        ("sex_code", None, "confirmed_population_age_and_sex_required"),
        ("age_years", 17, "unsupported_population"),
        ("population_code", "unapproved", "unsupported_population"),
        ("sex_code", "unapproved", "personal_target_formula_not_approved"),
        ("activity_code", None, "confirmed_approved_activity_required"),
        ("activity_code", "unapproved", "confirmed_approved_activity_required"),
        ("weight_kg", None, "confirmed_formula_input_required"),
        ("conditions", {"state": "unknown", "codes": []}, "confirmed_conditions_and_requirements_required"),
        ("doctor_requirements", {"state": "unknown", "codes": []}, "confirmed_conditions_and_requirements_required"),
        ("conditions", {"state": "specified", "codes": ["unapproved"]}, "personal_target_formula_not_approved"),
        (
            "doctor_requirements",
            {"state": "specified", "codes": ["unapproved"]},
            "doctor_requirement_rule_not_approved",
        ),
    ],
)
def test_required_confirmed_inputs_are_not_inferred(field, value, reason):
    """每项新门禁独立制造其失败，不能回退默认公式。"""
    profile, rules = confirmed_inputs()
    profile[field] = value
    result = calculated(profile, rules)
    assert result["status"] == "not_ready" and result["reason"] == reason
    assert "bounds" not in result
    if field == "weight_kg":
        assert result["missing_field"] == "weight_kg"


def test_zero_coefficient_unused_height_is_not_collected():
    """未使用的身体字段不强制提供，缺失不会改变批准结果。"""
    profile, rules = confirmed_inputs()
    assert "height_cm" not in profile
    result = calculated(profile, rules)
    assert result["status"] == "ready" and Decimal(result["energy_kcal"]) == 330
    assert "height_cm" not in result["inputs"]
    assert result["inputs"]["age_years"] == "30" and result["inputs"]["doctor_requirements"] == []
    rules["personal_targets"][0]["height_cm_coefficient"] = "1"
    assert calculated(profile, rules)["missing_field"] == "height_cm"


@pytest.mark.parametrize("change", ["negative_energy", "large_energy", "large_nutrient"])
def test_outside_computational_domain_does_not_produce_ready_bounds(change):
    """批准参数合法仍可能产生不支持的结果，计算不可悄悄截断。"""
    profile, rules = confirmed_inputs()
    formula = rules["personal_targets"][0]
    if change == "negative_energy":
        formula["intercept_kcal"] = "-1000"
    elif change == "large_energy":
        formula["activity_factors"]["synthetic_activity"] = "1000000"
    else:
        formula["nutrient_ranges"]["protein_g"]["maximum_per_energy"] = "1000000"
    assert calculated(profile, rules)["reason"] == "formula_result_outside_supported_range"


def test_general_and_multiple_doctor_ranges_intersect_without_widening():
    """个人0..40、通用20..40、两医嘱22..35/25..32共同为25..32。"""
    profile, rules = confirmed_inputs()
    rules["personal_targets"][0]["nutrient_ranges"]["protein_g"]["minimum_constant"] = "0"
    profile["doctor_requirements"] = {"state": "specified", "codes": ["a", "b"]}
    rules["doctor_requirement_rules"] = [
        {"code": code, "daily_bounds": {"protein_g": {"minimum": lo, "maximum": hi}}}
        for code, lo, hi in [("a", "22", "35"), ("b", "25", "32")]
    ]
    result = calculated(profile, rules)
    assert result["bounds"]["protein_g"] == {"minimum": "25", "maximum": "32"}
    assert result["inputs"]["doctor_requirements"] == ["a", "b"]
    rules["doctor_requirement_rules"][1]["daily_bounds"]["protein_g"]["minimum"] = "36"
    rules["doctor_requirement_rules"][1]["daily_bounds"]["protein_g"]["maximum"] = "38"
    result = calculated(profile, rules)
    assert result["reason"] == "approved_target_ranges_conflict" and result["nutrient"] == "protein_g"
    assert "bounds" not in result


@pytest.mark.parametrize(
    "change",
    [
        "missing_nutrient",
        "reversed_factor",
        "reversed_constant",
        "negative_factor",
        "empty_activity",
        "zero_activity",
        "missing_coefficient",
        "duplicate_formula",
        "unapproved_population",
        "unapproved_conditions",
        "duplicate_conditions",
    ],
)
def test_invalid_external_formula_is_rejected_at_schema_boundary(change):
    """批准标记不能让结构含糊或目录不支持的公式进入持久化。"""
    _, rules = confirmed_inputs()
    formula = rules["personal_targets"][0]
    if change == "missing_nutrient":
        del formula["nutrient_ranges"]["sodium_mg"]
    elif change == "reversed_factor":
        formula["nutrient_ranges"]["energy_kcal"]["minimum_per_energy"] = "2"
    elif change == "reversed_constant":
        formula["nutrient_ranges"]["protein_g"]["minimum_constant"] = "100"
    elif change == "negative_factor":
        formula["nutrient_ranges"]["protein_g"]["minimum_per_energy"] = "-1"
    elif change == "empty_activity":
        formula["activity_factors"] = {}
    elif change == "zero_activity":
        formula["activity_factors"]["synthetic_activity"] = "0"
    elif change == "missing_coefficient":
        del formula["height_cm_coefficient"]
    elif change == "duplicate_formula":
        rules["personal_targets"].append(deepcopy(formula))
    elif change == "unapproved_population":
        formula["population_code"] = "unapproved"
    elif change == "unapproved_conditions":
        formula["condition_codes"] = ["unapproved"]
    else:
        formula["condition_codes"] = ["a", "a"]
    with pytest.raises(ValidationError):
        QualityRules.model_validate(rules)


def test_personal_targets_actually_constrain_quality_and_missing_is_not_passed():
    """旧通用300合格，新增330目标后不合格；缺体重不能继续通过。"""
    assert evaluated()["status"] == "passed"
    profile, rules = confirmed_inputs()
    result = evaluated(profile=profile, rules=rules)
    assert result["checks_version"] == "quality-rules-v2-personal"
    assert result["status"] == "conflict" and result["conflicts"] == [
        {"path": "nutrition.energy_kcal", "code": "approved_nutrient_range", "reason": "计划量超出当前批准范围"}
    ]
    assert evaluated(profile=profile, rules=rules, nutrient={"energy_kcal": "330"})["status"] == "passed"
    del profile["weight_kg"]
    result = evaluated(profile=profile, rules=rules)
    assert result["status"] == "unknown" and result["missing"][0] == {
        "path": "personal_targets",
        "reason": "confirmed_formula_input_required",
    }


def test_target_only_approved_bounds_work_but_unknown_allergies_still_block_plan():
    """有全五项个人范围可以检查，无过敏资料不能把目标就绪当安全放行。"""
    profile, rules = confirmed_inputs()
    rules["daily_bounds"] = {}
    assert evaluated(profile=profile, rules=rules, nutrient={"energy_kcal": "330"})["status"] == "passed"
    profile["allergies"] = {"state": "unknown", "codes": []}
    result = evaluated(profile=profile, rules=rules, nutrient={"energy_kcal": "330"})
    assert result["personal_targets"]["status"] == "ready" and result["status"] == "unknown"
    assert result["missing"] == [{"path": "profile.allergies", "reason": "not_filled"}]


def test_legacy_general_rule_is_not_reported_as_personal_target():
    """没有批准公式仍保留历史通用检查契约，个人读取明确不可用。"""
    profile, rules = confirmed_inputs()
    del rules["personal_targets"]
    assert calculated(profile, rules)["reason"] == "personal_target_formula_not_approved"
    assert evaluated(profile=profile, rules=rules) == {
        "status": "passed",
        "missing": [],
        "conflicts": [],
        "checks_version": "quality-rules-v1",
    }

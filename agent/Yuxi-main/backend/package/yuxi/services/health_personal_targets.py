"""当前批准公式的纯计算及通用条款/医嘱范围求交。"""

from decimal import Decimal, localcontext

from yuxi.services.health_quality_types import ProfileProjection, QualityRules
from yuxi.services.health_vision_types import NUTRIENTS


def calculate_personal_targets(profile: ProfileProjection, rules: QualityRules, *, weight_source_missing=False):
    """只消费已解析的确认字段与批准参数，缺依赖及冲突不产生可用目标。"""
    result = {"status": "not_ready", "reason": None, "units": NUTRIENTS}
    if rules.personal_targets is None:
        result["reason"] = "personal_target_formula_not_approved"
        return result
    if profile.population_code is None or profile.age_years is None or profile.sex_code is None:
        result["reason"] = "confirmed_population_age_and_sex_required"
        return result
    if (
        not rules.minimum_age_years <= profile.age_years <= rules.maximum_age_years
        or profile.population_code not in rules.allowed_population_codes
    ):
        result["reason"] = "unsupported_population"
        return result
    if profile.conditions.state == "unknown" or profile.doctor_requirements.state == "unknown":
        result["reason"] = "confirmed_conditions_and_requirements_required"
        return result
    formula = next(
        (
            f
            for f in rules.personal_targets
            if f.population_code == profile.population_code
            and f.sex_code == profile.sex_code
            and set(f.condition_codes) == set(profile.conditions.codes)
        ),
        None,
    )
    if formula is None:
        result["reason"] = "personal_target_formula_not_approved"
        return result
    if profile.activity_code not in formula.activity_factors:
        result["reason"] = "confirmed_approved_activity_required"
        return result
    inputs = {
        "population_code": profile.population_code,
        "age_years": str(profile.age_years),
        "sex_code": profile.sex_code,
        "conditions": list(profile.conditions.codes),
        "doctor_requirements": list(profile.doctor_requirements.codes),
        "activity_code": profile.activity_code,
    }
    with localcontext() as context:
        context.prec = 64
        base = formula.intercept_kcal
        for name, coefficient in [
            ("weight_kg", formula.weight_kg_coefficient),
            ("height_cm", formula.height_cm_coefficient),
            ("age_years", formula.age_years_coefficient),
        ]:
            if not coefficient:
                continue
            if name == "weight_kg" and weight_source_missing:
                result.update(reason="selected_weight_measurement_required", missing_field=name)
                return result
            value = getattr(profile, name)
            if value is None:
                result.update(reason="confirmed_formula_input_required", missing_field=name)
                return result
            inputs[name] = str(value)
            base += coefficient * Decimal(value)
        energy = base * formula.activity_factors[profile.activity_code]
        if not 0 < energy <= 1000000:
            result["reason"] = "formula_result_outside_supported_range"
            return result
        requirements = {r.code: r for r in rules.doctor_requirement_rules}
        if set(profile.doctor_requirements.codes) - requirements.keys():
            result["reason"] = "doctor_requirement_rule_not_approved"
            return result
        raw, effective = {}, {}
        for nutrient in NUTRIENTS:
            factors = formula.nutrient_ranges[nutrient]
            low = energy * factors.minimum_per_energy + factors.minimum_constant
            high = energy * factors.maximum_per_energy + factors.maximum_constant
            if high > 1000000:
                result["reason"] = "formula_result_outside_supported_range"
                return result
            raw[nutrient] = {"minimum": str(low), "maximum": str(high)}
            bounds = [
                r.daily_bounds[nutrient]
                for code in profile.doctor_requirements.codes
                if nutrient in (r := requirements[code]).daily_bounds
            ]
            if nutrient in rules.daily_bounds:
                bounds.append(rules.daily_bounds[nutrient])
            minimum = max([low] + [b.minimum for b in bounds])
            maximum = min([high] + [b.maximum for b in bounds])
            if minimum > maximum:
                result.update(reason="approved_target_ranges_conflict", nutrient=nutrient)
                return result
            effective[nutrient] = {"minimum": str(minimum), "maximum": str(maximum)}
    result.update(
        status="ready",
        reason=None,
        energy_kcal=str(energy),
        inputs=inputs,
        formula={
            "population_code": formula.population_code,
            "sex_code": formula.sex_code,
            "condition_codes": list(formula.condition_codes),
        },
        formula_bounds=raw,
        bounds=effective,
    )
    return result

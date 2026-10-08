"""版本投影完整性及批准规则驱动的确定性质量检查。"""

from datetime import datetime, UTC
from decimal import Decimal, localcontext

from pydantic import ValidationError

from yuxi.services.health_nutrition_service import input_fingerprint
from yuxi.services.health_quality_types import ProfileProjection, QualityRules
from yuxi.services.health_personal_targets import calculate_personal_targets
from yuxi.services.health_vision_types import NUTRIENTS
from yuxi.utils.datetime_utils import utc_now_naive


def projection_digest(kind, key, version, payload, attestation):
    """来源归属、版本、内容及依据共同防止投影移用和篡改。"""
    return input_fingerprint(
        {"kind": kind, "key": key, "version": version, "payload": payload, "attestation": attestation}
    )


def external_projection(row, kind, key):
    """未交付、撤回、过期或完整性不符均不返回可用内容。"""
    result = {
        "status": "not_ready",
        "reason": "not_delivered",
        "id": None,
        "version": None,
        "content_hash": None,
        "payload": None,
        "attestation": None,
    }
    if row is None:
        return result
    result.update(id=row.id, version=row.version, content_hash=row.content_hash)
    result["reason"] = "integrity_mismatch"
    try:
        proof = row.attestation
        attested_at = datetime.fromisoformat(proof["attested_at"]).astimezone(UTC).replace(tzinfo=None)
        valid_until = datetime.fromisoformat(proof["valid_until"]).astimezone(UTC).replace(tzinfo=None)
        expected = projection_digest(kind, key, row.version, row.payload, proof)
        dto = ProfileProjection if kind == "profile" else QualityRules
        dto.model_validate(row.payload)
        if (
            expected != row.content_hash
            or proof["version"] != row.version
            or attested_at != row.attested_at
            or valid_until != row.valid_until
        ):
            return result
    except (KeyError, TypeError, ValueError, ValidationError):
        return result
    if row.revoked_at is not None:
        result["reason"] = "revoked"
    elif row.attested_at > utc_now_naive():
        result["reason"] = "future_attestation"
    elif row.valid_until <= utc_now_naive():
        result["reason"] = "expired"
    else:
        result.update(status="ready", reason=None, payload=row.payload, attestation=proof)
    return result


def evaluate_plan_quality(snapshot, profile, rules, ingredients, *, classifications=None, covered_meals=None):
    """只消费当前批准条款；批量候选可复用同一规则的已解析分类索引。"""
    missing, conflicts = [], []

    def unknown(path, reason):
        missing.append({"path": path, "reason": reason})

    def conflict(path, code, reason):
        conflicts.append({"path": path, "code": code, "reason": reason})

    if profile["status"] != "ready":
        unknown("profile", profile["reason"])
    if rules["status"] != "ready":
        unknown("rules", rules["reason"])
    if missing:
        return {"status": "unknown", "missing": missing, "conflicts": conflicts, "checks_version": "quality-rules-v1"}
    p = profile["payload"]
    r = rules["payload"]
    if not isinstance(p, ProfileProjection):
        p = ProfileProjection.model_validate(p)
    if not isinstance(r, QualityRules):
        r = QualityRules.model_validate(r)
    targets = calculate_personal_targets(p, r) if r.personal_targets is not None else None
    partial = covered_meals is not None and set(covered_meals) != {"breakfast", "lunch", "dinner"}
    if partial and r.meal_target_shares is None:
        unknown("rules.meal_target_shares", "covered_meal_ranges_not_approved")
    if targets is not None and targets["status"] != "ready":
        unknown("personal_targets", targets["reason"])
    if p.age_years is None or p.population_code is None:
        unknown("profile.population", "not_filled")
    elif (
        not r.minimum_age_years <= p.age_years <= r.maximum_age_years
        or p.population_code not in r.allowed_population_codes
    ):
        conflict("profile.population", "unsupported_population", "批准规则未支持该人群")
    for field in ("conditions", "allergies", "intolerances", "avoidances", "doctor_requirements"):
        if getattr(p, field).state == "unknown":
            unknown(f"profile.{field}", "not_filled")
    if p.conditions.state != "unknown" and set(p.conditions.codes) not in [set(c) for c in r.supported_condition_sets]:
        conflict("profile.conditions", "unsupported_condition_combination", "疾病组合未被批准规则明确支持")
    for field, catalog in (
        ("allergies", r.allergen_codes),
        ("intolerances", r.intolerance_codes),
        ("avoidances", r.food_categories),
    ):
        if set(getattr(p, field).codes) - set(catalog):
            unknown(f"profile.{field}", "classification_not_approved")
    requirements = {rule.code: rule for rule in r.doctor_requirement_rules}
    active_requirements = [requirements[code] for code in p.doctor_requirements.codes if code in requirements]
    if set(p.doctor_requirements.codes) - requirements.keys():
        unknown("profile.doctor_requirements", "requirement_rule_not_approved")
    if classifications is None:
        classifications = {str(c.food_id): c for c in r.ingredient_classifications}
    if not ingredients:
        unknown("ingredients", "no_confirmed_ingredients")
    for food_id, food in ingredients.items():
        path = f"ingredients.{food_id}"
        classification = classifications.get(food_id)
        if (
            classification is None
            or not classification.complete
            or classification.food_hash != food["content_hash"]
            or not food["source_current"]
        ):
            unknown(path, "complete_classification_or_current_source_missing")
            continue
        if set(p.allergies.codes) & set(classification.allergen_codes):
            conflict(path, "allergy", "配料与明确过敏限制冲突")
        if set(p.intolerances.codes) & set(classification.intolerance_codes):
            conflict(path, "intolerance", "配料与明确不耐受限制冲突")
        if set(p.avoidances.codes) & set(classification.food_categories):
            conflict(path, "avoidance", "配料与明确忌口冲突")
        for requirement in active_requirements:
            if food_id in {str(fid) for fid in requirement.excluded_food_ids} or set(
                classification.food_categories
            ) & set(requirement.excluded_food_categories):
                conflict(path, f"doctor:{requirement.code}", "配料与批准医嘱条款冲突")
    for nutrient in NUTRIENTS:
        value = snapshot["nutrition"]["totals"].get(nutrient)
        # 一般条款与同时生效的医嘱共同求交集，代码不擅自扩大批准范围。
        doctor_bounds = [req.daily_bounds[nutrient] for req in active_requirements if nutrient in req.daily_bounds]
        general = r.daily_bounds.get(nutrient)
        bounds = doctor_bounds + ([general] if general is not None else [])
        if value is None:
            unknown(f"nutrition.{nutrient}", "unknown_nutrient_or_portion")
        if partial and r.meal_target_shares is None:
            continue
        personal = targets["bounds"][nutrient] if targets is not None and targets["status"] == "ready" else None
        if not bounds and personal is None:
            unknown(f"rules.daily_bounds.{nutrient}", "bound_not_approved")
            continue
        minimum = max([b.minimum for b in bounds] + ([Decimal(personal["minimum"])] if personal is not None else []))
        maximum = min([b.maximum for b in bounds] + ([Decimal(personal["maximum"])] if personal is not None else []))
        if minimum > maximum:
            conflict(f"nutrition.{nutrient}", "doctor_requirements_conflict", "多条批准医嘱无法同时满足，须专业复核")
            continue
        if partial:
            with localcontext() as context:
                context.prec = 64
                fraction = sum(r.meal_target_shares[meal][nutrient] for meal in covered_meals)
                minimum, maximum = minimum * fraction, maximum * fraction
        if value is not None and not minimum <= Decimal(value) <= maximum:
            conflict(f"nutrition.{nutrient}", "approved_nutrient_range", "计划量超出当前批准范围")
    return {
        "status": "conflict" if conflicts else "unknown" if missing else "passed",
        "missing": missing,
        "conflicts": conflicts,
        "checks_version": "quality-rules-v2-personal" if targets is not None else "quality-rules-v1",
        **({"personal_targets": targets} if targets is not None else {}),
        **(
            {
                "coverage": {
                    "covered_meals": covered_meals,
                    "full_day_covered": not partial,
                    "range_scope": "participating_meals" if partial else "full_day",
                }
            }
            if covered_meals is not None
            else {}
        ),
    }

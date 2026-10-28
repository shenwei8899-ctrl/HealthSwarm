"""准备状态与来源引用的工程合成测试，不代表专业参数批准。"""

from types import SimpleNamespace

import pytest

from yuxi.services.health_readiness import nutrition_readiness
from yuxi.services.health_source_types import (
    knowledge_source_reference,
    nutrition_source_references,
    parse_knowledge_source,
)
from yuxi.services.health_vision_types import HealthVisionError, NUTRIENTS

FOOD = "00000000-0000-4000-8000-000000000001"
RECIPE = "00000000-0000-4000-8000-000000000002"


def sources():
    """提供独立手算目标和同一合成菜谱覆盖三餐的目录。"""
    profile = {
        "population_code": "synthetic_adult",
        "age_years": 30,
        "sex_code": "synthetic_sex",
        "activity_code": "synthetic_activity",
        **{
            key: {"state": "none", "codes": []}
            for key in ("conditions", "allergies", "intolerances", "avoidances", "doctor_requirements", "preferences")
        },
    }
    rules = {
        "allowed_population_codes": ["synthetic_adult"],
        "minimum_age_years": 18,
        "maximum_age_years": 90,
        "supported_condition_sets": [[]],
        "allergen_codes": ["synthetic_allergen"],
        "ingredient_classifications": [
            {"food_id": FOOD, "food_hash": "a" * 64, "complete": True, "allergen_codes": ["synthetic_allergen"]}
        ],
        "daily_bounds": {key: {"minimum": "0", "maximum": "500"} for key in NUTRIENTS},
        "personal_targets": [
            {
                "population_code": "synthetic_adult",
                "sex_code": "synthetic_sex",
                "condition_codes": [],
                "intercept_kcal": "300",
                "weight_kg_coefficient": "0",
                "height_cm_coefficient": "0",
                "age_years_coefficient": "0",
                "activity_factors": {"synthetic_activity": "1"},
                "nutrient_ranges": {
                    key: {
                        "minimum_per_energy": "0",
                        "maximum_per_energy": "0",
                        "minimum_constant": "0",
                        "maximum_constant": "500",
                    }
                    for key in NUTRIENTS
                },
            }
        ],
        "meal_generation": {
            "recipe_classifications": [
                {
                    "recipe_version_id": RECIPE,
                    "recipe_hash": "b" * 64,
                    "dish_type_code": "synthetic_dish",
                    "allowed_meal_types": ["breakfast", "lunch", "dinner"],
                }
            ],
            "profile_menus": [
                {
                    "population_code": "synthetic_adult",
                    "condition_codes": [],
                    "meals": [
                        {"meal_type": meal, "dishes": [{"dish_type_code": "synthetic_dish", "grams_options": [100]}]}
                        for meal in ("breakfast", "lunch", "dinner")
                    ],
                }
            ],
        },
    }

    def envelope(payload):
        """仅测试已验证输入下的业务状态。"""
        return {
            "id": "synthetic",
            "version": 1,
            "content_hash": "c" * 64,
            "status": "ready",
            "reason": None,
            "attestation": {},
            "payload": payload,
        }

    return [
        envelope(profile),
        envelope(rules),
        {RECIPE: SimpleNamespace(nutrients=dict.fromkeys(NUTRIENTS, "100"))},
        {RECIPE: {FOOD: {"content_hash": "a" * 64, "source_current": True}}},
        {RECIPE: "b" * 64},
    ]


def test_ready_is_only_permission_to_attempt_combination():
    """资料齐备不能声称组合已通过或专业批准。"""
    result = nutrition_readiness(*sources())
    assert result["personal_targets"] == {"status": "ready", "reason": None}
    assert result["meal_preview"] == {
        "status": "can_attempt_preview",
        "reason": None,
        "missing_slots": [],
        "rejected_candidates": [],
        "combination_checked": False,
    }
    assert result["professional_review"] == "not_a_professional_decision"
    assert result["plan_saved"] is False


@pytest.mark.parametrize("kind", ["unknown_allergy", "allergy", "source_changed", "recipe_changed", "unknown_nutrient"])
def test_incomplete_or_restricted_candidates_block_preview(kind):
    """分别恢复缺失、过敏及来源失效缺陷，不能把未知变为适用。"""
    args = sources()
    if kind == "unknown_allergy":
        args[0]["payload"]["allergies"]["state"] = "unknown"
    elif kind == "allergy":
        args[0]["payload"]["allergies"] = {"state": "specified", "codes": ["synthetic_allergen"]}
    elif kind == "source_changed":
        args[3][RECIPE][FOOD]["source_current"] = False
    elif kind == "recipe_changed":
        args[4][RECIPE] = "d" * 64
    else:
        args[2][RECIPE].nutrients["sodium_mg"] = None
    result = nutrition_readiness(*args)
    assert result["meal_preview"]["status"] == "not_ready"
    if kind == "unknown_allergy":
        assert {"path": "profile.allergies", "reason": "not_filled"} in result["missing"]
    else:
        assert len(result["meal_preview"]["missing_slots"]) == 3
        assert result["meal_preview"]["rejected_candidates"][0]["recipe_version_id"] == RECIPE


@pytest.mark.parametrize("index", [0, 1])
def test_missing_current_source_never_uses_payload(index):
    """原件或确认失效后，即使仍附带旧内容也不能计算。"""
    args = sources()
    args[index].update(status="not_ready", reason="knowledge_source_changed")
    result = nutrition_readiness(*args)
    assert result["personal_targets"]["status"] == "not_ready"
    assert result["meal_preview"]["status"] == "not_ready"


def test_no_approved_formula_or_catalog_has_specific_gap():
    """计算目标和拥有配餐目录是两个独立条件。"""
    args = sources()
    args[1]["payload"].pop("meal_generation")
    assert nutrition_readiness(*args)["meal_preview"]["reason"] == "initial_catalog_not_approved"
    args[1]["payload"].pop("personal_targets")
    assert nutrition_readiness(*args)["personal_targets"]["reason"] == "personal_target_formula_not_approved"


def test_approved_daily_bounds_allow_preview_without_personal_formula():
    """通用批准范围可支持预览，不能因此宣称已有个体目标公式。"""
    args = sources()
    args[1]["payload"].pop("personal_targets")
    result = nutrition_readiness(*args)
    assert result["personal_targets"] == {"status": "not_ready", "reason": "personal_target_formula_not_approved"}
    assert result["meal_preview"]["status"] == "can_attempt_preview"
    assert result["meal_preview"]["combination_checked"] is False


def test_mutually_exclusive_doctor_bounds_cannot_be_ready_for_preview():
    """医嘱与通用范围无交集时提前公开冲突，不把它当待组合营养差异。"""
    args = sources()
    args[1]["payload"].pop("personal_targets")
    args[0]["payload"]["doctor_requirements"] = {"state": "specified", "codes": ["synthetic_requirement"]}
    args[1]["payload"]["doctor_requirement_rules"] = [
        {"code": "synthetic_requirement", "daily_bounds": {"energy_kcal": {"minimum": "600", "maximum": "700"}}}
    ]
    result = nutrition_readiness(*args)
    assert result["meal_preview"]["status"] == "not_ready"
    assert result["conflicts"][0]["code"] == "doctor_requirements_conflict"
    assert result["conflicts"][0]["path"] == "nutrition.energy_kcal"


def test_exact_reference_and_nested_nutrition_sources():
    """引用绑定库、文件与原始摘要；配方内原料也纳入校验。"""
    reference = knowledge_source_reference("kb_one", "file_two", "a" * 64)
    assert parse_knowledge_source(reference) == ("kb_one", "file_two", "a" * 64)
    assert parse_knowledge_source("https://example.org/authorized-source") is None
    assert nutrition_source_references(
        [{"source": "recipe", "ingredients": [{"food": {"source": reference}}]}, {"source": "portion"}]
    ) == ["recipe", "portion", reference]


@pytest.mark.parametrize(
    "reference",
    [
        "knowledge://kb/file",
        "KNOWLEDGE://kb/file#" + "a" * 64,
        "knowledge://kb/../file#" + "a" * 64,
        "knowledge:invalid",
    ],
)
def test_malformed_reserved_scheme_cannot_be_external_source(reference):
    """非法知识库引用不得降级为兼容的外部来源。"""
    with pytest.raises(HealthVisionError, match="knowledge_source_invalid"):
        parse_knowledge_source(reference)

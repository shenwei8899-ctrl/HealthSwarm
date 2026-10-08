"""批准差异、零上限和受控换菜输入的独立负控。"""

from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

from yuxi.services.health_meal_plan_types import SafeSwapInput
from yuxi.services.health_quality_types import MealSwapRules
from yuxi.services.health_safe_meal_swap_service import nutrient_differences
from yuxi.services.health_vision_types import NUTRIENTS


def values(energy="100"):
    """测试期望数值独立给定。"""
    return {"energy_kcal": energy, "protein_g": "10", "fat_g": "2", "carbohydrate_g": "20", "sodium_mg": "50"}


def test_difference_exact_limit_zero_unknown_and_signed_delta():
    """上限含边界，零上限须相同，未知不能通过。"""
    limits = {key: Decimal(0) for key in NUTRIENTS}
    limits["energy_kcal"] = Decimal(20)
    result = nutrient_differences(values(), values("80"), limits)
    assert result == (
        {"energy_kcal": "-20", "protein_g": "0", "fat_g": "0", "carbohydrate_g": "0", "sodium_mg": "0"},
        Decimal(1),
    )
    assert nutrient_differences(values(), values("79.99"), limits) is None
    assert nutrient_differences(values(), {**values(), "protein_g": "10.01"}, limits) is None
    assert nutrient_differences(values(), {**values(), "sodium_mg": None}, limits) is None
    assert nutrient_differences(values(), values(), {k: Decimal(0) for k in NUTRIENTS})[1] == 0


@pytest.mark.parametrize("defect", ["missing_limit", "extra_limit", "negative", "duplicate_recipe", "duplicate_meal"])
def test_swap_approval_requires_unambiguous_full_limits(defect):
    """批准目录与差异范围不能靠默认值补齐。"""
    row = {
        "recipe_version_id": str(uuid4()),
        "recipe_hash": "a" * 64,
        "dish_type_code": "synthetic_main",
        "allowed_meal_types": ["lunch"],
    }
    body = {"recipe_classifications": [row], "maximum_nutrient_differences": {k: "0" for k in NUTRIENTS}}
    if defect == "missing_limit":
        del body["maximum_nutrient_differences"]["sodium_mg"]
    elif defect == "extra_limit":
        body["maximum_nutrient_differences"]["sugar_g"] = "0"
    elif defect == "negative":
        body["maximum_nutrient_differences"]["energy_kcal"] = "-1"
    elif defect == "duplicate_recipe":
        body["recipe_classifications"].append(dict(row))
    else:
        row["allowed_meal_types"] = ["lunch", "lunch"]
    with pytest.raises(ValidationError):
        MealSwapRules.model_validate(body)


@pytest.mark.parametrize("field", ["grams", "reason", "nutrition", "safety_check", "professional_review"])
def test_safe_swap_cannot_accept_client_claim_or_change_portion(field):
    """业务请求不提交份量、解释原因、营养或批准结论。"""
    body = {
        "version": 1,
        "rule_code": "synthetic",
        "rule_version": 1,
        "profile_version": 1,
        "meal_type": "lunch",
        "dish_index": 0,
        "client_request_id": str(uuid4()),
        "recipe_version_id": str(uuid4()),
        field: "forged",
    }
    with pytest.raises(ValidationError):
        SafeSwapInput.model_validate(body)

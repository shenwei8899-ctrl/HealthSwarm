"""预算价格与自然月边界的独立合成 oracle。"""

from datetime import datetime, UTC
from decimal import Decimal

import pytest
from pydantic import ValidationError

from yuxi.services.health_ai_budget_service import budget_month
from yuxi.services.health_ai_budget_types import HealthAiPriceInput, round_charge


@pytest.mark.parametrize("value,expected", [("0.0000001", "0.000001"), ("0", "0.000000"), ("39.9999991", "40.000000")])
def test_money_rounds_up(value, expected):
    assert round_charge(Decimal(value)) == Decimal(expected)


def test_month_uses_shanghai_midnight():
    assert str(budget_month(datetime(2026, 10, 31, 15, 59, 59))) == "2026-10-01"
    assert str(budget_month(datetime(2026, 10, 31, 16, 0, 0))) == "2026-11-01"


@pytest.mark.parametrize(
    "changes",
    [
        {"currency": "USD"},
        {"fixed_cny_per_page": "NaN"},
        {"fixed_cny_per_page": "0"},
        {"upper_bound_verified": False},
        {"valid_until": datetime(2027, 1, 1)},
        {"fixed_cny_per_page": "40.000001"},
        {"input_cny_per_million": "1"},
    ],
)
def test_price_requires_complete_verified_cny_bound(changes):
    data = {
        "kind": "ocr",
        "ocr_endpoint": "https://synthetic.invalid/ocr",
        "fixed_cny_per_page": "0.1",
        "valid_until": datetime(2027, 1, 1, tzinfo=UTC),
        "evidence": "明确的合成上界证据仅用于测试",
        "upper_bound_verified": True,
        **changes,
    }
    with pytest.raises(ValidationError):
        HealthAiPriceInput.model_validate(data)


def test_deepseek_disabled_thinking_is_fixed_budget_target():
    """允许已验证的官方非思考参数，配置变化仍生成不同的计费目标。"""
    from yuxi.models.providers.cache import ModelInfo
    from yuxi.services.health_ai_budget_service import model_target
    from dataclasses import replace
    info=ModelInfo(provider_id="synthetic",model_id="deepseek-flash",model_type="chat",display_name="合成",api_key="synthetic-key",base_url="https://api.deepseek.com/v1",provider_type="openai",request_body_overrides={"thinking":{"type":"disabled"}})
    assert len(model_target(info))==64
    assert model_target(info)!=model_target(replace(info,request_body_overrides={}))
    assert model_target(info)!=model_target(replace(info,api_key="rotated-synthetic"))
    for overridden in [{"thinking":{"type":"disabled"},"max_tokens":99999},{"model":"other"},{"thinking":{"type":"enabled"}}]:
        with pytest.raises(Exception,match="budget_price_unavailable"):
            model_target(replace(info,request_body_overrides=overridden))
    with pytest.raises(Exception,match="budget_price_unavailable"):
        model_target(replace(info,base_url="https://synthetic.invalid/v1"))

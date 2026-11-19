"""预算价格与自然月边界的独立合成 oracle。"""

from datetime import datetime, UTC
from decimal import Decimal
from unittest.mock import AsyncMock

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


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "purpose,provider_id,model_id,exempt",
    [
        ("meal", "deepseek", "deepseek-flash", True),
        ("report", "deepseek", "deepseek-flash", False),
        ("meal", "deepseek", "deepseek-v4-pro", False),
        ("meal", "test-provider", "deepseek-flash", False),
    ],
)
async def test_photo_model_price_exception_covers_readiness_and_worker(
    monkeypatch, purpose, provider_id, model_id, exempt
):
    from yuxi.models.providers.cache import ModelInfo
    from yuxi.services import health_ai_budget_service as budget
    from yuxi.services.health_vision_types import HealthVisionError

    info = ModelInfo(
        provider_id=provider_id,
        model_id=model_id,
        model_type="chat",
        display_name="合成模型",
        api_key="synthetic-key",
        base_url="https://api.deepseek.com",
        provider_type="openai",
    )
    monkeypatch.setenv("HEALTH_AI_BUDGET_MODE", "strict")
    monkeypatch.setattr(budget.model_cache, "get_model_info", {info.spec: info}.get)
    repo = AsyncMock()
    repo.price.return_value = None
    monkeypatch.setattr(budget, "HealthAiBudgetRepository", lambda session: repo)
    reserve = AsyncMock(side_effect=HealthVisionError("budget_price_unavailable", "缺少价格", 503))
    monkeypatch.setattr(budget, "reserve", reserve)

    async def reserve_for_vision():
        if purpose == "meal":
            return await budget.reserve_meal_photo_model("synthetic-task", info.spec)
        return await budget.reserve_model(purpose, "synthetic-task", info.spec)

    readiness = await budget.model_budget_readiness(object(), info, purpose=purpose)
    assert readiness["available"] is exempt
    if exempt:
        reservation = await reserve_for_vision()
        assert reservation.model_info is info
        assert reservation.call_id is None
        assert reservation.price is None
        assert reservation.unpriced_output_limit == 2048
        reserve.assert_not_awaited()
        repo.price.assert_not_awaited()
        with pytest.raises(HealthVisionError, match="budget_price_unavailable"):
            await budget.reserve_model("meal", "synthetic-recipe-translation", info.spec)
        reserve.assert_awaited_once()
    else:
        assert readiness["reason_code"] == "budget_price_unavailable"
        with pytest.raises(HealthVisionError, match="budget_price_unavailable"):
            await reserve_for_vision()
        reserve.assert_awaited_once()
        repo.price.assert_awaited_once()


@pytest.mark.asyncio
async def test_photo_model_still_requires_valid_model_configuration(monkeypatch):
    from yuxi.services import health_ai_budget_service as budget
    from yuxi.services.health_vision_types import HealthVisionError

    missing_model = None
    monkeypatch.setattr(budget.model_cache, "get_model_info", lambda spec: missing_model)
    result = await budget.model_budget_readiness(object(), missing_model, purpose="meal")
    assert result["reason_code"] == "model_unavailable"
    with pytest.raises(HealthVisionError, match="model_unavailable"):
        await budget.reserve_meal_photo_model("synthetic-task", "deepseek:deepseek-flash")


@pytest.mark.asyncio
@pytest.mark.parametrize("has_ocr_approval", [True, False])
async def test_report_deepseek_fields_still_require_ocr_approval(monkeypatch, has_ocr_approval):
    from types import SimpleNamespace

    from yuxi.models.providers.cache import ModelInfo
    from yuxi.services import health_ai_budget_service as budget
    from yuxi.services.health_vision_types import HealthVisionError

    info = ModelInfo(
        provider_id="deepseek",
        model_id="deepseek-flash",
        model_type="chat",
        display_name="合成模型",
        api_key="synthetic-key",
        base_url="https://api.deepseek.com",
        provider_type="openai",
    )
    monkeypatch.setenv("HEALTH_AI_BUDGET_MODE", "strict")
    monkeypatch.setattr(budget.model_cache, "get_model_info", {info.spec: info}.get)
    repo = AsyncMock()
    repo.now.return_value = datetime(2026, 11, 18, 12)
    endpoint = "https://synthetic.invalid/ocr"
    ocr_price = SimpleNamespace(
        specification={
            "kind": "ocr",
            "billing_mode": "free_quota",
            "stops_when_quota_exhausted": True,
            "ocr_endpoint": endpoint,
            "fixed_cny_per_page": "0",
            "valid_until": datetime(2027, 1, 1, tzinfo=UTC),
            "evidence": "合成 OCR 免费额度仅用于测试",
            "upper_bound_verified": True,
        }
    )
    repo.price.return_value = ocr_price if has_ocr_approval else None
    monkeypatch.setattr(budget, "HealthAiBudgetRepository", lambda session: repo)
    reserve = AsyncMock(side_effect=HealthVisionError("budget_price_unavailable", "缺少价格", 503))
    monkeypatch.setattr(budget, "reserve", reserve)

    readiness = await budget.report_budget_readiness(
        object(), info, {"api_url": endpoint, "api_token": "synthetic-ocr-token"}
    )
    assert readiness["available"] is has_ocr_approval
    assert readiness["reason_code"] == (None if has_ocr_approval else "budget_price_unavailable")
    repo.price.assert_awaited_once_with(budget.ocr_target(endpoint, "synthetic-ocr-token"), repo.now.return_value)

    reservation = await budget.reserve_report_field_model("synthetic-fields", info.spec)
    assert reservation.model_info is info
    assert reservation.call_id is None and reservation.price is None
    assert reservation.unpriced_output_limit == 8192
    reserve.assert_not_awaited()

    with pytest.raises(HealthVisionError, match="budget_price_unavailable"):
        await budget.reserve_model("report", "synthetic-other-report-purpose", info.spec)
    reserve.assert_awaited_once()

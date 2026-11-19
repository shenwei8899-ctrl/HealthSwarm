"""参考预算放行未知费用，严格预算及模型绑定继续拒绝错误配置。"""

from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from yuxi.services import health_ai_budget_service as budget
from yuxi.services.health_vision_types import HealthVisionError


@pytest.fixture
def model_info():
    return SimpleNamespace(
        spec="synthetic:model",
        api_key="synthetic",
        provider_type="openai",
        request_body_overrides={},
        model_id="model",
        provider_id="synthetic",
        base_url="https://synthetic.invalid/v1",
        headers={},
        extra={},
    )


@pytest.mark.asyncio
async def test_advisory_missing_price_never_creates_fake_reservation(monkeypatch, model_info):
    monkeypatch.setenv("HEALTH_AI_BUDGET_MODE", "advisory")
    monkeypatch.setattr(budget.model_cache, "get_model_info", lambda _: model_info)

    account = SimpleNamespace(occupied_cny=Decimal(40), blocked=False)
    repo = SimpleNamespace(
        lock=AsyncMock(),
        call=AsyncMock(return_value=None),
        now=AsyncMock(return_value=datetime(2026, 10, 26)),
        month=AsyncMock(return_value=account),
    )

    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

    monkeypatch.setattr(budget.pg_manager, "get_async_session_context", Session)
    monkeypatch.setattr(budget, "HealthAiBudgetRepository", lambda _: repo)
    assert (await budget.model_budget_readiness(None, model_info, purpose="consultation"))["available"]
    reservation = await budget.reserve_model("consultation", "synthetic-run", model_info.spec)
    assert reservation.call_id is None and reservation.price is None
    assert reservation.model_info is model_info
    assert account.blocked and account.occupied_cny == Decimal(40)
    await budget.settle(reservation, {"input_tokens": 12, "output_tokens": 7})


@pytest.mark.asyncio
async def test_strict_missing_price_still_refuses(monkeypatch, model_info):
    monkeypatch.setenv("HEALTH_AI_BUDGET_MODE", "strict")
    repo = SimpleNamespace(now=AsyncMock(return_value=datetime(2026, 10, 26)), price=AsyncMock(return_value=None))
    monkeypatch.setattr(budget, "HealthAiBudgetRepository", lambda _: repo)
    result = await budget.model_budget_readiness(None, model_info, purpose="indicator_review")
    assert not result["available"] and result["reason_code"] == "budget_price_unavailable"


@pytest.mark.asyncio
async def test_default_mode_skips_ledger_for_all_health_purposes(monkeypatch, model_info):
    """就绪检查、实际模型和 OCR 调用均不读取审批表。"""
    monkeypatch.delenv("HEALTH_AI_BUDGET_MODE", raising=False)
    monkeypatch.setattr(budget.model_cache, "get_model_info", lambda _: model_info)
    ledger = AsyncMock(side_effect=AssertionError("关闭模式不访问人民币账本"))
    monkeypatch.setattr(budget.pg_manager, "get_async_session_context", ledger)
    monkeypatch.setattr(budget, "HealthAiBudgetRepository", ledger)

    assert budget.budget_mode() == "off"
    model_info.request_body_overrides = {"enable_thinking": False}
    for purpose in budget.HEALTH_BUDGET_PURPOSES:
        assert (await budget.model_budget_readiness(None, model_info, purpose=purpose))["available"]
        reservation = await budget.reserve_model(purpose, "synthetic-task", model_info.spec)
        assert reservation.call_id is None and reservation.price is None and reservation.model_info is model_info
        await budget.settle(reservation, {"input_tokens": 12, "output_tokens": 7})

    report = await budget.reserve_report_field_model("synthetic-report", model_info.spec)
    meal = await budget.reserve_meal_photo_model("synthetic-meal", model_info.spec)
    assert report.unpriced_output_limit == 8192 and meal.unpriced_output_limit == 2048
    for reservation in (report, meal, await budget.reserve("report", "synthetic-ocr", "synthetic-target")):
        assert reservation.call_id is None and reservation.price is None
        await budget.settle(reservation, fixed_charge=True)

    assert (await budget.report_budget_readiness(None, model_info, {"api_token": "synthetic"}))["available"]
    assert (await budget.report_budget_readiness(None, model_info, {}))["reason_code"] == "ocr_credentials_missing"
    model_info.request_body_overrides = {"max_tokens": 100_000}
    with pytest.raises(HealthVisionError, match="model_unavailable"):
        await budget.reserve_model("meal", "synthetic-menu", model_info.spec)
    model_info.request_body_overrides = {}
    model_info.api_key = ""
    assert (await budget.model_budget_readiness(None, model_info, purpose="meal"))["reason_code"] == "model_unavailable"
    with pytest.raises(HealthVisionError, match="model_unavailable"):
        await budget.reserve_meal_photo_model("synthetic-meal", model_info.spec)
    ledger.assert_not_called()


@pytest.mark.asyncio
async def test_strict_consultation_skips_approval_without_freezing_the_ledger(monkeypatch, model_info):
    monkeypatch.setenv("HEALTH_AI_BUDGET_MODE", "strict")
    monkeypatch.setattr(budget.model_cache, "get_model_info", lambda _: model_info)
    reserve = AsyncMock(side_effect=HealthVisionError("budget_price_unavailable", "缺少价格", 503))
    monkeypatch.setattr(budget, "reserve", reserve)

    assert (await budget.model_budget_readiness(None, model_info, purpose="consultation"))["available"]
    reservation = await budget.reserve_model("consultation", "synthetic-run", model_info.spec)
    assert reservation.call_id is None and reservation.price is None
    assert reservation.model_info is model_info and reservation.unpriced_output_limit == 4096
    reserve.assert_not_awaited()

    with pytest.raises(HealthVisionError, match="budget_price_unavailable"):
        await budget.reserve_model("indicator_review", "synthetic-run", model_info.spec)
    reserve.assert_awaited_once()

    with pytest.raises(HealthVisionError, match="budget_context_invalid"):
        await budget.reserve_model("consultation", "", model_info.spec)
    model_info.api_key = ""
    with pytest.raises(HealthVisionError, match="budget_price_unavailable"):
        await budget.reserve_model("consultation", "synthetic-run", model_info.spec)


@pytest.mark.asyncio
async def test_advisory_does_not_accept_missing_model_credentials(monkeypatch, model_info):
    monkeypatch.setenv("HEALTH_AI_BUDGET_MODE", "advisory")
    model_info.api_key = ""
    assert not (await budget.model_budget_readiness(None, model_info, purpose="consultation"))["available"]


def test_advisory_model_has_output_limit_and_no_sdk_retry(monkeypatch, model_info):
    from yuxi.models import chat

    monkeypatch.setattr(budget.model_cache, "get_model_info", lambda _: model_info)
    monkeypatch.setattr(chat, "load_chat_model_from_info", lambda info, **kwargs: kwargs)
    reservation = budget.BudgetReservation(None, None, model_info)
    actual = budget.reserved_chat_model(reservation)
    assert actual["max_tokens"] == 2048 and actual["max_retries"] == 0
    monkeypatch.setattr(budget.model_cache, "get_model_info", lambda _: None)
    with pytest.raises(HealthVisionError, match="policy_changed"):
        budget.reserved_chat_model(reservation)


@pytest.mark.asyncio
async def test_advisory_status_keeps_unknown_money_null_even_with_old_block(monkeypatch):
    monkeypatch.setenv("HEALTH_AI_BUDGET_MODE", "advisory")
    repo = SimpleNamespace(
        lock=AsyncMock(),
        now=AsyncMock(return_value=datetime(2026, 10, 26)),
        month=AsyncMock(return_value=SimpleNamespace(occupied_cny=Decimal(40), blocked=True)),
        opening=AsyncMock(return_value=None),
        calls=AsyncMock(return_value=[]),
    )

    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

    monkeypatch.setattr(budget.pg_manager, "get_async_session_context", Session)
    monkeypatch.setattr(budget, "HealthAiBudgetRepository", lambda _: repo)
    result = await budget.budget_status()
    assert result["mode"] == "advisory" and not result["blocked"]
    assert result["limit_cny"] is result["occupied_cny"] is result["remaining_cny"] is None
    assert result["reference_budget_cny"] is None
    assert result["advisory_purposes"] == ["consultation", "indicator_review", "diet_analysis"]


@pytest.mark.parametrize("value", ["", "false", "unlimited", "ADVISORY"])
def test_unknown_mode_never_silently_disables_strict_budget(monkeypatch, value):
    monkeypatch.setenv("HEALTH_AI_BUDGET_MODE", value)
    with pytest.raises(ValueError):
        budget.budget_mode()

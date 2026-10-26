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
    assert (await budget.model_budget_readiness(None, model_info))["available"]
    reservation = await budget.reserve_model("consultation", "synthetic-run", model_info.spec)
    assert reservation.call_id is None and reservation.price is None
    assert reservation.model_info is model_info
    assert account.blocked and account.occupied_cny == Decimal(40)
    await budget.settle(reservation, {"input_tokens": 12, "output_tokens": 7})


@pytest.mark.asyncio
async def test_strict_missing_price_still_refuses(monkeypatch, model_info):
    monkeypatch.delenv("HEALTH_AI_BUDGET_MODE", raising=False)
    repo = SimpleNamespace(now=AsyncMock(return_value=datetime(2026, 10, 26)), price=AsyncMock(return_value=None))
    monkeypatch.setattr(budget, "HealthAiBudgetRepository", lambda _: repo)
    result = await budget.model_budget_readiness(None, model_info)
    assert not result["available"] and result["reason_code"] == "budget_price_unavailable"


@pytest.mark.asyncio
async def test_advisory_does_not_accept_missing_model_credentials(monkeypatch, model_info):
    monkeypatch.setenv("HEALTH_AI_BUDGET_MODE", "advisory")
    model_info.api_key = ""
    assert not (await budget.model_budget_readiness(None, model_info))["available"]


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
    assert result["reference_budget_cny"] == "40"


@pytest.mark.parametrize("value", ["", "false", "unlimited", "ADVISORY"])
def test_unknown_mode_never_silently_disables_strict_budget(monkeypatch, value):
    monkeypatch.setenv("HEALTH_AI_BUDGET_MODE", value)
    with pytest.raises(ValueError):
        budget.budget_mode()

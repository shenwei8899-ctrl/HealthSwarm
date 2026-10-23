"""仅供供应商协议 unit 隔离数据库，预算本身由独立 PG 套件验证。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from yuxi.services import health_ai_budget_service as budget
from yuxi.models.providers.cache import model_cache


@pytest.fixture
def synthetic_budget(monkeypatch):
    """保留请求参数约束，协议测试不访问真实预算或供应商。"""
    reservation = budget.BudgetReservation("synthetic-unit", SimpleNamespace(max_output_tokens=1000))

    async def reserve_model(purpose, owner_id, spec):
        """协议测试仍绑定已配置的合成模型实例。"""
        return budget.BudgetReservation("synthetic-unit", reservation.price, model_cache.get_model_info(spec))

    monkeypatch.setattr(budget, "reserve_model", reserve_model)
    monkeypatch.setattr(budget, "reserve", AsyncMock(return_value=reservation))
    monkeypatch.setattr(budget, "settle", AsyncMock())


def stub_agent_budget(monkeypatch, model):
    """工具绑定 unit 使用原合成模型，保留 middleware 与授权路径。"""
    reserve = AsyncMock(return_value=SimpleNamespace(call_id="synthetic-unit"))
    monkeypatch.setattr(budget, "reserve_model", reserve)
    monkeypatch.setattr(budget, "reserved_chat_model", lambda *args, **kwargs: model)
    monkeypatch.setattr(budget, "settle", AsyncMock())
    return reserve

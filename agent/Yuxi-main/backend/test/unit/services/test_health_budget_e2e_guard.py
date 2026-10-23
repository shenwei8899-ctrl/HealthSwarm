"""测试预算准备器拒绝把合成价格写向非隔离环境。"""

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from test.support import health_budget_e2e as helper


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid", ["flag", "api", "database", "provider"])
async def test_synthetic_budget_rejects_untrusted_environment_before_writes(monkeypatch, invalid):
    """任一真实边界不匹配时，价格和期初HTTP写入均不能发生。"""
    monkeypatch.setenv("HEALTH_CONSULTATION_E2E_ISOLATED", "false" if invalid == "flag" else "true")
    client = SimpleNamespace(
        base_url="https://external.invalid" if invalid == "api" else "http://localhost:5050", post=AsyncMock()
    )

    @asynccontextmanager
    async def session():
        """只模拟读取到的数据库身份，不连接外部资源。"""
        yield SimpleNamespace(
            scalar=AsyncMock(return_value="production" if invalid == "database" else "health_consultation_e2e")
        )

    monkeypatch.setattr(helper.pg_manager, "get_async_session_context", session)
    monkeypatch.setattr(helper.model_cache, "refresh", Mock())
    monkeypatch.setattr(
        helper,
        "current_health_model_info",
        AsyncMock(
            return_value=SimpleNamespace(
                base_url="https://external.invalid/v1", provider_id="health-replay-test", api_key="synthetic-key"
            )
        ),
    )
    with pytest.raises(AssertionError):
        await helper.approve_synthetic_budget(client, {}, "health-replay-test:synthetic")
    client.post.assert_not_awaited()

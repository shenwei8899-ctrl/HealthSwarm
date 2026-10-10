"""餐单合成夹具在明确隔离标记和真实数据库边界失败时关闭入口。"""

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from test.support import health_miniapp_meal_plan_fixture as fixture

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]


async def test_missing_isolation_marker_rejects_before_database_or_http(monkeypatch):
    """默认环境不能靠固定文件路径误开健康夹具的数据库入口。"""
    monkeypatch.delenv("HEALTH_CONSULTATION_E2E_ISOLATED", raising=False)
    manager = SimpleNamespace(initialize=Mock())
    monkeypatch.setattr(fixture, "pg_manager", manager)
    http_client = Mock()
    monkeypatch.setattr(fixture.httpx, "AsyncClient", http_client)

    with pytest.raises(RuntimeError, match="隔离健康验收槽位"):
        await fixture.require_isolated_slot()

    manager.initialize.assert_not_called()
    http_client.assert_not_called()


async def test_main_database_rejects_before_schema_or_http_even_with_marker(monkeypatch):
    """实际PG数据库名拥有边界，环境标记不能授权主库写入。"""
    monkeypatch.setenv("HEALTH_CONSULTATION_E2E_ISOLATED", "true")
    session = SimpleNamespace(scalar=AsyncMock(return_value="yuxi"))

    @asynccontextmanager
    async def database_session():
        """模拟真实数据库名查询，避免单测连接任何服务。"""
        yield session

    manager = SimpleNamespace(
        initialize=Mock(), get_async_session_context=database_session, require_current_schema=AsyncMock()
    )
    monkeypatch.setattr(fixture, "pg_manager", manager)
    http_client = Mock()
    monkeypatch.setattr(fixture.httpx, "AsyncClient", http_client)

    with pytest.raises(RuntimeError, match="禁止操作主数据库"):
        await fixture.require_isolated_slot()

    manager.require_current_schema.assert_not_called()
    http_client.assert_not_called()

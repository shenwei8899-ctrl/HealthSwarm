"""每日咨询日期列表只依赖当前成员访问权限。"""

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from yuxi.services import health_daily_service as service
from yuxi.services.health_vision_types import HealthVisionError


@pytest.mark.asyncio
@pytest.mark.parametrize("authorized", [True, False])
async def test_daily_history_uses_member_access_without_extra_processing_consent(monkeypatch, authorized):
    """有成员权限直接读取，撤回成员权限后仍拒绝查询。"""

    @asynccontextmanager
    async def session_context():
        yield SimpleNamespace()

    authorize = AsyncMock(side_effect=None if authorized else HealthVisionError("not_found", "无权访问", 404))
    history = AsyncMock(return_value=[])
    monkeypatch.setattr(service.pg_manager, "get_async_session_context", session_context)
    monkeypatch.setattr(service.HealthVisionRepository, "authorize", authorize)
    monkeypatch.setattr(service.HealthDailyRepository, "history", history)

    if authorized:
        assert await service.daily_history("actor", "member") == {"days": [], "next_before": None}
        history.assert_awaited_once_with("actor", "member", None)
    else:
        with pytest.raises(HealthVisionError) as denied:
            await service.daily_history("actor", "member")
        assert denied.value.code == "not_found" and denied.value.status == 404
        history.assert_not_awaited()
    authorize.assert_awaited_once_with("member", "actor", "ai_use")

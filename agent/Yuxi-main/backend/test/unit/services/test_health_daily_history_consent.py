"""每日咨询日期列表也遵守当前咨询用途同意。"""

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from yuxi.services import health_daily_service as service
from yuxi.services.health_vision_types import HealthVisionError


@pytest.mark.asyncio
async def test_revoked_consultation_consent_rejects_before_daily_history_query(monkeypatch):
    @asynccontextmanager
    async def session_context():
        yield SimpleNamespace()

    authorize = AsyncMock()
    consent = AsyncMock(side_effect=HealthVisionError("consent_required", "请先同意当前咨询用途", 403))
    history = AsyncMock(side_effect=AssertionError("不得查询已撤回用途的日期列表"))
    monkeypatch.setattr(service.pg_manager, "get_async_session_context", session_context)
    monkeypatch.setattr(service.HealthVisionRepository, "authorize", authorize)
    monkeypatch.setattr(service.HealthConsultationRepository, "require_active_consultation_consent", consent)
    monkeypatch.setattr(service.HealthDailyRepository, "history", history)

    with pytest.raises(HealthVisionError) as denied:
        await service.daily_history("actor", "member")

    assert denied.value.code == "consent_required" and denied.value.status == 403
    authorize.assert_awaited_once_with("member", "actor", "ai_use")
    consent.assert_awaited_once_with("member", "actor")
    history.assert_not_awaited()

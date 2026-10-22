"""交接只使用源 Run 实际读取的冻结范围，不扩大到最新自然日。"""

from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from yuxi.repositories.health_task_repository import HealthTaskRepository
from yuxi.services import health_handoff_service as service
from yuxi.services import health_indicator_review_service, health_task_service
from yuxi.services.health_vision_types import HealthVisionError


@pytest.mark.asyncio
@pytest.mark.parametrize("count", [0, 2])
async def test_handoff_rejects_missing_or_ambiguous_indicator_receipt(count):
    """一般科普未读指标，或多次读取范围不同，都不得猜测交接范围。"""
    session = SimpleNamespace(scalars=AsyncMock(return_value=[object()] * count))
    with pytest.raises(HealthVisionError) as error:
        await HealthTaskRepository(session).indicator_receipt("source-run", "blood_glucose")
    assert error.value.status == 409
    query = session.scalars.await_args.args[0]
    assert "source-run" in query.compile().params.values()


@pytest.mark.asyncio
@pytest.mark.parametrize("changed", [False, True])
async def test_handoff_freezes_historical_period_and_rejects_changed_facts(monkeypatch, changed):
    """无需冻结系统时间：源回执明显早于今日，断言读取仍使用其起止日期。"""
    request = SimpleNamespace(uid="actor", agent_slug="health-blood-glucose")
    binding = SimpleNamespace(member_id="member", indicator_selection=None)
    run = SimpleNamespace(id="source-run")
    task = SimpleNamespace(
        execution_status="completed",
        result=object(),
        final_message_id=10,
        model_dump=lambda **_: {"run_id": run.id, "final_message_id": 10},
    )
    receipt = SimpleNamespace(start_date=date(2025, 1, 1), end_date=date(2025, 1, 7), payload_hash="original")
    monkeypatch.setattr(service.AgentRunRequestRepository, "get_by_request_id", AsyncMock(return_value=request))
    monkeypatch.setattr(HealthTaskRepository, "request_context", AsyncMock(return_value=(request, binding, run)))
    monkeypatch.setattr(HealthTaskRepository, "indicator_receipt", AsyncMock(return_value=receipt))
    monkeypatch.setattr(health_task_service, "read_health_task_in_session", AsyncMock(return_value=task))
    period = {"start_date": "2025-01-01", "end_date": "2025-01-07", "timezone": "Asia/Shanghai"}
    read = AsyncMock(
        return_value={"source_hash": "changed" if changed else "original", "period": period, "records": []}
    )
    monkeypatch.setattr(health_indicator_review_service, "read_indicator_in_session", read)
    if changed:
        with pytest.raises(HealthVisionError) as error:
            await service.handoff_source_in_session(object(), "actor", "request")
        assert error.value.status == 410
    else:
        result = await service.handoff_source_in_session(object(), "actor", "request")
        assert result["summary"]["period"] == period
        assert result["target_agent"] == "health-consultation"
    assert read.await_args.kwargs["period"] == period

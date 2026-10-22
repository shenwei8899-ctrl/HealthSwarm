"""每日安排恢复不能挪用相邻 Run 或其他成员选择的回执。"""

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from test.unit.services.test_health_initial_meal_generation import initial_fixture
from yuxi.services.daily_arrangement_service import authorize_daily_agent_result
from yuxi.services.health_vision_types import HealthVisionError


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "change",
    ["missing_run", "uid", "agent_slug", "status", "request_id", "processing", "selection"],
)
async def test_checkpoint_rejects_invalid_run_or_different_selection(monkeypatch, change):
    """持久恢复边界逐项拒绝错误身份、未完成运行、旧处理快照和替换来源。"""
    from yuxi.services import health_consultation_service

    selected = initial_fixture()[0].model_dump(mode="json")
    run = SimpleNamespace(
        uid="owner",
        agent_slug="health-meal-planner",
        status="completed",
        request_id="request",
        conversation_thread_id="thread",
        input_payload={"health_processing": {"initial_selection_hash": "frozen"}},
    )
    binding = SimpleNamespace(initial_planner_selection={"selection": deepcopy(selected)})
    require = AsyncMock(return_value=(binding, {}))
    monkeypatch.setattr(health_consultation_service, "require_consultation", require)
    if change == "missing_run":
        run = None
    elif change == "processing":
        run.input_payload = {}
    elif change == "selection":
        binding.initial_planner_selection["selection"]["plan_date"] = "2026-01-01"
    else:
        setattr(run, change, "other")
    db = SimpleNamespace(get=AsyncMock(return_value=run))
    with pytest.raises(HealthVisionError) as error:
        await authorize_daily_agent_result(
            db, "owner", {"initial": selected, "agent_result": {"run_id": "run", "task_key": "request"}}
        )
    assert error.value.code == "source_invalidated"
    if change == "selection":
        assert require.await_args.kwargs == {
            "expected": {"initial_selection_hash": "frozen"},
            "lock": True,
        }
    else:
        require.assert_not_awaited()

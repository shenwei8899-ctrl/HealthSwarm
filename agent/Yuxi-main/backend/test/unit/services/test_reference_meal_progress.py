"""参考餐单只投影固定工具阶段与固定失败说明。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import json
import pytest

from yuxi.services import agent_run_service
from yuxi.services.agent_run_service import _public_health_error, _public_health_run_event
from yuxi.services.health_answer_stream import health_catalog_tool_phase
from yuxi.services.run_worker import _map_chunk_to_run_event


def test_reference_tool_phases_expose_only_fixed_labels():
    """工具参数、正文和失败输出不能进入公开进度。"""
    for name, started, finished in (
        ("search_reference_recipes", "searching_recipes", "reading_recipes"),
        ("read_reference_recipe", "reading_recipes", "saving_meal_plan"),
        ("save_reference_meal_plan", "saving_meal_plan", "validating"),
    ):
        event = {"method": "tools", "data": {"event": "tool-started", "tool_name": name, "input": "PRIVATE"}}
        assert health_catalog_tool_phase(event) == started
        event["data"] = {"event": "tool-finished", "tool_name": name, "output": {"content": "PRIVATE"}}
        assert health_catalog_tool_phase(event) == finished
        event["data"]["output"]["status"] = "error"
        assert health_catalog_tool_phase(event) is None


def test_reference_progress_survives_worker_event_and_public_projection():
    """真实工具阶段经 worker 事件映射后仍有固定 phase，不含工具正文。"""
    phase = health_catalog_tool_phase(
        {"method": "tools", "data": {"event": "tool-started", "tool_name": "read_reference_recipe", "input": "PRIVATE"}}
    )
    kind, payload = _map_chunk_to_run_event({"status": "health_progress", "phase": phase, "input": "PRIVATE"})
    run = SimpleNamespace(id="run", request_id="request", conversation_thread_id="thread", status="running")
    event = _public_health_run_event(run, kind, {"payload": payload})
    assert event["payload"]["chunk"]["phase"] == "reading_recipes"
    assert event["payload"]["chunk"]["message"] == "正在核对菜谱原文和食材"
    assert "PRIVATE" not in str(event)


@pytest.mark.asyncio
async def test_planner_run_sse_keeps_fixed_phase_with_verbose_false(monkeypatch):
    """实际 Run SSE 路由保留配餐阶段，拒绝原始工具正文。"""
    run = SimpleNamespace(
        id="run",
        request_id="request",
        conversation_thread_id="thread",
        agent_slug="health-meal-planner",
        status="completed",
    )
    monkeypatch.setattr(agent_run_service, "_load_stream_run_for_user", AsyncMock(return_value=run))
    monkeypatch.setattr(
        agent_run_service,
        "list_run_stream_events",
        AsyncMock(
            return_value=[
                {
                    "seq": "1-0",
                    "event_type": "custom",
                    "payload": {
                        "event": "custom",
                        "payload": {
                            "name": "yuxi.health_progress",
                            "chunk": {
                                "phase": "reading_recipes",
                                "message": "PRIVATE",
                                "input": "PRIVATE",
                            },
                        },
                    },
                },
                {"seq": "2-0", "event_type": "end", "payload": {"event": "end", "payload": {"status": "completed"}}},
            ]
        ),
    )
    frames = [
        frame
        async for frame in agent_run_service.stream_agent_run_events(
            run_id="run",
            after_seq="0-0",
            current_uid="actor",
            verbose=False,
        )
    ]
    public = json.loads(next(line[6:] for line in frames[0].splitlines() if line.startswith("data: ")))
    assert public["payload"]["chunk"]["phase"] == "reading_recipes"
    assert public["payload"]["chunk"]["message"] == "正在核对菜谱原文和食材"
    assert "PRIVATE" not in "".join(frames)


def test_translation_failure_has_specific_public_error_without_private_details():
    """失败终态只显示服务端固定文案。"""
    result = _public_health_error("reference_translation_correction_invalid")
    assert result == {
        "type": "reference_translation_correction_invalid",
        "message": "餐单译文修正未通过，请重新生成餐单",
    }
    assert _public_health_error("PRIVATE")["type"] == "health_execution_failed"


@pytest.mark.parametrize(
    "code", ["reference_recipe_repeated", "reference_menu_repeated", "reference_variety_exhausted"]
)
def test_variety_failure_has_specific_fixed_public_error(code):
    result = _public_health_error(code)
    assert result["type"] == code
    assert "重复" in result["message"] or "近期餐单" in result["message"]

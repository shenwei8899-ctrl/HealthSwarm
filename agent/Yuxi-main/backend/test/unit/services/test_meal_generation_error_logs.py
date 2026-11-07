"""配餐失败日志只记录可定位的代码与字段路径。"""

import json
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

from yuxi.services import run_worker, tool_message_audit_service


@pytest.mark.asyncio
async def test_failed_run_logs_persisted_reason_once_without_private_message(monkeypatch):
    records = []

    @asynccontextmanager
    async def session():
        yield object()

    class Repository:
        def __init__(self, _db):
            pass

        async def set_terminal_status(self, _run_id, **kwargs):
            return (
                SimpleNamespace(
                    id="run-1",
                    request_id="request-1",
                    agent_slug="health-meal-planner",
                    status="failed",
                    error_type=kwargs["error_type"],
                ),
                True,
            )

        async def cancel_active_execution_tree_descendants(self, _run):
            return []

    monkeypatch.setattr(run_worker.pg_manager, "get_async_session_context", session)
    monkeypatch.setattr(run_worker, "AgentRunRepository", Repository)
    monkeypatch.setattr(run_worker, "publish_cancel_signals", lambda _ids: _async_none())
    monkeypatch.setattr(run_worker.logger, "warning", lambda message, *args: records.append(message.format(*args)))

    await run_worker.mark_run_terminal(
        "run-1",
        "failed",
        error_type="planner_output_invalid",
        error_message="private-health-sentinel",
        worker_id="worker-1",
    )

    log = json.loads(records[-1].removeprefix("agent_run_failed "))
    assert log == {
        "event": "agent_run_failed",
        "run_id": "run-1",
        "request_id": "request-1",
        "agent": "health-meal-planner",
        "error_code": "planner_output_invalid",
    }
    assert "private-health-sentinel" not in records[-1]

    def broken_log(*_args):
        raise RuntimeError("log sink unavailable")

    monkeypatch.setattr(run_worker.logger, "warning", broken_log)
    transition = await run_worker.mark_run_terminal(
        "run-1", "failed", error_type="planner_output_invalid", worker_id="worker-1"
    )
    assert transition.status == "failed" and transition.changed


@pytest.mark.asyncio
async def test_completed_run_does_not_emit_failure_log(monkeypatch):
    records = []

    @asynccontextmanager
    async def session():
        yield object()

    class Repository:
        def __init__(self, _db):
            pass

        async def set_terminal_status(self, _run_id, **_kwargs):
            return SimpleNamespace(status="completed"), True

        async def cancel_active_execution_tree_descendants(self, _run):
            return []

    monkeypatch.setattr(run_worker.pg_manager, "get_async_session_context", session)
    monkeypatch.setattr(run_worker, "AgentRunRepository", Repository)
    monkeypatch.setattr(run_worker, "publish_cancel_signals", lambda _ids: _async_none())
    monkeypatch.setattr(run_worker.logger, "warning", lambda *args: records.append(args))

    await run_worker.mark_run_terminal("run-1", "completed", worker_id="worker-1")
    assert records == []


@pytest.mark.asyncio
async def test_expired_worker_lease_logs_failed_run_reason(monkeypatch):
    records = []

    @asynccontextmanager
    async def session():
        yield object()

    class Repository:
        def __init__(self, _db):
            pass

        async def reconcile_expired_leases(self, **_kwargs):
            run = SimpleNamespace(
                id="run-expired",
                request_id="request-expired",
                agent_slug="health-meal-planner",
                error_type="worker_lease_expired",
                status="failed",
            )
            return [run], []

    monkeypatch.setattr(run_worker.pg_manager, "get_async_session_context", session)
    monkeypatch.setattr(run_worker, "AgentRunRepository", Repository)
    monkeypatch.setattr(run_worker, "publish_cancel_signals", lambda _ids: _async_none())
    monkeypatch.setattr(run_worker, "reconcile_pending_runtime_cleanups", lambda: _async_none())
    monkeypatch.setattr(run_worker.logger, "warning", lambda message, *args: records.append(message.format(*args)))

    assert await run_worker.reconcile_expired_run_leases() == ["run-expired"]
    log = json.loads(records[-1].removeprefix("agent_run_failed "))
    assert log["run_id"] == "run-expired"
    assert log["error_code"] == "worker_lease_expired"


async def _async_none():
    return None


@pytest.mark.asyncio
async def test_failed_tool_logs_safe_reason_and_field_paths(monkeypatch):
    records = []
    finished = False

    @asynccontextmanager
    async def session():
        yield object()

    class Repository:
        def __init__(self, _db):
            pass

        async def start(self, **_kwargs):
            return SimpleNamespace(execution_status="failed" if finished else "running"), not finished

        async def fail(self, **_kwargs):
            nonlocal finished
            finished = True
            return object()

    monkeypatch.setattr(tool_message_audit_service.pg_manager, "get_async_session_context", session)
    monkeypatch.setattr(tool_message_audit_service, "ToolMessageAuditRepository", Repository)
    monkeypatch.setattr(
        tool_message_audit_service.logger, "warning", lambda message, *args: records.append(message.format(*args))
    )
    collector = tool_message_audit_service.ToolMessageAuditCollector(
        run_id="run-1", request_id="request-1", thread_id="thread-1", worker_id="worker-1"
    )
    await collector.consume(
        {
            "method": "tools",
            "seq": 1,
            "timestamp": 1_777_000_123_456,
            "data": {
                "event": "tool-started",
                "tool_call_id": "call-1",
                "tool_name": "save_reference_meal_plan",
                "input": {},
            },
        }
    )
    failed_output = {
        "status": "error",
        "content": json.dumps(
            {
                "error_code": "reference_purchase_coverage_invalid",
                "message": "private-health-sentinel",
                "issues": {
                    "missing_ingredient_paths": [
                        "meals[0].dishes[1].ingredients[2]",
                        "meals[0].dishes[1].ingredients[2].private-health-sentinel",
                    ],
                    "counts": {"missing_ingredient_paths": 1},
                },
            }
        ),
    }
    await collector.consume(
        {
            "method": "tools",
            "seq": 2,
            "timestamp": 1_777_000_123_789,
            "data": {
                "event": "tool-finished",
                "tool_call_id": "call-1",
                "output": failed_output,
            },
        }
    )

    log = json.loads(records[-1].removeprefix("agent_tool_failed "))
    assert log["error_code"] == "reference_purchase_coverage_invalid"
    assert log["run_id"] == "run-1" and log["tool_call_id"] == "call-1"
    assert log["issues"]["missing_ingredient_paths"] == ["meals[0].dishes[1].ingredients[2]"]
    assert log["issue_counts"] == {"missing_ingredient_paths": 1}
    assert "private-health-sentinel" not in records[-1]

    await collector.consume(
        {
            "method": "tools",
            "seq": 2,
            "timestamp": 1_777_000_123_789,
            "data": {"event": "tool-finished", "tool_call_id": "call-1", "output": failed_output},
        }
    )
    assert len(records) == 1

    await collector.consume(
        {
            "method": "tools",
            "seq": 1,
            "timestamp": 1_777_000_123_456,
            "data": {
                "event": "tool-started",
                "tool_call_id": "call-1",
                "tool_name": "save_reference_meal_plan",
                "input": {},
            },
        }
    )
    await collector.consume(
        {
            "method": "tools",
            "seq": 2,
            "timestamp": 1_777_000_123_789,
            "data": {"event": "tool-finished", "tool_call_id": "call-1", "output": failed_output},
        }
    )
    assert len(records) == 1


@pytest.mark.asyncio
async def test_failed_tool_log_rejects_untrusted_identifiers(monkeypatch):
    records = []

    @asynccontextmanager
    async def session():
        yield object()

    class Repository:
        def __init__(self, _db):
            pass

        async def start(self, **_kwargs):
            return object(), True

        async def fail(self, **_kwargs):
            return object()

    monkeypatch.setattr(tool_message_audit_service.pg_manager, "get_async_session_context", session)
    monkeypatch.setattr(tool_message_audit_service, "ToolMessageAuditRepository", Repository)
    monkeypatch.setattr(
        tool_message_audit_service.logger, "warning", lambda message, *args: records.append(message.format(*args))
    )
    collector = tool_message_audit_service.ToolMessageAuditCollector(
        run_id="run-1", request_id="request-1", thread_id="thread-1", worker_id="worker-1"
    )
    unsafe = "private-health-sentinel with spaces"
    await collector.consume(
        {
            "method": "tools",
            "seq": 1,
            "timestamp": 1_777_000_123_456,
            "data": {"event": "tool-started", "tool_call_id": unsafe, "tool_name": unsafe, "input": {}},
        }
    )
    await collector.consume(
        {
            "method": "tools",
            "seq": 2,
            "timestamp": 1_777_000_123_789,
            "data": {
                "event": "tool-finished",
                "tool_call_id": unsafe,
                "output": {"status": "error", "content": "private-health-sentinel"},
            },
        }
    )
    log = json.loads(records[-1].removeprefix("agent_tool_failed "))
    assert log["tool_call_id"] == "invalid"
    assert log["tool"] == "unknown"
    assert "private-health-sentinel" not in records[-1]


def test_failed_tool_log_cannot_break_after_persistence(monkeypatch):
    records = []
    monkeypatch.setattr(
        tool_message_audit_service.logger,
        "warning",
        lambda message, *args: records.append(message.format(*args)),
    )
    tool_message_audit_service.log_failed_tool_event(
        run_id="run-1",
        request_id="request-1",
        tool_call_id="call-1",
        tool_name="search_reference_recipes",
        content="[" * 5000 + "0" + "]" * 5000,
        duration_ms=100,
    )
    assert len(records) == 1
    assert json.loads(records[-1].removeprefix("agent_tool_failed "))["error_code"] == "tool_execution_failed"

    def broken_log(*_args):
        raise RuntimeError("log sink unavailable")

    monkeypatch.setattr(tool_message_audit_service.logger, "warning", broken_log)
    tool_message_audit_service.log_failed_tool_event(
        run_id="run-1",
        request_id="request-1",
        tool_call_id="call-1",
        tool_name="search_reference_recipes",
        content="{}",
        duration_ms=100,
    )

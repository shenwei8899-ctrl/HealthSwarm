"""将 LangGraph v3 Tool 生命周期投影为 PostgreSQL ToolMessage。"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from time import monotonic
from typing import Any

from yuxi.repositories.tool_message_audit_repository import ToolMessageAuditRepository
from yuxi.storage.postgres.manager import pg_manager
from yuxi.utils.logging_config import logger


class ToolMessageAuditCollector:
    """按 tools lifecycle 串行提交 ToolMessage 审计短事务。"""

    def __init__(self, *, run_id: str, request_id: str, thread_id: str, worker_id: str):
        self.run_id = run_id
        self.request_id = request_id
        self.thread_id = thread_id
        self.worker_id = worker_id
        self._operations: dict[str, float | None] = {}
        self._tool_names: dict[str, str] = {}

    async def consume(self, event: Any) -> None:
        """消费一条根 tools ProtocolEvent；非生命周期事件保持无副作用。"""
        if not isinstance(event, dict) or event.get("method") != "tools":
            return
        data = event.get("data")
        if not isinstance(data, dict) or not isinstance(data.get("event"), str):
            return

        event_name = data["event"]
        if event_name == "tool-started":
            await self._start(event, data)
        elif event_name == "tool-finished":
            await self._finish(event, data)
        elif event_name == "tool-error":
            await self._error(event, data)

    async def _start(self, event: dict[str, Any], data: dict[str, Any]) -> None:
        tool_call_id = self._tool_call_id(data)
        tool_name = str(data.get("tool_name") or "").strip()
        tool_input = data.get("input")
        if tool_input is None:
            tool_input = {}
        if not isinstance(tool_input, dict):
            raise ValueError("tool-started input 必须是对象")

        sequence = self._sequence(event)
        started_at = self._wall_clock(event)
        monotonic_started_at = monotonic()
        namespace = self._namespace(event)
        async with pg_manager.get_async_session_context() as db:
            message, created = await ToolMessageAuditRepository(db).start(
                run_id=self.run_id,
                request_id=self.request_id,
                thread_id=self.thread_id,
                worker_id=self.worker_id,
                tool_call_id=tool_call_id,
                tool_name=tool_name,
                tool_input=dict(tool_input),
                sequence=sequence,
                started_at=started_at,
                metadata={"namespace": namespace},
            )

        if created:
            self._operations[tool_call_id] = monotonic_started_at
        else:
            self._operations.setdefault(tool_call_id, None)
        if created or getattr(message, "execution_status", "running") == "running":
            self._tool_names[tool_call_id] = tool_name
        else:
            self._tool_names.pop(tool_call_id, None)

    async def _finish(self, event: dict[str, Any], data: dict[str, Any]) -> None:
        tool_call_id = self._tool_call_id(data)
        output = data.get("output")
        content = _tool_output_content(output)
        failed = isinstance(output, dict) and output.get("status") == "error"
        error_message = content if failed else None
        await self._close(
            event=event,
            tool_call_id=tool_call_id,
            output=output,
            content=content,
            error_message=error_message,
        )

    async def _error(self, event: dict[str, Any], data: dict[str, Any]) -> None:
        tool_call_id = self._tool_call_id(data)
        error_message = str(data.get("message") or "Tool 执行失败")
        await self._close(
            event=event,
            tool_call_id=tool_call_id,
            output=None,
            content="",
            error_message=error_message,
            wait_for_run_terminal=True,
        )

    async def _close(
        self,
        *,
        event: dict[str, Any],
        tool_call_id: str,
        output: Any,
        content: str,
        error_message: str | None,
        wait_for_run_terminal: bool = False,
    ) -> None:
        """将进程内计时与 terminal 事实一次提交给 Repository。"""
        monotonic_started_at = self._operations.get(tool_call_id)
        duration_ms = (
            max(0, round((monotonic() - monotonic_started_at) * 1000)) if monotonic_started_at is not None else None
        )
        kwargs = {
            "run_id": self.run_id,
            "request_id": self.request_id,
            "thread_id": self.thread_id,
            "worker_id": self.worker_id,
            "tool_call_id": tool_call_id,
            "output": output,
            "content": content,
            "finished_at": self._wall_clock(event),
            "duration_ms": duration_ms,
            "finished_sequence": self._sequence(event),
        }
        async with pg_manager.get_async_session_context() as db:
            repository = ToolMessageAuditRepository(db)
            if wait_for_run_terminal:
                await repository.observe_error(
                    run_id=self.run_id,
                    request_id=self.request_id,
                    thread_id=self.thread_id,
                    worker_id=self.worker_id,
                    tool_call_id=tool_call_id,
                    error_message=error_message or "Tool 执行失败",
                    finished_at=kwargs["finished_at"],
                    duration_ms=duration_ms,
                    finished_sequence=kwargs["finished_sequence"],
                )
            elif error_message is None:
                await repository.complete(**kwargs)
            else:
                await repository.fail(error_message=error_message, **kwargs)
        if error_message is not None and not wait_for_run_terminal and tool_call_id in self._tool_names:
            log_failed_tool_event(
                run_id=self.run_id,
                request_id=self.request_id,
                tool_call_id=tool_call_id,
                tool_name=self._tool_names[tool_call_id],
                content=content,
                duration_ms=duration_ms,
            )
        self._operations.pop(tool_call_id, None)
        self._tool_names.pop(tool_call_id, None)

    @staticmethod
    def _tool_call_id(data: dict[str, Any]) -> str:
        tool_call_id = str(data.get("tool_call_id") or "").strip()
        if not tool_call_id:
            raise ValueError("Tool lifecycle 缺少稳定 tool_call_id")
        return tool_call_id

    @staticmethod
    def _sequence(event: dict[str, Any]) -> int:
        sequence = event.get("seq")
        if not isinstance(sequence, int) or isinstance(sequence, bool) or sequence < 0:
            raise ValueError("Tool lifecycle 缺少有效 ProtocolEvent seq")
        return sequence

    @staticmethod
    def _wall_clock(event: dict[str, Any]) -> datetime:
        timestamp = event.get("timestamp")
        if not isinstance(timestamp, int | float) or isinstance(timestamp, bool):
            raise ValueError("Tool lifecycle 缺少有效 params.timestamp")
        return datetime.fromtimestamp(timestamp / 1000, UTC).replace(tzinfo=None)

    @staticmethod
    def _namespace(event: dict[str, Any]) -> list[str]:
        namespace = event.get("namespace")
        return [str(item) for item in namespace] if isinstance(namespace, list) else []


def log_failed_tool_event(
    *, run_id: str, request_id: str, tool_call_id: str, tool_name: str, content: str, duration_ms: int | None
) -> None:
    """仅把已确认失败工具的错误码和字段路径写入运行日志。"""
    diagnosis = {"error_code": "tool_execution_failed"}
    try:
        payload = json.loads(content) if len(content) <= 32_768 else None
    except (ValueError, TypeError, RecursionError):
        payload = None
    if isinstance(payload, dict):
        code = payload.get("error_code")
        if isinstance(code, str) and re.fullmatch(r"[a-z][a-z0-9_]{0,79}", code):
            diagnosis["error_code"] = code
        issues = payload.get("issues")
        if isinstance(issues, dict):
            safe_issues = {}
            fields = ("missing_ingredient_paths", "extra_decision_paths", "duplicate_decision_paths")
            for field in fields:
                paths = issues.get(field)
                if not isinstance(paths, list):
                    continue
                flattened = [path for item in paths[:12] for path in (item if isinstance(item, list) else [item])]
                safe_issues[field] = [
                    path
                    for path in flattened[:12]
                    if isinstance(path, str)
                    and len(path) <= 128
                    and re.fullmatch(r"(?:meals|purchase_items|purchase_gaps)\[\d+\](?:\.[a-z_]+(?:\[\d+\])?)*", path)
                ]
            if safe_issues:
                diagnosis["issues"] = safe_issues
            counts = issues.get("counts")
            if isinstance(counts, dict):
                diagnosis["issue_counts"] = {
                    field: counts[field]
                    for field in fields
                    if isinstance(counts.get(field), int) and not isinstance(counts[field], bool) and counts[field] >= 0
                }
    try:
        logger.warning(
            "agent_tool_failed {}",
            json.dumps(
                {
                    "event": "agent_tool_failed",
                    "run_id": run_id,
                    "request_id": request_id,
                    "tool_call_id": tool_call_id
                    if re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", tool_call_id)
                    else "invalid",
                    "tool": tool_name if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.:-]{0,79}", tool_name) else "unknown",
                    "duration_ms": duration_ms,
                    **diagnosis,
                },
                ensure_ascii=False,
            ),
        )
    except Exception:
        # 运行日志不可使已提交的 Tool 审计或 Run 终态回报失败。
        pass


def _tool_output_content(output: Any) -> str:
    """将 ToolMessage output 规整为兼容展示文本，同时保留原始 output metadata。"""
    value = output.get("content") if isinstance(output, dict) else output
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, default=str)

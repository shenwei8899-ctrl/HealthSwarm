"""原样提取生产函数验证流发布边界；依赖替身不代表真实数据库验收。"""

import ast
import asyncio
import json
import unittest
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, patch


BACKEND = Path(__file__).resolve().parents[3]
SERVICES = BACKEND / "package/yuxi/services"
PRIVATE = "synthetic-private-prefix-and-metadata"


def source_functions(path, names, scope=None):
    """编译真实源码中的指定函数，不改写其实现或绕过其内部调用。"""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    definitions = [node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]
    selected = [node for node in definitions if node.name in names]
    if {node.name for node in selected} != set(names):
        raise AssertionError("待验收生产函数已变化，请重新核对测试边界")
    future = ast.parse("from __future__ import annotations").body[0]
    namespace = dict(scope or {})
    exec(compile(ast.Module(body=[future, *selected], type_ignores=[]), str(path), "exec"), namespace)
    return namespace


def dependency_modules(profile, evidence, repository=None):
    """仅替换待测函数显式导入的外部权限和来源依赖。"""
    modules = {}
    for name, attribute, value in [
        ("yuxi.services.health_family_profile_service", "validate_profile_publication", profile),
        ("yuxi.services.health_evidence_service", "validate_evidence_publication", evidence),
        ("yuxi.repositories.health_consultation_repository", "HealthConsultationRepository", repository),
    ]:
        module = ModuleType(name)
        setattr(module, attribute, value)
        modules[name] = module
    return modules


def envelope(content="已校验正文。", prefix=None, offset=0):
    """带污染字段的真实专用增量 envelope。"""
    return {
        "run_id": PRIVATE,
        "metadata": PRIVATE,
        "payload": {
            "name": "yuxi.health_answer_delta",
            "metadata": PRIVATE,
            "chunk": {
                "validated_prefix": content if prefix is None else prefix,
                "metadata": PRIVATE,
                "response": PRIVATE,
                "delta": {"content": content, "offset": offset, "message_id": "message", "reasoning": PRIVATE},
            },
        },
    }


class HealthAnswerStreamPublicationTests(unittest.IsolatedAsyncioTestCase):
    """真实投影、重放校验和 SSE generator 的本地边界证据。"""

    def setUp(self):
        self.run = SimpleNamespace(
            id="run",
            conversation_thread_id="thread",
            request_id="request",
            agent_slug="health-consultation",
            run_type="chat",
            source="chat",
            status="completed",
        )
        self.db = object()
        self.order = []

        @asynccontextmanager
        async def session():
            yield self.db

        self.scope = source_functions(
            SERVICES / "agent_run_service.py",
            [
                "_public_health_error",
                "_public_health_run_event",
                "validate_health_stream_publication",
                "stream_agent_run_events",
            ],
            {
                "pg_manager": SimpleNamespace(get_async_session_context=session),
                "TERMINAL_RUN_STATUSES": {"completed", "failed", "cancelled", "interrupted"},
                "HEALTH_AGENT_BACKENDS": {"health-consultation"},
                "EDUCATION_HEALTH_AGENTS": {"health-consultation"},
                "asyncio": asyncio,
                "utc_now_naive": datetime.now,
                "monotonic": lambda: 0,
                "normalize_after_seq": lambda value: value,
                "RUN_SSE_STATUS_POLL_SECONDS": 5,
                "RUN_SSE_ACTIVE_POLL_SECONDS": 0.1,
                "_load_stream_run_for_user": AsyncMock(return_value=self.run),
            },
        )
        self.scope.update(source_functions(BACKEND / "package/yuxi/utils/sse_utils.py", ["format_sse"], {"json": json}))

    def project(self, value):
        return self.scope["_public_health_run_event"](self.run, "custom", value)

    def validators(self, *, reject_evidence=False):
        """提供明确可撤回的来源依赖，并保留顺序与输入断言。"""

        async def profile(db, run):
            self.assertIs(db, self.db)
            self.assertIs(run, self.run)
            self.order.append("profile")

        async def evidence(db, run, content):
            self.assertIs(db, self.db)
            self.assertIs(run, self.run)
            self.order.append(("evidence", content))
            if reject_evidence:
                raise RuntimeError(PRIVATE)

        return profile, evidence

    def stream(self, values):
        events = [
            {"seq": f"{index}-0", "event_type": event_type, "payload": value}
            for index, (event_type, value) in enumerate(values, 1)
        ]
        self.scope["list_run_stream_events"] = AsyncMock(return_value=events)
        return self.scope["stream_agent_run_events"](run_id="run", after_seq="0-0", current_uid="actor")

    async def test_delta_projection_uses_only_public_identity_content_offset_and_message(self):
        content = "第二段已校验正文。"
        value = envelope(content, PRIVATE + content, len(PRIVATE))
        projected = self.project(value)
        self.assertEqual(
            projected,
            {
                "run_id": "run",
                "thread_id": "thread",
                "request_id": "request",
                "event": "custom",
                "payload": {
                    "name": "yuxi.health_answer_delta",
                    "chunk": {
                        "run_id": "run",
                        "thread_id": "thread",
                        "request_id": "request",
                        "status": "health_answer_delta",
                        "content": content,
                        "offset": len(PRIVATE),
                        "message_id": "message",
                    },
                },
            },
        )
        self.assertNotIn(PRIVATE, json.dumps(projected))
        self.assertNotIn("validated_prefix", json.dumps(projected))

    async def test_missing_prefix_and_invalid_offsets_are_rejected(self):
        missing = envelope()
        del missing["payload"]["chunk"]["validated_prefix"]
        invalid = [missing, envelope(offset=1), envelope(offset=-1), envelope(offset=True), envelope(prefix="wrong")]
        for value in invalid:
            with self.subTest(value=value):
                self.assertIsNone(self.project(value))

    async def test_real_stream_revalidates_each_delta_before_yield_then_sends_end(self):
        profile, evidence = self.validators()
        first, second = "第一段。", "第二段。"
        values = [
            ("custom", envelope(first)),
            ("custom", envelope(second, first + second, len(first))),
            ("end", {"payload": {"status": "completed", "metadata": PRIVATE}}),
        ]
        with patch.dict("sys.modules", dependency_modules(profile, evidence)):
            stream = self.stream(values)
            one = await anext(stream)
            self.assertEqual(self.order, ["profile", ("evidence", first)])
            self.assertIn(first, one)
            two = await anext(stream)
            self.assertEqual(self.order, ["profile", ("evidence", first), "profile", ("evidence", first + second)])
            self.assertIn(second, two)
            end = await anext(stream)
            self.assertIn("event: end", end)
            with self.assertRaises(StopAsyncIteration):
                await anext(stream)
        self.assertNotIn(PRIVATE, one + two + end)
        self.assertNotIn("validated_prefix", one + two + end)

    async def test_revoked_source_replay_emits_fixed_error_without_old_body(self):
        profile, evidence = self.validators(reject_evidence=True)
        old_body = "已撤回来源的旧正文不得重新公开。"
        with patch.dict("sys.modules", dependency_modules(profile, evidence)):
            outputs = [
                chunk
                async for chunk in self.stream(
                    [
                        ("custom", envelope(old_body)),
                        ("end", {"payload": {"status": "completed"}}),
                    ]
                )
            ]
        self.assertEqual(len(outputs), 1)
        self.assertIn("event: error", outputs[0])
        self.assertIn("答复来源或授权已变化，请重新读取本次任务", outputs[0])
        self.assertNotIn(old_body, outputs[0])
        self.assertNotIn(PRIVATE, outputs[0])
        self.assertEqual(self.order, ["profile", ("evidence", old_body)])

    async def test_replay_validator_checks_profile_before_evidence_and_propagates_rejection(self):
        profile = AsyncMock(side_effect=RuntimeError("profile withdrawn"))
        evidence = AsyncMock()
        with patch.dict("sys.modules", dependency_modules(profile, evidence)):
            with self.assertRaisesRegex(RuntimeError, "profile withdrawn"):
                await self.scope["validate_health_stream_publication"](self.run, envelope())
        profile.assert_awaited_once_with(self.db, self.run)
        evidence.assert_not_awaited()

    async def test_chat_prefix_rechecks_locked_attempt_profile_and_evidence(self):
        profile, evidence = self.validators()
        context = object()

        async def require_attempt(actual_context, *, lock):
            self.assertIs(actual_context, context)
            self.assertIs(lock, True)
            self.order.append("attempt")
            return self.run

        require = AsyncMock(side_effect=require_attempt)

        def repository(db):
            self.assertIs(db, self.db)
            return SimpleNamespace(require_attempt=require)

        chat = source_functions(
            SERVICES / "chat_service.py",
            ["validate_health_stream_prefix"],
            {
                "pg_manager": self.scope["pg_manager"],
                "EDUCATION_HEALTH_AGENTS": {"health-consultation"},
            },
        )
        with patch.dict("sys.modules", dependency_modules(profile, evidence, repository)):
            await chat["validate_health_stream_prefix"](context, "完整段落。")
            self.assertEqual(self.order, ["attempt", "profile", ("evidence", "完整段落。")])
            self.order.clear()
            self.run.agent_slug = "health-meal-planner"
            with self.assertRaisesRegex(ValueError, "只有科普答复"):
                await chat["validate_health_stream_prefix"](context, PRIVATE)
            self.assertEqual(self.order, ["attempt"])
            self.order.clear()
            self.run.agent_slug = "health-consultation"
            require.side_effect = RuntimeError("attempt expired")
            with self.assertRaisesRegex(RuntimeError, "attempt expired"):
                await chat["validate_health_stream_prefix"](context, PRIVATE)
            self.assertEqual(self.order, [])


if __name__ == "__main__":
    unittest.main()

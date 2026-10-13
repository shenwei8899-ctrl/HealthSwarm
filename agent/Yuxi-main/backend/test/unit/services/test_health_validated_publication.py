"""健康解释候选只进入审计，公开流和恢复只显示进度与已提交结果。"""

import json
import inspect
import os
import textwrap
from contextlib import asynccontextmanager
from types import FunctionType, SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from langchain.messages import AIMessage, AIMessageChunk

from test.unit.agent_context_fixtures import prepared_execution
from yuxi.services import agent_run_service, chat_service, conversation_service, run_worker
from yuxi.services.input_message_service import build_chat_input_message

pytestmark = pytest.mark.asyncio
PRIVATE = "PRIVATE_HEALTH_CANDIDATE_OR_REASONING"
SLUGS = ["health-consultation", "health-blood-glucose", "health-blood-lipids", "health-blood-pressure"]


@pytest.fixture(autouse=True)
def controlled_publication_mutation(monkeypatch, request):
    """只变异独立测试进程的函数副本，原始服务及共享源码保持不变。"""
    mode = os.getenv("HEALTH_PUBLICATION_MUTATION")
    if mode == "matrix":
        mode = {
            "test_candidate_streams_are_audited_but_publication_waits_for_owner_commit": "producer",
            "test_old_redis_candidates_are_not_replayed_even_after_completed_commit": "redis",
            "test_state_checkpoint_candidates_do_not_bypass_fresh_public_history": "state",
            "test_published_health_history_does_not_expose_legacy_reasoning_metadata_or_tool_output": "history",
            "test_status_result_and_progress_hide_executor_error_and_candidate": "error",
            "test_success_and_legacy_pg_usage_do_not_expose_provider_metadata_candidates": "usage",
            "test_interrupted_state_cannot_promote_unvalidated_model_to_public_output_pointer": "unfinished_save",
            "test_terminal_commit_false_cannot_emit_completed_notification": "commit",
            "test_health_interrupt_payloads_and_meta_stay_private_but_generic_approval_remains": "interrupt",
        }.get(request.node.originalname)
    targets = {
        "producer": [
            (
                chat_service,
                name,
                "withhold_health_output = agent_item.slug in EDUCATION_HEALTH_AGENTS",
                "withhold_health_output = False",
            )
            for name in ("stream_agent_chat", "stream_agent_resume")
        ],
        "redis": [
            (
                agent_run_service,
                "stream_agent_run_events",
                "if run.agent_slug in EDUCATION_HEALTH_AGENTS:\n"
                "                    envelope = _public_health_run_event",
                "if False:\n                    envelope = _public_health_run_event",
            )
        ],
        "state": [
            (
                chat_service,
                "get_agent_state_view",
                'if withhold_health_output:\n            response["agent_state"] = extract_agent_state({})',
                'if False:\n            response["agent_state"] = extract_agent_state({})',
            )
        ],
        "history": [
            (
                conversation_service,
                "get_thread_history_view",
                'health_answer = conversation.agent_id in EDUCATION_HEALTH_AGENTS and msg.role == "assistant"',
                "health_answer = False",
            )
        ],
        "error": [(agent_run_service, "_public_run_view", "if run.error_type or run.error_message:", "if False:")],
        "usage": [
            (
                agent_run_service,
                "project_health_token_usage",
                'if not isinstance(usage, dict) or usage.get("schema_version") != 2:',
                'return usage\n    if not isinstance(usage, dict) or usage.get("schema_version") != 2:',
            )
        ],
        "timing": [(run_worker, "process_agent_run", 'chunk.get("status") == "health_progress"', "False")],
        "unfinished_save": [
            (
                chat_service,
                "save_messages_from_langgraph_state",
                "(run_id and locked_run.agent_slug in EDUCATION_HEALTH_AGENTS and not complete_run)",
                "False",
            )
        ],
        "commit": [
            (chat_service, name, "if withhold_health_output and not terminal_committed:", "if False:")
            for name in ("stream_agent_chat", "stream_agent_resume")
        ],
        "interrupt": [
            (
                chat_service,
                name,
                "if withhold_health_output:\n"
                '                interrupt_error_type, interrupt_error_message = "interrupted"',
                'if False:\n                interrupt_error_type, interrupt_error_message = "interrupted"',
            )
            for name in ("stream_agent_chat", "stream_agent_resume")
        ],
    }
    for owner, attribute, old, new in targets.get(mode, []):
        original = getattr(owner, attribute)
        source = textwrap.dedent(inspect.getsource(original))
        assert source.count(old) == 1, f"负控目标已漂移: {mode}/{attribute}"
        scope = dict(original.__globals__)
        exec(compile(source.replace(old, new), f"<controlled_publication_mutation:{mode}>", "exec"), scope)
        compiled = scope[attribute]
        mutated = FunctionType(compiled.__code__, original.__globals__, attribute, compiled.__defaults__)
        mutated.__kwdefaults__ = compiled.__kwdefaults__
        monkeypatch.setattr(owner, attribute, mutated)


def stream_scaffold(monkeypatch, slug, *, output=True, persistence_error=False, interrupt_payload=None):
    """把模型、工具及 checkpoint 的不同候选入口送入真实 stream service。"""
    calls = []
    db = SimpleNamespace(commit=AsyncMock(), rollback=AsyncMock())
    final = SimpleNamespace(
        values={"messages": [AIMessage(content=PRIVATE)], "todos": [PRIVATE]},
        tasks=[SimpleNamespace(interrupts=[interrupt_payload])] if interrupt_payload else [],
    )

    class Agent:
        """协议起始不算输出，正文与工具内容也不能成为公开事件。"""

        async def stream_messages_with_state(self, *args, **kwargs):
            """产生多个实际流分支，最后交给持久化 Owner。"""
            yield "messages", ({"event": "message-start", "id": "model"}, {})
            yield "messages", (AIMessageChunk(content=""), {})
            if output:
                yield "messages", (AIMessageChunk(content=PRIVATE), {})
                yield (
                    "messages",
                    ({"event": "content-block-delta", "delta": {"type": "reasoning-delta", "reasoning": PRIVATE}}, {}),
                )
                yield (
                    "messages",
                    (
                        AIMessageChunk(
                            content="", tool_call_chunks=[{"id": "call", "name": "tool", "args": PRIVATE, "index": 0}]
                        ),
                        {},
                    ),
                )
            yield "stream_event", {"method": "tools", "data": {"event": "tool-finished", "output": PRIVATE}}
            yield "values", {"todos": [PRIVATE], "files": {PRIVATE: PRIVATE}, "artifacts": [PRIVATE]}
            yield "custom", {"type": "yuxi.context_compression", "message": PRIVATE}
            yield "checkpoint", final

        stream_resume_with_state = stream_messages_with_state

    agent = Agent()
    model_audit = SimpleNamespace(consume=AsyncMock())
    tool_audit = SimpleNamespace(consume=AsyncMock())
    item = SimpleNamespace(slug=slug, backend_id="HealthConsultationAgent", name="健康解释")
    context = prepared_execution().context
    conv = SimpleNamespace(id=7, uid="actor", thread_id="thread", agent_id=slug)
    repo = SimpleNamespace(db=db, get_attachments=AsyncMock(return_value=[]))
    monkeypatch.setattr(chat_service, "_resolve_agent_runtime", AsyncMock(return_value=(item, agent, context, conv)))
    monkeypatch.setattr(chat_service, "ConversationRepository", lambda _db: repo)
    monkeypatch.setattr(chat_service, "_build_model_message_audit_collector", lambda *args: model_audit)
    monkeypatch.setattr(chat_service, "_build_tool_message_audit_collector", lambda *args: tool_audit)
    monkeypatch.setattr(chat_service, "_persist_agent_run_langfuse_trace", AsyncMock())
    monkeypatch.setattr(chat_service, "_persist_model_request_timing", AsyncMock())
    monkeypatch.setattr(
        chat_service,
        "_build_langfuse_run_context",
        lambda **kwargs: SimpleNamespace(callbacks=[], metadata={}, tags=[], trace_id=None),
    )
    monkeypatch.setattr(chat_service, "get_trace_info", lambda run: {})
    monkeypatch.setattr(chat_service, "flush_langfuse", lambda: None)

    async def publish(**kwargs):
        """模拟真实发布 Owner 的拒绝或提交，检查事件在提交后才终结。"""
        assert kwargs["complete_run"] is (interrupt_payload is None)
        calls.append("validate")
        if persistence_error:
            raise ValueError(PRIVATE)
        await db.commit()
        calls.append("commit")
        return True

    monkeypatch.setattr(chat_service, "save_messages_from_langgraph_state", publish)
    return db, model_audit, tool_audit, calls


def execution_stream(mode, slug, db):
    """普通 chat 和执行层 resume 使用相同发布约束。"""
    kwargs = dict(
        thread_id="thread",
        meta={"request_id": "request", "run_id": "run", "worker_id": "worker"},
        current_user=SimpleNamespace(uid="actor"),
        db=db,
        prepared_execution=prepared_execution(),
    )
    if mode == "chat":
        return chat_service.stream_agent_chat(
            **kwargs, agent_slug=slug, input_message=build_chat_input_message("回顾记录")
        )
    return chat_service.stream_agent_resume(**kwargs, resume_input="继续")


@pytest.mark.parametrize("slug", SLUGS)
@pytest.mark.parametrize("mode", ["chat", "resume"])
@pytest.mark.parametrize("persistence_error", [False, True])
async def test_candidate_streams_are_audited_but_publication_waits_for_owner_commit(
    monkeypatch, slug, mode, persistence_error
):
    db, model_audit, tool_audit, calls = stream_scaffold(monkeypatch, slug, persistence_error=persistence_error)
    chunks = []
    async for raw in execution_stream(mode, slug, db):
        chunk = json.loads(raw)
        chunks.append(chunk)
        assert PRIVATE not in raw.decode()
        assert chunk.get("response") is None and "stream_event" not in chunk and "event" not in chunk
        assert "agent_state" not in chunk and "compression" not in chunk
        if chunk.get("phase") == "validating":
            assert calls == []
        if chunk["status"] == "finished":
            assert calls == ["validate", "commit"] and chunk["terminal_committed"] is True
    assert tool_audit.consume.await_count == 1 and model_audit.consume.await_count == 5
    assert sum(chunk.get("model_output_started") is True for chunk in chunks) == 1
    assert [chunk["status"] for chunk in chunks][-1] == ("error" if persistence_error else "finished")
    if persistence_error:
        assert calls == ["validate"] and chunks[-1]["error_type"] == "output_persistence_error"


@pytest.mark.parametrize("mode", ["chat", "resume"])
async def test_empty_protocol_starts_do_not_move_first_model_output_time(monkeypatch, mode):
    db, _, _, _ = stream_scaffold(monkeypatch, SLUGS[0], output=False)
    chunks = [json.loads(raw) async for raw in execution_stream(mode, SLUGS[0], db)]
    assert not any(chunk.get("model_output_started") is True for chunk in chunks)
    assert not any(run_worker._contains_model_output(chunk) for chunk in chunks)
    assert run_worker._contains_model_output(
        {"status": "health_progress", "phase": "running", "model_output_started": True}
    )


@pytest.mark.parametrize("mode", ["chat", "resume"])
async def test_terminal_commit_false_cannot_emit_completed_notification(monkeypatch, mode):
    db, _, _, _ = stream_scaffold(monkeypatch, SLUGS[0])
    monkeypatch.setattr(chat_service, "save_messages_from_langgraph_state", AsyncMock(return_value=False))
    chunks = [json.loads(raw) async for raw in execution_stream(mode, SLUGS[0], db)]
    assert all(chunk["status"] != "finished" for chunk in chunks)
    assert chunks[-1]["error_type"] == "output_persistence_error"
    assert PRIVATE not in str(chunks)


@pytest.mark.parametrize("slug", SLUGS + ["ordinary-agent"])
@pytest.mark.parametrize("mode", ["chat", "resume"])
@pytest.mark.parametrize("interrupt_kind", ["question", "approval"])
async def test_health_interrupt_payloads_and_meta_stay_private_but_generic_approval_remains(
    monkeypatch, slug, mode, interrupt_kind
):
    """意外健康中断只公开固定摘要，原有普通审批协议仍保留。"""
    payload = (
        {"questions": [{"id": "question", "header": "合成问题", "question": PRIVATE, "options": []}]}
        if interrupt_kind == "question"
        else {
            "action_requests": [{"name": "tool", "args": {"private": PRIVATE}}],
            "review_configs": [{"action_name": "tool", "allowed_decisions": ["approve", "reject"]}],
        }
    )
    db, _, _, calls = stream_scaffold(monkeypatch, slug, output=False, interrupt_payload=payload)
    chunks = [json.loads(raw) async for raw in execution_stream(mode, slug, db)]
    assert calls == ["validate", "commit"]
    if slug == "ordinary-agent":
        expected = "human_approval_required" if interrupt_kind == "approval" else "ask_user_question_required"
        assert any(chunk["status"] == expected for chunk in chunks) and PRIVATE in str(chunks)
    else:
        assert PRIVATE not in str(chunks)
        assert chunks[-1]["status"] == "interrupted" and "重新发送文字咨询" in chunks[-1]["message"]
        assert not any(
            "questions" in chunk or "approval" in chunk or "interrupt" in chunk.get("meta", {}) for chunk in chunks
        )


@pytest.mark.parametrize("slug", SLUGS)
async def test_interrupted_state_cannot_promote_unvalidated_model_to_public_output_pointer(monkeypatch, slug):
    """中断 State 可以收尾执行事实，但不发布 AI 候选或绑定正式输出。"""
    from yuxi.services import health_evidence_service, health_family_profile_service

    db = SimpleNamespace(commit=AsyncMock(), rollback=AsyncMock())
    message = SimpleNamespace(id=42, content=PRIVATE, extra_metadata={}, message_type="text")
    conv = SimpleNamespace(
        db=db,
        get_message_source_ids_by_thread_id=AsyncMock(return_value=[]),
        add_message_by_thread_id=AsyncMock(return_value=message),
        publish_assistant_output=AsyncMock(),
    )
    locked = SimpleNamespace(agent_slug=slug, conversation_id=7)
    run_repo = SimpleNamespace(
        lock_output_persistence=AsyncMock(return_value=locked),
        set_output_message=AsyncMock(),
        set_terminal_status=AsyncMock(return_value=(locked, True)),
        cancel_active_execution_tree_descendants=AsyncMock(return_value=[]),
    )

    def empty_audit(db):
        """模拟无 lifecycle 事实的旧 State，仍执行同一发布 guard。"""
        return SimpleNamespace(list_for_run=AsyncMock(return_value=[]))

    monkeypatch.setattr(chat_service, "AgentRunRepository", lambda db: run_repo)
    monkeypatch.setattr(chat_service, "ModelMessageAuditRepository", empty_audit)
    monkeypatch.setattr(chat_service, "ToolMessageAuditRepository", empty_audit)
    monkeypatch.setattr(chat_service, "publish_cancel_signals", AsyncMock())
    validate_profile = AsyncMock(side_effect=AssertionError("未完成正文不得触发正式发布"))
    validate_evidence = AsyncMock(side_effect=AssertionError("未完成正文不得触发正式发布"))
    monkeypatch.setattr(health_family_profile_service, "validate_profile_publication", validate_profile)
    monkeypatch.setattr(health_evidence_service, "validate_evidence_publication", validate_evidence)
    state = SimpleNamespace(values={"messages": [AIMessage(content=PRIVATE, id="candidate")]})
    assert await chat_service.save_messages_from_langgraph_state(
        state,
        "thread",
        conv,
        run_id="run",
        request_id="request",
        worker_id="worker",
        interrupt_run=True,
        interrupt_error_type="interrupted",
        interrupt_error_message="咨询已中断",
    )
    conv.publish_assistant_output.assert_not_awaited()
    conv.add_message_by_thread_id.assert_not_awaited()
    run_repo.set_output_message.assert_not_awaited()
    assert run_repo.set_terminal_status.await_args.kwargs["status"] == "interrupted"
    db.commit.assert_awaited_once()
    validate_profile.assert_not_awaited()
    validate_evidence.assert_not_awaited()


@pytest.mark.parametrize("mode", ["chat", "resume"])
async def test_ordinary_agent_stream_preserves_model_tool_and_state_behavior(monkeypatch, mode):
    db, _, _, _ = stream_scaffold(monkeypatch, "ordinary-agent")
    chunks = [json.loads(raw) async for raw in execution_stream(mode, "ordinary-agent", db)]
    assert any(chunk.get("response") == PRIVATE for chunk in chunks)
    assert any(chunk.get("event", {}).get("method") == "tools" for chunk in chunks)
    assert any(chunk.get("agent_state", {}).get("todos") == [PRIVATE] for chunk in chunks)
    assert any(chunk.get("compression", {}).get("message") == PRIVATE for chunk in chunks)


def public_run(slug, status="completed"):
    """运行身份与状态来自数据库，不采用 Redis candidate 身份。"""
    values = dict(
        id="run",
        uid="actor",
        agent_slug=slug,
        status=status,
        request_id="request",
        conversation_id=7,
        conversation_thread_id="thread",
        run_type="chat",
        source="chat",
        error_type="worker_error",
        error_message=PRIVATE,
    )
    return SimpleNamespace(**values, to_dict=lambda: dict(values))


@pytest.mark.parametrize(
    "case",
    [
        "valid",
        "no_authorized_run",
        "wrong_actor",
        "wrong_thread",
        "wrong_snapshot_run",
        "invalid_numeric_usage",
        "no_checkpoint",
    ],
)
async def test_private_health_failure_usage_keeps_only_authorized_same_run_numeric_facts(monkeypatch, case):
    """收尾可保全已产生用量，普通 API 不需要取得完整 checkpoint。"""
    run = public_run(SLUGS[0], "failed")
    run.input_payload = {"model_spec": "provider:model"}
    counts = {"input_tokens": 10, "output_tokens": 2, "total_tokens": 12}
    aggregate = {
        "schema_version": 2,
        "total": dict(counts),
        "model_call_count": 1,
        "complete": True,
        "error": PRIVATE,
        "models": {
            "provider:model": {
                "usage": dict(counts),
                "model_call_count": 1,
                "model": {"response_model_ids": [PRIVATE]},
                "error": PRIVATE,
            },
            PRIVATE: {"usage": dict(counts)},
        },
    }
    values = {"messages": [AIMessage(content=PRIVATE)], "token_usage": {"current_run_id": "run", "run": aggregate}}
    if case == "wrong_actor":
        run.uid = "other"
    elif case == "wrong_thread":
        run.conversation_thread_id = "other"
    elif case == "wrong_snapshot_run":
        values["token_usage"]["current_run_id"] = "other"
    elif case == "invalid_numeric_usage":
        aggregate["total"]["total_tokens"] = PRIVATE
    saved = SimpleNamespace(checkpoint={"channel_values": values})
    checker = SimpleNamespace(aget_tuple=AsyncMock(return_value=None if case == "no_checkpoint" else saved))
    authorize = AsyncMock(return_value=None if case == "no_authorized_run" else run)

    @asynccontextmanager
    async def session():
        """私有读取仍需当前服务端 Run 和成员授权。"""
        yield object()

    monkeypatch.setattr(run_worker.pg_manager, "get_async_session_context", session)
    monkeypatch.setattr(run_worker.pg_manager, "get_langgraph_checkpointer", lambda: checker)
    monkeypatch.setattr(run_worker, "AgentRunRepository", lambda db: SimpleNamespace(get_run_for_user=authorize))
    monkeypatch.setattr(
        run_worker, "get_agent_state_view", AsyncMock(side_effect=AssertionError("异常用量不读取公开空state"))
    )
    usage = await run_worker._read_run_token_usage_from_state(
        run_id="run", thread_id="thread", current_user=SimpleNamespace(uid="actor"), run=run
    )
    assert PRIVATE not in str(usage)
    if case != "valid":
        assert usage is None
        if case in {"no_authorized_run", "wrong_actor", "wrong_thread"}:
            checker.aget_tuple.assert_not_awaited()
        return
    assert usage == {
        "schema_version": 2,
        "models": {
            "provider:model": {
                "model": {"configured_model_spec": "provider:model"},
                "usage": counts,
                "model_call_count": 1,
            }
        },
        "total": counts,
        "model_call_count": 1,
        "complete": True,
    }
    checker.aget_tuple.assert_awaited_once_with(
        {"configurable": {"uid": "actor", "thread_id": "thread", "checkpoint_ns": ""}}
    )


@pytest.mark.parametrize("slug", SLUGS)
@pytest.mark.parametrize("verbose", [False, True])
@pytest.mark.parametrize("after_seq", ["0-0", "2-0"])
async def test_old_redis_candidates_are_not_replayed_even_after_completed_commit(monkeypatch, slug, verbose, after_seq):
    run = public_run(slug)
    monkeypatch.setattr(agent_run_service, "_load_stream_run_for_user", AsyncMock(return_value=run))
    events = []
    for seq, event_type, payload in [
        (
            "1-0",
            "messages",
            {
                "chunk": {
                    "response": PRIVATE,
                    "stream_event": {"type": "message_delta", "content": PRIVATE, "reasoning_content": PRIVATE},
                }
            },
        ),
        ("2-0", "custom", {"name": "yuxi.agent_state", "agent_state": {"todos": [PRIVATE]}}),
        (
            "3-0",
            "custom",
            {"name": "yuxi.health_progress", "chunk": {"phase": "validating", "message": PRIVATE, "response": PRIVATE}},
        ),
        ("4-0", "error", {"chunk": {"error_type": PRIVATE, "error_message": PRIVATE}}),
        ("5-0", "end", {"status": "completed", "chunk": {"response": PRIVATE, "agent_state": {"todos": [PRIVATE]}}}),
    ]:
        events.append(
            {
                "seq": seq,
                "event_type": event_type,
                "payload": {"run_id": "untrusted", "event": event_type, "payload": payload},
            }
        )
    monkeypatch.setattr(
        agent_run_service,
        "list_run_stream_events",
        AsyncMock(return_value=[event for event in events if event["seq"] > after_seq]),
    )
    chunks = [
        raw
        async for raw in agent_run_service.stream_agent_run_events(
            run_id="run", after_seq=after_seq, current_uid="actor", verbose=verbose
        )
    ]
    assert PRIVATE not in "".join(chunks) and "untrusted" not in "".join(chunks)
    assert [chunk.splitlines()[0] for chunk in chunks] == ["event: custom", "event: error", "event: end"]
    assert "正在校验答复来源与引用" in "".join(chunks)
    assert "health_execution_failed" in "".join(chunks)
    data = json.loads(next(line[6:] for line in chunks[0].splitlines() if line.startswith("data: ")))
    assert data["payload"]["chunk"]["phase"] == "validating"
    assert data["payload"]["chunk"]["request_id"] == "request"
    assert data["payload"]["chunk"]["thread_id"] == "thread"


async def test_redis_completed_candidate_cannot_end_running_database_run():
    run = public_run(SLUGS[0], status="running")
    assert (
        agent_run_service._public_health_run_event(
            run, "end", {"payload": {"status": "completed", "response": PRIVATE}}
        )
        is None
    )


@pytest.mark.parametrize("slug", SLUGS)
async def test_status_result_and_progress_hide_executor_error_and_candidate(monkeypatch, slug):
    run = public_run(slug, status="failed")
    monkeypatch.setattr(
        agent_run_service,
        "AgentRunRepository",
        lambda db: SimpleNamespace(get_run_for_user=AsyncMock(return_value=run)),
    )
    monkeypatch.setattr(
        agent_run_service,
        "list_recent_run_stream_events",
        AsyncMock(
            return_value=[
                {
                    "seq": "9-0",
                    "event_type": "messages",
                    "payload": {"payload": {"chunk": {"stream_event": {"type": "message_delta", "content": PRIVATE}}}},
                }
            ]
        ),
    )
    view = await agent_run_service.get_agent_run_view(run_id="run", current_uid="actor", db=object())
    result = await agent_run_service.get_agent_run_result(run_id="run", current_uid="actor", db=object())
    progress = await agent_run_service.get_agent_run_progress("run", agent_slug=slug)
    assert PRIVATE not in str([view, result, progress])
    assert result["output"] == "" and result["final_message_id"] is None
    assert result["error"]["type"] == "health_execution_failed"
    assert progress == {"last_seq": "9-0", "messages": []}


@pytest.mark.parametrize("slug", SLUGS)
@pytest.mark.parametrize("invalid_numbers", [False, True])
async def test_success_and_legacy_pg_usage_do_not_expose_provider_metadata_candidates(
    monkeypatch, slug, invalid_numbers
):
    """成功与旧 PG 行都必须通过同一公开数字投影，不能把 Provider 文本夹入用量。"""
    from yuxi.services import health_evidence_service

    run = public_run(slug)
    run.input_payload = {"model_spec": "provider:model"}
    tokens = {"input_tokens": 10, "output_tokens": 2, "total_tokens": PRIVATE if invalid_numbers else 12}
    run.token_usage = {
        "schema_version": 2,
        "total": tokens,
        "complete": True,
        "error": PRIVATE,
        "models": {
            "provider:model": {"model": {"response_model_ids": [PRIVATE]}, "usage": tokens},
            PRIVATE: {"usage": tokens},
        },
    }
    original_view = run.to_dict()
    run.to_dict = lambda: {**original_view, "token_usage": run.token_usage}
    monkeypatch.setattr(
        agent_run_service,
        "AgentRunRepository",
        lambda db: SimpleNamespace(get_run_for_user=AsyncMock(return_value=run)),
    )
    monkeypatch.setattr(
        health_evidence_service,
        "read_public_consultation_answer",
        AsyncMock(return_value=SimpleNamespace(id=42, content="当前有效的正式正文", extra_metadata={})),
    )
    view = await agent_run_service.get_agent_run_view(run_id="run", current_uid="actor", db=object())
    result = await agent_run_service.get_agent_run_result(run_id="run", current_uid="actor", db=object())
    assert PRIVATE not in str([view, result])
    assert result["output"] == "当前有效的正式正文" and result["final_message_id"] == 42
    assert view["run"]["token_usage"] == result["token_usage"]
    if invalid_numbers:
        assert result["token_usage"] == {"available": False}
    else:
        assert result["token_usage"]["total"] == tokens and list(result["token_usage"]["models"]) == ["provider:model"]


@pytest.mark.parametrize("slug", SLUGS)
async def test_state_checkpoint_candidates_do_not_bypass_fresh_public_history(monkeypatch, slug):
    conv = SimpleNamespace(uid="actor", id=7, thread_id="thread", agent_id=slug, status="active")
    repo = SimpleNamespace(get_conversation_by_thread_id=AsyncMock(return_value=conv))
    monkeypatch.setattr(chat_service, "ConversationRepository", lambda db: repo)
    monkeypatch.setattr(
        chat_service,
        "AgentRunRepository",
        lambda db: SimpleNamespace(
            get_latest_run_by_thread_for_user=AsyncMock(return_value=public_run(slug, "interrupted"))
        ),
    )
    monkeypatch.setattr(conversation_service, "require_user_conversation", AsyncMock(return_value=conv))
    monkeypatch.setattr(chat_service, "resolve_conversation_workdir_path", AsyncMock(return_value="projects/synthetic"))
    values = {
        "messages": [AIMessage(content=PRIVATE)],
        "todos": [PRIVATE],
        "files": {PRIVATE: PRIVATE},
        "artifacts": [PRIVATE],
        "subagent_runs": [{"error": PRIVATE}],
        "token_usage": {PRIVATE: PRIVATE},
    }
    monkeypatch.setattr(chat_service, "_read_checkpoint_state", AsyncMock(return_value=(values, {"question": PRIVATE})))
    history = AsyncMock(return_value={"history": [{"id": 42, "type": "ai", "content": "当前有效的已完成正文"}]})
    monkeypatch.setattr(conversation_service, "get_thread_history_view", history)
    result = await chat_service.get_agent_state_view(
        thread_id="thread", current_user=SimpleNamespace(uid="actor"), db=object(), include_messages=True
    )
    assert PRIVATE not in str(result) and "interrupt" not in result
    assert result["agent_state"] == {
        "todos": [],
        "files": {},
        "artifacts": [],
        "subagent_runs": [],
        "token_usage": None,
    }
    assert result["messages"] == [{"id": "42", "type": "ai", "content": "当前有效的已完成正文"}]
    history.assert_awaited_once()


async def test_published_health_history_does_not_expose_legacy_reasoning_metadata_or_tool_output(monkeypatch):
    """旧无 lifecycle operation_id 的完成消息也不能夹带审计候选。"""
    from yuxi.utils.datetime_utils import utc_now_naive

    conv = SimpleNamespace(id=7, thread_id="thread", agent_id=SLUGS[0], last_viewed_run_id=None)
    message = SimpleNamespace(
        id=42,
        role="assistant",
        content="经过来源校验的正式正文",
        message_type="text",
        delivery_status="complete",
        run_id="run",
        request_id="request",
        created_at=utc_now_naive(),
        feedbacks=[],
        extra_metadata={
            "reasoning_content": PRIVATE,
            "content": [{"type": "reasoning", "reasoning": PRIVATE}],
            "error_message": PRIVATE,
        },
        operation_id=None,
        image_content=None,
        tool_calls=[
            SimpleNamespace(
                id=1,
                langgraph_tool_call_id="tool",
                tool_name="synthetic_tool",
                tool_input={"private": PRIVATE},
                tool_output=PRIVATE,
                status="success",
                error_message=PRIVATE,
            )
        ],
    )
    repo = SimpleNamespace(
        get_messages=AsyncMock(return_value=[message]), list_agent_runs_for_history=AsyncMock(return_value=[])
    )
    monkeypatch.setattr(conversation_service, "ConversationRepository", lambda db: repo)
    monkeypatch.setattr(conversation_service, "require_user_conversation", AsyncMock(return_value=conv))
    monkeypatch.setattr(conversation_service, "_consultation_message_is_public", AsyncMock(return_value=True))
    monkeypatch.setattr(conversation_service, "_serialize_thread", AsyncMock(return_value={"id": "thread"}))
    result = await conversation_service.get_thread_history_view(thread_id="thread", current_uid="actor", db=object())
    assert PRIVATE not in str(result)
    answer = result["history"][0]
    assert answer["content"] == "经过来源校验的正式正文" and answer["reasoning_content"] == ""
    assert answer["extra_metadata"] == {} and "tool_calls" not in answer

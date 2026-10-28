"""真实图、可信最终流与公开投影联合验证；不替代HTTP、PG或Worker验收。"""

import ast
import json
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import asyncio
import pytest
from langchain.agents import create_agent
from langchain_core.messages import AIMessageChunk, HumanMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.stream.transformers import CustomTransformer

from test.unit.middlewares.test_health_final_answer import (
    Context,
    ControlledStreamModel,
    production,
    read_authorized_records,
    tool_chunk,
)
from yuxi.services.health_answer_stream import MAX_PREFIX_CHARS, TrustedHealthFinalAnswerStream
from yuxi.services.health_vision_types import HealthVisionError


CITATION = "[证据:11111111-1111-4111-8111-111111111111]"
FIRST = "公开首段🥦只用于验证已经通过当前来源校验的科普内容，必须保留足够文字与真实合成引用。" + CITATION + "\n\n"
SECOND = "第二段延续本轮已经确认的科普说明，不增加治疗、个体诊断或者未经程序确认的营养数值。" + CITATION + "\n\n"


def production_projection():
    """原样加载公开投影，避免Windows装载无关Linux沙盒入口。"""
    source = Path(__file__).resolve().parents[3] / "package/yuxi/services/agent_run_service.py"
    names = {"_public_health_error", "_public_health_run_event"}
    functions = [
        node
        for node in ast.parse(source.read_text(encoding="utf-8")).body
        if isinstance(node, ast.FunctionDef) and node.name in names
    ]
    assert {node.name for node in functions} == names
    scope = {"TERMINAL_RUN_STATUSES": {"completed", "failed", "cancelled", "interrupted"}}
    future = ast.parse("from __future__ import annotations").body[0]
    exec(compile(ast.Module(body=[future, *functions], type_ignores=[]), str(source), "exec"), scope)
    return scope["_public_health_run_event"]


def run_identity(context):
    """只使用合成运行的公开身份。"""
    return SimpleNamespace(
        id=context.run_id, request_id=context.request_id, conversation_thread_id=context.thread_id, status="running"
    )


def final_event(kind, *, message_id=None, **fields):
    """构造当前请求的可信事件，边界用例自行修改身份。"""
    context = Context()
    return {
        "type": "health_final_answer_" + kind,
        "message_id": message_id,
        "request_id": context.request_id,
        "run_id": context.run_id,
        "thread_id": context.thread_id,
        **fields,
    }


class RevocableEvidence:
    """独立可撤回引用oracle，不声称验证真实授权或数据库来源。"""

    def __init__(self):
        self.allowed = True
        self.checked = []

    async def validate(self, prefix):
        """必须引用完整，撤回后在下一次公开边界拒绝。"""
        self.checked.append(prefix)
        if not self.allowed:
            raise HealthVisionError("source_invalidated", "synthetic source withdrawn", 410)
        if CITATION not in prefix:
            raise HealthVisionError("citation_invalid", "synthetic citation incomplete", 409)


async def consume_real_graph(model, evidence, public, *, revoke_after_first=False):
    """实际create_agent的custom先经生产helper校验，再经生产公开投影。"""
    context = Context()
    helper = TrustedHealthFinalAnswerStream(
        evidence.validate, request_id=context.request_id, run_id=context.run_id, thread_id=context.thread_id
    )
    project, run = production_projection(), run_identity(context)
    graph = create_agent(
        model,
        tools=[read_authorized_records, production.finalize_health_answer],
        middleware=[production.HealthFinalAnswerMiddleware()],
        context_schema=Context,
        checkpointer=InMemorySaver(),
    )
    native = []
    async with await graph.astream_events(
        {"messages": [HumanMessage("synthetic consultation")]},
        context=context,
        config={"configurable": {"thread_id": context.thread_id}},
        version="v3",
        transformers=[CustomTransformer],
    ) as events:
        async for event in events:
            if event["method"] == "messages":
                raw, _ = event["params"]["data"]
                native.append(raw)
                assert await helper.consume(raw) is None
                assert project(run, "messages", {"payload": {"chunk": {"stream_event": raw}}}) is None
                continue
            if event["method"] != "custom":
                continue
            delta = await helper.consume(event["params"]["data"])
            if not delta:
                continue
            preview = project(
                run,
                "custom",
                {
                    "private": "PRIVATE_ENVELOPE",
                    "payload": {
                        "name": "yuxi.health_answer_delta",
                        "chunk": {
                            "delta": {**delta, "reasoning": "PRIVATE_REASONING"},
                            "validated_prefix": helper.prefix[: helper.published],
                            "metadata": "PRIVATE_METADATA",
                        },
                    },
                },
            )
            assert preview is not None
            public.append(preview)
            if len(public) == 1:
                # 第一段已通过两个生产Owner，第二块模型输出仍被门闩阻塞。
                assert len(model.finished) == 2
                assert len(model.calls) == 3
                assert not model.released.is_set()
                if revoke_after_first:
                    evidence.allowed = False
                model.released.set()
    state = await graph.aget_state({"configurable": {"thread_id": context.thread_id}})
    return helper, native, state, project, run


def paused_model():
    """原始工具前言有完整长段落，不能因正文已经成段而公开。"""
    return ControlledStreamModel(
        plan=[
            [AIMessageChunk(content="PRIVATE_TOOL_PREAMBLE。" * 10 + "\n\n"), tool_chunk(read_authorized_records.name)],
            [tool_chunk(production.finalize_health_answer.name)],
            [AIMessageChunk(content=FIRST), AIMessageChunk(content=SECOND)],
        ],
        released=asyncio.Event(),
    )


@pytest.mark.asyncio
async def test_first_validated_public_delta_precedes_the_paused_models_second_chunk_and_completion():
    model, evidence, public = paused_model(), RevocableEvidence(), []
    helper, native, state, _, _ = await consume_real_graph(model, evidence, public)
    chunks = [event["payload"]["chunk"] for event in public]
    assert [item["content"] for item in chunks] == [FIRST, SECOND]
    assert [item["offset"] for item in chunks] == [0, len(FIRST)]
    assert len(FIRST.encode("utf-16-le")) // 2 > len(FIRST)
    assert len({item["message_id"] for item in chunks}) == 1
    assert all(
        set(item) == {"run_id", "request_id", "thread_id", "status", "content", "offset", "message_id"}
        for item in chunks
    )
    assert evidence.checked == [FIRST, FIRST + SECOND]
    assert helper.published == len(FIRST + SECOND)
    assert state.values["messages"][-1].text == FIRST + SECOND
    native_ids = {item["id"] for item in native if isinstance(item, dict) and item.get("event") == "message-start"}
    assert state.values["messages"][-1].id in native_ids
    assert "PRIVATE_TOOL_PREAMBLE" in json.dumps(native, default=str)
    assert "PRIVATE" not in json.dumps(public)
    assert "validated_prefix" not in json.dumps(public)


@pytest.mark.asyncio
async def test_revoked_source_stops_the_next_real_graph_delta_and_failed_run_cannot_replay_old_preview():
    model, evidence, public = paused_model(), RevocableEvidence(), []
    with pytest.raises(HealthVisionError) as error:
        await consume_real_graph(model, evidence, public, revoke_after_first=True)
    assert error.value.code == "source_invalidated"
    assert len(public) == 1 and public[0]["payload"]["chunk"]["content"] == FIRST
    assert evidence.checked == [FIRST, FIRST + SECOND]
    project, run = production_projection(), run_identity(Context())
    run.status = "failed"
    old = public[0]["payload"]["chunk"]
    assert (
        project(
            run,
            "custom",
            {
                "payload": {
                    "name": "yuxi.health_answer_delta",
                    "chunk": {
                        "delta": {key: old[key] for key in ("content", "offset", "message_id")},
                        "validated_prefix": FIRST,
                    },
                }
            },
        )
        is None
    )


@pytest.mark.asyncio
async def test_partial_citation_waits_until_closed_and_validates_the_same_cumulative_prefix():
    evidence = RevocableEvidence()
    helper = TrustedHealthFinalAnswerStream(
        evidence.validate,
        **{
            "request_id": Context().request_id,
            "run_id": Context().run_id,
            "thread_id": Context().thread_id,
        },
    )
    message_id = str(uuid4())
    await helper.consume(final_event("start", message_id=message_id))
    prefix, tail = FIRST.split(CITATION, 1)
    opening = prefix + CITATION[:-1]
    assert await helper.consume(final_event("delta", message_id=message_id, content=opening, offset=0)) is None
    result = await helper.consume(final_event("delta", message_id=message_id, content="]" + tail, offset=len(opening)))
    assert result == {"content": FIRST, "offset": 0, "message_id": message_id}
    assert evidence.checked[-1] == FIRST
    assert await helper.consume(final_event("end", message_id=message_id, offset=len(FIRST))) is None


@pytest.mark.asyncio
async def test_other_request_run_thread_or_message_cannot_change_current_prefix():
    evidence = RevocableEvidence()
    context, message_id = Context(), str(uuid4())
    helper = TrustedHealthFinalAnswerStream(
        evidence.validate, request_id=context.request_id, run_id=context.run_id, thread_id=context.thread_id
    )
    for key in ("request_id", "run_id", "thread_id"):
        assert await helper.consume(final_event("start", message_id=message_id, **{key: "other"})) is None
    assert helper.message_id == ""
    await helper.consume(final_event("start", message_id=message_id))
    for key in ("request_id", "run_id", "thread_id", "message_id"):
        value = final_event("delta", message_id=message_id, content=FIRST, offset=0)
        value[key] = str(uuid4()) if key == "message_id" else "other"
        assert await helper.consume(value) is None
    assert helper.prefix == "" and not evidence.checked
    assert await helper.consume(final_event("delta", message_id=message_id, content=FIRST, offset=0))
    assert helper.prefix == FIRST


@pytest.mark.asyncio
async def test_duplicate_frames_are_ignored_but_offset_gaps_invalid_types_and_message_switch_fail():
    context, message_id, evidence = Context(), str(uuid4()), RevocableEvidence()
    helper = TrustedHealthFinalAnswerStream(
        evidence.validate, request_id=context.request_id, run_id=context.run_id, thread_id=context.thread_id
    )
    await helper.consume(final_event("start", message_id=message_id))
    value = final_event("delta", message_id=message_id, content=FIRST, offset=0)
    assert await helper.consume(value)
    assert await helper.consume(value) is None
    assert evidence.checked == [FIRST]
    for offset in (True, -1, len(FIRST) + 1, len(FIRST) - 1):
        with pytest.raises(HealthVisionError) as error:
            await helper.consume(final_event("delta", message_id=message_id, content="新内容", offset=offset))
        assert error.value.code == "answer_stream_offset"
    with pytest.raises(HealthVisionError) as error:
        await helper.consume(final_event("start", message_id=str(uuid4())))
    assert error.value.code == "answer_stream_conflict"
    assert helper.prefix == FIRST


@pytest.mark.asyncio
async def test_oversized_trusted_prefix_fails_before_validator_or_publication():
    context, message_id, evidence = Context(), str(uuid4()), RevocableEvidence()
    helper = TrustedHealthFinalAnswerStream(
        evidence.validate, request_id=context.request_id, run_id=context.run_id, thread_id=context.thread_id
    )
    await helper.consume(final_event("start", message_id=message_id))
    with pytest.raises(HealthVisionError) as error:
        await helper.consume(
            final_event("delta", message_id=message_id, content="x" * (MAX_PREFIX_CHARS + 1), offset=0)
        )
    assert error.value.code == "answer_stream_limit"
    assert helper.prefix == "" and not evidence.checked

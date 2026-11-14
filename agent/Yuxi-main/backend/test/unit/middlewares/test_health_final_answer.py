"""真实 create_agent 图验证最终无工具调用的生成时点与私有准备边界。"""

import asyncio
import json
import importlib.util
import sys
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from langchain.agents import create_agent
from langchain.agents.middleware import AgentMiddleware
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGenerationChunk
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.stream.transformers import CustomTransformer
from pydantic import Field

from yuxi.services.health_vision_types import HealthVisionError


def production_middleware(name):
    """原样加载独立中间件，Windows 不装载无关的 Linux 文件系统入口。"""
    source = Path(__file__).resolve().parents[3] / f"package/yuxi/agents/middlewares/{name}.py"
    spec = importlib.util.spec_from_file_location(f"{name}_under_test", source)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


production = production_middleware("health_final_answer")
usage = production_middleware("token_usage")


@dataclass
class Context:
    """仅使用合成的请求和执行身份。"""

    request_id: str = "synthetic-request"
    run_id: str = "synthetic-run"
    thread_id: str = "synthetic-thread"


class ControlledStreamModel(BaseChatModel):
    """使用真实模型流桥；最终第二块必须等测试消费首块后才继续。"""

    plan: list[list[AIMessageChunk]]
    calls: list[dict[str, Any]] = Field(default_factory=list)
    released: Any = None
    finished: list[bool] = Field(default_factory=list)

    @property
    def _llm_type(self):
        """模型完全在本地执行，不依赖供应商。"""
        return "controlled-health-final-stream"

    def bind_tools(self, tools, *, tool_choice=None, **kwargs):
        """记录标准 create_agent 实际绑定的工具和调用策略。"""
        return self.bind(tools=[item.name for item in tools], tool_choice=tool_choice, **kwargs)

    def _generate(self, *args, **kwargs):
        """用例必须经过异步原生流桥。"""
        raise AssertionError("streaming path required")

    async def _astream(self, messages, stop=None, run_manager=None, **kwargs):
        """按预先指定的消息脚本发送，在最终调用中暴露确定性的阻塞点。"""
        index = len(self.calls)
        self.calls.append(
            {"tools": kwargs.get("tools", []), "tool_choice": kwargs.get("tool_choice"), "system": messages[0].text}
        )
        for offset, message in enumerate(self.plan[index]):
            if not kwargs.get("tools") and offset == 1 and self.released is not None:
                await asyncio.wait_for(self.released.wait(), timeout=3)
            yield ChatGenerationChunk(message=message)
        self.finished.append(True)


class ObservedCallMiddleware(AgentMiddleware):
    """验证请求修改继续流经现有内层 handler，而不是绕开用量链。"""

    def __init__(self):
        """每张测试图单独记录。"""
        self.tools = []

    async def awrap_model_call(self, request, handler):
        """记录真正的最终请求工具数并调用标准执行器。"""
        self.tools.append([item.name for item in request.tools])
        return await handler(request)


@tool
async def read_authorized_records() -> str:
    """读取合成的已授权业务记录。"""
    return "synthetic-authorized-records"


def tool_chunk(name):
    """构造模型真实工具调用。"""
    return AIMessageChunk(content="", tool_call_chunks=[{"name": name, "args": "{}", "id": f"call-{name}", "index": 0}])


async def run_graph(model, *, context=None, checkpointer=None, on_custom=None, middleware_prefix=()):
    """通过与 BaseAgent 相同的 v3 transformer 消费实际图事件。"""
    observed = ObservedCallMiddleware()
    graph = create_agent(
        model,
        tools=[read_authorized_records, production.finalize_health_answer],
        system_prompt="原有授权、专业边界和引用规则。",
        middleware=[
            *middleware_prefix,
            production.HealthFinalAnswerMiddleware(),
            observed,
            usage.TokenUsageMiddleware(),
        ],
        context_schema=Context,
        checkpointer=checkpointer,
    )
    custom, native = [], []
    context = context or Context()
    async with await graph.astream_events(
        {"messages": [HumanMessage("synthetic consultation")]},
        context=context,
        config={"configurable": {"thread_id": context.thread_id}},
        version="v3",
        transformers=[CustomTransformer],
    ) as events:
        async for event in events:
            if event["method"] == "custom":
                value = event["params"]["data"]
                custom.append(value)
                if on_custom:
                    on_custom(value)
            elif event["method"] == "messages":
                native.append(event["params"]["data"])
    return graph, custom, native, observed


@pytest.mark.asyncio
@pytest.mark.parametrize("request_matches", [True, False])
async def test_final_graph_provides_only_current_successful_family_citation_ids(request_matches):
    """实际图最终调用只允许引用本轮成功回执的标识。"""
    source_id = "11111111-1111-4111-8111-111111111111"
    filename = "合成营养资料 完整版.docx"

    @tool
    async def query_family_nutrition_knowledge() -> dict:
        """返回合成的当前成功工具资料，不调用外部知识库。"""
        return {"sources": [{"source_id": source_id, "filename": filename}]}

    final_text = (
        json.dumps({"answer": "合成正文。", "citations": [{"kind": "family", "id": source_id}]}, ensure_ascii=False)
        if request_matches
        else "合成正文。"
    )
    model = ControlledStreamModel(
        plan=[
            [tool_chunk(query_family_nutrition_knowledge.name)],
            [tool_chunk(production.finalize_health_answer.name)],
            [AIMessageChunk(content=final_text)],
        ]
    )
    graph = create_agent(
        model,
        tools=[query_family_nutrition_knowledge, production.finalize_health_answer],
        system_prompt="保留原来源校验。",
        middleware=[production.HealthFinalAnswerMiddleware()],
        context_schema=Context,
    )
    old_call = {"name": "query_family_nutrition_knowledge", "id": "old-call", "args": {}}
    old = json.dumps({"sources": [{"source_id": "old-source", "filename": "旧资料.pdf"}]})
    incoming = [
        HumanMessage("上一轮", additional_kwargs={"health_request_id": "old-request"}),
        AIMessage("", tool_calls=[old_call]),
        ToolMessage(old, name=old_call["name"], tool_call_id=old_call["id"]),
        HumanMessage(
            "本轮问题", additional_kwargs={"health_request_id": "synthetic-request" if request_matches else "wrong"}
        ),
        AIMessage("", tool_calls=[{**old_call, "id": "failed-call"}]),
        ToolMessage(old, name=old_call["name"], tool_call_id="failed-call", status="error"),
        AIMessage("", tool_calls=[{**old_call, "name": "unrelated_tool", "id": "other-call"}]),
        ToolMessage(old, name="unrelated_tool", tool_call_id="other-call"),
    ]
    async with await graph.astream_events(
        {"messages": incoming}, context=Context(), version="v3", transformers=[CustomTransformer]
    ) as events:
        async for _ in events:
            pass
    assert len(model.calls) == 3 and model.calls[-1]["tools"] == []
    assert (source_id in model.calls[-1]["system"]) is request_matches
    assert "old-source" not in model.calls[-1]["system"]
    assert filename not in model.calls[-1]["system"]
    assert "保留原来源校验。" in model.calls[-1]["system"]


@pytest.mark.asyncio
@pytest.mark.parametrize("valid_json", [True, False])
async def test_cited_final_answer_requests_provider_json_mode_and_keeps_validation(monkeypatch, valid_json):
    """真实 OpenAI 兼容模型的请求载荷启用 JSON 模式，纯文本仍被拒绝。"""
    source_id = "11111111-1111-4111-8111-111111111111"
    model = ChatOpenAI(model="synthetic", api_key="test", base_url="http://example.invalid")
    events = []
    monkeypatch.setattr(production, "get_stream_writer", lambda: events.append)
    request = SimpleNamespace(
        state={"health_final_request_id": "synthetic-request", "health_answer_phase": "final"},
        runtime=SimpleNamespace(context=Context()),
        messages=[
            HumanMessage("合成问题", additional_kwargs={"health_request_id": "synthetic-request"}),
            ToolMessage(
                json.dumps({"sources": [{"source_id": source_id}]}),
                name="query_family_nutrition_knowledge",
                tool_call_id="source-call",
            ),
        ],
        model=model,
        system_message=HumanMessage("原有引用约束"),
        tools=[],
        tool_choice=None,
        response_format=None,
    )
    request.override = lambda **changes: SimpleNamespace(**{**vars(request), **changes})

    async def handler(prepared):
        assert prepared.tools == [] and prepared.response_format is None
        assert prepared.model.model_kwargs["response_format"] == {"type": "json_object"}
        wire = prepared.model._get_request_payload([HumanMessage("合成问题")])
        assert wire["response_format"] == {"type": "json_object"}
        answer = (
            json.dumps({"answer": "合成答复。", "citations": [{"kind": "family", "id": source_id}]})
            if valid_json
            else "合成答复。"
        )
        return SimpleNamespace(result=[AIMessage(content=answer)])

    if not valid_json:
        with pytest.raises(HealthVisionError, match="citation_invalid"):
            await production.HealthFinalAnswerMiddleware().awrap_model_call(request, handler)
        assert [event["type"] for event in events] == ["health_final_answer_start"]
        return
    result = await production.HealthFinalAnswerMiddleware().awrap_model_call(request, handler)
    assert result.result[0].text == "合成答复。"
    assert result.result[0].additional_kwargs[production.CONSULTATION_CITATIONS_KEY] == [
        {"kind": "family", "id": source_id}
    ]
    assert [event["type"] for event in events] == [
        "health_final_answer_start",
        "health_final_answer_delta",
        "health_final_answer_end",
    ]


@pytest.mark.asyncio
async def test_real_graph_emits_first_custom_before_final_model_finishes_and_never_rewrites_answer():
    gate = asyncio.Event()
    model = ControlledStreamModel(
        plan=[
            [AIMessageChunk(content="PRIVATE_TOOL_PREAMBLE。"), tool_chunk(read_authorized_records.name)],
            [tool_chunk(production.finalize_health_answer.name)],
            [AIMessageChunk(content="第一段🥦。"), AIMessageChunk(content="第二段。")],
        ],
        released=gate,
    )

    def consume(value):
        """第二块产生前必须先收到首个 custom，且最终模型尚未完成。"""
        if value["type"] == "health_final_answer_delta" and value["offset"] == 0:
            assert len(model.finished) == 2
            assert len(model.calls) == 3
            gate.set()

    graph, custom, native, observed = await run_graph(model, checkpointer=InMemorySaver(), on_custom=consume)
    deltas = [item for item in custom if item["type"] == "health_final_answer_delta"]
    assert [item["content"] for item in deltas] == ["第一段🥦。", "第二段。"]
    assert [item["offset"] for item in deltas] == [0, len("第一段🥦。")]
    assert all(item["request_id"] == "synthetic-request" and item["run_id"] == "synthetic-run" for item in custom)
    assert all(item["thread_id"] == "synthetic-thread" for item in custom)
    assert len({item["message_id"] for item in custom}) == 1
    assert "PRIVATE" not in str(custom)
    assert len(native) > 0
    assert [call["tools"] for call in model.calls] == [
        [read_authorized_records.name, production.finalize_health_answer.name],
        [read_authorized_records.name, production.finalize_health_answer.name],
        [],
    ]
    assert [call["tool_choice"] for call in model.calls] == ["any", "any", None]
    assert observed.tools[-1] == []
    state = await graph.aget_state({"configurable": {"thread_id": "synthetic-thread"}})
    assert state.values["messages"][-1].text == "第一段🥦。第二段。"
    native_message_ids = [
        event["id"] for event, _ in native if isinstance(event, dict) and event.get("event") == "message-start"
    ]
    assert state.values["messages"][-1].id == native_message_ids[-1]
    assert state.values["token_usage"]["run"]["model_call_count"] == 3
    assert state.values["token_usage"]["tool_count"] == 0
    assert state.values["token_usage"]["tools_tokens"] == 0
    assert custom[-1]["type"] == "health_final_answer_end"


@pytest.mark.asyncio
async def test_planning_plain_answer_fails_without_any_public_custom():
    model = ControlledStreamModel(plan=[[AIMessageChunk(content="PRIVATE_UNFINALIZED_ANSWER")]])
    seen = []
    with pytest.raises(HealthVisionError) as error:
        await run_graph(model, on_custom=seen.append)
    assert error.value.code == "answer_finalization_required"
    assert len(model.calls) == 1
    assert not seen


@pytest.mark.asyncio
async def test_parallel_finalization_and_business_tool_is_rejected_before_tool_execution():
    calls = AIMessageChunk(
        content="PRIVATE_TOOL_PREAMBLE",
        tool_call_chunks=[
            {"name": read_authorized_records.name, "args": "{}", "id": "call-read", "index": 0},
            {"name": production.finalize_health_answer.name, "args": "{}", "id": "call-final", "index": 1},
        ],
    )
    model = ControlledStreamModel(plan=[[calls]])
    with pytest.raises(HealthVisionError) as error:
        await run_graph(model)
    assert error.value.code == "answer_finalization_required"
    assert len(model.calls) == 1


@pytest.mark.asyncio
async def test_final_callback_ignores_reasoning_and_rejects_tool_blocks():
    for block in (
        tool_chunk("unexpected"),
        AIMessageChunk(content=[{"type": "server_tool_result", "id": "synthetic", "index": 0}]),
    ):
        model = ControlledStreamModel(plan=[[tool_chunk(production.finalize_health_answer.name)], [block]])
        seen = []
        with pytest.raises(HealthVisionError) as error:
            await run_graph(model, on_custom=seen.append)
        assert error.value.code == "answer_stream_tool_call"
        assert [item["type"] for item in seen] == ["health_final_answer_start"]

    model = ControlledStreamModel(
        plan=[
            [tool_chunk(production.finalize_health_answer.name)],
            [
                AIMessageChunk(content=[{"type": "reasoning", "reasoning": "PRIVATE_REASONING", "index": 0}]),
                AIMessageChunk(content=[{"type": "text", "text": "公开正文。", "index": 1}]),
            ],
        ]
    )
    _, custom, _, _ = await run_graph(model)
    assert "PRIVATE" not in str(custom)
    assert [item["content"] for item in custom if "content" in item] == ["公开正文。"]


@pytest.mark.asyncio
async def test_new_request_cannot_reuse_previous_final_phase():
    checkpoint = InMemorySaver()
    first = ControlledStreamModel(
        plan=[[tool_chunk(production.finalize_health_answer.name)], [AIMessageChunk(content="首轮。")]]
    )
    await run_graph(first, checkpointer=checkpoint)
    second = ControlledStreamModel(
        plan=[[tool_chunk(production.finalize_health_answer.name)], [AIMessageChunk(content="次轮。")]]
    )
    _, custom, _, _ = await run_graph(
        second,
        context=Context(request_id="synthetic-request-2", run_id="synthetic-run-2"),
        checkpointer=checkpoint,
    )
    assert len(second.calls) == 2
    assert second.calls[0]["tools"]
    assert all(item["request_id"] == "synthetic-request-2" and item["run_id"] == "synthetic-run-2" for item in custom)


@pytest.mark.asyncio
async def test_real_chat_openai_wire_chunks_do_not_double_publish_provider_token_callbacks():
    class WireStream:
        """SDK兼容的本地流对象，不使用网络或实际供应商。"""

        def __init__(self, items):
            self.items = items

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        def __aiter__(self):
            return self.iterate()

        async def iterate(self):
            """真实 ChatOpenAI._astream 负责转换wire并触发其原生回调。"""
            for item in self.items:
                yield item

    class Completions:
        """只替换供应商传输边界，保留真实模型适配器与完整图。"""

        async def create(self, **payload):
            """先结束工具准备，最终无工具请求发送两个独立正文块。"""
            deltas = (
                [
                    {
                        "role": "assistant",
                        "tool_calls": [
                            {
                                "index": 0,
                                "id": "call-final",
                                "type": "function",
                                "function": {"name": production.finalize_health_answer.name, "arguments": "{}"},
                            }
                        ],
                    }
                ]
                if payload.get("tools")
                else [{"role": "assistant", "content": "FIRST."}, {"content": "SECOND."}]
            )
            return WireStream(
                [
                    {
                        "id": "synthetic",
                        "object": "chat.completion.chunk",
                        "model": "synthetic",
                        "choices": [{"index": 0, "delta": delta, "finish_reason": None}],
                    }
                    for delta in deltas
                ]
            )

    model = ChatOpenAI(model="synthetic", api_key="synthetic", async_client=Completions(), max_retries=0)
    graph, custom, native, _ = await run_graph(model, checkpointer=InMemorySaver())
    deltas = [item for item in custom if item["type"] == "health_final_answer_delta"]
    assert [item["content"] for item in deltas] == ["FIRST.", "SECOND."]
    assert [item["offset"] for item in deltas] == [0, len("FIRST.")]
    assert custom[-1]["offset"] == len("FIRST.SECOND.")
    state = await graph.aget_state({"configurable": {"thread_id": "synthetic-thread"}})
    assert state.values["messages"][-1].text == "FIRST.SECOND."
    native_message_ids = [
        event["id"] for event, _ in native if isinstance(event, dict) and event.get("event") == "message-start"
    ]
    assert native_message_ids[-1] == state.values["messages"][-1].id


@pytest.mark.asyncio
async def test_callback_failure_keeps_final_pending_and_same_request_can_resume_without_repeating_tools():
    checkpoint, seen = InMemorySaver(), []
    failed = ControlledStreamModel(
        plan=[
            [tool_chunk(production.finalize_health_answer.name)],
            [AIMessageChunk(content="尚未完成的首句。"), tool_chunk("unexpected")],
        ]
    )
    with pytest.raises(HealthVisionError) as error:
        await run_graph(failed, checkpointer=checkpoint, on_custom=seen.append)
    assert error.value.code == "answer_stream_tool_call"
    assert [item["type"] for item in seen] == ["health_final_answer_start", "health_final_answer_delta"]
    stored = await checkpoint.aget_tuple({"configurable": {"thread_id": "synthetic-thread"}})
    values = stored.checkpoint["channel_values"]
    assert values["health_answer_phase"] == "final"
    assert values["messages"][-1].type == "tool"
    assert not any(message.text == "尚未完成的首句。" for message in values["messages"])

    resumed = ControlledStreamModel(plan=[[AIMessageChunk(content="恢复后完整答复。")]])
    _, custom, _, observed = await run_graph(resumed, checkpointer=checkpoint)
    assert len(resumed.calls) == 1 and resumed.calls[0]["tools"] == []
    assert observed.tools == [[]]
    assert custom[-1]["type"] == "health_final_answer_end"


@pytest.mark.asyncio
async def test_model_end_is_not_success_when_the_existing_after_model_guard_rejects():
    class RejectSource(AgentMiddleware):
        """独立拒绝oracle模拟现有来源守卫，不替代真实数据库校验。"""

        async def aafter_model(self, state, runtime):
            """仅拒绝最终正文，准备工具仍可正常执行。"""
            if not state["messages"][-1].tool_calls:
                raise HealthVisionError("citation_invalid", "synthetic source rejection", 422)

    model = ControlledStreamModel(
        plan=[[tool_chunk(production.finalize_health_answer.name)], [AIMessageChunk(content="等待来源终验的正文。")]]
    )
    seen = []
    with pytest.raises(HealthVisionError) as error:
        await run_graph(model, on_custom=seen.append, middleware_prefix=[RejectSource()])
    assert error.value.code == "citation_invalid"
    assert seen[-1]["type"] == "health_final_answer_end"

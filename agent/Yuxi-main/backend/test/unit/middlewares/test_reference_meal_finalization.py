"""参考餐单成功保存后由真实模型收尾；合成服务 oracle 不代替 PG 或供应商验收。"""

import json
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from langchain.agents import create_agent
from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import ModelRequest, ModelResponse
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, SystemMessage, ToolMessage
from langchain_core.messages.utils import message_chunk_to_message
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.stream.transformers import CustomTransformer
from pydantic import Field

from test.unit.middlewares.test_health_final_answer import ControlledStreamModel, usage
from yuxi.agents.buildin.health_meal_planner.graph import MealPlanResultMiddleware
from yuxi.agents.toolkits import meal_planner
from yuxi.models.chat import ChatCompletionsAdapter
from yuxi.services import health_meal_plan_service, reference_meal_plan_service
from yuxi.services import model_message_audit_service
from yuxi.services.health_family_planner_types import FAMILY_PLANNER_TOOLS
from yuxi.services.health_initial_meal_plan_types import INITIAL_PLANNER_TOOLS
from yuxi.services.health_safe_planner_types import SAFE_PLANNER_TOOLS
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.services.reference_meal_plan_types import REFERENCE_TOOLS, ReferencePlanDraft

PREVIEW = "00000000-0000-4000-8000-000000000001"
OTHER_PREVIEW = "00000000-0000-4000-8000-000000000002"
TOOLS = [getattr(meal_planner, name) for name in REFERENCE_TOOLS]
DRAFT = {
    "meals": [
        {
            "meal_type": "dinner",
            "dishes": [
                {
                    "file_id": "synthetic-file",
                    "chunk_id": "synthetic-chunk",
                    "name": "合成食谱",
                    "ingredients": ["合成食材"],
                    "steps": ["合成步骤"],
                }
            ],
        }
    ],
    "purchase_items": [],
    "purchase_gaps": [{"ingredient": "合成食材", "reason": "catalog_unavailable", "detail": "合成目录不可用"}],
}


@dataclass
class Context:
    """只提供当前图和工具所需的合成身份与固定模式。"""

    request_id: str = "synthetic-request"
    run_id: str = "synthetic-run"
    thread_id: str = "synthetic-thread"
    tools: list[str] = field(default_factory=lambda: list(REFERENCE_TOOLS))


class RepeatingSaveModel(ControlledStreamModel):
    """工具开放时持续保存；只有真实无工具调用才产生最终模型消息。"""

    fail_first_save: bool = False
    identity_prefix: str = ""
    terminal: AIMessageChunk | None = None
    seen_messages: list = Field(default_factory=list)

    async def _astream(self, messages, stop=None, run_manager=None, **kwargs):
        """复用真实流桥；缺少收尾控制会持续循环至图递归限制。"""
        index = len(self.calls)
        self.seen_messages.append(messages)
        if kwargs.get("tools"):
            draft = (
                {"meals": [], "purchase_items": [], "purchase_gaps": []}
                if self.fail_first_save and not index
                else DRAFT
            )
            chunk = AIMessageChunk(
                id=f"{self.identity_prefix}provider-planning-{index}",
                content="",
                tool_call_chunks=[
                    {
                        "name": "save_reference_meal_plan",
                        "args": json.dumps(draft),
                        "id": f"{self.identity_prefix}save-{index}",
                        "index": 0,
                    }
                ],
                usage_metadata={"input_tokens": 3, "output_tokens": 2, "total_tokens": 5},
            )
        else:
            chunk = self.terminal or AIMessageChunk(
                id=f"{self.identity_prefix}provider-final-real",
                content="模型正文不拥有餐单事实。",
                additional_kwargs={"synthetic_provider_field": "retained"},
                response_metadata={"finish_reason": "stop", "model_name": "synthetic-provider"},
                usage_metadata={"input_tokens": 7, "output_tokens": 4, "total_tokens": 11},
            )
        self.plan.append([chunk])
        async for generation in super()._astream(messages, stop=stop, run_manager=run_manager, **kwargs):
            yield generation


class ObserveRequests(AgentMiddleware):
    """观察经过生产收尾控制和用量链的真实请求。"""

    def __init__(self):
        """每张图保存独立观察结果。"""
        self.requests = []

    async def awrap_model_call(self, request, handler):
        """仅记录输入，继续调用原 handler。"""
        self.requests.append(request)
        return await handler(request)


def human(request_id="synthetic-request"):
    """请求标识与生产授权中间件写入格式一致。"""
    return HumanMessage("合成参考餐单请求", additional_kwargs={"health_request_id": request_id})


def receipt(preview_id=PREVIEW, *, status="success", name="save_reference_meal_plan", content=None):
    """构造协议真实的工具结果，失败内容允许不可解析。"""
    return ToolMessage(
        content=json.dumps({"preview_id": preview_id}) if content is None else content,
        name=name,
        tool_call_id="synthetic-call",
        status=status,
    )


def snapshot(preview_id=PREVIEW):
    """固定服务事实，与模型最终正文独立。"""
    return {
        "preview_id": preview_id,
        "status": "reference_ready",
        "professional_status": "not_reviewed",
        "nutrition_status": "not_calculated",
        "meals": DRAFT["meals"],
    }


@pytest.fixture
def services(monkeypatch):
    """只替换业务服务读取和保存，不替换中间件或图生命周期。"""

    async def final(context, text):
        """业务 oracle 只接受回执选择，返回独立的权威快照。"""
        return snapshot(json.loads(text)["preview_id"])

    saved = AsyncMock(return_value=snapshot())
    final_result = AsyncMock(side_effect=final)
    monkeypatch.setattr(reference_meal_plan_service, "save_reference_plan", saved)
    monkeypatch.setattr(health_meal_plan_service, "planner_final_result", final_result)
    return SimpleNamespace(saved=saved, final=final_result)


def request_for(messages, context=None):
    """真实 ModelRequest 保留原工具策略与结构化输出配置。"""
    return ModelRequest(
        model=ControlledStreamModel(plan=[]),
        messages=messages,
        tools=TOOLS,
        tool_choice="any",
        response_format={"synthetic": "existing-format"},
        system_message=SystemMessage("原有授权、来源与专业边界。"),
        state={"messages": messages},
        runtime=SimpleNamespace(context=context or Context()),
    )


async def run_graph(model, *, context=None, checkpoint=None, messages=None):
    """真实 create_agent、ToolNode、流桥和 checkpoint 驱动全部 hook。"""
    observed = ObserveRequests()
    graph = create_agent(
        model,
        tools=TOOLS,
        system_prompt="原有授权、来源与专业边界。",
        middleware=[MealPlanResultMiddleware(), observed, usage.TokenUsageMiddleware()],
        context_schema=Context,
        checkpointer=checkpoint or InMemorySaver(),
    )
    context = context or Context()
    config = {"configurable": {"thread_id": context.thread_id}}
    native = []
    async for message, metadata in graph.astream(
        {"messages": messages or [human(context.request_id)]}, context=context, config=config, stream_mode="messages"
    ):
        native.append((message, metadata))
    return await graph.aget_state(config), observed, native


def sdk_response(message, identifier, prompt_tokens, completion_tokens, *, stream=False):
    """内存 HTTP 提供完整工具 JSON，只有无工具最终回复使用真实 SSE 格式。"""
    usage_data = {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
    }
    finish_reason = "tool_calls" if message.get("tool_calls") else "stop"
    if not stream:
        return httpx.Response(
            200,
            json={
                "id": identifier,
                "object": "chat.completion",
                "created": 1,
                "model": "gpt-6.1-sol",
                "system_fingerprint": "synthetic-fingerprint",
                "choices": [{"index": 0, "message": message, "finish_reason": finish_reason}],
                "usage": usage_data,
            },
        )

    frames = [
        {
            "id": identifier,
            "object": "chat.completion.chunk",
            "created": 1,
            "model": "gpt-6.1-sol",
            "system_fingerprint": "synthetic-fingerprint",
            "choices": [{"index": 0, "delta": message, "finish_reason": finish_reason}],
        },
        {
            "id": identifier,
            "object": "chat.completion.chunk",
            "created": 1,
            "model": "gpt-6.1-sol",
            "choices": [],
            "usage": usage_data,
        },
    ]
    content = "".join(f"data: {json.dumps(frame)}\n\n" for frame in frames) + "data: [DONE]\n\n"
    return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=content.encode())


@pytest.mark.asyncio
@pytest.mark.parametrize("model_type", [ChatCompletionsAdapter, ChatOpenAI])
@pytest.mark.parametrize("phase", ["preparation", "override_parallel", "saved"])
async def test_reference_serial_tool_setting_reaches_real_openai_wire_only_during_preparation(
    model_type, phase, services
):
    """工具准备接收完整 JSON；原模型不变，保存后的无工具回复仍走 SSE。"""
    wire_requests = []

    def respond(request):
        """内存 HTTP 边界只记录实际载荷，不访问网络。"""
        wire = json.loads(request.content)
        wire_requests.append(wire)
        message = {"role": "assistant", "content": "合成模型回复"}
        if phase != "saved":
            message["tool_calls"] = [
                {
                    "id": "synthetic-search",
                    "type": "function",
                    "function": {"name": "search_reference_recipes", "arguments": '{"query":"燕麦 鸡蛋"}'},
                }
            ]
        return sdk_response(
            message,
            "synthetic-completion",
            3,
            2,
            stream=wire.get("stream") is True,
        )

    settings = {"temperature": 0.17, "max_completion_tokens": 64}
    if phase == "override_parallel":
        settings["parallel_tool_calls"] = True
    original_settings = settings.copy()
    messages = [human(), receipt()] if phase == "saved" else [human()]
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        model = model_type(
            model="gpt-6.1-sol",
            api_key="synthetic-test-key",
            base_url="https://example.invalid/v1",
            http_async_client=client,
            use_responses_api=False,
            stream_usage=True,
            max_retries=0,
        )
        original_streaming = model.disable_streaming
        request = request_for(messages).override(model=model, model_settings=settings)

        async def call_model(prepared):
            """沿用 create_agent 的工具绑定与 model_settings 传递方式。"""
            bound = (
                prepared.model.bind_tools(prepared.tools, tool_choice=prepared.tool_choice, **prepared.model_settings)
                if prepared.tools
                else prepared.model.bind(**prepared.model_settings)
            )
            chunks = [chunk async for chunk in bound.astream([prepared.system_message, *prepared.messages])]
            result = chunks[0]
            for chunk in chunks[1:]:
                result += chunk
            return ModelResponse(result=[message_chunk_to_message(result)])

        handler = AsyncMock(side_effect=call_model)
        result = await MealPlanResultMiddleware().awrap_model_call(request, handler)

    handler.assert_awaited_once()
    prepared = handler.await_args.args[0]
    if model_type is ChatOpenAI and phase != "saved":
        assert prepared is request
    else:
        assert prepared is not request
    assert result.result[0].text == "合成模型回复"
    assert len(wire_requests) == 1
    wire = wire_requests[0]
    assert wire["temperature"] == 0.17 and wire["max_completion_tokens"] == 64
    assert request.model is model and request.model_settings is settings
    assert model.disable_streaming is original_streaming is False
    assert "complete_tool_responses" not in wire
    assert "complete_tool_responses" not in model.model_dump()
    assert settings == original_settings
    assert request.tools == TOOLS and request.tool_choice == "any" and request.response_format
    if phase == "saved":
        assert prepared.tools == [] and prepared.tool_choice is None and prepared.response_format is None
        assert prepared.model_settings == original_settings
        assert prepared.model is model and wire["stream"] is True
        assert "tools" not in wire and "parallel_tool_calls" not in wire
        services.final.assert_awaited_once()
    elif model_type is ChatCompletionsAdapter:
        assert prepared.model_settings == {**original_settings, "parallel_tool_calls": False}
        assert prepared.model_settings is not settings
        assert prepared.model is not model and prepared.model.complete_tool_responses is True
        assert prepared.model.disable_streaming is False and model.complete_tool_responses is False
        assert wire.get("stream") is not True
        assert wire["parallel_tool_calls"] is False
        assert "parallel_tool_calls" not in wire.get("extra_body", {})
        functions = {tool["function"]["name"]: tool["function"] for tool in wire["tools"]}
        assert list(functions) == list(REFERENCE_TOOLS)
        assert "query" in functions["search_reference_recipes"]["parameters"]["required"]
        assert result.result[0].tool_calls == [
            {
                "id": "synthetic-search",
                "name": "search_reference_recipes",
                "args": {"query": "燕麦 鸡蛋"},
                "type": "tool_call",
            }
        ]
        services.final.assert_not_awaited()
    else:
        assert prepared.model is model and prepared.model_settings is settings
        assert wire["stream"] is True
        assert wire.get("parallel_tool_calls") == original_settings.get("parallel_tool_calls")
        services.final.assert_not_awaited()


@pytest.mark.asyncio
async def test_complete_tool_responses_keep_arguments_audit_usage_and_streamed_finalization(services, monkeypatch):
    """真实 SDK 与 v3 图连接三路参数、保存、流式收尾和审计；数据库与来源服务仍为合成边界。"""
    searches = AsyncMock(return_value={"items": [{"file_id": "synthetic-file", "chunk_id": "synthetic-chunk"}]})
    monkeypatch.setattr(reference_meal_plan_service, "search_reference_recipes", searches)
    audit_repository = SimpleNamespace(start=AsyncMock(return_value=(None, True)), finish=AsyncMock())

    @asynccontextmanager
    async def audit_session():
        """只隔离审计数据库，不替换实际生命周期消费者。"""
        yield object()

    monkeypatch.setattr(model_message_audit_service.pg_manager, "get_async_session_context", audit_session)
    monkeypatch.setattr(model_message_audit_service, "ModelMessageAuditRepository", lambda db: audit_repository)
    context = Context()
    collector = model_message_audit_service.ModelMessageAuditCollector(
        run_id=context.run_id,
        request_id=context.request_id,
        thread_id=context.thread_id,
        worker_id="synthetic-worker",
    )
    queries = ["燕麦 鸡蛋", "米饭 鸡胸肉", "西兰花 豆腐"]
    wire_requests = []

    def respond(request):
        """供应商 stub 故意返回三个合法调用，验证参数完整性不依赖其遵守串行请求。"""
        wire = json.loads(request.content)
        wire_requests.append(wire)
        call_index = len(wire_requests)
        if call_index == 1:
            tool_calls = [
                {
                    "id": f"synthetic-search-{index}",
                    "type": "function",
                    "function": {"name": "search_reference_recipes", "arguments": json.dumps({"query": query})},
                }
                for index, query in enumerate(queries)
            ]
        elif call_index == 2:
            tool_calls = [
                {
                    "id": "synthetic-save",
                    "type": "function",
                    "function": {"name": "save_reference_meal_plan", "arguments": json.dumps(DRAFT)},
                }
            ]
        else:
            assert call_index == 3, "保存后只能出现一次无工具最终模型调用"
            tool_calls = []
        message = {"role": "assistant", "content": "模型正文不拥有餐单事实。" if not tool_calls else ""}
        if tool_calls:
            message["tool_calls"] = tool_calls
        return sdk_response(message, f"synthetic-completion-{call_index}", 3, 2, stream=wire.get("stream") is True)

    observed = ObserveRequests()
    native = []
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        model = ChatCompletionsAdapter(
            model="gpt-6.1-sol",
            api_key="synthetic-test-key",
            base_url="https://example.invalid/v1",
            http_async_client=client,
            use_responses_api=False,
            stream_usage=True,
            max_retries=0,
        )
        graph = create_agent(
            model,
            tools=TOOLS,
            middleware=[MealPlanResultMiddleware(), observed, usage.TokenUsageMiddleware()],
            context_schema=Context,
            checkpointer=InMemorySaver(),
        )
        config = {"configurable": {"thread_id": context.thread_id}}
        async with await graph.astream_events(
            {"messages": [human()]}, context=context, config=config, version="v3", transformers=[CustomTransformer]
        ) as events:
            async for event in events:
                if event["method"] != "messages":
                    continue
                params = event["params"]
                message, metadata = params["data"]
                native.append((message, metadata))
                await collector.consume(
                    message,
                    {
                        **metadata,
                        "stream_event": {
                            "namespace": params["namespace"],
                            "seq": event["seq"],
                            "timestamp": params["timestamp"],
                        },
                    },
                )
        state = await graph.aget_state(config)

    assert len(wire_requests) == 3
    assert [wire.get("stream") is True for wire in wire_requests] == [False, False, True]
    assert [wire["parallel_tool_calls"] for wire in wire_requests[:2]] == [False, False]
    assert "tools" not in wire_requests[-1] and "parallel_tool_calls" not in wire_requests[-1]
    assert all("complete_tool_responses" not in wire for wire in wire_requests)
    assert model.disable_streaming is False
    assert model.complete_tool_responses is False and "complete_tool_responses" not in model.model_dump()
    assert all(request.model.complete_tool_responses is True for request in observed.requests[:2])
    assert all(request.model.disable_streaming is False for request in observed.requests)
    assert observed.requests[-1].model is model and observed.requests[-1].tools == []
    assert sorted(call.args[1] for call in searches.await_args_list) == sorted(queries)
    assert all(call.args[0] == context for call in searches.await_args_list)
    tools = [message for message in state.values["messages"] if isinstance(message, ToolMessage)]
    assert len(tools) == 4 and all(message.status == "success" for message in tools)
    assert services.saved.await_count == 1
    assert services.saved.await_args.args[0] == context
    assert ReferencePlanDraft.model_validate(services.saved.await_args.args[1]).model_dump(exclude_none=True) == DRAFT
    assert [json.loads(call.args[1]) for call in services.final.await_args_list] == [{"preview_id": PREVIEW}] * 2
    final = state.values["messages"][-1]
    assert json.loads(final.text) == snapshot()
    lifecycle_starts = [
        message for message, _ in native if isinstance(message, dict) and message.get("event") == "message-start"
    ]
    assert final.id == lifecycle_starts[-1]["id"]
    assert final.usage_metadata["total_tokens"] == 5
    assert state.values["token_usage"]["run"]["model_call_count"] == 3
    assert state.values["token_usage"]["run"]["usage_reported_call_count"] == 3
    assert state.values["token_usage"]["run"]["total"] == {"input_tokens": 9, "output_tokens": 6, "total_tokens": 15}
    assert audit_repository.start.await_count == audit_repository.finish.await_count == 3
    started = [call.kwargs for call in audit_repository.start.await_args_list]
    finished = [call.kwargs for call in audit_repository.finish.await_args_list]
    assert [item["operation_id"] for item in started] == [item["operation_id"] for item in finished]
    assert finished[-1]["operation_id"] == final.id
    assert all(item["run_id"] == context.run_id and item["request_id"] == context.request_id for item in finished)
    assert [item["usage"]["total_tokens"] for item in finished] == [5, 5, 5]
    assert [item["metadata"]["finish_metadata"]["finish_reason"] for item in finished] == [
        "tool_calls",
        "tool_calls",
        "stop",
    ]
    assert [item["metadata"]["finish_metadata"]["id"] for item in finished[:2]] == [
        "synthetic-completion-1",
        "synthetic-completion-2",
    ]
    assert all(item["metadata"]["finish_metadata"]["model_name"] == "gpt-6.1-sol" for item in finished)
    assert all(item["metadata"]["finish_metadata"]["model_provider"] == "openai" for item in finished)
    assert all(
        item["metadata"]["finish_metadata"]["system_fingerprint"] == "synthetic-fingerprint" for item in finished
    )
    assert [item["metadata"]["finish_metadata"]["token_usage"]["total_tokens"] for item in finished[:2]] == [5, 5]
    assert [call["args"]["query"] for call in finished[0]["metadata"]["tool_calls"]] == queries
    assert finished[1]["metadata"]["tool_calls"][0]["name"] == "save_reference_meal_plan"
    assert not finished[-1]["metadata"]["tool_calls"]


@pytest.mark.asyncio
@pytest.mark.parametrize("arguments", ["invalid-json", '{"query":'])
@pytest.mark.parametrize("preserve_reasoning,output_version", [(False, None), (True, "v1")])
async def test_complete_response_keeps_invalid_arguments_without_executing_tools(
    arguments, preserve_reasoning, output_version, monkeypatch
):
    """真实 SDK/ToolNode 参数边界保持非法记录；不以模型桥证明来源授权或最终发布。"""
    search = AsyncMock()
    monkeypatch.setattr(reference_meal_plan_service, "search_reference_recipes", search)
    wire_requests = []

    def respond(request):
        """非法参数为独立输入，禁止补成空对象或有效查询。"""
        wire_requests.append(json.loads(request.content))
        return sdk_response(
            {
                "role": "assistant",
                "content": "",
                "reasoning_content": "合成推理原文",
                "tool_calls": [
                    {
                        "id": "synthetic-invalid-call",
                        "type": "function",
                        "function": {"name": "search_reference_recipes", "arguments": arguments},
                    }
                ],
            },
            "synthetic-invalid-completion",
            3,
            2,
            stream=wire_requests[-1].get("stream") is True,
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        original = ChatCompletionsAdapter(
            model="gpt-6.1-sol",
            api_key="synthetic-test-key",
            base_url="https://example.invalid/v1",
            http_async_client=client,
            preserve_reasoning=preserve_reasoning,
            output_version=output_version,
            use_responses_api=False,
            max_retries=0,
        )
        model = original.model_copy(update={"complete_tool_responses": True})
        graph = create_agent(model, tools=TOOLS, context_schema=Context, checkpointer=InMemorySaver())
        context = Context()
        config = {"configurable": {"thread_id": context.thread_id}}
        async with await graph.astream_events(
            {"messages": [human()]}, context=context, config=config, version="v3", transformers=[CustomTransformer]
        ) as events:
            async for _ in events:
                pass
        state = await graph.aget_state(config)

    assert len(wire_requests) == 1 and wire_requests[0].get("stream") is False
    assert "complete_tool_responses" not in wire_requests[0] and "complete_tool_responses" not in model.model_dump()
    assert original.complete_tool_responses is False and original.disable_streaming is False
    search.assert_not_awaited()
    assert not any(isinstance(message, ToolMessage) for message in state.values["messages"])
    final = state.values["messages"][-1]
    assert not final.tool_calls and len(final.invalid_tool_calls) == 1
    invalid = final.invalid_tool_calls[0]
    assert invalid["id"] == "synthetic-invalid-call"
    assert invalid["name"] == "search_reference_recipes" and invalid["args"] == arguments
    assert invalid["error"]
    assert final.usage_metadata["total_tokens"] == 5
    assert final.response_metadata["finish_reason"] == "tool_calls"
    assert final.response_metadata["id"] == "synthetic-invalid-completion"
    assert final.response_metadata["model_name"] == "gpt-6.1-sol"
    if preserve_reasoning:
        assert any(block.get("reasoning") == "合成推理原文" for block in final.content_blocks)


@pytest.mark.asyncio
@pytest.mark.parametrize("boundary", ["non_reference", "non_openai", "no_tools"])
async def test_serial_tool_setting_does_not_change_other_requests(boundary, services):
    """非参考、非 OpenAI 和无工具准备请求不继承供应商参数。"""
    context = Context(tools=list(SAFE_PLANNER_TOOLS)) if boundary == "non_reference" else Context()
    settings = {"temperature": 0.17}
    request = request_for([human()], context).override(model_settings=settings)
    if boundary != "non_openai":
        request = request.override(model=ChatCompletionsAdapter(model="gpt-6.1-sol", api_key="synthetic-test-key"))
    if boundary == "no_tools":
        request = request.override(tools=[])
    handler = AsyncMock(return_value=ModelResponse(result=[AIMessage(content="继续准备")]))

    await MealPlanResultMiddleware().awrap_model_call(request, handler)

    handler.assert_awaited_once_with(request)
    assert request.model_settings is settings and settings == {"temperature": 0.17}
    if isinstance(request.model, ChatCompletionsAdapter):
        assert request.model.complete_tool_responses is False and request.model.disable_streaming is False
    services.final.assert_not_awaited()


@pytest.mark.asyncio
async def test_successful_save_triggers_one_real_tool_free_model_and_preserves_identity_usage(services):
    """缺陷恢复后此模型会继续保存；修复后只有两次真实调用和一次工具执行。"""
    model = RepeatingSaveModel(plan=[])
    state, observed, native = await run_graph(model)
    assert [call["tools"] for call in model.calls] == [list(REFERENCE_TOOLS), []]
    assert len(model.finished) == 2
    services.saved.assert_awaited_once()
    assert services.saved.await_args.args[0] == Context()
    assert ReferencePlanDraft.model_validate(services.saved.await_args.args[1]).model_dump(exclude_none=True) == DRAFT
    assert len([item for item in state.values["messages"] if isinstance(item, ToolMessage)]) == 1
    assert len(observed.requests) == 2
    final_request = observed.requests[-1]
    assert final_request.tools == [] and final_request.tool_choice is None and final_request.response_format is None
    assert final_request.system_message.text.startswith("原有授权、来源与专业边界。")
    assert PREVIEW in final_request.system_message.text
    final_message = state.values["messages"][-1]
    assert json.loads(final_message.text) == snapshot()
    final_model_chunks = [
        message
        for message, _ in native
        if isinstance(message, AIMessageChunk) and message.text == "模型正文不拥有餐单事实。"
    ]
    assert len(final_model_chunks) == 1
    assert final_message.id == "provider-final-real" == final_model_chunks[0].id
    assert final_message.additional_kwargs == {"synthetic_provider_field": "retained"}
    assert final_message.response_metadata["finish_reason"] == "stop"
    assert final_message.response_metadata["model_name"] == "synthetic-provider"
    assert final_message.usage_metadata == {"input_tokens": 7, "output_tokens": 4, "total_tokens": 11}
    assert state.values["token_usage"]["run"]["model_call_count"] == 2
    assert state.values["token_usage"]["tool_count"] == 0
    assert [json.loads(call.args[1]) for call in services.final.await_args_list] == [{"preview_id": PREVIEW}] * 2


@pytest.mark.asyncio
async def test_failed_save_can_be_corrected_before_tool_free_finalization(services):
    """真实 ToolNode 将首轮 schema 失败写成 error，修正成功后才进入最终调用。"""
    model = RepeatingSaveModel(plan=[], fail_first_save=True)
    state, _, _ = await run_graph(model)
    assert [bool(call["tools"]) for call in model.calls] == [True, True, False]
    assert [item.status for item in state.values["messages"] if isinstance(item, ToolMessage)] == ["error", "success"]
    assert services.saved.await_count == 1 and services.final.await_count == 2
    assert json.loads(state.values["messages"][-1].text) == snapshot()


@pytest.mark.asyncio
async def test_same_checkpoint_new_request_must_save_again(services):
    """同一线程旧成功回执不能跳过下一请求的准备工具。"""
    checkpoint = InMemorySaver()
    await run_graph(RepeatingSaveModel(plan=[]), checkpoint=checkpoint)
    services.saved.return_value = snapshot(OTHER_PREVIEW)
    second = RepeatingSaveModel(plan=[], identity_prefix="second-")
    state, _, _ = await run_graph(
        second,
        checkpoint=checkpoint,
        context=Context(request_id="second-request", run_id="second-run"),
    )
    assert [bool(call["tools"]) for call in second.calls] == [True, False]
    assert services.saved.await_count == 2
    assert json.loads(state.values["messages"][-1].text) == snapshot(OTHER_PREVIEW)


@pytest.mark.asyncio
@pytest.mark.parametrize("boundary", ["no_human", "untagged", "latest_other_request", "save_before_current_human"])
async def test_old_or_unscoped_receipts_keep_original_request(boundary, services):
    """只检查最新 Human 的请求边界，不向前搜寻可利用的旧请求标签。"""
    messages = {
        "no_human": [receipt()],
        "untagged": [HumanMessage("无标签"), receipt()],
        "latest_other_request": [human(), human("other-request"), receipt()],
        "save_before_current_human": [human("old-request"), receipt(), human()],
    }[boundary]
    request = request_for(messages)
    handler = AsyncMock(return_value=ModelResponse(result=[AIMessage(content="继续准备")]))
    await MealPlanResultMiddleware().awrap_model_call(request, handler)
    handler.assert_awaited_once_with(request)
    services.final.assert_not_awaited()


@pytest.mark.asyncio
async def test_failed_save_alone_keeps_preparation_and_original_question_contract(services):
    """失败保存不能提前收尾，原有补充问题仍交给业务服务核验。"""
    messages = [human(), receipt(status="error", content="合成保存失败")]
    request = request_for(messages)
    handler = AsyncMock(return_value=ModelResponse(result=[AIMessage(content="继续准备")]))
    middleware = MealPlanResultMiddleware()
    await middleware.awrap_model_call(request, handler)
    handler.assert_awaited_once_with(request)
    services.final.assert_not_awaited()
    original = '{"questions":["还需补充哪项资料？"]}'
    services.final.side_effect = None
    services.final.return_value = {"status": "needs_input"}
    result = await middleware.aafter_model({"messages": [*messages, AIMessage(content=original)]}, request.runtime)
    services.final.assert_awaited_once_with(request.runtime.context, original)
    assert json.loads(result["messages"][0].text) == {"status": "needs_input"}


@pytest.mark.asyncio
async def test_duplicate_receipts_ignore_failed_or_other_tools_and_use_current_candidate(services):
    """同 ID 幂等去重；失败与其他工具不得制造候选，也不能由最终模型换 ID。"""
    messages = [
        human(),
        receipt(content="失败正文", status="error"),
        receipt(OTHER_PREVIEW, name="read_reference_recipe"),
        receipt(),
        receipt(),
    ]
    request = request_for(messages, Context(tools=[*REFERENCE_TOOLS, "query_family_nutrition_knowledge"]))
    handler = AsyncMock(return_value=ModelResponse(result=[AIMessage(content="最终模型")]))
    await MealPlanResultMiddleware().awrap_model_call(request, handler)
    prepared = handler.await_args.args[0]
    assert prepared.tools == [] and prepared.tool_choice is None and prepared.response_format is None
    assert request.tools == TOOLS and request.tool_choice == "any" and request.response_format
    final = AIMessage(content=json.dumps({"preview_id": OTHER_PREVIEW}), id="real-final-id")
    result = await MealPlanResultMiddleware().aafter_model({"messages": [*messages, final]}, request.runtime)
    assert json.loads(result["messages"][0].text) == snapshot()
    assert result["messages"][0].id == "real-final-id"
    assert final.text == json.dumps({"preview_id": OTHER_PREVIEW})
    assert [json.loads(call.args[1]) for call in services.final.await_args_list] == [{"preview_id": PREVIEW}] * 2


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", ["ambiguous", "malformed", "missing", "wrong_type"])
async def test_ambiguous_or_malformed_success_receipt_fails_closed(bad, services):
    """成功保存审计格式错误或出现不同 ID 时，两个 hook 都必须拒绝。"""
    extra = {
        "ambiguous": receipt(OTHER_PREVIEW),
        "malformed": receipt(content="{broken"),
        "missing": receipt(content="{}"),
        "wrong_type": receipt(content='{"preview_id":12}'),
    }[bad]
    request = request_for([human(), receipt(), extra])
    handler = AsyncMock()
    with pytest.raises(HealthVisionError, match="reference_receipt_invalid"):
        await MealPlanResultMiddleware().awrap_model_call(request, handler)
    with pytest.raises(HealthVisionError, match="reference_receipt_invalid"):
        await MealPlanResultMiddleware().aafter_model(
            {"messages": [*request.messages, AIMessage(content="最终正文")]}, request.runtime
        )
    handler.assert_not_awaited()
    services.final.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mode",
    [
        SAFE_PLANNER_TOOLS,
        INITIAL_PLANNER_TOOLS,
        FAMILY_PLANNER_TOOLS,
        ("search_meal_plan_recipes", "preview_meal_plan"),
    ],
)
async def test_other_planner_modes_keep_original_final_answer_contract(mode, services):
    """正式单人、初始、家庭和普通草稿模式不继承参考餐单强制收尾。"""
    request = request_for([human(), receipt()], Context(tools=list(mode)))
    handler = AsyncMock(return_value=ModelResponse(result=[AIMessage(content="继续原流程")]))
    await MealPlanResultMiddleware().awrap_model_call(request, handler)
    handler.assert_awaited_once_with(request)
    services.final.assert_not_awaited()
    original = '{"questions":["合成补充问题"]}'
    services.final.return_value = {"status": "needs_input"}
    services.final.side_effect = None
    await MealPlanResultMiddleware().aafter_model(
        {"messages": [*request.messages, AIMessage(content=original)]}, request.runtime
    )
    services.final.assert_awaited_once_with(request.runtime.context, original)


@pytest.mark.asyncio
async def test_real_final_service_rejects_missing_current_run_audit_before_model(monkeypatch):
    """真实 planner/reference 服务要求同 Run 完成审计，checkpoint 中的成功字样不够。"""
    session, run = object(), SimpleNamespace(id="current-run", uid="synthetic-user")
    binding = SimpleNamespace(initial_planner_selection={"selection": {"mode": "reference"}})

    @asynccontextmanager
    async def session_context():
        """只替换数据库连接边界。"""
        yield session

    monkeypatch.setattr(health_meal_plan_service.pg_manager, "get_async_session_context", session_context)
    monkeypatch.setattr(health_meal_plan_service, "require_planner_run", AsyncMock(return_value=(run, binding)))
    monkeypatch.setattr(reference_meal_plan_service, "bound_reference_context", AsyncMock())
    monkeypatch.setattr(reference_meal_plan_service, "reference_result_in_session", AsyncMock(return_value=snapshot()))
    audits = AsyncMock(return_value=[])
    monkeypatch.setattr(reference_meal_plan_service, "tool_payloads", audits)
    handler = AsyncMock()
    with pytest.raises(HealthVisionError, match="reference_receipt_invalid"):
        await MealPlanResultMiddleware().awrap_model_call(request_for([human(), receipt()]), handler)
    audits.assert_awaited_once_with(session, run, "save_reference_meal_plan")
    handler.assert_not_awaited()


@pytest.mark.asyncio
async def test_source_invalidated_after_final_model_is_rechecked_and_rejected(services):
    """准备时有效不能替代最终重验；失败时 checkpoint 不含可发布最终快照。"""
    services.final.side_effect = [snapshot(), HealthVisionError("source_invalidated", "合成来源已失效", 410)]
    model, checkpoint = RepeatingSaveModel(plan=[]), InMemorySaver()
    with pytest.raises(HealthVisionError, match="source_invalidated"):
        await run_graph(model, checkpoint=checkpoint)
    assert [bool(call["tools"]) for call in model.calls] == [True, False]
    assert services.saved.await_count == 1 and services.final.await_count == 2
    stored = await checkpoint.aget_tuple({"configurable": {"thread_id": "synthetic-thread"}})
    assert not any(
        isinstance(message, AIMessage) and message.content == json.dumps(snapshot(), ensure_ascii=False)
        for message in stored.checkpoint["channel_values"]["messages"]
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("arguments", ["{}", "invalid-json"])
async def test_provider_tool_calls_in_tool_free_final_turn_never_execute(arguments, services):
    """供应商忽略无工具请求时，合法或非法工具调用都不能继续执行。"""
    terminal = AIMessageChunk(
        id="provider-violated-final",
        content="",
        tool_call_chunks=[{"name": "save_reference_meal_plan", "args": arguments, "id": "extra-save", "index": 0}],
    )
    model = RepeatingSaveModel(plan=[], terminal=terminal)
    with pytest.raises(HealthVisionError, match="planner_finalization_invalid"):
        await run_graph(model)
    assert [bool(call["tools"]) for call in model.calls] == [True, False]
    assert services.saved.await_count == 1 and services.final.await_count == 1

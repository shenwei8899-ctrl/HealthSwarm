"""历史失败轮次在实际模型发送边界不再携带未完成的工具调用。"""

from copy import deepcopy
import json

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from pydantic import SecretStr

from yuxi.models.chat import ChatCompletionsAdapter


def messages():
    """模拟真实 checkpoint：已完成一条工具调用，三条未完成，随后用户重问。"""
    return [
        HumanMessage(content="synthetic old question"),
        AIMessage(content="", tool_calls=[{"id": "done", "name": "get_context", "args": {}}]),
        ToolMessage(content="synthetic result", tool_call_id="done"),
        AIMessage(content="", tool_calls=[{"id": f"missing-{i}", "name": "read_recipe", "args": {}} for i in range(3)]),
        HumanMessage(content="synthetic new question"),
    ]


def adapter():
    """使用真实 ChatOpenAI 子类，外部 HTTP 由测试夹具接管。"""
    return ChatCompletionsAdapter(model="test", api_key=SecretStr("test-key"), base_url="http://test.local/v1")


def assert_wire(request):
    """独立检查实际 HTTP JSON：保留完成配对，无伪造 tool 输出，当前问题不变。"""
    wire = json.loads(request.content)["messages"]
    assert wire[1]["tool_calls"][0]["id"] == "done"
    assert wire[2]["tool_call_id"] == "done"
    assert "tool_calls" not in wire[3]
    assert "上次工具调用未完成" in wire[3]["content"]
    assert [m["role"] for m in wire].count("tool") == 1
    assert wire[-1]["content"] == "synthetic new question"


def test_sync_actual_http_and_checkpoint_is_unchanged(httpx_mock):
    original = messages()
    before = deepcopy(original)
    httpx_mock.add_response(
        url="http://test.local/v1/chat/completions",
        json={"choices": [{"message": {"role": "assistant", "content": "ok"}}]},
    )
    adapter().invoke(original)
    assert_wire(httpx_mock.get_request())
    assert original == before


@pytest.mark.asyncio
async def test_async_stream_actual_http(httpx_mock):
    httpx_mock.add_response(
        url="http://test.local/v1/chat/completions",
        text='data: {"choices":[{"delta":{"content":"ok"},"index":0}]}\n\ndata: [DONE]\n\n',
    )
    async for _ in adapter().astream(messages()):
        pass
    assert_wire(httpx_mock.get_request())


def test_current_tool_call_is_left_for_agent_execution():
    original = messages()[:-1]
    wire = adapter()._get_request_payload(original)["messages"]
    assert len(wire[-1]["tool_calls"]) == 3


def test_partially_completed_group_keeps_the_actual_result():
    original = messages()
    original.insert(-1, ToolMessage(content="actual saved output", tool_call_id="missing-1"))
    wire = adapter()._get_request_payload(original)["messages"]
    assert [c["id"] for c in wire[3]["tool_calls"]] == ["missing-1"]
    assert wire[4]["content"] == "actual saved output"
    assert "missing-0" not in json.dumps(wire)


def test_complete_history_has_no_interruption_notice():
    original = messages()[:3] + [HumanMessage(content="new question")]
    wire = adapter()._get_request_payload(original)["messages"]
    assert "上次工具调用未完成" not in json.dumps(wire, ensure_ascii=False)
    assert wire[1]["tool_calls"][0]["id"] == "done"

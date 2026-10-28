"""用合成目录及真实 Agent 工具节点验证重复查询和模型输入边界。"""

import json
from types import SimpleNamespace

import pytest
from langchain.agents import create_agent
from langchain.agents.middleware.types import ToolCallRequest
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import tool
from langgraph.checkpoint.memory import InMemorySaver

from yuxi.agents.middlewares.health_catalog_context import (
    HealthCatalogContextMiddleware,
    compact_catalog_messages,
)

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]


def call(identity, **args):
    """构造稳定工具身份，空参数复现线上重复浏览。"""
    return {"name": "find_food_packages", "args": args, "id": identity, "type": "tool_call"}


def catalog(version="v1"):
    """只使用合成资料，同时保留未知过敏原与非实测限制。"""
    description = "营养说明仅为同类食材参考，非本商品实测；过敏原未知。" * 40
    return {
        "catalog_context_version": 1,
        "catalog_version": version,
        "catalog_index": [{"sku_id": str(i), "name": "合成食材" + str(i), "spec": "1份"} for i in range(95)],
        "profile_context": {"allergyStatus": "unknown", "doctorStatus": "unknown"},
        "offers": [
            {
                "sku_id": "1",
                "product_description": description,
                "note": "适用性待核实。\n" + description,
                "offer_token": "synthetic-signed-receipt-" * 70,
                "purchase_eligible": False,
            }
        ],
    }


def result(identity="first", payload=None, status="success"):
    """工具原始消息代表服务端回执。"""
    return ToolMessage(
        content=json.dumps(catalog() if payload is None else payload, ensure_ascii=False),
        tool_call_id=identity,
        name="find_food_packages",
        status=status,
    )


async def invoke(messages, current, handler):
    """运行实际工具包装入口。"""
    request = ToolCallRequest(
        tool_call=current, tool=None, state={"messages": messages}, runtime=SimpleNamespace(context=None)
    )
    return await HealthCatalogContextMiddleware().awrap_tool_call(request, handler)


@pytest.mark.parametrize("parallel", [False, True])
async def test_identical_query_does_not_execute_again(parallel):
    first, second = call("first", query="", offset=0), call("second")
    repeats = [second, call("third")] if parallel else [second]
    messages = [
        HumanMessage("合成选菜需求"),
        AIMessage("", tool_calls=[first]),
        result(),
        AIMessage("", tool_calls=repeats),
    ]

    async def forbidden(request):
        raise AssertionError("重复查询不应再次读取商城")

    reply = await invoke(messages, second, forbidden)
    assert reply.tool_call_id == "second"
    assert json.loads(reply.content)["original_tool_call_id"] == "first"
    assert json.loads(reply.content)["offers"] == []
    assert "profile_context" not in json.loads(reply.content)


async def test_inflight_first_query_is_not_reported_as_successful_source():
    first, second = call("first"), call("second")
    messages = [HumanMessage("合成需求"), AIMessage("", tool_calls=[first, second])]

    async def failure(request):
        return result(request.tool_call["id"], {"error": "catalog_unavailable"}, status="error")

    reply = await invoke(messages, second, failure)
    assert reply.status == "error"
    assert not json.loads(reply.content).get("duplicate_query")


@pytest.mark.parametrize("change", ["new_turn", "page", "query", "failed", "invalid", "duplicate_only"])
async def test_different_or_unsuccessful_queries_still_execute(change):
    first, second = call("first", query="豆腐"), call("second", query="豆腐")
    original = result()
    if change == "page":
        second["args"]["offset"] = 3
    elif change == "query":
        second["args"]["query"] = "鸡蛋"
    elif change == "failed":
        original = result(status="error")
    elif change == "invalid":
        second["args"]["member_id"] = "forged"
    elif change == "duplicate_only":
        original = result(payload={"duplicate_query": True, "offers": []})
    messages = [HumanMessage("第一轮"), AIMessage("", tool_calls=[first]), original]
    if change == "new_turn":
        messages.append(HumanMessage("第二轮"))
    messages.append(AIMessage("", tool_calls=[second]))

    async def execute(request):
        return result(request.tool_call["id"], {"offers": [], "message": "真实空结果"})

    reply = await invoke(messages, second, execute)
    assert json.loads(reply.content) == {"offers": [], "message": "真实空结果"}


async def test_projection_reduces_payload_and_preserves_original_safety_receipts():
    originals = [HumanMessage("第一轮"), result("a"), result("b"), result("c")]
    before = [message.model_dump() for message in originals]
    compacted = compact_catalog_messages(originals)
    payloads = [json.loads(m.content) for m in compacted[1:]]
    assert len(payloads[0]["catalog_index"]) == 95
    assert payloads[1]["catalog_index_from_tool_call_id"] == "a"
    assert "catalog_index" not in payloads[1]
    for payload in payloads:
        offer = payload["offers"][0]
        assert offer["product_description"] == catalog()["offers"][0]["product_description"]
        assert offer["note"] == "适用性待核实。"
        assert offer["purchase_eligible"] is False
        assert payload["profile_context"] == catalog()["profile_context"]
        assert "offer_token" not in offer
    assert [message.model_dump() for message in originals] == before
    assert sum(len(m.content) for m in compacted) < sum(len(m.content) for m in originals) * 0.45


async def test_new_catalog_or_new_turn_keeps_its_own_index_and_legacy_receipts():
    legacy = result("legacy", {"offers": [{"reference": "[食材包:synthetic-signature]"}]})
    messages = [
        HumanMessage("第一轮"),
        result("a"),
        result("b", catalog("v2")),
        HumanMessage("第二轮"),
        result("c"),
        legacy,
    ]
    compacted = compact_catalog_messages(messages)
    for index in [1, 2, 4]:
        assert "catalog_index" in json.loads(compacted[index].content)
    assert compacted[-1] is legacy


class CatalogModel(BaseChatModel):
    """合成供应商复现首次查询后并行重复空参数，再给出最终答复。"""

    inputs: list = []

    @property
    def _llm_type(self):
        return "synthetic-catalog"

    def bind_tools(self, tools, **kwargs):
        """真实 Agent 继续通过 ToolNode 执行已注册工具。"""
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        """保存模型实际收到的输入，按当前轮工具数量返回预置调用。"""
        self.inputs.append(messages)
        start = max(i for i, m in enumerate(messages) if isinstance(m, HumanMessage))
        count = sum(isinstance(m, ToolMessage) for m in messages[start:])
        if count == 0:
            answer = AIMessage("", tool_calls=[call("first-" + str(len(self.inputs)), query="", offset=0)])
        elif count == 1:
            answer = AIMessage("", tool_calls=[call("repeat-" + str(len(self.inputs)) + str(i)) for i in range(3)])
        else:
            answer = AIMessage("已读取合成食材资料；过敏原未知，适用性待核实。")
        return ChatResult(generations=[ChatGeneration(message=answer)])


async def test_real_agent_parallel_tools_checkpoint_resume_and_new_request():
    executions = []

    @tool
    async def find_food_packages(query: str = "", offset: int = 0) -> dict:
        """合成商城返回完整回执，记录实际调用以验证去重。"""
        executions.append((query, offset))
        return catalog()

    model = CatalogModel()
    checkpoint = InMemorySaver()
    agent = create_agent(
        model=model, tools=[find_food_packages], middleware=[HealthCatalogContextMiddleware()], checkpointer=checkpoint
    )
    config = {"configurable": {"thread_id": "synthetic-catalog"}}
    state = await agent.ainvoke({"messages": [HumanMessage("合成选菜需求")]}, config)
    assert executions == [("", 0)]
    tools = [m for m in state["messages"] if isinstance(m, ToolMessage)]
    assert len(tools) == 4 and len({m.tool_call_id for m in tools}) == 4
    assert "offer_token" in json.loads(tools[0].content)["offers"][0]
    assert "适用性待核实" in state["messages"][-1].content
    saved = await agent.aget_state(config)
    assert saved.values["messages"] == state["messages"]
    # 再构图模拟进程恢复；去重不依赖中间件实例中的缓存。
    restored = create_agent(
        model=model, tools=[find_food_packages], middleware=[HealthCatalogContextMiddleware()], checkpointer=checkpoint
    )
    await restored.ainvoke({"messages": [HumanMessage("另一轮合成需求")]}, config)
    assert executions == [("", 0), ("", 0)]


async def test_same_scripted_conversation_reduces_calls_and_model_input():
    calls = []

    @tool
    async def find_food_packages(query: str = "", offset: int = 0) -> dict:
        """同一合成商品服务用于修复前后对照。"""
        calls.append((query, offset))
        return catalog()

    measurements = []
    for middleware in [[], [HealthCatalogContextMiddleware()]]:
        calls.clear()
        model = CatalogModel()
        graph = create_agent(model=model, tools=[find_food_packages], middleware=middleware)
        final = await graph.ainvoke({"messages": [HumanMessage("合成选菜需求")]})
        measurements.append((len(calls), sum(len(m.content) for turn in model.inputs for m in turn)))
        assert "过敏原未知" in final["messages"][-1].content
    assert measurements[0][0] == 4 and measurements[1][0] == 1
    assert measurements[1][1] < measurements[0][1] * 0.45
    print("synthetic_catalog_comparison=" + json.dumps({"before": measurements[0], "after": measurements[1]}))


async def test_unfinished_tool_batch_resumes_from_saved_successful_query():
    executions = []

    @tool
    async def find_food_packages(query: str = "", offset: int = 0) -> dict:
        """已完成的商品回执在恢复中复用，后续重复批次不重新访问商城。"""
        executions.append((query, offset))
        return catalog()

    checkpoint = InMemorySaver()
    model = CatalogModel()
    graph = create_agent(
        model=model,
        tools=[find_food_packages],
        middleware=[HealthCatalogContextMiddleware()],
        checkpointer=checkpoint,
        interrupt_before=["tools"],
    )
    config = {"configurable": {"thread_id": "synthetic-interrupted"}}
    await graph.ainvoke({"messages": [HumanMessage("合成需求")]}, config)
    assert executions == []
    # 首次恢复执行初次查询，随后在重复批次工具节点前再次中断。
    await graph.ainvoke(None, config)
    pending = await graph.aget_state(config)
    assert pending.next == ("tools", "tools", "tools") and executions == [("", 0)]
    assert len(pending.values["messages"][-1].tool_calls) == 3
    restored = create_agent(
        model=model, tools=[find_food_packages], middleware=[HealthCatalogContextMiddleware()], checkpointer=checkpoint
    )
    final = await restored.ainvoke(None, config)
    assert executions == [("", 0)]
    assert "适用性待核实" in final["messages"][-1].content

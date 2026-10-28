"""真实图组合目录与最终流；合成工具和预算oracle不替代PG或provider验收。"""

import ast
import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest
from langchain.agents import create_agent
from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import ModelRequest, ModelResponse
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.stream.transformers import CustomTransformer

from test.unit.middlewares.test_health_final_answer import (
    Context,
    ControlledStreamModel,
    production,
    production_middleware,
    tool_chunk,
)
from yuxi.services.health_vision_types import HealthVisionError

catalog = production_middleware("health_catalog")


@tool
async def find_food_packages() -> str:
    """返回合成目录，不查询真实商城。"""
    return "synthetic catalog"


@tool
async def select_food_products() -> str:
    """返回合成选择，不写商品、订单或实际业务数据。"""
    return "synthetic selection"


class ReplacingBudgetOracle(AgentMiddleware):
    """每次inner调用替换模型，证明目录重试仍进同一链且Final保留回调。"""

    def __init__(self):
        """仅记录合成执行次数，不声称发生真实费用预留。"""
        self.calls = 0

    async def awrap_model_call(self, request, handler):
        """模拟真实预算中间件构造新模型的边界。"""
        self.calls += 1
        model = request.model.model_copy(update={"callbacks": None})
        return await handler(request.override(model=model))


def human(text="推荐可以买的食材", *, request_id="synthetic-request"):
    """本轮Human身份与生产授权中间件写入的标记一致。"""
    return HumanMessage(text, additional_kwargs={"health_request_id": request_id})


def receipt(name, *, status="success"):
    """仅用于恢复边界，真实选择来源仍由业务service拥有。"""
    return ToolMessage(content="synthetic receipt", name=name, tool_call_id="call-" + name, status=status)


async def catalog_graph(model, messages, *, final=False, on_custom=None, system_prompt=None, extra_tools=()):
    """保持生产Catalog→Budget→Final顺序，通过实际v3桥消费custom。"""
    context = Context()
    budget = ReplacingBudgetOracle()
    checkpoint = InMemorySaver()
    graph = create_agent(
        model,
        tools=[find_food_packages, select_food_products, *extra_tools, production.finalize_health_answer],
        system_prompt=system_prompt,
        middleware=[catalog.HealthCatalogMiddleware(), budget, production.HealthFinalAnswerMiddleware()],
        context_schema=Context,
        checkpointer=checkpoint,
    )
    initial = {"messages": messages}
    if final:
        initial.update(health_final_request_id=context.request_id, health_answer_phase="final")
    custom = []
    try:
        async with await graph.astream_events(
            initial,
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
    except HealthVisionError as error:
        error.seen_custom = custom
        error.budget_calls = budget.calls
        raise
    return graph, custom, budget


@pytest.mark.asyncio
async def test_catalog_forced_tools_and_final_generation_keep_budget_order_and_one_public_stream():
    gate = asyncio.Event()
    model = ControlledStreamModel(
        plan=[
            [AIMessageChunk(content="PRIVATE_QUERY_PLAN"), tool_chunk(find_food_packages.name)],
            [tool_chunk(production.finalize_health_answer.name)],
            [tool_chunk(select_food_products.name)],
            [tool_chunk(production.finalize_health_answer.name)],
            [AIMessageChunk(content="公开首句🥦。"), AIMessageChunk(content="公开次句。")],
        ],
        released=gate,
    )

    def consume(value):
        """第二正文块暂停时，首个实际custom已产生，回调未被预算替换丢失。"""
        if value["type"] == "health_final_answer_delta" and value["offset"] == 0:
            assert len(model.calls) == 5 and len(model.finished) == 4
            gate.set()

    graph, custom, budget = await catalog_graph(model, [human()], on_custom=consume)
    assert [call["tool_choice"] for call in model.calls] == [
        catalog.tool_choice(find_food_packages.name),
        "any",
        catalog.tool_choice(select_food_products.name),
        "any",
        None,
    ]
    assert budget.calls == len(model.calls) == 5
    assert all(call["tools"] for call in model.calls[:-1]) and model.calls[-1]["tools"] == []
    assert [value["type"] for value in custom].count("health_final_answer_start") == 1
    assert [value["type"] for value in custom].count("health_final_answer_end") == 1
    deltas = [value for value in custom if value["type"] == "health_final_answer_delta"]
    assert [value["content"] for value in deltas] == ["公开首句🥦。", "公开次句。"]
    assert "PRIVATE" not in str(custom)
    state = await graph.aget_state({"configurable": {"thread_id": Context().thread_id}})
    assert state.values["messages"][-1].text == "公开首句🥦。公开次句。"
    assert [message.name for message in state.values["messages"] if isinstance(message, ToolMessage)] == [
        find_food_packages.name,
        select_food_products.name,
        production.finalize_health_answer.name,
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("queries", [1, 3, 4])
async def test_final_phase_without_successful_selection_rejects_before_model_or_custom(queries):
    messages = [human(), *[receipt(find_food_packages.name) for _ in range(queries)]]
    model = ControlledStreamModel(plan=[[AIMessageChunk(content="MUST_NOT_GENERATE")]])
    with pytest.raises(HealthVisionError) as error:
        await catalog_graph(model, messages, final=True)
    assert error.value.code == "catalog_selection_required"
    assert not model.calls and not error.value.seen_custom and error.value.budget_calls == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "messages,code",
    [
        ([human()], "catalog_tool_required"),
        ([human(), receipt(find_food_packages.name, status="error")], "catalog_tool_required"),
        (
            [human(), receipt(find_food_packages.name), receipt(select_food_products.name, status="error")],
            "catalog_selection_required",
        ),
        (
            [
                human(request_id="old-request"),
                receipt(find_food_packages.name),
                receipt(select_food_products.name),
                human(),
            ],
            "catalog_tool_required",
        ),
        ([human(request_id="foreign-request")], "catalog_request_mismatch"),
    ],
)
async def test_final_phase_cannot_reuse_failed_or_previous_request_catalog_receipts(messages, code):
    model = ControlledStreamModel(plan=[[AIMessageChunk(content="MUST_NOT_GENERATE")]])
    with pytest.raises(HealthVisionError) as error:
        await catalog_graph(model, messages, final=True)
    assert error.value.code == code
    assert not model.calls and not error.value.seen_custom


@pytest.mark.asyncio
@pytest.mark.parametrize("queries,required", [(0, find_food_packages.name), (4, select_food_products.name)])
async def test_model_cannot_finalize_instead_of_an_explicit_catalog_obligation(queries, required):
    messages = [human(), *[receipt(find_food_packages.name) for _ in range(queries)]]
    model = ControlledStreamModel(plan=[[tool_chunk(production.finalize_health_answer.name)]])
    with pytest.raises(HealthVisionError) as error:
        await catalog_graph(model, messages)
    assert error.value.code == "catalog_tool_required"
    assert len(model.calls) == error.value.budget_calls == 1
    assert model.calls[0]["tool_choice"] == catalog.tool_choice(required)
    assert not error.value.seen_custom


@pytest.mark.asyncio
@pytest.mark.parametrize("selected", [False, True])
async def test_valid_final_phase_calls_model_once_without_catalog_retry(selected):
    messages = [human("普通科普，不要推荐商品。")]
    if selected:
        messages = [human(), receipt(find_food_packages.name), receipt(select_food_products.name)]
    model = ControlledStreamModel(plan=[[AIMessageChunk(content="唯一最终正文。")]])
    _, custom, budget = await catalog_graph(model, messages, final=True)
    assert len(model.calls) == budget.calls == 1 and model.calls[0]["tools"] == []
    assert [value["type"] for value in custom] == [
        "health_final_answer_start",
        "health_final_answer_delta",
        "health_final_answer_end",
    ]


@pytest.mark.asyncio
async def test_catalog_retry_cannot_accept_another_finalize_instead_of_selection():
    model = ControlledStreamModel(
        plan=[
            [tool_chunk(production.finalize_health_answer.name)],
            [tool_chunk(production.finalize_health_answer.name)],
        ]
    )
    with pytest.raises(HealthVisionError) as error:
        await catalog_graph(model, [human(), receipt(find_food_packages.name)])
    assert error.value.code == "catalog_selection_required"
    assert [call["tool_choice"] for call in model.calls] == ["any", catalog.tool_choice(select_food_products.name)]
    assert error.value.budget_calls == 2 and not error.value.seen_custom


@pytest.mark.asyncio
@pytest.mark.parametrize("choice", [None, "auto", "none", catalog.tool_choice(find_food_packages.name)])
async def test_preparation_keeps_existing_explicit_tool_choice(choice):
    model = ControlledStreamModel(plan=[])
    request = ModelRequest(
        model=model,
        messages=[human()],
        tools=[find_food_packages, select_food_products, production.finalize_health_answer],
        tool_choice=choice,
        state={},
        runtime=SimpleNamespace(context=Context()),
    )
    observed = []

    async def handler(prepared):
        """记录真实ModelRequest覆盖结果，不发起模型请求。"""
        observed.append(prepared.tool_choice)
        return ModelResponse(result=[AIMessage(content="", tool_calls=[])])

    await production.HealthFinalAnswerMiddleware().awrap_model_call(request, handler)
    assert observed == [choice if choice is not None else "any"]


def test_production_graph_retains_catalog_selection_and_callback_safe_order():
    path = Path(__file__).resolve().parents[3] / "package/yuxi/agents/buildin/health_consultation/graph.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    build = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "create_agent"
    )
    middleware = next(item.value for item in build.keywords if item.arg == "middleware")
    names = [item.func.id for item in middleware.elts]
    assert (
        names.index("HealthCatalogMiddleware")
        < names.index("HealthAiBudgetMiddleware")
        < names.index("HealthFinalAnswerMiddleware")
    )
    tools = next(item.value for item in build.keywords if item.arg == "tools")
    assert any(isinstance(item, ast.Name) and item.id == "finalize_health_answer" for item in tools.elts)
    assert any(isinstance(node, ast.Name) and node.id == "select_food_products" for node in ast.walk(tree))

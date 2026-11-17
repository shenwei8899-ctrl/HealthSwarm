"""真实消息和 create_agent 验证历史投影，不替换生产知识库过滤函数。"""

import ast
import importlib.util
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest
from langchain.agents import create_agent
from langchain.agents.middleware import AgentMiddleware
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import tool
from langgraph.checkpoint.memory import InMemorySaver
from pydantic import Field

from yuxi.services.health_vision_types import HealthVisionError


BACKEND = Path(__file__).resolve().parents[3]


@pytest.fixture
def history_filter():
    """原样执行纯逻辑 Owner，隔离其无关的 Milvus 和 Linux 依赖。"""
    source = BACKEND / "package/yuxi/services/health_family_kb_service.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    nodes = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "filter_family_kb_history"
        or isinstance(node, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "TOOL_NAME" for t in node.targets)
    ]
    scope = dict(AIMessage=AIMessage, HumanMessage=HumanMessage, ToolMessage=ToolMessage)
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(source), "exec"), scope)
    return scope["filter_family_kb_history"]


def dialogue():
    """来源和健康问答使用合成占位内容，保留用户报告的提问顺序。"""
    question = HumanMessage("运动完后可以喝冰水吗", additional_kwargs={"health_request_id": "old"})
    planning = AIMessage("", tool_calls=[{"name": "query_family_nutrition_knowledge", "args": {}, "id": "kb-old"}])
    receipt = ToolMessage("旧检索片段", name="query_family_nutrition_knowledge", tool_call_id="kb-old")
    answer = AIMessage("上一轮已经给出的合成答复", id="old-answer")
    current = HumanMessage("生理期可以喝红糖水是什么原因", additional_kwargs={"health_request_id": "current"})
    return question, planning, receipt, answer, current


def test_old_kb_question_keeps_its_answer(history_filter):
    """恢复只保留 HumanMessage 的缺陷时，此断言必须失败。"""
    question, planning, receipt, answer, current = dialogue()
    messages = [question, planning, receipt, answer, current]
    before = [message.model_dump() for message in messages]
    projected = history_filter(messages)
    assert projected == [question, answer, current]
    assert projected[0] is question and projected[-1] is current
    assert [message.model_dump() for message in messages] == before


@pytest.mark.parametrize("followup", ["为什么", "把刚才两个问题总结一下", "早餐怎么搭配"])
def test_followup_preserves_history_meaning(history_filter, followup):
    """追问与换题均保留上一轮正常答复。"""
    question, planning, receipt, answer, _ = dialogue()
    current = HumanMessage(followup)
    assert history_filter([question, planning, receipt, answer, current]) == [question, answer, current]


@pytest.mark.parametrize("status", ["success", "error"])
def test_empty_or_failed_retrieval_keeps_final_dialogue(history_filter, status):
    """零命中或工具报错不应删掉该轮解释缺口的正常答复。"""
    question, planning, receipt, answer, current = dialogue()
    receipt = receipt.model_copy(update={"content": '{"sources":[]}', "status": status})
    assert history_filter([question, planning, receipt, answer, current]) == [question, answer, current]


@pytest.mark.parametrize("ending", ["tool", "call", "invalid", "empty"])
def test_unfinished_round_does_not_invent_an_answer(history_filter, ending):
    """取消和失败残留没有可复用正文时，不补造成功状态或助手答复。"""
    question, planning, receipt, _, current = dialogue()
    last = {
        "tool": receipt,
        "call": planning,
        "invalid": AIMessage("", invalid_tool_calls=[{"name": "bad", "args": "{", "id": "bad", "error": "bad"}]),
        "empty": AIMessage("  "),
    }[ending]
    assert history_filter([question, receipt, last, current]) == [question, current]


def test_preparation_is_not_historical_answer(history_filter):
    """只保留轮末正文，中间准备文本不进入后续历史。"""
    question, planning, receipt, answer, current = dialogue()
    assert history_filter([question, AIMessage("私有准备文本"), planning, receipt, answer, current]) == [
        question,
        answer,
        current,
    ]


def test_three_turns_and_current_tool_protocol(history_filter):
    """旧轮问答成对，当前轮的工具调用和回执保持原对象。"""
    question, planning, receipt, answer, current = dialogue()
    answer2, question3 = AIMessage("第二轮合成答复"), HumanMessage("第三个问题")
    messages = [question, planning, receipt, answer, current, planning, receipt, answer2, question3, planning, receipt]
    assert history_filter(messages) == [question, answer, current, answer2, question3, planning, receipt]
    assert history_filter([question, answer, current]) == [question, answer, current]
    assert history_filter([]) == []


@pytest.fixture
def authorization(monkeypatch, history_filter):
    """只替换 PG 业务边界；生产授权类与历史投影原样参与真实图执行。"""
    source = BACKEND / "package/yuxi/agents/buildin/health_consultation/graph.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    node = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "HealthAuthorizationMiddleware")
    scope = dict(
        AgentMiddleware=AgentMiddleware,
        HumanMessage=HumanMessage,
        HealthVisionError=HealthVisionError,
        model_cache=SimpleNamespace(get_model_info=lambda _: "fixed"),
    )
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(source), "exec"), scope)
    observed = {"validated": [], "filtered": [], "reject": False, "remove_old": False}

    async def require_attempt(context, messages=None):
        """记录调用前完整输入；数据库授权行为由独立集成测试证明。"""
        observed["validated"].append(list(messages or []))
        if observed["reject"]:
            raise HealthVisionError("source_invalidated", "合成来源失效", 410)

    async def filter_history(context, messages, **kwargs):
        """业务过滤必须先收到未精简的工具回执。"""
        observed["filtered"].append(list(messages))
        if observed["remove_old"]:
            start = next(i for i, m in enumerate(messages) if isinstance(m, HumanMessage) and m.text == "当前问题")
            return messages[start:]
        return messages

    for name, members in {
        "health_consultation_service": {"require_consultation_attempt": require_attempt},
        "health_meal_feedback_service": {"filter_health_history": filter_history},
        "health_family_kb_service": {"filter_family_kb_history": history_filter},
    }.items():
        module = ModuleType("yuxi.services." + name)
        module.__dict__.update(members)
        monkeypatch.setitem(sys.modules, module.__name__, module)
    return scope["HealthAuthorizationMiddleware"]("fixed"), observed


@pytest.mark.asyncio
async def test_validity_filter_runs_before_compaction(authorization):
    """撤回过滤看到完整旧回执；其移除的轮次不会被投影重新加入。"""
    middleware, observed = authorization
    question, planning, receipt, answer, _ = dialogue()
    messages = [question, planning, receipt, answer, HumanMessage("当前问题")]
    observed["remove_old"] = True
    request = SimpleNamespace(messages=messages, runtime=SimpleNamespace(context=None))
    request.override = lambda **kwargs: SimpleNamespace(**kwargs)

    async def handler(projected):
        """观察最终传递给模型的输入。"""
        return projected.messages

    assert await middleware.awrap_model_call(request, handler) == [messages[-1]]
    assert observed["filtered"] == [messages]


@dataclass
class Context:
    """合成请求身份，不连接真实账号或业务存储。"""

    request_id: str
    model: str = "synthetic"
    run_id: str = "synthetic-run"
    thread_id: str = "synthetic-history"


class ObservedModel(FakeMessagesListChatModel):
    """记录标准模型实际收到的消息，而非根据最终假答案推断修复生效。"""

    seen: list = Field(default_factory=list)

    def bind_tools(self, tools, **kwargs):
        """工具执行仍使用真实 create_agent ToolNode。"""
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        """在供应商边界记录真实投影。"""
        response = self.responses[len(self.seen)]
        self.seen.append(list(messages))
        return ChatResult(generations=[ChatGeneration(message=response)])


@pytest.fixture
def final_answer_module(monkeypatch):
    """原样加载生产最终正文及目录投影，隔离 agents 包的无关启动依赖。"""
    modules = {}
    for name in ("health_catalog_context", "health_final_answer"):
        source = BACKEND / f"package/yuxi/agents/middlewares/{name}.py"
        spec = importlib.util.spec_from_file_location("yuxi.agents.middlewares." + name, source)
        module = importlib.util.module_from_spec(spec)
        monkeypatch.setitem(sys.modules, spec.name, module)
        spec.loader.exec_module(module)
        modules[name] = module
    return modules["health_final_answer"]


@pytest.mark.asyncio
async def test_real_graph_second_turn_sees_paired_history(authorization, final_answer_module):
    """真实图和 checkpoint 连续两轮经过生产授权类及知识库过滤。"""
    middleware, observed = authorization

    @tool
    async def query_family_nutrition_knowledge() -> str:
        """返回合成知识结果，不访问真实知识库。"""
        return "合成知识片段"

    model = ObservedModel(
        responses=[
            AIMessage("", tool_calls=[{"name": query_family_nutrition_knowledge.name, "args": {}, "id": "old-kb"}]),
            AIMessage("", tool_calls=[{"name": "finalize_health_answer", "args": {}, "id": "old-final"}]),
            AIMessage("第一轮合成答复"),
            AIMessage("", tool_calls=[{"name": query_family_nutrition_knowledge.name, "args": {}, "id": "new-kb"}]),
            AIMessage("", tool_calls=[{"name": "finalize_health_answer", "args": {}, "id": "new-final"}]),
            AIMessage("第二轮合成答复"),
        ]
    )
    graph = create_agent(
        model,
        tools=[query_family_nutrition_knowledge, final_answer_module.finalize_health_answer],
        middleware=[middleware, final_answer_module.HealthFinalAnswerMiddleware()],
        context_schema=Context,
        checkpointer=InMemorySaver(),
    )
    config = {"configurable": {"thread_id": "synthetic-history"}}
    await graph.ainvoke({"messages": [HumanMessage("运动完后可以喝冰水吗")]}, config=config, context=Context("old"))
    await graph.ainvoke(
        {"messages": [HumanMessage("生理期可以喝红糖水是什么原因")]}, config=config, context=Context("current")
    )
    second = model.seen[3]
    assert [(m.type, m.text) for m in second if m.type != "system"] == [
        ("human", "运动完后可以喝冰水吗"),
        ("ai", "第一轮合成答复"),
        ("human", "生理期可以喝红糖水是什么原因"),
    ]
    assert any(isinstance(m, ToolMessage) and m.tool_call_id == "old-kb" for m in observed["filtered"][3])
    assert [m.tool_call_id for m in model.seen[4] if isinstance(m, ToolMessage)] == ["new-kb"]
    assert "以最新用户消息为本轮任务" in model.seen[5][0].text
    assert "除非本轮明确要求回顾、比较或汇总" in model.seen[5][0].text
    persisted = await graph.aget_state(config)
    assert [m.tool_call_id for m in persisted.values["messages"] if isinstance(m, ToolMessage)] == [
        "old-kb",
        "old-final",
        "new-kb",
        "new-final",
    ]
    assert second[-1].additional_kwargs["health_request_id"] == "current"


def test_final_labels_only_use_current_sources(final_answer_module):
    """保留旧答复不会把历史引用转成最终正文的本轮标签。"""
    import json

    old_id, current_id = "11111111-1111-4111-8111-111111111111", "22222222-2222-4222-8222-222222222222"
    old = ToolMessage(
        json.dumps({"sources": [{"source_id": old_id, "filename": "旧资料.md"}]}),
        name="query_family_nutrition_knowledge",
        tool_call_id="old",
    )
    current = ToolMessage(
        json.dumps({"sources": [{"source_id": current_id, "filename": "本轮资料.md"}]}),
        name="query_family_nutrition_knowledge",
        tool_call_id="current",
    )
    request = SimpleNamespace(
        messages=[
            HumanMessage("旧问题"),
            old,
            AIMessage(f"旧答复[资料:{old_id}]"),
            HumanMessage("新问题", additional_kwargs={"health_request_id": "current"}),
            current,
        ],
        runtime=SimpleNamespace(context=Context("current")),
    )
    assert final_answer_module.HealthFinalAnswerMiddleware._citation_ids(
        request, "query_family_nutrition_knowledge", "sources", "source_id"
    ) == [current_id]


def test_consultation_prompt_has_current_task_boundary():
    """固定角色提示覆盖换题、未完成轮次和显式回顾请求。"""
    tree = ast.parse((BACKEND / "package/yuxi/services/health_consultation_service.py").read_text(encoding="utf-8"))
    assignment = next(
        n
        for n in tree.body
        if isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "CONSULTATION_PROMPT" for t in n.targets)
    )
    text = "".join(
        n.value for n in ast.walk(assignment.value) if isinstance(n, ast.Constant) and isinstance(n.value, str)
    )
    assert "以最新用户消息为本轮任务" in text
    assert "除非最新消息明确要求回顾、比较或汇总" in text
    assert "旧轮未完成的问题也不自动续答" in text


@pytest.mark.asyncio
async def test_invalid_source_stops_before_model(authorization):
    """原有来源授权拒绝仍阻止外呼，保留旧答复不绕过边界。"""
    middleware, observed = authorization
    observed["reject"] = True
    model = ObservedModel(responses=[AIMessage("不应执行")])
    graph = create_agent(model, middleware=[middleware], context_schema=Context)
    with pytest.raises(HealthVisionError, match="合成来源失效"):
        await graph.ainvoke({"messages": [HumanMessage("当前问题")]}, context=Context("current"))
    assert model.seen == []

"""真实配餐工具节点的参数自纠，不替代真实知识库、授权存储或模型验收。"""

import ast
import json
import re
import sys
from contextlib import asynccontextmanager
from dataclasses import dataclass
from itertools import zip_longest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from langchain.agents import create_agent
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.prebuilt.tool_node import ToolRuntime
from pydantic import ValidationError
from sqlalchemy import case, or_, select

from test.unit.middlewares.test_health_final_answer import Context
from yuxi.agents.toolkits.health import query_family_nutrition_knowledge, query_reviewed_nutrition_knowledge
from yuxi.agents.toolkits.meal_planner import (
    query_initial_nutrition_knowledge,
    search_meal_plan_recipes,
    search_reference_recipes,
)
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.storage.postgres.models_knowledge import KnowledgeChunk, KnowledgeFile

BACKEND = Path(__file__).resolve().parents[3]
SEARCHES = [(search_reference_recipes, 80), (query_initial_nutrition_knowledge, 120)]


@dataclass
class SearchContext(Context):
    """补充原参考服务读取的合成账号，保留真实 ToolRuntime 注入。"""

    uid: str = "synthetic-query-user"


def runtime():
    """使用真实 ToolRuntime 类型，身份完全为合成值。"""
    return ToolRuntime(
        state={}, context=SearchContext(), config={}, stream_writer=lambda item: None, tool_call_id="query", store=None
    )


def load_functions(filename, names, namespace):
    """原样执行相关生产函数，隔离 Windows 无关文件系统与服务启动入口。"""
    source = BACKEND / "package/yuxi/services" / filename
    nodes = [node for node in ast.parse(source.read_text(encoding="utf-8")).body if getattr(node, "name", "") in names]
    assert {node.name for node in nodes} == set(names)
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(source), "exec"), namespace)
    return namespace


@pytest.fixture
def search_services(monkeypatch):
    """生产检索函数保留；PG、知识命中及权限存储使用显式合成依赖。"""
    session = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(all=lambda: [])))

    @asynccontextmanager
    async def transaction():
        """不建立数据库连接。"""
        yield session

    manager = SimpleNamespace(get_async_session_context=transaction)
    binding = SimpleNamespace(initial_planner_selection={"selection": {"mode": "single"}})
    authorize = AsyncMock(return_value=(None, binding))
    sources = AsyncMock()
    kb_guard = AsyncMock()
    retrieve = AsyncMock(return_value={"results": []})
    knowledge = load_functions(
        "health_family_kb_service.py",
        ["retrieve_family_nutrition_knowledge", "_retrieve_nutrition_knowledge"],
        {
            "HealthVisionError": HealthVisionError,
            "pg_manager": manager,
            "configured_family_kb_id": lambda: "synthetic-kb",
            "_require_fixed_kb": kb_guard,
            "knowledge_base": SimpleNamespace(retrieve=retrieve),
            "MAX_SOURCES": 4,
            "CONSULTATION_SLUG": "health-consultation",
            "PLANNER_SLUG": "health-meal-planner",
            "zip_longest": zip_longest,
        },
    )
    reference = load_functions(
        "reference_meal_plan_service.py",
        ["reference_binding", "search_reference_recipes"],
        {
            "HealthVisionError": HealthVisionError,
            "pg_manager": manager,
            "require_planner_run": authorize,
            "bound_reference_context": sources,
            "configured_health_kb_ids": lambda role: ("synthetic-kb",),
            "search_family_nutrition_knowledge": AsyncMock(
                return_value={"status": "insufficient_material", "sources": []}
            ),
            "KnowledgeFile": KnowledgeFile,
            "KnowledgeChunk": KnowledgeChunk,
            "select": select,
            "case": case,
            "or_": or_,
            "re": re,
        },
    )
    initial = load_functions(
        "health_initial_planner_service.py",
        ["require_initial_binding", "search_initial_nutrition_knowledge"],
        {"HealthVisionError": HealthVisionError, "pg_manager": manager},
    )

    for name, values in (
        ("health_meal_plan_service", {"require_planner_run": authorize}),
        ("health_family_kb_service", knowledge),
        ("reference_meal_plan_service", reference),
        ("health_initial_planner_service", initial),
    ):
        module = ModuleType("yuxi.services." + name)
        module.__dict__.update(values)
        monkeypatch.setitem(sys.modules, module.__name__, module)
    reference_call = AsyncMock(wraps=reference["search_reference_recipes"])
    initial_call = AsyncMock(wraps=initial["search_initial_nutrition_knowledge"])
    monkeypatch.setattr(
        sys.modules["yuxi.services.reference_meal_plan_service"], "search_reference_recipes", reference_call
    )
    monkeypatch.setattr(
        sys.modules["yuxi.services.health_initial_planner_service"], "search_initial_nutrition_knowledge", initial_call
    )
    return SimpleNamespace(
        authorize=authorize,
        sources=sources,
        kb_guard=kb_guard,
        calls={search_reference_recipes.name: reference_call, query_initial_nutrition_knowledge.name: initial_call},
    )


class ScriptedSearchModel(GenericFakeChatModel):
    """脚本模型只发出显式坏参数和纠正参数，结果来自真实工具节点。"""

    def bind_tools(self, tools, **kwargs):
        """沿用标准 Agent 工具节点，不实现真实供应商调用。"""
        return self


@pytest.mark.parametrize("search,maximum", SEARCHES)
@pytest.mark.parametrize("query", [None, "", " \t\n"])
def test_keyword_search_requires_a_nonblank_query(search, maximum, query):
    """缺失与 trim 后空串必须在服务调用前拒绝。"""
    payload = {"runtime": runtime(), **({"query": query} if query is not None else {})}
    with pytest.raises(ValidationError):
        search.args_schema.model_validate(payload)


@pytest.mark.parametrize("search,maximum", SEARCHES)
def test_keyword_search_matches_its_service_trim_and_length_boundary(search, maximum):
    """保留原关键词，不截断，trim 后按各服务边界接受。"""
    payload = search.args_schema.model_validate({"runtime": runtime(), "query": "  " + "粥" * maximum + "  "})
    assert payload.query == "粥" * maximum
    with pytest.raises(ValidationError):
        search.args_schema.model_validate({"runtime": runtime(), "query": "粥" * (maximum + 1)})
    public = search.tool_call_schema.model_json_schema()
    assert "query" in public["required"] and "runtime" not in public["properties"]


@pytest.mark.parametrize("search", [query_family_nutrition_knowledge, query_reviewed_nutrition_knowledge])
def test_consultation_knowledge_queries_keep_their_existing_nonblank_contract(search):
    """咨询知识工具已有非空约束，不因配餐修复改变其输入。"""
    with pytest.raises(ValidationError):
        search.args_schema.model_validate({"runtime": runtime(), "query": " \t "})
    assert search.args_schema.model_validate({"runtime": runtime(), "query": "  科普  "}).query == "科普"


def test_published_recipe_catalog_still_allows_an_omitted_or_blank_query():
    """正式菜谱的默认空查询是目录浏览，不能被知识检索约束破坏。"""
    for payload in [{}, {"query": ""}, {"query": "   "}]:
        assert search_meal_plan_recipes.args_schema.model_validate({"runtime": runtime(), **payload}).query == ""


@pytest.mark.asyncio
@pytest.mark.parametrize("search,maximum", SEARCHES)
@pytest.mark.parametrize("bad_kind", ["missing", "blank", "too_long"])
async def test_real_agent_corrects_invalid_keyword_before_the_only_service_call(
    search_services, search, maximum, bad_kind
):
    """参数错误应成为可读工具错误；旧实现会因服务异常或缺参中止图。"""
    bad = {"missing": {}, "blank": {"query": " \t "}, "too_long": {"query": "粥" * (maximum + 1)}}[bad_kind]
    model = ScriptedSearchModel(
        messages=iter(
            [
                AIMessage(content="", tool_calls=[{"name": search.name, "args": bad, "id": "invalid"}]),
                AIMessage(content="", tool_calls=[{"name": search.name, "args": {"query": "  蒸蛋  "}, "id": "valid"}]),
                AIMessage(content="合成回放：受控资料不足，未保存餐单。"),
            ]
        )
    )
    graph = create_agent(model, tools=[search], context_schema=SearchContext)
    result = await graph.ainvoke({"messages": [HumanMessage("合成：查询烹饪参考")]}, context=SearchContext())
    receipts = [message for message in result["messages"] if isinstance(message, ToolMessage)]

    assert [(message.tool_call_id, message.status) for message in receipts] == [
        ("invalid", "error"),
        ("valid", "success"),
    ]
    assert "query" in receipts[0].content
    payload = json.loads(receipts[1].content)
    assert payload["status"] == "insufficient_material"
    assert not payload.get("sources") and not payload.get("items")
    search_services.calls[search.name].assert_awaited_once_with(SearchContext(), "蒸蛋")
    assert search_services.authorize.await_count == 2
    assert result["messages"][-1].text == "合成回放：受控资料不足，未保存餐单。"


@pytest.mark.asyncio
@pytest.mark.parametrize("search,maximum", SEARCHES)
@pytest.mark.parametrize("code", ["not_authorized", "source_invalidated"])
async def test_valid_keyword_does_not_swallow_authorization_or_source_errors(search_services, search, maximum, code):
    """合法参数继续进入原授权边界，原异常仍中止图而非假空结果。"""
    if code == "not_authorized":
        search_services.authorize.side_effect = HealthVisionError(code, "合成授权拒绝", 403)
    elif search.name == search_reference_recipes.name:
        search_services.sources.side_effect = HealthVisionError(code, "合成来源失效", 410)
    else:
        search_services.kb_guard.side_effect = HealthVisionError(code, "合成来源失效", 410)
    model = ScriptedSearchModel(
        messages=iter(
            [
                AIMessage(content="", tool_calls=[{"name": search.name, "args": {"query": "蒸蛋"}, "id": "denied"}]),
            ]
        )
    )
    graph = create_agent(model, tools=[search], context_schema=SearchContext)
    with pytest.raises(HealthVisionError) as failure:
        await graph.ainvoke({"messages": [HumanMessage("合成：查询参考")]}, context=SearchContext())
    assert failure.value.code == code
    search_services.authorize.assert_awaited_once()

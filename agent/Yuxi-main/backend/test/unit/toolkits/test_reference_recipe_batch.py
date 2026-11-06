"""参考菜谱批量工具保持当前 Run 的单份来源校验。"""

from dataclasses import dataclass
from collections import Counter
from unittest.mock import AsyncMock
import json
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage, ToolMessage
from langgraph.graph import START, END, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode
from langgraph.prebuilt.tool_node import ToolRuntime
from pydantic import ValidationError

from yuxi.agents.toolkits import meal_planner
from yuxi.services import reference_meal_plan_service
from yuxi.services import reference_recipe_index
from yuxi.services.health_vision_types import HealthVisionError


@dataclass
class Context:
    """仅供工具注入的合成运行身份。"""

    uid: str = "synthetic"


def runtime():
    """返回未连接真实资料的合成 ToolRuntime。"""
    return ToolRuntime({}, Context(), {}, lambda _: None, "synthetic-call", None)


def test_batch_inputs_are_bounded_and_unique():
    """批量和旧单份参数互斥，重复及越界输入在工具边界拒绝。"""
    injected = runtime()
    meal_planner.ReferenceRecipeSearch.model_validate({"runtime": injected, "queries": ["大米", "鸡蛋"]})
    meal_planner.ReferenceRecipeInput.model_validate(
        {"runtime": injected, "recipes": [{"file_id": "file-1", "chunk_id": "chunk-1"}]}
    )
    for value in (
        {"query": "大米", "queries": ["鸡蛋"]},
        {"queries": ["大米", "大米"]},
        {"queries": [" "]},
    ):
        with pytest.raises(ValidationError):
            meal_planner.ReferenceRecipeSearch.model_validate({"runtime": injected, **value})
    for value in (
        {"file_id": "file-1"},
        {"file_id": "file-1", "chunk_id": "chunk-1", "recipes": [{"file_id": "file-1", "chunk_id": "chunk-1"}]},
        {"recipes": [{"file_id": "file-1", "chunk_id": "chunk-1"}] * 2},
    ):
        with pytest.raises(ValidationError):
            meal_planner.ReferenceRecipeInput.model_validate({"runtime": injected, **value})


@pytest.mark.asyncio
async def test_batch_rankings_share_one_recipe_row_query(monkeypatch):
    """多个关键词只扫描数据库一次，各自保留独立相关性排序。"""
    rows = [
        (
            "rice",
            "kb",
            "家常菜谱_大米粥.md",
            "hash-rice",
            "chunk-rice",
            "# 大米粥\n\n## 食材\n- 大米100克\n\n## 做法\n1. 加水煮熟",
        ),
        (
            "egg",
            "kb",
            "家常菜谱_鸡蛋羹.md",
            "hash-egg",
            "chunk-egg",
            "# 鸡蛋羹\n\n## 食材\n- 鸡蛋1个\n\n## 做法\n1. 蒸熟",
        ),
    ]
    session = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(all=lambda: rows)))
    monkeypatch.setattr(reference_recipe_index, "configured_health_kb_ids", lambda _: ("kb",))
    ranked = await reference_recipe_index.purchasable_reference_recipes_batch(session, [], ["大米", "鸡蛋"])
    assert session.execute.await_count == 1
    assert [matches[0]["file_id"] for matches in ranked] == ["rice", "egg"]


@pytest.mark.asyncio
async def test_batch_reuses_recipe_analysis_without_reusing_later_call(monkeypatch):
    """同批重叠候选只解析一次，新调用重新按当前原谱和商品分析。"""
    rows = [
        (
            "both", "kb", "家常菜谱_鸡蛋大米粥.md", "hash-1", "chunk-1",
            "# 鸡蛋大米粥\n## 食材\n- 大米 100克\n- 鸡蛋 1个\n## 做法\n- 加水煮熟",
        ),
        (
            "rice", "kb", "家常菜谱_大米饭.md", "hash-2", "chunk-2",
            "# 大米饭\n## 食材\n- 大米 100克\n## 做法\n- 加水煮熟",
        ),
    ]
    session = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(all=lambda: rows)))
    monkeypatch.setattr(reference_recipe_index, "configured_health_kb_ids", lambda _: ("kb",))
    parsed = Counter()
    matched = Counter()
    original_parse = reference_recipe_index.parse_reference_recipe
    original_match = reference_recipe_index.reference_ingredient_matches

    def parse(content):
        parsed[content] += 1
        return original_parse(content)

    def match(ingredients, products):
        matched[ingredients] += 1
        return original_match(ingredients, products)

    monkeypatch.setattr(reference_recipe_index, "parse_reference_recipe", parse)
    monkeypatch.setattr(reference_recipe_index, "reference_ingredient_matches", match)
    products = [{"sku_id": "rice-sku", "product_name": "大米", "available_quantity": 5, "price_cent": 100}]

    ranked = await reference_recipe_index.purchasable_reference_recipes_batch(session, products, ["大米", "鸡蛋"])

    assert [[item["file_id"] for item in matches] for matches in ranked] == [["rice", "both"], ["both"]]
    assert sum(parsed.values()) == 2
    assert sum(matched.values()) == 2
    assert all(item["chunks_hash"] for matches in ranked for item in matches)
    assert ranked[0][0]["ingredient_matches"][0]["status"] == "matched"

    changed = [("both", "kb", "家常菜谱_鸡蛋大米粥.md", "hash-new", "chunk-new", rows[0][-1])]
    session.execute.return_value = SimpleNamespace(all=lambda: changed)
    later = await reference_recipe_index.purchasable_reference_recipes_batch(session, [], ["鸡蛋"])

    assert later[0][0]["file_hash"] == "hash-new"
    assert later[0][0]["chunk_id"] == "chunk-new"
    assert later[0][0]["ingredient_matches"][0]["status"] == "missing_product"
    assert sum(parsed.values()) == 3
    assert sum(matched.values()) == 3


@pytest.mark.asyncio
async def test_batch_tool_calls_existing_authorized_service_for_each_source(monkeypatch):
    """批量读取逐份复用原服务的来源验证，输出供持久回执展开。"""
    search = AsyncMock(return_value={"items": []})
    read = AsyncMock(
        side_effect=[{"file_id": "file-1", "chunk_id": "chunk-1"}, {"file_id": "file-2", "chunk_id": "chunk-2"}]
    )
    monkeypatch.setattr(reference_meal_plan_service, "search_reference_recipes", search)
    monkeypatch.setattr(reference_meal_plan_service, "read_reference_recipe", read)
    injected = runtime()
    await meal_planner.search_reference_recipes.coroutine(runtime=injected, queries=["大米", "鸡蛋"])
    assert search.await_args.args == (injected.context, ["大米", "鸡蛋"])
    result = await meal_planner.read_reference_recipe.coroutine(
        runtime=injected,
        recipes=[
            meal_planner.ReferenceRecipeRef(file_id="file-1", chunk_id="chunk-1"),
            meal_planner.ReferenceRecipeRef(file_id="file-2", chunk_id="chunk-2"),
        ],
    )
    assert [item["file_id"] for item in result["items"]] == ["file-1", "file-2"]
    assert [call.args for call in read.await_args_list] == [
        (injected.context, "file-1", "chunk-1"),
        (injected.context, "file-2", "chunk-2"),
    ]


@pytest.mark.asyncio
async def test_real_tool_node_injects_context_for_batch_read(monkeypatch):
    """真实 ToolNode 解析模型 JSON 并逐份传入同一运行身份。"""
    read = AsyncMock(side_effect=[{"file_id": "file-1"}, {"file_id": "file-2"}])
    monkeypatch.setattr(reference_meal_plan_service, "read_reference_recipe", read)
    graph = StateGraph(MessagesState, context_schema=Context)
    graph.add_node("tools", ToolNode([meal_planner.read_reference_recipe]))
    graph.add_edge(START, "tools")
    graph.add_edge("tools", END)
    context = Context()
    result = await graph.compile().ainvoke(
        {
            "messages": [
                AIMessage(
                    "",
                    tool_calls=[
                        {
                            "id": "batch-read",
                            "name": "read_reference_recipe",
                            "args": {
                                "recipes": [
                                    {"file_id": "file-1", "chunk_id": "chunk-1"},
                                    {"file_id": "file-2", "chunk_id": "chunk-2"},
                                ]
                            },
                        }
                    ],
                )
            ]
        },
        context=context,
    )
    receipt = result["messages"][-1]
    assert isinstance(receipt, ToolMessage) and receipt.status == "success"
    assert json.loads(receipt.content) == {"items": [{"file_id": "file-1"}, {"file_id": "file-2"}]}
    assert [call.args for call in read.await_args_list] == [
        (context, "file-1", "chunk-1"),
        (context, "file-2", "chunk-2"),
    ]


@pytest.mark.asyncio
async def test_checkpoint_revalidates_each_batch_source(monkeypatch):
    """恢复时第二份原谱变化也阻止沿用批量回执。"""
    reads = [
        {"file_id": "file-1", "chunk_id": "chunk-1", "content": "original-1"},
        {"file_id": "file-2", "chunk_id": "chunk-2", "content": "original-2"},
    ]
    content = json.dumps({"items": reads})
    message = SimpleNamespace(name="read_reference_recipe", tool_call_id="batch-read", content=content)
    audit = SimpleNamespace(
        content=content,
        execution_status="completed",
        request_id="request",
        conversation_id="conversation",
        extra_metadata={"tool_name": "read_reference_recipe"},
    )
    original = SimpleNamespace(
        request_id="request", input_payload={"health_processing": {"initial_selection_hash": "selection-hash"}}
    )
    session = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(all=lambda: [(audit, original)])))
    context = SimpleNamespace(uid="actor", thread_id="thread")
    binding = SimpleNamespace(conversation_id="conversation", initial_planner_selection={"synthetic": True})
    monkeypatch.setattr(reference_meal_plan_service, "bound_reference_context", AsyncMock(return_value={}))
    monkeypatch.setattr(reference_meal_plan_service, "input_fingerprint", lambda _: "selection-hash")
    document = AsyncMock(side_effect=reads)
    monkeypatch.setattr(reference_meal_plan_service, "recipe_document", document)
    await reference_meal_plan_service.validate_reference_tool_payload(session, context, binding, message)
    assert document.await_count == 2

    document.reset_mock(side_effect=True)
    document.side_effect = [reads[0], {**reads[1], "content": "changed"}]
    with pytest.raises(HealthVisionError, match="source_invalidated"):
        await reference_meal_plan_service.validate_reference_tool_payload(session, context, binding, message)

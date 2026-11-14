"""商品工具约束只允许当前用户请求中实际查询与选择的结果。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from test.unit.middlewares.test_health_final_answer import production_middleware

from yuxi.services.health_vision_types import HealthVisionError

HealthCatalogMiddleware = production_middleware("health_catalog").HealthCatalogMiddleware


def model_request(text="帮我推荐商城食材", after=(), request_id="request-current"):
    """构造 middleware 实际读取的请求边界并记录模型指定工具。"""
    overrides = []
    request = SimpleNamespace(
        state={},
        tools=[SimpleNamespace(name=name) for name in ("find_food_packages", "select_food_products")],
        messages=[HumanMessage(content=text, additional_kwargs={"health_request_id": request_id}), *after],
        runtime=SimpleNamespace(context=SimpleNamespace(request_id="request-current")),
    )

    def override(**kwargs):
        """返回带指定工具的新请求，不改变原消息。"""
        overrides.append(kwargs)
        return SimpleNamespace(**{**vars(request), **kwargs})

    request.override = override
    return request, overrides


def model_answer(tool=None):
    """模型输出使用真实 LangChain 消息而非布尔成功标志。"""
    return SimpleNamespace(
        result=[AIMessage(content="候选回复", tool_calls=[{"name": tool, "args": {}, "id": "call"}] if tool else [])]
    )


@pytest.mark.asyncio
async def test_product_request_cannot_ignore_forced_catalog_query():
    request, overrides = model_request()
    handler = AsyncMock(return_value=model_answer())
    with pytest.raises(HealthVisionError, match="catalog_tool_required"):
        await HealthCatalogMiddleware().awrap_model_call(request, handler)
    assert overrides == [{"tool_choice": {"type": "function", "function": {"name": "find_food_packages"}}}]


@pytest.mark.asyncio
async def test_catalog_result_cannot_publish_plain_answer_without_selection():
    queried = ToolMessage(content='{"offers":[]}', tool_call_id="query", name="find_food_packages")
    request, overrides = model_request(after=[queried])
    handler = AsyncMock(return_value=model_answer())
    with pytest.raises(HealthVisionError, match="catalog_selection_required"):
        await HealthCatalogMiddleware().awrap_model_call(request, handler)
    assert handler.await_count == 2
    assert overrides[-1]["tool_choice"]["function"]["name"] == "select_food_products"


@pytest.mark.asyncio
async def test_explicit_refusal_keeps_ordinary_education_without_catalog_query():
    request, overrides = model_request("不要推荐商品，只解释食物营养标签")
    answer = model_answer()
    handler = AsyncMock(return_value=answer)
    assert await HealthCatalogMiddleware().awrap_model_call(request, handler) is answer
    assert overrides == [{"tools": []}]


@pytest.mark.asyncio
async def test_prior_request_cannot_supply_this_round_catalog_context():
    request, _ = model_request(request_id="another-request")
    handler = AsyncMock()
    with pytest.raises(HealthVisionError, match="catalog_request_mismatch"):
        await HealthCatalogMiddleware().awrap_model_call(request, handler)
    handler.assert_not_awaited()


@pytest.mark.asyncio
async def test_verified_current_selection_permits_final_answer():
    after = [
        ToolMessage(content="{}", tool_call_id=name, name=name)
        for name in ("find_food_packages", "select_food_products")
    ]
    request, overrides = model_request(after=after)
    answer = model_answer()
    assert await HealthCatalogMiddleware().awrap_model_call(request, AsyncMock(return_value=answer)) is answer
    assert overrides == []


@pytest.mark.asyncio
@pytest.mark.parametrize("text", ["帮我推荐商城食材", "下午加餐吃啥"])
async def test_current_category_query_precedes_product_tools(text):
    """新版分类入口存在时，明确商品意图先取得本轮分类，不能直接查询或选品。"""
    request, overrides = model_request(text)
    request.tools.extend(SimpleNamespace(name=name) for name in ("get_food_categories", "finalize_health_answer"))
    original_tools = list(request.tools)
    answer = model_answer("get_food_categories")
    handler = AsyncMock(return_value=answer)
    assert await HealthCatalogMiddleware().awrap_model_call(request, handler) is answer
    assert overrides[-1]["tool_choice"]["function"]["name"] == "get_food_categories"
    assert {tool.name for tool in overrides[-1]["tools"]} == {"get_food_categories", "finalize_health_answer"}
    assert request.tools == original_tools


@pytest.mark.asyncio
async def test_successful_category_from_another_turn_cannot_open_product_tools():
    """恢复历史里的分类只属于旧轮，当前商品请求仍强制先取得分类。"""
    request, overrides = model_request()
    request.tools.append(SimpleNamespace(name="get_food_categories"))
    request.messages[:0] = [
        HumanMessage(content="旧轮", additional_kwargs={"health_request_id": "old"}),
        ToolMessage(content='{"categories":[]}', tool_call_id="old", name="get_food_categories"),
    ]
    await HealthCatalogMiddleware().awrap_model_call(
        request, AsyncMock(return_value=model_answer("get_food_categories"))
    )
    assert overrides[-1]["tool_choice"]["function"]["name"] == "get_food_categories"


@pytest.mark.asyncio
async def test_ordinary_nutrition_cannot_expose_catalog_tools():
    """普通问答的模型工具中不能留下分类入口。"""
    request, _ = model_request("鸡蛋有什么营养")
    request.tools.extend(SimpleNamespace(name=name) for name in ("get_food_categories", "finalize_health_answer"))
    seen = []

    async def handler(filtered):
        """记录真实模型边界能看到的工具集。"""
        seen.extend(tool.name for tool in filtered.tools)
        return model_answer()

    await HealthCatalogMiddleware().awrap_model_call(request, handler)
    assert seen == ["finalize_health_answer"]


@pytest.mark.asyncio
async def test_direct_catalog_tool_cannot_run_without_purchase_intent():
    """工具节点恢复不能绕过模型工具过滤，当前轮可继续准备。"""
    request = SimpleNamespace(
        tool_call={"name": "get_food_categories", "id": "unbound-catalog"},
        state={"messages": [HumanMessage("后天吃啥", additional_kwargs={"health_request_id": "current"})]},
        runtime=SimpleNamespace(context=SimpleNamespace(request_id="current")),
    )
    handler = AsyncMock()
    result = await HealthCatalogMiddleware().awrap_tool_call(request, handler)
    assert isinstance(result, ToolMessage)
    assert result.status == "error" and result.tool_call_id == "unbound-catalog"
    assert "未查询商品" in result.text
    handler.assert_not_awaited()


@pytest.mark.asyncio
async def test_catalog_tool_with_wrong_request_id_still_fails_closed():
    """旧轮或伪造的商城调用不能伪装成当前普通咨询错误回执。"""
    request = SimpleNamespace(
        tool_call={"name": "find_food_packages", "id": "old-catalog"},
        state={"messages": [HumanMessage("后天吃啥", additional_kwargs={"health_request_id": "old"})]},
        runtime=SimpleNamespace(context=SimpleNamespace(request_id="current")),
    )
    handler = AsyncMock()
    with pytest.raises(HealthVisionError, match="catalog_request_mismatch"):
        await HealthCatalogMiddleware().awrap_tool_call(request, handler)
    handler.assert_not_awaited()

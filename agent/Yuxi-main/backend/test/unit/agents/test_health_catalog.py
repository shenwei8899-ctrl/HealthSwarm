"""商品工具约束只允许当前用户请求中实际查询与选择的结果。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from yuxi.agents.middlewares.health_catalog import HealthCatalogMiddleware
from yuxi.services.health_vision_types import HealthVisionError


def model_request(text="帮我推荐食材", after=(), request_id="request-current"):
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
        return SimpleNamespace(**vars(request), **kwargs)

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
    assert overrides == []


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

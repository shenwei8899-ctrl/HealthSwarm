"""正常商城拒绝不得终止普通咨询，真实来源错误仍保持拒绝。"""

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from yuxi.services import health_consultation_service as service
from yuxi.services.health_vision_types import HealthVisionError


DENIAL = "本轮没有商城商品请求，未查询商品。请使用已授权的资料工具核对限制，随后完成普通咨询；不要再次调用商城工具。"
CATALOG_TOOLS = ("get_food_categories", "find_food_packages", "select_food_products")


@pytest.fixture
def authorized_attempt(monkeypatch):
    """只替换数据库边界，实际执行完整咨询回执校验。"""

    @asynccontextmanager
    async def session():
        """返回无外部副作用的会话。"""
        yield SimpleNamespace()

    monkeypatch.setattr(service.pg_manager, "get_async_session_context", session)
    monkeypatch.setattr(
        service.HealthConsultationRepository,
        "require_attempt",
        AsyncMock(
            return_value=SimpleNamespace(
                input_payload={"health_processing": {"model": "synthetic/fixed"}}, agent_slug="health-consultation"
            )
        ),
    )
    monkeypatch.setattr(service, "require_consultation", AsyncMock(return_value=(SimpleNamespace(), {})))
    return SimpleNamespace(uid="synthetic", thread_id="thread", model="synthetic/fixed", request_id="current")


def denial_turn(name="get_food_categories", *, marked=False):
    """独立构造已部署文案及新协议，避免从实现生成期望值。"""
    return [
        HumanMessage(content="鸡蛋有什么营养", additional_kwargs={"health_request_id": "old"}),
        AIMessage(content="", tool_calls=[{"id": "catalog-call", "name": name, "args": {}}]),
        ToolMessage(
            name=name,
            tool_call_id="catalog-call",
            content=DENIAL,
            status="error",
            additional_kwargs=(
                {"catalog_guard": {"reason": "no_product_intent", "request_id": "old"}} if marked else {}
            ),
        ),
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("name", CATALOG_TOOLS)
@pytest.mark.parametrize("marked", [False, True])
async def test_denial_allows_current_recovery_and_followup(authorized_attempt, name, marked):
    """新旧正常拒绝可恢复，也不污染同会话后续轮次。"""
    history = denial_turn(name, marked=marked)
    await service.require_consultation_attempt(authorized_attempt, history)
    history.extend(
        [
            AIMessage(content="合成回答"),
            HumanMessage(content="那怎么买商城鸡蛋", additional_kwargs={"health_request_id": "current"}),
        ]
    )
    await service.require_consultation_attempt(authorized_attempt, history)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "change",
    [
        "real_error",
        "missing_call",
        "wrong_call_id",
        "wrong_name",
        "missing_human",
        "purchase_intent",
        "missing_request",
        "wrong_marker_request",
        "wrong_reason",
        "empty_marker",
        "success",
        "next_turn",
    ],
)
async def test_unproven_denial_and_real_errors_remain_blocked(authorized_attempt, change):
    """文案或标识本身不能让错误回执绕过真实来源校验。"""
    history = denial_turn(marked=change in {"wrong_marker_request", "wrong_reason", "empty_marker"})
    human, call, receipt = history
    if change == "real_error":
        receipt.content = "商品来源已撤回"
    elif change == "missing_call":
        history.pop(1)
    elif change == "wrong_call_id":
        receipt.tool_call_id = "another-call"
    elif change == "wrong_name":
        call.tool_calls[0]["name"] = "find_food_packages"
    elif change == "missing_human":
        history.pop(0)
    elif change == "purchase_intent":
        human.content = "帮我买商城鸡蛋"
    elif change == "missing_request":
        human.additional_kwargs = {}
    elif change == "wrong_marker_request":
        receipt.additional_kwargs["catalog_guard"]["request_id"] = "forged"
    elif change == "wrong_reason":
        receipt.additional_kwargs["catalog_guard"]["reason"] = "source_changed"
    elif change == "empty_marker":
        receipt.additional_kwargs["catalog_guard"] = None
    elif change == "success":
        receipt.status = "success"
    elif change == "next_turn":
        history.insert(2, HumanMessage(content="继续", additional_kwargs={"health_request_id": "next"}))
    with pytest.raises(
        HealthVisionError, match="profile_source_changed" if change == "success" else "source_invalidated"
    ):
        await service.require_consultation_attempt(authorized_attempt, history)


@pytest.mark.asyncio
@pytest.mark.parametrize("boundary", ["require_attempt", "require_consultation"])
async def test_denial_never_bypasses_authorization(authorized_attempt, monkeypatch, boundary):
    """正常拒绝也必须先通过运行所有权与用途审批。"""
    owner = service.HealthConsultationRepository if boundary == "require_attempt" else service
    monkeypatch.setattr(owner, boundary, AsyncMock(side_effect=HealthVisionError("not_authorized", "合成拒绝", 403)))
    with pytest.raises(HealthVisionError, match="not_authorized"):
        await service.require_consultation_attempt(authorized_attempt, denial_turn(marked=True))

from datetime import date

import pytest

from yuxi.services.health_intent_router_service import classify_health_intent


@pytest.mark.parametrize(("text", "day"), [("后天吃啥", 2), ("明天早餐吃什么", 1)])
def test_single_day_uses_requested_date(text, day):
    """相对日期以服务器业务日期计算。"""
    result = classify_health_intent(text, today=date(2026, 11, 9))
    assert result.route == "single_day_meal"
    assert result.business_date.isoformat() == f"2026-11-{9 + day:02d}"


def test_weekly_request_is_handoff_without_task_creation():
    """多日请求仅提供计划入口。"""
    result = classify_health_intent("安排一周三餐", today=date(2026, 11, 9))
    assert result.route == "exclusive_plan"
    assert result.action == "handoff"
    assert result.day_count == 21


def test_ordinary_nutrition_is_consultation():
    """营养科普交给咨询。"""
    assert classify_health_intent("鸡蛋有什么营养", today=date(2026, 11, 9)).route == "nutrition_consultation"


def test_ambiguous_text_requires_clarification():
    """模糊规则结果留给分析模型。"""
    result = classify_health_intent("给我安排一下", today=date(2026, 11, 9))
    assert result is None


@pytest.mark.parametrize(
    ("text", "expected_date", "action"),
    [
        ("大后天午餐吃啥", "2026-11-12", "generate"),
        ("安排2026年11月15日早餐", "2026-11-15", "generate"),
        ("看看后天的餐单", "2026-11-11", "view"),
        ("换一下明天的午餐", "2026-11-10", "change"),
    ],
)
def test_date_and_action_are_authoritative(text, expected_date, action):
    """日期和查看换菜动作分别保留。"""
    result = classify_health_intent(text, today=date(2026, 11, 9))
    assert result.route == "single_day_meal"
    assert result.business_date.isoformat() == expected_date
    assert result.action == action


@pytest.mark.parametrize(
    "text", ["一周三餐应该注意什么", "不要安排一周三餐，解释膳食营养", "我今天午餐吃了鸡蛋", "安排2月30日早餐"]
)
def test_education_cancellation_recording_and_invalid_dates_do_not_start_planning(text):
    """科普、记录及无效日期不启动配餐。"""
    result = classify_health_intent(text, today=date(2026, 11, 9))
    assert result.route not in {"single_day_meal", "exclusive_plan"}


@pytest.mark.parametrize(
    ("text", "meals"), [("只改晚餐，其他两餐保持原样", ["dinner"]), ("再换一批", ["lunch"]), ("还有别的吗", ["lunch"])]
)
def test_revision_keeps_previous_date_and_meals(text, meals):
    """换菜上下文不能扩大到今天全家三餐。"""
    result = classify_health_intent(
        text, today=date(2026, 11, 9), previous_date=date(2026, 11, 11), previous_meals=["lunch"]
    )
    assert result.route == "single_day_meal"
    assert result.business_date == date(2026, 11, 11)
    assert result.meal_types == meals
    assert result.action == "change"


@pytest.mark.parametrize("text", ["商品价格是多少", "我想买鸡胸肉", "蛋白质怎么选", "蔬菜怎么做更好吃"])
def test_consultation_is_not_captured_by_pending_meal(text):
    """待补充餐单不能吞掉用户新问题。"""
    result = classify_health_intent(
        text,
        today=date(2026, 11, 9),
        previous_date=date(2026, 11, 11),
        previous_meals=["lunch"],
        awaiting_meal_details=True,
    )
    assert result is None or result.route == "nutrition_consultation"


def test_unrelated_pending_reply_is_analyzed_instead_of_submitted():
    """补资料上下文不能把无关陈述直接送进配餐。"""
    assert classify_health_intent("帮我写一首诗", previous_date=date(2026, 11, 11), awaiting_meal_details=True) is None


@pytest.mark.parametrize("text", ["安排今天和明天三餐", "安排明天到后天的餐单", "安排这周三餐"])
def test_multiple_dates_only_offer_plan_entry(text):
    """多个日期不能取其中一天静默生成。"""
    assert classify_health_intent(text).route == "exclusive_plan"


def test_purchase_vegetables_does_not_create_meal_plan():
    """买菜意图通过咨询的商城工具处理。"""
    assert classify_health_intent("给我买点菜").route == "nutrition_consultation"


@pytest.mark.parametrize("text", ["怎么吃更健康", "糖尿病饮食怎么吃", "请解释我明天餐单的营养"])
def test_nutrition_explanation_is_not_single_day_generation(text):
    """咨询含餐单或吃法词也不能自动生成。"""
    assert classify_health_intent(text).route == "nutrition_consultation"


@pytest.mark.parametrize("text", ["取消配菜", "不用配菜，讲讲营养", "不用了", "停止"])
def test_cancelled_planning_never_starts_meal_task(text):
    """取消请求优先于配菜关键词。"""
    assert classify_health_intent(text).route == "nutrition_consultation"


@pytest.mark.parametrize("text", ["给我安排11-15晚餐", "给我安排15号晚餐"])
def test_unresolved_explicit_date_requires_clarification(text):
    """不支持的日期写法不能静默变成今天。"""
    assert classify_health_intent(text).route == "needs_clarification"


def test_all_day_revision_expands_previous_single_meal():
    """明确全天要求覆盖上次单餐范围。"""
    result = classify_health_intent("重新安排三餐", previous_date=date(2026, 11, 11), previous_meals=["lunch"])
    assert result.meal_types == ["breakfast", "lunch", "dinner"]


def test_pending_view_stays_read_only():
    """待补充资料不把查看转换为继续生成。"""
    result = classify_health_intent(
        "查看今天的餐单",
        today=date(2026, 11, 9),
        previous_date=date(2026, 11, 9),
        previous_meals=["lunch"],
        awaiting_meal_details=True,
    )
    assert result.action == "view"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "output", ['{"route":"nutrition_consultation","action":"generate"}', "无效输出", "provider_error", "revoked"]
)
async def test_model_classification_uses_approved_budget_and_no_tools(monkeypatch, output):
    """真实模型调用边界必须先复核处理授权并结算用量。"""
    from contextlib import asynccontextmanager
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, Mock
    from uuid import uuid4
    from langchain_core.messages import AIMessage
    from yuxi.services import health_ai_budget_service as budget
    from yuxi.services import health_consultation_service as consultation
    from yuxi.services import health_intent_router_service as service
    from yuxi.services.health_intent_router_types import HealthIntentInput
    from yuxi.services.health_vision_types import HealthVisionError

    @asynccontextmanager
    async def session_context():
        """提供当前调用持有的事务。"""
        yield object()

    reservation = object()
    reserve = AsyncMock(return_value=reservation)
    authorize = AsyncMock()
    settle = AsyncMock()
    reply = AIMessage(content=output, usage_metadata={"input_tokens": 10, "output_tokens": 5, "total_tokens": 15})
    model = SimpleNamespace(ainvoke=AsyncMock(return_value=reply))
    if output == "provider_error":
        model.ainvoke.side_effect = RuntimeError("synthetic provider error")
    if output == "revoked":
        authorize.side_effect = HealthVisionError("consent_required", "合成授权已撤回", 409)
    factory = Mock(return_value=model)
    monkeypatch.setattr(budget, "reserve_model", reserve)
    monkeypatch.setattr(budget, "reserved_chat_model", factory)
    monkeypatch.setattr(budget, "settle", settle)
    monkeypatch.setattr(consultation, "require_consultation", authorize)
    from yuxi.storage.postgres.manager import pg_manager

    monkeypatch.setattr(pg_manager, "get_async_session_context", session_context)
    data = HealthIntentInput(text="安排一下", client_request_id=uuid4(), thread_id=uuid4())
    snapshot = {"model": "synthetic/model"}
    if output == "revoked":
        with pytest.raises(HealthVisionError, match="consent_required"):
            await service.analyze_health_intent("synthetic", data, date(2026, 11, 9), snapshot, [])
        factory.assert_not_called()
        model.ainvoke.assert_not_awaited()
        settle.assert_awaited_once_with(reservation, None)
        return
    result = await service.analyze_health_intent("synthetic", data, date(2026, 11, 9), snapshot, [])
    assert result.route == ("nutrition_consultation" if output.startswith("{") else "needs_clarification")
    reserve.assert_awaited_once_with("consultation", "intent:" + str(data.client_request_id), snapshot["model"])
    assert authorize.await_args.kwargs == {"expected": snapshot}
    assert model.ainvoke.await_args.kwargs == {}
    assert len(model.ainvoke.await_args.args[0]) == 2
    settle.assert_awaited_once_with(reservation, None if output == "provider_error" else reply.usage_metadata)

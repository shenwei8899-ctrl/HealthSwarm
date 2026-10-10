"""显式次日提议桥接的输入与失败边界，真实持久证据由 HTTP/E2E 提供。"""

import json
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from pydantic import ValidationError

from yuxi.services import health_next_day_agent_service as service
from yuxi.services.health_daily_service import business_date
from yuxi.services.health_next_day_agent_types import AgentNextDayProposalInput
from yuxi.services.health_vision_types import HealthVisionError

MEMBER, PREVIEW, RUN, THREAD = (str(uuid4()) for _ in range(4))


def input_body():
    """平台 Request ID 保留普通字符串合同。"""
    return {
        "client_request_id": str(uuid4()),
        "preview_id": PREVIEW,
        "source_date": business_date().isoformat(),
        "request_id": "synthetic-request:next-day",
        "final_message_id": 81,
    }


@pytest.mark.parametrize(
    "changed",
    [
        {"final_message_id": True},
        {"final_message_id": 0},
        {"request_id": ""},
        {"request_id": "x" * 65},
        {"nutrition": {}},
    ],
)
def test_agent_input_requires_selected_message_and_bounded_request_id(changed):
    """消息布尔值、缺标识与自由营养字段都在 HTTP 输入边界拒绝。"""
    with pytest.raises(ValidationError):
        AgentNextDayProposalInput.model_validate({**input_body(), **changed})


def test_request_id_does_not_require_uuid():
    """既有普通 Request 标识不因桥接变成 UUID 专属合同。"""
    assert AgentNextDayProposalInput.model_validate(input_body()).request_id == "synthetic-request:next-day"


@pytest.fixture
def scenario(monkeypatch):
    """复用来源 Owner 的单事务编排；不把此 fixture 当作持久证据。"""
    session = SimpleNamespace(refresh=AsyncMock())
    binding = SimpleNamespace(
        conversation_id=7,
        member_id=MEMBER,
        initial_planner_selection=None,
        family_planner_selection=None,
        safe_planner_selection=None,
    )
    request = SimpleNamespace(request_id="synthetic-request:next-day", agent_slug="health-meal-planner")
    run = SimpleNamespace(
        id=RUN,
        uid="actor",
        request_id=request.request_id,
        agent_slug=request.agent_slug,
        status="completed",
        conversation_thread_id=THREAD,
        conversation_id=7,
        input_payload={"health_processing": {"policy_version": "synthetic-v1"}},
    )
    message = SimpleNamespace(id=81, content=json.dumps({"preview_id": PREVIEW}))
    request_context = AsyncMock(return_value=(request, binding, run))
    final_message = AsyncMock(return_value=message)
    lock_run = AsyncMock(return_value=run)
    require = AsyncMock(return_value=(binding, run.input_payload["health_processing"]))
    validate = AsyncMock()
    registered = {"proposal_id": "proposal", "current": True, "formal_plan_saved": False}
    register = AsyncMock(return_value=registered)

    @asynccontextmanager
    async def context():
        yield session

    monkeypatch.setattr(service.pg_manager, "get_async_session_context", context)
    monkeypatch.setattr(
        service,
        "HealthTaskRepository",
        lambda _: SimpleNamespace(request_context=request_context, final_message=final_message),
    )
    monkeypatch.setattr(service, "HealthPlanAdoptionRepository", lambda _: SimpleNamespace(lock_request=AsyncMock()))
    monkeypatch.setattr(service, "AgentRunRepository", lambda _: SimpleNamespace(lock_run_for_user=lock_run))
    monkeypatch.setattr(service, "require_consultation", require)
    monkeypatch.setattr(service, "validate_task_business_result", validate)
    monkeypatch.setattr(service, "create_next_day_proposal_in_session", register)
    return SimpleNamespace(
        session=session,
        binding=binding,
        request=request,
        run=run,
        message=message,
        request_context=request_context,
        final_message=final_message,
        lock_run=lock_run,
        require=require,
        validate=validate,
        register=register,
        registered=registered,
    )


@pytest.mark.asyncio
async def test_success_keeps_source_revalidation_and_registration_in_one_transaction(scenario):
    """返回同请求最终消息引用，登记 Owner 收到同一来源校验事务。"""
    data = AgentNextDayProposalInput.model_validate(input_body())
    result = await service.create_agent_next_day_proposal("actor", MEMBER, RUN, data)
    origin = {"agent_run_id": RUN, "request_id": data.request_id, "final_message_id": 81}
    assert result == {**scenario.registered, **origin}
    scenario.require.assert_awaited_once_with(
        scenario.session,
        "actor",
        THREAD,
        expected=scenario.run.input_payload["health_processing"],
        lock=True,
    )
    scenario.register.assert_awaited_once_with(scenario.session, "actor", MEMBER, data, agent_origin=origin)


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["pending", "running", "cancel_requested", "failed", "cancelled", "interrupted"])
async def test_uncompleted_run_rejects_before_run_lock_and_final_message(scenario, status):
    """成员锁内的拒绝路径不能等待 Worker 已持有的 Run 锁。"""
    scenario.run.status = status
    with pytest.raises(HealthVisionError, match="answer_not_completed"):
        await service.create_agent_next_day_proposal("actor", MEMBER, RUN, AgentNextDayProposalInput(**input_body()))
    scenario.lock_run.assert_not_awaited()
    scenario.final_message.assert_not_awaited()
    scenario.register.assert_not_awaited()


@pytest.mark.asyncio
async def test_locked_run_refresh_still_checks_completed_status(scenario):
    """早返检查不能替代取得锁后对当前执行终态的复验。"""

    async def refresh_run(run):
        """模拟取得执行锁后发现持久状态已发生变化。"""
        run.status = "failed"

    scenario.session.refresh.side_effect = refresh_run
    with pytest.raises(HealthVisionError, match="answer_not_completed"):
        await service.create_agent_next_day_proposal("actor", MEMBER, RUN, AgentNextDayProposalInput(**input_body()))
    scenario.lock_run.assert_awaited_once_with(RUN, "actor")
    scenario.final_message.assert_not_awaited()
    scenario.register.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case,code",
    [
        ("wrong_role", "not_found"),
        ("wrong_member", "not_found"),
        ("not_dispatched", "answer_not_completed"),
        ("neighbor_run", "request_run_conflict"),
        ("initial_mode", "planner_mode_not_supported"),
        ("family_mode", "planner_mode_not_supported"),
        ("safe_mode", "planner_mode_not_supported"),
        ("unowned", "not_found"),
        ("pending", "answer_not_completed"),
        ("failed", "answer_not_completed"),
        ("wrong_message", "answer_unavailable"),
        ("no_processing", "policy_changed"),
        ("wrong_binding", "source_invalidated"),
        ("non_object", "source_invalidated"),
        ("questions", "planner_receipt_invalid"),
        ("neighbor_preview", "planner_receipt_invalid"),
    ],
)
async def test_invalid_selected_source_never_reaches_registration(scenario, case, code):
    """各输入与执行边界在正确原因上拒绝，避免写入邻运行或未完成结果。"""
    if case == "wrong_role":
        scenario.request.agent_slug = "health-diet-analyst"
    elif case == "wrong_member":
        scenario.binding.member_id = str(uuid4())
    elif case == "not_dispatched":
        scenario.request_context.return_value = (scenario.request, scenario.binding, None)
    elif case == "neighbor_run":
        scenario.run.id = str(uuid4())
    elif case.endswith("_mode"):
        setattr(scenario.binding, f"{case.removesuffix('_mode')}_planner_selection", {})
    elif case == "unowned":
        scenario.lock_run.return_value = None
    elif case in {"pending", "failed"}:
        scenario.run.status = case
    elif case == "wrong_message":
        scenario.message.id = 82
    elif case == "no_processing":
        scenario.run.input_payload = {}
    elif case == "wrong_binding":
        scenario.require.return_value = (SimpleNamespace(conversation_id=8, member_id=MEMBER), {})
    elif case == "non_object":
        scenario.message.content = "[]"
    elif case == "questions":
        scenario.message.content = json.dumps({"questions": ["合成补充问题"]})
    else:
        scenario.message.content = json.dumps({"preview_id": str(uuid4())})
    with pytest.raises(HealthVisionError, match=code):
        await service.create_agent_next_day_proposal("actor", MEMBER, RUN, AgentNextDayProposalInput(**input_body()))
    scenario.register.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("owner", ["require", "validate", "register"])
async def test_current_owner_errors_are_preserved(scenario, owner):
    """授权、来源与幂等 Owner 的稳定业务错误不被包装为成功。"""
    getattr(scenario, owner).side_effect = HealthVisionError("source_invalidated", "合成来源已变化", 410)
    with pytest.raises(HealthVisionError, match="source_invalidated"):
        await service.create_agent_next_day_proposal("actor", MEMBER, RUN, AgentNextDayProposalInput(**input_body()))
    if owner != "register":
        scenario.register.assert_not_awaited()

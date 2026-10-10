"""血脂工具真实装配、模型前置来源核验与派生回答发布边界。"""

import json
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.prebuilt.tool_node import ToolRuntime
from pydantic import ValidationError

from yuxi.agents.buildin.health_consultation.graph import HealthAuthorizationMiddleware, HealthConsultationAgent
from yuxi.agents.context import BaseContext
from yuxi.agents.toolkits.health import get_member_blood_lipids_records
from yuxi.repositories.health_blood_lipids_repository import HealthBloodLipidsRepository
from yuxi.repositories.health_blood_glucose_repository import HealthBloodGlucoseRepository
from yuxi.repositories.health_blood_pressure_repository import HealthBloodPressureRepository
from yuxi.repositories.health_consultation_repository import HealthConsultationRepository
from yuxi.repositories.health_family_profile_repository import HealthFamilyProfileRepository
from yuxi.repositories.health_weight_repository import HealthWeightRepository
from yuxi.services import health_blood_lipids_service, health_consultation_service
from yuxi.services.health_agent_roles import consultation_skill_prompt, health_agent_roles
from yuxi.services.health_family_profile_service import validate_profile_publication
from yuxi.services.health_vision_types import HealthVisionError


def tool_runtime():
    """构造服务端注入的固定本人上下文。"""
    return ToolRuntime(
        state={},
        context=SimpleNamespace(uid="actor", thread_id="thread", model="provider/fixed", request_id="request"),
        config={},
        stream_writer=lambda _: None,
        tool_call_id="blood-lipids-call",
        store=None,
    )


def test_blood_lipids_tool_rejects_identity_component_and_query_override():
    """模型不能选择成员、拼接单项或扩大范围，角色仍明确专业边界。"""
    assert get_member_blood_lipids_records.tool_call_schema.model_json_schema()["properties"] == {}
    runtime = tool_runtime()
    for field in ("uid", "member_id", "thread_id", "kind", "condition", "components", "period", "days", "limit"):
        with pytest.raises(ValidationError) as failure:
            get_member_blood_lipids_records.args_schema.model_validate({"runtime": runtime, field: "forged"})
        assert any(error["loc"] == (field,) and error["type"] == "extra_forbidden" for error in failure.value.errors())
    with pytest.raises(ValidationError):
        get_member_blood_lipids_records.args_schema.model_validate({"runtime": "forged-runtime"})
    prompt = consultation_skill_prompt()
    assert "get_member_blood_lipids_records" in prompt
    assert "`tc` 是总胆固醇" in prompt and "`tg` 是甘油三酯" in prompt
    assert "`hdl` 是高密度脂蛋白" in prompt and "`ldl` 是低密度脂蛋白" in prompt
    assert "不能跨记录拼接四项" in prompt and "推导non-HDL及比值" in prompt
    assert "营养安全状态仍未就绪" in prompt
    roles = health_agent_roles()
    assert roles["full_health_profile_available"] is False
    entries = {role["role"]: role for role in roles["roles"]}
    for role in ("health-profile", "health-nutritionist"):
        assert entries[role]["status"] == "partial" and "血脂" in entries[role]["implemented_scope"]


@pytest.mark.asyncio
async def test_blood_lipids_tool_delegates_injected_context_and_propagates_refusal(monkeypatch):
    """工具只调用受控服务，未关联和用途拒绝保持真实结果。"""
    runtime = tool_runtime()
    expected = {"status": "not_ready", "code": "blood_lipids_not_linked", "records": []}
    read = AsyncMock(return_value=expected)
    monkeypatch.setattr(health_blood_lipids_service, "blood_lipids_records_for_run", read)
    assert await get_member_blood_lipids_records.ainvoke({"runtime": runtime}) == expected
    read.assert_awaited_once_with(runtime.context)
    read.side_effect = HealthVisionError("consent_required", "合成用途同意撤回", 403)
    with pytest.raises(HealthVisionError, match="consent_required"):
        await get_member_blood_lipids_records.ainvoke({"runtime": runtime})


@pytest.mark.asyncio
@pytest.mark.parametrize("approved", [False, True])
async def test_blood_lipids_service_records_same_run_only_after_attempt_and_frozen_consent(monkeypatch, approved):
    """血脂读取与回执使用同一事务及服务器绑定，缺审批时不读取来源。"""
    session = object()

    @asynccontextmanager
    async def transaction():
        """隔离数据库连接，保留服务编排。"""
        yield session

    context = tool_runtime().context
    snapshot = {"processor": "approved"} if approved else None
    run = SimpleNamespace(input_payload={"health_processing": snapshot})
    binding = SimpleNamespace(member_id="server-bound-self")
    attempt = AsyncMock(return_value=run)
    require = AsyncMock(return_value=(binding, snapshot))
    expected = {"status": "not_ready", "code": "blood_lipids_missing", "records": []}
    read, record = AsyncMock(return_value=expected), AsyncMock()
    monkeypatch.setattr(health_blood_lipids_service.pg_manager, "get_async_session_context", transaction)
    monkeypatch.setattr(HealthConsultationRepository, "require_attempt", attempt)
    monkeypatch.setattr(health_consultation_service, "require_consultation", require)
    monkeypatch.setattr(HealthBloodLipidsRepository, "read", read)
    monkeypatch.setattr(HealthBloodLipidsRepository, "record_use", record)
    if approved:
        assert await health_blood_lipids_service.blood_lipids_records_for_run(context) == expected
        require.assert_awaited_once_with(
            session, context.uid, context.thread_id, context.model, expected=snapshot, lock=True
        )
        read.assert_awaited_once_with(context.uid, "server-bound-self")
        record.assert_awaited_once_with(run, expected)
    else:
        with pytest.raises(HealthVisionError, match="policy_changed"):
            await health_blood_lipids_service.blood_lipids_records_for_run(context)
        require.assert_not_awaited()
        read.assert_not_awaited()
        record.assert_not_awaited()
    attempt.assert_awaited_once_with(context, lock=True)


@pytest.fixture
def checkpoint_guard(monkeypatch):
    """隔离事务，保留实际模型前置中间件和JSON边界。"""
    session = object()

    @asynccontextmanager
    async def transaction():
        """提供无连接的合成事务。"""
        yield session

    context = tool_runtime().context
    binding = SimpleNamespace(member_id="server-bound-self", conversation_id=7)
    snapshot = {"model": context.model, "processor": "approved"}
    monkeypatch.setattr(health_consultation_service.pg_manager, "get_async_session_context", transaction)
    monkeypatch.setattr(
        HealthConsultationRepository,
        "require_attempt",
        AsyncMock(
            return_value=SimpleNamespace(
                agent_slug="health-consultation", input_payload={"health_processing": snapshot}
            )
        ),
    )
    monkeypatch.setattr(
        health_consultation_service, "require_consultation", AsyncMock(return_value=(binding, snapshot))
    )
    monkeypatch.setattr("yuxi.agents.buildin.health_consultation.graph.model_cache.get_model_info", lambda _: None)
    validate = AsyncMock()
    monkeypatch.setattr(HealthBloodLipidsRepository, "validate_tool_payload", validate)
    return SimpleNamespace(context=context, binding=binding, validate=validate)


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["ready", "not_ready"])
async def test_actual_model_entry_checks_blood_lipids_checkpoint_in_own_repository(checkpoint_guard, status):
    """成功与缺口正文均经过专用来源核验，不从工具名推断可信。"""
    state = checkpoint_guard
    payload = {"status": status, "records": []}
    message = ToolMessage(
        name="get_member_blood_lipids_records", tool_call_id="blood-lipids-call", content=json.dumps(payload)
    )
    middleware = HealthAuthorizationMiddleware(None)
    await middleware.abefore_model({"messages": [message]}, SimpleNamespace(context=state.context))
    state.validate.assert_awaited_once_with(state.context.uid, state.binding, payload)
    state.validate.side_effect = HealthVisionError("blood_lipids_source_changed", "合成LDL原值更正", 410)
    with pytest.raises(HealthVisionError, match="blood_lipids_source_changed"):
        await middleware.abefore_model({"messages": [message]}, SimpleNamespace(context=state.context))


@pytest.mark.asyncio
@pytest.mark.parametrize("content", ["not-json", '{"records":', [{"type": "text", "text": "总胆固醇4.8mmol/L"}]])
async def test_actual_model_entry_rejects_unparseable_blood_lipids_checkpoint(checkpoint_guard, content):
    """无法核对的checkpoint在模型调用前返回稳定失效码。"""
    state = checkpoint_guard
    message = ToolMessage(name="get_member_blood_lipids_records", tool_call_id="blood-lipids-call", content=content)
    with pytest.raises(HealthVisionError, match="blood_lipids_source_changed") as failure:
        await HealthAuthorizationMiddleware(None).abefore_model(
            {"messages": [message]}, SimpleNamespace(context=state.context)
        )
    assert failure.value.status == 410
    state.validate.assert_not_awaited()


@pytest.mark.asyncio
async def test_blood_lipids_error_checkpoint_is_not_forwarded_as_verified_source(checkpoint_guard):
    """工具错误不能携带未核对的血脂正文进入下一次模型调用。"""
    state = checkpoint_guard
    message = ToolMessage(
        name="get_member_blood_lipids_records",
        tool_call_id="blood-lipids-call",
        status="error",
        content='{"records":[{"tc":999}]}',
    )
    with pytest.raises(HealthVisionError, match="blood_lipids_source_changed"):
        await HealthAuthorizationMiddleware(None).abefore_model(
            {"messages": [message]}, SimpleNamespace(context=state.context)
        )
    state.validate.assert_not_awaited()


@pytest.mark.asyncio
async def test_derived_consultation_without_new_tool_and_final_publication_recheck_lipids(monkeypatch):
    """整线程血脂引用在只读与最终发布锁边界重验，派生轮不读工具也拒绝更正来源。"""
    binding = SimpleNamespace(
        member_id="health-self",
        conversation_id=7,
        initial_planner_selection=None,
        family_planner_selection=None,
        personal_target_selection=None,
    )
    conversation = SimpleNamespace(agent_id="health-consultation")

    async def scalar(statement):
        """绑定查询返回当前行；精确目标依赖查询没有匹配Run。"""
        if "personal_target_selection_hash" in statement.compile().params.values():
            assert "agent_runs.conversation_id" in str(statement)
            assert binding.conversation_id in statement.compile().params.values()
            return None
        assert "FROM health_consultation JOIN conversations" in str(statement)
        return binding

    session = SimpleNamespace(scalar=AsyncMock(side_effect=scalar), get=AsyncMock(return_value=conversation))
    monkeypatch.setattr(health_consultation_service.HealthVisionRepository, "authorize", AsyncMock())
    guards = [AsyncMock() for _ in range(5)]
    for repository, guard in zip(
        (
            HealthFamilyProfileRepository,
            HealthWeightRepository,
            HealthBloodPressureRepository,
            HealthBloodGlucoseRepository,
            HealthBloodLipidsRepository,
        ),
        guards,
        strict=True,
    ):
        monkeypatch.setattr(repository, "validate_history", guard)
    await HealthConsultationRepository(session).authorize("actor", "thread")
    for guard in guards[:-1]:
        guard.assert_awaited_once_with("actor", binding, lock=False)

    @asynccontextmanager
    async def transaction():
        """复用实际授权查询所使用的合成事务。"""
        yield session

    async def require(session, uid, thread_id, model_spec=None, *, expected, lock=False):
        """保留实际来源校验，隔离审批配置与Skill查询。"""
        assert expected == {"processor": "approved"}
        return await HealthConsultationRepository(session).authorize(uid, thread_id, lock=lock), expected

    monkeypatch.setattr(health_consultation_service.pg_manager, "get_async_session_context", transaction)
    monkeypatch.setattr(health_consultation_service, "require_consultation", require)
    run = SimpleNamespace(
        uid="actor",
        agent_slug="health-consultation",
        conversation_thread_id="thread",
        input_payload={"health_processing": {"processor": "approved"}},
    )
    monkeypatch.setattr(HealthConsultationRepository, "require_attempt", AsyncMock(return_value=run))
    guards[-1].side_effect = HealthVisionError("blood_lipids_source_changed", "合成LDL更正", 410)
    context = tool_runtime().context
    with pytest.raises(HealthVisionError, match="blood_lipids_source_changed"):
        await HealthAuthorizationMiddleware(None).abefore_model(
            {"messages": [HumanMessage(content="根据刚才的结果再说明一次")]}, SimpleNamespace(context=context)
        )
    guards[-1].assert_awaited_with("actor", binding, lock=False)
    with pytest.raises(HealthVisionError, match="blood_lipids_source_changed"):
        await validate_profile_publication(session, run)
    guards[-1].assert_awaited_with("actor", binding, lock=True)


@pytest.mark.asyncio
async def test_actual_graph_binds_and_executes_fixed_blood_lipids_tool(monkeypatch):
    """真实LangChain图把血脂工具及发布Skill交给模型，并注入当前context执行。"""
    from yuxi.agents.buildin.health_consultation import graph as graph_module
    from yuxi.services import health_meal_feedback_service

    tool_lists, system_prompts = [], []

    class SyntheticModel(GenericFakeChatModel):
        """仅记录实际模型装配并返回合成工具调用。"""

        def bind_tools(self, tools, **kwargs):
            """记录真实工具名单。"""
            tool_lists.append([tool.name for tool in tools])
            return self

        def _generate(self, messages, stop=None, run_manager=None, **kwargs):
            """记录实际输入的Skill正文。"""
            system_prompts.append(messages[0].content)
            return super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)

    model = SyntheticModel(
        messages=iter(
            [
                AIMessage(
                    content="",
                    tool_calls=[{"id": "blood-lipids-call", "name": "get_member_blood_lipids_records", "args": {}}],
                ),
                AIMessage(content="当前没有血脂记录，营养安全和21天控糖仍未就绪"),
            ]
        )
    )
    monkeypatch.setattr(graph_module, "load_chat_model", lambda **kwargs: model)
    monkeypatch.setattr(graph_module.SteerMiddleware, "_jump_if_steer_requested", AsyncMock(return_value=None))
    monkeypatch.setattr(health_consultation_service, "require_consultation_attempt", AsyncMock())
    monkeypatch.setattr(
        health_meal_feedback_service,
        "filter_health_history",
        AsyncMock(side_effect=lambda _, messages, **kwargs: messages),
    )
    read = AsyncMock(return_value={"status": "not_ready", "code": "blood_lipids_missing", "records": []})
    monkeypatch.setattr(health_blood_lipids_service, "blood_lipids_records_for_run", read)
    backend = HealthConsultationAgent()
    monkeypatch.setattr(backend, "_get_checkpointer", AsyncMock(return_value=InMemorySaver()))
    context = BaseContext(
        uid="actor", thread_id="synthetic-thread", model="synthetic/fixed", run_id="run", worker_id="owner"
    )
    context._runtime_prepared = True
    graph = await backend.get_graph(context=context)
    result = await graph.ainvoke(
        {"messages": [HumanMessage(content="回顾我的血脂")]},
        config={"configurable": {"thread_id": context.thread_id}, "recursion_limit": 20},
        context=context,
    )
    read.assert_awaited_once_with(context)
    assert tool_lists and all("get_member_blood_lipids_records" in tools for tools in tool_lists)
    assert all(set(tools) == set(health_consultation_service.HEALTH_TOOL_NAMES) for tools in tool_lists)
    assert system_prompts and all('version: "2026.10.10.1"' in prompt for prompt in system_prompts)
    tool_result = next(message for message in result["messages"] if message.type == "tool")
    assert tool_result.name == "get_member_blood_lipids_records"
    assert json.loads(tool_result.content) == read.return_value
    assert result["messages"][-1].content == "当前没有血脂记录，营养安全和21天控糖仍未就绪"

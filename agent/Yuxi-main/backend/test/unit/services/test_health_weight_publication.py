"""体重工具与 checkpoint 校验及派生正文的发布边界。"""

import json
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from langchain_core.messages import AIMessage, ToolMessage
from langgraph.prebuilt.tool_node import ToolRuntime
from pydantic import ValidationError

from yuxi.agents.toolkits.health import get_member_weight_records
from yuxi.repositories.health_weight_repository import HealthWeightRepository
from yuxi.services import chat_service, health_consultation_service, health_weight_service
from yuxi.services.health_vision_types import HealthVisionError


def tool_runtime():
    """注入合成运行上下文，身份由服务器固定。"""
    return ToolRuntime(
        state={},
        context=SimpleNamespace(uid="actor", thread_id="thread", model="provider/fixed"),
        config={},
        stream_writer=lambda _: None,
        tool_call_id="weight-call",
        store=None,
    )


def test_weight_tool_exposes_no_model_arguments_and_rejects_scope_override():
    """合法 runtime 下仍拒绝模型选择身份、指标、日期范围或数量。"""
    assert get_member_weight_records.tool_call_schema.model_json_schema()["properties"] == {}
    runtime = tool_runtime()
    for field in ("uid", "member_id", "thread_id", "kind", "period", "days", "limit"):
        with pytest.raises(ValidationError) as failure:
            get_member_weight_records.args_schema.model_validate({"runtime": runtime, field: "forged"})
        assert any(error["loc"] == (field,) and error["type"] == "extra_forbidden" for error in failure.value.errors())
    with pytest.raises(ValidationError):
        get_member_weight_records.args_schema.model_validate({"runtime": "forged-runtime"})


@pytest.mark.asyncio
async def test_weight_tool_delegates_server_context_and_propagates_authorization_failure(monkeypatch):
    """工具不合成体重或吞掉受控服务的拒绝结果。"""
    runtime = tool_runtime()
    expected = {"status": "not_ready", "code": "weight_missing", "records": []}
    read = AsyncMock(return_value=expected)
    monkeypatch.setattr(health_weight_service, "weight_records_for_run", read)

    assert await get_member_weight_records.ainvoke({"runtime": runtime}) == expected
    read.assert_awaited_once_with(runtime.context)
    read.side_effect = HealthVisionError("consent_required", "合成用途同意撤回", 403)
    with pytest.raises(HealthVisionError, match="consent_required"):
        await get_member_weight_records.ainvoke({"runtime": runtime})


@pytest.fixture
def checkpoint_guard(monkeypatch):
    """保留真实 checkpoint 解析，只隔离数据库用例及来源核验。"""
    session = object()

    @asynccontextmanager
    async def session_context():
        """无数据库连接的合成事务。"""
        yield session

    context = tool_runtime().context
    snapshot = {"processor": "approved", "policy_version": "policy", "model": context.model}
    run = SimpleNamespace(input_payload={"health_processing": snapshot})
    binding = SimpleNamespace(member_id="bound-self", conversation_id=7)
    attempt = AsyncMock(return_value=run)
    require = AsyncMock(return_value=(binding, snapshot))
    validate = AsyncMock()
    monkeypatch.setattr(health_consultation_service.pg_manager, "get_async_session_context", session_context)
    monkeypatch.setattr(health_consultation_service.HealthConsultationRepository, "require_attempt", attempt)
    monkeypatch.setattr(health_consultation_service, "require_consultation", require)
    monkeypatch.setattr(HealthWeightRepository, "validate_tool_payload", validate)
    return SimpleNamespace(
        context=context,
        session=session,
        binding=binding,
        snapshot=snapshot,
        attempt=attempt,
        require=require,
        validate=validate,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("records", [[], [{"record_id": "weight-record", "value": 67.5, "version": 1}]])
async def test_weight_checkpoint_delegates_parsed_payload_to_current_bound_member(checkpoint_guard, records):
    """空结果及实测结果均不能跳过真实线程来源校验。"""
    state = checkpoint_guard
    payload = {"records": records, "period": {"start_date": "2026-09-09", "end_date": "2026-10-08"}}
    message = ToolMessage(name="get_member_weight_records", tool_call_id="weight-call", content=json.dumps(payload))

    await health_consultation_service.require_consultation_attempt(state.context, [message])

    state.attempt.assert_awaited_once_with(state.context)
    state.require.assert_awaited_once_with(
        state.session, state.context.uid, state.context.thread_id, state.context.model, expected=state.snapshot
    )
    state.validate.assert_awaited_once_with(state.context.uid, state.binding, payload)


@pytest.mark.asyncio
@pytest.mark.parametrize("content", ["not-json", '{"records":', [{"type": "text", "text": "67.5kg"}]])
async def test_malformed_weight_checkpoint_fails_before_repository_delegation(checkpoint_guard, content):
    """无法解析的 checkpoint 不可成为下一次模型调用的可信来源。"""
    state = checkpoint_guard
    message = ToolMessage(name="get_member_weight_records", tool_call_id="weight-call", content=content)

    with pytest.raises(HealthVisionError, match="weight_source_changed") as failure:
        await health_consultation_service.require_consultation_attempt(state.context, [message])

    assert failure.value.status == 410
    state.validate.assert_not_awaited()


@pytest.mark.asyncio
async def test_weight_checkpoint_source_rejection_propagates_to_model_call_guard(checkpoint_guard):
    """有效 JSON 不能绕过 repository 对更正、伪造或撤权的拒绝。"""
    state = checkpoint_guard
    error = HealthVisionError("weight_source_changed", "合成体重更正", 410)
    state.validate.side_effect = error
    message = ToolMessage(name="get_member_weight_records", tool_call_id="weight-call", content='{"records":[]}')

    with pytest.raises(HealthVisionError) as failure:
        await health_consultation_service.require_consultation_attempt(state.context, [message])

    assert failure.value is error
    state.validate.assert_awaited_once_with(state.context.uid, state.binding, {"records": []})


@pytest.mark.asyncio
async def test_weight_tool_error_feedback_is_not_parsed_as_successful_source(checkpoint_guard):
    """错误反馈可保留失败语义，但不能当作已读取的体重来源。"""
    state = checkpoint_guard
    message = ToolMessage(
        name="get_member_weight_records", tool_call_id="weight-call", content="合成读取失败", status="error"
    )

    await health_consultation_service.require_consultation_attempt(state.context, [message])

    state.validate.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("interrupt", [False, True])
@pytest.mark.parametrize("has_weight_dependency", [False, True])
@pytest.mark.parametrize("dependency_kind", ["weight", "blood_pressure", "blood_glucose", "blood_lipids"])
async def test_weight_derived_partial_discards_private_body_and_metadata(
    monkeypatch, interrupt, has_weight_dependency, dependency_kind
):
    """只有前轮独立测量依赖也阻断私有正文；去除对应EXISTS分支使负控变红。"""

    async def dependency_run(statement):
        """仅当本次查询确实包含当前测量表，才返回该表的历史回执。"""
        if has_weight_dependency and f"health_{dependency_kind}_use.run_id = agent_runs.id" in str(statement):
            return f"prior-{dependency_kind}-run"
        return None

    session = SimpleNamespace(
        scalar=AsyncMock(side_effect=dependency_run),
        commit=AsyncMock(),
        rollback=AsyncMock(),
    )
    saved = SimpleNamespace(id=42)
    conv = SimpleNamespace(db=session, add_message_by_thread_id=AsyncMock(return_value=saved))
    locked = SimpleNamespace(agent_slug="health-consultation", conversation_id=7)
    repo = SimpleNamespace(
        lock_output_persistence=AsyncMock(return_value=locked),
        set_output_message=AsyncMock(),
        set_terminal_status=AsyncMock(return_value=(locked, True)),
        cancel_active_execution_tree_descendants=AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(chat_service, "AgentRunRepository", lambda db: repo)
    monkeypatch.setattr(chat_service, "publish_cancel_signals", AsyncMock())
    private = f"synthetic-private-{dependency_kind}-body"
    output = await chat_service.save_partial_message(
        conv,
        "thread",
        full_msg=AIMessage(content=private, additional_kwargs={"private": private}, response_metadata={"raw": private}),
        error_message=private,
        trace_info={"private_trace": private},
        run_id="derived-run",
        request_id="request",
        worker_id="worker",
        interrupt_run=interrupt,
    )

    session.scalar.assert_awaited_once()
    query = session.scalar.await_args.args[0]
    sql = str(query)
    assert "health_weight_use.run_id = agent_runs.id" in sql and "EXISTS" in sql and " OR " in sql
    assert "health_blood_pressure_use.run_id = agent_runs.id" in sql
    assert "health_blood_glucose_use.run_id = agent_runs.id" in sql
    assert "health_blood_lipids_use.run_id = agent_runs.id" in sql
    assert "agent_runs.conversation_id" in sql and 7 in query.compile().params.values()
    session.rollback.assert_not_awaited()
    if has_weight_dependency and not interrupt:
        assert output is None
        conv.add_message_by_thread_id.assert_not_awaited()
        repo.set_output_message.assert_not_awaited()
        session.commit.assert_not_awaited()
        return

    assert output is saved
    written = conv.add_message_by_thread_id.await_args.kwargs
    if has_weight_dependency:
        assert written["content"] == ""
        assert written["extra_metadata"] == {
            "error_type": "interrupted",
            "is_error": True,
            "error_message": "咨询已中断",
        }
        assert private not in str(written)
    else:
        assert written["content"] == private
        assert written["extra_metadata"]["private_trace"] == private
    assert written["run_id"] == "derived-run" and written["request_id"] == "request"
    repo.set_output_message.assert_awaited_once_with("derived-run", 42, worker_id="worker")
    session.commit.assert_awaited_once()
    if interrupt:
        assert repo.set_terminal_status.await_args.kwargs["status"] == "interrupted"
    else:
        repo.set_terminal_status.assert_not_awaited()

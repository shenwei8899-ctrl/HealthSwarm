"""用户版本选择、最小目标投影、固定工具及完整来源失效的语义验证。"""

import hashlib
import json
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError
from yuxi.services import health_agent_personal_target_service as service
from yuxi.services.health_agent_personal_target_types import TargetAwareAnalystInput
from yuxi.services.health_quality_types import PersonalTargetSelection
from yuxi.services.health_vision_types import HealthVisionError

MEMBER = "11111111-1111-1111-1111-111111111111"
CLIENT_REQUEST = "22222222-2222-2222-2222-222222222222"
PROFILE = "33333333-3333-3333-3333-333333333333"
RULES = "44444444-4444-4444-4444-444444444444"
SELECTED = {"profile_version": 2, "rule_version": 2, "rule_code": "synthetic-target"}


def owner_result():
    """目标数值人工指定为330，私密输入不能出现在模型投影。"""
    return {
        "status": "ready",
        "reason": None,
        "energy_kcal": "330",
        "units": {"energy_kcal": "kcal"},
        "bounds": {"energy_kcal": {"minimum": "330", "maximum": "330"}},
        "formula_bounds": {"energy_kcal": {"minimum": "330", "maximum": "330"}},
        "inputs": {"weight_kg": "60", "conditions": ["synthetic-private-condition"]},
        "formula": {
            "population_code": "synthetic-private-population",
            "condition_codes": [],
        },
        "sources": {
            "profile": {
                "id": PROFILE,
                "version": 2,
                "content_hash": "a" * 64,
                "status": "ready",
                "reason": None,
            },
            "rules": {
                "id": RULES,
                "version": 2,
                "content_hash": "b" * 64,
                "status": "ready",
                "reason": None,
                "rule_code": "synthetic-target",
            },
        },
        "attestations": {
            "profile": {"source_ref": "synthetic://private-proof"},
            "rules": {},
        },
        "professional_review": "not_a_professional_decision",
    }


def raw_digest(value):
    """独立规范化oracle，不调用生产hash函数。"""
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()


def binding():
    """整个线程的明确选择，没有临床正文副本。"""
    return SimpleNamespace(
        actor_uid="actor",
        member_id=MEMBER,
        conversation_id=9,
        personal_target_selection={
            "selection": SELECTED,
            "source_hash": raw_digest(owner_result()),
        },
    )


def test_target_aware_entry_requires_user_selected_versions_and_rejects_model_values():
    """入口只有幂等键及专业版本，不接受身份、身体参数或目标值。"""
    data = {"client_request_id": CLIENT_REQUEST, "target_selection": SELECTED}
    parsed = TargetAwareAnalystInput.model_validate(data)
    assert parsed.target_selection == PersonalTargetSelection.model_validate(SELECTED)
    assert TargetAwareAnalystInput.model_validate({"client_request_id": CLIENT_REQUEST}).target_selection is None
    for field in (
        "member_id",
        "actor_uid",
        "agent_slug",
        "model",
        "bounds",
        "weight_kg",
    ):
        with pytest.raises(ValidationError):
            TargetAwareAnalystInput.model_validate({**data, field: "forged"})
        with pytest.raises(ValidationError):
            TargetAwareAnalystInput.model_validate({**data, "target_selection": {**SELECTED, field: "forged"}})


def test_projection_is_current_reference_and_omits_raw_profile_rules_and_calculation_inputs():
    """目标不能应用到记录窗口，输出不含差额、趋势或专业决定。"""
    current = owner_result()
    result = service.target_public_projection(current)
    assert result == {
        "scope": "current_personal_targets",
        "status": "ready",
        "energy_kcal": "330",
        "bounds": {"energy_kcal": {"minimum": "330", "maximum": "330"}},
        "units": {"energy_kcal": "kcal"},
        "sources": current["sources"],
        "source_hash": raw_digest(current),
        "professional_review": "not_a_professional_decision",
        "applied_to_record_window": False,
    }
    assert "synthetic-private" not in json.dumps(result)
    assert (
        not {
            "inputs",
            "formula",
            "formula_bounds",
            "attestations",
            "difference",
            "trend",
            "daily_complete",
        }
        & result.keys()
    )
    assert current == owner_result()


@pytest.mark.asyncio
async def test_bound_target_uses_original_owner_in_existing_session_and_freezes_complete_source(
    monkeypatch,
):
    """读取数字、当前审核、版本与实测依据都由Owner负责，不开嵌套事务。"""
    current = owner_result()
    reader = AsyncMock(return_value=current)
    monkeypatch.setattr(service, "personal_targets_in_session", reader)
    result = await service.target_context_in_session("session", "actor", MEMBER, PersonalTargetSelection(**SELECTED))
    assert result == current
    reader.assert_awaited_once_with("session", "actor", MEMBER, PersonalTargetSelection(**SELECTED))


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["not_ready", "version", "content_hash", "attestation", "value"])
async def test_authorized_binding_rejects_changed_current_owner_projection(monkeypatch, change):
    """Owner最高版本、专业依据或数字改变不能沿用旧线程；不退旧来源。"""
    current = owner_result()
    if change == "not_ready":
        current = {
            "status": "not_ready",
            "reason": "weight_measurement_source_changed",
            "sources": current["sources"],
        }
    elif change == "version":
        current["sources"]["profile"]["version"] = 3
    elif change == "content_hash":
        current["sources"]["rules"]["content_hash"] = "c" * 64
    elif change == "attestation":
        current["attestations"]["profile"]["source_ref"] = "synthetic://changed-proof"
    else:
        current["bounds"]["energy_kcal"]["maximum"] = "999"
    monkeypatch.setattr(service, "target_context_in_session", AsyncMock(return_value=current))
    with pytest.raises(HealthVisionError, match="source_invalidated"):
        await service.authorize_personal_target_binding("session", binding())


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "stored",
    [
        None,
        {},
        {"selection": SELECTED},
        {"selection": {"rule_code": "synthetic-target"}, "source_hash": "a" * 64},
    ],
)
async def test_malformed_selected_binding_fails_before_owner_read(monkeypatch, stored):
    """待选普通模式由调用方处理，已声明的目标模式不得容忍残缺选择。"""
    current = binding()
    current.personal_target_selection = stored
    reader = AsyncMock()
    monkeypatch.setattr(service, "target_context_in_session", reader)
    with pytest.raises(HealthVisionError, match="source_invalidated"):
        await service.authorize_personal_target_binding("session", current)
    reader.assert_not_called()


@pytest.mark.asyncio
async def test_successful_target_payload_must_equal_authorized_minimal_projection(
    monkeypatch,
):
    """合法来源ID不能授权多加身体字段或篡改同ID数字。"""
    current = owner_result()
    monkeypatch.setattr(service, "authorize_personal_target_binding", AsyncMock(return_value=current))
    projected = service.target_public_projection(current)
    await service.validate_personal_target_tool_payload("session", binding(), projected)
    for change in ("target", "private", "remove", "source"):
        forged = deepcopy(projected)
        if change == "target":
            forged["energy_kcal"] = "999"
        elif change == "private":
            forged["weight_kg"] = "60"
        elif change == "remove":
            forged.pop("source_hash")
        else:
            forged["sources"]["profile"]["id"] = RULES
        with pytest.raises(HealthVisionError, match="source_invalidated"):
            await service.validate_personal_target_tool_payload("session", binding(), forged)


@pytest.mark.asyncio
async def test_missing_owner_dependencies_do_not_produce_current_targets(monkeypatch):
    """初次绑定缺A批准依赖明确503；已有绑定失效后不自动成为无目标模式。"""
    monkeypatch.setattr(service, "personal_targets_in_session", AsyncMock(return_value={"status": "not_ready"}))
    with pytest.raises(HealthVisionError, match="target_dependencies_not_ready") as initial:
        await service.target_context_in_session("session", "actor", MEMBER, PersonalTargetSelection(**SELECTED))
    assert initial.value.status == 503
    with pytest.raises(HealthVisionError, match="source_invalidated") as changed:
        await service.authorize_personal_target_binding("session", binding())
    assert changed.value.status == 410


@pytest.mark.asyncio
async def test_authorized_owner_permission_error_is_preserved_without_admin_fallback(monkeypatch):
    """当前profile_view拒绝仍为404，不转成可读的依赖缺失正文。"""
    monkeypatch.setattr(
        service, "target_context_in_session", AsyncMock(side_effect=HealthVisionError("not_found", "不可见", 404))
    )
    with pytest.raises(HealthVisionError, match="not_found") as error:
        await service.authorize_personal_target_binding("session", binding())
    assert error.value.status == 404


def test_final_current_targets_do_not_change_fact_boundary_or_known_record_values():
    """当前330与已记录120并列；即使1日也不生成差额、达标或完整全天结论。"""
    facts = {"personal_target": None, "personalized": False, "nutrition": {"energy_kcal": "120.00"}}
    current_binding = binding()
    current_binding._personal_target_current = owner_result()
    result = service.attach_current_personal_targets(current_binding, facts)
    assert result["current_personal_targets"]["energy_kcal"] == "330"
    assert result["personal_target"] is None and result["personalized"] is False
    assert result["nutrition"] == {"energy_kcal": "120.00"}
    assert facts == {"personal_target": None, "personalized": False, "nutrition": {"energy_kcal": "120.00"}}
    assert service.attach_current_personal_targets(SimpleNamespace(), facts) == facts
    with pytest.raises(HealthVisionError, match="source_invalidated"):
        service.attach_current_personal_targets(binding(), facts)


@pytest.mark.asyncio
async def test_target_bound_manifest_excludes_feedback_generic_and_profile_tools(monkeypatch):
    """PG绑定增加唯一只读目标工具，用户context不能开放别的工具和知识。"""
    from yuxi.agents.context import BaseContext
    from yuxi.services import health_consultation_service as consultation

    approved = {"model": "test:fixed", "processor": "fingerprint", "policy_version": "policy"}
    monkeypatch.setattr(consultation, "require_consultation", AsyncMock(return_value=(binding(), approved)))
    context = BaseContext(uid="actor", thread_id="thread", tools=["get_complete_health_profile"], mcps=["all"])
    prepared = await consultation.prepare_consultation_context(
        context,
        SimpleNamespace(get=AsyncMock(return_value=None)),
        SimpleNamespace(agent_slug="health-diet-analyst", input_payload={"health_processing": approved}),
    )
    assert prepared.tools == [
        "list_analysis_meals",
        "analyze_confirmed_meal",
        "analyze_confirmed_period",
        "get_bound_personal_targets",
    ]
    assert prepared.skills == prepared.preload_skills == ["family-diet-analyst"]
    assert prepared.knowledges == prepared.mcps == []


@pytest.mark.asyncio
async def test_actual_bound_graph_four_tools_and_runtime_identity_reject_rule_arguments(monkeypatch):
    """真实LangChain注入协议：模型多传规则失败，无参目标调用只使用runtime身份。"""
    from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
    from langchain_core.messages import AIMessage, HumanMessage
    from langgraph.checkpoint.memory import InMemorySaver

    from yuxi.agents.buildin.health_diet_analyst import graph as graph_module
    from yuxi.agents.context import BaseContext
    from yuxi.services import health_consultation_service as consultation
    from yuxi.services import health_diet_analysis_service as analysis
    from yuxi.services import health_dialog_feedback_service as feedback
    from yuxi.services import health_memory_service, health_meal_feedback_service

    actual_tool_lists = []
    monkeypatch.setattr(
        health_memory_service, "filter_memory_history", AsyncMock(side_effect=lambda _, messages, **kwargs: messages)
    )
    monkeypatch.setattr(
        health_meal_feedback_service,
        "filter_health_history",
        AsyncMock(side_effect=lambda _, messages, **kwargs: messages),
    )

    class SyntheticModel(GenericFakeChatModel):
        """记录真正传给模型的工具schema，不推断已注册即已装配。"""

        def bind_tools(self, tools, **kwargs):
            actual_tool_lists.append([tool.name for tool in tools])
            return self

    model = SyntheticModel(
        messages=iter(
            [
                AIMessage(
                    content="",
                    tool_calls=[{"id": "bad", "name": "get_bound_personal_targets", "args": {"rule_code": "forged"}}],
                ),
                AIMessage(content="", tool_calls=[{"id": "good", "name": "get_bound_personal_targets", "args": {}}]),
                AIMessage(content='{"questions":["哪一餐？"]}'),
            ]
        )
    )
    monkeypatch.setattr(graph_module, "load_chat_model", lambda **kwargs: model)
    monkeypatch.setattr(graph_module.SteerMiddleware, "_jump_if_steer_requested", AsyncMock(return_value=None))
    ownership = AsyncMock()
    monkeypatch.setattr(consultation, "require_consultation_attempt", ownership)
    monkeypatch.setattr(feedback, "is_feedback_conversation", AsyncMock(return_value=False))
    monkeypatch.setattr(service, "is_personal_target_conversation", AsyncMock(return_value=True))
    reader = AsyncMock(return_value=service.target_public_projection(owner_result()))
    monkeypatch.setattr(service, "bound_personal_targets", reader)
    monkeypatch.setattr(analysis, "analyst_final_result", AsyncMock(return_value={"status": "needs_input"}))
    backend = graph_module.HealthDietAnalystAgent()
    monkeypatch.setattr(backend, "_get_checkpointer", AsyncMock(return_value=InMemorySaver()))
    context = BaseContext(
        uid="actor", thread_id="bound-thread", model="synthetic/fixed", run_id="run", worker_id="owner"
    )
    context._runtime_prepared = True
    graph = await backend.get_graph(context=context)
    result = await graph.ainvoke(
        {"messages": [HumanMessage(content="合成读取当前批准目标")]},
        config={"configurable": {"thread_id": context.thread_id}, "recursion_limit": 40},
        context=context,
    )
    assert actual_tool_lists and all(
        names
        == ["list_analysis_meals", "analyze_confirmed_meal", "analyze_confirmed_period", "get_bound_personal_targets"]
        for names in actual_tool_lists
    )
    assert result["messages"][-1].content == '{"status": "needs_input"}'
    assert any(message.type == "tool" and message.status == "error" for message in result["messages"])
    reader.assert_awaited_once_with(context)
    assert ownership.await_count == 4


@pytest.mark.parametrize(
    "removed",
    ["list_analysis_meals", "analyze_confirmed_meal", "analyze_confirmed_period", "get_bound_personal_targets"],
)
def test_bound_replay_oracle_rejects_each_missing_registered_tool(removed):
    """shipping四工具协议逐个反证，不把原普通三工具oracle放宽。"""
    from test.support.health_agent_personal_target_replay_server import MODEL, TOOLS, replay_delta

    body = {
        "model": MODEL,
        "stream": True,
        "tools": [{"function": {"name": name, "parameters": {"properties": {}}}} for name in sorted(TOOLS)],
        "messages": [
            {"role": "system", "content": "slug: family-diet-analyst"},
            {"role": "user", "content": "HEALTH_AGENT_TARGET_E2E:" + "a" * 32 + ":single"},
        ],
    }
    delta, answered = replay_delta("Bearer synthetic-target-key", body)
    assert answered is False and delta["tool_calls"][0]["function"]["name"] == "get_bound_personal_targets"
    body["tools"] = [item for item in body["tools"] if item["function"]["name"] != removed]
    with pytest.raises(ValueError, match="fixed_four_tools_required"):
        replay_delta("Bearer synthetic-target-key", body)

"""健康咨询处理审批、最小投影和实际受限执行图的本地验证。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.memory import InMemorySaver
from pydantic import ValidationError

from yuxi.agents.buildin.health_consultation.graph import HealthConsultationAgent
from yuxi.agents.context import BaseContext
from yuxi.agents.toolkits.health import get_confirmed_diet, get_confirmed_profile
from yuxi.services import health_consultation_service as service
from yuxi.services.health_vision_types import ConsultationInput, HealthVisionError, VisionConfigurationInput
from yuxi.utils.datetime_utils import utc_now_naive


def test_tool_schema_has_no_identity_and_rejects_extra_arguments():
    """模型参数不能指定账号、成员、线程或覆盖 runtime。"""
    for tool in (get_confirmed_profile, get_confirmed_diet):
        schema = tool.tool_call_schema.model_json_schema()
        assert schema["properties"] == {}
        assert tool.args_schema.model_config["extra"] == "forbid"
        for field in ("member_id", "uid", "thread_id", "runtime"):
            with pytest.raises(ValidationError):
                tool.args_schema.model_validate({field: "forged"})


def test_projection_omits_evidence_original_value_and_private_keys():
    """任意 OCR 原文与私有键不进入业务工具输出，缺失数字不补造。"""
    record = SimpleNamespace(
        id="confirmed-record",
        created_at=utc_now_naive(),
        snapshot={
            "name": "合成血糖",
            "value_numeric": None,
            "unit_raw": "mmol/L",
            "source": "manual",
            "value_raw": "synthetic-private-name",
            "evidence": {"raw_text": "synthetic-private-ocr"},
            "object_key": "synthetic-private-object",
            "member_id": "forged-member",
        },
    )
    projected = service.project_confirmed_record(record, "report")
    assert projected["value_numeric"] is None and projected["record_id"] == record.id
    assert set(projected) == {
        "record_id",
        "confirmed_at",
        "name",
        "observation_code",
        "value_numeric",
        "unit_raw",
        "reference_raw",
        "observed_at",
        "fasting",
        "source",
    }
    assert "synthetic-private" not in str(projected)


def test_consultation_configuration_requires_explicit_policy_review():
    """新增用途也不能凭默认值启用云模型。"""
    with pytest.raises(ValidationError):
        VisionConfigurationInput(consultation_model="provider/fixed-model")
    with pytest.raises(ValidationError):
        ConsultationInput(client_request_id="00000000-0000-4000-8000-000000000001", member_id="forged")


@pytest.mark.asyncio
async def test_unavailable_and_wrong_purpose_fail_before_model_configuration(monkeypatch):
    """未审批不能回落默认模型，已审批但未同意咨询用途仍拒绝。"""
    monkeypatch.setattr(
        service.HealthConsultationRepository,
        "authorize",
        AsyncMock(return_value=SimpleNamespace(member_id="member", conversation_id="conversation")),
    )
    config = {"policy_version": "policy", "consultation": {"available": False}}
    monkeypatch.setattr(service.health_vision_service, "configuration", AsyncMock(return_value=config))
    consent = AsyncMock(side_effect=HealthVisionError("consent_required", "合成未同意", 403))
    monkeypatch.setattr(service.HealthVisionRepository, "require_consent", consent)
    with pytest.raises(HealthVisionError, match="consultation_unavailable"):
        await service.require_consultation(
            SimpleNamespace(get=AsyncMock(return_value=SimpleNamespace(agent_id="health-consultation"))),
            "actor",
            "thread",
        )
    consent.assert_not_awaited()
    config["consultation"] = {"available": True, "model": "provider/fixed", "processor": "fingerprint"}
    with pytest.raises(HealthVisionError, match="policy_changed"):
        await service.require_consultation(
            SimpleNamespace(get=AsyncMock(return_value=SimpleNamespace(agent_id="health-consultation"))),
            "actor",
            "thread",
            "other/model",
        )
    with pytest.raises(HealthVisionError, match="policy_changed"):
        await service.require_consultation(
            SimpleNamespace(get=AsyncMock(return_value=SimpleNamespace(agent_id="health-consultation"))),
            "actor",
            "thread",
            expected={"processor": "old"},
        )
    with pytest.raises(HealthVisionError, match="consent_required"):
        await service.require_consultation(
            SimpleNamespace(get=AsyncMock(return_value=SimpleNamespace(agent_id="health-consultation"))),
            "actor",
            "thread",
        )
    assert consent.await_args.args[2] == "consultation"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "source_type,enabled", [(None, False), ("builtin", False), ("upload", True), ("builtin", True)]
)
async def test_consultation_requires_enabled_builtin_skill(monkeypatch, source_type, enabled):
    """平台停用与缺失内置 Skill 时不能通过个人同名内容回退。"""
    binding = SimpleNamespace(member_id="member", conversation_id="conversation")
    monkeypatch.setattr(service.HealthConsultationRepository, "authorize", AsyncMock(return_value=binding))
    approved = {"available": True, "model": "provider/fixed", "processor": "fingerprint"}
    monkeypatch.setattr(
        service.health_vision_service,
        "configuration",
        AsyncMock(return_value={"policy_version": "policy", "consultation": approved}),
    )
    monkeypatch.setattr(service.HealthVisionRepository, "require_consent", AsyncMock())
    skill = None if source_type is None else SimpleNamespace(source_type=source_type, enabled=enabled)
    lookup = AsyncMock(return_value=skill)
    monkeypatch.setattr(service.SkillRepository, "get_by_slug", lookup)
    if source_type == "builtin" and enabled:
        actual, _ = await service.require_consultation(
            SimpleNamespace(get=AsyncMock(return_value=SimpleNamespace(agent_id="health-consultation"))),
            "actor",
            "thread",
        )
        assert actual is binding
    else:
        with pytest.raises(HealthVisionError, match="nutritionist_skill_unavailable"):
            await service.require_consultation(
                SimpleNamespace(get=AsyncMock(return_value=SimpleNamespace(agent_id="health-consultation"))),
                "actor",
                "thread",
            )
    lookup.assert_awaited_once_with("family-nutritionist")


@pytest.mark.asyncio
async def test_context_does_not_expand_none_resources_or_user_prompt(monkeypatch):
    """清单上下文排除通用资源和用户工作区提示，审批来自 Run 冻结快照。"""
    snapshot = {"model": "provider/fixed", "processor": "fingerprint", "policy_version": "policy"}
    require = AsyncMock(return_value=(SimpleNamespace(member_id="member", conversation_id="conversation"), snapshot))
    monkeypatch.setattr(service, "require_consultation", require)
    context = BaseContext(
        uid="actor",
        thread_id="thread",
        system_prompt="untrusted workspace instruction",
        skills=["untrusted"],
        preload_skills=["untrusted"],
    )
    run = SimpleNamespace(agent_slug="health-consultation", input_payload={"health_processing": snapshot})
    prepared = await service.prepare_consultation_context(context, None, run)
    assert prepared.model == "provider/fixed" and prepared.tools == service.HEALTH_TOOL_NAMES
    assert prepared.system_prompt == service.CONSULTATION_PROMPT
    assert prepared.knowledges == prepared.mcps == []
    assert prepared.skills == prepared.preload_skills == ["family-nutritionist"]
    assert prepared._skill_runtime_snapshot["skill_metadata"]["family-nutritionist"]["source_scope"] == "builtin"
    assert require.await_args.kwargs["expected"] == snapshot
    with pytest.raises(HealthVisionError, match="policy_changed"):
        await service.prepare_consultation_context(context, None, SimpleNamespace(input_payload={}))


@pytest.mark.asyncio
async def test_actual_graph_only_binds_fixed_read_tools_and_checks_each_model_turn(monkeypatch):
    """真实 LangChain 构图与工具注入联调，不发起供应商请求。"""
    from yuxi.agents.buildin.health_consultation import graph as graph_module
    from yuxi.services import health_memory_service, health_meal_feedback_service

    monkeypatch.setattr(
        health_memory_service, "filter_memory_history", AsyncMock(side_effect=lambda _, messages, **kwargs: messages)
    )

    monkeypatch.setattr(
        health_meal_feedback_service,
        "filter_health_history",
        AsyncMock(side_effect=lambda _, messages, **kwargs: messages),
    )

    tool_lists = []
    system_prompts = []

    class SyntheticModel(GenericFakeChatModel):
        """合成模型仅记录实际可调用工具名单。"""

        def bind_tools(self, tools, **kwargs):
            """保留工具协议，返回固定合成消息。"""
            tool_lists.append([tool.name for tool in tools])
            return self

        def _generate(self, messages, stop=None, run_manager=None, **kwargs):
            """读取模型实际收到的系统内容，不从角色声明推断 Skill 已生效。"""
            system_prompts.append(messages[0].content)
            return super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)

    model = SyntheticModel(
        messages=iter(
            [
                AIMessage(
                    content="",
                    tool_calls=[
                        {"id": "call-invalid", "name": "get_confirmed_profile", "args": {"member_id": "forged"}}
                    ],
                ),
                AIMessage(
                    content="", tool_calls=[{"id": "call-synthetic", "name": "get_confirmed_profile", "args": {}}]
                ),
                AIMessage(content="合成记录解释，不是医疗建议"),
            ]
        )
    )
    monkeypatch.setattr(graph_module, "load_chat_model", lambda **kwargs: model)
    monkeypatch.setattr(graph_module.SteerMiddleware, "_jump_if_steer_requested", AsyncMock(return_value=None))
    ownership = AsyncMock()
    monkeypatch.setattr(service, "require_consultation_attempt", ownership)
    executor = AsyncMock(return_value={"records": [], "full_health_profile_available": False})
    monkeypatch.setattr(service, "confirmed_consultation_records", executor)
    backend = HealthConsultationAgent()
    monkeypatch.setattr(backend, "_get_checkpointer", AsyncMock(return_value=InMemorySaver()))
    context = BaseContext(
        uid="actor", thread_id="synthetic-thread", model="synthetic/fixed", run_id="run", worker_id="owner"
    )
    context._runtime_prepared = True
    graph = await backend.get_graph(context=context)
    result = await graph.ainvoke(
        {"messages": [HumanMessage(content="解释合成记录")]},
        config={"configurable": {"thread_id": context.thread_id}, "recursion_limit": 20},
        context=context,
    )
    assert result["messages"][-1].content == "合成记录解释，不是医疗建议"
    assert tool_lists and all(set(names) == set(service.HEALTH_TOOL_NAMES) for names in tool_lists)
    assert system_prompts and all(prompt == service.CONSULTATION_PROMPT for prompt in system_prompts)
    assert all("slug: family-nutritionist" in prompt and "## 咨询流程" in prompt for prompt in system_prompts)
    assert ownership.await_count == 4  # 构图一次、非法参数后修正调用，共三次模型轮次。
    assert any(message.type == "tool" and message.status == "error" for message in result["messages"])
    assert executor.await_args.args == (context, "report")

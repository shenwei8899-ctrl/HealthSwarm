"""指标专属Agent的固定工具、派生来源及公开答复门禁。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, call

import pytest
from sqlalchemy.dialects.postgresql import dialect

from yuxi.agents.buildin.health_blood_glucose.graph import HealthBloodGlucoseAgent
from yuxi.agents.buildin.health_blood_lipids.graph import HealthBloodLipidsAgent
from yuxi.agents.buildin.health_blood_pressure.graph import HealthBloodPressureAgent
from yuxi.agents.buildin.health_consultation import graph as graph_module
from yuxi.repositories.conversation_repository import ConversationRepository
from yuxi.repositories.health_blood_glucose_repository import HealthBloodGlucoseRepository
from yuxi.repositories.health_blood_lipids_repository import HealthBloodLipidsRepository
from yuxi.repositories.health_blood_pressure_repository import HealthBloodPressureRepository
from yuxi.repositories.health_consultation_repository import HealthConsultationRepository
from yuxi.repositories.health_family_profile_repository import HealthFamilyProfileRepository
from yuxi.repositories.health_weight_repository import HealthWeightRepository
from yuxi.services import agent_run_service, health_consultation_service, health_evidence_service
from yuxi.services.health_family_profile_service import validate_profile_publication
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.storage.postgres.models_health import HealthProcessingConsent

CASES = (
    ("health-blood-glucose", HealthBloodGlucoseAgent, "get_member_blood_glucose_records", "BLOOD_GLUCOSE_PROMPT"),
    ("health-blood-lipids", HealthBloodLipidsAgent, "get_member_blood_lipids_records", "BLOOD_LIPIDS_PROMPT"),
    ("health-blood-pressure", HealthBloodPressureAgent, "get_member_blood_pressure_records", "BLOOD_PRESSURE_PROMPT"),
)


def test_all_health_indicator_agents_use_the_health_worker_deadline():
    """新角色不能落入没有健康执行预算的普通Worker路径。"""
    from yuxi.services.run_worker import HEALTH_EXECUTION_AGENT_SLUGS

    assert {"health-blood-glucose", "health-blood-lipids", "health-blood-pressure"} <= HEALTH_EXECUTION_AGENT_SLUGS


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["foreign", "relative", "no_profile_scope"])
async def test_indicator_member_gate_requires_profile_scope_and_self_identity(monkeypatch, case):
    """有AI或管理员身份也不能进入他人指标助手；档案权限撤回仍拒绝。"""
    member = SimpleNamespace(owner_uid="actor", relationship_label="本人")
    if case == "foreign":
        member.owner_uid = "other"
    elif case == "relative":
        member.relationship_label = "父亲"
    authorize = AsyncMock(return_value=member)
    if case == "no_profile_scope":
        authorize.side_effect = [member, HealthVisionError("forbidden", "合成档案授权已撤回", 403)]
    monkeypatch.setattr(health_consultation_service.HealthVisionRepository, "authorize", authorize)
    with pytest.raises(HealthVisionError) as failure:
        await HealthConsultationRepository(object()).authorize_indicator_member("actor", "member", lock=True)
    assert failure.value.status == (403 if case == "no_profile_scope" else 404)
    assert authorize.await_args_list == [
        call("member", "actor", "ai_use", lock=True),
        call("member", "actor", "profile_view"),
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("slug,agent_class,record_tool,prompt_name", CASES)
async def test_actual_graph_ignores_user_tool_and_prompt_overrides(
    monkeypatch, slug, agent_class, record_tool, prompt_name
):
    """专属后端只装配两工具及发布prompt，个人覆盖不能扩大模型可见范围。"""
    context = SimpleNamespace(
        _runtime_prepared=True,
        model="synthetic/fixed",
        thread_id="thread",
        tools=["remember_member_fact", "get_complete_health_profile"],
        system_prompt="forged instructions",
    )
    guard = AsyncMock()
    monkeypatch.setattr(health_consultation_service, "require_consultation_attempt", guard)
    monkeypatch.setattr(health_consultation_service, prompt_name, f"published {slug}", raising=False)
    monkeypatch.setattr(graph_module.model_cache, "get_model_info", Mock(return_value={"model": "fixed"}))
    monkeypatch.setattr(graph_module, "load_chat_model", Mock(return_value="model"))
    monkeypatch.setattr(graph_module.HealthConsultationAgent, "_get_checkpointer", AsyncMock(return_value="PG"))
    assemble = Mock(return_value="compiled graph")
    monkeypatch.setattr(graph_module, "create_agent", assemble)

    assert await agent_class().get_graph(context=context) == "compiled graph"
    graph = assemble.call_args.kwargs
    assert [tool.name for tool in graph["tools"]] == [
        record_tool,
        "query_reviewed_nutrition_knowledge",
        "query_family_nutrition_knowledge",
        "finalize_health_answer",
    ]
    assert graph["system_prompt"] == f"published {slug}" and graph["checkpointer"] == "PG"
    assert [type(item).__name__ for item in graph["middleware"]] == [
        "SteerMiddleware",
        "HealthAuthorizationMiddleware",
        "HealthCatalogMiddleware",
        "HealthAiBudgetMiddleware",
        "HealthCitationMiddleware",
        "HealthFinalAnswerMiddleware",
        "TokenUsageMiddleware",
    ]
    guard.assert_awaited_once_with(context)


@pytest.mark.asyncio
@pytest.mark.parametrize("slug,agent_class,record_tool,prompt_name", CASES)
async def test_actual_graph_rejects_unprepared_or_unauthorized_attempt(
    monkeypatch, slug, agent_class, record_tool, prompt_name
):
    """审批或Worker所有权拒绝时不装配模型。"""
    assemble = Mock()
    monkeypatch.setattr(graph_module, "create_agent", assemble)
    context = SimpleNamespace(_runtime_prepared=False)
    with pytest.raises(ValueError, match="Context"):
        await agent_class().get_graph(context=context)
    context._runtime_prepared = True
    monkeypatch.setattr(
        health_consultation_service,
        "require_consultation_attempt",
        AsyncMock(side_effect=HealthVisionError("execution_not_owned", "合成执行拒绝", 409)),
    )
    with pytest.raises(HealthVisionError, match="execution_not_owned"):
        await agent_class().get_graph(context=context)
    assemble.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "slug,source_repository,source_code",
    [
        ("health-blood-glucose", HealthBloodGlucoseRepository, "blood_glucose_source_changed"),
        ("health-blood-lipids", HealthBloodLipidsRepository, "blood_lipids_source_changed"),
        ("health-blood-pressure", HealthBloodPressureRepository, "blood_pressure_source_changed"),
    ],
)
async def test_derived_specialist_answer_rechecks_source_without_another_tool_read(
    monkeypatch, slug, source_repository, source_code
):
    """来源失效阻止旧线程派生回答、完成发布和公开正文。"""
    binding = SimpleNamespace(member_id="member", actor_uid="actor", conversation_id=7)
    conversation = SimpleNamespace(agent_id=slug)

    async def get(model, identity, **kwargs):
        """提供当前会话及有效的咨询用途同意。"""
        if model is HealthProcessingConsent:
            return SimpleNamespace(revoked_at=None)
        return conversation

    session = SimpleNamespace(
        scalar=AsyncMock(
            side_effect=lambda query: binding if "FROM health_consultation JOIN conversations" in str(query) else None
        ),
        get=AsyncMock(side_effect=get),
    )
    monkeypatch.setattr(HealthConsultationRepository, "validate_personal_target_runs", AsyncMock())
    monkeypatch.setattr(
        health_consultation_service.HealthVisionRepository,
        "authorize",
        AsyncMock(return_value=SimpleNamespace(owner_uid="actor", relationship_label="本人")),
    )
    for repository in (
        HealthFamilyProfileRepository,
        HealthWeightRepository,
        HealthBloodGlucoseRepository,
        HealthBloodLipidsRepository,
        HealthBloodPressureRepository,
    ):
        monkeypatch.setattr(repository, "validate_history", AsyncMock())
    source_guard = AsyncMock(side_effect=HealthVisionError(source_code, "合成记录已更正", 410))
    monkeypatch.setattr(source_repository, "validate_history", source_guard)
    repo = HealthConsultationRepository(session)
    with pytest.raises(HealthVisionError, match=source_code):
        await repo.authorize("actor", "thread")

    async def require(current_session, uid, thread_id, model_spec=None, *, expected, lock=False):
        """只隔离审批查询，保留真实来源授权路径。"""
        return await HealthConsultationRepository(current_session).authorize(uid, thread_id, lock=lock), expected

    monkeypatch.setattr(health_consultation_service, "require_consultation", require)
    run = SimpleNamespace(
        id="run",
        uid="actor",
        agent_slug=slug,
        status="completed",
        conversation_id=7,
        conversation_thread_id="thread",
        input_payload={"health_processing": {"processor": "approved"}},
    )
    with pytest.raises(HealthVisionError, match=source_code):
        await validate_profile_publication(session, run)
    final = AsyncMock()
    monkeypatch.setattr(health_evidence_service.HealthEvidenceRepository, "final_answer", final)
    with pytest.raises(HealthVisionError, match=source_code):
        await health_evidence_service.read_public_consultation_answer(session, run, "actor")
    final.assert_not_awaited()
    assert source_guard.await_args.kwargs["lock"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize("slug,agent_class,record_tool,prompt_name", CASES)
async def test_generic_result_for_specialist_uses_current_public_answer_gate(
    monkeypatch, slug, agent_class, record_tool, prompt_name
):
    """通用Run结果接口不能旁路新角色的来源与引用校验。"""
    from fastapi import HTTPException

    run = SimpleNamespace(id="run", agent_slug=slug, status="completed")
    monkeypatch.setattr(
        agent_run_service,
        "AgentRunRepository",
        lambda _: SimpleNamespace(get_run_for_user=AsyncMock(return_value=run)),
    )
    monkeypatch.setattr(
        health_evidence_service,
        "read_public_consultation_answer",
        AsyncMock(side_effect=HealthVisionError("source_invalidated", "合成来源撤回", 410)),
    )
    with pytest.raises(HTTPException) as failure:
        await agent_run_service.get_agent_run_result(run_id="run", current_uid="actor", db=object())
    assert failure.value.status_code == 410 and failure.value.detail["code"] == "source_invalidated"


@pytest.mark.asyncio
@pytest.mark.parametrize("agent_id", [None, "health-blood-glucose", "health-blood-lipids", "health-blood-pressure"])
async def test_search_candidate_query_filters_one_requested_role_or_all_education_roles(agent_id):
    """指定专属角色搜索不混入其他指标，全部搜索纳入四类受控候选。"""

    class Rows:
        """仅承接真实SQL构造的空异步流。"""

        def __aiter__(self):
            return self

        async def __anext__(self):
            raise StopAsyncIteration

        async def close(self):
            pass

    session = SimpleNamespace(stream=AsyncMock(return_value=Rows()))
    assert [
        item
        async for item in ConversationRepository(session).iter_consultation_search_matches(
            uid="actor",
            query="合成",
            agent_id=agent_id,
        )
    ] == []
    statement = session.stream.await_args.args[0].compile(dialect=dialect())
    expected = (
        {"health-consultation", "health-blood-glucose", "health-blood-lipids", "health-blood-pressure"}
        if agent_id is None
        else {agent_id}
    )
    assert expected in [
        set(value) for value in statement.params.values() if isinstance(value, (list, tuple, frozenset))
    ]
    assert "conversations.uid =" in str(statement) and "actor" in statement.params.values()


@pytest.fixture(autouse=True)
def no_unrelated_catalog_history(monkeypatch):
    """本模块只验证指标/引证，商品审计由独立用例覆盖。"""
    from unittest.mock import AsyncMock
    from yuxi.repositories.conversation_purchase_repository import ConversationPurchaseRepository

    monkeypatch.setattr(ConversationPurchaseRepository, "catalog_profile_payloads", AsyncMock(return_value=[]))

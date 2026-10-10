"""最终答复引用的读取边界、顺序及权威指针验证。"""

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from yuxi.repositories import health_evidence_repository as repository_module
from yuxi.repositories.health_evidence_repository import HealthEvidenceRepository
from yuxi.services import health_evidence_service as service
from yuxi.services.health_evidence_types import NutritionCitationsResult
from yuxi.services.health_vision_types import HealthVisionError

FIRST = "11111111-1111-1111-1111-111111111111"
SECOND = "22222222-2222-2222-2222-222222222222"
THREAD = "33333333-3333-3333-3333-333333333333"
MEMBER = "44444444-4444-4444-4444-444444444444"


def test_citation_ids_preserve_first_use_order_and_do_not_invent_sources():
    """最终正文引用顺序独立于数据库或检索顺序。"""
    assert service.answer_citation_ids(f"乙[证据:{SECOND}] 甲[证据:{FIRST}] 重复[证据:{SECOND}]") == [
        SECOND,
        FIRST,
    ]
    assert service.answer_citation_ids("当前没有足够的审核依据。") == []


@pytest.mark.parametrize("text", [None, [], "[证据:forged]", "[证据:" + "-" * 36 + "]", "[证据:" + FIRST])
def test_citation_ids_reject_invalid_text_or_markers(text):
    """非法标记不能被悄悄遗漏为无引用。"""
    with pytest.raises(HealthVisionError):
        service.answer_citation_ids(text)


@pytest.mark.asyncio
async def test_read_returns_only_actual_final_citations_after_current_authorization(monkeypatch):
    """检索过的第三条片段不进入回答引用接口；已完成读取不依赖lease。"""
    run = SimpleNamespace(
        id="run",
        agent_slug="health-consultation",
        status="completed",
        request_id="request",
        conversation_thread_id=THREAD,
        conversation_id=7,
    )
    binding = SimpleNamespace(conversation_id=7, actor_uid="actor", member_id=MEMBER)
    answer = SimpleNamespace(id=12, content=f"乙[证据:{SECOND}] 甲[证据:{FIRST}] 重复[证据:{SECOND}]")
    current = {
        FIRST: {"citation_id": FIRST, "title": "甲"},
        SECOND: {"citation_id": SECOND, "title": "乙"},
    }
    run_repository = SimpleNamespace(get_run_for_user=AsyncMock(return_value=run))
    binding_repository = SimpleNamespace(authorize=AsyncMock(return_value=binding))
    evidence_repository = SimpleNamespace(
        final_answer=AsyncMock(return_value=answer), validate_citations=AsyncMock(return_value=current)
    )

    @asynccontextmanager
    async def session_context():
        yield "session"

    monkeypatch.setattr(service.pg_manager, "get_async_session_context", session_context)
    monkeypatch.setattr(service, "AgentRunRepository", lambda _: run_repository)
    monkeypatch.setattr(service, "HealthConsultationRepository", lambda _: binding_repository)
    monkeypatch.setattr(service, "HealthEvidenceRepository", lambda _: evidence_repository)
    result = await service.read_consultation_citations("actor", "run")
    assert result == {
        "result_type": "nutrition_citations",
        "status": "cited",
        "agent_run_id": "run",
        "request_id": "request",
        "thread_id": THREAD,
        "member_id": MEMBER,
        "final_message_id": 12,
        "citations": [{"citation_id": SECOND, "title": "乙"}, {"citation_id": FIRST, "title": "甲"}],
    }
    binding_repository.authorize.assert_awaited_once_with("actor", THREAD, lock=True, preview_history=True)
    evidence_repository.validate_citations.assert_awaited_once_with([SECOND, FIRST], binding, "actor", run_id="run")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case,code",
    [
        ("missing", "not_found"),
        ("planner", "not_found"),
        ("pending", "answer_not_completed"),
        ("actor", "not_found"),
        ("conversation", "not_found"),
    ],
)
async def test_read_rejects_scope_or_execution_before_loading_answer(monkeypatch, case, code):
    """授权或完成条件不满足时不读取正文及证据。"""
    run = SimpleNamespace(
        id="run", agent_slug="health-consultation", status="completed", conversation_thread_id=THREAD, conversation_id=7
    )
    binding = SimpleNamespace(conversation_id=7, actor_uid="actor", member_id=MEMBER)
    if case == "missing":
        run = None
    elif case == "planner":
        run.agent_slug = "health-meal-planner"
    elif case == "pending":
        run.status = "pending"
    elif case == "actor":
        binding.actor_uid = "other"
    else:
        binding.conversation_id = 8

    @asynccontextmanager
    async def session_context():
        yield "session"

    monkeypatch.setattr(service.pg_manager, "get_async_session_context", session_context)
    monkeypatch.setattr(
        service, "AgentRunRepository", lambda _: SimpleNamespace(get_run_for_user=AsyncMock(return_value=run))
    )
    monkeypatch.setattr(
        service, "HealthConsultationRepository", lambda _: SimpleNamespace(authorize=AsyncMock(return_value=binding))
    )
    monkeypatch.setattr(service, "HealthEvidenceRepository", lambda _: pytest.fail("无权查询不得加载最终正文"))
    with pytest.raises(HealthVisionError) as error:
        await service.read_consultation_citations("actor", "run")
    assert error.value.code == code


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["pointer", "conversation", "missing", "audit", "delivery", "request"])
async def test_final_answer_requires_pointer_and_regular_complete_same_request(monkeypatch, case):
    """同Run最后一条审计或邻请求消息不能充当权威答复。"""
    run = SimpleNamespace(id="run", conversation_id=7, output_message_id=12, request_id="request")
    run.uid, run.conversation_thread_id = "actor", THREAD
    session = SimpleNamespace(
        get=AsyncMock(return_value=SimpleNamespace(uid="actor", thread_id=THREAD, agent_id="health-consultation"))
    )
    answer = SimpleNamespace(message_type="text", delivery_status="complete", request_id="request")
    if case == "pointer":
        run.output_message_id = None
    elif case == "conversation":
        run.conversation_id = None
    elif case == "missing":
        answer = None
    elif case == "audit":
        answer.message_type = "model_audit"
    elif case == "delivery":
        answer.delivery_status = "error"
    else:
        answer.request_id = "other"
    output = SimpleNamespace(get_output_message=AsyncMock(return_value=answer))
    monkeypatch.setattr(repository_module, "AgentRunOutputRepository", lambda _: output)
    with pytest.raises(HealthVisionError, match="answer_unavailable"):
        await HealthEvidenceRepository(session).final_answer(run)
    if case in {"pointer", "conversation"}:
        output.get_output_message.assert_not_called()


@pytest.mark.asyncio
async def test_final_answer_accepts_only_exact_pointer_without_legacy_fallback(monkeypatch):
    """权威消息读取不能退到该线程或同Run最新消息。"""
    run = SimpleNamespace(
        id="run",
        uid="actor",
        conversation_id=7,
        conversation_thread_id=THREAD,
        output_message_id=12,
        request_id="request",
    )
    session = SimpleNamespace(
        get=AsyncMock(return_value=SimpleNamespace(uid="actor", thread_id=THREAD, agent_id="health-consultation"))
    )
    answer = SimpleNamespace(message_type="text", delivery_status="complete", request_id="request")
    output = SimpleNamespace(get_output_message=AsyncMock(return_value=answer))
    monkeypatch.setattr(repository_module, "AgentRunOutputRepository", lambda _: output)
    assert await HealthEvidenceRepository(session).final_answer(run) is answer
    output.get_output_message.assert_awaited_once_with(
        run_id="run", conversation_id=7, output_message_id=12, allow_legacy_fallback=False
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("field,value", [("uid", "other"), ("thread_id", "other"), ("agent_id", "health-meal-planner")])
async def test_final_answer_rejects_changed_conversation_identity(field, value):
    """仅修改Run的角色或线程快照不能冒充不同专属会话。"""
    run = SimpleNamespace(
        id="run",
        uid="actor",
        conversation_id=7,
        conversation_thread_id=THREAD,
        output_message_id=12,
        request_id="request",
    )
    conversation = SimpleNamespace(uid="actor", thread_id=THREAD, agent_id="health-consultation")
    setattr(conversation, field, value)
    with pytest.raises(HealthVisionError, match="not_found"):
        await HealthEvidenceRepository(SimpleNamespace(get=AsyncMock(return_value=conversation))).final_answer(run)


@pytest.mark.parametrize(
    "removed",
    [
        "get_member_weight_records",
        "get_member_blood_pressure_records",
        "get_member_blood_glucose_records",
        "get_member_blood_lipids_records",
    ],
)
def test_current_nutritionist_replay_rejects_missing_newly_registered_tool(removed):
    """11工具的显式oracle必须拒绝缺少任一正式记录工具。"""
    from test.support.health_consultation_replay_server import validate_request
    from test.unit.services.test_health_consultation_replay import AUTH, replay_body

    body = replay_body()
    assert validate_request(AUTH, body)[3] is False
    body["tools"] = [tool for tool in body["tools"] if tool["function"]["name"] != removed]
    with pytest.raises(ValueError, match="unexpected_tool_set"):
        validate_request(AUTH, body)


def test_public_result_schema_excludes_answer_audit_and_private_identity():
    """协议只有结果绑定和引用集合，额外健康正文不能进入响应模型。"""
    data = {
        "status": "not_cited",
        "agent_run_id": "run",
        "request_id": "request",
        "thread_id": THREAD,
        "member_id": MEMBER,
        "final_message_id": 12,
        "citations": [],
    }
    result = NutritionCitationsResult.model_validate(data)
    assert result.model_dump(mode="json") == {"result_type": "nutrition_citations", **data}
    for field in ("output", "actor_uid", "tool_audit", "model_input"):
        with pytest.raises(ValidationError):
            NutritionCitationsResult.model_validate({**data, field: "private"})

"""最终正文读取不提升用途、不猜旧指针、不检查未采用回执。"""

import inspect
import os
import textwrap
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import HTTPException
from langchain_core.messages import AIMessage, HumanMessage
from sqlalchemy.dialects.postgresql import dialect

from yuxi.repositories.conversation_repository import ConversationRepository
from yuxi.services import agent_run_service, chat_service, conversation_service, health_evidence_service as evidence
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.utils.datetime_utils import utc_now_naive

pytestmark = pytest.mark.asyncio
REFERENCE = "11111111-1111-1111-1111-111111111111"


@pytest.fixture(autouse=True)
def controlled_read_mutation(monkeypatch):
    """只在测试进程副本移除最终来源读取gate，失效正文断言必须变红。"""
    mode = os.getenv("HEALTH_EVIDENCE_MUTATION")
    if mode == "read_gate":
        owner, attribute = evidence, "read_public_consultation_answer"
        original = evidence.read_public_consultation_answer
        old = "await repo.validate_citations(ids, binding, uid, run_id=run.id, lock=True)"
        replacements = [(old, "pass")]
    elif mode == "history_projection":
        owner, attribute = ConversationRepository, "list_agent_runs_for_history"
        original = ConversationRepository.list_agent_runs_for_history
        replacements = [
            (f"AgentRun.{field},", "")
            for field in ("uid", "agent_slug", "conversation_id", "conversation_thread_id", "output_message_id")
        ]
    elif mode == "search_projection":
        owner, attribute = conversation_service, "search_threads_view"
        original = conversation_service.search_threads_view
        replacements = [
            (
                '"workdir_path": await resolve_conversation_workdir_path'
                "(conversation=conv, uid=str(current_uid), db=db),",
                "",
            )
        ]
    else:
        return
    source = textwrap.dedent(inspect.getsource(original))
    for old, new in replacements:
        assert source.count(old) == 1
        source = source.replace(old, new)

    async def mutated(*args, **kwargs):
        scope = dict(original.__globals__)
        exec(compile(source, "<controlled_evidence_read_mutation>", "exec"), scope)
        return await scope[original.__name__](*args, **kwargs)

    monkeypatch.setattr(owner, attribute, mutated)


def run_and_binding():
    """独立声明当前运行与绑定，正文来自专属 final Answer Owner。"""
    run = SimpleNamespace(
        id="current-run",
        uid="actor",
        agent_slug="health-consultation",
        status="completed",
        conversation_id=7,
        conversation_thread_id="thread",
        output_message_id=42,
        request_id="current-request",
        error_type=None,
        error_message=None,
    )
    binding = SimpleNamespace(conversation_id=7, actor_uid="actor", member_id="member")
    return run, binding


@pytest.mark.parametrize("case", ["other_actor", "other_role", "pending", "wrong_binding"])
async def test_public_read_rejects_wrong_run_scope_before_body(monkeypatch, case):
    run, binding = run_and_binding()
    if case == "other_actor":
        run.uid = "foreign"
    elif case == "other_role":
        run.agent_slug = "health-meal-planner"
    elif case == "pending":
        run.status = "pending"
    else:
        binding.conversation_id = 8
    final = AsyncMock()
    monkeypatch.setattr(evidence.HealthEvidenceRepository, "final_answer", final)
    with pytest.raises(HealthVisionError):
        await evidence.read_public_consultation_answer(object(), run, "actor", binding=binding)
    final.assert_not_awaited()


@pytest.mark.parametrize("content", ["请补充问题", f"合成科普[证据:{REFERENCE}][证据:{REFERENCE}]"])
async def test_read_validates_only_actual_final_refs_without_processing_or_retrieval_query(monkeypatch, content):
    run, binding = run_and_binding()
    answer = SimpleNamespace(id=42, content=content)
    final = AsyncMock(return_value=answer)
    proof = AsyncMock()
    session = SimpleNamespace(scalar=AsyncMock(side_effect=AssertionError("不得查询未采用检索回执")))
    monkeypatch.setattr(evidence.HealthEvidenceRepository, "final_answer", final)
    monkeypatch.setattr(evidence.HealthEvidenceRepository, "validate_citations", proof)
    assert await evidence.read_public_consultation_answer(session, run, "actor", binding=binding) is answer
    proof.assert_awaited_once_with(
        [REFERENCE] if "[证据:" in content else [], binding, "actor", run_id=run.id, lock=True
    )
    session.scalar.assert_not_awaited()


async def test_generic_result_converts_source_error_to_controlled_http_without_body(monkeypatch):
    run, _ = run_and_binding()
    monkeypatch.setattr(
        agent_run_service,
        "AgentRunRepository",
        lambda db: SimpleNamespace(get_run_for_user=AsyncMock(return_value=run)),
    )
    monkeypatch.setattr(
        evidence,
        "read_public_consultation_answer",
        AsyncMock(side_effect=HealthVisionError("source_invalidated", "请重新咨询", 410)),
    )
    with pytest.raises(HTTPException) as rejected:
        await agent_run_service.get_agent_run_result(run_id=run.id, current_uid="actor", db=object())
    assert rejected.value.status_code == 410
    assert rejected.value.detail == {"code": "source_invalidated", "message": "请重新咨询"}


@pytest.mark.parametrize("case", ["no_pointer", "foreign_pointer", "invalid_source", "private_audit", "tool_candidate"])
async def test_history_hides_only_unpublic_answer(monkeypatch, case):
    run, _ = run_and_binding()
    message = SimpleNamespace(id=42, conversation_id=7, run_id=run.id, role="assistant", message_type="text")
    if case == "no_pointer":
        run.output_message_id = None
    elif case == "foreign_pointer":
        run.output_message_id = 43
    elif case == "private_audit":
        message.message_type = "model_audit"
    elif case == "tool_candidate":
        message.role = "tool"
    proof = AsyncMock(side_effect=HealthVisionError("source_invalidated", "请重新咨询", 410))
    monkeypatch.setattr(evidence, "read_public_consultation_answer", proof)
    assert not await conversation_service._consultation_message_is_public(object(), message, "actor", run=run)
    assert proof.await_count == int(case == "invalid_source")


async def test_public_read_refuses_revoked_final_source_instead_of_returning_stored_body(monkeypatch):
    """有正确最终指针也不能公开当前已撤回的证据正文。"""
    run, binding = run_and_binding()
    answer = SimpleNamespace(id=42, content=f"不应公开的旧正文[证据:{REFERENCE}]")
    monkeypatch.setattr(evidence.HealthEvidenceRepository, "final_answer", AsyncMock(return_value=answer))
    proof = AsyncMock(side_effect=HealthVisionError("source_invalidated", "请重新咨询", 410))
    monkeypatch.setattr(evidence.HealthEvidenceRepository, "validate_citations", proof)
    with pytest.raises(HealthVisionError, match="source_invalidated"):
        await evidence.read_public_consultation_answer(object(), run, "actor", binding=binding)
    proof.assert_awaited_once_with([REFERENCE], binding, "actor", run_id=run.id, lock=True)


async def test_read_without_binding_rechecks_history_authorization_without_model_consent(monkeypatch):
    """历史读取复验成员授权，而不重新授权一次模型外呼。"""
    run, binding = run_and_binding()
    authorize = AsyncMock(return_value=binding)
    monkeypatch.setattr(evidence.HealthConsultationRepository, "authorize", authorize)
    answer = SimpleNamespace(id=42, content="不含检索的补充问题")
    monkeypatch.setattr(evidence.HealthEvidenceRepository, "final_answer", AsyncMock(return_value=answer))
    proof = AsyncMock()
    monkeypatch.setattr(evidence.HealthEvidenceRepository, "validate_citations", proof)
    assert await evidence.read_public_consultation_answer(object(), run, "actor") is answer
    authorize.assert_awaited_once_with("actor", "thread", lock=True, preview_history=True)
    proof.assert_awaited_once_with([], binding, "actor", run_id=run.id, lock=True)


async def test_generic_result_keeps_legacy_output_without_consultation_gate(monkeypatch):
    """普通Agent继续使用既有最终输出仓库及legacy兼容。"""
    run, _ = run_and_binding()
    run.agent_slug = "ordinary-agent"
    output = SimpleNamespace(id=42, content="普通Agent最终正文", extra_metadata={})
    read = AsyncMock(return_value=output)
    monkeypatch.setattr(
        agent_run_service,
        "AgentRunRepository",
        lambda db: SimpleNamespace(get_run_for_user=AsyncMock(return_value=run)),
    )
    monkeypatch.setattr(
        agent_run_service, "AgentRunOutputRepository", lambda db: SimpleNamespace(get_output_message=read)
    )
    gate = AsyncMock(side_effect=AssertionError("普通结果不得增加咨询发布门槛"))
    monkeypatch.setattr(evidence, "read_public_consultation_answer", gate)
    result = await agent_run_service.get_agent_run_result(run_id=run.id, current_uid="actor", db=object())
    assert result["output"] == output.content and result["final_message_id"] == 42
    read.assert_awaited_once_with(run_id=run.id, conversation_id=7, output_message_id=42, allow_legacy_fallback=True)
    gate.assert_not_awaited()


async def test_generic_state_keeps_checkpoint_messages_without_health_history_projection(monkeypatch):
    """普通chat/state消息继续来自原checkpoint，并保留模型历史形状。"""
    conv = SimpleNamespace(uid="actor", id=7, thread_id="thread", agent_id="ordinary-agent", status="active")
    monkeypatch.setattr(
        chat_service,
        "ConversationRepository",
        lambda db: SimpleNamespace(get_conversation_by_thread_id=AsyncMock(return_value=conv)),
    )
    monkeypatch.setattr(
        chat_service,
        "AgentRunRepository",
        lambda db: SimpleNamespace(get_latest_run_by_thread_for_user=AsyncMock(return_value=None)),
    )
    monkeypatch.setattr(chat_service, "resolve_conversation_workdir_path", AsyncMock(return_value="projects/synthetic"))
    monkeypatch.setattr(chat_service, "runtime_workdir_path", lambda value: value)
    values = {
        "messages": [HumanMessage(content="普通输入", id="human"), AIMessage(content="普通checkpoint正文", id="ai")]
    }
    checkpoint = AsyncMock(return_value=(values, None))
    monkeypatch.setattr(chat_service, "_read_checkpoint_state", checkpoint)
    history = AsyncMock(side_effect=AssertionError("普通state不得改成健康History"))
    monkeypatch.setattr(conversation_service, "get_thread_history_view", history)
    result = await chat_service.get_agent_state_view(
        thread_id="thread",
        current_user=SimpleNamespace(uid="actor"),
        db=object(),
        include_messages=True,
        include_relations=False,
    )
    assert [(message["id"], message["type"], message["content"]) for message in result["messages"]] == [
        ("human", "human", "普通输入"),
        ("ai", "ai", "普通checkpoint正文"),
    ]
    assert all(
        message["additional_kwargs"] == {} and message["response_metadata"] == {} for message in result["messages"]
    )
    checkpoint.assert_awaited_once_with(uid="actor", thread_id="thread")
    history.assert_not_awaited()


async def test_generic_history_keeps_legacy_assistant_and_tool_messages(monkeypatch):
    """普通历史保留无Run旧正文及tool消息，不执行专属咨询来源校验。"""
    now = utc_now_naive()
    conv = SimpleNamespace(id=7, thread_id="thread", agent_id="ordinary-agent", last_viewed_run_id=None)
    messages = [
        SimpleNamespace(
            id=i,
            role=role,
            content=content,
            message_type="text",
            delivery_status="complete",
            run_id=None,
            request_id=None,
            created_at=now,
            feedbacks=[],
            extra_metadata={},
            operation_id=None,
            image_content=None,
            tool_calls=[],
        )
        for i, role, content in [(42, "assistant", "普通旧正文"), (43, "tool", "普通工具结果")]
    ]
    repo = SimpleNamespace(
        get_messages=AsyncMock(return_value=messages), list_agent_runs_for_history=AsyncMock(return_value=[])
    )
    monkeypatch.setattr(conversation_service, "ConversationRepository", lambda db: repo)
    authorize = AsyncMock(return_value=conv)
    monkeypatch.setattr(conversation_service, "require_user_conversation", authorize)
    monkeypatch.setattr(conversation_service, "_serialize_thread", AsyncMock(return_value={"id": "thread"}))
    gate = AsyncMock(side_effect=AssertionError("普通历史不得调用咨询来源gate"))
    monkeypatch.setattr(evidence, "read_public_consultation_answer", gate)
    result = await conversation_service.get_thread_history_view(thread_id="thread", current_uid="actor", db=object())
    assert [(message["id"], message["type"], message["content"]) for message in result["history"]] == [
        (42, "ai", "普通旧正文"),
        (43, "tool", "普通工具结果"),
    ]
    authorize.assert_awaited_once_with(repo, "thread", "actor")
    gate.assert_not_awaited()


async def test_generic_message_search_keeps_ordinary_snippets_and_count(monkeypatch):
    """普通搜索仍使用仓库命中计数，不新增逐消息健康读取。"""
    from server.routers.chat_router import ThreadSearchResponse

    now = utc_now_naive()
    conv = SimpleNamespace(
        id=7,
        thread_id="thread",
        uid="actor",
        agent_id="ordinary-agent",
        title="普通对话",
        is_pinned=False,
        created_at=now,
        updated_at=now,
        extra_metadata={},
    )
    search = AsyncMock(
        return_value=(
            [
                {
                    "conversation": conv,
                    "matched_count": 2,
                    "snippets": [{"message_id": 42, "content": "普通命中正文", "created_at": now}],
                }
            ],
            False,
        )
    )
    monkeypatch.setattr(
        conversation_service,
        "ConversationRepository",
        lambda db: SimpleNamespace(search_conversations_by_message_content=search),
    )
    workdir = AsyncMock(return_value="projects/11111111-1111-4111-8111-111111111111")
    monkeypatch.setattr(conversation_service, "resolve_conversation_workdir_path", workdir)
    db = SimpleNamespace(get=AsyncMock(side_effect=AssertionError("普通搜索不得追加逐条健康消息查询")))
    result = await conversation_service.search_threads_view(
        query=" 普通 ", agent_id="ordinary-agent", current_uid="actor", db=db
    )
    assert result["items"][0]["matched_count"] == 2
    assert result["items"][0]["snippets"][0]["content"] == "普通命中正文"
    assert "workdir_path" in result["items"][0], "普通搜索必须符合继承的ThreadResponse字段契约"
    response = ThreadSearchResponse.model_validate(result)
    assert response.items[0].workdir_path == "projects/11111111-1111-4111-8111-111111111111"
    workdir.assert_awaited_once_with(conversation=conv, uid="actor", db=db)
    assert search.await_args.kwargs["uid"] == "actor" and search.await_args.kwargs["query"] == "普通"
    db.get.assert_not_awaited()


async def test_history_run_projection_loads_authoritative_read_identity_and_pointer():
    """轻量历史Run必须含读取Owner需要的身份与最终指针，避免raiseload异常。"""
    rows = Mock()
    rows.scalars.return_value.all.return_value = []
    db = SimpleNamespace(execute=AsyncMock(return_value=rows))
    assert await ConversationRepository(db).list_agent_runs_for_history(7) == []
    sql = str(db.execute.await_args.args[0].compile(dialect=dialect()))
    projection = sql.partition("\nFROM ")[0]
    for field in ("uid", "agent_slug", "conversation_id", "conversation_thread_id", "output_message_id"):
        assert f"agent_runs.{field}" in projection, f"缺少历史读取所需的{field}"
    assert "agent_runs.input_payload" not in projection and "agent_runs.execution_manifest" not in projection

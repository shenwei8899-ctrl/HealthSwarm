"""真实 final-save 提交边界、来源共享锁与四个已完成正文入口。"""

import json
from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError

from test.e2e.test_health_consultation_e2e import isolated_health  # noqa: F401
from test.integration.services.test_health_evidence_lexical_http import publish
from test.integration.services.test_health_task_http import verified_task_cleanup  # noqa: F401
from test.integration.services.test_health_vision_http import ROOT, create_member, health_http  # noqa: F401
from yuxi.repositories.agent_run_repository import AgentRunRepository
from yuxi.repositories.agent_run_request_repository import AgentRunRequestRepository
from yuxi.repositories.conversation_repository import ConversationRepository
from yuxi.repositories.model_message_audit_repository import ModelMessageAuditRepository
from yuxi.services.chat_service import save_messages_from_langgraph_state
from yuxi.services.health_consultation_service import require_consultation
from yuxi.services.health_evidence_service import (
    search_nutrition_evidence,
    validate_evidence_publication,
    validate_nutrition_answer,
)
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_business import AUDIT_MESSAGE_TYPES, AgentRun, Message
from yuxi.storage.postgres.models_health import NutritionEvidence, NutritionEvidenceCitation
from yuxi.utils.datetime_utils import utc_now_naive

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def binding_for(client, users, configuration):
    """真实成员、当前 local-only 用途同意与正式咨询绑定。"""
    headers = users[0]["headers"]
    member = await create_member(client, headers)
    consent = await client.post(
        f"{ROOT}/members/{member}/processing-consents",
        headers=headers,
        json={
            "purpose": "consultation",
            "accepted": True,
            "processor": configuration["consultation"]["processor"],
            "policy_version": configuration["policy_version"],
        },
    )
    assert consent.status_code == 200, consent.text
    key = str(uuid4())
    bound = await client.post(
        f"{ROOT}/members/{member}/consultations",
        headers={**headers, "Idempotency-Key": key},
        json={"client_request_id": key},
    )
    assert bound.status_code == 201, bound.text
    return bound.json()["thread_id"]


async def owned_run(uid, thread, model):
    """真实 Request/Run/attempt Owner；不投递 ARQ，也不创建 execution runtime。"""
    run_id, request_id = str(uuid4()), str(uuid4())
    worker = f"synthetic-evidence-publication-{uuid4()}"
    async with pg_manager.get_async_session_context() as session:
        binding, snapshot = await require_consultation(session, uid, thread, model)
        conv = ConversationRepository(session)
        message = await conv.add_message_by_thread_id(
            thread, role="user", content="合成科普请求", request_id=request_id, run_id=None, commit=False
        )
        payload = {"health_processing": snapshot}
        request = await AgentRunRequestRepository(session).create(
            request_id=request_id,
            uid=uid,
            agent_slug="health-consultation",
            conversation_thread_id=thread,
            input_message_id=message.id,
            input_payload=payload,
            status="dispatched",
        )
        repo = AgentRunRepository(session)
        await repo.create_run(
            run_id=run_id,
            uid=uid,
            agent_slug="health-consultation",
            conversation_thread_id=thread,
            request_id=request_id,
            conversation_id=binding.conversation_id,
            input_message_id=message.id,
            input_payload=payload,
        )
        run, claimed = await repo.mark_running(run_id, worker_id=worker, lease_seconds=180)
        assert claimed and run.status == "running"
        request.dispatched_run_id, request.dispatched_at = run_id, utc_now_naive()
        message.run_id = run_id
    return SimpleNamespace(
        uid=uid, thread_id=thread, run_id=run_id, request_id=request_id, worker_id=worker, model=model
    )


async def answer_state(context, query, *, unused_query=None):
    """真实检索回执、图 validator 与已持久化的私有 Model lifecycle。"""
    result = await search_nutrition_evidence(context, query)
    assert len(result["citations"]) == 1
    if unused_query:
        unused = await search_nutrition_evidence(context, unused_query)
        assert len(unused["citations"]) == 1
    answer = f"公开合成正文 {query} [证据:{result['citations'][0]['citation_id']}]"
    operation = str(uuid4())
    messages = [
        HumanMessage(content="合成问题"),
        ToolMessage(
            name="query_reviewed_nutrition_knowledge", content=json.dumps(result), tool_call_id="synthetic-tool"
        ),
        AIMessage(content=answer, id=operation),
    ]
    await validate_nutrition_answer(context, answer, messages)
    async with pg_manager.get_async_session_context() as session:
        audit = ModelMessageAuditRepository(session)
        facts = dict(
            run_id=context.run_id,
            request_id=context.request_id,
            thread_id=context.thread_id,
            worker_id=context.worker_id,
            operation_id=operation,
        )
        await audit.start(**facts, sequence=0, started_at=utc_now_naive())
        message = await audit.finish(**facts, content=answer, finished_at=utc_now_naive(), duration_ms=1, usage={})
        audit_id = message.id
    return SimpleNamespace(values={"messages": messages}), answer, result["citations"][0], audit_id


async def save_actual(session, context, state):
    """调用 production owning final-save，禁止测试手写 Message/pointer/completed。"""
    return await save_messages_from_langgraph_state(
        state,
        context.thread_id,
        ConversationRepository(session),
        run_id=context.run_id,
        request_id=context.request_id,
        worker_id=context.worker_id,
        complete_run=True,
    )


async def close_synthetic_run(context):
    """只清理本fixture从未投递/创建runtime的Owner事实，不冒充Worker回执。"""
    async with pg_manager.get_async_session_context() as session:
        run = await session.get(AgentRun, context.run_id)
        if run.status not in {"completed", "failed", "cancelled", "interrupted"}:
            await AgentRunRepository(session).set_terminal_status(
                context.run_id, status="failed", worker_id=context.worker_id, error_type="synthetic_fixture_cleanup"
            )
        run.runtime_cleanup_pending = False


@pytest.mark.parametrize("mutation", ["revoke", "expire", "body", "foreign_run"])
async def test_graph_validated_answer_cannot_publish_after_source_change(isolated_health, mutation):  # noqa: F811
    """独立图校验通过后变更来源，真实finalsave必须rollback而保留私有审计。"""
    client, users, configuration, model = isolated_health
    token = uuid4().hex
    source, _ = await publish(client, users[2]["headers"], token, "first")
    thread = await binding_for(client, users, configuration)
    context = await owned_run(users[0]["uid"], thread, model)
    other = None
    try:
        state, answer, citation, audit_id = await answer_state(context, f"lexical{token} first")
        async with pg_manager.get_async_session_context() as owning:
            old_source = await owning.get(NutritionEvidence, source)
            assert old_source.revoked_at is None
            async with pg_manager.get_async_session_context() as concurrent:
                if mutation == "foreign_run":
                    other_thread = await binding_for(client, users, configuration)
                    other = await owned_run(users[0]["uid"], other_thread, model)
                    (await concurrent.get(NutritionEvidenceCitation, citation["citation_id"])).run_id = other.run_id
                else:
                    row = await concurrent.get(NutritionEvidence, source)
                    if mutation == "revoke":
                        row.revoked_at = utc_now_naive()
                    elif mutation == "expire":
                        row.valid_until = utc_now_naive() - timedelta(seconds=1)
                    else:
                        row.content = "未审核的不同正文"
            with pytest.raises(HealthVisionError) as rejected:
                await save_actual(owning, context, state)
            assert rejected.value.code == ("citation_invalid" if mutation == "foreign_run" else "source_invalidated")
        async with pg_manager.get_async_session_context() as read:
            run = await read.get(AgentRun, context.run_id)
            assert run.status == "running" and run.output_message_id is None
            ordinary = await read.scalars(
                select(Message).where(
                    Message.run_id == run.id,
                    Message.role == "assistant",
                    Message.message_type.notin_(AUDIT_MESSAGE_TYPES),
                )
            )
            assert list(ordinary) == []
            audit = await read.get(Message, audit_id)
            assert (
                audit.content == answer
                and audit.message_type == "model_audit"
                and audit.execution_status == "completed"
            )
    finally:
        await close_synthetic_run(context)
        if other:
            await close_synthetic_run(other)


@pytest.mark.parametrize("mutation", ["revoke", "expire", "body", "foreign_citation"])
async def test_completed_four_body_reads_only_guard_actual_adopted_sources(isolated_health, mutation):  # noqa: F811
    """同线程A/B最终正文独立；未采用C不误封A，B失效不泄正文也不封A。"""
    client, users, configuration, model = isolated_health
    headers, admin = users[0]["headers"], users[2]["headers"]
    token = uuid4().hex
    sources = {}
    for key in ("first", "second", "unused"):
        sources[key], _ = await publish(client, admin, token, key)
    thread = await binding_for(client, users, configuration)
    contexts = []
    try:
        first = await owned_run(users[0]["uid"], thread, model)
        contexts.append(first)
        first_state, answer_a, citation_a, _ = await answer_state(
            first, f"lexical{token} first", unused_query=f"lexical{token} unused"
        )
        async with pg_manager.get_async_session_context() as session:
            assert await save_actual(session, first, first_state) is True
        await close_synthetic_run(first)
        second = await owned_run(users[0]["uid"], thread, model)
        contexts.append(second)
        second_state, answer_b, _, _ = await answer_state(second, f"lexical{token} second")
        answer_b_prefix = answer_b.split("[证据:")[0].strip()
        async with pg_manager.get_async_session_context() as session:
            assert await save_actual(session, second, second_state) is True
        await close_synthetic_run(second)
        async with pg_manager.get_async_session_context() as session:
            pointers = {
                context.run_id: (await session.get(AgentRun, context.run_id)).output_message_id for context in contexts
            }
            assert all(pointers.values()) and len(set(pointers.values())) == 2

        async def read_paths(context, *, status=200, expected=None):
            """真实 generic、citations、Task 三个不同路由，确认专用错误不被改404。"""
            for path in (
                f"/api/agent/runs/{context.run_id}/result",
                f"{ROOT}/consultation-runs/{context.run_id}/citations",
                f"{ROOT}/tasks/{context.request_id}",
            ):
                response = await client.get(path, headers=headers)
                assert response.status_code == status, (path, response.text)
                if status != 200:
                    assert answer_b_prefix not in response.text and "未审核" not in response.text
                elif expected is not None and "/citations" not in path:
                    assert expected in response.text, (path, response.text)

        async def projections(contains_b):
            """三个线程正文投影，B失效时保留A而不原样返回checkpoint候选。"""
            history = await client.get(f"/api/chat/thread/{thread}/history", headers=headers)
            state = await client.get(
                f"/api/chat/thread/{thread}/state",
                headers=headers,
                params={"include_messages": "true", "include_relations": "false"},
            )
            search = await client.get(
                "/api/chat/threads/search", headers=headers, params={"q": token, "agent_id": "health-consultation"}
            )
            for response in (history, state, search):
                assert response.status_code == 200, (str(response.request.url), response.text)
                assert answer_a in response.text
                assert (answer_b in response.text) is contains_b
                if not contains_b:
                    assert answer_b_prefix not in response.text
                assert "未审核" not in response.text
            visible = search.json()["items"]
            assert len(visible) == 1 and visible[0]["matched_count"] == (2 if contains_b else 1)
            assert visible[0]["message_id"] in {row["message_id"] for row in visible[0]["snippets"]}
            default = await client.get(f"/api/chat/thread/{thread}/state", headers=headers)
            assert default.status_code == 200 and "messages" not in default.json()

        await read_paths(first, expected=answer_a)
        await read_paths(second, expected=answer_b)
        await projections(True)
        revoked_unused = await client.delete(f"{ROOT}/nutrition-evidence/{sources['unused']}", headers=admin)
        assert revoked_unused.status_code == 200
        await read_paths(first, expected=answer_a)
        await read_paths(second, expected=answer_b)
        await projections(True)
        if mutation == "revoke":
            revoked = await client.delete(f"{ROOT}/nutrition-evidence/{sources['second']}", headers=admin)
            assert revoked.status_code == 200
        else:
            async with pg_manager.get_async_session_context() as session:
                if mutation == "foreign_citation":
                    (
                        await session.get(Message, pointers[second.run_id])
                    ).content = f"{answer_b.split('[证据:')[0]}[证据:{citation_a['citation_id']}]"
                else:
                    source = await session.get(NutritionEvidence, sources["second"])
                    if mutation == "expire":
                        source.valid_until = utc_now_naive() - timedelta(seconds=1)
                    else:
                        source.content = "未审核不同正文"
        await read_paths(first, expected=answer_a)
        await read_paths(second, status=409 if mutation == "foreign_citation" else 410)
        await projections(False)
        async with pg_manager.get_async_session_context() as session:
            for context in contexts:
                run = await session.get(AgentRun, context.run_id)
                assert run.status == "completed" and run.output_message_id == pointers[run.id]
    finally:
        for context in contexts:
            await close_synthetic_run(context)


async def test_publication_share_lock_blocks_admin_update_until_actual_commit(isolated_health):  # noqa: F811
    """真实锁的NOWAIT负控，不用会挂死测试的阻塞DELETE。"""
    client, users, configuration, model = isolated_health
    token = uuid4().hex
    source, _ = await publish(client, users[2]["headers"], token, "first")
    thread = await binding_for(client, users, configuration)
    context = await owned_run(users[0]["uid"], thread, model)
    try:
        state, answer, _, _ = await answer_state(context, f"lexical{token} first")
        async with pg_manager.get_async_session_context() as owning:
            run = await owning.get(AgentRun, context.run_id)
            await validate_evidence_publication(owning, run, answer)
            async with pg_manager.get_async_session_context() as concurrent:
                with pytest.raises(DBAPIError) as blocked:
                    await concurrent.scalar(
                        select(NutritionEvidence).where(NutritionEvidence.id == source).with_for_update(nowait=True)
                    )
                assert "55P03" == getattr(blocked.value.orig, "sqlstate", None)
                await concurrent.rollback()
            assert await save_actual(owning, context, state) is True
        async with pg_manager.get_async_session_context() as concurrent:
            assert await concurrent.scalar(
                select(NutritionEvidence).where(NutritionEvidence.id == source).with_for_update(nowait=True)
            )
    finally:
        await close_synthetic_run(context)

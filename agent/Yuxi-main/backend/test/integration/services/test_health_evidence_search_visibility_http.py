"""真实已发布咨询的搜索计数、摘要和公开线程分页。"""

from uuid import uuid4

import pytest

from test.e2e.test_health_consultation_e2e import isolated_health  # noqa: F401
from test.integration.services.test_health_evidence_final_publication_http import (
    answer_state,
    binding_for,
    close_synthetic_run,
    owned_run,
    save_actual,
)
from test.integration.services.test_health_evidence_lexical_http import publish
from test.integration.services.test_health_task_http import verified_task_cleanup  # noqa: F401
from test.integration.services.test_health_vision_http import ROOT, health_http  # noqa: F401
from yuxi.repositories.conversation_repository import MESSAGE_SEARCH_SNIPPETS_PER_THREAD, ConversationRepository
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_business import AgentRun, Message
from yuxi.utils.datetime_utils import format_utc_datetime

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def complete_four(isolated, token, threads, contexts):
    """四条来源经真实图校验及 owning final-save，各自持久化权威指针。"""
    client, users, _, model = isolated
    results = []
    for index, thread in enumerate(threads):
        key = f"source{index}"
        source, _ = await publish(client, users[2]["headers"], token, key)
        context = await owned_run(users[0]["uid"], thread, model)
        contexts.append(context)
        state, answer, _, _ = await answer_state(context, f"lexical{token} {key}")
        async with pg_manager.get_async_session_context() as session:
            assert await save_actual(session, context, state) is True
        await close_synthetic_run(context)
        async with pg_manager.get_async_session_context() as session:
            run = await session.get(AgentRun, context.run_id)
            assert run.status == "completed" and run.output_message_id
            message = await session.get(Message, run.output_message_id)
            assert message.content == answer and message.run_id == run.id and message.request_id == context.request_id
            results.append(
                {"source": source, "message": message.id, "answer": answer, "created_at": message.created_at}
            )
    assert len({row["message"] for row in results}) == 4
    return results


async def search(client, headers, token, *, agent_id="health-consultation", limit=20, offset=0):
    """真实 ResponseDTO 与正文，空白或私有命中不作为有效线程。"""
    params = {"q": token, "limit": limit, "offset": offset}
    if agent_id is not None:
        params["agent_id"] = agent_id
    response = await client.get("/api/chat/threads/search", headers=headers, params=params)
    assert response.status_code == 200, response.text
    return response.json()


async def test_search_counts_all_four_before_snippet_limit_and_retains_old_valid_answer(isolated_health):  # noqa: F811
    """最新三条失效不能吞最早有效回答；四条有效的count不能压成摘要数。"""
    client, users, configuration, _ = isolated_health
    token, contexts = uuid4().hex, []
    thread = await binding_for(client, users, configuration)
    try:
        rows = await complete_four(isolated_health, token, [thread] * 4, contexts)
        for agent_id in ("health-consultation", None):
            visible = await search(client, users[0]["headers"], token, agent_id=agent_id)
            assert len(visible["items"]) == 1 and visible["has_more"] is False
            item = visible["items"][0]
            assert item["thread_id"] == thread and item["matched_count"] == 4
            assert [snippet["message_id"] for snippet in item["snippets"]] == [
                row["message"] for row in reversed(rows[-MESSAGE_SEARCH_SNIPPETS_PER_THREAD:])
            ]
            assert len(item["snippets"]) == MESSAGE_SEARCH_SNIPPETS_PER_THREAD <= 3
            assert item["message_id"] == rows[-1]["message"]
        for row in rows[1:]:
            assert (
                await client.delete(f"{ROOT}/nutrition-evidence/{row['source']}", headers=users[2]["headers"])
            ).status_code == 200
        for agent_id in ("health-consultation", None):
            visible = await search(client, users[0]["headers"], token, agent_id=agent_id, limit=1)
            item = visible["items"][0]
            assert item["thread_id"] == thread and item["matched_count"] == 1
            assert item["message_id"] == rows[0]["message"] and visible["has_more"] is False
            assert item["latest_match_at"] == format_utc_datetime(rows[0]["created_at"])
            assert [snippet["message_id"] for snippet in item["snippets"]] == [rows[0]["message"]]
            assert rows[0]["answer"] in str(item)
            for invalid in rows[1:]:
                assert invalid["answer"].split("[证据:")[0].strip() not in str(visible)
        assert (
            await client.delete(f"{ROOT}/nutrition-evidence/{rows[0]['source']}", headers=users[2]["headers"])
        ).status_code == 200
        empty = await search(client, users[0]["headers"], token, limit=1)
        assert empty["items"] == [] and empty["has_more"] is False
    finally:
        for context in contexts:
            await close_synthetic_run(context)


async def test_search_paginates_visible_threads_after_removing_all_invalid_latest_thread(isolated_health):  # noqa: F811
    """较新的全失效线程不占page；offset和has_more依据当前公开匹配。"""
    client, users, configuration, _ = isolated_health
    token, contexts = uuid4().hex, []
    threads = [await binding_for(client, users, configuration) for _ in range(3)]
    try:
        rows = await complete_four(isolated_health, token, [threads[0], threads[1], threads[2], threads[2]], contexts)
        for row in rows[2:]:
            assert (
                await client.delete(f"{ROOT}/nutrition-evidence/{row['source']}", headers=users[2]["headers"])
            ).status_code == 200
        for agent_id in ("health-consultation", None):
            first = await search(client, users[0]["headers"], token, agent_id=agent_id, limit=1)
            second = await search(client, users[0]["headers"], token, agent_id=agent_id, limit=1, offset=1)
            end = await search(client, users[0]["headers"], token, agent_id=agent_id, limit=1, offset=2)
            assert [item["thread_id"] for item in first["items"]] == [threads[1]] and first["has_more"] is True
            assert [item["thread_id"] for item in second["items"]] == [threads[0]] and second["has_more"] is False
            assert end["items"] == [] and end["has_more"] is False
            assert first["items"][0]["matched_count"] == second["items"][0]["matched_count"] == 1
            assert first["items"][0]["message_id"] == rows[1]["message"]
            assert second["items"][0]["message_id"] == rows[0]["message"]
        denied = await search(client, users[1]["headers"], token)
        assert denied["items"] == [] and denied["has_more"] is False
        async with pg_manager.get_async_session_context() as session:
            for context, row in zip(contexts, rows, strict=True):
                run = await session.get(AgentRun, context.run_id)
                assert run.status == "completed" and run.output_message_id == row["message"]
    finally:
        for context in contexts:
            await close_synthetic_run(context)


async def test_unfiltered_search_merges_public_consultation_with_ordinary_real_count(isolated_health):  # noqa: F811
    """普通线程保留完整计数和有限摘要，跨角色页按实际最新公开匹配排序。"""
    client, users, configuration, _ = isolated_health
    token, contexts = uuid4().hex, []
    thread = await binding_for(client, users, configuration)
    try:
        rows = await complete_four(isolated_health, token, [thread] * 4, contexts)
        created = await client.post(
            "/api/chat/thread",
            headers=users[0]["headers"],
            json={"agent_id": "default-chatbot", "title": "合成普通搜索"},
        )
        assert created.status_code == 200, created.text
        ordinary_thread = created.json()["id"]
        async with pg_manager.get_async_session_context() as session:
            repo = ConversationRepository(session)
            for index in range(4):
                await repo.add_message_by_thread_id(
                    ordinary_thread, role="user", content=f"普通合成匹配 {token} {index}", commit=False
                )
        for row in rows[1:]:
            assert (
                await client.delete(f"{ROOT}/nutrition-evidence/{row['source']}", headers=users[2]["headers"])
            ).status_code == 200
        first = await search(client, users[0]["headers"], token, agent_id=None, limit=1)
        second = await search(client, users[0]["headers"], token, agent_id=None, limit=1, offset=1)
        assert first["has_more"] is True and first["items"][0]["thread_id"] == ordinary_thread
        assert first["items"][0]["matched_count"] == 4
        assert len(first["items"][0]["snippets"]) == MESSAGE_SEARCH_SNIPPETS_PER_THREAD
        assert second["has_more"] is False and second["items"][0]["thread_id"] == thread
        assert second["items"][0]["matched_count"] == 1
        explicit = await search(client, users[0]["headers"], token, agent_id="default-chatbot", limit=1)
        assert explicit["items"] == first["items"] and explicit["has_more"] is False
    finally:
        for context in contexts:
            await close_synthetic_run(context)

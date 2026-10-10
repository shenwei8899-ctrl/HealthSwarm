"""咨询搜索先判断当前可公开性，再计数、截摘要和跨线程分页。"""

import inspect
import os
import textwrap
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import HTTPException
from sqlalchemy.dialects.postgresql import dialect

from yuxi.repositories.conversation_repository import ConversationRepository
from yuxi.services import conversation_service as service
from yuxi.utils.datetime_utils import format_utc_datetime

pytestmark = pytest.mark.asyncio
EPOCH = datetime(2026, 10, 10, 0, 0)
WORKDIR = "projects/11111111-1111-4111-8111-111111111111"


@pytest.fixture(autouse=True)
def controlled_search_mutation(monkeypatch):
    """只变异测试进程的函数副本；生产源码与其它进程保持原样。"""
    mode = os.getenv("HEALTH_SEARCH_VISIBILITY_MUTATION")
    repo_modes = {
        "candidate_limit": (
            ".execution_options(yield_per=100, populate_existing=True)",
            ".limit(2).execution_options(yield_per=100, populate_existing=True)",
        ),
        "candidate_fresh": (
            ".execution_options(yield_per=100, populate_existing=True)",
            ".execution_options(yield_per=100)",
        ),
        "candidate_audit": ("*self._message_search_conditions(query),", ""),
        "candidate_scope": ("Conversation.uid == str(uid),", ""),
    }
    if mode in repo_modes:
        original = ConversationRepository.iter_consultation_search_matches
        source = textwrap.dedent(inspect.getsource(original))
        old, new = repo_modes[mode]
        assert source.count(old) == 1
        source = source.replace(old, new)

        async def mutated_rows(*args, **kwargs):
            scope = dict(original.__globals__)
            exec(compile(source, "<controlled_search_candidate_mutation>", "exec"), scope)
            rows = scope[original.__name__](*args, **kwargs)
            try:
                async for row in rows:
                    yield row
            finally:
                await rows.aclose()

        monkeypatch.setattr(ConversationRepository, "iter_consultation_search_matches", mutated_rows)
        return
    old_gate = (
        "if not authorized_threads[conversation.id] or not await _consultation_message_is_public(db, message, uid):"
    )
    replacements = {
        "raw_snippets": [
            ("consultation_items = {}", "consultation_items = {}\n    raw_counts = {}"),
            (
                old_gate,
                "raw_counts[conversation.id] = raw_counts.get(conversation.id, 0) + 1\n"
                "        if raw_counts[conversation.id] > 2:\n            continue\n        " + old_gate,
            ),
        ],
        "snippet_count": [('item["matched_count"] += 1', 'item["matched_count"] = min(2, item["matched_count"] + 1)')],
        "raw_pagination": [
            ("consultation_items = {}", "consultation_items = {}\n    raw_threads = set()"),
            (
                old_gate,
                "raw_threads.add(conversation.id)\n"
                "        if len(raw_threads) > page_end:\n            continue\n        " + old_gate,
            ),
        ],
        "raw_latest": [
            ("consultation_items = {}", "consultation_items = {}\n    raw_latest = {}"),
            (old_gate, "raw_latest.setdefault(conversation.id, message.created_at)\n        " + old_gate),
            ('"latest_match_at": message.created_at,', '"latest_match_at": raw_latest[conversation.id],'),
        ],
        "raw_has_more": [("len(visible_items) > offset + limit", "len(authorized_threads) > offset + limit")],
        "no_ordinary_refill": [("if not raw_has_more:", "if True:")],
        "public_gate": [(old_gate, "if not authorized_threads[conversation.id]:")],
    }.get(mode)
    if replacements is None:
        return
    original = service._search_with_public_consultations
    source = textwrap.dedent(inspect.getsource(original))
    for old, new in replacements:
        assert source.count(old) == 1
        source = source.replace(old, new)

    async def mutated(*args, **kwargs):
        # Fixture mocks must already be installed when copying the global scope.
        scope = dict(original.__globals__)
        exec(compile(source, "<controlled_public_search_mutation>", "exec"), scope)
        return await scope[original.__name__](*args, **kwargs)

    monkeypatch.setattr(service, "_search_with_public_consultations", mutated)


def conversation(number, *, agent_id="health-consultation", updated=1):
    return SimpleNamespace(
        id=number,
        thread_id=f"thread-{number}",
        uid="actor",
        agent_id=agent_id,
        title=f"合成线程{number}",
        is_pinned=False,
        created_at=EPOCH,
        updated_at=EPOCH + timedelta(minutes=updated),
        extra_metadata={},
    )


def message(number, minute, *, public=True):
    return SimpleNamespace(
        id=number,
        created_at=EPOCH + timedelta(minutes=minute),
        content=f"营养合成命中{number}",
        public=public,
    )


def ordinary_item(conv, minute, *, count=7):
    return {
        "conversation": conv,
        "matched_count": count,
        "latest_match_at": EPOCH + timedelta(minutes=minute),
        "message_id": conv.id * 100,
        "snippets": [
            {
                "message_id": conv.id * 100 + index,
                "content": f"普通营养{index}",
                "created_at": EPOCH + timedelta(minutes=minute - index),
            }
            for index in range(2)
        ],
    }


class SearchRepository:
    def __init__(self, rows=(), ordinary=()):
        self.rows = sorted(rows, key=lambda row: (row[1].created_at, row[1].id), reverse=True)
        self.ordinary = list(ordinary)
        self.iterator_calls = []
        self.search = AsyncMock(side_effect=self._search)

    async def iter_consultation_search_matches(self, **kwargs):
        self.iterator_calls.append(kwargs)
        for row in self.rows:
            yield row

    async def _search(self, **kwargs):
        offset, limit = kwargs["offset"], kwargs["limit"]
        return self.ordinary[offset : offset + limit], len(self.ordinary) > offset + limit

    async def search_conversations_by_message_content(self, **kwargs):
        return await self.search(**kwargs)

    def _build_message_search_snippet(self, content, query):
        return ConversationRepository(object())._build_message_search_snippet(content, query)


def install_search(monkeypatch, rows=(), ordinary=(), *, denied=()):
    repo = SearchRepository(rows, ordinary)
    monkeypatch.setattr(service, "ConversationRepository", lambda db: repo)

    async def authorize(repository, thread_id, uid):
        assert repository is repo and uid == "actor"
        if thread_id in denied:
            raise HTTPException(404, "不可访问的合成线程")

    auth = AsyncMock(side_effect=authorize)
    public = AsyncMock(side_effect=lambda db, row, uid: row.public)
    monkeypatch.setattr(service, "require_user_conversation", auth)
    monkeypatch.setattr(service, "_consultation_message_is_public", public)
    monkeypatch.setattr(service, "resolve_conversation_workdir_path", AsyncMock(return_value=WORKDIR))
    return repo, auth, public


async def search(*, agent_id="health-consultation", limit=20, offset=0):
    return await service.search_threads_view(
        query=" 营养 ", agent_id=agent_id, db=object(), current_uid="actor", limit=limit, offset=offset
    )


async def test_four_latest_invalid_answers_do_not_hide_oldest_public_match(monkeypatch):
    conv = conversation(1)
    rows = [(conv, message(index, index, public=index == 1)) for index in range(1, 6)]
    repo, auth, public = install_search(monkeypatch, rows)
    result = await search()
    assert [item["thread_id"] for item in result["items"]] == ["thread-1"]
    item = result["items"][0]
    assert item["matched_count"] == 1 and item["message_id"] == 1
    assert [snippet["message_id"] for snippet in item["snippets"]] == [1]
    assert item["latest_match_at"] == format_utc_datetime(EPOCH + timedelta(minutes=1))
    assert result["has_more"] is False
    assert public.await_count == 5 and auth.await_count == 1
    assert repo.iterator_calls == [
        {"uid": "actor", "query": "营养", "exclude_sources": ("agent_call", "agent_evaluation")}
    ]
    repo.search.assert_not_awaited()


async def test_four_public_matches_count_all_with_only_two_latest_snippets(monkeypatch):
    conv = conversation(1)
    install_search(monkeypatch, [(conv, message(index, index)) for index in range(1, 5)])
    result = await search()
    item = result["items"][0]
    assert item["matched_count"] == 4
    assert [snippet["message_id"] for snippet in item["snippets"]] == [4, 3]
    assert item["message_id"] == 4 and result["has_more"] is False


@pytest.mark.parametrize(
    ("offset", "expected", "has_more"), [(0, ["thread-10"], True), (1, ["thread-11"], False), (2, [], False)]
)
async def test_public_pagination_skips_newer_invisible_threads(monkeypatch, offset, expected, has_more):
    rows = [(conversation(index), message(index, 100 + index, public=False)) for index in range(1, 5)]
    rows.extend([(conversation(10), message(10, 20)), (conversation(11), message(11, 10))])
    install_search(monkeypatch, rows)
    result = await search(limit=1, offset=offset)
    assert [item["thread_id"] for item in result["items"]] == expected
    assert result["has_more"] is has_more and result["offset"] == offset and result["limit"] == 1


async def test_invisible_thread_count_does_not_inflate_has_more(monkeypatch):
    rows = [(conversation(index), message(index, 100 + index, public=False)) for index in range(1, 5)]
    rows.append((conversation(10), message(10, 20)))
    install_search(monkeypatch, rows)
    result = await search(limit=1)
    assert [item["thread_id"] for item in result["items"]] == ["thread-10"]
    assert result["has_more"] is False


async def test_mixed_search_sorts_public_time_and_preserves_ordinary_count(monkeypatch):
    from server.routers.chat_router import ThreadSearchResponse

    older, newer = conversation(1), conversation(2)
    ordinary = ordinary_item(conversation(3, agent_id="ordinary-agent"), 50)
    rows = [(older, message(100, 100, public=False)), (older, message(20, 20)), (newer, message(40, 40))]
    repo, _, _ = install_search(monkeypatch, rows, [ordinary])
    result = await search(agent_id=None, limit=2)
    assert [item["thread_id"] for item in result["items"]] == ["thread-3", "thread-2"]
    assert result["has_more"] is True
    assert result["items"][0]["matched_count"] == 7
    assert len(result["items"][0]["snippets"]) == 2
    response = ThreadSearchResponse.model_validate(result)
    assert all(item.workdir_path == WORKDIR for item in response.items)
    assert repo.search.await_args.kwargs["exclude_agent_ids"] == ("health-consultation",)


async def test_denied_threads_are_not_counted_or_checked_for_publication(monkeypatch):
    conv = conversation(1)
    _, auth, public = install_search(
        monkeypatch, [(conv, message(index, index)) for index in range(1, 5)], denied={"thread-1"}
    )
    result = await search(limit=1)
    assert result["items"] == [] and result["has_more"] is False
    auth.assert_awaited_once()
    public.assert_not_awaited()


async def test_mixed_search_refills_after_fifty_unauthorized_health_threads(monkeypatch):
    rejected = [
        ordinary_item(conversation(index, agent_id="health-meal-planner"), 200 - index) for index in range(1, 51)
    ]
    accepted = ordinary_item(conversation(51, agent_id="ordinary-agent"), 1)
    repo, _, public = install_search(
        monkeypatch, ordinary=[*rejected, accepted], denied={f"thread-{index}" for index in range(1, 51)}
    )
    result = await search(agent_id=None, limit=1)
    assert [item["thread_id"] for item in result["items"]] == ["thread-51"]
    assert result["items"][0]["matched_count"] == 7 and result["has_more"] is False
    assert [call.kwargs["offset"] for call in repo.search.await_args_list] == [0, 50]
    assert all(call.kwargs["limit"] == 50 for call in repo.search.await_args_list)
    public.assert_not_awaited()


async def test_explicit_ordinary_search_retains_original_repository_pagination(monkeypatch):
    ordinary = ordinary_item(conversation(7, agent_id="ordinary-agent"), 7, count=12)
    repo, auth, public = install_search(monkeypatch, ordinary=[ordinary])
    result = await search(agent_id="ordinary-agent", limit=1)
    assert result["items"][0]["matched_count"] == 12 and result["has_more"] is False
    assert repo.search.await_args.kwargs == {
        "uid": "actor",
        "agent_id": "ordinary-agent",
        "query": "营养",
        "limit": 1,
        "offset": 0,
        "exclude_sources": ("agent_call", "agent_evaluation"),
    }
    assert not repo.iterator_calls
    auth.assert_not_awaited()
    public.assert_not_awaited()


class StreamingRows:
    def __init__(self, rows):
        self.rows = iter(rows)
        self.close = AsyncMock()

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self.rows)
        except StopIteration:
            raise StopAsyncIteration from None


async def test_candidate_stream_has_current_uid_active_fixed_role_audit_filter_fresh_and_no_limit():
    rows = StreamingRows([(conversation(1), message(1, 1))])
    db = SimpleNamespace(stream=AsyncMock(return_value=rows))
    found = [
        row
        async for row in ConversationRepository(db).iter_consultation_search_matches(
            uid="actor", query="营养%_", exclude_sources=("agent_call", "agent_evaluation")
        )
    ]
    assert len(found) == 1
    statement = db.stream.await_args.args[0]
    compiled = statement.compile(dialect=dialect())
    sql, values = str(compiled), list(compiled.params.values())
    assert " LIMIT " not in sql.upper() and " OFFSET " not in sql.upper()
    assert "conversations.uid =" in sql and "actor" in values
    assert "conversations.status =" in sql and "active" in values
    assert "conversations.agent_id =" in sql and "health-consultation" in values
    assert "messages.role IN" in sql and {"user", "assistant"} in [
        set(value) for value in values if isinstance(value, (list, tuple))
    ]
    assert "messages.message_type NOT IN" in sql
    assert {"tool_call", "tool_result", "model_audit", "tool_audit"} in [
        set(value) for value in values if isinstance(value, (list, tuple))
    ]
    assert "%营养\\%\\_%" in values and "ILIKE" in sql
    assert {"agent_call", "agent_evaluation"} in [set(value) for value in values if isinstance(value, (list, tuple))]
    assert statement.get_execution_options().get("populate_existing") is True
    assert statement.get_execution_options().get("yield_per") == 100
    rows.close.assert_awaited_once()


async def test_candidate_stream_closes_when_consumer_stops_early():
    rows = StreamingRows([(conversation(1), message(1, 1)), (conversation(2), message(2, 2))])
    db = SimpleNamespace(stream=AsyncMock(return_value=rows))
    candidates = ConversationRepository(db).iter_consultation_search_matches(uid="actor", query="营养")
    assert (await anext(candidates))[0].id == 1
    await candidates.aclose()
    rows.close.assert_awaited_once()


@pytest.mark.parametrize("exclude", [(), ("health-consultation",)])
async def test_ordinary_repository_exclusion_is_opt_in_and_keeps_legacy_default(exclude):
    result = Mock()
    result.all.return_value = []
    db = SimpleNamespace(execute=AsyncMock(return_value=result))
    found, more = await ConversationRepository(db).search_conversations_by_message_content(
        uid="actor", query="营养", exclude_agent_ids=exclude
    )
    assert found == [] and more is False
    statement = db.execute.await_args.args[0]
    sql = str(statement.compile(dialect=dialect()))
    assert ("conversations.agent_id NOT IN" in sql) is bool(exclude)
    assert " LIMIT " in sql.upper() and " OFFSET " in sql.upper()

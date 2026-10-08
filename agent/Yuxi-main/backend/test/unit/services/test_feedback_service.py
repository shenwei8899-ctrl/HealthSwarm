from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from yuxi.services import feedback_service as svc


class _FakeResult:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class _FakeSession:
    def __init__(self, results):
        self.results = list(results)
        self.added = []
        self.committed = False
        self.rolled_back = False

    async def execute(self, _query):
        return _FakeResult(self.results.pop(0))

    def add(self, item):
        self.added.append(item)

    async def commit(self):
        self.committed = True

    async def refresh(self, item):
        item.id = 9
        item.created_at = datetime(2026, 1, 2, 3, 4, 5)

    async def rollback(self):
        self.rolled_back = True


@pytest.mark.asyncio
async def test_submit_message_feedback_syncs_langfuse_score(monkeypatch: pytest.MonkeyPatch):
    message = SimpleNamespace(
        id=3,
        conversation_id=7,
        extra_metadata={"langfuse_trace_id": "trace-1"},
    )
    conversation = SimpleNamespace(id=7, uid="user-1", agent_id="default")
    db = _FakeSession([message, conversation, None])
    calls = []

    monkeypatch.setattr(svc, "submit_user_feedback_score", lambda **kwargs: calls.append(kwargs) or True)

    result = await svc.submit_message_feedback_view(
        message_id=3,
        rating="like",
        reason=None,
        db=db,
        current_uid="user-1",
    )

    assert result == {
        "id": 9,
        "message_id": 3,
        "rating": "like",
        "reason": None,
        "created_at": "2026-01-02T03:04:05",
    }
    assert db.committed is True
    assert db.rolled_back is False
    assert calls == [
        {
            "trace_id": "trace-1",
            "feedback_id": 9,
            "message_id": 3,
            "conversation_id": 7,
            "uid": "user-1",
            "rating": "like",
            "reason": None,
        }
    ]


@pytest.mark.asyncio
async def test_submit_message_feedback_skips_langfuse_without_trace_id(monkeypatch: pytest.MonkeyPatch):
    message = SimpleNamespace(id=3, conversation_id=7, extra_metadata={})
    conversation = SimpleNamespace(id=7, uid="user-1", agent_id="default")
    db = _FakeSession([message, conversation, None])
    calls = []

    monkeypatch.setattr(svc, "submit_user_feedback_score", lambda **kwargs: calls.append(kwargs) or True)

    result = await svc.submit_message_feedback_view(
        message_id=3,
        rating="dislike",
        reason="不相关",
        db=db,
        current_uid="user-1",
    )

    assert result["rating"] == "dislike"
    assert result["reason"] == "不相关"
    assert calls == []


@pytest.mark.asyncio
async def test_health_feedback_rechecks_member_and_never_exports_reason_to_langfuse(monkeypatch):
    """健康反馈留在本地，已有 trace 也不能绕过咨询用途审批外发。"""
    message = SimpleNamespace(id=3, conversation_id=7, extra_metadata={"langfuse_trace_id": "synthetic-trace"})
    conversation = SimpleNamespace(id=7, uid="user-1", agent_id="health-consultation", thread_id="bound-thread")
    db = _FakeSession([message, conversation, None])
    authorize = AsyncMock(return_value=conversation)
    export = AsyncMock()
    monkeypatch.setattr(svc, "require_user_conversation", authorize)
    monkeypatch.setattr(svc, "submit_user_feedback_score", export)
    result = await svc.submit_message_feedback_view(
        message_id=3, rating="dislike", reason="synthetic-health-reason", db=db, current_uid="user-1"
    )
    assert result["reason"] == "synthetic-health-reason" and db.committed
    authorize.assert_awaited_once()
    assert authorize.await_args.args[1:] == ("bound-thread", "user-1")
    export.assert_not_called()

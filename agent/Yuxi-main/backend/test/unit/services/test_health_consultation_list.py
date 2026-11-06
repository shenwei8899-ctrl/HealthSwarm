"""成员咨询列表的授权顺序、最小投影和分页验证。"""

from contextlib import asynccontextmanager
from datetime import UTC, date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from yuxi.services import health_consultation_service as service
from yuxi.services.health_vision_types import HealthVisionError


@pytest.fixture
def list_dependencies(monkeypatch):
    """只替代持久化边界，保留真实授权流程和响应装配。"""

    @asynccontextmanager
    async def session_context():
        yield SimpleNamespace()

    authorize = AsyncMock()
    query = AsyncMock(return_value=[])
    cloud_configuration = AsyncMock(side_effect=AssertionError("元数据列表不应检查云处理配置"))
    active_consent = AsyncMock()
    history_validation = AsyncMock()
    threads = AsyncMock(return_value=[])
    first_questions = AsyncMock(return_value=[])
    monkeypatch.setattr(service.pg_manager, "get_async_session_context", session_context)
    monkeypatch.setattr(service.HealthVisionRepository, "authorize", authorize)
    monkeypatch.setattr(
        service.HealthConsultationRepository, "require_active_consultation_consent", active_consent, raising=False
    )
    monkeypatch.setattr(service.HealthConsultationRepository, "list_member_consultations", query)
    monkeypatch.setattr(service.HealthConsultationRepository, "authorize", history_validation)
    monkeypatch.setattr(service.HealthConsultationRepository, "conversation_threads", threads)
    monkeypatch.setattr(service.HealthConsultationRepository, "first_questions", first_questions)
    monkeypatch.setattr(service.health_vision_service, "configuration", cloud_configuration)
    return SimpleNamespace(
        authorize=authorize,
        active_consent=active_consent,
        query=query,
        cloud_configuration=cloud_configuration,
        history_validation=history_validation,
        threads=threads,
        first_questions=first_questions,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("row_count,has_more,next_offset", [(0, False, None), (2, False, None), (3, True, 5)])
async def test_list_projects_only_metadata_and_uses_extra_row(list_dependencies, row_count, has_more, next_offset):
    """分页仅公开当前授权线程的目录摘要，额外一行不参与标题读取。"""
    dependencies = list_dependencies
    created_at = datetime(2026, 10, 10, 1, 2, 3, tzinfo=UTC)
    rows = [(f"thread-{index}", date(2026, 10, 9) if index == 0 else None, created_at) for index in range(row_count)]
    dependencies.query.return_value = rows
    dependencies.threads.return_value = [
        (SimpleNamespace(id=index, thread_id=thread_id, extra_metadata={}), object())
        for index, (thread_id, _, _) in enumerate(rows[:2])
    ]

    result = await service.list_consultations("actor", "member", limit=2, offset=3)

    assert result == {
        "items": [
            {
                "thread_id": thread_id,
                "member_id": "member",
                "agent_slug": "health-consultation",
                "business_date": day.isoformat() if day is not None else None,
                "created_at": "2026-10-10T01:02:03Z",
                "title": "新对话",
                "unavailable": False,
            }
            for thread_id, day, _ in rows[:2]
        ],
        "has_more": has_more,
        "next_offset": next_offset,
    }
    assert [call.args for call in dependencies.authorize.await_args_list] == [
        ("member", "actor", "ai_use"),
    ]
    dependencies.query.assert_awaited_once_with("actor", "member", limit=2, offset=3)
    dependencies.active_consent.assert_not_awaited()
    dependencies.cloud_configuration.assert_not_awaited()
    if rows:
        dependencies.threads.assert_awaited_once_with("actor", [row[0] for row in rows[:2]])
        dependencies.first_questions.assert_awaited_once_with(list(range(min(row_count, 2))))
    else:
        dependencies.threads.assert_not_awaited()
        dependencies.first_questions.assert_not_awaited()
    assert [(call.args, call.kwargs) for call in dependencies.history_validation.await_args_list] == [
        (("actor", thread_id), {"preview_history": True}) for thread_id, _, _ in rows[:2]
    ]


@pytest.mark.asyncio
async def test_missing_member_scope_rejects_before_list_query(list_dependencies):
    """成员 AI 授权缺失或撤回时先拒绝，不读取目录或标题。"""
    dependencies = list_dependencies

    async def authorize_scope(member_id, uid, scope):
        if scope == "ai_use":
            raise HealthVisionError("not_found", "无权访问当前成员", 404)

    dependencies.authorize.side_effect = authorize_scope

    with pytest.raises(HealthVisionError) as denied:
        await service.list_consultations("actor", "member")

    assert denied.value.code == "not_found" and denied.value.status == 404
    dependencies.active_consent.assert_not_awaited()
    dependencies.query.assert_not_awaited()
    dependencies.threads.assert_not_awaited()
    dependencies.first_questions.assert_not_awaited()
    dependencies.history_validation.assert_not_awaited()


@pytest.mark.asyncio
async def test_legacy_processing_consent_does_not_block_directory_reads(list_dependencies):
    """目录按成员访问与逐线程来源校验，旧咨询同意记录不阻断读取。"""
    dependencies = list_dependencies
    dependencies.active_consent.side_effect = HealthVisionError("consent_required", "请先同意当前咨询用途", 403)
    dependencies.query.return_value = [("thread", None, datetime(2026, 10, 10, tzinfo=UTC))]
    dependencies.threads.return_value = [(SimpleNamespace(id=7, thread_id="thread", extra_metadata={}), object())]

    result = await service.list_consultations("actor", "member")

    assert result["items"][0]["unavailable"] is False
    dependencies.authorize.assert_awaited_once_with("member", "actor", "ai_use")
    dependencies.active_consent.assert_not_awaited()
    dependencies.query.assert_awaited_once_with("actor", "member", limit=20, offset=0)
    dependencies.threads.assert_awaited_once_with("actor", ["thread"])
    dependencies.first_questions.assert_awaited_once_with([7])
    dependencies.history_validation.assert_awaited_once_with("actor", "thread", preview_history=True)
    dependencies.cloud_configuration.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [403, 404, 409, 410])
async def test_unavailable_thread_keeps_page_without_reading_its_first_question(list_dependencies, status):
    """撤权或来源失效只保留不可用占位，不能借目录标题泄露首问。"""
    dependencies = list_dependencies
    now = datetime(2026, 10, 10, tzinfo=UTC)
    dependencies.query.return_value = [("revoked-thread", None, now), ("valid-thread", None, now)]
    dependencies.threads.return_value = [
        (SimpleNamespace(id=7, thread_id="revoked-thread", extra_metadata={}), object()),
        (SimpleNamespace(id=8, thread_id="valid-thread", extra_metadata={}), object()),
    ]

    async def authorize_history(uid, thread_id, *, preview_history):
        """失效线程拒绝读取，其他线程保留独立正控。"""
        assert uid == "actor" and preview_history is True
        if thread_id == "revoked-thread":
            raise HealthVisionError("source_invalidated" if status == 410 else "not_found", "不可访问", status)

    dependencies.history_validation.side_effect = authorize_history
    dependencies.first_questions.side_effect = lambda ids: [
        {
            "conversation_id": conversation_id,
            "content": "不得泄露的首问" if conversation_id == 7 else "有效首问",
            "has_image": False,
            "created_at": now,
            "id": conversation_id,
        }
        for conversation_id in ids
    ]

    result = await service.list_consultations("actor", "member")

    assert [(item["thread_id"], item["title"], item["unavailable"]) for item in result["items"]] == [
        ("revoked-thread", "该对话暂不可访问", True),
        ("valid-thread", "有效首问", False),
    ]
    assert result["has_more"] is False and result["next_offset"] is None
    dependencies.first_questions.assert_awaited_once_with([8])
    assert "不得泄露的首问" not in str(result)

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
    consent = AsyncMock(side_effect=AssertionError("元数据列表不应要求云处理同意"))
    history_validation = AsyncMock(side_effect=AssertionError("来源失效不应阻止列出咨询元数据"))
    monkeypatch.setattr(service.pg_manager, "get_async_session_context", session_context)
    monkeypatch.setattr(service.HealthVisionRepository, "authorize", authorize)
    monkeypatch.setattr(service.HealthVisionRepository, "require_consent", consent)
    monkeypatch.setattr(service.HealthConsultationRepository, "list_member_consultations", query)
    monkeypatch.setattr(service.HealthConsultationRepository, "authorize", history_validation)
    monkeypatch.setattr(service.health_vision_service, "configuration", cloud_configuration)
    return authorize, query, cloud_configuration, consent, history_validation


@pytest.mark.asyncio
@pytest.mark.parametrize("row_count,has_more,next_offset", [(0, False, None), (2, False, None), (3, True, 5)])
async def test_list_projects_only_metadata_and_uses_extra_row(list_dependencies, row_count, has_more, next_offset):
    """空页、末页和额外一行分页均不暴露正文，日期允许为空。"""
    authorize, query, cloud_configuration, consent, history_validation = list_dependencies
    created_at = datetime(2026, 10, 10, 1, 2, 3, tzinfo=UTC)
    rows = [(f"thread-{index}", date(2026, 10, 9) if index == 0 else None, created_at) for index in range(row_count)]
    query.return_value = rows

    result = await service.list_consultations("actor", "member", limit=2, offset=3)

    assert result == {
        "items": [
            {
                "thread_id": thread_id,
                "member_id": "member",
                "agent_slug": "health-consultation",
                "business_date": day.isoformat() if day is not None else None,
                "created_at": "2026-10-10T01:02:03Z",
            }
            for thread_id, day, _ in rows[:2]
        ],
        "has_more": has_more,
        "next_offset": next_offset,
    }
    assert [call.args for call in authorize.await_args_list] == [
        ("member", "actor", "ai_use"),
        ("member", "actor", "report_view"),
        ("member", "actor", "diet_edit"),
    ]
    query.assert_awaited_once_with("actor", "member", limit=2, offset=3)
    cloud_configuration.assert_not_awaited()
    consent.assert_not_awaited()
    history_validation.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("denied_scope", ["ai_use", "report_view", "diet_edit"])
async def test_missing_member_scope_rejects_before_list_query(list_dependencies, denied_scope):
    """任一当前成员授权缺失均先拒绝，不查询咨询元数据。"""
    authorize, query, _, _, _ = list_dependencies

    async def authorize_scope(member_id, uid, scope):
        if scope == denied_scope:
            raise HealthVisionError("not_found", "无权访问当前成员", 404)

    authorize.side_effect = authorize_scope

    with pytest.raises(HealthVisionError) as denied:
        await service.list_consultations("actor", "member")

    assert denied.value.code == "not_found" and denied.value.status == 404
    query.assert_not_awaited()

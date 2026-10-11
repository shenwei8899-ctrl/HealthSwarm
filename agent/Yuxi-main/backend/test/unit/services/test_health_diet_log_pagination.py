"""饮食分页的范围、来源与授权拒绝原因。"""

from contextlib import asynccontextmanager
import inspect
import os
import textwrap
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.dialects.postgresql import dialect

from yuxi.repositories.health_vision_repository import HealthVisionRepository
from yuxi.services.health_vision_service import HealthVisionService, pg_manager
from yuxi.services.health_vision_types import HealthVisionError


@pytest.mark.asyncio
@pytest.mark.parametrize("count,next_offset", [(0, None), (2, None), (3, 9)])
async def test_page_uses_raw_window_and_filters_invalid_sources(monkeypatch, count, next_offset):
    """空可见页仍按原始窗口继续，不让失效源快照流出。"""
    rows = [
        SimpleNamespace(id=str(i), confirmation_id=str(i), snapshot={"marker": i}, created_at=datetime(2026, 10, 11))
        for i in range(count)
    ]
    session = SimpleNamespace(get=AsyncMock(return_value=SimpleNamespace(draft_id="source", draft_version=3)))
    authorize = AsyncMock()
    query = AsyncMock(return_value=rows)
    draft = AsyncMock(side_effect=HealthVisionError("source_invalidated", "源文件已删除", 410))

    @asynccontextmanager
    async def database():
        """隔离投影逻辑，真实读写另由HTTP/PG验证。"""
        yield session

    monkeypatch.setattr(pg_manager, "get_async_session_context", database)
    monkeypatch.setattr(HealthVisionRepository, "authorize", authorize)
    monkeypatch.setattr(HealthVisionRepository, "list_records", query)
    monkeypatch.setattr(HealthVisionRepository, "draft", draft)
    result = await HealthVisionService().diet_log_page("actor", "member", limit=2, offset=7)
    assert result == {"records": [], "next_offset": next_offset}
    query.assert_awaited_once_with("member", "meal", limit=3, offset=7)
    authorize.assert_awaited_once_with("member", "actor", "diet_edit")
    assert draft.await_count == min(count, 2)


@pytest.mark.asyncio
async def test_revoked_page_rejects_before_any_record_read(monkeypatch):
    """去掉当前授权检查时，明确的404 oracle必须失败。"""
    query = AsyncMock()

    @asynccontextmanager
    async def database():
        """记录查询不应到达。"""
        yield SimpleNamespace()

    monkeypatch.setattr(pg_manager, "get_async_session_context", database)
    monkeypatch.setattr(
        HealthVisionRepository, "authorize", AsyncMock(side_effect=HealthVisionError("not_found", "无权访问", 404))
    )
    monkeypatch.setattr(HealthVisionRepository, "list_records", query)
    with pytest.raises(HealthVisionError) as rejected:
        await HealthVisionService().diet_log_page("actor", "member", offset=20)
    assert rejected.value.status == 404 and rejected.value.code == "not_found"
    query.assert_not_awaited()


@pytest.mark.asyncio
async def test_query_uses_member_scope_and_stable_order():
    """同时间记录以ID固定次序，不再限制最初100条。"""
    session = SimpleNamespace(scalars=AsyncMock(return_value=SimpleNamespace(all=lambda: [])))
    await HealthVisionRepository(session).list_records("member", "meal", limit=21, offset=120)
    compiled = session.scalars.await_args.args[0].compile(dialect=dialect())
    assert "WHERE diet_log.member_id =" in str(compiled)
    assert "ORDER BY diet_log.created_at DESC, diet_log.id ASC" in str(compiled)
    assert compiled.params == {"member_id_1": "member", "param_1": 21, "param_2": 120}


@pytest.fixture(autouse=True)
def controlled_pagination_mutation(monkeypatch):
    """仅变异测试进程函数副本，证明新边界在正确原因上变红。"""
    mode = os.getenv("HEALTH_DIET_PAGINATION_MUTATION")
    if not mode:
        return
    mutations = {
        "authorization": (
            HealthVisionService,
            "diet_log_page",
            'await repo.authorize(member_id, uid, "diet_edit")',
            "pass",
        ),
        "lookahead": (HealthVisionService, "diet_log_page", "limit=limit + 1", "limit=limit"),
        "source": (
            HealthVisionService,
            "_visible_records",
            "await repo.draft(confirmation.draft_id, uid, kind)",
            "pass",
        ),
        "offset": (HealthVisionRepository, "list_records", ".offset(offset)", ".offset(0)"),
        "order": (
            HealthVisionRepository,
            "list_records",
            "model.created_at.desc(), model.id.asc()",
            "model.created_at.desc()",
        ),
    }
    owner, name, old, new = mutations[mode]
    original = getattr(owner, name)
    source = textwrap.dedent(inspect.getsource(original))
    assert source.count(old) == 1
    scope = dict(original.__globals__)
    exec(compile(source.replace(old, new), "<controlled_diet_pagination_mutation>", "exec"), scope)
    monkeypatch.setattr(owner, name, scope[name])

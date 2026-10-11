"""识图双列表分页的原始窗口、用途授权与失效源负向 oracle。"""

from contextlib import asynccontextmanager
from datetime import datetime
import inspect
import os
from types import SimpleNamespace
import textwrap
from unittest.mock import ANY, AsyncMock

import pytest
from sqlalchemy.dialects.postgresql import dialect

from yuxi.repositories.health_vision_repository import HealthVisionRepository
from yuxi.services.health_vision_service import HealthVisionService, pg_manager
from yuxi.services.health_vision_types import HealthVisionError, VisionListPage


@pytest.mark.asyncio
@pytest.mark.parametrize("kind,scope", [("report", "report_view"), ("meal", "diet_edit")])
@pytest.mark.parametrize("job_count,draft_count", [(0, 0), (2, 3), (3, 4)])
async def test_pages_use_kind_and_independent_raw_windows(monkeypatch, kind, scope, job_count, draft_count):
    """可见空页仍按原始行推进；任务和草稿没有共用 offset。"""
    jobs, drafts = list(range(job_count)), list(range(draft_count))
    authorize = AsyncMock()
    jobs_query, drafts_query = AsyncMock(return_value=jobs), AsyncMock(return_value=drafts)
    visible_jobs, visible_drafts = AsyncMock(return_value=[]), AsyncMock(return_value=[])
    session = SimpleNamespace()

    @asynccontextmanager
    async def database():
        """只隔离窗口逻辑，真实查询由 HTTP/PG 证明。"""
        yield session

    monkeypatch.setattr(pg_manager, "get_async_session_context", database)
    monkeypatch.setattr(HealthVisionRepository, "authorize", authorize)
    monkeypatch.setattr(HealthVisionRepository, "list_jobs", jobs_query)
    monkeypatch.setattr(HealthVisionRepository, "list_drafts", drafts_query)
    monkeypatch.setattr(HealthVisionService, "_visible_jobs", visible_jobs)
    monkeypatch.setattr(HealthVisionService, "_visible_drafts", visible_drafts)
    result = await HealthVisionService().jobs_page(
        "actor", "member", kind, jobs_limit=2, jobs_offset=7, drafts_limit=3, drafts_offset=11
    )
    assert result == {
        "jobs": [],
        "drafts": [],
        "jobs_next_offset": 9 if job_count > 2 else None,
        "drafts_next_offset": 14 if draft_count > 3 else None,
    }
    VisionListPage.model_validate(result)
    authorize.assert_awaited_once_with("member", "actor", scope)
    jobs_query.assert_awaited_once_with("member", kind=kind, limit=3, offset=7)
    drafts_query.assert_awaited_once_with("member", kind=kind, limit=4, offset=11)
    visible_jobs.assert_awaited_once_with(session, ANY, "actor", jobs[:2])
    assert visible_drafts.await_args.args[0] is session
    assert visible_drafts.await_args.args[2:] == ("actor", drafts[:3])


@pytest.mark.asyncio
@pytest.mark.parametrize("kind,scope", [("report", "report_view"), ("meal", "diet_edit")])
async def test_revoked_or_wrong_purpose_rejects_before_empty_or_out_of_range_queries(monkeypatch, kind, scope):
    """无当前用途授权时，空页和越界页也必须先返回404。"""
    jobs_query, drafts_query = AsyncMock(return_value=[]), AsyncMock(return_value=[])
    authorize = AsyncMock(side_effect=HealthVisionError("not_found", "无权访问", 404))

    @asynccontextmanager
    async def database():
        """失去授权后两个查询都不应到达。"""
        yield SimpleNamespace()

    monkeypatch.setattr(pg_manager, "get_async_session_context", database)
    monkeypatch.setattr(HealthVisionRepository, "authorize", authorize)
    monkeypatch.setattr(HealthVisionRepository, "list_jobs", jobs_query)
    monkeypatch.setattr(HealthVisionRepository, "list_drafts", drafts_query)
    with pytest.raises(HealthVisionError) as rejected:
        await HealthVisionService().jobs_page("actor", "member", kind, jobs_offset=2147483647, drafts_offset=2147483647)
    assert rejected.value.status == 404 and rejected.value.code == "not_found"
    authorize.assert_awaited_once_with("member", "actor", scope)
    jobs_query.assert_not_awaited()
    drafts_query.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("method,table", [("list_jobs", "vision_job"), ("list_drafts", "vision_draft")])
async def test_database_filters_kind_before_stable_order_and_offset(method, table):
    """成员、用途、同时间ID排序和独立窗口都由数据库查询拥有。"""
    result = SimpleNamespace(all=lambda: [])
    session = SimpleNamespace(execute=AsyncMock(return_value=result), scalars=AsyncMock(return_value=result))
    await getattr(HealthVisionRepository(session), method)("member", kind="report", limit=21, offset=60)
    query = session.execute if method == "list_jobs" else session.scalars
    compiled = query.await_args.args[0].compile(dialect=dialect())
    sql = str(compiled)
    assert f"WHERE {table}.member_id =" in sql and f"{table}.kind =" in sql
    assert f"ORDER BY {table}.created_at DESC, {table}.id ASC" in sql
    assert compiled.params == {"member_id_1": "member", "kind_1": "report", "param_1": 21, "param_2": 60}


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["list_jobs", "list_drafts"])
async def test_legacy_queries_keep_mixed_kind_and_fifty_row_defaults(method):
    """原 vision 使用混合用途且每个列表至多50条的查询。"""
    result = SimpleNamespace(all=lambda: [])
    session = SimpleNamespace(execute=AsyncMock(return_value=result), scalars=AsyncMock(return_value=result))
    await getattr(HealthVisionRepository(session), method)("member")
    query = session.execute if method == "list_jobs" else session.scalars
    compiled = query.await_args.args[0].compile(dialect=dialect())
    assert compiled.params == {"member_id_1": "member", "param_1": 50, "param_2": 0}


@pytest.mark.asyncio
async def test_job_projection_hides_invalidated_source(monkeypatch):
    """恢复源过滤缺陷时，失效任务会错误流入公开列表。"""
    valid, invalid = (
        SimpleNamespace(task_id=name, member_id="member", kind="report", result_id=None)
        for name in ("valid", "invalid")
    )

    async def uploads(job):
        """明确指定失效任务，避免由被测实现生成期望。"""
        if job.task_id == "invalid":
            raise HealthVisionError("source_invalidated", "源文件不可用", 410)
        return []

    repo = SimpleNamespace(authorize=AsyncMock(), active_uploads=AsyncMock(side_effect=uploads))
    monkeypatch.setattr(HealthVisionService, "_serialize_job", lambda self, job, task, draft: {"task_id": job.task_id})
    rows = await HealthVisionService()._visible_jobs(SimpleNamespace(), repo, "actor", [(valid, None), (invalid, None)])
    assert rows == [{"task_id": "valid"}]


@pytest.mark.asyncio
async def test_draft_projection_keeps_manual_and_hides_invalidated_source():
    """人工草稿无需图片；识图草稿只在源仍有效时展示。"""
    records = [
        SimpleNamespace(
            id=name,
            member_id="member",
            kind="meal",
            job_id=None if name == "manual" else name,
            version=3,
            review_status="confirmed" if name == "manual" else "pending_confirmation",
            payload={"synthetic": name},
            model_version=None,
            parser_version=None,
            created_at=datetime(2026, 10, 11),
        )
        for name in ("manual", "valid", "invalid")
    ]

    async def uploads(job):
        """由独立源状态决定该草稿是否失效。"""
        if job == "invalid":
            raise HealthVisionError("source_invalidated", "源文件不可用", 410)
        return []

    async def get_record(model, record_id):
        """复现 linked job 查找，不做实际模型调用。"""
        return record_id

    repo = SimpleNamespace(authorize=AsyncMock(), active_uploads=AsyncMock(side_effect=uploads))
    rows = await HealthVisionService()._visible_drafts(SimpleNamespace(get=get_record), repo, "actor", records)
    assert [row["id"] for row in rows] == ["manual", "valid"]
    assert rows[0]["version"] == 3 and rows[0]["review_status"] == "confirmed"


@pytest.fixture(autouse=True)
def controlled_vision_pagination_mutation(monkeypatch):
    """只变异本测试进程函数副本，证明每个 guard 在正确原因上变红。"""
    mode = os.getenv("HEALTH_VISION_PAGINATION_MUTATION")
    if not mode:
        return
    mutations = {
        "authorization": (
            HealthVisionService,
            "jobs_page",
            'await repo.authorize(member_id, uid, "report_view" if kind == "report" else "diet_edit")',
            "pass",
        ),
        "jobs_lookahead": (HealthVisionService, "jobs_page", "limit=jobs_limit + 1", "limit=jobs_limit"),
        "drafts_lookahead": (HealthVisionService, "jobs_page", "limit=drafts_limit + 1", "limit=drafts_limit"),
        "jobs_source": (HealthVisionService, "_visible_jobs", "await repo.active_uploads(job)", "pass"),
        "drafts_source": (
            HealthVisionService,
            "_visible_drafts",
            "await repo.active_uploads(await session.get(VisionJob, draft.job_id))",
            "pass",
        ),
        "jobs_kind": (HealthVisionRepository, "list_jobs", "stmt = stmt.where(VisionJob.kind == kind)", "pass"),
        "drafts_kind": (HealthVisionRepository, "list_drafts", "stmt = stmt.where(VisionDraft.kind == kind)", "pass"),
        "jobs_offset": (HealthVisionRepository, "list_jobs", ".offset(offset)", ".offset(0)"),
        "drafts_offset": (HealthVisionRepository, "list_drafts", ".offset(offset)", ".offset(0)"),
        "jobs_order": (
            HealthVisionRepository,
            "list_jobs",
            "VisionJob.created_at.desc(), VisionJob.id.asc()",
            "VisionJob.created_at.desc()",
        ),
        "drafts_order": (
            HealthVisionRepository,
            "list_drafts",
            "VisionDraft.created_at.desc(), VisionDraft.id.asc()",
            "VisionDraft.created_at.desc()",
        ),
    }
    owner, name, old, new = mutations[mode]
    original = getattr(owner, name)
    source = textwrap.dedent(inspect.getsource(original))
    assert source.count(old) == 1
    scope = dict(original.__globals__)
    exec(compile(source.replace(old, new), "<controlled_vision_pagination_mutation>", "exec"), scope)
    monkeypatch.setattr(owner, name, scope[name])

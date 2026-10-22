"""配餐与导入继续使用家庭库，专题咨询保持角色范围与事后授权。"""

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from yuxi.services import health_family_kb_service as service
from yuxi.services.health_vision_types import HealthVisionError


@pytest.fixture
def family_material(monkeypatch):
    """真实检索实现读取合成当前分片，测试不调用外部模型或向量服务。"""
    monkeypatch.setenv(service.KB_ID_ENV, "family-only")
    for name in service.INDICATOR_KB_ENVS.values():
        monkeypatch.setenv(name, "topic-private")
    file = SimpleNamespace(
        file_id="file",
        filename="合成营养资料.md",
        status="indexed",
        content_hash="v1",
        updated_at=datetime(2026, 10, 21, tzinfo=UTC),
    )
    chunk = SimpleNamespace(chunk_id="chunk", file_id="file", content="有来源的合成营养片段。")
    session = SimpleNamespace(scalar=AsyncMock(side_effect=[chunk, file]))

    @asynccontextmanager
    async def session_context():
        yield session

    monkeypatch.setattr(service.pg_manager, "get_async_session_context", session_context)
    monkeypatch.setattr(service, "_require_fixed_kb", AsyncMock())
    retrieve = AsyncMock(
        return_value={
            "results": [
                {"id": "chunk", "file_id": "file", "kb_id": "family-only", "content": chunk.content},
            ]
        }
    )
    monkeypatch.setattr(service.knowledge_base, "retrieve", retrieve)
    return session, file, chunk, retrieve


async def test_nutrition_business_uses_only_family_kb_without_consultation_run(monkeypatch, family_material):
    """后台导入没有咨询 Run，仍只接受固定家庭库的版本化资料。"""
    _, file, chunk, retrieve = family_material
    monkeypatch.setattr(service, "_authorized_run", AsyncMock(side_effect=AssertionError("不是咨询入口")))

    result = await service.retrieve_family_nutrition_knowledge("  营养搭配  ")

    assert result["kb_id"] == "family-only" and "kb_ids" not in result
    assert result["query"] == "营养搭配" and result["status"] == "ok"
    assert len(result["sources"]) == 1
    source = result["sources"][0]
    assert source["filename"] == file.filename and source["content"] == chunk.content
    assert source["kb_id"] == "family-only" and source["file_content_hash"] == "v1"
    retrieve.assert_awaited_once_with(
        "family-only",
        "营养搭配",
        final_top_k=4,
        search_mode="keyword",
        use_reranker=False,
        use_graph_retrieval=False,
        read_only=True,
    )


@pytest.mark.parametrize("revoked", [False, True])
async def test_initial_planner_preserves_authorization_around_shared_retrieval(monkeypatch, family_material, revoked):
    """初始配餐实际调用共用检索；检索期间撤权时不返回正文。"""
    from yuxi.services import health_initial_planner_service, health_meal_plan_service

    binding = SimpleNamespace(initial_planner_selection={"kind": "single"})
    auth = AsyncMock(
        side_effect=[
            (None, binding),
            HealthVisionError("not_found", "已撤权", 404) if revoked else (None, binding),
        ]
    )
    monkeypatch.setattr(health_meal_plan_service, "require_planner_run", auth)

    if revoked:
        with pytest.raises(HealthVisionError, match="not_found"):
            await health_initial_planner_service.search_initial_nutrition_knowledge(SimpleNamespace(), "营养搭配")
    else:
        result = await health_initial_planner_service.search_initial_nutrition_knowledge(SimpleNamespace(), "营养搭配")
        assert result["kb_id"] == "family-only" and result["sources"][0]["content"]
    assert auth.await_count == 2
    assert family_material[3].await_count == 1


async def test_business_source_validation_keeps_family_scope_and_shared_locks(monkeypatch, family_material):
    """来源消费仍锁读当前版本，专题库回执和改版片段均拒绝。"""
    session, file, chunk, _ = family_material
    source = service._project_source("family-only", file, chunk, str(uuid4()))
    payload = {
        "status": "ok",
        "scope": "general_education",
        "query": "营养搭配",
        "kb_id": "family-only",
        "sources": [source],
    }
    session.scalar = AsyncMock(side_effect=[file, chunk])

    assert await service.validate_nutrition_knowledge_sources(session, payload) == [source]
    for call in session.scalar.await_args_list:
        statement = call.args[0]
        assert statement._for_update_arg is not None and statement._for_update_arg.read
        assert statement.get_execution_options()["populate_existing"]

    topic_payload = {key: value for key, value in payload.items() if key != "kb_id"}
    topic_payload["kb_ids"] = ["topic-private"]
    with pytest.raises(HealthVisionError, match="source_invalidated"):
        await service.validate_nutrition_knowledge_sources(session, topic_payload)
    chunk.content = "分片已改版"
    session.scalar = AsyncMock(side_effect=[file, chunk])
    with pytest.raises(HealthVisionError, match="source_invalidated"):
        await service.validate_nutrition_knowledge_sources(session, payload)


@pytest.mark.parametrize("role", [service.CONSULTATION_SLUG, *service.INDICATOR_KB_ENVS])
@pytest.mark.parametrize("change", ["binding", "role"])
async def test_consultation_rejects_scope_changes_during_retrieval(monkeypatch, role, change):
    """检索期间切库或切角色不能把旧范围的资料返回给模型。"""
    monkeypatch.setenv(service.KB_ID_ENV, "family-only")
    env_name = service.KB_ID_ENV if role == service.CONSULTATION_SLUG else service.INDICATOR_KB_ENVS[role]
    monkeypatch.setenv(env_name, "initial-kb")

    @asynccontextmanager
    async def session_context():
        yield None

    async def retrieve(*args, **kwargs):
        if change == "binding":
            monkeypatch.setenv(env_name, "changed-kb")
        return {"results": []}

    second_role = service.GLUCOSE_SLUG if role == service.CONSULTATION_SLUG else service.CONSULTATION_SLUG
    monkeypatch.setattr(service.pg_manager, "get_async_session_context", session_context)
    monkeypatch.setattr(
        service,
        "_authorized_run",
        AsyncMock(
            side_effect=[
                (SimpleNamespace(agent_slug=role), None),
                (SimpleNamespace(agent_slug=second_role if change == "role" else role), None),
            ]
        ),
    )
    monkeypatch.setattr(service, "_require_fixed_kb", AsyncMock())
    monkeypatch.setattr(service.knowledge_base, "retrieve", retrieve)

    with pytest.raises(HealthVisionError, match="source_invalidated"):
        await service.search_family_nutrition_knowledge(SimpleNamespace(), "科普")

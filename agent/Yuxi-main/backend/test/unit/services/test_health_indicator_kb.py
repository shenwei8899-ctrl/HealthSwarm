"""专题库按真实角色限域，来源回执不能跨库或跨角色复用。"""

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from yuxi.services import health_family_kb_service as service
from yuxi.services.health_vision_types import HealthVisionError

ROLES = ("health-blood-glucose", "health-blood-lipids", "health-blood-pressure")


@pytest.mark.parametrize("role", ROLES)
def test_indicator_tool_is_in_graph_context_and_skill(role):
    """三个真实装配Owner必须同时提供科普工具和仅科普指令。"""
    from yuxi.agents.buildin.health_blood_glucose.graph import HealthBloodGlucoseAgent
    from yuxi.agents.buildin.health_blood_lipids.graph import HealthBloodLipidsAgent
    from yuxi.agents.buildin.health_blood_pressure.graph import HealthBloodPressureAgent
    from yuxi.services.health_consultation_service import INDICATOR_TOOLS, INDICATOR_PROMPTS, INDICATOR_SKILL_SNAPSHOTS

    agent = dict(zip(ROLES, (HealthBloodGlucoseAgent, HealthBloodLipidsAgent, HealthBloodPressureAgent)))[role]
    assert {tool.name for tool in agent.consultation_tools} == set(INDICATOR_TOOLS[role])
    assert service.TOOL_NAME in INDICATOR_TOOLS[role]
    assert "[资料:source_id]" in INDICATOR_PROMPTS[role]
    assert "个人目标、治疗或配餐依据" in INDICATOR_PROMPTS[role]
    assert "2026.10.21.1" in str(INDICATOR_SKILL_SNAPSHOTS[role])


@pytest.mark.parametrize("role", ROLES)
@pytest.mark.parametrize("configured", ["", "one,", "one,one", "a,b,c,d,e,f"])
def test_empty_or_malformed_role_binding_fails_closed(monkeypatch, role, configured):
    """家庭库存在也不能回退；重复和超限配置必须显式拒绝。"""
    monkeypatch.setenv(service.KB_ID_ENV, "family-private")
    monkeypatch.setenv(service.INDICATOR_KB_ENVS[role], configured)
    with pytest.raises(HealthVisionError, match="knowledge_unavailable"):
        service.configured_education_kb_ids(role)


@pytest.mark.parametrize("role", ROLES)
async def test_search_is_bounded_and_rechecks_authorization(monkeypatch, role):
    """跨库交错取结果且总数受限；撤权发生在检索后时不返回正文。"""
    kb_ids = ("topic-primary", "topic-secondary", "topic-third")
    monkeypatch.setenv(service.INDICATOR_KB_ENVS[role], ",".join(kb_ids))
    monkeypatch.setenv(service.KB_ID_ENV, "family-private")
    file = SimpleNamespace(
        file_id="file", filename="合成科普.md", status="indexed", content_hash="v1", updated_at=datetime.now(UTC)
    )
    chunk = SimpleNamespace(chunk_id="chunk", file_id="file", content="合成一般科普")
    session = SimpleNamespace(scalar=AsyncMock(side_effect=[chunk, file] * 4))

    @asynccontextmanager
    async def session_context():
        yield session

    monkeypatch.setattr(service.pg_manager, "get_async_session_context", session_context)
    auth = AsyncMock(return_value=(SimpleNamespace(agent_slug=role), None))
    monkeypatch.setattr(service, "_authorized_run", auth)
    monkeypatch.setattr(service, "_require_fixed_kb", AsyncMock())
    retrieve = AsyncMock(
        side_effect=[
            {
                "results": [
                    {"id": f"chunk-{number}", "file_id": "file", "kb_id": kb, "content": chunk.content}
                    for number in range(4)
                ]
            }
            for kb in kb_ids
        ]
    )
    monkeypatch.setattr(service.knowledge_base, "retrieve", retrieve)
    result = await service.search_family_nutrition_knowledge(SimpleNamespace(), "科普")
    assert result["kb_ids"] == list(kb_ids) and "kb_id" not in result
    assert [source["kb_id"] for source in result["sources"]] == [*kb_ids, kb_ids[0]]
    assert len(result["sources"]) == 4
    assert auth.await_count == 2
    for call, kb in zip(retrieve.await_args_list, kb_ids):
        assert call.args == (kb, "科普")
        assert call.kwargs == dict(
            final_top_k=4, search_mode="keyword", use_reranker=False, use_graph_retrieval=False, read_only=True
        )
    retrieve.side_effect = [{"results": []}] * 3
    auth.side_effect = [(SimpleNamespace(agent_slug=role), None), HealthVisionError("not_found", "已撤权", 404)]
    with pytest.raises(HealthVisionError, match="not_found"):
        await service.search_family_nutrition_knowledge(SimpleNamespace(), "科普")


@pytest.mark.parametrize("role", ROLES)
async def test_payload_rejects_cross_role_binding_and_foreign_source(monkeypatch, role):
    """来源属于当前角色清单才可公开；审计内容不能自授其他库权限。"""
    monkeypatch.setenv(service.INDICATOR_KB_ENVS[role], "primary,secondary")
    monkeypatch.setattr(service, "_require_fixed_kb", AsyncMock())
    file = SimpleNamespace(
        file_id="file", filename="合成科普.md", status="indexed", content_hash="v1", updated_at=datetime.now(UTC)
    )
    chunk = SimpleNamespace(chunk_id="chunk", content="合成一般科普")
    source = service._project_source("secondary", file, chunk, str(uuid4()))
    payload = {
        "status": "ok",
        "scope": "general_education",
        "query": "科普",
        "kb_ids": ["primary", "secondary"],
        "sources": [source],
    }
    session = SimpleNamespace(scalar=AsyncMock(side_effect=[file, chunk]))
    assert await service._validate_payload(session, payload, agent_slug=role) == [source]
    for altered in (
        {**payload, "kb_ids": ["foreign"]},
        {**payload, "sources": [{**source, "kb_id": "foreign"}]},
        {**payload, "kb_id": "primary"},
    ):
        with pytest.raises(HealthVisionError, match="source_invalidated"):
            await service._validate_payload(session, altered, agent_slug=role)
    monkeypatch.setenv(service.INDICATOR_KB_ENVS[role], "new-binding")
    with pytest.raises(HealthVisionError, match="source_invalidated"):
        await service._validate_payload(session, payload, agent_slug=role)


async def test_authorization_failure_never_queries_knowledge(monkeypatch):
    """未授权的实际工具调用在发送检索词前结束。"""

    @asynccontextmanager
    async def session_context():
        yield None

    monkeypatch.setattr(service.pg_manager, "get_async_session_context", session_context)
    monkeypatch.setattr(
        service, "_authorized_run", AsyncMock(side_effect=HealthVisionError("consent_required", "撤同意", 403))
    )
    retrieve = AsyncMock()
    monkeypatch.setattr(service.knowledge_base, "retrieve", retrieve)
    with pytest.raises(HealthVisionError, match="consent_required"):
        await service.search_family_nutrition_knowledge(SimpleNamespace(), "科普")
    retrieve.assert_not_awaited()

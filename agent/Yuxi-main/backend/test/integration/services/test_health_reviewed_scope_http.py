"""真实管理员HTTP与PG验证旧范围兼容及索引之后的fresh范围检查。"""

import hashlib
import json
import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select

from test.e2e.test_health_consultation_e2e import isolated_health  # noqa: F401
from test.integration.services.test_health_evidence_final_publication_http import (
    answer_state,
    binding_for,
    close_synthetic_run,
    owned_run,
)
from test.integration.services.test_health_task_http import verified_task_cleanup  # noqa: F401
from test.integration.services.test_health_vision_http import ROOT, health_http  # noqa: F401
from yuxi.repositories import health_evidence_repository as owner
from yuxi.repositories.health_evidence_repository import HealthEvidenceRepository
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_health import HealthConsultation, NutritionEvidence, NutritionEvidenceCitation

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_legacy_http_source_remains_ordinary_only_and_indicator_search_is_empty(health_http):  # noqa: F811
    """无登记来源保持原响应与普通命中，不将旧审核扩成指标使用。"""
    client, users = health_http
    token = uuid4().hex
    source_id, body = await publish(client, users[2]["headers"], token)
    async with pg_manager.get_async_session_context() as session:
        source = await session.get(NutritionEvidence, source_id)
        assert source.reviewed_scope is None and source.scope_hash is None
        result = await HealthEvidenceRepository(session).search(f"scopehttp{token}", agent_slug="health-consultation")
        assert len(result) == 1 and result[0].id == source_id and result[0].content == body["content"]
        for role in ("health-blood-glucose", "health-blood-lipids", "health-blood-pressure"):
            assert await HealthEvidenceRepository(session).search(f"scopehttp{token}", agent_slug=role) == []
    revoked = await client.delete(f"{ROOT}/nutrition-evidence/{source_id}", headers=users[2]["headers"])
    assert revoked.status_code == 200 and revoked.json()["revoked"] is True
    async with pg_manager.get_async_session_context() as session:
        assert (await session.get(NutritionEvidence, source_id)).revoked_at is not None
        assert (
            await HealthEvidenceRepository(session).search(f"scopehttp{token}", agent_slug="health-consultation") == []
        )


async def test_pg_scope_changed_after_index_snapshot_is_rejected_before_citation(health_http, monkeypatch):  # noqa: F811
    """保留真实词法算法和PG，另一事务改范围后fresh锁读关闭命中。"""
    client, users = health_http
    token = uuid4().hex
    scope = {
        "domains": ["blood_glucose"],
        "population_category": "general_education",
        "population_description": "合成范围竞态通用说明",
        "exclusion_conditions": [],
        "license_ref": "synthetic://scope-http-license",
    }
    source_id, _ = await publish(client, users[2]["headers"], token, scope=scope)
    real_index = owner.search_evidence_index
    observed = []

    async def index_with_external_scope_change(documents, query):
        """hook只控制竞态时间点，实际shipping索引与SQL仍被执行。"""
        hits = await real_index(documents, query)
        observed.extend(hit.evidence_id for hit in hits)
        assert observed == [source_id]
        async with pg_manager.get_async_session_context() as concurrent:
            source = await concurrent.get(NutritionEvidence, source_id)
            changed = {**scope, "domains": ["blood_pressure"]}
            source.reviewed_scope = changed
            source.scope_hash = hashlib.sha256(
                json.dumps(changed, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
            ).hexdigest()
        return hits

    monkeypatch.setattr(owner, "search_evidence_index", index_with_external_scope_change)
    async with pg_manager.get_async_session_context() as session:
        cached = await session.get(NutritionEvidence, source_id)
        assert cached.reviewed_scope["domains"] == ["blood_glucose"]
        with pytest.raises(HealthVisionError) as rejected:
            await HealthEvidenceRepository(session).search(f"scopehttp{token}", agent_slug="health-blood-glucose")
        assert rejected.value.code == "source_invalidated"
        assert observed == [source_id]
        # populate_existing必须覆写早前identity-map缓存。
        assert cached.reviewed_scope["domains"] == ["blood_pressure"]
    async with pg_manager.get_async_session_context() as session:
        assert (await session.get(NutritionEvidence, source_id)).reviewed_scope["domains"] == ["blood_pressure"]


async def test_pg_checkpoint_tool_scope_cannot_reuse_cached_source(isolated_health, monkeypatch):  # noqa: F811
    """同Session旧来源缓存不拥有授权；checkpoint回执使用fresh范围与摘要。"""
    client, users, configuration, model = isolated_health
    token = uuid4().hex
    source_id, _ = await publish(client, users[2]["headers"], token)
    thread = await binding_for(client, users, configuration)
    context = await owned_run(users[0]["uid"], thread, model)
    try:
        state, _, adopted, _ = await answer_state(context, f"scopehttp{token}")
        payload = json.loads(state.values["messages"][1].content)
        new_scope = {
            "domains": ["nutrition"],
            "population_category": "general_education",
            "population_description": "合成scope已重新登记，旧引用摘要不得复用",
            "exclusion_conditions": [],
            "license_ref": "synthetic://checkpoint-scope-license",
        }
        async with pg_manager.get_async_session_context() as cached_session:
            cached = await cached_session.get(NutritionEvidence, source_id)
            citation = await cached_session.get(NutritionEvidenceCitation, adopted["citation_id"])
            binding = await cached_session.scalar(
                select(HealthConsultation).where(HealthConsultation.conversation_id == citation.conversation_id)
            )
            assert cached.reviewed_scope is None and cached.scope_hash is None and citation.scope_hash is None
            async with pg_manager.get_async_session_context() as external:
                changed = await external.get(NutritionEvidence, source_id)
                changed.reviewed_scope = new_scope
                changed.scope_hash = hashlib.sha256(
                    json.dumps(new_scope, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
                ).hexdigest()
            if os.getenv("HEALTH_SCOPE_PG_MUTATION") == "checkpoint_cache":
                original_execute = cached_session.execute

                async def execute_without_orm_refresh(statement, *args, **kwargs):
                    """只在此测试Session恢复旧ORM缓存缺陷；实际SQL与PG保留。"""
                    statement = statement.execution_options(populate_existing=False)
                    return await original_execute(statement, *args, **kwargs)

                monkeypatch.setattr(cached_session, "execute", execute_without_orm_refresh)
            with pytest.raises(HealthVisionError) as rejected:
                await HealthEvidenceRepository(cached_session).validate_tool_payload(
                    payload, binding, context.uid, agent_slug="health-consultation"
                )
            assert rejected.value.code == "source_invalidated"
            assert cached.reviewed_scope == new_scope
    finally:
        await close_synthetic_run(context)


async def publish(client, admin, token, *, scope=None):
    """不可变来源经真实HTTP创建，范围仅使用明确合成字段。"""
    now = datetime.now(UTC)
    body = {
        "source_ref": f"synthetic://scope-http/{token}",
        "source_version": "synthetic-v1",
        "title": f"scopehttp{token} 合成科普",
        "content": f"scopehttp{token} 合成索引与范围协议资料。",
        "review_ref": f"synthetic://scope-http-review/{token}",
        "reviewed_by": "synthetic-reviewer",
        "reviewed_at": (now - timedelta(days=1)).isoformat(),
        "valid_until": (now + timedelta(days=1)).isoformat(),
    }
    if scope is not None:
        body["reviewed_scope"] = scope
    response = await client.post(f"{ROOT}/nutrition-evidence", headers=admin, json=body)
    assert response.status_code == 201, response.text
    if scope is None:
        assert set(response.json()) == {"evidence_id", "source_version", "scope"}
    return response.json()["evidence_id"], body

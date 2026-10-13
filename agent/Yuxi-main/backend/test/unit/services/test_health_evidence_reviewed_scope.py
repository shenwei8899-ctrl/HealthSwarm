"""登记范围的跨域、复用、序列化与后台竞态独立边界。"""

import hashlib
import inspect
import json
import os
import textwrap
from contextlib import asynccontextmanager
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from pydantic import ValidationError
from sqlalchemy.dialects.postgresql import dialect
from sqlalchemy.dialects.sqlite import dialect as sqlite_dialect
from sqlalchemy.schema import CreateTable

from yuxi.repositories import health_evidence_repository as repository
from yuxi.repositories.health_evidence_repository import HealthEvidenceRepository
from yuxi.services import health_consultation_service as consultation
from yuxi.services import health_evidence_service as service
from yuxi.services.health_evidence_types import (
    NutritionCitation,
    NutritionCitationsResult,
    NutritionEvidenceInput,
    ReviewedKnowledgeScope,
)
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.storage.postgres.models_health import NutritionEvidence
from yuxi.utils.datetime_utils import utc_now_naive

ROLES = {
    "health-consultation": "nutrition",
    "health-blood-glucose": "blood_glucose",
    "health-blood-lipids": "blood_lipids",
    "health-blood-pressure": "blood_pressure",
}
REFERENCE = "11111111-1111-4111-8111-111111111111"
SOURCE = "22222222-2222-4222-8222-222222222222"
MEMBER = "33333333-3333-4333-8333-333333333333"
THREAD = "44444444-4444-4444-8444-444444444444"


def registered_scope(domain="nutrition", *, category="general_education", exclusions=()):
    """独立合成登记材料，不代表真实专业批准。"""
    return {
        "domains": [domain],
        "population_category": category,
        "population_description": "仅用于合成通用教育回放",
        "exclusion_conditions": list(exclusions),
        "license_ref": "synthetic://scope-license",
    }


def literal_digest(scope):
    """期望值独立从登记字面量计算，不复用生产摘要。"""
    return hashlib.sha256(
        json.dumps(scope, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()


def evidence(scope=None):
    """真实来源与回执应绑定两个不同事实摘要。"""
    content = "审核合成教育正文"
    source = SimpleNamespace(
        id=SOURCE,
        title="合成材料",
        content=content,
        content_hash=hashlib.sha256(content.encode()).hexdigest(),
        reviewed_scope=scope,
        scope_hash=literal_digest(scope) if scope else None,
        source_ref="synthetic://education",
        source_version="scope-v1",
        reviewed_at=utc_now_naive() - timedelta(days=1),
        valid_until=utc_now_naive() + timedelta(days=1),
        revoked_at=None,
    )
    citation = SimpleNamespace(
        id=REFERENCE, run_id="run", content_hash=source.content_hash, scope_hash=source.scope_hash
    )
    return source, citation


@pytest.fixture(autouse=True)
def controlled_scope_mutation(monkeypatch):
    """恢复单个目标缺陷，仅变异测试进程函数副本。"""
    mode = os.getenv("HEALTH_REVIEWED_SCOPE_MUTATION")
    if mode == "sql_scope":
        monkeypatch.setattr(HealthEvidenceRepository, "scope_filter", staticmethod(lambda role: True))
        return
    if mode == "fresh_scope":
        owner, attribute, old, new = (
            HealthEvidenceRepository,
            "search",
            "self.validate_source_scope(source, agent_slug)",
            "pass",
        )
    elif mode == "scope_snapshot":
        owner, attribute, old, new = (
            HealthEvidenceRepository,
            "search",
            "or source.scope_hash != scope_hashes[hit.evidence_id]",
            "",
        )
    elif mode == "citation_scope":
        owner, attribute, old, new = (
            HealthEvidenceRepository,
            "validate_citations",
            "self.validate_source_scope(source, agent_slug)",
            "pass",
        )
    elif mode == "citation_hash":
        owner, attribute, old, new = (
            HealthEvidenceRepository,
            "validate_citations",
            "if citation.scope_hash != source.scope_hash:",
            "if False:",
        )
    elif mode == "citation_role":
        owner, attribute, old, new = (
            HealthEvidenceRepository,
            "validate_citations",
            "AgentRun.agent_slug == agent_slug,",
            "",
        )
    elif mode == "citation_fresh":
        owner, attribute, old, new = (
            HealthEvidenceRepository,
            "validate_citations",
            ".execution_options(populate_existing=True)",
            ".execution_options(populate_existing=False)",
        )
    elif mode == "search_role":
        owner, attribute, old, new = (
            service,
            "search_nutrition_evidence",
            "agent_slug=run.agent_slug",
            'agent_slug="health-consultation"',
        )
    else:
        return
    original = getattr(owner, attribute)
    source = textwrap.dedent(inspect.getsource(original))
    assert source.count(old) == 1

    async def mutated(*args, **kwargs):
        # Mock装配之后再绑定原globals，保证红灯来自目标边界。
        namespace = dict(original.__globals__)
        exec(compile(source.replace(old, new), "<controlled_reviewed_scope>", "exec"), namespace)
        return await namespace[original.__name__](*args, **kwargs)

    monkeypatch.setattr(owner, attribute, mutated)


@pytest.mark.parametrize(
    "field,value",
    [
        ("domains", []),
        ("domains", ["nutrition", "nutrition"]),
        ("domains", ["invented"]),
        ("population_category", "adult_diabetes"),
        ("population_description", " "),
        ("license_ref", " "),
        ("exclusion_conditions", [" "]),
    ],
)
def test_scope_registration_refuses_missing_or_invented_professional_contract(field, value):
    data = registered_scope()
    data[field] = value
    with pytest.raises(ValidationError):
        ReviewedKnowledgeScope.model_validate(data)


def test_reviewed_scope_fields_are_not_automatically_expanded_to_all_roles():
    data = registered_scope("blood_pressure")
    scope = ReviewedKnowledgeScope.model_validate(data)
    assert scope.model_dump() == data
    assert HealthEvidenceRepository.scope_digest(data) == literal_digest(data)
    assert HealthEvidenceRepository.scope_digest(None) is None


def test_multi_domain_registration_canonicalizes_order_and_hashes_all_professional_fields():
    data = registered_scope()
    data["domains"] = ["nutrition", "blood_pressure", "blood_glucose"]
    canonical = ReviewedKnowledgeScope.model_validate(data).model_dump()
    assert canonical["domains"] == ["blood_glucose", "blood_pressure", "nutrition"]
    original_digest = literal_digest(canonical)
    assert HealthEvidenceRepository.scope_digest(canonical) == original_digest
    for field in ("population_description", "license_ref"):
        changed = {**canonical, field: "changed professional input"}
        assert HealthEvidenceRepository.scope_digest(changed) != original_digest


@pytest.mark.parametrize(
    "scope", [None, registered_scope(), registered_scope(category="professional_selection_required")]
)
@pytest.mark.asyncio
async def test_publish_records_explicit_scope_without_rewriting_legacy_or_restricted_material(monkeypatch, scope):
    from datetime import UTC

    session = SimpleNamespace(add=Mock(), flush=AsyncMock())

    @asynccontextmanager
    async def session_context():
        yield session

    monkeypatch.setattr(service.pg_manager, "get_async_session_context", session_context)
    authorize = AsyncMock()
    monkeypatch.setattr(service, "require_evidence_admin", authorize)
    data = NutritionEvidenceInput(
        source_ref="synthetic://source",
        source_version="scope-v1",
        title="合成资料",
        content="合成科普正文",
        review_ref="synthetic://professional-review",
        reviewed_by="synthetic-professional",
        reviewed_at=(utc_now_naive() - timedelta(days=1)).replace(tzinfo=UTC),
        valid_until=(utc_now_naive() + timedelta(days=1)).replace(tzinfo=UTC),
        reviewed_scope=scope,
    )
    result = await service.publish_evidence("admin-actor", data)
    saved = session.add.call_args.args[0]
    authorize.assert_awaited_once_with(session, "admin-actor")
    assert saved.reviewed_scope == scope
    assert saved.scope_hash == (literal_digest(scope) if scope else None)
    assert saved.content_hash == hashlib.sha256("合成科普正文".encode()).hexdigest()
    if scope:
        assert result["reviewed_scope"] == scope and result["scope"] == scope["population_category"]
    else:
        assert set(result) == {"evidence_id", "source_version", "scope"}


@pytest.mark.parametrize("role", ROLES)
@pytest.mark.asyncio
async def test_search_sql_limits_domain_and_general_population_before_local_index(monkeypatch, role):
    session = SimpleNamespace(execute=AsyncMock(return_value=[]))
    index = AsyncMock(return_value=[])
    monkeypatch.setattr(repository, "search_evidence_index", index)
    assert await HealthEvidenceRepository(session).search("合成", agent_slug=role) == []
    compiled = session.execute.await_args.args[0].compile(dialect=dialect())
    sql = str(compiled)
    assert "@>" in sql and "LIKE" not in sql
    assert [ROLES[role]] in compiled.params.values()
    assert "general_education" in compiled.params.values() and [] in compiled.params.values()
    assert ("nutrition_evidence.reviewed_scope IS NULL" in sql) == (role == "health-consultation")
    index.assert_awaited_once_with([], "合成")


@pytest.mark.parametrize("role", ROLES)
@pytest.mark.asyncio
async def test_fresh_search_refuses_cross_domain_even_when_index_returns_valid_content_proof(monkeypatch, role):
    foreign_domain = "nutrition" if role != "health-consultation" else "blood_pressure"
    source, _ = evidence(registered_scope(foreign_domain))
    session = SimpleNamespace(
        execute=AsyncMock(
            return_value=[
                (source.id, source.source_version, source.content_hash, source.title, source.content, source.scope_hash)
            ]
        ),
        scalars=AsyncMock(return_value=[source]),
    )
    monkeypatch.setattr(
        repository,
        "search_evidence_index",
        AsyncMock(
            return_value=[
                SimpleNamespace(
                    evidence_id=source.id,
                    source_version=source.source_version,
                    content_hash=source.content_hash,
                )
            ]
        ),
    )
    with pytest.raises(HealthVisionError, match="source_invalidated"):
        await HealthEvidenceRepository(session).search("合成", agent_slug=role)


@pytest.mark.asyncio
async def test_inflight_registered_scope_change_requires_a_new_index_proof(monkeypatch):
    source, _ = evidence(registered_scope())
    previous_hash = source.scope_hash
    source.reviewed_scope["license_ref"] = "synthetic://revised-license"
    source.scope_hash = literal_digest(source.reviewed_scope)
    session = SimpleNamespace(
        execute=AsyncMock(
            return_value=[
                (source.id, source.source_version, source.content_hash, source.title, source.content, previous_hash)
            ]
        ),
        scalars=AsyncMock(return_value=[source]),
    )
    monkeypatch.setattr(
        repository,
        "search_evidence_index",
        AsyncMock(
            return_value=[
                SimpleNamespace(
                    evidence_id=source.id,
                    source_version=source.source_version,
                    content_hash=source.content_hash,
                )
            ]
        ),
    )
    with pytest.raises(HealthVisionError, match="source_invalidated"):
        await HealthEvidenceRepository(session).search("合成", agent_slug="health-consultation")


@pytest.mark.parametrize("lock", [False, True])
@pytest.mark.parametrize("role", ROLES)
@pytest.mark.asyncio
async def test_registered_citation_revalidates_role_scope_and_independent_receipt_hash(role, lock):
    source, citation = evidence(registered_scope(ROLES[role]))
    session = SimpleNamespace(execute=AsyncMock(return_value=[(citation, source)]))
    binding = SimpleNamespace(conversation_id=7, member_id=MEMBER)
    projection = await HealthEvidenceRepository(session).validate_citations(
        [REFERENCE],
        binding,
        "actor",
        agent_slug=role,
        run_id="run",
        lock=lock,
    )
    assert projection[REFERENCE]["reviewed_scope"] == source.reviewed_scope
    assert projection[REFERENCE]["scope_hash"] == literal_digest(source.reviewed_scope)
    compiled = session.execute.await_args.args[0].compile(dialect=dialect())
    assert "agent_runs.agent_slug =" in str(compiled) and "conversations.agent_id =" in str(compiled)
    assert list(compiled.params.values()).count(role) == 2
    assert ("FOR SHARE OF nutrition_evidence, nutrition_evidence_citation" in str(compiled)) == lock
    assert session.execute.await_args.args[0].get_execution_options().get("populate_existing") is True


def test_reviewed_scope_keeps_postgresql_jsonb_and_existing_sqlite_unit_ddl():
    """真实PG仍存JSONB，原SQLite基础接口单测可继续创建共享ORM表。"""
    assert "reviewed_scope JSONB" in str(CreateTable(NutritionEvidence.__table__).compile(dialect=dialect()))
    assert "reviewed_scope JSON" in str(CreateTable(NutritionEvidence.__table__).compile(dialect=sqlite_dialect()))


@pytest.mark.parametrize(
    "case",
    [
        "cross_domain",
        "restricted",
        "exclusion",
        "scope_tampered",
        "source_hash_tampered",
        "receipt_hash_tampered",
        "legacy_indicator",
    ],
)
@pytest.mark.asyncio
async def test_citation_never_returns_body_without_current_scope_proof(case):
    source, citation = evidence(registered_scope("blood_glucose"))
    role = "health-blood-glucose"
    if case == "cross_domain":
        role = "health-blood-lipids"
    elif case in {"restricted", "exclusion"}:
        source.reviewed_scope["population_category"] = (
            "professional_selection_required" if case == "restricted" else "general_education"
        )
        source.reviewed_scope["exclusion_conditions"] = ["合成排除条件"] if case == "exclusion" else []
        source.scope_hash = literal_digest(source.reviewed_scope)
        citation.scope_hash = source.scope_hash
    elif case == "scope_tampered":
        source.reviewed_scope["license_ref"] = "synthetic://unapproved-change"
    elif case == "source_hash_tampered":
        source.scope_hash = citation.scope_hash = "0" * 64
    elif case == "receipt_hash_tampered":
        citation.scope_hash = "0" * 64
    else:
        source.reviewed_scope = source.scope_hash = citation.scope_hash = None
    session = SimpleNamespace(execute=AsyncMock(return_value=[(citation, source)]))
    binding = SimpleNamespace(conversation_id=7, member_id=MEMBER)
    with pytest.raises(HealthVisionError, match="source_invalidated"):
        await HealthEvidenceRepository(session).validate_citations([REFERENCE], binding, "actor", agent_slug=role)


@pytest.mark.asyncio
async def test_legacy_consultation_tool_shape_and_http_shape_preserve_existing_contract():
    source, citation = evidence()
    session = SimpleNamespace(execute=AsyncMock(return_value=[(citation, source)]))
    binding = SimpleNamespace(conversation_id=7, member_id=MEMBER)
    projection = await HealthEvidenceRepository(session).validate_citations(
        [REFERENCE], binding, "actor", agent_slug="health-consultation"
    )
    item = projection[REFERENCE]
    assert set(item) == {
        "citation_id",
        "evidence_id",
        "title",
        "content",
        "source_ref",
        "source_version",
        "reviewed_at",
        "scope",
    }
    http_item = NutritionCitation.model_validate(item).model_dump(mode="json")
    assert set(http_item) == set(item)
    result = NutritionCitationsResult(
        status="cited",
        agent_run_id="run",
        request_id=None,
        thread_id=THREAD,
        member_id=MEMBER,
        final_message_id=42,
        citations=[item],
    ).model_dump(mode="json")
    assert result["request_id"] is None and set(result["citations"][0]) == set(item)
    payload = {"status": "ok", "query": "合成", "citations": [item], "personal_meal_plan_available": False}
    await HealthEvidenceRepository(session).validate_tool_payload(
        payload, binding, "actor", agent_slug="health-consultation"
    )


@pytest.mark.parametrize("role", ROLES)
@pytest.mark.asyncio
async def test_search_service_uses_real_run_role_and_records_scope_digest(monkeypatch, role):
    source, _ = evidence(registered_scope(ROLES[role]))
    session = SimpleNamespace(add=Mock())
    context = SimpleNamespace(uid="actor", thread_id=THREAD, model="synthetic-model")
    run = SimpleNamespace(id="run", agent_slug=role, input_payload={"health_processing": {"synthetic": True}})
    binding = SimpleNamespace(conversation_id=7, member_id=MEMBER)

    @asynccontextmanager
    async def session_context():
        yield session

    monkeypatch.setattr(service.pg_manager, "get_async_session_context", session_context)
    monkeypatch.setattr(
        service, "HealthConsultationRepository", lambda _: SimpleNamespace(require_attempt=AsyncMock(return_value=run))
    )
    monkeypatch.setattr(consultation, "require_consultation", AsyncMock(return_value=(binding, {})))
    search = AsyncMock(return_value=[source])
    monkeypatch.setattr(service.HealthEvidenceRepository, "search", search)
    result = await service.search_nutrition_evidence(context, "合成")
    search.assert_awaited_once_with("合成", agent_slug=role)
    saved = session.add.call_args.args[0]
    assert saved.scope_hash == literal_digest(source.reviewed_scope)
    assert result["citations"][0]["reviewed_scope"] == source.reviewed_scope

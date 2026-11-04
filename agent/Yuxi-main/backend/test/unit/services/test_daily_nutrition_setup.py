"""准备状态只解释当前资料，不把候选或历史总数当专业批准。"""

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.dialects import postgresql

from yuxi.services import daily_nutrition_setup as setup


@pytest.fixture
def preparation(monkeypatch):
    """隔离服务依赖，保留真实统计 SQL 及返回装配。"""
    session = SimpleNamespace(
        scalar=AsyncMock(side_effect=[3, 4, 9, 2, 1]),
        execute=AsyncMock(return_value=SimpleNamespace(all=lambda: [("food", 2, 7, 3, 4)])),
        scalars=AsyncMock(return_value=SimpleNamespace(all=lambda: ["kb-family"])),
    )

    @asynccontextmanager
    async def transaction():
        yield session

    rules = AsyncMock(return_value=None)
    monkeypatch.setattr(setup.pg_manager, "get_async_session_context", transaction)
    monkeypatch.setattr(setup, "HealthQualityRepository", lambda _: SimpleNamespace(rules=rules))
    monkeypatch.setattr(
        setup.health_vision_service,
        "configuration",
        AsyncMock(
            return_value={
                "meal_plan": {"available": True, "reason_code": None, "model": "fixture"},
                "policy_version": "p1",
            }
        ),
    )
    projection = {"status": "not_ready", "reason": "expired", "version": 7}
    monkeypatch.setattr(setup, "external_projection", lambda *_: projection)
    monkeypatch.setenv("HEALTH_DAILY_RULE_CODE", "fixture-rule")
    monkeypatch.setenv("HEALTH_FAMILY_NUTRITION_KB_ID", " kb-family ")
    monkeypatch.setenv("HEALTH_RECIPE_KB_ID", "kb-missing")
    return session, rules, projection


@pytest.mark.asyncio
async def test_historical_counts_and_owned_candidate_rows_are_distinct(preparation):
    session, rules, _ = preparation
    result = await setup.daily_setup_readiness("actor-A")
    assert result["counts"] == {
        "foods": 3,
        "recipes": 4,
        "rule_versions": 9,
        "recipe_sources": 2,
        "recipe_classifications": 1,
    }
    assert result["candidate_batches"]["food"] == {"batches": 2, "rows": 7, "invalid": 3, "pending_review": 4}
    assert result["candidate_batches"]["recipe"] == {"batches": 0, "rows": 0, "invalid": 0, "pending_review": 0}
    statement = session.execute.await_args.args[0].compile(dialect=postgresql.dialect())
    assert "nutrition_import_batch.actor_uid =" in str(statement)
    assert "actor-A" in statement.params.values()
    assert result["rules"] == {
        "configured": True,
        "code": "fixture-rule",
        "status": "not_ready",
        "reason": "expired",
        "version": 7,
    }
    assert result["rules_ready"] is False
    rules.assert_awaited_once_with("fixture-rule")


@pytest.mark.asyncio
async def test_knowledge_binding_must_resolve_to_existing_milvus(preparation):
    session, _, _ = preparation
    result = await setup.daily_setup_readiness("actor-A")
    assert result["knowledge_bindings"] == {
        "food": {"configured": True, "available": True, "reason": None},
        "recipe": {"configured": True, "available": False, "reason": "not_found"},
    }
    statement = session.scalars.await_args.args[0].compile(dialect=postgresql.dialect())
    assert "knowledge_bases.kb_type =" in str(statement) and "milvus" in statement.params.values()


@pytest.mark.asyncio
async def test_missing_configuration_is_not_reported_as_missing_content(preparation, monkeypatch):
    monkeypatch.delenv("HEALTH_DAILY_RULE_CODE")
    monkeypatch.delenv("HEALTH_RECIPE_KB_ID")
    result = await setup.daily_setup_readiness("actor-A")
    assert result["rules"]["reason"] == "not_configured"
    assert result["rules"]["configured"] is False
    assert result["knowledge_bindings"]["recipe"] == {
        "configured": False,
        "available": False,
        "reason": "not_configured",
    }


@pytest.mark.asyncio
async def test_rule_lookup_preserves_the_planning_consumers_configuration(preparation, monkeypatch):
    """准备页不能擅自修正规则代码并误报真实配餐可用。"""
    _, rules, _ = preparation
    monkeypatch.setenv("HEALTH_DAILY_RULE_CODE", " fixture-rule ")
    result = await setup.daily_setup_readiness("actor-A")
    rules.assert_awaited_once_with(" fixture-rule ")
    assert result["rules"]["code"] == " fixture-rule "


@pytest.mark.asyncio
@pytest.mark.parametrize("reason", ["revoked", "expired", "integrity_mismatch", "knowledge_source_changed"])
async def test_current_rule_failure_reason_is_not_hidden_by_history(preparation, reason):
    _, _, projection = preparation
    projection["reason"] = reason
    result = await setup.daily_setup_readiness("actor-A")
    assert result["counts"]["rule_versions"] == 9
    assert result["rules"]["reason"] == reason and result["rules_ready"] is False

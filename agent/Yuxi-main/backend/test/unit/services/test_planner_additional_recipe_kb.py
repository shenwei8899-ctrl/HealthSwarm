"""配餐参考菜谱沿固定绑定读取，旧线程在绑定变化后失效。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from yuxi.services import reference_meal_plan_service as plans
from yuxi.services import reference_recipe_index as recipes
from yuxi.services.health_family_kb_service import configured_health_kb_ids
from yuxi.services.health_nutrition_service import input_fingerprint


async def test_reference_recipe_query_includes_additional_library(monkeypatch):
    """参考菜谱 SQL 的库范围包含主库与附加库。"""
    monkeypatch.setenv("HEALTH_RECIPE_KB_ID", "primary")
    monkeypatch.setenv("HEALTH_RECIPE_EXTRA_KB_IDS", "additional")
    rows = [("primary-file", "primary"), ("additional-file", "additional")]
    session = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(all=lambda: rows)))

    assert await recipes.reference_recipe_rows(session) == rows

    statement = session.execute.await_args.args[0]
    assert list(configured_health_kb_ids("health-meal-planner")) in statement.compile().params.values()


async def test_reference_thread_rejects_changed_recipe_library_scope(monkeypatch):
    """旧线程不能沿用只包含主库的来源哈希。"""
    monkeypatch.setenv("HEALTH_RECIPE_KB_ID", "primary")
    monkeypatch.setenv("HEALTH_RECIPE_EXTRA_KB_IDS", "additional")
    old_sources = {"recipe_kb_ids": ["primary"]}
    binding = SimpleNamespace(
        initial_planner_selection={
            "selection": {"mode": "reference"},
            "source_hash": input_fingerprint(old_sources),
        },
        member_id="member",
    )

    async def current_context(*args, **kwargs):
        return {
            "selection": binding.initial_planner_selection["selection"],
            "sources": {"recipe_kb_ids": list(configured_health_kb_ids("health-meal-planner"))},
        }

    monkeypatch.setattr(plans, "reference_context_in_session", current_context)

    with pytest.raises(plans.ReferencePlanSourceChanged, match="source_invalidated"):
        await plans.bound_reference_context(None, "user", binding)

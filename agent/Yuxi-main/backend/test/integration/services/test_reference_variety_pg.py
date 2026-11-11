"""真实 PostgreSQL 检查并发保留组合与逐账号当前餐单投影。"""

# ruff: noqa: F401,F811
import asyncio
from datetime import date
from uuid import uuid4

import pytest
from sqlalchemy import select, func

from test.integration.services.test_reference_meal_plan_http import (
    family_profile_http,
    ensure_live_api_schema,
    cleanup_test_sandboxes,
    cleanup_test_knowledge_resources,
    isolate_delivery,
    setup_reference,
    bind_reference,
    running_context,
    grounded_plan,
    complete,
)
from test.unit.services.test_reference_variety import meals
from yuxi.repositories.reference_variety_repository import reference_history, current_reference_menus
from yuxi.services.reference_recipe_variety import validate_variety
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.storage.postgres.models_health import HealthInitialPlanPreview, HealthDailyMealPlan
from yuxi.storage.postgres.models_business import AgentRun

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_concurrent_families_cannot_reserve_identical_menu(family_profile_http, monkeypatch):
    current = await setup_reference(family_profile_http, monkeypatch)
    _, sessions, _, member_id, _, choice = current
    selected = meals(["rice", "fish", "greens"])
    first_locked, release = asyncio.Event(), asyncio.Event()

    async def save(family, first=False):
        selection = {"mode": "reference", "family_id": family, "plan_date": choice["plan_date"]}
        async with sessions.begin() as db:
            history = await reference_history(db, selection, lock=True)
            if first:
                first_locked.set()
                await release.wait()
            validate_variety(history, selection, selected)
            db.add(
                HealthInitialPlanPreview(
                    id=str(uuid4()),
                    actor_uid="self",
                    member_id=member_id,
                    selection=selection,
                    snapshot={"meals": selected},
                )
            )

    first = asyncio.create_task(save("family-a", True))
    await first_locked.wait()
    second = asyncio.create_task(save("family-b"))
    try:
        await asyncio.sleep(0.05)
        assert not second.done()
    finally:
        release.set()
    await first
    with pytest.raises(HealthVisionError) as error:
        await second
    assert error.value.code == "reference_menu_repeated"
    async with sessions() as db:
        assert await db.scalar(select(func.count()).select_from(HealthInitialPlanPreview)) == 1


async def test_other_account_preview_does_not_hide_published_menu(family_profile_http, monkeypatch):
    current = await setup_reference(family_profile_http, monkeypatch)
    _, sessions, _, member_id, _, choice = current
    family = choice["family_id"]
    async with sessions.begin() as db:
        for actor, names in (("self", ["rice", "fish", "greens"]), ("other", ["bread", "beef", "beans"])):
            pid = str(uuid4())
            db.add(
                HealthInitialPlanPreview(
                    id=pid,
                    actor_uid=actor,
                    member_id=member_id,
                    selection={"mode": "reference", **choice},
                    snapshot={"meals": meals(names)},
                )
            )
            await db.flush()
            db.add(
                HealthDailyMealPlan(
                    id=str(uuid4()),
                    actor_uid=actor,
                    family_id=family,
                    plan_date=date.fromisoformat(choice["plan_date"]),
                    version=1,
                    meal_sources={kind: {"kind": "reference", "id": pid} for kind in ("breakfast", "lunch", "dinner")},
                )
            )
    selection = {"family_id": "new-family", "plan_date": choice["plan_date"]}
    async with sessions() as db:
        menus = await current_reference_menus(db, selection)
        assert len(menus) == 2
        with pytest.raises(HealthVisionError) as error:
            validate_variety([], selection, meals(["rice", "fish", "greens"]), current_menus=menus, actor_uid="new")
        assert error.value.code == "reference_menu_repeated"


@pytest.mark.parametrize("status", ["failed", "cancelled", "interrupted"])
async def test_unsuccessful_run_releases_reserved_recipes(family_profile_http, monkeypatch, status):
    current = await setup_reference(family_profile_http, monkeypatch)
    bound = await bind_reference(current)
    context = await running_context(current, bound.json()["thread_id"])
    await grounded_plan(current, context)
    async with current[1].begin() as db:
        assert len(await reference_history(db, current[-1])) == 1
        run = await db.get(AgentRun, context.run_id)
        run.status = status
    async with current[1]() as db:
        assert await reference_history(db, current[-1]) == []


async def test_publication_checks_combined_legacy_meals(family_profile_http, monkeypatch):
    """没有每日索引的旧三餐也按实际分餐合并，发布时不能撞上新保留组合。"""
    current = await setup_reference(family_profile_http, monkeypatch)
    kinds = ["breakfast", "lunch", "dinner"]
    bound = await bind_reference(current, meal_types=kinds)
    first = await running_context(current, bound.json()["thread_id"])
    original, _, _ = await grounded_plan(current, first, meal_types=kinds)
    await complete(current, first, original)
    bound = await bind_reference(current, meal_types=["dinner"], daily_base_version=0)
    second = await running_context(current, bound.json()["thread_id"])
    changed, _, _ = await grounded_plan(current, second, meal_type="dinner", replacement=True)
    async with current[1].begin() as db:
        assert await db.scalar(select(func.count()).select_from(HealthDailyMealPlan)) == 0
        db.add(
            HealthInitialPlanPreview(
                id=str(uuid4()),
                actor_uid="other",
                member_id=current[3],
                selection={"mode": "reference", **current[-1], "family_id": "other-family"},
                snapshot={"meals": original["meals"][:2] + changed["meals"]},
            )
        )
    with pytest.raises(HealthVisionError, match="reference_menu_repeated"):
        await complete(current, second, changed)
    async with current[1]() as db:
        assert await db.scalar(select(func.count()).select_from(HealthDailyMealPlan)) == 0

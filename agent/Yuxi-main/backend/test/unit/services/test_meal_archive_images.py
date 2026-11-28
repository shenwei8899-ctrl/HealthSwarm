"""归档补图只能复用准确来源的已生成图片，不能改动快照。"""

import copy
import asyncio
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from yuxi.services import meal_archive_service as archive
from yuxi.services.meal_archive_projection import archive_meal
from yuxi.services.recipe_image_identity import recipe_image_key
from yuxi.services.reference_recipe_presentation import recipe_image_key as today_image_key


def original_dish():
    """构造不含真实用户信息的保存菜谱。"""
    return {
        "file_id": "file",
        "chunk_id": "chunk",
        "name": "合成蒸蛋",
        "ingredients": ["鸡蛋"],
        "steps": ["蒸熟"],
        "source": {"kb_id": "kb", "file_id": "file", "file_hash": "hash"},
    }


def archived_row(dish):
    """构造有日期和来源索引的日归档。"""
    return SimpleNamespace(
        id="day",
        family_id="family",
        plan_date=date(2026, 11, 24),
        version=1,
        meal_sources={"breakfast": {"kind": "reference", "id": "preview"}},
        archive_meals={"breakfast": {"meal_type": "breakfast", "dishes": [dish], "members": []}},
    )


def test_new_archive_preserves_image_identity_without_source_disclosure():
    dish = original_dish()
    saved = archive_meal({"meal_type": "breakfast", "dishes": [dish]})["dishes"][0]
    assert saved["recipe_image_key"] == today_image_key(dish)
    assert "source" not in saved
    assert archive_meal({"meal_type": "breakfast", "dishes": [saved]})["dishes"][0] == saved


@pytest.mark.asyncio
async def test_old_archive_recovers_exact_key_and_deduplicates_reads(monkeypatch):
    dish = original_dish()
    old = {k: v for k, v in dish.items() if k != "source"}
    row = archived_row(copy.deepcopy(old))
    row.archive_meals["breakfast"]["dishes"].append(copy.deepcopy(old))
    before = copy.deepcopy(row.archive_meals)
    monkeypatch.setattr(archive, "archive_source_cache", AsyncMock(return_value={}))
    source = AsyncMock(return_value={"dishes": [dish]})
    monkeypatch.setattr(archive, "stored_meal", source)
    image = {"image_url": "/minio/public/" + today_image_key(dish), "image_source": {"image_role": "ai_generated"}}
    lookup = AsyncMock(return_value=image)
    monkeypatch.setattr(archive, "stored_recipe_image", lookup)
    result = await archive.archive_with_images(None, [row])
    assert all(item["image_url"] == image["image_url"] for item in result[0]["meals"][0]["dishes"])
    lookup.assert_awaited_once_with(today_image_key(dish))
    source.assert_awaited_once()
    assert row.archive_meals == before
    assert "recipe_image_key" not in str(result) and "kb_id" not in str(result)


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["steps", "file_id", "ingredients", "name"])
async def test_mismatched_history_cannot_borrow_another_recipe_image(monkeypatch, change):
    dish = original_dish()
    old = {k: v for k, v in dish.items() if k != "source"}
    old[change] = ["不同"] if isinstance(old[change], list) else "不同"
    monkeypatch.setattr(archive, "archive_source_cache", AsyncMock(return_value={}))
    monkeypatch.setattr(archive, "stored_meal", AsyncMock(return_value={"dishes": [dish]}))
    lookup = AsyncMock()
    monkeypatch.setattr(archive, "stored_recipe_image", lookup)
    result = await archive.archive_with_images(None, [archived_row(old)])
    assert "image_url" not in result[0]["meals"][0]["dishes"][0]
    lookup.assert_not_awaited()


@pytest.mark.asyncio
async def test_saved_key_reads_later_image_without_loading_old_sources(monkeypatch):
    dish = original_dish()
    saved = archive_meal({"meal_type": "breakfast", "dishes": [dish]})["dishes"][0]
    cache = AsyncMock()
    monkeypatch.setattr(archive, "archive_source_cache", cache)
    lookup = AsyncMock(side_effect=[{}, {"image_url": "/minio/public/" + recipe_image_key(dish)}])
    monkeypatch.setattr(archive, "stored_recipe_image", lookup)
    row = archived_row(saved)
    first = await archive.archive_with_images(None, [row])
    second = await archive.archive_with_images(None, [row])
    assert "image_url" not in first[0]["meals"][0]["dishes"][0]
    assert second[0]["meals"][0]["dishes"][0]["image_url"].endswith(".webp")
    assert "image_url" not in row.archive_meals["breakfast"]["dishes"][0]
    cache.assert_not_awaited()


@pytest.mark.asyncio
async def test_slow_storage_returns_snapshot_and_frozen_sources_are_not_reused(monkeypatch):
    dish = original_dish()
    row = archived_row(archive_meal({"dishes": [dish]})["dishes"][0])

    async def blocked(key):
        """模拟对象存储持续阻塞。"""
        await asyncio.sleep(10)

    monkeypatch.setattr(archive, "stored_recipe_image", blocked)
    monkeypatch.setattr(archive, "ARCHIVE_IMAGE_TIMEOUT_SECONDS", 0.01)
    result = await asyncio.wait_for(archive.archive_with_images(None, [row]), timeout=0.2)
    assert result[0]["meals"][0]["dishes"][0]["name"] == dish["name"]
    row = archived_row({k: v for k, v in dish.items() if k != "source"})
    row.meal_sources["breakfast"] = {"kind": "selection", "dish_sources": [{"frozen": {"meal": {"dishes": [dish]}}}]}
    monkeypatch.setattr(archive, "archive_source_cache", AsyncMock(return_value={}))
    recover = AsyncMock()
    monkeypatch.setattr(archive, "stored_meal", recover)
    await archive.archive_with_images(None, [row])
    recover.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["family", "date", "version", "missing"])
async def test_formal_source_guards_are_enforced_by_repository(change):
    from yuxi.repositories.meal_archive_repository import stored_meal
    from yuxi.storage.postgres.models_health import HealthDailyArrangement

    today = date(2026, 11, 24)
    row = SimpleNamespace(
        family_id="other" if change == "family" else "family",
        plan_date=date(2026, 11, 23) if change == "date" else today,
        snapshot={
            "version": 2 if change == "version" else 1,
            "meals": [{"meal_type": "breakfast", "dishes": [original_dish()]}],
        },
    )
    cache = {} if change == "missing" else {(HealthDailyArrangement, "source"): row}
    assert (
        await stored_meal(
            None, "family", today, {"kind": "formal", "id": "source", "version": 1}, "breakfast", cache=cache
        )
        is None
    )


@pytest.mark.asyncio
async def test_uncompleted_reference_source_is_not_used():
    from yuxi.repositories.meal_archive_repository import stored_meal
    from yuxi.storage.postgres.models_health import HealthInitialPlanPreview
    from yuxi.storage.postgres.models_business import AgentRun

    row = SimpleNamespace(
        run_id="run",
        actor_uid="owner",
        selection={"family_id": "family", "plan_date": "2026-11-24"},
        snapshot={"meals": []},
    )
    cache = {
        (HealthInitialPlanPreview, "preview"): row,
        (AgentRun, "run"): SimpleNamespace(status="running", uid="owner"),
    }
    assert (
        await stored_meal(
            None, "family", date(2026, 11, 24), {"kind": "reference", "id": "preview"}, "breakfast", cache=cache
        )
        is None
    )

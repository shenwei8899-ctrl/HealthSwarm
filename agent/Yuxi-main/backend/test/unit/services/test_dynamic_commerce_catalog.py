"""商城目录版本缓存和结构化食材匹配。"""

from unittest.mock import AsyncMock

import pytest

from yuxi.services import daily_commerce_service, reference_recipe_index, reference_recipe_matching
from yuxi.services import reference_meal_plan_service, reference_recipe_image_tasks


@pytest.fixture(autouse=True)
def reset_catalog_cache():
    daily_commerce_service.reset_catalog_cache()
    yield
    daily_commerce_service.reset_catalog_cache()


@pytest.mark.asyncio
async def test_catalog_reuses_snapshot_until_lightweight_version_changes(monkeypatch):
    request = AsyncMock(
        side_effect=[
            {"catalog_version": "v1"},
            {"items": [{"sku_id": "1", "category_code": "vegetable"}], "catalog_version": "v1", "has_more": False},
            {"catalog_version": "v1"},
            {"catalog_version": "v2"},
            {"items": [{"sku_id": "2", "category_code": "protein"}], "catalog_version": "v2", "has_more": False},
        ]
    )
    monkeypatch.setattr(daily_commerce_service, "commerce_request", request)
    monkeypatch.setattr(daily_commerce_service, "_CATALOG_PROBE_TTL_SECONDS", 0)

    first = await daily_commerce_service.current_catalog()
    second = await daily_commerce_service.current_catalog(["vegetable"])
    changed = await daily_commerce_service.current_catalog()

    assert [item["sku_id"] for item in first["items"]] == ["1"]
    assert [item["sku_id"] for item in second["items"]] == ["1"]
    assert [item["sku_id"] for item in changed["items"]] == ["2"]
    product_calls = [call for call in request.await_args_list if "/catalog/products?" in call.args[1]]
    assert len(product_calls) == 2


def test_dynamic_product_ingredient_alias_matches_without_product_name_guessing():
    product = {
        "sku_id": "sku-okra",
        "product_name": "当日鲜蔬组合A",
        "sale_status": "available",
        "available_quantity": 8,
        "price_cent": 699,
        "ingredients": [
            {"ingredient_code": "okra", "name": "秋葵", "aliases": ["黄秋葵"]},
        ],
    }

    matched = reference_recipe_matching.reference_ingredient_candidates(("黄秋葵 200克",), [product])

    assert matched[0]["status"] == "matched"
    assert matched[0]["food"] == "秋葵"
    assert matched[0]["candidate_skus"][0]["sku_id"] == "sku-okra"


def test_ambiguous_dynamic_alias_is_not_silently_selected():
    products = [
        {
            "sku_id": sku,
            "product_name": name,
            "sale_status": "available",
            "available_quantity": 5,
            "ingredients": [{"ingredient_code": code, "name": name, "aliases": ["青菜"]}],
        }
        for sku, code, name in (("1", "bok_choy", "小白菜"), ("2", "lettuce", "生菜"))
    ]

    matched = reference_recipe_matching.reference_ingredient_candidates(("青菜 100克",), products)

    assert matched[0]["status"] == "needs_confirmation"
    assert matched[0]["candidate_skus"] == []


def test_legacy_food_name_resolves_to_structured_canonical_alias():
    product = {
        "sku_id": "egg",
        "product_name": "当日鲜蛋",
        "sale_status": "available",
        "available_quantity": 5,
        "ingredients": [{"ingredient_code": "fresh_egg", "name": "鲜鸡蛋", "aliases": ["鸡蛋"]}],
    }

    matched = reference_recipe_matching.reference_ingredient_candidates(("鸡蛋 2个",), [product])

    assert matched[0]["status"] == "matched"
    assert matched[0]["food"] == "鲜鸡蛋"


def test_opened_recipe_candidates_authorize_only_returned_skus():
    receipts = [
        {
            "recipe_check": {
                "ingredient_matches": [
                    {"candidate_skus": [{"sku_id": "12"}, {"sku_id": "13"}]},
                    {"candidate_skus": []},
                ]
            }
        }
    ]

    assert reference_meal_plan_service.reference_candidate_sku_ids(receipts) == {"12", "13"}


def test_ranker_excludes_recent_recipe_sources_without_reordering_remaining():
    rows = [
        (
            file_id, "kb", f"家常菜谱_{name}.md", f"hash-{file_id}", f"chunk-{file_id}",
            f"# {name}\n\n## 食材\n- 鸡蛋 1个\n\n## 做法\n1. 蒸熟",
        )
        for file_id, name in (("old", "鸡蛋羹"), ("new", "蒸鸡蛋"))
    ]

    ranked = reference_recipe_index.rank_reference_recipes(
        rows, [], "鸡蛋", 9, excluded_file_ids={"old"}
    )

    assert [item["file_id"] for item in ranked] == ["new"]


@pytest.mark.asyncio
async def test_recipe_image_task_reads_saved_preview_and_returns_count(monkeypatch):
    from contextlib import asynccontextmanager
    from types import SimpleNamespace

    preview = SimpleNamespace(
        snapshot={"scope": "daily_reference", "meals": [{"dishes": [{"name": "番茄炒蛋"}]}]}
    )
    session = SimpleNamespace(get=AsyncMock(return_value=preview))

    @asynccontextmanager
    async def transaction():
        yield session

    prepared = AsyncMock()
    monkeypatch.setattr(reference_recipe_image_tasks.pg_manager, "get_async_session_context", transaction)
    import yuxi.services.reference_recipe_presentation as presentation

    monkeypatch.setattr(presentation, "prepare_recipe_images", prepared)
    result = await reference_recipe_image_tasks.run_reference_recipe_images(
        SimpleNamespace(payload={"preview_id": "preview-1"})
    )

    assert result == {"preview_id": "preview-1", "dish_count": 1}
    prepared.assert_awaited_once_with(preview.snapshot["meals"])


@pytest.mark.asyncio
async def test_recent_recipe_exclusions_are_scoped_to_actor_family_and_date():
    from types import SimpleNamespace

    matching = SimpleNamespace(
        selection={"mode": "reference", "family_id": "family-1", "plan_date": "2026-11-09"},
        snapshot={"meals": [{"dishes": [{"source": {"file_id": "used-recipe"}}]}]},
    )
    other_family = SimpleNamespace(
        selection={"mode": "reference", "family_id": "family-2", "plan_date": "2026-11-09"},
        snapshot={"meals": [{"dishes": [{"source": {"file_id": "other-recipe"}}]}]},
    )
    session = SimpleNamespace(
        scalars=AsyncMock(return_value=SimpleNamespace(all=lambda: [matching, other_family]))
    )

    result = await reference_meal_plan_service.recent_reference_file_ids(
        session, "owner", {"family_id": "family-1", "plan_date": "2026-11-09"}
    )

    assert result == {"used-recipe"}

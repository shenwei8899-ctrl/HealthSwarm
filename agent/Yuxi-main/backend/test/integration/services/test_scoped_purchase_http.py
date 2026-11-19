"""真实 HTTP 与 PG 验证采购范围、家庭隔离及版本；原来源由合成发布快照提供。"""

from copy import deepcopy
from datetime import datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from test.integration.services.test_daily_arrangement_http import source
from test.integration.services.test_health_family_profile_http import (
    family_profile_http,  # noqa: F401
    ensure_live_api_schema,  # noqa: F401
    cleanup_test_sandboxes,  # noqa: F401
    cleanup_test_knowledge_resources,  # noqa: F401
)
from yuxi.storage.postgres.models_health import HealthDailyMealPlan
from yuxi.services import meal_purchase_source as origins
from yuxi.services import daily_meal_plan_service as daily
from yuxi.services import daily_commerce_service as commerce
from yuxi.services import meal_dish_service as purchase
from yuxi.services.health_vision_types import HealthVisionError

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_scoped_purchase_never_reads_other_dishes_or_whole_plan(family_profile_http, monkeypatch):  # noqa: F811
    client, sessions, users = family_profile_http
    family, _, profile, _ = await source(client, users["self"])
    member = profile["members"][0]["member_id"]
    day = datetime.now(ZoneInfo("Asia/Shanghai")).date()
    dish = {"name": "合成米饭", "dish_key": "rice", "ingredients": ["大米300克"]}
    sku = {
        "sku_id": "rice-250",
        "product_id": "rice",
        "product_name": "大米",
        "sku_name": "250克",
        "net_content": {"value": 250, "unit": "g"},
        "price_cent": 400,
        "available_quantity": 20,
        "sale_status": "available",
        "ingredients": [],
        "product_description": "大米",
        "allergen_codes": [],
    }
    from yuxi.services.reference_meal_plan_service import reference_product

    saved = {
        "meals": [{"dishes": [dish]}],
        "purchase_items": [{**reference_product(sku, 2), "ingredient_refs": ["大米300克"]}],
    }
    selected = [{"dish_key": key, "source": {"kind": "reference", "id": key}} for key in ("rice", "unrelated")]
    async with sessions() as db:
        db.add(
            HealthDailyMealPlan(
                id=str(uuid4()),
                actor_uid="self",
                family_id=family["id"],
                plan_date=day,
                version=4,
                is_shared=True,
                meal_sources={
                    "dinner": {"kind": "selection", "dish_sources": selected, "member_ids": [member]},
                    "lunch": {"kind": "invalid"},
                },
                pending={},
            )
        )
        await db.commit()
    calls = []

    async def resolve(_session, uid, fid, origin, cache):
        assert origin["dish_key"] == "rice"
        calls.append(origin["dish_key"])
        return deepcopy(dish), {}, [{"id": member}], deepcopy(saved)

    async def whole_plan(*args, **kwargs):
        raise AssertionError("purchase read whole-day display")

    async def catalog():
        return {"items": [sku], "version": "test"}

    async def publish(*args, **kwargs):
        return {
            "status": "available",
            "trade_validation_status": "passed",
            "package_sn": "synthetic",
            "package_version": 1,
            "items": [{"sku_id": "rice-250", "quantity": 2}],
        }

    monkeypatch.setattr(origins, "purchase_origin", resolve)
    monkeypatch.setattr(daily, "read_current_plan", whole_plan)
    monkeypatch.setattr(commerce, "current_catalog", catalog)
    monkeypatch.setattr(commerce, "commerce_request", publish)
    monkeypatch.setattr(
        "yuxi.services.health_commerce_service.sign_commerce_source", lambda value: {"payload": "synthetic"}
    )
    url = f"/api/family/{family['id']}/daily-meal-plans/{day}/meals/dinner/purchase"
    body = {"version": 4, "dish_keys": ["rice"]}
    response = await client.post(url, json=body, headers=users["self"])
    assert response.status_code == 200, response.text
    result = response.json()["purchase"]
    assert result["available"] and result["items"][0]["sku"]["product_name"] == "大米"
    assert result["items"][0]["quantity"] == 2 and calls == ["rice"]
    assert (await client.post(url, json=body, headers=users["other"])).status_code == 404
    assert (await client.post(url, json={**body, "version": 3}, headers=users["self"])).status_code == 409
    assert (await client.post(url, json={**body, "dish_keys": ["foreign"]}, headers=users["self"])).status_code == 422

    # Source validation binds mapping while allowing price and reserved stock to change.
    async def resolved(*args):
        return [({**dish, "origin": selected[0]}, {}, [{"id": member}], saved)]

    monkeypatch.setattr(origins, "selected_purchase_origins", resolved)
    receipt = {
        "scope_hash_version": 2,
        "scope_hash": purchase.procurement_hash(await resolved()),
        "uid": "self",
        "family_id": family["id"],
        "date": str(day),
        "meal_type": "dinner",
        "version": 4,
        "dish_keys": ["rice"],
        "expires_at": 9999999999,
        "items": [{"sku_id": "rice-250", "quantity": 2, "identity": purchase.merchant_facts(sku)}],
    }
    sku["price_cent"] = 900
    sku["available_quantity"] = 0
    assert (await purchase.validate_selection_purchase(receipt))["items"] == [{"sku_id": "rice-250", "quantity": 2}]
    saved["purchase_items"][0]["quantity"] = 3
    with pytest.raises(HealthVisionError, match="菜品食材对应"):
        await purchase.validate_selection_purchase(receipt)


async def test_purchase_recipe_metadata_uses_current_postgres_versions(family_profile_http, monkeypatch):  # noqa: F811
    from yuxi.storage.postgres.models_knowledge import Base, KnowledgeBase, KnowledgeChunk, KnowledgeFile
    from yuxi.services import health_family_kb_service as kb
    from yuxi.services.health_nutrition_service import input_fingerprint

    _, sessions, _ = family_profile_http
    async with sessions() as db:
        connection = await db.connection()
        await connection.run_sync(Base.metadata.create_all)
        db.add(KnowledgeBase(kb_id="purchase-recipes", name="合成采购菜谱", kb_type="milvus"))
        await db.flush()
        db.add(
            KnowledgeFile(
                file_id="fish",
                kb_id="purchase-recipes",
                filename="fish.md",
                status="indexed",
                content_hash="recipe-v1",
                is_folder=False,
            )
        )
        await db.flush()
        db.add(
            KnowledgeChunk(
                chunk_id="fish-1", file_id="fish", kb_id="purchase-recipes", chunk_index=0, content="鱼100克"
            )
        )
        await db.commit()
    monkeypatch.setattr(kb, "configured_health_kb_ids", lambda role: ["purchase-recipes"])
    dish = {
        "file_id": "fish",
        "chunk_id": "fish-1",
        "source": {
            "kb_id": "purchase-recipes",
            "file_hash": "recipe-v1",
            "chunks_hash": input_fingerprint([("fish-1", "鱼100克")]),
        },
    }
    async with sessions() as db:
        await origins.recipe_metadata(db, dish)
    async with sessions() as db:
        from sqlalchemy import update

        await db.execute(update(KnowledgeChunk).where(KnowledgeChunk.chunk_id == "fish-1").values(content="鱼200克"))
        await db.commit()
    async with sessions() as db:
        with pytest.raises(HealthVisionError, match="分片版本"):
            await origins.recipe_metadata(db, dish)
    monkeypatch.setattr(kb, "configured_health_kb_ids", lambda role: ["different-kb"])
    async with sessions() as db:
        with pytest.raises(HealthVisionError, match="来源版本"):
            await origins.recipe_metadata(db, dish)

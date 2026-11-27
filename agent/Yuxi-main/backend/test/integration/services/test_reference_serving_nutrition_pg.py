"""真实发布结构及来源失效条件下的参考菜谱营养计算。"""
# ruff: noqa: F811 -- 复用显式隔离的 PostgreSQL fixture。

from copy import deepcopy
from datetime import date
from uuid import uuid4

import pytest
from sqlalchemy import select

from test.integration.services.test_health_family_profile_http import (  # noqa: F401
    family_profile_http,
    ensure_live_api_schema,
    cleanup_test_sandboxes,
    cleanup_test_knowledge_resources,
)
from test.unit.services.test_reference_serving import A, B, suggestion
from yuxi.services.health_source_types import knowledge_source_reference
from yuxi.services.health_vision_service import health_vision_service
from yuxi.services.health_vision_types import FoodInput, RecipeInput
from yuxi.services.reference_meal_plan_types import ReferenceServingSuggestion
from yuxi.services.reference_serving import checked_member_servings
from yuxi.services.reference_serving_nutrition import attach_reference_nutrition
from yuxi.services.meal_archive_projection import archive_meal
from yuxi.storage.postgres.models_health import HealthDailyMealPlan
from yuxi.storage.postgres.models_knowledge import KnowledgeBase, KnowledgeFile

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.mark.parametrize("changed_source", ["food-source", "recipe-source"])
async def test_published_recipe_structure_and_source_invalidation(family_profile_http, changed_source):
    """走实际发布用例，原件变版后新餐单不再使用旧营养。"""
    client, sessions, identities = family_profile_http
    async with sessions.begin() as db:
        connection = await db.connection()
        await connection.run_sync(lambda sync: KnowledgeBase.__table__.create(sync, checkfirst=True))
        await connection.run_sync(lambda sync: KnowledgeFile.__table__.create(sync, checkfirst=True))
        db.add(
            KnowledgeBase(
                kb_id="serving-kb",
                name="合成份量资料",
                kb_type="milvus",
                created_by="admin",
                share_config={
                    "version": 2,
                    "read_scope": {"access_level": "global", "department_ids": [], "user_uids": []},
                    "manage_scope": {"access_level": "user", "department_ids": [], "user_uids": ["admin"]},
                },
            )
        )
        await db.flush()
        for fid in ["food-source", "recipe-source"]:
            db.add(
                KnowledgeFile(
                    file_id=fid, kb_id="serving-kb", filename=fid + ".md", file_size=100, content_hash="a" * 64
                )
            )
    food_source = knowledge_source_reference("serving-kb", "food-source", "a" * 64)
    recipe_source = knowledge_source_reference("serving-kb", "recipe-source", "a" * 64)
    published = []
    for index, energy in enumerate([200, 20]):
        published.append(
            await health_vision_service.publish_food(
                "admin",
                FoodInput.model_validate(
                    {
                        "record_code": f"serving-food-{index}",
                        "name": f"合成食品{index}",
                        "cooking_state": "raw",
                        "source": food_source,
                        "license": "synthetic-test",
                        "edition": "1",
                        "dataset_version": "1",
                        "nutrients": {"energy_kcal": energy, "protein_g": energy / 10},
                    }
                ),
            )
        )
    recipe = await health_vision_service.publish_recipe(
        "admin",
        RecipeInput.model_validate(
            {
                "record_code": "reference:serving-test",
                "name": "合成分餐菜",
                "cooking_state": "熟食",
                "source": recipe_source,
                "license": "synthetic-test",
                "edition": "1",
                "dataset_version": "c" * 64,
                "ingredients": [{"food_id": food["id"], "grams": grams} for food, grams in zip(published, [250, 400])],
                "yield_grams": 600,
            }
        ),
    )
    value = ReferenceServingSuggestion.model_validate(suggestion())
    dish = {
        "name": "合成原食谱菜",
        "file_id": "pg:serving-test",
        "chunk_id": "recipe_catalog",
        "ingredients": ["合成肉250克", "合成菜400克"],
        "serving_suggestion": value.model_dump(mode="json"),
        "member_servings": checked_member_servings(value, {A, B}, {A: "甲", B: "乙"}),
        "nutrition_status": "not_calculated",
    }
    documents = {(dish["file_id"], dish["chunk_id"]): {"recipe_id": "serving-test", "file_hash": "c" * 64}}
    result = deepcopy(dish)
    async with sessions.begin() as db:
        await attach_reference_nutrition(db, [{"dishes": [result]}], documents)
    assert result["nutrition_status"] == "calculated"
    assert result["nutrition_reference"]["recipe_version_id"] == recipe["id"]
    assert result["nutrition_total"]["energyKcal"] == 580  # 本餐计划100/200克只能得到240，原谱250/400克得到580。
    assert result["nutrition_total"]["quantity_basis"] == "source_recipe"
    assert "nutrition" not in result
    assert all("nutrition" not in person for person in result["member_servings"])
    assert result["serving_suggestion"] == dish["serving_suggestion"]
    assert result["nutrition_total"]["sodiumMg"] is None

    alternate = deepcopy(dish)
    alternate.pop("serving_suggestion")
    alternate.pop("member_servings")
    async with sessions.begin() as db:
        await attach_reference_nutrition(db, [{"dishes": [alternate]}], documents)
    assert alternate["nutrition_total"] == result["nutrition_total"]

    family = await client.post("/api/family", headers=identities["admin"], json={"name": "合成原谱营养家庭"})
    assert family.status_code == 200, family.text
    fid = family.json()["id"]
    rid = str(uuid4())
    legacy = {"name": "旧计划量菜", "nutrition_total": {"basis": "whole_dish", "energyKcal": 240}}
    async with sessions.begin() as db:
        db.add(
            HealthDailyMealPlan(
                id=rid,
                actor_uid="admin",
                family_id=fid,
                plan_date=date(2026, 11, 27),
                version=1,
                meal_sources={},
                archive_meals={"dinner": archive_meal({"meal_type": "dinner", "dishes": [result, legacy]})},
            )
        )
    async with sessions() as db:
        saved = await db.get(HealthDailyMealPlan, rid)
        assert saved.archive_meals["dinner"]["dishes"][0]["nutrition_total"] == result["nutrition_total"]
    response = await client.get(f"/api/family/{fid}/daily-meal-plans/2026-11-27/archive", headers=identities["admin"])
    assert response.status_code == 200, response.text
    assert response.json()["meals"][0]["dishes"][0]["nutrition_total"] == result["nutrition_total"]
    assert response.json()["meals"][0]["dishes"][1]["nutrition_total"] == legacy["nutrition_total"]

    async with sessions.begin() as db:
        source = await db.scalar(select(KnowledgeFile).where(KnowledgeFile.file_id == changed_source))
        source.content_hash = "b" * 64
    unchanged = deepcopy(dish)
    async with sessions.begin() as db:
        await attach_reference_nutrition(db, [{"dishes": [unchanged]}], documents)
    assert unchanged["nutrition_status"] == "not_calculated"
    assert "nutrition_total" not in unchanged
    assert result["nutrition_total"]["energyKcal"] == 580  # 历史已计算快照保持原值。
    archived = await client.get(f"/api/family/{fid}/daily-meal-plans/2026-11-27/archive", headers=identities["admin"])
    assert archived.status_code == 200, archived.text
    assert archived.json()["meals"][0]["dishes"][0]["nutrition_total"] == result["nutrition_total"]

"""真实 HTTP/PG 验证知识库原件、发布和专业状态联动；数据仅用于隔离工程测试。"""

from contextlib import asynccontextmanager
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import delete, update

from test.integration.services.test_health_meal_planner_http import plan_spec, publish_planner_recipe
from test.integration.services.test_health_plan_adoption_http import adopt_body, approve
from test.integration.services.test_health_quality_http import setup_quality
from test.integration.services.test_health_vision_http import ROOT, create_member, health_http  # noqa: F401
from yuxi.services.health_source_types import knowledge_source_reference
from yuxi.services.health_daily_service import business_date
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_health import HealthMealPlanAdoption, HealthProfessionalReview, RecipeVersion
from yuxi.storage.postgres.models_knowledge import KnowledgeBase, KnowledgeFile

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@asynccontextmanager
async def source_document(uid):
    """独立建立原件元数据；仅改变、清理本测试的准确 ID，不依赖公共资料或真实批准。"""
    kb, fid = "kb_" + uuid4().hex, "file_" + uuid4().hex
    async with pg_manager.get_async_session_context() as session:
        session.add(
            KnowledgeBase(
                kb_id=kb,
                name="synthetic-nutrition",
                kb_type="lightrag",
                created_by=uid,
                share_config={"version": 2, "read_scope": None, "manage_scope": None},
            )
        )
        await session.flush()
        session.add(
            KnowledgeFile(
                kb_id=kb,
                file_id=fid,
                filename="synthetic-source.md",
                content_hash="a" * 64,
                file_size=20,
                created_by=uid,
                is_folder=False,
                status="uploaded",
            )
        )
    try:
        yield kb, fid, knowledge_source_reference(kb, fid, "a" * 64)
    finally:
        async with pg_manager.get_async_session_context() as session:
            await session.execute(delete(KnowledgeFile).where(KnowledgeFile.file_id == fid))
            await session.execute(delete(KnowledgeBase).where(KnowledgeBase.kb_id == kb))


async def test_source_permission_hash_and_member_readiness(health_http):  # noqa: F811
    """来源管理权限、摘要绑定与成员读取边界分别由真实接口验证。"""
    client, users = health_http
    owner, other, admin = [u["headers"] for u in users]
    async with source_document(users[2]["uid"]) as (kb, fid, reference):
        endpoint = f"{ROOT}/nutrition-sources/{kb}/documents/{fid}"
        assert (await client.get(endpoint, headers=owner)).status_code == 403
        selected = await client.get(endpoint, headers=admin)
        assert selected.status_code == 200, selected.text
        assert selected.json()["source_ref"] == reference
        assert selected.json()["professional_approval"] is False
        async with pg_manager.get_async_session_context() as session:
            await session.execute(
                update(KnowledgeBase).where(KnowledgeBase.kb_id == kb).values(created_by=users[0]["uid"])
            )
        assert (await client.get(endpoint, headers=admin)).status_code == 403
        async with pg_manager.get_async_session_context() as session:
            await session.execute(
                update(KnowledgeBase).where(KnowledgeBase.kb_id == kb).values(created_by=users[2]["uid"])
            )
            await session.execute(
                update(KnowledgeFile).where(KnowledgeFile.file_id == fid).values(content_hash="b" * 64)
            )
        body = {
            "record_code": str(uuid4()),
            "name": "合成原料",
            "cooking_state": "合成",
            "source": reference,
            "license": "synthetic",
            "edition": "v1",
            "dataset_version": "v1",
            "nutrients": {"energy_kcal": "0"},
        }
        stale = await client.post(f"{ROOT}/foods", headers=admin, json=body)
        assert stale.status_code == 409 and stale.json()["code"] == "knowledge_source_changed"
        body["source"] = reference.replace("a" * 64, "b" * 64)
        valid = await client.post(f"{ROOT}/foods", headers=admin, json=body)
        assert valid.status_code == 201, valid.text
        assert valid.json()["nutrients"]["energy_kcal"] == "0"
        assert valid.json()["nutrients"]["sodium_mg"] is None
    member = await create_member(client, owner)
    endpoint = f"{ROOT}/members/{member}/nutrition-readiness?rule_code=synthetic-missing"
    result = await client.get(endpoint, headers=owner)
    assert result.status_code == 200, result.text
    assert result.headers["cache-control"] == "no-store"
    assert result.json()["personal_targets"]["status"] == "not_ready"
    assert result.json()["meal_preview"]["status"] == "not_ready"
    assert (await client.get(endpoint, headers=other)).status_code == 404


@pytest.mark.parametrize("target", ["food", "recipe", "rules"])
async def test_changed_original_invalidates_review_and_adoption(health_http, target):  # noqa: F811
    """使用当前原件完成批准及采用，再改摘要；状态须持久化失效且不改历史快照。"""
    client, users = health_http
    owner = users[0]["headers"]
    async with source_document(users[2]["uid"]) as (_, fid, reference):
        current = await setup_quality(client, users, source_refs={target: reference})
        await approve(client, users, current)
        adopted = await client.post(
            f"{ROOT}/meal-plans/{current['plan']}/adopt", headers=owner, json=adopt_body(current)
        )
        assert adopted.status_code == 201, adopted.text
        initial = adopted.json()
        async with pg_manager.get_async_session_context() as session:
            await session.execute(
                update(KnowledgeFile).where(KnowledgeFile.file_id == fid).values(content_hash="b" * 64)
            )
        read = await client.get(f"{ROOT}/professional-reviews/{current['case']['review_id']}", headers=owner)
        assert read.status_code == 200 and read.json()["status"] == "invalidated", read.text
        async with pg_manager.get_async_session_context() as session:
            case = await session.get(HealthProfessionalReview, current["case"]["review_id"])
            adoption = await session.get(HealthMealPlanAdoption, initial["adoption_id"])
            assert case.status == "invalidated" and case.version == 4
            assert adoption.status == "invalidated" and adoption.version == 2
            assert adoption.snapshot == initial["snapshot"]
        read = await client.get(f"{ROOT}/meal-plan-adoptions/{initial['adoption_id']}", headers=owner)
        assert read.status_code == 200 and read.json()["status"] == "invalidated", read.text


async def test_deleted_ingredient_blocks_preview_recipe_and_both_portions(health_http):  # noqa: F811
    """删除原料原件后不能通过菜谱、普通预览或份量发布入口继续使用。"""
    client, users = health_http
    owner, admin = users[0]["headers"], users[2]["headers"]
    async with source_document(users[2]["uid"]) as (_, fid, reference):
        recipe = await publish_planner_recipe(client, admin, "合成来源菜谱", food_source=reference)
        async with pg_manager.get_async_session_context() as session:
            row = await session.get(RecipeVersion, recipe)
            food_id = row.ingredients[0]["food"]["id"]
            await session.execute(delete(KnowledgeFile).where(KnowledgeFile.file_id == fid))
        member = await create_member(client, owner)
        preview = await client.post(
            f"{ROOT}/members/{member}/meal-plan-previews", headers=owner, json=plan_spec(recipe)
        )
        assert preview.status_code == 409 and preview.json()["code"] == "knowledge_source_changed"
        source = {
            "source": "synthetic:other-valid-source",
            "license": "synthetic",
            "edition": "v1",
            "dataset_version": "v1",
        }
        rejected = await client.post(
            f"{ROOT}/recipes",
            headers=admin,
            json={
                **source,
                "name": "合成新菜",
                "record_code": str(uuid4()),
                "cooking_state": "合成",
                "yield_grams": "100",
                "ingredients": [{"food_id": food_id, "grams": "100", "role": "food"}],
            },
        )
        assert rejected.status_code == 409 and rejected.json()["code"] == "knowledge_source_changed"
        for key, value in [("food_id", food_id), ("recipe_version_id", recipe)]:
            portion = await client.post(
                f"{ROOT}/portion-references",
                headers=admin,
                json={
                    **source,
                    key: value,
                    "unit_label": "合成份",
                    "grams_per_unit": "100",
                    "applicable_scope": "仅合成测试",
                },
            )
            assert portion.status_code == 409 and portion.json()["code"] == "knowledge_source_changed", portion.text


async def test_next_day_proposal_retains_snapshot_when_original_changes(health_http):  # noqa: F811
    """提议原件变更走失效映射，不能直接返回计算错误或覆盖历史营养。"""
    client, users = health_http
    owner, admin = users[0]["headers"], users[2]["headers"]
    async with source_document(users[2]["uid"]) as (_, fid, reference):
        member = await create_member(client, owner)
        recipe = await publish_planner_recipe(client, admin, "合成次日来源菜谱", food_source=reference)
        spec = {**plan_spec(recipe), "plan_date": (business_date() + timedelta(days=1)).isoformat()}
        preview = await client.post(f"{ROOT}/members/{member}/meal-plan-previews", headers=owner, json=spec)
        assert preview.status_code == 201, preview.text
        proposed = await client.post(
            f"{ROOT}/members/{member}/next-day-proposals",
            headers=owner,
            json={
                "client_request_id": str(uuid4()),
                "preview_id": preview.json()["preview_id"],
                "source_date": business_date().isoformat(),
            },
        )
        assert proposed.status_code == 201, proposed.text
        initial = proposed.json()
        assert initial["status"] == "proposed"
        async with pg_manager.get_async_session_context() as session:
            await session.execute(
                update(KnowledgeFile).where(KnowledgeFile.file_id == fid).values(content_hash="b" * 64)
            )
        read = await client.get(f"{ROOT}/next-day-proposals/{initial['proposal_id']}", headers=owner)
        assert read.status_code == 200 and read.json()["status"] == "invalidated", read.text
        assert read.json()["reason"] == "source_changed"
        assert read.json()["snapshot"] == initial["snapshot"]

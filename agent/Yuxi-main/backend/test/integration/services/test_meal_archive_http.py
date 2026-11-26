"""真实 TCP 和独立 PostgreSQL schema 验证归档成功、替换和隔离。"""

# ruff: noqa: F401,F811 -- 复用真实 HTTP 与隔离 schema fixture。
from copy import deepcopy
import asyncio
from datetime import date, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import select, text

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
from yuxi.services.daily_meal_plan_service import (
    publish_formal_in_session,
    publish_reference_in_session,
    read_current_plan,
    reserve_reference_request,
)
from yuxi.services.health_consultation_service import require_consultation
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.storage.postgres.models_business import AgentRun, AgentRunRequest, FamilyMember
from yuxi.storage.postgres.models_health import HealthDailyMealPlan, HealthInitialPlanPreview, HealthDailyArrangement
from yuxi.storage_migrations.v039_meal_archive import upgrade_meal_archive

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.fixture(autouse=True)
def archive_image_storage(monkeypatch):
    """归档协议测试使用确定的对象查询，不依赖生产图片存储。"""
    from unittest.mock import AsyncMock
    from yuxi.services import meal_archive_service

    monkeypatch.setattr(meal_archive_service, "stored_recipe_image", AsyncMock(return_value={}), raising=False)


async def test_later_image_appears_in_today_and_legacy_archive_without_rewriting_snapshot(
    family_profile_http, monkeypatch
):
    """真实HTTP和PG验证晚出图、旧归档恢复及首页归档回退共用图片。"""
    from yuxi.services import meal_archive_service, reference_recipe_presentation
    from yuxi.services.meal_archive_projection import archive_meal
    from yuxi.services.recipe_image_identity import recipe_image_key

    generated_recipe_image = reference_recipe_presentation.generated_recipe_image
    current = await setup_reference(family_profile_http, monkeypatch)
    monkeypatch.setattr(reference_recipe_presentation, "generated_recipe_image", generated_recipe_image)
    client, sessions, users, _, _, choice = current
    day = date.fromisoformat(choice["plan_date"])
    root = f"/api/family/{choice['family_id']}/daily-meal-plans"
    dish = {
        "file_id": "synthetic",
        "chunk_id": "synthetic-chunk",
        "name": "合成蒸蛋",
        "ingredients": ["鸡蛋"],
        "steps": ["蒸熟"],
        "source": {"kb_id": "synthetic", "file_id": "synthetic", "file_hash": "immutable"},
    }
    meal = {"meal_type": "breakfast", "dishes": [dish], "members": []}
    key = recipe_image_key(dish)
    arrangement_id = str(uuid4())
    async with sessions.begin() as db:
        db.add(
            HealthDailyArrangement(
                id=arrangement_id,
                actor_uid="self",
                family_id=choice["family_id"],
                plan_date=day,
                version=1,
                status="ready",
                request_id=str(uuid4()),
                selection={},
                sources={},
                snapshot={"version": 1, "meals": [meal]},
            )
        )
        db.add(
            HealthDailyMealPlan(
                id=str(uuid4()),
                actor_uid="self",
                family_id=choice["family_id"],
                plan_date=day,
                is_shared=True,
                version=1,
                pending={},
                archive_meals={"breakfast": archive_meal(meal)},
                meal_sources={
                    "breakfast": {"kind": "formal", "id": arrangement_id, "version": 1},
                    "_roster": {"breakfast": {"status": "pending"}},
                },
            )
        )
    available = set()

    async def lookup(image_key, **kwargs):
        """模拟后台任务完成前后同一对象是否已经存在。"""
        return (
            {"image_url": "/minio/public/" + image_key, "image_source": {"image_role": "ai_generated"}}
            if image_key in available
            else {}
        )

    monkeypatch.setattr(meal_archive_service, "stored_recipe_image", lookup)
    monkeypatch.setattr(reference_recipe_presentation, "stored_recipe_image", lookup)
    first = (await client.get(root, headers=users["self"])).json()["plans"][0]
    assert not first["meals"][0]["dishes"][0].get("image_url")
    available.add(key)
    live_image = (await reference_recipe_presentation.generated_recipe_image(dish))["image_url"]
    saved = (await client.get(root + f"/{day}/archive", headers=users["self"])).json()
    assert saved["meals"][0]["dishes"][0]["image_url"] == live_image
    today = (await client.get(root + f"/{day}", headers=users["self"])).json()
    assert today["meals"][0]["meal"]["dishes"][0]["image_url"] == live_image
    assert "recipe_image_key" not in str(today) and "recipe_image_key" not in str(saved)
    async with sessions.begin() as db:
        row = await db.scalar(
            select(HealthDailyMealPlan).where(
                HealthDailyMealPlan.family_id == choice["family_id"], HealthDailyMealPlan.plan_date == day
            )
        )
        assert not row.archive_meals["breakfast"]["dishes"][0].get("image_url")
        legacy = deepcopy(row.archive_meals)
        for item in legacy["breakfast"]["dishes"]:
            item.pop("recipe_image_key", None)
        row.archive_meals = legacy
    restored = (await client.get(root, headers=users["self"])).json()["plans"][0]
    assert restored["meals"][0]["dishes"][0]["image_url"] == live_image
    async with sessions.begin() as db:
        row = await db.scalar(
            select(HealthDailyMealPlan).where(
                HealthDailyMealPlan.family_id == choice["family_id"], HealthDailyMealPlan.plan_date == day
            )
        )
        assert row.archive_meals == legacy
    assert (await client.get(root, headers=users["other"])).status_code == 404


async def test_archive_reads_do_not_wait_for_family_write_lock(family_profile_http, monkeypatch):
    """换菜持有家庭锁时列表和详情仍返回快照，并拒绝非有效成员。"""
    from yuxi.repositories.family_repository import FamilyRepository

    current = await setup_reference(family_profile_http, monkeypatch)
    client, sessions, users, _, _, choice = current
    day = date.fromisoformat(choice["plan_date"])
    root = f"/api/family/{choice['family_id']}/daily-meal-plans"
    async with sessions.begin() as db:
        await publish_formal_in_session(
            db,
            "self",
            choice["family_id"],
            day,
            SimpleNamespace(
                id=str(uuid4()),
                snapshot={
                    "version": 1,
                    "meals": [
                        {"type": kind, "dishes": [{"name": "合成青菜", "steps": ["煮熟"]}]}
                        for kind in ("breakfast", "lunch", "dinner")
                    ],
                },
            ),
            0,
            None,
        )
    async with sessions.begin() as blocker:
        assert await FamilyRepository(blocker).get_family(choice["family_id"], "self")
        for path in (root, root + f"/{day}/archive"):
            response = await asyncio.wait_for(client.get(path, headers=users["self"]), timeout=2)
            assert response.status_code == 200, response.text
            saved = response.json()["plans"][0] if path == root else response.json()
            assert saved["meals"][0]["dishes"][0]["name"] == "合成青菜"
    for path in (root, root + f"/{day}/archive"):
        assert (await client.get(path, headers=users["other"])).status_code == 404
    async with sessions.begin() as db:
        member = await db.scalar(select(FamilyMember).where(FamilyMember.subject_uid == "self"))
        member.is_active = False
    for path in (root, root + f"/{day}/archive"):
        assert (await client.get(path, headers=users["self"])).status_code == 404


async def test_generated_meals_archive_replace_and_preserve_failed_results(family_profile_http, monkeypatch):
    """成功事务原子收录，未完成和过期生成不能覆盖旧菜谱。"""
    current = await setup_reference(family_profile_http, monkeypatch)
    client, sessions, users, _, _, choice = current
    root = f"/api/family/{choice['family_id']}/daily-meal-plans"
    detail = root + f"/{choice['plan_date']}/archive"

    async def generate(base, meals, replacement=False):
        bound = await bind_reference(current, daily_base_version=base, meal_types=meals)
        assert bound.status_code == 200, bound.text
        context = await running_context(current, bound.json()["thread_id"])
        plan, _, _ = await grounded_plan(current, context, meal_types=meals, replacement=replacement)
        return context, plan

    context, plan = await generate(0, ["breakfast", "lunch", "dinner"])
    assert (await client.get(detail, headers=users["self"])).status_code == 404
    assert (await client.get(root, headers=users["self"])).json()["plans"] == []
    await complete(current, context, plan)
    saved = (await client.get(detail, headers=users["self"])).json()
    assert saved["version"] == 1 and len(saved["meals"]) == 3
    assert all(meal["dishes"][0]["name"] == "清粥" for meal in saved["meals"])
    assert all(set(member) == {"id", "name"} for meal in saved["meals"] for member in meal["members"])
    assert "memberNotes" not in str(saved) and "doctor_instructions" not in str(saved)

    newer, dinner = await generate(1, ["dinner"], True)
    assert (await client.get(detail, headers=users["self"])).json() == saved
    older, stale = await generate(1, ["dinner"], True)
    await complete(current, newer, dinner)
    with pytest.raises(HealthVisionError, match="daily_plan_version_changed"):
        await complete(current, older, stale)
    replaced = (await client.get(detail, headers=users["self"])).json()
    assert replaced["version"] == 2
    assert replaced["meals"][:2] == saved["meals"][:2]
    assert replaced["meals"][2]["dishes"][0]["name"] == "香煎米饼"
    pending, _ = await generate(2, ["dinner"], True)
    for status in ("failed", "cancelled"):
        async with sessions.begin() as db:
            run = await db.get(AgentRun, pending.run_id)
            run.status = status
        assert (await client.get(detail, headers=users["self"])).json() == replaced
    assert len((await client.get(root, headers=users["self"])).json()["plans"]) == 1

    whole_day, new_plan = await generate(2, ["breakfast", "lunch", "dinner"], True)
    await complete(current, whole_day, new_plan)
    replaced = (await client.get(detail, headers=users["self"])).json()
    assert replaced["version"] == 3 and len(replaced["meals"]) == 3
    assert all(meal["dishes"][0]["name"] == "香煎米饼" for meal in replaced["meals"])

    # 历史查询只依赖 PG 展示快照，商城停用不影响已保存菜谱。
    async def unavailable(*args, **kwargs):
        raise AssertionError("archive must not contact commerce")

    monkeypatch.setattr("yuxi.services.reference_meal_plan_service.current_catalog", unavailable)
    assert (await client.get(detail, headers=users["self"])).json() == replaced
    assert (await client.get(detail, headers=users["other"])).status_code in (403, 404)
    member_id = str(uuid4())
    async with sessions.begin() as db:
        db.add(
            FamilyMember(
                id=member_id, family_id=choice["family_id"], subject_uid="other", name="合成家人", relationship="家人"
            )
        )
    assert (await client.get(detail, headers=users["other"])).json() == replaced
    async with sessions.begin() as db:
        (await db.get(FamilyMember, member_id)).is_active = False
    assert (await client.get(detail, headers=users["other"])).status_code in (403, 404)


async def test_archive_migration_backfills_successful_sources_idempotently(family_profile_http, monkeypatch):
    """真实 PostgreSQL 补列、成功来源回填和重复迁移保持原版本。"""
    current = await setup_reference(family_profile_http, monkeypatch)
    client, sessions, users, _, _, choice = current
    bound = await bind_reference(current, daily_base_version=0, meal_types=["breakfast"])
    context = await running_context(current, bound.json()["thread_id"])
    plan, _, _ = await grounded_plan(current, context)
    await complete(current, context, plan)
    async with sessions.begin() as db:
        row = await db.scalar(select(HealthDailyMealPlan))
        expected, version = deepcopy(row.archive_meals), row.version
        await db.execute(text("ALTER TABLE health_daily_meal_plan DROP COLUMN archive_meals"))
    await upgrade_meal_archive(SimpleNamespace(async_engine=sessions.kw["bind"]))
    await upgrade_meal_archive(SimpleNamespace(async_engine=sessions.kw["bind"]))
    async with sessions() as db:
        row = await db.scalar(select(HealthDailyMealPlan))
        assert row.archive_meals == expected and row.version == version

    # 兼容回退代码可能只更新来源；重新上线时即使schema已是39也校准已有归档。
    newer = await bind_reference(current, daily_base_version=1, meal_types=["breakfast"])
    second = await running_context(current, newer.json()["thread_id"])
    replacement, _, _ = await grounded_plan(current, second, replacement=True)
    await complete(current, second, replacement)
    async with sessions.begin() as db:
        row = await db.scalar(select(HealthDailyMealPlan))
        row.archive_meals = expected
    from yuxi.services.recipe_translation_service import translation_key
    from yuxi.storage.postgres.models_health import HealthRecipeTranslation

    async with sessions.begin() as db:
        preview = await db.get(HealthInitialPlanPreview, replacement["preview_id"])
        dish = preview.snapshot["meals"][0]["dishes"][0]
        db.add(
            HealthRecipeTranslation(
                id=translation_key(dish),
                source=dish["source"],
                display={"name": "无效缓存", "ingredients": [], "steps": []},
                producer="synthetic",
                translation_version="recipe-zh-v1",
            )
        )
    await upgrade_meal_archive(SimpleNamespace(async_engine=sessions.kw["bind"]), refresh_existing=True)
    async with sessions() as db:
        row = await db.scalar(select(HealthDailyMealPlan))
        assert "display_zh" not in row.archive_meals["breakfast"]["dishes"][0]
        assert row.version == 2 and row.archive_meals["breakfast"]["dishes"][0]["name"] == "香煎米饼"


async def test_formal_and_reference_share_archive_and_date_pagination(family_profile_http, monkeypatch):
    """不同生成来源统一展示，分页不收录空白或生成中日期。"""
    current = await setup_reference(family_profile_http, monkeypatch)
    client, sessions, users, _, _, choice = current
    day = date.fromisoformat(choice["plan_date"])
    root = f"/api/family/{choice['family_id']}/daily-meal-plans"
    for offset in (0, 1, 2):
        async with sessions.begin() as db:
            arrangement = SimpleNamespace(
                id=str(uuid4()),
                snapshot={
                    "version": 1,
                    "meals": [
                        {"type": kind, "dishes": [{"name": f"合成{offset}", "steps": ["煮熟"]}]}
                        for kind in ("breakfast", "lunch", "dinner")
                    ],
                },
            )
            await publish_formal_in_session(
                db, "self", choice["family_id"], day + timedelta(days=offset), arrangement, 0, None
            )
    first = await client.get(root + "?limit=2", headers=users["self"])
    assert first.status_code == 200, first.text
    assert [row["plan_date"] for row in first.json()["plans"]] == [
        str(day + timedelta(days=2)),
        str(day + timedelta(days=1)),
    ]
    cursor = first.json()["next_before"]
    last = (await client.get(root + f"?limit=2&before={cursor}", headers=users["self"])).json()
    assert [row["plan_date"] for row in last["plans"]] == [str(day)]
    assert last["next_before"] is None
    assert (await client.get(root + "?limit=0", headers=users["self"])).status_code == 422

    # 原安排在重新生成时清空来源快照，首页仍展示与归档相同的最后成功餐次。
    async with sessions() as db:
        home = await read_current_plan("self", choice["family_id"], day, session=db)
    assert len(home["meals"]) == 3
    assert all(meal["purchase_ready"] is False for meal in home["meals"])
    assert home["purchase_options"] == []
    assert home["meals"][0]["meal"] == last["plans"][0]["meals"][0]


async def test_legacy_request_reserves_version_and_rejects_wrong_meal_scope(family_profile_http, monkeypatch):
    """旧线程缺省版本也自动收录，发布范围错误不能改写已保存内容。"""
    import json

    current = await setup_reference(family_profile_http, monkeypatch)
    client, sessions, users, _, _, choice = current
    bound = await bind_reference(current)
    context = await running_context(current, bound.json()["thread_id"])
    async with sessions.begin() as db:
        binding, _ = await require_consultation(db, "self", context.thread_id)
        request = await db.scalar(select(AgentRunRequest).where(AgentRunRequest.request_id == context.request_id))
        await reserve_reference_request(db, "self", binding, request)
    plan, _, _ = await grounded_plan(current, context)
    async with sessions.begin() as db:
        preview = await db.get(HealthInitialPlanPreview, plan["preview_id"])
        original = deepcopy(preview.snapshot)
        wrong = deepcopy(original)
        wrong["meals"][0]["meal_type"] = "dinner"
        preview.snapshot = wrong
    with pytest.raises(HealthVisionError, match="daily_plan_scope_invalid"):
        async with sessions.begin() as db:
            run = await db.get(AgentRun, context.run_id)
            await publish_reference_in_session(db, run, json.dumps({"preview_id": plan["preview_id"]}))
    async with sessions.begin() as db:
        preview = await db.get(HealthInitialPlanPreview, plan["preview_id"])
        preview.snapshot = original
    await complete(current, context, plan)
    result = await client.get(
        f"/api/family/{choice['family_id']}/daily-meal-plans/{choice['plan_date']}/archive", headers=users["self"]
    )
    assert result.status_code == 200, result.text
    assert [meal["meal_type"] for meal in result.json()["meals"]] == ["breakfast"]


async def test_formal_dinner_update_preserves_breakfast_and_lunch(family_profile_http, monkeypatch):
    """同一来源单餐更新时，未请求餐次保持上次成功展示。"""
    current = await setup_reference(family_profile_http, monkeypatch)
    _, sessions, _, _, _, choice = current
    day = date.fromisoformat(choice["plan_date"])
    arrangement = HealthDailyArrangement(
        id=str(uuid4()),
        actor_uid="self",
        family_id=choice["family_id"],
        plan_date=day,
        version=1,
        status="ready",
        request_id=str(uuid4()),
        selection={},
        sources={},
        snapshot={
            "version": 1,
            "meals": [
                {"type": kind, "dishes": [{"name": "上次成功", "steps": ["煮熟"]}]}
                for kind in ("breakfast", "lunch", "dinner")
            ],
        },
    )
    async with sessions.begin() as db:
        db.add(arrangement)
        await db.flush()
        await publish_formal_in_session(db, "self", choice["family_id"], day, arrangement, 0, None)
    arrangement.snapshot = {
        "version": 2,
        "meals": [
            {"type": kind, "dishes": [{"name": "新结果", "steps": ["煮熟"]}]}
            for kind in ("breakfast", "lunch", "dinner")
        ],
    }
    async with sessions.begin() as db:
        db.add(arrangement)
        await db.flush()
        await publish_formal_in_session(db, "self", choice["family_id"], day, arrangement, 1, "dinner")
    async with sessions() as db:
        row = await db.scalar(select(HealthDailyMealPlan))
        assert row.archive_meals["breakfast"]["dishes"][0]["name"] == "上次成功"
        assert row.archive_meals["lunch"]["dishes"][0]["name"] == "上次成功"
        assert row.archive_meals["dinner"]["dishes"][0]["name"] == "新结果"
        assert row.meal_sources["breakfast"]["version"] == 1
        assert row.meal_sources["dinner"]["version"] == 2

        async def authorized(*args, **kwargs):
            return None

        monkeypatch.setattr("yuxi.services.daily_arrangement_service.authorize_sources", authorized)
        home = await read_current_plan("self", choice["family_id"], day, session=db)
        assert home["formal_arrangement"] is None
        assert [m["meal"]["dishes"][0]["name"] for m in home["meals"]] == ["上次成功", "上次成功", "新结果"]

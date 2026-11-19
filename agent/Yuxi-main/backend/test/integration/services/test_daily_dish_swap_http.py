"""真实 HTTP 和 PostgreSQL 验证单菜替换事务，原谱和商城使用合成来源。"""

import copy
import asyncio
from datetime import datetime
from types import SimpleNamespace
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest

from test.integration.services.test_daily_arrangement_http import source
from test.integration.services.test_health_family_profile_http import (  # noqa: F401
    family_profile_http,
    ensure_live_api_schema,
    cleanup_test_sandboxes,
    cleanup_test_knowledge_resources,
)
from yuxi.services import daily_dish_swap_service as swap
from yuxi.services import daily_meal_plan_service as daily
from yuxi.services import reference_meal_plan_service as reference
from yuxi.services import reference_recipe_index as index
from yuxi.services import daily_commerce_service as commerce
from yuxi.services.meal_archive_projection import archive_meal
from yuxi.storage.postgres.models_health import HealthDailyMealPlan

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_replace_only_selected_position_persists_and_replays(family_profile_http, monkeypatch):  # noqa: F811
    """目标之外逐项相等；并发同键只写一次，旧版本和越权写均拒绝。"""
    client, sessions, users = family_profile_http
    family, _, profile, _ = await source(client, users["self"])
    member = profile["members"][0]["member_id"]
    day = datetime.now(ZoneInfo("Asia/Shanghai")).date()
    fid, pid, source_id = family["id"], str(uuid4()), str(uuid4())
    rows = [
        ("spinach", "kb", "家常菜谱_炒菠菜.md", "a" * 64, "c1", "# 炒菠菜\n## 食材\n- 菠菜 100克\n## 做法\n- 炒熟。\n"),
        (
            "broccoli",
            "kb",
            "家常菜谱_炒西兰花.md",
            "b" * 64,
            "c2",
            "# 炒西兰花\n## 食材\n- 西兰花 100克\n## 做法\n- 炒熟。\n",
        ),
    ]
    documents = index.prepare_reference_documents(rows)
    by_id = {
        d["source"]["file_id"]: {**d["source"], "content": d["content"], "chunks_hash": d["chunks_hash"]}
        for d in documents
    }
    people = [{"id": member, "name": "合成本人", "allergens": [], "avoidances": []}]
    anchor_dish = {
        "name": "荷塘月色",
        "file_id": "original",
        "chunk_id": "o",
        "ingredients": ["藕100克"],
        "steps": ["炒熟"],
        "recipe_text_source": "original",
        "source": {"kb_id": "kb", "file_hash": "old", "chunks_hash": "old"},
    }
    other = {**copy.deepcopy(anchor_dish), "name": "菠菜汤", "file_id": "soup", "chunk_id": "s"}
    meals = [
        {"meal_type": meal, "members": people, "dishes": [copy.deepcopy(anchor_dish), copy.deepcopy(other)]}
        for meal in ("breakfast", "lunch", "dinner")
    ]
    original_source = {"meals": meals, "members": people, "plan_date": str(day), "sources": {"family_id": fid}}

    async def read_original(*_args):
        """测试只替代外部 Run 来源；当前餐单读写和事务仍使用真实数据库。"""
        return SimpleNamespace(uid="self"), copy.deepcopy(original_source)

    memory_facts = []

    async def context(_session, uid, family_id, date, meal_type, members):
        """合成成员授权结果供事务测试，家庭访问权限仍由真实服务校验。"""
        return {
            "selection": {
                "family_id": family_id,
                "plan_date": str(date),
                "meal_types": [meal_type],
                "participant_ids": [member],
            },
            "members": people,
            "sources": {
                "family_id": fid,
                "members": {member: {"version": 1}},
                "memory_restrictions": copy.deepcopy(memory_facts),
            },
        }

    async def document(_session, file_id, chunk_id):
        """返回实际参与候选排序的同一合成原文。"""
        if file_id in by_id:
            return copy.deepcopy(by_id[file_id])
        return {**anchor_dish["source"], "file_id": file_id, "chunk_id": chunk_id, "content": "# 原菜谱"}

    async def media(_session, meal):
        """图片生成不属于本次事务测试，保留真实菜品字段。"""
        return copy.deepcopy(meal)

    async def recipe_rows(_session):
        """使用固定的两道合成候选。"""
        return rows

    async def catalog():
        """暂无可购商品，候选仍可展示并保留自备食材缺口。"""
        return {"items": [], "version": "synthetic"}

    monkeypatch.setattr(daily, "read_published_reference_source", read_original)
    monkeypatch.setattr(reference, "recipe_document", document)
    monkeypatch.setattr(reference, "reference_meal_media", media)
    monkeypatch.setattr(swap, "meal_context", context)
    monkeypatch.setattr(index, "reference_recipe_rows", recipe_rows)
    monkeypatch.setattr(commerce, "current_product_catalog", catalog)
    async with sessions.begin() as db:
        db.add(
            HealthDailyMealPlan(
                id=pid,
                actor_uid="self",
                family_id=fid,
                plan_date=day,
                is_shared=True,
                version=1,
                meal_sources={m: {"kind": "reference", "id": source_id} for m in ("breakfast", "lunch", "dinner")},
                archive_meals={meal["meal_type"]: archive_meal(meal) for meal in meals},
                pending={},
            )
        )
    path = f"/api/family/{fid}/daily-meal-plans/{day}"
    before = (await client.get(path, headers=users["self"])).json()
    candidates = await client.get(path + "/dish-swap-candidates?version=1", headers=users["self"])
    assert candidates.status_code == 200, candidates.text
    lunch = next(m for m in candidates.json()["meals"] if m["meal_type"] == "lunch")
    choice = lunch["dishes"][0]
    assert len(choice["candidates"]) == 2
    assert all("snapshot" not in candidate for candidate in choice["candidates"])
    data = {
        "version": 1,
        "meal_type": "lunch",
        "dish_key": choice["dish_key"],
        "candidate_id": choice["candidates"][0]["candidate_id"],
        "client_request_id": str(uuid4()),
    }
    assert (await client.post(path + "/dish-swaps", headers=users["other"], json=data)).status_code == 404
    invalid = {**data, "candidate_id": "f" * 64, "client_request_id": str(uuid4())}
    assert (await client.post(path + "/dish-swaps", headers=users["self"], json=invalid)).status_code == 409
    responses = await asyncio.gather(
        client.post(path + "/dish-swaps", headers=users["self"], json=data),
        client.post(path + "/dish-swaps", headers=users["self"], json=data),
    )
    assert all(result.status_code == 200 for result in responses), [result.text for result in responses]
    assert all(result.json()["version"] == 2 for result in responses)
    after = (await client.get(path, headers=users["self"])).json()
    assert after["version"] == 2
    assert after["meals"][0] == before["meals"][0]
    assert after["meals"][2] == before["meals"][2]
    assert after["meals"][1]["meal"]["dishes"][1] == before["meals"][1]["meal"]["dishes"][1]
    assert after["meals"][1]["meal"]["dishes"][0]["name"] == choice["candidates"][0]["dish"]["name"]
    retry = await client.post(path + "/dish-swaps", headers=users["self"], json=data)
    assert retry.status_code == 200 and retry.json()["version"] == 2
    changed = {**data, "candidate_id": choice["candidates"][1]["candidate_id"]}
    assert (await client.post(path + "/dish-swaps", headers=users["self"], json=changed)).status_code == 409
    stale = {**data, "client_request_id": str(uuid4())}
    assert (await client.post(path + "/dish-swaps", headers=users["self"], json=stale)).status_code == 409
    async with sessions() as db:
        row = await db.get(HealthDailyMealPlan, pid)
        assert row.version == 2
        assert row.meal_sources["breakfast"] == {"kind": "reference", "id": source_id}
        assert (
            row.meal_sources["lunch"]["dish_sources"][1]["dish_key"]
            == before["meals"][1]["meal"]["dishes"][1]["dish_key"]
        )

    memory_facts.append({"id": "fact", "version": 1, "restriction": "牛肉"})
    invalidated = await client.get(path, headers=users["self"])
    assert invalidated.status_code == 200, invalidated.text
    result = invalidated.json()
    assert result["version"] == 2
    assert result["needs_regeneration"] == ["lunch"]
    assert result["regeneration_participants"] == {"lunch": [member]}
    assert result["meals"][0] == after["meals"][0] and result["meals"][2] == after["meals"][2]
    archived = result["meals"][1]
    assert archived["meal_type"] == "lunch" and archived["purchase_ready"] is False
    assert all("origin" not in dish for dish in archived["meal"]["dishes"])
    available = await client.get(path + "/dish-swap-candidates?version=2", headers=users["self"])
    assert available.status_code == 200, available.text
    assert available.json()["needs_regeneration"] == ["lunch"]
    by_meal = {meal["meal_type"]: meal["dishes"] for meal in available.json()["meals"]}
    assert by_meal["lunch"] == []
    assert by_meal["breakfast"][0]["candidates"] and by_meal["dinner"][0]["candidates"]
    refused = await client.post(
        path + "/dish-swaps", headers=users["self"], json={**data, "version": 2, "client_request_id": str(uuid4())}
    )
    assert refused.status_code == 409 and "swap_meal_needs_regeneration" in refused.text
    async with sessions() as db:
        row = await db.get(HealthDailyMealPlan, pid)
        assert row.version == 2 and row.meal_sources["lunch"]["kind"] == "selection"
    memory_facts.clear()
    restored = await client.get(path, headers=users["self"])
    assert restored.status_code == 200 and restored.json()["meals"] == after["meals"]

    async def denied(*_args):
        """权限失败保持拒绝，不伪装为可重排的内容失效。"""
        from yuxi.services.health_vision_types import HealthVisionError

        raise HealthVisionError("member_access_denied", "无权访问成员", 403)

    monkeypatch.setattr(swap, "meal_context", denied)
    assert (await client.get(path, headers=users["self"])).status_code == 403

    monkeypatch.setattr(swap, "meal_context", context)
    memory_facts.append({"id": "fact", "version": 1, "restriction": "牛肉"})
    breakfast_dish = by_meal["breakfast"][0]
    replaced = await client.post(
        path + "/dish-swaps",
        headers=users["self"],
        json={
            "version": 2,
            "meal_type": "breakfast",
            "dish_key": breakfast_dish["dish_key"],
            "candidate_id": breakfast_dish["candidates"][0]["candidate_id"],
            "client_request_id": str(uuid4()),
        },
    )
    assert replaced.status_code == 200, replaced.text
    assert replaced.json()["version"] == 3 and replaced.json()["needs_regeneration"] == ["lunch"]
    async with sessions() as db:
        row = await db.get(HealthDailyMealPlan, pid)
        assert row.meal_sources["breakfast"]["kind"] == "selection"
        assert row.meal_sources["lunch"]["version"] == 2

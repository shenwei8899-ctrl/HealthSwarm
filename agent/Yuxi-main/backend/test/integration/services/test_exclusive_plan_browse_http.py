"""真实 TCP/PG 验证按日协议、缓存回执和来源失效，存储使用精确字节替身。"""

from copy import deepcopy
from datetime import date, timedelta, datetime, UTC
import hashlib
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import select, event, text

from test.integration.services.test_reference_meal_plan_http import (  # noqa: F401
    setup_reference,
    add_recipe,
    family_profile_http,
    ensure_live_api_schema,
    cleanup_test_sandboxes,
    cleanup_test_knowledge_resources,
    isolate_delivery,
)
from yuxi.services import exclusive_plan_browse as browse
from yuxi.services.exclusive_reference_plan import (
    exclusive_reference_context,
    generate_reference_day,
    validate_reference_days,
    REFERENCE_POLICY,
)
from yuxi.storage.postgres.models_health import (
    HealthExclusivePlanGroup,
    HealthExclusiveDayValidation,
    HealthRecipeTranslation,
)
from yuxi.storage.postgres.models_knowledge import KnowledgeFile, KnowledgeChunk
from yuxi.storage.postgres.manager import PostgresManager
from yuxi.services.recipe_translation_service import save_chinese_display, translation_key
from yuxi.services.health_nutrition_service import input_fingerprint
from yuxi.services.health_vision_types import HealthVisionError

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def published(fixture, monkeypatch):
    """用真实原谱和整期验证构造已发布计划，不调用模型或商城。"""
    current = await setup_reference(fixture, monkeypatch)
    client, sessions, users, member, _, selection = current
    for n in range(24):
        await add_recipe(
            current,
            f"browse-{n}",
            f"烹饪菜谱{n}.md",
            f"# 合成蔬菜饭{n}\n## 食材\n- 大米100克\n- 菠菜适量\n## 做法\n1. 加热至熟。",
        )
    fid, gid = selection["family_id"], str(uuid4())
    async with sessions.begin() as db:
        context = await exclusive_reference_context(db, "self", fid, load_documents=True)
        start = date.today()
        entries = []
        catalog = {"items": [], "status": "unavailable", "version": None}
        for n in range(7):
            context["selection"] = context["selection"].model_copy(update={"plan_date": start + timedelta(days=n)})
            entries.append(generate_reference_day(context, "standard", entries, "browse-fixture", catalog))
        await validate_reference_days(db, context, entries)
        db.add(
            HealthExclusivePlanGroup(
                id=gid,
                actor_uid="self",
                family_id=fid,
                request_id=str(uuid4()),
                basis_hash=context["basis_hash"],
                status="ready",
                attempt=1,
                selection={"plan_date":start.isoformat()},
                sources=context["sources"],
                policy=REFERENCE_POLICY,
                progress={"tiers": {tier: deepcopy(entries) for tier in ("economy", "standard", "premium")}},
            )
        )
    gets, heads, queries = [], [], []
    objects = sessions.reference_objects

    def stat(bucket, key):
        """HEAD 不返回原文，旁路覆盖也改变对象版本。"""
        heads.append(key)
        if key not in objects:
            raise FileNotFoundError(key)
        return SimpleNamespace(
            etag=hashlib.sha256(objects[key]).hexdigest(),
            version_id=None,
            size=len(objects[key]),
            last_modified=datetime(2026, 1, 1, tzinfo=UTC),
        )

    async def download(bucket, key):
        """只统计用户实际请求日期的原文读取。"""
        gets.append(key)
        if key not in objects:
            raise FileNotFoundError(key)
        return objects[key]

    monkeypatch.setattr(
        browse,
        "get_minio_client",
        lambda: SimpleNamespace(client=SimpleNamespace(stat_object=stat), adownload_file=download),
    )
    engine = sessions.kw["bind"]

    def count(connection, cursor, statement, parameters, context, many):
        """独立统计来源 SQL 数量，避免用方法调用次数冒充批量查询。"""
        if "knowledge_files" in statement or "knowledge_chunks" in statement:
            queries.append(statement)

    event.listen(engine.sync_engine, "before_cursor_execute", count)
    root = f"/api/health/v1/families/{fid}/exclusive-plans/{gid}"
    return SimpleNamespace(
        client=client,
        sessions=sessions,
        users=users,
        member=member,
        root=root,
        gid=gid,
        actor=current[4],
        fid=fid,
        entries=entries,
        objects=objects,
        gets=gets,
        heads=heads,
        queries=queries,
    )


async def test_directory_day_versions_scope_and_batched_sources(family_profile_http, monkeypatch):  # noqa: F811
    """目录零原文，第一天只下载本日；版本命中不重下载，外部版本不可绕过校验。"""
    h = await published(family_profile_http, monkeypatch)
    # 在此隔离 schema 模拟已有计划从 v40 升级；重复迁移不能改写旧计划。
    engine = h.sessions.kw["bind"]
    async with engine.begin() as conn:
        before = await conn.scalar(text("SELECT progress FROM health_exclusive_plan_group WHERE id=:id"), {"id": h.gid})
        await conn.execute(text("DROP TABLE health_exclusive_day_validation"))
    manager = object.__new__(PostgresManager)
    manager.async_engine, manager._initialized = engine, True
    await manager.create_health_tables()
    await manager.create_health_tables()
    async with engine.connect() as conn:
        assert (
            await conn.scalar(text("SELECT progress FROM health_exclusive_plan_group WHERE id=:id"), {"id": h.gid})
            == before
        )
        assert await conn.scalar(text("SELECT count(*) FROM health_exclusive_day_validation")) == 0
    h.queries.clear()
    headers = h.users["self"]
    path = h.root + "/tiers/standard"
    directory = await h.client.get(path + "/directory", headers=headers)
    assert directory.status_code == 200, directory.text
    assert len(directory.json()["days"]) == 7 and h.gets == [] and h.heads == []
    assert len(h.queries) == 2
    h.queries.clear()
    first = await h.client.get(path + "/days/1", headers=headers)
    assert first.status_code == 200, first.text
    day = first.json()
    assert day["day"]["day_no"] == 1 and day["unchanged"] is False
    expected = {d["file_id"] + ".md" for m in h.entries[0]["meals"] for d in m["dishes"]}
    assert set(h.gets) == expected and len(h.gets) == len(expected)
    assert len(h.queries) == 2
    h.gets.clear()
    again = await h.client.get(path + "/days/1?known_version=" + day["version"], headers=headers)
    assert again.json() == {"unchanged": True, "day_no": 1, "version": day["version"]}
    assert h.gets == []
    async with h.sessions() as db:
        assert (await db.get(HealthExclusiveDayValidation, (h.gid, "standard", 1))).version == day["version"]
    denied = await h.client.get(path + "/days/1?known_version=" + day["version"], headers=h.users["other"])
    assert denied.status_code in (403, 404)
    assert h.gets == []
    summary = await h.client.get(h.root + "?summary=true", headers=headers)
    assert summary.status_code == 200 and len(summary.json()["plans"]) == 3, summary.text
    assert h.gets == []
    async with h.sessions.begin() as db:
        group = await db.get(HealthExclusivePlanGroup, h.gid)
        broken = deepcopy(group.progress)
        broken["tiers"]["standard"][0]["day"]["day_no"] = 22
        group.progress = broken
    incomplete = await h.client.get(path + "/directory", headers=headers)
    assert incomplete.status_code == 409, incomplete.text
    summary = await h.client.get(h.root + "?summary=true", headers=headers)
    assert summary.json()["status"] == "stale" and summary.json()["plans"] == []


@pytest.mark.parametrize("change", ["chunk", "file", "object", "delete", "profile", "permission"])
async def test_changed_sources_cannot_reuse_old_receipt(family_profile_http, monkeypatch, change):  # noqa: F811
    """分片时间不前进、文件失效、对象覆盖/删除和整体依据变化均拒绝旧回执。"""
    h = await published(family_profile_http, monkeypatch)
    headers = h.users["self"]
    path = h.root + "/tiers/standard"
    first = await h.client.get(path + "/days/1", headers=headers)
    assert first.status_code == 200, first.text
    version = first.json()["version"]
    before = (await h.client.get(path + "/directory", headers=headers)).json() if change == "chunk" else None
    h.gets.clear()
    dish = h.entries[0]["meals"][0]["dishes"][0]
    key = dish["file_id"] + ".md"
    if change in ("object", "delete"):
        if change == "object":
            h.objects[key] = b"changed outside database"
        else:
            del h.objects[key]
    else:
        async with h.sessions.begin() as db:
            if change == "chunk":
                chunk = await db.scalar(select(KnowledgeChunk).where(KnowledgeChunk.chunk_id == dish["chunk_id"]))
                old = chunk.updated_at
                chunk.content += "\n版本变化"
                chunk.updated_at = old
            elif change == "file":
                file = await db.scalar(select(KnowledgeFile).where(KnowledgeFile.file_id == dish["file_id"]))
                file.status = "error_indexing"
            elif change == "profile":
                from yuxi.storage.postgres.models_business import FamilyMember

                member = await db.get(FamilyMember, h.actor)
                member.version += 1
            else:
                from yuxi.storage.postgres.models_business import FamilyMember

                actor = await db.get(FamilyMember, h.actor)
                actor.is_active = False
    response = await h.client.get(path + "/days/1?known_version=" + version, headers=headers)
    assert response.status_code in (403, 404, 409, 410), response.text
    if change == "profile":
        assert response.json()["code"] == "plan_basis_changed"
    if change == "chunk":
        after = (await h.client.get(path + "/directory", headers=headers)).json()
        affected = {
            e["day"]["day_no"]
            for e in h.entries
            if any(d["file_id"] == dish["file_id"] for m in e["meals"] for d in m["dishes"])
        }
        assert affected and len(affected) < 21
        for old, new in zip(before["days"], after["days"]):
            assert (old["version"] != new["version"]) == (old["day_no"] in affected)
            assert new["available"] == (old["day_no"] not in affected)
    async with h.sessions() as db:
        assert (await db.get(HealthExclusiveDayValidation, (h.gid, "standard", 1))).version == version


@pytest.mark.parametrize("display_mode", ["translated", "excluded"])
async def test_legacy_english_source_has_translated_or_hidden_display(family_profile_http, monkeypatch, display_mode):  # noqa: F811
    """历史英文原谱仍逐字核验，中文展示可更新，缺译被禁用来源不泄出英文。"""
    h = await published(family_profile_http, monkeypatch)
    original = h.entries[0]["meals"][0]["dishes"][0]
    content = "# Spinach Rice\n## 食材\n- 大米100克\n- 菠菜适量\n## 做法\n1. 加热至熟。"
    raw = content.encode()
    h.objects[original["file_id"] + ".md"] = raw
    async with h.sessions.begin() as db:
        file = await db.scalar(select(KnowledgeFile).where(KnowledgeFile.file_id == original["file_id"]))
        chunk = await db.scalar(select(KnowledgeChunk).where(KnowledgeChunk.chunk_id == original["chunk_id"]))
        file.content_hash, chunk.content = hashlib.sha256(raw).hexdigest(), content
        file.processing_params = {"recipe_search_excluded": display_mode == "excluded"}
        group = await db.get(HealthExclusivePlanGroup, h.gid)
        progress = deepcopy(group.progress)
        for entries in progress["tiers"].values():
            for entry in entries:
                for meal in entry["meals"]:
                    for dish in meal["dishes"]:
                        if dish["file_id"] == file.file_id:
                            dish["name"] = "Spinach Rice"
                            dish["source"]["file_hash"] = file.content_hash
                            dish["source"]["chunks_hash"] = input_fingerprint([(chunk.chunk_id, content)])
        group.progress = progress
        changed = progress["tiers"]["standard"][0]["meals"][0]["dishes"][0]
        if display_mode == "translated":
            await save_chinese_display(
                db,
                changed,
                {
                    "name": "菠菜饭",
                    "ingredients": changed["ingredients"],
                    "steps": changed["steps"],
                    "portion_quote": None,
                    "nutrition_quote": None,
                },
                "synthetic-test",
            )
        await db.flush()
        context = await exclusive_reference_context(db, "self", h.fid, load_documents=False)
        with pytest.raises(HealthVisionError, match="recipe_translation_invalid"):
            await validate_reference_days(db, context, [deepcopy(progress["tiers"]["standard"][0])])
    path = h.root + "/tiers/standard/days/1"
    response = await h.client.get(path, headers=h.users["self"])
    assert response.status_code == 200, response.text
    result = response.json()
    item = next(d for d in result["day"]["meals"] if d["source"]["file_id"] == original["file_id"])
    assert item["recipe_name"] == ("菠菜饭" if display_mode == "translated" else "菜谱暂不可展示")
    if display_mode == "excluded":
        assert item["ingredients"] == [] and item["steps"] == [] and item["recipe_snapshot"] == {}
    else:
        async with h.sessions.begin() as db:
            record = await db.get(HealthRecipeTranslation, translation_key(changed))
            record.display = {**record.display, "name": "新菠菜饭"}
        updated = await h.client.get(path + "?known_version=" + result["version"], headers=h.users["self"])
        assert updated.status_code == 200 and updated.json()["unchanged"] is False, updated.text
        assert "新菠菜饭" in str(updated.json())

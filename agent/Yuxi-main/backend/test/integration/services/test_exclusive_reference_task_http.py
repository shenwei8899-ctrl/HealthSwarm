"""真实 HTTP/PG 和任务 lease 验证菜单发布；仅替代对象存储与商城网络。"""
# ruff: noqa: F401,F811 -- 复用隔离数据库与真实建档 fixture。

from copy import deepcopy
from uuid import uuid4

import pytest
from sqlalchemy import select

from test.integration.services.test_reference_meal_plan_http import (
    setup_reference,
    add_recipe,
    family_profile_http,
    ensure_live_api_schema,
    cleanup_test_sandboxes,
    cleanup_test_knowledge_resources,
    isolate_delivery,
)
from yuxi.repositories.task_repository import TaskRepository
from yuxi.services import exclusive_reference_plan as reference
from yuxi.services.exclusive_plan_service import start_exclusive_plan
from yuxi.services.exclusive_plan_types import ExclusivePlanInput
from yuxi.services.exclusive_plan_generation import TIERS
from yuxi.services.exclusive_plan_tasks import run_exclusive_plan
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.services.task_service import TaskContext
from yuxi.storage.postgres.models_business import TaskRecord, FamilyMember
from yuxi.storage.postgres.models_health import (
    HealthExclusivePlanGroup,
    HealthMemoryFact,
    HealthFamilyProfileLink,
)
from yuxi.storage.postgres.models_knowledge import KnowledgeFile

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_real_task_publishes_and_reads_all_days_without_catalog_or_purchase_mapping(
    family_profile_http, monkeypatch
):
    """断点恢复、完整发布和读取不借助预填ready或跳过来源复核。"""
    current = await setup_reference(family_profile_http, monkeypatch)
    client, sessions, users, mid, actor, selection = current
    notice = (await client.get("/api/service-notice")).json()
    acknowledged = await client.post(
        "/api/account/service-notice",
        headers=users["self"],
        json={"version": notice["version"], "content_hash": notice["content_hash"], "acknowledged": True},
    )
    assert acknowledged.status_code == 200, acknowledged.text
    for number in range(24):
        content = f"# 合成蔬菜饭{number}\n## 食材\n- 大米100克\n- 菠菜适量\n## 做法\n1. 加热至熟。"
        await add_recipe(current, f"exclusive-{number}", f"烹饪菜谱{number}.md", content)

    async def no_catalog():
        raise HealthVisionError("commerce_not_configured", "未接入供应商", 503)

    monkeypatch.setattr(reference, "current_catalog", no_catalog)
    with pytest.raises(HealthVisionError, match="not_found"):
        await start_exclusive_plan(
            "self",
            selection["family_id"],
            ExclusivePlanInput(client_request_id=uuid4()),
            required_member=str(uuid4()),
        )
    path = f"/api/health/v1/families/{selection['family_id']}/exclusive-plans"
    key = str(uuid4())
    response = await client.post(path, headers=users["self"], json={"client_request_id": key})
    assert response.status_code == 200, response.text
    gid = response.json()["group_id"]
    async with sessions() as db:
        task = await db.scalar(select(TaskRecord).where(TaskRecord.type == "exclusive_plan_v1"))
        tid, payload = task.id, deepcopy(task.payload)
    record, claimed = await TaskRepository().claim(tid, worker_id="exclusive-test", lease_seconds=600)
    assert claimed
    context = TaskContext(tid, "exclusive-test", payload)
    original_progress = context.set_progress

    async def pause_after_day(progress, message=None):
        await original_progress(progress, message)
        if progress > 1:
            raise InterruptedError("synthetic process interruption")

    context.set_progress = pause_after_day
    with pytest.raises(InterruptedError):
        await run_exclusive_plan(context)
    async with sessions() as db:
        row = await db.get(HealthExclusivePlanGroup, gid)
        saved_first = deepcopy(row.progress["tiers"]["economy"][0])
        assert row.status == "generating"
        assert row.progress["catalog_snapshot"]["status"] == "unavailable"
    context.set_progress = original_progress
    assert await run_exclusive_plan(context) == {"group_id": gid, "status": "ready"}
    async with sessions() as db:
        row = await db.get(HealthExclusivePlanGroup, gid)
        assert row.status == "ready"
        assert row.progress["tiers"]["economy"][0] == saved_first
        assert all(len(row.progress["tiers"][tier]) == 7 for tier in TIERS)
        assert "tier_costs_cent" not in row.progress and "receipts" not in row.progress
        source_id = saved_first["meals"][0]["dishes"][0]["file_id"]
    group = await client.get(path + "/" + gid, headers=users["self"])
    assert group.status_code == 200, group.text
    assert group.json()["status"] == "ready" and group.json()["completed_days"] == 21
    # 读取原周计划不再依赖阅读当天；跨午夜仍保留最初的第一天。
    from yuxi.services import exclusive_plan_service as plan_service
    from datetime import datetime
    class NoCurrentDate(datetime):
        @classmethod
        def now(cls, tz=None):
            raise AssertionError("读取已保存周计划不能重新选择当天")
    with monkeypatch.context() as clock_patch:
        clock_patch.setattr(plan_service, "datetime", NoCurrentDate)
        unchanged = await client.get(path + "/" + gid, headers=users["self"])
        assert unchanged.status_code == 200, unchanged.text
        assert unchanged.json()["start_date"] == saved_first["day"]["plan_date"]

    # 旧21天参考记录只返回失效提示，原始快照不裁剪也不自动改写。
    legacy_id = str(uuid4())
    async with sessions.begin() as db:
        original = await db.get(HealthExclusivePlanGroup, gid)
        legacy_progress = {"tiers": {"economy": [{"day": {"day_no": n}} for n in range(1, 22)]}}
        db.add(HealthExclusivePlanGroup(id=legacy_id, actor_uid="self", family_id=selection["family_id"], request_id=str(uuid4()), basis_hash="a"*64, status="ready", selection=original.selection, sources=original.sources, policy={"version":"exclusive-reference-v2","hash":"exclusive-reference-v2"}, progress=legacy_progress))
    legacy = await client.get(path + "/" + legacy_id, headers=users["self"])
    assert legacy.status_code == 200 and legacy.json()["status"] == "stale" and not legacy.json()["plans"]
    async with sessions() as db:
        archived = await db.get(HealthExclusivePlanGroup, legacy_id)
        assert archived.progress == legacy_progress and archived.status == "ready"

    for tier in TIERS:
        detail = await client.get(path + f"/{gid}/tiers/{tier}", headers=users["self"])
        assert detail.status_code == 200, detail.text
        data = detail.json()
        assert len(data["days"]) == 7
        assert data["days"][6]["procurement"]["ingredients"]
        assert data["pricing"]["matched_subtotal_cent"] is None
        assert all(gap["reason"] == "catalog_unavailable" for gap in data["pricing"]["unpriced_ingredients"])
    assert (await client.get(path + f"/{gid}/tiers/economy", headers=users["other"])).status_code == 404
    assert group.headers["Cache-Control"] == "no-store"
    assert (await client.post(path, headers=users["self"], json={"client_request_id": key})).json()["group_id"] == gid
    async with sessions.begin() as db:
        link = await db.get(HealthFamilyProfileLink, mid)
        db.add(
            HealthMemoryFact(
                id="new-restriction",
                actor_uid="self",
                member_id=mid,
                fact_key="beef",
                content="我不吃牛肉",
                kind="restriction",
                version=1,
                provenance={
                    "family_id": selection["family_id"],
                    "source_member_id": link.source_member_id,
                    "entity": "牛肉",
                },
            )
        )
    stale_memory = await client.get(path + "/" + gid, headers=users["self"])
    assert stale_memory.status_code == 200 and stale_memory.json()["status"] == "stale", stale_memory.text
    assert (await client.get(path + f"/{gid}/tiers/economy", headers=users["self"])).status_code == 410
    from yuxi.services.exclusive_plan_purchase import read_purchase

    with pytest.raises(HealthVisionError, match="source_invalidated"):
        await read_purchase("self", selection["family_id"], gid, "economy")
    async with sessions.begin() as db:
        fact = await db.get(HealthMemoryFact, "new-restriction")
        fact.status, fact.version = "revoked", 2
    restored = await client.get(path + f"/{gid}/tiers/economy", headers=users["self"])
    assert restored.status_code == 200, restored.text
    async with sessions.begin() as db:
        source = await db.scalar(select(KnowledgeFile).where(KnowledgeFile.file_id == source_id))
        source.content_hash = "changed-source"
    rejected = await client.get(path + f"/{gid}/tiers/economy", headers=users["self"])
    assert rejected.status_code == 410, rejected.text
    async with sessions.begin() as db:
        source = await db.scalar(select(KnowledgeFile).where(KnowledgeFile.file_id == source_id))
        source.status = "pending"
    unavailable = await client.get(path + f"/{gid}/tiers/economy", headers=users["self"])
    assert unavailable.status_code == 410, unavailable.text
    stale = await client.get(path + "/" + gid, headers=users["self"])
    assert stale.status_code == 200 and stale.json()["status"] == "stale", stale.text
    replacement = await client.post(path, headers=users["self"], json={"client_request_id": str(uuid4())})
    assert replacement.status_code == 200 and replacement.json()["group_id"] != gid, replacement.text
    # 升级前已排队的旧参考任务停止补生成；不把它当成正式商城计划导出。
    async with sessions.begin() as db:
        retired = await db.get(HealthExclusivePlanGroup, gid)
        retired.policy = {"version":"exclusive-reference-v2", "hash":"exclusive-reference-v2"}
        retired.status = "generating"
        retired.progress = deepcopy(legacy_progress)
    assert await run_exclusive_plan(context) == {"group_id":gid, "status":"stale"}
    async with sessions() as db:
        retired = await db.get(HealthExclusivePlanGroup, gid)
        assert retired.status == "stale" and retired.progress == legacy_progress

    async with sessions.begin() as db:
        member = await db.get(FamilyMember, actor)
        member.is_active = False
    revoked = await client.get(path + "/" + replacement.json()["group_id"], headers=users["self"])
    assert revoked.status_code in (403, 404, 409), revoked.text

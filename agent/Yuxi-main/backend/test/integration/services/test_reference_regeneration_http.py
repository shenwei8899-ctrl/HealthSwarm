"""真实 HTTP 和独立 PG 验证旧来源失效后可重新发布指定餐次。"""

# ruff: noqa: F401,F811 -- pytest 使用共享的隔离数据库 fixture。
import json
import hashlib
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import select

from test.integration.services.test_reference_meal_plan_http import (
    family_profile_http,
    ensure_live_api_schema,
    cleanup_test_sandboxes,
    cleanup_test_knowledge_resources,
    isolate_delivery,
    setup_reference,
    replace_source,
    bind_reference,
    running_context,
    grounded_plan,
    complete,
    input_for,
)
from yuxi.services.daily_meal_plan_service import reserve_reference_request
from yuxi.services.health_consultation_service import require_consultation
from yuxi.services.health_meal_plan_service import planner_final_result
from yuxi.storage.postgres.models_business import AgentRun, AgentRunRequest, FamilyArchive, Message
from yuxi.utils.datetime_utils import utc_now_naive
from yuxi.storage.postgres.models_health import HealthDailyMealPlan, HealthGrant, HealthProcessingConsent
from yuxi.storage.postgres.models_knowledge import KnowledgeChunk, KnowledgeFile

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]
PRODUCTION_TEXT = "# 清粥\n原食谱供两人食用\n## 食材\n- 大米100克\n## 做法\n1. 加水煮熟"


@pytest.mark.parametrize("legacy", [False, True])
@pytest.mark.parametrize("change", ["family", "recipe"])
async def test_expired_source_can_be_read_and_replaced(family_profile_http, monkeypatch, legacy, change):
    """读取保留原版本，替换结果由发布事务递增，旧正文不泄露。"""
    current = await setup_reference(family_profile_http, monkeypatch)
    await replace_source(current, PRODUCTION_TEXT)
    client, sessions, users, _, _, choice = current
    bound = await bind_reference(current, **({} if legacy else {"daily_base_version": 0}))
    context = await running_context(current, bound.json()["thread_id"])
    original, _, _ = await grounded_plan(current, context)
    await complete(current, context, original)
    async with sessions.begin() as db:
        if change == "family":
            family = await db.get(FamilyArchive, choice["family_id"])
            family.version += 1
        else:
            chunk = await db.scalar(select(KnowledgeChunk))
            chunk.content = chunk.content.replace("原食谱供两人食用", "原食谱供两人食用\n资料版本更新")
            changed_recipe = chunk.content
            file = await db.scalar(select(KnowledgeFile).where(KnowledgeFile.file_id == "reference-file"))
            file.content_hash = hashlib.sha256(changed_recipe.encode()).hexdigest()
    if change == "recipe":
        from yuxi.storage import minio

        async def updated_bytes(bucket, name):
            return changed_recipe.encode()

        monkeypatch.setattr(minio, "get_minio_client", lambda: SimpleNamespace(adownload_file=updated_bytes))
    path = f"/api/family/{choice['family_id']}/daily-meal-plans/{choice['plan_date']}"
    response = await client.get(path, headers=users["self"])
    assert response.status_code == 200, response.text
    plan = response.json()
    assert plan["status"] == "needs_regeneration"
    assert plan["version"] == (0 if legacy else 1)
    assert plan["needs_regeneration"] == ["breakfast"]
    assert plan["regeneration_participants"] == {"breakfast": choice["participant_ids"]}
    assert plan["meals"] == plan["purchase_options"] == []
    assert "大米100克" not in response.text
    async with sessions() as db:
        row = await db.scalar(select(HealthDailyMealPlan))
        assert (row.version if row else 0) == plan["version"]
    assert (await client.get(path, headers=users["other"])).status_code in {403, 404}
    fresh = await bind_reference(current, daily_base_version=plan["version"])
    assert fresh.status_code == 200, fresh.text
    assert fresh.json()["thread_id"] != context.thread_id
    replacement = await running_context(current, fresh.json()["thread_id"])
    async with sessions.begin() as db:
        binding, _ = await require_consultation(db, "self", replacement.thread_id)
        request = await db.scalar(select(AgentRunRequest).where(AgentRunRequest.request_id == replacement.request_id))
        await reserve_reference_request(db, "self", binding, request)
    updated, _, _ = await grounded_plan(current, replacement)
    await complete(current, replacement, updated)
    final = await client.get(path, headers=users["self"])
    assert final.status_code == 200, final.text
    assert final.json()["status"] == "ready"
    assert final.json()["version"] == plan["version"] + 1
    assert final.json()["meals"][0]["source"]["id"] == updated["preview_id"]


async def test_expired_followup_releases_reservation_for_a_fresh_task(family_profile_http, monkeypatch):
    """追问完成后资料变化，当前读取与下一次预占均可恢复。"""
    current = await setup_reference(family_profile_http, monkeypatch)
    await replace_source(current, PRODUCTION_TEXT)
    client, sessions, users, _, _, choice = current
    bound = await bind_reference(current, daily_base_version=0)
    context = await running_context(current, bound.json()["thread_id"])
    async with sessions.begin() as db:
        binding, _ = await require_consultation(db, "self", context.thread_id)
        request = await db.scalar(select(AgentRunRequest).where(AgentRunRequest.request_id == context.request_id))
        await reserve_reference_request(db, "self", binding, request)
    result = await planner_final_result(context, json.dumps({"questions": ["需要避开什么食材？"]}))
    async with sessions.begin() as db:
        run = await db.get(AgentRun, context.run_id)
        message = Message(
            conversation_id=run.conversation_id,
            role="assistant",
            content=json.dumps(result),
            run_id=run.id,
            request_id=run.request_id,
            delivery_status="complete",
        )
        db.add(message)
        await db.flush()
        run.output_message_id, run.status, run.finished_at = message.id, "completed", utc_now_naive()
        family = await db.get(FamilyArchive, choice["family_id"])
        family.version += 1
    path = f"/api/family/{choice['family_id']}/daily-meal-plans/{choice['plan_date']}"
    response = await client.get(path, headers=users["self"])
    assert response.status_code == 200, response.text
    assert response.json()["pending"] is None
    assert response.json()["needs_regeneration"] == ["breakfast"]
    fresh = await bind_reference(current, daily_base_version=0)
    assert fresh.status_code == 200, fresh.text
    replacement = await running_context(current, fresh.json()["thread_id"])
    async with sessions.begin() as db:
        binding, _ = await require_consultation(db, "self", replacement.thread_id)
        request = await db.scalar(select(AgentRunRequest).where(AgentRunRequest.request_id == replacement.request_id))
        await reserve_reference_request(db, "self", binding, request)
        row = await db.scalar(select(HealthDailyMealPlan))
        assert row.pending["request_id"] == replacement.request_id


async def test_saving_identical_profile_preserves_versions(family_profile_http):
    """相同档案使用新请求键保存，也不制造资料版本变化。"""
    client, _, users = family_profile_http
    family, _, body, headers = await input_for(client, users["self"])
    body.pop("processing_consents")
    path = f"/api/family/{family['id']}/miniapp-profile"
    first = await client.post(path, json=body, headers=headers)
    assert first.status_code == 200, first.text
    saved = first.json()
    body["client_request_id"] = str(uuid4())
    body["family_version"] = saved["familyVersion"]
    body["members"][0]["version"] = saved["members"][0]["version"]
    again = await client.post(path, json=body, headers={**users["self"], "Idempotency-Key": body["client_request_id"]})
    assert again.status_code == 200, again.text
    assert again.json()["familyVersion"] == saved["familyVersion"]
    assert again.json()["members"][0]["version"] == saved["members"][0]["version"]


@pytest.mark.parametrize(
    "code,status", [("source_invalidated", 410), ("reference_receipt_invalid", 409), ("not_authorized", 403)]
)
async def test_unclassified_failure_is_not_projected_as_regeneration(family_profile_http, monkeypatch, code, status):
    """未分类拒绝保持原错误，不把来源失效标签作为权限豁免。"""
    from yuxi.services import reference_meal_plan_service as service
    from yuxi.services.health_vision_types import HealthVisionError

    current = await setup_reference(family_profile_http, monkeypatch)
    await replace_source(current, PRODUCTION_TEXT)
    bound = await bind_reference(current, daily_base_version=0)
    context = await running_context(current, bound.json()["thread_id"])
    original, _, _ = await grounded_plan(current, context)
    await complete(current, context, original)

    async def refused(*args):
        """模拟原服务返回未分类拒绝。"""
        raise HealthVisionError(code, "合成拒绝", status)

    monkeypatch.setattr(service, "read_reference_plan_in_session", refused)
    choice = current[-1]
    path = f"/api/family/{choice['family_id']}/daily-meal-plans/{choice['plan_date']}"
    response = await current[0].get(path, headers=current[2]["self"])
    assert response.status_code == status, response.text
    assert response.json()["code"] == code


@pytest.mark.parametrize("revoked", ["consent", "grant"])
async def test_real_revocation_with_changed_sources_is_not_regenerated(family_profile_http, monkeypatch, revoked):
    """来源变化与真实撤权并存时，授权拒绝优先于重新生成。"""
    current = await setup_reference(family_profile_http, monkeypatch)
    await replace_source(current, PRODUCTION_TEXT)
    bound = await bind_reference(current, daily_base_version=0)
    context = await running_context(current, bound.json()["thread_id"])
    original, _, _ = await grounded_plan(current, context)
    await complete(current, context, original)
    async with current[1].begin() as db:
        family = await db.get(FamilyArchive, current[-1]["family_id"])
        family.version += 1
        if revoked == "consent":
            record = await db.get(HealthProcessingConsent, (current[3], "self", "meal_plan"))
        else:
            record = await db.get(HealthGrant, (current[3], "self"))
        assert record is not None
        record.revoked_at = utc_now_naive()
    choice = current[-1]
    response = await current[0].get(
        f"/api/family/{choice['family_id']}/daily-meal-plans/{choice['plan_date']}", headers=current[2]["self"]
    )
    assert response.status_code == (403 if revoked == "consent" else 404), response.text
    assert "needs_regeneration" not in response.text
    assert "大米100克" not in response.text


async def test_deleted_recipe_requires_regeneration_without_exposing_its_body(family_profile_http, monkeypatch):
    """已删除菜谱的完成餐单只返回重生成范围，不返回旧正文。"""
    current = await setup_reference(family_profile_http, monkeypatch)
    await replace_source(current, PRODUCTION_TEXT)
    bound = await bind_reference(current, daily_base_version=0)
    context = await running_context(current, bound.json()["thread_id"])
    original, _, _ = await grounded_plan(current, context)
    await complete(current, context, original)
    async with current[1].begin() as db:
        file = await db.scalar(select(KnowledgeFile).where(KnowledgeFile.file_id == "reference-file"))
        file.status = "deleted"
    choice = current[-1]
    response = await current[0].get(
        f"/api/family/{choice['family_id']}/daily-meal-plans/{choice['plan_date']}", headers=current[2]["self"]
    )
    assert response.status_code == 200, response.text
    assert response.json()["needs_regeneration"] == ["breakfast"]
    assert response.json()["meals"] == []
    assert "大米100克" not in response.text

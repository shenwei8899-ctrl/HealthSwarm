"""隔离 PG 和真实 TCP 验证更正提交、并发、失效及权限。"""

# ruff: noqa: F811 -- pytest 注入导入的隔离 fixture。

import asyncio
import json
from copy import deepcopy
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import select, func, text

from test.integration.services.test_health_diet_analysis_http import confirm_analysis_meal
from test.integration.services.test_health_meal_plan_pagination_http import (  # noqa: F401
    cleanup_test_sandboxes,
    cleanup_test_knowledge_resources,
    ensure_live_api_schema,
    meal_pagination_http,
    revoke_grant,
)
from yuxi.repositories.health_diet_analysis_repository import HealthDietAnalysisRepository
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.storage.postgres.models_health import DietLog, DietLogRevision, NutritionCalculation, VisionDraft
from yuxi.storage.postgres.models_business import Project, Conversation, AgentRun, Message, TOOL_AUDIT_MESSAGE_TYPE

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]
ROOT = "/api/health/v1"


async def test_correction_recalculates_same_id_archives_and_invalidates_all_feedback(meal_pagination_http):
    """150g改成300g：120变240kcal；未知钠保持空，所有账号旧反馈失效。"""
    c = meal_pagination_http
    record, draft_id = await confirm_analysis_meal(
        c.client, c.identities["owner"], c.identities["admin"], c.member, revised=True
    )
    original = deepcopy(record["snapshot"])
    for actor in ("owner", "other"):
        key = str(uuid4())
        response = await c.client.put(
            f"{ROOT}/diet-logs/{record['id']}/feedback",
            headers={**c.identities[actor], "Idempotency-Key": key, "If-Match": '"0"'},
            json={"client_request_id": key, "version": 0, "comment": "合成旧反馈"},
        )
        assert response.status_code == 200, response.text
    analysis_url = f"{ROOT}/members/{c.member}/diet-analysis"
    old = await c.client.post(
        analysis_url, headers=c.identities["owner"], json={"record_id": record["id"], "source_version": 2}
    )
    assert old.status_code == 200
    period_url = f"{ROOT}/members/{c.member}/diet-period-analysis"
    window = {"period_days": 7, "end_date": "2026-10-07"}
    old_period = await c.client.post(period_url, headers=c.identities["owner"], json=window)
    assert old_period.status_code == 200, old_period.text
    payload = correction(record)
    changed = await patch(c, record, payload)
    assert changed.status_code == 200, changed.text
    result = changed.json()
    assert result["id"] == record["id"] and result["source_version"] == 3
    assert result["analysis"]["source"]["source_version"] == 3
    assert result["snapshot"]["nutrition"]["totals"]["energy_kcal"] == "240.00"
    assert result["snapshot"]["nutrition"]["totals"]["sodium_mg"] is None
    new_period = await c.client.post(period_url, headers=c.identities["owner"], json=window)
    assert new_period.json()["nutrition"]["totals"]["energy_kcal"]["recorded_total"] == "240.00"
    assert new_period.json()["feedback"]["count"] == 0
    stale = await c.client.post(
        analysis_url, headers=c.identities["owner"], json={"record_id": record["id"], "source_version": 2}
    )
    assert stale.status_code == 409
    for actor in ("owner", "other"):
        feedback = (await c.client.get(f"{ROOT}/diet-logs/{record['id']}/feedback", headers=c.identities[actor])).json()
        assert feedback["feedback"]["status"] == "invalidated"
        assert feedback["feedback"]["version"] == 2 and feedback["feedback"]["details"] is None
        assert feedback["revisions"][-1]["status"] == "invalidated"
    history = await c.client.get(f"{ROOT}/diet-logs/{record['id']}/revisions", headers=c.identities["owner"])
    assert [r["version"] for r in history.json()["revisions"]] == [2, 3]
    assert history.json()["revisions"][0]["snapshot"] == original
    async with c.sessions() as session:
        draft = await session.get(VisionDraft, draft_id)
        assert draft.version == 2 and draft.payload == original["meal"]
        assert await session.scalar(select(func.count()).select_from(DietLog)) == 1
        with pytest.raises(HealthVisionError) as stale_history:
            await HealthDietAnalysisRepository(session).validate_payload("owner", c.member, old.json())
        assert stale_history.value.code == "version_conflict"
        with pytest.raises(HealthVisionError):
            await HealthDietAnalysisRepository(session).validate_payload("owner", c.member, old_period.json())
    replay = await patch(c, record, payload)
    assert replay.json() == result


async def test_concurrent_corrections_and_old_receipt_never_revert_current(meal_pagination_http):
    """同一版本并发只提交一次；旧收据重试返回当前记录而不复活旧数据。"""
    c = meal_pagination_http
    record, _ = await confirm_analysis_meal(c.client, c.identities["owner"], c.identities["admin"], c.member)
    first, second = correction(record), correction(record)
    responses = await asyncio.gather(patch(c, record, first), patch(c, record, second))
    assert sorted(r.status_code for r in responses) == [200, 409]
    applied = first if responses[0].status_code == 200 else second
    third = correction(record)
    third["expected_version"] = 2
    third["meal"]["items"][0]["grams"] = "450"
    response, concurrent_replay = await asyncio.gather(patch(c, record, third), patch(c, record, third))
    assert response.status_code == 200 and response.json()["source_version"] == 3
    assert concurrent_replay.status_code == 200 and concurrent_replay.json() == response.json()
    replay = await patch(c, record, applied)
    assert replay.json()["source_version"] == 3 and replay.json()["applied_version"] == 2
    assert replay.json()["snapshot"]["nutrition"]["totals"]["energy_kcal"] == "360.00"
    conflict = deepcopy(applied)
    conflict["reason"] = "同键异参"
    assert (await patch(c, record, conflict)).json()["code"] == "idempotency_conflict"
    async with c.sessions() as session:
        assert await session.scalar(select(func.count()).select_from(DietLogRevision)) == 3
        assert await session.scalar(select(func.count()).select_from(NutritionCalculation)) == 3


async def test_rejected_corrections_leave_every_snapshot_unchanged(meal_pagination_http, monkeypatch):
    """缺失未接受、伪造来源、重复项目、越权及头部不一致均不能写入。"""
    c = meal_pagination_http
    record, _ = await confirm_analysis_meal(c.client, c.identities["owner"], c.identities["admin"], c.member)
    invalid = correction(record)
    invalid["accept_incomplete"] = False
    assert (await patch(c, record, invalid)).json()["code"] == "nutrition_incomplete"
    duplicate = correction(record)
    duplicate["meal"]["items"] *= 2
    assert (await patch(c, record, duplicate)).status_code == 422
    forged = correction(record)
    forged["meal"]["photos"] = [{"image_index": 0, "upload_id": str(uuid4()), "upload_page_index": 0}]
    assert (await patch(c, record, forged)).json()["code"] == "evidence_invalid"
    extra = correction(record)
    extra["nutrition"] = {"energy_kcal": "1"}
    assert (await patch(c, record, extra)).status_code == 422
    bad_header = await c.client.patch(
        f"{ROOT}/diet-logs/{record['id']}", headers=c.identities["owner"], json=correction(record)
    )
    assert bad_header.status_code == 422 and bad_header.json()["code"] == "request_key_mismatch"
    await revoke_grant(c, c.member, "admin")
    assert (await patch(c, record, correction(record), actor="admin")).status_code == 404
    denied_history = await c.client.get(f"{ROOT}/diet-logs/{record['id']}/revisions", headers=c.identities["admin"])
    assert denied_history.status_code == 404
    from yuxi.repositories.health_diet_correction_repository import HealthDietCorrectionRepository

    async def fail_after_calculation(*_args):
        """在旧快照和新计算flush后制造明确失败，检查整个事务回滚。"""
        raise HealthVisionError("test_interrupted", "合成事务失败", 503)

    monkeypatch.setattr(HealthDietCorrectionRepository, "active_feedback", fail_after_calculation)
    failed = await patch(c, record, correction(record))
    assert failed.status_code == 503 and failed.json()["code"] == "test_interrupted"
    async with c.sessions() as session:
        current = await session.get(DietLog, record["id"])
        assert current.snapshot == record["snapshot"] and current.version == 1
        assert await session.scalar(select(func.count()).select_from(DietLogRevision)) == 0
        assert await session.scalar(select(func.count()).select_from(NutritionCalculation)) == 1


async def test_schema24_upgrade_preserves_confirmation_version_and_is_repeatable(meal_pagination_http):
    """旧表升级到26，两次正式DDL保留原确认版本并创建选择列和候选表。"""
    from test.integration.services.test_schema_migration_version import _scoped_manager

    c = meal_pagination_http
    record, _ = await confirm_analysis_meal(
        c.client, c.identities["owner"], c.identities["admin"], c.member, revised=True
    )
    async with c.sessions() as session:
        engine = session.bind
    async with engine.begin() as connection:
        await connection.execute(text("DROP TABLE diet_log_revision"))
        await connection.execute(text("ALTER TABLE diet_log DROP COLUMN version"))
        await connection.execute(text("ALTER TABLE health_consultation DROP COLUMN indicator_selection"))
        await connection.execute(text("DROP TABLE nutrition_import_batch"))
    manager = _scoped_manager(engine)
    await manager.create_health_tables()
    await manager.create_health_tables()
    async with c.sessions() as session:
        assert await session.scalar(text("SELECT count(*) FROM nutrition_import_batch")) == 0
        assert (
            await session.scalar(text("SELECT count(*) FROM health_consultation WHERE indicator_selection IS NOT NULL"))
            == 0
        )
        current = await session.get(DietLog, record["id"])
        assert current.version == 2 and current.snapshot == record["snapshot"]
    changed = await patch(c, record, correction(record))
    assert changed.status_code == 200 and changed.json()["source_version"] == 3, changed.text
    await manager.create_health_tables()
    async with c.sessions() as session:
        assert (await session.get(DietLog, record["id"])).version == 3
        assert await session.scalar(select(func.count()).select_from(DietLogRevision)) == 2


async def test_legacy_consultation_receipt_invalidates_even_when_nutrition_is_unchanged(meal_pagination_http):
    """旧工具回执兼容原确认；同内容更正后也不能沿用旧建议或模型输入。"""
    from yuxi.repositories.health_diet_correction_repository import HealthDietCorrectionRepository
    from yuxi.services.health_consultation_service import project_confirmed_record

    c = meal_pagination_http
    record, _ = await confirm_analysis_meal(c.client, c.identities["owner"], c.identities["admin"], c.member)
    async with c.sessions() as session:
        project = Project(
            id=str(uuid4()),
            uid="owner",
            name="合成更正验证",
            selection_status="implicit",
            directory_mode="managed",
            workdir_path="synthetic/correction",
        )
        session.add(project)
        await session.flush()
        conversation = Conversation(
            thread_id=str(uuid4()), uid="owner", agent_id="health-consultation", project_id=project.id
        )
        session.add(conversation)
        await session.flush()
        binding = SimpleNamespace(member_id=c.member, conversation_id=conversation.id)
        run = AgentRun(
            id=str(uuid4()),
            uid="owner",
            agent_slug="health-consultation",
            request_id=str(uuid4()),
            conversation_thread_id=conversation.thread_id,
            runtime_scope_id=conversation.thread_id,
            conversation_id=conversation.id,
            status="completed",
        )
        session.add(run)
        await session.flush()
        projection = project_confirmed_record(await session.get(DietLog, record["id"]), "meal")
        projection.pop("source_version")
        session.add(
            Message(
                conversation_id=conversation.id,
                run_id=run.id,
                request_id=run.request_id,
                role="tool",
                message_type=TOOL_AUDIT_MESSAGE_TYPE,
                execution_status="completed",
                extra_metadata={"tool_name": "get_confirmed_diet"},
                content=json.dumps(
                    {
                        "records": [projection],
                        "full_health_profile_available": False,
                        "personal_meal_plan_available": False,
                    }
                ),
            )
        )
        await session.commit()
        await HealthDietCorrectionRepository(session).validate_consultation_history("owner", binding)
    payload = correction(record)
    payload["meal"] = record["snapshot"]["meal"]
    changed = await patch(c, record, payload)
    assert changed.status_code == 200, changed.text
    async with c.sessions() as session:
        with pytest.raises(HealthVisionError) as stale:
            await HealthDietCorrectionRepository(session).validate_consultation_history("owner", binding)
        assert stale.value.code == "source_invalidated"


def correction(record):
    """独立更正150克为300克，不提交任何营养值。"""
    meal = deepcopy(record["snapshot"]["meal"])
    meal["items"][0]["grams"] = "300"
    return {
        "expected_version": record["source_version"],
        "client_request_id": str(uuid4()),
        "reason": "修正称重",
        "meal": meal,
        "accept_incomplete": True,
    }


async def patch(current, record, payload, *, actor="owner"):
    """真实 TCP 更正同时发送匹配的版本与幂等头。"""
    return await current.client.patch(
        f"{ROOT}/diet-logs/{record['id']}",
        headers={
            **current.identities[actor],
            "If-Match": '"' + str(payload["expected_version"]) + '"',
            "Idempotency-Key": payload["client_request_id"],
        },
        json=payload,
    )

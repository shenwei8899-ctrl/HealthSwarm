"""真实HTTP/PG核对明确角色入口、零持久缺选择及当前执行关联。"""

import json
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from test.integration.services import test_health_vision_http as health_fixture_owner
from test.integration.services.test_health_agent_personal_targets_http import digest
from test.integration.services.test_health_personal_targets_http import import_targets, read_targets
from test.integration.services.test_health_quality_http import setup_quality
from test.integration.services.test_health_vision_http import ROOT, create_member, health_http  # noqa: F401
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_business import (
    AgentRun,
    AgentRunAttempt,
    AgentRunRequest,
    Conversation,
    Department,
    Message,
    Project,
    User,
)
from yuxi.storage.postgres.models_health import (
    FamilyMember,
    FoodRecord,
    HealthConsultation,
    HealthFamilyPlannerPreview,
    HealthInitialPlanPreview,
    HealthMealPlan,
    HealthMealPlanAdoption,
    HealthMealPlanPreview,
    HealthRuleSnapshot,
    HealthProfileSnapshot,
    HealthPurchasePreview,
    HealthQualityCheck,
    HealthSafePlannerPreview,
    NutritionEvidence,
    NutritionEvidenceCitation,
    RecipeVersion,
)

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.fixture(autouse=True)
def verified_task_cleanup(monkeypatch, request):
    """沿既有精确清理Owner执行，再读取本次账号及所有运行关联的零行事实。"""
    original = health_fixture_owner.cleanup_health_test_resources

    async def cleanup_and_verify(identities, department_id):
        uids = [identity["uid"] for identity in identities]
        async with pg_manager.get_async_session_context() as session:
            conversations = list(await session.scalars(select(Conversation.id).where(Conversation.uid.in_(uids))))
            runs = list(await session.scalars(select(AgentRun.id).where(AgentRun.uid.in_(uids))))
        await original(identities, department_id)
        counts = {}
        async with pg_manager.get_async_session_context() as session:
            for model, owner in (
                (User, User.uid),
                (Project, Project.uid),
                (Conversation, Conversation.uid),
                (AgentRunRequest, AgentRunRequest.uid),
                (AgentRun, AgentRun.uid),
                (FamilyMember, FamilyMember.owner_uid),
                (HealthConsultation, HealthConsultation.actor_uid),
                (HealthMealPlan, HealthMealPlan.actor_uid),
                (HealthMealPlanPreview, HealthMealPlanPreview.actor_uid),
                (HealthInitialPlanPreview, HealthInitialPlanPreview.actor_uid),
                (HealthFamilyPlannerPreview, HealthFamilyPlannerPreview.actor_uid),
                (HealthSafePlannerPreview, HealthSafePlannerPreview.actor_uid),
                (HealthPurchasePreview, HealthPurchasePreview.actor_uid),
                (HealthMealPlanAdoption, HealthMealPlanAdoption.actor_uid),
                (HealthQualityCheck, HealthQualityCheck.actor_uid),
                (HealthProfileSnapshot, HealthProfileSnapshot.imported_by),
                (HealthRuleSnapshot, HealthRuleSnapshot.imported_by),
                (NutritionEvidence, NutritionEvidence.published_by),
                (NutritionEvidenceCitation, NutritionEvidenceCitation.actor_uid),
                (RecipeVersion, RecipeVersion.published_by),
                (FoodRecord, FoodRecord.published_by),
            ):
                counts[model.__tablename__] = await session.scalar(
                    select(func.count()).select_from(model).where(owner.in_(uids))
                )
            for model, condition in (
                (Message, Message.conversation_id.in_(conversations)),
                (AgentRunAttempt, AgentRunAttempt.run_id.in_(runs)),
                (Department, Department.id == department_id),
            ):
                counts[model.__tablename__] = await session.scalar(
                    select(func.count()).select_from(model).where(condition)
                )
        assert not any(counts.values()), f"本次精确清理后仍有持久化事实：{counts}"
        report = Path("test/.tmp/health-task-projection/cleanup-readback.jsonl")
        report.parent.mkdir(parents=True, exist_ok=True)
        with report.open("a", encoding="utf-8") as stream:
            stream.write(
                json.dumps(
                    {
                        "test": request.node.nodeid,
                        "uids": uids,
                        "conversation_ids": conversations,
                        "run_ids": runs,
                        "counts": counts,
                    }
                )
                + "\n"
            )

    monkeypatch.setattr(health_fixture_owner, "cleanup_health_test_resources", cleanup_and_verify)
    yield


async def entry(client, headers, member, task_type, *, key=None, selection=None, target_selection=None):
    """入口请求键仅用于线程，后续消息使用独立Request键。"""
    key = key or str(uuid4())
    body = {"task_type": task_type, "client_request_id": key}
    if selection is not None:
        body["selection"] = selection
    if target_selection is not None:
        body["target_selection"] = target_selection
    return await client.post(
        f"{ROOT}/members/{member}/task-entries", headers={**headers, "Idempotency-Key": key}, json=body
    )


async def owned_counts(uid):
    """只统计测试账号持久事实，避免并行账号造成虚假结果。"""
    async with pg_manager.get_async_session_context() as session:
        counts = []
        for model, owner in (
            (Project, Project.uid),
            (Conversation, Conversation.uid),
            (HealthConsultation, HealthConsultation.actor_uid),
            (AgentRunRequest, AgentRunRequest.uid),
            (AgentRun, AgentRun.uid),
        ):
            counts.append(await session.scalar(select(func.count()).select_from(model).where(owner == uid)))
        return counts


async def test_missing_selection_and_external_dependency_create_no_rows(health_http):  # noqa: F811
    """needs_input不消耗幂等键，未知专业/多日用途不生成空运行。"""
    client, users = health_http
    owner = users[0]
    member = await create_member(client, owner["headers"])
    before = await owned_counts(owner["uid"])
    key = str(uuid4())
    for headers in (owner["headers"], {**owner["headers"], "Idempotency-Key": str(uuid4())}):
        rejected = await client.post(
            f"{ROOT}/members/{member}/task-entries",
            headers=headers,
            json={"task_type": "consultation", "client_request_id": key},
        )
        assert rejected.status_code == 422 and rejected.json()["code"] == "request_key_mismatch", rejected.text
    for task_type in (
        "initial_meal_preview",
        "family_meal_revision",
        "safe_meal_revision",
        "quality_check",
        "purchase_requirements",
    ):
        missing = await entry(client, owner["headers"], member, task_type)
        assert missing.status_code == 200, missing.text
        result = missing.json()
        assert result["entry_status"] == "needs_input" and result["reason_code"] == "selection_required"
        assert result["thread_id"] is None and result["request_submit_url"] is None
        assert "request_id" not in result and "run_id" not in result
        assert missing.headers["Cache-Control"] == "no-store"
    for task_type in ("glucose_plan", "multi_day_plan", "automatic_family_coordination"):
        pending = await entry(client, owner["headers"], member, task_type)
        assert pending.status_code == 200 and pending.json()["entry_status"] == "dependency_not_ready", pending.text
    for other in users[1:]:
        assert (await entry(client, other["headers"], member, "initial_meal_preview")).status_code == 404
    assert await owned_counts(owner["uid"]) == before


async def test_analyst_task_entry_keeps_target_owner_binding_and_legacy_mode(health_http):  # noqa: F811
    """当前目标来源由用户选择并持久绑定，无目标保留既有分析入口。"""
    client, users = health_http
    owner = users[0]
    current = await setup_quality(client, users)
    legacy = await entry(client, owner["headers"], current["member"], "diet_analysis")
    assert legacy.status_code == 200 and legacy.json()["entry_status"] == "ready", legacy.text
    unavailable = await entry(
        client,
        owner["headers"],
        current["member"],
        "diet_analysis",
        target_selection={"rule_code": current["rules"]["rule_code"], "rule_version": 1, "profile_version": 1},
    )
    assert unavailable.status_code == 503 and unavailable.json()["code"] == "target_dependencies_not_ready"
    await import_targets(client, users, current)
    target = await read_targets(client, owner["headers"], current)
    assert target.status_code == 200 and target.json()["energy_kcal"] == "330", target.text
    chosen = {"rule_code": current["rules"]["rule_code"], "rule_version": 2, "profile_version": 2}
    key = str(uuid4())
    created = await entry(
        client, owner["headers"], current["member"], "diet_analysis", key=key, target_selection=chosen
    )
    assert created.status_code == 200 and created.json()["entry_status"] == "ready", created.text
    async with pg_manager.get_async_session_context() as session:
        binding = await session.scalar(select(HealthConsultation).where(HealthConsultation.request_id == key))
        assert binding.personal_target_selection == {"selection": chosen, "source_hash": digest(target.json())}
        assert "weight_kg" not in json.dumps(binding.personal_target_selection)
        assert (
            await session.scalar(
                select(func.count()).select_from(AgentRunRequest).where(AgentRunRequest.uid == owner["uid"])
            )
        ) == 0
    replay = await entry(client, owner["headers"], current["member"], "diet_analysis", key=key, target_selection=chosen)
    assert replay.json() == created.json()
    for selected in (None, {**chosen, "profile_version": 1}):
        changed = await entry(
            client, owner["headers"], current["member"], "diet_analysis", key=key, target_selection=selected
        )
        assert changed.status_code == 409 and changed.json()["code"] == "request_conflict", changed.text
    for kind in ("consultation", "meal_preview", "quality_check", "purchase_requirements"):
        mixed = await entry(client, owner["headers"], current["member"], kind, target_selection=chosen)
        assert mixed.status_code == 422, mixed.text
    assert (await client.get(f"{ROOT}/tasks/{key}", headers=owner["headers"])).status_code == 404


async def test_basic_entries_fix_roles_and_do_not_create_requests(health_http):  # noqa: F811
    """客户端仍明确提交既有消息入口，role变化不能重用线程键。"""
    client, users = health_http
    owner = users[0]
    member = await create_member(client, owner["headers"])
    for task_type, slug in (
        ("consultation", "health-consultation"),
        ("meal_preview", "health-meal-planner"),
        ("diet_analysis", "health-diet-analyst"),
    ):
        key = str(uuid4())
        created = await entry(client, owner["headers"], member, task_type, key=key)
        assert created.status_code == 200, created.text
        result = created.json()
        assert result["entry_status"] == "ready" and result["agent_slug"] == slug
        assert result["request_submit_url"] == "/api/agent/runs" and "request_id" not in result
        replay = await entry(client, owner["headers"], member, task_type, key=key)
        assert replay.json() == result
        async with pg_manager.get_async_session_context() as session:
            binding = await session.scalar(select(HealthConsultation).where(HealthConsultation.request_id == key))
            conversation = await session.get(Conversation, binding.conversation_id)
            assert conversation.thread_id == result["thread_id"] and conversation.agent_id == slug
            assert (
                await session.scalar(
                    select(func.count()).select_from(AgentRunRequest).where(AgentRunRequest.uid == owner["uid"])
                )
                == 0
            )
        mismatch = await entry(
            client, owner["headers"], member, "meal_preview" if task_type != "meal_preview" else "consultation", key=key
        )
        assert mismatch.status_code == 409 and mismatch.json()["code"] == "request_conflict", mismatch.text
        assert (await client.get(f"{ROOT}/tasks/{key}", headers=owner["headers"])).status_code == 404


async def test_pending_failed_and_neighbor_run_projection_does_not_read_output(health_http):  # noqa: F811
    """手工PG边界只证明HTTP投影；真正Worker结果另由E2E验收。"""
    client, users = health_http
    owner = users[0]
    member = await create_member(client, owner["headers"])
    created = await entry(client, owner["headers"], member, "consultation")
    assert created.status_code == 200, created.text
    thread, key, run_id = created.json()["thread_id"], str(uuid4()), str(uuid4())
    async with pg_manager.get_async_session_context() as session:
        conversation = await session.scalar(select(Conversation).where(Conversation.thread_id == thread))
        message = Message(conversation_id=conversation.id, request_id=key, role="user", content="合成状态查询")
        session.add(message)
        await session.flush()
        run = AgentRun(
            id=run_id,
            request_id=key,
            uid=owner["uid"],
            agent_slug="health-consultation",
            status="pending",
            conversation_id=conversation.id,
            conversation_thread_id=thread,
            runtime_scope_id=thread,
            input_message_id=message.id,
        )
        session.add(run)
        await session.flush()
        request = AgentRunRequest(
            request_id=key,
            uid=owner["uid"],
            agent_slug="health-consultation",
            conversation_thread_id=thread,
            input_message_id=message.id,
            status="dispatched",
            dispatched_run_id=run_id,
        )
        session.add(request)
    try:
        result = await client.get(f"{ROOT}/tasks/{key}", headers=owner["headers"])
        assert result.status_code == 200, result.text
        payload = result.json()
        assert payload["execution_status"] == "pending" and payload["result"] is None and payload["run_id"] == run_id
        assert payload["run_events_url"] == f"/api/agent/runs/{run_id}/events"
        for other in users[1:]:
            assert (await client.get(f"{ROOT}/tasks/{key}", headers=other["headers"])).status_code == 404
        async with pg_manager.get_async_session_context() as session:
            run = await session.get(AgentRun, run_id)
            run.status, run.error_type, run.error_message = "failed", "provider_error", "private upstream health text"
        failed = await client.get(f"{ROOT}/tasks/{key}", headers=owner["headers"])
        assert failed.status_code == 200 and failed.json()["result"]["code"] == "execution_failed", failed.text
        assert failed.json()["final_message_id"] is None and "private upstream health text" not in failed.text
        neighbor_id, neighbor_key = str(uuid4()), str(uuid4())
        async with pg_manager.get_async_session_context() as session:
            original = await session.get(AgentRun, run_id)
            neighbor = AgentRun(
                id=neighbor_id,
                request_id=neighbor_key,
                uid=owner["uid"],
                agent_slug="health-consultation",
                status="failed",
                conversation_id=original.conversation_id,
                conversation_thread_id=thread,
                runtime_scope_id=thread,
            )
            session.add(neighbor)
            await session.flush()
            request = await session.scalar(select(AgentRunRequest).where(AgentRunRequest.request_id == key))
            request.dispatched_run_id = neighbor_id
        wrong_run = await client.get(f"{ROOT}/tasks/{key}", headers=owner["headers"])
        assert wrong_run.status_code == 410 and wrong_run.json()["code"] == "source_invalidated", wrong_run.text
        async with pg_manager.get_async_session_context() as session:
            request = await session.scalar(select(AgentRunRequest).where(AgentRunRequest.request_id == key))
            request.dispatched_run_id = run_id
            request.conversation_thread_id = str(uuid4())
        stale = await client.get(f"{ROOT}/tasks/{key}", headers=owner["headers"])
        assert stale.status_code == 404 and "private upstream" not in stale.text
        async with pg_manager.get_async_session_context() as session:
            request = await session.scalar(select(AgentRunRequest).where(AgentRunRequest.request_id == key))
            request.conversation_thread_id = thread
        revoked = await client.put(
            f"{ROOT}/members/{member}/grants",
            headers=owner["headers"],
            json={"actor_uid": owner["uid"], "scopes": ["diet_edit", "profile_edit"]},
        )
        assert revoked.status_code == 200, revoked.text
        denied = await client.get(f"{ROOT}/tasks/{key}", headers=owner["headers"])
        assert denied.status_code == 404 and "private upstream" not in denied.text
    finally:
        async with pg_manager.get_async_session_context() as session:
            run = await session.get(AgentRun, run_id)
            run.status = "failed"

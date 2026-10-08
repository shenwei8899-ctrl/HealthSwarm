"""真实HTTP和PG核对家庭线程、全员同意与当前Run只读收据。"""

import json
import asyncio
from copy import deepcopy
from datetime import timedelta
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import select, func

from test.e2e.test_health_consultation_e2e import isolated_health  # noqa: F401
from test.integration.services.test_health_vision_http import ROOT, health_http, create_member  # noqa: F401
from test.integration.services.test_health_family_safe_plan_http import setup_safe_family, selection, assert_original
from yuxi.agents.context import BaseContext
from yuxi.services.health_consultation_service import require_consultation
from yuxi.services.health_family_planner_service import (
    read_family_context_for_run,
    preview_family_for_run,
    validate_family_planner_publication,
    validate_family_planner_tool_payload,
)
from yuxi.services.health_meal_plan_service import planner_final_result, meal_plan_recipes_for_run
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_business import AgentRun, Conversation, AgentRunRequest, Message
from yuxi.storage.postgres.models_health import HealthConsultation, HealthFamilyPlannerPreview, HealthGrant
from yuxi.utils.datetime_utils import utc_now_naive

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]
MODEL = "deterministic-family-meal-plan-20261008"


@pytest_asyncio.fixture
async def family_runtime(isolated_health):  # noqa: F811
    """仅独立合成槽位审批家庭配餐处理方，退出恢复配置和provider。"""
    client, users, configuration, consultation_model = isolated_health
    provider = f"family-planner-replay-{uuid4().hex[:12]}"
    created = await client.post(
        "/api/system/model-providers",
        headers=users[2]["headers"],
        json={
            "provider_id": provider,
            "display_name": "Synthetic family planner only",
            "provider_type": "openai",
            "base_url": "http://api:8772/v1",
            "api_key": "synthetic-family-planner-key",
            "capabilities": ["chat"],
            "enabled_models": [{"id": MODEL, "display_name": "synthetic", "type": "chat", "source": "manual"}],
            "is_enabled": True,
        },
    )
    assert created.status_code == 200, created.text
    try:
        response = await client.put(
            f"{ROOT}/configuration",
            headers=users[2]["headers"],
            json={
                "consultation_model": consultation_model,
                "meal_plan_model": f"{provider}:{MODEL}",
                "policy_version": configuration["policy_version"],
                "cloud_processing_reviewed": True,
            },
        )
        assert response.status_code == 200 and response.json()["meal_plan"]["available"], response.text
        configured = response.json()
        current = await setup_safe_family(client, users)
        consent = {
            "purpose": "meal_plan",
            "accepted": True,
            "processor": configured["meal_plan"]["processor"],
            "policy_version": configured["policy_version"],
        }
        for member in (current["member"], current["second"]):
            saved = await client.post(
                f"{ROOT}/members/{member}/processing-consents", headers=users[0]["headers"], json=consent
            )
            assert saved.status_code == 200, saved.text
        yield client, users, current, consent
    finally:
        # 人工PG边界Run也必须终态且释放lease，避免fixture把测试失败伪装为清理成功。
        async with pg_manager.get_async_session_context() as session:
            runs = list((await session.scalars(select(AgentRun).where(AgentRun.uid == users[0]["uid"]))).all())
            for run in runs:
                if run.worker_id == "synthetic-family-boundary":
                    run.status, run.worker_id, run.lease_expires_at = "failed", None, None
        restored = await client.put(
            f"{ROOT}/configuration",
            headers=users[2]["headers"],
            json={
                "consultation_model": consultation_model,
                "policy_version": configuration["policy_version"],
                "cloud_processing_reviewed": True,
            },
        )
        assert restored.status_code == 200, restored.text
        deleted = await client.delete(f"/api/system/model-providers/{provider}", headers=users[2]["headers"])
        assert deleted.status_code == 200, deleted.text


async def bind_family(client, users, current, **updates):
    """真实HTTP明确选择方案、来源版本和全体成员。"""
    body = {**selection(current), "plan_id": current["plan"], "client_request_id": str(uuid4()), **updates}
    response = await client.post(
        f"{ROOT}/members/{current['member']}/family-meal-planner", headers=users[0]["headers"], json=body
    )
    return response, body


async def seed_family_run(users, thread):
    """真实PG执行Owner验证发布和工具；此helper不冒充worker执行证据。"""
    request_id, run_id = str(uuid4()), str(uuid4())
    async with pg_manager.get_async_session_context() as session:
        binding, snapshot = await require_consultation(session, users[0]["uid"], thread)
        session.add(
            AgentRun(
                id=run_id,
                request_id=request_id,
                uid=users[0]["uid"],
                agent_slug="health-meal-planner",
                conversation_id=binding.conversation_id,
                conversation_thread_id=thread,
                runtime_scope_id=thread,
                worker_id="synthetic-family-boundary",
                status="running",
                lease_expires_at=utc_now_naive() + timedelta(minutes=3),
                input_payload={"health_processing": snapshot},
            )
        )
    return BaseContext(
        uid=users[0]["uid"],
        thread_id=thread,
        request_id=request_id,
        run_id=run_id,
        worker_id="synthetic-family-boundary",
        model=snapshot["model"],
    )


def original_allocations(current):
    """保留真实原共同菜位，仅取分配参数。"""
    return [
        {
            "meal_type": meal["meal_type"],
            "participant_ids": deepcopy(meal["participant_ids"]),
            "dishes": [
                {"dish_index": i, "member_portions": deepcopy(dish["member_portions"])}
                for i, dish in enumerate(meal["dishes"])
            ],
        }
        for meal in current["spec"]["meals"]
    ]


async def test_http_family_selection_is_immutable_and_rejects_missing_consent(family_runtime):
    """漏原成员、跨账号、错版本、错用途和同键改选都不能绑定。"""
    client, users, current, consent = family_runtime
    for changes, expected in (
        ({"profile_versions": {current["member"]: 2}}, 409),
        ({"version": 2}, 410),
        ({"rule_version": 2}, 410),
        ({"profile_versions": {current["member"]: 1, current["second"]: 1}}, 410),
        ({"uid": "forged"}, 422),
    ):
        response, _ = await bind_family(client, users, current, **changes)
        assert response.status_code == expected, response.text
    revoked = await client.post(
        f"{ROOT}/members/{current['second']}/processing-consents",
        headers=users[0]["headers"],
        json={**consent, "accepted": False},
    )
    assert revoked.status_code == 200
    response, body = await bind_family(client, users, current)
    assert response.status_code == 403, response.text
    async with pg_manager.get_async_session_context() as session:
        assert (
            await session.scalar(
                select(HealthConsultation).where(HealthConsultation.request_id == body["client_request_id"])
            )
            is None
        )
    assert (
        await client.post(
            f"{ROOT}/members/{current['second']}/processing-consents", headers=users[0]["headers"], json=consent
        )
    ).status_code == 200
    bound, body = await bind_family(client, users, current)
    assert bound.status_code == 201, bound.text
    same, _ = await bind_family(client, users, current, **body)
    assert same.status_code == 201 and same.json() == bound.json(), same.text
    changed, _ = await bind_family(client, users, current, **{**body, "rule_version": 2})
    assert changed.status_code == 409, changed.text
    legacy = await client.post(
        f"{ROOT}/members/{current['member']}/meal-planner",
        headers=users[0]["headers"],
        json={"client_request_id": body["client_request_id"]},
    )
    assert legacy.status_code == 409, legacy.text
    foreign = await client.post(
        f"{ROOT}/members/{current['member']}/family-meal-planner", headers=users[2]["headers"], json=body
    )
    assert foreign.status_code == 404, foreign.text
    async with pg_manager.get_async_session_context() as session:
        conversation = await session.scalar(
            select(Conversation).where(Conversation.thread_id == bound.json()["thread_id"])
        )
        binding = await session.get(HealthConsultation, conversation.id)
        assert binding.family_planner_selection["selection"] == {
            k: v for k, v in body.items() if k != "client_request_id"
        }
        assert len(binding.family_planner_selection["source_hash"]) == 64
    await assert_original(current)


async def test_pg_fixed_tools_current_receipts_and_history_owner(family_runtime):
    """真实PG手算360kcal，四工具只写Run收据，历史所属Run和最终当前Run分开检查。"""
    client, users, current, _ = family_runtime
    bound, _ = await bind_family(client, users, current)
    assert bound.status_code == 201, bound.text
    context = await seed_family_run(users, bound.json()["thread_id"])
    projected = await read_family_context_for_run(context)
    assert set(projected["member_ids"]) == {current["member"], current["second"]}
    assert projected["plan_snapshot"]["nutrition"]["totals"]["energy_kcal"] == "360.00"
    from yuxi.services.health_initial_planner_service import read_initial_context_for_run, preview_initial_for_run

    for invoke in (read_initial_context_for_run, preview_initial_for_run):
        with pytest.raises(HealthVisionError, match="initial_selection_required"):
            await invoke(context)
    with pytest.raises(HealthVisionError, match="participation_unchanged"):
        await preview_family_for_run(context, "participation", {"allocations": original_allocations(current)})
    allocations = original_allocations(current)
    portions = allocations[0]["dishes"][0]["member_portions"]
    next(p for p in portions if p["member_id"] == current["member"])["grams"] = "55"
    for operation, parameters in (
        ("swap", {"meal_type": "breakfast", "dish_index": 0}),
        ("regeneration", {}),
        ("participation", {"allocations": allocations}),
    ):
        result = await preview_family_for_run(context, operation, parameters)
        assert result["scope"] == "family_saved_plan" and result["operation"] == operation
        assert len(result["member_ids"]) == 2
        if operation == "participation":
            assert result["result"]["plan_snapshot"]["nutrition"]["totals"]["energy_kcal"] == "365.00"
        final = await planner_final_result(context, json.dumps({"preview_id": result["preview_id"]}))
        assert final == result
        async with pg_manager.get_async_session_context() as session:
            run = await session.get(AgentRun, context.run_id)
            await validate_family_planner_publication(session, run, json.dumps(final))
    with pytest.raises(HealthVisionError, match="planner_mode_conflict"):
        await meal_plan_recipes_for_run(context, "")
    async with pg_manager.get_async_session_context() as session:
        original = await session.get(AgentRun, context.run_id)
        original.status, original.worker_id, original.lease_expires_at = "completed", None, None
    other = await seed_family_run(users, context.thread_id)
    with pytest.raises(HealthVisionError, match="planner_receipt_invalid"):
        await planner_final_result(other, json.dumps({"preview_id": result["preview_id"]}))
    async with pg_manager.get_async_session_context() as session:
        binding, _ = await require_consultation(session, context.uid, context.thread_id)
        await validate_family_planner_tool_payload(session, binding, "preview_family_plan_participation", result)
        original = await session.get(AgentRun, context.run_id)
        original.conversation_thread_id = "foreign-thread"
        await session.flush()
        with pytest.raises(HealthVisionError, match="source_invalidated"):
            await validate_family_planner_tool_payload(session, binding, "preview_family_plan_participation", result)
        original.conversation_thread_id = context.thread_id
        for processing in (None, {}, {"model": context.model}):
            original.input_payload = {"health_processing": processing}
            await session.flush()
            with pytest.raises(HealthVisionError, match="policy_changed"):
                await validate_family_planner_publication(session, original, json.dumps(final))
        assert (
            await session.scalar(
                select(func.count())
                .select_from(HealthFamilyPlannerPreview)
                .where(HealthFamilyPlannerPreview.run_id == context.run_id)
            )
            == 3
        )
    await assert_original(current)


@pytest.mark.parametrize("scope", ["ai_use", "diet_edit", "profile_view"])
async def test_http_second_member_revocation_blocks_history_queue_and_pg_publication(family_runtime, scope):
    """第二成员撤权使私有历史、入队、工具和发布拒绝，失败请求不写Message/Run。"""
    client, users, current, _ = family_runtime
    bound, _ = await bind_family(client, users, current)
    assert bound.status_code == 201, bound.text
    context = await seed_family_run(users, bound.json()["thread_id"])
    final = await planner_final_result(context, '{"questions": ["合成：需要补充什么？"]}')
    async with pg_manager.get_async_session_context() as session:
        grant = await session.get(HealthGrant, (current["second"], users[0]["uid"]))
        grant.scopes = [value for value in grant.scopes if value != scope]
    history = await client.get(
        f"/api/agent/thread/{context.thread_id}/requests",
        headers=users[0]["headers"],
        params={"agent_slug": "health-meal-planner"},
    )
    assert history.status_code == 404, history.text
    key = str(uuid4())
    denied = await client.post(
        "/api/agent/runs",
        headers=users[0]["headers"],
        json={
            "agent_slug": "health-meal-planner",
            "thread_id": context.thread_id,
            "query": "synthetic",
            "meta": {"request_id": key},
        },
    )
    assert denied.status_code == 404, denied.text
    with pytest.raises(HealthVisionError, match="not_found"):
        await read_family_context_for_run(context)
    async with pg_manager.get_async_session_context() as session:
        run = await session.get(AgentRun, context.run_id)
        with pytest.raises(HealthVisionError, match="not_found"):
            await validate_family_planner_publication(session, run, json.dumps(final))
        for model in (AgentRun, AgentRunRequest, Message):
            assert await session.scalar(select(model).where(model.request_id == key)) is None


async def test_http_prospective_member_requires_independent_consent_and_scope(family_runtime):
    """拟加入者先明确选定并同意，模型不能自行扩大参与者集合。"""
    client, users, current, consent = family_runtime
    owner, admin = users[0]["headers"], users[2]["headers"]
    third = await create_member(client, owner)
    assert (
        await client.put(
            f"{ROOT}/members/{third}/grants",
            headers=owner,
            json={"actor_uid": users[2]["uid"], "scopes": ["profile_edit"]},
        )
    ).status_code == 200
    profile = {**deepcopy(current["profile"]), "version": 1, "source_version": "v1"}
    assert (
        await client.post(f"{ROOT}/members/{third}/external-profile-versions", headers=admin, json=profile)
    ).status_code == 201
    versions = {current["member"]: 2, current["second"]: 1, third: 1}
    missing, _ = await bind_family(client, users, current, profile_versions=versions)
    assert missing.status_code == 403, missing.text
    assert (
        await client.post(f"{ROOT}/members/{third}/processing-consents", headers=owner, json=consent)
    ).status_code == 200
    bound, _ = await bind_family(client, users, current, profile_versions=versions)
    assert bound.status_code == 201, bound.text
    context = await seed_family_run(users, bound.json()["thread_id"])
    assert set((await read_family_context_for_run(context))["member_ids"]) == set(versions)
    allocations = original_allocations(current)
    allocations[1]["participant_ids"].append(third)
    allocations[1]["dishes"][0]["member_portions"].append({"member_id": third, "grams": "90"})
    result = await preview_family_for_run(context, "participation", {"allocations": allocations})
    assert (
        result["result"]["status"] == "ready"
        and result["result"]["plan_snapshot"]["nutrition"]["totals"]["energy_kcal"] == "450.00"
    )
    foreign = str(uuid4())
    allocations[1]["participant_ids"].append(foreign)
    allocations[1]["dishes"][0]["member_portions"].append({"member_id": foreign, "grams": "90"})
    with pytest.raises(HealthVisionError, match="family_member_not_selected"):
        await preview_family_for_run(context, "participation", {"allocations": allocations})
    await assert_original(current)


async def test_second_member_source_change_blocks_history_model_and_publication(family_runtime):
    """第二成员档案换版即使权限保留，也使原固定线程/模型/checkpoint失效。"""
    from yuxi.services.health_consultation_service import require_consultation_attempt

    client, users, current, _ = family_runtime
    bound, _ = await bind_family(client, users, current)
    assert bound.status_code == 201, bound.text
    context = await seed_family_run(users, bound.json()["thread_id"])
    final = await planner_final_result(context, '{"questions": ["合成问题"]}')
    body = {**deepcopy(current["profile"]), "version": 2, "source_version": "v2"}
    changed = await client.post(
        f"{ROOT}/members/{current['second']}/external-profile-versions", headers=users[2]["headers"], json=body
    )
    assert changed.status_code == 201, changed.text
    history = await client.get(
        f"/api/agent/thread/{context.thread_id}/requests",
        headers=users[0]["headers"],
        params={"agent_slug": "health-meal-planner"},
    )
    assert history.status_code == 404, history.text
    with pytest.raises(HealthVisionError, match="source_invalidated"):
        await require_consultation_attempt(context)
    async with pg_manager.get_async_session_context() as session:
        run = await session.get(AgentRun, context.run_id)
        with pytest.raises(HealthVisionError, match="source_invalidated"):
            await validate_family_planner_publication(session, run, json.dumps(final))


async def test_pg_waiting_member_lock_refreshes_plan_before_quality_owner(family_runtime, monkeypatch):
    """实际PG等待第二把成员锁时改版，锁后拒绝且不会调用可追加锁的质量Owner。"""
    from yuxi.repositories.health_vision_repository import HealthVisionRepository
    from yuxi.services import health_family_planner_service as service
    from yuxi.services.health_family_planner_types import FamilyPlannerSelection
    from yuxi.storage.postgres.models_health import FamilyMember, HealthMealPlan

    _, users, current, _ = family_runtime
    ids = sorted([current["member"], current["second"]])
    waiting, locked = asyncio.Event(), []
    authorize = HealthVisionRepository.authorize

    async def observed(self, member_id, uid, scope, *, lock=False):
        """观察真正PG成员锁进入点，不替代锁或授权行为。"""
        if lock:
            locked.append(member_id)
            if member_id == ids[1]:
                waiting.set()
        return await authorize(self, member_id, uid, scope, lock=lock)

    async def forbidden_quality(*_args, **_kwargs):
        """失效计划若进入质量Owner会在错误原因上失败。"""
        pytest.fail("锁后失效计划不能进入会追加成员锁的质量Owner")

    monkeypatch.setattr(HealthVisionRepository, "authorize", observed)
    monkeypatch.setattr(service, "quality_context_in_session", forbidden_quality)
    selected = FamilyPlannerSelection.model_validate({**selection(current), "plan_id": current["plan"]})

    async def read():
        async with pg_manager.get_async_session_context() as session:
            return await service.family_planner_context_in_session(
                session, users[0]["uid"], current["member"], selected
            )

    task = None
    try:
        async with pg_manager.get_async_session_context() as writer:
            await writer.scalar(select(FamilyMember).where(FamilyMember.id == ids[1]).with_for_update())
            task = asyncio.create_task(read())
            await asyncio.wait_for(waiting.wait(), 10)
            assert not task.done()
            plan = await writer.get(HealthMealPlan, current["plan"])
            plan.version = 2
            altered = deepcopy(plan.spec)
            altered["meals"][0]["participant_ids"].append("00000000-0000-0000-0000-000000000001")
            plan.spec = altered
        with pytest.raises(HealthVisionError, match="source_invalidated"):
            await asyncio.wait_for(task, 15)
        assert locked == ids
    finally:
        if task is not None and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)


@pytest.mark.parametrize("change", ["missing_snapshot", "forged_output", "expired_lease"])
async def test_pg_message_publication_rolls_back_without_graph_precheck(family_runtime, change):
    """直接调用实际Message发布Owner，坏审批/正文使写入和Run终态一起回滚。"""
    from types import SimpleNamespace
    from langchain_core.messages import AIMessage
    from yuxi.repositories.conversation_repository import ConversationRepository
    from yuxi.services.chat_service import save_messages_from_langgraph_state

    client, users, current, _ = family_runtime
    bound, _ = await bind_family(client, users, current)
    assert bound.status_code == 201, bound.text
    context = await seed_family_run(users, bound.json()["thread_id"])
    final = await planner_final_result(context, '{"questions": ["合成问题"]}')
    if change == "missing_snapshot":
        async with pg_manager.get_async_session_context() as session:
            (await session.get(AgentRun, context.run_id)).input_payload = {}
    elif change == "forged_output":
        final["professional_review"] = "approved"
    else:
        async with pg_manager.get_async_session_context() as session:
            (await session.get(AgentRun, context.run_id)).lease_expires_at = utc_now_naive() - timedelta(seconds=1)
    error, reason = (
        (ValueError, "lease owner")
        if change == "expired_lease"
        else (HealthVisionError, "policy_changed" if change == "missing_snapshot" else "source_invalidated")
    )
    with pytest.raises(error, match=reason):
        async with pg_manager.get_async_session_context() as session:
            await save_messages_from_langgraph_state(
                SimpleNamespace(values={"messages": [AIMessage(id=str(uuid4()), content=json.dumps(final))]}),
                context.thread_id,
                ConversationRepository(session),
                run_id=context.run_id,
                request_id=context.request_id,
                worker_id=context.worker_id,
                complete_run=True,
            )
    async with pg_manager.get_async_session_context() as session:
        run = await session.get(AgentRun, context.run_id)
        assert run.status == "running" and run.output_message_id is None
        assert (
            await session.scalar(select(Message).where(Message.run_id == run.id, Message.role == "assistant")) is None
        )


@pytest.mark.parametrize("stage", ["authorization", "preview"])
async def test_pg_lease_expiring_during_member_wait_or_preview_cannot_write_receipt(family_runtime, monkeypatch, stage):
    """真实时间到期分别发生在成员等待或预览计算后，两个写入窗口均拒绝。"""
    from yuxi.repositories.health_vision_repository import HealthVisionRepository
    from yuxi.services import health_family_planner_service as service
    from yuxi.storage.postgres.models_health import FamilyMember

    client, users, current, _ = family_runtime
    bound, _ = await bind_family(client, users, current)
    assert bound.status_code == 201, bound.text
    context = await seed_family_run(users, bound.json()["thread_id"])
    deadline = utc_now_naive() + timedelta(seconds=3)
    async with pg_manager.get_async_session_context() as session:
        (await session.get(AgentRun, context.run_id)).lease_expires_at = deadline
    reached, last = asyncio.Event(), sorted([current["member"], current["second"]])[-1]
    original_authorize = HealthVisionRepository.authorize
    original_preview = service.family_preview_in_session

    async def observed(self, member_id, uid, scope, *, lock=False):
        """真实成员锁前报告位置，授权和锁均由原Owner执行。"""
        if lock and member_id == last:
            reached.set()
        return await original_authorize(self, member_id, uid, scope, lock=lock)

    async def delayed(*args, **kwargs):
        """先跑真实预览，模拟搜索在已持Run锁时耗尽剩余lease。"""
        result = await original_preview(*args, **kwargs)
        await asyncio.sleep(max(0, (deadline - utc_now_naive()).total_seconds()) + 0.1)
        return result

    if stage == "authorization":
        monkeypatch.setattr(HealthVisionRepository, "authorize", observed)
    else:
        monkeypatch.setattr(service, "family_preview_in_session", delayed)
    task = None
    try:
        if stage == "authorization":
            async with pg_manager.get_async_session_context() as holder:
                await holder.scalar(select(FamilyMember).where(FamilyMember.id == last).with_for_update())
                task = asyncio.create_task(preview_family_for_run(context, "regeneration", {}))
                await asyncio.wait_for(reached.wait(), 2)
                assert not task.done()
                await asyncio.sleep(max(0, (deadline - utc_now_naive()).total_seconds()) + 0.1)
            with pytest.raises(HealthVisionError, match="execution_not_owned"):
                await asyncio.wait_for(task, 10)
        else:
            with pytest.raises(HealthVisionError, match="execution_not_owned"):
                await preview_family_for_run(context, "regeneration", {})
        async with pg_manager.get_async_session_context() as session:
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(HealthFamilyPlannerPreview)
                    .where(HealthFamilyPlannerPreview.run_id == context.run_id)
                )
                == 0
            )
    finally:
        if task is not None and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

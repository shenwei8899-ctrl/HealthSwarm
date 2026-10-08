"""独立合成槽位的初始线程、全员门禁与PG发布验证。"""

import asyncio
import json
from copy import deepcopy
from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
import pytest_asyncio
from langchain_core.messages import AIMessage
from sqlalchemy import func, select

from test.e2e.test_health_consultation_e2e import isolated_health  # noqa: F401
from test.integration.services.test_health_vision_http import ROOT, health_http  # noqa: F401
from test.integration.services.test_health_initial_meal_plan_http import setup_initial, selection, save, assert_no_plan
from test.integration.services.test_health_family_planner_http import seed_family_run
from yuxi.repositories.conversation_repository import ConversationRepository
from yuxi.services.chat_service import save_messages_from_langgraph_state
from yuxi.services.health_consultation_service import require_consultation, require_consultation_attempt
from yuxi.services.health_initial_planner_service import (
    read_initial_context_for_run,
    preview_initial_for_run,
    validate_initial_planner_publication,
    validate_initial_planner_tool_payload,
)
from yuxi.services.health_meal_plan_service import planner_final_result, meal_plan_recipes_for_run
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_business import AgentRun, AgentRunRequest, Message, Conversation
from yuxi.storage.postgres.models_health import (
    HealthConsultation,
    HealthInitialPlanPreview,
    HealthGrant,
    HealthMealPlan,
    HealthProfessionalReview,
    RecipeVersion,
)
from yuxi.utils.datetime_utils import utc_now_naive

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]
MODEL = "deterministic-initial-meal-plan-20261008"


@pytest_asyncio.fixture
async def initial_runtime(isolated_health):  # noqa: F811
    """审批隔离回放与初始目录，无旧Plan，结束恢复全部配置。"""
    client, users, configuration, consultation_model = isolated_health
    provider = f"initial-planner-replay-{uuid4().hex[:12]}"
    created = await client.post(
        "/api/system/model-providers",
        headers=users[2]["headers"],
        json={
            "provider_id": provider,
            "display_name": "Synthetic initial planner only",
            "provider_type": "openai",
            "base_url": "http://api:8773/v1",
            "api_key": "synthetic-initial-planner-key",
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
        current = await setup_initial(client, users)
        consent = {
            "purpose": "meal_plan",
            "accepted": True,
            "processor": configured["meal_plan"]["processor"],
            "policy_version": configured["policy_version"],
        }
        for mid in (current["member"], current["second"]):
            response = await client.post(
                f"{ROOT}/members/{mid}/processing-consents", headers=users[0]["headers"], json=consent
            )
            assert response.status_code == 200, response.text
        yield client, users, current, consent
    finally:
        async with pg_manager.get_async_session_context() as session:
            for run in (await session.scalars(select(AgentRun).where(AgentRun.uid == users[0]["uid"]))).all():
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


async def bind_initial(client, users, current, *, family=True, **updates):
    """真实HTTP固定日期、范围、餐次及来源版本。"""
    body = {**selection(current, family=family), "client_request_id": str(uuid4()), **updates}
    response = await client.post(
        f"{ROOT}/members/{current['member']}/initial-meal-planner", headers=users[0]["headers"], json=body
    )
    return response, body


async def test_initial_binding_immutable_and_all_member_consent(initial_runtime):
    """缺同意无绑定，同键重放不变，跨账号和跨模式均拒绝。"""
    client, users, current, consent = initial_runtime
    rejected, _ = await bind_initial(client, users, current, uid="forged")
    assert rejected.status_code == 422, rejected.text
    response = await client.post(
        f"{ROOT}/members/{current['second']}/processing-consents",
        headers=users[0]["headers"],
        json={**consent, "accepted": False},
    )
    assert response.status_code == 200
    rejected, body = await bind_initial(client, users, current)
    assert rejected.status_code == 403, rejected.text
    async with pg_manager.get_async_session_context() as session:
        assert (
            await session.scalar(
                select(HealthConsultation).where(HealthConsultation.request_id == body["client_request_id"])
            )
            is None
        )
    response = await client.post(
        f"{ROOT}/members/{current['second']}/processing-consents", headers=users[0]["headers"], json=consent
    )
    assert response.status_code == 200
    bound, body = await bind_initial(client, users, current)
    assert bound.status_code == 201, bound.text
    same, _ = await bind_initial(client, users, current, **body)
    assert same.status_code == 201 and same.json() == bound.json(), same.text
    changed, _ = await bind_initial(client, users, current, **{**body, "plan_date": "2026-10-09"})
    assert changed.status_code == 409, changed.text
    legacy = await client.post(
        f"{ROOT}/members/{current['member']}/meal-planner",
        headers=users[0]["headers"],
        json={"client_request_id": body["client_request_id"]},
    )
    assert legacy.status_code == 409, legacy.text
    foreign = await client.post(
        f"{ROOT}/members/{current['member']}/initial-meal-planner", headers=users[2]["headers"], json=body
    )
    assert foreign.status_code == 404, foreign.text
    async with pg_manager.get_async_session_context() as session:
        conversation = await session.scalar(
            select(Conversation).where(Conversation.thread_id == bound.json()["thread_id"])
        )
        binding = await session.get(HealthConsultation, conversation.id)
        expected_selection = {k: deepcopy(v) for k, v in body.items() if k != "client_request_id"}
        for meal in expected_selection["meals"]:
            meal["participant_ids"].sort()
        assert binding.initial_planner_selection["selection"] == expected_selection
        assert binding.family_planner_selection is None and len(binding.initial_planner_selection["source_hash"]) == 64
    await assert_no_plan(users[0]["uid"])


async def test_generic_mode_cannot_use_initial_tools(initial_runtime):
    """通用线程不能从替代调用路径进入批准初始生成。"""
    client, users, current, _ = initial_runtime
    bound = await client.post(
        f"{ROOT}/members/{current['member']}/meal-planner",
        headers=users[0]["headers"],
        json={"client_request_id": str(uuid4())},
    )
    assert bound.status_code == 201, bound.text
    context = await seed_family_run(users, bound.json()["thread_id"])
    for invoke in (read_initial_context_for_run, preview_initial_for_run):
        with pytest.raises(HealthVisionError, match="initial_selection_required"):
            await invoke(context)
    await assert_no_plan(users[0]["uid"])


@pytest.mark.parametrize("family", [False, True])
async def test_initial_current_receipt_history_and_explicit_save(initial_runtime, family):
    """330/396独立手算，本Run只读；历史原Run有效而跨Run最终拒绝。"""
    client, users, current, _ = initial_runtime
    bound, _ = await bind_initial(client, users, current, family=family)
    assert bound.status_code == 201, bound.text
    context = await seed_family_run(users, bound.json()["thread_id"])
    projected = await read_initial_context_for_run(context)
    assert len(projected["profiles"]) == (2 if family else 1)
    assert projected["full_health_profile_available"] is False
    result = await preview_initial_for_run(context)
    assert result["status"] == "ready" and result["plan_snapshot"]["nutrition"]["totals"]["energy_kcal"] == (
        "396.00" if family else "330.00"
    )
    final = await planner_final_result(context, json.dumps({"preview_id": result["preview_id"]}))
    assert final == result
    with pytest.raises(HealthVisionError, match="planner_mode_conflict"):
        await meal_plan_recipes_for_run(context, "")
    await assert_no_plan(users[0]["uid"])
    async with pg_manager.get_async_session_context() as session:
        run = await session.get(AgentRun, context.run_id)
        await validate_initial_planner_publication(session, run, json.dumps(final))
        run.status, run.worker_id, run.lease_expires_at = "completed", None, None
    other = await seed_family_run(users, context.thread_id)
    with pytest.raises(HealthVisionError, match="planner_receipt_invalid"):
        await planner_final_result(other, json.dumps({"preview_id": result["preview_id"]}))
    async with pg_manager.get_async_session_context() as session:
        binding, _ = await require_consultation(session, context.uid, context.thread_id)
        await validate_initial_planner_tool_payload(session, binding, "preview_initial_meal_plan", result)
        original = await session.get(AgentRun, context.run_id)
        original.conversation_thread_id = "foreign-thread"
        await session.flush()
        with pytest.raises(HealthVisionError, match="source_invalidated"):
            await validate_initial_planner_tool_payload(session, binding, "preview_initial_meal_plan", result)
        original.conversation_thread_id = context.thread_id
    saved = await save(client, users[0]["headers"], current, result["preview_id"])
    assert saved.status_code == 201 and saved.json()["quality_check"]["safety_check"]["status"] == "passed", saved.text
    async with pg_manager.get_async_session_context() as session:
        plan = await session.get(HealthMealPlan, saved.json()["plan_id"])
        review = await session.scalar(
            select(HealthProfessionalReview).where(
                HealthProfessionalReview.check_id == saved.json()["quality_check"]["check_id"]
            )
        )
        assert plan.version == 1 and review.status == "draft"


@pytest.mark.parametrize("change", ["ai_use", "diet_edit", "profile_view", "consent"])
async def test_initial_second_member_revocation_all_paths(initial_runtime, change):
    """第二成员撤回同时阻止历史、入队、模型、工具及发布，失败零消息。"""
    client, users, current, consent = initial_runtime
    bound, _ = await bind_initial(client, users, current)
    assert bound.status_code == 201, bound.text
    context = await seed_family_run(users, bound.json()["thread_id"])
    final = await planner_final_result(context, '{"questions":["合成问题"]}')
    if change == "consent":
        denied = await client.post(
            f"{ROOT}/members/{current['second']}/processing-consents",
            headers=users[0]["headers"],
            json={**consent, "accepted": False},
        )
        assert denied.status_code == 200
    else:
        async with pg_manager.get_async_session_context() as session:
            grant = await session.get(HealthGrant, (current["second"], users[0]["uid"]))
            original_scopes = list(grant.scopes)
            grant.scopes = [s for s in grant.scopes if s != change]
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
    assert denied.status_code == (403 if change == "consent" else 404), denied.text
    reason = "consent_required" if change == "consent" else "not_found"
    for invoke in (read_initial_context_for_run, require_consultation_attempt):
        with pytest.raises(HealthVisionError, match=reason):
            await invoke(context)
    async with pg_manager.get_async_session_context() as session:
        with pytest.raises(HealthVisionError, match=reason):
            await validate_initial_planner_publication(
                session, await session.get(AgentRun, context.run_id), json.dumps(final)
            )
        for model in (AgentRun, AgentRunRequest, Message):
            assert await session.scalar(select(model).where(model.request_id == key)) is None
    if change == "consent":
        assert (
            await client.post(
                f"{ROOT}/members/{current['second']}/processing-consents", headers=users[0]["headers"], json=consent
            )
        ).status_code == 200
    else:
        async with pg_manager.get_async_session_context() as session:
            (await session.get(HealthGrant, (current["second"], users[0]["uid"]))).scopes = original_scopes
    assert (await read_initial_context_for_run(context))["scope"] == "initial_plan"
    await assert_no_plan(users[0]["uid"])


@pytest.mark.parametrize("change", ["profile", "rules", "recipe", "payload"])
async def test_initial_changed_source_and_forged_receipt(initial_runtime, change):
    """换来源及篡改持久化内容使旧线程或回执拒绝，正式初版保持零。"""
    client, users, current, _ = initial_runtime
    bound, _ = await bind_initial(client, users, current)
    assert bound.status_code == 201, bound.text
    context = await seed_family_run(users, bound.json()["thread_id"])
    result = await preview_initial_for_run(context)
    if change in {"profile", "rules"}:
        body = {**deepcopy(current[change]), "version": 2, "source_version": "v2"}
        path = (
            f"{ROOT}/members/{current['second']}/external-profile-versions"
            if change == "profile"
            else f"{ROOT}/approved-quality-rules"
        )
        updated = await client.post(path, headers=users[2]["headers"], json=body)
        assert updated.status_code == 201, updated.text
    else:
        async with pg_manager.get_async_session_context() as session:
            if change == "recipe":
                row = await session.get(RecipeVersion, current["recipe"])
                row.nutrients = {**row.nutrients, "energy_kcal": "111"}
            else:
                row = await session.get(HealthInitialPlanPreview, result["preview_id"])
                row.snapshot = {**deepcopy(row.snapshot), "professional_review": "approved"}
    with pytest.raises(HealthVisionError, match="source_invalidated"):
        await planner_final_result(context, json.dumps({"preview_id": result["preview_id"]}))
    async with pg_manager.get_async_session_context() as session:
        with pytest.raises(HealthVisionError, match="source_invalidated"):
            await validate_initial_planner_publication(
                session, await session.get(AgentRun, context.run_id), json.dumps(result)
            )
    await assert_no_plan(users[0]["uid"])


async def test_initial_unmatched_approved_menu_is_read_only_not_ready(initial_runtime):
    """批准目录没有匹配人群时保存未就绪回执，显式确认也拒绝。"""
    client, users, current, _ = initial_runtime
    rules = deepcopy(current["rules"])
    rules.update(version=2, source_version="v2")
    rules["payload"]["allowed_population_codes"].append("synthetic_other")
    rules["payload"]["meal_generation"]["profile_menus"][0]["population_code"] = "synthetic_other"
    response = await client.post(f"{ROOT}/approved-quality-rules", headers=users[2]["headers"], json=rules)
    assert response.status_code == 201, response.text
    bound, _ = await bind_initial(client, users, current, rule_version=2)
    assert bound.status_code == 201, bound.text
    context = await seed_family_run(users, bound.json()["thread_id"])
    result = await preview_initial_for_run(context)
    assert result["status"] == "not_ready" and result["reason"] == "profile_menu_not_approved"
    assert "plan_snapshot" not in result
    assert await planner_final_result(context, json.dumps({"preview_id": result["preview_id"]})) == result
    denied = await save(client, users[0]["headers"], current, result["preview_id"])
    assert denied.status_code == 409 and denied.json()["code"] == "initial_plan_not_ready", denied.text
    await assert_no_plan(users[0]["uid"])


@pytest.mark.parametrize("change", ["missing_snapshot", "forged_output", "expired_lease"])
async def test_initial_actual_message_owner_rolls_back(initial_runtime, change):
    """直接Message事务Owner拒绝坏快照/正文/租约，不依赖graph前置检查。"""
    client, users, current, _ = initial_runtime
    bound, _ = await bind_initial(client, users, current)
    assert bound.status_code == 201, bound.text
    context = await seed_family_run(users, bound.json()["thread_id"])
    final = await planner_final_result(context, '{"questions":["合成问题"]}')
    async with pg_manager.get_async_session_context() as session:
        run = await session.get(AgentRun, context.run_id)
        processing = deepcopy(run.input_payload)
        if change == "missing_snapshot":
            run.input_payload = {}
        elif change == "expired_lease":
            run.lease_expires_at = utc_now_naive() - timedelta(seconds=1)
    if change == "forged_output":
        final["professional_review"] = "approved"
    reason = (
        "lease owner"
        if change == "expired_lease"
        else "policy_changed"
        if change == "missing_snapshot"
        else "source_invalidated"
    )
    with pytest.raises(ValueError if change == "expired_lease" else HealthVisionError, match=reason):
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
        run.input_payload = processing
        run.lease_expires_at = utc_now_naive() + timedelta(minutes=3)
    final = await planner_final_result(context, '{"questions":["合成问题"]}')
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
        assert run.status == "completed" and run.output_message_id
        assert json.loads((await session.get(Message, run.output_message_id)).content) == final


@pytest.mark.parametrize("slug", ["health-meal-planner", "health-diet-analyst", "health-quality"])
async def test_structured_health_error_does_not_save_partial_body(initial_runtime, slug):
    """实际PG部分消息Owner保留Run错误边界，通用角色仍允许部分输出。"""
    from yuxi.services.chat_service import save_partial_message

    client, users, current, _ = initial_runtime
    bound, _ = await bind_initial(client, users, current)
    assert bound.status_code == 201, bound.text
    context = await seed_family_run(users, bound.json()["thread_id"])
    async with pg_manager.get_async_session_context() as session:
        (await session.get(AgentRun, context.run_id)).agent_slug = slug
    async with pg_manager.get_async_session_context() as session:
        message = await save_partial_message(
            ConversationRepository(session),
            context.thread_id,
            full_msg=AIMessage(content="UNVERIFIED_PARTIAL"),
            error_message="synthetic",
            run_id=context.run_id,
            request_id=context.request_id,
            worker_id=context.worker_id,
        )
        assert message is None
    async with pg_manager.get_async_session_context() as session:
        run = await session.get(AgentRun, context.run_id)
        assert run.output_message_id is None and run.status == "running"
        assert (
            await session.scalar(select(Message).where(Message.run_id == run.id, Message.role == "assistant")) is None
        )
        run.agent_slug = "synthetic-generic"
    async with pg_manager.get_async_session_context() as session:
        message = await save_partial_message(
            ConversationRepository(session),
            context.thread_id,
            full_msg=AIMessage(content="generic partial"),
            error_message="synthetic",
            run_id=context.run_id,
            request_id=context.request_id,
            worker_id=context.worker_id,
        )
        assert message is not None and message.content == "generic partial"


@pytest.mark.parametrize("status", ["completed", "failed"])
async def test_structured_health_audit_body_stays_private_in_pg(initial_runtime, status):
    """终态State兼容审计在健康历史/结果不可见，通用历史兼容仍保留。"""
    from yuxi.repositories.agent_run_output_repository import AgentRunOutputRepository
    from yuxi.storage.postgres.models_business import ToolCall

    client, users, current, _ = initial_runtime
    bound, _ = await bind_initial(client, users, current)
    assert bound.status_code == 201, bound.text
    context = await seed_family_run(users, bound.json()["thread_id"])
    async with pg_manager.get_async_session_context() as session:
        run = await session.get(AgentRun, context.run_id)
        run.status, run.worker_id, run.lease_expires_at = status, None, None
        audit = Message(
            conversation_id=run.conversation_id,
            run_id=run.id,
            request_id=run.request_id,
            role="assistant",
            message_type="model_audit",
            content="UNVERIFIED_INITIAL_MODEL_TEXT",
            extra_metadata={"state_reconciled": True},
        )
        session.add(audit)
        await session.flush()
        session.add(
            ToolCall(
                message_id=audit.id,
                tool_name="get_initial_plan_context",
                langgraph_tool_call_id=str(uuid4()),
                status="success",
            )
        )
        run.output_message_id = audit.id
    result = await client.get(f"/api/agent/runs/{context.run_id}/result", headers=users[0]["headers"])
    assert result.status_code == 200 and result.json()["output"] == "", result.text
    assert "UNVERIFIED_INITIAL_MODEL_TEXT" not in result.text
    history = await client.get(f"/api/chat/thread/{context.thread_id}/history", headers=users[0]["headers"])
    assert history.status_code == 200 and "UNVERIFIED_INITIAL_MODEL_TEXT" not in history.text, history.text
    async with pg_manager.get_async_session_context() as session:
        run = await session.get(AgentRun, context.run_id)
        assert (
            await AgentRunOutputRepository(session).get_output_message(
                run_id=run.id, conversation_id=run.conversation_id, output_message_id=run.output_message_id
            )
            is None
        )
        assert await ConversationRepository(session).get_messages(run.conversation_id) == []
        run.agent_slug = "synthetic-generic"
        await session.flush()
        messages = await ConversationRepository(session).get_messages(run.conversation_id)
        assert len(messages) == 1 and messages[0].content == "UNVERIFIED_INITIAL_MODEL_TEXT"


@pytest.mark.parametrize("stage", ["authorization", "generation"])
async def test_initial_waiting_lease_expiry_cannot_write_receipt(initial_runtime, monkeypatch, stage):
    """成员锁等待或真实生成之后租约过期，都不保存新回执。"""
    from yuxi.repositories.health_vision_repository import HealthVisionRepository
    from yuxi.services import health_initial_planner_service as service
    from yuxi.storage.postgres.models_health import FamilyMember

    client, users, current, _ = initial_runtime
    bound, _ = await bind_initial(client, users, current)
    assert bound.status_code == 201, bound.text
    context = await seed_family_run(users, bound.json()["thread_id"])
    deadline = utc_now_naive() + timedelta(seconds=3)
    async with pg_manager.get_async_session_context() as session:
        (await session.get(AgentRun, context.run_id)).lease_expires_at = deadline
    reached, last = asyncio.Event(), sorted([current["member"], current["second"]])[-1]
    original_authorize, original_generation = HealthVisionRepository.authorize, service.initial_generation_in_session

    async def observed(self, mid, uid, scope, *, lock=False):
        """真实锁前报告进入位置。"""
        if lock and mid == last:
            reached.set()
        return await original_authorize(self, mid, uid, scope, lock=lock)

    async def delayed(*args, **kwargs):
        """仍跑真实批准目录生成，仅延长其耗时。"""
        result = await original_generation(*args, **kwargs)
        await asyncio.sleep(max(0, (deadline - utc_now_naive()).total_seconds()) + 0.1)
        return result

    task = None
    try:
        if stage == "authorization":
            monkeypatch.setattr(HealthVisionRepository, "authorize", observed)
            async with pg_manager.get_async_session_context() as holder:
                await holder.scalar(select(FamilyMember).where(FamilyMember.id == last).with_for_update())
                task = asyncio.create_task(preview_initial_for_run(context))
                await asyncio.wait_for(reached.wait(), 2)
                assert not task.done()
                await asyncio.sleep(max(0, (deadline - utc_now_naive()).total_seconds()) + 0.1)
            with pytest.raises(HealthVisionError, match="execution_not_owned"):
                await asyncio.wait_for(task, 10)
        else:
            monkeypatch.setattr(service, "initial_generation_in_session", delayed)
            with pytest.raises(HealthVisionError, match="execution_not_owned"):
                await preview_initial_for_run(context)
        async with pg_manager.get_async_session_context() as session:
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(HealthInitialPlanPreview)
                    .where(HealthInitialPlanPreview.run_id == context.run_id)
                )
                == 0
            )
    finally:
        if task is not None and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

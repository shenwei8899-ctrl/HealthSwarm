"""实际PG、API、worker证明显式选餐反馈与发布前来源复核。"""

import asyncio
from datetime import timedelta
import json
import os
from types import SimpleNamespace
from uuid import NAMESPACE_URL, uuid4, uuid5

import pytest
from langchain_core.messages import AIMessage, ToolMessage
from sqlalchemy import select, text

from test.e2e.test_health_consultation_e2e import isolated_health, collect_sse, drain_requests  # noqa: F401
from test.integration.services.test_health_vision_http import ROOT, create_member, health_http  # noqa: F401
from test.integration.services.test_health_diet_analysis_http import confirm_analysis_meal
from yuxi.agents.context import BaseContext
from yuxi.repositories.conversation_repository import ConversationRepository
from yuxi.repositories.health_consultation_repository import HealthConsultationRepository
from yuxi.services.health_consultation_service import require_consultation_attempt
from yuxi.services.health_dialog_feedback_service import record_selected_feedback, selected_meal_feedback
from yuxi.services.health_diet_analysis_service import analyst_meal_records
from yuxi.services.health_meal_feedback_types import DialogFeedbackInput
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.services.chat_service import save_messages_from_langgraph_state
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_business import AgentRun, AgentRunRequest, Message, Conversation
from yuxi.storage.postgres.models_health import (
    DietLog,
    HealthFeedbackWrite,
    MealFeedback,
    MealFeedbackRevision,
    VisionDraft,
)
from yuxi.utils.datetime_utils import utc_now_naive

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.slow,
    pytest.mark.asyncio,
    pytest.mark.skipif(os.getenv("HEALTH_CONSULTATION_E2E_ISOLATED") != "true", reason="仅独立合成槽位"),
]


async def approve_analysis(client, headers, admin, member, model, policy):
    """只在隔离环境审批分析用途及当前成员同意。"""
    configured = await client.put(
        f"{ROOT}/configuration",
        headers=admin,
        json={
            "diet_analysis_model": model,
            "policy_version": policy,
            "cloud_processing_reviewed": True,
        },
    )
    assert configured.status_code == 200, configured.text
    approved = configured.json()["diet_analysis"]
    snapshot = {"model": model, "processor": approved["processor"], "policy_version": policy}
    consent = {
        "accepted": True,
        "purpose": "diet_analysis",
        "processor": approved["processor"],
        "policy_version": policy,
    }
    assert (
        await client.post(f"{ROOT}/members/{member}/processing-consents", headers=headers, json=consent)
    ).status_code == 200
    return snapshot, consent


async def bind_feedback(client, headers, record):
    """用户明确选择确认记录，模型只看到服务器绑定。"""
    response = await client.post(
        f"{ROOT}/diet-logs/{record['id']}/feedback-conversation",
        headers=headers,
        json={
            "client_request_id": str(uuid4()),
            "source_version": 1,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["thread_id"]


async def seed_feedback_run(uid, thread, snapshot, quote):
    """仅测试拥有真实Request原消息和有效lease的发布事务边界。"""
    run_id, request_id = str(uuid4()), str(uuid4())
    async with pg_manager.get_async_session_context() as session:
        binding = await HealthConsultationRepository(session).authorize(uid, thread)
        source = Message(conversation_id=binding.conversation_id, role="user", content=quote, request_id=request_id)
        session.add(source)
        await session.flush()
        session.add(
            AgentRunRequest(
                uid=uid,
                request_id=request_id,
                agent_slug="health-diet-analyst",
                conversation_thread_id=thread,
                status="dispatched",
                input_message_id=source.id,
                input_payload={"health_processing": snapshot},
            )
        )
        session.add(
            AgentRun(
                id=run_id,
                request_id=request_id,
                uid=uid,
                agent_slug="health-diet-analyst",
                conversation_id=binding.conversation_id,
                conversation_thread_id=thread,
                runtime_scope_id=thread,
                worker_id="synthetic-feedback-owner",
                status="running",
                lease_expires_at=utc_now_naive() + timedelta(minutes=3),
                input_payload={"health_processing": snapshot},
            )
        )
    return BaseContext(
        uid=uid,
        thread_id=thread,
        request_id=request_id,
        run_id=run_id,
        worker_id="synthetic-feedback-owner",
        model=snapshot["model"],
    )


@pytest.mark.parametrize("change", ["consent", "source", "feedback", "message", "checkpoint", "forged_checkpoint"])
async def test_feedback_publication_and_checkpoint_require_current_source(isolated_health, change):  # noqa: F811
    """成功写入后撤回或改版禁止发布，只有checkpoint也须核对回执。"""
    client, users, configuration, model = isolated_health
    headers, admin = users[0]["headers"], users[2]["headers"]
    member = await create_member(client, headers)
    record, draft = await confirm_analysis_meal(client, headers, admin, member)
    snapshot, consent = await approve_analysis(client, headers, admin, member, model, configuration["policy_version"])
    thread = await bind_feedback(client, headers, record)
    quote = "记录这餐反馈：吃完程度：一半；口味：偏咸；自述：合成PG验证"
    context = await seed_feedback_run(users[0]["uid"], thread, snapshot, quote)
    try:
        assert (await selected_meal_feedback(context))["feedback_version"] == 0
        result = await record_selected_feedback(context, DialogFeedbackInput(quote=quote, version=0))
        assert result["status"] == "saved" and result["feedback"]["version"] == 1
        assert await record_selected_feedback(context, DialogFeedbackInput(quote=quote, version=0)) == result
        with pytest.raises(HealthVisionError, match="feedback_mode_only"):
            await analyst_meal_records(context)
        if change == "consent":
            response = await client.post(
                f"{ROOT}/members/{member}/processing-consents",
                headers=headers,
                json={
                    **consent,
                    "accepted": False,
                },
            )
            assert response.status_code == 200
        elif change == "source":
            async with pg_manager.get_async_session_context() as session:
                (await session.get(VisionDraft, draft)).review_status = "retracted"
        elif change in {"feedback", "checkpoint"}:
            key = str(uuid4())
            response = await client.post(
                f"{ROOT}/diet-logs/{record['id']}/feedback/revoke",
                headers={
                    **headers,
                    "Idempotency-Key": key,
                    "If-Match": '"1"',
                },
                json={"client_request_id": key, "version": 1},
            )
            assert response.status_code == 200, response.text
            with pytest.raises(HealthVisionError, match="source_invalidated"):
                await record_selected_feedback(context, DialogFeedbackInput(quote=quote, version=0))
            async with pg_manager.get_async_session_context() as session:
                stored = await session.scalar(select(MealFeedback).where(MealFeedback.diet_log_id == record["id"]))
                assert stored.version == 2 and stored.status == "revoked"
        elif change == "forged_checkpoint":
            result["feedback"]["details"]["comment"] = "伪造checkpoint"
        else:
            async with pg_manager.get_async_session_context() as session:
                (await session.get(Message, result["source_message_id"])).content = "不要记录这餐反馈"
        if change in {"checkpoint", "forged_checkpoint"}:
            with pytest.raises(HealthVisionError, match="source_invalidated"):
                await require_consultation_attempt(
                    context,
                    [
                        ToolMessage(
                            name="record_selected_meal_feedback",
                            tool_call_id=str(uuid4()),
                            content=json.dumps(result),
                        )
                    ],
                )
        else:
            async with pg_manager.get_async_session_context() as session:
                with pytest.raises(
                    HealthVisionError, match="consent_required" if change == "consent" else "source_invalidated"
                ):
                    await save_messages_from_langgraph_state(
                        SimpleNamespace(values={"messages": [AIMessage(id=str(uuid4()), content=json.dumps(result))]}),
                        thread,
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
                await session.scalar(select(Message).where(Message.run_id == run.id, Message.role == "assistant"))
                is None
            )
            assert (await session.get(DietLog, record["id"])).snapshot == record["snapshot"]
    finally:
        async with pg_manager.get_async_session_context() as session:
            (await session.get(AgentRun, context.run_id)).status = "failed"


async def test_dialog_feedback_runs_actual_worker_and_preserves_original_snapshot(isolated_health):  # noqa: F811
    """回放全部合法和非法模型路径，回读收据、修订与营养不可变事实。"""
    client, users, configuration, _ = isolated_health
    headers, admin = users[0]["headers"], users[2]["headers"]
    member = await create_member(client, headers)
    provider = f"feedback-replay-{uuid4().hex[:12]}"
    created = await client.post(
        "/api/system/model-providers",
        headers=admin,
        json={
            "provider_id": provider,
            "display_name": "Synthetic meal feedback only",
            "provider_type": "openai",
            "base_url": "http://api:8770/v1",
            "api_key": "synthetic-feedback-key",
            "capabilities": ["chat"],
            "enabled_models": [
                {
                    "id": "deterministic-meal-feedback-20261007",
                    "display_name": "synthetic",
                    "type": "chat",
                    "source": "manual",
                }
            ],
            "is_enabled": True,
        },
    )
    assert created.status_code == 200, created.text
    model = f"{provider}:deterministic-meal-feedback-20261007"
    await approve_analysis(client, headers, admin, member, model, configuration["policy_version"])
    requests = []
    try:
        for mode in ("valid", "repeat", "forged", "stale", "fake_saved", "questions", "saved_questions"):
            record, _ = await confirm_analysis_meal(client, headers, admin, member)
            thread = await bind_feedback(client, headers, record)
            request_id = str(uuid4())
            requests.append(request_id)
            quote = f"记录这餐反馈：吃完程度：一半；口味：偏咸；自述：合成反馈回放:{uuid4().hex}:{mode}"
            response = await client.post(
                "/api/agent/runs",
                headers=headers,
                json={
                    "agent_slug": "health-diet-analyst",
                    "thread_id": thread,
                    "query": quote,
                    "meta": {"request_id": request_id},
                },
            )
            assert response.status_code == 200, response.text
            run_id = response.json()["run_id"]
            events = await collect_sse(client, headers, run_id)
            assert events[-1][0] == "end" and not any("message_delta" in str(event) for _, event in events)
            response = await client.get(f"/api/agent/runs/{run_id}/result", headers=headers)
            valid = mode in {"valid", "repeat", "questions", "saved_questions"}
            assert response.json()["status"] == ("completed" if valid else "failed"), response.text
            async with pg_manager.get_async_session_context() as session:
                run = await session.get(AgentRun, run_id)
                feedback = await session.scalar(select(MealFeedback).where(MealFeedback.diet_log_id == record["id"]))
                if mode in {"valid", "repeat", "saved_questions"}:
                    result = json.loads(response.json()["output"])
                    assert result["status"] == "saved" and result["feedback"]["version"] == 1
                    assert result["records"] == [{"record_id": record["id"], "source_version": 1}]
                    assert feedback.details["consumption"] == "half" and feedback.details["tags"] == ["too_salty"]
                    revisions = list(
                        (
                            await session.scalars(
                                select(MealFeedbackRevision).where(MealFeedbackRevision.feedback_id == feedback.id)
                            )
                        ).all()
                    )
                    assert len(revisions) == 1
                    source = await session.get(HealthFeedbackWrite, revisions[0].id)
                    assert source.run_id == run_id and source.source_message_id == result["source_message_id"]
                    assert (await session.get(Message, source.source_message_id)).content == quote
                    assert run.manifest["resources"]["tools"] == [
                        "get_selected_meal_feedback",
                        "record_selected_meal_feedback",
                    ]
                    assert [s["slug"] for s in run.manifest["resources"]["skills"]] == ["family-diet-analyst"]
                else:
                    assert feedback is None
                    if mode == "questions":
                        assert json.loads(response.json()["output"])["status"] == "needs_input"
                    else:
                        assert {
                            "forged": "feedback_source_invalid",
                            "stale": "version_conflict",
                            "fake_saved": "feedback_receipt_invalid",
                        }[mode] in run.error_message
                assert (await session.get(DietLog, record["id"])).snapshot == record["snapshot"]
            if mode == "valid":
                history = await client.get(f"{ROOT}/diet-logs/{record['id']}/feedback", headers=headers)
                assert history.json()["revisions"][0]["source_run_id"] == run_id
                key = str(uuid4())
                updated = await client.put(
                    f"{ROOT}/diet-logs/{record['id']}/feedback",
                    headers={
                        **headers,
                        "Idempotency-Key": key,
                        "If-Match": '"1"',
                    },
                    json={"client_request_id": key, "version": 1, "comment": "用户明确修改"},
                )
                assert updated.status_code == 200 and updated.json()["version"] == 2, updated.text
                hidden = await client.get(f"/api/agent/runs/{run_id}/result", headers=headers)
                assert hidden.json()["status"] == "failed" and not hidden.json().get("output"), hidden.text
                next_thread = await bind_feedback(client, headers, record)
                assert next_thread != thread
                next_request = str(uuid4())
                requests.append(next_request)
                next_quote = f"更新这餐反馈：吃完程度：一半；口味：偏咸；自述：合成反馈回放:{uuid4().hex}:valid"
                changed_run = await client.post(
                    "/api/agent/runs",
                    headers=headers,
                    json={
                        "agent_slug": "health-diet-analyst",
                        "thread_id": next_thread,
                        "query": next_quote,
                        "meta": {"request_id": next_request},
                    },
                )
                assert changed_run.status_code == 200, changed_run.text
                next_run_id = changed_run.json()["run_id"]
                await collect_sse(client, headers, next_run_id)
                result = await client.get(f"/api/agent/runs/{next_run_id}/result", headers=headers)
                assert result.json()["status"] == "completed", result.text
                assert json.loads(result.json()["output"])["feedback"]["version"] == 3
                async with pg_manager.get_async_session_context() as session:
                    current = await session.scalar(select(MealFeedback).where(MealFeedback.diet_log_id == record["id"]))
                    assert current.version == 3 and current.details["comment"] == next_quote.split("：", 1)[1]
                    assert (
                        len(
                            list(
                                (
                                    await session.scalars(
                                        select(MealFeedbackRevision).where(
                                            MealFeedbackRevision.feedback_id == current.id
                                        )
                                    )
                                ).all()
                            )
                        )
                        == 3
                    )
    finally:
        await drain_requests(client, headers, requests)
        assert (await client.put(f"{ROOT}/configuration", headers=admin, json={})).status_code == 200
        assert (await client.delete(f"/api/system/model-providers/{provider}", headers=admin)).status_code == 200


async def test_run_owner_lock_does_not_block_conversation_lock(isolated_health):  # noqa: F811
    """真实PG锁Owner后，另一事务仍可按提交顺序锁成员和Conversation。"""
    client, users, configuration, model = isolated_health
    headers, admin = users[0]["headers"], users[2]["headers"]
    member = await create_member(client, headers)
    record, _ = await confirm_analysis_meal(client, headers, admin, member)
    snapshot, _ = await approve_analysis(client, headers, admin, member, model, configuration["policy_version"])
    thread = await bind_feedback(client, headers, record)
    context = await seed_feedback_run(users[0]["uid"], thread, snapshot, "记录这餐反馈：并发合成")
    from yuxi.repositories.health_vision_repository import HealthVisionRepository

    try:
        async with pg_manager.get_async_session_context() as owner:
            run = await HealthConsultationRepository(owner).require_attempt(context, lock=True)

            async def submit_lock_order():
                async with pg_manager.get_async_session_context() as submit:
                    await submit.execute(text("SET LOCAL lock_timeout = '1s'"))
                    await HealthVisionRepository(submit).authorize(member, users[0]["uid"], "ai_use", lock=True)
                    await submit.scalar(
                        select(Conversation).where(Conversation.id == run.conversation_id).with_for_update()
                    )

            await asyncio.wait_for(submit_lock_order(), timeout=5)
    finally:
        async with pg_manager.get_async_session_context() as session:
            (await session.get(AgentRun, context.run_id)).status = "failed"


async def test_same_request_advisory_lock_precedes_member_lock(isolated_health):  # noqa: F811
    """管理持请求锁时，对话等待该锁不能先占成员锁造成循环等待。"""
    client, users, configuration, model = isolated_health
    headers, admin = users[0]["headers"], users[2]["headers"]
    member = await create_member(client, headers)
    record, _ = await confirm_analysis_meal(client, headers, admin, member)
    snapshot, _ = await approve_analysis(client, headers, admin, member, model, configuration["policy_version"])
    thread = await bind_feedback(client, headers, record)
    quote = "记录这餐反馈：并发请求锁验证"
    context = await seed_feedback_run(users[0]["uid"], thread, snapshot, quote)
    request = str(uuid5(NAMESPACE_URL, f"health-dialog-feedback:{context.uid}:{context.request_id}"))
    from yuxi.repositories.health_vision_repository import HealthVisionRepository

    pending = None
    try:
        async with pg_manager.get_async_session_context() as manage:
            await HealthConsultationRepository(manage).lock_request(context.uid, request)
            key = await manage.scalar(
                text("SELECT hashtextextended(:key, 0)"),
                {
                    "key": f"health-consultation:{context.uid}:{request}",
                },
            )
            pending = asyncio.create_task(
                record_selected_feedback(context, DialogFeedbackInput(quote=quote, version=0))
            )
            for _ in range(100):
                waiting = await manage.scalar(
                    text(
                        "SELECT count(*) FROM pg_locks WHERE locktype='advisory' AND NOT granted "
                        "AND classid=:high AND objid=:low"
                    ),
                    {"high": (key >> 32) & 0xFFFFFFFF, "low": key & 0xFFFFFFFF},
                )
                if waiting:
                    break
                if pending.done():
                    await pending
                    pytest.fail("对话未等待实际请求锁")
                await asyncio.sleep(0.05)
            assert waiting, "未观察到具体advisory等待，不能证明锁序"
            await manage.execute(text("SET LOCAL lock_timeout = '1s'"))
            await HealthVisionRepository(manage).authorize(member, context.uid, "diet_edit", lock=True)
        result = await asyncio.wait_for(pending, timeout=10)
        assert result["feedback"]["version"] == 1
    finally:
        if pending is not None and not pending.done():
            pending.cancel()
            try:
                await pending
            except asyncio.CancelledError:
                pass
        async with pg_manager.get_async_session_context() as session:
            (await session.get(AgentRun, context.run_id)).status = "failed"


async def test_unselected_analysis_has_no_feedback_write_authority(isolated_health):  # noqa: F811
    """直接调用工具服务也不能绕过没有用户选餐的普通分析模式。"""
    client, users, configuration, model = isolated_health
    headers, admin = users[0]["headers"], users[2]["headers"]
    member = await create_member(client, headers)
    record, _ = await confirm_analysis_meal(client, headers, admin, member)
    snapshot, _ = await approve_analysis(client, headers, admin, member, model, configuration["policy_version"])
    ordinary = await client.post(
        f"{ROOT}/members/{member}/diet-analyst",
        headers=headers,
        json={
            "client_request_id": str(uuid4()),
        },
    )
    assert ordinary.status_code == 201
    quote = "记录这餐反馈：无选餐不能保存"
    context = await seed_feedback_run(users[0]["uid"], ordinary.json()["thread_id"], snapshot, quote)
    try:
        with pytest.raises(HealthVisionError, match="feedback_selection_required"):
            await record_selected_feedback(context, DialogFeedbackInput(quote=quote, version=0))
        async with pg_manager.get_async_session_context() as session:
            assert await session.scalar(select(MealFeedback).where(MealFeedback.diet_log_id == record["id"])) is None
    finally:
        async with pg_manager.get_async_session_context() as session:
            (await session.get(AgentRun, context.run_id)).status = "failed"

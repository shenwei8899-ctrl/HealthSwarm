"""真实 HTTP 与 PG 验证未完成执行不能登记次日提议。"""

import asyncio
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select

from test.integration.services.test_health_vision_http import ROOT, create_member, health_http  # noqa: F401
from yuxi.services.health_daily_service import business_date
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_business import AgentRun, AgentRunRequest, Conversation, Message
from yuxi.storage.postgres.models_health import FamilyMember, HealthNextDayProposal
from yuxi.utils.datetime_utils import utc_now_naive

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_pending_failed_cancelled_runs_and_foreign_actor_create_no_proposal(health_http):  # noqa: F811
    """该 PG 边界测试只证明 HTTP 拒绝，成功路径另由真实 Worker E2E 证明。"""
    client, users = health_http
    owner = users[0]
    member = await create_member(client, owner["headers"])
    binding = await client.post(
        f"{ROOT}/members/{member}/meal-planner",
        headers=owner["headers"],
        json={"client_request_id": str(uuid4())},
    )
    assert binding.status_code == 201, binding.text
    thread, request_id, run_id = binding.json()["thread_id"], str(uuid4()), str(uuid4())
    async with pg_manager.get_async_session_context() as session:
        conversation = await session.scalar(select(Conversation).where(Conversation.thread_id == thread))
        message = Message(
            conversation_id=conversation.id, request_id=request_id, role="user", content="合成未完成登记边界"
        )
        session.add(message)
        await session.flush()
        run = AgentRun(
            id=run_id,
            request_id=request_id,
            uid=owner["uid"],
            agent_slug="health-meal-planner",
            status="pending",
            conversation_id=conversation.id,
            conversation_thread_id=thread,
            runtime_scope_id=thread,
            input_message_id=message.id,
        )
        session.add(run)
        await session.flush()
        session.add(
            AgentRunRequest(
                request_id=request_id,
                uid=owner["uid"],
                agent_slug="health-meal-planner",
                conversation_thread_id=thread,
                input_message_id=message.id,
                status="dispatched",
                dispatched_run_id=run.id,
            )
        )
    body = {
        "client_request_id": str(uuid4()),
        "request_id": request_id,
        "final_message_id": 1,
        "preview_id": str(uuid4()),
        "source_date": business_date().isoformat(),
    }
    endpoint = f"{ROOT}/members/{member}/meal-planner-runs/{run_id}/next-day-proposals"
    try:
        for invalid_input in (
            {"final_message_id": True},
            {"final_message_id": 0},
            {"request_id": "x" * 65},
            {"nutrition": {"energy_kcal": "300.00"}},
        ):
            rejected = await client.post(endpoint, headers=owner["headers"], json={**body, **invalid_input})
            assert rejected.status_code == 422, rejected.text
        for actor in users[1:]:
            denied = await client.post(endpoint, headers=actor["headers"], json=body)
            assert denied.status_code == 404, denied.text
        for status in ("pending", "failed", "cancelled", "interrupted"):
            async with pg_manager.get_async_session_context() as session:
                (await session.get(AgentRun, run_id)).status = status
            denied = await client.post(endpoint, headers=owner["headers"], json=body)
            assert denied.status_code == 409 and denied.json()["code"] == "answer_not_completed", denied.text
            async with pg_manager.get_async_session_context() as session:
                assert (
                    await session.scalar(
                        select(HealthNextDayProposal).where(HealthNextDayProposal.actor_uid == owner["uid"])
                    )
                ) is None
    finally:
        async with pg_manager.get_async_session_context() as session:
            (await session.get(AgentRun, run_id)).status = "failed"


async def test_running_run_lock_does_not_block_rejection_or_keep_member_locked(health_http):  # noqa: F811
    """真实 Run 锁下快返 409，随后 NOWAIT 成员锁证明拒绝已释放事务。"""
    client, users = health_http
    owner = users[0]
    member = await create_member(client, owner["headers"])
    binding = await client.post(
        f"{ROOT}/members/{member}/meal-planner",
        headers=owner["headers"],
        json={"client_request_id": str(uuid4())},
    )
    assert binding.status_code == 201, binding.text
    thread, request_id, run_id = binding.json()["thread_id"], str(uuid4()), str(uuid4())
    now = utc_now_naive()
    async with pg_manager.get_async_session_context() as session:
        conversation = await session.scalar(select(Conversation).where(Conversation.thread_id == thread))
        message = Message(
            conversation_id=conversation.id, request_id=request_id, role="user", content="合成执行锁拒绝边界"
        )
        session.add(message)
        await session.flush()
        session.add(
            AgentRun(
                id=run_id,
                request_id=request_id,
                uid=owner["uid"],
                agent_slug="health-meal-planner",
                status="running",
                conversation_id=conversation.id,
                conversation_thread_id=thread,
                runtime_scope_id=thread,
                input_message_id=message.id,
                worker_id=f"synthetic-next-day-lock-oracle:{uuid4()}",
                heartbeat_at=now,
                lease_expires_at=now + timedelta(minutes=3),
                started_at=now,
            )
        )
        await session.flush()
        session.add(
            AgentRunRequest(
                request_id=request_id,
                uid=owner["uid"],
                agent_slug="health-meal-planner",
                conversation_thread_id=thread,
                input_message_id=message.id,
                status="dispatched",
                dispatched_run_id=run_id,
            )
        )
    body = {
        "client_request_id": str(uuid4()),
        "request_id": request_id,
        "final_message_id": 1,
        "preview_id": str(uuid4()),
        "source_date": business_date().isoformat(),
    }
    holder = await pg_manager.get_async_session()
    pending_http = None
    try:
        await holder.execute(select(AgentRun).where(AgentRun.id == run_id).with_for_update())
        pending_http = asyncio.create_task(
            client.post(
                f"{ROOT}/members/{member}/meal-planner-runs/{run_id}/next-day-proposals",
                headers=owner["headers"],
                json=body,
            )
        )
        rejected = await asyncio.wait_for(asyncio.shield(pending_http), timeout=3)
        assert rejected.status_code == 409 and rejected.json()["code"] == "answer_not_completed", rejected.text
        locked_member = await holder.scalar(
            select(FamilyMember).where(FamilyMember.id == member).with_for_update(nowait=True)
        )
        assert locked_member is not None and locked_member.id == member
        assert (
            await holder.scalar(select(HealthNextDayProposal).where(HealthNextDayProposal.actor_uid == owner["uid"]))
        ) is None
    finally:
        await holder.rollback()
        await holder.close()
        try:
            if pending_http is not None:
                try:
                    await asyncio.wait_for(asyncio.shield(pending_http), timeout=10)
                except TimeoutError:
                    pending_http.cancel()
                    await asyncio.gather(pending_http, return_exceptions=True)
        finally:
            async with pg_manager.get_async_session_context() as session:
                run = await session.get(AgentRun, run_id)
                run.status = "failed"
                run.worker_id = run.heartbeat_at = run.lease_expires_at = None
                run.finished_at = utc_now_naive()

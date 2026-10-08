"""真实 worker 读取餐次反馈、版本失效传播及外呼期间撤回。"""

import asyncio
import os
from datetime import timedelta
from uuid import uuid4
import httpx
import pytest
from sqlalchemy import select
from test.e2e.test_health_consultation_e2e import collect_sse, drain_requests, isolated_health  # noqa: F401
from test.integration.services.test_health_vision_http import ROOT, create_member, health_http  # noqa: F401
from test.integration.services.test_health_meal_feedback_http import confirmed_meal, feedback_headers
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_business import AgentRun, Message
from yuxi.storage.postgres.models_health import (
    MealFeedbackUse,
    HealthDailyConversation,
    VisionDraft,
    HealthMemoryFact,
    HealthMemoryRevision,
    HealthMemoryUse,
)
from yuxi.services.health_daily_service import business_date

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.e2e,
    pytest.mark.slow,
    pytest.mark.skipif(os.getenv("HEALTH_CONSULTATION_E2E_ISOLATED") != "true", reason="仅在独立合成槽位运行"),
]


async def prepare_feedback(client, users, config):
    """通过真实接口建立单餐和咨询用途。"""
    headers = users[0]["headers"]
    member = await create_member(client, headers)
    record, draft = await confirmed_meal(client, headers, member)
    body = {
        "client_request_id": str(uuid4()),
        "version": 0,
        "comment": "合成单餐偏咸",
        "tags": ["too_salty"],
        "consumption": "half",
    }
    saved = await client.put(f"{ROOT}/diet-logs/{record}/feedback", headers=feedback_headers(headers, body), json=body)
    assert saved.status_code == 200
    thread = (await client.post(f"{ROOT}/members/{member}/daily-consultations", headers=headers)).json()["thread_id"]
    consent = await client.post(
        f"{ROOT}/members/{member}/processing-consents",
        headers=headers,
        json={
            "purpose": "consultation",
            "accepted": True,
            "processor": config["consultation"]["processor"],
            "policy_version": config["policy_version"],
        },
    )
    assert consent.status_code == 200
    return member, record, draft, saved.json()["feedback_id"], thread


async def submit(client, headers, thread, token, step, requests):
    """真实 API 排队并收集对应 Run 的最终 SSE。"""
    request = str(uuid4())
    requests.append(request)
    response = await client.post(
        "/api/agent/runs",
        headers=headers,
        json={
            "agent_slug": "health-consultation",
            "thread_id": thread,
            "query": f"HEALTH_CONSULTATION_E2E:{token}:{step}",
            "meta": {"request_id": request},
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["run_id"]


async def test_feedback_worker_edit_revoke_and_daily_sources(isolated_health):  # noqa: F811
    """模型 oracle 核对真实反馈和历史；PG 证明派生依赖与日终排除。"""
    client, users, config, _ = isolated_health
    headers = users[0]["headers"]
    member, record, _, feedback_id, thread = await prepare_feedback(client, users, config)
    token, requests, runs = uuid4().hex, [], []
    try:
        for step in ("feedback", "derived_feedback", "edited_feedback", "empty_feedback"):
            if step == "edited_feedback":
                edited = {"client_request_id": str(uuid4()), "version": 1, "comment": "合成餐后补充"}
                result = await client.put(
                    f"{ROOT}/diet-logs/{record}/feedback", headers=feedback_headers(headers, edited), json=edited
                )
                assert result.json()["version"] == 2
            if step == "empty_feedback":
                revoke = {"client_request_id": str(uuid4()), "version": 2}
                assert (
                    await client.post(
                        f"{ROOT}/diet-logs/{record}/feedback/revoke",
                        headers=feedback_headers(headers, revoke),
                        json=revoke,
                    )
                ).status_code == 200
            run_id = await submit(client, headers, thread, token, step, requests)
            runs.append(run_id)
            await collect_sse(client, headers, run_id)
            async with pg_manager.get_async_session_context() as session:
                run = await session.get(AgentRun, run_id)
                assert run.status == "completed", (run.error_type, run.error_message)
                uses = list(
                    (await session.scalars(select(MealFeedbackUse).where(MealFeedbackUse.run_id == run_id))).all()
                )
                if step != "empty_feedback":
                    assert {(use.feedback_id, use.version) for use in uses} == {
                        (feedback_id, 2 if step == "edited_feedback" else 1)
                    }
                else:
                    assert uses == []
        async with pg_manager.get_async_session_context() as session:
            day = await session.scalar(
                select(HealthDailyConversation).where(HealthDailyConversation.member_id == member)
            )
            day.business_date = business_date() - timedelta(days=1)
        result = await client.post(f"{ROOT}/daily-conversations/{thread}/summary", headers=headers)
        assert result.status_code == 200 and result.json()["status"] == "ready"
        async with pg_manager.get_async_session_context() as session:
            sources = list(
                (
                    await session.scalars(
                        select(Message).where(
                            Message.request_id == requests[-1],
                            Message.role.in_(("user", "assistant")),
                            Message.message_type == "text",
                            Message.content != "",
                        )
                    )
                ).all()
            )
            assert set(result.json()["summary"]["source_message_ids"]) == {row.id for row in sources}
            assert not any(
                "合成单餐偏咸" in row["excerpt"] or "合成餐后补充" in row["excerpt"]
                for row in result.json()["summary"]["excerpts"]
            )
            assert (
                len(
                    list(
                        (
                            await session.scalars(
                                select(Message).where(
                                    Message.request_id.in_(requests[:-1]),
                                    Message.role == "assistant",
                                    Message.message_type == "text",
                                    Message.content != "",
                                )
                            )
                        ).all()
                    )
                )
                == 3
            )
    finally:
        await drain_requests(client, headers, requests)


@pytest.mark.parametrize("invalidate", ["feedback", "source"])
async def test_feedback_withdrawn_during_external_model_call_fails_run(isolated_health, invalidate):  # noqa: F811
    """外呼已经开始后撤回反馈或原餐次，最终输出不得成功发布。"""
    client, users, config, _ = isolated_health
    headers = users[0]["headers"]
    _, record, draft, _, thread = await prepare_feedback(client, users, config)
    token, requests = uuid4().hex, []
    async with httpx.AsyncClient(base_url="http://api:8766", timeout=10) as replay:
        try:
            run_id = await submit(client, headers, thread, token, "feedback_gate", requests)
            async with asyncio.timeout(30):
                while True:
                    observations = (await replay.get("/observations", params={"token": token})).json()
                    if any(item["phase"] == "answer" for item in observations.get("calls", [])):
                        break
                    await asyncio.sleep(0.1)
            if invalidate == "feedback":
                data = {"client_request_id": str(uuid4()), "version": 1}
                assert (
                    await client.post(
                        f"{ROOT}/diet-logs/{record}/feedback/revoke", headers=feedback_headers(headers, data), json=data
                    )
                ).status_code == 200
            else:
                async with pg_manager.get_async_session_context() as session:
                    source = await session.get(VisionDraft, draft)
                    source.review_status = "invalidated"
            await replay.get("/release", params={"token": token})
            await collect_sse(client, headers, run_id)
            async with pg_manager.get_async_session_context() as session:
                run = await session.get(AgentRun, run_id)
                assert run.status == "failed" and "meal_feedback_changed" in run.error_message, (
                    run.status,
                    run.error_type,
                    run.error_message,
                )
        finally:
            await replay.get("/release", params={"token": token})
            await drain_requests(client, headers, requests)


async def test_mixed_feedback_and_memory_only_propagate_visible_context(isolated_health):  # noqa: F811
    """真实 worker 共同读取后撤回记忆，无关回答不带反馈依赖或误从摘要移除。"""
    client, users, config, _ = isolated_health
    headers = users[0]["headers"]
    member, record, _, feedback_id, thread = await prepare_feedback(client, users, config)
    memory_id = str(uuid4())
    async with pg_manager.get_async_session_context() as session:
        session.add(
            HealthMemoryFact(
                id=memory_id,
                actor_uid=users[0]["uid"],
                member_id=member,
                fact_key="coriander",
                kind="preference",
                content="我以后不吃香菜",
                version=1,
                status="active",
            )
        )
        await session.flush()
        session.add(
            HealthMemoryRevision(
                id=str(uuid4()),
                fact_id=memory_id,
                actor_uid=users[0]["uid"],
                version=1,
                request_id=str(uuid4()),
                source_hash="a" * 64,
                kind="preference",
                content="我以后不吃香菜",
                status="active",
            )
        )
    token, requests = uuid4().hex, []
    try:
        source_run = await submit(client, headers, thread, token, "mixed_feedback", requests)
        await collect_sse(client, headers, source_run)
        async with pg_manager.get_async_session_context() as session:
            run = await session.get(AgentRun, source_run)
            assert run.status == "completed", (run.error_type, run.error_message)
            assert (
                await session.scalar(select(MealFeedbackUse).where(MealFeedbackUse.run_id == source_run))
            ).feedback_id == feedback_id
            assert (
                await session.scalar(select(HealthMemoryUse).where(HealthMemoryUse.run_id == source_run))
            ).fact_id == memory_id
        revoke = {"client_request_id": str(uuid4()), "version": 1}
        assert (
            await client.post(
                f"{ROOT}/memory/{memory_id}/revoke", headers=feedback_headers(headers, revoke), json=revoke
            )
        ).status_code == 200
        for turn in range(2):
            if turn:
                revoke = {"client_request_id": str(uuid4()), "version": 1}
                assert (
                    await client.post(
                        f"{ROOT}/diet-logs/{record}/feedback/revoke",
                        headers=feedback_headers(headers, revoke),
                        json=revoke,
                    )
                ).status_code == 200
            run_id = await submit(client, headers, thread, token, "neutral", requests)
            await collect_sse(client, headers, run_id)
            async with pg_manager.get_async_session_context() as session:
                run = await session.get(AgentRun, run_id)
                assert run.status == "completed", (run.error_type, run.error_message)
                for model in (MealFeedbackUse, HealthMemoryUse):
                    assert await session.scalar(select(model).where(model.run_id == run_id)) is None
        async with pg_manager.get_async_session_context() as session:
            day = await session.scalar(
                select(HealthDailyConversation).where(HealthDailyConversation.member_id == member)
            )
            day.business_date = business_date() - timedelta(days=1)
        summary = await client.post(f"{ROOT}/daily-conversations/{thread}/summary", headers=headers)
        assert summary.json()["status"] == "ready"
        async with pg_manager.get_async_session_context() as session:
            messages = list(
                (
                    await session.scalars(
                        select(Message).where(
                            Message.request_id.in_(requests[1:]),
                            Message.role.in_(("user", "assistant")),
                            Message.message_type == "text",
                            Message.content != "",
                        )
                    )
                ).all()
            )
            assert set(summary.json()["summary"]["source_message_ids"]) == {row.id for row in messages}
    finally:
        await drain_requests(client, headers, requests)

"""真实 worker 自动记忆、撤回后的模型输入及日终 cron。"""

import asyncio
import os
from datetime import timedelta
from uuid import uuid4
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select
from langchain_core.messages import HumanMessage, AIMessage
from yuxi.services.health_memory_service import filter_memory_history

from test.e2e.test_health_consultation_e2e import collect_sse, drain_requests, isolated_health  # noqa: F401
from test.integration.services.test_health_vision_http import ROOT, create_member, health_http  # noqa: F401
from yuxi.services.health_daily_service import business_date
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_business import AgentRun, AgentRunRequest, Message
from yuxi.storage.postgres.models_health import (
    HealthDailyConversation,
    HealthMemoryFact,
    HealthMemoryRevision,
    HealthMemoryUse,
)

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.e2e,
    pytest.mark.slow,
    pytest.mark.skipif(os.getenv("HEALTH_CONSULTATION_E2E_ISOLATED") != "true", reason="仅在独立合成槽位运行"),
]


async def test_worker_memory_revoke_filters_history_and_cron_summarizes(isolated_health):  # noqa: F811
    """从模型工具写入回读 PG；撤回影响真实模型请求，cron 原子发布摘要。"""
    client, users, config, _ = isolated_health
    headers = users[0]["headers"]
    member = await create_member(client, headers)
    bound = await client.post(f"{ROOT}/members/{member}/daily-consultations", headers=headers)
    assert bound.status_code == 201
    thread = bound.json()["thread_id"]
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
    token, requests = uuid4().hex, []
    try:
        request = str(uuid4())
        requests.append(request)
        body = {
            "agent_slug": "health-consultation",
            "thread_id": thread,
            "query": f"HEALTH_CONSULTATION_E2E:{token}:memory\n我以后不吃香菜",
            "meta": {"request_id": request},
        }
        submitted = await client.post("/api/agent/runs", headers=headers, json=body)
        assert submitted.status_code == 200, submitted.text
        run_id = submitted.json()["run_id"]
        await collect_sse(client, headers, run_id)
        async with pg_manager.get_async_session_context() as session:
            run = await session.get(AgentRun, run_id)
            assert run.status == "completed", (run.error_type, run.error_message)
            facts = list(
                (await session.scalars(select(HealthMemoryFact).where(HealthMemoryFact.member_id == member))).all()
            )
            assert len(facts) == 1 and facts[0].content == "我以后不吃香菜" and facts[0].version == 1
            fact_id = facts[0].id
            revision = await session.scalar(select(HealthMemoryRevision).where(HealthMemoryRevision.fact_id == fact_id))
            source = await session.get(Message, revision.source_message_id)
            assert source.request_id == request and revision.source_run_id == run_id and source.role == "user"
            assert revision.content == facts[0].content
        duplicate = await client.post("/api/agent/runs", headers=headers, json=body)
        assert duplicate.json()["run_id"] == run_id
        # 另两轮分别读取及无工具沿用旧回答，验证依赖传播至摘要。
        for step in ("read_memory", "derived_memory", "update_memory"):
            followup = str(uuid4())
            requests.append(followup)
            response = await client.post(
                "/api/agent/runs",
                headers=headers,
                json={
                    **body,
                    "query": f"HEALTH_CONSULTATION_E2E:{token}:{step}"
                    + ("\n我以后会吃香菜" if step == "update_memory" else ""),
                    "meta": {"request_id": followup},
                },
            )
            assert response.status_code == 200
            await collect_sse(client, headers, response.json()["run_id"])
            async with pg_manager.get_async_session_context() as session:
                followed = await session.get(AgentRun, response.json()["run_id"])
                assert followed.status == "completed", (followed.error_type, followed.error_message)
                version = 2 if step == "update_memory" else 1
                assert await session.get(HealthMemoryUse, (followed.id, fact_id, version)) is not None
                if step == "update_memory":
                    assert await session.get(HealthMemoryUse, (followed.id, fact_id, 1)) is None
        revoke_key = str(uuid4())
        revoked = await client.post(
            f"{ROOT}/memory/{fact_id}/revoke",
            headers={**headers, "Idempotency-Key": revoke_key, "If-Match": '"2"'},
            json={"client_request_id": revoke_key, "version": 2},
        )
        assert revoked.status_code == 200 and revoked.json()["version"] == 3
        current = HumanMessage(content="新问题", additional_kwargs={"health_request_id": "fresh"})
        # 真实 PG 依赖对照没有任何工具收据的历史，模拟提交后的 checkpoint 中断。
        lost_receipt_history = [
            item
            for old_request in requests
            for item in (
                HumanMessage(content="合成旧提问", additional_kwargs={"health_request_id": old_request}),
                AIMessage(content="合成旧记忆回答"),
            )
        ] + [current]
        assert await filter_memory_history(
            SimpleNamespace(uid=users[0]["uid"], thread_id=thread), lost_receipt_history
        ) == [current]
        request2 = str(uuid4())
        requests.append(request2)
        second = await client.post(
            "/api/agent/runs",
            headers=headers,
            json={**body, "query": f"HEALTH_CONSULTATION_E2E:{token}:empty_memory", "meta": {"request_id": request2}},
        )
        assert second.status_code == 200, second.text
        await collect_sse(client, headers, second.json()["run_id"])
        async with pg_manager.get_async_session_context() as session:
            run2 = await session.get(AgentRun, second.json()["run_id"])
            assert run2.status == "completed", (run2.error_type, run2.error_message)
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(HealthMemoryRevision)
                    .where(HealthMemoryRevision.fact_id == fact_id)
                )
                == 3
            )
            day = await session.scalar(
                select(HealthDailyConversation).where(HealthDailyConversation.member_id == member)
            )
            day.business_date = business_date() - timedelta(days=1)
        # 等待 shipping worker 的分钟 cron；不在测试进程直接调用生成函数。
        async with asyncio.timeout(80):
            while True:
                summary = await client.get(f"{ROOT}/daily-conversations/{thread}/summary", headers=headers)
                assert summary.status_code == 200
                if summary.json()["status"] == "ready":
                    break
                await asyncio.sleep(1)
        snapshot = summary.json()
        assert snapshot["version"] == 1 and snapshot["summary"]["meal_plan_generated"] is False
        async with pg_manager.get_async_session_context() as session:
            sources = list(
                (
                    await session.scalars(
                        select(Message).where(
                            Message.request_id == request2,
                            Message.role.in_(("user", "assistant")),
                            Message.message_type == "text",
                            Message.content != "",
                        )
                    )
                ).all()
            )
            assert set(snapshot["summary"]["source_message_ids"]) == {row.id for row in sources}
            assert all(row["excerpt"] != "我以后不吃香菜" for row in snapshot["summary"]["excerpts"])
            day = await session.get(HealthDailyConversation, day.conversation_id)
            assert day.summary_generated_at and day.summary_version == 1
        refresh = await client.post(f"{ROOT}/daily-conversations/{thread}/summary", headers=headers)
        assert refresh.json()["version"] == 1
        denied_key = str(uuid4())
        denied = await client.post(
            "/api/agent/runs", headers=headers, json={**body, "meta": {"request_id": denied_key}}
        )
        assert denied.status_code == 409 and denied.json()["detail"] == "该日对话已归档，请进入今天的营养咨询"
        async with pg_manager.get_async_session_context() as session:
            for model in (Message, AgentRunRequest, AgentRun):
                assert await session.scalar(select(model).where(model.request_id == denied_key)) is None
    finally:
        await drain_requests(client, headers, requests)

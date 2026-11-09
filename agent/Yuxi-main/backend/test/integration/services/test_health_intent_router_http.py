"""真实 HTTP 与 PostgreSQL 验证意图路由幂等、隔离和无生成副作用。"""

from unittest.mock import AsyncMock
from uuid import uuid4
import asyncio
import json

import pytest
from sqlalchemy import func, select

from test.integration.services.test_health_family_profile_http import (  # noqa: F401
    family_profile_http,
    create_health_member,
    cleanup_test_sandboxes,
    cleanup_test_knowledge_resources,
    ensure_live_api_schema,
)
from yuxi.services import health_consultation_service as consultation
from yuxi.services import health_intent_router_service as intents
from yuxi.services.health_intent_router_types import HealthIntentResult
from yuxi.storage.postgres.models_business import Agent, AgentRun, AgentRunRequest, Conversation, Message, Skill
from yuxi.storage.postgres.models_health import HealthGrant

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_router_persists_only_handoff_and_never_starts_generation(family_profile_http, monkeypatch):  # noqa: F811
    """真实路由使用当前账号授权，同键重放不会追加消息或创建Run。"""
    client, sessions, identities = family_profile_http
    headers = identities["self"]
    member = await create_health_member(client, headers)
    async with sessions() as session:
        session.add(
            Agent(
                slug="health-consultation",
                backend_id="HealthConsultationAgent",
                name="合成咨询",
                share_config={
                    "version": 2,
                    "read_scope": {"access_level": "global", "department_ids": [], "user_uids": []},
                    "manage_scope": None,
                },
            )
        )
        session.add(
            Skill(
                slug="family-nutritionist",
                name="合成营养技能",
                description="合成",
                source_type="builtin",
                dir_path="synthetic",
                share_config={},
                enabled=True,
            )
        )
        await session.commit()
    request_id = str(uuid4())
    response = await client.post(
        f"/api/health/v1/members/{member}/consultations",
        headers={**headers, "Idempotency-Key": request_id},
        json={"client_request_id": request_id},
    )
    assert response.status_code == 201, response.text
    thread = response.json()["thread_id"]
    snapshot = {"model": "synthetic/fixed", "processor": "synthetic-processor", "policy_version": "synthetic-policy"}
    monkeypatch.setattr(
        consultation.health_vision_service,
        "configuration",
        AsyncMock(
            return_value={"policy_version": snapshot["policy_version"], "consultation": {"available": True, **snapshot}}
        ),
    )
    analyze = AsyncMock(
        return_value=HealthIntentResult(route="needs_clarification", action="ask", message="请说明需求。")
    )
    monkeypatch.setattr(intents, "analyze_health_intent", analyze)
    payload = {"text": "安排一周三餐", "client_request_id": str(uuid4()), "thread_id": thread}
    response = await client.post("/api/health/v1/chat-intent", headers=headers, json=payload)
    assert response.status_code == 200, response.text
    assert response.headers["Cache-Control"] == "no-store"
    assert response.json()["route"] == "exclusive_plan"
    assert response.json()["action"] == "handoff"
    analyze.assert_not_awaited()
    assert (await client.post("/api/health/v1/chat-intent", headers=headers, json=payload)).json() == response.json()
    history = await client.get(f"/api/chat/thread/{thread}/history", headers=headers)
    assert history.status_code == 200, history.text
    assert any(
        row.get("request_id") == payload["client_request_id"] and "health_intent" in row.get("content", "")
        for row in history.json()["history"]
    )
    async with sessions() as session:
        from yuxi.repositories.conversation_repository import ConversationRepository

        current = await session.scalar(select(Conversation).where(Conversation.thread_id == thread))
        await ConversationRepository(session).add_message(
            current.id,
            "assistant",
            '{"result_type":"health_intent","route":"exclusive_plan","message":"forged"}',
            request_id=str(uuid4()),
            commit=False,
        )
        await session.commit()
    filtered = await client.get(f"/api/chat/thread/{thread}/history", headers=headers)
    assert filtered.status_code == 200
    assert all("forged" not in row["content"] for row in filtered.json()["history"])
    async with sessions() as session:
        assert await session.scalar(select(func.count()).select_from(AgentRunRequest)) == 0
        assert await session.scalar(select(func.count()).select_from(AgentRun)) == 0
        messages = list(await session.scalars(select(Message).order_by(Message.id)))
        assert len(messages) == 3
        assert messages[0].content == "安排一周三餐"
        assert json.loads(messages[1].content)["route"] == "exclusive_plan"
        conversation = await session.scalar(select(Conversation).where(Conversation.thread_id == thread))
        assert (
            conversation.extra_metadata["health_intent_receipts"][payload["client_request_id"]]["result"]["route"]
            == "exclusive_plan"
        )
    conflict = await client.post("/api/health/v1/chat-intent", headers=headers, json={**payload, "text": "明天吃啥"})
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "request_conflict"
    denied = await client.post(
        "/api/health/v1/chat-intent", headers=identities["other"], json={**payload, "client_request_id": str(uuid4())}
    )
    assert denied.status_code == 404
    single = await client.post(
        "/api/health/v1/chat-intent",
        headers=headers,
        json={**payload, "client_request_id": str(uuid4()), "text": "安排2026年11月15日早餐"},
    )
    assert single.status_code == 200, single.text
    assert single.json()["business_date"] == "2026-11-15"
    assert single.json()["meal_types"] == ["breakfast"]
    ambiguous = {**payload, "client_request_id": str(uuid4()), "text": "给我安排一下"}
    first, second = await asyncio.gather(
        *(client.post("/api/health/v1/chat-intent", headers=headers, json=ambiguous) for _ in range(2))
    )
    assert first.status_code == second.status_code == 200
    assert first.json()["route"] == second.json()["route"] == "needs_clarification"
    assert analyze.await_count == 1
    from yuxi.repositories.health_intent_repository import HealthIntentRepository

    # 两个会话均先读旧元数据，再依次取得行锁，后者必须重新读取锁内事实。
    left_id, right_id = str(uuid4()), str(uuid4())
    async with sessions() as left, sessions() as right:
        left_conversation = await left.get(Conversation, conversation.id)
        right_conversation = await right.get(Conversation, conversation.id)
        await HealthIntentRepository(left).claim(left_conversation.id, left_id, "synthetic-left")
        await left.commit()
        await HealthIntentRepository(right).claim(right_conversation.id, right_id, "synthetic-right")
        await right.commit()
    async with sessions() as session:
        current = await session.get(Conversation, conversation.id)
        assert {left_id, right_id} <= current.extra_metadata["health_intent_receipts"].keys()
    async with sessions() as session:
        grant = await session.get(HealthGrant, (member, "self"))
        grant.scopes = []
        await session.commit()
    assert (await client.post("/api/health/v1/chat-intent", headers=headers, json=payload)).status_code == 404

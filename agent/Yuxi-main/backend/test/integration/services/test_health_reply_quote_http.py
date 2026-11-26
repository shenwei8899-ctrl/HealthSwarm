"""真实 HTTP 与 PostgreSQL 验证意图路由幂等、隔离和无生成副作用。"""

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy import select

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
from yuxi.storage.postgres.models_business import Agent, AgentRun, Conversation, Message, Skill

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_selected_quote_roundtrip_authorization_and_source_invalidation(family_profile_http, monkeypatch):  # noqa: F811
    """真实HTTP和PG证明引用保存、同键重放、伪造拒绝及来源失效清理。"""
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
    notice = await client.get("/api/service-notice")
    assert notice.status_code == 200, notice.text
    document = notice.json()
    accepted = await client.post(
        "/api/account/service-notice",
        headers=headers,
        json={
            "version": document["version"],
            "content_hash": document["content_hash"],
            "acknowledged": True,
        },
    )
    assert accepted.status_code == 200, accepted.text
    source_request = str(uuid4())
    source_payload = {"text": "安排一周三餐", "client_request_id": source_request, "thread_id": thread}
    source_result = await client.post("/api/health/v1/chat-intent", headers=headers, json=source_payload)
    assert source_result.status_code == 200, source_result.text
    passage = source_result.json()["message"]
    quote = {"source_thread_id": thread, "source_request_id": source_request, "text": passage}
    outgoing = {"text": "安排一周三餐", "client_request_id": str(uuid4()), "thread_id": thread, "reply_quote": quote}
    response = await client.post("/api/health/v1/chat-intent", headers=headers, json=outgoing)
    assert response.status_code == 200, response.text
    replay = await client.post("/api/health/v1/chat-intent", headers=headers, json=outgoing)
    assert replay.status_code == 200 and replay.json() == response.json()
    async with sessions() as session:
        stored = list(await session.scalars(select(Message).where(Message.request_id == outgoing["client_request_id"])))
        assert len(stored) == 2
        user_message = next(m for m in stored if m.role == "user")
        assert user_message.content == outgoing["text"]
        saved_quote = user_message.extra_metadata["reply_quote"]
        assert saved_quote["text"] == passage and isinstance(saved_quote["source_message_id"], int)
        intent_reply = next(m for m in stored if m.role == "assistant")
        intent_reply_id = intent_reply.id
    history = await client.get(f"/api/chat/thread/{thread}/history", headers=headers)
    assert history.status_code == 200, history.text
    user = next(
        m
        for m in history.json()["history"]
        if m.get("request_id") == outgoing["client_request_id"] and m["type"] == "human"
    )
    assert user["extra_metadata"]["reply_quote"] == saved_quote
    forged = await client.post(
        "/api/health/v1/chat-intent",
        headers=headers,
        json={**outgoing, "client_request_id": str(uuid4()), "reply_quote": {**quote, "text": "原回复没有这一句"}},
    )
    assert forged.status_code == 409, forged.text
    changed = await client.post(
        "/api/health/v1/chat-intent", headers=headers, json={**outgoing, "reply_quote": {**quote, "text": passage[:-1]}}
    )
    assert changed.status_code == 409, changed.text
    denied = await client.post(
        "/api/health/v1/chat-intent", headers=identities["other"], json={**outgoing, "client_request_id": str(uuid4())}
    )
    assert denied.status_code == 404, denied.text
    async with sessions() as session:
        current = await session.scalar(select(Conversation).where(Conversation.thread_id == thread))
        run = AgentRun(
            id=str(uuid4()),
            request_id=outgoing["client_request_id"],
            uid=current.uid,
            agent_slug="health-consultation",
            conversation_thread_id=thread,
            conversation_id=current.id,
            runtime_scope_id=thread,
            status="completed",
            input_message_id=user_message.id,
            input_payload={"health_processing": snapshot},
        )
        session.add(run)
        await session.flush()
        repeated = Message(
            conversation_id=current.id,
            run_id=run.id,
            request_id=run.request_id,
            role="assistant",
            message_type="text",
            delivery_status="complete",
            content="引用复述的正式答复",
        )
        session.add(repeated)
        await session.flush()
        run.output_message_id = repeated.id
        derived_run_id = run.id
        await session.commit()
    second_quote = {"source_thread_id": thread, "source_message_id": intent_reply_id, "text": passage}
    derived_intent = {
        "text": "安排一下",
        "thread_id": thread,
        "client_request_id": str(uuid4()),
        "reply_quote": second_quote,
    }
    derived = await client.post("/api/health/v1/chat-intent", headers=headers, json=derived_intent)
    assert derived.status_code == 200, derived.text
    assert derived.json()["route"] == "needs_clarification"
    before_revoke = await client.get(f"/api/chat/thread/{thread}/history", headers=headers)
    assert before_revoke.status_code == 200, before_revoke.text
    assert any(m["content"] == "引用复述的正式答复" for m in before_revoke.json()["history"])
    async with sessions() as session:
        original = await session.get(Message, saved_quote["source_message_id"])
        original.content = "来源已变化"
        await session.commit()
    changed_history = await client.get(f"/api/chat/thread/{thread}/history", headers=headers)
    assert changed_history.status_code == 200, changed_history.text
    user = next(
        m
        for m in changed_history.json()["history"]
        if m.get("request_id") == outgoing["client_request_id"] and m["type"] == "human"
    )
    assert user["extra_metadata"]["reply_quote"] == {"unavailable": True, "text": "原引用内容当前不可用"}
    assert "raw_message" not in user["extra_metadata"]

    assert all(m["content"] != "引用复述的正式答复" for m in changed_history.json()["history"])
    from yuxi.services.health_evidence_service import validate_evidence_publication
    from yuxi.services.health_vision_types import HealthVisionError

    async with sessions() as session:
        run = await session.get(AgentRun, derived_run_id)
        with pytest.raises(HealthVisionError):
            await validate_evidence_publication(session, run, "模型调用后来源才失效的复述")

    # 分类派生回复、再次引用和同键重放也必须随原来源失效。
    assert all(m.get("id") != intent_reply_id for m in changed_history.json()["history"])
    assert all(
        not (m.get("request_id") == derived_intent["client_request_id"] and m["type"] == "ai")
        for m in changed_history.json()["history"]
    )
    quote_invalid = await client.post(
        "/api/health/v1/chat-intent", headers=headers, json={**derived_intent, "client_request_id": str(uuid4())}
    )
    assert quote_invalid.status_code == 409, quote_invalid.text
    cached_invalid = await client.post("/api/health/v1/chat-intent", headers=headers, json=derived_intent)
    assert cached_invalid.status_code == 409, cached_invalid.text
    after_invalid = await client.post(
        "/api/health/v1/chat-intent",
        headers=headers,
        json={"text": "安排一下", "thread_id": thread, "client_request_id": str(uuid4())},
    )
    assert after_invalid.status_code == 200, after_invalid.text
    assert not any(row["role"] == "assistant" for row in analyze.await_args.args[4])

    # 未执行的旧输入不能污染后续当前输入，当前queued输入仍须被检查。
    create_id = str(uuid4())
    other = await client.post(
        f"/api/health/v1/members/{member}/consultations",
        headers={**headers, "Idempotency-Key": create_id},
        json={"client_request_id": create_id},
    )
    assert other.status_code == 201, other.text
    other_thread = other.json()["thread_id"]
    from types import SimpleNamespace
    from yuxi.services.health_reply_quote_service import validate_quote_dependencies

    async with sessions() as session:
        current = await session.scalar(select(Conversation).where(Conversation.thread_id == other_thread))
        for status in ("queued", "rejected", "cancelled"):
            session.add(
                Message(
                    conversation_id=current.id,
                    role="user",
                    content="未执行引用",
                    delivery_status=status,
                    extra_metadata={"reply_quote": saved_quote},
                )
            )
        await session.flush()
        neutral = Message(conversation_id=current.id, role="user", content="正常新问题", delivery_status="queued")
        session.add(neutral)
        await session.flush()
        pending_run = SimpleNamespace(
            id=str(uuid4()),
            conversation_id=current.id,
            conversation_thread_id=other_thread,
            input_message_id=neutral.id,
        )
        await validate_quote_dependencies(session, pending_run, current.uid)
        neutral.extra_metadata = {"reply_quote": saved_quote}
        await session.flush()
        with pytest.raises(HealthVisionError):
            await validate_quote_dependencies(session, pending_run, current.uid)

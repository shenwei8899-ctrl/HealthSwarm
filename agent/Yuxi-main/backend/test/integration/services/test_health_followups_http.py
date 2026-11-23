"""真实 TCP/PG 验证一次认领、公开投影、账号及当前授权边界。"""

# ruff: noqa: F401,F811 -- 复用独立 schema/TCP fixture，禁止外部资源清理。
import asyncio
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import text

from test.integration.services.test_health_family_profile_http import (
    family_profile_http,
    ensure_live_api_schema,
    cleanup_test_sandboxes,
    cleanup_test_knowledge_resources,
)
from yuxi.repositories.skill_repository import SkillRepository
from yuxi.services import health_followup_service as service
from yuxi.services.health_followup_types import ChatFollowupOutput
from yuxi.services.health_vision_service import health_vision_service
from yuxi.storage.postgres.models_business import AgentRun, Conversation, Message, Project
from yuxi.storage.postgres.models_health import FamilyMember, HealthConsultation, HealthGrant, HealthProcessingConsent
from yuxi.utils.datetime_utils import utc_now_naive

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]
POLICY = {"model": "synthetic:model", "processor": "synthetic", "policy_version": "synthetic-v1"}
ITEMS = [
    {"label": "只有15分钟怎么做", "question": "这份清淡晚餐只有15分钟准备，可以怎样调整？"},
    {"label": "换成不吃鱼的搭配", "question": "这份晚餐不吃鱼可以怎么替换？"},
]


async def answer_case(fixture, monkeypatch):
    """固定合成问答与正式绑定，所有读取及权限执行真实数据库路径。"""
    client, sessions, users = fixture

    async def configuration(db=None):
        return {"consultation": {"available": True, **POLICY}, "policy_version": POLICY["policy_version"]}

    async def skill(self, slug):
        return SimpleNamespace(source_type="builtin", enabled=True)

    monkeypatch.setattr(health_vision_service, "configuration", configuration)
    monkeypatch.setattr(SkillRepository, "get_by_slug", skill)
    member_id, project_id, thread_id, run_id, request_id = [str(uuid4()) for _ in range(5)]
    async with sessions.begin() as db:
        db.add(FamilyMember(id=member_id, owner_uid="self", display_name="合成成员", relationship_label="本人"))
        db.add(
            Project(
                id=project_id,
                uid="self",
                selection_status="implicit",
                directory_mode="managed",
                workdir_path=f"projects/{project_id}",
            )
        )
        await db.flush()
        db.add(
            HealthGrant(
                member_id=member_id, actor_uid="self", scopes=["ai_use", "profile_view", "diet_edit", "report_view"]
            )
        )
        db.add(
            HealthProcessingConsent(
                member_id=member_id,
                actor_uid="self",
                purpose="consultation",
                processor=POLICY["processor"],
                policy_version=POLICY["policy_version"],
            )
        )
        conversation = Conversation(
            uid="self", thread_id=thread_id, agent_id="health-consultation", project_id=project_id
        )
        db.add(conversation)
        await db.flush()
        db.add(
            HealthConsultation(
                conversation_id=conversation.id, member_id=member_id, actor_uid="self", request_id=str(uuid4())
            )
        )
        run = AgentRun(
            id=run_id,
            uid="self",
            conversation_id=conversation.id,
            conversation_thread_id=thread_id,
            runtime_scope_id=thread_id,
            agent_slug="health-consultation",
            status="completed",
            request_id=request_id,
            input_payload={"health_processing": POLICY},
        )
        db.add(run)
        await db.flush()
        question = Message(
            conversation_id=conversation.id,
            run_id=run_id,
            request_id=request_id,
            role="user",
            content="今晚想吃得清淡一点，有什么推荐？",
        )
        answer = Message(
            conversation_id=conversation.id,
            run_id=run_id,
            request_id=request_id,
            role="assistant",
            content="可以清蒸鱼、白灼西兰花，再配一小碗米饭。",
            extra_metadata={"private": "must stay private"},
        )
        audit = Message(
            conversation_id=conversation.id,
            run_id=run_id,
            request_id=request_id,
            role="assistant",
            message_type="model_audit",
            content="private audit",
        )
        db.add_all([question, answer, audit])
        await db.flush()
        run.input_message_id, run.output_message_id = question.id, answer.id
        result = dict(message_id=answer.id, audit_id=audit.id, thread_id=thread_id, run_id=run_id, member_id=member_id)
    result["path"] = f"/api/health/v1/consultations/{thread_id}/messages/{result['message_id']}/followups"
    return result


async def test_concurrent_post_generates_once_get_is_pure_and_history_restores(family_profile_http, monkeypatch):
    client, sessions, users = family_profile_http
    case = await answer_case(family_profile_http, monkeypatch)
    entered, release = asyncio.Event(), asyncio.Event()
    calls = []

    async def generate(*args):
        calls.append(args)
        entered.set()
        await release.wait()
        return ChatFollowupOutput(followups=ITEMS)

    monkeypatch.setattr(service, "generate_followups", generate)
    before = await client.get(case["path"], headers=users["self"])
    assert before.status_code == 200 and before.json()["status"] == "absent", before.text
    assert before.headers["cache-control"] == "no-store"
    assert not calls

    first = asyncio.create_task(client.post(case["path"], headers=users["self"]))
    await asyncio.wait_for(entered.wait(), 5)
    second = await client.post(case["path"], headers=users["self"])
    assert second.json()["status"] == "pending", second.text
    release.set()
    completed = await first
    assert completed.status_code == 200 and completed.json()["followups"] == ITEMS, completed.text
    assert len(calls) == 1
    for method in [client.get, client.post, client.get]:
        restored = await method(case["path"], headers=users["self"])
        assert restored.json() == completed.json()
    assert len(calls) == 1
    async with sessions() as db:
        stored = await db.get(Message, case["message_id"])
        xmin = await db.scalar(text("SELECT xmin::text FROM messages WHERE id=:id"), {"id": stored.id})
        assert stored.extra_metadata["private"] == "must stay private"
        assert (await db.get(AgentRun, case["run_id"])).status == "completed"
    await client.get(case["path"], headers=users["self"])
    async with sessions() as db:
        assert await db.scalar(text("SELECT xmin::text FROM messages WHERE id=:id"), {"id": case["message_id"]}) == xmin
    history = await client.get(f"/api/chat/thread/{case['thread_id']}/history", headers=users["self"])
    assert history.status_code == 200, history.text
    answer = next(row for row in history.json()["history"] if row["id"] == case["message_id"])
    assert answer["followups"] == ITEMS
    assert "must stay private" not in history.text


async def test_foreign_threads_audit_messages_and_revocation_never_generate(family_profile_http, monkeypatch):
    client, sessions, users = family_profile_http
    case = await answer_case(family_profile_http, monkeypatch)
    calls = []

    async def generate(*args):
        calls.append(args)
        return ChatFollowupOutput()

    monkeypatch.setattr(service, "generate_followups", generate)
    for user in ["other", "admin"]:
        assert (await client.post(case["path"], headers=users[user])).status_code == 404
    audit_path = case["path"].replace(f"/messages/{case['message_id']}/", f"/messages/{case['audit_id']}/")
    assert (await client.post(audit_path, headers=users["self"])).status_code == 404
    wrong_thread = case["path"].replace(case["thread_id"], str(uuid4()))
    assert (await client.post(wrong_thread, headers=users["self"])).status_code == 404
    async with sessions.begin() as db:
        grant = await db.get(HealthGrant, (case["member_id"], "self"))
        grant.revoked_at = utc_now_naive()
    assert (await client.post(case["path"], headers=users["self"])).status_code == 404
    assert not calls


async def test_revocation_while_generating_cannot_publish_suggestions(family_profile_http, monkeypatch):
    """生成开始后的撤权仍在保存边界被拒绝，不修改原答复或 Run 终态。"""
    client, sessions, users = family_profile_http
    case = await answer_case(family_profile_http, monkeypatch)
    entered, release = asyncio.Event(), asyncio.Event()

    async def generate(*args):
        entered.set()
        await release.wait()
        return ChatFollowupOutput(followups=ITEMS)

    monkeypatch.setattr(service, "generate_followups", generate)
    flight = asyncio.create_task(client.post(case["path"], headers=users["self"]))
    await asyncio.wait_for(entered.wait(), 5)
    async with sessions.begin() as db:
        grant = await db.get(HealthGrant, (case["member_id"], "self"))
        grant.revoked_at = utc_now_naive()
    release.set()
    denied = await flight
    assert denied.status_code == 404, denied.text
    async with sessions() as db:
        message = await db.get(Message, case["message_id"])
        assert message.extra_metadata["health_context_followups"]["status"] == "pending"
        assert message.content == "可以清蒸鱼、白灼西兰花，再配一小碗米饭。"
        assert (await db.get(AgentRun, case["run_id"])).status == "completed"


async def test_revocation_during_budget_wait_never_sends_answer(family_profile_http, monkeypatch):
    """真实HTTP/PG在预算等待中撤权，外部模型不得收到已读问答。"""
    from unittest.mock import AsyncMock
    from yuxi.services import health_ai_budget_service as budget

    client, sessions, users = family_profile_http
    case = await answer_case(family_profile_http, monkeypatch)
    entered, release = asyncio.Event(), asyncio.Event()
    reservation = object()
    model = SimpleNamespace(ainvoke=AsyncMock())
    settle = AsyncMock()

    async def reserve(*args):
        entered.set()
        await release.wait()
        return reservation

    monkeypatch.setattr(budget, "reserve_model", reserve)
    monkeypatch.setattr(budget, "reserved_chat_model", lambda *args, **kwargs: model)
    monkeypatch.setattr(budget, "settle", settle)
    flight = asyncio.create_task(client.post(case["path"], headers=users["self"]))
    await asyncio.wait_for(entered.wait(), 5)
    async with sessions.begin() as db:
        grant = await db.get(HealthGrant, (case["member_id"], "self"))
        grant.revoked_at = utc_now_naive()
    release.set()
    denied = await flight
    assert denied.status_code == 404, denied.text
    model.ainvoke.assert_not_awaited()
    settle.assert_awaited_once_with(reservation, None)
    async with sessions() as db:
        message = await db.get(Message, case["message_id"])
        assert message.extra_metadata["health_context_followups"]["status"] == "pending"
        assert (await db.get(AgentRun, case["run_id"])).status == "completed"

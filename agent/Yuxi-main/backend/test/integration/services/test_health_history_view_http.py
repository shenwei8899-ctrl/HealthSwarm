"""真实 HTTP / PostgreSQL 区分资料改版回看、继续执行与撤权。"""
# ruff: noqa: F811 -- pytest 复用真实 HTTP 与隔离数据库 fixture。

import pytest
from uuid import uuid4
from fastapi import HTTPException
from sqlalchemy import select

from test.integration.services.test_health_family_profile_http import (  # noqa: F401
    cleanup_test_knowledge_resources,
    cleanup_test_sandboxes,
    ensure_live_api_schema,
    family_profile_http,
    linked_self,
    recorded_profile_use,
    SYNTHETIC_PROFILE,
)
from test.integration.services.test_reference_meal_plan_http import (
    bind_reference,
    complete,
    grounded_plan,
    running_context,
    setup_reference,
)
from test.integration.services.test_onboarding_preparation_http import isolate_delivery  # noqa: F401
from yuxi.repositories.conversation_repository import ConversationRepository
from yuxi.repositories.health_family_profile_repository import HealthFamilyProfileRepository
from yuxi.services.conversation_service import require_user_conversation
from yuxi.storage.postgres.models_business import (
    AgentRun,
    Conversation,
    FamilyMember,
    Message,
    User,
    TOOL_AUDIT_MESSAGE_TYPE,
)
from yuxi.storage.postgres.models_health import HealthFamilyProfileLink, HealthMemoryFact, HealthMemoryUse
from yuxi.storage.postgres.models_health import FamilyMember as HealthMember
from yuxi.storage.postgres.models_knowledge import KnowledgeFile

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]
ROOT = "/api/health/v1"
ANSWER = "合成历史答复：按当时资料提供的饮食建议。"


async def memory_use(db, run, member, source):
    """持久化具有当前家庭来源的真实版本依赖。"""
    fact = HealthMemoryFact(
        id=str(uuid4()),
        actor_uid="self",
        member_id=member,
        fact_key="history-preference",
        kind="preference",
        content="合成偏好",
        provenance={"family_id": source["family_id"], "source_member_id": source["source_member_id"]},
    )
    db.add(fact)
    await db.flush()
    db.add(HealthMemoryUse(run_id=run.id, fact_id=fact.id, version=fact.version))
    return fact.id


async def published_consultation(fixture):
    """保存同 Run 权威最终消息及真实档案依赖，再通过正式接口改版。"""
    client, sessions, users = fixture
    member, source = await linked_self(client, users["self"])
    binding, _ = await recorded_profile_use(sessions, member, "self")
    async with sessions.begin() as db:
        conversation = await db.get(Conversation, binding.conversation_id)
        run = await db.scalar(select(AgentRun).where(AgentRun.conversation_id == conversation.id))
        run.manifest = {"resources": {"tools": ["query_family_nutrition_knowledge", "get_complete_health_profile"]}}
        question = Message(
            conversation_id=conversation.id, role="user", content="合成历史首问", request_id=run.request_id
        )
        answer = Message(
            conversation_id=conversation.id,
            run_id=run.id,
            request_id=run.request_id,
            role="assistant",
            content=ANSWER,
            delivery_status="complete",
        )
        db.add_all([question, answer])
        await db.flush()
        run.input_message_id = question.id
        run.output_message_id = answer.id
        thread, run_id = conversation.thread_id, run.id
    changed = await client.put(
        f"/api/family/{source['family_id']}/members/{source['source_member_id']}",
        headers=users["self"],
        json={"expected_version": 2, "profile": {"height_cm": 171}},
    )
    assert changed.status_code == 200, changed.text
    return member, source, thread, run_id


async def test_changed_profile_history_keeps_original_answer_but_not_execution_or_quote(family_profile_http):
    """正常改版后能回看；同一历史不能被引用或继续执行。"""
    client, sessions, users = family_profile_http
    member, _, thread, run_id = await published_consultation(family_profile_http)
    history = await client.get(f"/api/chat/thread/{thread}/history", headers=users["self"])
    assert history.status_code == 200, history.text
    assert history.json()["thread"]["history_read_only"] is True
    assert "仅供历史回看" in history.json()["thread"]["history_notice"]
    assert ANSWER in [row["content"] for row in history.json()["history"]]
    directory = await client.get(f"{ROOT}/members/{member}/consultations", headers=users["self"])
    assert directory.status_code == 200, directory.text
    row = next(row for row in directory.json()["items"] if row["thread_id"] == thread)
    assert row["unavailable"] is False and row["title"] == "合成历史首问"
    async with sessions() as db:
        with pytest.raises(HTTPException) as error:
            await require_user_conversation(ConversationRepository(db), thread, "self")
        assert error.value.status_code == 404
    citations = await client.get(f"{ROOT}/consultation-runs/{run_id}/citations", headers=users["self"])
    assert citations.status_code == 404, citations.text
    assert (await client.get(f"/api/chat/thread/{thread}/history", headers=users["other"])).status_code == 404


@pytest.mark.parametrize("withdrawal", ["inactive_source", "removed_link", "deleted_user"])
async def test_changed_profile_history_cannot_bypass_withdrawal(family_profile_http, withdrawal):
    """改版回看不覆盖真实来源撤销、身份关联丢失或账号停用。"""
    client, sessions, users = family_profile_http
    member, source, thread, _ = await published_consultation(family_profile_http)
    async with sessions.begin() as db:
        if withdrawal == "inactive_source":
            (await db.get(FamilyMember, source["source_member_id"])).is_active = False
        elif withdrawal == "removed_link":
            await db.delete(await db.get(HealthFamilyProfileLink, member))
        else:
            (await db.scalar(select(User).where(User.uid == "self"))).is_deleted = 1
    denied = await client.get(f"/api/chat/thread/{thread}/history", headers=users["self"])
    assert denied.status_code in {401, 403, 404}, denied.text
    assert ANSWER not in denied.text


async def test_changed_profile_history_hides_answer_after_memory_withdrawal(family_profile_http):
    """允许档案改版不复活已经撤回的自述记忆及其派生答复。"""
    client, sessions, users = family_profile_http
    member, source, thread, run_id = await published_consultation(family_profile_http)
    async with sessions.begin() as db:
        fact_id = await memory_use(db, await db.get(AgentRun, run_id), member, source)
    path = f"/api/chat/thread/{thread}/history"
    before = await client.get(path, headers=users["self"])
    assert before.status_code == 200 and ANSWER in before.text
    async with sessions.begin() as db:
        (await db.get(HealthMemoryFact, fact_id)).status = "revoked"
    after = await client.get(path, headers=users["self"])
    assert after.status_code == 200 and ANSWER not in after.text
    assert "合成历史首问" in after.text


async def test_family_profile_dependencies_keep_conversation_anchor_and_recheck_each_source(family_profile_http):
    """家庭上下文的来源成员可异于会话锚点；每个真实来源仍须获授权。"""
    client, sessions, users = family_profile_http
    anchor, source, thread, run_id = await published_consultation(family_profile_http)
    other_source, other_health = str(uuid4()), str(uuid4())
    async with sessions.begin() as db:
        db.add(
            FamilyMember(
                id=other_source,
                family_id=source["family_id"],
                name="合成家人",
                relationship="母亲",
                profile=dict(SYNTHETIC_PROFILE),
                version=4,
            )
        )
        db.add(HealthMember(id=other_health, owner_uid="self", display_name="合成家人", relationship_label="母亲"))
        await db.flush()
        db.add(
            HealthFamilyProfileLink(
                member_id=other_health, source_member_id=other_source, family_id=source["family_id"], actor_uid="self"
            )
        )
        await db.flush()
        profiles = HealthFamilyProfileRepository(db)
        payload = await profiles.read("self", other_health, family_assistant=True, audit=False)
        await profiles.record_use(await db.get(AgentRun, run_id), payload)
    path = f"/api/chat/thread/{thread}/history"
    before = await client.get(path, headers=users["self"])
    assert before.status_code == 200 and ANSWER in before.text, before.text
    assert before.json()["thread"]["history_read_only"] is True
    async with sessions.begin() as db:
        (await db.get(FamilyMember, other_source)).is_active = False
    after = await client.get(path, headers=users["self"])
    assert after.status_code == 404 and ANSWER not in after.text


@pytest.mark.parametrize("withdrawal", ["knowledge_deleted", "memory_revoked"])
async def test_reference_history_after_profile_change_still_rechecks_recipe_access(
    family_profile_http, monkeypatch, withdrawal
):
    """参考餐单回看保留原回执，不能复用当前业务动作或读取已撤销知识来源。"""
    current = await setup_reference(family_profile_http, monkeypatch)
    client, sessions, users, _, actor, _ = current
    bound = await bind_reference(current)
    assert bound.status_code == 200, bound.text
    context = await running_context(current, bound.json()["thread_id"])
    plan, _, _ = await grounded_plan(current, context)
    await complete(current, context, plan)
    async with sessions.begin() as db:
        run = await db.get(AgentRun, context.run_id)
        final = await db.get(Message, run.output_message_id)
        final.extra_metadata = {
            **(final.extra_metadata or {}),
            "reasoning_content": "不应公开的中间推理",
            "additional_kwargs": {"reasoning_content": "不应公开的中间推理"},
        }
        db.add_all(
            [
                Message(
                    conversation_id=run.conversation_id,
                    run_id=run.id,
                    request_id=run.request_id,
                    role="tool",
                    message_type=TOOL_AUDIT_MESSAGE_TYPE,
                    content="不应公开的中间工具记录",
                    extra_metadata={"tool_name": "diagnostic_private_tool"},
                    execution_status="completed",
                ),
                Message(
                    conversation_id=run.conversation_id,
                    run_id=run.id,
                    request_id=run.request_id,
                    role="assistant",
                    content="不应公开的中间答复",
                    delivery_status="complete",
                ),
            ]
        )
        link = await db.scalar(select(HealthFamilyProfileLink).where(HealthFamilyProfileLink.source_member_id == actor))
        profiles = HealthFamilyProfileRepository(db)
        await profiles.record_use(run, await profiles.read("self", link.member_id, family_assistant=True))
        fact_id = await memory_use(
            db, run, link.member_id, {"family_id": current[5]["family_id"], "source_member_id": actor}
        )
        member = await db.get(FamilyMember, actor)
        member.profile = {**member.profile, "height_cm": 171}
        member.version += 1
    path = f"/api/chat/thread/{context.thread_id}/history"
    history = await client.get(path, headers=users["self"])
    assert history.status_code == 200, history.text
    assert history.json()["thread"]["history_read_only"] is True
    assert plan["preview_id"] in history.text
    assert "不应公开的中间" not in history.text
    result = next(row for row in history.json()["history"] if row["type"] == "ai")
    import json

    frozen = json.loads(result["content"])
    assert frozen["meals"] == plan["meals"] and frozen["purchase_ready"] is False
    assert "purchase_validation_version" not in frozen
    assert (await client.get(path, headers=users["other"])).status_code == 404
    strict = await client.get(f"{ROOT}/reference-meal-plans/{plan['preview_id']}", headers=users["self"])
    assert strict.status_code == 410, strict.text
    async with sessions.begin() as db:
        if withdrawal == "knowledge_deleted":
            (await db.scalar(select(KnowledgeFile).where(KnowledgeFile.file_id == "reference-file"))).status = "deleted"
        else:
            (await db.get(HealthMemoryFact, fact_id)).status = "revoked"
    withdrawn = await client.get(path, headers=users["self"])
    assert withdrawn.status_code == 404, withdrawn.text
    assert plan["preview_id"] not in withdrawn.text

"""成员记忆管理与每日入口的真实 HTTP、PG 验证。"""

import asyncio
from copy import deepcopy
from datetime import timedelta
import json
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from test.integration.services.test_health_vision_http import ROOT, create_member, health_http  # noqa: F401
from test.integration.services.test_health_family_profile_http import family_profile_http  # noqa: F401
from langchain_core.messages import HumanMessage, ToolMessage
from yuxi.services.health_memory_service import filter_memory_history, memory_result
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_business import Conversation, Project
from yuxi.storage.postgres.models_health import (
    HealthConsultation,
    HealthDailyConversation,
    HealthMemoryFact,
    HealthMemoryRevision,
)
from yuxi.services.health_daily_service import business_date
from yuxi.repositories.health_memory_repository import HealthMemoryRepository

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_checkpoint_memory_projection_uses_real_persisted_fact_and_bound_member(family_profile_http):  # noqa: F811
    """HTTP创建的成员与真实PG绑定只允许原始正文、kind及本成员投影进入模型。"""
    client, sessions, identities = family_profile_http
    headers = identities["self"]
    member_id = await create_member(client, headers)
    other_member_id = await create_member(client, headers)
    thread_id, project_id = str(uuid4()), str(uuid4())
    fact_ids = [str(uuid4()), str(uuid4())]
    async with sessions() as session:
        session.add(
            Project(
                id=project_id,
                uid="self",
                selection_status="implicit",
                directory_mode="managed",
                workdir_path=f"projects/{project_id}",
            )
        )
        await session.flush()
        conversation = Conversation(
            uid="self", thread_id=thread_id, project_id=project_id, agent_id="health-consultation"
        )
        session.add(conversation)
        await session.flush()
        session.add(
            HealthConsultation(
                conversation_id=conversation.id, member_id=member_id, actor_uid="self", request_id=str(uuid4())
            )
        )
        for fact_id, selected_member in zip(fact_ids, [member_id, other_member_id]):
            session.add(
                HealthMemoryFact(
                    id=fact_id,
                    actor_uid="self",
                    member_id=selected_member,
                    fact_key="avoid_coriander",
                    kind="preference",
                    content="我以后不吃香菜",
                    version=1,
                    status="active",
                )
            )
        await session.commit()
    context = SimpleNamespace(uid="self", thread_id=thread_id)
    async with sessions() as session:
        repository = HealthMemoryRepository(session)
        original = memory_result(await repository.get("self", fact_ids[0]))
        other = memory_result(await repository.get("self", fact_ids[1]))
        for tool_name in ("get_member_memories", "remember_member_fact"):

            def messages(reference):
                """仅改变待校验checkpoint，数据库事实保持原值。"""
                payload = (
                    {"memories": [reference], "truncated": False}
                    if tool_name == "get_member_memories"
                    else {**reference, "written_version": 1, "replayed": False}
                )
                return [
                    HumanMessage(content="合成问题"),
                    ToolMessage(name=tool_name, tool_call_id="synthetic-call", content=json.dumps(payload)),
                ]

            assert await filter_memory_history(
                context, messages(original), session=session, persist_uses=False
            ) == messages(original)
            for field, value in (
                ("content", "我患有糖尿病"),
                ("kind", "health_self_report"),
                ("source_type", "confirmed_profile"),
                ("version", True),
            ):
                forged = deepcopy(original)
                forged[field] = value
                with pytest.raises(HealthVisionError, match="memory_history_invalid"):
                    await filter_memory_history(context, messages(forged), session=session, persist_uses=False)
            with pytest.raises(HealthVisionError, match="memory_history_invalid"):
                await filter_memory_history(context, messages(other), session=session, persist_uses=False)
            for mutation in ("record_extra", "envelope_extra", "error_status"):
                tool_messages = messages(original)
                payload = json.loads(tool_messages[-1].content)
                if mutation == "record_extra":
                    target = payload["memories"][0] if tool_name == "get_member_memories" else payload
                    target["diagnosis"] = "未经来源确认的合成诊断"
                else:
                    payload["extra_body"] = "未经来源确认的合成诊断"
                tool_messages[-1] = tool_messages[-1].model_copy(
                    update={
                        "content": json.dumps(payload),
                        "status": "error" if mutation == "error_status" else "success",
                    }
                )
                with pytest.raises(HealthVisionError, match="memory_history_invalid"):
                    await filter_memory_history(context, tool_messages, session=session, persist_uses=False)
        actual = await repository.get("self", fact_ids[0])
        assert actual.content == "我以后不吃香菜" and actual.kind == "preference" and actual.version == 1


async def test_private_memory_management_keeps_versions_and_replay_tombstone(health_http):  # noqa: F811
    """真实管理入口不授权管理员旁路；撤回重复操作不会复活旧版本。"""
    client, users = health_http
    uid, headers = users[0]["uid"], users[0]["headers"]
    member = await create_member(client, headers)
    fact_id = str(uuid4())
    async with pg_manager.get_async_session_context() as session:
        session.add(
            HealthMemoryFact(
                id=fact_id,
                actor_uid=uid,
                member_id=member,
                fact_key="avoid_coriander",
                kind="preference",
                content="合成长期偏好",
                version=1,
                status="active",
            )
        )
        await session.flush()
        session.add(
            HealthMemoryRevision(
                id=str(uuid4()),
                fact_id=fact_id,
                actor_uid=uid,
                version=1,
                request_id=str(uuid4()),
                source_hash="a" * 64,
                content="合成长期偏好",
                kind="preference",
                status="active",
            )
        )
    for actor in users[1:]:
        assert (await client.get(f"{ROOT}/memory/{fact_id}", headers=actor["headers"])).status_code == 404
    edited_key = str(uuid4())
    edited = {
        "client_request_id": edited_key,
        "version": 1,
        "kind": "health_self_report",
        "content": "合成用户健康自述",
    }
    edit_headers = {**headers, "Idempotency-Key": edited_key, "If-Match": '"1"'}
    async with pg_manager.get_async_session_context() as reader:
        repo = HealthMemoryRepository(reader)
        original = await repo.get(uid, fact_id)
        assert original.version == 1
        response = await client.patch(f"{ROOT}/memory/{fact_id}", headers=edit_headers, json=edited)
        refreshed = await repo.get(uid, fact_id)
        assert refreshed is original and refreshed.version == 2
    assert response.status_code == 200 and response.json()["version"] == 2
    assert response.json()["professional_review"] == "not_reviewed" and response.json()["formal_profile"] is False
    assert (await client.patch(f"{ROOT}/memory/{fact_id}", headers=edit_headers, json=edited)).json()["version"] == 2
    conflict = {**edited, "client_request_id": str(uuid4()), "content": "另一条合成内容"}
    assert (
        await client.patch(
            f"{ROOT}/memory/{fact_id}",
            headers={**edit_headers, "Idempotency-Key": conflict["client_request_id"]},
            json=conflict,
        )
    ).status_code == 409
    revoke_key = str(uuid4())
    revoke = {"client_request_id": revoke_key, "version": 2}
    revoke_headers = {**headers, "Idempotency-Key": revoke_key, "If-Match": '"2"'}
    assert (await client.delete(f"{ROOT}/memory/{fact_id}", headers=headers)).status_code == 422
    for _ in range(2):
        result = await client.post(f"{ROOT}/memory/{fact_id}/revoke", headers=revoke_headers, json=revoke)
        assert result.status_code == 200 and result.json()["status"] == "revoked" and result.json()["version"] == 3
    assert (await client.patch(f"{ROOT}/memory/{fact_id}", headers=edit_headers, json=edited)).json()[
        "status"
    ] == "revoked"
    assert (await client.get(f"{ROOT}/members/{member}/memory", headers=headers)).json()["memories"] == []
    history = (await client.get(f"{ROOT}/memory/{fact_id}", headers=headers)).json()
    assert [row["version"] for row in history["revisions"]] == [1, 2, 3]
    async with pg_manager.get_async_session_context() as session:
        assert (
            await session.scalar(
                select(func.count()).select_from(HealthMemoryRevision).where(HealthMemoryRevision.fact_id == fact_id)
            )
            == 3
        )
    revoked = await client.put(
        f"{ROOT}/members/{member}/grants", headers=headers, json={"actor_uid": uid, "scopes": []}
    )
    assert revoked.status_code == 200
    assert (await client.get(f"{ROOT}/members/{member}/memory", headers=headers)).status_code == 404


async def test_daily_entry_concurrency_archive_and_summary_replay(health_http):  # noqa: F811
    """当前日期唯一，历史私有且补跑不增加重复摘要版本。"""
    client, users = health_http
    headers = users[0]["headers"]
    member = await create_member(client, headers)
    endpoint = f"{ROOT}/members/{member}/daily-consultations"
    responses = await asyncio.gather(*[client.post(endpoint, headers=headers) for _ in range(5)])
    assert all(row.status_code == 201 for row in responses)
    thread = responses[0].json()["thread_id"]
    assert {row.json()["thread_id"] for row in responses} == {thread}
    assert responses[0].json()["business_date"] == business_date().isoformat()
    deleted = await client.delete(f"/api/chat/thread/{thread}", headers=headers)
    assert deleted.status_code == 409
    assert (await client.post(endpoint, headers=headers)).json()["thread_id"] == thread
    assert (await client.post(f"{ROOT}/daily-conversations/{thread}/summary", headers=headers)).status_code == 409
    async with pg_manager.get_async_session_context() as session:
        day = await session.scalar(select(HealthDailyConversation).where(HealthDailyConversation.member_id == member))
        assert (
            await session.scalar(
                select(func.count())
                .select_from(HealthDailyConversation)
                .where(HealthDailyConversation.member_id == member)
            )
            == 1
        )
        day.business_date = business_date() - timedelta(days=1)
        binding = await session.get(HealthConsultation, day.conversation_id)
        binding.request_id = str(uuid4())  # 合成昨日创建键，今天应使用不同的服务器日键。
    newer = await client.post(endpoint, headers=headers)
    assert newer.status_code == 201 and newer.json()["thread_id"] != thread
    for actor in users[1:]:
        assert (
            await client.get(f"{ROOT}/daily-conversations/{thread}/summary", headers=actor["headers"])
        ).status_code == 404
    first = await client.post(f"{ROOT}/daily-conversations/{thread}/summary", headers=headers)
    assert first.status_code == 200 and first.json()["status"] == "ready"
    assert first.json()["summary"]["source_message_ids"] == []
    repeated = await client.post(f"{ROOT}/daily-conversations/{thread}/summary", headers=headers)
    assert repeated.json()["version"] == first.json()["version"] == 1
    days = (await client.get(f"{ROOT}/members/{member}/daily-conversations", headers=headers)).json()["days"]
    assert [row["date"] for row in days] == [
        business_date().isoformat(),
        (business_date() - timedelta(days=1)).isoformat(),
    ]
    async with pg_manager.get_async_session_context() as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(Conversation)
                .join(HealthConsultation)
                .where(HealthConsultation.member_id == member)
            )
            == 2
        )
    assert (await client.delete(f"/api/chat/thread/{thread}", headers=headers)).status_code == 200
    assert (await client.post(endpoint, headers=headers)).json()["thread_id"] == newer.json()["thread_id"]

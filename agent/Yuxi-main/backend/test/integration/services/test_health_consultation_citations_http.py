"""真实HTTP与PG最终引用投影；所有变更限定本次合成账号。"""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select

from test.integration.services.test_health_vision_http import ROOT, create_member, health_http  # noqa: F401
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_business import AgentRun, Conversation, Message, User
from yuxi.storage.postgres.models_health import HealthGrant, NutritionEvidence, NutritionEvidenceCitation
from yuxi.utils.datetime_utils import utc_now_naive

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def citation_case(client, users):
    """通过正式发布/绑定HTTP创建来源，再持久化精确同Run引用与最终消息。"""
    owner, _, admin = users
    member_id = await create_member(client, owner["headers"])
    second_member_id = await create_member(client, owner["headers"])
    key = str(uuid4())
    bound = await client.post(
        f"{ROOT}/members/{member_id}/consultations",
        headers={**owner["headers"], "Idempotency-Key": key},
        json={"client_request_id": key},
    )
    assert bound.status_code == 201, bound.text
    thread_id = bound.json()["thread_id"]
    sources = []
    for title in ("第一条", "第二条", "未采用的检索片段"):
        body = {
            "source_ref": f"synthetic://citations/{uuid4()}",
            "source_version": "synthetic-v1",
            "title": title,
            "content": f"合成引用内容：{title}",
            "review_ref": "synthetic://citations/review",
            "reviewed_by": "synthetic-reviewer",
            "reviewed_at": (datetime.now(UTC) - timedelta(days=1)).isoformat(),
            "valid_until": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
        }
        published = await client.post(f"{ROOT}/nutrition-evidence", headers=admin["headers"], json=body)
        assert published.status_code == 201, published.text
        sources.append({"id": published.json()["evidence_id"], **body})
    run_id, old_run_id = str(uuid4()), str(uuid4())
    ids = [str(uuid4()) for _ in range(4)]
    async with pg_manager.get_async_session_context() as session:
        conversation = await session.scalar(select(Conversation).where(Conversation.thread_id == thread_id))
        for identity in (run_id, old_run_id):
            session.add(
                AgentRun(
                    id=identity,
                    request_id=str(uuid4()),
                    uid=owner["uid"],
                    agent_slug="health-consultation",
                    conversation_thread_id=thread_id,
                    conversation_id=conversation.id,
                    runtime_scope_id=thread_id,
                    status="completed",
                    input_payload={},
                )
            )
        await session.flush()
        for index, citation_id in enumerate(ids):
            source = await session.get(NutritionEvidence, sources[index % 3]["id"])
            session.add(
                NutritionEvidenceCitation(
                    id=citation_id,
                    evidence_id=source.id,
                    run_id=run_id if index < 3 else old_run_id,
                    conversation_id=conversation.id,
                    member_id=member_id,
                    actor_uid=owner["uid"],
                    content_hash=source.content_hash,
                )
            )
        run = await session.get(AgentRun, run_id)
        answer = Message(
            conversation_id=conversation.id,
            run_id=run_id,
            request_id=run.request_id,
            role="assistant",
            message_type="text",
            delivery_status="complete",
            content=f"私有咨询正文 [证据:{ids[1]}] [证据:{ids[0]}] [证据:{ids[1]}]",
        )
        session.add(answer)
        await session.flush()
        run.output_message_id = answer.id
        audit = Message(
            conversation_id=conversation.id,
            run_id=run_id,
            request_id=run.request_id,
            role="assistant",
            message_type="model_audit",
            content="私有模型审计",
        )
        session.add(audit)
        await session.flush()
        return dict(
            run_id=run_id,
            old_run_id=old_run_id,
            ids=ids,
            sources=sources,
            member_id=member_id,
            second_member_id=second_member_id,
            thread_id=thread_id,
            conversation_id=conversation.id,
            final_message_id=answer.id,
            audit_id=audit.id,
            request_id=run.request_id,
            answer=answer.content,
        )


async def test_final_citations_are_ordered_subset_with_no_admin_or_foreign_access(health_http):  # noqa: F811
    """未采用检索和后写审计不出现；即使superadmin也无患者正文旁路。"""
    client, users = health_http
    case = await citation_case(client, users)
    path = f"{ROOT}/consultation-runs/{case['run_id']}/citations"
    response = await client.get(path, headers=users[0]["headers"])
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    result = response.json()
    assert set(result) == {
        "result_type",
        "status",
        "agent_run_id",
        "request_id",
        "thread_id",
        "member_id",
        "final_message_id",
        "citations",
    }
    assert result == {
        "result_type": "nutrition_citations",
        "status": "cited",
        "agent_run_id": case["run_id"],
        "request_id": case["request_id"],
        "thread_id": case["thread_id"],
        "member_id": case["member_id"],
        "final_message_id": case["final_message_id"],
        "citations": result["citations"],
    }
    assert [row["citation_id"] for row in result["citations"]] == [case["ids"][1], case["ids"][0]]
    for row, source in zip(result["citations"], (case["sources"][1], case["sources"][0]), strict=True):
        assert set(row) == {
            "citation_id",
            "evidence_id",
            "title",
            "content",
            "source_ref",
            "source_version",
            "reviewed_at",
            "scope",
        }
        assert row["evidence_id"] == source["id"] and row["content"] == source["content"]
        assert row["source_ref"] == source["source_ref"] and row["source_version"] == "synthetic-v1"
        assert row["scope"] == "general_education"
    assert "私有咨询正文" not in response.text and "私有模型审计" not in response.text
    assert case["ids"][2] not in response.text and case["ids"][3] not in response.text
    for actor in (users[1], users[2]):
        denied = await client.get(path, headers=actor["headers"])
        assert denied.status_code == 404 and "合成引用内容" not in denied.text
    async with pg_manager.get_async_session_context() as session:
        (await session.scalar(select(User).where(User.uid == users[2]["uid"]))).role = "superadmin"
    assert (await client.get(path, headers=users[2]["headers"])).status_code == 404
    assert (await client.get(path)).status_code == 401
    async with pg_manager.get_async_session_context() as session:
        (await session.get(Message, case["final_message_id"])).content = "信息不足，请补充问题。"
    empty = await client.get(path, headers=users[0]["headers"])
    assert empty.status_code == 200 and empty.json()["status"] == "not_cited"
    assert empty.json()["citations"] == []


async def test_final_citation_scope_pointer_status_and_current_source_rejections(health_http):  # noqa: F811
    """每项篡改经真实HTTP拒绝且恢复，撤回授权后不能读取既有答复。"""
    client, users = health_http
    case = await citation_case(client, users)
    path = f"{ROOT}/consultation-runs/{case['run_id']}/citations"
    mutations = [
        (AgentRun, case["run_id"], "status", "pending", 409, "answer_not_completed"),
        (AgentRun, case["run_id"], "agent_slug", "health-meal-planner", 404, "not_found"),
        (AgentRun, case["run_id"], "output_message_id", None, 409, "answer_unavailable"),
        (AgentRun, case["run_id"], "output_message_id", case["audit_id"], 409, "answer_unavailable"),
        (AgentRun, case["run_id"], "conversation_id", None, 404, "not_found"),
        (Message, case["final_message_id"], "run_id", case["old_run_id"], 409, "answer_unavailable"),
        (Message, case["final_message_id"], "request_id", str(uuid4()), 409, "answer_unavailable"),
        (Message, case["final_message_id"], "role", "user", 409, "answer_unavailable"),
        (Message, case["final_message_id"], "delivery_status", "failed", 409, "answer_unavailable"),
        (Message, case["final_message_id"], "content", "[证据:forged]", 409, "citation_invalid"),
        (Message, case["final_message_id"], "content", f"[证据:{case['ids'][3]}]", 409, "citation_invalid"),
        (NutritionEvidenceCitation, case["ids"][0], "actor_uid", users[1]["uid"], 409, "citation_invalid"),
        (NutritionEvidenceCitation, case["ids"][0], "member_id", case["second_member_id"], 409, "citation_invalid"),
        (NutritionEvidenceCitation, case["ids"][0], "content_hash", "0" * 64, 410, "source_invalidated"),
        (NutritionEvidence, case["sources"][0]["id"], "revoked_at", utc_now_naive(), 410, "source_invalidated"),
        (
            NutritionEvidence,
            case["sources"][0]["id"],
            "valid_until",
            utc_now_naive() - timedelta(seconds=1),
            410,
            "source_invalidated",
        ),
        (NutritionEvidence, case["sources"][0]["id"], "content", "未审核的篡改内容", 410, "source_invalidated"),
    ]
    for model, identity, field, value, status, code in mutations:
        async with pg_manager.get_async_session_context() as session:
            row = await session.get(model, identity)
            original = getattr(row, field)
            setattr(row, field, value)
        try:
            rejected = await client.get(path, headers=users[0]["headers"])
            assert rejected.status_code == status, (field, rejected.text)
            assert rejected.json()["code"] == code, (field, rejected.text)
            assert "合成引用内容" not in rejected.text and "私有咨询正文" not in rejected.text
        finally:
            async with pg_manager.get_async_session_context() as session:
                setattr(await session.get(model, identity), field, original)
    async with pg_manager.get_async_session_context() as session:
        grants = await session.scalars(select(HealthGrant).where(HealthGrant.member_id == case["member_id"]))
        for grant in grants:
            grant.revoked_at = utc_now_naive()
    denied = await client.get(path, headers=users[0]["headers"])
    assert denied.status_code == 404 and "合成引用内容" not in denied.text

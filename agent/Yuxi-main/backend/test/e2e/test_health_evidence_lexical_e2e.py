"""受限词法索引真实 HTTP→Worker→最终引用和独立 evidence-ID gold。"""

import json
import os
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import select

from test.e2e.test_health_consultation_e2e import collect_sse, drain_requests, isolated_health  # noqa: F401
from test.integration.services.test_health_evidence_lexical_http import publish
from test.integration.services.test_health_task_http import verified_task_cleanup  # noqa: F401
from test.integration.services.test_health_vision_http import ROOT, create_member, health_http  # noqa: F401
from test.support.health_evidence_evaluation import evaluate_evidence_retrieval
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_business import AgentRun, Message
from yuxi.storage.postgres.models_health import NutritionEvidence, NutritionEvidenceCitation
from yuxi.utils.datetime_utils import utc_now_naive

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.e2e,
    pytest.mark.slow,
    pytest.mark.skipif(os.getenv("HEALTH_CONSULTATION_E2E_ISOLATED") != "true", reason="仅在独立合成槽位运行"),
]


async def test_lexical_worker_current_gold_citations_and_source_rebuild(isolated_health):  # noqa: F811
    """分散关键词真实采用两条 gold，撤回/过期后 fresh thread 只采用新版本。"""
    client, users, configuration, _ = isolated_health
    headers, admin = users[0]["headers"], users[2]["headers"]
    token, requests = uuid4().hex, []
    first, first_body = await publish(client, admin, token, "first")
    second, second_body = await publish(client, admin, token, "second")
    gold_bodies = {first: first_body, second: second_body}
    member_id = await create_member(client, headers)
    consent = await client.post(
        f"{ROOT}/members/{member_id}/processing-consents",
        headers=headers,
        json={
            "purpose": "consultation",
            "accepted": True,
            "processor": configuration["consultation"]["processor"],
            "policy_version": configuration["policy_version"],
        },
    )
    assert consent.status_code == 200

    async def run_query(mode, gold):
        key, request_id = str(uuid4()), str(uuid4())
        bound = await client.post(
            f"{ROOT}/members/{member_id}/consultations",
            headers={**headers, "Idempotency-Key": key},
            json={"client_request_id": key},
        )
        assert bound.status_code == 201, bound.text
        thread_id = bound.json()["thread_id"]
        requests.append(request_id)
        started = await client.post(
            "/api/agent/runs",
            headers=headers,
            json={
                "query": f"HEALTH_CONSULTATION_E2E:{token}:{mode}",
                "agent_slug": "health-consultation",
                "thread_id": thread_id,
                "meta": {"request_id": request_id},
            },
        )
        assert started.status_code == 200, started.text
        run_id = started.json()["run_id"]
        events = await collect_sse(client, headers, run_id)
        assert events[-1][0] == "end" and events[-1][1]["request_id"] == request_id
        result = await client.get(f"/api/agent/runs/{run_id}/result", headers=headers)
        assert result.json()["status"] == "completed", result.text
        response = await client.get(f"{ROOT}/consultation-runs/{run_id}/citations", headers=headers)
        assert response.status_code == 200 and response.headers["cache-control"] == "no-store", response.text
        adopted = response.json()["citations"]
        actual_ids = [citation["evidence_id"] for citation in adopted]
        assert len(actual_ids) == len(set(actual_ids)) == len(gold)
        assert set(actual_ids) == set(gold), "gold was declared from published source IDs before the model call"
        async with pg_manager.get_async_session_context() as session:
            run = await session.get(AgentRun, run_id)
            answer = await session.get(Message, run.output_message_id)
            expected = "合成词法科普 " + " ".join(f"[证据:{citation['citation_id']}]" for citation in adopted)
            assert answer.content == result.json()["output"] == expected
            assert run.output_message_id == response.json()["final_message_id"]
            assert run.request_id == request_id and run.conversation_thread_id == thread_id
            persisted = list(
                await session.scalars(
                    select(NutritionEvidenceCitation).where(NutritionEvidenceCitation.run_id == run_id)
                )
            )
            assert {citation.id for citation in persisted} == {citation["citation_id"] for citation in adopted}
            assert all(
                citation.actor_uid == users[0]["uid"] and citation.member_id == member_id for citation in persisted
            )
            final_id, final_text = answer.id, answer.content
        for citation in adopted:
            body = gold_bodies[citation["evidence_id"]]
            assert citation["content"] == body["content"] and citation["source_ref"] == body["source_ref"]
            assert citation["source_version"] == body["source_version"] and citation["scope"] == "general_education"
        scores = evaluate_evidence_retrieval(actual_ids, gold, k=len(gold))
        assert scores["metrics"] == {f"recall@{len(gold)}": 1.0, f"f1@{len(gold)}": 1.0}
        return run_id, adopted, final_id, final_text, scores, thread_id

    try:
        original_run, original_citations, _, original_text, original_scores, original_thread = await run_query(
            "lexical", [first, second]
        )
        saved = await pg_manager.get_langgraph_checkpointer().aget_tuple(
            {"configurable": {"uid": users[0]["uid"], "thread_id": original_thread, "checkpoint_ns": ""}}
        )
        assert saved is not None
        checkpoint_messages = saved.checkpoint["channel_values"]["messages"]
        knowledge_outputs = [
            json.loads(message.content)
            for message in checkpoint_messages
            if getattr(message, "type", None) == "tool"
            and getattr(message, "name", None) == "query_reviewed_nutrition_knowledge"
        ]
        assert len(knowledge_outputs) == 1
        assert {row["evidence_id"] for row in knowledge_outputs[0]["citations"]} == {first, second}
        before_state = await client.get(
            f"/api/chat/thread/{original_thread}/state", headers=headers, params={"include_messages": "true"}
        )
        assert before_state.status_code == 200 and original_text in before_state.text
        assert first_body["content"] not in before_state.text and second_body["content"] not in before_state.text
        assert (await client.delete(f"{ROOT}/nutrition-evidence/{first}", headers=admin)).status_code == 200
        async with pg_manager.get_async_session_context() as session:
            (await session.get(NutritionEvidence, second)).valid_until = utc_now_naive() - timedelta(seconds=1)
        invalid = await client.get(f"{ROOT}/consultation-runs/{original_run}/citations", headers=headers)
        assert invalid.status_code == 410 and invalid.json()["code"] == "source_invalidated"
        assert first_body["content"] not in invalid.text and "合成词法科普" not in invalid.text
        blocked_result = await client.get(f"/api/agent/runs/{original_run}/result", headers=headers)
        assert blocked_result.status_code == 410 and "合成词法科普" not in blocked_result.text
        for suffix in ("history", "state?include_messages=true"):
            projected = await client.get(f"/api/chat/thread/{original_thread}/{suffix}", headers=headers)
            assert projected.status_code == 200
            assert "合成词法科普" not in projected.text and first_body["content"] not in projected.text
        searched = await client.get(
            "/api/chat/threads/search",
            headers=headers,
            params={"q": "合成词法科普", "agent_id": "health-consultation"},
        )
        assert searched.status_code == 200 and searched.json()["items"] == []
        restored, restored_body = await publish(client, admin, token, "first", version="v2")
        gold_bodies[restored] = restored_body
        rebuilt_run, rebuilt_citations, final_id, final_text, rebuilt_scores, _ = await run_query(
            "lexical_rebuilt", [restored]
        )
        assert {citation["evidence_id"] for citation in rebuilt_citations}.isdisjoint({first, second})
        async with pg_manager.get_async_session_context() as session:
            (
                await session.get(Message, final_id)
            ).content = f"伪造旧Run引用 [证据:{original_citations[0]['citation_id']}]"
        forged = await client.get(f"{ROOT}/consultation-runs/{rebuilt_run}/citations", headers=headers)
        assert forged.status_code == 409 and forged.json()["code"] == "citation_invalid"
        assert restored_body["content"] not in forged.text
        async with pg_manager.get_async_session_context() as session:
            (await session.get(Message, final_id)).content = final_text
        assert (
            await client.get(f"{ROOT}/consultation-runs/{rebuilt_run}/citations", headers=headers)
        ).status_code == 200
        async with httpx.AsyncClient(base_url="http://localhost:8766", timeout=10) as replay:
            calls = (await replay.get("/observations", params={"token": token})).json()["calls"]
        assert [call["step"] for call in calls] == ["lexical", "lexical", "lexical_rebuilt", "lexical_rebuilt"]
        report = Path("test/.tmp/health-evidence-lexical/gold-readback.json")
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(
            json.dumps(
                {
                    "gold_ids": [first, second],
                    "original_run": original_run,
                    "original": original_scores,
                    "rebuilt_id": restored,
                    "rebuilt_run": rebuilt_run,
                    "rebuilt": rebuilt_scores,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
    finally:
        await drain_requests(client, headers, requests)

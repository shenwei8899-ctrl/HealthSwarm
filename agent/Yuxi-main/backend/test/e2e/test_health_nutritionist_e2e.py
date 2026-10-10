"""隔离真实 HTTP、PG 和 worker 的审核证据闭环。"""

import os
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import select

from test.e2e.test_health_consultation_e2e import (
    collect_sse,
    drain_requests,
    isolated_health,  # noqa: F401
)
from test.integration.services.test_health_task_http import verified_task_cleanup  # noqa: F401
from test.integration.services.test_health_vision_http import ROOT, create_member, health_http  # noqa: F401
from yuxi.repositories.health_evidence_repository import HealthEvidenceRepository
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_business import AgentRun, Message
from yuxi.storage.postgres.models_health import HealthConsultation, NutritionEvidence, NutritionEvidenceCitation
from yuxi.utils.datetime_utils import utc_now_naive

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.e2e,
    pytest.mark.slow,
    pytest.mark.skipif(os.getenv("HEALTH_CONSULTATION_E2E_ISOLATED") != "true", reason="仅在独立合成槽位运行"),
]


async def test_reviewed_evidence_worker_citations_and_revoked_history(isolated_health):  # noqa: F811
    """回读引用所属运行，撤回后新请求在外呼前终止。"""
    client, users, configuration, _ = isolated_health
    headers, admin = users[0]["headers"], users[2]["headers"]
    source = {
        "source_ref": "synthetic://nutrition/source",
        "source_version": "synthetic-v1",
        "title": "合成营养证据",
        "content": "合成营养证据：此文本只用于协议验收。",
        "review_ref": "synthetic://nutrition/review",
        "reviewed_by": "synthetic-professional-reviewer",
        "reviewed_at": (datetime.now(UTC) - timedelta(days=1)).isoformat(),
        "valid_until": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
    }
    denied = await client.post(f"{ROOT}/nutrition-evidence", headers=headers, json=source)
    assert denied.status_code == 403
    async with pg_manager.get_async_session_context() as session:
        assert (
            await session.scalar(select(NutritionEvidence).where(NutritionEvidence.published_by == users[0]["uid"]))
            is None
        )
    published = await client.post(f"{ROOT}/nutrition-evidence", headers=admin, json=source)
    assert published.status_code == 201, published.text
    evidence_id = published.json()["evidence_id"]
    for kind in ("revoked", "expired"):
        excluded = await client.post(
            f"{ROOT}/nutrition-evidence",
            headers=admin,
            json={**source, "content": f"合成营养证据：{kind} 片段不得检索。"},
        )
        assert excluded.status_code == 201
        excluded_id = excluded.json()["evidence_id"]
        if kind == "revoked":
            assert (await client.delete(f"{ROOT}/nutrition-evidence/{excluded_id}", headers=admin)).status_code == 200
        else:
            async with pg_manager.get_async_session_context() as session:
                expired = await session.get(NutritionEvidence, excluded_id)
                expired.valid_until = utc_now_naive() - timedelta(seconds=1)
    async with pg_manager.get_async_session_context() as session:
        repository = HealthEvidenceRepository(session)
        assert [row.id for row in await repository.search("合成营养证据")] == [evidence_id]
        assert await repository.search("%") == []
        assert await repository.search("不存在的合成词") == []
    roles = await client.get(f"{ROOT}/agent-roles", headers=headers)
    assert roles.status_code == 200 and roles.json()["full_health_profile_available"] is False
    native_skills = await client.get("/api/skills/accessible", headers=headers)
    assert native_skills.status_code == 200
    native = next(item for item in native_skills.json()["data"] if item["slug"] == "family-nutritionist")
    assert native["name"] == "家庭营养师" and native["is_builtin"] is True
    assert set(native["tool_dependencies"]) == {
        "get_confirmed_profile",
        "get_confirmed_diet",
        "get_complete_health_profile",
        "get_member_weight_records",
        "get_member_blood_pressure_records",
        "get_member_blood_glucose_records",
        "get_member_blood_lipids_records",
        "query_reviewed_nutrition_knowledge",
        "get_member_memories",
        "remember_member_fact",
        "get_meal_feedback",
    }
    member_id = await create_member(client, headers)
    key = str(uuid4())
    bound = await client.post(
        f"{ROOT}/members/{member_id}/consultations",
        headers={**headers, "Idempotency-Key": key},
        json={"client_request_id": key},
    )
    assert bound.status_code == 201
    thread_id = bound.json()["thread_id"]
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
    requests, token = [], uuid4().hex
    try:
        request_id = str(uuid4())
        requests.append(request_id)
        body = {
            "query": f"HEALTH_CONSULTATION_E2E:{token}:evidence",
            "agent_slug": "health-consultation",
            "thread_id": thread_id,
            "meta": {"request_id": request_id},
        }
        started = await client.post("/api/agent/runs", headers=headers, json=body)
        assert started.status_code == 200, started.text
        run_id = started.json()["run_id"]
        events = await collect_sse(client, headers, run_id)
        assert events[-1][0] == "end" and events[-1][1]["request_id"] == request_id
        result = await client.get(f"/api/agent/runs/{run_id}/result", headers=headers)
        assert result.json()["status"] == "completed", result.text
        async with pg_manager.get_async_session_context() as session:
            citation = await session.scalar(
                select(NutritionEvidenceCitation).where(NutritionEvidenceCitation.run_id == run_id)
            )
            assert citation and citation.evidence_id == evidence_id and citation.member_id == member_id
            assert citation.actor_uid == users[0]["uid"]
            run = await session.get(AgentRun, run_id)
            output = await session.get(Message, run.output_message_id)
            assert output.content == result.json()["output"] == f"合成科普说明 [证据:{citation.id}]"
            binding = await session.get(HealthConsultation, citation.conversation_id)
            repo = HealthEvidenceRepository(session)
            await repo.validate_citations([citation.id], binding, users[0]["uid"], run_id=run_id)
            original = await session.get(NutritionEvidence, evidence_id)
            original.content = "合成篡改内容"
            await session.flush()
            with pytest.raises(HealthVisionError, match="source_invalidated"):
                await repo.validate_citations([citation.id], binding, users[0]["uid"], run_id=run_id)
            original.content = source["content"]
            await session.flush()
            for wrong_uid, wrong_run, wrong_member in (
                (users[1]["uid"], run_id, member_id),
                (users[0]["uid"], str(uuid4()), member_id),
                (users[0]["uid"], run_id, str(uuid4())),
            ):
                wrong_binding = SimpleNamespace(conversation_id=binding.conversation_id, member_id=wrong_member)
                with pytest.raises(HealthVisionError, match="citation_invalid"):
                    await repo.validate_citations([citation.id], wrong_binding, wrong_uid, run_id=wrong_run)
        citation_result = await client.get(f"{ROOT}/consultation-runs/{run_id}/citations", headers=headers)
        assert citation_result.status_code == 200, citation_result.text
        citation_data = citation_result.json()
        assert citation_data["status"] == "cited" and citation_data["agent_run_id"] == run_id
        assert citation_data["request_id"] == request_id and citation_data["member_id"] == member_id
        assert citation_data["thread_id"] == thread_id and citation_data["final_message_id"] == output.id
        assert citation_data["citations"] == [
            {
                "citation_id": citation.id,
                "evidence_id": evidence_id,
                "title": source["title"],
                "content": source["content"],
                "source_ref": source["source_ref"],
                "source_version": source["source_version"],
                "reviewed_at": citation_data["citations"][0]["reviewed_at"],
                "scope": "general_education",
            }
        ]
        assert "output" not in citation_data
        for actor in (users[1], users[2]):
            denied = await client.get(f"{ROOT}/consultation-runs/{run_id}/citations", headers=actor["headers"])
            assert denied.status_code == 404 and source["content"] not in denied.text
        bad_key = str(uuid4())
        bad_bound = await client.post(
            f"{ROOT}/members/{member_id}/consultations",
            headers={**headers, "Idempotency-Key": bad_key},
            json={"client_request_id": bad_key},
        )
        assert bad_bound.status_code == 201
        bad_request = str(uuid4())
        requests.append(bad_request)
        bad_started = await client.post(
            "/api/agent/runs",
            headers=headers,
            json={
                **body,
                "query": f"HEALTH_CONSULTATION_E2E:{uuid4().hex}:invalid_evidence",
                "thread_id": bad_bound.json()["thread_id"],
                "meta": {"request_id": bad_request},
            },
        )
        assert bad_started.status_code == 200
        bad_run_id = bad_started.json()["run_id"]
        await collect_sse(client, headers, bad_run_id)
        bad_result = await client.get(f"/api/agent/runs/{bad_run_id}/result", headers=headers)
        assert bad_result.json()["status"] == "failed", bad_result.text
        bad_citations = await client.get(f"{ROOT}/consultation-runs/{bad_run_id}/citations", headers=headers)
        assert bad_citations.status_code == 409 and bad_citations.json()["code"] == "answer_not_completed"
        async with pg_manager.get_async_session_context() as session:
            bad_run = await session.get(AgentRun, bad_run_id)
            assert "citation_invalid" in bad_run.error_message
            assert (
                await session.scalar(
                    select(NutritionEvidenceCitation).where(NutritionEvidenceCitation.run_id == bad_run_id)
                )
                is not None
            )
            assert bad_run.output_message_id is None and bad_result.json()["final_message_id"] is None
            assert not list(
                await session.scalars(
                    select(Message).where(
                        Message.run_id == bad_run_id, Message.role == "assistant", Message.message_type == "text"
                    )
                )
            )
            assert list(
                await session.scalars(
                    select(Message).where(Message.run_id == bad_run_id, Message.message_type == "model_audit")
                )
            ), "失败模型过程仍须保留受访问控制的私有审计"
        denied_revoke = await client.delete(f"{ROOT}/nutrition-evidence/{evidence_id}", headers=headers)
        assert denied_revoke.status_code == 403
        revoked = await client.delete(f"{ROOT}/nutrition-evidence/{evidence_id}", headers=admin)
        assert revoked.status_code == 200
        withdrawn = await client.get(f"{ROOT}/consultation-runs/{run_id}/citations", headers=headers)
        assert withdrawn.status_code == 410 and withdrawn.json()["code"] == "source_invalidated"
        assert source["content"] not in withdrawn.text and "合成科普说明" not in withdrawn.text
        async with pg_manager.get_async_session_context() as session:
            assert (await session.get(NutritionEvidence, evidence_id)).revoked_at is not None
            with pytest.raises(HealthVisionError, match="source_invalidated"):
                await HealthEvidenceRepository(session).validate_citations([citation.id], binding, users[0]["uid"])
        async with httpx.AsyncClient(base_url="http://localhost:8766", timeout=10) as replay:
            calls = (await replay.get("/observations", params={"token": token})).json()["calls"]
            assert len(calls) == 2 and calls[-1]["record_ids"] == [citation.id]
            request_id = str(uuid4())
            requests.append(request_id)
            rejected = await client.post(
                "/api/agent/runs", headers=headers, json={**body, "meta": {"request_id": request_id}}
            )
            assert rejected.status_code == 200
            rejected_id = rejected.json()["run_id"]
            await collect_sse(client, headers, rejected_id)
            failed = await client.get(f"/api/agent/runs/{rejected_id}/result", headers=headers)
            assert failed.json()["status"] == "failed", failed.text
            async with pg_manager.get_async_session_context() as session:
                failed_run = await session.get(AgentRun, rejected_id)
                assert failed_run.error_type == "unexpected_error" and "source_invalidated" in failed_run.error_message
                assert (
                    await session.scalar(
                        select(NutritionEvidenceCitation).where(NutritionEvidenceCitation.run_id == rejected_id)
                    )
                    is None
                )
            assert (await replay.get("/observations", params={"token": token})).json()["calls"] == calls
    finally:
        await drain_requests(client, headers, requests)

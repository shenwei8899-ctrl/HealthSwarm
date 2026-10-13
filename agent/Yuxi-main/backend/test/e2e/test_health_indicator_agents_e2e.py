"""独立指标Agent经真实HTTP、Worker、SSE和PG的两工具验收。"""

import os
import socket
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import delete, select

from test.e2e.test_health_blood_glucose_e2e import add_blood_glucose, correct_blood_glucose
from test.e2e.test_health_blood_lipids_e2e import add_blood_lipids, correct_blood_lipids
from test.e2e.test_health_blood_pressure_e2e import add_blood_pressure, correct_blood_pressure
from test.e2e.test_health_consultation_e2e import drain_requests, isolated_health, wait_until  # noqa: F401
from test.e2e.test_health_task_e2e import run_task
from test.integration.services.test_health_task_http import entry, owned_counts, verified_task_cleanup  # noqa: F401
from test.integration.services.test_health_vision_http import ROOT, create_member, health_http  # noqa: F401
from test.integration.services.test_health_weight_http import cleanup_weight_subject, create_weight_subject
from test.support.health_indicator_replay_server import MODEL, PORT
from yuxi.services.run_queue_service import get_redis_client
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_business import AgentRun, FamilyMeasurement, Message
from yuxi.storage.postgres.models_health import (
    HealthBloodGlucoseUse,
    HealthBloodLipidsUse,
    HealthBloodPressureUse,
    HealthFamilyProfileUse,
    HealthWeightUse,
    NutritionEvidenceCitation,
)
from yuxi.storage.redis import close_async_redis_client

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.e2e,
    pytest.mark.slow,
    pytest.mark.skipif(os.getenv("HEALTH_CONSULTATION_E2E_ISOLATED") != "true", reason="仅在独立合成槽位运行"),
]
CASES = (
    ("blood_glucose", add_blood_glucose, correct_blood_glucose, HealthBloodGlucoseUse),
    ("blood_lipids", add_blood_lipids, correct_blood_lipids, HealthBloodLipidsUse),
    ("blood_pressure", add_blood_pressure, correct_blood_pressure, HealthBloodPressureUse),
)


@pytest.mark.parametrize("kind,add_record,correct_record,use_model", CASES)
async def test_three_indicator_agents_current_records_citations_correction_and_void(
    indicator_runtime, kind, add_record, correct_record, use_model
):
    """本人门禁先于写入；更正/作废及证据撤回均关闭旧公开结果。"""
    runtime = indicator_runtime
    await assert_rejected_entries(runtime, kind)
    subject = await create_weight_subject(runtime.client, runtime.users)
    subject.requests = runtime.requests
    limited = await runtime.client.put(
        f"{ROOT}/members/{subject.member_id}/grants",
        headers=subject.headers,
        json={"actor_uid": subject.uid, "scopes": ["ai_use", "profile_view"]},
    )
    assert limited.status_code == 200, limited.text
    token = uuid4().hex
    task_type, slug = f"{kind}_review", f"health-{kind.replace('_', '-')}"
    consent = await runtime.client.post(
        f"{ROOT}/members/{subject.member_id}/processing-consents",
        headers=subject.headers,
        json={
            "purpose": "consultation",
            "accepted": True,
            "processor": runtime.configuration["consultation"]["processor"],
            "policy_version": runtime.configuration["policy_version"],
        },
    )
    assert consent.status_code == 200, consent.text
    evidence = await runtime.client.post(
        f"{ROOT}/nutrition-evidence",
        headers=runtime.users[2]["headers"],
        json={
            "source_ref": f"synthetic://indicator/{token}",
            "source_version": "synthetic-v1",
            "title": f"合成指标科普 indicator{token}",
            "content": f"indicator{token} 此文本仅用于审核来源协议验收，不包含医学规则。",
            "review_ref": f"synthetic://indicator-review/{token}",
            "reviewed_by": "synthetic-reviewer",
            "reviewed_at": (datetime.now(UTC) - timedelta(days=1)).isoformat(),
            "valid_until": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
            "reviewed_scope": {
                "domains": [kind],
                "population_category": "general_education",
                "population_description": "合成通用指标教育，仅协议验收",
                "exclusion_conditions": [],
                "license_ref": f"synthetic://indicator-license/{token}",
            },
        },
    )
    assert evidence.status_code == 201, evidence.text
    evidence_id = evidence.json()["evidence_id"]
    try:
        record = await add_record(subject)
        for other_kind, other_add, _, _ in CASES:
            if other_kind != kind:
                await other_add(subject)
        first_entry = await indicator_entry(subject, task_type, slug)
        first_key, first_run, first = await run_task(
            subject.client, subject.headers, first_entry, f"INDICATOR_E2E:{token}:{kind}:read", runtime.requests
        )
        await assert_indicator_result(subject, first, first_run, kind, use_model, record["id"], 1, evidence_id)
        before = (await runtime.replay.get("/observations", params={"token": token})).json()["calls"]
        assert before == [
            {"kind": kind, "mode": "read", "phase": phase} for phase in ("records", "knowledge", "answer")
        ]
        corrected = await correct_record(subject, record["id"])
        assert corrected["version"] == 2
        await assert_invalidated_thread(subject, first_entry, first_key, first_run, f"{kind}_source_changed")
        rejected = await subject.client.post(
            "/api/agent/runs",
            headers=subject.headers,
            json={
                "agent_slug": slug,
                "thread_id": first_entry["thread_id"],
                "query": f"INDICATOR_E2E:{token}:{kind}:read",
                "meta": {"request_id": str(uuid4())},
            },
        )
        assert rejected.status_code == 410 and "detail" in rejected.json(), rejected.text
        assert (await runtime.replay.get("/observations", params={"token": token})).json()["calls"] == before

        second_entry = await indicator_entry(subject, task_type, slug)
        assert second_entry["thread_id"] != first_entry["thread_id"]
        second_key, second_run, second = await run_task(
            subject.client, subject.headers, second_entry, f"INDICATOR_E2E:{token}:{kind}:updated", runtime.requests
        )
        await assert_indicator_result(subject, second, second_run, kind, use_model, record["id"], 2, evidence_id)
        voided = await subject.client.post(
            f"{subject.measurement_path}/{record['id']}/void",
            headers=subject.headers,
            json={"expected_version": 2, "reason": "合成协议验收误录作废"},
        )
        assert voided.status_code == 200 and voided.json()["version"] == 3, voided.text
        async with pg_manager.get_async_session_context() as session:
            fact = await session.get(FamilyMeasurement, record["id"])
            assert fact.version == 3 and fact.voided_at is not None
            assert fact.previous[0]["version"] == 1 and fact.previous[1]["version"] == 2
        await assert_invalidated_thread(subject, second_entry, second_key, second_run, f"{kind}_source_changed")

        third_entry = await indicator_entry(subject, task_type, slug)
        third_key, third_run, third = await run_task(
            subject.client, subject.headers, third_entry, f"INDICATOR_E2E:{token}:{kind}:missing", runtime.requests
        )
        await assert_indicator_result(subject, third, third_run, kind, use_model, None, None, evidence_id)
        withdrawn = await subject.client.delete(
            f"{ROOT}/nutrition-evidence/{evidence_id}", headers=runtime.users[2]["headers"]
        )
        assert withdrawn.status_code == 200, withdrawn.text
        old_citations = await subject.client.get(
            f"{ROOT}/consultation-runs/{third_run}/citations", headers=subject.headers
        )
        assert old_citations.status_code == 410 and old_citations.json()["code"] == "source_invalidated", (
            old_citations.text
        )
        old_task = await subject.client.get(f"{ROOT}/tasks/{third_key}", headers=subject.headers)
        assert old_task.status_code == 410 and old_task.json()["code"] == "source_invalidated", old_task.text
        history = await subject.client.get(
            f"/api/chat/thread/{third_entry['thread_id']}/history", headers=subject.headers
        )
        assert history.status_code == 200 and not any(item["type"] == "ai" for item in history.json()["history"]), (
            history.text
        )
        fourth_entry = await indicator_entry(subject, task_type, slug)
        _, fourth_run, fourth = await run_task(
            subject.client, subject.headers, fourth_entry, f"INDICATOR_E2E:{token}:{kind}:missing", runtime.requests
        )
        await assert_indicator_result(subject, fourth, fourth_run, kind, use_model, None, None, None)
        assert "审核依据不足" in fourth["result"]["answer"]
    finally:
        await drain_requests(subject.client, subject.headers, runtime.requests)
        async with pg_manager.get_async_session_context() as session:
            for model in (HealthBloodGlucoseUse, HealthBloodLipidsUse, HealthBloodPressureUse, HealthFamilyProfileUse):
                await session.execute(delete(model).where(model.member_id == subject.member_id))
        await cleanup_weight_subject(subject)


async def assert_rejected_entries(runtime, kind):
    """非本人和缺档案读取权拒绝入口，不新增Project、Conversation、Request或Run。"""
    client, users = runtime.client, runtime.users
    owner = users[0]
    relative = await client.post(
        f"{ROOT}/members",
        headers=owner["headers"],
        json={"display_name": "合成亲属", "relationship_label": "父亲", "authorized": True},
    )
    assert relative.status_code == 201
    proxy = await create_member(client, users[1]["headers"])
    grant = await client.put(
        f"{ROOT}/members/{proxy}/grants",
        headers=users[1]["headers"],
        json={"actor_uid": owner["uid"], "scopes": ["profile_view", "ai_use", "report_view", "diet_edit"]},
    )
    assert grant.status_code == 200
    no_profile = await create_member(client, owner["headers"])
    revoked = await client.put(
        f"{ROOT}/members/{no_profile}/grants",
        headers=owner["headers"],
        json={"actor_uid": owner["uid"], "scopes": ["ai_use", "report_view", "diet_edit"]},
    )
    assert revoked.status_code == 200
    for member in (relative.json()["id"], proxy, no_profile):
        before = await owned_counts(owner["uid"])
        response = await entry(client, owner["headers"], member, f"{kind}_review")
        assert response.status_code == 404, response.text
        assert await owned_counts(owner["uid"]) == before


async def indicator_entry(subject, task_type, slug):
    """统一任务入口的角色和幂等性从真实响应核对。"""
    key = str(uuid4())
    response = await entry(subject.client, subject.headers, subject.member_id, task_type, key=key)
    assert response.status_code == 200, response.text
    bound = response.json()
    assert bound["entry_status"] == "ready" and bound["agent_slug"] == slug and bound["task_type"] == task_type
    repeated = await entry(subject.client, subject.headers, subject.member_id, task_type, key=key)
    assert repeated.status_code == 200 and repeated.json() == bound
    return bound


async def assert_indicator_result(subject, projected, run_id, kind, use_model, record_id, version, evidence_id):
    """核对同Run最终Message、固定工具Skill及对应来源回执，其他指标不旁读。"""
    answer = projected["result"]
    assert projected["task_type"] == f"{kind}_review" and projected["execution_status"] == "completed"
    assert answer["result_type"] == "general_education_answer" and answer["scope"] == "general_education"
    async with pg_manager.get_async_session_context() as session:
        run = await session.get(AgentRun, run_id)
        message = await session.get(Message, run.output_message_id)
        assert message.content == answer["answer"] and message.id == projected["final_message_id"]
        assert run.manifest["resources"]["tools"] == [
            f"get_member_{kind}_records",
            "query_reviewed_nutrition_knowledge",
        ]
        assert [skill["slug"] for skill in run.manifest["resources"]["skills"]] == [f"family-{kind.replace('_', '-')}"]
        assert run.manifest["resources"]["skills"][0]["version"] == "2026.10.13.1"
        uses = list(await session.scalars(select(use_model).where(use_model.run_id == run_id)))
        assert (
            len(uses) == 1 and uses[0].member_id == subject.member_id and uses[0].source_member_id == subject.source_id
        )
        assert uses[0].record_refs == ([{"record_id": record_id, "version": version}] if record_id else [])
        for model in (
            HealthBloodGlucoseUse,
            HealthBloodLipidsUse,
            HealthBloodPressureUse,
            HealthFamilyProfileUse,
            HealthWeightUse,
        ):
            if model is not use_model:
                assert await session.scalar(select(model.run_id).where(model.run_id == run_id)) is None
        citations = list(
            await session.scalars(select(NutritionEvidenceCitation).where(NutritionEvidenceCitation.run_id == run_id))
        )
        assert len(citations) == (1 if evidence_id else 0)
        if evidence_id:
            assert citations[0].evidence_id == evidence_id and citations[0].actor_uid == subject.uid
            assert citations[0].member_id == subject.member_id and f"[证据:{citations[0].id}]" in answer["answer"]
            assert answer["citations"][0]["citation_id"] == citations[0].id
        else:
            assert answer["citations"] == [] and "[证据:" not in answer["answer"]
    read = await subject.client.get(f"/api/agent/runs/{run_id}/result", headers=subject.headers)
    assert read.status_code == 200 and read.json()["output"] == answer["answer"], read.text
    citation_read = await subject.client.get(f"{ROOT}/consultation-runs/{run_id}/citations", headers=subject.headers)
    assert citation_read.status_code == 200 and citation_read.json()["citations"] == answer["citations"], (
        citation_read.text
    )
    assert "不得外发" not in answer["answer"]


async def assert_invalidated_thread(subject, bound, request_id, run_id, code):
    """当前来源变化关闭旧任务、正文、引用、历史和搜索摘要。"""
    task = await subject.client.get(f"{ROOT}/tasks/{request_id}", headers=subject.headers)
    assert task.status_code == 410 and task.json()["code"] == code, task.text
    assert (
        await subject.client.get(f"/api/chat/thread/{bound['thread_id']}/history", headers=subject.headers)
    ).status_code == 404
    read = await subject.client.get(f"/api/agent/runs/{run_id}/result", headers=subject.headers)
    assert (
        read.status_code == 200 and read.json()["output"] == "" and read.json()["error"]["type"] == "run_not_found"
    ), read.text
    citations = await subject.client.get(f"{ROOT}/consultation-runs/{run_id}/citations", headers=subject.headers)
    assert citations.status_code == 404 and "citations" not in citations.json(), citations.text
    for agent_id in (bound["agent_slug"], None):
        search = await subject.client.get(
            "/api/chat/threads/search",
            headers=subject.headers,
            params={"q": "INDICATOR_E2E_REVIEW", **({"agent_id": agent_id} if agent_id else {})},
        )
        assert search.status_code == 200 and all(
            item["thread_id"] != bound["thread_id"] for item in search.json()["items"]
        ), search.text


@pytest_asyncio.fixture
async def indicator_runtime(isolated_health):  # noqa: F811
    """只启动本fixture的8778重放与临时审批，已有监听拒绝接管。"""
    client, users, configuration, original_model = isolated_health
    try:
        with socket.create_connection(("127.0.0.1", PORT), timeout=1):
            pass
    except OSError:
        pass
    else:
        raise RuntimeError("8778已有服务，拒绝接管指标重放")
    output = Path("test/.tmp/health-indicator-agents")
    output.mkdir(parents=True, exist_ok=True)
    provider = f"indicator-replay-{uuid4().hex[:12]}"
    requests = []
    with (output / f"replay-{provider}.log").open("w", encoding="utf-8") as log:
        process = subprocess.Popen(
            [sys.executable, "test/support/health_indicator_replay_server.py"], stdout=log, stderr=log
        )
        created = False
        try:
            async with httpx.AsyncClient(base_url=f"http://localhost:{PORT}", timeout=10) as replay:

                async def ready():
                    """所属进程退出必须失败，不接管其他服务。"""
                    if process.poll() is not None:
                        raise RuntimeError("指标重放提前退出")
                    try:
                        return (await replay.get("/health")).status_code == 200
                    except httpx.ConnectError:
                        return False

                await wait_until(ready, bool)
                registered = await client.post(
                    "/api/system/model-providers",
                    headers=users[2]["headers"],
                    json={
                        "provider_id": provider,
                        "display_name": "Synthetic indicator replay only",
                        "provider_type": "openai",
                        "base_url": f"http://api:{PORT}/v1",
                        "api_key": "synthetic-health-indicator-key",
                        "capabilities": ["chat"],
                        "is_enabled": True,
                        "enabled_models": [{"id": MODEL, "display_name": MODEL, "type": "chat", "source": "manual"}],
                    },
                )
                assert registered.status_code == 200, registered.text
                created = True
                approved = await client.put(
                    f"{ROOT}/configuration",
                    headers=users[2]["headers"],
                    json={
                        "consultation_model": f"{provider}:{MODEL}",
                        "policy_version": configuration["policy_version"],
                        "cloud_processing_reviewed": True,
                    },
                )
                assert approved.status_code == 200 and approved.json()["consultation"]["available"], approved.text
                yield SimpleNamespace(
                    client=client, users=users, configuration=approved.json(), replay=replay, requests=requests
                )
        finally:
            try:
                await drain_requests(client, users[0]["headers"], requests)
                redis = await get_redis_client()
                async with pg_manager.get_async_session_context() as session:
                    run_ids = list(await session.scalars(select(AgentRun.id).where(AgentRun.request_id.in_(requests))))
                for run_id in run_ids:
                    await redis.delete(f"run:events:{run_id}")
                    assert not await redis.exists(f"run:events:{run_id}")
                if created:
                    restored = await client.put(
                        f"{ROOT}/configuration",
                        headers=users[2]["headers"],
                        json={
                            "consultation_model": original_model,
                            "policy_version": configuration["policy_version"],
                            "cloud_processing_reviewed": True,
                        },
                    )
                    assert restored.status_code == 200, restored.text
                    removed = await client.delete(
                        f"/api/system/model-providers/{provider}", headers=users[2]["headers"]
                    )
                    assert removed.status_code == 200, removed.text
            finally:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=5)
                assert process.poll() is not None
                await close_async_redis_client()

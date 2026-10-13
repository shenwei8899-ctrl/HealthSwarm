"""审核范围经真实管理员HTTP、Worker模型请求及当前PG发布/历史边界验收。"""

import asyncio
import hashlib
import json
import os
import socket
import subprocess
import sys
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select

from test.e2e.test_health_consultation_e2e import collect_sse, drain_requests, isolated_health, wait_until  # noqa: F401
from test.integration.services.test_health_task_http import entry, verified_task_cleanup  # noqa: F401
from test.integration.services.test_health_vision_http import ROOT, health_http  # noqa: F401
from test.integration.services.test_health_weight_http import cleanup_weight_subject, create_weight_subject
from test.support.health_reviewed_scope_replay_server import MODEL, PORT
from yuxi.repositories.health_evidence_repository import HealthEvidenceRepository
from yuxi.services.health_evidence_service import validate_evidence_publication
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.services.run_queue_service import get_redis_client
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_business import AgentRun, AgentRunAttempt, AgentRunRequest, Message
from yuxi.storage.postgres.models_health import HealthConsultation, NutritionEvidence, NutritionEvidenceCitation
from yuxi.storage.redis import close_async_redis_client

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.e2e,
    pytest.mark.slow,
    pytest.mark.skipif(os.getenv("HEALTH_CONSULTATION_E2E_ISOLATED") != "true", reason="仅在本轮独立合成槽位运行"),
]
ROLES = ("consultation", "blood_glucose", "blood_lipids", "blood_pressure")
DOMAINS = {"consultation": "nutrition", **{role: role for role in ROLES[1:]}}
OUTPUT = Path("test/.tmp/health-reviewed-scope")


@pytest.mark.parametrize("role", ROLES)
async def test_reviewed_scope_role_input_commit_history_and_cross_role_citation(scope_runtime, role):
    """四角色独立gold：跨域/专项/排除正文不进模型；范围变化不发布或复用。"""
    runtime = scope_runtime
    subject = await create_weight_subject(runtime.client, runtime.users)
    token, requests = uuid4().hex, []
    pending_stream = None
    try:
        consent = await subject.client.post(
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
        sources = await publish_source_pool(runtime, token)
        gold = role_gold(sources, token)
        await configure_gold(runtime, token, gold)
        bound = await fresh_entry(subject, role)
        request, run, _ = await start_run(subject, bound, token, role, "success", requests, runtime.requests)
        await assert_completed(subject, bound, request, run, token, role, "success", gold[role])

        # 无外部资料替换：仅自有fixture直接改变范围，正文与旧采用仍保存。
        chosen = sources[role]
        changed_scope = {**chosen["scope"], "population_description": "合成登记说明已变更；不得复用旧采用"}
        await mutate_scope(chosen["id"], changed_scope)
        sources[role]["scope"] = changed_scope
        await assert_stale_reads(subject, bound, request, run, token)
        before_calls = (await runtime.replay.get("/observations", params={"token": token})).json()["calls"]
        # API先持久化请求；已有checkpoint由实际Worker在下一次模型调用前校验。
        denied_request, denied_run, _ = await start_run(
            subject, bound, token, role, "success", requests, runtime.requests
        )
        await assert_checkpoint_rejected(subject, bound, denied_request, denied_run, token)
        assert (await runtime.replay.get("/observations", params={"token": token})).json()["calls"] == before_calls

        # 新线程可选择新范围；模型已取到合法正文后撤销适用类别，最终提交关闭。
        gold = role_gold(sources, token)
        await configure_gold(runtime, token, gold)
        pending_bound = await fresh_entry(subject, role)
        pending_request, pending_run, pending_stream = await start_run(
            subject, pending_bound, token, role, "changed", requests, runtime.requests, paused=True
        )
        await wait_until(lambda: observation(runtime, token), lambda value: value["answer_started"], timeout=60)
        async with pg_manager.get_async_session_context() as session:
            row = await session.get(AgentRun, pending_run)
            assert row.status == "running" and row.output_message_id is None
            receipts = list(
                await session.scalars(
                    select(NutritionEvidenceCitation).where(NutritionEvidenceCitation.run_id == pending_run)
                )
            )
            assert {receipt.evidence_id for receipt in receipts} == set(gold[role]["evidence_ids"])
        restricted_scope = {**changed_scope, "population_category": "professional_selection_required"}
        await mutate_scope(chosen["id"], restricted_scope)
        sources[role]["scope"] = restricted_scope
        assert (await runtime.replay.get("/release", params={"token": token})).status_code == 200
        await asyncio.wait_for(pending_stream, 60)
        await assert_failed(subject, pending_bound, pending_request, pending_run, token, "source_invalidated")

        # 真实另一角色成功取得明确共享证据，再用其真实引用冒充当前Run。
        gold = role_gold(sources, token, unavailable_role=role)
        await configure_gold(runtime, token, gold)
        other_role = ROLES[(ROLES.index(role) + 1) % len(ROLES)]
        other_bound = await fresh_entry(subject, other_role)
        other_request, other_run, _ = await start_run(
            subject, other_bound, token, other_role, "success", requests, runtime.requests
        )
        other_answer = await assert_completed(
            subject, other_bound, other_request, other_run, token, other_role, "success", gold[other_role]
        )
        shared_citation = next(
            citation["citation_id"]
            for citation in other_answer["citations"]
            if citation["evidence_id"] == sources["shared"]["id"]
        )
        await configure_gold(runtime, token, gold, foreign_citation=shared_citation)
        foreign_bound = await fresh_entry(subject, role)
        foreign_request, foreign_run, _ = await start_run(
            subject, foreign_bound, token, role, "foreign", requests, runtime.requests
        )
        await assert_failed(
            subject, foreign_bound, foreign_request, foreign_run, token, "citation_invalid", citation=shared_citation
        )
        final_observation = await observation(runtime, token)
        assert final_observation["rejected"] == [], final_observation
        assert final_observation["calls"] == [
            {"role": current_role, "mode": mode, "phase": phase}
            for current_role, mode in ((role, "success"), (role, "changed"), (other_role, "success"), (role, "foreign"))
            for phase in ("knowledge", "answer")
        ]
        write_receipt("model-calls", {"role": role, **final_observation})
    finally:
        release = await runtime.replay.get("/release", params={"token": token})
        if release.status_code == 200:
            write_receipt("teardown-model-observations", {"role": role, **release.json()})
        if pending_stream is not None:
            if not pending_stream.done():
                pending_stream.cancel()
            await asyncio.gather(pending_stream, return_exceptions=True)
        await drain_requests(subject.client, subject.headers, requests)
        await cleanup_weight_subject(subject)


async def publish_source_pool(runtime, token):
    """全部来源命中同一query；gold由发布前范围决定，禁入正文有独立哨兵。"""
    sources = {}
    scopes = {role: reviewed_scope([domain]) for role, domain in DOMAINS.items()}
    scopes["shared"] = reviewed_scope(list(DOMAINS.values()))
    scopes["professional"] = {
        **reviewed_scope(list(DOMAINS.values())),
        "population_category": "professional_selection_required",
    }
    scopes["excluded"] = {
        **reviewed_scope(list(DOMAINS.values())),
        "exclusion_conditions": ["合成排除条件；尚无正式匹配契约"],
    }
    scopes["legacy"] = None
    for label, scope in scopes.items():
        body = {
            "source_ref": f"synthetic://reviewed-scope/{token}/{label}",
            "source_version": "synthetic-v1",
            "title": f"合成审核 scope{token} {label}",
            "content": f"scope{token} SCOPE_SOURCE:{token}:{label} 合成范围协议资料，不包含医学规则。",
            "review_ref": f"synthetic://reviewed-scope-review/{token}/{label}",
            "reviewed_by": "synthetic-reviewer",
            "reviewed_at": (datetime.now(UTC) - timedelta(days=1)).isoformat(),
            "valid_until": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
        }
        if scope is not None:
            body["reviewed_scope"] = scope
        # 既有权限Owner通过真实HTTP保持；拒绝不能新增来源。
        if label == "shared":
            forbidden = await runtime.client.post(
                f"{ROOT}/nutrition-evidence", headers=runtime.users[0]["headers"], json=body
            )
            assert forbidden.status_code == 403, forbidden.text
            async with pg_manager.get_async_session_context() as session:
                assert (
                    await session.scalar(
                        select(NutritionEvidence.id).where(NutritionEvidence.source_ref == body["source_ref"])
                    )
                    is None
                )
        published = await runtime.client.post(
            f"{ROOT}/nutrition-evidence", headers=runtime.users[2]["headers"], json=body
        )
        assert published.status_code == 201, published.text
        expected_scope = {**scope, "domains": sorted(scope["domains"])} if scope else None
        source_id = published.json()["evidence_id"]
        async with pg_manager.get_async_session_context() as session:
            source = await session.get(NutritionEvidence, source_id)
            assert source.content == body["content"] and source.reviewed_scope == expected_scope
            assert source.scope_hash == digest(expected_scope)
        if expected_scope is None:
            assert set(published.json()) == {"evidence_id", "source_version", "scope"}
            assert published.json()["scope"] == "general_education"
        else:
            assert published.json()["reviewed_scope"] == expected_scope and published.json()["scope_hash"] == digest(
                expected_scope
            )
        sources[label] = {"id": source_id, "content": body["content"], "scope": expected_scope}
    denied = await runtime.client.delete(
        f"{ROOT}/nutrition-evidence/{sources['shared']['id']}", headers=runtime.users[0]["headers"]
    )
    assert denied.status_code == 403
    async with pg_manager.get_async_session_context() as session:
        assert (await session.get(NutritionEvidence, sources["shared"]["id"])).revoked_at is None
    return sources


def reviewed_scope(domains):
    """程序只认通用类别，不推断专项年龄、病种或妊娠条件。"""
    return {
        "domains": domains,
        "population_category": "general_education",
        "population_description": "合成通用教育资料，仅验证明确登记契约",
        "exclusion_conditions": [],
        "license_ref": "synthetic://license/scope-contract-only",
    }


def role_gold(sources, token, *, unavailable_role=None):
    """预先手写四角色分域允许集合，未读取搜索返回值。"""
    gold = {}
    declared = {
        "consultation": ["consultation", "shared", "legacy"],
        "blood_glucose": ["blood_glucose", "shared"],
        "blood_lipids": ["blood_lipids", "shared"],
        "blood_pressure": ["blood_pressure", "shared"],
    }
    for role, allowed in declared.items():
        allowed = [label for label in allowed if label != unavailable_role]
        gold[role] = {
            "evidence_ids": [sources[label]["id"] for label in allowed],
            "contents": {sources[label]["id"]: sources[label]["content"] for label in allowed},
            "scopes": {sources[label]["id"]: sources[label]["scope"] for label in allowed},
            "forbidden": [f"SCOPE_SOURCE:{token}:{label}" for label in sources if label not in allowed],
        }
    return gold


async def configure_gold(runtime, token, gold, *, foreign_citation=None):
    """服务器以固定ID与正文为独立oracle，拒绝从模型返回动态生成gold。"""
    response = await runtime.replay.post(
        "/setup", json={"token": token, "roles": gold, "foreign_citation": foreign_citation}
    )
    assert response.status_code == 200


async def fresh_entry(subject, role):
    """实际统一入口固定角色与用途，前端参数不拥有范围。"""
    response = await entry(
        subject.client,
        subject.headers,
        subject.member_id,
        "consultation" if role == "consultation" else f"{role}_review",
    )
    assert response.status_code == 200 and response.json()["entry_status"] == "ready", response.text
    assert response.json()["agent_slug"] == (
        "health-consultation" if role == "consultation" else f"health-{role.replace('_', '-')}"
    )
    return response.json()


async def start_run(subject, bound, token, role, mode, requests, all_requests, *, paused=False):
    """真实HTTP投递与SSE末帧，从PG核对Worker取走本次Request。"""
    request = str(uuid4())
    requests.append(request)
    all_requests.append(request)
    response = await subject.client.post(
        "/api/agent/runs",
        headers=subject.headers,
        json={
            "agent_slug": bound["agent_slug"],
            "thread_id": bound["thread_id"],
            "query": f"REVIEWED_SCOPE_E2E:{token}:{role}:{mode}",
            "meta": {"request_id": request},
        },
    )
    assert response.status_code == 200 and response.json()["status"] == "dispatched", response.text
    run = response.json()["run_id"]
    stream = asyncio.create_task(collect_sse(subject.client, subject.headers, run))
    if not paused:
        events = await asyncio.wait_for(stream, 60)
        assert events[-1][0] == "end" and events[-1][1]["request_id"] == request
    return request, run, stream


async def assert_completed(subject, bound, request, run_id, token, role, mode, gold):
    """最终同Run Message、Task、结果、引用、普通历史与checkpoint均回读。"""
    result = await subject.client.get(f"/api/agent/runs/{run_id}/result", headers=subject.headers)
    task = await subject.client.get(f"{ROOT}/tasks/{request}", headers=subject.headers)
    cited = await subject.client.get(f"{ROOT}/consultation-runs/{run_id}/citations", headers=subject.headers)
    assert result.status_code == task.status_code == cited.status_code == 200
    assert result.json()["status"] == task.json()["execution_status"] == "completed"
    answer = task.json()["result"]
    citations = cited.json()["citations"]
    assert len(citations) == len(gold["evidence_ids"]) and {citation["evidence_id"] for citation in citations} == set(
        gold["evidence_ids"]
    )
    assert answer["citations"] == citations
    for citation in citations:
        evidence = citation["evidence_id"]
        assert citation["content"] == gold["contents"][evidence]
        scope = gold["scopes"][evidence]
        if scope is None:
            assert "reviewed_scope" not in citation and "scope_hash" not in citation
        else:
            assert citation["reviewed_scope"] == scope and citation["scope_hash"] == digest(scope)
    expected = f"REVIEWED_SCOPE_BODY:{token}:{role}:{mode} 合成范围协议正文。" + " ".join(
        f"[证据:{citation['citation_id']}]" for citation in citations
    )
    assert result.json()["output"] == answer["answer"] == expected
    async with pg_manager.get_async_session_context() as session:
        run = await session.get(AgentRun, run_id)
        message = await session.get(Message, run.output_message_id)
        attempts = list(await session.scalars(select(AgentRunAttempt).where(AgentRunAttempt.run_id == run_id)))
        persisted = list(
            await session.scalars(select(NutritionEvidenceCitation).where(NutritionEvidenceCitation.run_id == run_id))
        )
        assert run.status == "completed" and run.worker_id is None and run.lease_expires_at is None
        assert len(attempts) == 1 and attempts[0].worker_id and attempts[0].outcome == "completed"
        assert message.content == expected and message.run_id == run_id and message.request_id == request
        assert (
            message.id
            == result.json()["final_message_id"]
            == task.json()["final_message_id"]
            == cited.json()["final_message_id"]
        )
        assert {receipt.id for receipt in persisted} == {citation["citation_id"] for citation in citations}
        assert all(receipt.scope_hash == digest(gold["scopes"][receipt.evidence_id]) for receipt in persisted)
        write_receipt(
            "pg-runs",
            {
                "role": role,
                "mode": mode,
                "run_id": run_id,
                "request_id": request,
                "status": run.status,
                "final_message_id": message.id,
                "evidence_ids": sorted(gold["evidence_ids"]),
                "attempt_id": attempts[0].id,
            },
        )
    history = await subject.client.get(f"/api/chat/thread/{bound['thread_id']}/history", headers=subject.headers)
    state = await subject.client.get(
        f"/api/chat/thread/{bound['thread_id']}/state?include_messages=true", headers=subject.headers
    )
    assert history.status_code == state.status_code == 200
    assert [message["content"] for message in history.json()["history"] if message["type"] == "ai"] == [expected]
    assert [message["content"] for message in state.json()["messages"] if message["type"] == "ai"] == [expected]
    saved = await pg_manager.get_langgraph_checkpointer().aget_tuple(
        {"configurable": {"uid": subject.uid, "thread_id": bound["thread_id"], "checkpoint_ns": ""}}
    )
    assert saved is not None
    tool_messages = [
        message
        for message in saved.checkpoint["channel_values"]["messages"]
        if getattr(message, "name", None) == "query_reviewed_nutrition_knowledge"
        and getattr(message, "type", None) == "tool"
    ]
    assert len(tool_messages) == 1
    checkpoint_citations = json.loads(tool_messages[0].content)["citations"]
    assert {citation["evidence_id"] for citation in checkpoint_citations} == set(gold["evidence_ids"])
    return answer


async def assert_stale_reads(subject, bound, request, run_id, token):
    """采用时scope摘要已过时，所有普通正文读取关闭且PG旧正文仍在。"""
    for path in (
        f"/api/agent/runs/{run_id}/result",
        f"{ROOT}/tasks/{request}",
        f"{ROOT}/consultation-runs/{run_id}/citations",
    ):
        response = await subject.client.get(path, headers=subject.headers)
        assert response.status_code == 410, response.text
        assert f"REVIEWED_SCOPE_BODY:{token}" not in response.text
    history = await subject.client.get(f"/api/chat/thread/{bound['thread_id']}/history", headers=subject.headers)
    assert history.status_code == 200 and not any(message["type"] == "ai" for message in history.json()["history"]), (
        history.text
    )
    state = await subject.client.get(
        f"/api/chat/thread/{bound['thread_id']}/state?include_messages=true", headers=subject.headers
    )
    assert state.status_code == 200 and not any(message["type"] == "ai" for message in state.json()["messages"]), (
        state.text
    )
    search = await subject.client.get(
        "/api/chat/threads/search", headers=subject.headers, params={"q": f"REVIEWED_SCOPE_BODY:{token}"}
    )
    assert search.status_code == 200
    assert all(item["thread_id"] != bound["thread_id"] for item in search.json()["items"]), search.text
    async with pg_manager.get_async_session_context() as session:
        run = await session.get(AgentRun, run_id)
        assert run.status == "completed" and (await session.get(Message, run.output_message_id)).content.startswith(
            f"REVIEWED_SCOPE_BODY:{token}"
        )


async def assert_checkpoint_rejected(subject, bound, request_id, run_id, token):
    """实际Worker拒绝旧scope；无下一次模型请求、回执或正式正文。"""
    async with pg_manager.get_async_session_context() as session:
        run = await session.get(AgentRun, run_id)
        request = await session.scalar(select(AgentRunRequest).where(AgentRunRequest.request_id == request_id))
        attempts = list(await session.scalars(select(AgentRunAttempt).where(AgentRunAttempt.run_id == run_id)))
        assert request.dispatched_run_id == run_id and request.status == "dispatched"
        assert run.status == "failed" and run.output_message_id is None, run.to_dict()
        assert run.worker_id is None and run.lease_expires_at is None and run.first_model_request_at is None
        assert len(attempts) == 1 and attempts[0].worker_id and attempts[0].outcome == "failed"
        assert (
            list(await session.scalars(select(Message).where(Message.run_id == run_id, Message.role == "assistant")))
            == []
        )
        assert (
            list(
                await session.scalars(
                    select(NutritionEvidenceCitation).where(NutritionEvidenceCitation.run_id == run_id)
                )
            )
            == []
        )
        binding = await session.get(HealthConsultation, run.conversation_id)
        saved = await pg_manager.get_langgraph_checkpointer().aget_tuple(
            {"configurable": {"uid": subject.uid, "thread_id": bound["thread_id"], "checkpoint_ns": ""}}
        )
        old_payloads = [
            json.loads(message.content)
            for message in saved.checkpoint["channel_values"]["messages"]
            if getattr(message, "type", None) == "tool"
            and getattr(message, "name", None) == "query_reviewed_nutrition_knowledge"
        ]
        assert old_payloads
        with pytest.raises(HealthVisionError) as rejected:
            await HealthEvidenceRepository(session).validate_tool_payload(
                old_payloads[0], binding, subject.uid, agent_slug=bound["agent_slug"]
            )
        assert rejected.value.code == "source_invalidated"
        write_receipt(
            "pg-runs",
            {
                "run_id": run_id,
                "request_id": request_id,
                "status": run.status,
                "final_message_id": run.output_message_id,
                "guard_code": "source_invalidated",
                "model_request_started": False,
                "checkpoint_rejected": True,
                "attempt_id": attempts[0].id,
            },
        )
    result = await subject.client.get(f"/api/agent/runs/{run_id}/result", headers=subject.headers)
    task = await subject.client.get(f"{ROOT}/tasks/{request_id}", headers=subject.headers)
    assert result.status_code == task.status_code == 200
    assert result.json()["status"] == task.json()["execution_status"] == "failed"
    assert result.json()["output"] == "" and task.json()["final_message_id"] is None
    assert f"REVIEWED_SCOPE_BODY:{token}" not in result.text + task.text


async def assert_failed(subject, bound, request, run_id, token, code, *, citation=None):
    """真实Worker失败、无公开Message及指针；直接验证器指出目标拒绝原因。"""
    async with pg_manager.get_async_session_context() as session:
        run = await session.get(AgentRun, run_id)
        assert run.status == "failed" and run.output_message_id is None, run.to_dict()
        assert run.worker_id is None and run.lease_expires_at is None
        messages = list(
            await session.scalars(
                select(Message).where(
                    Message.run_id == run_id, Message.role == "assistant", Message.message_type == "text"
                )
            )
        )
        assert messages == []
        attempts = list(await session.scalars(select(AgentRunAttempt).where(AgentRunAttempt.run_id == run_id)))
        assert len(attempts) == 1 and attempts[0].worker_id and attempts[0].outcome == "failed"
        adopted = list(
            await session.scalars(select(NutritionEvidenceCitation).where(NutritionEvidenceCitation.run_id == run_id))
        )
        if citation is None:
            for item in adopted:
                source = await session.get(NutritionEvidence, item.evidence_id)
                if (
                    source.reviewed_scope
                    and source.reviewed_scope["population_category"] == "professional_selection_required"
                ):
                    citation = item.id
                    break
            assert citation is not None, "已采用的自有来源必须已变成需专业选择类别"
        with pytest.raises(HealthVisionError) as rejected:
            await validate_evidence_publication(session, run, f"合成拒绝校验 [证据:{citation}]")
        assert rejected.value.code == code
        write_receipt(
            "pg-runs",
            {
                "run_id": run_id,
                "request_id": request,
                "status": run.status,
                "final_message_id": run.output_message_id,
                "guard_code": code,
                "attempt_id": attempts[0].id,
            },
        )
    result = await subject.client.get(f"/api/agent/runs/{run_id}/result", headers=subject.headers)
    task = await subject.client.get(f"{ROOT}/tasks/{request}", headers=subject.headers)
    history = await subject.client.get(f"/api/chat/thread/{bound['thread_id']}/history", headers=subject.headers)
    assert result.status_code == task.status_code == history.status_code == 200
    assert result.json()["status"] == task.json()["execution_status"] == "failed"
    assert result.json()["output"] == "" and task.json()["final_message_id"] is None
    assert not any(message["type"] == "ai" for message in history.json()["history"])
    assert all(f"REVIEWED_SCOPE_BODY:{token}" not in response.text for response in (result, task, history))


async def mutate_scope(source_id, scope):
    """合成fixture模拟外部修改，程序hash算法由测试独立定义。"""
    async with pg_manager.get_async_session_context() as session:
        source = await session.get(NutritionEvidence, source_id)
        source.reviewed_scope = deepcopy(scope)
        source.scope_hash = digest(scope)


def digest(scope):
    """固定wire规范的独立SHA oracle，不调用生产helper。"""
    return (
        hashlib.sha256(
            json.dumps(scope, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
        ).hexdigest()
        if scope is not None
        else None
    )


async def observation(runtime, token):
    """真实独立模型端只读阶段观察。"""
    response = await runtime.replay.get("/observations", params={"token": token})
    assert response.status_code == 200
    return response.json()


def write_receipt(kind, payload):
    """诊断只保存本轮合成事实，不保存登录Token。"""
    OUTPUT.mkdir(parents=True, exist_ok=True)
    with (OUTPUT / f"{kind}.jsonl").open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(payload, ensure_ascii=False) + "\n")


@pytest_asyncio.fixture
async def scope_runtime(isolated_health):  # noqa: F811
    """仅本fixture启动8780回放并恢复原审批和provider，拒绝接管已有监听。"""
    client, users, configuration, original_model = isolated_health
    try:
        with socket.create_connection(("127.0.0.1", PORT), timeout=1):
            pass
    except OSError:
        pass
    else:
        raise RuntimeError("8780已有服务，拒绝接管审核范围回放")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    provider, requests = f"scope-replay-{uuid4().hex[:12]}", []
    with (OUTPUT / f"replay-{provider}.log").open("w", encoding="utf-8") as log:
        process = subprocess.Popen(
            [sys.executable, "-m", "test.support.health_reviewed_scope_replay_server"], stdout=log, stderr=log
        )
        registered = False
        try:
            async with httpx.AsyncClient(base_url=f"http://localhost:{PORT}", timeout=10) as replay:

                async def ready():
                    """自己的进程退出必须失败，不将环境失败当业务负控。"""
                    if process.poll() is not None:
                        raise RuntimeError("范围回放提前退出")
                    try:
                        return (await replay.get("/health")).status_code == 200
                    except httpx.ConnectError:
                        return False

                await wait_until(ready, bool)
                created = await client.post(
                    "/api/system/model-providers",
                    headers=users[2]["headers"],
                    json={
                        "provider_id": provider,
                        "display_name": "Synthetic reviewed scope replay only",
                        "provider_type": "openai",
                        "base_url": f"http://api:{PORT}/v1",
                        "api_key": "synthetic-health-reviewed-scope-key",
                        "capabilities": ["chat"],
                        "is_enabled": True,
                        "enabled_models": [{"id": MODEL, "display_name": MODEL, "type": "chat", "source": "manual"}],
                    },
                )
                assert created.status_code == 200, created.text
                registered = True
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
                if registered:
                    restored = await client.put(
                        f"{ROOT}/configuration",
                        headers=users[2]["headers"],
                        json={
                            "consultation_model": original_model,
                            "policy_version": configuration["policy_version"],
                            "cloud_processing_reviewed": True,
                        },
                    )
                    assert restored.status_code == 200
                    removed = await client.delete(
                        f"/api/system/model-providers/{provider}", headers=users[2]["headers"]
                    )
                    assert removed.status_code == 200
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

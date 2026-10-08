"""隔离API、真实worker/SSE与PG证明质量检查固定资源及本Run收据。"""

import json
import os
from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import select
from langchain_core.messages import AIMessage, ToolMessage

from test.e2e.test_health_consultation_e2e import isolated_health, collect_sse, drain_requests  # noqa: F401
from test.integration.services.test_health_vision_http import ROOT, health_http  # noqa: F401
from test.integration.services.test_health_quality_http import setup_quality
from test.integration.services.test_health_personal_targets_http import import_targets
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_business import AgentRun, AgentRunRequest, Message
from yuxi.storage.postgres.models_health import HealthQualityCheck, HealthProfessionalReview
from yuxi.agents.context import BaseContext
from yuxi.repositories.health_consultation_repository import HealthConsultationRepository
from yuxi.repositories.conversation_repository import ConversationRepository
from yuxi.services.health_consultation_service import require_consultation_attempt
from yuxi.services.health_quality_service import selected_quality_context, check_selected_quality, quality_final_result
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.services.chat_service import save_messages_from_langgraph_state
from yuxi.utils.datetime_utils import utc_now_naive

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.slow,
    pytest.mark.asyncio,
    pytest.mark.skipif(os.getenv("HEALTH_CONSULTATION_E2E_ISOLATED") != "true", reason="仅隔离合成槽位"),
]


async def approve_quality(client, owner, admin, member, model, policy):
    """独立质量用途审批不继承咨询或配餐审批。"""
    configured = await client.put(
        f"{ROOT}/configuration",
        headers=admin,
        json={"quality_review_model": model, "policy_version": policy, "cloud_processing_reviewed": True},
    )
    assert configured.status_code == 200, configured.text
    config = configured.json()["quality_review"]
    assert config["available"] is True
    consent = {
        "accepted": True,
        "purpose": "quality_review",
        "processor": config["processor"],
        "policy_version": policy,
    }
    saved = await client.post(f"{ROOT}/members/{member}/processing-consents", headers=owner, json=consent)
    assert saved.status_code == 200, saved.text
    return {"model": model, "processor": config["processor"], "policy_version": policy}, consent


async def bind_quality(client, owner, current):
    """明确业务对象、版本和规则，模型不能修改绑定。"""
    response = await client.post(
        f"{ROOT}/meal-plans/{current['plan']}/quality-conversation",
        headers=owner,
        json={**current["body"], "client_request_id": str(uuid4())},
    )
    assert response.status_code == 201, response.text
    return response.json()["thread_id"]


async def seed_quality_run(uid, thread, snapshot):
    """仅为发布/checkpoint边界建立真实PG执行Owner，不冒充模型调用。"""
    run_id, request = str(uuid4()), str(uuid4())
    async with pg_manager.get_async_session_context() as session:
        binding = await HealthConsultationRepository(session).authorize(uid, thread)
        source = Message(
            conversation_id=binding.conversation_id, role="user", content="合成质量边界", request_id=request
        )
        session.add(source)
        await session.flush()
        session.add(
            AgentRunRequest(
                uid=uid,
                request_id=request,
                agent_slug="health-quality",
                conversation_thread_id=thread,
                status="dispatched",
                input_message_id=source.id,
                input_payload={"health_processing": snapshot},
            )
        )
        session.add(
            AgentRun(
                id=run_id,
                request_id=request,
                uid=uid,
                agent_slug="health-quality",
                conversation_id=binding.conversation_id,
                conversation_thread_id=thread,
                runtime_scope_id=thread,
                worker_id="synthetic-quality-owner",
                status="running",
                lease_expires_at=utc_now_naive() + timedelta(minutes=3),
                input_payload={"health_processing": snapshot},
            )
        )
    return BaseContext(
        uid=uid,
        thread_id=thread,
        request_id=request,
        run_id=run_id,
        worker_id="synthetic-quality-owner",
        model=snapshot["model"],
    )


@pytest.mark.parametrize("change", ["consent", "profile", "rules", "checkpoint", "forged_context", "forged_check"])
async def test_quality_publication_and_checkpoint_reject_changed_sources(isolated_health, change):  # noqa: F811
    """成功检查后变源不能发布；checkpoint即使保留来源摘要也不能伪造结果。"""
    client, users, config, model = isolated_health
    owner, admin = users[0]["headers"], users[2]["headers"]
    current = await setup_quality(client, users)
    snapshot, consent = await approve_quality(client, owner, admin, current["member"], model, config["policy_version"])
    thread = await bind_quality(client, owner, current)
    context = await seed_quality_run(users[0]["uid"], thread, snapshot)
    try:
        tool_context = await selected_quality_context(context)
        result = await check_selected_quality(context)
        assert result == await check_selected_quality(context)
        assert await quality_final_result(context, json.dumps({"check_id": result["check_id"]})) == result
        if change == "consent":
            response = await client.post(
                f"{ROOT}/members/{current['member']}/processing-consents",
                headers=owner,
                json={**consent, "accepted": False},
            )
            assert response.status_code == 200, response.text
        elif change in {"profile", "checkpoint"}:
            body = {**current["profile"], "version": 2, "source_version": "v2"}
            response = await client.post(
                f"{ROOT}/members/{current['member']}/external-profile-versions", headers=admin, json=body
            )
            assert response.status_code == 201, response.text
        elif change == "rules":
            body = {**current["rules"], "version": 2, "source_version": "v2"}
            response = await client.post(f"{ROOT}/approved-quality-rules", headers=admin, json=body)
            assert response.status_code == 201, response.text
        elif change == "forged_context":
            tool_context["profile"]["payload"]["age_years"] += 1
        else:
            result["safety_check"]["status"] = "unknown"
        if change in {"checkpoint", "forged_context", "forged_check"}:
            payload = tool_context if change == "forged_context" else result
            name = "get_quality_review_context" if change == "forged_context" else "check_selected_plan_quality"
            with pytest.raises(HealthVisionError, match="source_invalidated"):
                await require_consultation_attempt(
                    context, [ToolMessage(name=name, tool_call_id=str(uuid4()), content=json.dumps(payload))]
                )
        else:
            async with pg_manager.get_async_session_context() as session:
                with pytest.raises(
                    HealthVisionError, match="consent_required" if change == "consent" else "source_invalidated"
                ):
                    await save_messages_from_langgraph_state(
                        SimpleNamespace(values={"messages": [AIMessage(id=str(uuid4()), content=json.dumps(result))]}),
                        thread,
                        ConversationRepository(session),
                        run_id=context.run_id,
                        request_id=context.request_id,
                        worker_id=context.worker_id,
                        complete_run=True,
                    )
        async with pg_manager.get_async_session_context() as session:
            run = await session.get(AgentRun, context.run_id)
            assert run.status == "running" and run.output_message_id is None
            assert (
                await session.scalar(select(Message).where(Message.run_id == run.id, Message.role == "assistant"))
                is None
            )
    finally:
        async with pg_manager.get_async_session_context() as session:
            (await session.get(AgentRun, context.run_id)).status = "failed"


@pytest.mark.parametrize("personal", [False, True])
async def test_quality_actual_worker_two_turns_and_illegal_final_selectors(isolated_health, personal):  # noqa: F811
    """真实两轮分别保存本Run检查，模型批准/假收据/跨Run最终选择均失败。"""
    client, users, configuration, _ = isolated_health
    owner, admin = users[0]["headers"], users[2]["headers"]
    current = await setup_quality(client, users)
    if personal:
        await import_targets(client, users, current)
    provider = "quality-replay-" + uuid4().hex[:12]
    created = await client.post(
        "/api/system/model-providers",
        headers=admin,
        json={
            "provider_id": provider,
            "display_name": "Synthetic quality only",
            "provider_type": "openai",
            "base_url": "http://api:8771/v1",
            "api_key": "synthetic-quality-key",
            "capabilities": ["chat"],
            "enabled_models": [
                {
                    "id": "deterministic-quality-20261007",
                    "display_name": "synthetic",
                    "type": "chat",
                    "source": "manual",
                }
            ],
            "is_enabled": True,
        },
    )
    assert created.status_code == 200, created.text
    model = f"{provider}:deterministic-quality-20261007"
    requests, valid_checks = [], []
    try:
        await approve_quality(client, owner, admin, current["member"], model, configuration["policy_version"])
        shared_thread = await bind_quality(client, owner, current)
        for mode in ("valid", "valid", "cross_run", "questions", "no_receipt", "fake_approval"):
            thread = shared_thread if mode in {"valid", "cross_run"} else await bind_quality(client, owner, current)
            request = str(uuid4())
            requests.append(request)
            submitted = await client.post(
                "/api/agent/runs",
                headers=owner,
                json={
                    "agent_slug": "health-quality",
                    "thread_id": thread,
                    "query": f"QUALITY_E2E:{uuid4().hex}:{mode}" + (":personal" if personal else ""),
                    "meta": {"request_id": request},
                },
            )
            assert submitted.status_code == 200, submitted.text
            run_id = submitted.json()["run_id"]
            events = await collect_sse(client, owner, run_id)
            assert events[-1][0] == "end" and not any("message_delta" in str(e) for _, e in events)
            response = await client.get(f"/api/agent/runs/{run_id}/result", headers=owner)
            expected = "completed" if mode in {"valid", "questions"} else "failed"
            assert response.json()["status"] == expected, response.text
            async with pg_manager.get_async_session_context() as session:
                run = await session.get(AgentRun, run_id)
                check = await session.scalar(select(HealthQualityCheck).where(HealthQualityCheck.run_id == run_id))
                if mode == "valid":
                    result = json.loads(response.json()["output"])
                    assert check is not None and result["check_id"] == check.id and check.actor_uid == users[0]["uid"]
                    assert result["safety_check"]["status"] == ("conflict" if personal else "passed")
                    if personal:
                        target = result["safety_check"]["personal_targets"]
                        assert target["status"] == "ready" and target["energy_kcal"] == "330"
                        assert target["inputs"]["age_years"] == "30" and target["inputs"]["doctor_requirements"] == []
                        assert check.snapshot["sources"]["profiles"][current["member"]]["version"] == 2
                        assert check.snapshot["sources"]["rules"]["version"] == 2
                    assert result["professional_review"] == "not_a_professional_decision"
                    assert result["nutrition"]["totals"]["energy_kcal"] == "300.00"
                    case = await session.scalar(
                        select(HealthProfessionalReview).where(HealthProfessionalReview.check_id == check.id)
                    )
                    assert case.status == "draft" and case.version == 1
                    assert (await session.get(Message, run.output_message_id)).run_id == run_id
                    assert run.manifest["resources"]["tools"] == [
                        "get_quality_review_context",
                        "check_selected_plan_quality",
                    ]
                    assert [s["slug"] for s in run.manifest["resources"]["skills"]] == ["family-quality-review"]
                    valid_checks.append(check.id)
                else:
                    assert check is None
                    if mode == "questions":
                        assert json.loads(response.json()["output"])["result_type"] == "needs_input"
                    else:
                        assert {
                            "cross_run": "quality_receipt_invalid",
                            "no_receipt": "quality_receipt_invalid",
                            "fake_approval": "quality_answer_invalid",
                        }[mode] in run.error_message
                        assert not response.json().get("output")
                        if run.output_message_id is not None:
                            diagnostic = await session.get(Message, run.output_message_id)
                            assert diagnostic.run_id == run_id and diagnostic.request_id == request
                            assert diagnostic.content == "" and diagnostic.extra_metadata["is_error"] is True
        assert len(valid_checks) == 2 and valid_checks[0] != valid_checks[1]
        gate = await client.get(f"{ROOT}/meal-plans/{current['plan']}/approval-state?version=1", headers=owner)
        assert gate.json()["available"] is False
    finally:
        await drain_requests(client, owner, requests)
        assert (await client.put(f"{ROOT}/configuration", headers=admin, json={})).status_code == 200
        assert (await client.delete(f"/api/system/model-providers/{provider}", headers=admin)).status_code == 200

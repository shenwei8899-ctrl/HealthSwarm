"""真实 Worker 读取本人档案、复用历史及改版后发布拒绝。"""

import asyncio
import os
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import delete, select

from test.e2e.test_health_consultation_e2e import collect_sse, drain_requests, isolated_health, wait_until  # noqa: F401
from test.integration.services.test_health_vision_http import ROOT, create_member, health_http  # noqa: F401
from yuxi.services.health_family_profile_service import validate_profile_publication
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_business import (
    AgentRun,
    FamilyArchive,
    FamilyAudit,
    FamilyMeasurement,
    FamilyMember,
    FamilyProfileRevision,
    Message,
)
from yuxi.storage.postgres.models_health import HealthFamilyProfileLink, HealthFamilyProfileUse

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.e2e,
    pytest.mark.slow,
    pytest.mark.skipif(os.getenv("HEALTH_CONSULTATION_E2E_ISOLATED") != "true", reason="仅在隔离合成槽位运行"),
]


@pytest.mark.parametrize("mutation", ["profile", "processing_consent"])
async def test_profile_worker_history_and_late_publication_recheck(isolated_health, mutation):  # noqa: F811
    """独立重放核对171原值，数据库证明改版后无普通输出及旧线程无再外呼。"""
    client, users, configuration, _ = isolated_health
    headers, uid = users[0]["headers"], users[0]["uid"]
    member_id = await create_member(client, headers)
    created = await client.post("/api/family", headers=headers, json={"name": "合成本人档案E2E"})
    assert created.status_code == 200, created.text
    family_id = created.json()["id"]
    source = next(item for item in created.json()["members"] if item["is_self"])
    path = f"/api/family/{family_id}/members/{source['id']}"
    requests, pending_stream = [], None
    token, gate_token = uuid4().hex, uuid4().hex
    async with httpx.AsyncClient(base_url="http://localhost:8766", timeout=10) as replay:
        try:
            changed = await client.put(
                path,
                headers=headers,
                json={
                    "expected_version": source["version"],
                    "profile": {
                        "sex": "female",
                        "birth_date": "1992-01-02",
                        "height_cm": 171,
                        "activity_level": "light",
                        "goal": "合成均衡饮食",
                        "allergens": [],
                    },
                },
            )
            assert changed.status_code == 200 and changed.json()["version"] == 2, changed.text
            assert (
                await client.post(path + "/confirm", headers=headers, json={"expected_version": 2})
            ).status_code == 200
            linked = await client.post(
                f"{ROOT}/members/{member_id}/family-profile-link",
                headers=headers,
                json={
                    "family_id": family_id,
                    "source_member_id": source["id"],
                    "confirmed_identity": True,
                },
            )
            assert linked.status_code == 200, linked.text
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
            assert consent.status_code == 200, consent.text

            async def new_thread():
                key = str(uuid4())
                response = await client.post(
                    f"{ROOT}/members/{member_id}/consultations",
                    headers={
                        **headers,
                        "Idempotency-Key": key,
                    },
                    json={"client_request_id": key},
                )
                assert response.status_code == 201, response.text
                return response.json()["thread_id"]

            async def start(thread, replay_token, step):
                request = str(uuid4())
                requests.append(request)
                response = await client.post(
                    "/api/agent/runs",
                    headers=headers,
                    json={
                        "query": f"HEALTH_CONSULTATION_E2E:{replay_token}:{step}",
                        "agent_slug": "health-consultation",
                        "thread_id": thread,
                        "meta": {"request_id": request},
                    },
                )
                assert response.status_code == 200, response.text
                return response.json()["run_id"]

            thread = await new_thread()
            for step in ("profile", "derived_profile"):
                run_id = await start(thread, token, step)
                await collect_sse(client, headers, run_id)
                result = await client.get(f"/api/agent/runs/{run_id}/result", headers=headers)
                assert result.status_code == 200 and result.json()["status"] == "completed", result.text
                assert result.json()["output"] == "合成本人身高171；营养安全字段尚未就绪"
                async with pg_manager.get_async_session_context() as session:
                    run = await session.get(AgentRun, run_id)
                    assert (await session.get(Message, run.output_message_id)).content == result.json()["output"]
                    if step == "profile":
                        use = await session.scalar(
                            select(HealthFamilyProfileUse).where(HealthFamilyProfileUse.run_id == run_id)
                        )
                        assert use and use.version == 2 and use.member_id == member_id
            gate_thread = await new_thread() if mutation == "profile" else thread
            gate_step = "profile_gate" if mutation == "profile" else "derived_profile_gate"
            gated_run = await start(gate_thread, gate_token, gate_step)
            pending_stream = asyncio.create_task(collect_sse(client, headers, gated_run))
            await wait_until(
                lambda: replay.get("/observations", params={"token": gate_token}),
                lambda response: any(item["phase"] == "answer" for item in response.json()["calls"]),
            )
            if mutation == "profile":
                edited = await client.put(
                    path, headers=headers, json={"expected_version": 2, "profile": {"height_cm": 172}}
                )
            else:
                edited = await client.post(
                    f"{ROOT}/members/{member_id}/processing-consents",
                    headers=headers,
                    json={
                        "purpose": "consultation",
                        "accepted": False,
                        "processor": configuration["consultation"]["processor"],
                        "policy_version": configuration["policy_version"],
                    },
                )
            assert edited.status_code == 200, edited.text
            assert (await replay.get("/release", params={"token": gate_token})).status_code == 200
            # SSE重验当前授权，来源变化可关闭已有流；终态以PG事实为准。
            await asyncio.gather(pending_stream, return_exceptions=True)
            pending_stream = None

            async def terminal_run():
                async with pg_manager.get_async_session_context() as session:
                    return (await session.get(AgentRun, gated_run)).status

            await wait_until(terminal_run, lambda status: status == "failed")
            async with pg_manager.get_async_session_context() as session:
                failed = await session.get(AgentRun, gated_run)
                assert failed.status == "failed"
                assert failed.error_type in {"unexpected_error", "output_persistence_error"}
                if failed.error_type == "unexpected_error":
                    assert (
                        "profile_source_changed" if mutation == "profile" else "consent_required"
                    ) in failed.error_message
                assert failed.output_message_id is None
                assert not list(
                    (
                        await session.scalars(
                            select(Message).where(
                                Message.run_id == gated_run,
                                Message.role == "assistant",
                                Message.message_type == "text",
                            )
                        )
                    ).all()
                )
                # 直接验证最终发布守卫也读取当前PG事实，独立于图中的after_model检查。
                with pytest.raises(HealthVisionError) as denied_publication:
                    await validate_profile_publication(session, failed)
                assert denied_publication.value.code == (
                    "profile_source_changed" if mutation == "profile" else "consent_required"
                )
            if mutation == "processing_consent":
                # 档案未改版，后续查询仍由当前权限决定；失败Run不含普通输出。
                result = await client.get(f"/api/agent/runs/{gated_run}/result", headers=headers)
                assert result.status_code == 200 and result.json()["status"] == "failed", result.text
                assert not result.json().get("output")
                return
            denied_result = await client.get(f"/api/agent/runs/{gated_run}/result", headers=headers)
            assert denied_result.status_code == 200 and denied_result.json()["error"]["type"] == "run_not_found"
            assert denied_result.json()["output"] == ""
            calls = (await replay.get("/observations", params={"token": token})).json()["calls"]
            rejected = await client.post(
                "/api/agent/runs",
                headers=headers,
                json={
                    "query": f"HEALTH_CONSULTATION_E2E:{token}:derived_profile",
                    "agent_slug": "health-consultation",
                    "thread_id": thread,
                    "meta": {"request_id": str(uuid4())},
                },
            )
            assert rejected.status_code == 410, rejected.text
            assert (await replay.get("/observations", params={"token": token})).json()["calls"] == calls
            assert (await client.get(f"/api/chat/thread/{thread}/history", headers=headers)).status_code == 404
        finally:
            await replay.get("/release", params={"token": gate_token})
            if pending_stream is not None:
                await asyncio.gather(pending_stream, return_exceptions=True)
            await drain_requests(client, headers, requests)
            async with pg_manager.get_async_session_context() as session:
                await session.execute(
                    delete(HealthFamilyProfileLink).where(HealthFamilyProfileLink.member_id == member_id)
                )
                await session.execute(
                    delete(HealthFamilyProfileUse).where(HealthFamilyProfileUse.member_id == member_id)
                )
                for model in (FamilyAudit, FamilyMeasurement, FamilyProfileRevision):
                    condition = (
                        model.family_id == family_id if model is FamilyAudit else model.member_id == source["id"]
                    )
                    await session.execute(delete(model).where(condition))
                await session.execute(delete(FamilyMember).where(FamilyMember.family_id == family_id))
                await session.execute(
                    delete(FamilyArchive).where(FamilyArchive.id == family_id, FamilyArchive.owner_uid == uid)
                )

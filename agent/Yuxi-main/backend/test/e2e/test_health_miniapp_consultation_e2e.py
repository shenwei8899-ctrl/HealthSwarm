"""小程序本人咨询契约的真实HTTP、Worker及独立PG定向验收。"""

import asyncio
import os
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import func, select

from test.support.health_miniapp_consultation_fixture import (
    ROOT,
    load_state,
    login_headers,
    read_facts,
    require_isolated_slot,
    require_status,
    save_json,
)
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_business import AgentRun, AgentRunRequest, Conversation, Message, Project
from yuxi.storage.postgres.models_health import HealthConsultation

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.e2e,
    pytest.mark.slow,
    pytest.mark.skipif(
        os.getenv("HEALTH_CONSULTATION_E2E_ISOLATED") != "true"
        or os.getenv("HEALTH_MINIAPP_CONSULTATION_E2E") != "true",
        reason="需要独立小程序合成夹具和隔离槽位的显式运行标记",
    ),
]


@pytest.fixture(scope="session", autouse=True)
def cleanup_e2e_test_resources():
    """本轮仅使用CLI精确清理，禁止继承其他E2E账号的批量会话清理。"""
    yield


async def test_consultation_request_run_authority_and_current_source():
    """没有同意不接入，终态按同Run输出，变源与撤权拒绝历史和后续提问。"""
    await require_isolated_slot()
    state = load_state()
    assert not state["cleaned"]
    save_json("http-worker-pg-verification.json", {"passed": False, "status": "running"})
    selected = state["members"]["owner"]
    member_id, token = selected["health_member_id"], selected["replay_token"]
    completed = []
    try:
        async with (
            httpx.AsyncClient(base_url="http://localhost:5050", timeout=20) as client,
            httpx.AsyncClient(base_url="http://localhost:8766", timeout=10) as replay,
        ):
            owner, browser = await login_headers(client, "owner"), await login_headers(client, "browser")
            # 中断后的本轮合成验收可以重入，先明确撤回owner用途同意再验证入口拒绝。
            require_status(
                await client.post(
                    f"{ROOT}/members/{member_id}/processing-consents",
                    headers=owner,
                    json={
                        "purpose": "consultation",
                        "accepted": False,
                        "processor": state["configuration"]["consultation"]["processor"],
                        "policy_version": state["configuration"]["policy_version"],
                    },
                ),
                200,
            )
            thread = await create_thread(client, owner, member_id)
            foreign_thread = await create_thread(client, browser, state["members"]["browser"]["health_member_id"])
            key = str(uuid4())
            body = request_body(thread, token, "profile", key)
            for denied_body, status in ((body, 403), ({**body, "thread_id": foreign_thread}, 404)):
                denied = await client.post("/api/agent/runs", headers=owner, json=denied_body)
                require_status(denied, status)
            await assert_not_received(key)
            completed.append("missing_consent_and_foreign_thread_reject_before_persistence")

            require_status(
                await client.post(
                    f"{ROOT}/members/{member_id}/processing-consents",
                    headers=owner,
                    json={
                        "purpose": "consultation",
                        "accepted": True,
                        "processor": state["configuration"]["consultation"]["processor"],
                        "policy_version": state["configuration"]["policy_version"],
                    },
                ),
                200,
            )
            first = await client.post("/api/agent/runs", headers=owner, json=body)
            require_status(first, 200)
            repeated = await client.post("/api/agent/runs", headers=owner, json=body)
            require_status(repeated, 200)
            assert repeated.json()["request_id"] == key
            first_run = await poll_request_run(client, owner, key)
            assert repeated.json().get("run_id") in (None, first_run)
            result = await poll_result(client, owner, first_run, "completed")
            assert result["output"] == "合成本人身高171；营养安全字段尚未就绪"
            await assert_pg_output(state, key, first_run, 2, 171)
            completed.append("explicit_purpose_consent_idempotent_request_and_worker_v2_authority")

            second_key = str(uuid4())
            require_status(
                await client.post(
                    "/api/agent/runs", headers=owner, json=request_body(thread, token, "derived_profile", second_key)
                ),
                200,
            )
            second_run = await poll_request_run(client, owner, second_key)
            assert second_run != first_run
            second = await poll_result(client, owner, second_run, "completed")
            assert second["output"] == result["output"]
            await assert_pg_output(state, second_key, second_run, 2, 171, source_required=False)
            history = await client.get(f"/api/chat/thread/{thread}/history", headers=owner)
            require_status(history, 200)
            save_json("history-wire-v2.json", history.json())
            completed.append("second_turn_and_real_history_wire_use_exact_request_and_run")

            gate_token = uuid4().hex
            gate_thread = await create_thread(client, owner, member_id)
            gate_key = str(uuid4())
            require_status(
                await client.post(
                    "/api/agent/runs",
                    headers=owner,
                    json=request_body(gate_thread, gate_token, "profile_gate", gate_key),
                ),
                200,
            )
            gate_run = await poll_request_run(client, owner, gate_key)
            try:
                async with asyncio.timeout(35):
                    while True:
                        observation = (await replay.get("/observations", params={"token": gate_token})).json()
                        if any(row["phase"] == "answer" for row in observation["calls"]):
                            break
                        await asyncio.sleep(0.1)
                require_status(await client.post(f"/api/agent/runs/{gate_run}/cancel", headers=owner), 200)
            finally:
                require_status(await replay.get("/release", params={"token": gate_token}), 200)
            cancelled = await poll_result(client, owner, gate_run, "cancelled")
            assert not cancelled.get("output")
            async with pg_manager.get_async_session_context() as session:
                run = await session.get(AgentRun, gate_run)
                assert run.output_message_id is None
            completed.append("real_cancelled_worker_run_never_borrows_a_completed_answer")

            profile_path = f"/api/family/{selected['family_id']}/members/{selected['source_member_id']}"
            edited = await client.put(
                profile_path, headers=owner, json={"expected_version": 2, "profile": {"height_cm": 172}}
            )
            require_status(edited, 200)
            require_status(
                await client.post(profile_path + "/confirm", headers=owner, json={"expected_version": 3}), 200
            )
            previous_calls = (await replay.get("/observations", params={"token": token})).json()
            stale_key = str(uuid4())
            denied = await client.post(
                "/api/agent/runs", headers=owner, json=request_body(thread, token, "derived_profile", stale_key)
            )
            require_status(denied, 410)
            # 普通Agent请求入口将业务错误映射为HTTPException的detail字符串。
            assert set(denied.json()) == {"detail"} and isinstance(denied.json()["detail"], str)
            await assert_not_received(stale_key)
            assert (await replay.get("/observations", params={"token": token})).json() == previous_calls
            require_status(await client.get(f"/api/chat/thread/{thread}/history", headers=owner), 404)
            masked = await client.get(f"/api/agent/runs/{first_run}/result", headers=owner)
            require_status(masked, 200)
            assert masked.json()["error"]["type"] == "run_not_found" and masked.json()["output"] == ""
            completed.append("profile_v3_rejects_old_thread_history_and_result_without_another_model_call")

            fresh_thread = await create_thread(client, owner, member_id)
            fresh_key = str(uuid4())
            require_status(
                await client.post(
                    "/api/agent/runs",
                    headers=owner,
                    json=request_body(fresh_thread, token, "profile_updated", fresh_key),
                ),
                200,
            )
            fresh_run = await poll_request_run(client, owner, fresh_key)
            fresh = await poll_result(client, owner, fresh_run, "completed")
            assert fresh["output"] == "合成本人身高172；营养安全字段尚未就绪"
            await assert_pg_output(state, fresh_key, fresh_run, 3, 172)
            completed.append("explicit_fresh_consultation_reads_current_confirmed_v3_source")

            failed_key = str(uuid4())
            require_status(
                await client.post(
                    "/api/agent/runs",
                    headers=owner,
                    json=request_body(fresh_thread, token, "unsupported_synthetic_probe", failed_key),
                ),
                200,
            )
            failed_run = await poll_request_run(client, owner, failed_key)
            failed = await poll_result(client, owner, failed_run, "failed")
            assert not failed.get("output") and failed.get("error")
            async with pg_manager.get_async_session_context() as session:
                row = await session.get(AgentRun, failed_run)
                assert row.output_message_id is None
                assert not await session.scalar(
                    select(Message.id).where(
                        Message.run_id == failed_run, Message.role == "assistant", Message.message_type == "text"
                    )
                )
            save_json("failed-run-wire.json", failed)
            completed.append("real_failed_worker_run_has_no_final_output_or_neighbor_answer")

            withdrawn_key = str(uuid4())
            original_scopes = next(row["scopes"] for row in state["before"]["grants"] if row["member_id"] == member_id)
            try:
                require_status(
                    await client.put(
                        f"{ROOT}/members/{member_id}/grants",
                        headers=owner,
                        json={"actor_uid": state["accounts"]["owner"]["uid"], "scopes": ["profile_edit"]},
                    ),
                    200,
                )
                require_status(
                    await client.post(
                        "/api/agent/runs",
                        headers=owner,
                        json=request_body(fresh_thread, token, "profile_updated", withdrawn_key),
                    ),
                    404,
                )
                await assert_not_received(withdrawn_key)
                require_status(await client.get(f"/api/chat/thread/{fresh_thread}/history", headers=owner), 404)
                denied_result = await client.get(f"/api/agent/runs/{fresh_run}/result", headers=owner)
                require_status(denied_result, 200)
                assert denied_result.json()["output"] == "" and denied_result.json()["error"]["type"] == "run_not_found"
            finally:
                require_status(
                    await client.put(
                        f"{ROOT}/members/{member_id}/grants",
                        headers=owner,
                        json={"actor_uid": state["accounts"]["owner"]["uid"], "scopes": original_scopes},
                    ),
                    200,
                )
            completed.append("current_scope_withdrawal_denies_submit_and_private_history_without_persistence")

            require_status(
                await client.post(
                    f"{ROOT}/members/{member_id}/processing-consents",
                    headers=owner,
                    json={
                        "purpose": "consultation",
                        "accepted": False,
                        "processor": state["configuration"]["consultation"]["processor"],
                        "policy_version": state["configuration"]["policy_version"],
                    },
                ),
                200,
            )
            consent_key = str(uuid4())
            require_status(
                await client.post(
                    "/api/agent/runs",
                    headers=owner,
                    json=request_body(fresh_thread, token, "profile_updated", consent_key),
                ),
                403,
            )
            await assert_not_received(consent_key)
            facts = await read_facts(state)
            assert facts["grants"] == state["before"]["grants"]
            assert facts["links"] == state["before"]["links"]
            assert not any(row["actor_uid"] == state["accounts"]["browser"]["uid"] for row in facts["consents"])
            assert not any(row["uid"] == state["accounts"]["browser"]["uid"] for row in facts["runs"])
            completed.append("explicit_consent_revocation_and_independent_browser_account_remain_separate")
            save_json(
                "http-worker-pg-verification.json",
                {"passed": True, "status": "passed", "checks": completed, "facts": facts},
            )
    except Exception:
        save_json(
            "http-worker-pg-verification.json",
            {"passed": False, "status": "failed", "completed_checks": completed, "facts": await read_facts(state)},
        )
        raise
    finally:
        await pg_manager.close()


async def test_member_consultation_list_pagination_visibility_and_read_only():
    """真实列表只读当前账号固定角色元数据；持久化负控覆盖有效关系和分页。"""
    await require_isolated_slot()
    state = load_state()
    member_id, uid = state["members"]["owner"]["health_member_id"], state["accounts"]["owner"]["uid"]
    path = f"{ROOT}/members/{member_id}/consultations"
    save_json("consultation-list-verification.json", {"passed": False, "status": "running"})
    try:
        async with httpx.AsyncClient(base_url="http://localhost:5050", timeout=20) as client:
            owner, browser = await login_headers(client, "owner"), await login_headers(client, "browser")
            first = await create_thread(client, owner, member_id)
            second = await create_thread(client, owner, member_id)
            assert first != second
            archived = await create_thread(client, owner, member_id)
            inactive_project = await create_thread(client, owner, member_id)
            foreign = await create_thread(client, browser, state["members"]["browser"]["health_member_id"])
            planner = await client.post(
                f"{ROOT}/members/{member_id}/meal-planner", headers=owner, json={"client_request_id": str(uuid4())}
            )
            require_status(planner, 201)
            planner_thread = planner.json()["thread_id"]
            async with pg_manager.get_async_session_context() as session:
                first_row = await session.scalar(select(Conversation).where(Conversation.thread_id == first))
                second_row = await session.scalar(select(Conversation).where(Conversation.thread_id == second))
                second_row.created_at = first_row.created_at
                (
                    await session.scalar(select(Conversation).where(Conversation.thread_id == archived))
                ).status = "deleted"
                inactive = await session.scalar(select(Conversation).where(Conversation.thread_id == inactive_project))
                (await session.get(Project, inactive.project_id)).status = "deleted"
                foreign_row = await session.scalar(select(Conversation).where(Conversation.thread_id == foreign))
                foreign_binding = await session.get(HealthConsultation, foreign_row.id)
                foreign_binding.actor_uid = uid
                foreign_binding.member_id = member_id
                # 真实数据库维持外来Conversation/Project的同一uid，关联行的actor/member可独立造负控。
            async with pg_manager.get_async_session_context() as session:
                expected = list(
                    (
                        await session.scalars(
                            select(Conversation)
                            .join(HealthConsultation, HealthConsultation.conversation_id == Conversation.id)
                            .join(Project, Project.id == Conversation.project_id)
                            .where(
                                HealthConsultation.actor_uid == uid,
                                HealthConsultation.member_id == member_id,
                                Conversation.uid == uid,
                                Conversation.status == "active",
                                Conversation.agent_id == "health-consultation",
                                Project.uid == uid,
                                Project.status == "active",
                            )
                            .order_by(Conversation.created_at.desc(), Conversation.id.desc())
                        )
                    ).all()
                )
                expected_threads = [row.thread_id for row in expected]
                before = await row_counts(session, state)
            assert first in expected_threads and second in expected_threads
            assert expected_threads.index(second) < expected_threads.index(first), "同created_at按实际数据库id降序"
            received = []
            for offset in range(len(expected_threads)):
                response = await client.get(path, headers=owner, params={"limit": 1, "offset": offset})
                require_status(response, 200)
                page = response.json()
                assert set(page) == {"items", "has_more", "next_offset"}
                assert len(page["items"]) == 1
                item = page["items"][0]
                assert set(item) == {"thread_id", "member_id", "agent_slug", "business_date", "created_at"}
                assert item["member_id"] == member_id and item["agent_slug"] == "health-consultation"
                assert item["business_date"] is None
                assert item["created_at"].endswith("Z")
                received.append(item["thread_id"])
                assert page["has_more"] is (offset + 1 < len(expected_threads))
                assert page["next_offset"] == (offset + 1 if page["has_more"] else None)
            assert received == expected_threads
            assert not {archived, inactive_project, foreign, planner_thread} & set(received)
            far_page = await client.get(path, headers=owner, params={"limit": 1, "offset": 10001})
            require_status(far_page, 200)
            assert far_page.json() == {"items": [], "has_more": False, "next_offset": None}
            require_status(await client.get(path, headers=browser), 404)
            foreign_member = state["members"]["browser"]["health_member_id"]
            require_status(await client.get(f"{ROOT}/members/{foreign_member}/consultations", headers=owner), 404)
            async with pg_manager.get_async_session_context() as session:
                assert await row_counts(session, state) == before
            original = next(row["scopes"] for row in state["before"]["grants"] if row["member_id"] == member_id)
            try:
                require_status(
                    await client.put(
                        f"{ROOT}/members/{member_id}/grants",
                        headers=owner,
                        json={"actor_uid": uid, "scopes": ["profile_edit"]},
                    ),
                    200,
                )
                require_status(await client.get(path, headers=owner), 404)
            finally:
                require_status(
                    await client.put(
                        f"{ROOT}/members/{member_id}/grants", headers=owner, json={"actor_uid": uid, "scopes": original}
                    ),
                    200,
                )
            save_json(
                "consultation-list-verification.json",
                {
                    "passed": True,
                    "status": "passed",
                    "threads": received,
                    "excluded": {
                        "deleted_conversation": archived,
                        "deleted_project": inactive_project,
                        "foreign_actor_namespace": foreign,
                        "planner": planner_thread,
                    },
                    "read_only_counts": before,
                },
            )
    finally:
        await pg_manager.close()


async def create_thread(client, headers, member_id):
    """固定健康成员的咨询绑定使用自己的幂等意图，重复调用不增线程。"""
    key = str(uuid4())
    path = f"{ROOT}/members/{member_id}/consultations"
    body = {"client_request_id": key}
    response = await client.post(path, headers={**headers, "Idempotency-Key": key}, json=body)
    require_status(response, 201)
    repeated = await client.post(path, headers={**headers, "Idempotency-Key": key}, json=body)
    require_status(repeated, 201)
    assert repeated.json() == response.json()
    return response.json()["thread_id"]


def request_body(thread, token, step, key):
    """与正式小程序提交相同的固定角色、线程和Request包。"""
    return {
        "query": f"HEALTH_CONSULTATION_E2E:{token}:{step}",
        "agent_slug": "health-consultation",
        "thread_id": thread,
        "meta": {"request_id": key},
    }


async def poll_request_run(client, headers, key):
    """只跟随当前Request派发的Run，永不查询线程最近回答。"""
    async with asyncio.timeout(45):
        while True:
            response = await client.get(f"/api/agent/requests/{key}", headers=headers)
            require_status(response, 200)
            request = response.json()["request"]
            assert request["request_id"] == key
            if request.get("dispatched_run_id"):
                return request["dispatched_run_id"]
            await asyncio.sleep(0.1)


async def poll_result(client, headers, run_id, status):
    """轮询指定Run的权威终态；失败不会被相邻Run覆盖。"""
    async with asyncio.timeout(45):
        while True:
            response = await client.get(f"/api/agent/runs/{run_id}/result", headers=headers)
            require_status(response, 200)
            data = response.json()
            if data["status"] in {"completed", "failed", "cancelled", "interrupted"}:
                assert data["status"] == status, data
                return data
            await asyncio.sleep(0.1)


async def assert_not_received(request_id):
    """拒绝请求必须没有Message、Request或Run持久化事实。"""
    async with pg_manager.get_async_session_context() as session:
        for model in (Message, AgentRunRequest, AgentRun):
            assert not await session.scalar(select(model).where(model.request_id == request_id))


async def assert_pg_output(state, request_id, run_id, version, height, *, source_required=True):
    """独立PG查询使用夹具身份及数值oracle核对同Run最终Message与来源。"""
    facts = await read_facts(state)
    run = next(row for row in facts["runs"] if row["run_id"] == run_id)
    request = next(row for row in facts["requests"] if row["request_id"] == request_id)
    selected, uid = state["members"]["owner"], state["accounts"]["owner"]["uid"]
    assert request["run_id"] == run_id and request["uid"] == uid
    assert run["request_id"] == request_id and run["uid"] == uid
    assert run["thread_id"] == request["thread_id"]
    assert run["binding"] == {"member_id": selected["health_member_id"], "actor_uid": uid}
    assert run["message"] == {
        "run_id": run_id,
        "request_id": request_id,
        "role": "assistant",
        "message_type": "text",
        "content": f"合成本人身高{height}；营养安全字段尚未就绪",
    }
    assert run["attempts"] and all(row["finished"] and row["outcome"] == "completed" for row in run["attempts"])
    if source_required:
        assert len(run["profile_uses"]) == 1
        source = run["profile_uses"][0]
        assert (source["member_id"], source["source_member_id"], source["version"]) == (
            selected["health_member_id"],
            selected["source_member_id"],
            version,
        )
        assert len(source["payload_hash"]) == 64


async def row_counts(session, state):
    """独立统计实际对象，列表读取不应新增消息、线程、请求、Run或绑定。"""
    uids = [row["uid"] for row in state["accounts"].values()]
    counts = {}
    for model in (Conversation, Project, AgentRunRequest, AgentRun):
        counts[model.__tablename__] = int(
            await session.scalar(select(func.count()).select_from(model).where(model.uid.in_(uids))) or 0
        )
    counts[Message.__tablename__] = int(
        await session.scalar(
            select(func.count())
            .select_from(Message)
            .join(Conversation, Conversation.id == Message.conversation_id)
            .where(Conversation.uid.in_(uids))
        )
        or 0
    )
    counts[HealthConsultation.__tablename__] = int(
        await session.scalar(
            select(func.count()).select_from(HealthConsultation).where(HealthConsultation.actor_uid.in_(uids))
        )
        or 0
    )
    return counts

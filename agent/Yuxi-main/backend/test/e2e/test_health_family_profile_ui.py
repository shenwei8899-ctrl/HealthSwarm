"""真实浏览器填写、关联及档案改版的隔离 UI 验收夹具与 PG 回读。"""

import asyncio
import json
import os
from pathlib import Path
from uuid import NAMESPACE_URL, uuid4, uuid5

import httpx
import pytest
from sqlalchemy import delete, select

from test.e2e.test_health_consultation_e2e import drain_requests, isolated_health  # noqa: F401
from test.integration.services.test_health_vision_http import ROOT, create_member, health_http  # noqa: F401
from yuxi.services.health_daily_service import business_date
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_business import (
    AgentRun,
    AgentRunRequest,
    Conversation,
    FamilyArchive,
    FamilyAudit,
    FamilyMeasurement,
    FamilyMember,
    FamilyProfileRevision,
    Message,
)
from yuxi.storage.postgres.models_health import (
    HealthConsultation,
    HealthDailyConversation,
    HealthFamilyProfileLink,
    HealthFamilyProfileUse,
)

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.e2e,
    pytest.mark.slow,
    pytest.mark.skipif(os.getenv("HEALTH_CONSULTATION_E2E_ISOLATED") != "true", reason="仅在隔离合成槽位运行"),
    pytest.mark.skipif(not os.getenv("HEALTH_PROFILE_UI_CONTROL_DIR"), reason="需要真实浏览器验收控制目录"),
]


async def test_browser_profile_confirmation_link_and_fresh_consultation(isolated_health):  # noqa: F811
    """准备空合成档案，等待真实 UI 回执后独立核对版本、输出及旧会话拒绝。"""
    client, users, _, _ = isolated_health
    headers, uid = users[0]["headers"], users[0]["uid"]
    control = Path(os.environ["HEALTH_PROFILE_UI_CONTROL_DIR"])
    control.mkdir(parents=True, exist_ok=True)
    assert not any(
        (control / name).exists() for name in ("context.json", "done.json", "failure.json", "verified.json")
    ), "UI 控制目录必须是本轮新建的空目录"
    member_id = await create_member(client, headers)
    created = await client.post("/api/family", headers=headers, json={"name": "合成浏览器本人档案验收"})
    assert created.status_code == 200
    family_id = created.json()["id"]
    source = next(item for item in created.json()["members"] if item["is_self"])
    source_id, token = source["id"], uuid4().hex
    try:
        async with pg_manager.get_async_session_context() as session:
            empty = await session.get(FamilyMember, source_id)
            assert empty.version == 1 and empty.confirmed_version is None and empty.profile == {}
            assert await session.get(HealthFamilyProfileLink, member_id) is None
        write_control(
            control / "context.json",
            {
                "access_token": headers["Authorization"].removeprefix("Bearer "),
                "health_member_id": member_id,
                "family_id": family_id,
                "source_id": source_id,
                "replay_token": token,
                "uid": uid,
            },
        )
        receipt = await wait_for_browser(control)
        expected_keys = {"old_thread", "new_thread", "old_run_id", "new_run_id"}
        assert isinstance(receipt, dict) and set(receipt) == expected_keys, "浏览器完成回执字段不符合协议"
        old_thread, new_thread = receipt["old_thread"], receipt["new_thread"]
        old_run_id, new_run_id = receipt["old_run_id"], receipt["new_run_id"]
        assert old_thread != new_thread and old_run_id != new_run_id, "改版后必须显式创建新的咨询"
        async with pg_manager.get_async_session_context() as session:
            links = list(
                (
                    await session.scalars(
                        select(HealthFamilyProfileLink).where(HealthFamilyProfileLink.actor_uid == uid)
                    )
                ).all()
            )
            assert len(links) == 1
            link = links[0]
            assert (link.member_id, link.family_id, link.source_member_id) == (member_id, family_id, source_id)
            current = await session.get(FamilyMember, source_id)
            assert current.version == current.confirmed_version == 3 and current.profile["height_cm"] == 172
            revisions = list(
                (
                    await session.scalars(
                        select(FamilyProfileRevision)
                        .where(FamilyProfileRevision.member_id == source_id)
                        .order_by(FamilyProfileRevision.version)
                    )
                ).all()
            )
            assert [(row.version, row.profile["height_cm"]) for row in revisions] == [(2, 171), (3, 172)]
            assert all(row.actor_uid == uid for row in revisions)
            consultations = list(
                (
                    await session.scalars(
                        select(HealthConsultation).where(
                            HealthConsultation.actor_uid == uid, HealthConsultation.member_id == member_id
                        )
                    )
                ).all()
            )
            assert len(consultations) == 2
            by_thread = {
                (await session.get(Conversation, binding.conversation_id)).thread_id: binding
                for binding in consultations
            }
            assert set(by_thread) == {old_thread, new_thread}
            daily_key = str(uuid5(NAMESPACE_URL, f"health-daily:{uid}:{member_id}:{business_date().isoformat()}"))
            assert by_thread[old_thread].request_id == daily_key
            daily = await session.get(HealthDailyConversation, by_thread[old_thread].conversation_id)
            assert daily is not None and daily.member_id == member_id and daily.business_date == business_date()
            assert await session.get(HealthDailyConversation, by_thread[new_thread].conversation_id) is None
            for run_id, thread, step, height, version in (
                (old_run_id, old_thread, "profile", 171, 2),
                (new_run_id, new_thread, "profile_updated", 172, 3),
            ):
                run = await session.get(AgentRun, run_id)
                assert run is not None and run.uid == uid and run.status == "completed"
                assert run.conversation_id == by_thread[thread].conversation_id
                output = await session.get(Message, run.output_message_id)
                assert output.run_id == run.id and output.role == "assistant" and output.message_type == "text"
                assert output.content == f"合成本人身高{height}；营养安全字段尚未就绪"
                query = await session.scalar(
                    select(Message).where(Message.request_id == run.request_id, Message.role == "user")
                )
                assert query.content == f"HEALTH_CONSULTATION_E2E:{token}:{step}"
                uses = list(
                    (
                        await session.scalars(
                            select(HealthFamilyProfileUse).where(HealthFamilyProfileUse.run_id == run_id)
                        )
                    ).all()
                )
                assert len(uses) == 1
                use = uses[0]
                assert (use.member_id, use.source_member_id, use.version) == (member_id, source_id, version)
                assert len(use.payload_hash) == 64

        async with httpx.AsyncClient(base_url="http://localhost:8766", timeout=10) as replay:
            observed = await replay.get("/observations", params={"token": token})
            assert observed.status_code == 200
            assert observed.json()["calls"] == [
                {"step": step, "phase": phase, "record_ids": [source_id] if phase == "answer" else []}
                for step in ("profile", "profile_updated")
                for phase in ("read", "answer")
            ]
        daily_again = await client.post(f"{ROOT}/members/{member_id}/daily-consultations", headers=headers)
        assert daily_again.status_code == 410 and daily_again.json()["code"] == "profile_source_changed"
        history = await client.get(f"/api/chat/thread/{old_thread}/history", headers=headers)
        assert history.status_code == 404
        denied_result = await client.get(f"/api/agent/runs/{old_run_id}/result", headers=headers)
        assert denied_result.status_code == 200 and denied_result.json()["error"]["type"] == "run_not_found"
        assert denied_result.json()["output"] == ""
        result = await client.get(f"/api/agent/runs/{new_run_id}/result", headers=headers)
        assert result.status_code == 200 and result.json()["status"] == "completed"
        assert result.json()["output"] == "合成本人身高172；营养安全字段尚未就绪"
        repeated = await client.post(
            f"{ROOT}/members/{member_id}/family-profile-link",
            headers=headers,
            json={"family_id": family_id, "source_member_id": source_id, "confirmed_identity": True},
        )
        assert repeated.status_code == 200
        assert repeated.json() == {
            "member_id": member_id,
            "family_id": family_id,
            "source_member_id": source_id,
            "scope": "self_confirmed_profile",
        }
        async with pg_manager.get_async_session_context() as session:
            links = list(
                (
                    await session.scalars(
                        select(HealthFamilyProfileLink).where(HealthFamilyProfileLink.actor_uid == uid)
                    )
                ).all()
            )
            assert len(links) == 1 and links[0].member_id == member_id and links[0].source_member_id == source_id
        write_control(control / "verified.json", {"status": "passed", **receipt, "versions": [2, 3]})
    finally:
        async with pg_manager.get_async_session_context() as session:
            request_ids = list(
                (await session.scalars(select(AgentRunRequest.request_id).where(AgentRunRequest.uid == uid))).all()
            )
        await drain_requests(client, headers, request_ids)
        async with pg_manager.get_async_session_context() as session:
            await session.execute(delete(HealthFamilyProfileUse).where(HealthFamilyProfileUse.member_id == member_id))
            await session.execute(delete(HealthFamilyProfileLink).where(HealthFamilyProfileLink.member_id == member_id))
            await session.execute(delete(FamilyAudit).where(FamilyAudit.family_id == family_id))
            for model in (FamilyMeasurement, FamilyProfileRevision):
                await session.execute(delete(model).where(model.member_id == source_id))
            await session.execute(delete(FamilyMember).where(FamilyMember.family_id == family_id))
            await session.execute(
                delete(FamilyArchive).where(FamilyArchive.id == family_id, FamilyArchive.owner_uid == uid)
            )


async def wait_for_browser(control):
    """只读取完成或失败信号，不输出带凭据的控制文件及浏览器正文。"""
    try:
        async with asyncio.timeout(1200):
            while True:
                if (control / "failure.json").exists():
                    pytest.fail("真实浏览器 UI 验收失败，请检查本地浏览器报告")
                done = control / "done.json"
                if done.exists():
                    return json.loads(done.read_text(encoding="utf-8"))
                await asyncio.sleep(1)
    except TimeoutError:
        pytest.fail("等待真实浏览器 UI 验收回执超时；未形成验收通过证据")


def write_control(path, payload):
    """原子发布仅供本轮浏览器读取的私有控制文件。"""
    pending = path.with_suffix(".pending")
    with pending.open("x", encoding="utf-8") as stream:
        os.chmod(pending, 0o600)
        json.dump(payload, stream, ensure_ascii=False)
        stream.write("\n")
    pending.replace(path)

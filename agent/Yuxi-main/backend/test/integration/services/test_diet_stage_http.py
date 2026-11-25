"""隔离PostgreSQL、真实TCP/HTTP和真实任务lease验证阶段管理。"""

import asyncio
from contextlib import asynccontextmanager
from copy import deepcopy
from datetime import timedelta
import json
import os
import socket
from types import SimpleNamespace
from uuid import uuid4

from fastapi import FastAPI, Header
import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
import uvicorn

from server.routers.diet_stage_router import diet_stage
from server.utils.auth_middleware import get_required_user
from yuxi.repositories.task_repository import TaskRepository
from yuxi.services import diet_stage_tasks
from yuxi.services.health_vision_service import health_vision_service
from yuxi.services.task_service import TaskContext, tasker
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_business import (
    Base,
    FamilyArchive,
    FamilyMember,
    FamilyProfileRevision,
    TaskRecord,
    User,
)
from yuxi.storage.postgres.models_diet_stage import DietStage, DietStageReview
from yuxi.storage.postgres.models_health import FamilyMember as HealthMember, HealthFamilyProfileLink
from yuxi.utils.datetime_utils import utc_now_naive

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.fixture(scope="session", autouse=True)
def cleanup_test_sandboxes():
    """本文件不创建沙盒，专用测试容器由运行脚本停止。"""
    yield


@pytest.fixture(scope="session", autouse=True)
def cleanup_test_knowledge_resources():
    """本文件只创建合成关系数据，不创建知识库对象。"""
    yield


@pytest.fixture(scope="session", autouse=True)
def ensure_live_api_schema():
    """专用数据库由本文件建表，不读取共享生产schema。"""


@pytest_asyncio.fixture
async def stage_http(monkeypatch):
    """只使用专用合成数据库，不连接共享业务数据库。"""
    dsn = os.environ["DIET_STAGE_TEST_POSTGRES_URL"]
    assert "diet_stage_test" in dsn
    engine = create_async_engine(dsn)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    uid, viewer, outsider = "stage-owner-" + uuid4().hex, "stage-viewer-" + uuid4().hex, "stage-outside-" + uuid4().hex
    fid, mid, other, hid = [str(uuid4()) for _ in range(4)]
    profile = {"goal": "规律三餐", "dietary_details": {"goals": ["规律三餐"]}}
    async with sessions.begin() as session:
        for account in (uid, viewer, outsider):
            session.add(User(uid=account, username=account, password_hash="synthetic-not-used"))
        await session.flush()
        session.add(FamilyArchive(id=fid, owner_uid=uid, name="合成家庭", settings={}))
        await session.flush()
        session.add_all(
            [
                FamilyMember(
                    id=mid, family_id=fid, subject_uid=uid, name="合成成员", relationship="本人", profile=profile
                ),
                FamilyMember(
                    id=other, family_id=fid, subject_uid=viewer, name="合成家人", relationship="家人", profile={}
                ),
                HealthMember(id=hid, owner_uid=uid, display_name="合成成员", relationship_label="本人"),
            ]
        )
        await session.flush()
        session.add(
            HealthFamilyProfileLink(
                member_id=hid, source_member_id=mid, family_id=fid, actor_uid=uid, source_kind="miniapp_reported"
            )
        )
        session.add(FamilyProfileRevision(member_id=mid, version=1, profile=profile, actor_uid=uid))

    @asynccontextmanager
    async def context():
        async with sessions() as session:
            async with session.begin():
                yield session

    monkeypatch.setattr(pg_manager, "get_async_session_context", context)

    async def configuration(session=None):
        return {
            "consultation": {"available": True, "model": "synthetic/model", "processor": "synthetic"},
            "policy_version": "test-policy",
        }

    monkeypatch.setattr(health_vision_service, "configuration", configuration)
    published = []

    async def publish(task):
        async with sessions() as session:
            assert await session.get(TaskRecord, task.id) is not None
        published.append(task.id)

    monkeypatch.setattr(tasker, "publish", publish)
    from yuxi.services import health_ai_budget_service as budget

    async def reserve(*args):
        return SimpleNamespace()

    async def settle(*args):
        return None

    calls = []

    class Model:
        async def ainvoke(self, messages):
            content = json.loads(messages[-1].content)
            calls.append(content)
            if content["kind"] == "review":
                result = {
                    "summary": "根据已记录的行动进行回顾，缺少记餐不算未完成。",
                    "observations": ["按已确认行动继续回顾"],
                    "next_steps": ["保留适合自己的安排"],
                }
            else:
                result = {
                    "goals": ["规律三餐"],
                    "actions": [{"title": "提前准备早餐", "target": 3, "count": 0}],
                    "reason": "先从可执行的行为开始",
                }
            return SimpleNamespace(content=json.dumps(result, ensure_ascii=False), usage_metadata=None)

    monkeypatch.setattr(budget, "reserve_model", reserve)
    monkeypatch.setattr(budget, "settle", settle)
    monkeypatch.setattr(budget, "reserved_chat_model", lambda *args, **kwargs: Model())
    app = FastAPI()
    app.include_router(diet_stage, prefix="/api")

    async def actor(x_stage_test_user: str = Header(default="owner")):
        return SimpleNamespace(uid={"owner": uid, "viewer": viewer, "outsider": outsider}[x_stage_test_user])

    app.dependency_overrides[get_required_user] = actor
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(128)
    port = listener.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, log_level="critical", lifespan="off"))
    running = asyncio.create_task(server.serve(sockets=[listener]))
    for _ in range(100):
        if server.started:
            break
        await asyncio.sleep(0.01)
    root = f"/api/health/v1/families/{fid}/members/{mid}/diet-stage"
    async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}", timeout=20) as client:
        yield SimpleNamespace(
            client=client,
            root=root,
            sessions=sessions,
            uid=uid,
            mid=mid,
            fid=fid,
            hid=hid,
            other=other,
            published=published,
            calls=calls,
        )
    server.should_exit = True
    await running
    listener.close()
    await engine.dispose()


async def finish_job(c, job_id):
    """真正claim任务并通过当前lease发布领域结果。"""
    async with c.sessions() as session:
        job = await session.get(DietStageReview, job_id)
        task = await session.get(TaskRecord, job.task_id)
        payload, tid = deepcopy(task.payload), task.id
    worker = "stage-test-" + uuid4().hex
    _, claimed = await TaskRepository().claim(tid, worker_id=worker, lease_seconds=180)
    assert claimed
    await diet_stage_tasks.run_diet_stage(TaskContext(tid, worker, payload))
    row = (await c.client.get(c.root + "/generations/" + job_id)).json()
    assert row["status"] == "ready", row
    return row


async def start_stage(c):
    data = {"client_request_id": str(uuid4()), "kind": "draft", "goals": ["规律三餐"]}
    response = await c.client.post(c.root + "/generations", json=data)
    assert response.status_code == 200, response.text
    job = await finish_job(c, response.json()["id"])
    body = {
        "client_request_id": str(uuid4()),
        "expected_version": 0,
        "profile_version": 1,
        "goals": job["result"]["goals"],
        "actions": job["result"]["actions"],
        "draft_id": job["id"],
    }
    saved = await c.client.put(c.root, json=body)
    assert saved.status_code == 200, saved.text
    return saved.json(), body


async def test_stage_confirmation_and_replay_are_atomic_and_reads_do_not_generate(stage_http):
    c = stage_http
    first = await c.client.get(c.root)
    assert first.status_code == 200 and first.json()["stage"] is None and not c.published
    saved, body = await start_stage(c)
    again = await c.client.put(c.root, json=body)
    assert again.json() == saved
    async with c.sessions() as session:
        member = await session.get(FamilyMember, c.mid)
        assert member.profile["goal"] == "规律三餐"
        assert member.profile["dietary_details"]["goals"] == saved["stage"]["goals"]
        assert member.version == 2
        assert (await session.scalars(select(DietStage).where(DietStage.member_id == c.mid))).all().__len__() == 1
    changed = {**body, "goals": ["另一个目标"]}
    assert (await c.client.put(c.root, json=changed)).status_code == 409


async def test_action_counts_are_independent_replayable_and_reject_stale_concurrent_writes(stage_http):
    c = stage_http
    saved, _ = await start_stage(c)
    week = saved["week"]
    actions = deepcopy(week["actions"])
    actions[0]["count"] = 1
    body = {"client_request_id": str(uuid4()), "expected_version": 1, "actions": actions}
    path = c.root + f"/{saved['stage']['id']}/weeks/{week['id']}"
    first = await c.client.put(path, json=body)
    assert first.status_code == 200 and first.json()["actions"][0]["count"] == 1
    assert (await c.client.put(path, json=body)).json() == first.json()
    stale = await c.client.put(path, json={**body, "client_request_id": str(uuid4())})
    assert stale.status_code == 409
    current = (await c.client.get(c.root)).json()
    assert current["profile_version"] == 2 and current["stage"]["version"] == 1
    actions[0]["count"] = 0
    undo = await c.client.put(path, json={"client_request_id": str(uuid4()), "expected_version": 2, "actions": actions})
    assert undo.json()["completed"] == 0


async def test_no_private_job_or_write_for_other_actor_or_other_member(stage_http):
    c = stage_http
    saved, _ = await start_stage(c)
    viewer = {"X-Stage-Test-User": "viewer"}
    denied = await c.client.post(
        c.root + "/generations", headers=viewer, json={"client_request_id": str(uuid4()), "kind": "review"}
    )
    assert denied.status_code == 403
    assert (await c.client.get(c.root, headers={"X-Stage-Test-User": "outsider"})).status_code == 404
    job = c.published[0]
    async with c.sessions() as session:
        actual = await session.scalar(select(DietStageReview).where(DietStageReview.task_id == job))
        jid = actual.id
    assert (await c.client.get(c.root + "/generations/" + jid, headers=viewer)).status_code == 404
    other_root = c.root.replace(c.mid, c.other)
    assert (await c.client.get(other_root + "?stage_id=" + saved["stage"]["id"])).status_code == 404


async def test_review_without_report_and_source_change_never_reuses_stale_text(stage_http):
    c = stage_http
    saved, _ = await start_stage(c)
    job = await c.client.post(
        c.root + "/generations",
        json={"client_request_id": str(uuid4()), "kind": "review", "stage_id": saved["stage"]["id"]},
    )
    result = await finish_job(c, job.json()["id"])
    assert result["reports"] == [] and "缺少记餐" in result["result"]["summary"]
    actions = deepcopy(saved["week"]["actions"])
    actions[0]["count"] = 1
    path = c.root + f"/{saved['stage']['id']}/weeks/{saved['week']['id']}"
    assert (
        await c.client.put(path, json={"client_request_id": str(uuid4()), "expected_version": 1, "actions": actions})
    ).status_code == 200
    stale = (await c.client.get(c.root + "/generations/" + result["id"])).json()
    assert stale["status"] == "stale" and stale["result"] is None


async def test_lost_task_lease_cannot_publish_draft(stage_http):
    c = stage_http
    response = await c.client.post(c.root + "/generations", json={"client_request_id": str(uuid4()), "kind": "draft"})
    jid = response.json()["id"]
    async with c.sessions() as session:
        job = await session.get(DietStageReview, jid)
        task = await session.get(TaskRecord, job.task_id)
        payload, tid = deepcopy(task.payload), task.id
    await TaskRepository().claim(tid, worker_id="actual-owner", lease_seconds=180)
    with pytest.raises(asyncio.CancelledError):
        await diet_stage_tasks.run_diet_stage(TaskContext(tid, "obsolete-owner", payload))
    async with c.sessions() as session:
        assert (await session.get(DietStageReview, jid)).result is None


async def test_end_confirmation_rejects_early_review_even_when_ready(stage_http):
    c = stage_http
    saved, _ = await start_stage(c)
    early = await c.client.post(
        c.root + "/generations",
        json={"client_request_id": str(uuid4()), "kind": "review", "stage_id": saved["stage"]["id"]},
    )
    await finish_job(c, early.json()["id"])
    async with c.sessions.begin() as session:
        stage = await session.get(DietStage, saved["stage"]["id"])
        stage.starts_on -= timedelta(days=90)
        stage.review_on = diet_stage_tasks.stage_today()
    draft_job = await c.client.post(
        c.root + "/generations",
        json={"client_request_id": str(uuid4()), "kind": "draft", "stage_id": saved["stage"]["id"]},
    )
    draft = await finish_job(c, draft_job.json()["id"])
    response = await c.client.put(
        c.root,
        json={
            "client_request_id": str(uuid4()),
            "expected_version": 1,
            "profile_version": 2,
            "goals": draft["result"]["goals"],
            "actions": draft["result"]["actions"],
            "draft_id": draft["id"],
            "previous_stage_id": saved["stage"]["id"],
        },
    )
    assert response.status_code == 409 and response.json()["code"] == "stage_review_stale"


async def test_original_generation_request_replays_before_and_after_completion(stage_http):
    c = stage_http
    body = {"client_request_id": str(uuid4()), "kind": "draft"}
    a = await c.client.post(c.root + "/generations", json=body)
    b = await c.client.post(c.root + "/generations", json=body)
    assert a.json()["id"] == b.json()["id"] and len(c.published) == 1
    await finish_job(c, a.json()["id"])
    replay = await c.client.post(c.root + "/generations", json=body)
    assert replay.json()["id"] == a.json()["id"] and replay.json()["status"] == "ready"
    assert len(c.published) == 1


async def test_rotating_scan_reaches_member_after_first_hundred(stage_http):
    from yuxi.storage.postgres.models_diet_stage import DietActionWeek
    from yuxi.services.diet_stage_types import review_date

    c = stage_http
    saved, _ = await start_stage(c)
    today = diet_stage_tasks.stage_today()
    async with c.sessions.begin() as session:
        stage = await session.get(DietStage, saved["stage"]["id"])
        stage.starts_on = today - timedelta(days=90)
        stage.review_on = today
        stage.checked_at = utc_now_naive() - timedelta(days=100)
        for i in range(100):
            member_id, sid = str(uuid4()), str(uuid4())
            session.add(
                FamilyMember(id=member_id, family_id=c.fid, name=f"合成轮转{i}", relationship="家人", profile={})
            )
            await session.flush()
            session.add(
                DietStage(
                    id=sid,
                    family_id=c.fid,
                    member_id=member_id,
                    actor_uid=c.uid,
                    starts_on=today,
                    review_on=review_date(today),
                    goals=["规律三餐"],
                )
            )
            await session.flush()
            session.add(
                DietActionWeek(
                    id=str(uuid4()),
                    stage_id=sid,
                    starts_on=today,
                    ends_on=today + timedelta(days=7),
                    actions=[],
                    version=1,
                )
            )
    c.published.clear()
    await diet_stage_tasks.prepare_diet_stages({})
    async with c.sessions() as session:
        assert (
            await session.scalar(
                select(DietStageReview).where(
                    DietStageReview.stage_id == saved["stage"]["id"], DietStageReview.kind == "review"
                )
            )
            is None
        )
    await diet_stage_tasks.prepare_diet_stages({})
    async with c.sessions() as session:
        assert (
            await session.scalar(
                select(DietStageReview).where(
                    DietStageReview.stage_id == saved["stage"]["id"], DietStageReview.kind == "review"
                )
            )
            is not None
        )


async def test_complete_report_query_is_not_truncated_at_one_hundred_fields(stage_http):
    from yuxi.services.diet_stage_sources import report_sources
    from yuxi.storage.postgres.models_health import HealthObservation, VisionConfirmation, VisionDraft

    c = stage_http
    draft, confirmation = str(uuid4()), str(uuid4())
    async with c.sessions.begin() as session:
        session.add(
            VisionDraft(
                id=draft,
                member_id=c.hid,
                kind="report",
                version=1,
                review_status="confirmed",
                original_payload={},
                payload={},
            )
        )
        await session.flush()
        session.add(
            VisionConfirmation(
                id=confirmation,
                draft_id=draft,
                draft_version=1,
                actor_uid=c.uid,
                member_id=c.hid,
                kind="report",
                request_id=str(uuid4()),
                fingerprint="a" * 64,
                target_ids=[],
            )
        )
        await session.flush()
        for i in range(121):
            session.add(
                HealthObservation(
                    id=str(uuid4()),
                    member_id=c.hid,
                    confirmation_id=confirmation,
                    field_id=str(uuid4()),
                    snapshot={
                        "name": f"合成指标{i}",
                        "observation_code": "unknown",
                        "observed_at": "2026-11-25",
                        "value_raw": str(i),
                    },
                )
            )
    async with c.sessions() as session:
        rows = await report_sources(session, c.uid, c.hid)
        assert len(rows) == 121
    async with c.sessions.begin() as session:
        row = await session.get(VisionDraft, draft)
        row.review_status = "withdrawn"
    async with c.sessions() as session:
        assert await report_sources(session, c.uid, c.hid) == []


async def test_ended_review_freezes_text_and_adds_new_report_as_supplement(stage_http):
    from yuxi.storage.postgres.models_health import HealthObservation, VisionConfirmation, VisionDraft

    c = stage_http
    saved, _ = await start_stage(c)
    today = diet_stage_tasks.stage_today()

    async def report(day, number):
        draft, confirmation = str(uuid4()), str(uuid4())
        async with c.sessions.begin() as session:
            session.add(
                VisionDraft(
                    id=draft,
                    member_id=c.hid,
                    kind="report",
                    version=1,
                    review_status="confirmed",
                    original_payload={},
                    payload={},
                )
            )
            await session.flush()
            session.add(
                VisionConfirmation(
                    id=confirmation,
                    draft_id=draft,
                    draft_version=1,
                    actor_uid=c.uid,
                    member_id=c.hid,
                    kind="report",
                    request_id=str(uuid4()),
                    fingerprint="b" * 64,
                    target_ids=[],
                )
            )
            await session.flush()
            session.add(
                HealthObservation(
                    id=str(uuid4()),
                    member_id=c.hid,
                    confirmation_id=confirmation,
                    field_id=str(uuid4()),
                    snapshot={
                        "name": "合成指标",
                        "observation_code": "glucose",
                        "observed_at": day.isoformat(),
                        "value_raw": str(number),
                        "value_numeric": str(number),
                        "unit_raw": "mmol/L",
                        "fasting": "yes",
                    },
                )
            )

    async with c.sessions.begin() as session:
        stage = await session.get(DietStage, saved["stage"]["id"])
        stage.starts_on = today - timedelta(days=90)
        stage.review_on = today
    await report(today - timedelta(days=100), 7)
    response = await c.client.post(
        c.root + "/generations",
        json={"client_request_id": str(uuid4()), "kind": "review", "stage_id": saved["stage"]["id"]},
    )
    original = await finish_job(c, response.json()["id"])
    async with c.sessions.begin() as session:
        stage = await session.get(DietStage, saved["stage"]["id"])
        stage.status = "completed"
    await report(today, 6)
    supplement = (await c.client.get(c.root + "/generations/" + original["id"])).json()
    assert supplement["status"] == "ready"
    assert supplement["result"] == original["result"]
    assert supplement["reports"][0]["supplemental"] is True
    assert supplement["reports"][0]["delta"] == "-1"


async def seed_stage_conversation(c, *, hidden=False, failed=False):
    """合成真实日会话、用户原话及过期商品审计，供来源边界测试。"""
    from yuxi.storage.postgres.models_business import Project, Conversation, AgentRun, Message, TOOL_AUDIT_MESSAGE_TYPE
    from yuxi.storage.postgres.models_health import HealthConsultation, HealthDailyConversation
    from yuxi.services.diet_stage_types import stage_today

    pid, thread, rid, request = [str(uuid4()) for _ in range(4)]
    async with c.sessions.begin() as session:
        session.add(
            Project(
                id=pid,
                uid=c.uid,
                name="合成阶段测试",
                selection_status="implicit",
                directory_mode="managed",
                workdir_path="projects/" + pid,
                status="deleted" if hidden else "active",
            )
        )
        await session.flush()
        conversation = Conversation(thread_id=thread, uid=c.uid, agent_id="health-consultation", project_id=pid)
        session.add(conversation)
        await session.flush()
        session.add(
            HealthConsultation(
                conversation_id=conversation.id, actor_uid=c.uid, member_id=c.hid, request_id=str(uuid4())
            )
        )
        await session.flush()
        session.add(
            HealthDailyConversation(
                conversation_id=conversation.id, actor_uid=c.uid, member_id=c.hid, business_date=stage_today()
            )
        )
        session.add(
            AgentRun(
                id=rid,
                conversation_id=conversation.id,
                conversation_thread_id=thread,
                runtime_scope_id=thread,
                agent_slug="health-consultation",
                uid=c.uid,
                status="failed" if failed else "completed",
                request_id=request,
            )
        )
        await session.flush()
        session.add_all(
            [
                Message(
                    conversation_id=conversation.id,
                    role="user",
                    content="合成：最近早餐不规律",
                    request_id=request,
                    run_id=rid,
                ),
                Message(
                    conversation_id=conversation.id,
                    role="assistant",
                    content="旧AI答复不得当成执行事实",
                    request_id=request,
                    run_id=rid,
                ),
                Message(
                    conversation_id=conversation.id,
                    role="tool",
                    message_type=TOOL_AUDIT_MESSAGE_TYPE,
                    execution_status="completed",
                    extra_metadata={"tool_name": "query_food_catalog"},
                    content=json.dumps({"catalog_context_version": 1, "profile_context": {"profile_hash": "expired"}}),
                    request_id=request,
                    run_id=rid,
                ),
            ]
        )
    return pid, thread


async def test_stale_catalog_history_does_not_block_current_stage_and_ai_reads_user_only(stage_http):
    """真实PG/HTTP/lease链路只投影用户自述，旧商品审计不进入模型。"""
    c = stage_http
    await seed_stage_conversation(c)
    response = await c.client.post(c.root + "/generations", json={"client_request_id": str(uuid4()), "kind": "draft"})
    assert response.status_code == 200, response.text
    await finish_job(c, response.json()["id"])
    facts = c.calls[-1]["facts"]
    assert [m["text"] for m in facts["user_messages"]] == ["合成：最近早餐不规律"]
    assert "expired" not in json.dumps(facts) and "旧AI答复" not in json.dumps(facts, ensure_ascii=False)
    saved, _ = await start_stage(c)
    review = await c.client.post(
        c.root + "/generations",
        json={"client_request_id": str(uuid4()), "kind": "review", "stage_id": saved["stage"]["id"]},
    )
    assert review.status_code == 200, review.text
    await finish_job(c, review.json()["id"])


@pytest.mark.parametrize("hidden,failed", [(True, False), (False, True)])
async def test_stage_user_sources_exclude_deleted_projects_and_failed_runs(stage_http, hidden, failed):
    """会话或执行不可用时不把旧原话补回阶段分析。"""
    c = stage_http
    await seed_stage_conversation(c, hidden=hidden, failed=failed)
    response = await c.client.post(c.root + "/generations", json={"client_request_id": str(uuid4()), "kind": "draft"})
    assert response.status_code == 200, response.text
    await finish_job(c, response.json()["id"])
    assert c.calls[-1]["facts"]["user_messages"] == []


async def test_withdrawn_user_source_invalidates_existing_stage_draft(stage_http):
    """来源在生成后删除，已生成的正文仍不可继续展示。"""
    from yuxi.storage.postgres.models_business import Project

    c = stage_http
    pid, _ = await seed_stage_conversation(c)
    response = await c.client.post(c.root + "/generations", json={"client_request_id": str(uuid4()), "kind": "draft"})
    jid = response.json()["id"]
    await finish_job(c, jid)
    async with c.sessions.begin() as session:
        project = await session.get(Project, pid)
        project.status = "deleted"
    result = await c.client.get(c.root + "/generations/" + jid)
    assert result.json()["status"] == "stale" and result.json()["result"] is None


@pytest.mark.parametrize("mismatch", ["member", "actor"])
async def test_stage_user_sources_require_matching_consultation_binding(stage_http, mismatch):
    """每日记录不能借用另一个成员或账号的咨询绑定。"""
    from yuxi.storage.postgres.models_health import HealthConsultation
    from yuxi.storage.postgres.models_business import Conversation

    c = stage_http
    _, thread = await seed_stage_conversation(c)
    async with c.sessions.begin() as session:
        conversation = await session.scalar(select(Conversation).where(Conversation.thread_id == thread))
        binding = await session.get(HealthConsultation, conversation.id)
        if mismatch == "member":
            hid = str(uuid4())
            session.add(HealthMember(id=hid, owner_uid=c.uid, display_name="另一个成员", relationship_label="家人"))
            await session.flush()
            binding.member_id = hid
        else:
            other = await session.get(FamilyMember, c.other)
            binding.actor_uid = other.subject_uid
    response = await c.client.post(c.root + "/generations", json={"client_request_id": str(uuid4()), "kind": "draft"})
    assert response.status_code == 200, response.text
    await finish_job(c, response.json()["id"])
    assert c.calls[-1]["facts"]["user_messages"] == []


async def test_stage_source_access_loss_rejects_old_result(stage_http):
    """成员被移除后，已生成的草案不能继续展示。"""
    c = stage_http
    await seed_stage_conversation(c)
    response = await c.client.post(c.root + "/generations", json={"client_request_id": str(uuid4()), "kind": "draft"})
    jid = response.json()["id"]
    await finish_job(c, jid)
    async with c.sessions.begin() as session:
        member = await session.get(FamilyMember, c.mid)
        member.is_active = False
    result = await c.client.get(c.root + "/generations/" + jid)
    assert result.status_code in (403, 404) and "result" not in result.json()

"""真实HTTP与PostgreSQL验证建档准备的事务、幂等、隔离和恢复。"""
# ruff: noqa: F811 -- pytest 使用共享隔离 fixture。

import asyncio
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import func, select, text

from test.integration.services.test_daily_arrangement_http import source
from test.integration.services.test_health_family_profile_http import (  # noqa: F401
    family_profile_http,
    ensure_live_api_schema,
    cleanup_test_sandboxes,
    cleanup_test_knowledge_resources,
)
from yuxi.services.health_vision_service import health_vision_service
from yuxi.services.task_service import tasker
from yuxi.storage.postgres.models_business import TaskRecord, FamilyMember
from yuxi.storage.postgres.models_health import HealthOnboardingPreparation, HealthMiniappProfileReceipt

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]
POLICY = {"processor": "synthetic-processor", "policy_version": "synthetic-policy"}


@pytest.fixture(autouse=True)
def isolate_delivery(monkeypatch):
    """只隔离外部Redis与模型配置，HTTP、事务和数据库均真实执行。"""

    async def publish(task):
        return None

    async def configuration(db=None):
        return {
            "consultation": {"available": True, "model": "synthetic:model", **POLICY},
            "meal_plan": {"available": True, "model": "synthetic:model", **POLICY},
            "policy_version": POLICY["policy_version"],
        }

    monkeypatch.setattr(tasker, "publish", publish)
    monkeypatch.setattr(health_vision_service, "configuration", configuration)


async def input_for(client, user):
    """创建个人场景，保留真实建档字段校验。"""
    family, _, body, headers = await source(client, user)
    body["members"] = body["members"][:1]
    body["default_diners"] = ["self"]
    body["usage_mode"] = "个人使用"
    body["processing_consents"] = [{"purpose": p, **POLICY} for p in ("consultation", "meal_plan")]
    path = f"/api/family/{family['id']}/onboarding-preparations"
    return family, path, body, headers


async def test_parallel_replay_saves_once_and_current_read_is_pure(family_profile_http):
    """并发重放只有一份收据、准备和Task；重进GET不创建任务。"""
    client, sessions, users = family_profile_http
    family, path, body, headers = await input_for(client, users["self"])
    replies = await asyncio.gather(*(client.post(path, json=body, headers=headers) for _ in range(3)))
    assert all(r.status_code == 200 for r in replies), [r.text for r in replies]
    ids = {r.json()["id"] for r in replies}
    assert len(ids) == 1 and replies[0].json()["profile_saved"]
    for _ in range(2):
        result = await client.get(path + "/current", headers=users["self"])
        assert result.json()["id"] in ids
    async with sessions() as db:
        for model in (HealthOnboardingPreparation, HealthMiniappProfileReceipt, TaskRecord):
            assert await db.scalar(select(func.count()).select_from(model)) == 1
        assert (await db.get(FamilyMember, body["members"][0]["member_id"])).version == 2
    assert (await client.get(path + "/current", headers=users["other"])).status_code == 404
    assert (await client.get(path + "/" + next(iter(ids)), headers=users["other"])).status_code == 404


async def test_task_registration_failure_rolls_back_profile_and_receipt(family_profile_http, monkeypatch):
    """登记失败不可留下已建档却无法恢复的半次提交。"""
    client, sessions, users = family_profile_http
    family, path, body, headers = await input_for(client, users["self"])

    async def fail(*args, **kwargs):
        raise RuntimeError("synthetic registration failure")

    monkeypatch.setattr(tasker, "create_unique_in_session", fail)
    response = await client.post(path, json=body, headers=headers)
    assert response.status_code == 500
    async with sessions() as db:
        assert await db.scalar(select(func.count()).select_from(HealthOnboardingPreparation)) == 0
        assert await db.scalar(select(func.count()).select_from(HealthMiniappProfileReceipt)) == 0
        assert (await db.get(FamilyMember, body["members"][0]["member_id"])).version == 1


async def test_conflicting_payload_cannot_reuse_preparation_key(family_profile_http):
    """同键改资料拒绝，不覆盖已保存结果。"""
    client, sessions, users = family_profile_http
    _, path, body, headers = await input_for(client, users["self"])
    assert (await client.post(path, json=body, headers=headers)).status_code == 200
    body["members"][0]["name"] = "更改合成名称"
    assert (await client.post(path, json=body, headers=headers)).status_code == 409
    async with sessions() as db:
        assert await db.scalar(select(func.count()).select_from(TaskRecord)) == 1


async def test_failed_setup_preserves_profile_and_concurrent_resume_queues_once(family_profile_http, monkeypatch):
    """实际执行后台入口，过期配置失败后保留档案，重试只登记新阶段。"""
    client, sessions, users = family_profile_http
    _, path, body, headers = await input_for(client, users["self"])
    body["processing_consents"] = []
    created = await client.post(path, json=body, headers=headers)
    assert created.status_code == 200, created.text
    pid = created.json()["id"]
    await execute_preparation(pid, sessions, monkeypatch)
    failed = (await client.get(path + "/" + pid, headers=users["self"])).json()
    assert failed["status"] == "failed" and failed["profile_saved"]
    assert failed["error_code"] == "preparation_policy_changed"
    replies = await asyncio.gather(
        *(client.post(path + "/" + pid + "/resume", headers=users["self"]) for _ in range(3))
    )
    assert all(r.status_code == 200 for r in replies), [r.text for r in replies]
    async with sessions() as db:
        assert (await db.get(HealthOnboardingPreparation, pid)).attempt == 1
        assert await db.scalar(select(func.count()).select_from(TaskRecord)) == 2
        assert await db.scalar(select(func.count()).select_from(HealthMiniappProfileReceipt)) == 1


async def test_changed_profile_is_not_exposed_as_ready(family_profile_http):
    """准备期间改档案，旧准备不会越过版本校验。"""
    client, sessions, users = family_profile_http
    family, path, body, headers = await input_for(client, users["self"])
    created = await client.post(path, json=body, headers=headers)
    async with sessions() as db:
        member = await db.get(FamilyMember, body["members"][0]["member_id"])
        member.version += 1
        await db.commit()
    result = await client.get(path + "/current", headers=users["self"])
    assert result.json()["status"] == "stale" and "arrangement" not in result.json()
    assert (await client.post(path + "/" + created.json()["id"] + "/resume", headers=users["self"])).status_code == 409


async def test_preparation_table_creation_is_idempotent(family_profile_http):
    """现有PG结构上重复执行新增表迁移，保存数据不变。"""
    client, sessions, users = family_profile_http
    _, path, body, headers = await input_for(client, users["self"])
    created = await client.post(path, json=body, headers=headers)
    async with sessions() as db:
        connection = await db.connection()
        for _ in range(2):
            await connection.run_sync(lambda conn: HealthOnboardingPreparation.__table__.create(conn, checkfirst=True))
        assert (await db.get(HealthOnboardingPreparation, created.json()["id"])).request_id == body["client_request_id"]


async def test_saved_result_handoff_and_consent_revocation(family_profile_http, monkeypatch):
    """真实创建每日会话、保存来源与完成回读；只隔离配餐生成及专业校验子系统。"""
    from copy import deepcopy
    from yuxi.repositories.skill_repository import SkillRepository
    from yuxi.services import daily_arrangement_service, onboarding_preparation_service
    from yuxi.services.health_daily_service import business_date
    from yuxi.storage.postgres.models_business import Agent
    from yuxi.storage.postgres.models_health import (
        HealthDailyArrangement,
        HealthDailyConversation,
        HealthFamilyProfileLink,
        HealthProcessingConsent,
    )
    from yuxi.utils.datetime_utils import utc_now_naive

    client, sessions, users = family_profile_http
    family, path, body, headers = await input_for(client, users["self"])
    rid = str(uuid4())

    async def available_skill(self, slug):
        return SimpleNamespace(source_type="builtin", enabled=True)

    async def quality_passed(*args, **kwargs):
        return None

    async def daily_start(uid, fid, data):
        async with sessions() as db:
            link = await db.scalar(select(HealthFamilyProfileLink))
            own = await db.get(FamilyMember, body["members"][0]["member_id"])
            db.add(
                HealthDailyArrangement(
                    id=rid,
                    actor_uid=uid,
                    family_id=fid,
                    plan_date=data.date,
                    request_id=str(data.client_request_id),
                    status="generating",
                    version=1,
                    sources={
                        "members": {link.member_id: {"id": own.id, "version": own.version}},
                        "default_diners": [own.id],
                    },
                    selection={"preparation_stage": "analyzing"},
                    snapshot={},
                )
            )
            await db.commit()
        return {"id": rid, "status": "generating"}

    monkeypatch.setattr(SkillRepository, "get_by_slug", available_skill)
    monkeypatch.setattr(daily_arrangement_service, "validate_daily_quality", quality_passed)
    monkeypatch.setattr(daily_arrangement_service, "start_daily_arrangement", daily_start)
    async with sessions() as db:
        db.add(
            Agent(
                slug="health-consultation",
                backend_id="HealthConsultationAgent",
                name="合成准备咨询角色",
                share_config={
                    "version": 2,
                    "read_scope": {"access_level": "global", "department_ids": [], "user_uids": []},
                    "manage_scope": None,
                },
            )
        )
        await db.commit()
    response = await client.post(path, json=body, headers=headers)
    assert response.status_code == 200, response.text
    pid = response.json()["id"]
    await execute_preparation(pid, sessions, monkeypatch)
    progress = (await client.get(path + "/current", headers=users["self"])).json()
    assert progress["status"] == "preparing" and progress["stage"] == "analyzing", progress
    assert "arrangement" not in progress
    day = business_date()
    mid = body["members"][0]["member_id"]
    snapshot = {
        "status": "ready",
        "id": rid,
        "version": 1,
        "date": day.isoformat(),
        "saved": True,
        "validation": {"status": "passed"},
        "procurement": {"checked": True},
        "analysis": {
            "source": "agent",
            "request_id": "synthetic-request",
            "run_id": "synthetic-run",
            "text": "合成已保存三餐说明",
        },
        "meals": [
            {
                "type": meal,
                "detail_ref": meal,
                "members": [{"id": mid, "name": "合成成员"}],
                "dishes": [
                    {
                        "id": "synthetic-recipe",
                        "name": "合成菜品",
                        "recipeVersion": "v1",
                        "ingredients": ["合成食材"],
                        "steps": ["合成做法"],
                    }
                ],
                "memberNotes": [{"memberId": mid, "dishes": [{"grams": 100}]}],
                "nutrition": {"energy": 100},
                "nutritionSource": {"source": "synthetic-only"},
                "purchase": {"package_sn": "synthetic-package", "package_version": 1},
            }
            for meal in ("breakfast", "lunch", "dinner")
        ],
    }
    async with sessions() as db:
        daily = await db.get(HealthDailyArrangement, rid)
        daily.status, daily.snapshot = "ready", snapshot
        await db.commit()
    await onboarding_preparation_service.finish_onboarding_preparations("self", family["id"], day, snapshot)
    for _ in range(2):
        ready = (await client.get(path + "/current", headers=users["self"])).json()
        assert ready["status"] == "ready" and ready["arrangement"]["analysis"]["request_id"] == "synthetic-request", (
            ready
        )
    async with sessions() as db:
        assert await db.scalar(select(func.count()).select_from(HealthDailyConversation)) == 1
        assert await db.scalar(select(func.count()).select_from(TaskRecord)) == 1
        assert (await db.get(HealthOnboardingPreparation, pid)).status == "ready"
        daily = await db.get(HealthDailyArrangement, rid)
        incomplete = deepcopy(snapshot)
        incomplete["meals"].pop()
        daily.snapshot = incomplete
        await db.commit()
    blocked = (await client.get(path + "/current", headers=users["self"])).json()
    assert blocked["status"] == "blocked" and "arrangement" not in blocked
    async with sessions() as db:
        daily = await db.get(HealthDailyArrangement, rid)
        daily.snapshot = snapshot
        consent = await db.scalar(
            select(HealthProcessingConsent).where(HealthProcessingConsent.purpose == "consultation")
        )
        consent.revoked_at = utc_now_naive()
        await db.commit()
    revoked = (await client.get(path + "/current", headers=users["self"])).json()
    assert revoked["status"] == "blocked" and "arrangement" not in revoked


async def execute_preparation(pid, sessions, monkeypatch):
    """执行正式Task入口、真实PG claim/lease/checkpoint/终态，不替换租约回调。"""
    from yuxi.services import task_service, health_vision_tasks

    async def no_external_delivery(*args, **kwargs):
        return None

    monkeypatch.setattr(task_service, "publish_pending_tasks", no_external_delivery)
    monkeypatch.setattr(health_vision_tasks, "cleanup_health_result_objects", no_external_delivery)
    async with sessions() as db:
        prep = await db.get(HealthOnboardingPreparation, pid)
        task_id = prep.task_id
    await task_service.process_task({"worker_id": "synthetic-onboarding-lease-test"}, task_id)
    async with sessions() as db:
        task = await db.get(TaskRecord, task_id)
        assert task.status == "success", task.error
        assert task.attempt_count == 1 and task.worker_id is None


@pytest.mark.parametrize("operation", ["resume", "finish"])
async def test_family_lock_precedes_preparation_locks(family_profile_http, operation):
    """另一事务持有家庭锁时，恢复与完成不能先占准备锁形成反向等待。"""
    from yuxi.services import onboarding_preparation_service as service
    from yuxi.services.family_service import FamilyService
    from yuxi.services.health_daily_service import business_date

    client, sessions, users = family_profile_http
    family, path, body, headers = await input_for(client, users["self"])
    created = await client.post(path, json=body, headers=headers)
    assert created.status_code == 200, created.text
    pid, fid = created.json()["id"], family["id"]
    async with sessions.begin() as db:
        row = await db.get(HealthOnboardingPreparation, pid)
        row.status = "waiting" if operation == "finish" else "pending"
    pending = None
    try:
        async with sessions.begin() as holder:
            await FamilyService(holder, "self").context(fid)
            holder_pid = await holder.scalar(text("SELECT pg_backend_pid()"))
            pending = asyncio.create_task(
                client.post(path + "/" + pid + "/resume", headers=users["self"])
                if operation == "resume"
                else service.finish_onboarding_preparations("self", fid, business_date(), {"id": "synthetic"})
            )
            async with sessions() as observer:
                for _ in range(150):
                    await observer.execute(text("SELECT pg_stat_clear_snapshot()"))
                    waiting = await observer.scalar(
                        text("SELECT EXISTS (SELECT 1 FROM pg_stat_activity WHERE :pid = ANY(pg_blocking_pids(pid)))"),
                        {"pid": holder_pid},
                    )
                    if waiting:
                        break
                    await asyncio.sleep(0.02)
                assert waiting, "必须实际到达数据库锁等待"
            await holder.execute(text("SET LOCAL lock_timeout = '500ms'"))
            if operation == "resume":
                await service.lock_preparation(holder, "self", fid)
            else:
                await holder.get(HealthOnboardingPreparation, pid, with_for_update=True)
        result = await asyncio.wait_for(pending, 10)
        if operation == "resume":
            assert result.status_code == 200, result.text
        async with sessions() as db:
            assert await db.scalar(select(func.count()).select_from(TaskRecord)) == 1
            assert await db.scalar(select(func.count()).select_from(HealthMiniappProfileReceipt)) == 1
    finally:
        if pending is not None:
            await asyncio.gather(pending, return_exceptions=True)


async def test_preparation_binding_serializes_with_consent_revocation(family_profile_http, monkeypatch):
    """后台用途绑定持有同意行锁，撤回只能在绑定提交后生效且不会被恢复。"""
    from sqlalchemy.exc import DBAPIError
    from yuxi.services import miniapp_planning_source
    from yuxi.storage.postgres.models_health import HealthProcessingConsent
    from yuxi.utils.datetime_utils import utc_now_naive

    client, sessions, users = family_profile_http
    source_family, path, body, headers = await input_for(client, users["self"])
    response = await client.post(path, json=body, headers=headers)
    assert response.status_code == 200, response.text
    original = miniapp_planning_source.bind_submitted_profile
    from yuxi.services.family_service import FamilyService

    async with sessions.begin() as db:
        service = FamilyService(db, "self")
        family, _ = await service.context(source_family["id"])
        members = [member for member in await service.repo.members(family.id) if member.subject_uid == "self"]
        for purpose in ("consultation", "meal_plan"):
            await original(db, "self", family, members, {"purpose": purpose, **POLICY})
    observed = []

    async def binding(session, uid, family, members, consent):
        """在真实事务检查完成后交错另一事务的撤回写入。"""
        if consent["purpose"] == "consultation":
            hid = await session.scalar(
                select(HealthProcessingConsent.member_id).where(HealthProcessingConsent.purpose == "consultation")
            )
            async with sessions() as other:
                await other.execute(text("SET LOCAL lock_timeout = '300ms'"))
                with pytest.raises(DBAPIError, match="lock timeout"):
                    await other.execute(
                        text(
                            "UPDATE health_processing_consent SET revoked_at=NOW() "
                            "WHERE member_id=:mid AND actor_uid=:uid AND purpose='consultation'"
                        ),
                        {"mid": hid, "uid": uid},
                    )
                await other.rollback()
            observed.append(hid)
        return await original(session, uid, family, members, consent)

    monkeypatch.setattr(miniapp_planning_source, "bind_submitted_profile", binding)
    await execute_preparation(response.json()["id"], sessions, monkeypatch)
    assert len(observed) == 1
    async with sessions.begin() as db:
        consent = await db.get(HealthProcessingConsent, (observed[0], "self", "consultation"))
        consent.revoked_at = utc_now_naive()
    async with sessions() as db:
        assert (await db.get(HealthProcessingConsent, (observed[0], "self", "consultation"))).revoked_at is not None


async def test_single_day_context_coexists_with_preparation_schema(family_profile_http, monkeypatch):
    """在同一 health 32 与真实 TCP 中验证主线单日入口权限、规则撤回和无计划写入。"""
    from test.integration.services.test_health_initial_plan_context_http import (
        test_initial_context_reads_current_sources_without_creating_plan as verify_context,
    )

    client, _, users = family_profile_http
    monkeypatch.setenv("HEALTH_DAILY_RULE_CODE", "synthetic-integration-" + uuid4().hex)
    await verify_context((client, [{"uid": uid, "headers": users[uid]} for uid in ("self", "other", "admin")]))

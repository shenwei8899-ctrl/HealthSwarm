"""独立槽位家庭页面合成资料、只读PG事实和明确收敛清理。"""

import asyncio
import json
import os
import shutil
from copy import deepcopy
from uuid import uuid4

from sqlalchemy import delete, func, or_, select, text

from test.e2e.test_health_consultation_e2e import drain_requests
from test.integration.services.test_health_family_safe_plan_http import setup_safe_family
from test.integration.services.test_health_quality_http import action
from test.integration.services.test_health_vision_http import ROOT, create_member, health_http
from test.support.health_family_planner_replay_server import MODEL
from yuxi.config import get_user_data_dir
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_business import (
    AgentRun,
    AgentRunAttempt,
    AgentRunRequest,
    Message,
    OperationLog,
    User,
)
from yuxi.storage.postgres.models_health import (
    DietLog,
    FamilyMember,
    HealthFamilyPlannerPreview,
    HealthMealPlan,
    HealthMealPlanAdoption,
    HealthMealPlanRevision,
    HealthMemoryFact,
    HealthProfessionalReview,
    HealthQualityCheck,
)
from yuxi.storage.redis import sync_redis_client
from yuxi.workspace.paths import global_user_data_dir


async def family_ui_fixture(*, replay_port=8778, third_only=False):
    """创建普通合成用户与四份独立计划，先检查实际DB再创建账号。"""
    assert os.getenv("HEALTH_CONSULTATION_E2E_ISOLATED") == "true"
    pg_manager.initialize()
    async with pg_manager.get_async_session_context() as session:
        assert await session.scalar(text("SELECT current_database()")) == "health_consultation_e2e"
        assert not await session.scalar(
            select(AgentRun.id).where(
                or_(
                    AgentRun.status.not_in(("completed", "failed", "cancelled", "interrupted")),
                    AgentRun.worker_id.is_not(None),
                    AgentRun.lease_expires_at.is_not(None),
                    AgentRun.runtime_cleanup_pending.is_(True),
                )
            )
        )
    health_gen = health_http.__wrapped__()
    client, users = await anext(health_gen)
    state = {"client": client, "users": users, "provider": None, "plans": {}}
    try:
        assert str(client.base_url).rstrip("/") == "http://localhost:5050"
        original = await client.get(f"{ROOT}/configuration", headers=users[2]["headers"])
        assert original.status_code == 200 and not original.json()["policy_version"]
        assert not any(
            original.json()[purpose]["available"]
            for purpose in ("report", "meal", "consultation", "meal_plan", "diet_analysis", "quality_review")
        )
        provider = "family-ui-replay-" + uuid4().hex[:12]
        created = await client.post(
            "/api/system/model-providers",
            headers=users[2]["headers"],
            json={
                "provider_id": provider,
                "display_name": "Synthetic family UI only",
                "provider_type": "openai",
                "base_url": f"http://api:{replay_port}/v1",
                "api_key": "synthetic-family-planner-key",
                "capabilities": ["chat"],
                "enabled_models": [{"id": MODEL, "display_name": "synthetic", "type": "chat", "source": "manual"}],
                "is_enabled": True,
            },
        )
        assert created.status_code == 200
        state["provider"] = provider
        configured = await client.put(
            f"{ROOT}/configuration",
            headers=users[2]["headers"],
            json={
                "meal_plan_model": f"{provider}:{MODEL}",
                "policy_version": "synthetic-family-ui-v1",
                "cloud_processing_reviewed": True,
            },
        )
        assert configured.status_code == 200 and configured.json()["meal_plan"]["available"]
        current = await setup_safe_family(client, users, energies=(110,))
        state["current"] = current
        state["plans"]["third" if third_only else "swap"] = current["plan"]
        additional = (
            []
            if third_only
            else [("regeneration", "2026-10-10"), ("participation", "2026-10-11"), ("revocation", "2026-10-12")]
        )
        for mode, day in additional:
            spec = {**deepcopy(current["spec"]), "plan_date": day}
            preview = await client.post(
                f"{ROOT}/members/{current['member']}/family-meal-plan-previews", headers=users[0]["headers"], json=spec
            )
            assert preview.status_code == 201
            key = str(uuid4())
            saved = await client.post(
                f"{ROOT}/members/{current['member']}/meal-plans",
                headers={**users[0]["headers"], "Idempotency-Key": key},
                json={"client_request_id": key, "preview_id": preview.json()["preview_id"]},
            )
            assert saved.status_code == 201 and saved.json()["nutrition"]["totals"]["energy_kcal"] == "360.00"
            state["plans"][mode] = saved.json()["plan_id"]
        strict = {
            **deepcopy(current["rules"]),
            "rule_code": "synthetic-family-ui-strict-" + uuid4().hex,
            "version": 1,
            "source_version": "v1",
        }
        strict["payload"]["personal_targets"][0]["nutrient_ranges"]["energy_kcal"].update(
            minimum_per_energy="1.1", maximum_per_energy="1.1"
        )
        imported = await client.post(f"{ROOT}/approved-quality-rules", headers=users[2]["headers"], json=strict)
        assert imported.status_code == 201
        state["strict_rule"] = strict
        state["approved"] = {}
        for mode, plan_id in state["plans"].items():
            check = await client.post(
                f"{ROOT}/meal-plans/{plan_id}/quality-checks",
                headers=users[0]["headers"],
                json={"client_request_id": str(uuid4()), "version": 1, "rule_code": current["rules"]["rule_code"]},
            )
            assert check.status_code == 201 and check.json()["safety_check"]["status"] == "passed"
            read = await client.get(f"{ROOT}/quality-checks/{check.json()['check_id']}", headers=users[0]["headers"])
            review = read.json()["review"]["review_id"]
            await action(client, users[0]["headers"], review, "submit", 1)
            await action(client, users[1]["headers"], review, "approve", 2)
            adopted = await client.post(
                f"{ROOT}/meal-plans/{plan_id}/adopt",
                headers=users[0]["headers"],
                json={
                    "client_request_id": str(uuid4()),
                    "version": 1,
                    "review_id": review,
                    "profile_versions": {current["member"]: 2, current["second"]: 1},
                },
            )
            assert adopted.status_code == 201
            state["approved"][mode] = {"review_id": review, "adoption_id": adopted.json()["adoption_id"]}
        async with pg_manager.get_async_session_context() as session:
            for member_id, name in (
                (current["member"], "家庭配餐合成主成员"),
                (current["second"], "家庭配餐合成第二成员"),
            ):
                row = await session.get(FamilyMember, member_id)
                row.display_name = name
        state["member_ids"] = [current["member"], current["second"]]
        if third_only:
            third = await create_member(client, users[0]["headers"])
            for actor, scopes in (
                (users[2]["uid"], ["profile_edit"]),
                (users[1]["uid"], ["profile_view", "professional_review"]),
            ):
                response = await client.put(
                    f"{ROOT}/members/{third}/grants",
                    headers=users[0]["headers"],
                    json={"actor_uid": actor, "scopes": scopes},
                )
                assert response.status_code == 200
            profile = {**deepcopy(current["profile"]), "version": 1, "source_version": "v1"}
            imported = await client.post(
                f"{ROOT}/members/{third}/external-profile-versions", headers=users[2]["headers"], json=profile
            )
            assert imported.status_code == 201
            async with pg_manager.get_async_session_context() as session:
                row = await session.get(FamilyMember, third)
                row.display_name = "家庭配餐合成拟加入成员"
            state["third_member"] = third
            state["member_ids"].append(third)
        state["consent"] = {
            "purpose": "meal_plan",
            "accepted": True,
            "processor": configured.json()["meal_plan"]["processor"],
            "policy_version": configured.json()["policy_version"],
        }
        state["before"] = await family_ui_facts(state)
        yield state
    finally:
        async with pg_manager.get_async_session_context() as session:
            requests = list(
                (
                    await session.scalars(
                        select(AgentRunRequest.request_id).where(AgentRunRequest.uid == users[0]["uid"])
                    )
                ).all()
            )
        await drain_requests(client, users[0]["headers"], requests)
        await require_family_ui_settled(users)
        async with pg_manager.get_async_session_context() as session:
            run_ids = list(
                (await session.scalars(select(AgentRun.id).where(AgentRun.uid.in_([u["uid"] for u in users])))).all()
            )
        if state["provider"]:
            reset = await client.put(f"{ROOT}/configuration", headers=users[2]["headers"], json={})
            assert reset.status_code == 200 and not reset.json()["policy_version"]
            removed = await client.delete(
                f"/api/system/model-providers/{state['provider']}", headers=users[2]["headers"]
            )
            assert removed.status_code == 200
        async with pg_manager.get_async_session_context() as session:
            await session.execute(
                delete(OperationLog).where(
                    OperationLog.user_id.in_(select(User.id).where(User.uid.in_([u["uid"] for u in users])))
                )
            )
        root = get_user_data_dir().resolve()
        for user in users:
            target = global_user_data_dir(user["uid"])
            target.resolve().relative_to(root)
            assert target.name == user["uid"] and target.name.startswith("pytest_health_")
            if target.exists():
                shutil.rmtree(target)
        await health_gen.aclose()
        pg_manager.initialize()
        try:
            async with pg_manager.get_async_session_context() as session:
                assert await session.scalar(text("SELECT current_database()")) == "health_consultation_e2e"
                assert not await session.scalar(select(AgentRun.id).where(AgentRun.id.in_(run_ids)))
            with sync_redis_client() as redis:
                keys = ["run:events:" + run_id for run_id in run_ids]
                assert all(redis.type(key) in {"none", "stream"} for key in keys)
                if keys:
                    redis.delete(*keys)
            with sync_redis_client() as independent:
                assert not any(independent.exists(key) for key in keys)
        finally:
            await pg_manager.close()


async def require_family_ui_settled(users):
    """终态以外还须明确释放执行Owner、lease和runtime清理。"""
    async with asyncio.timeout(45):
        while True:
            async with pg_manager.get_async_session_context() as session:
                runs = list(
                    (await session.scalars(select(AgentRun).where(AgentRun.uid.in_([u["uid"] for u in users])))).all()
                )
                if all(
                    r.status in {"completed", "failed", "cancelled", "interrupted"}
                    and r.worker_id is None
                    and r.lease_expires_at is None
                    and not r.runtime_cleanup_pending
                    for r in runs
                ):
                    return
            await asyncio.sleep(0.1)


async def family_ui_facts(state):
    """重新读取计划完整事实与当前Run身份，使用独立PG连接作为oracle。"""
    current, users = state["current"], state["users"]
    async with pg_manager.get_async_session_context() as session:
        result = {"plans": {}, "runs": []}
        for mode, plan_id in state["plans"].items():
            plan = await session.get(HealthMealPlan, plan_id)
            revisions = list(
                (
                    await session.scalars(
                        select(HealthMealPlanRevision)
                        .where(HealthMealPlanRevision.plan_id == plan_id)
                        .order_by(HealthMealPlanRevision.version)
                    )
                ).all()
            )
            checks = list(
                (
                    await session.scalars(
                        select(HealthQualityCheck)
                        .where(HealthQualityCheck.plan_id == plan_id)
                        .order_by(HealthQualityCheck.id)
                    )
                ).all()
            )
            reviews = list(
                (
                    await session.scalars(
                        select(HealthProfessionalReview)
                        .where(HealthProfessionalReview.check_id.in_([c.id for c in checks]))
                        .order_by(HealthProfessionalReview.id)
                    )
                ).all()
            )
            adoptions = list(
                (
                    await session.scalars(
                        select(HealthMealPlanAdoption)
                        .where(HealthMealPlanAdoption.plan_id == plan_id)
                        .order_by(HealthMealPlanAdoption.id)
                    )
                ).all()
            )
            result["plans"][mode] = {
                "plan_id": plan.id,
                "version": plan.version,
                "spec": deepcopy(plan.spec),
                "snapshot": deepcopy(plan.snapshot),
                "revisions": [
                    {"id": r.id, "version": r.version, "spec": deepcopy(r.spec), "snapshot": deepcopy(r.snapshot)}
                    for r in revisions
                ],
                "checks": [
                    {"check_id": c.id, "plan_version": c.plan_version, "snapshot": deepcopy(c.snapshot)} for c in checks
                ],
                "reviews": [
                    {"review_id": r.id, "check_id": r.check_id, "version": r.version, "status": r.status}
                    for r in reviews
                ],
                "adoptions": [
                    {"adoption_id": a.id, "version": a.version, "status": a.status, "snapshot": deepcopy(a.snapshot)}
                    for a in adoptions
                ],
            }
        runs = list(
            (
                await session.scalars(
                    select(AgentRun).where(AgentRun.uid == users[0]["uid"]).order_by(AgentRun.created_at)
                )
            ).all()
        )
        for run in runs:
            attempts = list(
                (await session.scalars(select(AgentRunAttempt).where(AgentRunAttempt.run_id == run.id))).all()
            )
            message = await session.get(Message, run.output_message_id) if run.output_message_id else None
            previews = list(
                (
                    await session.scalars(
                        select(HealthFamilyPlannerPreview).where(HealthFamilyPlannerPreview.run_id == run.id)
                    )
                ).all()
            )
            result["runs"].append(
                {
                    "run_id": run.id,
                    "request_id": run.request_id,
                    "thread_id": run.conversation_thread_id,
                    "status": run.status,
                    "owner_released": run.worker_id is None,
                    "lease_released": run.lease_expires_at is None,
                    "runtime_cleanup_pending": run.runtime_cleanup_pending,
                    "manifest": deepcopy(run.manifest),
                    "output_message_id": run.output_message_id,
                    "message": {
                        "run_id": message.run_id,
                        "request_id": message.request_id,
                        "content": json.loads(message.content),
                    }
                    if message
                    else None,
                    "attempts": [
                        {"attempt_id": a.id, "outcome": a.outcome, "finished": a.finished_at is not None}
                        for a in attempts
                    ],
                    "previews": [
                        {
                            "preview_id": p.id,
                            "run_id": p.run_id,
                            "actor_uid": p.actor_uid,
                            "operation": p.operation,
                            "parameters": deepcopy(p.parameters),
                            "snapshot": deepcopy(p.snapshot),
                        }
                        for p in previews
                    ],
                }
            )
        members = state.get("member_ids", [current["member"], current["second"]])
        result["actual_diet_logs"] = int(
            await session.scalar(select(func.count()).select_from(DietLog).where(DietLog.member_id.in_(members))) or 0
        )
        result["memory_facts"] = int(
            await session.scalar(
                select(func.count()).select_from(HealthMemoryFact).where(HealthMemoryFact.member_id.in_(members))
            )
            or 0
        )
        result["owned"] = {
            "user_uids": [u["uid"] for u in users],
            "user_ids": list(
                (await session.scalars(select(User.id).where(User.uid.in_([u["uid"] for u in users])))).all()
            ),
            "member_ids": members,
            "plans": list(state["plans"].values()),
            "provider_ids": [state["provider"]],
            "run_ids": [r.id for r in runs],
            "thread_ids": list({r.conversation_thread_id for r in runs}),
        }
        return result

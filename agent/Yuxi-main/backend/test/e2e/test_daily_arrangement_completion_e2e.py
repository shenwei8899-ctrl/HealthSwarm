"""真实建档、后台三餐、单餐调整与明确重试的隔离闭环。"""

import asyncio
from copy import deepcopy
import os
from uuid import uuid4

import pytest
from sqlalchemy import delete, func, select

from test.e2e.test_daily_arrangement_recovery_e2e import recovery_runtime  # noqa: F401
from test.e2e.test_health_consultation_e2e import isolated_health, wait_until  # noqa: F401
from test.integration.services.test_health_initial_planner_http import initial_runtime  # noqa: F401
from test.integration.services.test_health_vision_http import ROOT, health_http  # noqa: F401
from test.integration.services.test_daily_arrangement_http import source
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_business import (
    AgentRun,
    FamilyArchive,
    FamilyAudit,
    FamilyMember,
    FamilyProfileRevision,
    TaskRecord,
)
from yuxi.storage.postgres.models_health import (
    HealthDailyArrangement,
    HealthFamilyProfileLink,
    HealthMiniappProfileReceipt,
    HealthMealPlan,
    HealthRecipeCommerceSource,
    HealthRuleSnapshot,
)

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.slow,
    pytest.mark.asyncio,
    pytest.mark.skipif(os.getenv("HEALTH_DAILY_RECOVERY_E2E") != "true", reason="仅在专用健康隔离槽位运行"),
]


@pytest.mark.parametrize("operation", ["change_meal", "retry_policy", "retry_transient"])
async def test_onboarding_background_three_meals_and_explicit_retry(recovery_runtime, operation):  # noqa: F811
    """真实HTTP/Worker生成后校验PG；重试从明确登记的失败检查点开始。"""
    client, users, current, consent, gate, _, requests, _, _, stop_workers = recovery_runtime
    owner, admin = users[0]["headers"], users[2]["headers"]
    family, profile_path, data, keyed = await source(client, owner)
    uid, fid = users[0]["uid"], family["id"]
    root = f"/api/family/{fid}/daily-arrangements"
    path = root + "/2026-10-22"
    gate.set()
    try:
        rules = deepcopy(current["rules"])
        rules["rule_code"] = "synthetic-daily-fullchain"
        async with pg_manager.get_async_session_context() as db:
            rules["version"] = 1 + (
                await db.scalar(
                    select(func.max(HealthRuleSnapshot.version)).where(
                        HealthRuleSnapshot.rule_code == rules["rule_code"]
                    )
                )
                or 0
            )
        payload = rules["payload"]
        payload["miniapp_profile_codes"] = {"population_age_ranges": {"18:130": "synthetic_adult"}}
        payload["daily_bounds"]["energy_kcal"] = {"minimum": "300", "maximum": "360"}
        for meal, shares in payload["meal_target_shares"].items():
            payload["meal_target_shares"][meal] = {key: "0.34" if meal == "breakfast" else "0.33" for key in shares}
        for meal in payload["meal_generation"]["profile_menus"][0]["meals"]:
            meal["dishes"][0]["grams_options"] = ["100"]
        response = await client.post(f"{ROOT}/approved-quality-rules", headers=admin, json=rules)
        assert response.status_code == 201, response.text
        response = await client.get(f"{ROOT}/recipe-commerce-sources/{current['recipe']}", headers=admin)
        assert response.status_code == 200, response.text
        mapping = response.json()
        response = await client.put(
            f"{ROOT}/recipe-commerce-sources/{current['recipe']}",
            headers=admin,
            json={
                "recipe_hash": mapping["recipe_hash"],
                "source_ref": "synthetic-fullchain",
                "steps": ["合成做法，仅测试"],
                "ingredient_codes": {item["food_id"]: "food-A" for item in mapping["ingredients"]},
            },
        )
        assert response.status_code == 200, response.text
        data["members"][1]["birth_date"] = "1992-01-01"
        data["members"][1]["dietary"] = deepcopy(data["members"][0]["dietary"])
        data["analysis_consent"] = {key: consent[key] for key in ("processor", "policy_version")}
        response = await client.post(profile_path, headers=keyed, json=data)
        assert response.status_code == 200, response.text
        profile = (await client.get(profile_path, headers=owner)).json()
        assert profile["onboarded"] and len(profile["defaultDiners"]) == 2
        request_id = str(uuid4())
        response = await client.post(
            root,
            headers={**owner, "Idempotency-Key": request_id},
            json={"client_request_id": request_id, "date": "2026-10-22"},
        )
        assert response.status_code == 200, response.text
        rid = response.json()["id"]

        async def state():
            """仅从持久化事实观察，不靠页面推动执行。"""
            async with pg_manager.get_async_session_context() as db:
                row = await db.get(HealthDailyArrangement, rid)
                tasks = list(
                    (
                        await db.scalars(
                            select(TaskRecord).where(TaskRecord.payload["arrangement_id"].as_string() == rid)
                        )
                    ).all()
                )
                return row, tasks

        async def terminal():
            """Worker及业务均收敛后才验收。"""
            result = await wait_until(
                state,
                lambda pair: pair[0].status != "generating" and all(t.status in {"success", "failed"} for t in pair[1]),
                timeout=90,
            )
            assert result[0].status == "ready", [(t.status, t.error) for t in result[1]]
            return result[0]

        row = await terminal()
        assert row.version == 1 and row.snapshot["saved"] is True
        assert len(row.snapshot["meals"]) == 3 and all(m["dishes"] for m in row.snapshot["meals"])
        before, original_run = deepcopy(row.snapshot), row.snapshot["analysis"]["run_id"]
        purchases = deepcopy(row.selection["purchase_payloads"])
        assert (await client.get(path, headers=users[1]["headers"])).status_code == 404
        if operation == "change_meal":
            request_id = str(uuid4())
            response = await client.post(
                path + "/members",
                headers={**owner, "Idempotency-Key": request_id},
                json={
                    "client_request_id": request_id,
                    "version": 1,
                    "meal": "lunch",
                    "member_ids": profile["defaultDiners"][:1],
                },
            )
            assert response.status_code == 200, response.text
            row = await terminal()
            assert row.id == rid and row.version == 2
            lunch = next(m for m in row.snapshot["meals"] if m["type"] == "lunch")
            assert {member["id"] for member in lunch["members"]} == set(profile["defaultDiners"][:1])
            assert lunch["nutrition"]["kcal"] == 110
            assert len(lunch["memberNotes"]) == 1 and lunch["memberNotes"][0]["dishes"][0]["grams"] == 100
            async with pg_manager.get_async_session_context() as db:
                plan = await db.get(HealthMealPlan, row.snapshot["plan_id"])
                plan_lunch = next(meal for meal in plan.spec["meals"] if meal["meal_type"] == "lunch")
                assert plan_lunch["participant_ids"] == [lunch["members"][0]["healthMemberId"]]
                assert [(p["member_id"], p["grams"]) for p in plan_lunch["dishes"][0]["member_portions"]] == [
                    (lunch["members"][0]["healthMemberId"], "100")
                ]
            for meal in ("breakfast", "dinner"):
                assert next(m for m in row.snapshot["meals"] if m["type"] == meal) == next(
                    m for m in before["meals"] if m["type"] == meal
                )
                assert row.selection["purchase_payloads"][meal] == purchases[meal]
            assert row.selection["purchase_payloads"]["lunch"]["agent_task_id"] != purchases["lunch"]["agent_task_id"]
        else:
            # 精确构造外部故障后的持久检查点；前置Run、档案和回执均来自真实链路。
            async with pg_manager.get_async_session_context() as db:
                failed = await db.get(HealthDailyArrangement, rid)
                failed.status = "failed"
                failed.snapshot = {}
                failed.selection = {**failed.selection, "failure_message": "合成外部暂时故障"}
            if operation == "retry_policy":
                config = (await client.get(f"{ROOT}/configuration", headers=admin)).json()
                response = await client.put(
                    f"{ROOT}/configuration",
                    headers=admin,
                    json={
                        "consultation_model": config["consultation"]["model"],
                        "meal_plan_model": config["meal_plan"]["model"],
                        "policy_version": "synthetic-local-only-v2",
                        "cloud_processing_reviewed": True,
                    },
                )
                assert response.status_code == 200, response.text
                denied = await client.post(path + "/resume?retry_failed=true", headers=owner)
                assert denied.status_code == 403, denied.text
                assert (await state())[0].status == "failed"
                for mid in row.selection["initial"]["profile_versions"]:
                    response = await client.post(
                        f"{ROOT}/members/{mid}/processing-consents",
                        headers=owner,
                        json={**consent, "policy_version": "synthetic-local-only-v2"},
                    )
                    assert response.status_code == 200, response.text
            responses = await asyncio.gather(
                *(client.post(path + "/resume?retry_failed=true", headers=owner) for _ in range(2))
            )
            assert all(r.status_code == 200 for r in responses), [r.text for r in responses]
            row = await terminal()
            assert row.id == rid and row.version == 1
            assert row.selection.get("attempt", 0) == (1 if operation == "retry_policy" else 0)
            assert (row.snapshot["analysis"]["run_id"] == original_run) == (operation == "retry_transient")
            for meal in ("breakfast", "lunch", "dinner"):
                package = row.selection["purchase_payloads"][meal]
                assert (package["agent_task_id"] == purchases[meal]["agent_task_id"]) == (
                    operation == "retry_transient"
                )
                assert package["menu_version_ref"] == row.snapshot["plan_id"] + ":" + str(row.snapshot["plan_version"])
        async with pg_manager.get_async_session_context() as db:
            runs = list((await db.scalars(select(AgentRun).where(AgentRun.uid == uid))).all())
            assert len(runs) == (1 if operation == "retry_transient" else 2)
            assert all(run.status == "completed" for run in runs)
        assert len((await state())[1]) == 2
        assert "UNEXPECTED_POST" not in requests
        assert (await client.get(path, headers=owner)).json()["version"] == row.version
    finally:
        gate.set()
        await stop_workers()
        async with pg_manager.get_async_session_context() as db:
            await db.execute(delete(TaskRecord).where(TaskRecord.payload["family_id"].as_string() == fid))
            await db.execute(delete(HealthDailyArrangement).where(HealthDailyArrangement.family_id == fid))
            await db.execute(delete(HealthMiniappProfileReceipt).where(HealthMiniappProfileReceipt.family_id == fid))
            await db.execute(delete(HealthFamilyProfileLink).where(HealthFamilyProfileLink.family_id == fid))
            await db.execute(
                delete(HealthRecipeCommerceSource).where(
                    HealthRecipeCommerceSource.recipe_version_id == current["recipe"]
                )
            )
            await db.execute(delete(FamilyAudit).where(FamilyAudit.family_id == fid))
            await db.execute(
                delete(FamilyProfileRevision).where(
                    FamilyProfileRevision.member_id.in_(select(FamilyMember.id).where(FamilyMember.family_id == fid))
                )
            )
            await db.execute(delete(FamilyMember).where(FamilyMember.family_id == fid))
            await db.execute(delete(FamilyArchive).where(FamilyArchive.id == fid))

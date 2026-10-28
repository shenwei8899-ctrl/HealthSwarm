"""独立PostgreSQL与真实HTTP验证建档持久化和每日入口隔离。"""

import asyncio
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from test.integration.services.test_health_family_profile_http import family_profile_http  # noqa: F401
from test.integration.services.test_health_family_profile_http import ensure_live_api_schema  # noqa: F401
from test.integration.services.test_health_family_profile_http import cleanup_test_sandboxes  # noqa: F401
from test.integration.services.test_health_family_profile_http import cleanup_test_knowledge_resources  # noqa: F401

from yuxi.storage.postgres.models_business import FamilyMember
from yuxi.storage.postgres.models_health import (
    HealthMiniappProfileReceipt,
    HealthFamilyProfileLink,
    HealthGrant,
    HealthProfileSnapshot,
    HealthDailyArrangement,
)

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_late_stock_failure_preserves_committed_winner(family_profile_http, monkeypatch):  # noqa: F811
    """真实 PG 并发赢家已完成后，旧库存失败不能递增 attempt 或丢失回执。"""
    from copy import deepcopy
    from datetime import date
    from unittest.mock import AsyncMock
    from yuxi.services import daily_arrangement_service as service

    client, sessions, users = family_profile_http
    family, _, _, _ = await source(client, users["self"])
    rid, preview = str(uuid4()), str(uuid4())
    day = date(2099, 1, 1)
    receipt = {"status": "ready", "id": rid, "version": 1, "date": day.isoformat(), "meals": []}
    selection = {
        "initial": {"profile_versions": {str(uuid4()): 1}},
        "attempt": 0,
        "agent_result": {"payload": {"preview_id": preview}, "task_key": str(uuid4()), "run_id": str(uuid4())},
    }
    async with sessions.begin() as db:
        db.add(
            HealthDailyArrangement(
                id=rid,
                actor_uid="self",
                family_id=family["id"],
                plan_date=day,
                version=1,
                status="generating",
                request_id=str(uuid4()),
                selection=deepcopy(selection),
                sources={"members": {}},
                snapshot=deepcopy(receipt),
            )
        )
    monkeypatch.setattr(service, "authorize_daily_agent_result", AsyncMock())
    monkeypatch.setattr(service, "save_initial_plan", AsyncMock(return_value={}))
    monkeypatch.setattr(service, "meal_views", lambda *_: [{"type": "breakfast"}])
    monkeypatch.setattr(service, "ingredient_requirements", lambda *_: [])
    monkeypatch.setattr(service, "match_meal_requirements", lambda *_: None)

    async def late_catalog():
        """在落后 Worker 继续前提交另一个 Worker 的完成事实。"""
        async with sessions.begin() as db:
            row = await db.get(HealthDailyArrangement, rid)
            row.status = "ready"
        return {"version": "synthetic-catalog", "items": []}

    monkeypatch.setattr(service, "current_catalog", late_catalog)
    assert await service.resume_daily_arrangement("self", family["id"], day) == receipt
    async with sessions() as db:
        row = await db.get(HealthDailyArrangement, rid)
        assert row.status == "ready" and row.selection == selection and row.snapshot == receipt


async def test_revision_reads_published_snapshot_and_background_resume_deduplicates(family_profile_http, monkeypatch):  # noqa: F811
    """真实PG中保留原版本；GET不创建Task，并发恢复仅登记一个后台任务。"""
    from datetime import date
    from yuxi.services.task_service import tasker
    from yuxi.storage.postgres.models_business import TaskRecord

    async def quality_owner(db, uid, snapshot):
        # 本用例验证发布快照与后台去重，专业来源失效另有真实 HTTP/PG 回归。
        return None

    from yuxi.services import daily_arrangement_service as service

    monkeypatch.setattr(service, "validate_daily_quality", quality_owner)
    client, sessions, users = family_profile_http
    family, _, _, _ = await source(client, users["self"])
    saved = {
        "status": "ready",
        "id": str(uuid4()),
        "version": 1,
        "date": "2026-10-19",
        "saved": True,
        "analysis": {"text": "合成已保存说明"},
        "meals": [{"type": "lunch", "dishes": ["合成菜"]}],
    }
    async with sessions() as db:
        db.add(
            HealthDailyArrangement(
                id=saved["id"],
                actor_uid="self",
                family_id=family["id"],
                plan_date=date(2026, 10, 19),
                version=2,
                status="generating",
                request_id=str(uuid4()),
                selection={"initial": {}, "published_sources": {"members": {}}},
                sources={"members": {}},
                snapshot=saved,
            )
        )
        await db.commit()
    path = f"/api/family/{family['id']}/daily-arrangements/2026-10-19"
    response = await client.get(path, headers=users["self"])
    assert response.status_code == 200, response.text
    assert response.json()["version"] == 1 and response.json()["update"]["version"] == 2
    assert (await client.get(path, headers=users["other"])).status_code == 404
    async with sessions() as db:
        assert await db.scalar(select(func.count()).select_from(TaskRecord)) == 0

    async def publish(_task):
        return None  # 不向独立测试Schema之外的真实Redis发布。

    monkeypatch.setattr(tasker, "publish", publish)
    replies = await asyncio.gather(*(client.post(path + "/resume", headers=users["self"]) for _ in range(2)))
    assert all(reply.status_code == 200 for reply in replies), [reply.text for reply in replies]
    async with sessions() as db:
        tasks = list((await db.scalars(select(TaskRecord))).all())
        assert len(tasks) == 1 and tasks[0].type == "daily_arrangement_v1"
        assert tasks[0].payload["arrangement_id"] == saved["id"] and tasks[0].payload["version"] == 2


async def test_formal_details_and_purchase_reject_a_replaced_daily_meal(family_profile_http, monkeypatch):  # noqa: F811
    """旧正式餐仍存在时，也不能通过详情或采购入口绕过当前计划。"""
    from datetime import date
    from yuxi.services import daily_arrangement_service as service
    from yuxi.services.health_nutrition_service import input_fingerprint
    from yuxi.services.health_vision_types import HealthVisionError
    from yuxi.storage.postgres.models_health import HealthDailyMealPlan

    async def quality_owner(*args):
        return None

    monkeypatch.setattr(service, "validate_daily_quality", quality_owner)
    client, sessions, users = family_profile_http
    family, _, _, _ = await source(client, users["self"])
    rid = str(uuid4())
    meals = [
        {"type": meal, "members": [], "dishes": [{"name": "合成菜"}], "memberNotes": []}
        for meal in ("breakfast", "lunch", "dinner")
    ]
    snapshot = {"status": "ready", "id": rid, "version": 1, "date": "2099-01-01", "meals": meals, "analysis": {}}
    formal = {"kind": "formal", "id": rid, "version": 1}
    async with sessions.begin() as db:
        db.add(
            HealthDailyArrangement(
                id=rid,
                actor_uid="self",
                family_id=family["id"],
                plan_date=date(2099, 1, 1),
                version=1,
                status="ready",
                request_id=str(uuid4()),
                selection={},
                sources={"members": {}},
                snapshot=snapshot,
            )
        )
        db.add(
            HealthDailyMealPlan(
                id=str(uuid4()),
                actor_uid="self",
                family_id=family["id"],
                plan_date=date(2099, 1, 1),
                version=2,
                meal_sources={"breakfast": formal, "lunch": {"kind": "reference", "id": "other"}, "dinner": formal},
                pending={},
            )
        )
    path = f"/api/family/{family['id']}/daily-arrangements/2099-01-01/meals"
    params = f"?arrangement_id={rid}&version=1&daily_plan_version=2"
    assert (await client.get(path + "/breakfast" + params, headers=users["self"])).status_code == 200
    assert (await client.get(path + "/lunch" + params, headers=users["self"])).status_code == 409
    assert (
        await client.get(
            path + "/breakfast" + params.replace("daily_plan_version=2", "daily_plan_version=1"), headers=users["self"]
        )
    ).status_code == 409
    source_proof = {
        "uid": "self",
        "family_id": family["id"],
        "date": "2099-01-01",
        "arrangement_id": rid,
        "meal": "lunch",
        "meal_hash": input_fingerprint(meals[1]),
    }
    with pytest.raises(HealthVisionError, match="source_invalidated"):
        await service.validate_daily_commerce_source(source_proof)


async def source(client, headers):
    """以真实建档接口建立合成家庭，不借生产数据。"""
    result = await client.post("/api/family", headers=headers, json={"name": "每日安排合成测试家庭"})
    assert result.status_code == 200, result.text
    family = result.json()
    member = next(row for row in family["members"] if row["is_self"])
    request_id = str(uuid4())
    data = {
        "client_request_id": request_id,
        "family_version": family["version"],
        "usage_mode": "家庭使用",
        "default_diners": ["self", "child"],
        "members": [
            {
                "client_ref": "self",
                "member_id": member["id"],
                "version": member["version"],
                "name": "合成本人",
                "relation": "本人",
                "birth_date": "1990-01-01",
                "sex": "female",
                "height_cm": 165,
                "weight_kg": 55,
                "dietary": {
                    "healthStatus": "none",
                    "allergyStatus": "none",
                    "intoleranceStatus": "none",
                    "avoidanceStatus": "none",
                    "doctorStatus": "none",
                    "goals": ["饮食均衡"],
                    "tastePreferences": ["不限口味"],
                    "cuisines": ["不限菜系"],
                },
            },
            {
                "client_ref": "child",
                "name": "合成家人",
                "relation": "家人",
                "birth_date": "2015-01-01",
                "dietary": {
                    "healthStatus": "none",
                    "allergyStatus": "none",
                    "intoleranceStatus": "set",
                    "intolerances": ["测试不耐受"],
                    "avoidanceStatus": "none",
                    "doctorStatus": "none",
                    "goals": ["饮食均衡"],
                    "tastePreferences": ["不限口味"],
                    "cuisines": ["不限菜系"],
                },
            },
        ],
    }
    path = f"/api/family/{family['id']}/miniapp-profile"
    return family, path, data, {**headers, "Idempotency-Key": request_id}


async def test_complete_onboarding_is_atomic_idempotent_and_server_backed(family_profile_http):  # noqa: F811
    """并发重放只创建一位新增成员，响应丢失后能回读同一真实结果。"""
    client, sessions, users = family_profile_http
    family, path, data, headers = await source(client, users["self"])
    responses = await asyncio.gather(*(client.post(path, headers=headers, json=data) for _ in range(2)))
    assert all(response.status_code == 200 for response in responses), [response.text for response in responses]
    saved = (await client.get(path, headers=users["self"])).json()
    assert saved["source"] == "api" and saved["onboarded"] is True
    assert len(saved["defaultDiners"]) == 2 and len(saved["members"]) == 2
    own = next(member for member in saved["members"] if member["relation"] == "本人")
    assert own["allergyStatus"] == "none" and own["weight"] == 55
    async with sessions() as db:
        assert (
            await db.scalar(
                select(func.count()).select_from(FamilyMember).where(FamilyMember.family_id == family["id"])
            )
            == 2
        )
        assert await db.scalar(select(func.count()).select_from(HealthMiniappProfileReceipt)) == 1


async def test_onboarding_rejects_changed_replay_and_foreign_family(family_profile_http):  # noqa: F811
    """同键改内容及其他账号访问都由服务端拒绝。"""
    client, _, users = family_profile_http
    _, path, data, headers = await source(client, users["self"])
    assert (await client.post(path, headers=headers, json=data)).status_code == 200
    data["members"][0]["name"] = "篡改重放"
    assert (await client.post(path, headers=headers, json=data)).status_code == 409
    assert (await client.get(path, headers=users["other"])).status_code == 404


@pytest.mark.parametrize(
    "field",
    [
        "birth_date",
        "healthStatus",
        "allergyStatus",
        "intoleranceStatus",
        "avoidanceStatus",
        "doctorStatus",
        "goals",
        "tastePreferences",
    ],
)
async def test_incomplete_onboarding_does_not_mark_family_complete(family_profile_http, field):  # noqa: F811
    """真实HTTP拒绝缺失必填，数据库完成标记和保存收据均不生成。"""
    client, sessions, users = family_profile_http
    _, path, data, headers = await source(client, users["self"])
    member = data["members"][0]
    del (member if field == "birth_date" else member["dietary"])[field]
    response = await client.post(path, headers=headers, json=data)
    assert response.status_code == 422, response.text
    saved = (await client.get(path, headers=users["self"])).json()
    assert saved["onboarded"] is False
    async with sessions() as db:
        assert await db.scalar(select(func.count()).select_from(HealthMiniappProfileReceipt)) == 0


async def test_missing_real_planner_dependencies_cannot_publish_a_placeholder(family_profile_http):  # noqa: F811
    """尚无真实健康关联时是服务缺项，不生成空三餐或示例菜单。"""
    client, _, users = family_profile_http
    family, path, data, headers = await source(client, users["self"])
    assert (await client.post(path, headers=headers, json=data)).status_code == 200
    root = f"/api/family/{family['id']}/daily-arrangements"
    response = await client.get(root + "/2026-10-17", headers=users["self"])
    assert response.status_code == 200 and response.json()["status"] == "absent"
    request_id = str(uuid4())
    response = await client.post(
        root,
        headers={**users["self"], "Idempotency-Key": request_id},
        json={"client_request_id": request_id, "date": "2026-10-17"},
    )
    assert response.status_code == 503 and response.json()["code"] == "daily_member_sources_unavailable"
    assert "meals" not in response.json()


async def test_explicit_save_and_analyse_binds_actor_without_fake_professional_confirmation(
    family_profile_http,  # noqa: F811
    monkeypatch,
):
    """缺少用途的旧提交明确拒绝；建档同意只关联当前本人，不代家人授权。"""
    from yuxi.services.health_vision_service import health_vision_service

    async def configured(session=None):
        return {
            "meal_plan": {"available": True, "processor": "synthetic-processor"},
            "policy_version": "synthetic-policy",
        }

    monkeypatch.setattr(health_vision_service, "configuration", configured)
    client, sessions, users = family_profile_http
    _, path, data, headers = await source(client, users["self"])
    data["analysis_consent"] = {"processor": "synthetic-processor", "policy_version": "synthetic-policy"}
    rejected = await client.post(path, headers=headers, json=data)
    assert rejected.status_code == 409
    async with sessions() as db:
        assert await db.scalar(select(func.count()).select_from(HealthFamilyProfileLink)) == 0
    data["analysis_consent"]["purpose"] = "meal_plan"
    response = await client.post(path, headers=headers, json=data)
    assert response.status_code == 200, response.text
    assert (await client.post(path, headers=headers, json=data)).status_code == 200
    async with sessions() as db:
        links = list((await db.scalars(select(HealthFamilyProfileLink))).all())
        assert len(links) == 1 and links[0].source_kind == "miniapp_reported"
        assert links[0].source_member_id == response.json()["selfMemberId"]
        assert await db.scalar(select(func.count()).select_from(HealthProfileSnapshot)) == 0
        grants = list((await db.scalars(select(HealthGrant))).all())
        assert len(grants) == 1
        assert all(set(grant.scopes) == {"ai_use", "diet_edit", "profile_view"} for grant in grants)


async def test_saved_initial_result_replays_without_regeneration_but_rechecks_access(family_profile_http, monkeypatch):  # noqa: F811
    """保存响应丢失后回放PG收据，不因库存重搜换菜；权限撤回仍拒绝。"""
    from test.integration.services.test_health_initial_meal_plan_http import setup_initial, preview, save
    from yuxi.services import health_initial_meal_plan_service

    client, _, identities = family_profile_http
    users = [{"uid": uid, "headers": identities[uid]} for uid in ("self", "other", "admin")]
    current = await setup_initial(client, users)
    owner = identities["self"]
    generated = await preview(client, owner, current, family=True)
    assert generated["status"] == "ready"
    key = str(uuid4())
    first = await save(client, owner, current, generated["preview_id"], request_id=key)
    assert first.status_code == 201, first.text

    async def cannot_regenerate(*args, **kwargs):
        raise AssertionError("已保存回执不应再次运行库存相关搜索")

    monkeypatch.setattr(health_initial_meal_plan_service, "initial_generation_in_session", cannot_regenerate)
    again = await save(client, owner, current, generated["preview_id"], request_id=key)
    assert again.status_code == 201, again.text
    assert again.json()["plan_id"] == first.json()["plan_id"]
    revoked = await client.put(
        f"/api/health/v1/members/{current['second']}/grants",
        headers=owner,
        json={"actor_uid": "self", "scopes": ["profile_view"]},
    )
    assert revoked.status_code == 200, revoked.text
    replay = await save(client, owner, current, generated["preview_id"], request_id=key)
    assert replay.status_code == 404, replay.text
    assert replay.json()["code"] == "not_found"
    assert "plan_id" not in replay.json()


async def test_daily_purchase_source_survives_other_meal_changes_but_not_revocation(family_profile_http, monkeypatch):  # noqa: F811
    """真实HTTP与PG回源：改午餐保留早餐采购，改早餐或撤权立即拒绝旧来源。"""
    from copy import deepcopy
    from datetime import date
    from yuxi.services.daily_arrangement_service import daily_commerce_source
    from unittest.mock import AsyncMock
    from yuxi.services import daily_arrangement_service as daily

    # 本用例检验餐次hash及真实授权；专业来源和目录失效有独立HTTP/PG回归。
    monkeypatch.setattr(daily, "validate_daily_quality", AsyncMock())
    monkeypatch.setattr(daily, "validate_daily_purchase_composition", AsyncMock())
    from yuxi.services.health_vision_service import health_vision_service

    async def configured(session=None):
        return {
            "meal_plan": {"available": True, "processor": "synthetic-processor"},
            "policy_version": "synthetic-policy",
        }

    monkeypatch.setattr(health_vision_service, "configuration", configured)
    monkeypatch.setenv("HEALTH_COMMERCE_SOURCE_SECRET", "synthetic-daily-source-secret-32bytes")
    monkeypatch.delenv("HEALTH_COMMERCE_INGREDIENT_MAP", raising=False)
    client, sessions, users = family_profile_http
    family, path, data, headers = await source(client, users["self"])
    data["analysis_consent"] = {
        "purpose": "meal_plan",
        "processor": "synthetic-processor",
        "policy_version": "synthetic-policy",
    }
    response = await client.post(path, headers=headers, json=data)
    assert response.status_code == 200, response.text
    profile = (await client.get(path, headers=users["self"])).json()
    members = {
        row["healthMemberId"]: {"id": row["id"], "version": row["version"]}
        for row in profile["members"]
        if row["healthMemberId"]
    }
    breakfast = {
        "type": "breakfast",
        "members": [{"id": row["id"]} for row in profile["members"] if row["healthMemberId"]],
        "dishes": [{"id": "synthetic-recipe-A"}],
        "memberNotes": [{"grams": 100}],
    }
    lunch = {**deepcopy(breakfast), "type": "lunch"}
    rid, day = str(uuid4()), date(2026, 10, 19)
    snapshot = {"status": "ready", "id": rid, "version": 1, "meals": [breakfast, lunch]}
    async with sessions() as db:
        db.add(
            HealthDailyArrangement(
                id=rid,
                actor_uid="self",
                family_id=family["id"],
                plan_date=day,
                status="ready",
                request_id=str(uuid4()),
                sources={"members": members},
                selection={},
                snapshot=snapshot,
            )
        )
        await db.commit()
    proof = daily_commerce_source("self", family["id"], day, rid, breakfast)
    endpoint = "/api/health/v1/commerce/source-validation"
    result = await client.post(endpoint, json=proof)
    assert result.status_code == 200 and result.json() == {"available": True}, result.text
    tampered = {**proof, "payload": proof["payload"].replace('"self"', '"other"')}
    assert (await client.post(endpoint, json=tampered)).status_code == 403
    async with sessions() as db:
        row = await db.get(HealthDailyArrangement, rid)
        updated = deepcopy(row.snapshot)
        updated["version"] = 2
        row.version = 2
        updated["meals"][1]["dishes"] = [{"id": "synthetic-recipe-B"}]
        row.snapshot = updated
        await db.commit()
    assert (await client.post(endpoint, json=proof)).status_code == 200
    async with sessions() as db:
        grant = await db.get(HealthGrant, (next(iter(members)), "self"))
        grant.scopes = ["profile_view"]
        await db.commit()
    denied = await client.post(endpoint, json=proof)
    assert denied.status_code == 404 and "available" not in denied.json(), denied.text

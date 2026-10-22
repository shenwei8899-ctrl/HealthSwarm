"""真实 PostgreSQL 与 HTTP 核验先安排、同页查看和显式发布采购。"""

from datetime import UTC, date, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import select

from test.integration.services.test_daily_arrangement_http import source
from test.integration.services.test_health_family_profile_http import (  # noqa: F401
    family_profile_http,
    ensure_live_api_schema,
    cleanup_test_sandboxes,
    cleanup_test_knowledge_resources,
)
from yuxi.storage.postgres.models_business import FamilyArchive, FamilyMember
from yuxi.storage.postgres.models_health import HealthDailyArrangement, HealthFamilyProfileLink, HealthGrant

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.mark.parametrize("blocked_first", [False, True])
@pytest.mark.parametrize("initial_stock", [0, 4])
async def test_view_is_read_only_and_purchase_publish_uses_saved_version(
    family_profile_http,  # noqa: F811
    monkeypatch,
    blocked_first,  # noqa: F811
    initial_stock,
):
    """未关联商城仍可查看商品，显式购买才发布，重试不重复发布。"""
    from yuxi.services import daily_arrangement_service as service

    client, sessions, users = family_profile_http
    family, _, _, _ = await source(client, users["self"])
    rid, task_key = str(uuid4()), str(uuid4())
    sku = {
        "sku_id": "sku-1",
        "data_completeness": "complete",
        "product_name": "合成番茄",
        "price_cent": 800,
        "available_quantity": initial_stock,
        "sale_status": "available",
        "ingredients": [
            {
                "ingredient_id": "tomato",
                "ingredient_code": "tomato",
                "net_unit": "g",
                "net_value": 500,
                "review_status": "approved",
            }
        ],
    }
    purchase = {
        "status": "matched",
        "catalog_version": "catalog-1",
        "items": [{"sku_id": "sku-1", "quantity": 1, "sku": sku}],
        "ingredient_requirements": [{"ingredient_id": "tomato", "required_value": "300", "required_unit": "g"}],
    }
    async with sessions() as db:
        db.add(
            HealthDailyArrangement(
                id=rid,
                actor_uid="self",
                family_id=family["id"],
                plan_date=date(2026, 10, 21),
                version=1,
                status="ready",
                request_id=str(uuid4()),
                sources={"members": {}},
                selection={
                    "purchase_payloads": {
                        "dinner": {
                            "agent_task_id": task_key,
                            "items": [{"sku_id": "sku-1", "quantity": 1}],
                            "ingredient_requirements": purchase["ingredient_requirements"],
                        }
                    }
                },
                snapshot={
                    "status": "ready",
                    "id": rid,
                    "version": 1,
                    "date": "2026-10-21",
                    "meals": [{"type": "dinner", "purchase": purchase}],
                },
            )
        )
        await db.commit()

    async def quality_owner(db, uid, snapshot):
        # 本用例只验采购状态机；真实质量失效由独立 HTTP/PG 回归覆盖。
        return None

    monkeypatch.setattr(service, "validate_daily_quality", quality_owner)
    calls = []

    async def catalog():
        return {"items": [sku, {**sku, "sku_id": "sku-alternative", "available_quantity": 4}], "version": "catalog-2"}

    async def publish(method, path, payload=None, *, request_id=None):
        if method == "GET":
            return (
                {**sku, "sale_status": "unavailable", "unavailable_reason": "out_of_stock"}
                if sku["available_quantity"] == 0
                else sku
            )
        calls.append((method, path, request_id))
        if blocked_first and len(calls) == 1:
            return {"status": "blocked", "trade_validation_status": "failed"}
        return {
            "status": "available",
            "trade_validation_status": "passed",
            "package_sn": "synthetic-pack",
            "package_version": 1,
            "items": payload["items"],
        }

    monkeypatch.setattr(service, "current_catalog", catalog)
    monkeypatch.setattr(service, "commerce_request", publish)
    monkeypatch.setattr("yuxi.services.daily_commerce_service.commerce_request", publish)
    path = f"/api/family/{family['id']}/daily-arrangements/2026-10-21/meals/dinner/purchase"
    response = await client.get(path, params={"arrangement_id": rid, "version": 1}, headers=users["self"])
    assert response.status_code == 200, response.text
    assert response.json()["purchase"]["available"] is True
    assert response.json()["purchase"]["items"][0]["sku_id"] == ("sku-1" if initial_stock else "sku-alternative")
    assert response.json()["purchase"]["items"][0]["sku"]["price_cent"] == 800
    assert calls == []
    assert (
        await client.get(path, params={"arrangement_id": rid, "version": 1}, headers=users["other"])
    ).status_code == 404
    body = {"arrangement_id": rid, "version": 1}
    assert (await client.post(path, json={**body, "version": 2}, headers=users["self"])).status_code == 409
    if blocked_first:
        assert (await client.post(path, json=body, headers=users["self"])).status_code == 409
    for _ in range(2):
        response = await client.post(path, json=body, headers=users["self"])
        assert response.status_code == 200, response.text
        assert response.json()["purchase"]["package_sn"] == "synthetic-pack"
    assert len(calls) == (2 if blocked_first else 1)
    assert calls[0] == ("POST", "/api/v1/integration/ai/recommendation-packages", task_key)
    if blocked_first:
        assert calls[1][2] != task_key
    sku["available_quantity"] = 0

    async def empty_catalog():
        return {"items": [], "version": "empty"}

    monkeypatch.setattr(service, "current_catalog", empty_catalog)
    response = await client.get(path, params=body, headers=users["self"])
    assert response.json()["purchase"]["available"] is False


@pytest.mark.parametrize("change", ["profile", "default_diners"])
async def test_changed_profile_restarts_same_arrangement_but_revocation_still_denies(
    family_profile_http,  # noqa: F811
    monkeypatch,
    change,  # noqa: F811
):
    """来源过期可以创建新版本，权限失效不能借自动重配绕过。"""
    from yuxi.services import daily_arrangement_service as service
    from yuxi.services import daily_arrangement_tasks as tasks
    from yuxi.services.health_vision_service import health_vision_service
    from yuxi.services.task_service import tasker

    async def configured(session=None):
        return {
            "meal_plan": {"available": True, "processor": "synthetic-processor"},
            "policy_version": "synthetic-policy",
        }

    monkeypatch.setattr(health_vision_service, "configuration", configured)
    client, sessions, users = family_profile_http
    family, profile_path, data, headers = await source(client, users["self"])
    data["analysis_consent"] = {"processor": "synthetic-processor", "policy_version": "synthetic-policy"}
    response = await client.post(profile_path, json=data, headers=headers)
    assert response.status_code == 200, response.text
    rid = str(uuid4())
    async with sessions() as db:
        link = await db.scalar(select(HealthFamilyProfileLink).where(HealthFamilyProfileLink.family_id == family["id"]))
        member = await db.get(FamilyMember, link.source_member_id)
        saved_family = await db.get(FamilyArchive, family["id"])
        old_diners = sorted(saved_family.settings["default_diners"])
        old_version, hid, mid = member.version, link.member_id, member.id
        sources = {
            "members": {hid: {"id": mid, "version": old_version}},
            "account_ref": "uid:self",
            "default_diners": old_diners,
        }
        db.add(
            HealthDailyArrangement(
                id=rid,
                actor_uid="self",
                family_id=family["id"],
                plan_date=date(2026, 10, 21),
                version=1,
                status="ready",
                request_id=str(uuid4()),
                sources=sources,
                selection={},
                snapshot={"status": "ready", "id": rid, "version": 1, "meals": []},
            )
        )
        if change == "profile":
            member.version += 1
        else:
            saved_family.settings = {**saved_family.settings, "default_diners": [mid]}
            saved_family.version += 1
        await db.commit()
    path = f"/api/family/{family['id']}/daily-arrangements"
    response = await client.get(path + "/2026-10-21", headers=users["self"])
    assert response.status_code == 200 and response.json()["status"] == "stale", response.text
    queued = []

    async def selection(db, uid, family, day, **kwargs):
        current_version = old_version + (change == "profile")
        return SimpleNamespace(model_dump=lambda **_: {"profile_versions": {hid: current_version}}), {
            "members": {hid: {"id": mid, "version": current_version}},
            "account_ref": "uid:self",
            "default_diners": sorted(family.settings["default_diners"]),
        }

    async def queue(db, row):
        queued.append(row.version)
        return SimpleNamespace(id="synthetic-task")

    async def publish(task):
        pass

    monkeypatch.setattr(service, "daily_selection", selection)
    monkeypatch.setattr(tasks, "queue_daily_in_session", queue)
    monkeypatch.setattr(tasker, "publish", publish)
    key = str(uuid4())
    body = {"date": "2026-10-21", "client_request_id": key}
    for _ in range(2):
        response = await client.post(path, json=body, headers={**users["self"], "Idempotency-Key": key})
        assert response.status_code == 200 and response.json()["id"] == rid, response.text
    assert queued == [2]
    async with sessions() as db:
        row = await db.get(HealthDailyArrangement, rid)
        assert row.version == 2 and row.status == "generating" and row.snapshot == {}
        grant = await db.scalar(
            select(HealthGrant).where(HealthGrant.member_id == hid, HealthGrant.actor_uid == "self")
        )
        grant.revoked_at = datetime.now(UTC).replace(tzinfo=None)
        await db.commit()
    assert (await client.get(path + "/2026-10-21", headers=users["self"])).status_code in (403, 404)


@pytest.mark.parametrize("legacy", [False, True])
@pytest.mark.parametrize("blocked_first", [False, True])
async def test_summary_merges_grams_before_rounding_and_signs_only_chosen_meals(
    family_profile_http,  # noqa: F811
    monkeypatch,
    legacy,
    blocked_first,
):
    """跨餐共需300克只买一包500克；换版本、越权和重复餐次均拒绝。"""
    import json
    from yuxi.services import daily_arrangement_purchase as summary
    from yuxi.services import daily_arrangement_service as service
    from yuxi.services.health_vision_types import HealthVisionError

    client, sessions, users = family_profile_http
    family, _, _, _ = await source(client, users["self"])
    rid = str(uuid4())
    monkeypatch.setenv("HEALTH_COMMERCE_SOURCE_SECRET", "synthetic-source-secret-0123456789012345")
    sku = {
        "sku_id": "rice-500",
        "product_name": "合成大米",
        "data_completeness": "complete",
        "price_cent": 1000,
        "sale_status": "available",
        "available_quantity": 5,
        "ingredients": [
            {
                "ingredient_id": "rice",
                "ingredient_code": "rice",
                "net_unit": "g",
                "net_value": 500,
                "review_status": "approved",
            }
        ],
    }
    requirement = {"ingredient_id": "rice", "ingredient_code": "rice", "required_value": "150", "required_unit": "g"}
    meals = [
        {
            "type": name,
            "members": [],
            "dishes": [],
            "memberNotes": [],
            "purchase": {"items": [{"sku_id": "rice-500", "quantity": 1}], "ingredient_requirements": [requirement]},
        }
        for name in ("breakfast", "lunch", "dinner")
    ]
    if legacy:
        for meal in meals:
            meal["purchase"].pop("ingredient_requirements")
    async with sessions() as db:
        db.add(
            HealthDailyArrangement(
                id=rid,
                actor_uid="self",
                family_id=family["id"],
                plan_date=date(2026, 10, 21),
                status="ready",
                version=1,
                request_id=str(uuid4()),
                sources={"members": {}},
                snapshot={
                    "status": "ready",
                    "id": rid,
                    "version": 1,
                    "meals": meals,
                    "plan_id": str(uuid4()),
                    "plan_version": 1,
                },
                selection={
                    "purchase_payloads": {
                        meal["type"]: {
                            "agent_task_id": str(uuid4()),
                            "recipes": [],
                            "ingredient_requirements": [requirement],
                            "items": [{"sku_id": "rice-500", "quantity": 1}],
                            "nutrition_validation": {"status": "passed"},
                        }
                        for meal in meals
                    }
                },
            )
        )
        await db.commit()

    async def quality_owner(db, uid, snapshot):
        # 本用例只验采购状态机；真实质量失效由独立 HTTP/PG 回归覆盖。
        return None

    monkeypatch.setattr(service, "validate_daily_quality", quality_owner)
    calls = []

    async def catalog():
        return {
            "version": "catalog-1",
            "items": [
                sku,
                {**sku, "sku_id": "rice-alternative", "available_quantity": 5 if blocked_first and calls else 0},
            ],
        }

    async def publish(method, path, payload=None, *, request_id=None):
        if method == "GET":
            return (
                {**sku, "sale_status": "unavailable", "unavailable_reason": "out_of_stock"}
                if sku["available_quantity"] == 0
                else sku
            )
        calls.append(payload)
        if blocked_first and len(calls) == 1:
            sku["available_quantity"] = 0
            return {"status": "blocked", "trade_validation_status": "failed"}
        if blocked_first and len(calls) == 2:
            raise HealthVisionError("commerce_timeout", "合成测试：商城发布响应丢失", 503)
        return {
            "status": "available",
            "trade_validation_status": "passed",
            "package_sn": "summary-pack",
            "package_version": 1,
            "items": payload["items"],
        }

    monkeypatch.setattr(summary, "current_catalog", catalog)
    monkeypatch.setattr(service, "current_catalog", catalog)
    monkeypatch.setattr(service, "commerce_request", publish)
    monkeypatch.setattr("yuxi.services.daily_commerce_service.commerce_request", publish)
    path = f"/api/family/{family['id']}/daily-arrangements/2026-10-21/purchase"
    params = {"arrangement_id": rid, "version": 1, "meals": ["breakfast", "lunch"]}
    response = await client.get(path, params=params, headers=users["self"])
    assert response.status_code == 200, response.text
    purchase = response.json()["purchase"]
    assert purchase["ingredient_requirements"][0]["required_value"] == "300"
    assert purchase["items"][0]["quantity"] == 1 and calls == []
    assert (await client.get(path, params=params, headers=users["other"])).status_code == 404
    assert (await client.get(path, params={**params, "version": 2}, headers=users["self"])).status_code == 409
    assert (
        await client.get(path, params={**params, "meals": ["lunch", "lunch"]}, headers=users["self"])
    ).status_code == 422
    if blocked_first:
        assert (await client.post(path, json=params, headers=users["self"])).status_code == 409
        response = await client.get(path, params=params, headers=users["self"])
        assert response.json()["purchase"]["items"][0]["sku_id"] == "rice-alternative"
        assert (await client.post(path, json=params, headers=users["self"])).status_code == 503
    for _ in range(2):
        response = await client.post(path, json=params, headers=users["self"])
        assert response.status_code == 200, response.text
        assert response.json()["purchase"]["package_sn"] == "summary-pack"
    assert len(calls) == (3 if blocked_first else 1)
    assert calls[0]["items"] == [{"sku_id": "rice-500", "quantity": 1}]
    if blocked_first:
        assert calls[-1]["items"] == [{"sku_id": "rice-alternative", "quantity": 1}]
        assert calls[1] == calls[2], "发布结果不确定时必须重放相同SKU、数量和幂等键"
    proof = json.loads(calls[0]["agent_source_proof"]["payload"])
    assert {item["meal"] for item in proof["meals"]} == {"breakfast", "lunch"}
    await service.validate_daily_commerce_source(proof)
    from yuxi.services import daily_arrangement_tasks as tasks
    from yuxi.services.task_service import tasker

    async def selection(db, uid, family, day, **kwargs):
        return SimpleNamespace(model_dump=lambda **_: {}), {"members": {}}

    async def queue(db, row):
        return SimpleNamespace(id="synthetic-task")

    async def dispatch(task):
        pass

    monkeypatch.setattr(service, "daily_selection", selection)
    monkeypatch.setattr(tasks, "queue_daily_in_session", queue)
    monkeypatch.setattr(tasker, "publish", dispatch)
    sku["available_quantity"] = 5  # 后续单餐调整独立验证，先恢复合成库存。
    async with sessions() as db:
        row = await db.get(HealthDailyArrangement, rid)
        row.selection = {**row.selection, "purchase_inflight": {"breakfast": 0}}
        original_breakfast_payload = row.selection["purchase_payloads"]["breakfast"]
        await db.commit()
    change_key = str(uuid4())
    response = await client.post(
        path.removesuffix("/purchase") + "/members",
        json={
            "client_request_id": change_key,
            "version": 1,
            "meal": "lunch",
            "member_ids": [family["members"][0]["id"]],
        },
        headers={**users["self"], "Idempotency-Key": change_key},
    )
    assert response.status_code == 200, response.text
    async with sessions() as db:
        row = await db.get(HealthDailyArrangement, rid)
        assert set(row.selection["purchase_payloads"]) == {"breakfast", "dinner"}
        assert row.selection.get("daily_purchases") is None
        assert row.selection["purchase_inflight"] == {"breakfast": 0}
        assert row.selection["purchase_payloads"]["breakfast"] == original_breakfast_payload
        # 隔离模拟Worker完成改午餐，未改餐次的采购来源必须由真实调整事务保留。
        row.selection = {
            **row.selection,
            "purchase_payloads": {
                **row.selection["purchase_payloads"],
                "lunch": {
                    "agent_task_id": str(uuid4()),
                    "recipes": [],
                    "ingredient_requirements": [requirement],
                    "items": [{"sku_id": "rice-500", "quantity": 1}],
                    "nutrition_validation": {"status": "passed"},
                },
            },
        }
        row.status = "ready"
        row.snapshot = {
            **row.snapshot,
            "version": 2,
            "meals": [
                {**meal, "dishes": ["changed"]} if meal["type"] == "lunch" else meal for meal in row.snapshot["meals"]
            ],
        }
        await db.commit()
    breakfast_path = path.removesuffix("/purchase") + "/meals/breakfast/purchase"
    sku["available_quantity"] = 0

    async def recovery_catalog():
        return {
            "version": "recovery-catalog",
            "items": [{**sku, "sku_id": "rice-alternative", "available_quantity": 5}],
        }

    monkeypatch.setattr(service, "current_catalog", recovery_catalog)
    recovery = await client.get(breakfast_path, params={"arrangement_id": rid, "version": 2}, headers=users["self"])
    assert recovery.status_code == 200 and recovery.json()["purchase"]["confirmation_pending"] is True, recovery.text
    assert recovery.json()["purchase"]["available"] is False
    recovered_item = recovery.json()["purchase"]["items"][0]
    assert recovered_item["sku_id"] == recovered_item["sku"]["sku_id"] == "rice-500"
    assert recovered_item["sku"]["product_name"] == sku["product_name"]
    assert recovered_item["sku"]["price_cent"] == sku["price_cent"]
    assert recovered_item["sku"]["available_quantity"] == 0
    response = await client.post(breakfast_path, json={"arrangement_id": rid, "version": 2}, headers=users["self"])
    assert calls[-1]["items"] == original_breakfast_payload["items"]
    assert calls[-1]["agent_task_id"] == original_breakfast_payload["agent_task_id"]
    sku["available_quantity"] = 5

    assert response.status_code == 200, response.text
    response = await client.post(path, json={**params, "version": 2}, headers=users["self"])
    assert response.status_code == 200, response.text
    with pytest.raises(HealthVisionError, match="已更新"):
        await service.validate_daily_commerce_source(proof)


@pytest.mark.parametrize("invalidated", ["rules_expired", "rules_revoked", "food_changed", "knowledge_changed"])
async def test_real_quality_sources_gate_daily_read_publish_and_commerce(
    family_profile_http,  # noqa: F811
    monkeypatch,
    invalidated,
):
    """真实检查先通过；专业来源失效后 HTTP 展示、发布和签名回源均拒绝。"""
    from datetime import timedelta
    from test.integration.services.test_health_quality_http import setup_quality
    from yuxi.services import daily_arrangement_service as service
    from yuxi.storage.postgres.models_health import HealthRuleSnapshot, HealthMealPlan, RecipeVersion, FoodRecord

    client, sessions, headers = family_profile_http
    users = [{"uid": uid, "headers": headers[uid]} for uid in ("self", "other", "admin")]
    current = await setup_quality(client, users)
    assert current["check"]["safety_check"]["status"] == "passed"
    if invalidated == "knowledge_changed":
        from test.integration.services.test_health_quality_http import proof as source_proof
        from yuxi.storage.postgres.models_knowledge import Base as KnowledgeBaseMetadata, KnowledgeBase, KnowledgeFile

        async with sessions() as db:
            connection = await db.connection()
            await connection.run_sync(KnowledgeBaseMetadata.metadata.create_all)
            db.add(
                KnowledgeBase(
                    kb_id="synthetic-nutrition",
                    name="合成专业来源",
                    kb_type="milvus",
                    created_by="admin",
                    share_config={"version": 2, "read_scope": None, "manage_scope": None},
                )
            )
            await db.flush()
            db.add(
                KnowledgeFile(
                    file_id="synthetic-source",
                    kb_id="synthetic-nutrition",
                    filename="synthetic.txt",
                    content_hash="a" * 64,
                    file_size=10,
                )
            )
            await db.commit()
        origin = await client.get(
            "/api/health/v1/nutrition-sources/synthetic-nutrition/documents/synthetic-source", headers=headers["admin"]
        )
        assert origin.status_code == 200, origin.text
        body = {**current["rules"], **source_proof(2), "source_ref": origin.json()["source_ref"]}
        imported = await client.post("/api/health/v1/approved-quality-rules", headers=headers["admin"], json=body)
        assert imported.status_code == 201, imported.text
        checked = await client.post(
            f"/api/health/v1/meal-plans/{current['plan']}/quality-checks",
            headers=headers["self"],
            json={**current["body"], "client_request_id": str(uuid4())},
        )
        assert checked.status_code == 201, checked.text
        current["check"] = checked.json()

    family, _, _, _ = await source(client, headers["self"])
    rid = str(uuid4())
    monkeypatch.setenv("HEALTH_COMMERCE_SOURCE_SECRET", "synthetic-daily-source-verification-20261022")
    needs = [{"ingredient_id": "synthetic-food", "required_value": "150", "required_unit": "g"}]
    product = {
        "sku_id": "synthetic-sku",
        "data_completeness": "complete",
        "sale_status": "available",
        "price_cent": 100,
        "available_quantity": 10,
        "allergen_codes": [],
        "ingredients": [
            {
                "ingredient_id": "synthetic-food",
                "ingredient_code": "synthetic-food",
                "review_status": "approved",
                "net_unit": "g",
                "net_value": "200",
            }
        ],
    }
    meal = {
        "type": "dinner",
        "members": [],
        "dishes": [],
        "memberNotes": [],
        "purchase": {"items": [{"sku_id": "synthetic-sku", "quantity": 1}], "ingredient_requirements": needs},
    }
    proof = service.daily_commerce_source("self", family["id"], date(2026, 10, 21), rid, meal)
    async with sessions() as db:
        db.add(
            HealthDailyArrangement(
                id=rid,
                actor_uid="self",
                family_id=family["id"],
                plan_date=date(2026, 10, 21),
                status="ready",
                version=1,
                request_id=str(uuid4()),
                sources={"members": {}},
                snapshot={
                    "status": "ready",
                    "id": rid,
                    "version": 1,
                    "meals": [meal],
                    "plan_id": current["plan"],
                    "plan_version": 1,
                    "quality_check_id": current["check"]["check_id"],
                },
                selection={
                    "purchase_payloads": {
                        "dinner": {
                            "agent_task_id": str(uuid4()),
                            "ingredient_requirements": needs,
                            "items": meal["purchase"]["items"],
                        }
                    }
                },
            )
        )
        await db.commit()

    async def commerce(method, path, payload=None, **kwargs):
        assert method == "GET", "失效来源不能到达商城发布"
        return product

    monkeypatch.setattr(service, "commerce_request", commerce)
    path = f"/api/family/{family['id']}/daily-arrangements/2026-10-21"
    result = await client.get(path, headers=headers["self"])
    assert result.status_code == 200 and result.json()["status"] == "ready", result.text
    callback = "/api/health/v1/commerce/source-validation"
    result = await client.post(callback, json=proof)
    assert result.status_code == 200 and result.json()["available"] is True, result.text
    async with sessions() as db:
        rule = await db.scalar(
            select(HealthRuleSnapshot)
            .where(HealthRuleSnapshot.rule_code == current["body"]["rule_code"])
            .order_by(HealthRuleSnapshot.version.desc())
            .limit(1)
        )
        if invalidated == "rules_expired":
            rule.valid_until = datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=1)
        elif invalidated == "rules_revoked":
            rule.revoked_at = datetime.now(UTC).replace(tzinfo=None)
        elif invalidated == "knowledge_changed":
            file = await db.scalar(select(KnowledgeFile).where(KnowledgeFile.file_id == "synthetic-source"))
            file.content_hash = "b" * 64
        else:
            plan = await db.get(HealthMealPlan, current["plan"])
            recipe = await db.get(RecipeVersion, plan.spec["meals"][0]["dishes"][0]["recipe_version_id"])
            food = await db.get(FoodRecord, recipe.ingredients[0]["food"]["id"])
            food.nutrients = {**food.nutrients, "energy_kcal": "999"}
        await db.commit()
    result = await client.get(path, headers=headers["self"])
    assert result.status_code == 200 and result.json()["status"] == "stale", result.text
    result = await client.post(
        path + "/meals/dinner/purchase", headers=headers["self"], json={"arrangement_id": rid, "version": 1}
    )
    assert result.status_code in (409, 410), result.text
    result = await client.post(callback, json=proof)
    assert result.status_code == 410, result.text

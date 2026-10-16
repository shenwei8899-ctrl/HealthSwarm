"""真实 TCP 与隔离 PG 验证记餐、候选导入和指标选取。"""

# ruff: noqa: F811 -- pytest 注入隔离 fixture。
import asyncio
from copy import deepcopy
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import select, func

from test.integration.services.test_health_meal_plan_pagination_http import (  # noqa: F401
    cleanup_test_sandboxes,
    cleanup_test_knowledge_resources,
    ensure_live_api_schema,
    meal_pagination_http,
)
from test.integration.services.test_health_diet_analysis_http import confirm_analysis_meal
from test.integration.services.test_health_weight_http import create_weight_subject
from yuxi.storage.postgres.models_health import (
    DietLog,
    VisionDraft,
    NutritionCalculation,
    FoodRecord,
    NutritionImportBatch,
)

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]
ROOT = "/api/health/v1"


async def test_atomic_recording_concurrent_replay_and_partial_family_retry(meal_pagination_http):
    """一个成员成功、一个越权失败；重试不会再插入成功记录。"""
    c = meal_pagination_http
    source, _ = await confirm_analysis_meal(c.client, c.identities["owner"], c.identities["admin"], c.member)
    meal = deepcopy(source["snapshot"]["meal"])
    meal["items"][0]["share_ratio"] = 1
    body = {
        "group_id": str(uuid4()),
        "members": [
            {"member_id": member, "client_request_id": str(uuid4()), "meal": meal, "accept_incomplete": True}
            for member in (c.member, c.foreign_member)
        ],
    }
    headers = {**c.identities["owner"], "Idempotency-Key": body["group_id"]}
    a, b = await asyncio.gather(
        *(c.client.post(ROOT + "/family-meal-recordings", json=body, headers=headers) for _ in range(2))
    )
    assert a.status_code == b.status_code == 200, a.text
    saved, failed = a.json()["results"]
    assert saved["status"] == "saved" and saved["snapshot"]["nutrition"]["totals"]["energy_kcal"] == "300.00"
    assert failed["status"] == "failed" and failed["http_status"] == 404
    assert b.json()["results"][0]["id"] == saved["id"]
    async with c.sessions() as session:
        assert await session.scalar(select(func.count()).select_from(DietLog)) == 2
        assert await session.scalar(select(func.count()).select_from(VisionDraft)) == 2
        assert await session.scalar(select(func.count()).select_from(NutritionCalculation)) == 2
    changed = deepcopy(body)
    changed["members"][0]["meal"]["items"][0]["grams"] = "200"
    conflict = await c.client.post(ROOT + "/family-meal-recordings", json=changed, headers=headers)
    assert conflict.json()["results"][0]["code"] == "idempotency_conflict"
    path = f"{ROOT}/members/{c.member}/diet-logs/{saved['id']}/detail"
    assert (await c.client.get(path, headers=c.identities["owner"])).json()["id"] == saved["id"]
    assert (
        await c.client.get(path.replace(c.member, c.foreign_member), headers=c.identities["owner"])
    ).status_code == 404
    # 部分重试只包含原失败成员，成功记录保持原 ID。
    body["members"] = body["members"][1:]
    assert (await c.client.post(ROOT + "/family-meal-recordings", json=body, headers=headers)).json()["results"][0][
        "status"
    ] == "failed"


async def test_recording_missing_acceptance_rolls_back_and_recipe_calculates(meal_pagination_http):
    """配方版记餐按净成品重量计算，缺失与无效份量不生成空日记。"""
    c = meal_pagination_http
    source, _ = await confirm_analysis_meal(c.client, c.identities["owner"], c.identities["admin"], c.member)
    food = source["snapshot"]["meal"]["items"][0]["food_id"]
    recipe = await c.client.post(
        ROOT + "/recipes",
        headers=c.identities["admin"],
        json={
            "record_code": str(uuid4()),
            "name": "合成菜谱",
            "cooking_state": "熟",
            "source": "合成",
            "license": "测试",
            "edition": "1",
            "dataset_version": "1",
            "yield_grams": "200",
            "ingredients": [{"food_id": food, "grams": "100"}],
        },
    )
    assert recipe.status_code == 201, recipe.text
    body = {
        "member_id": c.member,
        "client_request_id": str(uuid4()),
        "meal": {
            "meal_type": "lunch",
            "eaten_at": "2026-10-16T12:00:00+08:00",
            "items": [
                {
                    "item_id": str(uuid4()),
                    "name": "合成菜谱",
                    "recipe_version_id": recipe.json()["id"],
                    "grams": "50",
                    "share_ratio": 1,
                    "portion_source": "manual",
                }
            ],
        },
    }
    headers = {**c.identities["owner"], "Idempotency-Key": body["client_request_id"]}
    denied = await c.client.post(ROOT + "/meal-recordings", headers=headers, json=body)
    assert denied.json()["code"] == "nutrition_incomplete"
    async with c.sessions() as session:
        assert await session.scalar(select(func.count()).select_from(VisionDraft)) == 1
    body["accept_incomplete"] = True
    result = await c.client.post(ROOT + "/meal-recordings", headers=headers, json=body)
    assert result.status_code == 201, result.text
    assert result.json()["snapshot"]["nutrition"]["totals"]["energy_kcal"] == "50.00"
    assert result.json()["snapshot"]["nutrition"]["totals"]["sodium_mg"] is None
    assert (await c.client.post(ROOT + "/meal-recordings", headers=headers, json=body)).json()["id"] == result.json()[
        "id"
    ]
    body["meal"]["items"][0]["share_ratio"] = "0.5"
    assert (await c.client.post(ROOT + "/meal-recordings", headers=headers, json=body)).status_code == 422


async def test_candidate_import_persists_reports_without_publishing(meal_pagination_http):
    """缺许可、负值、重复行、越权和重放均与正式食品隔离。"""
    c = meal_pagination_http
    row = {
        "record_code": "synthetic-import",
        "name": "合成候选",
        "cooking_state": "熟",
        "nutrients": {"energy_kcal": "100"},
    }
    body = {
        "client_request_id": str(uuid4()),
        "kind": "food",
        "rows": [row, {**row, "record_code": "other"}, {**row, "nutrients": {"energy_kcal": -1}}],
    }
    headers = {**c.identities["admin"], "Idempotency-Key": body["client_request_id"]}
    result = await c.client.post(ROOT + "/nutrition-imports", headers=headers, json=body)
    assert result.status_code == 201, result.text
    report = result.json()
    assert report["summary"] == {"total": 3, "invalid": 2, "pending_review": 1}
    assert report["published_count"] == 0
    assert report["items"][1]["candidate"]["nutrients"]["energy_kcal"] == "100"
    assert (await c.client.post(ROOT + "/nutrition-imports", headers=headers, json=body)).json() == report
    assert (
        await c.client.get(ROOT + "/nutrition-imports/" + report["id"], headers=c.identities["owner"])
    ).status_code == 403
    body["rows"].pop()
    assert (await c.client.post(ROOT + "/nutrition-imports", headers=headers, json=body)).status_code == 409
    async with c.sessions() as session:
        assert await session.scalar(select(func.count()).select_from(FoodRecord)) == 0
        assert await session.scalar(select(func.count()).select_from(NutritionImportBatch)) == 1


async def test_indicator_fixed_window_selected_versions_and_condition_statistics(meal_pagination_http):
    """北京时间跨日边界、血糖条件分组及选定旧版本拒绝走真实记录接口。"""
    c = meal_pagination_http
    subject = await create_weight_subject(c.client, [{"uid": "owner", "headers": c.identities["owner"]}])
    selected_ids = []
    for value, condition, hour in ((5, "fasting", 0), (7, "fasting", 1), (9, "after_meal_2h", 2)):
        key = str(uuid4())
        selected_ids.append(key)
        response = await c.client.post(
            subject.measurement_path,
            headers=subject.headers,
            json={
                "id": key,
                "kind": "blood_glucose",
                "values": {"glucose": value},
                "measured_at": datetime(2026, 10, 15, hour, tzinfo=UTC).isoformat(),
                "source": "synthetic",
                "condition": condition,
            },
        )
        assert response.status_code == 200, response.text
    path = f"{ROOT}/members/{subject.member_id}/indicator-reviews/blood_glucose"
    selection = {"start_date": "2026-10-15", "end_date": "2026-10-15"}
    response = await c.client.post(path, headers=subject.headers, json=selection)
    assert response.status_code == 200, response.text
    report = response.json()
    assert report["total"] == 3 and len(report["records"]) == 3 and not report["truncated"]
    groups = {row["condition"]: row["statistics"]["glucose"] for row in report["review"]["groups"]}
    assert groups["fasting"]["mean"] == "6.00" and groups["after_meal_2h"]["mean"] == "9.00"
    assert report["review"]["citations"] == [] and report["review"]["individual_recommendation"] is None
    selection["records"] = [{"record_id": selected_ids[0], "version": 1}]
    assert (await c.client.post(path, headers=subject.headers, json=selection)).json()["total"] == 1
    selection["records"][0]["version"] = 2
    assert (await c.client.post(path, headers=subject.headers, json=selection)).status_code == 409
    selection["records"][0]["record_id"] = str(uuid4())
    assert (await c.client.post(path, headers=subject.headers, json=selection)).status_code == 409
    assert (await c.client.post(path, headers=c.identities["other"], json=selection)).status_code == 404
    assert (
        await c.client.post(path, headers=subject.headers, json={"start_date": "2024-01-01", "end_date": "2026-01-01"})
    ).status_code == 422


@pytest.mark.parametrize(
    "kind,values,expected",
    [
        ("blood_pressure", {"systolic": 120, "diastolic": 80}, {"systolic": "120.00", "diastolic": "80.00"}),
        (
            "blood_lipids",
            {"tc": 4.5, "tg": 1.2, "hdl": 1.4, "ldl": 2.4},
            {"tc": "4.50", "tg": "1.20", "hdl": "1.40", "ldl": "2.40"},
        ),
    ],
)
async def test_indicator_paired_values_and_empty_window(meal_pagination_http, kind, values, expected):
    """成对及同条四项保留同一来源，零条记录没有虚构统计。"""
    c = meal_pagination_http
    subject = await create_weight_subject(c.client, [{"uid": "owner", "headers": c.identities["owner"]}])
    key = str(uuid4())
    response = await c.client.post(
        subject.measurement_path,
        headers=subject.headers,
        json={"id": key, "kind": kind, "values": values, "measured_at": "2026-10-15T16:00:00Z", "source": "synthetic"},
    )
    assert response.status_code == 200, response.text
    path = f"{ROOT}/members/{subject.member_id}/indicator-reviews/{kind}"
    selected = {"start_date": "2026-10-16", "end_date": "2026-10-16", "records": [{"record_id": key, "version": 1}]}
    response = await c.client.post(path, headers=subject.headers, json=selected)
    assert response.status_code == 200, response.text
    result = response.json()
    assert len(result["records"]) == 1 and result["records"][0]["record_id"] == key
    assert {k: v["mean"] for k, v in result["review"]["groups"][0]["statistics"].items()} == expected
    empty = await c.client.post(
        path, headers=subject.headers, json={"start_date": "2026-10-15", "end_date": "2026-10-15"}
    )
    assert empty.json()["total"] == 0 and empty.json()["review"]["groups"] == []
    assert empty.json()["review"]["status"] == "no_data"

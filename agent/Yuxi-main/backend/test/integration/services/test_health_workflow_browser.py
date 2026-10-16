"""浏览器通过真实 API 写入后，由独立 PG 会话核验；默认不等待浏览器。"""

# ruff: noqa: F811 -- pytest 注入隔离 fixture。
import asyncio
import json
import os
from pathlib import Path
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
from yuxi.storage.postgres.models_health import DietLog, DietLogRevision, NutritionImportBatch

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio,
    pytest.mark.skipif(not os.getenv("HEALTH_WORKFLOW_UI_CONTROL"), reason="需要独立浏览器控制目录"),
]


async def test_real_client_recording_correction_indicators_and_import(meal_pagination_http):
    """只准备合成资料，浏览器完成操作后核验最终事实。"""
    c = meal_pagination_http
    control = Path(os.environ["HEALTH_WORKFLOW_UI_CONTROL"])
    control.mkdir(parents=True, exist_ok=True)
    assert not (control / "ready.json").exists()
    root = "/api/health/v1"
    subject = await create_weight_subject(c.client, [{"uid": "owner", "headers": c.identities["owner"]}])
    record, _ = await confirm_analysis_meal(c.client, c.identities["owner"], c.identities["admin"], subject.member_id)
    recipe = await c.client.post(
        root + "/recipes",
        headers=c.identities["admin"],
        json={
            "record_code": str(uuid4()),
            "name": "合成米饭",
            "cooking_state": "熟",
            "source": "合成浏览器验收",
            "license": "仅测试",
            "edition": "1",
            "dataset_version": "1",
            "yield_grams": "200",
            "ingredients": [{"food_id": record["snapshot"]["meal"]["items"][0]["food_id"], "grams": "100"}],
        },
    )
    assert recipe.status_code == 201
    today = "2026-10-16T01:00:00Z"
    for kind, values, condition in (
        ("blood_glucose", {"glucose": 5.5}, "fasting"),
        ("blood_pressure", {"systolic": 120, "diastolic": 80}, None),
        ("blood_lipids", {"tc": 4.5, "tg": 1.2, "hdl": 1.4, "ldl": 2.4}, None),
    ):
        response = await c.client.post(
            subject.measurement_path,
            headers=subject.headers,
            json={
                "id": str(uuid4()),
                "kind": kind,
                "values": values,
                "measured_at": today,
                "source": "合成测量",
                **({"condition": condition} if condition else {}),
            },
        )
        assert response.status_code == 200, response.text
    (control / "ready.json").write_text(
        json.dumps(
            {
                "member": subject.member_id,
                "record": record["id"],
                "recipe": recipe.json()["id"],
                "owner": c.identities["owner"],
                "admin": c.identities["admin"],
            }
        ),
        encoding="utf-8",
    )
    for _ in range(1800):
        if (control / "done.json").exists():
            break
        if (control / "failed.json").exists():
            pytest.fail("浏览器验收失败，见本轮私有日志")
        await asyncio.sleep(1)
    assert (control / "done.json").exists(), "浏览器未交付操作回执"
    async with c.sessions() as session:
        changed = await session.get(DietLog, record["id"])
        assert changed.version == 2 and changed.snapshot["nutrition"]["totals"]["energy_kcal"] == "240.00"
        assert await session.scalar(select(func.count()).select_from(DietLogRevision)) == 2
        assert await session.scalar(select(func.count()).select_from(DietLog)) == 2
        assert await session.scalar(select(func.count()).select_from(NutritionImportBatch)) == 1
    (control / "verified.json").write_text(
        json.dumps(
            {
                "real_http_and_pg": True,
                "same_id_version_increment": True,
                "recalculated_kcal": "240.00",
                "recipe_meals": 1,
                "candidate_imports": 1,
                "models_called": False,
            }
        ),
        encoding="utf-8",
    )

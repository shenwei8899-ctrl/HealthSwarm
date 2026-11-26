"""日历与照片确认共用正式记录，撤销后只读状态仍可核对。"""
from datetime import datetime
from uuid import uuid4

import pytest

from test.integration.services.test_health_diet_analysis_http import confirm_analysis_meal
from test.integration.services.test_health_meal_plan_pagination_http import (  # noqa: F401
    cleanup_test_sandboxes, cleanup_test_knowledge_resources, ensure_live_api_schema, meal_pagination_http, revoke_grant,
)

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]
ROOT = "/api/health/v1"


async def test_confirmed_photo_record_is_visible_in_its_actual_calendar_day(meal_pagination_http):
    """历史用餐日期以已确认快照决定，不受当前分页或创建时间影响。"""
    c = meal_pagination_http
    record, _ = await confirm_analysis_meal(c.client, c.identities["owner"], c.identities["admin"], c.member)
    day = datetime.fromisoformat(record["snapshot"]["meal"]["eaten_at"]).date().isoformat()
    response = await c.client.get(f"{ROOT}/members/{c.member}/diet-journal?day={day}", headers=c.identities["owner"])
    assert response.status_code == 200, response.text
    assert record["id"] in [row["id"] for row in response.json()["records"]]
    assert day in response.json()["recorded_dates"]
    await revoke_grant(c, c.member, "admin")
    denied = await c.client.get(f"{ROOT}/members/{c.member}/diet-journal?day={day}", headers=c.identities["admin"])
    assert denied.status_code == 404


async def test_photo_record_withdrawal_replays_and_removes_calendar_entry(meal_pagination_http):
    """通用撤销接受照片记录并保留可回读状态，旧版本幂等重放不复活记录。"""
    c = meal_pagination_http
    record, _ = await confirm_analysis_meal(c.client, c.identities["owner"], c.identities["admin"], c.member)
    request_id = str(uuid4())
    payload = {"client_request_id": request_id, "expected_version": record["source_version"]}
    headers = {**c.identities["owner"], "Idempotency-Key": request_id, "If-Match": f'"{record["source_version"]}"'}
    url = f"{ROOT}/diet-logs/{record['id']}/withdraw"
    first = await c.client.post(url, headers=headers, json=payload)
    assert first.status_code == 200, first.text
    assert first.json()["status"] == "withdrawn"
    second = await c.client.post(url, headers=headers, json=payload)
    assert second.status_code == 200 and second.json() == first.json()
    status = await c.client.get(f"{ROOT}/diet-logs/{record['id']}/status", headers=c.identities["owner"])
    assert status.json()["status"] == "withdrawn"
    detail = await c.client.get(f"{ROOT}/members/{c.member}/diet-logs/{record['id']}/detail", headers=c.identities["owner"])
    assert detail.status_code == 410

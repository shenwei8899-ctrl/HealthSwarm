"""单日入口读取真实来源；跨账号与改版按HTTP事实拒绝。"""

import os
from copy import deepcopy

import pytest

from test.integration.services.test_health_vision_http import ROOT, create_member, health_http  # noqa: F401
from test.integration.services.test_health_initial_meal_plan_http import setup_initial
from test.integration.services.test_health_quality_http import proof

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_initial_context_reads_current_sources_without_creating_plan(health_http):  # noqa: F811
    """未确认档案、未批准默认规则及跨账号均不返回可生成选择。"""
    client, users = health_http
    owner, other, admin = [u["headers"] for u in users]
    member = await create_member(client, owner)
    path = f"{ROOT}/members/{member}/initial-meal-plan-context?plan_date=2026-10-27"
    missing = await client.get(path, headers=owner)
    assert missing.status_code == 200 and missing.json()["reason"] == "profile_not_ready"
    forbidden = await client.get(path, headers=other)
    assert forbidden.status_code in (403, 404)
    current = await setup_initial(client, users)
    member = current["member"]
    path = f"{ROOT}/members/{member}/initial-meal-plan-context?plan_date=2026-10-27"
    missing = await client.get(path, headers=owner)
    assert missing.json()["selection"] is None and missing.json()["reason"] == "rules_not_ready"
    configured = os.environ["HEALTH_DAILY_RULE_CODE"]
    payload = deepcopy(current["rules"]["payload"])
    imported = await client.post(
        f"{ROOT}/approved-quality-rules",
        headers=admin,
        json={**proof(), "rule_code": configured, "status": "approved", "payload": payload},
    )
    assert imported.status_code == 201, imported.text
    try:
        result = await client.get(path, headers=owner)
        assert result.status_code == 200 and result.headers["cache-control"] == "no-store", result.text
        selected = result.json()["selection"]
        assert selected["kind"] == "single" and selected["purchase_required"] is False
        assert selected["plan_date"] == "2026-10-27" and selected["rule_code"] == configured
        assert selected["profile_versions"] == {member: 1}
        assert selected["meals"] == [
            {"meal_type": meal, "participant_ids": [member]} for meal in ("breakfast", "lunch", "dinner")
        ]
        assert (await client.get(f"{ROOT}/members/{member}/meal-plans", headers=owner)).json()["plans"] == []
        revoked = await client.post(
            f"{ROOT}/approved-quality-rules/{configured}/versions/{selected['rule_version']}/revoke", headers=admin
        )
        assert revoked.status_code == 200, revoked.text
        assert (await client.get(path, headers=owner)).json()["reason"] == "rules_not_ready"
    finally:
        # 专用隔离测试规则不留作后续测试的有效输入。
        await client.post(f"{ROOT}/approved-quality-rules/{configured}/versions/1/revoke", headers=admin)

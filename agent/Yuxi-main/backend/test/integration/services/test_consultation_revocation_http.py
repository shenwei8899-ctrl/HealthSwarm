"""真实 TCP/PG 验证撤回咨询同意后关闭目录及每日历史。"""

# ruff: noqa: F401,F811 -- pytest 复用共享的隔离数据库和 TCP fixture。
import pytest

from test.integration.services.test_reference_meal_plan_http import (
    cleanup_test_knowledge_resources,
    cleanup_test_sandboxes,
    ensure_live_api_schema,
    family_profile_http,
    isolate_delivery,
    setup_reference,
)
from yuxi.storage.postgres.models_health import HealthGrant, HealthProcessingConsent
from yuxi.utils.datetime_utils import utc_now_naive

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_revoking_consultation_blocks_both_http_directories_without_revoking_member_grant(
    family_profile_http, monkeypatch
):
    """成员访问仍有效时，真实用途同意撤回仍返回 403。"""
    client, sessions, users, member_id, _, _ = await setup_reference(family_profile_http, monkeypatch)
    async with sessions.begin() as db:
        consent = await db.get(HealthProcessingConsent, (member_id, "self", "consultation"))
        if consent is None:
            consent = HealthProcessingConsent(
                member_id=member_id,
                actor_uid="self",
                purpose="consultation",
                processor="synthetic-processor",
                policy_version="synthetic-policy",
            )
            db.add(consent)
        consent.revoked_at = None
    paths = [
        f"/api/health/v1/members/{member_id}/consultations",
        f"/api/health/v1/members/{member_id}/daily-conversations",
    ]
    for path in paths:
        assert (await client.get(path, headers=users["self"])).status_code == 200
        assert (await client.get(path, headers=users["other"])).status_code == 404
        assert (await client.get(path)).status_code == 401
    async with sessions.begin() as db:
        consent = await db.get(HealthProcessingConsent, (member_id, "self", "consultation"))
        consent.revoked_at = utc_now_naive()
        grant = await db.get(HealthGrant, (member_id, "self"))
        assert grant.revoked_at is None and "ai_use" in grant.scopes
    for path in paths:
        response = await client.get(path, headers=users["self"])
        assert response.status_code == 403, response.text
        assert response.json()["code"] == "consent_required"

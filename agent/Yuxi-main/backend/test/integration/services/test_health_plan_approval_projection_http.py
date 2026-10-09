"""实际体重变源后审核状态的HTTP与持久化投影。"""

from datetime import timedelta

import pytest
from sqlalchemy import select

from test.integration.services.test_health_family_profile_http import (  # noqa: F401
    cleanup_test_knowledge_resources,
    cleanup_test_sandboxes,
    ensure_live_api_schema,
    family_profile_http,
)
from test.integration.services.test_health_weight_targets_http import (
    ROOT,
    approve_and_adopt,
    import_selected_profile,
    mutate_weight,
    save_weight_plan,
    selected_weight,  # noqa: F401
    publish_weight_rules,
)
from test.integration.services.test_health_quality_http import action
from yuxi.storage.postgres.models_health import HealthMealPlanAdoption, HealthProfessionalReview
from yuxi.services import health_quality_checks
from yuxi.utils.datetime_utils import utc_now_naive

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_actual_weight_change_is_visible_without_modifying_historical_plan(selected_weight):  # noqa: F811
    """先立即PG确认失效，再读页面所用状态；历史菜谱营养不改写。"""
    case = selected_weight
    await import_selected_profile(case)
    rules = await publish_weight_rules(case)
    saved = await save_weight_plan(case, rules)
    original = await case.client.get(f"{ROOT}/meal-plans/{saved['plan']}", headers=case.headers)
    assert original.status_code == 200
    snapshot = original.json()
    pending = await approval_state(case, saved)
    assert pending["available"] is False and pending["professional_review"] == "draft"
    assert pending["invalidation_reason"] is None
    adopted = await approve_and_adopt(case, saved)
    approved = await approval_state(case, saved)
    assert approved["available"] is True and approved["review_id"] == saved["review"]

    await mutate_weight(case, case.record, "correct")
    async with case.sessions() as session:
        review = await session.get(HealthProfessionalReview, saved["review"])
        adoption = await session.get(HealthMealPlanAdoption, adopted["adoption_id"])
        assert review.status == adoption.status == "invalidated"
        assert review.invalidation_reason == adoption.reason == "weight_measurement_changed"
    current = await approval_state(case, saved)
    assert current == {
        "available": False,
        "reason": "current_professional_approval_required",
        "plan_id": saved["plan"],
        "version": 1,
        "professional_review": "invalidated",
        "invalidation_reason": "weight_measurement_changed",
        "review_id": saved["review"],
        "check_id": saved["check"]["check_id"],
    }
    after = await case.client.get(f"{ROOT}/meal-plans/{saved['plan']}", headers=case.headers)
    assert after.status_code == 200 and after.json() == snapshot
    denied = await case.client.get(
        f"{ROOT}/meal-plans/{saved['plan']}/approval-state?version=1", headers=case.identities["other"]
    )
    assert denied.status_code == 404 and "weight_measurement_changed" not in denied.text
    async with case.sessions() as session:
        reviews = list(
            (
                await session.scalars(
                    select(HealthProfessionalReview).where(HealthProfessionalReview.id == saved["review"])
                )
            ).all()
        )
        assert len(reviews) == 1 and reviews[0].status == "invalidated"


async def approval_state(case, saved):
    """只读取准确当前餐单版本的服务端可用性。"""
    response = await case.client.get(
        f"{ROOT}/meal-plans/{saved['plan']}/approval-state?version={saved['version']}", headers=case.headers
    )
    assert response.status_code == 200, response.text
    return response.json()


async def test_pending_review_expiry_is_revalidated_by_approval_state(selected_weight, monkeypatch):  # noqa: F811
    """未批准专业对象的自然过期也在当前状态入口失效，不依赖主动写入失效。"""
    case = selected_weight
    await import_selected_profile(case)
    rules = await publish_weight_rules(case)
    saved = await save_weight_plan(case, rules)
    submitted = await action(case.client, case.headers, saved["review"], "submit", 1)
    assert submitted["status"] == "pending_review"
    pending = await approval_state(case, saved)
    assert pending["professional_review"] == "pending_review" and pending["available"] is False
    # TCP测试服务在同一进程，仅推进来源门禁的时钟；不篡改PG有效期、依据或指纹。
    future = utc_now_naive() + timedelta(days=2)
    monkeypatch.setattr(health_quality_checks, "utc_now_naive", lambda: future)
    profile = await case.client.get(
        f"{ROOT}/members/{case.member}/external-profile-versions/current", headers=case.headers
    )
    assert profile.status_code == 200 and profile.json()["reason"] == "expired", profile.text
    current = await approval_state(case, saved)
    assert current["professional_review"] == "invalidated"
    assert current["invalidation_reason"] == "source_changed_or_expired"
    async with case.sessions() as session:
        review = await session.get(HealthProfessionalReview, saved["review"])
        assert review.status == "invalidated" and review.invalidation_reason == "source_changed_or_expired"

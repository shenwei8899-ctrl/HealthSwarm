"""真实HTTP/PG证明实际进食窗口、反馈隔离和撤回后重新读取。"""

from uuid import uuid4

import pytest
from sqlalchemy import select

from test.integration.services.test_health_diet_analysis_http import confirm_analysis_meal
from test.integration.services.test_health_vision_http import ROOT, create_member, health_http  # noqa: F401
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_health import DietLog, HealthGrant, MealFeedback, VisionDraft

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_period_window_feedback_and_retraction_use_current_authorized_facts(health_http):  # noqa: F811
    """三餐360kcal独立手算，起止时区、其他账号反馈及无记录天数分别核对。"""
    client, users = health_http
    owner, admin = users[0]["headers"], users[2]["headers"]
    member = await create_member(client, owner)
    meals = []
    for eaten_at in (
        "2026-09-30T23:59:59+08:00",
        "2026-10-01T00:00:00+08:00",
        "2026-10-06T16:00:00+00:00",
        "2026-10-07T23:59:59+08:00",
        "2026-10-08T00:00:00+08:00",
    ):
        meals.append(await confirm_analysis_meal(client, owner, admin, member, eaten_at=eaten_at))
    record = meals[1][0]
    feedback_url = f"{ROOT}/diet-logs/{record['id']}/feedback"
    feedback_key = str(uuid4())
    feedback = await client.put(
        feedback_url,
        headers={**owner, "Idempotency-Key": feedback_key, "If-Match": '"0"'},
        json={
            "client_request_id": feedback_key,
            "version": 0,
            "consumption": "half",
            "tags": ["too_salty"],
        },
    )
    assert feedback.status_code == 200, feedback.text
    async with pg_manager.get_async_session_context() as session:
        session.add(HealthGrant(member_id=member, actor_uid=users[1]["uid"], scopes=["diet_edit"]))
        session.add(
            MealFeedback(
                id=str(uuid4()),
                actor_uid=users[1]["uid"],
                member_id=member,
                diet_log_id=record["id"],
                status="active",
                version=1,
                details={"consumption": "all", "tags": ["too_sweet"]},
            )
        )
    path, window = f"{ROOT}/members/{member}/diet-period-analysis", {"period_days": 7, "end_date": "2026-10-07"}
    response = await client.post(path, headers=owner, json=window)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["window"]["start_date"] == "2026-10-01"
    assert result["nutrition"]["totals"]["energy_kcal"]["recorded_total"] == "360.00"
    assert result["nutrition"]["totals"]["sodium_mg"]["recorded_total"] is None
    assert result["coverage"]["record_count"] == 3 and result["coverage"]["days_with_records"] == 2
    assert len(result["coverage"]["dates_without_records"]) == 5
    assert result["feedback"]["tag_counts"] == {"too_salty": 1}
    assert result["feedback"]["record_denominator"] == 3
    assert result["feedback"]["records_without_feedback"] == 2
    assert (await client.post(path, headers=admin, json=window)).status_code == 404
    other = await client.post(path, headers=users[1]["headers"], json=window)
    assert other.json()["feedback"]["tag_counts"] == {"too_sweet": 1}
    future = await client.post(path, headers=owner, json={**window, "end_date": "2099-01-01"})
    assert future.status_code == 422 and future.json()["code"] == "period_in_future"
    assert (await client.post(path, headers=owner, json={**window, "member_id": str(uuid4())})).status_code == 422
    assert (await client.post(path, headers=owner, json={**window, "period_days": 2})).status_code == 422
    assert (
        await client.post(path, headers=owner, json={"period_days": 1, "end_date": "0001-01-01"})
    ).status_code == 422
    day = await client.post(path, headers=owner, json={**window, "period_days": 1})
    assert day.json()["coverage"]["record_count"] == 2
    assert day.json()["nutrition"]["totals"]["energy_kcal"]["recorded_total"] == "240.00"
    async with pg_manager.get_async_session_context() as session:
        (await session.get(VisionDraft, meals[1][1])).review_status = "retracted"
    changed = await client.post(path, headers=owner, json=window)
    assert changed.status_code == 200, changed.text
    assert changed.json()["coverage"]["excluded_invalidated_records"] == 1
    assert changed.json()["nutrition"]["totals"]["energy_kcal"]["recorded_total"] == "240.00"
    assert changed.json()["feedback"]["count"] == 0
    async with pg_manager.get_async_session_context() as session:
        assert (
            await session.scalar(select(MealFeedback).where(MealFeedback.id == feedback.json()["feedback_id"]))
            is not None
        )


async def test_period_refuses_truncation_when_window_exceeds_record_limit(health_http):  # noqa: F811
    """实际PG超过边界时明确失败，不能静默少算并返回完整结果。"""
    client, users = health_http
    headers = users[0]["headers"]
    member = await create_member(client, headers)
    record, _ = await confirm_analysis_meal(client, headers, users[2]["headers"], member)
    async with pg_manager.get_async_session_context() as session:
        original = await session.get(DietLog, record["id"])
        session.add_all(
            [
                DietLog(
                    id=str(uuid4()),
                    member_id=member,
                    confirmation_id=original.confirmation_id,
                    calculation_id=original.calculation_id,
                    snapshot=original.snapshot,
                )
                for _ in range(1000)
            ]
        )
    response = await client.post(
        f"{ROOT}/members/{member}/diet-period-analysis",
        headers=headers,
        json={"period_days": 1, "end_date": "2026-10-07"},
    )
    assert response.status_code == 422 and response.json()["code"] == "period_limit_exceeded", response.text

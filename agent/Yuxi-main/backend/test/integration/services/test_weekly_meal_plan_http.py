"""隔离 PostgreSQL 与真实 HTTP 验证多日餐单归属、幂等和完整摘要。"""

from datetime import datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import delete, select, text

from test.integration.services.test_schema_migration_version import _create_isolated_manager, _drop_isolated_schema
from test.integration.services.test_health_family_profile_http import family_profile_http  # noqa: F401
from test.integration.services.test_health_family_profile_http import ensure_live_api_schema  # noqa: F401
from test.integration.services.test_health_family_profile_http import cleanup_test_sandboxes  # noqa: F401
from test.integration.services.test_health_family_profile_http import cleanup_test_knowledge_resources  # noqa: F401
from yuxi.storage.postgres.models_business import Conversation, Project
from yuxi.storage.postgres.models_health import (
    FamilyMember,
    HealthConsultation,
    HealthFamilyProfileLink,
    HealthGrant,
    HealthDailyArrangement,
    HealthWeeklyMealPlan,
)
from yuxi.utils.datetime_utils import utc_now_naive

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_weekly_table_creation_is_idempotent():
    """新健康表能在隔离 PostgreSQL 中重复创建而不删除既有记录。"""
    schema, admin_engine, engine, manager = await _create_isolated_manager("pytest_weekly_schema")
    try:
        await manager.create_business_tables()
        await manager.create_health_tables()
        await manager.create_health_tables()
        async with engine.begin() as connection:
            count = await connection.scalar(
                text(
                    "SELECT count(*) FROM information_schema.tables WHERE table_schema=:schema "
                    "AND table_name='health_weekly_meal_plan'"
                ),
                {"schema": schema},
            )
            assert count == 1
    finally:
        await _drop_isolated_schema(schema, admin_engine, engine)


async def test_weekly_http_saves_one_group_and_rejects_partial_or_other_family(
    family_profile_http,  # noqa: F811
    monkeypatch,
):
    """七日请求只有完整就绪才返回摘要，同键重放与异人回读均受约束。"""
    from yuxi.services import weekly_meal_plan_service as weekly

    client, sessions, users = family_profile_http
    response = await client.post("/api/family", headers=users["self"], json={"name": "合成家庭"})
    assert response.status_code == 200, response.text
    family = response.json()
    source_id = next(member["id"] for member in family["members"] if member["is_self"])
    member_id, project_id, thread_id = [str(uuid4()) for _ in range(3)]
    async with sessions.begin() as session:
        session.add(FamilyMember(id=member_id, owner_uid="self", display_name="合成成员", relationship_label="本人"))
        session.add(HealthGrant(member_id=member_id, actor_uid="self", scopes=["ai_use", "profile_view"]))
        session.add(
            HealthFamilyProfileLink(
                member_id=member_id, source_member_id=source_id, family_id=family["id"], actor_uid="self"
            )
        )
        session.add(
            Project(
                id=project_id,
                uid="self",
                selection_status="implicit",
                directory_mode="managed",
                workdir_path=f"projects/{project_id}",
            )
        )
        await session.flush()
        conversation = Conversation(
            uid="self", thread_id=thread_id, agent_id="health-consultation", project_id=project_id
        )
        session.add(conversation)
        await session.flush()
        session.add(
            HealthConsultation(
                conversation_id=conversation.id, member_id=member_id, actor_uid="self", request_id=str(uuid4())
            )
        )

    starts = []
    ready = set()
    refs = {}

    async def start(_uid, _family, data):
        value = data.date.isoformat()
        starts.append(value)
        refs[value] = {"id": str(uuid4()), "version": 1}
        async with sessions.begin() as session:
            session.add(
                HealthDailyArrangement(
                    id=refs[value]["id"],
                    actor_uid="self",
                    family_id=family["id"],
                    plan_date=data.date,
                    version=1,
                    status="generating",
                    request_id=str(data.client_request_id),
                    selection={},
                    sources={},
                    snapshot={},
                )
            )
        return {"status": "generating"}

    async def read(_uid, _family, day):
        value = day.isoformat()
        return {
            "status": "ready" if value in ready else "generating",
            "id": refs[value]["id"],
            "version": refs[value]["version"],
            "date": value,
            "meals": [{"type": meal, "dishes": [{"name": f"合成{meal}"}]} for meal in ("breakfast", "lunch", "dinner")]
            if value in ready
            else [],
        }

    monkeypatch.setattr(weekly, "start_daily_arrangement", start)
    monkeypatch.setattr(weekly, "read_daily_arrangement", read)
    day = (datetime.now(ZoneInfo("Asia/Shanghai")).date() + timedelta(days=1)).isoformat()
    key = str(uuid4())
    path = f"/api/family/{family['id']}/weekly-meal-plans"
    payload = {
        "client_request_id": key,
        "thread_id": thread_id,
        "start_date": day,
        "day_count": 2,
        "question": "安排明天起两天三餐",
    }
    response = await client.post(path, headers={**users["self"], "Idempotency-Key": key}, json=payload)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["status"] == "generating" and result["days"] == [] and len(starts) == 2
    group_id = result["group_id"]

    ready.add(day)
    response = await client.get(f"{path}/{group_id}", headers=users["self"], params={"thread_id": thread_id})
    assert response.status_code == 200 and response.json()["completed_days"] == 1
    assert response.json()["days"] == []
    ready.add((datetime.fromisoformat(day) + timedelta(days=1)).date().isoformat())
    response = await client.get(f"{path}/{group_id}", headers=users["self"], params={"thread_id": thread_id})
    assert response.status_code == 200 and len(response.json()["days"]) == 2
    assert len(response.json()["days"][0]["meals"]) == 3
    detail = await client.get(f"{path}/{group_id}/days/{day}", headers=users["self"], params={"thread_id": thread_id})
    assert detail.status_code == 200 and detail.json()["meals"][0]["dishes"][0]["name"] == "合成breakfast"
    assert (
        await client.get(f"{path}/{group_id}", headers=users["other"], params={"thread_id": thread_id})
    ).status_code == 404

    response = await client.post(path, headers={**users["self"], "Idempotency-Key": key}, json=payload)
    assert response.status_code == 200 and response.json()["group_id"] == group_id
    async with sessions() as session:
        assert len((await session.scalars(select(HealthWeeklyMealPlan))).all()) == 1

    changed = {**payload, "day_count": 3, "question": "安排明天起三天三餐"}
    response = await client.post(path, headers={**users["self"], "Idempotency-Key": key}, json=changed)
    assert response.status_code == 409

    restricted = {**payload, "client_request_id": str(uuid4()), "question": "安排两天三餐，不要花生"}
    response = await client.post(
        path, headers={**users["self"], "Idempotency-Key": restricted["client_request_id"]}, json=restricted
    )
    assert response.status_code == 422 and response.json()["code"] == "weekly_profile_review_required"
    assert len(starts) == 2
    for question in ("安排两天三餐，少盐", "安排两天三餐，不加花生", "给我安排两天三餐"):
        rejected = {**payload, "client_request_id": str(uuid4()), "question": question}
        response = await client.post(
            path, headers={**users["self"], "Idempotency-Key": rejected["client_request_id"]}, json=rejected
        )
        assert response.status_code == 422 and response.json()["code"] == "weekly_profile_review_required"
    mismatch = {**payload, "client_request_id": str(uuid4()), "day_count": 3}
    response = await client.post(
        path, headers={**users["self"], "Idempotency-Key": mismatch["client_request_id"]}, json=mismatch
    )
    assert response.status_code == 422 and response.json()["code"] == "weekly_request_mismatch"
    assert len(starts) == 2

    refs[day]["version"] = 2
    response = await client.get(f"{path}/{group_id}", headers=users["self"], params={"thread_id": thread_id})
    assert response.status_code == 200 and response.json()["status"] == "stale" and response.json()["days"] == []
    assert (
        await client.get(f"{path}/{group_id}/days/{day}", headers=users["self"], params={"thread_id": thread_id})
    ).status_code == 409

    refs[day]["version"] = 1
    missing_day = (datetime.fromisoformat(day) + timedelta(days=1)).date()
    async with sessions.begin() as session:
        group = await session.get(HealthWeeklyMealPlan, group_id)
        group.day_refs = {day: group.day_refs[day]}
        group.status = "initializing"
        group.updated_at = utc_now_naive() - timedelta(minutes=2)
        await session.execute(delete(HealthDailyArrangement).where(HealthDailyArrangement.plan_date == missing_day))
    response = await client.get(f"{path}/{group_id}", headers=users["self"], params={"thread_id": thread_id})
    assert response.status_code == 200 and response.json()["status"] == "failed"
    response = await client.post(f"{path}/{group_id}/retry", headers=users["self"], params={"thread_id": thread_id})
    assert response.status_code == 200 and response.json()["status"] == "ready"
    assert starts == [day, missing_day.isoformat(), missing_day.isoformat()]

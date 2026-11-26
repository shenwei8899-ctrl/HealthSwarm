"""真实 HTTP/PG 验证旧资料失效仍可回读归档，权限错误保持拒绝。"""

# ruff: noqa: F401,F811
from copy import deepcopy
from uuid import uuid4

import pytest
from sqlalchemy import select

from test.integration.services.test_meal_roster_http import setup_rows
from test.integration.services.test_onboarding_preparation_http import (
    family_profile_http,
    ensure_live_api_schema,
    cleanup_test_sandboxes,
    cleanup_test_knowledge_resources,
    isolate_delivery,
)
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.services.reference_meal_plan_types import REFERENCE_CATALOG_CHAIN_VERSION
from yuxi.storage.postgres.models_health import HealthDailyMealPlan, HealthInitialPlanPreview, HealthFamilyProfileLink

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def source_error(fixture, monkeypatch, source_kind, code, status):
    """保存合成共享餐单，只替代来源校验的指定失效结果。"""
    from yuxi.services import reference_meal_plan_service, meal_dish_service

    client, sessions, users = fixture
    family, _, _, profile, today = await setup_rows(fixture)
    async with sessions.begin() as db:
        row = await db.scalar(select(HealthDailyMealPlan).where(HealthDailyMealPlan.plan_date == today))
        archived = deepcopy(row.archive_meals["lunch"])
        ref = {"kind": source_kind, "id": str(uuid4()), "member_ids": [profile["selfMemberId"]]}
        row.meal_sources = {"lunch": ref}
        row.archive_meals = {"lunch": archived}
        if source_kind == "reference":
            link = await db.scalar(
                select(HealthFamilyProfileLink).where(
                    HealthFamilyProfileLink.source_member_id == profile["selfMemberId"]
                )
            )
            db.add(
                HealthInitialPlanPreview(
                    id=ref["id"],
                    actor_uid="self",
                    member_id=link.member_id,
                    selection={"family_id": family["id"], "plan_date": str(today)},
                    snapshot={"catalog_chain_version": REFERENCE_CATALOG_CHAIN_VERSION, "meals": [archived]},
                )
            )

    async def changed(*args, **kwargs):
        raise HealthVisionError(code, "合成来源校验失败", status)

    monkeypatch.setattr(reference_meal_plan_service, "read_reference_plan_in_session", changed)
    monkeypatch.setattr(meal_dish_service, "selected_source", changed)
    return client, sessions, users, family, today, archived, ref


@pytest.mark.parametrize("source_kind", ["reference", "selection"])
@pytest.mark.parametrize("code,status", [("memory_changed", 409), ("profile_source_changed", 410)])
async def test_changed_context_keeps_saved_menu_and_requires_regeneration(
    family_profile_http, monkeypatch, source_kind, code, status
):
    client, sessions, users, family, today, archived, ref = await source_error(
        family_profile_http, monkeypatch, source_kind, code, status
    )
    response = await client.get(f"/api/family/{family['id']}/daily-meal-plans/{today}", headers=users["self"])
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["status"] == "ready" and result["needs_regeneration"] == ["lunch"]
    assert result["meals"][0]["meal"] == archived
    assert result["meals"][0]["purchase_ready"] is False
    assert result["purchase_options"] == []
    assert result["regeneration_participants"]["lunch"] == ref["member_ids"]
    async with sessions() as db:
        row = await db.scalar(select(HealthDailyMealPlan).where(HealthDailyMealPlan.plan_date == today))
        assert row.version == 1 and row.meal_sources == {"lunch": ref}
        assert row.archive_meals == {"lunch": archived}
    foreign = await client.get(f"/api/family/{family['id']}/daily-meal-plans/{today}", headers=users["other"])
    assert foreign.status_code == 404


@pytest.mark.parametrize("source_kind", ["reference", "selection"])
@pytest.mark.parametrize("code,status", [("forbidden", 403), ("not_found", 404), ("reference_receipt_invalid", 409)])
async def test_access_and_receipt_errors_do_not_expose_archive(
    family_profile_http, monkeypatch, source_kind, code, status
):
    client, _, users, family, today, _, _ = await source_error(
        family_profile_http, monkeypatch, source_kind, code, status
    )
    response = await client.get(f"/api/family/{family['id']}/daily-meal-plans/{today}", headers=users["self"])
    assert response.status_code == status
    assert "meals" not in response.json()

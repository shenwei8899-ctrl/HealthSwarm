"""真实HTTP及PG验证单餐分析授权、版本与有效来源。"""

from copy import deepcopy
from uuid import uuid4

import pytest

from test.integration.services.test_health_vision_http import ROOT, create_member, confirmation, health_http  # noqa: F401
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_health import DietLog, VisionDraft

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def confirm_analysis_meal(client, headers, admin, member, *, eaten_at="2026-10-07T12:00:00+08:00", revised=False):
    """独立手算：150g乘0.4，200kcal/100g得120kcal；钠未知。"""
    food = await client.post(
        f"{ROOT}/foods",
        headers=admin,
        json={
            "record_code": str(uuid4()),
            "name": "合成分析食品",
            "cooking_state": "熟",
            "source": "独立合成手算",
            "license": "仅测试",
            "edition": "v1",
            "dataset_version": "test-analysis-v1",
            "nutrients": {
                "energy_kcal": "200",
                "protein_g": "10",
                "fat_g": "5",
                "carbohydrate_g": "25",
                "sodium_mg": None,
            },
        },
    )
    assert food.status_code == 201, food.text
    draft = await client.post(
        f"{ROOT}/manual-drafts",
        headers=headers,
        json={
            "member_id": member,
            "kind": "meal",
            "meal": {
                "meal_type": "lunch",
                "eaten_at": eaten_at,
                "items": [
                    {
                        "item_id": str(uuid4()),
                        "name": "合成分析食品",
                        "food_id": food.json()["id"],
                        "grams": "150",
                        "share_ratio": "0.4",
                        "portion_source": "weighed",
                    }
                ],
            },
        },
    )
    assert draft.status_code == 201, draft.text
    path = f"{ROOT}/meal-drafts/{draft.json()['id']}"
    version = 1
    if revised:
        changed = await client.patch(
            path,
            headers={**headers, "If-Match": '"1"'},
            json={"version": 1, "reason": "合成确认版本回归", "meal": draft.json()["payload"]},
        )
        assert changed.status_code == 200 and changed.json()["version"] == 2, changed.text
        version = 2
    calculation = await client.post(f"{path}/calculate", headers=headers, json={"version": version})
    assert calculation.status_code == 200, calculation.text
    data, key = confirmation(
        version=version, calculation_id=calculation.json()["calculation_id"], accept_incomplete=True
    )
    accepted = await client.post(f"{path}/confirm", headers={**headers, **key}, json=data)
    assert accepted.status_code == 200, accepted.text
    records = (await client.get(f"{ROOT}/members/{member}/diet-logs", headers=headers)).json()
    return records[0], draft.json()["id"]


async def test_diet_log_list_exposes_actual_confirmation_version_for_analysis_and_feedback(health_http):  # noqa: F811
    """真实更正后确认版本为2，列表选择可直接分析与绑定反馈且旧版本拒绝。"""
    client, users = health_http
    owner, admin = users[0]["headers"], users[2]["headers"]
    member = await create_member(client, owner)
    record, _ = await confirm_analysis_meal(client, owner, admin, member, revised=True)
    assert record["source_version"] == 2
    selection = {"record_id": record["id"], "source_version": record["source_version"]}
    analysis = await client.post(f"{ROOT}/members/{member}/diet-analysis", headers=owner, json=selection)
    assert analysis.status_code == 200 and analysis.json()["source"]["source_version"] == 2, analysis.text
    feedback_url = f"{ROOT}/diet-logs/{record['id']}/feedback-conversation"
    bound = await client.post(
        feedback_url,
        headers=owner,
        json={"client_request_id": str(uuid4()), "source_version": record["source_version"]},
    )
    assert bound.status_code == 201 and bound.json()["feedback_selection"] == selection, bound.text
    stale = await client.post(
        feedback_url, headers=owner, json={"client_request_id": str(uuid4()), "source_version": 1}
    )
    assert stale.status_code == 409 and stale.json()["code"] == "version_conflict", stale.text
    denied = await client.get(f"{ROOT}/members/{member}/diet-logs", headers=users[1]["headers"])
    assert denied.status_code == 404 and record["id"] not in denied.text


async def test_analysis_uses_confirmed_snapshot_and_blocks_foreign_retracted_or_stale_sources(health_http):  # noqa: F811
    """无模型事实分析与来源变更均走真实成员授权及PG记录。"""
    client, users = health_http
    headers, admin = users[0]["headers"], users[2]["headers"]
    member = await create_member(client, headers)
    record, draft_id = await confirm_analysis_meal(client, headers, admin, member)
    original = deepcopy(record["snapshot"])
    endpoint = f"{ROOT}/members/{member}/diet-analysis"
    data = {"record_id": record["id"], "source_version": 1}
    result = await client.post(endpoint, headers=headers, json=data)
    assert result.status_code == 200, result.text
    analysis = result.json()
    assert analysis["nutrition"]["totals"] == {
        "energy_kcal": "120.00",
        "protein_g": "6.00",
        "fat_g": "3.00",
        "carbohydrate_g": "15.00",
        "sodium_mg": None,
    }
    assert analysis["coverage"]["known_nutrients"] == 4
    assert analysis["items"][0]["eaten_grams"] == "60.00" or analysis["items"][0]["eaten_grams"] == "60.0"
    assert analysis["source"]["source_version"] == 1 and analysis["member_id"] == member
    assert analysis["personal_target"] is None and analysis["professional_review"] == "not_reviewed"
    for user in (users[1], users[2]):
        assert (await client.post(endpoint, headers=user["headers"], json=data)).status_code == 404
    other_member = await create_member(client, headers)
    assert (
        await client.post(f"{ROOT}/members/{other_member}/diet-analysis", headers=headers, json=data)
    ).status_code == 404
    assert (await client.post(endpoint, headers=headers, json={**data, "source_version": 2})).status_code == 409
    assert (await client.post(endpoint, headers=headers, json={**data, "energy_kcal": "1"})).status_code == 422
    binding_key = str(uuid4())
    assert (
        await client.put(
            f"{ROOT}/members/{member}/grants",
            headers=headers,
            json={"actor_uid": users[0]["uid"], "scopes": ["diet_edit", "ai_use", "profile_edit"]},
        )
    ).status_code == 200
    bound = await client.post(
        f"{ROOT}/members/{member}/diet-analyst", headers=headers, json={"client_request_id": binding_key}
    )
    assert bound.status_code == 201, bound.text
    assert bound.json()["agent_slug"] == "health-diet-analyst"
    assert (
        await client.post(
            f"{ROOT}/members/{member}/diet-analyst", headers=headers, json={"client_request_id": binding_key}
        )
    ).json() == bound.json()
    assert (
        await client.post(
            f"{ROOT}/members/{other_member}/diet-analyst",
            headers=headers,
            json={"client_request_id": binding_key},
        )
    ).status_code == 409
    async with pg_manager.get_async_session_context() as session:
        assert (await session.get(DietLog, record["id"])).snapshot == original
        source = await session.get(VisionDraft, draft_id)
        source.review_status = "retracted"
    rejected = await client.post(endpoint, headers=headers, json=data)
    assert rejected.status_code == 410 and rejected.json()["code"] == "source_invalidated"
    async with pg_manager.get_async_session_context() as session:
        source = await session.get(VisionDraft, draft_id)
        source.review_status = "confirmed"
    revoke = await client.put(
        f"{ROOT}/members/{member}/grants", headers=headers, json={"actor_uid": users[0]["uid"], "scopes": []}
    )
    assert revoke.status_code == 200
    assert (await client.post(endpoint, headers=headers, json=data)).status_code == 404

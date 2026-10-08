"""真实HTTP与PG验证三餐草稿、版本历史、并发和成员权限。"""

import asyncio
from copy import deepcopy
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select

from test.integration.services.test_health_vision_http import ROOT, create_member, health_http  # noqa: F401
from yuxi.storage.postgres.manager import pg_manager
from yuxi.agents.context import BaseContext
from yuxi.repositories.health_consultation_repository import HealthConsultationRepository
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.storage.postgres.models_business import AgentRun, Conversation, User
from yuxi.utils.datetime_utils import utc_now_naive
from yuxi.storage.postgres.models_health import DietLog, HealthMealPlan, HealthMealPlanPreview, HealthMealPlanRevision

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def publish_planner_recipe(client, admin, name, energy="100"):
    """固定合成来源和手算营养，仅用于协议验收。"""
    source = {"source": "synthetic-planner", "license": "synthetic-test", "edition": "v1", "dataset_version": "v1"}
    food = await client.post(
        f"{ROOT}/foods",
        headers=admin,
        json={
            **source,
            "record_code": str(uuid4()),
            "name": name + "原料",
            "cooking_state": "合成",
            "nutrients": {
                "energy_kcal": energy,
                "protein_g": "10",
                "fat_g": "2",
                "carbohydrate_g": "20",
                "sodium_mg": "50",
            },
        },
    )
    assert food.status_code == 201, food.text
    recipe = await client.post(
        f"{ROOT}/recipes",
        headers=admin,
        json={
            **source,
            "record_code": str(uuid4()),
            "name": name,
            "cooking_state": "合成",
            "yield_grams": "200",
            "ingredients": [{"food_id": food.json()["id"], "grams": "200", "role": "food"}],
        },
    )
    assert recipe.status_code == 201, recipe.text
    return recipe.json()["id"]


def plan_spec(recipe):
    """三餐50、100、150克为测试输入，不是营养建议。"""
    return {
        "plan_date": "2026-10-06",
        "meals": [
            {"meal_type": kind, "dishes": [{"recipe_version_id": recipe, "grams": str(grams)}]}
            for kind, grams in zip(("breakfast", "lunch", "dinner"), (50, 100, 150))
        ],
    }


async def test_save_swap_idempotency_concurrency_history_and_private_access(health_http):  # noqa: F811
    """回读PG快照；同版本并发仅一条成功，共享成员不能读取别人的计划。"""
    client, users = health_http
    headers, admin = users[0]["headers"], users[2]["headers"]
    member = await create_member(client, headers)
    recipe = await publish_planner_recipe(client, admin, "配餐HTTP合成菜")
    replacement = await publish_planner_recipe(client, admin, "配餐HTTP换菜", "200")
    spec = plan_spec(recipe)
    preview = await client.post(f"{ROOT}/members/{member}/meal-plan-previews", headers=headers, json=spec)
    assert preview.status_code == 201, preview.text
    assert preview.json()["nutrition"]["totals"]["energy_kcal"] == "300.00"
    key = str(uuid4())
    body = {"client_request_id": key, "preview_id": preview.json()["preview_id"]}
    endpoint = f"{ROOT}/members/{member}/meal-plans"
    keyed = {**headers, "Idempotency-Key": key}
    assert (await client.post(endpoint, headers=headers, json=body)).status_code == 422
    saved = await client.post(endpoint, headers=keyed, json=body)
    assert saved.status_code == 201, saved.text
    initial = saved.json()
    plan_id = initial["plan_id"]
    assert initial["version"] == 1 and initial["personalized"] is False
    assert initial["adoption_available"] is False and initial["purchase_available"] is False
    assert (await client.post(endpoint, headers=keyed, json=body)).json() == initial
    second_preview = await client.post(f"{ROOT}/members/{member}/meal-plan-previews", headers=headers, json=spec)
    assert (
        await client.post(endpoint, headers=keyed, json={**body, "preview_id": second_preview.json()["preview_id"]})
    ).status_code == 409
    swaps = [
        {
            "client_request_id": str(uuid4()),
            "version": 1,
            "meal_type": "lunch",
            "dish_index": 0,
            "replacement": {"recipe_version_id": replacement, "grams": "100"},
            "reason": "合成换菜测试",
        }
        for _ in range(2)
    ]
    outcomes = await asyncio.gather(
        *[
            client.post(
                f"{ROOT}/meal-plans/{plan_id}/swap",
                headers={**headers, "Idempotency-Key": data["client_request_id"], "If-Match": '"1"'},
                json=data,
            )
            for data in swaps
        ]
    )
    assert sorted(r.status_code for r in outcomes) == [200, 409], [r.text for r in outcomes]
    winner = next(data for data, response in zip(swaps, outcomes) if response.status_code == 200)
    replay = await client.post(
        f"{ROOT}/meal-plans/{plan_id}/swap",
        headers={**headers, "Idempotency-Key": winner["client_request_id"], "If-Match": '"1"'},
        json=winner,
    )
    assert replay.status_code == 200 and replay.json()["version"] == 2
    assert replay.json()["nutrition"]["totals"]["energy_kcal"] == "400.00"
    assert (await client.post(endpoint, headers=keyed, json=body)).json()["version"] == 2
    read = (await client.get(f"{ROOT}/meal-plans/{plan_id}", headers=headers)).json()
    assert [r["version"] for r in read["revisions"]] == [1, 2]
    assert [r["snapshot"]["nutrition"]["totals"]["energy_kcal"] for r in read["revisions"]] == ["300.00", "400.00"]
    assert (await client.get(endpoint, headers=headers)).json()["plans"][0]["plan_id"] == plan_id
    grant = await client.put(
        f"{ROOT}/members/{member}/grants",
        headers=headers,
        json={"actor_uid": users[1]["uid"], "scopes": ["diet_edit"]},
    )
    assert grant.status_code == 200, grant.text
    for other in (users[1], users[2]):
        assert (await client.get(f"{ROOT}/meal-plans/{plan_id}", headers=other["headers"])).status_code == 404
        assert (
            await client.post(endpoint, headers={**other["headers"], "Idempotency-Key": key}, json=body)
        ).status_code == 404
    assert (await client.get(endpoint, headers=users[1]["headers"])).json()["plans"] == []
    async with pg_manager.get_async_session_context() as session:
        row = await session.get(HealthMealPlan, plan_id)
        revisions = list(
            (
                await session.scalars(select(HealthMealPlanRevision).where(HealthMealPlanRevision.plan_id == plan_id))
            ).all()
        )
        assert row.version == 2 and row.actor_uid == users[0]["uid"] and len(revisions) == 2
        assert (await session.get(HealthMealPlanPreview, preview.json()["preview_id"])).run_id is None
        assert await session.scalar(select(DietLog).where(DietLog.member_id == member)) is None
    revoked = await client.put(
        f"{ROOT}/members/{member}/grants", headers=headers, json={"actor_uid": users[0]["uid"], "scopes": []}
    )
    assert revoked.status_code == 200
    assert (await client.get(f"{ROOT}/meal-plans/{plan_id}", headers=headers)).status_code == 404


async def test_unknown_amount_invalid_recipe_role_binding_and_model_approval(health_http):  # noqa: F811
    """未知量保持空；角色线程不能跨角色重用；未审批运行不产生持久请求。"""
    client, users = health_http
    headers, admin = users[0]["headers"], users[2]["headers"]
    member = await create_member(client, headers)
    recipe = await publish_planner_recipe(client, admin, "配餐HTTP未知量")
    spec = plan_spec(recipe)
    spec["meals"][0]["dishes"][0].pop("grams")
    preview = await client.post(f"{ROOT}/members/{member}/meal-plan-previews", headers=headers, json=spec)
    assert preview.status_code == 201 and preview.json()["nutrition"]["totals"]["energy_kcal"] is None
    invalid = deepcopy(spec)
    invalid["meals"][0]["dishes"][0]["recipe_version_id"] = str(uuid4())
    response = await client.post(f"{ROOT}/members/{member}/meal-plan-previews", headers=headers, json=invalid)
    assert response.status_code == 422 and response.json()["code"] == "recipe_not_found"
    key = str(uuid4())
    bound = await client.post(f"{ROOT}/members/{member}/meal-planner", headers=headers, json={"client_request_id": key})
    assert bound.status_code == 201 and bound.json()["agent_slug"] == "health-meal-planner", bound.text
    async with pg_manager.get_async_session_context() as session:
        administrator = await session.scalar(select(User).where(User.uid == users[2]["uid"]))
        administrator.role = "superadmin"
    analytics = await client.get(
        "/api/dashboard/stats/threads", headers=admin, params={"agent_id": "health-meal-planner"}
    )
    assert analytics.status_code == 200, analytics.text
    assert analytics.json()["summary"]["total_threads"] == 0
    assert analytics.json()["top_users"] == analytics.json()["agent_distribution"] == []
    options = await client.get("/api/dashboard/conversations/options", headers=admin)
    assert options.status_code == 200, options.text
    assert not any(row["uid"] == users[0]["uid"] for row in options.json()["users"])
    assert not any(row["agent_id"] == "health-meal-planner" for row in options.json()["agents"])
    cross = await client.post(
        f"{ROOT}/members/{member}/consultations",
        headers={**headers, "Idempotency-Key": key},
        json={"client_request_id": key},
    )
    assert cross.status_code == 409
    request = str(uuid4())
    denied = await client.post(
        "/api/agent/runs",
        headers=headers,
        json={
            "query": "合成配餐",
            "agent_slug": "health-meal-planner",
            "thread_id": bound.json()["thread_id"],
            "meta": {"request_id": request},
        },
    )
    assert denied.status_code == 503, denied.text


@pytest.mark.parametrize("invalid", ["expired_lease", "wrong_worker", "wrong_conversation_role"])
async def test_running_planner_executor_rejects_invalid_ownership_in_pg(health_http, invalid):  # noqa: F811
    """真实PG执行边界在running状态下拒绝过期lease、错误worker及角色绑定。"""
    client, users = health_http
    headers = users[0]["headers"]
    member = await create_member(client, headers)
    bound = await client.post(
        f"{ROOT}/members/{member}/meal-planner", headers=headers, json={"client_request_id": str(uuid4())}
    )
    assert bound.status_code == 201, bound.text
    thread, run_id, request_id = bound.json()["thread_id"], str(uuid4()), str(uuid4())
    context = BaseContext(
        uid=users[0]["uid"], thread_id=thread, run_id=run_id, request_id=request_id, worker_id="synthetic-owner"
    )
    async with pg_manager.get_async_session_context() as session:
        conversation = await session.scalar(select(Conversation).where(Conversation.thread_id == thread))
        run = AgentRun(
            id=run_id,
            request_id=request_id,
            uid=users[0]["uid"],
            agent_slug="health-meal-planner",
            conversation_id=conversation.id,
            conversation_thread_id=thread,
            runtime_scope_id=thread,
            worker_id="synthetic-owner",
            status="running",
            lease_expires_at=utc_now_naive() + timedelta(minutes=1),
            input_payload={},
        )
        session.add(run)
        await session.flush()
        repo = HealthConsultationRepository(session)
        assert (await repo.require_attempt(context)).id == run_id
        if invalid == "expired_lease":
            run.lease_expires_at = utc_now_naive() - timedelta(seconds=1)
        elif invalid == "wrong_worker":
            context.worker_id = "synthetic-stranger"
        else:
            conversation.agent_id = "health-consultation"
        await session.flush()
        with pytest.raises(HealthVisionError, match="execution_not_owned"):
            await repo.require_attempt(context, lock=True)
        await session.rollback()  # 测试运行从未入队，精确撤销本事务的合成行与角色变动。

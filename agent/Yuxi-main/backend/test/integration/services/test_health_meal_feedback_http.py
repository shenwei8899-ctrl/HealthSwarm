"""餐次反馈通过真实 HTTP 和 PG 验证授权、并发及撤回重放。"""

import asyncio
from uuid import uuid4
import pytest
from sqlalchemy import select, func
from test.integration.services.test_health_vision_http import ROOT, create_member, confirmation, health_http  # noqa: F401
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_health import MealFeedback, MealFeedbackRevision, HealthMemoryFact, VisionDraft

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def confirmed_meal(client, headers, member):
    """人工创建并确认合成餐次，避免依赖识图供应商。"""
    response = await client.post(
        f"{ROOT}/manual-drafts",
        headers=headers,
        json={
            "member_id": member,
            "kind": "meal",
            "meal": {
                "meal_type": "lunch",
                "eaten_at": "2026-10-06T12:00:00+08:00",
                "items": [{"item_id": str(uuid4()), "name": "合成食物"}],
            },
        },
    )
    assert response.status_code == 201, response.text
    draft = response.json()["id"]
    path = f"{ROOT}/meal-drafts/{draft}"
    calculation = await client.post(f"{path}/calculate", headers=headers, json={"version": 1})
    assert calculation.status_code == 200
    body, keys = confirmation(calculation_id=calculation.json()["calculation_id"], accept_incomplete=True)
    saved = await client.post(f"{path}/confirm", headers={**headers, **keys}, json=body)
    assert saved.status_code == 200, saved.text
    return saved.json()["target_ids"][0], draft


def feedback_headers(headers, body):
    """协议头与提交版本一致。"""
    return {**headers, "Idempotency-Key": body["client_request_id"], "If-Match": f'"{body["version"]}"'}


async def test_meal_feedback_private_versions_revoke_and_replay(health_http):  # noqa: F811
    """外账号和管理员不能越权；旧保存请求在撤回后不复活。"""
    client, users = health_http
    headers, uid = users[0]["headers"], users[0]["uid"]
    member = await create_member(client, headers)
    record, draft = await confirmed_meal(client, headers, member)
    path = f"{ROOT}/diet-logs/{record}/feedback"
    assert (await client.get(path, headers=headers)).json()["feedback"] is None
    body = {
        "client_request_id": str(uuid4()),
        "version": 0,
        "tags": ["too_salty"],
        "consumption": "half",
        "comment": "这顿偏咸",
    }
    for actor in users[1:]:
        assert (await client.get(path, headers=actor["headers"])).status_code == 404
        assert (await client.put(path, headers=feedback_headers(actor["headers"], body), json=body)).status_code == 404
    assert (await client.put(path, headers=headers, json=body)).status_code == 422
    first = await client.put(path, headers=feedback_headers(headers, body), json=body)
    assert first.status_code == 200, first.text
    assert first.json()["version"] == 1 and first.json()["scope"] == "single_meal"
    assert first.json()["formal_profile"] is False
    assert (await client.put(path, headers=feedback_headers(headers, body), json=body)).json()["version"] == 1
    changed = {**body, "comment": "同键不同内容"}
    assert (await client.put(path, headers=feedback_headers(headers, changed), json=changed)).status_code == 409
    edited = {**body, "version": 1, "comment": "已核对这顿体验", "client_request_id": str(uuid4())}
    assert (await client.put(path, headers=feedback_headers(headers, edited), json=edited)).json()["version"] == 2
    stale = {**edited, "client_request_id": str(uuid4())}
    assert (await client.put(path, headers=feedback_headers(headers, stale), json=stale)).status_code == 409
    revoke = {"client_request_id": str(uuid4()), "version": 2}
    for _ in range(2):
        result = await client.post(f"{path}/revoke", headers=feedback_headers(headers, revoke), json=revoke)
        assert result.status_code == 200 and result.json()["version"] == 3 and result.json()["details"] is None
    replay = await client.put(path, headers=feedback_headers(headers, body), json=body)
    assert replay.json()["status"] == "revoked" and replay.json()["version"] == 3
    history = (await client.get(path, headers=headers)).json()
    assert [row["version"] for row in history["revisions"]] == [1, 2, 3]
    async with pg_manager.get_async_session_context() as session:
        row = await session.get(MealFeedback, first.json()["feedback_id"])
        assert row.diet_log_id == record and row.member_id == member and row.actor_uid == uid
        assert row.status == "revoked" and row.details["consumption"] == "half"
        assert (
            await session.scalar(
                select(func.count()).select_from(MealFeedbackRevision).where(MealFeedbackRevision.feedback_id == row.id)
            )
            == 3
        )
        assert await session.scalar(select(HealthMemoryFact).where(HealthMemoryFact.member_id == member)) is None
    renewed = {**body, "version": 3, "client_request_id": str(uuid4())}
    assert (await client.put(path, headers=feedback_headers(headers, renewed), json=renewed)).json()["version"] == 4
    async with pg_manager.get_async_session_context() as session:
        source = await session.get(VisionDraft, draft)
        source.review_status = "invalidated"
    assert (await client.get(path, headers=headers)).status_code == 410
    assert (await client.put(path, headers=feedback_headers(headers, renewed), json=renewed)).status_code == 410


async def test_meal_feedback_concurrency_and_validation(health_http):  # noqa: F811
    """并发初次提交只发布一版，空及伪造输入拒绝。"""
    client, users = health_http
    headers = users[0]["headers"]
    member = await create_member(client, headers)
    record, _ = await confirmed_meal(client, headers, member)
    path = f"{ROOT}/diet-logs/{record}/feedback"
    base = {"client_request_id": str(uuid4()), "version": 0, "comment": "合成单餐体验"}
    for extra in (
        {"comment": " "},
        {"tags": ["too_salty", "too_salty"]},
        {"member_id": member},
        {"tags": ["diagnosis"]},
    ):
        data = {**base, **extra}
        assert (await client.put(path, headers=feedback_headers(headers, data), json=data)).status_code == 422
    bodies = [{**base, "client_request_id": str(uuid4())} for _ in range(2)]
    result = await asyncio.gather(
        *[client.put(path, headers=feedback_headers(headers, body), json=body) for body in bodies]
    )
    assert sorted(row.status_code for row in result) == [200, 409]
    history = (await client.get(path, headers=headers)).json()
    assert len(history["revisions"]) == 1
    # 授予可见同一餐次的账号，反馈仍按账号私有存储。
    grant = await client.put(
        f"{ROOT}/members/{member}/grants", headers=headers, json={"actor_uid": users[1]["uid"], "scopes": ["diet_edit"]}
    )
    assert grant.status_code == 200
    assert (await client.get(path, headers=users[1]["headers"])).json()["feedback"] is None
    await client.put(
        f"{ROOT}/members/{member}/grants", headers=headers, json={"actor_uid": users[0]["uid"], "scopes": []}
    )
    assert (await client.get(path, headers=headers)).status_code == 404

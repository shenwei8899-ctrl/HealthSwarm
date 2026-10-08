"""真实HTTP和PG验证用户显式选餐与不可变版本绑定。"""

from uuid import uuid4

import pytest
from sqlalchemy import select

from test.integration.services.test_health_diet_analysis_http import confirm_analysis_meal
from test.integration.services.test_health_vision_http import ROOT, create_member, health_http  # noqa: F401
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_business import Conversation
from yuxi.storage.postgres.models_health import HealthFeedbackConversation, VisionDraft

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_selected_meal_binding_is_owned_immutable_and_current(health_http):  # noqa: F811
    """同键不能换餐、成员或模式；metadata不改变选餐，确认更正后入口失效。"""
    client, users = health_http
    headers, foreign, admin = users[0]["headers"], users[1]["headers"], users[2]["headers"]
    member = await create_member(client, headers)
    record, draft = await confirm_analysis_meal(client, headers, admin, member)
    other, _ = await confirm_analysis_meal(client, headers, admin, member)
    data = {"client_request_id": str(uuid4()), "source_version": 1}
    url = f"{ROOT}/diet-logs/{record['id']}/feedback-conversation"
    bound = await client.post(url, headers=headers, json=data)
    assert bound.status_code == 201, bound.text
    assert bound.json()["feedback_selection"] == {"record_id": record["id"], "source_version": 1}
    assert (await client.post(url, headers=headers, json=data)).json() == bound.json()
    wrong = await client.post(f"{ROOT}/diet-logs/{other['id']}/feedback-conversation", headers=headers, json=data)
    assert wrong.status_code == 409 and wrong.json()["code"] == "request_conflict", wrong.text
    ordinary = await client.post(
        f"{ROOT}/members/{member}/diet-analyst",
        headers=headers,
        json={
            "client_request_id": data["client_request_id"],
        },
    )
    assert ordinary.status_code == 409, ordinary.text
    for actor in (foreign, admin):
        assert (
            await client.post(url, headers=actor, json={**data, "client_request_id": str(uuid4())})
        ).status_code == 404
    assert (
        await client.post(
            url,
            headers=headers,
            json={
                "client_request_id": str(uuid4()),
                "source_version": 2,
            },
        )
    ).status_code == 409
    assert (await client.post(url, headers=headers, json={**data, "member_id": member})).status_code == 422
    async with pg_manager.get_async_session_context() as session:
        conversation = await session.scalar(
            select(Conversation).where(Conversation.thread_id == bound.json()["thread_id"])
        )
        selected = await session.get(HealthFeedbackConversation, conversation.id)
        assert selected.diet_log_id == record["id"] and selected.source_version == 1
        conversation.extra_metadata = {"diet_log_id": other["id"], "source_version": 999}
    assert (await client.post(url, headers=headers, json=data)).json()["feedback_selection"]["record_id"] == record[
        "id"
    ]
    async with pg_manager.get_async_session_context() as session:
        (await session.get(VisionDraft, draft)).version += 1
    changed = await client.post(url, headers=headers, json={**data, "client_request_id": str(uuid4())})
    assert changed.status_code == 410 and changed.json()["code"] == "source_invalidated", changed.text
    assert (await client.get(f"{ROOT}/diet-logs/{record['id']}/feedback", headers=headers)).status_code == 410

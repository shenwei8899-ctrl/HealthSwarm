"""健康角色普通入口及报告确认成员锁定的真实浏览器和 PG 验收。"""

import os
from pathlib import Path

import pytest
from sqlalchemy import select

from test.e2e.test_health_family_profile_ui import wait_for_browser, write_control
from test.integration.services.test_health_vision_http import ROOT, field, health_http  # noqa: F401
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_business import Conversation
from yuxi.storage.postgres.models_health import HealthObservation, VisionConfirmation, VisionDraft

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.e2e,
    pytest.mark.slow,
    pytest.mark.skipif(os.getenv("HEALTH_CONSULTATION_E2E_ISOLATED") != "true", reason="仅在隔离合成槽位运行"),
    pytest.mark.skipif(not os.getenv("HEALTH_ENTRY_UI_CONTROL_DIR"), reason="需要真实浏览器验收控制目录"),
]


async def test_browser_health_entry_and_confirmation_member_lock(health_http):  # noqa: F811
    """普通角色选择不建健康线程，报告确认仅写入明确选定的合成成员。"""
    client, users = health_http
    actor = users[0]
    headers, uid = actor["headers"], actor["uid"]
    control = Path(os.environ["HEALTH_ENTRY_UI_CONTROL_DIR"])
    control.mkdir(parents=True, exist_ok=True)
    assert not any((control / name).exists() for name in ("context.json", "done.json", "failure.json", "verified.json"))
    members = []
    for label in ("合成确认成员甲", "合成确认成员乙"):
        created = await client.post(
            f"{ROOT}/members", headers=headers, json={"display_name": label, "authorized": True}
        )
        assert created.status_code == 201
        members.append(created.json()["id"])
    created = await client.post(
        f"{ROOT}/manual-drafts",
        headers=headers,
        json={"member_id": members[0], "kind": "report", "report": {"fields": [field()]}},
    )
    assert created.status_code == 201
    draft_id = created.json()["id"]
    write_control(
        control / "context.json",
        {
            "access_token": headers["Authorization"].removeprefix("Bearer "),
            "member_id": members[0],
            "other_member_id": members[1],
            "draft_id": draft_id,
        },
    )
    receipt = await wait_for_browser(control)
    assert receipt == {"entry_redirected": True, "selector_disabled": True, "confirmed_member_retained": True}
    async with pg_manager.get_async_session_context() as session:
        threads = list((await session.scalars(select(Conversation).where(Conversation.uid == uid))).all())
        assert threads == [], "普通入口仅导航，不允许生成未绑定的健康线程"
        draft = await session.get(VisionDraft, draft_id)
        assert draft.member_id == members[0] and draft.review_status == "confirmed" and draft.version == 1
        confirmation = await session.scalar(select(VisionConfirmation).where(VisionConfirmation.draft_id == draft_id))
        assert confirmation.member_id == members[0] and confirmation.actor_uid == uid
        observations = list(
            (await session.scalars(select(HealthObservation).where(HealthObservation.member_id.in_(members)))).all()
        )
        assert len(observations) == 1
        assert observations[0].member_id == members[0] and observations[0].confirmation_id == confirmation.id
    write_control(control / "verified.json", {"http_and_pg_verified": True, "observations": 1, "orphan_threads": 0})

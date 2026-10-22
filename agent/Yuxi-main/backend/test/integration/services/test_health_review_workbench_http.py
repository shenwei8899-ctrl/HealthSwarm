"""专业工作台在真实HTTP和PG下复用审核事实及逐成员授权。"""

from uuid import uuid4

import pytest
from sqlalchemy import select

from test.integration.services.test_health_quality_http import setup_quality, action, action_body
from test.integration.services.test_health_vision_http import ROOT, health_http  # noqa: F401
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_health import HealthReviewAction

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_workbench_return_supplement_replay_and_approval(health_http):  # noqa: F811
    """原申请退回补充，当前版本批准且重放不增加专业动作。"""
    client, users = health_http
    owner, reviewer, admin = [u["headers"] for u in users]
    data = await setup_quality(client, users)
    case = data["case"]["review_id"]
    listing = f"{ROOT}/members/{data['member']}/professional-reviews"
    detail_url = f"{ROOT}/professional-reviews/{case}/workbench"
    own = await client.get(listing, headers=owner)
    assert own.status_code == 200 and own.json()["items"][0]["status"] == "draft"
    inbox = await client.get(listing + "?inbox=true", headers=reviewer)
    assert inbox.status_code == 200 and inbox.json()["items"] == []
    assert (await client.get(detail_url, headers=admin)).status_code == 404
    assert (await client.get(listing + "?limit=0", headers=owner)).status_code == 422
    submitted = await action(client, owner, case, "submit", 1)
    inbox = await client.get(listing + "?inbox=true", headers=reviewer)
    assert [r["review_id"] for r in inbox.json()["items"]] == [case]
    loaded = await client.get(detail_url, headers=reviewer)
    assert loaded.status_code == 200, loaded.text
    assert loaded.json()["allowed_actions"] == ["return", "approve"]
    assert loaded.json()["plan_snapshot"]["nutrition"]["totals"]["energy_kcal"] == "300.00"
    await action(client, reviewer, case, "return", submitted["version"])
    applicant = await client.get(detail_url, headers=owner)
    assert applicant.json()["allowed_actions"] == ["submit"]
    await action(client, owner, case, "submit", applicant.json()["review"]["version"])
    body = action_body(4)
    body["reason"] = "synthetic:已核对补充材料"
    for _ in range(2):
        approved = await client.post(f"{ROOT}/professional-reviews/{case}/approve", headers=reviewer, json=body)
        assert approved.status_code == 200, approved.text
    detail = (await client.get(detail_url, headers=owner)).json()
    assert detail["review"]["status"] == "approved" and detail["allowed_actions"] == []
    assert detail["review"]["actions"][-1]["reason"] == body["reason"]
    async with pg_manager.get_async_session_context() as session:
        actions = list(
            (await session.scalars(select(HealthReviewAction).where(HealthReviewAction.review_id == case))).all()
        )
        assert len(actions) == 4


async def test_workbench_revocation_and_new_check_after_source_change(health_http):  # noqa: F811
    """来源变化保留失效历史，新检查产生新申请，撤权立即拒绝详情和列表。"""
    client, users = health_http
    owner, reviewer, admin = [u["headers"] for u in users]
    data = await setup_quality(client, users)
    case = data["case"]["review_id"]
    await action(client, owner, case, "submit", 1)
    profile = {**data["profile"], "version": 2, "source_version": "v2"}
    result = await client.post(
        f"{ROOT}/members/{data['member']}/external-profile-versions", headers=admin, json=profile
    )
    assert result.status_code == 201, result.text
    old = await client.get(f"{ROOT}/professional-reviews/{case}/workbench", headers=owner)
    assert old.json()["review"]["status"] == "invalidated"
    assert old.json()["allowed_actions"] == []
    check = await client.post(
        f"{ROOT}/meal-plans/{data['plan']}/quality-checks",
        headers=owner,
        json={**data["body"], "client_request_id": str(uuid4())},
    )
    assert check.status_code == 201, check.text
    replacement = await client.get(f"{ROOT}/quality-checks/{check.json()['check_id']}", headers=owner)
    assert replacement.json()["review"]["review_id"] != case
    assert replacement.json()["sources"]["profiles"][data["member"]]["version"] == 2
    revoked = await client.put(
        f"{ROOT}/members/{data['member']}/grants", headers=owner, json={"actor_uid": users[1]["uid"], "scopes": []}
    )
    assert revoked.status_code == 200
    assert (await client.get(f"{ROOT}/professional-reviews/{case}/workbench", headers=reviewer)).status_code == 404
    assert (
        await client.get(f"{ROOT}/members/{data['member']}/professional-reviews?inbox=true", headers=reviewer)
    ).status_code == 404


async def test_workbench_unknown_quality_has_no_approval_action(health_http):  # noqa: F811
    """有资格仍不能批准资料不足的工程检查，也不能查看无权其他成员。"""
    client, users = health_http
    data = await setup_quality(client, users, field="unknown")
    case = data["case"]["review_id"]
    await action(client, users[0]["headers"], case, "submit", 1)
    loaded = await client.get(f"{ROOT}/professional-reviews/{case}/workbench", headers=users[1]["headers"])
    assert loaded.json()["allowed_actions"] == ["return"]
    assert loaded.json()["check"]["safety_check"]["missing"]
    assert (
        await client.get(f"{ROOT}/members/{uuid4()}/professional-reviews", headers=users[0]["headers"])
    ).status_code == 404

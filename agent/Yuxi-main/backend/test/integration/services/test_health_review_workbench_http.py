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


async def test_lost_submit_response_replays_current_returned_state_without_resubmitting(health_http):  # noqa: F811
    """提交响应丢失后原样重放返回最新退回态，不能替用户再次提交。"""
    client, users = health_http
    owner, reviewer = users[0]["headers"], users[1]["headers"]
    data = await setup_quality(client, users)
    case = data["case"]["review_id"]
    url = f"{ROOT}/professional-reviews/{case}"
    original = action_body(1)
    submitted = await client.post(url + "/submit", headers=owner, json=original)
    assert submitted.status_code == 200 and submitted.json()["version"] == 2
    # 服务端已提交，但客户端未采用响应；期间审核人已经退回。
    returned = await action(client, reviewer, case, "return", 2)
    assert returned["status"] == "returned" and returned["version"] == 3
    replay = await client.post(url + "/submit", headers=owner, json=original)
    assert replay.status_code == 200, replay.text
    assert replay.json()["status"] == "returned" and replay.json()["version"] == 3

    changed = await client.post(url + "/submit", headers=owner, json={**original, "reason": "合成补充的新说明"})
    assert changed.status_code == 409 and changed.json()["code"] == "request_conflict"
    stale = await client.post(url + "/submit", headers=owner, json=action_body(1))
    assert stale.status_code == 409 and stale.json()["code"] == "version_conflict"
    current = await client.get(url + "/workbench", headers=owner)
    assert current.headers["Cache-Control"] == "no-store"
    assert current.json()["allowed_actions"] == ["submit"]
    assert len(current.json()["review"]["actions"]) == 2

    supplement = action_body(current.json()["review"]["version"])
    supplement.update(reason="合成补充材料后明确重新提交", evidence_refs=["synthetic:supplement-v2"])
    resubmitted = await client.post(url + "/submit", headers=owner, json=supplement)
    assert resubmitted.status_code == 200 and resubmitted.json()["version"] == 4
    final = (await client.get(url + "/workbench", headers=owner)).json()
    assert final["review"]["status"] == "pending_review" and final["allowed_actions"] == []
    async with pg_manager.get_async_session_context() as session:
        actions = list(
            await session.scalars(
                select(HealthReviewAction)
                .where(HealthReviewAction.review_id == case)
                .order_by(HealthReviewAction.version)
            )
        )
        assert [a.status for a in actions] == ["pending_review", "returned", "pending_review"]
        assert [a.version for a in actions] == [2, 3, 4]
        assert sum(a.request_id == original["client_request_id"] for a in actions) == 1
        assert actions[-1].evidence_refs == supplement["evidence_refs"]

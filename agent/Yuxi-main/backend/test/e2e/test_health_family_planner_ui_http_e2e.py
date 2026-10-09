"""家庭页面三种自然操作的真实HTTP/Worker和普通业务确认。"""

import asyncio
import json
import os
from copy import deepcopy
from http.server import ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from uuid import uuid4

import pytest

from test.e2e.test_health_consultation_e2e import collect_sse
from test.integration.services.test_health_family_planner_http import bind_family
from test.integration.services.test_health_vision_http import ROOT
from test.support import health_family_planner_replay_server as replay
from test.support.health_family_planner_ui_fixture import family_ui_facts, family_ui_fixture, require_family_ui_settled
from test.support.health_family_planner_ui_replay import family_ui_delta

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.slow,
    pytest.mark.asyncio,
    pytest.mark.skipif(os.getenv("HEALTH_CONSULTATION_E2E_ISOLATED") != "true", reason="仅独立合成槽位"),
]


@pytest.fixture(scope="session", autouse=True)
def cleanup_e2e_test_resources():
    """仅所属fixture精确清理，不登录既有账号清理其他数据。"""
    yield


async def test_family_natural_operations_preview_and_explicit_confirmation():
    """只读预览保持完整业务事实；三次确认各只写一次版本且审核不继承。"""
    original_delta = replay.replay_delta
    replay.replay_delta = family_ui_delta
    server = ThreadingHTTPServer(("0.0.0.0", 8778), replay.FamilyPlannerReplayHandler)
    Thread(target=server.serve_forever, daemon=True).start()
    generator = family_ui_fixture()
    state = None
    try:
        state = await anext(generator)
        client, users, current = state["client"], state["users"], state["current"]
        owner = users[0]["headers"]
        for member in (current["member"], current["second"]):
            assert (
                await client.post(f"{ROOT}/members/{member}/processing-consents", headers=owner, json=state["consent"])
            ).status_code == 200
        scope = (
            f"已选定处理范围：家庭配餐合成主成员（ID:{current['member']}）、"
            f"家庭配餐合成第二成员（ID:{current['second']}）"
        )
        for operation, prefix, expected_members, expected_total in (
            ("swap", "请为当前家庭餐单的早餐第1道共同菜提供安全换菜候选。", ("305.00", "66.00"), "371.00"),
            ("regeneration", "请为当前家庭餐单重新生成安全三餐预览。", ("330.00", "66.00"), "396.00"),
            (
                "participation",
                "请调整当前家庭餐单的参加成员和份量。将主成员早餐份量调整为55克，保留其他份量",
                ("305.00", "60.00"),
                "365.00",
            ),
        ):
            selected = {
                **current,
                "plan": state["plans"][operation],
                "rules": state["strict_rule"] if operation == "regeneration" else current["rules"],
            }
            before = await family_ui_facts(state)
            bound, _ = await bind_family(client, users, selected)
            assert bound.status_code == 201
            request_id = str(uuid4())
            submitted = await client.post(
                "/api/agent/runs",
                headers=owner,
                json={
                    "agent_slug": "health-meal-planner",
                    "thread_id": bound.json()["thread_id"],
                    "query": prefix + "\n" + scope,
                    "meta": {"request_id": request_id},
                },
            )
            assert submitted.status_code == 200
            run_id = submitted.json()["run_id"]
            async with asyncio.timeout(180):
                events = await collect_sse(client, owner, run_id)
            assert events[-1][0] == "end"
            result = await client.get(f"/api/agent/runs/{run_id}/result", headers=owner)
            assert result.status_code == 200 and result.json()["status"] == "completed"
            final = json.loads(result.json()["output"])
            await require_family_ui_settled(users)
            preview_facts = await family_ui_facts(state)
            assert preview_facts["plans"] == before["plans"]
            assert preview_facts["actual_diet_logs"] == preview_facts["memory_facts"] == 0
            run = next(r for r in preview_facts["runs"] if r["run_id"] == run_id)
            assert run["request_id"] == run["message"]["request_id"] == request_id
            assert run["message"]["run_id"] == run_id and run["message"]["content"] == final
            assert run["attempts"] == [
                {"attempt_id": run["attempts"][0]["attempt_id"], "outcome": "completed", "finished": True}
            ]
            assert run["manifest"]["resources"]["tools"] == [
                "get_family_plan_context",
                "preview_family_plan_swap",
                "preview_family_plan_regeneration",
                "preview_family_plan_participation",
            ]
            assert [s["slug"] for s in run["manifest"]["resources"]["skills"]] == ["family-meal-planner"]
            assert len(run["previews"]) == 1
            receipt = run["previews"][0]
            assert final["preview_id"] == receipt["preview_id"] and final["result"] == receipt["snapshot"]
            assert receipt["operation"] == operation and receipt["actor_uid"] == users[0]["uid"]
            preview = final["result"]
            target = preview["candidates"][0] if operation == "swap" else preview
            snapshot = target["plan_snapshot"]
            assert snapshot["nutrition"]["totals"]["energy_kcal"] == expected_total
            assert [
                snapshot["members"][m]["nutrition"]["totals"]["energy_kcal"]
                for m in (current["member"], current["second"])
            ] == list(expected_members)
            assert target["safety_check"]["status"] == "passed"
            body = {
                "version": 1,
                "rule_code": selected["rules"]["rule_code"],
                "rule_version": selected["rules"]["version"],
                "profile_versions": {current["member"]: 2, current["second"]: 1},
                "client_request_id": str(uuid4()),
            }
            if operation == "swap":
                body.update(meal_type="breakfast", dish_index=0, recipe_version_id=target["recipe_version_id"])
                suffix = "family-safe-swap"
            else:
                body["preview_hash"] = preview["preview_hash"]
                suffix = "family-safe-regenerate" if operation == "regeneration" else "family-participation"
                if operation == "participation":
                    body["allocations"] = deepcopy(receipt["parameters"]["allocations"])
                    body["reason"] = "用户确认合成家庭成员早餐份量调整"
            endpoint = f"{ROOT}/meal-plans/{selected['plan']}/{suffix}"
            headers = {**owner, "Idempotency-Key": body["client_request_id"], "If-Match": '"1"'}
            confirmed = await client.post(endpoint, headers=headers, json=body)
            assert confirmed.status_code == 200 and confirmed.json()["version"] == 2, confirmed.text
            retry = await client.post(endpoint, headers=headers, json=body)
            assert (
                retry.status_code == 200
                and retry.json()["quality_check"]["check_id"] == confirmed.json()["quality_check"]["check_id"]
            )
            after = await family_ui_facts(state)
            saved = after["plans"][operation]
            assert saved["version"] == 2 and [r["version"] for r in saved["revisions"]] == [1, 2]
            assert saved["revisions"][0] == before["plans"][operation]["revisions"][0]
            assert saved["snapshot"] == snapshot
            approved = state["approved"][operation]
            assert (
                next(r for r in saved["reviews"] if r["review_id"] == approved["review_id"])["status"] == "invalidated"
            )
            assert (
                next(a for a in saved["adoptions"] if a["adoption_id"] == approved["adoption_id"])["status"]
                == "invalidated"
            )
            assert any(r["status"] == "draft" for r in saved["reviews"])
            assert after["actual_diet_logs"] == after["memory_facts"] == 0
            for other in state["plans"]:
                if other != operation:
                    assert after["plans"][other] == before["plans"][other]
        evidence = await family_ui_facts(state)
        destination = Path(__file__).parents[1] / ".tmp" / "family-planner-ui-20261009"
        destination.mkdir(parents=True, exist_ok=True)
        (destination / "http-completed.json").write_text(
            json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    finally:
        if state is not None:
            destination = Path(__file__).parents[1] / ".tmp" / "family-planner-ui-20261009"
            destination.mkdir(parents=True, exist_ok=True)
            (destination / ("http-final-" + uuid4().hex + ".json")).write_text(
                json.dumps(await family_ui_facts(state), ensure_ascii=False, indent=2), encoding="utf-8"
            )
        await generator.aclose()
        replay.replay_delta = original_delta
        server.shutdown()
        server.server_close()

"""小程序普通三餐的真实HTTP与独立PG验收；不经过模型或Worker。"""

import os
from copy import deepcopy
from uuid import uuid4

import httpx
import pytest

from test.support.health_miniapp_meal_plan_fixture import (
    HTTP_BASE,
    ROOT,
    assert_plan_snapshot,
    load_state,
    login_headers,
    plan_spec,
    read_facts,
    require_isolated_slot,
    require_status,
    save_json,
    verify_business_boundary,
)
from yuxi.storage.postgres.manager import pg_manager

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.e2e,
    pytest.mark.slow,
    pytest.mark.skipif(
        os.getenv("HEALTH_CONSULTATION_E2E_ISOLATED") != "true" or os.getenv("HEALTH_MINIAPP_MEAL_PLAN_E2E") != "true",
        reason="需要独立小程序合成夹具和隔离槽位的显式运行标记",
    ),
]


@pytest.fixture(scope="session", autouse=True)
def cleanup_e2e_test_resources():
    """本轮仅由专属CLI精确清理，保留浏览器账号给页面验收。"""
    yield


async def test_plain_three_meals_save_swap_history_permissions_and_no_adoption():
    """真实入口复算、幂等收据、版本冲突及撤权，最终事实从PG回读。"""
    await require_isolated_slot()
    state = load_state()
    assert not state["cleaned"]
    save_json("http-pg-verification.json", {"passed": False, "status": "running"})
    member = state["members"]["owner"]["health_member_id"]
    uid = state["accounts"]["owner"]["uid"]
    completed = []
    try:
        async with httpx.AsyncClient(base_url=HTTP_BASE, timeout=20) as client:
            owner, other = await login_headers(client, "owner"), await login_headers(client, "browser")
            endpoint = f"{ROOT}/members/{member}/meal-plans"
            listing = await client.get(endpoint, headers=owner)
            require_status(listing, 200)
            assert listing.json() == {"plans": [], "truncated": False}
            recipes = await client.get(ROOT + "/recipes", headers=owner, params={"q": "合成"})
            require_status(recipes, 200)
            assert {row["recipe_id"] for row in state["recipes"].values()} <= {row["id"] for row in recipes.json()}
            for recipe in state["recipes"].values():
                portions = await client.get(
                    ROOT + "/portion-references", headers=owner, params={"recipe_version_id": recipe["recipe_id"]}
                )
                require_status(portions, 200)
                assert any(row["id"] == recipe["portion_id"] for row in portions.json())
            completed.append("published_recipe_and_portion_catalog")

            spec = plan_spec(state)
            preview = await client.post(f"{ROOT}/members/{member}/meal-plan-previews", headers=owner, json=spec)
            require_status(preview, 201)
            assert_plan_snapshot(state, preview.json(), swapped=False)
            facts = await read_facts(state)
            assert facts["plans"] == [] and len(facts["previews"]) == 1
            verify_business_boundary(state, facts)
            assert (await client.get(endpoint, headers=owner)).json()["plans"] == []
            completed.append("preview_only_creates_no_plan_or_actual_record")

            # 合法参考量换算与明确克数产生同一手算结果，不把份数当成克数。
            portion_spec = deepcopy(spec)
            portion_spec["meals"][0]["dishes"][0].update(
                grams=None,
                portion_reference_id=state["recipes"]["breakfast"]["portion_id"],
                portion_count="0.5",
            )
            reference_preview = await client.post(
                f"{ROOT}/members/{member}/meal-plan-previews", headers=owner, json=portion_spec
            )
            require_status(reference_preview, 201)
            assert_plan_snapshot(state, reference_preview.json(), swapped=False)

            for invalid, code in (("unpublished", "recipe_not_found"), ("wrong_portion", "portion_mapping_mismatch")):
                invalid_spec = deepcopy(portion_spec)
                dish = invalid_spec["meals"][0]["dishes"][0]
                if invalid == "unpublished":
                    dish["recipe_version_id"] = str(uuid4())
                else:
                    dish["portion_reference_id"] = state["recipes"]["lunch"]["portion_id"]
                denied = await client.post(
                    f"{ROOT}/members/{member}/meal-plan-previews", headers=owner, json=invalid_spec
                )
                require_status(denied, 422)
                assert denied.json()["code"] == code
            assert len((await read_facts(state))["previews"]) == 2
            completed.append("reference_amount_and_unpublished_or_mismatched_sources")

            key = str(uuid4())
            body = {"client_request_id": key, "preview_id": preview.json()["preview_id"]}
            keyed = {**owner, "Idempotency-Key": key}
            require_status(await client.post(endpoint, headers=owner, json=body), 422)
            first = await client.post(endpoint, headers=keyed, json=body)
            require_status(first, 201)
            repeated = await client.post(endpoint, headers=keyed, json=body)
            require_status(repeated, 201)
            assert repeated.json() == first.json()
            plan_id = first.json()["plan_id"]
            assert first.json()["version"] == 1
            assert_plan_snapshot(state, first.json(), swapped=False)
            facts = await read_facts(state)
            assert len(facts["plans"]) == 1
            assert [row["version"] for row in facts["plans"][0]["revisions"]] == [1]
            changed = await client.post(
                endpoint, headers=keyed, json={**body, "preview_id": reference_preview.json()["preview_id"]}
            )
            require_status(changed, 409)
            assert changed.json()["code"] == "request_conflict"
            completed.append("explicit_save_and_duplicate_key_only_one_initial_revision")

            swap = {
                "client_request_id": str(uuid4()),
                "version": 1,
                **state["browser_swap"],
                "reason": "合成普通餐单HTTP换菜",
            }
            swap_headers = {**owner, "Idempotency-Key": swap["client_request_id"], "If-Match": '"1"'}
            swap_path = f"{ROOT}/meal-plans/{plan_id}/swap"
            second = await client.post(swap_path, headers=swap_headers, json=swap)
            require_status(second, 200)
            replay = await client.post(swap_path, headers=swap_headers, json=swap)
            require_status(replay, 200)
            assert second.json() == replay.json() and replay.json()["version"] == 2
            assert_plan_snapshot(state, replay.json(), swapped=True)
            stale = {**swap, "client_request_id": str(uuid4())}
            rejected = await client.post(
                swap_path, headers={**swap_headers, "Idempotency-Key": stale["client_request_id"]}, json=stale
            )
            require_status(rejected, 409)
            assert rejected.json()["code"] == "version_conflict"
            detail = await client.get(f"{ROOT}/meal-plans/{plan_id}", headers=owner)
            require_status(detail, 200)
            assert [row["version"] for row in detail.json()["revisions"]] == [1, 2]
            assert_plan_snapshot(state, detail.json()["revisions"][0]["snapshot"], swapped=False)
            assert_plan_snapshot(state, detail.json()["revisions"][1]["snapshot"], swapped=True)
            assert (await client.get(endpoint, headers=owner)).json()["plans"][0]["plan_id"] == plan_id
            completed.append("swap_v1_to_v2_original_package_retry_history_and_stale_409")

            for method, path, data, extra in (
                ("GET", endpoint, None, {}),
                ("GET", f"{ROOT}/meal-plans/{plan_id}", None, {}),
                ("POST", endpoint, body, {"Idempotency-Key": key}),
                ("POST", swap_path, swap, {"Idempotency-Key": swap["client_request_id"], "If-Match": '"1"'}),
            ):
                denied = await client.request(method, path, headers={**other, **extra}, json=data)
                require_status(denied, 404)
            completed.append("foreign_account_read_save_and_swap_reject")

            # 保留本人profile_edit以便真实HTTP恢复本轮diet_edit，不能越权使用PG恢复。
            grant_path = f"{ROOT}/members/{member}/grants"
            require_status(
                await client.put(
                    grant_path, headers=owner, json={"actor_uid": uid, "scopes": ["profile_edit", "profile_view"]}
                ),
                200,
            )
            try:
                for method, path, data, extra in (
                    ("GET", endpoint, None, {}),
                    ("GET", f"{ROOT}/meal-plans/{plan_id}", None, {}),
                    ("POST", endpoint, body, {"Idempotency-Key": key}),
                    ("POST", swap_path, swap, {"Idempotency-Key": swap["client_request_id"], "If-Match": '"1"'}),
                    ("POST", f"{ROOT}/members/{member}/meal-plan-previews", spec, {}),
                ):
                    denied = await client.request(method, path, headers={**owner, **extra}, json=data)
                    require_status(denied, 404)
            finally:
                require_status(
                    await client.put(
                        grant_path,
                        headers=owner,
                        json={"actor_uid": uid, "scopes": ["profile_edit", "profile_view", "diet_edit"]},
                    ),
                    200,
                )
            completed.append("revoked_diet_edit_rejects_history_and_duplicate_writes")

        facts = await read_facts(state)
        verify_business_boundary(state, facts)
        assert facts["grants"] == state["before"]["grants"] and facts["links"] == state["before"]["links"]
        owner_plans = [row for row in facts["plans"] if row["actor_uid"] == uid]
        assert len(owner_plans) == 1
        plan = owner_plans[0]
        assert plan["plan_id"] == plan_id and plan["version"] == 2
        assert [row["request_id"] for row in plan["revisions"]] == [key, swap["client_request_id"]]
        assert_plan_snapshot(state, plan["revisions"][0]["snapshot"], swapped=False)
        assert_plan_snapshot(state, plan["snapshot"], swapped=True)
        assert plan["snapshot"] == plan["revisions"][1]["snapshot"]
        completed.append("independent_pg_final_revision_and_no_adoption_diet_log_or_agent")
        save_json("http-pg-verification.json", {"passed": True, "completed": completed, "facts": facts})
    except Exception:
        save_json(
            "http-pg-verification.json", {"passed": False, "completed": completed, "facts": await read_facts(state)}
        )
        raise
    finally:
        await pg_manager.close()

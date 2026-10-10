"""真实HTTP/PG的采购来源、全员同意、库存选择及回执边界。"""

import asyncio
import os
import subprocess
import sys
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select

from test.e2e.test_health_consultation_e2e import isolated_health, wait_until  # noqa: F401
from test.integration.services.test_health_plan_adoption_http import adopt_body, approve
from test.integration.services.test_health_quality_http import setup_quality
from test.integration.services.test_health_family_plan_adoption_http import (
    approve_family,
    selection as family_selection,
)
from test.integration.services.test_health_family_meal_plan_http import setup_family
from test.integration.services.test_health_vision_http import ROOT, health_http  # noqa: F401
from test.support.health_purchase_replay_server import MODEL
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_health import HealthConsultation, HealthMealPlanAdoption, RecipeVersion

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]
ISOLATED = pytest.mark.skipif(os.getenv("HEALTH_CONSULTATION_E2E_ISOLATED") != "true", reason="只审批隔离合成采购模型")


async def adopted_purchase(client, users, *, family=False):
    """所有专业批准与采用均经真实业务HTTP，不手写有效状态。"""
    current = await setup_family(client, users) if family else await setup_quality(client, users)
    if family:
        await approve_family(client, users, current)
        body = family_selection(current)
    else:
        await approve(client, users, current)
        body = adopt_body(current)
    adopted = await client.post(f"{ROOT}/meal-plans/{current['plan']}/adopt", headers=users[0]["headers"], json=body)
    assert adopted.status_code == 201 and adopted.json()["current"], adopted.text
    current["adoption"] = adopted.json()
    async with pg_manager.get_async_session_context() as session:
        row = await session.get(HealthMealPlanAdoption, adopted.json()["adoption_id"])
        snapshot = row.snapshot["members"][current["member"]] if family else row.snapshot
        recipe_id = snapshot["meals"][0]["dishes"][0]["recipe_version_id"]
        recipe = await session.get(RecipeVersion, recipe_id)
        food = recipe.ingredients[0]["food"]
        current["food"] = {"food_id": food["id"], "cooking_state": food["cooking_state"], "edible_grams": "40"}
    return current


def purchase_selection(current, *, confirmed=True):
    """采用版本和用户库存是显式客户端输入。"""
    row = current["adoption"]
    return {
        "adoption_id": row["adoption_id"],
        "adoption_version": row["version"],
        "plan_version": row["plan_version"],
        "inventory_confirmed": confirmed,
        "inventory": [current["food"]] if confirmed else [],
    }


async def bind_purchase(client, users, current, chosen=None, *, key=None):
    """线程创建走实际业务入口，幂等头匹配请求。"""
    key = key or str(uuid4())
    body = {"client_request_id": key, **(chosen if chosen is not None else purchase_selection(current))}
    response = await client.post(
        f"{ROOT}/members/{current['member']}/purchase-conversations",
        headers={**users[0]["headers"], "Idempotency-Key": key},
        json=body,
    )
    return response, body


async def test_purchase_business_requirements_unknown_inventory_private_source_and_version(health_http):  # noqa: F811
    client, users = health_http
    current = await adopted_purchase(client, users)
    endpoint = f"{ROOT}/members/{current['member']}/purchase-requirements"
    chosen = purchase_selection(current)
    response = await client.post(endpoint, headers=users[0]["headers"], json=chosen)
    assert response.status_code == 200, response.text
    result = response.json()
    assert [
        (item["required_grams"], item["inventory_grams"], item["net_required_grams"]) for item in result["items"]
    ] == [("300.000000", "40.000000", "260.000000")]
    assert result["purchase_available"] is False and result["sku_candidates"] == []
    assert not {"profiles", "rules", "nutrition", "medical_history", "allergies"} & set(result)
    unknown = await client.post(
        endpoint, headers=users[0]["headers"], json=purchase_selection(current, confirmed=False)
    )
    assert unknown.status_code == 200 and unknown.json()["items"][0]["net_required_grams"] is None
    for actor in users[1:]:
        denied = await client.post(endpoint, headers=actor["headers"], json=chosen)
        assert denied.status_code == 404
    wrong = await client.post(endpoint, headers=users[0]["headers"], json={**chosen, "plan_version": 2})
    assert wrong.status_code == 410 and wrong.json()["code"] == "source_invalidated"
    missing_key = await client.post(
        f"{ROOT}/members/{current['member']}/purchase-conversations",
        headers=users[0]["headers"],
        json={"client_request_id": str(uuid4()), **chosen},
    )
    assert missing_key.status_code == 422 and missing_key.json()["code"] == "request_key_mismatch"
    disabled, _ = await bind_purchase(client, users, current)
    assert disabled.status_code == 503 and disabled.json()["code"] == "purchase_unavailable"
    withdrawn = await client.post(
        f"{ROOT}/meal-plan-adoptions/{chosen['adoption_id']}/withdraw",
        headers=users[0]["headers"],
        json={"client_request_id": str(uuid4()), "version": 1, "reason": "合成采购撤销采用"},
    )
    assert withdrawn.status_code == 200
    denied = await client.post(endpoint, headers=users[0]["headers"], json=chosen)
    assert denied.status_code == 410


@pytest_asyncio.fixture
async def purchase_runtime(isolated_health):  # noqa: F811
    """只在隔离槽位启动专属本地replay，配置恢复后清理精确provider。"""
    client, users, configuration, consultation_model = isolated_health
    process = subprocess.Popen(
        [sys.executable, "test/support/health_purchase_replay_server.py"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    provider = "purchase-replay-" + uuid4().hex[:12]
    provider_created = False
    try:
        async with httpx.AsyncClient(timeout=2) as replay:

            async def ready():
                try:
                    return (await replay.get("http://localhost:8776/health")).status_code
                except httpx.HTTPError:
                    return 0

            await wait_until(ready, lambda status: status == 200)
        created = await client.post(
            "/api/system/model-providers",
            headers=users[2]["headers"],
            json={
                "provider_id": provider,
                "display_name": "Synthetic purchase only",
                "provider_type": "openai",
                "base_url": "http://api:8776/v1",
                "api_key": "synthetic-purchase-key",
                "capabilities": ["chat"],
                "enabled_models": [{"id": MODEL, "display_name": "synthetic", "type": "chat", "source": "manual"}],
                "is_enabled": True,
            },
        )
        assert created.status_code == 200, created.text
        provider_created = True
        configured = await client.put(
            f"{ROOT}/configuration",
            headers=users[2]["headers"],
            json={
                "consultation_model": consultation_model,
                "purchase_model": f"{provider}:{MODEL}",
                "policy_version": configuration["policy_version"],
                "cloud_processing_reviewed": True,
            },
        )
        assert configured.status_code == 200 and configured.json()["purchase"]["available"], configured.text
        consent = {
            "purpose": "purchase",
            "accepted": True,
            "processor": configured.json()["purchase"]["processor"],
            "policy_version": configuration["policy_version"],
        }
        yield client, users, consent
    finally:
        try:
            restored = await client.put(
                f"{ROOT}/configuration",
                headers=users[2]["headers"],
                json={
                    "consultation_model": consultation_model,
                    "policy_version": configuration["policy_version"],
                    "cloud_processing_reviewed": True,
                },
            )
            assert restored.status_code == 200 and not restored.json()["purchase"]["available"], restored.text
            if provider_created:
                deleted = await client.delete(f"/api/system/model-providers/{provider}", headers=users[2]["headers"])
                assert deleted.status_code == 200, deleted.text
        finally:
            process.terminate()
            process.wait(timeout=5)


async def consent_purchase(client, users, current, consent, *, family=False):
    """每个实际采用参与者分别明确同意新purchase用途。"""
    for member in [current["member"], current["second"]] if family else [current["member"]]:
        response = await client.post(
            f"{ROOT}/members/{member}/processing-consents", headers=users[0]["headers"], json=consent
        )
        assert response.status_code == 200, response.text


@ISOLATED
async def test_purchase_thread_all_member_consent_idempotency_and_old_selection(purchase_runtime):
    client, users, consent = purchase_runtime
    current = await adopted_purchase(client, users, family=True)
    requirements = await client.post(
        f"{ROOT}/members/{current['member']}/purchase-requirements",
        headers=users[0]["headers"],
        json=purchase_selection(current),
    )
    assert requirements.status_code == 200, requirements.text
    assert [
        (item["required_grams"], item["inventory_grams"], item["net_required_grams"])
        for item in requirements.json()["items"]
    ] == [("360.000000", "40.000000", "320.000000")]
    # 同处理方meal_plan批准也不构成purchase同意。
    current_config = (await client.get(f"{ROOT}/configuration", headers=users[2]["headers"])).json()
    approved = await client.put(
        f"{ROOT}/configuration",
        headers=users[2]["headers"],
        json={
            "consultation_model": current_config["consultation"]["model"],
            "purchase_model": current_config["purchase"]["model"],
            "meal_plan_model": current_config["purchase"]["model"],
            "policy_version": current_config["policy_version"],
            "cloud_processing_reviewed": True,
        },
    )
    assert approved.status_code == 200 and approved.json()["meal_plan"]["available"], approved.text
    assert approved.json()["meal_plan"]["processor"] == consent["processor"]
    wrong = {**consent, "purpose": "meal_plan", "processor": approved.json()["meal_plan"]["processor"]}
    await consent_purchase(client, users, current, wrong, family=True)
    denied, _ = await bind_purchase(client, users, current)
    assert denied.status_code == 403 and denied.json()["code"] == "consent_required", denied.text
    await consent_purchase(client, users, current, consent)
    denied, _ = await bind_purchase(client, users, current)
    assert denied.status_code == 403 and denied.json()["code"] == "consent_required", denied.text
    await consent_purchase(client, users, current, consent, family=True)
    key = str(uuid4())
    results = await asyncio.gather(*(bind_purchase(client, users, current, key=key) for _ in range(2)))
    assert all(response.status_code == 201 for response, _ in results)
    assert results[0][0].json() == results[1][0].json()
    changed = purchase_selection(current)
    changed["inventory"][0] = {**changed["inventory"][0], "edible_grams": "41"}
    denied, _ = await bind_purchase(client, users, current, chosen=changed, key=key)
    assert denied.status_code == 409 and denied.json()["code"] == "request_conflict"
    async with pg_manager.get_async_session_context() as session:
        binding = await session.scalar(select(HealthConsultation).where(HealthConsultation.request_id == key))
        assert binding.purchase_selection["selection"]["inventory"][0]["edible_grams"] == "40"
        assert binding.safe_planner_selection is None and len(binding.purchase_selection["source_hash"]) == 64
    revoked = await client.post(
        f"{ROOT}/members/{current['second']}/processing-consents",
        headers=users[0]["headers"],
        json={**consent, "accepted": False},
    )
    assert revoked.status_code == 200
    denied, _ = await bind_purchase(client, users, current, key=key)
    assert denied.status_code == 403 and denied.json()["code"] == "consent_required"

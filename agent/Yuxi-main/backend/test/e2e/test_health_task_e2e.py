"""明确健康入口→实际Request/Worker→当前业务结果投影与撤权。"""

import json
import os
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import select

from test.e2e.test_health_consultation_e2e import collect_sse, drain_requests, isolated_health  # noqa: F401
from test.integration.services.test_health_diet_analysis_http import confirm_analysis_meal
from test.integration.services.test_health_family_planner_http import family_runtime  # noqa: F401
from test.integration.services.test_health_family_safe_plan_http import selection as family_selection
from test.integration.services.test_health_initial_meal_plan_http import selection as initial_selection
from test.integration.services.test_health_initial_planner_http import initial_runtime  # noqa: F401
from test.integration.services.test_health_meal_planner_http import publish_planner_recipe
from test.integration.services.test_health_personal_targets_http import import_targets, read_targets
from test.integration.services.test_health_purchase_http import (
    adopted_purchase,
    consent_purchase,
    purchase_runtime,  # noqa: F401
    purchase_selection,
)
from test.integration.services.test_health_quality_http import setup_quality
from test.integration.services.test_health_safe_planner_http import safe_runtime  # noqa: F401
from test.integration.services.test_health_safe_plan_regeneration_http import selection as safe_selection
from test.integration.services.test_health_task_http import entry, owned_counts, verified_task_cleanup  # noqa: F401
from test.integration.services.test_health_vision_http import ROOT, create_member, health_http  # noqa: F401
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_business import AgentRun, AgentRunAttempt, AgentRunRequest, Message
from yuxi.storage.postgres.models_health import (
    HealthConsultation,
    HealthMealPlan,
    HealthRuleSnapshot,
    RecipeVersion,
    VisionDraft,
)
from yuxi.utils.datetime_utils import utc_now_naive

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.slow,
    pytest.mark.asyncio,
    pytest.mark.skipif(os.getenv("HEALTH_CONSULTATION_E2E_ISOLATED") != "true", reason="仅独立合成槽位"),
]


async def run_task(client, headers, bound, query, requests):
    """沿真实消息入口执行并核对SSE与PG最终Message。"""
    key = str(uuid4())
    requests.append(key)
    submitted = await client.post(
        "/api/agent/runs",
        headers=headers,
        json={
            "agent_slug": bound["agent_slug"],
            "thread_id": bound["thread_id"],
            "query": query,
            "meta": {"request_id": key},
        },
    )
    assert submitted.status_code == 200, submitted.text
    run_id = submitted.json()["run_id"]
    events = await collect_sse(client, headers, run_id)
    assert events[-1][0] == "end" and events[-1][1]["request_id"] == key
    projected = await client.get(f"{ROOT}/tasks/{key}", headers=headers)
    assert projected.status_code == 200, projected.text
    assert projected.headers["Cache-Control"] == "no-store"
    result = projected.json()
    async with pg_manager.get_async_session_context() as session:
        request = await session.scalar(select(AgentRunRequest).where(AgentRunRequest.request_id == key))
        run = await session.get(AgentRun, run_id)
        attempts = list(await session.scalars(select(AgentRunAttempt).where(AgentRunAttempt.run_id == run_id)))
        assert (
            request.dispatched_run_id == run_id
            and run.request_id == key
            and run.conversation_thread_id == bound["thread_id"]
        )
        assert attempts and any(attempt.worker_id for attempt in attempts), "必须由真实Worker获取执行所有权"
        assert result["run_id"] == run_id and result["execution_status"] == run.status
        if run.status == "completed":
            message = await session.get(Message, run.output_message_id)
            assert message.id == result["final_message_id"] and message.run_id == run_id and message.request_id == key
            assert message.delivery_status == "complete"
            if result["result"]["result_type"] not in {"needs_input", "general_education_answer"}:
                assert result["result"]["data"] == json.loads(message.content)
        else:
            assert result["result"]["result_type"] == "error" and result["final_message_id"] is None
        report = Path("test/.tmp/health-task-projection/runtime-projection.jsonl")
        report.parent.mkdir(parents=True, exist_ok=True)
        with report.open("a", encoding="utf-8") as stream:
            stream.write(
                json.dumps(
                    {
                        "request_id": key,
                        "run_id": run_id,
                        "thread_id": bound["thread_id"],
                        "task_type": result["task_type"],
                        "execution_status": run.status,
                        "worker_attempt_ids": [attempt.id for attempt in attempts],
                        "final_message_id": result["final_message_id"],
                        "result_type": result["result"]["result_type"],
                    }
                )
                + "\n"
            )
    return key, run_id, result


@pytest.mark.parametrize("kind", ["consultation", "meal_preview", "diet_analysis", "quality_check"])
async def test_four_roles_current_results_questions_failure_and_revocation(isolated_health, kind):  # noqa: F811
    """当前角色真实结果不混为临床批准；同Run指针、来源和授权均重验。"""
    client, users, configuration, consultation_model = isolated_health
    owner, admin = users[0]["headers"], users[2]["headers"]
    policy = configuration["policy_version"]
    requests, provider = [], None
    evidence_id, draft_id, selected, recipe_id = None, None, None, None
    if kind == "quality_check":
        current = await setup_quality(client, users)
        member = current["member"]
        selected = {"plan_id": current["plan"], "version": 1, "rule_code": current["body"]["rule_code"]}
    else:
        member = await create_member(client, owner)
    if kind == "diet_analysis":
        _, draft_id = await confirm_analysis_meal(client, owner, admin, member)
    try:
        purpose = {
            "consultation": "consultation",
            "meal_preview": "meal_plan",
            "diet_analysis": "diet_analysis",
            "quality_check": "quality_review",
        }[kind]
        if kind != "consultation":
            model, port, key = {
                "meal_preview": ("deterministic-meal-plan-20261006", 8768, "synthetic-planner-key"),
                "diet_analysis": ("deterministic-diet-analysis-20261007", 8769, "synthetic-analyst-key"),
                "quality_check": ("deterministic-quality-20261007", 8771, "synthetic-quality-key"),
            }[kind]
            provider = "task-replay-" + uuid4().hex[:12]
            created = await client.post(
                "/api/system/model-providers",
                headers=admin,
                json={
                    "provider_id": provider,
                    "display_name": "Synthetic task projection only",
                    "provider_type": "openai",
                    "base_url": f"http://api:{port}/v1",
                    "api_key": key,
                    "capabilities": ["chat"],
                    "enabled_models": [{"id": model, "display_name": "synthetic", "type": "chat", "source": "manual"}],
                    "is_enabled": True,
                },
            )
            assert created.status_code == 200, created.text
            configured = await client.put(
                f"{ROOT}/configuration",
                headers=admin,
                json={
                    "consultation_model": consultation_model,
                    f"{purpose}_model": f"{provider}:{model}",
                    "policy_version": policy,
                    "cloud_processing_reviewed": True,
                },
            )
            assert configured.status_code == 200 and configured.json()[purpose]["available"], configured.text
            configuration = configured.json()
        consent = {
            "purpose": purpose,
            "accepted": True,
            "processor": configuration[purpose]["processor"],
            "policy_version": policy,
        }
        assert (
            await client.post(f"{ROOT}/members/{member}/processing-consents", headers=owner, json=consent)
        ).status_code == 200
        if kind == "consultation":
            published = await client.post(
                f"{ROOT}/nutrition-evidence",
                headers=admin,
                json={
                    "source_ref": "synthetic://nutrition/source",
                    "source_version": "synthetic-v1",
                    "title": "合成营养证据",
                    "content": "合成营养证据：此文本只用于协议验收。",
                    "review_ref": "synthetic://nutrition/review",
                    "reviewed_by": "synthetic-professional-reviewer",
                    "reviewed_at": (datetime.now(UTC) - timedelta(days=1)).isoformat(),
                    "valid_until": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
                },
            )
            assert published.status_code == 201, published.text
            evidence_id = published.json()["evidence_id"]
        bound = await entry(client, owner, member, kind, selection=selected)
        assert bound.status_code == 200 and bound.json()["entry_status"] == "ready", bound.text
        modes = (
            ["evidence"]
            if kind == "consultation"
            else ["valid", "questions", "invalid" if kind != "quality_check" else "fake_approval"]
        )
        completed = None
        for mode in modes:
            token = uuid4().hex
            query = {
                "consultation": f"HEALTH_CONSULTATION_E2E:{token}:{mode}",
                "meal_preview": f"HEALTH_MEAL_PLANNER_E2E:{token}:{mode}",
                "diet_analysis": f"HEALTH_DIET_ANALYSIS_E2E:{token}:{mode}",
                "quality_check": f"QUALITY_E2E:{token}:{mode}",
            }[kind]
            if kind == "meal_preview" and mode == "valid":
                recipe_id = await publish_planner_recipe(client, admin, f"合成配餐E2E-{token}")
            request_id, run_id, result = await run_task(client, owner, bound.json(), query, requests)
            if mode in {"valid", "evidence"}:
                completed = request_id, run_id, result
                assert result["execution_status"] == "completed"
                if kind == "consultation":
                    assert result["result"]["result_type"] == "general_education_answer"
                    assert result["result"]["scope"] == "general_education"
                    assert len(result["result"]["citations"]) == 1
                else:
                    assert result["result"]["validation"] == "current_business_sources"
                    if kind == "meal_preview":
                        assert result["result"]["data"]["nutrition"]["totals"]["energy_kcal"] == "300.00"
                        assert result["result"]["data"]["personalized"] is False
                    elif kind == "diet_analysis":
                        assert result["result"]["data"]["nutrition"]["totals"]["energy_kcal"] == "120.00"
                        assert result["result"]["data"]["nutrition"]["totals"]["sodium_mg"] is None
                    else:
                        assert result["result"]["data"]["professional_review"] == "not_a_professional_decision"
            elif mode == "questions":
                assert result["execution_status"] == "completed" and result["result"]["result_type"] == "needs_input"
            else:
                assert result["execution_status"] == "failed" and result["result"]["code"] == "execution_failed"
        request_id, run_id, result = completed
        for other in users[1:]:
            assert (await client.get(f"{ROOT}/tasks/{request_id}", headers=other["headers"])).status_code == 404
        async with pg_manager.get_async_session_context() as session:
            run = await session.get(AgentRun, run_id)
            original_pointer = run.output_message_id
            run.output_message_id = None
        absent = await client.get(f"{ROOT}/tasks/{request_id}", headers=owner)
        assert absent.status_code == 409 and absent.json()["code"] == "answer_unavailable", absent.text
        async with pg_manager.get_async_session_context() as session:
            run = await session.get(AgentRun, run_id)
            run.output_message_id = original_pointer
        if kind != "consultation":
            async with pg_manager.get_async_session_context() as session:
                message = await session.get(Message, original_pointer)
                original_content = message.content
                payload = json.loads(original_content)
                message.content = json.dumps({**payload, "approved": True})
            forged = await client.get(f"{ROOT}/tasks/{request_id}", headers=owner)
            assert forged.status_code in {409, 410, 422} and "data" not in forged.json(), forged.text
            async with pg_manager.get_async_session_context() as session:
                message = await session.get(Message, original_pointer)
                message.content = original_content
        assert (
            await client.post(
                f"{ROOT}/members/{member}/processing-consents", headers=owner, json={**consent, "accepted": False}
            )
        ).status_code == 200
        withdrawn = await client.get(f"{ROOT}/tasks/{request_id}", headers=owner)
        assert withdrawn.status_code == 403 and "data" not in withdrawn.json(), withdrawn.text
        assert (
            await client.post(f"{ROOT}/members/{member}/processing-consents", headers=owner, json=consent)
        ).status_code == 200
        if evidence_id is not None:
            assert (await client.delete(f"{ROOT}/nutrition-evidence/{evidence_id}", headers=admin)).status_code == 200
            stale = await client.get(f"{ROOT}/tasks/{request_id}", headers=owner)
            assert stale.status_code == 410 and "合成科普说明" not in stale.text and "此文本" not in stale.text
        if draft_id is not None:
            async with pg_manager.get_async_session_context() as session:
                draft = await session.get(VisionDraft, draft_id)
                draft.review_status = "retracted"
            stale = await client.get(f"{ROOT}/tasks/{request_id}", headers=owner)
            assert stale.status_code == 410 and "120.00" not in stale.text, stale.text
        if recipe_id is not None:
            async with pg_manager.get_async_session_context() as session:
                recipe = await session.get(RecipeVersion, recipe_id)
                recipe.yield_grams = 400
            stale = await client.get(f"{ROOT}/tasks/{request_id}", headers=owner)
            assert stale.status_code == 410 and "300.00" not in stale.text, stale.text
        if kind == "quality_check":
            async with pg_manager.get_async_session_context() as session:
                plan = await session.get(HealthMealPlan, current["plan"])
                plan.version = 2
            stale = await client.get(f"{ROOT}/tasks/{request_id}", headers=owner)
            assert stale.status_code == 410 and "data" not in stale.json(), stale.text
    finally:
        await drain_requests(client, owner, requests)
        if provider is not None:
            reset = await client.put(
                f"{ROOT}/configuration",
                headers=admin,
                json={
                    "consultation_model": consultation_model,
                    "policy_version": policy,
                    "cloud_processing_reviewed": True,
                },
            )
            assert reset.status_code == 200, reset.text
            assert (await client.delete(f"/api/system/model-providers/{provider}", headers=admin)).status_code == 200


@pytest.mark.parametrize("family", [False, True])
async def test_initial_entry_missing_selection_then_same_key_runs_current_preview(initial_runtime, family):  # noqa: F811
    """初始范围由明确选择固定，缺选择后同键可补齐；不采用餐单。"""
    client, users, current, _ = initial_runtime
    owner, key, requests = users[0]["headers"], str(uuid4()), []
    missing = await entry(client, owner, current["member"], "initial_meal_preview", key=key)
    assert missing.status_code == 200 and missing.json()["entry_status"] == "needs_input", missing.text
    chosen = initial_selection(current, family=family)
    bound = await entry(client, owner, current["member"], "initial_meal_preview", key=key, selection=chosen)
    assert bound.status_code == 200 and bound.json()["entry_status"] == "ready", bound.text
    try:
        _, _, result = await run_task(client, owner, bound.json(), f"INITIAL_PLANNER_E2E:{uuid4().hex}:ready", requests)
        assert result["task_type"] == "initial_meal_preview" and result["result"]["result_type"] == "meal_plan_preview"
        snapshot = result["result"]["data"]["plan_snapshot"]
        assert snapshot["nutrition"]["totals"]["energy_kcal"] == ("396.00" if family else "330.00")
    finally:
        await drain_requests(client, owner, requests)


async def test_family_entry_preserves_all_member_binding_and_real_worker_result(family_runtime):  # noqa: F811
    """家庭改版沿四工具和全员来源，用户入口不替代专业批准。"""
    client, users, current, _ = family_runtime
    owner, requests = users[0]["headers"], []
    chosen = {**family_selection(current), "plan_id": current["plan"]}
    bound = await entry(client, owner, current["member"], "family_meal_revision", selection=chosen)
    assert bound.status_code == 200 and bound.json()["entry_status"] == "ready", bound.text
    try:
        _, _, result = await run_task(client, owner, bound.json(), f"FAMILY_PLANNER_E2E:{uuid4().hex}:swap", requests)
        assert (
            result["task_type"] == "family_meal_revision" and result["result"]["data"]["scope"] == "family_saved_plan"
        )
    finally:
        await drain_requests(client, owner, requests)


async def test_safe_entry_preserves_single_member_current_plan_and_worker_result(safe_runtime):  # noqa: F811
    """单成员安全改版只返回当前服务核对的只读预览。"""
    client, users, current, _ = safe_runtime
    owner, requests = users[0]["headers"], []
    chosen = {**safe_selection(current), "plan_id": current["plan"]}
    bound = await entry(client, owner, current["member"], "safe_meal_revision", selection=chosen)
    assert bound.status_code == 200 and bound.json()["entry_status"] == "ready", bound.text
    try:
        _, _, result = await run_task(client, owner, bound.json(), f"SAFE_PLANNER_E2E:{uuid4().hex}:swap", requests)
        assert (
            result["task_type"] == "safe_meal_revision"
            and result["result"]["data"]["scope"] == "single_member_saved_plan"
        )
    finally:
        await drain_requests(client, owner, requests)


@pytest.mark.parametrize("family", [False, True])
async def test_purchase_task_entry_current_receipt_unknown_inventory_and_withdrawal(purchase_runtime, family):  # noqa: F811
    """需求入口复用独立用途与全员同意，库存未知和商城未接入保持真实状态。"""
    client, users, consent = purchase_runtime
    owner, requests = users[0]["headers"], []
    current = await adopted_purchase(client, users, family=family)
    before = await owned_counts(users[0]["uid"])
    key = str(uuid4())
    missing = await entry(client, owner, current["member"], "purchase_requirements", key=key)
    assert missing.status_code == 200 and missing.json()["entry_status"] == "needs_input", missing.text
    assert await owned_counts(users[0]["uid"]) == before
    chosen = purchase_selection(current)
    no_consent = await entry(client, owner, current["member"], "purchase_requirements", key=key, selection=chosen)
    assert no_consent.status_code == 403 and no_consent.json()["code"] == "consent_required", no_consent.text
    assert await owned_counts(users[0]["uid"]) == before
    await consent_purchase(client, users, current, consent, family=family)
    bound = await entry(client, owner, current["member"], "purchase_requirements", key=key, selection=chosen)
    assert bound.status_code == 200 and bound.json()["entry_status"] == "ready", bound.text
    assert bound.json()["agent_slug"] == "health-purchase"
    repeated = await entry(client, owner, current["member"], "purchase_requirements", key=key, selection=chosen)
    assert repeated.json() == bound.json()
    changed = await entry(
        client,
        owner,
        current["member"],
        "purchase_requirements",
        key=key,
        selection=purchase_selection(current, confirmed=False),
    )
    assert changed.status_code == 409 and changed.json()["code"] == "request_conflict", changed.text
    retained, receipt_id = None, None
    try:
        for mode in ("normal", "questions", "invalid", "foreign"):
            query = f"PURCHASE_E2E:{uuid4().hex}:{mode}" + (f":{receipt_id}" if mode == "foreign" else "")
            request_id, run_id, result = await run_task(client, owner, bound.json(), query, requests)
            if mode == "normal":
                retained = request_id, run_id, result
                assert result["task_type"] == "purchase_requirements"
                assert result["result"]["result_type"] == "ingredient_requirements"
                payload = result["result"]["data"]
                receipt_id = payload["preview_id"]
                demand = payload["result"]
                assert demand["status"] == "requirements_ready"
                assert demand["items"][0]["net_required_grams"] == ("320.000000" if family else "260.000000")
                assert demand["purchase_available"] is False and demand["order_available"] is False
                assert demand["sku_candidates"] == [] and "sku_catalog" in demand["missing_dependencies"]
                assert not {"profiles", "rules", "nutrition", "medical_history", "allergies"} & set(demand)
            elif mode == "questions":
                assert result["execution_status"] == "completed" and result["result"]["result_type"] == "needs_input"
            else:
                assert result["execution_status"] == "failed" and result["result"]["code"] == "execution_failed"
        if not family:
            unknown = await entry(
                client,
                owner,
                current["member"],
                "purchase_requirements",
                selection=purchase_selection(current, confirmed=False),
            )
            assert unknown.status_code == 200, unknown.text
            _, _, result = await run_task(client, owner, unknown.json(), f"PURCHASE_E2E:{uuid4().hex}:normal", requests)
            assert (
                result["execution_status"] == "completed"
                and result["result"]["result_type"] == "ingredient_requirements"
            )
            demand = result["result"]["data"]["result"]
            assert demand["status"] == "needs_input" and demand["missing_fields"] == ["inventory_confirmation"]
            assert demand["items"][0]["net_required_grams"] is None and demand["items"][0]["inventory_grams"] is None
        request_id, run_id, _ = retained
        for actor in users[1:]:
            denied = await client.get(f"{ROOT}/tasks/{request_id}", headers=actor["headers"])
            assert denied.status_code == 404 and "data" not in denied.json()
        async with pg_manager.get_async_session_context() as session:
            run = await session.get(AgentRun, run_id)
            message = await session.get(Message, run.output_message_id)
            message_id, original = message.id, message.content
            forged = json.loads(original)
            forged["result"]["sku_candidates"] = [{"sku": "synthetic-forged"}]
            forged["result"]["order_available"] = True
            message.content = json.dumps(forged)
        invalid = await client.get(f"{ROOT}/tasks/{request_id}", headers=owner)
        assert invalid.status_code == 410 and "synthetic-forged" not in invalid.text, invalid.text
        async with pg_manager.get_async_session_context() as session:
            (await session.get(Message, message_id)).content = original
        revoked = await client.post(
            f"{ROOT}/members/{current['second'] if family else current['member']}/processing-consents",
            headers=owner,
            json={**consent, "accepted": False},
        )
        assert revoked.status_code == 200, revoked.text
        hidden = await client.get(f"{ROOT}/tasks/{request_id}", headers=owner)
        assert hidden.status_code == 403 and "data" not in hidden.json(), hidden.text
        await consent_purchase(client, users, current, consent, family=family)
        withdrawn = await client.post(
            f"{ROOT}/meal-plan-adoptions/{chosen['adoption_id']}/withdraw",
            headers=owner,
            json={"client_request_id": str(uuid4()), "version": 1, "reason": "合成Task验收撤回采用"},
        )
        assert withdrawn.status_code == 200, withdrawn.text
        stale = await client.get(f"{ROOT}/tasks/{request_id}", headers=owner)
        assert stale.status_code == 410 and "data" not in stale.json(), stale.text
    finally:
        await drain_requests(client, owner, requests)


async def test_target_analyst_task_keeps_current_targets_separate_and_invalidates_history(isolated_health):  # noqa: F811
    """目标330独立于已记录120及空白天，来源变化使Task历史同Owner失效。"""
    client, users, configuration, consultation_model = isolated_health
    owner, admin = users[0]["headers"], users[2]["headers"]
    current = await setup_quality(client, users)
    await import_targets(client, users, current)
    target = await read_targets(client, owner, current)
    assert target.status_code == 200 and target.json()["energy_kcal"] == "330", target.text
    member = current["member"]
    await confirm_analysis_meal(client, owner, admin, member)
    provider = "task-target-replay-" + uuid4().hex[:12]
    created = await client.post(
        "/api/system/model-providers",
        headers=admin,
        json={
            "provider_id": provider,
            "display_name": "Synthetic task target only",
            "provider_type": "openai",
            "base_url": "http://api:8775/v1",
            "api_key": "synthetic-target-key",
            "capabilities": ["chat"],
            "enabled_models": [
                {
                    "id": "deterministic-bound-target-20261010",
                    "display_name": "synthetic",
                    "type": "chat",
                    "source": "manual",
                }
            ],
            "is_enabled": True,
        },
    )
    assert created.status_code == 200, created.text
    requests, completed = [], []
    try:
        configured = await client.put(
            f"{ROOT}/configuration",
            headers=admin,
            json={
                "consultation_model": consultation_model,
                "diet_analysis_model": f"{provider}:deterministic-bound-target-20261010",
                "policy_version": configuration["policy_version"],
                "cloud_processing_reviewed": True,
            },
        )
        assert configured.status_code == 200 and configured.json()["diet_analysis"]["available"], configured.text
        consent = {
            "purpose": "diet_analysis",
            "accepted": True,
            "processor": configured.json()["diet_analysis"]["processor"],
            "policy_version": configuration["policy_version"],
        }
        assert (
            await client.post(f"{ROOT}/members/{member}/processing-consents", headers=owner, json=consent)
        ).status_code == 200
        chosen = {"rule_code": current["rules"]["rule_code"], "rule_version": 2, "profile_version": 2}
        bound = await entry(client, owner, member, "diet_analysis", target_selection=chosen)
        assert bound.status_code == 200 and bound.json()["entry_status"] == "ready", bound.text
        for mode in ("single", "period7", "questions", "invalid"):
            request_id, run_id, result = await run_task(
                client, owner, bound.json(), f"HEALTH_AGENT_TARGET_E2E:{uuid4().hex}:{mode}", requests
            )
            if mode == "invalid":
                assert result["execution_status"] == "failed" and result["result"]["code"] == "execution_failed"
                continue
            completed.append(request_id)
            assert result["task_type"] == "diet_analysis" and result["execution_status"] == "completed"
            if mode == "questions":
                assert result["result"]["result_type"] == "needs_input"
                continue
            payload = result["result"]["data"]
            assert payload["current_personal_targets"]["energy_kcal"] == "330"
            assert payload["current_personal_targets"]["bounds"]["energy_kcal"] == {"minimum": "330", "maximum": "330"}
            assert payload["current_personal_targets"]["applied_to_record_window"] is False
            assert payload["personal_target"] is None and payload["personalized"] is False
            assert not {"weight_kg", "height_cm", "formula", "difference"} & set(payload["current_personal_targets"])
            if mode == "single":
                assert payload["nutrition"]["totals"]["energy_kcal"] == "120.00"
                assert payload["nutrition"]["totals"]["sodium_mg"] is None
            else:
                assert payload["nutrition"]["totals"]["energy_kcal"]["recorded_total"] == "120.00"
                assert payload["nutrition"]["totals"]["sodium_mg"]["recorded_total"] is None
                assert (
                    payload["coverage"]["window_days"] == 7 and len(payload["coverage"]["dates_without_records"]) == 6
                )
                assert payload["trend"]["direction"] is None
            async with pg_manager.get_async_session_context() as session:
                run = await session.get(AgentRun, run_id)
                assert "personal_target_selection_hash" in run.input_payload["health_processing"]
        async with pg_manager.get_async_session_context() as session:
            binding = await session.scalar(
                select(HealthConsultation)
                .join(AgentRun, AgentRun.conversation_id == HealthConsultation.conversation_id)
                .where(AgentRun.id == run_id)
            )
            conversation_id, original_binding = binding.conversation_id, deepcopy(binding.personal_target_selection)
            binding.personal_target_selection = None
        try:
            hidden = await client.get(f"{ROOT}/tasks/{completed[0]}", headers=owner)
            assert hidden.status_code == 410 and "data" not in hidden.json(), hidden.text
        finally:
            async with pg_manager.get_async_session_context() as session:
                (await session.get(HealthConsultation, conversation_id)).personal_target_selection = original_binding
        async with pg_manager.get_async_session_context() as session:
            rule_id = target.json()["sources"]["rules"]["id"]
            rule = await session.get(HealthRuleSnapshot, rule_id)
            original_revoked, rule.revoked_at = rule.revoked_at, utc_now_naive()
        try:
            for request_id in completed:
                stale = await client.get(f"{ROOT}/tasks/{request_id}", headers=owner)
                assert stale.status_code == 410 and "data" not in stale.json(), stale.text
        finally:
            async with pg_manager.get_async_session_context() as session:
                (await session.get(HealthRuleSnapshot, rule_id)).revoked_at = original_revoked
    finally:
        await drain_requests(client, owner, requests)
        restored = await client.put(
            f"{ROOT}/configuration",
            headers=admin,
            json={
                "consultation_model": consultation_model,
                "policy_version": configuration["policy_version"],
                "cloud_processing_reviewed": True,
            },
        )
        assert restored.status_code == 200, restored.text
        assert (await client.delete(f"/api/system/model-providers/{provider}", headers=admin)).status_code == 200

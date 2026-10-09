"""明确开启的真实云模型、合成餐单、API/Worker及PG验收。"""

import asyncio
import json
import os
import shutil
from copy import deepcopy
from pathlib import Path
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import func, or_, select, text

from test.integration.services.test_health_quality_http import action
from test.integration.services.test_health_safe_meal_swap_http import setup_swap, swap, selection
from test.integration.services.test_health_safe_planner_http import bind_safe, safe_business_facts
from test.integration.services.test_health_vision_http import ROOT, health_http  # noqa: F401
from test.support.health_safe_planner_live_inputs import LiveModelNotConfigured, load_live_inputs
from yuxi.config import get_user_data_dir
from yuxi.services.health_safe_planner_types import SAFE_PLANNER_TOOLS
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_business import (
    AgentRun,
    AgentRunAttempt,
    AgentRunRequest,
    Department,
    Message,
    ModelProvider,
    TaskRecord,
    User,
)
from yuxi.storage.postgres.models_health import (
    FamilyMember,
    HealthConsultation,
    HealthMealPlan,
    HealthMealPlanAdoption,
    HealthMemoryFact,
    HealthProfessionalReview,
    HealthQualityCheck,
    HealthSafePlannerPreview,
    RecipeVersion,
)
from yuxi.storage.redis import create_async_redis_client
from yuxi.workspace.paths import global_user_data_dir

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.slow,
    pytest.mark.asyncio,
    pytest.mark.skipif(os.getenv("RUN_HEALTH_SAFE_PLANNER_REAL_MODEL") != "1", reason="真实模型探针须显式开启"),
    pytest.mark.skipif(os.getenv("HEALTH_CONSULTATION_E2E_ISOLATED") != "true", reason="真实配餐仅允许独立合成槽位"),
]
PURPOSES = ("report", "meal", "consultation", "meal_plan", "diet_analysis", "quality_review")
EVIDENCE_DIR = Path("/tmp/health-safe-planner-live-evidence")


@pytest.fixture(scope="session", autouse=True)
def cleanup_e2e_test_resources():
    """只使用本文件health_http精确清理，不清理环境账号的其它测试资源。"""
    yield


@pytest.fixture
def live_model():
    """缺少外部依赖明确跳过，无效live参数必须失败。"""
    try:
        return load_live_inputs(os.environ)
    except LiveModelNotConfigured as exc:
        pytest.skip(str(exc))


@pytest_asyncio.fixture
async def live_cleanup_oracle(live_model):
    """在health_http的原Owner清理完成后，另开PG连接核对精确残留。"""
    pg_manager.initialize()
    try:
        async with pg_manager.get_async_session_context() as session:
            assert await session.scalar(text("SELECT current_database()")) == "health_consultation_e2e", (
                "必须先核对独立数据库，不能在其它槽创建合成账号"
            )
    finally:
        await pg_manager.close()
    ledger = {}
    yield ledger
    if not ledger:
        return
    pg_manager.initialize()
    try:
        async with pg_manager.get_async_session_context() as session:
            assert await session.scalar(text("SELECT current_database()")) == "health_consultation_e2e"
            uids = ledger["uids"]
            predicates = (
                (User, User.uid.in_(uids)),
                (Department, Department.id == ledger["department_id"]),
                (FamilyMember, FamilyMember.owner_uid.in_(uids)),
                (AgentRun, AgentRun.uid.in_(uids)),
                (AgentRunRequest, AgentRunRequest.uid.in_(uids)),
                (HealthConsultation, HealthConsultation.actor_uid.in_(uids)),
                (HealthMealPlan, HealthMealPlan.actor_uid.in_(uids)),
                (HealthSafePlannerPreview, HealthSafePlannerPreview.actor_uid.in_(uids)),
                (RecipeVersion, RecipeVersion.published_by.in_(uids)),
                (ModelProvider, ModelProvider.provider_id == ledger["provider_id"]),
            )
            residuals = {
                model.__tablename__: await session.scalar(select(func.count()).select_from(model).where(predicate))
                for model, predicate in predicates
            }
        _record_evidence(ledger["id"] + "-cleanup", {"residuals": residuals})
        assert not any(residuals.values()), "本轮合成数据清理后仍有精确残留"
    finally:
        await pg_manager.close()


@pytest_asyncio.fixture
async def live_planner(live_model, live_cleanup_oracle, health_http):  # noqa: F811
    """仅空审批独立数据库临时配置meal_plan，先收敛再精确恢复。"""
    client, users = health_http
    async with pg_manager.get_async_session_context() as session:
        assert await session.scalar(text("SELECT current_database()")) == "health_consultation_e2e", (
            "必须是独立合成数据库"
        )
        occupied = await session.scalar(
            select(AgentRun.id)
            .where(
                or_(
                    AgentRun.status.notin_(("completed", "failed", "cancelled", "interrupted")),
                    AgentRun.worker_id.is_not(None),
                    AgentRun.lease_expires_at.is_not(None),
                    AgentRun.runtime_cleanup_pending.is_(True),
                )
            )
            .limit(1)
        )
        tasks = await session.scalar(
            select(TaskRecord.id)
            .where(
                or_(
                    TaskRecord.status.notin_(("success", "failed", "cancelled")),
                    TaskRecord.worker_id.is_not(None),
                    TaskRecord.lease_expires_at.is_not(None),
                )
            )
            .limit(1)
        )
        queued = await session.scalar(
            select(AgentRunRequest.request_id).where(AgentRunRequest.status == "queued").limit(1)
        )
        assert occupied is None and tasks is None and queued is None, "独立槽位有活动任务，不能开启真实模型探针"
        department_id = await session.scalar(select(User.department_id).where(User.uid == users[0]["uid"]))
    assert str(client.base_url).rstrip("/") == "http://localhost:5050", "必须访问同槽位API"
    original = await client.get(f"{ROOT}/configuration", headers=users[2]["headers"])
    assert original.status_code == 200, f"配置读取HTTP {original.status_code}"
    original = original.json()
    assert not original["policy_version"] and all(not original[kind]["model"] for kind in PURPOSES), (
        "不能覆盖已有用途审批"
    )
    provider_id = f"health-safe-live-{uuid4().hex[:12]}"
    live_cleanup_oracle.update(
        id=uuid4().hex, uids=[actor["uid"] for actor in users], department_id=department_id, provider_id=provider_id
    )
    model_spec = f"{provider_id}:{live_model.model_id}"
    requests, created, configured = [], False, False
    try:
        response = await client.post(
            "/api/system/model-providers",
            headers=users[2]["headers"],
            json={
                "provider_id": provider_id,
                "display_name": "Synthetic data real meal planner probe only",
                "provider_type": live_model.provider_type,
                "base_url": live_model.base_url,
                "api_key": live_model.api_key,
                "headers_json": live_model.headers_json,
                "extra_json": live_model.extra_json,
                "include_user_uid": live_model.include_user_uid,
                "capabilities": ["chat"],
                "enabled_models": [
                    live_model.model_json or {"id": live_model.model_id, "type": "chat", "source": "manual"}
                ],
                "is_enabled": True,
            },
        )
        assert response.status_code == 200, f"临时供应商创建HTTP {response.status_code}"
        created = True
        configured = True
        response = await client.put(
            f"{ROOT}/configuration",
            headers=users[2]["headers"],
            json={
                "meal_plan_model": model_spec,
                "policy_version": "synthetic-real-model-probe-v1",
                "cloud_processing_reviewed": True,
            },
        )
        assert response.status_code == 200, f"配餐用途配置HTTP {response.status_code}"
        configuration = response.json()
        assert configuration["meal_plan"]["available"] and configuration["meal_plan"]["model"] == model_spec
        assert all(not configuration[kind]["model"] for kind in PURPOSES if kind != "meal_plan")
        yield client, users, configuration, model_spec, requests
    finally:
        # 若Worker仍拥有执行或清理租约，保留本轮配置和账号供诊断，不能先删除数据。
        await _drain_live_requests(client, users[0], requests)
        if configured:
            restored = await client.put(f"{ROOT}/configuration", headers=users[2]["headers"], json={})
            assert restored.status_code == 200, f"配置恢复HTTP {restored.status_code}"
            restored = restored.json()
            assert restored["policy_version"] == original["policy_version"]
            assert all(
                restored[kind]["model"] == original[kind]["model"] and not restored[kind]["available"]
                for kind in PURPOSES
            )
        if created:
            deleted = await client.delete(f"/api/system/model-providers/{provider_id}", headers=users[2]["headers"])
            assert deleted.status_code == 200, f"临时供应商清理HTTP {deleted.status_code}"
            absent = await client.get(f"/api/system/model-providers/{provider_id}", headers=users[2]["headers"])
            assert absent.status_code == 404, f"临时供应商仍存在HTTP {absent.status_code}"
        root = get_user_data_dir().resolve()
        for actor in users:
            target = global_user_data_dir(actor["uid"])
            target.resolve().relative_to(root)
            assert target.name == actor["uid"] and actor["uid"].startswith("pytest_health_")
            if target.exists():
                shutil.rmtree(target)
        _record_evidence(
            live_cleanup_oracle["id"] + "-restored",
            {"provider_removed": created, "empty_policy_restored": configured, "runs_settled": True},
        )


@pytest.mark.parametrize("case", ["swap", "regeneration", "no_candidates", "not_ready"])
async def test_real_model_safe_preview_and_explicit_confirmation(live_planner, case):
    """真实模型理解中文任务，只有程序回执可以成为输出和显式确认依据。"""
    client, users, configuration, model_spec, requests = live_planner
    current = await setup_swap(client, users, count=0 if case == "no_candidates" else 1)
    rule_version = 2
    if case == "not_ready":
        rules = deepcopy(current["rules"])
        rules.update(version=3, source_version="v3")
        rules["payload"]["meal_swap"] = None
        imported = await client.post(f"{ROOT}/approved-quality-rules", headers=users[2]["headers"], json=rules)
        assert imported.status_code == 201, f"合成规则导入HTTP {imported.status_code}"
        current["rules"], rule_version = rules, 3
    approved = await _approve_original(client, users, current) if case == "swap" else None
    consent = await client.post(
        f"{ROOT}/members/{current['member']}/processing-consents",
        headers=users[0]["headers"],
        json={
            "purpose": "meal_plan",
            "accepted": True,
            "processor": configuration["meal_plan"]["processor"],
            "policy_version": configuration["policy_version"],
        },
    )
    assert consent.status_code == 200, f"合成用途同意HTTP {consent.status_code}"
    bound, _ = await bind_safe(client, users, current, rule_version=rule_version)
    assert bound.status_code == 201, f"固定来源绑定HTTP {bound.status_code}"
    before = await _formal_facts(current)
    run_id, request_id, output = await _run_live_preview(client, users[0], bound.json()["thread_id"], case, requests)
    async with pg_manager.get_async_session_context() as session:
        run = await session.get(AgentRun, run_id)
        await _save_owned_run_diagnostic(session, run, users[0]["uid"])
    await _assert_live_worker_result(run_id, request_id, users[0], current, model_spec, output, case)
    assert await _formal_facts(current) == before, "模型预览不得修改正式餐单、专业决定、采用、记忆或饮食"
    result = output["result"]
    assert result["professional_review"] == "not_a_professional_decision"
    if case == "no_candidates":
        assert (
            result["status"] == "ready" and result["candidates"] == [] and result["reason"] == "no_eligible_candidates"
        )
    elif case == "not_ready":
        assert (
            result["status"] == "not_ready"
            and result["reason"] == "swap_rules_not_approved"
            and result["candidates"] == []
        )
    elif case == "regeneration":
        assert result["status"] == "ready" and result["safety_check"]["status"] == "passed"
        assert result["plan_snapshot"]["nutrition"]["totals"]["energy_kcal"] == "305.00"
        assert [meal["dishes"][0]["planned_grams"] for meal in result["plan_snapshot"]["meals"]] == ["50", "100", "150"]
        breakfast = result["plan_spec"]["meals"][0]["dishes"][0]["recipe_version_id"]
        # “仅早餐”版本也是批准的110kcal/100g，与通用候选同分，UUID决定排序。
        assert breakfast in {current["eligible"][0], current["excluded"][1]}
        expected = deepcopy(before["spec"])
        expected["meals"][0]["dishes"][0]["recipe_version_id"] = breakfast
        assert result["plan_spec"] == expected
        assert [meal["dishes"][0]["nutrition"]["energy_kcal"] for meal in result["plan_snapshot"]["meals"]] == [
            "55.00",
            "100.00",
            "150.00",
        ]
    else:
        assert result["status"] == "ready" and len(result["candidates"]) == 1
        candidate = result["candidates"][0]
        assert candidate["recipe_version_id"] == current["eligible"][0] and candidate["planned_grams"] == "100"
        assert candidate["nutrition_difference"]["energy_kcal"] == "10.00"
        assert candidate["plan_snapshot"]["nutrition"]["totals"]["energy_kcal"] == "310.00"
        assert candidate["safety_check"]["status"] == "passed"
        await _confirm_once(client, users, current, candidate, approved, before)
    _record_evidence(
        case + "-" + run_id,
        {
            "case": case,
            "run_id": run_id,
            "status": result["status"],
            "reason": result.get("reason"),
            "preview_formal_facts_unchanged": True,
            "original_energy_kcal": "300.00",
            "preview_energy_kcal": "310.00" if case == "swap" else "305.00" if case == "regeneration" else None,
        },
    )


async def _run_live_preview(client, owner, thread, case, requests):
    """仅提交一次中文任务，不重试模型失败或修复最终JSON。"""
    request_id = str(uuid4())
    requests.append(request_id)
    query = (
        "请为当前餐单重新生成安全三餐预览。"
        if case == "regeneration"
        else "请为当前餐单的午餐第1道菜提供安全换菜候选。"
    )
    submitted = await client.post(
        "/api/agent/runs",
        headers=owner["headers"],
        json={
            "agent_slug": "health-meal-planner",
            "thread_id": thread,
            "query": query,
            "meta": {"request_id": request_id},
        },
    )
    assert submitted.status_code == 200, f"真实Agent入口HTTP {submitted.status_code}"
    run_id = submitted.json()["run_id"]
    event, lines, ended = "message", [], False
    async with asyncio.timeout(180):
        async with client.stream(
            "GET", f"/api/agent/runs/{run_id}/events?verbose=false", headers=owner["headers"], timeout=180
        ) as response:
            assert response.status_code == 200, f"真实SSE HTTP {response.status_code}"
            async for line in response.aiter_lines():
                if line.startswith("event:"):
                    event = line[6:].strip()
                elif line.startswith("data:"):
                    lines.append(line[5:].strip())
                elif not line and lines:
                    payload = json.loads("\n".join(lines))
                    assert "message_delta" not in str(payload), "健康模型原始正文不能流向客户端"
                    assert event != "error", "真实模型SSE出现失败，保留Run诊断"
                    if event == "end":
                        assert payload["run_id"] == run_id
                        ended = True
                        break
                    event, lines = "message", []
    assert ended, "真实SSE必须有明确终态"
    response = await client.get(f"/api/agent/runs/{run_id}/result", headers=owner["headers"])
    assert response.status_code == 200, f"结果回读HTTP {response.status_code}"
    result = response.json()
    assert result["status"] == "completed", f"真实模型Run未完成：{run_id}，状态={result['status']}"
    return run_id, request_id, json.loads(result["output"])


async def _assert_live_worker_result(run_id, request_id, owner, current, model_spec, output, case):
    """权威输出、真实模型用量与有效工具输入从PG独立读取。"""
    async with pg_manager.get_async_session_context() as session:
        run = await session.get(AgentRun, run_id)
        assert run.status == "completed" and run.request_id == request_id and run.uid == owner["uid"]
        assert run.worker_id is None and run.lease_expires_at is None
        assert run.manifest["model"]["spec"] == model_spec
        assert run.manifest["resources"]["tools"] == list(SAFE_PLANNER_TOOLS)
        assert [skill["slug"] for skill in run.manifest["resources"]["skills"]] == ["family-meal-planner"]
        assert run.token_usage["model_call_count"] > 0 and run.token_usage["total"]["total_tokens"] > 0
        assert set(run.token_usage["models"]) == {model_spec}
        identity = run.token_usage["models"][model_spec]["model"]
        assert identity["configured_model_spec"] == model_spec
        assert identity["configured_model_id"] == model_spec.partition(":")[2]
        attempts = list((await session.scalars(select(AgentRunAttempt).where(AgentRunAttempt.run_id == run_id))).all())
        assert len(attempts) == 1 and attempts[0].outcome == "completed" and attempts[0].finished_at
        message = await session.get(Message, run.output_message_id)
        assert message.run_id == run_id and message.request_id == request_id and json.loads(message.content) == output
        assert set(output) == {"preview_id", "scope", "member_id", "operation", "result"}
        assert output["scope"] == "single_member_saved_plan" and output["member_id"] == current["member"]
        expected = "regeneration" if case == "regeneration" else "swap"
        assert output["operation"] == expected
        preview = await session.get(HealthSafePlannerPreview, output["preview_id"])
        assert (
            preview.actor_uid == owner["uid"]
            and preview.run_id == run_id
            and preview.conversation_id == run.conversation_id
        )
        assert preview.operation == expected and preview.snapshot == output["result"]
        sources = output["result"]["sources"]
        assert sources["plan"]["id"] == current["plan"] and sources["plan"]["version"] == 1
        assert set(sources["profiles"]) == {current["member"]}
        assert sources["profiles"][current["member"]]["version"] == 1
        assert sources["rules"]["rule_code"] == current["rules"]["rule_code"]
        assert sources["rules"]["version"] == (3 if case == "not_ready" else 2)
        audits = list(
            (
                await session.scalars(
                    select(Message).where(Message.run_id == run_id, Message.message_type == "tool_audit")
                )
            ).all()
        )
        assert audits and all(row.execution_status == "completed" for row in audits)
        names = [(row.extra_metadata or {})["tool_name"] for row in audits]
        assert set(names) <= set(SAFE_PLANNER_TOOLS) and "get_safe_plan_context" in names
        target = "preview_safe_plan_regeneration" if case == "regeneration" else "preview_safe_plan_swap"
        assert target in names
        for audit in audits:
            metadata = audit.extra_metadata
            assert metadata["input"] == (
                {"meal_type": "lunch", "dish_index": 0} if metadata["tool_name"] == "preview_safe_plan_swap" else {}
            )
        models = list(
            (
                await session.scalars(
                    select(Message).where(
                        Message.run_id == run_id, Message.role == "assistant", Message.execution_status == "completed"
                    )
                )
            ).all()
        )
        assert models and any((row.usage or {}).get("total_tokens", 0) > 0 for row in models)
        _record_evidence(
            case + "-" + run_id + "-worker",
            {
                "run_id": run_id,
                "request_id": request_id,
                "model": model_spec,
                "status": run.status,
                "model_calls": run.token_usage["model_call_count"],
                "total_tokens": run.token_usage["total"]["total_tokens"],
                "actual_response_model_ids": identity.get("response_model_ids", []),
                "tool_names": names,
                "output_message_id": run.output_message_id,
                "owner_released": True,
                "lease_released": True,
            },
        )


async def _formal_facts(current):
    """数量之外保存专业状态、采用快照和记忆，不能以同数量掩盖修改。"""
    facts = await safe_business_facts(current)
    async with pg_manager.get_async_session_context() as session:
        reviews = list(
            (
                await session.scalars(
                    select(HealthProfessionalReview).where(HealthProfessionalReview.member_id == current["member"])
                )
            ).all()
        )
        adoptions = list(
            (
                await session.scalars(
                    select(HealthMealPlanAdoption).where(HealthMealPlanAdoption.plan_id == current["plan"])
                )
            ).all()
        )
        facts["reviews"] = {row.id: (row.version, row.status, row.invalidation_reason) for row in reviews}
        facts["adoptions"] = {row.id: (row.version, row.status, deepcopy(row.snapshot)) for row in adoptions}
        facts["memory_ids"] = list(
            (
                await session.scalars(
                    select(HealthMemoryFact.id).where(HealthMemoryFact.member_id == current["member"])
                )
            ).all()
        )
    return facts


async def _approve_original(client, users, current):
    """批准原版本仅用于验证用户确认后原批准及采用确实失效。"""
    owner = users[0]["headers"]
    checked = await client.post(
        f"{ROOT}/meal-plans/{current['plan']}/quality-checks",
        headers=owner,
        json={"client_request_id": str(uuid4()), "version": 1, "rule_code": current["rules"]["rule_code"]},
    )
    assert checked.status_code == 201
    read = await client.get(f"{ROOT}/quality-checks/{checked.json()['check_id']}", headers=owner)
    assert read.status_code == 200
    review = read.json()["review"]["review_id"]
    await action(client, owner, review, "submit", 1)
    await action(client, users[1]["headers"], review, "approve", 2)
    adopted = await client.post(
        f"{ROOT}/meal-plans/{current['plan']}/adopt",
        headers=owner,
        json={
            "client_request_id": str(uuid4()),
            "version": 1,
            "review_id": review,
            "profile_versions": {current["member"]: 1},
        },
    )
    assert adopted.status_code == 201
    return review, adopted.json()["adoption_id"]


async def _confirm_once(client, users, current, candidate, approved, before):
    """显式业务保存与原包原键恢复只生成一次修订，不继承专业批准。"""
    body = {
        **selection(current),
        "client_request_id": str(uuid4()),
        "recipe_version_id": candidate["recipe_version_id"],
    }
    first = await swap(client, users[0]["headers"], current, candidate["recipe_version_id"], body=body)
    assert first.status_code == 200
    replay = await swap(client, users[0]["headers"], current, candidate["recipe_version_id"], body=body)
    assert replay.status_code == 200 and replay.json() == first.json()
    saved = first.json()
    assert saved["version"] == saved["applied_version"] == 2 and saved["nutrition"]["totals"]["energy_kcal"] == "310.00"
    after = await _formal_facts(current)
    assert after["version"] == 2 and after["HealthMealPlanRevision"] == before["HealthMealPlanRevision"] + 1
    assert after["DietLog"] == before["DietLog"] == 0 and after["memory_ids"] == before["memory_ids"] == []
    assert after["reviews"][approved[0]][1:] == ("invalidated", "plan_changed")
    assert after["adoptions"][approved[1]][1] == "invalidated"
    assert after["adoptions"][approved[1]][2] == before["adoptions"][approved[1]][2]
    async with pg_manager.get_async_session_context() as session:
        check = await session.get(HealthQualityCheck, saved["quality_check"]["check_id"])
        review = await session.scalar(
            select(HealthProfessionalReview).where(HealthProfessionalReview.check_id == check.id)
        )
        assert check.plan_version == 2 and review.status == "draft"
    _record_evidence(
        "confirmation-" + current["plan"],
        {
            "version": 2,
            "revision_count": after["HealthMealPlanRevision"],
            "same_key_recovered": True,
            "previous_approval_invalidated": True,
            "actual_diet_count": 0,
        },
    )


async def _drain_live_requests(client, owner, request_ids):
    """有界取消本轮请求并等待数据库租约与运行清理，不删除活跃对象。"""
    async with pg_manager.get_async_session_context() as session:
        queued = list(
            (
                await session.scalars(
                    select(AgentRunRequest.request_id).where(
                        AgentRunRequest.uid == owner["uid"],
                        AgentRunRequest.request_id.in_(request_ids),
                        AgentRunRequest.status == "queued",
                    )
                )
            ).all()
        )
        active = list(
            (
                await session.scalars(
                    select(AgentRun.id).where(
                        AgentRun.uid == owner["uid"],
                        AgentRun.request_id.in_(request_ids),
                        AgentRun.status.notin_(("completed", "failed", "cancelled", "interrupted")),
                    )
                )
            ).all()
        )
    for request_id in queued:
        await client.post(f"/api/agent/requests/{request_id}/cancel", headers=owner["headers"])
    for run_id in active:
        await client.post(f"/api/agent/runs/{run_id}/cancel", headers=owner["headers"])
    async with asyncio.timeout(45):
        while True:
            async with pg_manager.get_async_session_context() as session:
                runs = list(
                    (
                        await session.scalars(
                            select(AgentRun).where(AgentRun.uid == owner["uid"], AgentRun.request_id.in_(request_ids))
                        )
                    ).all()
                )
                queued = await session.scalar(
                    select(AgentRunRequest.request_id)
                    .where(
                        AgentRunRequest.uid == owner["uid"],
                        AgentRunRequest.request_id.in_(request_ids),
                        AgentRunRequest.status == "queued",
                    )
                    .limit(1)
                )
                if queued is None and all(
                    run.status in {"completed", "failed", "cancelled", "interrupted"}
                    and run.worker_id is None
                    and run.lease_expires_at is None
                    and not run.runtime_cleanup_pending
                    for run in runs
                ):
                    for run in runs:
                        await _save_owned_run_diagnostic(session, run, owner["uid"])
                    await _clear_live_run_redis(runs, owner["uid"], request_ids)
                    _record_evidence(
                        "settled-" + uuid4().hex,
                        {
                            "runs": [
                                {
                                    "run_id": run.id,
                                    "request_id": run.request_id,
                                    "status": run.status,
                                    "owner_released": run.worker_id is None,
                                    "lease_released": run.lease_expires_at is None,
                                    "runtime_cleanup_pending": run.runtime_cleanup_pending,
                                    "model_calls": (run.token_usage or {}).get("model_call_count", 0),
                                    "output_message_id": run.output_message_id,
                                    "error_code": next(
                                        (
                                            code
                                            for code in (
                                                "planner_output_invalid",
                                                "planner_receipt_invalid",
                                                "source_invalidated",
                                                "consent_required",
                                            )
                                            if code in (run.error_message or "")
                                        ),
                                        None,
                                    ),
                                }
                                for run in runs
                            ],
                            "queued_request_count": 0,
                        },
                    )
                    return
            await asyncio.sleep(0.2)


async def _save_owned_run_diagnostic(session, run, owner_uid):
    """断言及清理前保存本轮合成审计，已发布投影不冒充原始模型正文。"""
    assert owner_uid.startswith("pytest_health_") and run.uid == owner_uid, "失败正文只允许本轮合成账号"
    binding = await session.get(HealthConsultation, run.conversation_id)
    member = await session.get(FamilyMember, binding.member_id) if binding is not None else None
    assert (
        binding is not None and binding.actor_uid == owner_uid and member is not None and member.owner_uid == owner_uid
    ), "必须核对本轮合成成员才能保存模型正文"
    models = list(
        (
            await session.scalars(
                select(Message)
                .where(
                    Message.run_id == run.id,
                    Message.request_id == run.request_id,
                    Message.conversation_id == run.conversation_id,
                    Message.role == "assistant",
                    Message.message_type == "model_audit",
                    Message.execution_status == "completed",
                )
                .order_by(Message.id.desc())
                .limit(8)
            )
        ).all()
    )
    tools = list(
        (
            await session.scalars(
                select(Message)
                .where(Message.run_id == run.id, Message.message_type == "tool_audit")
                .order_by(Message.id.desc())
                .limit(16)
            )
        ).all()
    )
    attempts = list(
        (
            await session.scalars(
                select(AgentRunAttempt)
                .where(AgentRunAttempt.run_id == run.id)
                .order_by(AgentRunAttempt.attempt_no)
                .limit(8)
            )
        ).all()
    )
    receipts = list(
        (
            await session.scalars(
                select(HealthSafePlannerPreview)
                .where(
                    HealthSafePlannerPreview.run_id == run.id,
                    HealthSafePlannerPreview.actor_uid == owner_uid,
                    HealthSafePlannerPreview.conversation_id == run.conversation_id,
                )
                .order_by(HealthSafePlannerPreview.created_at)
                .limit(8)
            )
        ).all()
    )
    published = await session.get(Message, run.output_message_id) if run.output_message_id is not None else None
    if published is not None:
        assert published.run_id == run.id and published.request_id == run.request_id
    evidence = {
        "run_id": run.id,
        "request_id": run.request_id,
        "status": run.status,
        "synthetic_owner_verified": True,
        "error_code": next(
            (
                code
                for code in (
                    "planner_output_invalid",
                    "planner_receipt_invalid",
                    "source_invalidated",
                    "consent_required",
                )
                if code in (run.error_message or "")
            ),
            None,
        ),
        "attempts": [
            {"attempt_no": item.attempt_no, "outcome": item.outcome, "finished": item.finished_at is not None}
            for item in attempts
        ],
        "raw_model_content_status": "available" if any(item.content for item in models) else "unavailable",
        "model_messages": [
            {
                "id": item.id,
                "type": item.message_type,
                "status": item.execution_status,
                **_bounded_model_content(item.content),
            }
            for item in reversed(models)
        ],
        "published_output": {
            "id": published.id,
            "type": "server_projection",
            **_bounded_model_content(published.content),
        }
        if published is not None
        else {"type": "unavailable"},
        "receipts": [
            {
                "id": item.id,
                "operation": item.operation,
                "status": item.snapshot.get("status"),
                "reason": item.snapshot.get("reason"),
                "snapshot": _bounded_model_content(json.dumps(item.snapshot, ensure_ascii=False, sort_keys=True)),
            }
            for item in receipts
        ],
        "tool_audits": [
            {
                "id": item.id,
                "name": (item.extra_metadata or {}).get("tool_name")
                if (item.extra_metadata or {}).get("tool_name") in SAFE_PLANNER_TOOLS
                else "unrecognized",
                "status": item.execution_status,
            }
            for item in reversed(tools)
        ],
    }
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    target = EVIDENCE_DIR / ("run-" + run.id + ".json")
    target.write_text(json.dumps(evidence, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    print(
        "safe_planner_live_run_evidence="
        + json.dumps(
            {"run_id": run.id, "file": target.name, "raw_model_content_status": evidence["raw_model_content_status"]}
        )
    )


def _bounded_model_content(content):
    """按UTF-8字节限制每条正文64KiB并显式记录截断，不改写模型协议。"""
    encoded = (content or "").encode("utf-8")
    return {
        "content": encoded[:65536].decode("utf-8", errors="ignore"),
        "original_bytes": len(encoded),
        "truncated": len(encoded) > 65536,
    }


async def _clear_live_run_redis(runs, owner_uid, request_ids):
    """只有本轮PG已收敛Run可删除精确事件/取消键，不扫描或清理公共键。"""
    if not runs:
        return
    assert owner_uid.startswith("pytest_health_") and all(
        run.uid == owner_uid
        and run.request_id in request_ids
        and run.status in {"completed", "failed", "cancelled", "interrupted"}
        and run.worker_id is None
        and run.lease_expires_at is None
        and not run.runtime_cleanup_pending
        for run in runs
    ), "本轮Run未收敛或归属不符，不能删除Redis键"
    keys = [key for run in runs for key in (f"run:events:{run.id}", f"run:cancel:{run.id}")]
    redis = await create_async_redis_client()
    try:
        removed = await redis.delete(*keys)
        remaining = await redis.exists(*keys)
        assert remaining == 0, "本轮Run精确Redis键清理后仍有残留"
    finally:
        await redis.aclose()
    _record_evidence(
        "redis-" + uuid4().hex,
        {
            "run_ids": [run.id for run in runs],
            "key_count": len(keys),
            "removed_count": removed,
            "remaining_count": remaining,
        },
    )


def _record_evidence(name, evidence):
    """只写调用方构造的ID、状态及聚合，不写健康正文或供应商参数。"""
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(evidence, ensure_ascii=False, sort_keys=True)
    (EVIDENCE_DIR / (name + ".json")).write_text(encoded + "\n", encoding="utf-8")
    print("safe_planner_live_evidence=" + encoded)

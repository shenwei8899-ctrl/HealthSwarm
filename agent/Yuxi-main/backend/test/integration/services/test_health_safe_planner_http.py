"""真实HTTP/PG验证单成员固定选择、只读回执、来源及显式保存。"""

import json
import os
from copy import deepcopy
from datetime import timedelta
from uuid import uuid4

import pytest
import pytest_asyncio
import httpx
from sqlalchemy import func, select

from test.e2e.test_health_consultation_e2e import isolated_health  # noqa: F401
from test.integration.services.test_health_family_safe_plan_http import setup_safe_family
from test.integration.services.test_health_quality_http import action
from test.integration.services.test_health_safe_meal_swap_http import setup_swap, swap
from test.integration.services.test_health_safe_plan_regeneration_http import save, selection
from test.integration.services.test_health_vision_http import (
    ROOT,
    cleanup_health_test_resources,
    create_member,
    health_http,  # noqa: F401
)
from test.support.health_consultation_replay_server import (
    MODEL,
    SAFE_PLANNER_MODEL,
    SAFE_PLANNER_TOOLS,
    TOOLS,
    safe_planner_replay_delta,
)
from yuxi.agents.context import BaseContext
from yuxi.services.health_consultation_service import require_consultation
from yuxi.services.health_meal_plan_service import meal_plan_recipes_for_run, planner_final_result
from yuxi.services.health_safe_planner_service import (
    preview_safe_for_run,
    read_safe_context_for_run,
    validate_safe_planner_publication,
    validate_safe_planner_tool_payload,
)
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_business import AgentRun, AgentRunRequest, Conversation, Message, User
from yuxi.storage.postgres.models_health import (
    DietLog,
    HealthConsultation,
    HealthGrant,
    HealthMealPlan,
    HealthMealPlanAdoption,
    HealthMealPlanRevision,
    HealthProfessionalReview,
    HealthQualityCheck,
    HealthSafePlannerPreview,
)
from yuxi.utils.datetime_utils import utc_now_naive

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]
ISOLATED = pytest.mark.skipif(
    os.getenv("HEALTH_CONSULTATION_E2E_ISOLATED") != "true", reason="仅独立合成槽位审批配餐模型"
)


@pytest_asyncio.fixture
async def safe_runtime(isolated_health):  # noqa: F811
    """实际配置只指向同槽位replay，退出恢复原审批并撤销provider。"""
    client, users, configuration, consultation_model = isolated_health
    provider = f"safe-planner-replay-{uuid4().hex[:12]}"
    created = await client.post(
        "/api/system/model-providers",
        headers=users[2]["headers"],
        json={
            "provider_id": provider,
            "display_name": "Synthetic single member safe planner only",
            "provider_type": "openai",
            "base_url": "http://api:8766/v1",
            "api_key": "synthetic-safe-planner-key",
            "capabilities": ["chat"],
            "enabled_models": [
                {"id": SAFE_PLANNER_MODEL, "display_name": "synthetic", "type": "chat", "source": "manual"}
            ],
            "is_enabled": True,
        },
    )
    assert created.status_code == 200, created.text
    try:
        configured = await client.put(
            f"{ROOT}/configuration",
            headers=users[2]["headers"],
            json={
                "consultation_model": consultation_model,
                "meal_plan_model": f"{provider}:{SAFE_PLANNER_MODEL}",
                "policy_version": configuration["policy_version"],
                "cloud_processing_reviewed": True,
            },
        )
        assert configured.status_code == 200 and configured.json()["meal_plan"]["available"], configured.text
        current = await setup_swap(client, users, count=1)
        consent = {
            "purpose": "meal_plan",
            "accepted": True,
            "processor": configured.json()["meal_plan"]["processor"],
            "policy_version": configuration["policy_version"],
        }
        accepted = await client.post(
            f"{ROOT}/members/{current['member']}/processing-consents", headers=users[0]["headers"], json=consent
        )
        assert accepted.status_code == 200, accepted.text
        # 审计HTTP要求superadmin；仅提升随机合成账号，健康grant仍须逐项满足。
        async with pg_manager.get_async_session_context() as session:
            owner = await session.scalar(select(User).where(User.uid == users[0]["uid"]))
            assert owner.uid.startswith("pytest_health_") and owner.role == "user"
            owner.role = "superadmin"
        yield client, users, current, consent
    finally:
        restored = await client.put(
            f"{ROOT}/configuration",
            headers=users[2]["headers"],
            json={
                "consultation_model": consultation_model,
                "policy_version": configuration["policy_version"],
                "cloud_processing_reviewed": True,
            },
        )
        assert restored.status_code == 200 and not restored.json()["meal_plan"]["available"], restored.text
        deleted = await client.delete(f"/api/system/model-providers/{provider}", headers=users[2]["headers"])
        assert deleted.status_code == 200, deleted.text
        async with pg_manager.get_async_session_context() as session:
            owner = await session.scalar(select(User).where(User.uid == users[0]["uid"]))
            owner.role = "user"
            runs = (await session.scalars(select(AgentRun).where(AgentRun.uid == users[0]["uid"]))).all()
            for run in runs:
                if run.worker_id == "synthetic-safe-boundary":
                    run.status, run.worker_id, run.lease_expires_at = "failed", None, None
                else:
                    assert (
                        run.status in {"completed", "failed", "cancelled"}
                        and run.worker_id is None
                        and run.lease_expires_at is None
                    ), run.id


async def bind_safe(client, users, current, **updates):
    """HTTP提交完整不可变选择，并允许负控显式覆盖参数。"""
    body = {**selection(current), "plan_id": current["plan"], "client_request_id": str(uuid4()), **updates}
    response = await client.post(
        f"{ROOT}/members/{current['member']}/safe-meal-plan-conversations", headers=users[0]["headers"], json=body
    )
    return response, body


async def seed_safe_run(users, thread):
    """真实PG人工Owner仅用于边界验证，真实worker另由E2E证明。"""
    request_id, run_id = str(uuid4()), str(uuid4())
    async with pg_manager.get_async_session_context() as session:
        binding, processing = await require_consultation(session, users[0]["uid"], thread)
        session.add(
            AgentRun(
                id=run_id,
                request_id=request_id,
                uid=users[0]["uid"],
                agent_slug="health-meal-planner",
                conversation_id=binding.conversation_id,
                conversation_thread_id=thread,
                runtime_scope_id=thread,
                worker_id="synthetic-safe-boundary",
                status="running",
                lease_expires_at=utc_now_naive() + timedelta(minutes=3),
                input_payload={"health_processing": processing},
            )
        )
    return BaseContext(
        uid=users[0]["uid"],
        thread_id=thread,
        request_id=request_id,
        run_id=run_id,
        worker_id="synthetic-safe-boundary",
        model=processing["model"],
    )


async def safe_business_facts(current):
    """独立PG读取四类正式事实，预览只允许新增专用回执。"""
    async with pg_manager.get_async_session_context() as session:
        plan = await session.get(HealthMealPlan, current["plan"])
        facts = {"version": plan.version, "spec": deepcopy(plan.spec), "snapshot": deepcopy(plan.snapshot)}
        for model, predicate in (
            (HealthMealPlanRevision, HealthMealPlanRevision.plan_id == plan.id),
            (HealthQualityCheck, HealthQualityCheck.plan_id == plan.id),
            (HealthMealPlanAdoption, HealthMealPlanAdoption.plan_id == plan.id),
            (DietLog, DietLog.member_id == current["member"]),
        ):
            facts[model.__name__] = await session.scalar(select(func.count()).select_from(model).where(predicate))
        return facts


async def assert_safe_private_denied(client, users, thread, run_id, *, expected_submit):
    """旧结果、SSE、历史及新请求不能暴露被撤销或失效的健康投影。"""
    owner = users[0]["headers"]
    result = await client.get(f"/api/agent/runs/{run_id}/result", headers=owner)
    assert result.status_code == 200 and result.json()["error"]["type"] == "run_not_found", result.text
    assert result.json()["output"] == ""
    events = await client.get(f"/api/agent/runs/{run_id}/events", headers=owner)
    assert events.status_code == 200 and "event: error" in events.text, events.text
    assert [json.loads(line[6:]) for line in events.text.splitlines() if line.startswith("data: ")] == [
        {"run_id": run_id, "message": "运行任务不存在"}
    ]
    history = await client.get(
        f"/api/agent/thread/{thread}/requests", headers=owner, params={"agent_slug": "health-meal-planner"}
    )
    assert history.status_code == 404, history.text
    audits = await client.get(f"/api/chat/thread/{thread}/audits", headers=owner)
    assert audits.status_code == 404, audits.text
    key = str(uuid4())
    rejected = await client.post(
        "/api/agent/runs",
        headers=owner,
        json={
            "agent_slug": "health-meal-planner",
            "thread_id": thread,
            "query": "synthetic",
            "meta": {"request_id": key},
        },
    )
    assert rejected.status_code == expected_submit, rejected.text
    if expected_submit == 409:
        assert rejected.json() == {"detail": "单成员预览回执不属于当前运行"}, rejected.text
    async with pg_manager.get_async_session_context() as session:
        for model in (AgentRun, AgentRunRequest, Message):
            assert await session.scalar(select(model).where(model.request_id == key)) is None
    print(
        "safe_planner_private_evidence="
        + json.dumps(
            {
                "run_id": run_id,
                "result_error": result.json()["error"]["type"],
                "sse_error": "运行任务不存在",
                "history_http": history.status_code,
                "audits_http": audits.status_code,
                "newrun_http": rejected.status_code,
                "new_request_rows": 0,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )


@ISOLATED
async def test_http_safe_binding_preserves_selection_and_rejects_identity_version_mode_conflicts(safe_runtime):
    """同键不改来源，非法身份和版本不产生任何专属咨询行。"""
    client, users, current, consent = safe_runtime
    before = await safe_business_facts(current)
    other_member = await create_member(client, users[0]["headers"])
    for updates, status in (
        ({"version": 2}, 410),
        ({"rule_version": 1}, 410),
        ({"profile_version": 2}, 410),
        ({"uid": "forged"}, 422),
    ):
        response, body = await bind_safe(client, users, current, **updates)
        assert response.status_code == status, response.text
        async with pg_manager.get_async_session_context() as session:
            assert (
                await session.scalar(
                    select(HealthConsultation).where(HealthConsultation.request_id == body["client_request_id"])
                )
                is None
            )
    body = {**selection(current), "plan_id": current["plan"], "client_request_id": str(uuid4())}
    for member, headers in ((other_member, users[0]["headers"]), (current["member"], users[2]["headers"])):
        denied = await client.post(f"{ROOT}/members/{member}/safe-meal-plan-conversations", headers=headers, json=body)
        assert denied.status_code == 404, denied.text
    revoked = await client.post(
        f"{ROOT}/members/{current['member']}/processing-consents",
        headers=users[0]["headers"],
        json={**consent, "accepted": False},
    )
    assert revoked.status_code == 200, revoked.text
    denied, denied_body = await bind_safe(client, users, current)
    assert denied.status_code == 403, denied.text
    async with pg_manager.get_async_session_context() as session:
        assert (
            await session.scalar(
                select(HealthConsultation).where(HealthConsultation.request_id == denied_body["client_request_id"])
            )
            is None
        )
    assert (
        await client.post(
            f"{ROOT}/members/{current['member']}/processing-consents", headers=users[0]["headers"], json=consent
        )
    ).status_code == 200
    bound, body = await bind_safe(client, users, current)
    assert bound.status_code == 201, bound.text
    replay, _ = await bind_safe(client, users, current, **body)
    assert replay.status_code == 201 and replay.json() == bound.json(), replay.text
    conflict, _ = await bind_safe(client, users, current, **{**body, "version": 2})
    assert conflict.status_code == 409, conflict.text
    legacy = await client.post(
        f"{ROOT}/members/{current['member']}/meal-planner",
        headers=users[0]["headers"],
        json={"client_request_id": body["client_request_id"]},
    )
    assert legacy.status_code == 409, legacy.text
    async with pg_manager.get_async_session_context() as session:
        conversation = await session.scalar(
            select(Conversation).where(Conversation.thread_id == bound.json()["thread_id"])
        )
        binding = await session.get(HealthConsultation, conversation.id)
        assert binding.safe_planner_selection["selection"] == {
            key: value for key, value in body.items() if key != "client_request_id"
        }
        assert len(binding.safe_planner_selection["source_hash"]) == 64
        assert binding.family_planner_selection is None and binding.initial_planner_selection is None
    assert await safe_business_facts(current) == before


@ISOLATED
async def test_pg_safe_previews_are_real_read_only_and_reject_forged_or_cross_run_receipts(safe_runtime):
    """310换菜与305整份重算独立手算，伪造内容及其它Run选择均拒绝。"""
    client, users, current, _ = safe_runtime
    before = await safe_business_facts(current)
    bound, _ = await bind_safe(client, users, current)
    assert bound.status_code == 201, bound.text
    context = await seed_safe_run(users, bound.json()["thread_id"])
    projected = await read_safe_context_for_run(context)
    assert projected["scope"] == "single_member_saved_plan" and projected["member_id"] == current["member"]
    assert projected["plan_snapshot"]["nutrition"]["totals"]["energy_kcal"] == "300.00"
    with pytest.raises(HealthVisionError, match="planner_mode_conflict"):
        await meal_plan_recipes_for_run(context, "")
    for operation, parameters, tool in (
        ("swap", {"meal_type": "lunch", "dish_index": 0}, "preview_safe_plan_swap"),
        ("regeneration", {}, "preview_safe_plan_regeneration"),
    ):
        receipt = await preview_safe_for_run(context, operation, parameters)
        assert receipt["operation"] == operation and receipt["member_id"] == current["member"]
        if operation == "swap":
            candidate = receipt["result"]["candidates"][0]
            assert candidate["recipe_version_id"] == current["eligible"][0]
            assert candidate["plan_snapshot"]["nutrition"]["totals"]["energy_kcal"] == "310.00"
        else:
            assert receipt["result"]["plan_snapshot"]["nutrition"]["totals"]["energy_kcal"] == "305.00"
        final = await planner_final_result(context, json.dumps({"preview_id": receipt["preview_id"]}))
        assert final == receipt
        async with pg_manager.get_async_session_context() as session:
            run = await session.get(AgentRun, context.run_id)
            binding, _ = await require_consultation(session, context.uid, context.thread_id)
            await validate_safe_planner_publication(session, run, json.dumps(final))
            await validate_safe_planner_tool_payload(session, binding, tool, final)
            forged = {**deepcopy(final), "result": {"status": "ready", "nutrition": {"energy_kcal": "999"}}}
            with pytest.raises(HealthVisionError, match="source_invalidated"):
                await validate_safe_planner_publication(session, run, json.dumps(forged))
            with pytest.raises(HealthVisionError, match="source_invalidated"):
                await validate_safe_planner_tool_payload(session, binding, tool, forged)
            stored = await session.get(HealthSafePlannerPreview, receipt["preview_id"])
            original_snapshot = deepcopy(stored.snapshot)
            stored.snapshot = {"status": "ready", "forged": True}
            await session.flush()
            with pytest.raises(HealthVisionError, match="source_invalidated"):
                await validate_safe_planner_publication(session, run, json.dumps(final))
            stored.snapshot = original_snapshot
            await session.flush()
            original_input = deepcopy(run.input_payload)
            for processing in (None, {}, {"model": context.model}):
                run.input_payload = {"health_processing": processing}
                await session.flush()
                with pytest.raises(HealthVisionError, match="policy_changed"):
                    await validate_safe_planner_publication(session, run, json.dumps(final))
            run.input_payload = original_input
            await session.flush()
    for answer, code in (
        ({"preview_id": str(uuid4())}, "planner_receipt_invalid"),
        ({"preview_id": receipt["preview_id"], "nutrition": "forged"}, "planner_output_invalid"),
    ):
        with pytest.raises(HealthVisionError, match=code):
            await planner_final_result(context, json.dumps(answer))
    async with pg_manager.get_async_session_context() as session:
        run = await session.get(AgentRun, context.run_id)
        run.status, run.worker_id, run.lease_expires_at = "completed", None, None
    another = await seed_safe_run(users, context.thread_id)
    with pytest.raises(HealthVisionError, match="planner_receipt_invalid"):
        await planner_final_result(another, json.dumps({"preview_id": receipt["preview_id"]}))
    with pytest.raises(HealthVisionError, match="execution_not_owned"):
        await preview_safe_for_run(context, "regeneration", {})
    async with pg_manager.get_async_session_context() as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(HealthSafePlannerPreview)
                .where(HealthSafePlannerPreview.run_id == context.run_id)
            )
            == 2
        )
    assert await safe_business_facts(current) == before


@ISOLATED
async def test_http_family_plan_cannot_enter_single_member_mode(isolated_health):  # noqa: F811
    """真实家庭对象在单成员入口拒绝，不能降级忽略第二成员。"""
    client, users, _, _ = isolated_health
    family = await setup_safe_family(client, users)
    response, body = await bind_safe(client, users, family, rule_version=3, profile_version=2)
    assert response.status_code == 409 and response.json()["code"] == "family_operation_not_ready", response.text
    async with pg_manager.get_async_session_context() as session:
        assert (
            await session.scalar(
                select(HealthConsultation).where(HealthConsultation.request_id == body["client_request_id"])
            )
            is None
        )


@ISOLATED
@pytest.mark.parametrize(
    "status,owned,leased", [("running", False, False), ("failed", True, False), ("failed", False, True)]
)
async def test_cleanup_preserves_unsettled_safe_run_and_private_receipt(safe_runtime, status, owned, leased):
    """未收敛Run或残留执行Owner阻止精确测试账号清理，保留诊断事实。"""
    client, users, current, _ = safe_runtime
    bound, _ = await bind_safe(client, users, current)
    assert bound.status_code == 201, bound.text
    context = await seed_safe_run(users, bound.json()["thread_id"])
    receipt = await preview_safe_for_run(context, "regeneration", {})
    async with pg_manager.get_async_session_context() as session:
        department_id = await session.scalar(select(User.department_id).where(User.uid == context.uid))
        run = await session.get(AgentRun, context.run_id)
        run.status = status
        run.worker_id = "synthetic-safe-boundary" if owned else None
        run.lease_expires_at = utc_now_naive() + timedelta(minutes=3) if leased else None
    try:
        with pytest.raises(RuntimeError, match="健康测试AgentRun尚未收敛"):
            await cleanup_health_test_resources(users, department_id)
        async with pg_manager.get_async_session_context() as session:
            assert await session.get(AgentRun, context.run_id) is not None
            assert await session.get(HealthSafePlannerPreview, receipt["preview_id"]) is not None
            assert await session.get(HealthMealPlan, current["plan"]) is not None
            assert await session.scalar(select(User).where(User.uid == context.uid)) is not None
    finally:
        async with pg_manager.get_async_session_context() as session:
            run = await session.get(AgentRun, context.run_id)
            run.status, run.worker_id, run.lease_expires_at = "failed", None, None


@ISOLATED
async def test_unapproved_swap_rules_return_not_ready_and_preserve_formal_facts(safe_runtime):
    """专业换菜条款缺失不得由模型补齐，两个工具只返回未就绪回执。"""
    client, users, current, _ = safe_runtime
    rules = deepcopy(current["rules"])
    rules.update(version=3, source_version="v3")
    del rules["payload"]["meal_swap"]
    imported = await client.post(f"{ROOT}/approved-quality-rules", headers=users[2]["headers"], json=rules)
    assert imported.status_code == 201, imported.text
    before = await safe_business_facts(current)
    bound, _ = await bind_safe(client, users, current, rule_version=3)
    assert bound.status_code == 201, bound.text
    context = await seed_safe_run(users, bound.json()["thread_id"])
    for operation, parameters in (("swap", {"meal_type": "lunch", "dish_index": 0}), ("regeneration", {})):
        receipt = await preview_safe_for_run(context, operation, parameters)
        assert receipt["result"]["status"] == "not_ready"
        assert receipt["result"]["reason"] == "swap_rules_not_approved"
        assert await planner_final_result(context, json.dumps({"preview_id": receipt["preview_id"]})) == receipt
    assert await safe_business_facts(current) == before


@ISOLATED
@pytest.mark.parametrize("revoked", ["ai_use", "diet_edit", "profile_view", "consent", "profile"])
async def test_http_revocation_or_professional_profile_correction_blocks_old_private_paths(safe_runtime, revoked):
    """来源更正、每个权限和同意撤销都拒绝旧工具、发布及真实HTTP读取。"""
    client, users, current, consent = safe_runtime
    bound, _ = await bind_safe(client, users, current)
    assert bound.status_code == 201, bound.text
    context = await seed_safe_run(users, bound.json()["thread_id"])
    final = await planner_final_result(context, json.dumps({"questions": ["合成补充问题"]}))
    audits = await client.get(f"/api/chat/thread/{context.thread_id}/audits", headers=users[0]["headers"])
    assert audits.status_code == 200, audits.text
    if revoked == "profile":
        changed = deepcopy(current["profile"])
        changed.update(version=2, source_version="v2")
        corrected = await client.post(
            f"{ROOT}/members/{current['member']}/external-profile-versions", headers=users[2]["headers"], json=changed
        )
        assert corrected.status_code == 201, corrected.text
        code, submit = "source_invalidated", 410
    elif revoked == "consent":
        response = await client.post(
            f"{ROOT}/members/{current['member']}/processing-consents",
            headers=users[0]["headers"],
            json={**consent, "accepted": False},
        )
        assert response.status_code == 200, response.text
        code, submit = "consent", 403
    else:
        async with pg_manager.get_async_session_context() as session:
            grant = await session.get(HealthGrant, (current["member"], users[0]["uid"]))
            grant.scopes = [scope for scope in grant.scopes if scope != revoked]
        code, submit = "not_found", 404
    with pytest.raises(HealthVisionError, match=code):
        await read_safe_context_for_run(context)
    async with pg_manager.get_async_session_context() as session:
        run = await session.get(AgentRun, context.run_id)
        with pytest.raises(HealthVisionError, match=code):
            await validate_safe_planner_publication(session, run, json.dumps(final))
    await assert_safe_private_denied(client, users, context.thread_id, context.run_id, expected_submit=submit)


@ISOLATED
@pytest.mark.parametrize("operation", ["swap", "regeneration"])
async def test_user_confirmation_persists_preview_revision_and_invalidates_old_approval_adoption(
    safe_runtime, operation
):
    """预览不能采用；显式旧HTTP确认保存第二版并使原专业批准/采用失效。"""
    client, users, current, _ = safe_runtime
    owner = users[0]["headers"]
    checked = await client.post(
        f"{ROOT}/meal-plans/{current['plan']}/quality-checks",
        headers=owner,
        json={"client_request_id": str(uuid4()), "version": 1, "rule_code": current["rules"]["rule_code"]},
    )
    assert checked.status_code == 201, checked.text
    detail = await client.get(f"{ROOT}/quality-checks/{checked.json()['check_id']}", headers=owner)
    case = detail.json()["review"]["review_id"]
    await action(client, owner, case, "submit", 1)
    await action(client, users[1]["headers"], case, "approve", 2)
    adopted = await client.post(
        f"{ROOT}/meal-plans/{current['plan']}/adopt",
        headers=owner,
        json={
            "client_request_id": str(uuid4()),
            "version": 1,
            "review_id": case,
            "profile_versions": {current["member"]: 1},
        },
    )
    assert adopted.status_code == 201, adopted.text
    before = await safe_business_facts(current)
    bound, _ = await bind_safe(client, users, current)
    assert bound.status_code == 201, bound.text
    context = await seed_safe_run(users, bound.json()["thread_id"])
    preview = await preview_safe_for_run(
        context, operation, {"meal_type": "lunch", "dish_index": 0} if operation == "swap" else {}
    )
    assert await safe_business_facts(current) == before
    if operation == "swap":
        response = await swap(client, owner, current, preview["result"]["candidates"][0]["recipe_version_id"])
        energy = "310.00"
    else:
        response = await save(
            client,
            owner,
            current,
            {
                **selection(current),
                "client_request_id": str(uuid4()),
                "preview_hash": preview["result"]["preview_hash"],
            },
        )
        energy = "305.00"
    assert response.status_code == 200 and response.json()["version"] == 2, response.text
    assert response.json()["nutrition"]["totals"]["energy_kcal"] == energy
    async with pg_manager.get_async_session_context() as session:
        rows = (
            await session.scalars(
                select(HealthMealPlanRevision)
                .where(HealthMealPlanRevision.plan_id == current["plan"])
                .order_by(HealthMealPlanRevision.version)
            )
        ).all()
        assert len(rows) == 2 and rows[0].snapshot["nutrition"]["totals"]["energy_kcal"] == "300.00"
        assert rows[1].snapshot["nutrition"]["totals"]["energy_kcal"] == energy
        assert (await session.get(HealthProfessionalReview, case)).status == "invalidated"
        old = await session.get(HealthMealPlanAdoption, adopted.json()["adoption_id"])
        assert old.status == "invalidated" and old.snapshot == adopted.json()["snapshot"]
        assert await session.scalar(select(DietLog).where(DietLog.member_id == current["member"])) is None
    with pytest.raises(HealthVisionError, match="source_invalidated"):
        await read_safe_context_for_run(context)


async def test_replay_rejects_extra_tools_and_nonliteral_nutrition_oracles():
    """回放自身负控阻断工具扩大及伪造的业务数值。"""
    token = uuid4().hex
    body = {
        "model": SAFE_PLANNER_MODEL,
        "stream": True,
        "tools": [{"function": {"name": name}} for name in sorted(SAFE_PLANNER_TOOLS)],
        "messages": [
            {"role": "system", "content": "slug: family-meal-planner"},
            {"role": "user", "content": f"SAFE_PLANNER_E2E:{token}:swap"},
        ],
    }
    assert safe_planner_replay_delta("Bearer synthetic-safe-planner-key", body)[3] is False
    second_turn = {
        **body,
        "messages": [body["messages"][0], {"role": "user", "content": f"SAFE_PLANNER_E2E:{token}:swap_second"}],
    }
    with pytest.raises(ValueError, match="prior_safe_checkpoint_required"):
        safe_planner_replay_delta("Bearer synthetic-safe-planner-key", second_turn)
    with pytest.raises(ValueError, match="fixed_safe_tools_required"):
        safe_planner_replay_delta(
            "Bearer synthetic-safe-planner-key",
            {**body, "tools": body["tools"] + [{"function": {"name": "save_plan"}}]},
        )
    context = {
        "scope": "single_member_saved_plan",
        "member_id": str(uuid4()),
        "professional_review": "not_a_professional_decision",
        "plan_snapshot": {"nutrition": {"totals": {"energy_kcal": "999.00"}}},
    }
    with pytest.raises(ValueError, match="independent_original_300kcal_required"):
        safe_planner_replay_delta(
            "Bearer synthetic-safe-planner-key",
            {
                **body,
                "messages": body["messages"]
                + [{"role": "tool", "tool_call_id": f"safe-context-{token}", "content": json.dumps(context)}],
            },
        )
    context["plan_snapshot"]["nutrition"]["totals"]["energy_kcal"] = "300.00"
    context_message = {"role": "tool", "tool_call_id": f"safe-context-{token}", "content": json.dumps(context)}
    assert (
        safe_planner_replay_delta(
            "Bearer synthetic-safe-planner-key", {**body, "messages": [*body["messages"], context_message]}
        )[3]
        is False
    )
    for operation, energy, code in (
        ("swap", "310.00", "independent_310kcal_required"),
        ("regeneration", "305.00", "independent_305kcal_required"),
    ):
        snapshot = {"nutrition": {"totals": {"energy_kcal": energy}}}
        result = (
            {"status": "ready", "candidates": [{"plan_snapshot": snapshot}]}
            if operation == "swap"
            else {"status": "ready", "plan_snapshot": snapshot}
        )
        receipt = {
            "preview_id": str(uuid4()),
            "scope": "single_member_saved_plan",
            "member_id": context["member_id"],
            "operation": operation,
            "result": result,
        }
        messages = [
            body["messages"][0],
            {"role": "user", "content": f"SAFE_PLANNER_E2E:{token}:{operation}"},
            context_message,
            {"role": "tool", "tool_call_id": f"safe-preview-{token}", "content": json.dumps(receipt)},
        ]
        assert safe_planner_replay_delta("Bearer synthetic-safe-planner-key", {**body, "messages": messages})[3] is True
        snapshot["nutrition"]["totals"]["energy_kcal"] = "999.00"
        messages[-1]["content"] = json.dumps(receipt)
        with pytest.raises(ValueError, match=code):
            safe_planner_replay_delta("Bearer synthetic-safe-planner-key", {**body, "messages": messages})


@ISOLATED
async def test_safe_replay_allows_bounded_checkpoint_size_and_preserves_consultation_limit():
    """本地真实wire仅允许单成员大checkpoint，原咨询200KB边界保持。"""
    body = {
        "model": SAFE_PLANNER_MODEL,
        "stream": True,
        "tools": [{"function": {"name": name}} for name in sorted(SAFE_PLANNER_TOOLS)],
        "messages": [
            {"role": "system", "content": "slug: family-meal-planner"},
            {"role": "user", "content": f"SAFE_PLANNER_E2E:{uuid4().hex}:swap"},
        ],
        "synthetic_padding": "x" * 220000,
    }
    async with httpx.AsyncClient(base_url="http://localhost:8766", timeout=10) as replay:
        allowed = await replay.post(
            "/v1/chat/completions", headers={"Authorization": "Bearer synthetic-safe-planner-key"}, json=body
        )
        assert allowed.status_code == 200 and '"name": "get_safe_plan_context"' in allowed.text, allowed.text
        legacy = {
            **body,
            "model": MODEL,
            "tools": [{"function": {"name": name}} for name in sorted(TOOLS)],
            "messages": [
                {"role": "system", "content": "slug: family-nutritionist\n## 咨询流程\n## 日常反馈与记忆边界"},
                {"role": "user", "content": f"HEALTH_CONSULTATION_E2E:{uuid4().hex}:neutral"},
            ],
        }
        denied = await replay.post(
            "/v1/chat/completions", headers={"Authorization": "Bearer synthetic-health-replay-key"}, json=legacy
        )
        assert denied.status_code == 422 and denied.json() == {"error": "outside_synthetic_contract"}
        oversized = await replay.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer synthetic-safe-planner-key"},
            json={**body, "synthetic_padding": "x" * 1000000},
        )
        assert oversized.status_code == 422 and oversized.json() == {"error": "outside_synthetic_contract"}

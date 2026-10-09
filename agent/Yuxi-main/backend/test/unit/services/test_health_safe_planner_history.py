"""私有历史读取也校验原餐单外的候选来源、完整预览及所属Run。"""

import json
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from test.unit.services.test_health_safe_planner import scenario  # noqa: F401
from yuxi.services import health_safe_planner_service as service
from yuxi.services import agent_request_service, health_consultation_service
from yuxi.services.input_message_service import build_chat_input_message
from yuxi.repositories.health_consultation_repository import HealthConsultationRepository
from yuxi.repositories.health_vision_repository import HealthVisionRepository
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.storage.postgres.models_business import TOOL_AUDIT_MESSAGE_TYPE


@pytest.mark.asyncio
@pytest.mark.parametrize("changed", [None, "candidate", "sources", "removed", "owner"])
async def test_private_history_checks_the_existing_receipt_after_candidate_source_changes(
    scenario,  # noqa: F811
    monkeypatch,
    changed,
):
    """独立字面量旧回执仍完整；当前候选改变后私有读取必须拒绝。"""
    scenario.session.scalars = AsyncMock(return_value=SimpleNamespace(all=lambda: [scenario.receipt]))
    scenario.session.execute = AsyncMock(return_value=SimpleNamespace(all=lambda: []))
    current = deepcopy(scenario.receipt.snapshot)
    if changed == "candidate":
        current["candidates"][0]["plan_snapshot"]["nutrition"]["totals"]["energy_kcal"] = "999.00"
    elif changed == "sources":
        current["sources"]["rules"]["version"] = True
    elif changed == "removed":
        current["candidates"] = []
    elif changed == "owner":
        scenario.run.uid = "foreign-owner"

    async def current_preview(_session, _binding, _operation, parameters):
        return parameters, current

    monkeypatch.setattr(service, "safe_preview_in_session", current_preview)
    if changed is None:
        await service.validate_safe_planner_history(scenario.session, scenario.binding)
        assert scenario.session.added == []
    else:
        with pytest.raises(HealthVisionError, match="source_invalidated"):
            await service.validate_safe_planner_history(scenario.session, scenario.binding)


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["final", "audit"])
@pytest.mark.parametrize("change", [None, "approved", "nutrition", "invalid_json", "foreign_receipt", "run"])
async def test_private_history_checks_actual_persisted_message_and_successful_audit(
    scenario,  # noqa: F811
    monkeypatch,
    kind,
    change,
):
    """来源与回执仍合法，独立篡改实际返回正文也必须被私有读取拒绝。"""
    payload = deepcopy(scenario.payload)
    if change == "approved":
        payload["professional_review"] = "approved"
    elif change == "nutrition":
        payload["result"]["candidates"][0]["plan_snapshot"]["nutrition"]["totals"]["energy_kcal"] = "999.00"
    elif change == "foreign_receipt":
        payload["preview_id"] = "00000000-0000-4000-8000-000000000099"
    message = SimpleNamespace(
        content="not-json" if change == "invalid_json" else json.dumps(payload),
        message_type=TOOL_AUDIT_MESSAGE_TYPE if kind == "audit" else "ai",
        conversation_id=3,
        extra_metadata={"tool_name": "preview_safe_plan_swap"},
    )
    actual_run = deepcopy(scenario.run)
    if change == "run":
        actual_run.id = "foreign-message-run"
    scenario.session.scalars = AsyncMock(return_value=SimpleNamespace(all=lambda: [scenario.receipt]))
    scenario.session.execute = AsyncMock(return_value=SimpleNamespace(all=lambda: [(message, actual_run)]))
    recompute = AsyncMock(return_value=(scenario.receipt.parameters, deepcopy(scenario.receipt.snapshot)))
    monkeypatch.setattr(service, "safe_preview_in_session", recompute)
    if change is None:
        await service.validate_safe_planner_history(scenario.session, scenario.binding)
        assert recompute.await_count == 1
        assert scenario.session.added == []
    else:
        with pytest.raises(HealthVisionError):
            await service.validate_safe_planner_history(scenario.session, scenario.binding)


@pytest.mark.asyncio
@pytest.mark.parametrize("had_safe_history", [False, True])
async def test_private_history_cannot_become_generic_when_original_safe_selection_is_removed(
    monkeypatch, had_safe_history
):
    """当前模式已无safe字段，旧Run或专用回执存在时仍拒绝私有历史降级。"""
    binding = SimpleNamespace(
        actor_uid="synthetic",
        member_id="synthetic",
        conversation_id=3,
        safe_planner_selection=None,
        family_planner_selection=None,
        initial_planner_selection=None,
    )
    session = SimpleNamespace(
        scalar=AsyncMock(side_effect=[binding, had_safe_history]),
        get=AsyncMock(return_value=SimpleNamespace(agent_id="health-meal-planner")),
    )
    member_authorize = AsyncMock()
    monkeypatch.setattr(HealthVisionRepository, "authorize", member_authorize)
    if had_safe_history:
        with pytest.raises(HealthVisionError, match="source_invalidated"):
            await HealthConsultationRepository(session).authorize("synthetic", "synthetic", preview_history=True)
        member_authorize.assert_not_awaited()
    else:
        assert (
            await HealthConsultationRepository(session).authorize("synthetic", "synthetic", preview_history=True)
            is binding
        )


@pytest.mark.asyncio
async def test_new_request_rechecks_safe_history_before_request_or_message_persistence(monkeypatch):
    """候选或历史正文已失效时，新用户请求在入队和任何消息写入前拒绝。"""
    session = SimpleNamespace(get=AsyncMock(return_value=SimpleNamespace(agent_id="health-meal-planner")))
    agent = SimpleNamespace(slug="health-meal-planner", backend_id="HealthMealPlannerAgent")
    monkeypatch.setattr(
        agent_request_service,
        "AgentRepository",
        lambda _session: SimpleNamespace(get_visible_by_slug=AsyncMock(return_value=agent)),
    )

    async def history_authorize(_self, _uid, _thread_id, *, lock=False, preview_history=False):
        if preview_history:
            raise HealthVisionError("source_invalidated", "synthetic stale preview", 410)
        return SimpleNamespace(conversation_id=3, member_id="synthetic")

    monkeypatch.setattr(HealthConsultationRepository, "authorize", history_authorize)
    request_lookup = AsyncMock(return_value=None)
    monkeypatch.setattr(
        agent_request_service,
        "AgentRunRequestRepository",
        lambda _session: SimpleNamespace(get_by_request_id=request_lookup),
    )
    existing = SimpleNamespace(
        id="synthetic-existing-run",
        uid="synthetic",
        agent_slug=agent.slug,
        run_type="chat",
        conversation_thread_id="synthetic-thread",
        status="completed",
        input_message_id=1,
    )
    monkeypatch.setattr(
        agent_request_service,
        "AgentRunRepository",
        lambda _session: SimpleNamespace(get_run_by_request_id=AsyncMock(return_value=existing)),
    )
    monkeypatch.setattr(
        health_consultation_service.health_vision_service,
        "configuration",
        AsyncMock(
            return_value={
                "meal_plan": {"available": True, "model": "synthetic/fixed", "processor": "synthetic"},
                "policy_version": "synthetic",
            }
        ),
    )
    monkeypatch.setattr(HealthVisionRepository, "require_consent", AsyncMock())
    monkeypatch.setattr(
        health_consultation_service.SkillRepository,
        "get_by_slug",
        AsyncMock(return_value=SimpleNamespace(source_type="builtin", enabled=True)),
    )
    monkeypatch.setattr(agent_request_service, "require_consultation", health_consultation_service.require_consultation)
    request = agent_request_service.AgentRequestInput(
        agent_slug=agent.slug,
        thread_id="synthetic-thread",
        request_id="synthetic-request",
        input_message=build_chat_input_message("换一道菜"),
        origin=agent_request_service.RunOrigin(source="chat", channel="web"),
    )
    with pytest.raises(HTTPException) as exc:
        await agent_request_service.submit_agent_request(
            request_input=request, current_user=SimpleNamespace(uid="synthetic"), db=session
        )
    assert exc.value.status_code == 410 and exc.value.detail == "synthetic stale preview"
    session.get.assert_not_awaited()
    request_lookup.assert_not_awaited()

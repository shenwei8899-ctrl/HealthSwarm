"""健康任务入口严格选择及当前Run投影的负向边界。"""

import json
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from pydantic import ValidationError

from yuxi.repositories import health_task_repository as repository
from yuxi.repositories.health_task_repository import HealthTaskRepository
from yuxi.services import health_task_service as service
from yuxi.services.health_task_types import HealthTaskEntryInput, HealthTaskResult
from yuxi.services.health_agent_personal_target_types import TargetAwareAnalystInput
from yuxi.services.health_purchase_types import PurchaseSelection
from yuxi.services.health_vision_types import HealthVisionError

MEMBER = str(uuid4())
THREAD = str(uuid4())
TARGET = {"rule_code": "synthetic.target.v1", "rule_version": 1, "profile_version": 1}


def purchase_choice(*, confirmed=False):
    """明确采用选择保留未知库存，不伪造零库存。"""
    return {
        "adoption_id": str(uuid4()),
        "adoption_version": 1,
        "plan_version": 1,
        "inventory_confirmed": confirmed,
        "inventory": [],
    }


@pytest.mark.parametrize(
    "kind",
    [
        "consultation",
        "meal_preview",
        "initial_meal_preview",
        "family_meal_revision",
        "safe_meal_revision",
        "quality_check",
        "purchase_requirements",
        "glucose_plan",
        "multi_day_plan",
        "automatic_family_coordination",
    ],
)
def test_target_selection_only_allowed_in_ordinary_analyst_entry(kind):
    """分析目标不能扩大其他角色或采购的数据范围。"""
    with pytest.raises(ValidationError):
        HealthTaskEntryInput.model_validate(
            {"task_type": kind, "client_request_id": str(uuid4()), "target_selection": TARGET}
        )


@pytest.mark.parametrize("change", [{"weight_kg": "60"}, {"rule_version": "1"}, {"profile_version": True}])
def test_analyst_target_selection_rejects_body_values_and_coerced_versions(change):
    """仅当前批准版本选择有效，不把身体数值交给模型入口。"""
    with pytest.raises(ValidationError):
        HealthTaskEntryInput.model_validate(
            {
                "task_type": "diet_analysis",
                "client_request_id": str(uuid4()),
                "target_selection": {**TARGET, **change},
            }
        )


@pytest.mark.parametrize("field", ["member_id", "nutrition", "sku_id", "approved"])
def test_purchase_selection_forbids_foreign_scope_numbers_and_transaction_fields(field):
    """需求选择复用原业务DTO，不能夹带营养或商品批准。"""
    with pytest.raises(ValidationError):
        HealthTaskEntryInput.model_validate(
            {
                "task_type": "purchase_requirements",
                "client_request_id": str(uuid4()),
                "selection": {**purchase_choice(), field: "untrusted"},
            }
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("target", [None, TARGET])
async def test_analyst_entry_preserves_typed_explicit_selection_and_legacy_none(monkeypatch, target):
    """目标绑定只交给创建Owner，Task不计算或补足目标。"""
    key = uuid4()
    data = HealthTaskEntryInput.model_validate(
        {"task_type": "diet_analysis", "client_request_id": key, "target_selection": target}
    )
    creator = AsyncMock(return_value={"thread_id": THREAD, "agent_slug": "health-diet-analyst"})
    monkeypatch.setattr(service, "create_consultation", creator)
    result = await service.create_health_task_entry("actor", MEMBER, data)
    args, kwargs = creator.await_args
    assert args[:2] == ("actor", MEMBER) and isinstance(args[2], TargetAwareAnalystInput)
    assert args[2].client_request_id == key
    assert kwargs == {"agent_slug": "health-diet-analyst", "target_selection": args[2].target_selection}
    assert args[2].target_selection.model_dump() == target if target is not None else args[2].target_selection is None
    assert result.entry_status == "ready" and result.task_type == "diet_analysis"


@pytest.mark.asyncio
async def test_purchase_entry_missing_selection_only_authorizes_anchor(monkeypatch):
    """缺采用和库存选择不消费线程幂等键或写任务。"""
    authorize = AsyncMock()
    creator = AsyncMock(side_effect=AssertionError("缺选择禁止创建事实"))

    @asynccontextmanager
    async def context():
        yield "session"

    monkeypatch.setattr(service.pg_manager, "get_async_session_context", context)
    monkeypatch.setattr(service, "HealthVisionRepository", lambda _: SimpleNamespace(authorize=authorize))
    monkeypatch.setattr(service, "create_consultation", creator)
    data = HealthTaskEntryInput.model_validate({"task_type": "purchase_requirements", "client_request_id": uuid4()})
    result = await service.create_health_task_entry("actor", MEMBER, data)
    assert result.entry_status == "needs_input" and result.thread_id is None and result.request_submit_url is None
    authorize.assert_awaited_once_with(MEMBER, "actor", "ai_use", lock=True)
    creator.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("confirmed", [False, True])
async def test_purchase_entry_uses_fixed_role_and_exact_existing_selection(monkeypatch, confirmed):
    """独立用途、全员同意和采用版本仍由既有创建Owner核对。"""
    chosen, key = purchase_choice(confirmed=confirmed), uuid4()
    data = HealthTaskEntryInput.model_validate(
        {"task_type": "purchase_requirements", "client_request_id": key, "selection": chosen}
    )
    assert isinstance(data.root.selection, PurchaseSelection)
    creator = AsyncMock(return_value={"thread_id": THREAD, "agent_slug": "health-purchase"})
    monkeypatch.setattr(service, "create_consultation", creator)
    result = await service.create_health_task_entry("actor", MEMBER, data)
    args, kwargs = creator.await_args
    assert args[:2] == ("actor", MEMBER) and args[2].client_request_id == key
    assert kwargs == {"agent_slug": "health-purchase", "purchase_selection": chosen}
    assert result.entry_status == "ready" and result.task_type == "purchase_requirements"


@pytest.mark.asyncio
@pytest.mark.parametrize("questions", [False, True])
async def test_purchase_query_keeps_owner_receipt_or_completed_questions(monkeypatch, questions):
    """未知库存回执仍是业务结果；模型追问独立保持completed。"""
    request = SimpleNamespace(
        request_id="request", agent_slug="health-purchase", conversation_thread_id=THREAD, status="dispatched"
    )
    binding = SimpleNamespace(member_id=MEMBER, conversation_id=7, purchase_selection={"selection": purchase_choice()})
    run = SimpleNamespace(
        id="run",
        status="completed",
        agent_slug="health-purchase",
        conversation_thread_id=THREAD,
        conversation_id=7,
        input_payload={"health_processing": {"purpose": "purchase", "purchase_selection_hash": "selected"}},
    )
    payload = (
        {"status": "needs_input", "questions": ["请确认库存。"], "purchase_available": False}
        if questions
        else {
            "preview_id": str(uuid4()),
            "run_id": "run",
            "result": {
                "status": "needs_input",
                "missing_fields": ["inventory_confirmation"],
                "items": [{"net_required_grams": None}],
                "purchase_available": False,
                "order_available": False,
            },
        }
    )
    message = SimpleNamespace(id=12, content=json.dumps(payload))

    @asynccontextmanager
    async def context():
        yield "session"

    monkeypatch.setattr(service.pg_manager, "get_async_session_context", context)
    monkeypatch.setattr(
        service,
        "HealthTaskRepository",
        lambda _: SimpleNamespace(
            request_context=AsyncMock(return_value=(request, binding, run)),
            final_message=AsyncMock(return_value=message),
        ),
    )
    monkeypatch.setattr(service, "require_consultation", AsyncMock(return_value=(binding, {})))
    validator = AsyncMock()
    monkeypatch.setattr(service, "validate_purchase_publication", validator)
    result = await service.read_health_task("actor", "request")
    assert result.task_type == "purchase_requirements" and result.execution_status == "completed"
    validator.assert_awaited_once_with("session", run, message.content)
    if questions:
        assert result.result.result_type == "needs_input" and result.result.questions == ["请确认库存。"]
    else:
        assert result.result.result_type == "ingredient_requirements" and result.result.data == payload
        assert result.result.data["result"]["items"][0]["net_required_grams"] is None


@pytest.mark.parametrize("field", ["member_id", "actor_uid", "nutrition", "model", "agent_slug"])
def test_entry_rejects_identity_numbers_and_model_selection(field):
    """入口不能扩大固定成员、模型和计算范围。"""
    with pytest.raises(ValidationError):
        HealthTaskEntryInput.model_validate(
            {"task_type": "meal_preview", "client_request_id": str(uuid4()), field: "untrusted"}
        )


def test_entry_discriminator_rejects_mode_mismatch_and_unsupported_payload():
    """专业对象选择不能混进普通模式或尚未支持的控糖用途。"""
    for kind in ("meal_preview", "glucose_plan"):
        with pytest.raises(ValidationError):
            HealthTaskEntryInput.model_validate(
                {"task_type": kind, "client_request_id": str(uuid4()), "selection": {"plan_id": str(uuid4())}}
            )
    for kind in ("initial_meal_preview", "family_meal_revision", "safe_meal_revision", "quality_check"):
        chosen = HealthTaskEntryInput.model_validate({"task_type": kind, "client_request_id": str(uuid4())})
        assert chosen.root.selection is None


def test_task_type_uses_server_binding_and_rejects_multiple_planner_modes():
    """任务类型没有模型文字或客户端来源。"""
    binding = SimpleNamespace(
        initial_planner_selection=None, family_planner_selection=None, safe_planner_selection=None
    )
    assert service.task_type_for_binding("health-meal-planner", binding) == "meal_preview"
    binding.safe_planner_selection = {"selection": "server"}
    assert service.task_type_for_binding("health-meal-planner", binding) == "safe_meal_revision"
    binding.initial_planner_selection = {"selection": "server"}
    with pytest.raises(HealthVisionError, match="source_invalidated"):
        service.task_type_for_binding("health-meal-planner", binding)
    with pytest.raises(HealthVisionError, match="not_found"):
        service.task_type_for_binding("chatbot", binding)


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["foreign", "generic", "missing"])
async def test_request_lookup_rejects_scope_before_loading_binding(monkeypatch, case):
    """管理员和普通Agent不能从健康查询读取他人任务。"""
    request = SimpleNamespace(uid="actor", agent_slug="health-consultation")
    if case == "foreign":
        request.uid = "other"
    elif case == "generic":
        request.agent_slug = "chatbot"
    else:
        request = None
    monkeypatch.setattr(
        repository,
        "AgentRunRequestRepository",
        lambda _: SimpleNamespace(get_by_request_id=AsyncMock(return_value=request)),
    )
    monkeypatch.setattr(repository, "HealthConsultationRepository", lambda _: pytest.fail("无权加载健康绑定"))
    with pytest.raises(HealthVisionError, match="not_found"):
        await HealthTaskRepository("session").request_context("actor", "request")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "field", ["uid", "request_id", "agent_slug", "conversation_id", "conversation_thread_id", "run_type"]
)
async def test_dispatched_request_requires_exact_run_causal_scope(monkeypatch, field):
    """同用户邻Run或子Agent结果不能替代当前Request。"""
    request = SimpleNamespace(
        uid="actor",
        request_id="request",
        agent_slug="health-consultation",
        conversation_thread_id=THREAD,
        dispatched_run_id="run",
        status="dispatched",
    )
    binding = SimpleNamespace(conversation_id=7, actor_uid="actor", member_id=MEMBER)
    run = SimpleNamespace(
        uid="actor",
        request_id="request",
        agent_slug="health-consultation",
        conversation_id=7,
        conversation_thread_id=THREAD,
        run_type="chat",
    )
    setattr(run, field, "other")
    monkeypatch.setattr(
        repository,
        "AgentRunRequestRepository",
        lambda _: SimpleNamespace(get_by_request_id=AsyncMock(return_value=request)),
    )
    monkeypatch.setattr(
        repository, "HealthConsultationRepository", lambda _: SimpleNamespace(authorize=AsyncMock(return_value=binding))
    )
    monkeypatch.setattr(
        repository, "AgentRunRepository", lambda _: SimpleNamespace(get_run=AsyncMock(return_value=run))
    )
    session = SimpleNamespace(get=AsyncMock(return_value=SimpleNamespace(agent_id="health-consultation")))
    with pytest.raises(HealthVisionError, match="source_invalidated"):
        await HealthTaskRepository(session).request_context("actor", "request")


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["pointer", "audit", "request", "delivery", "missing"])
async def test_final_requires_authoritative_complete_regular_message(monkeypatch, case):
    """缺指针不会降级为同Run最后审计；指针不符不会返回正文。"""
    run = SimpleNamespace(id="run", conversation_id=7, output_message_id=12, request_id="request")
    message = SimpleNamespace(message_type="text", request_id="request", delivery_status="complete")
    if case == "pointer":
        run.output_message_id = None
    elif case == "audit":
        message.message_type = "model_audit"
    elif case == "request":
        message.request_id = "neighbor"
    elif case == "delivery":
        message.delivery_status = "failed"
    else:
        message = None
    loader = AsyncMock(return_value=message)
    monkeypatch.setattr(repository, "AgentRunOutputRepository", lambda _: SimpleNamespace(get_output_message=loader))
    with pytest.raises(HealthVisionError, match="answer_unavailable"):
        await HealthTaskRepository("session").final_message(run)
    if case == "pointer":
        loader.assert_not_awaited()
    else:
        loader.assert_awaited_once_with(
            run_id="run", conversation_id=7, output_message_id=12, allow_legacy_fallback=False
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["pending", "running", "failed", "cancelled", "interrupted"])
async def test_uncompleted_query_never_reads_partial_answer_or_error_text(monkeypatch, status):
    """状态查询不公开部分模型结果及上游错误正文。"""
    request = SimpleNamespace(
        request_id="request", agent_slug="health-consultation", conversation_thread_id=THREAD, status="dispatched"
    )
    binding = SimpleNamespace(member_id=MEMBER)
    run = SimpleNamespace(id="run", status=status, error_message="private health text")
    final = AsyncMock(side_effect=AssertionError("非完成运行禁止读取正文"))

    @asynccontextmanager
    async def context():
        yield "session"

    monkeypatch.setattr(service.pg_manager, "get_async_session_context", context)
    monkeypatch.setattr(
        service,
        "HealthTaskRepository",
        lambda _: SimpleNamespace(request_context=AsyncMock(return_value=(request, binding, run)), final_message=final),
    )
    result = await service.read_health_task("actor", "request")
    assert result.execution_status == status and result.final_message_id is None
    assert "private health text" not in result.model_dump_json()
    assert result.result is None if status in {"pending", "running"} else result.result.result_type == "error"
    final.assert_not_awaited()


@pytest.mark.asyncio
async def test_completed_needs_input_is_not_interrupted_or_validated_result(monkeypatch):
    """业务追问保持completed，不标正式营养或专业结果。"""
    request = SimpleNamespace(
        request_id="request", agent_slug="health-meal-planner", conversation_thread_id=THREAD, status="dispatched"
    )
    binding = SimpleNamespace(
        member_id=MEMBER,
        conversation_id=7,
        initial_planner_selection=None,
        family_planner_selection=None,
        safe_planner_selection=None,
    )
    run = SimpleNamespace(
        id="run",
        status="completed",
        agent_slug="health-meal-planner",
        conversation_thread_id=THREAD,
        conversation_id=7,
        input_payload={"health_processing": {"policy": "selected"}},
    )
    message = SimpleNamespace(id=12, content='{"status":"needs_input","questions":["请明确份量。"]}')

    @asynccontextmanager
    async def context():
        yield "session"

    monkeypatch.setattr(service.pg_manager, "get_async_session_context", context)
    monkeypatch.setattr(
        service,
        "HealthTaskRepository",
        lambda _: SimpleNamespace(
            request_context=AsyncMock(return_value=(request, binding, run)),
            final_message=AsyncMock(return_value=message),
        ),
    )
    monkeypatch.setattr(service, "require_consultation", AsyncMock(return_value=(binding, {})))
    verified = AsyncMock()
    monkeypatch.setattr(service, "validate_task_business_result", verified)
    result = await service.read_health_task("actor", "request")
    assert result.execution_status == "completed" and result.result.result_type == "needs_input"
    assert result.result.questions == ["请明确份量。"] and result.final_message_id == 12
    verified.assert_awaited_once()
    with pytest.raises(ValidationError):
        HealthTaskResult.model_validate({**result.model_dump(), "model_audit": "private"})


@pytest.mark.asyncio
async def test_ordinary_questions_require_whole_current_boundary(monkeypatch):
    """存在合法问题不能夹带模型自报批准或营养。"""
    run = SimpleNamespace(agent_slug="health-meal-planner")
    binding = SimpleNamespace(
        initial_planner_selection=None, family_planner_selection=None, safe_planner_selection=None
    )
    current = {"questions": ["请明确份量。"], **service.PLANNER_BOUNDARY, "status": "needs_input"}
    await service.validate_task_business_result("session", run, binding, current, "unused")
    forged = {**current, "professional_review": "approved"}
    with pytest.raises(HealthVisionError, match="source_invalidated"):
        await service.validate_task_business_result("session", run, binding, forged, "unused")


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["run", "member", "source", "final"])
async def test_ordinary_preview_requires_current_same_run_receipt_and_full_projection(monkeypatch, case):
    """模型保留合法回执ID也不能改营养，邻Run回执不能重用。"""
    preview_id, recipe_id = str(uuid4()), str(uuid4())
    spec = {
        "plan_date": "2026-10-10",
        "meals": [
            {"meal_type": meal, "dishes": [{"recipe_version_id": recipe_id, "grams": "100"}]}
            for meal in ("breakfast", "lunch", "dinner")
        ],
    }
    current = {"nutrition": {"totals": {"energy_kcal": "300.00"}}}
    preview = SimpleNamespace(id=preview_id, run_id="run", member_id=MEMBER, spec=spec, snapshot=current)
    payload = {"preview_id": preview_id, "member_id": MEMBER, **current}
    if case == "run":
        preview.run_id = "neighbor"
    elif case == "member":
        preview.member_id = str(uuid4())
    elif case == "source":
        preview.snapshot = {"nutrition": {"totals": {"energy_kcal": "200.00"}}}
    else:
        payload = {**payload, "nutrition": {"totals": {"energy_kcal": "1"}}}
    monkeypatch.setattr(
        service, "HealthMealPlanRepository", lambda _: SimpleNamespace(preview=AsyncMock(return_value=preview))
    )
    monkeypatch.setattr(service, "calculate_in_session", AsyncMock(return_value=current))
    run = SimpleNamespace(id="run", uid="actor", agent_slug="health-meal-planner")
    binding = SimpleNamespace(
        member_id=MEMBER, initial_planner_selection=None, family_planner_selection=None, safe_planner_selection=None
    )
    with pytest.raises(HealthVisionError) as error:
        await service.validate_task_business_result("session", run, binding, payload, "unused")
    assert error.value.code == ("planner_receipt_invalid" if case in {"run", "member"} else "source_invalidated")

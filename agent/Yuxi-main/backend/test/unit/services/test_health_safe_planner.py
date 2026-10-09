"""单成员安全改版的固定模型协议、完整回执与执行归属负控。"""

import json
from contextlib import asynccontextmanager
from copy import deepcopy
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from yuxi.agents.toolkits.safe_meal_planner import (
    get_safe_plan_context,
    preview_safe_plan_regeneration,
    preview_safe_plan_swap,
)
from yuxi.repositories.health_consultation_repository import HealthConsultationRepository
from yuxi.services import health_consultation_service, health_meal_plan_service
from yuxi.services import health_safe_planner_service as service
from yuxi.services.health_meal_plan_types import PlannerAnswer
from yuxi.services.health_nutrition_service import input_fingerprint
from yuxi.services.health_safe_planner_types import SAFE_PLANNER_TOOLS, SafePlannerInput, SafePlannerSelection
from yuxi.services.health_safe_planner_types import SafeSwapParameters
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.storage.postgres.models_business import AgentRun, Conversation
from yuxi.storage.postgres.models_health import HealthSafePlannerPreview

MEMBER = "00000000-0000-4000-8000-000000000001"
PLAN = "00000000-0000-4000-8000-000000000002"
RECIPE = "00000000-0000-4000-8000-000000000003"
PREVIEW = "00000000-0000-4000-8000-000000000004"
REQUEST = "00000000-0000-4000-8000-000000000005"
REPLACEMENT = "00000000-0000-4000-8000-000000000006"


@pytest.fixture
def scenario():
    """字面量预览是独立oracle，不由被测投影或计算函数生成。"""
    selection = {"plan_id": PLAN, "version": 1, "rule_code": "synthetic", "rule_version": 2, "profile_version": 3}
    current = {
        "member_id": MEMBER,
        "plan_spec": {
            "plan_date": "2026-10-09",
            "meals": [
                {"meal_type": "breakfast", "dishes": [{"recipe_version_id": RECIPE, "grams": "50"}]},
                {"meal_type": "lunch", "dishes": [{"recipe_version_id": RECIPE, "grams": "100"}]},
                {"meal_type": "dinner", "dishes": [{"recipe_version_id": RECIPE, "grams": "150"}]},
            ],
        },
        "plan_snapshot": {
            "nutrition": {
                "totals": {
                    "energy_kcal": "300.00",
                    "protein_g": "15.00",
                    "fat_g": "6.00",
                    "carbohydrate_g": "45.00",
                    "sodium_mg": "60.00",
                }
            }
        },
        "profile": {"id": "synthetic-profile", "version": 3, "status": "ready"},
        "rules": {"id": "synthetic-rules", "version": 2, "status": "ready"},
        "sources": {
            "plan": {"id": PLAN, "version": 1, "content_hash": "a" * 64},
            "profiles": {MEMBER: {"id": "synthetic-profile", "version": 3, "content_hash": "b" * 64}},
            "rules": {"id": "synthetic-rules", "version": 2, "content_hash": "c" * 64},
            "recipes": {RECIPE: "d" * 64},
        },
    }
    binding = SimpleNamespace(
        actor_uid="synthetic-owner",
        member_id=MEMBER,
        conversation_id=3,
        safe_planner_selection={"selection": selection, "source_hash": input_fingerprint(current["sources"])},
        family_planner_selection=None,
        initial_planner_selection=None,
        _safe_planner_current=current,
    )
    run = SimpleNamespace(
        id="synthetic-current-run",
        uid="synthetic-owner",
        agent_slug="health-meal-planner",
        conversation_id=3,
        conversation_thread_id="synthetic-thread",
        input_payload={"health_processing": {"safe_selection_hash": input_fingerprint(binding.safe_planner_selection)}},
    )
    payload = {
        "preview_id": PREVIEW,
        "scope": "single_member_saved_plan",
        "member_id": MEMBER,
        "operation": "swap",
        "result": {
            "status": "ready",
            "candidates": [
                {
                    "recipe_version_id": REPLACEMENT,
                    "planned_grams": "100",
                    "plan_snapshot": {
                        "nutrition": {
                            "totals": {
                                "energy_kcal": "300.00",
                                "protein_g": "15.00",
                                "fat_g": "6.00",
                                "carbohydrate_g": "45.00",
                                "sodium_mg": "60.00",
                            }
                        }
                    },
                    "safety_check": {
                        "status": "passed",
                        "missing": [],
                        "conflicts": [],
                        "checks_version": "quality-rules-v1",
                    },
                }
            ],
            "sources": {
                "plan": {"id": PLAN, "version": 1},
                "rules": {"version": 2},
                "profiles": {MEMBER: {"version": 3}},
            },
            "professional_review": "not_a_professional_decision",
        },
    }
    receipt = SimpleNamespace(
        id=PREVIEW,
        actor_uid="synthetic-owner",
        conversation_id=3,
        run_id=run.id,
        operation="swap",
        parameters={"meal_type": "lunch", "dish_index": 0},
        snapshot=deepcopy(payload["result"]),
    )
    session = ReceiptSession(receipt, run, binding)
    return SimpleNamespace(binding=binding, current=current, run=run, payload=payload, receipt=receipt, session=session)


def test_fixed_tools_expose_only_the_original_dish_position():
    """独立列举固定工具及模型参数，身份和所有版本不可选择。"""
    assert SAFE_PLANNER_TOOLS == (
        "get_safe_plan_context",
        "preview_safe_plan_swap",
        "preview_safe_plan_regeneration",
    )
    for tool, fields in (
        (get_safe_plan_context, set()),
        (preview_safe_plan_swap, {"meal_type", "dish_index"}),
        (preview_safe_plan_regeneration, set()),
    ):
        assert set(tool.tool_call_schema.model_json_schema()["properties"]) == fields


@pytest.mark.parametrize("index", [0, 9])
def test_swap_accepts_both_integer_boundaries(index):
    """首末菜位保留真实整数，不在模型入口截掉合法边界。"""
    assert SafeSwapParameters(meal_type="lunch", dish_index=index).model_dump() == {
        "meal_type": "lunch",
        "dish_index": index,
    }


@pytest.mark.parametrize("index", [True, False, -1, 10, "0", 0.0, None])
def test_swap_rejects_coercion_and_out_of_range_positions(index):
    """布尔、字符串、浮点与越界菜位不能自动变成可信整数。"""
    with pytest.raises(ValidationError):
        SafeSwapParameters(meal_type="lunch", dish_index=index)


@pytest.mark.parametrize("extra", ["uid", "member_id", "run_id", "rule_version", "nutrition", "professional_review"])
def test_swap_rejects_model_controlled_identity_nutrition_and_approval(extra):
    """严格参数不能静默丢弃模型夹带的身份或计算结论。"""
    with pytest.raises(ValidationError):
        SafeSwapParameters.model_validate({"meal_type": "lunch", "dish_index": 0, extra: "forged"})


@pytest.mark.parametrize("extra", ["member_id", "uid", "run_id", "nutrition", "grams", "professional_review"])
def test_thread_entry_rejects_fabricated_runtime_or_business_results(scenario, extra):
    """用户入口仅允许固定对象和来源选择，不接收执行或营养事实。"""
    body = {**scenario.binding.safe_planner_selection["selection"], "client_request_id": REQUEST}
    assert SafePlannerInput.model_validate(body).model_dump(mode="json") == body
    with pytest.raises(ValidationError):
        SafePlannerInput.model_validate({**body, extra: "forged"})


@pytest.mark.parametrize("field", ["version", "rule_version", "profile_version"])
@pytest.mark.parametrize("value", [True, 0, "1", 1.0])
def test_thread_entry_requires_actual_positive_source_versions(scenario, field, value):
    """所有来源版本必须是正整数，不能经类型强转绕过。"""
    body = {**scenario.binding.safe_planner_selection["selection"], "client_request_id": REQUEST, field: value}
    with pytest.raises(ValidationError):
        SafePlannerInput.model_validate(body)


@pytest.mark.parametrize("mode", ["generic", "family", "initial", "mixed_family", "mixed_initial"])
def test_safe_tools_reject_other_or_mixed_planner_modes(scenario, mode):
    """单成员安全工具不能在普通、家庭或初始线程旁路执行。"""
    binding = scenario.binding
    if not mode.startswith("mixed"):
        binding.safe_planner_selection = None
    if "family" in mode:
        binding.family_planner_selection = {"selection": "synthetic"}
    if "initial" in mode:
        binding.initial_planner_selection = {"selection": "synthetic"}
    expected = "source_invalidated" if mode.startswith("mixed") else "safe_selection_required"
    with pytest.raises(HealthVisionError, match=expected):
        service.require_safe_binding(binding)


@pytest.mark.asyncio
async def test_binding_reloads_the_current_sources(scenario, monkeypatch):
    """授权后绑定只保存当前来源，选定对象和专业版本保持明确。"""
    patch_context_owner(monkeypatch, scenario)
    del scenario.binding._safe_planner_current

    selected, current = await service.authorize_safe_planner_binding(scenario.session, scenario.binding)

    assert selected.model_dump(mode="json") == {
        "plan_id": PLAN,
        "version": 1,
        "rule_code": "synthetic",
        "rule_version": 2,
        "profile_version": 3,
    }
    assert current is scenario.current
    assert scenario.binding._safe_planner_current is scenario.current


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["source_hash", "plan_source", "profile_source", "recipe_source", "missing_hash"])
async def test_binding_rejects_a_changed_source_digest(scenario, monkeypatch, change):
    """来源更正与缺失摘要均不能继承线程创建时的许可。"""
    patch_context_owner(monkeypatch, scenario)
    if change == "missing_hash":
        del scenario.binding.safe_planner_selection["source_hash"]
    elif change == "source_hash":
        scenario.binding.safe_planner_selection["source_hash"] = "f" * 64
    elif change == "profile_source":
        scenario.current["sources"]["profiles"][MEMBER]["content_hash"] = "f" * 64
    elif change == "recipe_source":
        scenario.current["sources"]["recipes"][RECIPE] = "f" * 64
    else:
        scenario.current["sources"]["plan"]["version"] = 2
    with pytest.raises(HealthVisionError, match="source_invalidated"):
        await service.authorize_safe_planner_binding(scenario.session, scenario.binding)


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["version", "rule_version", "profile_version"])
async def test_current_context_rejects_stale_selected_versions(scenario, monkeypatch, field):
    """真实上下文Owner分别核对餐单、专业档案和批准规则版本。"""
    patch_business_context(monkeypatch, scenario)
    selection = deepcopy(scenario.binding.safe_planner_selection["selection"])
    selection[field] += 1
    with pytest.raises(HealthVisionError, match="source_invalidated"):
        await service.safe_planner_context_in_session(
            scenario.session, scenario.binding.actor_uid, MEMBER, SafePlannerSelection.model_validate(selection)
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "change,code",
    [
        ("family", "family_operation_not_ready"),
        ("member", "not_found"),
        ("actor", "not_found"),
        ("missing", "not_found"),
        ("malformed", "source_invalidated"),
    ],
)
async def test_current_context_rejects_family_or_foreign_member_objects(scenario, monkeypatch, change, code):
    """持久餐单必须是选定成员的实际单成员对象。"""
    patch_business_context(monkeypatch, scenario)
    if change == "family":
        scenario.session.plan.spec["kind"] = "family"
    elif change == "member":
        scenario.session.plan.member_id = "foreign-member"
    elif change == "actor":
        scenario.session.plan.actor_uid = "foreign-owner"
    elif change == "missing":
        scenario.session.plan = None
    else:
        scenario.session.plan.spec = {"plan_date": "2026-10-09", "meals": []}
    with pytest.raises(HealthVisionError, match=code):
        await service.safe_planner_context_in_session(
            scenario.session,
            scenario.binding.actor_uid,
            MEMBER,
            SafePlannerSelection.model_validate(scenario.binding.safe_planner_selection["selection"]),
        )


@pytest.mark.asyncio
async def test_context_keeps_the_actual_single_member_plan_and_current_versions(scenario, monkeypatch):
    """合法上下文保留完整三餐和当前专业来源，而不产生正式写入。"""
    patch_business_context(monkeypatch, scenario)
    result = await service.safe_planner_context_in_session(
        scenario.session,
        "synthetic-owner",
        MEMBER,
        SafePlannerSelection.model_validate(scenario.binding.safe_planner_selection["selection"]),
    )
    assert result["member_id"] == MEMBER
    assert result["plan_spec"] == {
        "plan_date": "2026-10-09",
        "meals": [
            {"meal_type": "breakfast", "dishes": [{"recipe_version_id": RECIPE, "grams": "50"}]},
            {"meal_type": "lunch", "dishes": [{"recipe_version_id": RECIPE, "grams": "100"}]},
            {"meal_type": "dinner", "dishes": [{"recipe_version_id": RECIPE, "grams": "150"}]},
        ],
    }
    assert result["profile"]["version"] == 3 and result["rules"]["version"] == 2
    assert "profiles" not in result
    assert scenario.session.added == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "change,code",
    [
        ("refresh_version", "source_invalidated"),
        ("profile_unknown", "safe_dependencies_not_ready"),
        ("rules_unknown", "safe_dependencies_not_ready"),
        ("foreign_current_member", "source_invalidated"),
        ("family_current", "source_invalidated"),
    ],
)
async def test_current_context_rejects_changes_during_member_lock_or_quality_reload(
    scenario, monkeypatch, change, code
):
    """锁等待后版本及重新读取的专业范围仍须fail-closed。"""
    patch_business_context(monkeypatch, scenario)
    if change == "refresh_version":
        scenario.session.refresh_version = 2
    elif change == "profile_unknown":
        scenario.current["profile"]["status"] = "unknown"
    elif change == "rules_unknown":
        scenario.current["rules"]["status"] = "unknown"
    elif change == "foreign_current_member":
        scenario.current["member_id"] = "foreign-member"
    else:
        scenario.current["profiles"] = {MEMBER: scenario.current["profile"]}
    del scenario.binding._safe_planner_current
    with pytest.raises(HealthVisionError, match=code):
        await service.authorize_safe_planner_binding(scenario.session, scenario.binding)
    assert not hasattr(scenario.binding, "_safe_planner_current")
    assert scenario.session.added == []


@pytest.mark.asyncio
@pytest.mark.parametrize("denial", ["ai_use", "diet_edit", "profile_view", "consent"])
async def test_denied_authorization_or_consent_exposes_no_professional_context(scenario, monkeypatch, denial):
    """任何必要授权或当前用途同意失效均不得绑定专业资料。"""
    patch_business_context(monkeypatch, scenario)
    scenario.session.denial = denial
    del scenario.binding._safe_planner_current
    with pytest.raises(HealthVisionError, match="synthetic_denied"):
        await service.authorize_safe_planner_binding(scenario.session, scenario.binding)
    assert not hasattr(scenario.binding, "_safe_planner_current")
    assert scenario.session.added == []


def test_context_and_receipt_project_copies_without_promoting_unknown_or_review(scenario, monkeypatch):
    """未知钠值与专业边界保留，返回字典的修改不改变持久来源或回执。"""
    safety = {"status": "unknown", "missing": [{"path": "nutrition.sodium_mg"}], "conflicts": []}
    scenario.current["plan_snapshot"]["nutrition"]["totals"]["sodium_mg"] = None
    monkeypatch.setattr(service, "quality_snapshot", lambda _current: {"safety_check": deepcopy(safety)})
    expected_context = {
        "scope": "single_member_saved_plan",
        "member_id": MEMBER,
        "selection": {"plan_id": PLAN, "version": 1, "rule_code": "synthetic", "rule_version": 2, "profile_version": 3},
        "plan_spec": deepcopy(scenario.current["plan_spec"]),
        "plan_snapshot": {
            "nutrition": {
                "totals": {
                    "energy_kcal": "300.00",
                    "protein_g": "15.00",
                    "fat_g": "6.00",
                    "carbohydrate_g": "45.00",
                    "sodium_mg": None,
                }
            }
        },
        "profile": {"id": "synthetic-profile", "version": 3, "status": "ready"},
        "rules": {"id": "synthetic-rules", "version": 2, "status": "ready"},
        "sources": deepcopy(scenario.current["sources"]),
        "safety_check": safety,
        "professional_review": "not_a_professional_decision",
    }
    context = service.safe_context_result(scenario.binding)
    result = service.safe_preview_result(scenario.binding, scenario.receipt)
    assert context == expected_context
    assert result == scenario.payload
    context["selection"]["version"] = 99
    context["plan_snapshot"]["nutrition"]["totals"]["sodium_mg"] = "0"
    result["result"]["candidates"][0]["planned_grams"] = "999"
    assert scenario.binding.safe_planner_selection["selection"]["version"] == 1
    assert scenario.current["plan_snapshot"]["nutrition"]["totals"]["sodium_mg"] is None
    assert scenario.receipt.snapshot["candidates"][0]["planned_grams"] == "100"


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["swap", "regeneration"])
async def test_preview_calls_business_owner_with_server_bound_identity_and_versions(scenario, monkeypatch, operation):
    """模型只提供菜位，业务Owner收到固定账号、餐单及专业版本。"""
    observed = {}

    async def business_owner(session, uid, plan_id, data):
        """记录业务选择并提供独立候选，不替代被测选择组装。"""
        observed.update(uid=uid, plan_id=plan_id, selection=data.model_dump(mode="json"))
        return None, deepcopy(scenario.payload["result"])

    monkeypatch.setattr(service, "candidates_in_session", business_owner)
    monkeypatch.setattr(service, "regeneration_in_session", business_owner)
    parameters = {"meal_type": "lunch", "dish_index": 0} if operation == "swap" else {}
    actual_parameters, result = await service.safe_preview_in_session(
        scenario.session, scenario.binding, operation, parameters
    )
    assert observed == {
        "uid": "synthetic-owner",
        "plan_id": PLAN,
        "selection": {"version": 1, "rule_code": "synthetic", "rule_version": 2, "profile_version": 3, **parameters},
    }
    assert actual_parameters == parameters
    assert result == scenario.payload["result"]
    assert scenario.session.added == []
    assert scenario.session.plan.version == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "operation,parameters",
    [
        ("participation", {}),
        ("regeneration", {"nutrition": "forged"}),
        ("swap", {"meal_type": "lunch", "dish_index": 0, "rule_version": 99}),
        ("swap", {"meal_type": "snack", "dish_index": 0}),
    ],
)
async def test_preview_rejects_other_operations_or_extra_model_parameters(scenario, operation, parameters):
    """无效操作和额外字段在业务调用前结构化拒绝。"""
    with pytest.raises(HealthVisionError, match="planner_receipt_invalid"):
        await service.safe_preview_in_session(scenario.session, scenario.binding, operation, parameters)
    assert scenario.session.added == []


@pytest.mark.asyncio
async def test_final_answer_returns_the_complete_independent_receipt(scenario, monkeypatch):
    """最终投影保留完整来源、计算值和未审核状态。"""
    patch_preview_owner(monkeypatch, scenario)
    result = await service.safe_answer_in_session(
        scenario.session, scenario.run, scenario.binding, PlannerAnswer(preview_id=PREVIEW)
    )
    assert result == scenario.payload
    assert scenario.session.added == []


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["run_id", "actor_uid", "conversation_id", "missing"])
async def test_final_answer_rejects_receipts_from_other_runs_or_owners(scenario, change):
    """相同成员的相邻Run也不能被选择为本次最终结果。"""
    if change == "missing":
        scenario.session.receipt = None
    else:
        setattr(scenario.receipt, change, "foreign")
    with pytest.raises(HealthVisionError, match="planner_receipt_invalid"):
        await service.safe_answer_in_session(
            scenario.session, scenario.run, scenario.binding, PlannerAnswer(preview_id=PREVIEW)
        )


@pytest.mark.asyncio
async def test_questions_are_an_explicit_needs_input_business_result(scenario):
    """追问不声明安全通过，也不生成预览或正式记录。"""
    result = await service.safe_answer_in_session(
        scenario.session, scenario.run, scenario.binding, PlannerAnswer(questions=["请明确要替换哪餐？"])
    )
    assert result == {
        "scope": "single_member_saved_plan",
        "member_id": MEMBER,
        "status": "needs_input",
        "questions": ["请明确要替换哪餐？"],
        "professional_review": "not_a_professional_decision",
    }
    assert scenario.session.added == []


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["uid", "agent_slug", "conversation_id", "thread", "hash", "approval", "missing"])
async def test_checkpoint_rejects_an_inconsistent_original_run(scenario, change):
    """回执必须证明原Run完整身份和固定选择，不继承同会话其他Run。"""
    if change == "missing":
        scenario.session.original = None
    elif change == "approval":
        scenario.run.input_payload = {"health_processing": None}
    elif change == "hash":
        scenario.run.input_payload["health_processing"]["safe_selection_hash"] = "foreign"
    elif change == "thread":
        scenario.run.conversation_thread_id = "foreign-thread"
    else:
        setattr(scenario.run, change, "foreign")
    with pytest.raises(HealthVisionError, match="source_invalidated"):
        await service.validate_safe_planner_tool_payload(
            scenario.session, scenario.binding, "preview_safe_plan_swap", scenario.payload
        )


@pytest.mark.asyncio
async def test_checkpoint_accepts_a_real_previous_run_receipt(scenario, monkeypatch):
    """恢复允许原Run真实回执，最终选择仍受本Run归属限制。"""
    patch_preview_owner(monkeypatch, scenario)
    scenario.run.id = "synthetic-previous-run"
    scenario.receipt.run_id = scenario.run.id
    await service.validate_safe_planner_tool_payload(
        scenario.session, scenario.binding, "preview_safe_plan_swap", scenario.payload
    )
    assert scenario.session.added == []


@pytest.mark.asyncio
@pytest.mark.parametrize("tool", ["preview_family_plan_swap", "preview_initial_meal_plan", "preview_meal_plan"])
async def test_checkpoint_rejects_a_tool_outside_the_fixed_single_member_mode(scenario, tool):
    """普通和其他模式的工具结果不能夹进安全线程checkpoint。"""
    with pytest.raises(HealthVisionError, match="source_invalidated"):
        await service.validate_safe_planner_tool_payload(scenario.session, scenario.binding, tool, scenario.payload)


@pytest.mark.asyncio
@pytest.mark.parametrize("boundary", ["final", "checkpoint", "publication"])
@pytest.mark.parametrize("change", ["nutrition", "grams", "sources", "review", "candidate", "version_type"])
async def test_complete_receipt_recalculation_rejects_nested_tampering(scenario, monkeypatch, boundary, change):
    """只保留preview_id不足以验证完整候选、来源、份量及专业结论。"""
    patch_preview_owner(monkeypatch, scenario)
    patch_publication_binding(monkeypatch, scenario)
    altered = scenario.receipt.snapshot
    if change == "nutrition":
        altered["candidates"][0]["plan_snapshot"]["nutrition"]["totals"]["sodium_mg"] = "0"
    elif change == "grams":
        altered["candidates"][0]["planned_grams"] = "999"
    elif change == "sources":
        altered["sources"]["rules"]["version"] = 99
    elif change == "review":
        altered["professional_review"] = "approved"
    elif change == "version_type":
        altered["sources"]["plan"]["version"] = True
    else:
        altered["candidates"][0]["recipe_version_id"] = "00000000-0000-4000-8000-000000000099"
    with pytest.raises(HealthVisionError, match="source_invalidated"):
        if boundary == "final":
            await service.safe_answer_in_session(
                scenario.session, scenario.run, scenario.binding, PlannerAnswer(preview_id=PREVIEW)
            )
        elif boundary == "checkpoint":
            await service.validate_safe_planner_tool_payload(
                scenario.session, scenario.binding, "preview_safe_plan_swap", scenario.payload
            )
        else:
            await service.validate_safe_planner_publication(
                scenario.session, scenario.run, json.dumps(scenario.payload)
            )


@pytest.mark.asyncio
@pytest.mark.parametrize("boundary", ["checkpoint", "publication"])
@pytest.mark.parametrize("change", ["member_id", "scope", "operation", "result", "extra", "version_type"])
async def test_public_payload_must_equal_the_entire_server_projection(scenario, monkeypatch, boundary, change):
    """完整模型结果不能改范围、对象、操作或增加伪造结论。"""
    patch_preview_owner(monkeypatch, scenario)
    patch_publication_binding(monkeypatch, scenario)
    payload = deepcopy(scenario.payload)
    if change == "result":
        payload["result"]["professional_review"] = "approved"
    elif change == "version_type":
        payload["result"]["sources"]["plan"]["version"] = True
    elif change == "extra":
        payload["approved"] = True
    else:
        payload[change] = "forged"
    with pytest.raises(HealthVisionError, match="source_invalidated"):
        if boundary == "checkpoint":
            await service.validate_safe_planner_tool_payload(
                scenario.session, scenario.binding, "preview_safe_plan_swap", payload
            )
        else:
            await service.validate_safe_planner_publication(scenario.session, scenario.run, json.dumps(payload))


@pytest.mark.asyncio
async def test_publication_accepts_the_full_independent_payload(scenario, monkeypatch):
    """发布入口重新查真实绑定和完整回执，合格结果保持预览语义。"""
    patch_preview_owner(monkeypatch, scenario)
    patch_publication_binding(monkeypatch, scenario)
    await service.validate_safe_planner_publication(scenario.session, scenario.run, json.dumps(scenario.payload))
    assert scenario.session.added == []
    assert scenario.receipt.snapshot["professional_review"] == "not_a_professional_decision"


@pytest.mark.asyncio
@pytest.mark.parametrize("processing", [None, {}, {"model": "synthetic"}])
async def test_publication_cannot_drop_the_processing_snapshot(scenario, processing):
    """实际安全绑定不能靠丢失Run审批快照绕过发布Owner。"""
    scenario.run.input_payload = {"health_processing": processing}
    with pytest.raises(HealthVisionError, match="policy_changed"):
        await service.validate_safe_planner_publication(scenario.session, scenario.run, '{"questions":["synthetic"]}')


@pytest.mark.asyncio
@pytest.mark.parametrize("removal", ["selection", "binding"])
async def test_publication_cannot_drop_a_binding_while_the_run_retains_its_safe_selection(
    scenario, monkeypatch, removal
):
    """旧Run仍带安全审批时，删除当前选择或绑定不能旁路发布检查。"""
    original_processing = deepcopy(scenario.run.input_payload["health_processing"])
    if removal == "binding":
        scenario.session.binding = None
    else:
        scenario.binding.safe_planner_selection = None

    async def require_missing_binding(_session, _uid, _thread, *, expected, lock):
        """授权Owner拒绝删除后的绑定，不能被发布入口跳过。"""
        assert expected == original_processing and lock is True
        raise HealthVisionError("source_invalidated", "synthetic binding removed", 410)

    monkeypatch.setattr(health_consultation_service, "require_consultation", require_missing_binding)
    with pytest.raises(HealthVisionError, match="source_invalidated"):
        await service.validate_safe_planner_publication(scenario.session, scenario.run, json.dumps(scenario.payload))
    assert scenario.run.input_payload["health_processing"] == original_processing
    assert scenario.session.added == []


@pytest.mark.asyncio
@pytest.mark.parametrize("text", ["[]", "null", "not-json", '{"preview_id":"bad"}', '{"questions":[]}'])
async def test_publication_rejects_unparseable_or_ambiguous_results(scenario, monkeypatch, text):
    """发布边界将非法模型输出转换为明确错误状态。"""
    patch_publication_binding(monkeypatch, scenario)
    with pytest.raises(HealthVisionError, match="planner_output_invalid"):
        await service.validate_safe_planner_publication(scenario.session, scenario.run, text)


@pytest.mark.asyncio
@pytest.mark.parametrize("lease_valid", [True, False])
@pytest.mark.parametrize("operation", ["swap", "regeneration"])
async def test_worker_preview_rechecks_the_final_lease_and_only_writes_a_receipt(
    scenario, monkeypatch, lease_valid, operation
):
    """搜索后失去执行权不能留回执；有效执行也只保存只读预览。"""
    patch_preview_owner(monkeypatch, scenario)
    context = SimpleNamespace(uid="synthetic-owner", run_id=scenario.run.id)
    parameters = {"meal_type": "lunch", "dish_index": 0} if operation == "swap" else {}

    async def require_run(_session, _context):
        """上游授权已通过，末次租约仍必须在写入Owner复核。"""
        return scenario.run, scenario.binding

    async def require_attempt(_repository, _context):
        """独立提供末次执行权状态。"""
        if not lease_valid:
            raise HealthVisionError("execution_not_owned", "synthetic lease expired", 409)
        return scenario.run

    @asynccontextmanager
    async def session_context():
        """提供只记录实际新增业务对象的单位事务。"""
        yield scenario.session

    monkeypatch.setattr(health_meal_plan_service, "require_planner_run", require_run)
    monkeypatch.setattr(HealthConsultationRepository, "require_attempt", require_attempt)
    monkeypatch.setattr(service.pg_manager, "get_async_session_context", session_context)
    monkeypatch.setattr(service, "uuid4", lambda: PREVIEW)
    original_spec = deepcopy(scenario.session.plan.spec)
    original_snapshot = deepcopy(scenario.session.plan.snapshot)

    if lease_valid:
        result = await service.preview_safe_for_run(context, operation, parameters)
        expected = {**scenario.payload, "operation": operation}
        assert result == expected
        assert len(scenario.session.added) == 1
        receipt = scenario.session.added[0]
        assert isinstance(receipt, HealthSafePlannerPreview)
        assert (receipt.actor_uid, receipt.conversation_id, receipt.run_id) == ("synthetic-owner", 3, scenario.run.id)
        assert receipt.parameters == parameters
        assert receipt.snapshot == scenario.payload["result"]
    else:
        with pytest.raises(HealthVisionError, match="execution_not_owned"):
            await service.preview_safe_for_run(context, operation, parameters)
        assert scenario.session.added == []
    assert scenario.session.plan.version == 1
    assert scenario.session.plan.spec == original_spec
    assert scenario.session.plan.snapshot == original_snapshot


class ReceiptSession:
    """显式提供持久身份和新增行，结果断言不依赖mock调用次数。"""

    def __init__(self, receipt, original, binding):
        """保存本测试拥有的回执、Run、线程与原餐单事实。"""
        self.receipt, self.original, self.binding = receipt, original, binding
        self.conversation = SimpleNamespace(thread_id="synthetic-thread")
        self.plan = SimpleNamespace(
            id=PLAN,
            actor_uid="synthetic-owner",
            member_id=MEMBER,
            version=1,
            spec=deepcopy(binding._safe_planner_current["plan_spec"]),
            snapshot=deepcopy(binding._safe_planner_current["plan_snapshot"]),
        )
        self.added = []
        self.for_plan_context = False
        self.refresh_version = None
        self.denial = None

    async def get(self, model, _key):
        """按模型返回真实归属fixture，不从请求payload猜测结果。"""
        if model is AgentRun:
            return self.original
        if model is Conversation:
            return self.conversation
        if model is HealthSafePlannerPreview:
            return self.receipt
        raise AssertionError(f"Unexpected persistent model: {model}")

    async def scalar(self, _statement):
        """测试发布及上下文的真实绑定或原餐单投影。"""
        return self.plan if self.for_plan_context else self.binding

    async def refresh(self, _row):
        """稳定fixture不在成员锁等待期间变化。"""
        if self.refresh_version is not None:
            self.plan.version = self.refresh_version

    def add(self, row):
        """保留新增业务对象便于核对类型、身份和不可变结果。"""
        self.added.append(row)

    async def flush(self):
        """flush不会制造额外业务事实。"""


def patch_context_owner(monkeypatch, scenario):
    """替换专业数据读取Owner，不替代被测绑定摘要校验。"""

    async def context_owner(_session, _uid, _member_id, _selected):
        """提供独立当前专业来源。"""
        return scenario.current

    monkeypatch.setattr(service, "safe_planner_context_in_session", context_owner)


def patch_preview_owner(monkeypatch, scenario):
    """独立oracle重新返回原始业务结果，不复用可篡改持久回执。"""
    result = deepcopy(scenario.payload["result"])

    async def preview_owner(_session, _binding, _operation, parameters):
        """模拟实际候选或搜索Owner的完整重算结果。"""
        return parameters, deepcopy(result)

    monkeypatch.setattr(service, "safe_preview_in_session", preview_owner)


def patch_publication_binding(monkeypatch, scenario):
    """保留实际发布流程，只替换当前授权与同意读取Owner。"""

    async def require_binding(_session, _uid, _thread, *, expected, lock):
        """已授权fixture仍须与发布Run处理摘要相符。"""
        assert lock is True
        assert expected == scenario.run.input_payload["health_processing"]
        return scenario.binding, None

    monkeypatch.setattr(health_consultation_service, "require_consultation", require_binding)


def patch_business_context(monkeypatch, scenario):
    """仅替换权限和专业数据Owner，保留实际对象、模式及版本guard。"""
    from yuxi.services.health_vision_service import health_vision_service

    class HealthRepository:
        """合成账号已经具有本成员授权和处理同意。"""

        def __init__(self, _session):
            """权限fixture不写任何业务对象。"""

        async def authorize(self, _member, _uid, _scope, *, lock=False):
            """当前成员具备独立授权。"""
            if scenario.session.denial == _scope:
                raise HealthVisionError("synthetic_denied", "synthetic authorization withdrawn", 403)

        async def require_consent(self, _member, _uid, _purpose, _processing):
            """固定用途同意可用。"""
            if scenario.session.denial == "consent":
                raise HealthVisionError("synthetic_denied", "synthetic consent withdrawn", 403)

    class QualityRepository:
        """持锁当前专业来源，不替代service版本比较。"""

        def __init__(self, _session):
            """当前专业来源由scenario拥有。"""

        async def lock_profile_sources(self, _ids):
            """单位fixture提供稳定来源。"""

    async def configuration(_session):
        """提供合成审批配置，不涉及外部模型。"""
        return {"policy_version": 1, "meal_plan": {"available": True, "model": "synthetic", "processor": "synthetic"}}

    async def quality_context(_session, _uid, _selected):
        """提供当前来源版本供真实service核对。"""
        return scenario.current

    scenario.session.for_plan_context = True
    monkeypatch.setattr(service, "HealthVisionRepository", HealthRepository)
    monkeypatch.setattr(service, "HealthQualityRepository", QualityRepository)
    monkeypatch.setattr(service, "quality_context_in_session", quality_context)
    monkeypatch.setattr(health_vision_service, "configuration", configuration)

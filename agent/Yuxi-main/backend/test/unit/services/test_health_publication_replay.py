"""发布回放严格推进真实工具回执；不替代HTTP、Worker或PG测试。"""

import json
from copy import deepcopy

import pytest

from test.support.health_validated_publication_replay_server import AUTHORIZATION, MODEL, replay_response

TOKEN = "a" * 32
UUID = "11111111-1111-4111-8111-111111111111"
CONSULTATION_TOOLS = {
    "find_food_packages",
    "select_food_products",
    "get_confirmed_profile",
    "get_confirmed_diet",
    "get_complete_health_profile",
    "get_member_weight_records",
    "get_member_blood_pressure_records",
    "get_member_blood_glucose_records",
    "get_member_blood_lipids_records",
    "query_reviewed_nutrition_knowledge",
    "query_family_nutrition_knowledge",
    "get_member_memories",
    "remember_member_fact",
    "get_meal_feedback",
}


def request_body(role):
    """手写角色工具集合，不能从生产工具生成oracle。"""
    names = (
        CONSULTATION_TOOLS
        if role == "consultation"
        else {f"get_member_{role}_records", "query_reviewed_nutrition_knowledge", "query_family_nutrition_knowledge"}
    )
    skill = "family-nutritionist" if role == "consultation" else "family-" + role.replace("_", "-")
    return {
        "model": MODEL,
        "stream": True,
        "tool_choice": "required",
        "tools": [
            {"type": "function", "function": {"name": name}} for name in sorted(names | {"finalize_health_answer"})
        ],
        "messages": [
            {"role": "system", "content": "slug: " + skill},
            {"role": "user", "content": f"PUBLICATION_E2E:{TOKEN}:{role}:success"},
        ],
    }


def synthetic_records(role):
    """数值独立于业务计算，保持既有实测最小投影oracle。"""
    kind = "blood_glucose" if role == "consultation" else role
    values = {
        "blood_glucose": {"glucose": 5.5, "condition": "fasting"},
        "blood_lipids": {"tc": 4.8, "tg": 1.2, "hdl": 1.3, "ldl": 2.6},
        "blood_pressure": {"systolic": 120, "diastolic": 80},
    }[kind]
    return {
        "status": "ready",
        "code": f"self_{kind}_records",
        "owner": "健康档案服务",
        "member_id": UUID,
        "source_member_id": UUID,
        "period": {"start_date": "2026-09-14", "end_date": "2026-10-13", "timezone": "Asia/Shanghai"},
        "limit": 20,
        "truncated": False,
        "full_health_profile_available": False,
        "nutrition_safety_ready": False,
        "source_hash": "0" * 64,
        "records": [
            {
                "record_id": UUID,
                "unit": "mmHg" if kind == "blood_pressure" else "mmol/L",
                "measured_at": "2026-10-13T00:00:00Z",
                "source": f"synthetic-{kind.replace('_', '-')}-device",
                "version": 1,
                **values,
            }
        ],
    }


def attach(request, delta, payload):
    """仅添加回放明确要求的工具call_id收据。"""
    call = delta["tool_calls"][0]
    request["messages"].append({"role": "tool", "tool_call_id": call["id"], "content": json.dumps(payload)})


def prepared_request(role):
    """真实执行回放的记录和证据校验后，停在finalize工具选择前。"""
    request = request_body(role)
    *_, phase, delta = replay_response(AUTHORIZATION, request)
    assert phase == "records" and delta["content"].startswith("PRIVATE_TOOL_PREAMBLE:")
    attach(request, delta, synthetic_records(role))
    *_, phase, delta = replay_response(AUTHORIZATION, request)
    assert phase == "knowledge"
    attach(request, delta, {"citations": [{"citation_id": UUID, "content": f"publication{TOKEN} 合成审核科普"}]})
    return request


@pytest.mark.parametrize("role", ["consultation", "blood_glucose", "blood_lipids", "blood_pressure"])
def test_exact_four_role_protocol_requires_receipts_finalizer_and_tool_free_answer(role):
    request = prepared_request(role)
    *_, phase, delta = replay_response(AUTHORIZATION, request)
    assert phase == "finalize" and delta["tool_calls"][0]["function"]["name"] == "finalize_health_answer"
    attach(request, delta, "资料准备完成。")
    with pytest.raises(ValueError, match="explicit_tool_free_final_stage_required"):
        replay_response(AUTHORIZATION, request)
    request.pop("tools")
    request.pop("tool_choice")
    *_, phase, delta = replay_response(AUTHORIZATION, request)
    assert phase == "answer" and delta["content"].startswith("PUBLICATION_BODY:")
    assert len(delta["content"]) > 80 and "\n\n" in delta["content"]
    assert delta["content"].count(f"[证据:{UUID}]") == 2
    assert "PRIVATE_REASONING:" in delta["reasoning_content"]


@pytest.mark.parametrize("change", ["missing_select", "duplicate_select", "foreign_tool", "auto_choice"])
def test_consultation_replay_requires_the_exact_new_catalog_tool_contract(change):
    request = request_body("consultation")
    if change == "missing_select":
        request["tools"] = [item for item in request["tools"] if item["function"]["name"] != "select_food_products"]
    elif change == "duplicate_select":
        request["tools"].append({"function": {"name": "select_food_products"}})
    elif change == "foreign_tool":
        request["tools"].append({"function": {"name": "arbitrary_private_tool"}})
    else:
        request["tool_choice"] = "auto"
    with pytest.raises(ValueError, match="fixed_role_tools_required"):
        replay_response(AUTHORIZATION, request)


def test_replay_cannot_enter_final_without_records_knowledge_and_actual_finalize_receipt():
    request = request_body("blood_glucose")
    request.pop("tools")
    request.pop("tool_choice")
    with pytest.raises(ValueError, match="explicit_tool_free_final_stage_required"):
        replay_response(AUTHORIZATION, request)
    request = prepared_request("blood_glucose")
    invalid = deepcopy(request)
    evidence = json.loads(invalid["messages"][-1]["content"])
    evidence["citations"][0]["content"] = "other evidence"
    invalid["messages"][-1]["content"] = json.dumps(evidence)
    with pytest.raises(ValueError, match="actual_synthetic_evidence_required"):
        replay_response(AUTHORIZATION, invalid)
    invalid = deepcopy(request)
    records = json.loads(invalid["messages"][-2]["content"])
    records["records"][0]["glucose"] = 999
    invalid["messages"][-2]["content"] = json.dumps(records)
    with pytest.raises(ValueError, match="expected_synthetic_record_required"):
        replay_response(AUTHORIZATION, invalid)

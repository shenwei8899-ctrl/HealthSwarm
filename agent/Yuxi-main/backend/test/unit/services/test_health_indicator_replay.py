"""独立三工具指标重放必须拒绝额外工具、角色混淆和伪造科普引用。"""

import json
from copy import deepcopy

import pytest

from test.support.health_indicator_replay_server import AUTHORIZATION, MODEL, replay_response

TOKEN = "0" * 32
UUID = "11111111-1111-4111-8111-111111111111"


def body(kind="blood_glucose"):
    """手写模型请求只暴露本指标实测、审核知识与受控科普。"""
    return {
        "model": MODEL,
        "stream": True,
        "tools": [
            {"function": {"name": name}}
            for name in (
                f"get_member_{kind}_records",
                "query_reviewed_nutrition_knowledge",
                "query_family_nutrition_knowledge",
            )
        ],
        "messages": [
            {"role": "system", "content": f"slug: family-{kind.replace('_', '-')}"},
            {"role": "user", "content": f"INDICATOR_E2E:{TOKEN}:{kind}:read"},
        ],
    }


@pytest.mark.parametrize("kind", ["blood_glucose", "blood_lipids", "blood_pressure"])
def test_replay_first_call_uses_only_the_selected_indicator(kind):
    token, selected, mode, phase, delta = replay_response(AUTHORIZATION, body(kind))
    assert (token, selected, mode, phase) == (TOKEN, kind, "read", "records")
    assert delta["tool_calls"][0]["function"] == {"name": f"get_member_{kind}_records", "arguments": "{}"}


@pytest.mark.parametrize(
    "case", ["extra_tool", "other_metric", "duplicate", "wrong_skill", "arbitrary_input", "model", "stream"]
)
def test_replay_refuses_unbounded_or_mismatched_model_input(case):
    request = body()
    if case == "extra_tool":
        request["tools"].append({"function": {"name": "remember_member_fact"}})
    elif case == "other_metric":
        request["tools"][0]["function"]["name"] = "get_member_blood_lipids_records"
    elif case == "duplicate":
        request["tools"][1] = deepcopy(request["tools"][0])
    elif case == "wrong_skill":
        request["messages"][0]["content"] = "slug: family-nutritionist"
    elif case == "arbitrary_input":
        request["messages"][1]["content"] = "real patient data"
    else:
        request[case] = "other"
    with pytest.raises(ValueError):
        replay_response(AUTHORIZATION, request)
    with pytest.raises(ValueError, match="synthetic_model_required"):
        replay_response("Bearer other", body())


@pytest.mark.parametrize("with_evidence", [True, False])
def test_replay_real_record_then_knowledge_preserves_actual_citation_or_gap(with_evidence):
    request = body()
    call_id = f"indicator-{TOKEN}-blood_glucose-read"
    records = {
        "status": "ready",
        "code": "self_blood_glucose_records",
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
                "glucose": 5.5,
                "condition": "fasting",
                "unit": "mmol/L",
                "measured_at": "2026-10-13T00:00:00Z",
                "source": "synthetic-blood-glucose-device",
                "version": 1,
            }
        ],
    }
    request["messages"].append({"role": "tool", "tool_call_id": f"{call_id}-records", "content": json.dumps(records)})
    *_, phase, delta = replay_response(AUTHORIZATION, request)
    assert phase == "knowledge" and delta["tool_calls"][0]["function"]["name"] == "query_reviewed_nutrition_knowledge"
    evidence = {
        "personal_meal_plan_available": False,
        "citations": [{"scope": "general_education", "citation_id": UUID, "content": f"indicator{TOKEN} 合成科普"}]
        if with_evidence
        else [],
    }
    request["messages"].append(
        {"role": "tool", "tool_call_id": f"{call_id}-knowledge", "content": json.dumps(evidence)}
    )
    *_, phase, delta = replay_response(AUTHORIZATION, request)
    assert phase == "answer" and '"glucose": 5.5' in delta["content"] and '"condition": "fasting"' in delta["content"]
    assert (f"[证据:{UUID}]" in delta["content"]) is with_evidence
    if with_evidence:
        evidence["citations"][0]["content"] = "other evidence"
        request["messages"][-1]["content"] = json.dumps(evidence)
        with pytest.raises(ValueError, match="actual_synthetic_citation_required"):
            replay_response(AUTHORIZATION, request)


@pytest.mark.parametrize("kind", ["blood_glucose", "blood_lipids", "blood_pressure"])
def test_topic_replay_uses_real_dual_library_receipt_and_rejects_foreign_role(kind):
    """独立协议不凭工具名成功，必须收到本角色双库合成资料。"""
    request = body(kind)
    request["messages"][1]["content"] = f"INDICATOR_E2E:{TOKEN}:{kind}:education"
    *_, phase, delta = replay_response(AUTHORIZATION, request)
    assert phase == "education" and delta["tool_calls"][0]["function"]["name"] == "query_family_nutrition_knowledge"
    kb_ids = [f"pytest_indicator_{kind.removeprefix('blood_')}", "pytest_indicator_common"]
    payload = {
        "status": "ok",
        "scope": "general_education",
        "kb_ids": kb_ids,
        "sources": [
            {
                "kb_id": kb,
                "filename": f"{kb}.md",
                "source_id": UUID,
                "content": f"topic{TOKEN} synthetic education {kb}",
            }
            for kb in kb_ids
        ],
    }
    request["messages"].append(
        {"role": "tool", "tool_call_id": f"indicator-{TOKEN}-{kind}-education", "content": json.dumps(payload)}
    )
    *_, phase, delta = replay_response(AUTHORIZATION, request)
    assert phase == "answer" and f"[资料:{UUID}]" in delta["content"]
    payload["sources"][0]["kb_id"] = "foreign"
    request["messages"][-1]["content"] = json.dumps(payload)
    with pytest.raises(ValueError, match="role_scoped_topic_sources_required"):
        replay_response(AUTHORIZATION, request)


@pytest.mark.parametrize("kind", ["blood_glucose", "blood_lipids", "blood_pressure"])
def test_indicator_two_stage_replay_keeps_business_tools_until_explicit_finalization(kind):
    """三指标都先真实检索，再结束准备并进入无工具正文调用。"""
    request = body(kind)
    request["messages"][1]["content"] = f"INDICATOR_E2E:{TOKEN}:{kind}:education"
    request["tools"].append({"function": {"name": "finalize_health_answer"}})
    request["tool_choice"] = "required"
    *_, phase, _ = replay_response(AUTHORIZATION, request)
    assert phase == "education"
    kb_ids = [f"pytest_indicator_{kind.removeprefix('blood_')}", "pytest_indicator_common"]
    payload = {
        "status": "ok",
        "scope": "general_education",
        "kb_ids": kb_ids,
        "sources": [
            {
                "kb_id": kb,
                "filename": f"{kb}.md",
                "source_id": UUID,
                "content": f"topic{TOKEN} synthetic education {kb}",
            }
            for kb in kb_ids
        ],
    }
    request["messages"].append(
        {"role": "tool", "tool_call_id": f"indicator-{TOKEN}-{kind}-education", "content": json.dumps(payload)}
    )
    *_, phase, delta = replay_response(AUTHORIZATION, request)
    assert phase == "finalize" and delta["tool_calls"][0]["function"]["name"] == "finalize_health_answer"
    request["messages"].append(
        {"role": "tool", "tool_call_id": delta["tool_calls"][0]["id"], "content": "资料准备完成。"}
    )
    with pytest.raises(ValueError, match="explicit_finalization_required"):
        replay_response(AUTHORIZATION, request)
    request.pop("tools")
    request.pop("tool_choice")
    *_, phase, answer = replay_response(AUTHORIZATION, request)
    assert phase == "answer" and f"[资料:{UUID}]" in answer["content"]

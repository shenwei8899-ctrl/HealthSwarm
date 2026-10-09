"""合成血糖协议的独立测量条件 oracle。"""

import json

import pytest

from test.support.health_consultation_replay_server import validate_request
from test.unit.services.test_health_consultation_replay import AUTH, TOKEN, replay_body


@pytest.mark.parametrize("updated", [False, True])
def test_glucose_replay_accepts_declared_condition_and_rejects_tampering(updated):
    """固定样例证明仅更正条件时读取当前独立版本。"""
    step = "glucose_updated" if updated else "glucose_read"
    body = replay_body()
    body["messages"][-1]["content"] = f"HEALTH_CONSULTATION_E2E:{TOKEN}:{step}"
    payload = {
        "status": "ready",
        "code": "self_blood_glucose_records",
        "owner": "健康档案服务",
        "member_id": "11111111-1111-1111-1111-111111111111",
        "source_member_id": "22222222-2222-2222-2222-222222222222",
        "period": {"start_date": "2026-09-09", "end_date": "2026-10-08", "timezone": "Asia/Shanghai"},
        "limit": 20,
        "records": [
            {
                "record_id": "33333333-3333-3333-3333-333333333333",
                "glucose": 5.5,
                "condition": "after_meal_2h" if updated else "fasting",
                "unit": "mmol/L",
                "measured_at": "2026-10-08T01:00:00Z",
                "source": "synthetic-device",
                "version": 2 if updated else 1,
            }
        ],
        "truncated": False,
        "full_health_profile_available": False,
        "nutrition_safety_ready": False,
        "source_hash": "b" * 64,
    }
    body["messages"].append(
        {"role": "tool", "tool_call_id": f"health-read-{TOKEN}-{step}", "content": json.dumps(payload)}
    )
    assert validate_request(AUTH, body)[3:] == (True, [payload["records"][0]["record_id"]])
    for condition in ("", "random", "after_meal", None):
        payload["records"][0]["condition"] = condition
        body["messages"][-1]["content"] = json.dumps(payload)
        with pytest.raises(ValueError, match="synthetic_blood_glucose_pair_required"):
            validate_request(AUTH, body)
    del payload["records"][0]["condition"]
    body["messages"][-1]["content"] = json.dumps(payload)
    with pytest.raises(ValueError, match="minimal_blood_glucose_record_required"):
        validate_request(AUTH, body)


def test_glucose_derived_gate_requires_previous_answer_without_tool():
    """持久回执的迟到发布用例不伪装成当前轮重新读取。"""
    body = replay_body()
    body["messages"][-1]["content"] = f"HEALTH_CONSULTATION_E2E:{TOKEN}:glucose_derived_gate"
    with pytest.raises(ValueError, match="prior_blood_glucose_answer_required"):
        validate_request(AUTH, body)
    body["messages"].insert(1, {"role": "assistant", "content": "合成本人血糖5.5 mmol/L，测量条件fasting"})
    assert validate_request(AUTH, body)[3:] == (True, [])

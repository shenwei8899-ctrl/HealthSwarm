"""血脂四项同条原值和独立更正版本的协议oracle。"""

import json
from copy import deepcopy

import pytest

from test.support.health_consultation_replay_server import validate_request
from test.unit.services.test_health_consultation_replay import AUTH, TOKEN, replay_body


def lipids_body(*, updated=False):
    """显式四项预期与模型链路独立，摘要仅作协议形状占位。"""
    step = "lipids_updated" if updated else "lipids_read"
    body = replay_body()
    body["messages"][-1]["content"] = f"HEALTH_CONSULTATION_E2E:{TOKEN}:{step}"
    payload = {
        "status": "ready",
        "code": "self_blood_lipids_records",
        "owner": "健康档案服务",
        "member_id": "11111111-1111-1111-1111-111111111111",
        "source_member_id": "22222222-2222-2222-2222-222222222222",
        "period": {"start_date": "2026-09-09", "end_date": "2026-10-08", "timezone": "Asia/Shanghai"},
        "limit": 20,
        "records": [
            {
                "record_id": "33333333-3333-3333-3333-333333333333",
                "tc": 4.8,
                "tg": 1.2,
                "hdl": 1.3,
                "ldl": 2.7 if updated else 2.6,
                "unit": "mmol/L",
                "measured_at": "2026-10-08T01:00:00Z",
                "source": "synthetic-lab",
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
    return body, payload


@pytest.mark.parametrize("updated", [False, True])
def test_lipids_replay_accepts_single_ldl_change_and_same_record_three_values(updated):
    """单项更正只有LDL和版本改变，其他项来自同一测量。"""
    body, payload = lipids_body(updated=updated)
    assert validate_request(AUTH, body)[3:] == (True, [payload["records"][0]["record_id"]])


@pytest.mark.parametrize("field", ["tc", "tg", "hdl", "ldl"])
@pytest.mark.parametrize("tamper", ["missing", "wrong_value", "bool"])
def test_lipids_replay_rejects_any_missing_or_changed_component(field, tamper):
    """四项各自有固定oracle，缺失和类型伪装不能靠其他项蒙混。"""
    body, payload = lipids_body()
    changed = deepcopy(payload)
    if tamper == "missing":
        changed["records"][0].pop(field)
    else:
        changed["records"][0][field] = True if tamper == "bool" else 9.9
    body["messages"][-1]["content"] = json.dumps(changed)
    expected = "minimal_blood_lipids_record_required" if tamper == "missing" else "synthetic_blood_lipids_pair_required"
    with pytest.raises(ValueError, match=expected):
        validate_request(AUTH, body)


def test_lipids_replay_rejects_private_conditions_and_split_measurements():
    """额外条件以及分成两条的四项不符合公开同条投影。"""
    body, payload = lipids_body()
    payload["records"][0]["condition"] = "合成备注条件"
    body["messages"][-1]["content"] = json.dumps(payload)
    with pytest.raises(ValueError, match="minimal_blood_lipids_record_required"):
        validate_request(AUTH, body)
    payload["records"][0].pop("condition")
    payload["records"].append(deepcopy(payload["records"][0]))
    body["messages"][-1]["content"] = json.dumps(payload)
    with pytest.raises(ValueError, match="synthetic_blood_lipids_record_required"):
        validate_request(AUTH, body)


def test_lipids_derived_gate_requires_previous_answer_without_tool():
    """派生轮次不再次读工具仍有真实前轮血脂事实依赖。"""
    body = replay_body()
    body["messages"][-1]["content"] = f"HEALTH_CONSULTATION_E2E:{TOKEN}:lipids_derived_gate"
    with pytest.raises(ValueError, match="prior_blood_lipids_answer_required"):
        validate_request(AUTH, body)
    body["messages"].insert(1, {"role": "assistant", "content": "合成本人血脂四项tc4.8、tg1.2、hdl1.3、ldl2.6 mmol/L"})
    assert validate_request(AUTH, body)[3:] == (True, [])

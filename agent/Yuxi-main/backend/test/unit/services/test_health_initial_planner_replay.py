"""初始协议独立oracle与固定工具负控。"""

from copy import deepcopy

import pytest

from test.support.health_initial_planner_replay_server import MODEL, replay_delta


def protocol():
    """显式合成协议不从shipping计算生成预期营养值。"""
    return {
        "model": MODEL,
        "stream": True,
        "tools": [{"function": {"name": n}} for n in ("get_initial_plan_context", "preview_initial_meal_plan")],
        "messages": [
            {"role": "system", "content": "slug: family-meal-planner 初始"},
            {"role": "user", "content": "INITIAL_PLANNER_E2E:" + "a" * 32 + ":ready"},
        ],
    }


def test_replay_only_two_tools():
    """额外资源失败，恢复两工具可请求当前上下文。"""
    body = protocol()
    body["tools"].append({"function": {"name": "save_plan"}})
    with pytest.raises(ValueError, match="fixed_initial_tools_required"):
        replay_delta("Bearer synthetic-initial-planner-key", body)
    body["tools"].pop()
    delta, answered = replay_delta("Bearer synthetic-initial-planner-key", body)
    assert not answered and delta["tool_calls"][0]["function"] == {
        "name": "get_initial_plan_context",
        "arguments": "{}",
    }


@pytest.mark.parametrize("family,expected", [(False, "330.00"), (True, "396.00")])
def test_replay_energy_is_independent(family, expected):
    """伪造能量失败，恢复手算330/396才选取服务器回执。"""
    import json

    body = protocol()
    context = {
        "selection": {"kind": "family" if family else "single"},
        "scope": "initial_plan",
        "profiles": {"a": {}, **({"b": {}} if family else {})},
        "full_health_profile_available": False,
    }
    receipt = {
        "status": "ready",
        "preview_id": "server-owned",
        "plan_snapshot": {"nutrition": {"totals": {"energy_kcal": "1.00"}}},
    }
    body["messages"].extend(
        [
            {"role": "tool", "tool_call_id": "context-" + "a" * 32, "content": json.dumps(context)},
            {"role": "tool", "tool_call_id": "preview-" + "a" * 32, "content": json.dumps(receipt)},
        ]
    )
    with pytest.raises(ValueError, match="independent_initial_energy_required"):
        replay_delta("Bearer synthetic-initial-planner-key", body)
    correct = deepcopy(receipt)
    correct["plan_snapshot"]["nutrition"]["totals"]["energy_kcal"] = expected
    body["messages"][-1]["content"] = json.dumps(correct)
    delta, answered = replay_delta("Bearer synthetic-initial-planner-key", body)
    assert answered and json.loads(delta["content"]) == {"preview_id": "server-owned"}

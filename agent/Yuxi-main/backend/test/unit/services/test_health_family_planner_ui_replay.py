"""家庭页面本地回放的自然操作与独立手算拒绝边界。"""

import hashlib
import json

import pytest

from test.support.health_family_planner_replay_server import MODEL
from test.support.health_family_planner_ui_replay import family_ui_delta


def synthetic_body(operation, *, receipt=False, energy=None):
    """合成模型消息明确两成员，原家庭值独立固定360。"""
    prefix = {
        "swap": "请为当前家庭餐单的早餐第1道共同菜提供安全换菜候选。",
        "regeneration": "请为当前家庭餐单重新生成安全三餐预览。",
        "participation": "请调整当前家庭餐单的参加成员和份量。将主成员早餐份量调整为55克，保留其他份量",
    }[operation]
    query = prefix + "\n已选定处理范围：合成A（ID:a）、合成B（ID:b）"
    token = hashlib.sha256((query + "1").encode()).hexdigest()[:32]
    body = {
        "model": MODEL,
        "stream": True,
        "tools": [
            {"function": {"name": name}}
            for name in (
                "get_family_plan_context",
                "preview_family_plan_swap",
                "preview_family_plan_regeneration",
                "preview_family_plan_participation",
            )
        ],
        "messages": [
            {"role": "system", "content": "slug: family-meal-planner\n家庭合成"},
            {"role": "user", "content": query},
        ],
    }
    if receipt:
        total = energy or {"swap": "371.00", "regeneration": "396.00", "participation": "365.00"}[operation]
        snapshot = {"nutrition": {"totals": {"energy_kcal": total}}}
        result = {"status": "ready", "plan_snapshot": snapshot}
        if operation == "swap":
            result["candidates"] = [{"plan_snapshot": snapshot}]
        body["messages"].append(
            {
                "role": "tool",
                "tool_call_id": "preview-" + token,
                "content": json.dumps(
                    {
                        "scope": "family_saved_plan",
                        "member_ids": ["a", "b"],
                        "preview_id": "owned-synthetic-preview",
                        "result": result,
                    }
                ),
            }
        )
    return body


@pytest.mark.parametrize("operation", ["swap", "regeneration", "participation"])
def test_natural_operation_starts_from_fixed_context_tool(operation):
    """所有自然输入必须先读取当前服务器事实，不能直接编造结果。"""
    delta, answered = family_ui_delta("Bearer synthetic-family-planner-key", synthetic_body(operation))
    assert not answered and delta["tool_calls"][0]["function"] == {"name": "get_family_plan_context", "arguments": "{}"}


@pytest.mark.parametrize("operation", ["swap", "regeneration", "participation"])
def test_current_server_receipt_with_independent_energy(operation):
    """正确371/396/365仅选择当前工具返回的preview_id。"""
    delta, answered = family_ui_delta("Bearer synthetic-family-planner-key", synthetic_body(operation, receipt=True))
    assert answered and json.loads(delta["content"]) == {"preview_id": "owned-synthetic-preview"}


@pytest.mark.parametrize("operation", ["swap", "regeneration", "participation"])
def test_wrong_energy_is_rejected_even_with_ready_receipt(operation):
    """恢复错误总量时oracle拒绝，不把ready标记当作计算依据。"""
    with pytest.raises(ValueError, match="independent_family_energy_required"):
        family_ui_delta("Bearer synthetic-family-planner-key", synthetic_body(operation, receipt=True, energy="999.00"))


@pytest.mark.parametrize(
    "change,code",
    [
        ("scope", "explicit_family_scope_required"),
        ("portion", "synthetic_55g_instruction_required"),
        ("slot", "synthetic_breakfast_slot_required"),
        ("credentials", "synthetic_model_required"),
        ("tools", "fixed_family_tools_required"),
    ],
)
def test_replay_rejects_missing_scope_forged_slot_or_non_synthetic_owner(change, code):
    """回放不能无范围运行、扩大固定菜位或消费其他处理方。"""
    body = synthetic_body("participation" if change == "portion" else "swap")
    authorization = "Bearer synthetic-family-planner-key"
    if change == "scope":
        body["messages"][1]["content"] = body["messages"][1]["content"].split("\n")[0]
    elif change == "portion":
        body["messages"][1]["content"] = body["messages"][1]["content"].replace("55克", "56克")
    elif change == "slot":
        body["messages"][1]["content"] = body["messages"][1]["content"].replace("早餐", "午餐")
    elif change == "credentials":
        authorization = "Bearer unsupported-synthetic-key"
    else:
        body["tools"].pop()
    with pytest.raises(ValueError, match=code):
        family_ui_delta(authorization, body)


def third_body(*, context=True, receipt=False, total="420.00"):
    """原A300/B60，已选C只吃早餐60克，固定家庭420手算。"""
    body = synthetic_body("participation")
    query = (
        "请调整当前家庭餐单的参加成员和份量。将拟加入成员加入早餐，份量60克，保留原成员和其他份量\n"
        "已选定处理范围：合成A（ID:a）、合成B（ID:b）、合成C（ID:c）"
    )
    body["messages"][1]["content"] = query
    token = hashlib.sha256((query + "1").encode()).hexdigest()[:32]
    current = {
        "scope": "family_saved_plan",
        "member_id": "a",
        "profiles": {"a": {}, "b": {}, "c": {}},
        "plan_snapshot": {"nutrition": {"totals": {"energy_kcal": "360.00"}}},
        "plan_spec": {
            "meals": [
                {
                    "meal_type": meal,
                    "participant_ids": ["a", "b"] if meal == "breakfast" else ["a"],
                    "dishes": [
                        {
                            "member_portions": [{"member_id": "a", "grams": grams}]
                            + ([{"member_id": "b", "grams": "60"}] if meal == "breakfast" else [])
                        }
                    ],
                }
                for meal, grams in (("breakfast", "50"), ("lunch", "100"), ("dinner", "150"))
            ]
        },
    }
    if context:
        body["messages"].append({"role": "tool", "tool_call_id": "context-" + token, "content": json.dumps(current)})
    if receipt:
        body["messages"].append(
            {
                "role": "tool",
                "tool_call_id": "preview-" + token,
                "content": json.dumps(
                    {
                        "scope": "family_saved_plan",
                        "member_ids": ["a", "b", "c"],
                        "preview_id": "third-owned-preview",
                        "result": {
                            "status": "ready",
                            "plan_snapshot": {
                                "nutrition": {"totals": {"energy_kcal": total}},
                                "members": {
                                    m: {"nutrition": {"totals": {"energy_kcal": v}}}
                                    for m, v in (("a", "300.00"), ("b", "60.00"), ("c", "60.00"))
                                },
                            },
                        },
                    }
                ),
            }
        )
    return body


def test_third_member_starts_with_context_then_preserves_original_portions():
    """添加者只来自明确范围，60克来自自然指令，原A/B及其他餐不改。"""
    initial, answered = family_ui_delta("Bearer synthetic-family-planner-key", third_body(context=False))
    assert not answered and initial["tool_calls"][0]["function"]["name"] == "get_family_plan_context"
    delta, answered = family_ui_delta("Bearer synthetic-family-planner-key", third_body())
    assert not answered and delta["tool_calls"][0]["function"]["name"] == "preview_family_plan_participation"
    allocations = json.loads(delta["tool_calls"][0]["function"]["arguments"])["allocations"]
    assert allocations[0]["dishes"][0]["member_portions"] == [
        {"member_id": "a", "grams": "50"},
        {"member_id": "b", "grams": "60"},
        {"member_id": "c", "grams": "60"},
    ]
    assert [(m["participant_ids"], m["dishes"][0]["member_portions"]) for m in allocations[1:]] == [
        (["a"], [{"member_id": "a", "grams": "100"}]),
        (["a"], [{"member_id": "a", "grams": "150"}]),
    ]


def test_third_member_current_receipt_selects_only_independent_420_result():
    """最终只选择当前收据，错误420总量即使ready也不通过。"""
    final, answered = family_ui_delta("Bearer synthetic-family-planner-key", third_body(receipt=True))
    assert answered and json.loads(final["content"]) == {"preview_id": "third-owned-preview"}
    with pytest.raises(ValueError, match="independent_third_member_energy_required"):
        family_ui_delta("Bearer synthetic-family-planner-key", third_body(receipt=True, total="421.00"))


@pytest.mark.parametrize("change", ["unselected", "wrong_original", "incomplete_context"])
def test_third_member_query_must_match_all_three_actual_selected_profiles(change):
    """自然声明与当前选定档案不一致不能扩大参加范围。"""
    body = third_body()
    context = json.loads(body["messages"][2]["content"])
    if change == "unselected":
        context["profiles"] = {"a": {}, "b": {}, "d": {}}
    elif change == "wrong_original":
        context["plan_snapshot"]["nutrition"]["totals"]["energy_kcal"] = "361.00"
    else:
        context["profiles"].pop("c")
    body["messages"][2]["content"] = json.dumps(context)
    with pytest.raises(ValueError, match="explicit_third_member_context_required"):
        family_ui_delta("Bearer synthetic-family-planner-key", body)

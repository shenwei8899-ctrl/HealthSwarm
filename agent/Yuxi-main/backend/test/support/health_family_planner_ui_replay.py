"""家庭页面自然语言的本地合成协议，保持原四工具回放的验证。"""

import hashlib
import json
import re
from copy import deepcopy

from test.support.health_family_planner_replay_server import MODEL, replay_delta


def family_ui_delta(authorization, body):
    """仅将页面三种明确自然操作映射到独立手算的合成回放。"""
    messages = body.get("messages", [])
    index = next((i for i in range(len(messages) - 1, -1, -1) if messages[i].get("role") == "user"), None)
    if index is None:
        raise ValueError("synthetic_input_required")
    query = str(messages[index].get("content", ""))
    swap = re.match(r"请为当前家庭餐单的(早餐|午餐|晚餐)第(\d+)道共同菜提供安全换菜候选。", query)
    if swap:
        if swap.groups() != ("早餐", "1"):
            raise ValueError("synthetic_breakfast_slot_required")
        mode = "swap"
    elif query.startswith("请为当前家庭餐单重新生成安全三餐预览。"):
        mode = "regeneration"
    elif query.startswith("请调整当前家庭餐单的参加成员和份量"):
        if "将拟加入成员加入早餐，份量60克，保留原成员和其他份量" in query:
            mode = "third_participation"
        elif "将主成员早餐份量调整为55克，保留其他份量" in query:
            mode = "participation"
        else:
            raise ValueError("synthetic_55g_instruction_required")
    else:
        raise ValueError("synthetic_input_required")
    if "已选定处理范围：" not in query:
        raise ValueError("explicit_family_scope_required")
    token = hashlib.sha256((query + str(index)).encode()).hexdigest()[:32]
    if mode == "third_participation":
        return _third_participation_delta(authorization, body, query, token)
    copied = deepcopy(body)
    copied["messages"][index]["content"] = f"FAMILY_PLANNER_E2E:{token}:{mode}"
    preview_id = f"preview-{token}"
    receipt = next(
        (json.loads(m["content"]) for m in messages if m.get("role") == "tool" and m.get("tool_call_id") == preview_id),
        None,
    )
    if receipt is not None:
        result = receipt["result"]
        if mode == "swap":
            if len(result["candidates"]) != 1:
                raise ValueError("synthetic_unique_candidate_required")
            snapshot = result["candidates"][0]["plan_snapshot"]
            expected = "371.00"
        else:
            snapshot = result["plan_snapshot"]
            expected = "396.00" if mode == "regeneration" else "365.00"
        if snapshot["nutrition"]["totals"]["energy_kcal"] != expected:
            raise ValueError("independent_family_energy_required")
        if result["status"] != "ready":
            raise ValueError("synthetic_ready_preview_required")
    return replay_delta(authorization, copied)


def _third_participation_delta(authorization, body, query, token):
    """仅按明确60克指令将已选第三成员加入早餐，原成员分配保持。"""
    if (
        authorization != "Bearer synthetic-family-planner-key"
        or body.get("model") != MODEL
        or body.get("stream") is not True
    ):
        raise ValueError("synthetic_model_required")
    if {t.get("function", {}).get("name") for t in body.get("tools", [])} != {
        "get_family_plan_context",
        "preview_family_plan_swap",
        "preview_family_plan_regeneration",
        "preview_family_plan_participation",
    }:
        raise ValueError("fixed_family_tools_required")
    messages = body.get("messages", [])
    if not any(
        m.get("role") == "system"
        and "slug: family-meal-planner" in str(m.get("content"))
        and "家庭" in str(m.get("content"))
        for m in messages
    ):
        raise ValueError("fixed_family_skill_required")
    context_id, preview_id = "context-" + token, "preview-" + token
    outputs = {
        m.get("tool_call_id"): json.loads(m["content"])
        for m in messages
        if m.get("role") == "tool" and m.get("tool_call_id") in {context_id, preview_id}
    }
    if context_id not in outputs:
        name, args, call_id = "get_family_plan_context", {}, context_id
    else:
        current = outputs[context_id]
        selected = set(current["profiles"])
        named = re.findall(r"ID:([a-z0-9-]+)", query)
        original = {member for meal in current["plan_spec"]["meals"] for member in meal["participant_ids"]}
        added = selected - original
        if (
            current.get("scope") != "family_saved_plan"
            or current["plan_snapshot"]["nutrition"]["totals"]["energy_kcal"] != "360.00"
            or len(selected) != 3
            or len(original) != 2
            or len(added) != 1
            or set(named) != selected
            or len(named) != 3
        ):
            raise ValueError("explicit_third_member_context_required")
        third = added.pop()
        if preview_id in outputs:
            receipt = outputs[preview_id]
            result = receipt["result"]
            snapshot = result["plan_snapshot"]
            anchor = current["member_id"]
            other = (original - {anchor}).pop()
            if (
                receipt.get("scope") != "family_saved_plan"
                or set(receipt["member_ids"]) != selected
                or result.get("status") != "ready"
                or snapshot["nutrition"]["totals"]["energy_kcal"] != "420.00"
                or [snapshot["members"][m]["nutrition"]["totals"]["energy_kcal"] for m in (anchor, other, third)]
                != ["300.00", "60.00", "60.00"]
            ):
                raise ValueError("independent_third_member_energy_required")
            return {"role": "assistant", "content": json.dumps({"preview_id": receipt["preview_id"]})}, True
        allocations = [
            {
                "meal_type": meal["meal_type"],
                "participant_ids": deepcopy(meal["participant_ids"]),
                "dishes": [
                    {"dish_index": i, "member_portions": deepcopy(dish["member_portions"])}
                    for i, dish in enumerate(meal["dishes"])
                ],
            }
            for meal in current["plan_spec"]["meals"]
        ]
        breakfast = next(m for m in allocations if m["meal_type"] == "breakfast")
        breakfast["participant_ids"].append(third)
        breakfast["dishes"][0]["member_portions"].append({"member_id": third, "grams": "60"})
        name, args, call_id = "preview_family_plan_participation", {"allocations": allocations}, preview_id
    return {
        "role": "assistant",
        "tool_calls": [
            {"index": 0, "id": call_id, "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}
        ],
    }, False

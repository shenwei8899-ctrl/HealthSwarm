"""独立家庭配餐协议回放，只接收隔离合成资料及固定四工具。"""

import json
import re
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MODEL = "deterministic-family-meal-plan-20261008"


def replay_delta(authorization, body):
    """验证实际四资源和服务器事实，用当前工具收据选择最终结果。"""
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
    user = next((m for m in reversed(messages) if m.get("role") == "user"), {})
    match = re.fullmatch(
        r"FAMILY_PLANNER_E2E:([0-9a-f]{32}):(participation|swap|regeneration|invalid|foreign|questions)(?::([0-9a-f-]{36}))?",
        str(user.get("content", "")),
    )
    if not match:
        raise ValueError("synthetic_input_required")
    token, mode, foreign = match.groups()
    context_id, preview_id = f"context-{token}", f"preview-{token}"
    outputs = {
        m.get("tool_call_id"): json.loads(m["content"])
        for m in messages
        if m.get("role") == "tool" and m.get("tool_call_id") in {context_id, preview_id}
    }
    if preview_id in outputs:
        receipt = outputs[preview_id]
        if receipt.get("scope") != "family_saved_plan" or len(receipt.get("member_ids", [])) != 2:
            raise ValueError("family_receipt_required")
        if (
            mode in {"participation", "invalid", "foreign"}
            and receipt["result"]["plan_snapshot"]["nutrition"]["totals"]["energy_kcal"] != "365.00"
        ):
            raise ValueError("independent_365kcal_required")
        answer = {"preview_id": foreign if mode == "foreign" else receipt["preview_id"]}
        if mode == "invalid":
            answer["professional_review"] = "approved"
        return {"role": "assistant", "content": json.dumps(answer)}, True
    if context_id in outputs:
        current = outputs[context_id]
        if (
            current.get("scope") != "family_saved_plan"
            or current["plan_snapshot"]["nutrition"]["totals"]["energy_kcal"] != "360.00"
            or len(current["profiles"]) != 2
        ):
            raise ValueError("independent_original_360kcal_required")
        if mode == "questions":
            return {"role": "assistant", "content": json.dumps({"questions": ["合成：需要调整哪一餐？"]})}, True
        if mode == "swap":
            name, args = "preview_family_plan_swap", {"meal_type": "breakfast", "dish_index": 0}
        elif mode == "regeneration":
            name, args = "preview_family_plan_regeneration", {}
        else:
            anchor = current["member_id"]
            allocations = [
                {
                    "meal_type": meal["meal_type"],
                    "participant_ids": meal["participant_ids"],
                    "dishes": [
                        {"dish_index": i, "member_portions": dish["member_portions"]}
                        for i, dish in enumerate(meal["dishes"])
                    ],
                }
                for meal in current["plan_spec"]["meals"]
            ]
            breakfast = next(m for m in allocations if m["meal_type"] == "breakfast")
            next(p for p in breakfast["dishes"][0]["member_portions"] if p["member_id"] == anchor)["grams"] = "55"
            name, args = "preview_family_plan_participation", {"allocations": allocations}
        call_id = preview_id
    else:
        name, args, call_id = "get_family_plan_context", {}, context_id
    return {
        "role": "assistant",
        "tool_calls": [
            {"index": 0, "id": call_id, "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}
        ],
    }, False


class FamilyPlannerReplayHandler(BaseHTTPRequestHandler):
    """只实现本地OpenAI流式消息，不代理外部模型。"""

    def do_POST(self):
        """失败时只返回协议错误，不打印输入和凭据。"""
        try:
            if self.path != "/v1/chat/completions":
                raise ValueError("unsupported_path")
            delta, answered = replay_delta(
                self.headers.get("Authorization"),
                json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0")))),
            )
        except (ValueError, KeyError, TypeError):
            self.send_error(400, "invalid_synthetic_protocol")
            return
        common = {
            "id": "chatcmpl-synthetic-family",
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": MODEL,
        }
        chunks = [
            {**common, "choices": [{"index": 0, "delta": delta, "finish_reason": None}]},
            {
                **common,
                "choices": [{"index": 0, "delta": {}, "finish_reason": "stop" if answered else "tool_calls"}],
                "usage": {"prompt_tokens": 8, "completion_tokens": 4, "total_tokens": 12},
            },
        ]
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Connection", "close")
        self.end_headers()
        try:
            for chunk in chunks:
                self.wfile.write(f"data: {json.dumps(chunk)}\n\n".encode())
                self.wfile.flush()
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass
        self.close_connection = True

    def log_message(self, format, *args):
        """不记录请求正文和凭据。"""


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8772), FamilyPlannerReplayHandler).serve_forever()

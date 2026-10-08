"""隔离初始配餐协议回放，独立核对330/396与固定两工具。"""

import json
import re
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MODEL = "deterministic-initial-meal-plan-20261008"


def replay_delta(authorization, body):
    """只接纳合成请求，答案只能选择服务器当前工具回执。"""
    if (
        authorization != "Bearer synthetic-initial-planner-key"
        or body.get("model") != MODEL
        or body.get("stream") is not True
    ):
        raise ValueError("synthetic_model_required")
    if {t.get("function", {}).get("name") for t in body.get("tools", [])} != {
        "get_initial_plan_context",
        "preview_initial_meal_plan",
    }:
        raise ValueError("fixed_initial_tools_required")
    messages = body.get("messages", [])
    if not any(
        m.get("role") == "system"
        and "slug: family-meal-planner" in str(m.get("content"))
        and "初始" in str(m.get("content"))
        for m in messages
    ):
        raise ValueError("fixed_initial_skill_required")
    user = next((m for m in reversed(messages) if m.get("role") == "user"), {})
    match = re.fullmatch(
        r"INITIAL_PLANNER_E2E:([0-9a-f]{32}):(ready|invalid|foreign|questions)(?::([0-9a-f-]{36}))?",
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
    if context_id in outputs:
        current = outputs[context_id]
        count = 2 if current["selection"]["kind"] == "family" else 1
        if (
            current.get("scope") != "initial_plan"
            or len(current["profiles"]) != count
            or current["full_health_profile_available"] is not False
        ):
            raise ValueError("initial_context_required")
        if preview_id in outputs:
            receipt = outputs[preview_id]
            if receipt.get("status") != "ready" or receipt["plan_snapshot"]["nutrition"]["totals"]["energy_kcal"] != (
                "396.00" if count == 2 else "330.00"
            ):
                raise ValueError("independent_initial_energy_required")
            answer = {"preview_id": foreign if mode == "foreign" else receipt["preview_id"]}
            if mode == "invalid":
                answer["professional_review"] = "approved"
            return {"role": "assistant", "content": json.dumps(answer)}, True
        if mode == "questions":
            return {"role": "assistant", "content": json.dumps({"questions": ["合成：需要生成哪一天？"]})}, True
        name, call_id = "preview_initial_meal_plan", preview_id
    else:
        name, call_id = "get_initial_plan_context", context_id
    return {
        "role": "assistant",
        "content": "UNVERIFIED_INITIAL_MODEL_TEXT",
        "tool_calls": [{"index": 0, "id": call_id, "type": "function", "function": {"name": name, "arguments": "{}"}}],
    }, False


class InitialPlannerReplayHandler(BaseHTTPRequestHandler):
    """本地OpenAI流式协议，不访问外部供应商。"""

    def do_POST(self):
        """失败仅返回协议错误，正文和凭据不记录。"""
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
            "id": "chatcmpl-synthetic-initial",
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
        """不记录请求正文。"""


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8773), InitialPlannerReplayHandler).serve_forever()

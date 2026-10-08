"""只重放合成配餐协议，拒绝其他模型、工具和用户数据。"""

import json
import re
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MODEL = "deterministic-meal-plan-20261006"


def replay_delta(authorization, body):
    """独立oracle检查实际工具与Skill，并使用实际发布菜谱ID。"""
    if authorization != "Bearer synthetic-planner-key" or body.get("model") != MODEL or body.get("stream") is not True:
        raise ValueError("synthetic_model_required")
    if {t.get("function", {}).get("name") for t in body.get("tools", [])} != {
        "search_meal_plan_recipes",
        "preview_meal_plan",
    }:
        raise ValueError("fixed_tools_required")
    messages = body.get("messages", [])
    if not any(m.get("role") == "system" and "slug: family-meal-planner" in str(m.get("content")) for m in messages):
        raise ValueError("fixed_skill_required")
    user = next((m for m in reversed(messages) if m.get("role") == "user"), {})
    match = re.fullmatch(
        r"HEALTH_MEAL_PLANNER_E2E:([0-9a-f]{32}):(valid|invalid|foreign|questions)(?::([0-9a-f-]{36}))?",
        str(user.get("content", "")),
    )
    if not match:
        raise ValueError("synthetic_input_required")
    token, mode, foreign = match.groups()
    if mode == "questions":
        return {"role": "assistant", "content": json.dumps({"questions": ["合成测试：计划日期是什么？"]})}, True
    search_id, preview_id = f"search-{token}", f"preview-{token}"
    outputs = {
        m.get("tool_call_id"): json.loads(m["content"])
        for m in messages
        if m.get("role") == "tool" and m.get("tool_call_id") in {search_id, preview_id}
    }
    if preview_id in outputs:
        result = outputs[preview_id]
        if (
            result.get("personalized") is not False
            or result.get("profile_status") != "not_ready"
            or result.get("nutrition", {}).get("totals", {}).get("energy_kcal") != "300.00"
        ):
            raise ValueError("authoritative_preview_required")
        answer = {"preview_id": foreign if mode == "foreign" else result["preview_id"]}
        if mode == "invalid":
            answer["personalized"] = True
        return {"role": "assistant", "content": json.dumps(answer)}, True
    if search_id in outputs:
        recipes = outputs[search_id].get("recipes", [])
        if len(recipes) != 1 or recipes[0]["name"] != f"合成配餐E2E-{token}":
            raise ValueError("synthetic_recipe_required")
        recipe = recipes[0]["recipe_version_id"]
        args = {
            "plan_date": "2026-10-06",
            "meals": [
                {"meal_type": meal, "dishes": [{"recipe_version_id": recipe, "grams": str(grams)}]}
                for meal, grams in zip(("breakfast", "lunch", "dinner"), (50, 100, 150))
            ],
        }
        name, call_id = "preview_meal_plan", preview_id
    else:
        name, call_id, args = "search_meal_plan_recipes", search_id, {"query": f"合成配餐E2E-{token}"}
    return {
        "role": "assistant",
        "tool_calls": [
            {"index": 0, "id": call_id, "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}
        ],
    }, False


class PlannerReplayHandler(BaseHTTPRequestHandler):
    """本地OpenAI流式协议，不代理外部服务。"""

    def do_POST(self):
        """完整回放一次模型消息，失败时不暴露合成请求内容。"""
        try:
            if self.path != "/v1/chat/completions":
                raise ValueError("unsupported_path")
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))))
            delta, answered = replay_delta(self.headers.get("Authorization"), body)
        except (ValueError, KeyError, TypeError):
            self.send_error(400, "invalid_synthetic_protocol")
            return
        common = {
            "id": "chatcmpl-synthetic-planner",
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
        """不记录模型请求正文与凭据。"""


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8768), PlannerReplayHandler).serve_forever()

"""仅重放合成普通配餐的次日用户登记前置协议。"""

import json
import re
import time
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from zoneinfo import ZoneInfo

MODEL = "deterministic-next-day-plan-20261010"


def replay_delta(authorization, body):
    """固定工具与服务端营养回执是独立模型协议 oracle。"""
    if authorization != "Bearer synthetic-next-day-key" or body.get("model") != MODEL or body.get("stream") is not True:
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
        r"HEALTH_NEXT_DAY_E2E:([0-9a-f]{32}):(tomorrow|today|questions|invalid)",
        str(user.get("content", "")),
    )
    if not match:
        raise ValueError("synthetic_input_required")
    token, mode = match.groups()
    if mode == "questions":
        return {"role": "assistant", "content": json.dumps({"questions": ["合成测试：明日计划日期是什么？"]})}, True
    search_id, preview_id = f"next-search-{token}", f"next-preview-{token}"
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
        answer = {"preview_id": result["preview_id"]}
        if mode == "invalid":
            answer["personalized"] = True
        return {"role": "assistant", "content": json.dumps(answer)}, True
    if search_id in outputs:
        recipes = outputs[search_id].get("recipes", [])
        if len(recipes) != 1 or recipes[0]["name"] != f"合成次日E2E-{token}":
            raise ValueError("synthetic_recipe_required")
        today = datetime.now(ZoneInfo("Asia/Shanghai")).date()
        target_date = today if mode == "today" else today + timedelta(days=1)
        args = {
            "plan_date": target_date.isoformat(),
            "meals": [
                {
                    "meal_type": meal,
                    "dishes": [{"recipe_version_id": recipes[0]["recipe_version_id"], "grams": str(grams)}],
                }
                for meal, grams in zip(("breakfast", "lunch", "dinner"), (50, 100, 150))
            ],
        }
        name, call_id = "preview_meal_plan", preview_id
    else:
        name, call_id, args = "search_meal_plan_recipes", search_id, {"query": f"合成次日E2E-{token}"}
    return {
        "role": "assistant",
        "tool_calls": [
            {"index": 0, "id": call_id, "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}
        ],
    }, False


class NextDayReplayHandler(BaseHTTPRequestHandler):
    """本地 OpenAI 流式回放，仅服务合成模型协议。"""

    def do_POST(self):
        """完成一次模型协议响应，不转发外部请求。"""
        try:
            if self.path != "/v1/chat/completions":
                raise ValueError("unsupported_path")
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))))
            delta, answered = replay_delta(self.headers.get("Authorization"), body)
        except (ValueError, KeyError, TypeError):
            self.send_error(400, "invalid_synthetic_protocol")
            return
        common = {
            "id": "chatcmpl-synthetic-next-day",
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
    ThreadingHTTPServer(("0.0.0.0", 8774), NextDayReplayHandler).serve_forever()

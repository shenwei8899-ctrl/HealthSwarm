"""本地合成分析协议oracle；仅处理指定模型与合成测试消息。"""

import json
import re
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MODEL = "deterministic-diet-analysis-20261007"


def replay_delta(authorization, body):
    """固定工具、Skill和120kcal/钠缺失由独立协议校验。"""
    if authorization != "Bearer synthetic-analyst-key" or body.get("model") != MODEL or body.get("stream") is not True:
        raise ValueError("synthetic_model_required")
    if {tool.get("function", {}).get("name") for tool in body.get("tools", [])} != {
        "list_analysis_meals",
        "analyze_confirmed_meal",
        "analyze_confirmed_period",
    }:
        raise ValueError("fixed_tools_required")
    messages = body.get("messages", [])
    if not any(
        message.get("role") == "system" and "slug: family-diet-analyst" in str(message.get("content"))
        for message in messages
    ):
        raise ValueError("fixed_skill_required")
    user = next((message for message in reversed(messages) if message.get("role") == "user"), {})
    match = re.fullmatch(
        r"HEALTH_DIET_ANALYSIS_E2E:([0-9a-f]{32}):(valid|invalid|foreign|questions|stale|period)(?::([0-9a-f-]{36}))?",
        str(user.get("content", "")),
    )
    if not match:
        raise ValueError("synthetic_input_required")
    token, mode, foreign = match.groups()
    if mode == "questions":
        return {"role": "assistant", "content": json.dumps({"questions": ["合成测试：要分析哪一餐？"]})}, True
    listing_id, analysis_id = f"list-{token}", f"analysis-{token}"
    outputs = {
        message.get("tool_call_id"): json.loads(message["content"])
        for message in messages
        if message.get("role") == "tool" and message.get("tool_call_id") in {listing_id, analysis_id}
    }
    if analysis_id in outputs:
        result = outputs[analysis_id]
        if mode == "period":
            if (
                result.get("scope") != "confirmed_period"
                or result["nutrition"]["totals"]["energy_kcal"]["recorded_total"] != "120.00"
                or result["coverage"]["window_days"] != 7
                or result["coverage"]["days_with_records"] != 1
            ):
                raise ValueError("period_snapshot_required")
            return {"role": "assistant", "content": json.dumps({"period_days": 7, "end_date": "2026-10-07"})}, True
        if result.get("nutrition", {}).get("totals") != {
            "energy_kcal": "120.00",
            "protein_g": "6.00",
            "fat_g": "3.00",
            "carbohydrate_g": "15.00",
            "sodium_mg": None,
        }:
            raise ValueError("confirmed_snapshot_required")
        answer = result["records"][0].copy()
        if mode == "invalid":
            answer["energy_kcal"] = "1"
        if mode == "foreign":
            answer["record_id"] = foreign
        if mode == "stale":
            answer["source_version"] += 1
        return {"role": "assistant", "content": json.dumps(answer)}, True
    if listing_id in outputs:
        records = outputs[listing_id]["records"]
        if len(records) != 1 or records[0]["names"] != ["合成分析食品"]:
            raise ValueError("synthetic_record_required")
        name, call_id = "analyze_confirmed_meal", analysis_id
        args = {key: records[0][key] for key in ("record_id", "source_version")}
        if mode == "period":
            name, args = "analyze_confirmed_period", {"period_days": 7, "end_date": "2026-10-07"}
    else:
        name, call_id, args = "list_analysis_meals", listing_id, {}
    return {
        "role": "assistant",
        "tool_calls": [
            {"index": 0, "id": call_id, "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}
        ],
    }, False


class AnalystReplayHandler(BaseHTTPRequestHandler):
    """只重放本地OpenAI流式协议，不代理外网。"""

    def do_POST(self):
        """非指定合成输入直接拒绝，不记录正文和凭据。"""
        try:
            if self.path != "/v1/chat/completions":
                raise ValueError("unsupported_path")
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))))
            delta, answered = replay_delta(self.headers.get("Authorization"), body)
        except (ValueError, KeyError, TypeError):
            self.send_error(400, "invalid_synthetic_protocol")
            return
        common = {
            "id": "chatcmpl-synthetic-analyst",
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
        """不记录模型请求。"""


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8769), AnalystReplayHandler).serve_forever()

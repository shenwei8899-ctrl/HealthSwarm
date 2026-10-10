"""本地目标绑定分析协议草稿：固定四工具、330目标及120已记录事实。"""

import json
import re
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MODEL = "deterministic-bound-target-20261010"
TOOLS = {
    "list_analysis_meals",
    "analyze_confirmed_meal",
    "analyze_confirmed_period",
    "get_bound_personal_targets",
}
CALLS = []


def replay_delta(authorization, body):
    """手写oracle不调用业务计算：今日330不作用于历史120或空白天。"""
    if authorization != "Bearer synthetic-target-key" or body.get("model") != MODEL or body.get("stream") is not True:
        raise ValueError("synthetic_model_required")
    functions = [tool.get("function", {}) for tool in body.get("tools", [])]
    if len(functions) != 4 or {tool.get("name") for tool in functions} != TOOLS:
        raise ValueError("fixed_four_tools_required")
    target_schema = next(tool for tool in functions if tool["name"] == "get_bound_personal_targets")
    if target_schema.get("parameters", {}).get("properties"):
        raise ValueError("runtime_bound_no_argument_tool_required")
    messages = body.get("messages", [])
    if not any(
        message.get("role") == "system" and "slug: family-diet-analyst" in str(message.get("content"))
        for message in messages
    ):
        raise ValueError("fixed_skill_required")
    index = max(index for index, message in enumerate(messages) if message.get("role") == "user")
    match = re.fullmatch(
        r"HEALTH_AGENT_TARGET_E2E:([0-9a-f]{32}):(single|no_target|questions|invalid|period1|period7|period30)",
        str(messages[index].get("content", "")),
    )
    if match is None:
        raise ValueError("synthetic_input_required")
    token, mode = match.groups()
    call_ids = {name: f"{name}-{token}" for name in TOOLS}
    outputs = {
        message["tool_call_id"]: json.loads(message["content"])
        for message in messages[index + 1 :]
        if message.get("role") == "tool" and message.get("tool_call_id") in call_ids.values()
    }
    CALLS.append({"token": token, "mode": mode, "tool_result_count": len(outputs)})
    if len(CALLS) > 200:
        del CALLS[:-200]
    if mode == "questions":
        return {
            "role": "assistant",
            "content": json.dumps({"questions": ["合成：请明确记录窗口。"]}),
        }, True
    target = outputs.get(call_ids["get_bound_personal_targets"])
    if target is not None and (
        target.get("scope") != "current_personal_targets"
        or target.get("energy_kcal") != "330"
        or target.get("bounds", {}).get("energy_kcal") != {"minimum": "330", "maximum": "330"}
        or target.get("applied_to_record_window") is not False
        or target.get("professional_review") != "not_a_professional_decision"
        or set(target)
        != {
            "scope",
            "status",
            "energy_kcal",
            "bounds",
            "units",
            "sources",
            "source_hash",
            "professional_review",
            "applied_to_record_window",
        }
        or any(key in json.dumps(target) for key in ("weight_kg", "sex_code", "activity_code", "attestations"))
    ):
        raise ValueError("minimal_current_target_required")
    analysis = outputs.get(
        call_ids["analyze_confirmed_period"] if mode.startswith("period") else call_ids["analyze_confirmed_meal"]
    )
    if analysis is not None:
        if analysis.get("personal_target") is not None or analysis.get("personalized") is not False:
            raise ValueError("unapplied_fact_analysis_required")
        if mode.startswith("period"):
            days = int(mode.removeprefix("period"))
            if (
                analysis.get("scope") != "confirmed_period"
                or analysis["coverage"]["window_days"] != days
                or analysis["coverage"]["days_with_records"] != 1
                or len(analysis["coverage"]["dates_without_records"]) != days - 1
                or analysis["nutrition"]["totals"]["energy_kcal"]["recorded_total"] != "120.00"
                or analysis["nutrition"]["totals"]["sodium_mg"]["recorded_total"] is not None
                or analysis["trend"]["direction"] is not None
            ):
                raise ValueError("historical_window_facts_required")
            answer = {"period_days": days, "end_date": "2026-10-07"}
        else:
            if analysis.get("nutrition", {}).get("totals") != {
                "energy_kcal": "120.00",
                "protein_g": "6.00",
                "fat_g": "3.00",
                "carbohydrate_g": "15.00",
                "sodium_mg": None,
            }:
                raise ValueError("confirmed_meal_facts_required")
            answer = analysis["records"][0].copy()
        if mode == "invalid":
            answer["current_personal_targets"] = {"energy_kcal": "999"}
            answer["difference"] = "210"
        return {"role": "assistant", "content": json.dumps(answer)}, True
    listing = outputs.get(call_ids["list_analysis_meals"])
    if listing is not None:
        records = listing["records"]
        if len(records) != 1 or records[0]["names"] != ["合成分析食品"]:
            raise ValueError("one_confirmed_synthetic_record_required")
        if mode.startswith("period"):
            name, args = (
                "analyze_confirmed_period",
                {
                    "period_days": int(mode.removeprefix("period")),
                    "end_date": "2026-10-07",
                },
            )
        else:
            name, args = (
                "analyze_confirmed_meal",
                {key: records[0][key] for key in ("record_id", "source_version")},
            )
    elif target is None and mode != "no_target":
        name, args = "get_bound_personal_targets", {}
    else:
        name, args = "list_analysis_meals", {}
    return {
        "role": "assistant",
        "tool_calls": [
            {
                "index": 0,
                "id": call_ids[name],
                "type": "function",
                "function": {"name": name, "arguments": json.dumps(args)},
            }
        ],
    }, False


class BoundTargetReplayHandler(BaseHTTPRequestHandler):
    """独立本地协议端点，不代理外网、不记录正文或身份。"""

    def do_GET(self):
        """返回就绪或有界合成调用次数，便于真实worker验证。"""
        body = {"status": "ready"} if self.path == "/health" else {"calls": CALLS}
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(body).encode())

    def do_POST(self):
        """拒绝非指定合成流式协议。"""
        try:
            if self.path != "/v1/chat/completions":
                raise ValueError("unsupported_path")
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))))
            delta, answered = replay_delta(self.headers.get("Authorization"), body)
        except (KeyError, TypeError, ValueError):
            self.send_error(400, "invalid_synthetic_protocol")
            return
        common = {
            "id": "chatcmpl-bound-target",
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": MODEL,
        }
        chunks = [
            {
                **common,
                "choices": [{"index": 0, "delta": delta, "finish_reason": None}],
            },
            {
                **common,
                "choices": [
                    {
                        "index": 0,
                        "delta": {},
                        "finish_reason": "stop" if answered else "tool_calls",
                    }
                ],
                "usage": {
                    "prompt_tokens": 8,
                    "completion_tokens": 4,
                    "total_tokens": 12,
                },
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
        """保持无请求正文日志。"""


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8775), BoundTargetReplayHandler).serve_forever()

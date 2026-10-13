"""两工具指标Agent的独立合成协议重放，不代理供应商或读取数据库。"""

import json
import re
import time
from datetime import date, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Lock
from urllib.parse import parse_qs, urlparse

MODEL = "deterministic-health-indicator-20261013"
AUTHORIZATION = "Bearer synthetic-health-indicator-key"
PORT = 8778
OBSERVATIONS = {}
LOCK = Lock()


def replay_response(authorization, body):
    """独立oracle核对固定角色、最小实测及本轮证据，返回下一阶段。"""
    if authorization != AUTHORIZATION or body.get("model") != MODEL or body.get("stream") is not True:
        raise ValueError("synthetic_model_required")
    messages = body.get("messages", [])
    user = next((message for message in reversed(messages) if message.get("role") == "user"), {})
    marker = re.fullmatch(
        r"INDICATOR_E2E:([0-9a-f]{32}):(blood_glucose|blood_lipids|blood_pressure):(read|updated|missing)",
        str(user.get("content", "")),
    )
    if marker is None:
        raise ValueError("synthetic_input_required")
    token, kind, mode = marker.groups()
    names = [tool.get("function", {}).get("name") for tool in body.get("tools", [])]
    record_tool = f"get_member_{kind}_records"
    if len(names) != 2 or set(names) != {record_tool, "query_reviewed_nutrition_knowledge"}:
        raise ValueError("fixed_indicator_tools_required")
    if not any(
        message.get("role") == "system" and f"slug: family-{kind.replace('_', '-')}" in str(message.get("content"))
        for message in messages
    ):
        raise ValueError("fixed_indicator_skill_required")
    record_call = f"indicator-{token}-{kind}-{mode}-records"
    knowledge_call = f"indicator-{token}-{kind}-{mode}-knowledge"
    outputs = {
        message.get("tool_call_id"): json.loads(message["content"])
        for message in messages
        if message.get("role") == "tool" and message.get("tool_call_id") in {record_call, knowledge_call}
    }
    if record_call not in outputs:
        return token, kind, mode, "records", tool_delta(record_tool, {}, record_call)
    payload = outputs[record_call]
    validate_records(payload, kind, mode)
    if knowledge_call not in outputs:
        return (
            token,
            kind,
            mode,
            "knowledge",
            tool_delta("query_reviewed_nutrition_knowledge", {"query": f"indicator{token}"}, knowledge_call),
        )
    evidence = outputs[knowledge_call]
    citations = evidence["citations"]
    if evidence.get("personal_meal_plan_available") is not False or not isinstance(citations, list):
        raise ValueError("general_education_only")
    if citations and (
        len(citations) != 1
        or citations[0].get("scope") != "general_education"
        or not re.fullmatch(r"[0-9a-f-]{36}", str(citations[0].get("citation_id")))
        or f"indicator{token}" not in citations[0].get("content", "")
    ):
        raise ValueError("actual_synthetic_citation_required")
    content = (
        f"INDICATOR_E2E_REVIEW:{token}:{kind}:{mode} 合成记录回顾："
        + json.dumps(payload["records"], ensure_ascii=False, sort_keys=True)
        + "；营养安全未就绪，仅回顾来源事实。"
        + (f" [证据:{citations[0]['citation_id']}]" if citations else " 当前审核依据不足，请补充资料。")
    )
    return token, kind, mode, "answer", {"role": "assistant", "content": content}


def validate_records(payload, kind, mode):
    """期望数值、条件和版本来自手写合成fixture，拒绝旁读字段。"""
    if not isinstance(payload, dict) or set(payload) != {
        "status",
        "code",
        "owner",
        "member_id",
        "source_member_id",
        "period",
        "limit",
        "records",
        "truncated",
        "full_health_profile_available",
        "nutrition_safety_ready",
        "source_hash",
    }:
        raise ValueError("minimal_indicator_projection_required")
    period = payload["period"]
    if (
        set(period) != {"start_date", "end_date", "timezone"}
        or period["timezone"] != "Asia/Shanghai"
        or date.fromisoformat(period["end_date"]) - date.fromisoformat(period["start_date"]) != timedelta(days=29)
        or payload["limit"] != 20
        or payload["truncated"] is not False
        or payload["owner"] != "健康档案服务"
        or payload["full_health_profile_available"] is not False
        or payload["nutrition_safety_ready"] is not False
        or not re.fullmatch(r"[0-9a-f]{64}", str(payload["source_hash"]))
        or not re.fullmatch(r"[0-9a-f-]{36}", str(payload["source_member_id"]))
    ):
        raise ValueError("independent_indicator_source_required")
    if mode == "missing":
        if payload["status"] != "not_ready" or payload["code"] != f"{kind}_missing" or payload["records"] != []:
            raise ValueError("missing_indicator_required")
        return
    if payload["status"] != "ready" or payload["code"] != f"self_{kind}_records" or len(payload["records"]) != 1:
        raise ValueError("single_synthetic_record_required")
    record = payload["records"][0]
    fields = {
        "blood_glucose": {"glucose": 5.5, "condition": "after_meal_2h" if mode == "updated" else "fasting"},
        "blood_lipids": {"tc": 4.8, "tg": 1.2, "hdl": 1.3, "ldl": 2.7 if mode == "updated" else 2.6},
        "blood_pressure": {"systolic": 122 if mode == "updated" else 120, "diastolic": 82 if mode == "updated" else 80},
    }[kind]
    if (
        set(record) != {"record_id", "unit", "measured_at", "source", "version", *fields}
        or any(record[field] != value for field, value in fields.items())
        or record["unit"] != ("mmHg" if kind == "blood_pressure" else "mmol/L")
        or record["version"] != (2 if mode == "updated" else 1)
        or record["source"] != f"synthetic-{kind.replace('_', '-')}-device"
        or not str(record["measured_at"]).endswith("Z")
        or not re.fullmatch(r"[0-9a-f-]{36}", str(record["record_id"]))
    ):
        raise ValueError("expected_synthetic_record_required")


def tool_delta(name, arguments, call_id):
    """只返回真实图已开放的工具及显式合成参数。"""
    return {
        "role": "assistant",
        "tool_calls": [
            {
                "index": 0,
                "id": call_id,
                "type": "function",
                "function": {"name": name, "arguments": json.dumps(arguments)},
            }
        ],
    }


class IndicatorReplayHandler(BaseHTTPRequestHandler):
    """仅接受合成模型流量及无正文的健康与调用观察。"""

    protocol_version = "HTTP/1.1"

    def do_GET(self):  # noqa: N802
        """观察只输出阶段，不复制模型输入和私有健康内容。"""
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            self.write_json(200, {"isolated": True, "model": MODEL})
        elif parsed.path == "/observations":
            token = parse_qs(parsed.query).get("token", [""])[0]
            if not re.fullmatch(r"[0-9a-f]{32}", token):
                self.write_json(422, {"error": "synthetic_token_required"})
                return
            with LOCK:
                calls = list(OBSERVATIONS.get(token, []))
            self.write_json(200, {"calls": calls})
        else:
            self.write_json(404, {"error": "not_found"})

    def do_POST(self):  # noqa: N802
        """本地协议拒绝错角色或额外工具，按真实工具结果返回SSE。"""
        if self.path != "/v1/chat/completions":
            self.write_json(404, {"error": "not_found"})
            return
        try:
            length = int(self.headers.get("content-length", "0"))
            if not 0 < length <= 200000:
                raise ValueError("invalid_length")
            body = json.loads(self.rfile.read(length))
            token, kind, mode, phase, delta = replay_response(self.headers.get("authorization"), body)
        except (ValueError, KeyError, TypeError, IndexError):
            self.write_json(422, {"error": "outside_synthetic_contract"})
            return
        with LOCK:
            OBSERVATIONS.setdefault(token, []).append({"kind": kind, "mode": mode, "phase": phase})
        common = {
            "id": f"indicator-{token}-{mode}-{phase}",
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": MODEL,
        }
        chunks = [
            {**common, "choices": [{"index": 0, "delta": delta, "finish_reason": None}]},
            {
                **common,
                "choices": [{"index": 0, "delta": {}, "finish_reason": "stop" if phase == "answer" else "tool_calls"}],
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

    def write_json(self, status, payload):
        """控制响应不回显请求或凭据。"""
        data = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format, *args):
        """不记录模型正文、账号或Authorization。"""


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", PORT), IndicatorReplayHandler).serve_forever()

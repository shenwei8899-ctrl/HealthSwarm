"""三工具指标Agent的独立合成协议重放，不代理供应商或读取数据库。"""

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
    # 交接验收沿用独立饮食/配餐 oracle；统一合成处理方不会改变来源 Run 的审批摘要。
    query = str(user.get("content", ""))
    if query.startswith("HEALTH_DIET_ANALYSIS_E2E:"):
        from health_diet_analysis_replay_server import MODEL as analyst_model, replay_delta

        delta, answered = replay_delta("Bearer synthetic-analyst-key", {**body, "model": analyst_model})
        return query.split(":")[1], "analyst", "handoff", "answer" if answered else "tool", delta
    if query.startswith("HEALTH_MEAL_PLANNER_E2E:"):
        from health_meal_planner_replay_server import MODEL as planner_model, replay_delta

        systems = [str(m.get("content", "")) for m in messages if m.get("role") == "system"]
        transferred = [
            m.split("当前角色原有用途与工具边界继续生效：\n", 1)[1]
            for m in systems
            if "当前角色原有用途与工具边界继续生效：\n" in m
        ]
        summary = json.JSONDecoder().raw_decode(transferred[0])[0] if len(transferred) == 1 else {}
        if summary.get("scope") != "confirmed_period" or summary.get("window", {}).get("period_days") != 7:
            raise ValueError("frozen_period_handoff_required")
        if (
            "feedback" in summary
            or "answer" in summary
            or summary["nutrition"]["totals"]["sodium_mg"]["recorded_total"] is not None
        ):
            raise ValueError("minimal_facts_with_unknowns_required")
        delta, answered = replay_delta("Bearer synthetic-planner-key", {**body, "model": planner_model})
        return query.split(":")[1], "planner", "handoff", "answer" if answered else "tool", delta
    handoff = re.fullmatch(r"HANDOFF_E2E:([0-9a-f]{32})", str(user.get("content", "")))
    if handoff:
        systems = [str(m.get("content", "")) for m in messages if m.get("role") == "system"]
        transferred = [
            m.split("当前角色原有用途与工具边界继续生效：\n", 1)[1]
            for m in systems
            if "当前角色原有用途与工具边界继续生效：\n" in m
        ]
        if len(transferred) != 1:
            raise ValueError("confirmed_handoff_required")
        summary = json.JSONDecoder().raw_decode(transferred[0])[0]
        if set(summary) != {"kind", "period", "records", "truncated", "notice"}:
            raise ValueError("minimal_handoff_required")
        field, expected = {
            "blood_glucose": ("glucose", 5.5),
            "blood_lipids": ("tc", 4.8),
            "blood_pressure": ("systolic", 120),
        }[summary["kind"]]
        if summary["records"][0][field] != expected:
            raise ValueError("synthetic_record_required")
        names = {tool.get("function", {}).get("name") for tool in body.get("tools", [])}
        if "query_reviewed_nutrition_knowledge" not in names or f"get_member_{summary['kind']}_records" not in names:
            raise ValueError("target_tools_required")
        return (
            handoff[1],
            "handoff",
            "confirmed",
            "answer",
            {"role": "assistant", "content": "已收到用户确认的合成指标记录，仍仅作一般科普解释。"},
        )
    marker = re.fullmatch(
        r"INDICATOR_E2E:([0-9a-f]{32}):(blood_glucose|blood_lipids|blood_pressure):(read|updated|missing|education)",
        str(user.get("content", "")),
    )
    if marker is None:
        raise ValueError("synthetic_input_required")
    token, kind, mode = marker.groups()
    names = [tool.get("function", {}).get("name") for tool in body.get("tools", [])]
    record_tool = f"get_member_{kind}_records"
    if len(names) != 3 or set(names) != {
        record_tool,
        "query_reviewed_nutrition_knowledge",
        "query_family_nutrition_knowledge",
    }:
        raise ValueError("fixed_indicator_tools_required")
    if not any(
        message.get("role") == "system" and f"slug: family-{kind.replace('_', '-')}" in str(message.get("content"))
        for message in messages
    ):
        raise ValueError("fixed_indicator_skill_required")
    if mode == "education":
        return education_response(messages, token, kind, mode)
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


def education_response(messages, token, kind, mode):
    """专题回放独立核对双库、来源和合成正文，拒绝跨角色结果。"""
    call_id = f"indicator-{token}-{kind}-education"
    outputs = [
        message for message in messages if message.get("role") == "tool" and message.get("tool_call_id") == call_id
    ]
    if not outputs:
        return (
            token,
            kind,
            mode,
            "education",
            tool_delta("query_family_nutrition_knowledge", {"query": f"topic{token}"}, call_id),
        )
    payload = json.loads(outputs[-1]["content"])
    expected = [f"pytest_indicator_{kind.removeprefix('blood_')}", "pytest_indicator_common"]
    if (
        payload.get("scope") != "general_education"
        or payload.get("status") != "ok"
        or payload.get("kb_ids") != expected
        or len(payload.get("sources", [])) != 2
        or [source.get("kb_id") for source in payload["sources"]] != expected
    ):
        raise ValueError("role_scoped_topic_sources_required")
    references = []
    for source, kb_id in zip(payload["sources"], expected):
        if (
            source.get("content") != f"topic{token} synthetic education {kb_id}"
            or source.get("filename") != f"{kb_id}.md"
            or not re.fullmatch(r"[0-9a-f-]{36}", str(source.get("source_id")))
        ):
            raise ValueError("actual_topic_source_required")
        references.append(f"《{source['filename']}》[资料:{source['source_id']}]")
    return (
        token,
        kind,
        mode,
        "answer",
        {"role": "assistant", "content": "合成一般科普，仅验证来源引用；" + "；".join(references)},
    )


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
        except (ValueError, KeyError, TypeError, IndexError) as error:
            reason = str(error)
            print(reason if re.fullmatch(r"[a-z_]+", reason) else type(error).__name__, flush=True)
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

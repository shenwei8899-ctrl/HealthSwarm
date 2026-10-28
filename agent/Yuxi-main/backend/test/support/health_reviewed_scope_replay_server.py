"""按预先登记的合成证据ID核对四角色实际模型输入，不访问PG。"""

import json
import re
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Event, Lock
from urllib.parse import parse_qs, urlparse

from test.support.health_consultation_replay_server import TOOLS, final_answer_request, final_answer_tool_delta
from test.support.health_indicator_replay_server import tool_delta

MODEL = "deterministic-health-reviewed-scope-20261013"
PORT = 8780
AUTHORIZATION = "Bearer synthetic-health-reviewed-scope-key"
STATES = {}
LOCK = Lock()


def replay_response(authorization, body):
    """literal allowed-ID与禁入正文先于答复，schema只允许query参数。"""
    if authorization != AUTHORIZATION or body.get("model") != MODEL or body.get("stream") is not True:
        raise ValueError("synthetic_model_required")
    messages = body.get("messages", [])
    user = next((message for message in reversed(messages) if message.get("role") == "user"), {})
    marker = re.fullmatch(
        r"REVIEWED_SCOPE_E2E:([0-9a-f]{32}):(consultation|blood_glucose|blood_lipids|blood_pressure):(success|changed|foreign)",
        str(user.get("content", "")),
    )
    if marker is None:
        raise ValueError("synthetic_input_required")
    token, role, mode = marker.groups()
    with LOCK:
        expected = STATES[token]["roles"][role]
        foreign = STATES[token].get("foreign_citation")
    allowed = (
        TOOLS
        if role == "consultation"
        else {f"get_member_{role}_records", "query_reviewed_nutrition_knowledge", "query_family_nutrition_knowledge"}
    )
    body, stage, finalize_id = final_answer_request(body, allowed)
    names = [tool.get("function", {}).get("name") for tool in body.get("tools", [])]
    if len(names) != len(allowed) or set(names) != allowed:
        raise ValueError("fixed_role_tools_required")
    if stage != "final":
        tool = next(
            tool["function"]
            for tool in body["tools"]
            if tool["function"]["name"] == "query_reviewed_nutrition_knowledge"
        )
        if set(tool["parameters"]["properties"]) != {"query"} or tool["parameters"]["required"] != ["query"]:
            raise ValueError("query_only_tool_required")
    serialized = json.dumps(body, ensure_ascii=False)
    if any(marker in serialized for marker in expected["forbidden"]):
        raise ValueError("forbidden_scope_reached_model")
    knowledge_id = f"scope-knowledge-{token}-{role}-{mode}"
    output = next(
        (
            json.loads(message["content"])
            for message in messages
            if message.get("role") == "tool" and message.get("tool_call_id") == knowledge_id
        ),
        None,
    )
    if output is None:
        if stage == "final":
            raise ValueError("final_stage_requires_actual_tool_receipts")
        return (
            token,
            role,
            mode,
            "knowledge",
            tool_delta("query_reviewed_nutrition_knowledge", {"query": f"scope{token}"}, knowledge_id),
        )
    citations = output["citations"]
    if set(citation["evidence_id"] for citation in citations) != set(expected["evidence_ids"]) or len(citations) != len(
        expected["evidence_ids"]
    ):
        raise ValueError("declared_allowed_evidence_ids_required")
    for citation in citations:
        if (
            citation["content"] != expected["contents"][citation["evidence_id"]]
            or citation["scope"] != "general_education"
        ):
            raise ValueError("exact_reviewed_source_required")
        scope = expected["scopes"][citation["evidence_id"]]
        if scope is None:
            if "reviewed_scope" in citation or "scope_hash" in citation:
                raise ValueError("legacy_projection_must_remain_unchanged")
        elif citation.get("reviewed_scope") != scope or not re.fullmatch(
            r"[0-9a-f]{64}", str(citation.get("scope_hash"))
        ):
            raise ValueError("declared_scope_projection_required")
    if stage == "tools":
        return token, role, mode, "finalize", final_answer_tool_delta(finalize_id)
    adopted = [foreign] if mode == "foreign" else [citation["citation_id"] for citation in citations]
    if not adopted or any(not re.fullmatch(r"[0-9a-f-]{36}", str(citation)) for citation in adopted):
        raise ValueError("actual_citation_required")
    return (
        token,
        role,
        mode,
        "answer",
        {
            "role": "assistant",
            "content": f"REVIEWED_SCOPE_BODY:{token}:{role}:{mode} 合成范围协议正文。"
            + " ".join(f"[证据:{citation}]" for citation in adopted),
        },
    )


class ReviewedScopeReplayHandler(BaseHTTPRequestHandler):
    """自己的fixture通过setup登记gold；观察仅返回阶段与ID。"""

    protocol_version = "HTTP/1.1"

    def do_GET(self):  # noqa: N802
        """释放与观察不公开实际模型输入。"""
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            self.write_json(200, {"isolated": True, "model": MODEL})
            return
        token = parse_qs(parsed.query).get("token", [""])[0]
        with LOCK:
            state = STATES.get(token)
            if state is None:
                self.write_json(404, {"error": "synthetic_fixture_required"})
                return
            if parsed.path == "/release":
                state["release"].set()
            observation = {
                "calls": list(state["calls"]),
                "answer_started": state["answer_started"],
                "rejected": list(state["rejected"]),
            }
        if parsed.path in {"/observations", "/release"}:
            self.write_json(200, observation)
        else:
            self.write_json(404, {"error": "not_found"})

    def do_POST(self):  # noqa: N802
        """shipping OpenAI协议回放，changed先flush正文再暂停终结。"""
        try:
            length = int(self.headers.get("content-length", "0"))
            if not 0 < length <= 300000:
                raise ValueError("invalid_length")
            body = json.loads(self.rfile.read(length))
            if self.path == "/setup":
                token = body["token"]
                if not re.fullmatch(r"[0-9a-f]{32}", str(token)) or not isinstance(body["roles"], dict):
                    raise ValueError("synthetic_setup_required")
                with LOCK:
                    state = STATES.setdefault(
                        token, {"release": Event(), "calls": [], "answer_started": False, "rejected": []}
                    )
                    state["roles"] = body["roles"]
                    state["foreign_citation"] = body.get("foreign_citation")
                self.write_json(200, {"configured": True})
                return
            if self.path != "/v1/chat/completions":
                self.write_json(404, {"error": "not_found"})
                return
            token, role, mode, phase, delta = replay_response(self.headers.get("authorization"), body)
        except (ValueError, KeyError, TypeError, IndexError, StopIteration) as exc:
            # 拒绝原因只保留固定错误标识，便于区分oracle失败与环境失败。
            reason = str(exc)
            with LOCK:
                for state in STATES.values():
                    state["rejected"].append(reason if re.fullmatch(r"[a-z_]+", reason) else "invalid_contract")
            self.write_json(422, {"error": "outside_synthetic_contract"})
            return
        with LOCK:
            state = STATES[token]
            state["calls"].append({"role": role, "mode": mode, "phase": phase})
        common = {
            "id": f"scope-{token}-{role}-{mode}-{phase}",
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": MODEL,
        }
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Connection", "close")
        self.end_headers()
        try:
            self.write_chunk({**common, "choices": [{"index": 0, "delta": delta, "finish_reason": None}]})
            if phase == "answer" and mode == "changed":
                with LOCK:
                    state["answer_started"] = True
                if not state["release"].wait(timeout=60):
                    self.write_chunk({"error": {"message": "synthetic_scope_gate_timeout"}})
                    return
            self.write_chunk(
                {
                    **common,
                    "choices": [
                        {"index": 0, "delta": {}, "finish_reason": "stop" if phase == "answer" else "tool_calls"}
                    ],
                    "usage": {"prompt_tokens": 8, "completion_tokens": 4, "total_tokens": 12},
                }
            )
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            self.close_connection = True

    def write_chunk(self, chunk):
        """逐帧flush，外部事实可在真实Worker仍执行时核对。"""
        self.wfile.write(f"data: {json.dumps(chunk)}\n\n".encode())
        self.wfile.flush()

    def write_json(self, status, payload):
        """固定控制协议不回显Token或模型正文。"""
        data = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format, *args):
        """不记录模型正文、账号或Authorization。"""


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", PORT), ReviewedScopeReplayHandler).serve_forever()

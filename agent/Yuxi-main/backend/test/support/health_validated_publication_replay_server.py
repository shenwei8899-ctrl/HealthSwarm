"""工具准备后显式结束，再在无工具调用中分两块生成正文。"""

import json
import re
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Event, Lock
from urllib.parse import parse_qs, urlparse

from test.support.health_consultation_replay_server import TOOLS
from test.support.health_indicator_replay_server import tool_delta, validate_records

MODEL = "deterministic-health-publication-20261013"
PORT = 8779
AUTHORIZATION = "Bearer synthetic-health-publication-key"
STATES = {}
LOCK = Lock()


def replay_response(authorization, body):
    """按实际工具回执推进，固定四角色及独立合成数值。"""
    if authorization != AUTHORIZATION or body.get("model") != MODEL or body.get("stream") is not True:
        raise ValueError("synthetic_model_required")
    messages = body.get("messages", [])
    user = next((message for message in reversed(messages) if message.get("role") == "user"), {})
    marker = re.fullmatch(
        r"PUBLICATION_E2E:([0-9a-f]{32}):(consultation|blood_glucose|blood_lipids|blood_pressure):(success|forged|source|scope|consent|withdrawn|cancel|failure)",
        str(user.get("content", "")),
    )
    if marker is None:
        raise ValueError("synthetic_input_required")
    token, role, mode = marker.groups()
    kind = "blood_glucose" if role == "consultation" else role
    record_tool = f"get_member_{kind}_records"
    names = [tool.get("function", {}).get("name") for tool in body.get("tools", [])]
    expected = (
        TOOLS
        if role == "consultation"
        else {record_tool, "query_reviewed_nutrition_knowledge", "query_family_nutrition_knowledge"}
    ) | {"finalize_health_answer"}
    if names and (len(names) != len(expected) or set(names) != expected or body.get("tool_choice") != "required"):
        raise ValueError("fixed_role_tools_required")
    skill = "family-nutritionist" if role == "consultation" else f"family-{role.replace('_', '-')}"
    if not any(
        message.get("role") == "system" and f"slug: {skill}" in str(message.get("content")) for message in messages
    ):
        raise ValueError("fixed_role_skill_required")
    records_id, knowledge_id, finalize_id = (
        f"publication-records-{token}",
        f"publication-knowledge-{token}",
        f"publication-finalize-{token}",
    )
    finalized = any(
        message.get("role") == "tool" and message.get("tool_call_id") == finalize_id for message in messages
    )
    if bool(names) == finalized:
        raise ValueError("explicit_tool_free_final_stage_required")
    outputs = {
        message.get("tool_call_id"): json.loads(message["content"])
        for message in messages
        if message.get("role") == "tool" and message.get("tool_call_id") in {records_id, knowledge_id}
    }
    if records_id not in outputs:
        delta = tool_delta(record_tool, {}, records_id)
        delta["content"] = (
            f"PRIVATE_TOOL_PREAMBLE:{token} 这段内容先于工具调用字段到达，仍然属于模型准备调用工具时的私有前言。"
            "它故意包含足够长的完整文本和段落边界，用来证明公开通道必须等待消息结束并确认没有工具调用，"
            "不能因为文本已经成段就把尚未完成的模型消息当作最终答复发布。\n\n"
        )
        return token, role, mode, "records", delta
    validate_records(outputs[records_id], kind, "read")
    if knowledge_id not in outputs:
        return (
            token,
            role,
            mode,
            "knowledge",
            tool_delta("query_reviewed_nutrition_knowledge", {"query": f"publication{token}"}, knowledge_id),
        )
    citations = outputs[knowledge_id]["citations"]
    if len(citations) != 1 or f"publication{token}" not in citations[0]["content"]:
        raise ValueError("actual_synthetic_evidence_required")
    if not finalized:
        return token, role, mode, "finalize", tool_delta("finalize_health_answer", {}, finalize_id)
    citation = "00000000-0000-0000-0000-000000000000" if mode == "forged" else citations[0]["citation_id"]
    return (
        token,
        role,
        mode,
        "answer",
        {
            "role": "assistant",
            "content": (
                f"PUBLICATION_BODY:{token} 合成协议正文只用于检验健康解释的发布边界，"
                "说明本轮已经读取授权记录并检索审核来源，"
                "所有展示内容都应在当前授权、记录版本和来源状态重新校验后公开，测试文本不会添加医学判断、"
                f"个体诊断或者未经程序确认的营养数值。[证据:{citation}]\n\n"
                "第二块正文用于核对首段已公开后模型才继续生成，逐段校验的答复预览与最终保存结果必须逐字一致，"
                f"断线恢复也只能重放仍然通过当前业务校验的同一答复。[证据:{citation}]"
            ),
            "reasoning_content": f"PRIVATE_REASONING:{token}",
        },
    )


class PublicationReplayHandler(BaseHTTPRequestHandler):
    """控制接口只公开阶段，模型正文只发送给所属真实Worker。"""

    protocol_version = "HTTP/1.1"

    def do_GET(self):  # noqa: N802
        """门闩控制与状态查询不回显模型输入。"""
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            self.write_json(200, {"isolated": True, "model": MODEL})
            return
        token = parse_qs(parsed.query).get("token", [""])[0]
        if not re.fullmatch(r"[0-9a-f]{32}", token):
            self.write_json(422, {"error": "synthetic_token_required"})
            return
        with LOCK:
            state = STATES.setdefault(token, {"release": Event(), "calls": [], "delta_sent": False})
            if parsed.path == "/release":
                state["release"].set()
            response = {
                "calls": list(state["calls"]),
                "delta_sent": state["delta_sent"],
                "stream_failed": state.get("stream_failed", False),
                "answer_chunks_sent": state.get("answer_chunks_sent", 0),
                "finish_sent": state.get("finish_sent", False),
            }
        if parsed.path in {"/release", "/observations"}:
            self.write_json(200, response)
        else:
            self.write_json(404, {"error": "not_found"})

    def do_POST(self):  # noqa: N802
        """工具字段晚于前言；最终首段flush后门闩阻塞下一段生成。"""
        if self.path != "/v1/chat/completions":
            self.write_json(404, {"error": "not_found"})
            return
        try:
            length = int(self.headers.get("content-length", "0"))
            if not 0 < length <= 200000:
                raise ValueError("invalid_length")
            token, role, mode, phase, delta = replay_response(
                self.headers.get("authorization"), json.loads(self.rfile.read(length))
            )
        except (ValueError, KeyError, TypeError, IndexError):
            self.write_json(422, {"error": "outside_synthetic_contract"})
            return
        with LOCK:
            state = STATES.setdefault(token, {"release": Event(), "calls": [], "delta_sent": False})
            state["calls"].append({"role": role, "mode": mode, "phase": phase})
        common = {
            "id": f"publication-{token}-{phase}",
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": MODEL,
        }
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Connection", "close")
        self.end_headers()
        try:
            if phase == "records":
                deltas = [{"role": "assistant", "content": delta["content"]}, {"tool_calls": delta["tool_calls"]}]
            elif phase == "answer":
                first, second = delta["content"].split("\n\n", 1)
                deltas = [
                    {**delta, "content": first + "\n\n"},
                    {"content": second},
                ]
            else:
                deltas = [delta]
            for index, chunk in enumerate(deltas):
                self.write_chunk({**common, "choices": [{"index": 0, "delta": chunk, "finish_reason": None}]})
                if phase == "answer":
                    with LOCK:
                        state["answer_chunks_sent"] = index + 1
                        state["delta_sent"] = True
                    if index == 0:
                        if not state["release"].wait(timeout=60):
                            self.write_chunk({"error": {"message": "synthetic_gate_timeout"}})
                            return
                        if mode == "failure":
                            self.write_chunk({"error": {"message": f"PRIVATE_MODEL_FAILURE:{token}"}})
                            with LOCK:
                                state["stream_failed"] = True
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
            if phase == "answer":
                with LOCK:
                    state["finish_sent"] = True
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            self.close_connection = True

    def write_chunk(self, chunk):
        """单个协议帧立即落到网络。"""
        self.wfile.write(f"data: {json.dumps(chunk)}\n\n".encode())
        self.wfile.flush()

    def write_json(self, status, payload):
        """控制响应只含阶段与门闩状态。"""
        data = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format, *args):
        """不记录模型正文和Authorization。"""


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", PORT), PublicationReplayHandler).serve_forever()

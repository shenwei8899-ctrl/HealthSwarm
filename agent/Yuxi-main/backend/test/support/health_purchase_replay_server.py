"""仅合成采购固定模型协议，不访问外部模型、商城或健康资料。"""

import json
import re
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Event
from uuid import uuid4

MODEL = "synthetic-purchase-2026-10-10"
TOOLS = {"get_purchase_requirements", "preview_purchase_requirements"}
CALLS = []
GATES = {}


def purchase_delta(body):
    """独立检查shipping协议，并给当前工具真实回执而非固定业务结果。"""
    if body.get("model") != MODEL or {item["function"]["name"] for item in body.get("tools", [])} != TOOLS:
        raise ValueError("fixed model and tools required")
    messages = body["messages"]
    index = max(index for index, item in enumerate(messages) if item["role"] == "user")
    text = messages[index]["content"]
    if not isinstance(text, str):
        text = " ".join(item.get("text", "") for item in text if isinstance(item, dict))
    match = re.fullmatch(
        r"PURCHASE_E2E:([a-z0-9]+):(normal|repeat|questions|invalid|forged|foreign|gate)(?::([a-f0-9-]+))?", text
    )
    if match is None:
        raise ValueError("synthetic marker required")
    token, mode, foreign = match.groups()
    recent = messages[index + 1 :]
    outputs = [json.loads(item["content"]) for item in recent if item["role"] == "tool"]
    for output in outputs:
        data = output.get("result", output)
        if {"profiles", "rules", "nutrition", "medical_history", "allergies"} & set(data):
            raise ValueError("private professional data outside purchase projection")
    CALLS.append({"token": token, "mode": mode, "tools": sorted(TOOLS), "tool_result_count": len(outputs)})
    if mode == "questions":
        return {
            "role": "assistant",
            "content": json.dumps({"questions": ["合成：请明确确认同状态可食库存。"]}, ensure_ascii=False),
        }, True
    if mode == "invalid":
        return {"role": "assistant", "content": '{"items":[{"net_required_grams":"999","sku":"fake"}]}'}, True
    receipts = [output for output in outputs if "preview_id" in output]
    if len(outputs) == 0:
        name = "get_purchase_requirements"
    elif not receipts or (mode == "repeat" and len(receipts) < 2):
        name = "preview_purchase_requirements"
    else:
        preview = foreign if mode == "foreign" else str(uuid4()) if mode == "forged" else receipts[-1]["preview_id"]
        if mode == "repeat" and receipts[0] != receipts[1]:
            raise ValueError("repeated tool must return immutable same Run receipt")
        if mode == "gate":
            GATES[token] = Event()
        return {"role": "assistant", "content": json.dumps({"preview_id": preview})}, True
    return {
        "role": "assistant",
        "tool_calls": [
            {
                "index": 0,
                "id": f"purchase-{token}-{len(outputs)}",
                "type": "function",
                "function": {"name": name, "arguments": "{}"},
            }
        ],
    }, False


class PurchaseReplayHandler(BaseHTTPRequestHandler):
    """独立本地HTTP协议服务，不保存请求或认证正文。"""

    def do_GET(self):
        """只返回进程就绪和有界调用摘要。"""
        self.write_json(200, {"status": "ready"} if self.path == "/health" else {"calls": CALLS, "gated": list(GATES)})

    def do_POST(self):
        """精确模型和工具请求才形成流式协议响应。"""
        if self.path.startswith("/release/"):
            token = self.path.removeprefix("/release/")
            if token not in GATES:
                self.write_json(404, {"released": False})
                return
            GATES[token].set()
            self.write_json(200, {"released": True})
            return
        try:
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            delta, final = purchase_delta(body)
        except (ValueError, KeyError, TypeError):
            self.write_json(400, {"error": {"message": "synthetic purchase protocol rejected"}})
            return
        if final:
            marker = next(item["content"] for item in reversed(body["messages"]) if item["role"] == "user")
            token = marker.split(":")[1]
            if token in GATES and not GATES[token].wait(timeout=40):
                self.write_json(408, {"error": {"message": "synthetic gate not released"}})
                return
        common = {
            "id": "chatcmpl-purchase-" + uuid4().hex,
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": MODEL,
        }
        chunks = [
            {**common, "choices": [{"index": 0, "delta": delta, "finish_reason": None}]},
            {
                **common,
                "choices": [{"index": 0, "delta": {}, "finish_reason": "stop" if final else "tool_calls"}],
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
        """错误不输出请求正文或凭据。"""
        data = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format, *args):
        """不记录认证或健康请求。"""


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8776), PurchaseReplayHandler).serve_forever()

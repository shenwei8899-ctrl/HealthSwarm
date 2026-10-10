"""只接受合成执行预算查询的慢模型，不代理外部服务。"""

import json
import re
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Event, Lock
from urllib.parse import parse_qs, urlparse

MODEL = "deterministic-health-budget-20261010"
STATES = {}
LOCK = Lock()


class BudgetReplayHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        """控制接口只返回准确合成token的计数。"""
        parsed = urlparse(self.path)
        token = parse_qs(parsed.query).get("token", [""])[0]
        if parsed.path != "/state" or not re.fullmatch(r"[0-9a-f]{32}", token):
            self.write_json(404, {})
            return
        with LOCK:
            state = STATES.get(token, {})
            data = {"requests": state.get("requests", 0), "responses": state.get("responses", 0)}
        self.write_json(200, data)

    def do_POST(self):
        """慢响应等待测试释放，便于在模型发送后改变授权或执行ownership。"""
        release = re.fullmatch(r"/release/([0-9a-f]{32})", self.path)
        if release:
            with LOCK:
                state = STATES.get(release[1])
                if state:
                    state["release"].set()
            self.write_json(200 if state else 404, {})
            return
        if self.path != "/v1/chat/completions":
            self.write_json(404, {})
            return
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))))
        except (ValueError, json.JSONDecodeError):
            self.write_json(400, {})
            return
        user = next((m for m in reversed(body.get("messages", [])) if m.get("role") == "user"), {})
        match = re.fullmatch(
            r"HEALTH_BUDGET_E2E:([0-9a-f]{32}):(slow|retry|cancel|revoke|lease|fast)", str(user.get("content"))
        )
        if (
            match is None
            or body.get("model") != MODEL
            or body.get("stream") is not True
            or self.headers.get("Authorization") != "Bearer synthetic-health-budget-key"
        ):
            self.write_json(400, {"error": "synthetic_health_budget_required"})
            return
        token, mode = match.groups()
        with LOCK:
            state = STATES.setdefault(token, {"requests": 0, "responses": 0, "release": Event()})
            state["requests"] += 1
        if mode != "fast":
            state["release"].wait(timeout=12)
        common = {
            "id": f"chatcmpl-budget-{token}",
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": MODEL,
        }
        chunks = [
            {
                **common,
                "choices": [
                    {"index": 0, "delta": {"role": "assistant", "content": "合成执行时限验收。"}, "finish_reason": None}
                ],
            },
            {
                **common,
                "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            },
        ]
        try:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Connection", "close")
            self.end_headers()
            for chunk in chunks:
                self.wfile.write(f"data: {json.dumps(chunk)}\n\n".encode())
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()
            with LOCK:
                state["responses"] += 1
        except (BrokenPipeError, ConnectionResetError):
            pass
        self.close_connection = True

    def write_json(self, status, body):
        """禁止把Authorization或业务请求放进控制响应。"""
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *_args):
        pass


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8778), BudgetReplayHandler).serve_forever()

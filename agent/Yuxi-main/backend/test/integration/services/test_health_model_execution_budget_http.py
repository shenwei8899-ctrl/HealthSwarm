"""实际SDK发送边界证明剩余超时和关闭隐式HTTP重试。"""

import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

import pytest

from yuxi.models import chat
from yuxi.models.execution_budget import (
    bind_model_execution_deadline,
    model_execution_budget_options,
    reset_model_execution_deadline,
)
from yuxi.models.providers.cache import ModelInfo

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.fixture
def sdk_wire_server():
    """只返回合成500或迟延响应，记录实际HTTP请求次数。"""
    requests = []
    delay = [0.0]

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_POST(self):
            self.rfile.read(int(self.headers.get("Content-Length", "0")))
            requests.append(self.path)
            time.sleep(delay[0])
            body = json.dumps({"error": {"code": 500, "message": "synthetic transient", "status": "INTERNAL"}}).encode()
            try:
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", requests, delay
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@pytest.mark.parametrize("provider_type", ["openai", "anthropic", "gemini"])
@pytest.mark.parametrize("mode", ["retryable_500", "slow_response"])
async def test_scoped_sdk_budget_is_effective_on_actual_wire_and_leaves_existing_models_unchanged(
    monkeypatch, sdk_wire_server, provider_type, mode
):
    """真实HTTP只发送一次，慢响应在SDK超时内终止；旧实例保持原配置。"""
    url, requests, delay = sdk_wire_server
    info = ModelInfo("synthetic-sdk", "synthetic-model", "chat", "Synthetic", "synthetic-key", url, provider_type)
    monkeypatch.setattr(chat.model_cache, "get_model_info", lambda _spec: info)
    monkeypatch.setattr(chat, "get_docker_safe_url", lambda value: value)
    options = {"base_url": url} if provider_type == "gemini" else {}
    existing = chat.load_chat_model(info.spec, **options)
    old_retry = existing.max_retries
    old_timeout = getattr(existing, "request_timeout", getattr(existing, "default_request_timeout", None))
    token = bind_model_execution_deadline(time.monotonic() + 1.5)
    try:
        model = chat.load_chat_model(info.spec, **options)
        assert model is not existing and model.max_retries == 0
        if mode == "slow_response":
            delay[0] = 3.0
        started = time.monotonic()
        with pytest.raises(Exception):
            await model.ainvoke("Synthetic execution budget test")
        elapsed = time.monotonic() - started
        assert len(requests) == 1, "SDK默认隐藏重试不能再次发送HTTP"
        assert elapsed < 2.1, "慢响应必须受新SDK剩余timeout限制"
    finally:
        reset_model_execution_deadline(token)
    assert model_execution_budget_options() == {}
    assert existing.max_retries == old_retry
    assert getattr(existing, "request_timeout", getattr(existing, "default_request_timeout", None)) == old_timeout

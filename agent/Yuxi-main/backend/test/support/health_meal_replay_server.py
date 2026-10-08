"""只接受固定纯色合成图片的视觉协议重放，不访问外部服务。"""

import base64
import hashlib
import io
import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Lock

from PIL import Image

MODEL = "qwen3-vl-flash-2026-01-22"
AUTH = "Bearer synthetic-health-meal-key"
CALLS = []
LOCK = Lock()


def validate_meal_request(authorization, body):
    """人工固定 oracle 拒绝真实图片、快照不支持的参数及工具扩展。"""
    if authorization != AUTH or not isinstance(body, dict) or body.get("model") != MODEL:
        raise ValueError("invalid_authorization_or_model")
    if body.get("stream", False) is not False:
        raise ValueError("non_streaming_required")
    if "response_format" in body:
        raise ValueError("snapshot_json_mode_unsupported")
    if body.get("tools") or body.get("functions"):
        raise ValueError("tools_not_allowed")
    messages = body.get("messages")
    if not isinstance(messages, list) or len(messages) != 2 or [m.get("role") for m in messages] != ["system", "user"]:
        raise ValueError("unexpected_messages")
    content = messages[1].get("content")
    if not isinstance(content, list) or not 2 <= len(content) <= 4:
        raise ValueError("unexpected_image_count")
    if content[0] != {"type": "text", "text": "识别这些照片中的同一餐。"}:
        raise ValueError("synthetic_query_required")
    digests = []
    for item in content[1:]:
        url = item.get("image_url", {}).get("url", "")
        prefix = "data:image/png;base64,"
        if item.get("type") != "image_url" or not url.startswith(prefix):
            raise ValueError("inline_png_required")
        raw = base64.b64decode(url[len(prefix) :], validate=True)
        if len(raw) > 50000:
            raise ValueError("synthetic_image_required")
        with Image.open(io.BytesIO(raw)) as image:
            if image.format != "PNG" or image.mode != "RGB" or image.size != (512, 512):
                raise ValueError("synthetic_image_required")
            if image.getextrema() != ((44, 44), (180, 180), (91, 91)):
                raise ValueError("synthetic_image_required")
        digests.append(hashlib.sha256(raw).hexdigest())
    return digests


class MealReplayHandler(BaseHTTPRequestHandler):
    """固定 JSON 只表示协议成功，不把图片内容当作菜品真值。"""

    protocol_version = "HTTP/1.1"

    def do_GET(self):  # noqa: N802
        """控制回读仅含调用图片摘要，不返回正文。"""
        if self.path not in {"/health", "/observations"}:
            self.write_json(404, {"error": "not_found"})
            return
        with LOCK:
            calls = [list(digests) for digests in CALLS]
        self.write_json(200, {"calls": calls, "isolated": True})

    def do_POST(self):  # noqa: N802
        """仅在完整请求通过合成约束后产生模型响应。"""
        if self.path != "/v1/chat/completions":
            self.write_json(404, {"error": "not_found"})
            return
        try:
            length = int(self.headers.get("content-length", "0"))
            if not 0 < length <= 200000:
                raise ValueError("invalid_length")
            digests = validate_meal_request(self.headers.get("authorization"), json.loads(self.rfile.read(length)))
        except (ValueError, KeyError, TypeError, AttributeError, OSError):
            self.write_json(422, {"error": "outside_synthetic_contract"})
            return
        with LOCK:
            CALLS.append(digests)
        self.write_json(
            200,
            {
                "id": "synthetic-meal-completion",
                "object": "chat.completion",
                "created": int(time.time()),
                "model": MODEL,
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {
                            "role": "assistant",
                            "content": "```json\n"
                            + json.dumps(
                                {
                                    "items": [
                                        {
                                            "name": "合成米饭",
                                            "candidates": ["合成米饭"],
                                            "cooking_method": "蒸煮",
                                            "visible_ingredients": ["合成米粒"],
                                            "locations": [{"image_index": 0, "bbox": [0.1, 0.2, 0.8, 0.9]}],
                                            "uncertainties": ["测试占位结果，不代表真实图片识别"],
                                        }
                                    ]
                                },
                                ensure_ascii=False,
                            )
                            + "\n```",
                        },
                    }
                ],
                "usage": {"prompt_tokens": 8, "completion_tokens": 4, "total_tokens": 12},
            },
        )

    def write_json(self, status, payload):
        """受控响应不包含请求正文或访问凭据。"""
        data = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format, *args):
        """重放也不记录图片 Base64、Authorization 或健康正文。"""


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8767), MealReplayHandler).serve_forever()

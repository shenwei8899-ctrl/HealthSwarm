"""仅本轮合成中文问句适配，沿用既有固定工具与171cm/v2独立oracle。"""

import io
import json
from http.server import ThreadingHTTPServer
from pathlib import Path

from test.support.health_consultation_replay_server import HealthReplayHandler

CONTROL = Path("/app/test/.tmp/miniapp-consultation-20261010")

BROWSER_QUESTION = "请根据本人已确认的基础档案，说明目前可以用于营养咨询的信息。"
BROWSER_ANSWER = "已读取本人确认基础档案：身高171cm，版本2；这是合成联调答复，营养安全字段尚未就绪。"


class MiniappConsultationReplayHandler(HealthReplayHandler):
    """只适配唯一固定中文问句，真实工具、来源hash及版本仍由原validator拒绝。"""

    def do_POST(self):  # noqa: N802
        """为本轮浏览器输入映射固定合成协议，其他已有协议保持原样。"""
        length = int(self.headers.get("content-length", "0"))
        if not 0 < length <= 200000:
            self.write_json(422, {"error": "outside_synthetic_contract"})
            return
        raw = self.rfile.read(length)
        try:
            body = json.loads(raw)
            user = next(message for message in reversed(body.get("messages", [])) if message.get("role") == "user")
        except (ValueError, TypeError, StopIteration):
            self.write_json(422, {"error": "outside_synthetic_contract"})
            return
        natural = user.get("content") == BROWSER_QUESTION
        if natural:
            if not (CONTROL / "metadata.json").exists():
                self.write_json(503, {"error": "fixture_not_ready"})
                return
            state = json.loads((CONTROL / "metadata.json").read_text())
            if state["cleaned"]:
                self.write_json(503, {"error": "fixture_not_ready"})
                return
            user["content"] = state["members"]["browser"]["profile_query"]
            raw = json.dumps(body).encode()
        original_input, original_output = self.rfile, self.wfile
        self.rfile = io.BytesIO(raw)
        self.headers.replace_header("Content-Length", str(len(raw)))
        if natural:
            self.wfile = SyntheticAnswerWriter(original_output)
        try:
            super().do_POST()
        finally:
            self.rfile, self.wfile = original_input, original_output


class SyntheticAnswerWriter:
    """只替换原validator已验证后生成的唯一固定答复，不适配未知答案。"""

    def __init__(self, output):
        """输出仍属于原HTTP连接。"""
        self.output = output

    def write(self, value):
        """保持SSE协议，只在准确固定delta上添加中文合成说明。"""
        if value.startswith(b"data: {"):
            chunk = json.loads(value[6:])
            delta = chunk["choices"][0]["delta"]
            if delta.get("content") == "合成本人身高171；营养安全字段尚未就绪":
                delta["content"] = BROWSER_ANSWER
                value = b"data: " + json.dumps(chunk).encode() + b"\n\n"
        return self.output.write(value)

    def __getattr__(self, name):
        """flush与连接关闭仍由原writer负责。"""
        return getattr(self.output, name)


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8766), MiniappConsultationReplayHandler).serve_forever()

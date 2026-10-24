"""小程序合成回放不能把错误档案或多模态输入伪装成成功。"""

import io
import json
from email.message import Message

import pytest

from test.support.health_consultation_replay_server import MODEL, TOOLS, validate_request
from test.support.health_miniapp_consultation_replay import (
    UPDATED_ANSWER,
    HealthReplayHandler,
    MiniappConsultationReplayHandler,
    SyntheticAnswerWriter,
)


@pytest.mark.parametrize("change", [{}, {"confirmed_version": 2}, {"profile": {"height_cm": 171}}])
def test_updated_profile_requires_current_tool_facts(change):
    """版本与身高来自工具事实，旧事实必须被独立 oracle 拒绝。"""
    token = "a" * 32
    profile = {
        "status": "ready",
        "confirmed_version": 3,
        "profile": {"height_cm": 172},
        "nutrition_safety_ready": False,
        "full_health_profile_available": False,
        "source_hash": "b" * 64,
        "source": {"source_member_id": "synthetic-source"},
        **change,
    }
    body = {
        "model": MODEL,
        "stream": True,
        "tools": [{"function": {"name": name}} for name in TOOLS],
        "messages": [
            {"role": "system", "content": "slug: family-nutritionist\n## 咨询流程\n## 日常反馈与记忆边界"},
            {"role": "user", "content": f"HEALTH_CONSULTATION_E2E:{token}:profile_updated"},
            {"role": "tool", "tool_call_id": f"health-read-{token}-profile_updated", "content": json.dumps(profile)},
        ],
    }
    if change:
        with pytest.raises(ValueError, match="confirmed_self_profile_required"):
            validate_request("Bearer synthetic-health-replay-key", body)
    else:
        assert validate_request("Bearer synthetic-health-replay-key", body)[3:] == (True, ["synthetic-source"])


@pytest.mark.parametrize("content", [[{"type": "text", "text": "合成图片问题"}], {"invalid": True}])
def test_non_text_input_reaches_original_contract_rejection(monkeypatch, content):
    """非字符串输入交给原协议拒绝，不因集合查找抛出 TypeError。"""
    raw = json.dumps({"messages": [{"role": "user", "content": content}]}).encode()
    handler = object.__new__(MiniappConsultationReplayHandler)
    handler.headers = Message()
    handler.headers["Content-Length"] = str(len(raw))
    handler.rfile, handler.wfile = io.BytesIO(raw), io.BytesIO()
    captured = []

    def original(self):
        """核对适配层没有改写非法输入。"""
        captured.append(json.load(self.rfile))

    monkeypatch.setattr(HealthReplayHandler, "do_POST", original)
    handler.do_POST()
    assert captured == [{"messages": [{"role": "user", "content": content}]}]


@pytest.mark.parametrize("content", ["合成本人身高172；营养安全字段尚未就绪", "意外答复"])
def test_answer_writer_only_translates_verified_fixed_delta(content):
    """未知答案保持原样，不能被适配层改造成通过答案。"""
    output = io.BytesIO()
    writer = SyntheticAnswerWriter(output, updated=True)
    writer.write(b"data: " + json.dumps({"choices": [{"delta": {"content": content}}]}).encode() + b"\n\n")
    actual = json.loads(output.getvalue()[6:])["choices"][0]["delta"]["content"]
    assert actual == (UPDATED_ANSWER if content.startswith("合成本人身高172") else content)

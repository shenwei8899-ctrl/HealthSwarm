"""视觉重放 oracle 只允许合成输入，并拒绝所有外发扩展。"""

import base64
import hashlib
import io
import json
from unittest.mock import AsyncMock
from types import SimpleNamespace
from contextlib import asynccontextmanager

import pytest
from PIL import Image

from test.support.health_meal_replay_server import AUTH, CALLS, MODEL, MealReplayHandler, validate_meal_request


@pytest.mark.asyncio
async def test_failed_meal_drain_still_revokes_synthetic_approval(monkeypatch):
    """任务未收敛时仍关闭审批并移除本轮供应商，且错误不被吞掉。"""
    from test.e2e import test_health_meal_e2e as e2e

    monkeypatch.setattr(e2e, "drain_meal_tasks", AsyncMock(side_effect=TimeoutError("synthetic unfinished task")))
    response = type(
        "SyntheticResponse", (), {"status_code": 200, "json": lambda self: {"meal": {"available": False}}}
    )()
    client = type(
        "SyntheticClient", (), {"put": AsyncMock(return_value=response), "delete": AsyncMock(return_value=response)}
    )()
    with pytest.raises(TimeoutError, match="synthetic unfinished task"):
        await e2e.finish_meal_fixture(client, [{"headers": {}}] * 3, "synthetic-provider")
    client.put.assert_awaited_once_with(f"{e2e.ROOT}/configuration", headers={}, json={})
    client.delete.assert_awaited_once_with("/api/system/model-providers/synthetic-provider", headers={})


@pytest.mark.asyncio
async def test_pending_health_task_blocks_cleanup_before_any_delete(monkeypatch):
    """待发布状态的 guard 独立验证，不与真实后台 publisher 争抢人工 pending 行。"""
    from test.integration.services import test_health_vision_http as support

    rows = SimpleNamespace(
        all=lambda: [SimpleNamespace(id="synthetic", status="pending", worker_id=None, lease_expires_at=None)]
    )
    # Run查询为空，随后Task查询仍返回待发布任务，保留独立Task门禁证据。
    session = SimpleNamespace(
        scalars=AsyncMock(side_effect=[SimpleNamespace(all=lambda: []), rows]), execute=AsyncMock()
    )

    @asynccontextmanager
    async def session_context():
        """模拟 PG 返回的唯一待发布任务，不写入实际队列。"""
        yield session

    monkeypatch.setattr(support.pg_manager, "get_async_session_context", session_context)
    with pytest.raises(RuntimeError, match="保留账号、PG 及对象诊断数据"):
        await support.cleanup_health_test_resources([{"uid": "synthetic"}], 1)
    session.execute.assert_not_awaited()
    assert session.scalars.await_count == 2


def synthetic_png(size=(512, 512), color=(44, 180, 91), mode="RGB", fmt="PNG"):
    """构造人工定义的纯色占位图，不读取任何用户图片。"""
    stream = io.BytesIO()
    Image.new(mode, size, color).save(stream, fmt)
    return stream.getvalue()


def meal_body(raw=None, count=2):
    """独立定义冻结快照请求，不要求供应商 JSON 模式。"""
    data = synthetic_png() if raw is None else raw
    return {
        "model": MODEL,
        "stream": False,
        "messages": [
            {"role": "system", "content": "你只做食物识别。"},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "识别这些照片中的同一餐。"},
                    *[
                        {
                            "type": "image_url",
                            "image_url": {"url": "data:image/png;base64," + base64.b64encode(data).decode()},
                        }
                        for _ in range(count)
                    ],
                ],
            },
        ],
    }


@pytest.mark.parametrize("count", [1, 2, 3])
def test_meal_oracle_accepts_only_known_synthetic_png_views(count):
    """允许的一到三个视角只返回实际图片摘要。"""
    raw = synthetic_png()
    assert validate_meal_request(AUTH, meal_body(raw, count)) == [hashlib.sha256(raw).hexdigest()] * count


@pytest.mark.parametrize(
    "case,reason",
    [
        ("auth", "invalid_authorization_or_model"),
        ("body", "invalid_authorization_or_model"),
        ("model", "invalid_authorization_or_model"),
        ("stream", "non_streaming_required"),
        ("format", "snapshot_json_mode_unsupported"),
        ("tools", "tools_not_allowed"),
        ("functions", "tools_not_allowed"),
        ("roles", "unexpected_messages"),
        ("missing", "unexpected_image_count"),
        ("extra", "unexpected_image_count"),
        ("query", "synthetic_query_required"),
        ("external", "inline_png_required"),
        ("image_type", "inline_png_required"),
    ],
)
def test_meal_oracle_rejects_wrong_or_expanded_protocol(case, reason):
    """每个协议 guard 都能因具体错误而变红。"""
    body, authorization = meal_body(), AUTH
    if case == "auth":
        authorization = "Bearer wrong-synthetic-key"
    elif case == "body":
        body = []
    elif case == "model":
        body["model"] = "unapproved-model"
    elif case == "stream":
        body["stream"] = True
    elif case == "format":
        body["response_format"] = {"type": "json_object"}
    elif case in {"tools", "functions"}:
        body[case] = [{"name": "read_file"}]
    elif case == "roles":
        body["messages"][0]["role"] = "tool"
    elif case == "missing":
        body = meal_body(count=0)
    elif case == "extra":
        body = meal_body(count=4)
    elif case == "query":
        body["messages"][1]["content"][0]["text"] = "不是合成请求"
    elif case == "external":
        body["messages"][1]["content"][1]["image_url"]["url"] = "https://example.com/private.png"
    else:
        body["messages"][1]["content"][1]["type"] = "text"
    with pytest.raises(ValueError, match=reason):
        validate_meal_request(authorization, body)


@pytest.mark.parametrize(
    "raw",
    [
        synthetic_png(color=(255, 255, 255)),
        synthetic_png(size=(256, 256)),
        synthetic_png(mode="L", color=91),
        synthetic_png(fmt="JPEG"),
        b"x" * 50001,
    ],
)
def test_meal_oracle_rejects_non_synthetic_image_bytes(raw):
    """改变颜色、尺寸、格式或超过限额都不能伪装合成图片。"""
    with pytest.raises(ValueError, match="synthetic_image_required"):
        validate_meal_request(AUTH, meal_body(raw))


@pytest.mark.parametrize(
    "path,raw,length,expected",
    [
        ("/unknown", b"{}", 2, 404),
        ("/v1/chat/completions", b"", 0, 422),
        ("/v1/chat/completions", b"{}", 200001, 422),
        ("/v1/chat/completions", b"not-json", 8, 422),
        (
            "/v1/chat/completions",
            json.dumps({"model": MODEL, "stream": False, "messages": [None, None]}).encode(),
            None,
            422,
        ),
    ],
)
def test_meal_wire_rejects_bad_input_without_recording_success(path, raw, length, expected):
    """HTTP wire 的非法正文只返回稳定错误，成功调用列表保持不变。"""
    handler = object.__new__(MealReplayHandler)
    handler.path = path
    handler.headers = {"content-length": str(len(raw) if length is None else length), "authorization": AUTH}
    handler.rfile = io.BytesIO(raw)
    responses = []
    handler.write_json = lambda status, payload: responses.append((status, payload))
    before = list(CALLS)
    handler.do_POST()
    assert responses == [(expected, {"error": "not_found" if expected == 404 else "outside_synthetic_contract"})]
    assert CALLS == before


def test_meal_control_get_rejects_unknown_route():
    """不存在的控制路径不暴露调用记录。"""
    handler = object.__new__(MealReplayHandler)
    handler.path = "/unknown"
    responses = []
    handler.write_json = lambda status, payload: responses.append((status, payload))
    handler.do_GET()
    assert responses == [(404, {"error": "not_found"})]


def test_meal_wire_returns_one_complete_json_fence():
    """重放直接证明包装协议，独立核对菜品而不调用生产 parser。"""
    handler = object.__new__(MealReplayHandler)
    handler.path = "/v1/chat/completions"
    raw = json.dumps(meal_body()).encode()
    handler.headers = {"content-length": str(len(raw)), "authorization": AUTH}
    handler.rfile = io.BytesIO(raw)
    responses = []
    handler.write_json = lambda status, payload: responses.append((status, payload))
    before = len(CALLS)
    try:
        handler.do_POST()
        status, body = responses[0]
        assert status == 200
        content = body["choices"][0]["message"]["content"]
        assert content.startswith("```json\n") and content.endswith("\n```")
        candidate = json.loads(content[len("```json\n") : -len("\n```")])["items"][0]
        assert candidate["name"] == "合成米饭"
        assert candidate["visible_ingredients"] == ["合成米粒"]
        assert candidate["locations"] == [{"image_index": 0, "bbox": [0.1, 0.2, 0.8, 0.9]}]
        assert "grams" not in candidate and "energy_kcal" not in candidate
    finally:
        del CALLS[before:]

"""实际 SDK 请求体与 JSON 校验的独立协议 oracle，不调用云服务。"""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from yuxi.models.providers.cache import ModelInfo, model_cache
from yuxi.services.health_vision_provider import call_json_model, recognize_meal
from yuxi.services.health_vision_types import HealthVisionError


def configured_model(monkeypatch, model_id):
    """只替代配置查询，保留实际聊天 SDK 和 HTTP 编码。"""
    info = ModelInfo(
        provider_id="synthetic",
        model_id=model_id,
        model_type="chat",
        display_name="synthetic",
        api_key="synthetic-not-a-real-key",
        base_url="https://synthetic.invalid/v1",
        provider_type="openai",
    )
    monkeypatch.setattr(model_cache, "get_model_info", lambda _spec: info)
    return info.spec


def completion(content, model_id):
    """人工定义供应商响应，不从实现生成期望请求或菜品。"""
    return {
        "id": "synthetic-wire",
        "object": "chat.completion",
        "created": 1,
        "model": model_id,
        "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": content}}],
        "usage": {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18},
    }


@pytest.mark.asyncio
async def test_frozen_meal_snapshot_omits_json_mode_but_validates_json(httpx_mock, monkeypatch):
    """冻结快照省略 response_format，仍解析候选且不产生模型份量。"""
    model_id = "qwen3-vl-flash-2026-01-22"
    spec = configured_model(monkeypatch, model_id)
    candidate = {
        "name": "合成米饭",
        "candidates": ["合成米饭"],
        "cooking_method": "蒸煮",
        "visible_ingredients": ["米粒"],
        "locations": [{"image_index": 0, "bbox": [0.1, 0.2, 0.8, 0.9]}],
        "uncertainties": [],
    }
    httpx_mock.add_response(
        method="POST",
        url="https://synthetic.invalid/v1/chat/completions",
        json=completion(json.dumps({"items": [candidate]}, ensure_ascii=False), model_id),
    )
    result = await recognize_meal(spec, [b"synthetic-image"], SimpleNamespace(raise_if_cancelled=AsyncMock()))
    requests = httpx_mock.get_requests()
    assert len(requests) == 1
    wire = json.loads(requests[0].content)
    assert "response_format" not in wire
    assert wire["model"] == model_id and wire["enable_thinking"] is False
    assert "tools" not in wire and "functions" not in wire
    assert [message["role"] for message in wire["messages"]] == ["system", "user"]
    assert "JSON" in wire["messages"][0]["content"]
    prompt = wire["messages"][0]["content"]
    for element in (
        '"visible_ingredients"',
        '"locations"',
        '"image_index"',
        '"bbox"',
        "从0编号",
        "归一化",
        "每张照片至多一个位置",
        "无法可靠定位时locations为空",
        "不能据此证明没有隐藏食材或过敏原",
    ):
        assert element in prompt, f"饮食观察提示词缺少契约：{element}"
    assert wire["messages"][1]["content"][1] == {
        "type": "image_url",
        "image_url": {"url": "data:image/png;base64,c3ludGhldGljLWltYWdl"},
    }
    assert {key: result["items"][0][key] for key in candidate} == candidate
    assert result["items"][0]["grams"] is None and result["items"][0]["portion_source"] == "unknown"
    assert result["items"][0]["share_ratio"] is None and "nutrients" not in result["items"][0]
    assert result["metadata"]["model"] == model_id
    assert result["metadata"]["usage"]["total_tokens"] == 18


@pytest.mark.asyncio
async def test_report_field_model_keeps_json_object_mode(httpx_mock, monkeypatch):
    """报告字段抽取不随饮食快照修复取消 JSON 对象请求。"""
    spec = configured_model(monkeypatch, "report-fixed")
    httpx_mock.add_response(
        method="POST",
        url="https://synthetic.invalid/v1/chat/completions",
        json=completion('{"fields":[]}', "report-fixed"),
    )
    result, metadata = await call_json_model(
        spec, "只输出 JSON", [{"type": "text", "text": "合成指标"}], SimpleNamespace(raise_if_cancelled=AsyncMock())
    )
    wire = json.loads(httpx_mock.get_request().content)
    assert wire.get("response_format") == {"type": "json_object"}
    assert wire["enable_thinking"] is False
    assert result == {"fields": []} and metadata["model"] == "report-fixed"


@pytest.mark.asyncio
@pytest.mark.parametrize("language", ["json", ""])
async def test_report_json_mode_rejects_fence_without_extra_call(httpx_mock, monkeypatch, language):
    """JSON 模式仍只接受裸对象，不继承视觉包装兼容。"""
    spec = configured_model(monkeypatch, "report-fixed")
    httpx_mock.add_response(
        method="POST",
        url="https://synthetic.invalid/v1/chat/completions",
        json=completion(f'```{language}\n{{"fields":[]}}\n```', "report-fixed"),
    )
    with pytest.raises(HealthVisionError) as rejected:
        await call_json_model(
            spec, "只输出 JSON", [{"type": "text", "text": "合成指标"}], SimpleNamespace(raise_if_cancelled=AsyncMock())
        )
    assert rejected.value.code == "model_schema_invalid"
    requests = httpx_mock.get_requests()
    assert len(requests) == 1
    assert json.loads(requests[0].content)["response_format"] == {"type": "json_object"}


@pytest.mark.asyncio
@pytest.mark.parametrize("language", ["json", "JSON", ""])
async def test_meal_complete_json_fence_preserves_candidate_without_extra_call(httpx_mock, monkeypatch, language):
    """视觉 SDK 完整代码块可验证，候选和未知份量保持原值。"""
    model_id = "qwen3-vl-flash-2026-01-22"
    spec = configured_model(monkeypatch, model_id)
    httpx_mock.add_response(
        method="POST",
        url="https://synthetic.invalid/v1/chat/completions",
        json=completion(f'  ```{language}\n{{"items":[{{"name":"合成米饭"}}]}}\n```  ', model_id),
    )
    result = await recognize_meal(spec, [b"synthetic-image"], SimpleNamespace(raise_if_cancelled=AsyncMock()))
    assert result["items"][0]["name"] == "合成米饭"
    assert result["items"][0]["grams"] is None
    assert result["items"][0]["share_ratio"] is None
    assert len(httpx_mock.get_requests()) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "content",
    [
        '说明\n```json\n{"items":[]}\n```',
        '```json\n{"items":[]}\n```\n说明',
        '```json\n{"items":[]}\n```\n```json\n{"items":[]}\n```',
        '```python\n{"items":[]}\n```',
        '```json\n{"items":[]} ',
        '```json\n{"items":[\n```',
        '```json\n{"items":[{"name":"合成米饭","grams":100}]}\n```',
        '```json\n{"items":[{"name":"合成米饭","energy_kcal":130}]}\n```',
        "```json\n[]\n```",
    ],
)
async def test_meal_fence_does_not_repair_or_guess_invalid_output(httpx_mock, monkeypatch, content):
    """拒绝混合正文、多块、截断和模型补造营养，且只调用一次。"""
    model_id = "qwen3-vl-flash-2026-01-22"
    spec = configured_model(monkeypatch, model_id)
    httpx_mock.add_response(
        method="POST", url="https://synthetic.invalid/v1/chat/completions", json=completion(content, model_id)
    )
    with pytest.raises(HealthVisionError) as rejected:
        await recognize_meal(spec, [b"synthetic-image"], SimpleNamespace(raise_if_cancelled=AsyncMock()))
    assert rejected.value.code == "model_schema_invalid"
    assert len(httpx_mock.get_requests()) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "content",
    [
        "普通文字不是 JSON",
        "[]",
        '{"items":null}',
        '{"items":[{"name":"米饭","grams":100}]}',
        '{"items":[{"name":"米饭","energy_kcal":130}]}',
    ],
)
async def test_meal_non_json_or_extra_nutrition_is_rejected_without_second_call(httpx_mock, monkeypatch, content):
    """没有供应商 JSON 模式也不放宽领域 Schema 或自动追加付费纠正。"""
    model_id = "qwen3-vl-flash-2026-01-22"
    spec = configured_model(monkeypatch, model_id)
    httpx_mock.add_response(
        method="POST", url="https://synthetic.invalid/v1/chat/completions", json=completion(content, model_id)
    )
    with pytest.raises(HealthVisionError) as rejected:
        await recognize_meal(spec, [b"synthetic-image"], SimpleNamespace(raise_if_cancelled=AsyncMock()))
    assert rejected.value.code == "model_schema_invalid"
    assert len(httpx_mock.get_requests()) == 1

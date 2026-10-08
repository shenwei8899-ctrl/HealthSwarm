"""供应商 HTTP 契约回放，不冒充真实模型效果验收。"""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from yuxi.services.health_vision_provider import parse_report_page, redact_report_blocks
from yuxi.services.health_vision_service import processor_identity
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.models.providers.cache import ModelInfo


@pytest.mark.asyncio
async def test_paddle_upload_poll_jsonl_and_real_evidence_contract(httpx_mock):
    url = "https://paddleocr.aistudio-app.com/api/v2/ocr/jobs"
    result_url = "https://synthetic.bcebos.com/result.jsonl"
    httpx_mock.add_response(method="POST", url=url, json={"code": 0, "data": {"jobId": "synthetic-job"}})
    httpx_mock.add_response(
        method="GET", url=f"{url}/synthetic-job", json={"data": {"state": "done", "resultUrl": {"jsonUrl": result_url}}}
    )
    row = {
        "result": {
            "layoutParsingResults": [
                {
                    "prunedResult": {
                        "parsing_res_list": [
                            {"block_content": "血糖 6.8 mmol/L 3.9-6.1", "block_bbox": [100, 200, 300, 400]}
                        ]
                    }
                }
            ]
        }
    }
    httpx_mock.add_response(method="GET", url=result_url, content=json.dumps(row).encode())
    context = SimpleNamespace(raise_if_cancelled=AsyncMock())
    checkpoint = AsyncMock()
    result = await parse_report_page(
        b"synthetic-page-bytes",
        {"page_index": 2},
        {"api_token": "synthetic-token"},
        context,
        checkpoint,
        authorize=AsyncMock(),
    )
    assert result["blocks"][0]["block_id"] == "p2_b0"
    assert result["blocks"][0]["raw_text"] == "血糖 6.8 mmol/L 3.9-6.1"
    assert result["blocks"][0]["bbox"] is None
    checkpoint.assert_awaited_once_with("synthetic-job")
    request = httpx_mock.get_requests()[0]
    assert request.headers["Authorization"] == "bearer synthetic-token"
    assert b"synthetic-page-bytes" in request.content and b"PaddleOCR-VL-1.6" in request.content


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "result_url",
    [
        "http://synthetic.bcebos.com/result",
        "https://untrusted.invalid/result",
        "https://user:password@synthetic.bcebos.com/result",
    ],
)
async def test_paddle_rejects_untrusted_or_plaintext_result_address(httpx_mock, result_url):
    url = "https://paddleocr.aistudio-app.com/api/v2/ocr/jobs"
    httpx_mock.add_response(method="POST", url=url, json={"data": {"jobId": "synthetic-job"}})
    httpx_mock.add_response(
        method="GET", url=f"{url}/synthetic-job", json={"data": {"state": "done", "resultUrl": {"jsonUrl": result_url}}}
    )
    with pytest.raises(HealthVisionError, match="parser_contract_invalid"):
        await parse_report_page(
            b"test",
            {"page_index": 0},
            {"api_token": "synthetic"},
            SimpleNamespace(raise_if_cancelled=AsyncMock()),
            AsyncMock(),
            authorize=AsyncMock(),
        )
    assert len(httpx_mock.get_requests()) == 2


@pytest.mark.parametrize(
    "text",
    [
        "受检者：李四",
        "受检人：李四",
        "Name: Jane Doe",
        "邮箱: synthetic@example.com",
        "病案号 1234",
        "Patient ID: 1234",
    ],
)
def test_nickname_does_not_allow_patient_identifiers_outbound(text):
    assert redact_report_blocks([{"block_id": "b", "raw_text": text}], "父亲") == []


def test_processor_binding_changes_with_endpoint_type_or_overrides():
    kwargs = dict(
        provider_id="synthetic",
        model_id="fixed-2026-01-22",
        model_type="chat",
        display_name="test",
        api_key="synthetic",
        base_url="https://one.invalid",
        provider_type="openai",
    )
    initial = processor_identity("meal", ModelInfo(**kwargs))
    for changed in (
        {"base_url": "https://two.invalid"},
        {"provider_type": "openrouter"},
        {"request_body_overrides": {"thinking": True}},
    ):
        assert processor_identity("meal", ModelInfo(**{**kwargs, **changed})) != initial
    assert processor_identity("report", ModelInfo(**kwargs), {"api_url": "https://one.invalid"}) != processor_identity(
        "report", ModelInfo(**kwargs), {"api_url": "https://two.invalid"}
    )
    assert "https://" not in initial and "synthetic-token" not in initial


@pytest.mark.parametrize(
    "label,identity",
    [("Name", "Synthetic Alice Doe"), ("姓名", "合成人名"), ("姓名", "合成杨铁柱 12345"), ("姓名", "合成钠姓名 12345")],
)
def test_split_identity_values_are_not_sent_to_model(label, identity):
    """标签、身份值及指标行分别成块时，只外发真正指标行。"""
    blocks = [{"block_id": str(i), "raw_text": text} for i, text in enumerate([label, identity, "Glucose 6.8 mmol/L"])]
    assert redact_report_blocks(blocks, "Father") == [blocks[2]]

"""页归属恢复与供应商协议的独立负向测试，无真实外呼。"""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from yuxi.services.health_vision_provider import parse_report_page
from yuxi.services.health_vision_tasks import report_page_checkpoint
from yuxi.services.health_vision_types import HealthVisionError

URL = "https://paddleocr.aistudio-app.com/api/v2/ocr/jobs"
PAGE = {"page_index": 1, "upload_id": "synthetic-upload", "upload_page_index": 0}
ENTRY = {**PAGE, "provider_job_id": "synthetic-existing", "state": "submitted"}


@pytest.mark.parametrize(
    "changed",
    [
        {"page_index": 0},
        {"upload_id": "another-upload"},
        {"upload_page_index": 1},
        {"state": "failed"},
        {"state": None},
    ],
)
def test_checkpoint_rejects_changed_page_or_failed_state(changed):
    """每一项页归属都必须相符，明确失败的页不能回退到旧 ID。"""
    assert report_page_checkpoint([ENTRY], PAGE) == "synthetic-existing"
    assert report_page_checkpoint([{**ENTRY, **changed}], PAGE) is None
    assert report_page_checkpoint([ENTRY, {**ENTRY, "state": "failed"}], PAGE) is None
    assert report_page_checkpoint([{"page_index": 1, "provider_job_id": "legacy"}], PAGE) is None


@pytest.mark.asyncio
async def test_resume_polls_existing_job_without_post_and_keeps_evidence(httpx_mock):
    """仅 GET 的协议回放独立证明恢复不会上传或再登记已持久化请求。"""
    result_url = "https://synthetic.bcebos.com/resumed.jsonl"
    httpx_mock.add_response(
        method="GET",
        url=f"{URL}/synthetic-existing",
        json={"data": {"state": "done", "resultUrl": {"jsonUrl": result_url}}},
    )
    row = {"result": {"layoutParsingResults": [{"markdown": {"text": "血糖 6.8 mmol/L"}}]}}
    httpx_mock.add_response(method="GET", url=result_url, content=json.dumps(row).encode())
    checkpoint = AsyncMock()
    result = await parse_report_page(
        b"must-not-be-uploaded",
        PAGE,
        {"api_token": "synthetic"},
        SimpleNamespace(raise_if_cancelled=AsyncMock()),
        checkpoint,
        authorize=AsyncMock(),
        provider_job_id="synthetic-existing",
    )
    assert result["provider_job_id"] == "synthetic-existing"
    assert result["blocks"][0]["raw_text"] == "血糖 6.8 mmol/L"
    assert result["blocks"][0]["page_index"] == 1
    assert [request.method for request in httpx_mock.get_requests()] == ["GET", "GET"]
    checkpoint.assert_not_awaited()


@pytest.mark.asyncio
async def test_initial_authorization_denial_prevents_upload(httpx_mock):
    """即使尚无云任务，授权失败也不能 POST 图片。"""
    with pytest.raises(HealthVisionError, match="not_found"):
        await parse_report_page(
            b"must-not-upload",
            PAGE,
            {"api_token": "synthetic"},
            SimpleNamespace(raise_if_cancelled=AsyncMock()),
            AsyncMock(),
            authorize=AsyncMock(side_effect=HealthVisionError("not_found", "无权访问", 404)),
        )
    assert httpx_mock.get_requests() == []


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [404, 410])
async def test_expired_checkpoint_never_creates_second_paid_request(httpx_mock, status):
    """不存在的云任务明确失败，没有 POST fallback。"""
    httpx_mock.add_response(method="GET", url=f"{URL}/synthetic-existing", status_code=status)
    with pytest.raises(HealthVisionError, match="provider_job_unavailable"):
        await parse_report_page(
            b"test",
            PAGE,
            {"api_token": "synthetic"},
            SimpleNamespace(raise_if_cancelled=AsyncMock()),
            AsyncMock(),
            authorize=AsyncMock(),
            provider_job_id="synthetic-existing",
        )
    assert [request.method for request in httpx_mock.get_requests()] == ["GET"]


@pytest.mark.asyncio
async def test_provider_failure_is_checkpointed_before_rejecting(httpx_mock):
    """明确供应商失败留持久标记，后续显式重试才能重新提交该页。"""
    httpx_mock.add_response(method="GET", url=f"{URL}/synthetic-existing", json={"data": {"state": "failed"}})
    checkpoint = AsyncMock()
    with pytest.raises(HealthVisionError, match="provider_failed"):
        await parse_report_page(
            b"test",
            PAGE,
            {"api_token": "synthetic"},
            SimpleNamespace(raise_if_cancelled=AsyncMock()),
            checkpoint,
            authorize=AsyncMock(),
            provider_job_id="synthetic-existing",
        )
    checkpoint.assert_awaited_once_with("synthetic-existing", "failed")
    assert [request.method for request in httpx_mock.get_requests()] == ["GET"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "identifier", ["../secret", "https://evil.invalid", "job?token=1", "job/name", "", "x" * 201, 123]
)
@pytest.mark.parametrize("resumed", [True, False])
async def test_untrusted_job_identifier_cannot_change_poll_path(httpx_mock, identifier, resumed):
    """新供应商响应和持久化恢复都校验 wire 标识。"""
    if not resumed:
        httpx_mock.add_response(method="POST", url=URL, json={"data": {"jobId": identifier}})
    with pytest.raises(HealthVisionError, match="parser_contract_invalid"):
        await parse_report_page(
            b"test",
            PAGE,
            {"api_token": "synthetic"},
            SimpleNamespace(raise_if_cancelled=AsyncMock()),
            AsyncMock(),
            authorize=AsyncMock(),
            provider_job_id=identifier if resumed else None,
        )
    assert [request.method for request in httpx_mock.get_requests()] == ([] if resumed else ["POST"])

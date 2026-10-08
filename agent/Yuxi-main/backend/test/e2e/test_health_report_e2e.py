"""两页合成 PDF 经真实 HTTPS、独立 worker、复核和确认进入私有指标。"""

import asyncio
import hashlib
import io
import json
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import certifi
import pytest
import pytest_asyncio
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject
from sqlalchemy import select, text

from test.e2e.test_health_consultation_e2e import wait_until
from test.e2e.test_health_meal_e2e import drain_meal_tasks
from test.integration.services.test_health_vision_http import ROOT, confirmation, create_member, health_http  # noqa: F401
from yuxi.services.health_vision_service import PRIVATE_BUCKET
from yuxi.services.health_vision_provider import parse_report_page
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.storage.minio import get_minio_client
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_business import ConfigOption, TaskRecord
from yuxi.storage.postgres.models_health import HealthObservation, PrivateUpload, VisionDraft, VisionJob

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.e2e,
    pytest.mark.slow,
    pytest.mark.skipif(
        os.getenv("HEALTH_CONSULTATION_E2E_ISOLATED") != "true"
        or os.getenv("SSL_CERT_FILE") != "/app/health-report-tls/cert.pem",
        reason="报告合成 E2E 只在健康隔离槽位并加载专用 TLS 覆盖层运行",
    ),
]
MODEL = "qwen3-vl-flash-2026-01-22"
AUTH = {"Authorization": "Bearer synthetic-health-report-key"}


@pytest_asyncio.fixture
async def isolated_report(health_http):  # noqa: F811
    """只在专用数据库、空审批和无原 OCR 配置时审批合成端点。"""
    async with pg_manager.get_async_session_context() as session:
        assert await session.scalar(text("SELECT current_database()")) == "health_consultation_e2e"
        original = await session.scalar(select(ConfigOption).where(ConfigOption.key == "paddleocr_api_opts"))
        assert not any((original.value or {}).values()), "不能覆盖已有 OCR 配置"
    client, users = health_http
    assert str(client.base_url).rstrip("/") == "http://localhost:5050"
    admin = users[2]["headers"]
    current = await client.get(f"{ROOT}/configuration", headers=admin)
    assert current.status_code == 200 and not current.json()["policy_version"]
    provider = f"health-report-replay-{uuid4().hex[:12]}"
    created = await client.post(
        "/api/system/model-providers",
        headers=admin,
        json={
            "provider_id": provider,
            "display_name": "Synthetic report only",
            "provider_type": "openai",
            "base_url": "https://api:8768/v1",
            "api_key": "synthetic-health-report-key",
            "is_enabled": True,
            "capabilities": ["chat"],
            "enabled_models": [{"id": MODEL, "display_name": MODEL, "type": "chat", "source": "manual"}],
        },
    )
    assert created.status_code == 200, created.text
    try:
        ocr = await client.put(
            "/api/system/config/options/paddleocr_api_opts",
            headers=admin,
            json={"value": {"api_url": "https://api:8768/api/v2/ocr/jobs", "api_token": "synthetic-health-ocr-key"}},
        )
        assert ocr.status_code == 200, ocr.text
        configured = await client.put(
            f"{ROOT}/configuration",
            headers=admin,
            json={
                "report_model": f"{provider}:{MODEL}",
                "policy_version": "synthetic-report-only-v1",
                "cloud_processing_reviewed": True,
            },
        )
        assert configured.status_code == 200 and configured.json()["report"]["available"], configured.text
        yield client, users, configured.json()
    finally:
        try:
            await drain_meal_tasks(client, users)
        finally:
            reset = await client.put(f"{ROOT}/configuration", headers=admin, json={})
            assert reset.status_code == 200 and not reset.json()["report"]["available"]
            assert (
                await client.put(
                    "/api/system/config/options/paddleocr_api_opts",
                    headers=admin,
                    json={"value": {"api_url": "", "api_token": ""}},
                )
            ).status_code == 200
            assert (await client.delete(f"/api/system/model-providers/{provider}", headers=admin)).status_code == 200
            async with pg_manager.get_async_session_context() as session:
                restored = await session.scalar(select(ConfigOption).where(ConfigOption.key == "paddleocr_api_opts"))
                assert not any(restored.value.values()), "OCR 合成端点及占位凭据必须清空"


async def test_pdf_report_partial_page_reprocess_evidence_and_once_confirmation(isolated_report, monkeypatch):
    """失败页重新处理保持原页序和成功页人工修订，确认前无正式指标。"""
    client, users, config = isolated_report
    headers = users[0]["headers"]
    member = await create_member(client, headers)
    writer = PdfWriter()
    for color in ("0 0 1", "1 0 0"):
        page = writer.add_blank_page(width=600, height=800)
        stream = DecodedStreamObject()
        stream.set_data(f"{color} rg 0 0 600 800 re f".encode())
        page.replace_contents(stream)
    output = io.BytesIO()
    writer.write(output)
    pdf = output.getvalue()
    uploaded = await client.post(
        f"{ROOT}/uploads",
        headers=headers,
        data={"member_id": member, "purpose": "report"},
        files={"file": ("synthetic-report.pdf", pdf, "application/pdf")},
    )
    assert uploaded.status_code == 201, uploaded.text
    upload_id = uploaded.json()["upload_id"]
    digests, previews = [], []
    for index in (0, 1):
        preview = await client.get(f"{ROOT}/uploads/{upload_id}/preview?page_index={index}", headers=headers)
        assert preview.status_code == 200 and preview.headers["cache-control"] == "private, no-store"
        digests.append(hashlib.sha256(preview.content).hexdigest())
        previews.append(preview.content)
    async with httpx.AsyncClient(base_url="https://localhost:8768", headers=AUTH) as replay:
        control = await replay.post("/control", json={"token": uuid4().hex})
        assert control.status_code == 200
        checkpoint = AsyncMock()
        with monkeypatch.context() as untrusted:
            untrusted.setenv("SSL_CERT_FILE", certifi.where())
            with pytest.raises(HealthVisionError) as rejected:
                await parse_report_page(
                    previews[0],
                    {"page_index": 0},
                    {"api_url": "https://api:8768/api/v2/ocr/jobs", "api_token": "synthetic-health-ocr-key"},
                    SimpleNamespace(raise_if_cancelled=AsyncMock()),
                    checkpoint,
                    authorize=AsyncMock(),
                )
            assert rejected.value.code == "provider_unavailable"
        checkpoint.assert_not_awaited()
        assert (await replay.get("/observations")).json()["events"] == []
        request_id = str(uuid4())
        request = {"member_id": member, "upload_ids": [upload_id], "client_request_id": request_id}
        request_headers = {**headers, "Idempotency-Key": request_id}
        denied = await client.post(f"{ROOT}/report-tasks", headers=request_headers, json=request)
        assert denied.status_code == 403 and denied.json()["code"] == "consent_required"
        assert (await replay.get("/observations")).json()["events"] == []
        async with pg_manager.get_async_session_context() as session:
            assert await session.scalar(select(VisionJob).where(VisionJob.member_id == member)) is None
        consent = await client.post(
            f"{ROOT}/members/{member}/processing-consents",
            headers=headers,
            json={
                "purpose": "report",
                "accepted": True,
                "processor": config["report"]["processor"],
                "policy_version": config["policy_version"],
            },
        )
        assert consent.status_code == 200
        created = await client.post(f"{ROOT}/report-tasks", headers=request_headers, json=request)
        assert created.status_code == 202, created.text
        task_id = created.json()["task_id"]

        async def finished_task(identifier):
            """正式 HTTP 状态终态是唯一结束条件，执行器不在测试进程调用。"""

            async def state():
                """回读实际 Task 投影。"""
                response = await client.get(f"{ROOT}/vision-tasks/{identifier}", headers=headers)
                assert response.status_code == 200
                return response.json()

            return await wait_until(
                state, lambda value: value["execution_status"] in {"success", "failed", "cancelled"}
            )

        done = await finished_task(task_id)
        assert done["execution_status"] == "success" and done["phase"] == "partial_ready", done
        draft_id = done["result_id"]
        path = f"{ROOT}/report-extractions/{draft_id}"
        initial = (await client.get(path, headers=headers)).json()
        report = initial["payload"]
        assert initial["review_status"] == "pending_confirmation" and initial["version"] == 1
        assert [page["status"] for page in report["pages"]] == ["ready", "failed"]
        assert report["pages"][1]["error_code"] == "provider_failed"
        assert len(report["fields"]) == 1
        metric = report["fields"][0]
        assert metric["name"] == "葡萄糖" and metric["value_numeric"] == "6.8"
        assert metric["evidence"] == {
            "page_index": 0,
            "block_id": "p0_b1",
            "bbox": [0.1, 0.2, 0.8, 0.3],
            "raw_text": "葡萄糖 6.8 mmol/L 3.9-6.1",
        }
        assert (await client.get(f"{ROOT}/members/{member}/observations", headers=headers)).json() == []
        data, key = confirmation(1)
        incomplete = await client.post(f"{path}/confirm", headers={**headers, **key}, json=data)
        assert incomplete.status_code == 422 and incomplete.json()["code"] == "report_pages_incomplete", incomplete.text
        # 日期是用户输入；成功页的人工修订须经过重识别仍保留。
        metric["observed_at"] = "2026-10-01"
        modified = await client.patch(
            path,
            headers={**headers, "If-Match": '"1"'},
            json={"version": 1, "reason": "合成用户补充检查日期", "report": report},
        )
        assert modified.status_code == 200 and modified.json()["version"] == 2, modified.text
        retry_key = str(uuid4())
        retried = await client.post(
            f"{ROOT}/report-page-tasks",
            headers={**headers, "If-Match": '"2"', "Idempotency-Key": retry_key},
            json={"draft_id": draft_id, "version": 2, "page_indices": [1], "client_request_id": retry_key},
        )
        assert retried.status_code == 202, retried.text
        retry_task = retried.json()["task_id"]
        recovered = await finished_task(retry_task)
        assert recovered["execution_status"] == "success" and recovered["result_id"] == draft_id, recovered
        current = (await client.get(path, headers=headers)).json()
        assert current["version"] == 3 and [page["status"] for page in current["payload"]["pages"]] == [
            "ready",
            "ready",
        ]
        fields = current["payload"]["fields"]
        assert [field["name"] for field in fields] == ["葡萄糖", "甘油三酯"]
        assert fields[0] == metric
        assert fields[1]["value_numeric"] == "1.7" and fields[1]["observed_at"] is None
        assert (
            fields[1]["evidence"]["page_index"] == 1
            and fields[1]["evidence"]["raw_text"] == "甘油三酯\t1.7\tmmol/L\t0.0-1.7"
            and fields[1]["evidence"]["block_id"] == "p1_b1_r3"
        )
        assert (await client.get(f"{ROOT}/members/{member}/observations", headers=headers)).json() == []
        data, key = confirmation(2)
        assert (await client.post(f"{path}/confirm", headers={**headers, **key}, json=data)).status_code == 409
        data, key = confirmation(3)
        confirmed = await asyncio.gather(
            *[client.post(f"{path}/confirm", headers={**headers, **key}, json=data) for _ in range(3)]
        )
        assert all(response.status_code == 200 and response.json() == confirmed[0].json() for response in confirmed)
        ids = confirmed[0].json()["target_ids"]
        assert len(ids) == 2 and len(set(ids)) == 2
        events = (await replay.get("/observations")).json()["events"]
        assert [(event["kind"], event["page_index"]) for event in events] == [
            ("submit", 0),
            ("poll", 0),
            ("download", 0),
            ("fields", 0),
            ("submit", 1),
            ("poll", 1),
            ("submit", 1),
            ("poll", 1),
            ("download", 1),
            ("fields", 1),
        ]
        submits = [event for event in events if event["kind"] == "submit"]
        assert [event["sha256"] for event in submits] == [digests[0], digests[1], digests[1]]
    async with pg_manager.get_async_session_context() as session:
        observations = list(
            (await session.scalars(select(HealthObservation).where(HealthObservation.member_id == member))).all()
        )
        assert {row.id for row in observations} == set(ids)
        assert {row.field_id: row.snapshot for row in observations} == {field["field_id"]: field for field in fields}
        upload = await session.get(PrivateUpload, upload_id)
        assert upload.sha256 == hashlib.sha256(pdf).hexdigest() and len(upload.pages) == 2
        initial_job = await session.scalar(select(VisionJob).where(VisionJob.task_id == task_id))
        retry_job = await session.scalar(select(VisionJob).where(VisionJob.task_id == retry_task))
        assert retry_job.parent_task_id == task_id and retry_job.result_id == draft_id
        assert [(entry["page_index"], entry["state"]) for entry in initial_job.input_snapshot["provider_jobs"]] == [
            (0, "submitted"),
            (1, "failed"),
        ]
        checkpoints = {entry["page_index"]: entry for entry in retry_job.input_snapshot["provider_jobs"]}
        assert checkpoints[0] == initial_job.input_snapshot["provider_jobs"][0]
        assert checkpoints[1]["state"] == "submitted"
        assert checkpoints[1]["provider_job_id"] != initial_job.input_snapshot["provider_jobs"][1]["provider_job_id"]
        for identifier in (task_id, retry_task):
            task = await session.get(TaskRecord, identifier)
            assert (
                task.status == "success"
                and task.worker_id is None
                and task.lease_expires_at is None
                and task.attempt_count == 1
            )
        draft = await session.get(VisionDraft, draft_id)
        assert (
            draft.review_status == "confirmed"
            and draft.parser_version == "PaddleOCR-VL-1.6"
            and draft.model_version == MODEL
        )
        raw_keys = [initial_job.input_snapshot["published_result_key"], draft.raw_result_key]
    raw_results = [json.loads(await get_minio_client().adownload_file(PRIVATE_BUCKET, key)) for key in raw_keys]
    assert [result["pages"][0]["page_index"] for result in raw_results] == [0, 1]
    assert (
        raw_results[0]["failed_pages"] == [{"page_index": 1, "error_code": "provider_failed"}]
        and raw_results[1]["failed_pages"] == []
    )
    assert all(result["usages"][0]["usage"]["total_tokens"] == 12 for result in raw_results)
    for result in raw_results:
        parsed_page = result["pages"][0]
        source = parsed_page["raw"][0]["result"]["layoutParsingResults"][0]["prunedResult"]
        assert (source["width"], source["height"]) == (1200, 1600)
        assert source["model_settings"]["use_doc_preprocessor"] is False
        assert source["parsing_res_list"][1]["block_bbox"] == [120, 320, 960, 480]
        assert parsed_page["blocks"][1]["bbox"] == [0.1, 0.2, 0.8, 0.3]
        if parsed_page["page_index"] == 1:
            assert source["parsing_res_list"][1]["block_content"].startswith("<table>")
            assert "合成报告姓名" in source["parsing_res_list"][1]["block_content"]
            assert parsed_page["blocks"][4] == {
                "block_id": "p1_b1_r3",
                "page_index": 1,
                "raw_text": "甘油三酯\t1.7\tmmol/L\t0.0-1.7",
                "bbox": [0.1, 0.2, 0.8, 0.3],
                "table_columns": {"name": 0, "value": 1, "unit": 2, "reference": 3},
            }
    assert "合成报告姓名" in str(raw_results) and "read_file" in str(raw_results)
    refreshed = await client.get(f"{ROOT}/members/{member}/observations", headers=headers)
    assert refreshed.status_code == 200 and {row["id"] for row in refreshed.json()} == set(ids)
    for actor in users[1:]:
        assert (await client.get(path, headers=actor["headers"])).status_code == 404
        assert (await client.get(f"{ROOT}/members/{member}/observations", headers=actor["headers"])).status_code == 404

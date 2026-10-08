"""真实 PostgreSQL、MinIO 与 Task 执行器验证选择页版本化重识别。"""

import asyncio
import io
import json
from datetime import timedelta
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from minio.error import S3Error
from pypdf import PdfWriter
from sqlalchemy import select

from test.integration.services.test_durable_task_repository import durable_task_schema  # noqa: F401
from yuxi.config.options import Option
from yuxi.models.providers.cache import ModelInfo, model_cache
from yuxi.repositories.task_repository import TaskRepository
from yuxi.services import health_vision_service as service_module, health_vision_tasks as tasks_module
from yuxi.services.health_vision_service import HealthVisionService, PRIVATE_BUCKET, processor_identity
from yuxi.services.health_vision_types import (
    ConfirmInput,
    DraftPatch,
    HealthVisionError,
    MemberInput,
    ReportField,
    ReportPayload,
    ReportReprocessInput,
    VisionTaskInput,
)
from yuxi.services.task_service import Tasker, process_task
from yuxi.storage.minio import get_minio_client
from yuxi.storage.postgres.models_business import Base, Department, TaskRecord, User
from yuxi.storage.postgres.models_health import (
    HEALTH_TABLES,
    HealthGrant,
    HealthObservation,
    HealthProcessingConsent,
    PrivateUpload,
    VisionDraft,
    VisionJob,
    VisionRevision,
)
from yuxi.utils.datetime_utils import utc_now_naive

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.fixture(scope="session", autouse=True)
def ensure_live_api_schema():
    """只使用本次隔离 Schema，不触碰现有实例的配置。"""


@pytest.fixture(scope="session", autouse=True)
def cleanup_test_knowledge_resources():
    """没有知识库副作用。"""
    yield


@pytest.fixture(scope="session", autouse=True)
def cleanup_test_sandboxes():
    """没有沙盒副作用。"""
    yield


@pytest.mark.parametrize(
    "outcome",
    [
        "success",
        "legacy",
        "edit",
        "early_edit",
        "confirm",
        "revoke",
        "lease",
        "cancel",
        "all_failed",
        "multi_attempt",
        "policy_changed",
        "model_changed",
        "processor_changed",
        "actor_changed",
    ],
)
async def test_report_reprocess_versions_permissions_and_receipts(durable_task_schema, monkeypatch, outcome):  # noqa: F811
    """两次真实执行只替换外部模型协议，PG 版本、授权和对象归属独立回读。"""
    manager = durable_task_schema
    async with manager.async_engine.begin() as connection:
        await connection.run_sync(
            lambda conn: Base.metadata.create_all(conn, tables=[Department.__table__, User.__table__, *HEALTH_TABLES])
        )
    monkeypatch.setattr(service_module, "pg_manager", manager)
    monkeypatch.setattr(tasks_module, "pg_manager", manager)
    local_tasker = Tasker()
    local_tasker.publish = AsyncMock()
    monkeypatch.setattr(service_module, "tasker", local_tasker)
    service = HealthVisionService()
    info = ModelInfo(
        provider_id="synthetic-test",
        model_id="qwen3-vl-flash-2026-01-22",
        model_type="chat",
        display_name="合成协议",
        api_key="synthetic-not-a-real-key",
        base_url="http://test.invalid",
        provider_type="openai",
    )
    processor = processor_identity("report", info)
    options = {"report_model": info.spec, "policy_version": "synthetic-policy", "approved_report_processor": processor}

    async def option_get(_self, db=None):
        """隔离测试进程配置，绝不启用本地 shipping 云调用。"""
        return options

    async def ocr_options(*_args):
        """仅协议替身使用的合成凭据。"""
        return {"_ocr_processor_kwargs": {"api_token": "synthetic-not-a-real-key"}}

    monkeypatch.setattr(Option, "get", option_get)
    monkeypatch.setattr(model_cache, "get_model_info", lambda _spec: info)
    monkeypatch.setattr(tasks_module, "resolve_ocr_task_params", ocr_options)
    monkeypatch.setattr(
        service,
        "configuration",
        AsyncMock(
            return_value={
                "report": {"available": True, "model": info.spec, "processor": processor},
                "policy_version": "synthetic-policy",
            }
        ),
    )
    stage, parsed_indices = "initial", []

    async def parse_page(image, page, kwargs, context, checkpoint, *, authorize, provider_job_id=None):
        """第二页首次失败；重识别仍必须使用原全报告页序。"""
        await authorize()
        assert image.startswith(b"\x89PNG")
        index = page["page_index"]
        parsed_indices.append(index)
        await checkpoint(
            f"synthetic-page-{index}",
            "failed" if index > 0 and (stage == "initial" or outcome == "all_failed") else "submitted",
        )
        if index > 0 and (stage == "initial" or outcome == "all_failed"):
            raise HealthVisionError("provider_failed", "合成单页失败", 503)
        if stage == "reprocess":
            assert index == 1 and provider_job_id is None
        elif stage == "final_reprocess":
            assert index == 2 and provider_job_id is None
        return {
            "blocks": [
                {
                    "page_index": index,
                    "block_id": f"p{index}_metric",
                    "raw_text": "葡萄糖 6.8 units",
                    "bbox": None,
                }
            ]
        }

    async def field_response(spec, prompt, content, context):
        """独立验证文本页归属，所有返回指标都是合成数据。"""
        blocks = json.loads(content[0]["text"])
        assert len(blocks) == 1
        index = blocks[0]["page_index"]
        return {
            "fields": [
                {
                    "name": "葡萄糖",
                    "value_raw": "6.8",
                    "value_numeric": "6.8",
                    "unit_raw": "units",
                    "reference_raw": "",
                    "block_id": f"p{index}_metric",
                }
            ]
        }, {"model": info.model_id}

    monkeypatch.setattr(tasks_module, "parse_report_page", parse_page)
    monkeypatch.setattr(tasks_module, "call_json_model", field_response)
    uid = f"pytest_health_{uuid4().hex}"
    async with manager.get_async_session_context() as session:
        department = Department(name=f"pytest_{uuid4().hex[:16]}")
        session.add(department)
        await session.flush()
        session.add(User(uid=uid, username=uid, role="user", department_id=department.id, password_hash="synthetic"))
    member_id = (await service.create_member(uid, MemberInput(display_name="合成重识别成员", authorized=True)))["id"]
    async with manager.get_async_session_context() as session:
        session.add(
            HealthProcessingConsent(
                member_id=member_id,
                actor_uid=uid,
                purpose="report",
                processor=processor,
                policy_version="synthetic-policy",
            )
        )
    writer, data = PdfWriter(), io.BytesIO()
    writer.add_blank_page(width=120, height=120)
    writer.add_blank_page(width=120, height=120)
    if outcome == "multi_attempt":
        writer.add_blank_page(width=120, height=120)
    writer.write(data)
    upload_id = (await service.upload(uid, member_id, "report", data.getvalue()))["upload_id"]
    storage, objects = get_minio_client(), []
    async with manager.get_async_session_context() as session:
        upload = await session.get(PrivateUpload, upload_id)
        objects.extend([upload.original_key, *[page["object_key"] for page in upload.pages]])
    real_upload, real_download = storage.aupload_file, storage.adownload_file
    downloads = []

    async def upload_then_interrupt(bucket, key, content, mime):
        """真正外部上传之后改变 PG，验证成功 hook 拒绝迟到覆盖。"""
        result = await real_upload(bucket, key, content, mime)
        if key.startswith("results/"):
            objects.append(key)
        if stage != "reprocess" or not key.startswith("results/"):
            return result
        if outcome == "edit":
            latest = ReportPayload.model_validate(revised["payload"])
            latest.fields[0].value_raw, latest.fields[0].value_numeric = "8.1", None
            await service.patch_draft(
                uid, draft_id, "report", DraftPatch(version=2, reason="合成处理中人工修改", report=latest)
            )
        elif outcome == "confirm":
            await service.confirm(uid, draft_id, "report", ConfirmInput(version=2, client_request_id=uuid4()))
        elif outcome == "cancel":
            await TaskRepository().request_cancel(retry_task_id)
        elif outcome in {"revoke", "lease"}:
            async with manager.get_async_session_context() as session:
                if outcome == "revoke":
                    (await session.get(HealthGrant, (member_id, uid))).revoked_at = utc_now_naive()
                else:
                    (await session.get(TaskRecord, retry_task_id)).lease_expires_at = utc_now_naive() - timedelta(
                        seconds=1
                    )
        return result

    async def record_download(bucket, key):
        """记录真实源对象访问，检查成功页没有再次下载。"""
        downloads.append(key)
        return await real_download(bucket, key)

    monkeypatch.setattr(storage, "aupload_file", upload_then_interrupt)
    monkeypatch.setattr(storage, "adownload_file", record_download)
    try:
        initial = await service.create_task(
            uid, "report", VisionTaskInput(member_id=member_id, upload_ids=[upload_id], client_request_id=uuid4())
        )
        await process_task({"worker_id": "synthetic-initial"}, initial["task_id"])
        async with manager.get_async_session_context() as session:
            first_job = await session.scalar(select(VisionJob).where(VisionJob.task_id == initial["task_id"]))
            draft_id = first_job.result_id
            assert draft_id is not None, first_job.error_code
            original_key = (await session.get(VisionDraft, draft_id)).raw_result_key
            if outcome == "legacy":
                first_job.input_snapshot = {
                    key: value for key, value in first_job.input_snapshot.items() if not key.startswith("published_")
                }
        assert draft_id and parsed_indices == ([0, 1, 2] if outcome == "multi_attempt" else [0, 1])
        draft = await service.get_draft(uid, draft_id, "report")
        payload = ReportPayload.model_validate(draft["payload"])
        payload.fields[0].value_raw, payload.fields[0].value_numeric = "7.1", None
        payload.fields.append(ReportField(field_id=uuid4(), name="合成人工补充", value_raw="9"))
        payload.excluded_pages = [1]
        revised = await service.patch_draft(
            uid, draft_id, "report", DraftPatch(version=1, reason="合成保留人工修改", report=payload)
        )
        request = ReportReprocessInput(draft_id=draft_id, version=2, page_indices=[1], client_request_id=uuid4())
        if outcome in {"policy_changed", "model_changed", "processor_changed"}:
            changed_key = outcome.removesuffix("_changed")
            if changed_key == "policy":
                options["policy_version"] = "synthetic-policy-2"
                service.configuration.return_value["policy_version"] = "synthetic-policy-2"
            elif changed_key == "model":
                options["report_model"] = "synthetic:model-2"
                service.configuration.return_value["report"]["model"] = "synthetic:model-2"
            else:
                options["approved_report_processor"] = "synthetic-processor-2"
                service.configuration.return_value["report"]["processor"] = "synthetic-processor-2"
            async with manager.get_async_session_context() as session:
                consent = await session.get(HealthProcessingConsent, (member_id, uid, "report"))
                consent.policy_version = service.configuration.return_value["policy_version"]
                consent.processor = service.configuration.return_value["report"]["processor"]
            with pytest.raises(HealthVisionError, match="policy_changed"):
                await service.reprocess_report(uid, request)
            async with manager.get_async_session_context() as session:
                assert len((await session.scalars(select(VisionJob))).all()) == 1
                assert (await session.get(VisionDraft, draft_id)).version == 2
            return
        if outcome == "actor_changed":
            uid = f"pytest_health_{uuid4().hex}"
            async with manager.get_async_session_context() as session:
                session.add(
                    User(uid=uid, username=uid, role="user", department_id=department.id, password_hash="synthetic")
                )
                await session.flush()
                session.add(
                    HealthGrant(
                        member_id=member_id,
                        actor_uid=uid,
                        scopes=["report_view", "profile_edit", "report_upload", "ai_use"],
                    )
                )
                session.add(
                    HealthProcessingConsent(
                        member_id=member_id,
                        actor_uid=uid,
                        purpose="report",
                        processor=processor,
                        policy_version="synthetic-policy",
                    )
                )
                parent = await session.get(VisionJob, first_job.id)
                entries = [dict(entry) for entry in parent.input_snapshot["provider_jobs"]]
                entries[1].update(state="submitted", provider_job_id="synthetic-private-parent-job")
                parent.input_snapshot = {**parent.input_snapshot, "provider_jobs": entries}
        retry_task_id = (await service.reprocess_report(uid, request))["task_id"]
        if outcome == "actor_changed":
            async with manager.get_async_session_context() as session:
                created_job = await session.scalar(select(VisionJob).where(VisionJob.task_id == retry_task_id))
                assert created_job.input_snapshot.get("provider_jobs", []) == []
        assert (await service.reprocess_report(uid, request))["task_id"] == retry_task_id
        with pytest.raises(HealthVisionError, match="idempotency_conflict"):
            await service.reprocess_report(uid, request.model_copy(update={"page_indices": [0]}))
        with pytest.raises(HealthVisionError, match="report_reprocess_invalid"):
            await service.reprocess_report(
                uid, request.model_copy(update={"page_indices": [0], "client_request_id": uuid4()})
            )
        with pytest.raises(HealthVisionError, match="reprocess_conflict"):
            await service.reprocess_report(uid, request.model_copy(update={"client_request_id": uuid4()}))
        if outcome == "early_edit":
            await service.patch_draft(
                uid,
                draft_id,
                "report",
                DraftPatch(
                    version=2, reason="合成排队期间修改", report=ReportPayload.model_validate(revised["payload"])
                ),
            )
        stage, parsed_indices = "reprocess", []
        downloads.clear()
        await process_task({"worker_id": "synthetic-reprocess"}, retry_task_id)
        if outcome == "lease":
            from yuxi.services.task_queue_service import finalize_task_failure

            await TaskRepository().reconcile_expired_leases(before_fail=finalize_task_failure)
        assert parsed_indices == ([] if outcome == "early_edit" else [1])
        assert downloads == ([] if outcome == "early_edit" else [f"uploads/{upload_id}/pages/1.png"])
        await tasks_module.cleanup_health_result_objects(initial["task_id"])
        await tasks_module.cleanup_health_result_objects(retry_task_id)
        assert await real_download(PRIVATE_BUCKET, original_key)
        if outcome in {"success", "legacy", "multi_attempt", "actor_changed"}:
            assert (await service.reprocess_report(uid, request))["task_id"] == retry_task_id
        async with manager.get_async_session_context() as session:
            current = await session.get(VisionDraft, draft_id)
            task = await session.get(TaskRecord, retry_task_id)
            second_job = await session.scalar(select(VisionJob).where(VisionJob.task_id == retry_task_id))
            revisions = list(
                (await session.scalars(select(VisionRevision).where(VisionRevision.draft_id == draft_id))).all()
            )
            assert len((await session.scalars(select(VisionJob))).all()) == 2
            assert second_job.parent_task_id == initial["task_id"]
            assert current.payload["excluded_pages"] == [1]
            assert current.payload["fields"][0]["evidence"] == revised["payload"]["fields"][0]["evidence"]
            assert current.payload["fields"][1]["source"] == "manual"
            if outcome in {"success", "legacy", "multi_attempt", "actor_changed"}:
                assert task.status == "success" and task.result == {"result_id": draft_id}
                assert current.version == 3 and current.job_id == second_job.id
                assert current.payload["fields"][0]["value_raw"] == "7.1"
                assert current.payload["fields"][2]["evidence"]["page_index"] == 1
                assert current.payload["pages"][1]["status"] == "ready"
                assert current.original_payload["fields"][0]["value_raw"] == "6.8"
                assert len(revisions) == 2 and any(
                    revision.version == 3 and revision.payload == current.payload for revision in revisions
                )
                assert second_job.input_snapshot["published_result_key"] == current.raw_result_key
                assert await real_download(PRIVATE_BUCKET, current.raw_result_key)
                with pytest.raises(HealthVisionError, match="version_conflict"):
                    await service.confirm(uid, draft_id, "report", ConfirmInput(version=2, client_request_id=uuid4()))
            else:
                assert task.status == ("cancelled" if outcome == "cancel" else "failed")
                assert current.job_id == first_job.id and current.raw_result_key == original_key
                assert current.version == (3 if outcome in {"edit", "early_edit"} else 2)
                assert current.payload["fields"][0]["value_raw"] == ("8.1" if outcome == "edit" else "7.1")
                assert current.review_status == ("confirmed" if outcome == "confirm" else "pending_confirmation")
                observations = list(
                    (
                        await session.scalars(select(HealthObservation).where(HealthObservation.member_id == member_id))
                    ).all()
                )
                assert len(observations) == (2 if outcome == "confirm" else 0)
                for key in second_job.input_snapshot.get("raw_result_keys", []):
                    with pytest.raises(S3Error) as error:
                        await asyncio.to_thread(storage.client.stat_object, PRIVATE_BUCKET, key)
                    assert error.value.code == "NoSuchKey"
        if outcome == "all_failed":
            request_id = uuid4()
            recovered_task = await service.retry(uid, retry_task_id, request_id)
            assert (await service.retry(uid, retry_task_id, request_id))["task_id"] == recovered_task["task_id"]
            async with manager.get_async_session_context() as session:
                recovered_job = await session.scalar(
                    select(VisionJob).where(VisionJob.task_id == recovered_task["task_id"])
                )
                assert recovered_job.parent_task_id == retry_task_id
                assert recovered_job.input_snapshot["reprocess"]["page_indices"] == [1]
                assert recovered_job.input_snapshot["reprocess"]["version"] == 2
                assert len((await session.scalars(select(VisionJob))).all()) == 3
            outcome, parsed_indices = "recovered", []
            downloads.clear()
            await process_task({"worker_id": "synthetic-retry"}, recovered_task["task_id"])
            assert parsed_indices == [1] and downloads == [f"uploads/{upload_id}/pages/1.png"]
            async with manager.get_async_session_context() as session:
                assert (await session.get(TaskRecord, recovered_task["task_id"])).status == "success"
                assert (await session.get(TaskRecord, retry_task_id)).status == "failed"
                assert (await session.get(VisionDraft, draft_id)).version == 3
        if outcome == "multi_attempt":
            previous_key = current.raw_result_key
            stage, parsed_indices = "final_reprocess", []
            request = ReportReprocessInput(draft_id=draft_id, version=3, page_indices=[2], client_request_id=uuid4())
            final_task_id = (await service.reprocess_report(uid, request))["task_id"]
            downloads.clear()
            await process_task({"worker_id": "synthetic-third-attempt"}, final_task_id)
            assert downloads == [f"uploads/{upload_id}/pages/2.png"] and parsed_indices == [2]
            for task_id in (initial["task_id"], retry_task_id, final_task_id):
                await tasks_module.cleanup_health_result_objects(task_id)
            async with manager.get_async_session_context() as session:
                final = await session.get(VisionDraft, draft_id)
                final_job = await session.scalar(select(VisionJob).where(VisionJob.task_id == final_task_id))
                assert (await session.get(TaskRecord, final_task_id)).status == "success"
                assert final_job.parent_task_id == retry_task_id and final_job.phase == "ready"
                assert final.version == 4 and final.payload["excluded_pages"] == [1]
                assert final.payload["fields"][0]["value_raw"] == "7.1"
                assert final.payload["fields"][1]["source"] == "manual"
                assert [p["status"] for p in final.payload["pages"]] == ["ready"] * 3
                assert [f["evidence"]["page_index"] for f in final.payload["fields"] if f.get("evidence")] == [0, 1, 2]
                assert (
                    len(
                        (await session.scalars(select(VisionRevision).where(VisionRevision.draft_id == draft_id))).all()
                    )
                    == 3
                )
                for retained_key in (original_key, previous_key, final.raw_result_key):
                    assert await real_download(PRIVATE_BUCKET, retained_key)
    finally:
        for key in objects:
            await storage.adelete_file(PRIVATE_BUCKET, key)

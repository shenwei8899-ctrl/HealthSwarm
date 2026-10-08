"""独立 PG Schema 与真实 MinIO 验证执行器提交和结果上传后的拒绝回收。"""

import asyncio
import io
import json
from datetime import timedelta
from uuid import uuid4
from unittest.mock import AsyncMock

import pytest
import httpx
from PIL import Image
from minio.error import S3Error
from sqlalchemy import inspect, select

from test.integration.services.test_durable_task_repository import durable_task_schema  # noqa: F401
from yuxi.config.options import Option
from yuxi.models.providers.cache import ModelInfo, model_cache
from yuxi.repositories.task_repository import TaskRepository
from yuxi.services import health_vision_service as service_module, health_vision_tasks as tasks_module
from yuxi.services.health_vision_service import HealthVisionService, PRIVATE_BUCKET, processor_identity
from yuxi.services.health_vision_types import ConfirmInput, DraftPatch, HealthVisionError, MemberInput, ReportPayload
from yuxi.services.task_service import Tasker, process_task
from yuxi.storage.minio import get_minio_client
from yuxi.storage.postgres.models_business import (
    Base,
    Department,
    User,
    TaskRecord,
    ModelProvider,
    Project,
    Conversation,
)
from yuxi.storage.postgres.models_health import (
    HEALTH_TABLES,
    FoodRecord,
    HealthGrant,
    HealthObservation,
    HealthProcessingConsent,
    PrivateUpload,
    VisionDraft,
    VisionJob,
    RecipeVersion,
    PortionReference,
)
from yuxi.utils.datetime_utils import utc_now_naive

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.mark.parametrize("changed", [None, "model", "processor", "policy_version", "prompt_version", "actor_uid"])
async def test_report_retry_checkpoint_binding_and_revocation(durable_task_schema, monkeypatch, changed):  # noqa: F811
    """真实 PG 证明重试只复制同归属快照，撤权后不创建新任务。"""
    manager = durable_task_schema
    async with manager.async_engine.begin() as connection:
        await connection.run_sync(
            lambda conn: Base.metadata.create_all(
                conn,
                tables=[
                    Department.__table__,
                    User.__table__,
                    Project.__table__,
                    Conversation.__table__,
                    *HEALTH_TABLES,
                ],
            )
        )
    monkeypatch.setattr(service_module, "pg_manager", manager)
    service = HealthVisionService()
    config = {
        "policy_version": "synthetic-policy",
        "report": {"available": True, "model": "synthetic/fixed", "processor": "synthetic-processor"},
    }
    monkeypatch.setattr(service, "configuration", AsyncMock(return_value=config))
    local_tasker = Tasker()
    monkeypatch.setattr(local_tasker, "publish", AsyncMock())
    monkeypatch.setattr(service_module, "tasker", local_tasker)
    uid, other_uid = f"pytest_health_{uuid4().hex}", f"pytest_health_{uuid4().hex}"
    async with manager.get_async_session_context() as session:
        department = Department(name=f"pytest_{uuid4().hex[:16]}")
        session.add(department)
        await session.flush()
        for identity in (uid, other_uid):
            session.add(User(uid=identity, username=identity, department_id=department.id, password_hash="synthetic"))
    member_id = (await service.create_member(uid, MemberInput(display_name="合成恢复成员", authorized=True)))["id"]
    upload_id, parent_id = str(uuid4()), str(uuid4())
    entry = {
        "page_index": 0,
        "upload_id": upload_id,
        "upload_page_index": 0,
        "provider_job_id": "synthetic-existing",
        "state": "submitted",
    }
    snapshot = {
        "model": "synthetic/fixed",
        "processor": "synthetic-processor",
        "policy_version": "synthetic-policy",
        "prompt_version": "health-vision-v1",
        "provider_jobs": [entry],
    }
    if changed is not None and changed != "actor_uid":
        snapshot[changed] = "synthetic-old-value"
    async with manager.get_async_session_context() as session:
        session.add(
            PrivateUpload(
                id=upload_id,
                actor_uid=uid,
                member_id=member_id,
                purpose="report",
                original_key=f"uploads/{upload_id}/original",
                sha256="0" * 64,
                mime="image/png",
                byte_size=100,
                pages=[
                    {"page_index": 0, "object_key": f"uploads/{upload_id}/pages/0.png", "width": 120, "height": 120}
                ],
            )
        )
        session.add(
            HealthProcessingConsent(
                member_id=member_id,
                actor_uid=uid,
                purpose="report",
                processor="synthetic-processor",
                policy_version="synthetic-policy",
            )
        )
        parent_task = await local_tasker.create_in_session(
            session, name="合成失败报告", task_type="report_extract_v1", payload={"job_id": parent_id}
        )
        (await session.get(TaskRecord, parent_task.id)).status = "failed"
        session.add(
            VisionJob(
                id=parent_id,
                task_id=parent_task.id,
                member_id=member_id,
                actor_uid=other_uid if changed == "actor_uid" else uid,
                kind="report",
                request_id=str(uuid4()),
                fingerprint="0" * 64,
                upload_ids=[upload_id],
                input_snapshot=snapshot,
            )
        )
    request_id = uuid4()
    result = await service.retry(uid, parent_task.id, request_id)
    replay = await service.retry(uid, parent_task.id, request_id)
    assert replay["task_id"] == result["task_id"]
    async with manager.get_async_session_context() as session:
        new_job = await session.scalar(select(VisionJob).where(VisionJob.task_id == result["task_id"]))
        assert new_job.parent_task_id == parent_task.id and new_job.actor_uid == uid
        assert new_job.input_snapshot.get("provider_jobs", []) == ([entry] if changed is None else [])
        assert (await session.get(TaskRecord, result["task_id"])).status == "pending"
        (await session.get(HealthGrant, (member_id, uid))).revoked_at = utc_now_naive()
    with pytest.raises(HealthVisionError, match="not_found"):
        await service.retry(uid, parent_task.id, uuid4())
    async with manager.get_async_session_context() as session:
        assert len((await session.scalars(select(VisionJob))).all()) == 2


@pytest.fixture(scope="session", autouse=True)
def ensure_live_api_schema():
    """隔离 Schema 的执行器验证不调用现有实例的管理 API。"""


@pytest.fixture(scope="session", autouse=True)
def cleanup_test_knowledge_resources():
    """只使用测试自己的 PG Schema。"""
    yield


@pytest.fixture(scope="session", autouse=True)
def cleanup_test_sandboxes():
    """没有沙盒副作用。"""
    yield


async def test_health_schema_upgrade_keeps_v1_food_and_is_idempotent(durable_task_schema):  # noqa: F811
    """真实 PG 从旧健康表增加两张表，不覆盖既有食品版本。"""
    manager = durable_task_schema
    new_tables = {RecipeVersion.__table__, PortionReference.__table__}
    async with manager.async_engine.begin() as connection:
        await connection.run_sync(
            lambda conn: Base.metadata.create_all(
                conn,
                tables=[
                    Department.__table__,
                    User.__table__,
                    Project.__table__,
                    Conversation.__table__,
                    *[table for table in HEALTH_TABLES if table not in new_tables],
                ],
            )
        )
        assert "health_recipe_version" not in await connection.run_sync(lambda conn: inspect(conn).get_table_names())
    food_id, uid = str(uuid4()), f"pytest_health_{uuid4().hex}"
    async with manager.get_async_session_context() as session:
        department = Department(name=f"pytest_{uuid4().hex[:16]}")
        session.add(department)
        await session.flush()
        session.add(User(uid=uid, username=uid, department_id=department.id, role="admin", password_hash="synthetic"))
        await session.flush()
        session.add(
            FoodRecord(
                id=food_id,
                published_by=uid,
                record_code="synthetic-old",
                name="合成旧食品",
                cooking_state="熟",
                source="合成旧版本",
                license="仅测试",
                edition="old",
                dataset_version="old-1",
                nutrients={"energy_kcal": "200"},
                recipe_estimated=False,
            )
        )
    await manager.create_health_tables()
    await manager.create_health_tables()
    async with manager.async_engine.begin() as connection:
        tables = await connection.run_sync(lambda conn: inspect(conn).get_table_names())
        assert {"health_recipe_version", "health_portion_reference"} <= set(tables)
    async with manager.get_async_session_context() as session:
        original = await session.get(FoodRecord, food_id)
        assert original.nutrients == {"energy_kcal": "200"} and original.dataset_version == "old-1"


@pytest.mark.parametrize(
    "kind,outcome,model_change",
    [
        (kind, outcome, None)
        for kind in ("meal", "report")
        for outcome in ("success", "cancel", "revoke", "source_delete", "source_delete_retry", "expired_lease")
    ]
    + [
        ("report", outcome, None)
        for outcome in (
            "poll_revoke",
            "poll_consent",
            "download_expired_lease",
            "partial_first",
            "partial_last",
            "all_pages_failed",
            "page_revoke",
            "page_consent",
        )
    ]
    + [("meal", "success", change) for change in ("disabled", "credentials", "endpoint", "type")],
)
async def test_executor_result_binding_and_orphan_cleanup(
    durable_task_schema,  # noqa: F811
    monkeypatch,
    httpx_mock,
    outcome,
    kind,
    model_change,
):
    """仅模型外部响应使用确定性替身，执行器、授权、事务、lease 和对象存储均真实。"""
    manager = durable_task_schema
    async with manager.async_engine.begin() as connection:
        await connection.run_sync(
            lambda conn: Base.metadata.create_all(
                conn,
                tables=[
                    Department.__table__,
                    User.__table__,
                    Project.__table__,
                    Conversation.__table__,
                    ModelProvider.__table__,
                    *HEALTH_TABLES,
                ],
            )
        )
    monkeypatch.setattr(service_module, "pg_manager", manager)
    monkeypatch.setattr(tasks_module, "pg_manager", manager)
    info = ModelInfo(
        provider_id="synthetic-test",
        model_id="qwen3-vl-flash-2026-01-22",
        model_type="chat",
        display_name="合成协议替身",
        api_key="synthetic-not-a-real-key",
        base_url="http://test.invalid",
        provider_type="openai",
    )
    processor = processor_identity(kind, info)
    async with manager.get_async_session_context() as session:
        session.add(
            ModelProvider(
                provider_id=info.provider_id,
                display_name=info.display_name,
                provider_type=info.provider_type,
                api_key=info.api_key,
                base_url=info.base_url,
                is_enabled=True,
                enabled_models=[{"id": info.model_id, "type": "chat", "display_name": info.display_name}],
            )
        )
    options = {
        f"{kind}_model": info.spec,
        "policy_version": "synthetic-policy",
        f"approved_{kind}_processor": processor,
    }

    async def ocr_options(*_args):
        """只提供合成解析参数，无真实外呼或配置副作用。"""
        return {"_ocr_processor_kwargs": {"api_token": "synthetic-not-a-real-key"}}

    async def report_response(image, page, kwargs, context, checkpoint, *, authorize, provider_job_id=None):
        """保留真实页关联与 request checkpoint，合成报告包含分块身份值。"""
        assert image.startswith(b"\x89PNG")
        index = page["page_index"]
        await authorize()
        if outcome == "success":
            assert provider_job_id == "synthetic-existing-request"
        else:
            assert provider_job_id is None
            await checkpoint("synthetic-provider-request")
        if (
            outcome == "all_pages_failed"
            or (outcome == "partial_first" and index == 0)
            or (outcome == "partial_last" and index == 1)
        ):
            raise HealthVisionError("provider_failed", "合成单页失败", 503)
        return {
            "blocks": [
                {"block_id": f"p{index}_name", "page_index": index, "raw_text": "姓名", "bbox": None},
                {"block_id": f"p{index}_identity", "page_index": index, "raw_text": "合成杨铁柱 12345", "bbox": None},
                {
                    "block_id": f"p{index}_metric",
                    "page_index": index,
                    "raw_text": "葡萄糖 6.8 mmol/L 3.9-6.1",
                    "bbox": None,
                },
            ]
        }

    async def field_response(spec, prompt, content, context):
        """独立断言外发指标文本和真实证据绑定，不伪造云识别效果。"""
        blocks = json.loads(content[0]["text"])
        assert len(blocks) == 1 and blocks[0]["block_id"].endswith("_metric")
        assert "合成杨铁柱" not in content[0]["text"]
        if outcome in {"page_revoke", "page_consent"}:
            async with manager.get_async_session_context() as session:
                if outcome == "page_revoke":
                    (await session.get(HealthGrant, (member_id, uid))).revoked_at = utc_now_naive()
                else:
                    (
                        await session.get(HealthProcessingConsent, (member_id, uid, "report"))
                    ).revoked_at = utc_now_naive()
        return {
            "fields": [
                {
                    "name": "葡萄糖",
                    "value_raw": "6.8",
                    "value_numeric": "6.8",
                    "unit_raw": "mmol/L",
                    "reference_raw": "3.9-6.1",
                    "block_id": blocks[0]["block_id"],
                }
            ]
        }, {"model": info.model_id}

    monkeypatch.setattr(tasks_module, "resolve_ocr_task_params", ocr_options)
    monkeypatch.setattr(tasks_module, "parse_report_page", report_response)
    monkeypatch.setattr(tasks_module, "call_json_model", field_response)

    async def option_get(_self, db=None):
        """只在隔离的本测试进程代替配置，绝不改变运行实例的配置。"""
        return options

    monkeypatch.setattr(Option, "get", option_get)
    monkeypatch.setattr(model_cache, "get_model_info", lambda _spec: info)

    async def model_response(_spec, images, context):
        """图像候选替身无营养值，不声称真实视觉模型效果。"""
        assert len(images) == 1 and images[0].startswith(b"\x89PNG")
        return {"items": [{"item_id": str(uuid4()), "name": "合成候选食物"}], "metadata": {"model": info.model_id}}

    monkeypatch.setattr(tasks_module, "recognize_meal", model_response)
    before_result = outcome in {"poll_revoke", "poll_consent", "download_expired_lease"}
    uid, member_id = f"pytest_health_{uuid4().hex}", None
    service = HealthVisionService()
    async with manager.get_async_session_context() as session:
        department = Department(name=f"pytest_{uuid4().hex[:16]}")
        session.add(department)
        await session.flush()
        session.add(User(uid=uid, username=uid, department_id=department.id, role="user", password_hash="synthetic"))
    member_id = (await service.create_member(uid, MemberInput(display_name="合成成员", authorized=True)))["id"]
    buffer = io.BytesIO()
    multi_page = outcome in {"partial_first", "partial_last", "all_pages_failed", "page_revoke", "page_consent"}
    if multi_page:
        from pypdf import PdfWriter

        writer = PdfWriter()
        writer.add_blank_page(width=120, height=120)
        writer.add_blank_page(width=120, height=120)
        writer.write(buffer)
    else:
        Image.new("RGB", (120, 120), "white").save(buffer, "PNG")
    upload_id = (await service.upload(uid, member_id, kind, buffer.getvalue()))["upload_id"]
    job_id = str(uuid4())
    async with manager.get_async_session_context() as session:
        session.add(
            HealthProcessingConsent(
                member_id=member_id,
                actor_uid=uid,
                purpose=kind,
                processor=processor,
                policy_version="synthetic-policy",
            )
        )
        task = await Tasker().create_in_session(
            session,
            name="合成执行器测试",
            task_type="meal_recognize_v1" if kind == "meal" else "report_extract_v1",
            payload={"job_id": job_id},
        )
        session.add(
            VisionJob(
                id=job_id,
                task_id=task.id,
                member_id=member_id,
                actor_uid=uid,
                kind=kind,
                request_id=str(uuid4()),
                fingerprint="0" * 64,
                upload_ids=[upload_id],
                input_snapshot={
                    "model": info.spec,
                    "processor": processor,
                    "policy_version": "synthetic-policy",
                    "meal_type": "lunch",
                    "eaten_at": "2026-10-04T12:00:00+08:00",
                    "provider_jobs": [
                        {
                            "page_index": 0,
                            "upload_id": upload_id,
                            "upload_page_index": 0,
                            "provider_job_id": "synthetic-existing-request",
                            "state": "submitted",
                        }
                    ]
                    if kind == "report" and (outcome == "success" or before_result)
                    else [],
                },
            )
        )
    storage = get_minio_client()
    if model_change:
        real_download = storage.adownload_file

        async def download_then_change_model(bucket, key):
            """初检通过后改真实 PG，保留旧运行投影，下一外呼必须拒绝。"""
            data = await real_download(bucket, key)
            async with manager.get_async_session_context() as session:
                provider = await session.scalar(
                    select(ModelProvider).where(ModelProvider.provider_id == info.provider_id)
                )
                if model_change == "disabled":
                    provider.is_enabled = False
                elif model_change == "credentials":
                    provider.api_key = ""
                elif model_change == "endpoint":
                    provider.base_url = "https://changed.example.invalid/v1"
                else:
                    provider.enabled_models = [{"id": info.model_id, "type": "embedding"}]
            return data

        monkeypatch.setattr(storage, "adownload_file", download_then_change_model)
    if before_result:
        from yuxi.services.health_vision_provider import parse_report_page

        monkeypatch.setattr(tasks_module, "parse_report_page", parse_report_page)

        async def poll_then_invalidate(_request):
            """在真实 PG 撤回 grant、同意或 lease，后续外部访问必须停止。"""
            async with manager.get_async_session_context() as session:
                if outcome == "poll_revoke":
                    (await session.get(HealthGrant, (member_id, uid))).revoked_at = utc_now_naive()
                elif outcome == "poll_consent":
                    (
                        await session.get(HealthProcessingConsent, (member_id, uid, "report"))
                    ).revoked_at = utc_now_naive()
                else:
                    (await session.get(TaskRecord, task.id)).lease_expires_at = utc_now_naive() - timedelta(seconds=1)
            return httpx.Response(
                200,
                json={
                    "data": {
                        "state": "done" if outcome == "download_expired_lease" else "pending",
                        "resultUrl": {"jsonUrl": "https://synthetic.bcebos.com/must-not-download.jsonl"},
                    }
                },
            )

        httpx_mock.add_callback(
            poll_then_invalidate,
            method="GET",
            url="https://paddleocr.aistudio-app.com/api/v2/ocr/jobs/synthetic-existing-request",
        )
    real_upload = storage.aupload_file
    result_keys = []

    async def upload_then_interrupt(bucket, key, data, content_type):
        """在原始结果已落 MinIO 后产生真正的取消、撤回、删除或 lease 失效。"""
        response = await real_upload(bucket, key, data, content_type)
        if not key.startswith("results/"):
            return response
        result_keys.append(key)
        if outcome == "cancel":
            await TaskRepository().request_cancel(task.id)
        elif outcome in {"source_delete", "source_delete_retry"}:
            if outcome == "source_delete_retry":
                real_delete = storage.adelete_file

                async def unavailable(*args):
                    """模拟一次存储故障，验证标记已删除后精确键仍可恢复清理。"""
                    raise RuntimeError("synthetic storage unavailable")

                monkeypatch.setattr(storage, "adelete_file", unavailable)
                with pytest.raises(RuntimeError, match="synthetic"):
                    await service.delete_upload(uid, upload_id)
                monkeypatch.setattr(storage, "adelete_file", real_delete)
                await asyncio.to_thread(storage.client.stat_object, PRIVATE_BUCKET, f"uploads/{upload_id}/original")
            else:
                await service.delete_upload(uid, upload_id)
        elif outcome in {"revoke", "expired_lease"}:
            async with manager.get_async_session_context() as session:
                if outcome == "revoke":
                    grant = await session.get(HealthGrant, (member_id, uid))
                    grant.revoked_at = utc_now_naive()
                else:
                    record = await session.get(TaskRecord, task.id)
                    record.lease_expires_at = utc_now_naive() - timedelta(seconds=1)
        return response

    monkeypatch.setattr(storage, "aupload_file", upload_then_interrupt)
    try:
        await process_task({"worker_id": "synthetic-executor"}, task.id)
        if outcome in {"expired_lease", "download_expired_lease"}:
            from yuxi.services.task_queue_service import finalize_task_failure

            await TaskRepository().reconcile_expired_leases(before_fail=finalize_task_failure)
        await tasks_module.cleanup_health_result_objects(task.id)
        if outcome == "source_delete_retry":
            await tasks_module.cleanup_health_result_objects()
            for key in [f"uploads/{upload_id}/original", f"uploads/{upload_id}/pages/0.png"]:
                with pytest.raises(S3Error) as error:
                    await asyncio.to_thread(storage.client.stat_object, PRIVATE_BUCKET, key)
                assert error.value.code == "NoSuchKey"
        async with manager.get_async_session_context() as session:
            record = await session.get(TaskRecord, task.id)
            job = await session.get(VisionJob, job_id)
            drafts = list((await session.scalars(select(VisionDraft).where(VisionDraft.member_id == member_id))).all())
            if model_change or before_result or outcome in {"page_revoke", "page_consent", "all_pages_failed"}:
                assert result_keys == [] and drafts == [] and record.status == "failed"
                if model_change:
                    assert "policy_changed" in record.error
                    assert record.result is None and record.worker_id is None and record.lease_expires_at is None
                    assert job.phase == "preprocessing"
                if before_result:
                    assert [(request.method, request.url.path) for request in httpx_mock.get_requests()] == [
                        ("GET", "/api/v2/ocr/jobs/synthetic-existing-request")
                    ]
            else:
                assert result_keys and result_keys[0] in job.input_snapshot["raw_result_keys"]
            if kind == "report":
                external = job.input_snapshot["provider_jobs"][0]
                assert external["upload_id"] == upload_id and external["upload_page_index"] == 0
                assert external["state"] == "submitted"
            if not model_change and (outcome == "success" or outcome in {"partial_first", "partial_last"}):
                assert record.status == "success" and len(drafts) == 1
                assert drafts[0].review_status == "pending_confirmation"
                assert record.result == {"result_id": drafts[0].id}
                if kind == "meal":
                    assert drafts[0].payload["items"][0]["grams"] is None
                else:
                    assert drafts[0].payload["fields"][0]["value_numeric"] == "6.8"
                    good_page = 1 if outcome == "partial_first" else 0
                    assert drafts[0].payload["fields"][0]["evidence"]["block_id"] == f"p{good_page}_metric"
                    assert drafts[0].payload["pages"][0]["upload_id"] == upload_id
                    assert drafts[0].original_payload == drafts[0].payload
                assert await storage.adownload_file(PRIVATE_BUCKET, result_keys[0])
            else:
                assert record.status == ("cancelled" if outcome == "cancel" else "failed") and drafts == []
                for key in result_keys:
                    with pytest.raises(S3Error) as error:
                        await asyncio.to_thread(storage.client.stat_object, PRIVATE_BUCKET, key)
                    assert error.value.code == "NoSuchKey"
        if outcome in {"partial_first", "partial_last"}:
            draft = await service.get_draft(uid, drafts[0].id, "report")
            failed_index = 0 if outcome == "partial_first" else 1
            pages = draft["payload"]["pages"]
            assert len(pages) == 2 and pages[failed_index]["status"] == "failed"
            assert pages[failed_index]["error_code"] == "provider_failed"
            assert pages[1 - failed_index]["status"] == "ready"
            assert all(page["quality_flags"] == ["low_resolution"] for page in pages)
            assert job.phase == "partial_ready"
            with pytest.raises(HealthVisionError, match="report_pages_incomplete"):
                await service.confirm(
                    uid,
                    draft["id"],
                    "report",
                    ConfirmInput(version=1, client_request_id=uuid4(), accept_incomplete=True),
                )
            draft["payload"]["excluded_pages"] = [failed_index]
            revised = await service.patch_draft(
                uid,
                draft["id"],
                "report",
                DraftPatch(
                    version=1, reason="合成测试明确排除失败页", report=ReportPayload.model_validate(draft["payload"])
                ),
            )
            confirmed = await service.confirm(
                uid, draft["id"], "report", ConfirmInput(version=revised["version"], client_request_id=uuid4())
            )
            async with manager.get_async_session_context() as session:
                observations = list(
                    (
                        await session.scalars(select(HealthObservation).where(HealthObservation.member_id == member_id))
                    ).all()
                )
                assert len(observations) == 1 and observations[0].id == confirmed["target_ids"][0]
                assert observations[0].snapshot["evidence"]["page_index"] == 1 - failed_index
    finally:
        # 只删除本测试随机对象键；不改变任何用户或其他环境的存储。
        for key in result_keys:
            await storage.adelete_file(PRIVATE_BUCKET, key)
        if outcome != "source_delete":
            async with manager.get_async_session_context() as session:
                upload = await session.get(PrivateUpload, upload_id)
                keys = [upload.original_key, *[page["object_key"] for page in upload.pages]]
            for key in keys:
                await storage.adelete_file(PRIVATE_BUCKET, key)

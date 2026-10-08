"""私有饮食图片经真实 HTTP 与独立 worker 形成版本化正式日记。"""

import asyncio
import hashlib
import io
import json
import os
from copy import deepcopy
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from PIL import Image
from sqlalchemy import select, text

from test.e2e.test_health_consultation_e2e import wait_until
from test.integration.services.test_health_vision_http import ROOT, confirmation, create_member, health_http  # noqa: F401
from yuxi.services.health_vision_service import PRIVATE_BUCKET
from yuxi.storage.minio import get_minio_client
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_business import TaskRecord, ModelProvider
from yuxi.models.providers.cache import model_cache
from yuxi.services.task_service import tasker
from yuxi.storage.postgres.models_health import DietLog, NutritionCalculation, PrivateUpload, VisionDraft, VisionJob

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.e2e,
    pytest.mark.slow,
    pytest.mark.skipif(
        os.getenv("HEALTH_CONSULTATION_E2E_ISOLATED") != "true",
        reason="饮食合成 E2E 只在健康专用 Compose 隔离槽位运行",
    ),
]
MODEL = "qwen3-vl-flash-2026-01-22"


@pytest_asyncio.fixture
async def isolated_meal(health_http):  # noqa: F811
    """只在实际隔离数据库且审批为空时配置合成本地视觉入口。"""
    async with pg_manager.get_async_session_context() as session:
        assert await session.scalar(text("SELECT current_database()")) == "health_consultation_e2e"
    client, users = health_http
    assert str(client.base_url).rstrip("/") == "http://localhost:5050"
    admin = users[2]["headers"]
    current = await client.get(f"{ROOT}/configuration", headers=admin)
    assert current.status_code == 200 and not current.json()["policy_version"]
    provider_id = f"health-meal-replay-{uuid4().hex[:12]}"
    response = await client.post(
        "/api/system/model-providers",
        headers=admin,
        json={
            "provider_id": provider_id,
            "display_name": "Synthetic meal replay only",
            "provider_type": "openai",
            "base_url": "http://api:8767/v1",
            "api_key": "synthetic-health-meal-key",
            "is_enabled": True,
            "capabilities": ["chat", "vision"],
            "enabled_models": [{"id": MODEL, "display_name": MODEL, "type": "chat", "source": "manual"}],
        },
    )
    assert response.status_code == 200, response.text
    spec = f"{provider_id}:{MODEL}"
    try:
        configured = await client.put(
            f"{ROOT}/configuration",
            headers=admin,
            json={
                "meal_model": spec,
                "policy_version": "synthetic-meal-only-v1",
                "cloud_processing_reviewed": True,
            },
        )
        assert configured.status_code == 200 and configured.json()["meal"]["available"], configured.text
        yield client, users, configured.json(), spec
    finally:
        await finish_meal_fixture(client, users, provider_id)


async def finish_meal_fixture(client, users, provider_id):
    """任务收敛失败也关闭合成审批；资源由外层按 PG 所有权决定保留。"""
    admin = users[2]["headers"]
    try:
        await drain_meal_tasks(client, users)
    finally:
        reset = await client.put(f"{ROOT}/configuration", headers=admin, json={})
        assert reset.status_code == 200 and not reset.json()["meal"]["available"]
        deleted = await client.delete(f"/api/system/model-providers/{provider_id}", headers=admin)
        assert deleted.status_code == 200


@pytest.mark.parametrize("change", ["disabled", "credentials", "endpoint", "type"])
async def test_queued_worker_rejects_stale_projection_after_database_change(isolated_meal, change):
    """实际 worker 从 ARQ 接收旧审批快照；PG 撤销与任务提交同事务避免竞态。"""
    client, users, configuration, spec = isolated_meal
    headers, admin = users[0]["headers"], users[2]["headers"]
    member = await create_member(client, headers)
    image = io.BytesIO()
    Image.new("RGB", (512, 512), (44, 180, 91)).save(image, "PNG")
    uploaded = await client.post(
        f"{ROOT}/uploads",
        headers=headers,
        data={"member_id": member, "purpose": "meal"},
        files={"file": ("synthetic-revoked.png", image.getvalue(), "image/png")},
    )
    assert uploaded.status_code == 201
    consent = await client.post(
        f"{ROOT}/members/{member}/processing-consents",
        headers=headers,
        json={
            "purpose": "meal",
            "accepted": True,
            "processor": configuration["meal"]["processor"],
            "policy_version": configuration["policy_version"],
        },
    )
    assert consent.status_code == 200
    model_cache.refresh()
    old_info = model_cache.get_model_info(spec)
    assert old_info is not None and old_info.api_key
    job_id = str(uuid4())
    async with httpx.AsyncClient(base_url="http://localhost:8767") as replay:
        before = (await replay.get("/observations")).json()["calls"]
        async with pg_manager.get_async_session_context() as session:
            provider = await session.scalar(
                select(ModelProvider).where(ModelProvider.provider_id == old_info.provider_id)
            )
            if change == "disabled":
                provider.is_enabled = False
            elif change == "credentials":
                provider.api_key = ""
            elif change == "endpoint":
                provider.base_url = "https://changed.example.invalid/v1"
            else:
                provider.enabled_models = [{"id": MODEL, "type": "embedding"}]
            task = await tasker.create_in_session(
                session,
                name="合成排队撤销测试",
                task_type="meal_recognize_v1",
                payload={"job_id": job_id},
                timeout_seconds=60,
            )
            session.add(
                VisionJob(
                    id=job_id,
                    task_id=task.id,
                    member_id=member,
                    actor_uid=users[0]["uid"],
                    kind="meal",
                    request_id=str(uuid4()),
                    fingerprint="0" * 64,
                    upload_ids=[uploaded.json()["upload_id"]],
                    input_snapshot={
                        "model": spec,
                        "processor": configuration["meal"]["processor"],
                        "policy_version": configuration["policy_version"],
                        "prompt_version": "health-vision-v1",
                        "meal_type": "lunch",
                        "eaten_at": "2026-10-04T12:00:00+08:00",
                    },
                )
            )
        await tasker.publish(task)

        async def state():
            """HTTP 读取 shipping worker 的持久终态。"""
            response = await client.get(f"{ROOT}/vision-tasks/{task.id}", headers=headers)
            assert response.status_code == 200
            return response.json()

        result = await wait_until(
            state,
            lambda value: (
                value["execution_status"] in {"success", "cancelled"}
                or (value["execution_status"] == "failed" and value["error_code"] is not None)
            ),
        )
        assert result["execution_status"] == "failed" and result["error_code"] == "policy_changed", result
        assert result["result_id"] is None
        assert (await replay.get("/observations")).json()["calls"] == before
    model_cache.refresh()
    assert model_cache.get_model_info(spec) == old_info
    current = await client.get(f"{ROOT}/configuration", headers=admin)
    assert current.status_code == 200 and not current.json()["meal"]["available"]
    rejected = await client.put(
        f"{ROOT}/configuration",
        headers=admin,
        json={
            "meal_model": spec,
            "policy_version": "synthetic-new",
            "cloud_processing_reviewed": True,
        },
    )
    assert rejected.status_code == 422 and rejected.json()["code"] == "model_not_configured"
    async with pg_manager.get_async_session_context() as session:
        record = await session.get(TaskRecord, task.id)
        job = await session.get(VisionJob, job_id)
        assert record.status == "failed" and record.result is None
        assert record.worker_id is None and record.lease_expires_at is None
        assert job.phase == "validating" and job.error_code == "policy_changed" and job.result_id is None
        assert await session.scalar(select(VisionDraft).where(VisionDraft.member_id == member)) is None
        assert await session.scalar(select(DietLog).where(DietLog.member_id == member)) is None


async def test_multiview_meal_worker_correction_calculation_and_once_diary(isolated_meal):
    """多视角识别不重复计餐，纠错和改量后只能确认当前预览。"""
    client, users, configuration, spec = isolated_meal
    headers, admin = users[0]["headers"], users[2]["headers"]
    member = await create_member(client, headers)
    image = io.BytesIO()
    Image.new("RGB", (512, 512), (44, 180, 91)).save(image, "PNG")
    image_bytes = image.getvalue()
    uploads, processed_digests = [], []
    for _ in range(2):
        uploaded = await client.post(
            f"{ROOT}/uploads",
            headers=headers,
            data={"member_id": member, "purpose": "meal"},
            files={"file": ("synthetic-meal.png", image_bytes, "image/png")},
        )
        assert uploaded.status_code == 201, uploaded.text
        upload_id = uploaded.json()["upload_id"]
        uploads.append(upload_id)
        preview = await client.get(f"{ROOT}/uploads/{upload_id}/preview?page_index=0", headers=headers)
        assert preview.status_code == 200 and preview.headers["cache-control"] == "private, no-store"
        processed_digests.append(hashlib.sha256(preview.content).hexdigest())
    request = {
        "member_id": member,
        "upload_ids": uploads,
        "client_request_id": str(uuid4()),
        "meal_type": "lunch",
        "eaten_at": "2026-10-04T12:00:00+08:00",
    }
    request_headers = {**headers, "Idempotency-Key": request["client_request_id"]}
    async with httpx.AsyncClient(base_url="http://localhost:8767") as replay:
        before = (await replay.get("/observations")).json()["calls"]
        denied = await client.post(f"{ROOT}/meal-photo-tasks", headers=request_headers, json=request)
        assert denied.status_code == 403 and denied.json()["code"] == "consent_required", denied.text
        async with pg_manager.get_async_session_context() as session:
            assert await session.scalar(select(VisionJob).where(VisionJob.member_id == member)) is None
        assert (await replay.get("/observations")).json()["calls"] == before
        consent = await client.post(
            f"{ROOT}/members/{member}/processing-consents",
            headers=headers,
            json={
                "purpose": "meal",
                "accepted": True,
                "processor": configuration["meal"]["processor"],
                "policy_version": configuration["policy_version"],
            },
        )
        assert consent.status_code == 200
        created = await client.post(f"{ROOT}/meal-photo-tasks", headers=request_headers, json=request)
        assert created.status_code == 202, created.text
        task_id = created.json()["task_id"]
        duplicate = await client.post(f"{ROOT}/meal-photo-tasks", headers=request_headers, json=request)
        assert duplicate.status_code == 202 and duplicate.json()["task_id"] == task_id

        async def state():
            """轮询正式健康接口，而不是调用测试进程的执行器。"""
            response = await client.get(f"{ROOT}/vision-tasks/{task_id}", headers=headers)
            assert response.status_code == 200
            return response.json()

        finished = await wait_until(
            state, lambda value: value["execution_status"] in {"success", "failed", "cancelled"}
        )
        assert finished["execution_status"] == "success" and finished["review_status"] == "pending_confirmation", (
            finished
        )
        assert (await replay.get("/observations")).json()["calls"] == [*before, processed_digests]
    draft_id = finished["result_id"]
    path = f"{ROOT}/meal-drafts/{draft_id}"
    draft_response = await client.get(path, headers=headers)
    assert draft_response.status_code == 200
    draft = draft_response.json()
    meal = draft["payload"]
    assert len(meal["items"]) == 1 and meal["items"][0]["name"] == "合成米饭"
    assert meal["items"][0]["grams"] is None and meal["items"][0]["food_id"] is None
    expected_photos = [
        {"image_index": index, "upload_id": upload_id, "upload_page_index": 0}
        for index, upload_id in enumerate(uploads)
    ]
    expected_locations = [{"image_index": 0, "bbox": [0.1, 0.2, 0.8, 0.9]}]
    assert meal["photos"] == expected_photos
    assert meal["items"][0]["visible_ingredients"] == ["合成米粒"]
    assert meal["items"][0]["locations"] == expected_locations
    for change in ("upload", "location", "new_item"):
        tampered = deepcopy(meal)
        if change == "upload":
            tampered["photos"][0]["upload_id"] = str(uuid4())
        elif change == "location":
            tampered["items"][0]["locations"][0]["bbox"] = [0.2, 0.2, 0.8, 0.9]
        else:
            tampered["items"].append({**deepcopy(tampered["items"][0]), "item_id": str(uuid4())})
        rejected = await client.patch(
            path,
            headers={**headers, "If-Match": '"1"'},
            json={"version": 1, "reason": "合成来源篡改负控", "meal": tampered},
        )
        assert rejected.status_code == 422 and rejected.json()["code"] == "evidence_invalid"
        assert (await client.get(path, headers=headers)).json()["payload"] == meal
    manual = await client.post(
        f"{ROOT}/manual-drafts", headers=headers, json={"member_id": member, "kind": "meal", "meal": meal}
    )
    assert manual.status_code == 422 and manual.json()["code"] == "manual_evidence_invalid"
    assert (await client.get(f"{ROOT}/members/{member}/diet-logs", headers=headers)).json() == []
    incomplete = await client.post(f"{path}/calculate", headers=headers, json={"version": 1})
    assert incomplete.status_code == 200 and not incomplete.json()["complete"]
    async with pg_manager.get_async_session_context() as session:
        job = await session.scalar(select(VisionJob).where(VisionJob.task_id == task_id))
        task = await session.get(TaskRecord, task_id)
        stored = await session.get(VisionDraft, draft_id)
        assert task.type == "meal_recognize_v1" and task.handler_version == 1 and task.attempt_count == 1
        assert task.status == "success" and task.worker_id is None and task.lease_expires_at is None
        assert task.started_at and task.completed_at and task.result["result_id"] == draft_id
        assert job.result_id == draft_id and job.input_snapshot["model"] == spec and job.upload_ids == uploads
        assert job.input_snapshot["prompt_version"] == "health-meal-v2"
        assert stored.payload == meal and stored.original_payload == meal
        assert stored.model_version == MODEL and stored.parser_version is None
        raw_key = stored.raw_result_key
        for upload_id in uploads:
            upload = await session.get(PrivateUpload, upload_id)
            assert upload.member_id == member and upload.sha256 == hashlib.sha256(image_bytes).hexdigest()
    raw = json.loads(await get_minio_client().adownload_file(PRIVATE_BUCKET, raw_key))
    assert raw["metadata"]["model"] == MODEL and raw["metadata"]["usage"]["total_tokens"] == 12
    assert len(raw["items"]) == 1 and raw["items"][0]["grams"] is None
    assert raw["items"][0]["locations"] == expected_locations
    food = await client.post(
        f"{ROOT}/foods",
        headers=admin,
        json={
            "record_code": str(uuid4()),
            "name": "合成米饭",
            "cooking_state": "熟",
            "source": "独立手算常量",
            "license": "仅合成测试",
            "edition": "synthetic",
            "dataset_version": "meal-e2e-v1",
            "nutrients": {
                "energy_kcal": "130",
                "protein_g": "2.6",
                "fat_g": "0.3",
                "carbohydrate_g": "28",
                "sodium_mg": "2",
            },
        },
    )
    assert food.status_code == 201
    item = meal["items"][0]
    item.update(
        food_id=food.json()["id"],
        grams="200",
        share_ratio="0.25",
        portion_source="weighed",
        visible_ingredients=["人工核实合成米粒"],
    )
    corrected = await client.patch(
        path,
        headers={**headers, "If-Match": '"1"'},
        json={"version": 1, "reason": "合成称重并确认个人食用比例", "meal": meal},
    )
    assert corrected.status_code == 200 and corrected.json()["version"] == 2
    old = await client.post(f"{path}/calculate", headers=headers, json={"version": 2})
    assert old.status_code == 200
    assert old.json()["totals"] == {
        "energy_kcal": "65.00",
        "protein_g": "1.30",
        "fat_g": "0.15",
        "carbohydrate_g": "14.00",
        "sodium_mg": "1.00",
    }
    item["grams"] = "240"
    changed = await client.patch(
        path,
        headers={**headers, "If-Match": '"2"'},
        json={"version": 2, "reason": "合成改量使旧预览失效", "meal": meal},
    )
    assert changed.status_code == 200 and changed.json()["version"] == 3
    data, key = confirmation(3, calculation_id=old.json()["calculation_id"])
    assert (await client.post(f"{path}/confirm", headers={**headers, **key}, json=data)).status_code == 409
    latest = await client.post(f"{path}/calculate", headers=headers, json={"version": 3})
    assert latest.status_code == 200 and latest.json()["complete"] and not latest.json()["estimated"]
    expected = {
        "energy_kcal": "78.00",
        "protein_g": "1.56",
        "fat_g": "0.18",
        "carbohydrate_g": "16.80",
        "sodium_mg": "1.20",
    }
    assert latest.json()["totals"] == expected
    data, key = confirmation(3, calculation_id=latest.json()["calculation_id"])
    responses = await asyncio.gather(
        *[client.post(f"{path}/confirm", headers={**headers, **key}, json=data) for _ in range(3)]
    )
    assert all(response.status_code == 200 for response in responses)
    assert all(response.json() == responses[0].json() for response in responses)
    diary_id = responses[0].json()["target_ids"][0]
    async with pg_manager.get_async_session_context() as session:
        diary = await session.get(DietLog, diary_id)
        calculation = await session.get(NutritionCalculation, latest.json()["calculation_id"])
        assert diary.member_id == member and diary.snapshot["nutrition"]["totals"] == expected
        assert diary.snapshot["meal"]["photos"] == expected_photos
        assert diary.snapshot["meal"]["items"][0]["locations"] == expected_locations
        assert diary.snapshot["meal"]["items"][0]["visible_ingredients"] == ["人工核实合成米粒"]
        assert calculation.draft_version == 3 and calculation.result["totals"] == expected
        assert diary.snapshot["nutrition"]["sources"][0]["dataset_version"] == "meal-e2e-v1"
    reloaded = await client.get(f"{ROOT}/members/{member}/diet-logs", headers=headers)
    assert reloaded.status_code == 200 and len(reloaded.json()) == 1
    assert reloaded.json()[0]["id"] == diary_id and reloaded.json()[0]["snapshot"]["nutrition"]["totals"] == expected
    for actor in users[1:]:
        assert (await client.get(path, headers=actor["headers"])).status_code == 404
        assert (await client.get(f"{ROOT}/members/{member}/diet-logs", headers=actor["headers"])).status_code == 404


async def drain_meal_tasks(client, users):
    """任何断言失败后也取消本轮私有任务，并回读终态才清理。"""
    for actor in users:
        async with pg_manager.get_async_session_context() as session:
            rows = list(
                (
                    await session.scalars(
                        select(TaskRecord)
                        .join(VisionJob, VisionJob.task_id == TaskRecord.id)
                        .where(VisionJob.actor_uid == actor["uid"], TaskRecord.status.in_(["pending", "running"]))
                    )
                ).all()
            )
        for task in rows:
            response = await client.post(f"{ROOT}/vision-tasks/{task.id}/cancel", headers=actor["headers"])
            assert response.status_code == 200

    async def settled():
        """Task owner 和 lease 只以当前 PG 事实判断。"""
        async with pg_manager.get_async_session_context() as session:
            rows = list(
                (
                    await session.scalars(
                        select(TaskRecord)
                        .join(VisionJob, VisionJob.task_id == TaskRecord.id)
                        .where(VisionJob.actor_uid.in_([actor["uid"] for actor in users]))
                    )
                ).all()
            )
            return all(
                task.status in {"success", "failed", "cancelled"}
                and task.worker_id is None
                and task.lease_expires_at is None
                for task in rows
            )

    await wait_until(settled, bool)

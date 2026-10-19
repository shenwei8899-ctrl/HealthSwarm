"""正式 App 经真实 HTTP/PG/MinIO 验收；识别结果在队列边界使用合成替身。"""

# ruff: noqa: F811 -- pytest 注入隔离 fixture。
import asyncio
import json
import os
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from test.integration.services.test_health_meal_plan_pagination_http import (  # noqa: F401
    cleanup_test_sandboxes,
    cleanup_test_knowledge_resources,
    ensure_live_api_schema,
    meal_pagination_http,
)
from yuxi.services.health_vision_service import HealthVisionService, PRIVATE_BUCKET
from yuxi.services.health_vision_types import MealPayload
from yuxi.services.task_service import tasker
from yuxi.storage.minio import get_minio_client
from yuxi.storage.postgres.models_business import TaskRecord
from yuxi.storage.postgres.models_health import DietLog, HealthGrant, PrivateUpload, VisionDraft, VisionJob

pytestmark = [pytest.mark.integration, pytest.mark.asyncio,
              pytest.mark.skipif(not os.getenv("HEALTH_WORKFLOW_UI_CONTROL"), reason="需要浏览器控制目录")]


async def test_app_photo_upload_review_confirm(meal_pagination_http, monkeypatch):
    """页面负责上传和核对，独立会话核验正式记录及私有来源。"""
    c = meal_pagination_http
    control = Path(os.environ["HEALTH_WORKFLOW_UI_CONTROL"])
    control.mkdir(parents=True, exist_ok=True)
    assert not (control / "ready.json").exists()
    root = "/api/health/v1"
    async with c.sessions() as session:
        grant = await session.get(HealthGrant, (c.member, "owner"))
        grant.scopes = [*grant.scopes, "ai_use"]
        await session.commit()

    async def configuration(self, session=None):
        """测试配置仅存在 fixture 内，不写入业务配置或发起模型调用。"""
        available = not (control / "disabled").exists()
        return {"policy_version": "synthetic-test-only", "meal": {
            "available": available, "reason": "" if available else "模型和政策暂未配置",
            "model": "synthetic", "processor": "synthetic-test-only"},
            "limits": {"image_mb": 10, "meal_images": 3}}

    async def synthetic_result(task):
        """队列出口替身，仅构造候选；不替代上传、授权、确认或计算服务。"""
        async with c.sessions() as session:
            job = await session.scalar(select(VisionJob).where(VisionJob.task_id == task.id))
            upload = await session.get(PrivateUpload, job.upload_ids[0])
            data = await get_minio_client().adownload_file(PRIVATE_BUCKET, upload.original_key)
            assert data.startswith(b"\x89PNG")
            payload = MealPayload.model_validate({
                "meal_type": job.input_snapshot["meal_type"], "eaten_at": job.input_snapshot["eaten_at"],
                "photos": [{"image_index": 0, "upload_id": upload.id, "upload_page_index": 0}],
                "items": [{"item_id": str(uuid4()), "name": "合成米饭", "grams": None,
                           "share_ratio": None, "locations": [], "uncertainties": ["需核对实际份量"]}],
            }).model_dump(mode="json")
            draft = VisionDraft(id=str(uuid4()), job_id=job.id, member_id=job.member_id, kind="meal",
                                version=1, review_status="pending_confirmation", payload=payload,
                                original_payload=payload, parser_version="test", model_version="synthetic")
            session.add(draft)
            job.result_id = draft.id
            job.phase = "ready"
            record = await session.get(TaskRecord, task.id)
            record.status = "success"
            record.progress = 100
            await session.commit()

    monkeypatch.setattr(HealthVisionService, "configuration", configuration)
    monkeypatch.setattr(tasker, "publish", synthetic_result)
    food = await c.client.post(root + "/foods", headers=c.identities["admin"], json={
        "record_code": str(uuid4()), "name": "合成米饭", "cooking_state": "熟", "source": "合成测试",
        "license": "仅测试", "edition": "1", "dataset_version": "1",
        "nutrients": {"energy_kcal": "200", "protein_g": "10", "fat_g": "5",
                      "carbohydrate_g": "25", "sodium_mg": None}})
    assert food.status_code == 201, food.text
    (control / "ready.json").write_text(json.dumps({"member": c.member, "owner": c.identities["owner"]}), encoding="utf-8")
    for _ in range(900):
        if (control / "done.json").exists():
            break
        assert not (control / "failed.json").exists(), "浏览器操作失败"
        await asyncio.sleep(1)
    assert (control / "done.json").exists(), "浏览器未交付回执"
    async with c.sessions() as session:
        assert await session.scalar(select(func.count()).select_from(DietLog)) == 1
        record = await session.scalar(select(DietLog))
        assert record.snapshot["nutrition"]["totals"]["energy_kcal"] == "120.00"
        assert record.snapshot["nutrition"]["totals"]["sodium_mg"] is None
        draft = await session.scalar(select(VisionDraft))
        assert draft.version == 2 and draft.review_status == "confirmed"
        assert record.snapshot["meal"]["photos"] == draft.original_payload["photos"]
        assert await session.scalar(select(func.count()).select_from(PrivateUpload)) == 1
    (control / "verified.json").write_text(json.dumps({"real_http_pg_minio": True,
        "diet_logs": 1, "energy_kcal": "120.00", "unknown_sodium": True,
        "draft_version": 2, "provider_and_queue": "synthetic_result", "real_model_worker_tested": False}), encoding="utf-8")

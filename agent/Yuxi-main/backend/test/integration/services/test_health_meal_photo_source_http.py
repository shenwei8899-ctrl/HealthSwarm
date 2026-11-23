"""真实 HTTP 和隔离 PostgreSQL 验证来源任务、幂等重放和发布顺序。"""

from datetime import datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy import select

from test.integration.services.test_health_family_profile_http import family_profile_http, linked_self  # noqa: F401
from yuxi.services import health_meal_photo_source as source_module, health_vision_service as service_module
from yuxi.services.health_nutrition_service import input_fingerprint
from yuxi.storage.postgres.models_business import TaskRecord
from yuxi.storage.postgres.models_health import HealthProcessingConsent, PrivateUpload, VisionJob

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.fixture(scope="session", autouse=True)
def cleanup_test_sandboxes():
    """本文件只使用 fixture 自己的隔离 schema。"""
    yield


@pytest.fixture(scope="session", autouse=True)
def cleanup_test_knowledge_resources():
    """不创建知识库资源。"""
    yield


@pytest.fixture(scope="session", autouse=True)
def ensure_live_api_schema():
    """HTTP fixture 在本进程启动真实 TCP 服务。"""


async def test_source_snapshot_replay_rejection_retry_and_legacy_fingerprint(family_profile_http, monkeypatch):  # noqa: F811
    """来源只冻结服务端菜名，重放不重读新餐单，旧请求指纹保持兼容。"""
    client, sessions, identities = family_profile_http
    headers = identities["self"]
    member, linked = await linked_self(client, headers)
    config = {
        "policy_version": "synthetic-source",
        "meal": {"available": True, "model": "synthetic", "processor": "synthetic-source"},
        "report": {"available": True, "model": "synthetic", "processor": "synthetic-source"},
    }
    from server.routers.health_vision_router import service

    monkeypatch.setattr(service, "configuration", AsyncMock(return_value=config))
    published = []

    async def publish(task):
        """另一个会话必须已经能读取到任务，才允许投递。"""
        async with sessions() as session:
            assert await session.get(TaskRecord, task.id) is not None
            published.append(task.id)

    monkeypatch.setattr(service_module.tasker, "publish", publish)
    upload_id = str(uuid4())
    async with sessions() as session:
        session.add(
            PrivateUpload(
                id=upload_id,
                actor_uid="self",
                member_id=member,
                purpose="meal",
                original_key="synthetic/original",
                sha256="0" * 64,
                mime="image/png",
                byte_size=100,
                pages=[{"page_index": 0, "object_key": "synthetic/page", "width": 100, "height": 100}],
            )
        )
        session.add(
            HealthProcessingConsent(
                member_id=member,
                actor_uid="self",
                purpose="meal",
                processor="synthetic-source",
                policy_version="synthetic-source",
            )
        )
        await session.commit()
    source = {
        "family_id": linked["family_id"],
        "plan_date": "2026-11-21",
        "plan_version": 3,
        "meal_type": "dinner",
        "dish_key": "potato",
    }
    request = {
        "member_id": member,
        "upload_ids": [upload_id],
        "client_request_id": str(uuid4()),
        "meal_type": "lunch",
        "eaten_at": "2026-11-22T12:30:00+08:00",
        "source_context": source,
    }

    async def post(body, endpoint="meal-photo-tasks"):
        """以正式认证和幂等请求头穿过 HTTP 模型及事务。"""
        return await client.post(
            "/api/health/v1/" + endpoint, headers={**headers, "Idempotency-Key": body["client_request_id"]}, json=body
        )

    # 真实空餐单不能被客户端名称或来源证明冒充。
    absent = await post(request)
    assert absent.status_code == 409, absent.text
    plan = {
        "version": 3,
        "needs_regeneration": [],
        "meals": [
            {
                "meal_type": "dinner",
                "meal": {"dishes": [{"dish_key": "potato", "name": "服务端土豆蒸菜", "grams": 500}]},
            }
        ],
    }
    read = AsyncMock(return_value=plan)
    monkeypatch.setattr(source_module, "read_current_plan", read)
    response = await post(request)
    assert response.status_code == 202, response.text
    task_id = response.json()["task_id"]
    assert published == [task_id]
    plan["version"] = 4
    replay = await post(request)
    assert replay.status_code == 202 and replay.json()["task_id"] == task_id
    assert read.await_count == 1
    changed = await post({**request, "source_context": {**source, "dish_key": "other"}})
    assert changed.status_code == 409
    stale = await post({**request, "client_request_id": str(uuid4())})
    assert stale.status_code == 409
    cross_family = await post(
        {**request, "client_request_id": str(uuid4()), "source_context": {**source, "family_id": str(uuid4())}}
    )
    assert cross_family.status_code == 403
    report = await post({**request, "client_request_id": str(uuid4())}, "report-tasks")
    assert report.status_code == 422
    async with sessions() as session:
        job = await session.scalar(select(VisionJob).where(VisionJob.task_id == task_id))
        assert job.input_snapshot["source_hint"] == {"version": 1, "dish_name": "服务端土豆蒸菜"}
        assert job.input_snapshot["meal_type"] == "lunch"
        assert job.input_snapshot["source_context"]["meal_type"] == "dinner"
        (await session.get(TaskRecord, task_id)).status = "failed"
        await session.commit()
    plan["version"] = 3
    retry_id = str(uuid4())
    retry = await client.post(
        f"/api/health/v1/vision-tasks/{task_id}/retry",
        headers={**headers, "Idempotency-Key": retry_id},
        json={"client_request_id": retry_id},
    )
    assert retry.status_code == 202, retry.text
    legacy = {k: v for k, v in request.items() if k != "source_context"}
    legacy["client_request_id"] = str(uuid4())
    # 终止待投递任务，避免本测试的并发任务额度影响兼容验证。
    async with sessions() as session:
        for task in (await session.scalars(select(TaskRecord))).all():
            task.status = "failed"
        await session.commit()
    response = await post(legacy)
    assert response.status_code == 202, response.text
    fingerprint_payload = {**legacy, "eaten_at": datetime.fromisoformat(legacy["eaten_at"]).isoformat()}
    async with sessions() as session:
        job = await session.scalar(select(VisionJob).where(VisionJob.task_id == response.json()["task_id"]))
        assert job.fingerprint == input_fingerprint(fingerprint_payload)
        assert "source_hint" not in job.input_snapshot

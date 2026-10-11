"""复用隔离PG/TCP fixture验证正式饮食分页；合成快照不代表计算验收。"""

# ruff: noqa: F811 -- pytest按名称注入本模块导入的真实HTTP fixture。

from datetime import datetime
import hashlib
import json
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from test.integration.services.test_health_meal_plan_pagination_http import (  # noqa: F401
    cleanup_test_knowledge_resources,
    cleanup_test_sandboxes,
    ensure_live_api_schema,
    meal_pagination_http,
    revoke_grant,
    schema_facts,
)
from yuxi.storage.postgres.models_business import TaskRecord
from yuxi.storage.postgres.models_health import (
    DietLog,
    NutritionCalculation,
    PrivateUpload,
    VisionConfirmation,
    VisionDraft,
    VisionJob,
)

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_all_pages_preserve_order_versions_and_old_array_without_writes(meal_pagination_http):
    """121条真实持久化事实跨越旧100条限制，等时ID顺序独立定义。"""
    current = meal_pagination_http
    await seed_diet_logs(current)
    collected = []
    offset = 0
    while True:
        response = await diet_page(current, params={"limit": 20, "offset": offset})
        assert response.status_code == 200, response.text
        payload = response.json()
        assert [r["id"] for r in payload["records"]] == current.diet_ids[offset : offset + 20]
        assert all(r["source_version"] == 3 and r["created_at"].endswith("Z") for r in payload["records"])
        collected.extend(r["id"] for r in payload["records"])
        expected_next = offset + 20 if offset + 20 < 121 else None
        assert payload["next_offset"] == expected_next
        if expected_next is None:
            break
        offset = expected_next
    assert collected == current.diet_ids and len(set(collected)) == 121
    legacy = await diet_page(current, legacy=True)
    assert isinstance(legacy.json(), list)
    assert [r["id"] for r in legacy.json()] == current.diet_ids[:100]
    empty = await diet_page(current, params={"limit": 50, "offset": 121})
    assert empty.json() == {"records": [], "next_offset": None}
    default = await diet_page(current)
    explicit = await diet_page(current, params={"limit": 20, "offset": 0})
    assert default.json() == explicit.json()
    for params in (
        {"limit": 0},
        {"limit": 51},
        {"limit": "1.5"},
        {"offset": -1},
        {"offset": 2147483648},
        {"offset": "x"},
    ):
        rejected = await diet_page(current, params=params)
        assert rejected.status_code == 422
        assert rejected.json()["detail"][0]["loc"] == ["query", next(iter(params))]
    spec = (await current.client.get("/openapi.json")).json()
    assert spec["paths"]["/api/health/v1/members/{member_id}/diet-logs/page"]["get"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"]["$ref"].endswith("/DietLogPage")


async def test_every_page_rechecks_current_grant_and_member_scope(meal_pagination_http):
    """授权账号可读成员事实，管理员无旁路；后续页撤权即404。"""
    current = meal_pagination_http
    await seed_diet_logs(current)
    own = await diet_page(current)
    other_authorized = await diet_page(current, actor="other")
    assert other_authorized.json() == own.json()
    foreign = await diet_page(current, member=current.foreign_member)
    assert foreign.status_code == 404 and foreign.json()["code"] == "not_found"
    await revoke_grant(current, current.member, "admin")
    admin = await diet_page(current, actor="admin")
    assert admin.status_code == 404 and admin.json()["code"] == "not_found"
    await revoke_grant(current, current.member, "owner")
    for offset in (0, 20, 120):
        rejected = await diet_page(current, params={"offset": offset})
        assert rejected.status_code == 404 and rejected.json()["code"] == "not_found"


async def test_deleted_picture_hides_record_but_empty_page_keeps_next_offset(meal_pagination_http):
    """实际源元数据先有效后删除；空中间页不会使后续有效记录不可达。"""
    current = meal_pagination_http
    await seed_diet_logs(current)
    upload_id, job_id, task_id = str(uuid4()), str(uuid4()), uuid4().hex
    async with current.sessions() as session:
        session.add(TaskRecord(id=task_id, name="合成已完成识图", type="meal_recognize_v1", status="success"))
        session.add(
            PrivateUpload(
                id=upload_id,
                actor_uid="owner",
                member_id=current.member,
                purpose="meal",
                original_key=uuid4().hex,
                sha256="a" * 64,
                mime="image/png",
                byte_size=1,
                pages=[],
                status="active",
            )
        )
        await session.flush()
        session.add(
            VisionJob(
                id=job_id,
                task_id=task_id,
                actor_uid="owner",
                member_id=current.member,
                kind="meal",
                request_id=str(uuid4()),
                fingerprint="b" * 64,
                upload_ids=[upload_id],
                input_snapshot={},
            )
        )
        await session.flush()
        record = await session.get(DietLog, current.diet_ids[20])
        confirmation = await session.get(VisionConfirmation, record.confirmation_id)
        draft = await session.get(VisionDraft, confirmation.draft_id)
        draft.job_id = job_id
        await session.commit()
    before = await diet_page(current, params={"limit": 1, "offset": 20})
    assert [r["id"] for r in before.json()["records"]] == current.diet_ids[20:21]
    async with current.sessions() as session:
        upload = await session.get(PrivateUpload, upload_id)
        upload.status = "deleted"
        await session.commit()
    after = await diet_page(current, params={"limit": 1, "offset": 20})
    assert after.json() == {"records": [], "next_offset": 21}
    next_page = await diet_page(current, params={"limit": 1, "offset": after.json()["next_offset"]})
    assert [r["id"] for r in next_page.json()["records"]] == current.diet_ids[21:22]


async def seed_diet_logs(current):
    """反序插入合成查询事实，预先定义时间与ID顺序。"""
    current.diet_ids = [str(UUID(int=n)) for n in [*range(3000, 3020), *range(1000, 1101)]]
    async with current.sessions() as session:
        for index in reversed(range(121)):
            draft_id, calc_id, confirmation_id = (str(uuid4()) for _ in range(3))
            payload = {"meal_type": "lunch", "eaten_at": "2026-10-10T12:00:00+08:00", "items": [], "source": "manual"}
            nutrition = {
                "totals": {
                    "energy_kcal": "100",
                    "protein_g": "5",
                    "fat_g": None,
                    "carbohydrate_g": "10",
                    "sodium_mg": None,
                },
                "calculation_version": "synthetic-pagination",
                "complete": False,
                "estimated": False,
            }
            session.add(
                VisionDraft(
                    id=draft_id,
                    member_id=current.member,
                    kind="meal",
                    version=3,
                    review_status="confirmed",
                    original_payload=payload,
                    payload=payload,
                )
            )
            await session.flush()
            session.add(
                NutritionCalculation(
                    id=calc_id,
                    draft_id=draft_id,
                    draft_version=3,
                    input_hash="c" * 64,
                    input_snapshot=payload,
                    result=nutrition,
                    calculation_version="synthetic-pagination",
                )
            )
            session.add(
                VisionConfirmation(
                    id=confirmation_id,
                    draft_id=draft_id,
                    draft_version=3,
                    actor_uid="owner",
                    member_id=current.member,
                    kind="meal",
                    request_id=str(uuid4()),
                    fingerprint="d" * 64,
                    target_ids=[current.diet_ids[index]],
                )
            )
            await session.flush()
            session.add(
                DietLog(
                    id=current.diet_ids[index],
                    member_id=current.member,
                    confirmation_id=confirmation_id,
                    calculation_id=calc_id,
                    snapshot={"meal": payload, "nutrition": nutrition},
                    created_at=datetime(2026, 10, 10 if index < 20 else 9, 10),
                )
            )
        await session.commit()
    async with current.sessions() as session:
        persisted = (
            await session.scalars(select(DietLog.id).order_by(DietLog.created_at.desc(), DietLog.id.asc()))
        ).all()
        assert persisted == current.diet_ids
    current.evidence["diet_ids"] = current.diet_ids


async def diet_page(current, *, actor="owner", member=None, params=None, legacy=False):
    """TCP读取前后核对所有表及xmin，不以200替代只读事实。"""
    before = await schema_facts(current.sessions)
    path = f"/api/health/v1/members/{member or current.member}/diet-logs" + ("" if legacy else "/page")
    response = await current.client.get(path, headers=current.identities[actor], params=params)
    after = await schema_facts(current.sessions)
    current.evidence["requests"].append(
        {
            "path": path,
            "actor": actor,
            "params": params or {},
            "status": response.status_code,
            "response": response.json(),
            "all_rows_and_xmin_unchanged": before == after,
            "pg_before_sha256": hashlib.sha256(json.dumps(before, sort_keys=True).encode()).hexdigest(),
            "pg_after_sha256": hashlib.sha256(json.dumps(after, sort_keys=True).encode()).hexdigest(),
        }
    )
    assert before == after, "分页读取不得更新业务、授权、任务或Agent运行事实"
    if not legacy and response.status_code in (200, 404):
        assert response.headers["cache-control"] == "no-store"
    return response

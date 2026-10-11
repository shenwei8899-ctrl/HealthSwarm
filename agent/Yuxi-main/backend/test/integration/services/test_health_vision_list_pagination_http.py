"""隔离PG及真实TCP验证识图分页；人工查询快照不调用模型或对象存储。"""

# ruff: noqa: F811 -- pytest按名称注入本模块导入的真实HTTP fixture。

from datetime import datetime
import hashlib
import json
from uuid import UUID, uuid4

import pytest

from test.integration.services.test_health_meal_plan_pagination_http import (  # noqa: F401
    cleanup_test_knowledge_resources,
    cleanup_test_sandboxes,
    ensure_live_api_schema,
    meal_pagination_http,
    revoke_grant,
    schema_facts,
)
from yuxi.storage.postgres.models_business import TaskRecord
from yuxi.storage.postgres.models_health import HealthGrant, PrivateUpload, VisionDraft, VisionJob

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]
ROOT = "/api/health/v1"


@pytest.mark.parametrize("kind", ["report", "meal"])
async def test_every_kind_reads_beyond_fifty_in_stable_order_without_writes(meal_pagination_http, kind):
    """两种用途独立跨越旧50条限制，同时间顺序由预定义ID证明。"""
    current = meal_pagination_http
    await seed_vision_facts(current)
    expected = current.vision_ids[kind]
    default = await vision_page(current, params={"kind": kind})
    explicit = await vision_page(
        current, params={"kind": kind, "jobs_limit": 20, "drafts_limit": 20, "jobs_offset": 0, "drafts_offset": 0}
    )
    assert default.json() == explicit.json()
    collected_jobs, collected_drafts = [], []
    jobs_offset = drafts_offset = 0
    while True:
        response = await vision_page(
            current, params={"kind": kind, "jobs_offset": jobs_offset, "drafts_offset": drafts_offset}
        )
        assert_vision_page(response, expected, jobs_offset=jobs_offset, drafts_offset=drafts_offset)
        payload = response.json()
        assert all(row["kind"] == kind and row["created_at"].endswith("Z") for row in payload["jobs"])
        assert all(row["kind"] == kind and row["created_at"].endswith("Z") for row in payload["drafts"])
        collected_jobs.extend(row["task_id"] for row in payload["jobs"])
        collected_drafts.extend(row["id"] for row in payload["drafts"])
        if payload["jobs_next_offset"] is None and payload["drafts_next_offset"] is None:
            break
        jobs_offset = payload["jobs_next_offset"] if payload["jobs_next_offset"] is not None else len(expected["jobs"])
        drafts_offset = (
            payload["drafts_next_offset"] if payload["drafts_next_offset"] is not None else len(expected["drafts"])
        )
    assert collected_jobs == expected["jobs"] and len(set(collected_jobs)) == len(expected["jobs"])
    assert collected_drafts == expected["drafts"] and len(set(collected_drafts)) == len(expected["drafts"])


@pytest.mark.parametrize("kind", ["report", "meal"])
async def test_job_and_draft_windows_advance_independently(meal_pagination_http, kind):
    """任务已到末页时，草稿仍按自己的偏移和页长推进。"""
    current = meal_pagination_http
    await seed_vision_facts(current)
    expected = current.vision_ids[kind]
    response = await vision_page(
        current, params={"kind": kind, "jobs_limit": 50, "drafts_limit": 7, "jobs_offset": 50, "drafts_offset": 14}
    )
    assert_vision_page(response, expected, jobs_limit=50, drafts_limit=7, jobs_offset=50, drafts_offset=14)
    assert response.json()["jobs_next_offset"] is None and response.json()["drafts_next_offset"] == 21
    response = await vision_page(
        current,
        params={"kind": kind, "jobs_limit": 1, "drafts_limit": 50, "jobs_offset": 0, "drafts_offset": 50},
    )
    assert_vision_page(response, expected, jobs_limit=1, drafts_limit=50, jobs_offset=0, drafts_offset=50)
    assert response.json()["jobs_next_offset"] == 1 and response.json()["drafts_next_offset"] is None


@pytest.mark.parametrize("kind", ["report", "meal"])
async def test_each_page_rechecks_purpose_and_current_grant_even_for_admin(meal_pagination_http, kind):
    """三个账号只能读取当前授权用途，管理员与成员拥有者同样受撤权限制。"""
    current = meal_pagination_http
    await seed_vision_facts(current)
    scope = "report_view" if kind == "report" else "diet_edit"
    opposite = "meal" if kind == "report" else "report"
    owner = await vision_page(current, params={"kind": kind})
    assert owner.status_code == 200
    for actor in ("owner", "other", "admin"):
        authorized = await vision_page(current, actor=actor, params={"kind": kind})
        assert authorized.json() == owner.json()
        await set_grant_scopes(current, current.member, actor, [scope])
        allowed = await vision_page(current, actor=actor, params={"kind": kind, "jobs_offset": 20, "drafts_offset": 20})
        assert_vision_page(allowed, current.vision_ids[kind], jobs_offset=20, drafts_offset=20)
        for offset in (0, 20, 2147483647):
            denied = await vision_page(
                current, actor=actor, params={"kind": opposite, "jobs_offset": offset, "drafts_offset": offset}
            )
            assert denied.status_code == 404 and denied.json()["code"] == "not_found"
        await revoke_grant(current, current.member, actor)
        for offset in (0, 20, 2147483647):
            denied = await vision_page(
                current, actor=actor, params={"kind": kind, "jobs_offset": offset, "drafts_offset": offset}
            )
            assert denied.status_code == 404 and denied.json()["code"] == "not_found"


async def test_empty_and_past_end_pages_authorize_before_returning_empty(meal_pagination_http):
    """空成员与最大合法偏移仍先授权，未知或他人成员不可借空结果绕过。"""
    current = meal_pagination_http
    await seed_vision_facts(current)
    empty = {"jobs": [], "drafts": [], "jobs_next_offset": None, "drafts_next_offset": None}
    for kind in ("report", "meal"):
        foreign = await vision_page(current, actor="other", member=current.foreign_member, params={"kind": kind})
        assert_vision_page(foreign, current.foreign_vision_ids[kind])
        assert foreign.json()["drafts"][0]["member_id"] == current.foreign_member
        for offset in (0, 2147483647):
            response = await vision_page(
                current,
                member=current.empty_member,
                params={"kind": kind, "jobs_offset": offset, "drafts_offset": offset},
            )
            assert response.status_code == 200 and response.json() == empty
        response = await vision_page(
            current, params={"kind": kind, "jobs_offset": 2147483647, "drafts_offset": 2147483647}
        )
        assert response.status_code == 200 and response.json() == empty
        for member in (str(uuid4()), current.foreign_member):
            for actor in ("owner", "admin"):
                response = await vision_page(
                    current,
                    actor=actor,
                    member=member,
                    params={"kind": kind, "jobs_offset": 2147483647, "drafts_offset": 2147483647},
                )
                assert response.status_code == 404 and response.json()["code"] == "not_found"
    await revoke_grant(current, current.empty_member, "owner")
    for kind in ("report", "meal"):
        response = await vision_page(current, member=current.empty_member, params={"kind": kind})
        assert response.status_code == 404 and response.json()["code"] == "not_found"


@pytest.mark.parametrize("kind", ["report", "meal"])
async def test_deleted_source_hides_job_and_draft_but_empty_pages_continue(meal_pagination_http, kind):
    """真实源元数据失效后按原始行推进两游标，无来源人工草稿继续可见。"""
    current = meal_pagination_http
    await seed_vision_facts(current)
    expected = current.vision_ids[kind]
    upload_id = str(uuid4())
    async with current.sessions() as session:
        session.add(
            PrivateUpload(
                id=upload_id,
                actor_uid="owner",
                member_id=current.member,
                purpose=kind,
                original_key=uuid4().hex,
                sha256="a" * 64,
                mime="image/png",
                byte_size=1,
                pages=[],
                status="active",
            )
        )
        job = await session.get(VisionJob, expected["job_ids"][20])
        job.upload_ids = [upload_id]
        draft = await session.get(VisionDraft, expected["drafts"][20])
        draft.job_id = job.id
        job.result_id = draft.id
        await session.commit()
    params = {"kind": kind, "jobs_limit": 1, "drafts_limit": 1, "jobs_offset": 20, "drafts_offset": 20}
    active = await vision_page(current, params=params)
    assert_vision_page(active, expected, jobs_limit=1, drafts_limit=1, jobs_offset=20, drafts_offset=20)
    async with current.sessions() as session:
        upload = await session.get(PrivateUpload, upload_id)
        upload.status = "deleted"
        await session.commit()
    deleted = await vision_page(current, params=params)
    assert deleted.status_code == 200
    assert deleted.json() == {"jobs": [], "drafts": [], "jobs_next_offset": 21, "drafts_next_offset": 21}
    continued = await vision_page(current, params={**params, "jobs_offset": 21, "drafts_offset": 21})
    assert_vision_page(continued, expected, jobs_limit=1, drafts_limit=1, jobs_offset=21, drafts_offset=21)
    assert continued.json()["drafts"][0]["payload"]["source"] == "manual"
    async with current.sessions() as session:
        draft = await session.get(VisionDraft, expected["drafts"][21])
        assert draft.job_id is None


async def test_legacy_vision_keeps_its_two_fifty_row_arrays(meal_pagination_http):
    """旧接口保留混合用途和两组50条数组，不增加分页字段。"""
    current = meal_pagination_http
    await seed_vision_facts(current)
    response = await vision_page(current, legacy=True)
    assert response.status_code == 200
    payload = response.json()
    assert set(payload) == {"jobs", "drafts"}
    assert len(payload["jobs"]) == len(payload["drafts"]) == 50
    tasks = {value for expected in current.vision_ids.values() for value in expected["jobs"]}
    drafts = {value for expected in current.vision_ids.values() for value in expected["drafts"]}
    assert {row["task_id"] for row in payload["jobs"]} <= tasks
    assert {row["id"] for row in payload["drafts"]} <= drafts
    assert {row["kind"] for row in payload["jobs"]} == {"report", "meal"}
    assert {row["kind"] for row in payload["drafts"]} == {"report", "meal"}


async def test_invalid_parameters_and_typed_openapi_match_public_contract(meal_pagination_http):
    """查询参数由HTTP边界拒绝，OpenAPI明确公开分页及记录结构。"""
    current = meal_pagination_http
    for params, invalid in (
        ({}, "kind"),
        ({"kind": "other"}, "kind"),
        ({"kind": ""}, "kind"),
        *(
            ({"kind": "meal", name: value}, name)
            for name in ("jobs_limit", "drafts_limit")
            for value in (0, 51, "1.5", "x")
        ),
        *(
            ({"kind": "meal", name: value}, name)
            for name in ("jobs_offset", "drafts_offset")
            for value in (-1, 2147483648, "1.5", "x")
        ),
    ):
        response = await vision_page(current, params=params)
        assert response.status_code == 422
        assert response.json()["detail"][0]["loc"] == ["query", invalid]
    before = await schema_facts(current.sessions)
    spec = (await current.client.get("/openapi.json")).json()
    assert before == await schema_facts(current.sessions)
    operation = spec["paths"][f"{ROOT}/members/{{member_id}}/vision/page"]["get"]
    parameters = {parameter["name"]: parameter for parameter in operation["parameters"]}
    assert parameters["kind"]["required"] is True
    assert parameters["kind"]["schema"]["enum"] == ["report", "meal"]
    for name in ("jobs_limit", "drafts_limit"):
        schema = parameters[name]["schema"]
        assert (schema["type"], schema["default"], schema["minimum"], schema["maximum"]) == ("integer", 20, 1, 50)
    for name in ("jobs_offset", "drafts_offset"):
        schema = parameters[name]["schema"]
        assert (schema["type"], schema["default"], schema["minimum"], schema["maximum"]) == (
            "integer",
            0,
            0,
            2147483647,
        )
    reference = operation["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
    page = spec["components"]["schemas"][reference.rsplit("/", 1)[-1]]
    assert set(page["properties"]) == {"jobs", "drafts", "jobs_next_offset", "drafts_next_offset"}
    for name, required in (("jobs", {"task_id", "kind", "execution_status"}), ("drafts", {"id", "kind", "payload"})):
        array = page["properties"][name]
        assert array["type"] == "array"
        item = spec["components"]["schemas"][array["items"]["$ref"].rsplit("/", 1)[-1]]
        assert item["type"] == "object" and required <= set(item["properties"])
    for name in ("jobs_next_offset", "drafts_next_offset"):
        assert {schema["type"] for schema in page["properties"][name]["anyOf"]} == {"integer", "null"}


async def seed_vision_facts(current):
    """反序写入两用途的独立查询事实，预定义时间和ID序列不使用被测查询。"""
    current.vision_ids = {}
    current.foreign_vision_ids = {}
    async with current.sessions() as session:
        for actor, member in (
            ("owner", current.member),
            ("other", current.member),
            ("admin", current.member),
            ("owner", current.empty_member),
            ("other", current.foreign_member),
        ):
            grant = await session.get(HealthGrant, (member, actor))
            grant.scopes = ["report_view", "diet_edit"]
        for kind, base, job_count, draft_count in (("report", 100000, 63, 65), ("meal", 200000, 67, 71)):
            job_numbers = [*range(base + 3000, base + 3020), *range(base + 1000, base + 1000 + job_count - 20)]
            draft_numbers = [*range(base + 7000, base + 7017), *range(base + 5000, base + 5000 + draft_count - 17)]
            expected = {
                "job_ids": [str(UUID(int=number)) for number in job_numbers],
                "jobs": [UUID(int=number + 1000000).hex for number in job_numbers],
                "drafts": [str(UUID(int=number)) for number in draft_numbers],
            }
            current.vision_ids[kind] = expected
            for index in reversed(range(job_count)):
                session.add(
                    TaskRecord(
                        id=expected["jobs"][index],
                        name="合成识图分页任务",
                        type=f"{kind}_synthetic_list",
                        status="success",
                    )
                )
            foreign_task = UUID(int=base + 9000).hex
            current.foreign_vision_ids[kind] = {"jobs": [foreign_task], "drafts": [str(UUID(int=base + 9001))]}
            session.add(
                TaskRecord(id=foreign_task, name="他人成员合成任务", type=f"{kind}_synthetic_list", status="success")
            )
            await session.flush()
            for index in reversed(range(job_count)):
                session.add(
                    VisionJob(
                        id=expected["job_ids"][index],
                        task_id=expected["jobs"][index],
                        actor_uid="owner",
                        member_id=current.member,
                        kind=kind,
                        request_id=str(uuid4()),
                        fingerprint="b" * 64,
                        upload_ids=[],
                        input_snapshot={},
                        created_at=datetime(2026, 10, 10 if index < 20 else 9, 12),
                    )
                )
            session.add(
                VisionJob(
                    id=str(UUID(int=base + 9000)),
                    task_id=foreign_task,
                    actor_uid="other",
                    member_id=current.foreign_member,
                    kind=kind,
                    request_id=str(uuid4()),
                    fingerprint="c" * 64,
                    upload_ids=[],
                    input_snapshot={},
                    created_at=datetime(2026, 10, 11, 12),
                )
            )
            payload = (
                {"source": "manual", "fields": [], "pages": []}
                if kind == "report"
                else {"source": "manual", "items": [], "photos": [], "meal_type": "lunch", "eaten_at": None}
            )
            for index in reversed(range(draft_count)):
                session.add(
                    VisionDraft(
                        id=expected["drafts"][index],
                        member_id=current.member,
                        kind=kind,
                        version=3,
                        review_status="pending_confirmation",
                        original_payload=payload,
                        payload=payload,
                        created_at=datetime(2026, 10, 10 if index < 17 else 9, 12),
                    )
                )
            session.add(
                VisionDraft(
                    id=str(UUID(int=base + 9001)),
                    member_id=current.foreign_member,
                    kind=kind,
                    original_payload=payload,
                    payload=payload,
                    created_at=datetime(2026, 10, 11, 12),
                )
            )
        await session.commit()
    current.evidence["vision_ids"] = current.vision_ids


async def vision_page(current, *, actor="owner", member=None, params=None, legacy=False):
    """真实TCP读取前后比较所有ORM表及xmin，证据仅保留合成ID与摘要。"""
    before = await schema_facts(current.sessions)
    path = f"{ROOT}/members/{member or current.member}/vision" + ("" if legacy else "/page")
    response = await current.client.get(path, headers=current.identities[actor], params=params)
    after = await schema_facts(current.sessions)
    payload = response.json()
    current.evidence["requests"].append(
        {
            "actor": actor,
            "path": path,
            "params": params or {},
            "status": response.status_code,
            "jobs": [row["task_id"] for row in payload.get("jobs", [])],
            "drafts": [row["id"] for row in payload.get("drafts", [])],
            "jobs_next_offset": payload.get("jobs_next_offset"),
            "drafts_next_offset": payload.get("drafts_next_offset"),
            "pg_before_sha256": hashlib.sha256(json.dumps(before, sort_keys=True).encode()).hexdigest(),
            "pg_after_sha256": hashlib.sha256(json.dumps(after, sort_keys=True).encode()).hexdigest(),
            "all_rows_and_xmin_unchanged": before == after,
        }
    )
    assert before == after, "识图列表读取不得修改业务、授权、任务或Agent运行事实"
    if not legacy and response.status_code in (200, 404):
        assert response.headers["cache-control"] == "no-store"
    return response


def assert_vision_page(response, expected, *, jobs_limit=20, drafts_limit=20, jobs_offset=0, drafts_offset=0):
    """以预先定义的任务与草稿序列独立核对两分页窗口。"""
    assert response.status_code == 200, response.text
    payload = response.json()
    assert set(payload) == {"jobs", "drafts", "jobs_next_offset", "drafts_next_offset"}
    assert [row["task_id"] for row in payload["jobs"]] == expected["jobs"][jobs_offset : jobs_offset + jobs_limit]
    assert [row["id"] for row in payload["drafts"]] == expected["drafts"][drafts_offset : drafts_offset + drafts_limit]
    for name, offset, limit in (("jobs", jobs_offset, jobs_limit), ("drafts", drafts_offset, drafts_limit)):
        expected_next = offset + limit if offset + limit < len(expected[name]) else None
        assert payload[f"{name}_next_offset"] == expected_next
        assert expected_next is None or type(payload[f"{name}_next_offset"]) is int


async def set_grant_scopes(current, member, actor, scopes):
    """提交独立用途授权，后续页必须重新读取当前PG事实。"""
    async with current.sessions() as session:
        grant = await session.get(HealthGrant, (member, actor))
        grant.scopes = scopes
        await session.commit()

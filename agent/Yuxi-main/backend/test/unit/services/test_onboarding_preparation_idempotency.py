"""真实准备入口的幂等回归；内存会话不代表 PostgreSQL、HTTP 或 Worker 验收。"""

import ast
from contextlib import asynccontextmanager
from copy import deepcopy
from datetime import date
from hashlib import sha256
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy import select

from yuxi.services.health_vision_types import HealthVisionError
from yuxi.storage.postgres.models_health import HealthOnboardingPreparation


@pytest.fixture
def preparation_start():
    """执行未改写的生产入口，持久化收据与队列使用有界内存替身。"""
    state = SimpleNamespace(sources={"version": 1}, rows={}, saved=0)
    original = HealthOnboardingPreparation(
        id="original-preparation",
        actor_uid="synthetic-user",
        family_id="synthetic-family",
        request_id="original-request",
        fingerprint="original-fingerprint",
        plan_date=date(2026, 10, 28),
        sources={"version": 1},
        consents=[],
        result={},
        status="waiting",
    )
    state.rows[original.request_id] = original

    class Database:
        """按生产查询的请求键读取收据，保留实际模型实例。"""

        async def execute(self, *_args):
            """锁语句在本单线程替身中无副作用。"""
            pass

        async def scalar(self, query):
            """从真实查询绑定参数读取同账号请求收据。"""
            params = query.compile().params
            assert params["actor_uid_1"] == "synthetic-user"
            return state.rows.get(params["request_id_1"])

        async def flush(self):
            """行在 add 时已进入内存存储。"""
            pass

        def add(self, row):
            """拒绝同键覆盖，模拟唯一收据身份。"""
            assert row.request_id not in state.rows
            state.rows[row.request_id] = row

    @asynccontextmanager
    async def session():
        """每个请求使用新会话，收据独立于进程内调用结果保存。"""
        yield Database()

    class Family:
        """仅提供已授权合成家庭，不模拟真实授权验收。"""

        def __init__(self, _db, uid):
            """限制测试只访问合成账号。"""
            assert uid == "synthetic-user"

        async def context(self, fid):
            """返回指定合成家庭。"""
            assert fid == "synthetic-family"
            return SimpleNamespace(id=fid), None

    class Body:
        """入口前已校验输入的替身，仅保留本测试依赖的字段。"""

        def __init__(self, request_id, *, revision=1):
            """分离请求身份与可变表单内容。"""
            self.client_request_id = request_id
            self.processing_consents = []
            self.revision = revision

        def model_dump(self, **_kwargs):
            """为指纹保留请求键与表单版本。"""
            return {"client_request_id": self.client_request_id, "revision": self.revision}

    async def sources(*_args):
        """来源可被另一设备更新，不能改变已落库请求键的目标。"""
        return deepcopy(state.sources)

    async def latest(*_args):
        """alias 不成为最新业务准备，与生产查询过滤保持一致。"""
        return next(row for row in reversed(list(state.rows.values())) if row.status != "alias")

    async def save_profile(*_args):
        """模拟档案幂等收据；不将重放输入覆盖到当前来源。"""
        state.saved += 1
        return {"completeProfile": True}

    async def read(_uid, _fid, pid):
        """只回读目标身份与来源失效状态，不伪造已完成菜单。"""
        row = next(row for row in state.rows.values() if row.id == pid)
        if row.status == "alias":
            target = row.result["reused_preparation_id"]
            row = next(row for row in state.rows.values() if row.id == target)
        return {"id": row.id, "status": "stale" if row.sources != state.sources else "preparing"}

    state.queue = AsyncMock(return_value=SimpleNamespace(id="synthetic-task"))
    state.publish = AsyncMock()
    scope = {
        "pg_manager": SimpleNamespace(get_async_session_context=session),
        "FamilyService": Family,
        "input_fingerprint": lambda value: sha256(json.dumps(value, sort_keys=True).encode()).hexdigest(),
        "text": lambda value: value,
        "select": select,
        "HealthOnboardingPreparation": HealthOnboardingPreparation,
        "HealthVisionError": HealthVisionError,
        "lock_preparation": AsyncMock(),
        "latest_preparation": latest,
        "MiniappProfileInput": SimpleNamespace(model_validate=lambda value: value),
        "save_miniapp_profile_in_session": save_profile,
        "preparation_sources": sources,
        "business_date": lambda: original.plan_date,
        "uuid4": uuid4,
        "queue_preparation": state.queue,
        "tasker": SimpleNamespace(publish=state.publish),
        "read_onboarding_preparation": read,
    }
    path = Path(__file__).resolve().parents[3] / "package/yuxi/services/onboarding_preparation_service.py"
    owner = next(
        node
        for node in ast.parse(path.read_text(encoding="utf-8")).body
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "start_onboarding_preparation"
    )
    exec(compile(ast.Module(body=[owner], type_ignores=[]), str(path), "exec"), scope)
    state.start = lambda key, **kwargs: scope[owner.name]("synthetic-user", "synthetic-family", Body(key, **kwargs))
    return state


@pytest.mark.asyncio
async def test_reused_request_survives_lost_response_and_changed_sources_without_new_queue(preparation_start):
    """响应丢失后同键仍指向原准备，来源更新只使原结果失效，不创建新任务。"""
    state = preparation_start
    first = await state.start("lost-response-key")
    assert first == {"id": "original-preparation", "status": "preparing"}

    state.sources = {"version": 2}
    replayed = await state.start("lost-response-key")

    assert replayed == {"id": first["id"], "status": "stale"}
    alias = state.rows["lost-response-key"]
    assert alias.status == "alias" and alias.result == {"reused_preparation_id": first["id"]}
    assert state.saved == 1
    assert len(state.rows) == 2
    state.queue.assert_not_awaited()
    state.publish.assert_not_awaited()


@pytest.mark.asyncio
async def test_changed_sources_with_a_new_request_still_start_a_new_preparation(preparation_start):
    """固定旧请求键不影响用户以新请求准备当前档案。"""
    state = preparation_start
    await state.start("first-key")
    state.sources = {"version": 2}

    result = await state.start("new-key")

    row = state.rows["new-key"]
    assert result == {"id": row.id, "status": "preparing"}
    assert row.id != "original-preparation" and row.sources == {"version": 2}
    state.queue.assert_awaited_once()
    state.publish.assert_awaited_once()


@pytest.mark.asyncio
async def test_reused_request_cannot_change_its_original_input(preparation_start):
    """alias 收据与普通准备一样保留原始输入指纹冲突校验。"""
    state = preparation_start
    await state.start("fixed-key")

    with pytest.raises(HealthVisionError) as error:
        await state.start("fixed-key", revision=2)

    assert error.value.code == "request_conflict" and error.value.status == 409
    assert state.saved == 1
    state.queue.assert_not_awaited()
    state.publish.assert_not_awaited()

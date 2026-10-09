"""真实配餐失败先保留合成协议证据，再撤销临时配置和数据。"""

import json
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

from test.e2e import test_health_safe_planner_live_e2e as live

pytestmark = pytest.mark.unit
OWNER = "pytest_health_protocol_failure"
RAW = '```json\n{"preview_id":"00000000-0000-4000-8000-000000000001"}\n```'


class DiagnosticSession:
    """只重放同Run的已完成模型事实，无网络或真实PG。"""

    def __init__(self, *, raw_available=True, status="failed"):
        self.raw_available = raw_available
        self.run = SimpleNamespace(
            id="synthetic-failed-run",
            request_id="synthetic-request",
            uid=OWNER,
            status=status,
            conversation_id=1,
            worker_id=None,
            lease_expires_at=None,
            runtime_cleanup_pending=False,
            output_message_id=3 if status == "completed" else None,
            token_usage={"model_call_count": 3},
            error_message="planner_output_invalid transport-private-secret" if status == "failed" else None,
        )

    async def scalar(self, statement):
        """槽位独占，只有独立数据库及本轮部门有值。"""
        sql = str(statement)
        if "current_database()" in sql:
            return "health_consultation_e2e"
        if "users.department_id" in sql:
            return 1
        return None

    async def scalars(self, statement):
        """根据领域查询返回明确失败Run及审计，不使用生产期望值。"""
        sql = str(statement)
        if "FROM agent_run_requests" in sql or "NOT IN" in sql:
            rows = []
        elif "FROM agent_run_attempts" in sql:
            rows = [SimpleNamespace(attempt_no=1, outcome="failed", finished_at=True)]
        elif "FROM agent_runs" in sql:
            rows = [self.run]
        elif "FROM health_safe_planner_preview" in sql:
            rows = [
                SimpleNamespace(
                    id="synthetic-receipt",
                    operation="swap",
                    snapshot={"status": "not_ready", "reason": "swap_rules_not_approved", "candidates": []},
                )
            ]
        elif "FROM messages" in sql:
            if "tool_audit" in statement.compile().params.values():
                rows = [
                    SimpleNamespace(
                        id=1,
                        execution_status="completed",
                        extra_metadata={"tool_name": "preview_safe_plan_swap", "api_key": "metadata-private-secret"},
                    )
                ]
            else:
                rows = (
                    [SimpleNamespace(id=2, message_type="model_audit", execution_status="completed", content=RAW)]
                    if self.raw_available
                    else []
                )
        else:
            raise AssertionError("未声明的unit数据库查询")
        return SimpleNamespace(all=lambda: rows)

    async def get(self, model, _key):
        """只提供已核对的合成成员绑定。"""
        if model is live.Message:
            return SimpleNamespace(
                id=3,
                run_id=self.run.id,
                request_id=self.run.request_id,
                content='{"status":"needs_input","questions":["合成补充"]}',
            )
        return (
            SimpleNamespace(actor_uid=OWNER, member_id="synthetic-member")
            if model is live.HealthConsultation
            else SimpleNamespace(owner_uid=OWNER)
        )


class DiagnosticClient:
    """清理临时供应商之前直接读取诊断文件，验证真实fixture顺序。"""

    base_url = "http://localhost:5050"

    def __init__(self, evidence_dir, status="failed"):
        self.evidence_dir = evidence_dir
        self.deleted = False
        self.status = status

    async def get(self, path, **_kwargs):
        """配置为空，删除后临时供应商不可见。"""
        if path.endswith("/configuration"):
            body = {"policy_version": "", **{kind: {"model": "", "available": False} for kind in live.PURPOSES}}
            return SimpleNamespace(status_code=200, json=lambda: body)
        return SimpleNamespace(status_code=404)

    async def post(self, _path, **_kwargs):
        """只创建临时供应商，不调用模型。"""
        return SimpleNamespace(status_code=200)

    async def put(self, _path, *, json, **_kwargs):
        """回读明确用途模型，其它用途仍关闭。"""
        body = {
            "policy_version": json.get("policy_version", ""),
            **{
                kind: {"model": json.get(kind + "_model", ""), "available": bool(json.get(kind + "_model"))}
                for kind in live.PURPOSES
            },
        }
        return SimpleNamespace(status_code=200, json=lambda: body)

    async def delete(self, _path, **_kwargs):
        """在副作用边界核对失败证据已经实际存在。"""
        diagnostic = json.loads((self.evidence_dir / "run-synthetic-failed-run.json").read_text())
        assert diagnostic["model_messages"][-1]["content"] == RAW
        assert diagnostic["status"] == self.status
        assert diagnostic["error_code"] == ("planner_output_invalid" if self.status == "failed" else None)
        self.deleted = True
        return SimpleNamespace(status_code=200)


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["failed", "completed"])
async def test_protocol_evidence_is_persisted_before_fixture_provider_cleanup(monkeypatch, tmp_path, capsys, status):
    """失败及领域断言前已完成的Run，都须先保存审计再进入删除。"""
    session = DiagnosticSession(status=status)

    @asynccontextmanager
    async def database():
        yield session

    monkeypatch.setattr(live.pg_manager, "get_async_session_context", database)
    monkeypatch.setattr(live, "EVIDENCE_DIR", tmp_path)
    monkeypatch.setattr(live, "get_user_data_dir", lambda: tmp_path)
    monkeypatch.setattr(live, "global_user_data_dir", lambda uid: tmp_path / uid)
    redis = DiagnosticRedis()

    async def connection():
        return redis

    monkeypatch.setattr(live, "create_async_redis_client", connection)
    settings = SimpleNamespace(
        provider_type="openai",
        base_url="https://dashscope.aliyuncs.com/v1",
        api_key="fixture-private-secret",
        model_id="qwen-plus-2025-07-28",
        headers_json={},
        extra_json={},
        include_user_uid=False,
        model_json={},
    )
    users = [
        {"uid": OWNER, "headers": {}},
        {"uid": "pytest_health_reviewer", "headers": {}},
        {"uid": "pytest_health_admin", "headers": {}},
    ]
    client = DiagnosticClient(tmp_path, status)
    fixture = live.live_planner.__wrapped__(settings, {}, (client, users))
    context = await anext(fixture)
    context[-1].append("synthetic-request")
    await fixture.aclose()
    assert client.deleted
    stored = (tmp_path / "run-synthetic-failed-run.json").read_text()
    assert RAW == json.loads(stored)["model_messages"][-1]["content"]
    if status == "completed":
        assert json.loads(stored)["published_output"]["type"] == "server_projection"
        assert json.loads(stored)["published_output"]["content"] != RAW
    assert json.loads(stored)["receipts"][0]["reason"] == "swap_rules_not_approved"
    assert all(
        secret not in stored
        for secret in ("fixture-private-secret", "transport-private-secret", "metadata-private-secret")
    )
    output = capsys.readouterr()
    assert RAW not in output.out and "private-secret" not in output.out + output.err


@pytest.mark.asyncio
async def test_missing_completed_raw_message_is_reported_unavailable(monkeypatch, tmp_path):
    """PG没有末轮完成正文时明确缺失，不从错误文本或checkpoint补造。"""
    session = DiagnosticSession(raw_available=False)
    monkeypatch.setattr(live, "EVIDENCE_DIR", tmp_path)
    await live._save_owned_run_diagnostic(session, session.run, OWNER)
    stored = json.loads((tmp_path / "run-synthetic-failed-run.json").read_text())
    assert stored["raw_model_content_status"] == "unavailable" and stored["model_messages"] == []


def test_multibyte_model_text_is_bounded_by_bytes_with_explicit_truncation():
    """中文正文同样限制64KiB，不把字符上限误当字节上限。"""
    bounded = live._bounded_model_content("合成" * 20000)
    assert len(bounded["content"].encode("utf-8")) <= 65536
    assert bounded["original_bytes"] == 120000 and bounded["truncated"] is True


class DiagnosticRedis:
    """保存本轮及相邻事件键，单位测试能发现越界删除。"""

    def __init__(self):
        self.keys = {
            "run:events:synthetic-failed-run",
            "run:cancel:synthetic-failed-run",
            "run:events:neighbour",
            "worker:health",
        }

    async def delete(self, *keys):
        """仅删除显式提交的精确键。"""
        removed = len(self.keys.intersection(keys))
        self.keys.difference_update(keys)
        return removed

    async def exists(self, *keys):
        """独立读取剩余键，不能回显删除参数作为成功。"""
        return len(self.keys.intersection(keys))

    async def aclose(self):
        """本替身不持有真实连接。"""


@pytest.mark.asyncio
async def test_redis_cleanup_removes_only_exact_settled_run_keys(monkeypatch, tmp_path):
    """本轮事件与取消键清零，相邻Run和Worker公共键保留。"""
    redis = DiagnosticRedis()

    async def connection():
        return redis

    monkeypatch.setattr(live, "create_async_redis_client", connection)
    monkeypatch.setattr(live, "EVIDENCE_DIR", tmp_path)
    run = DiagnosticSession().run
    await live._clear_live_run_redis([run], OWNER, [run.request_id])
    assert redis.keys == {"run:events:neighbour", "worker:health"}


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid", ["foreign_request", "active", "lease", "pending_cleanup"])
async def test_redis_cleanup_rejects_unowned_or_unsettled_before_side_effect(monkeypatch, invalid):
    """归属、终态或清理租约不足时连Redis连接都不能打开。"""
    run = DiagnosticSession().run
    requests = [run.request_id]
    if invalid == "foreign_request":
        requests = ["another-request"]
    elif invalid == "active":
        run.status = "running"
    elif invalid == "lease":
        run.lease_expires_at = True
    else:
        run.runtime_cleanup_pending = True
    connected = []

    async def connection():
        connected.append(True)
        return DiagnosticRedis()

    monkeypatch.setattr(live, "create_async_redis_client", connection)
    with pytest.raises(AssertionError, match="未收敛或归属不符"):
        await live._clear_live_run_redis([run], OWNER, requests)
    assert not connected

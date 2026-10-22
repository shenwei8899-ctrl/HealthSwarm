"""已持久化配餐回执在实际 Worker 退出后的恢复与撤回拒绝。"""

import asyncio
from copy import deepcopy
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import subprocess
import sys
import threading
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import delete, func, select

from test.e2e.test_health_consultation_e2e import collect_sse, isolated_health, wait_until  # noqa: F401
from test.integration.services.test_health_initial_planner_http import initial_runtime, bind_initial  # noqa: F401
from test.integration.services.test_health_vision_http import ROOT, health_http  # noqa: F401
from test.unit.services.test_daily_arrangement import sku
from test.support.health_initial_planner_replay_server import InitialPlannerReplayHandler
from yuxi.services.task_queue_service import publish_task
from yuxi.services.run_queue_service import close_queue_clients
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_business import AgentRun, FamilyArchive, FamilyAudit, FamilyMember, TaskRecord
from yuxi.storage.postgres.models_health import (
    HealthDailyArrangement,
    HealthMealPlan,
    HealthProcessingConsent,
    HealthRecipeCommerceSource,
    RecipeVersion,
)
from yuxi.services.health_nutrition_service import input_fingerprint
from yuxi.utils.datetime_utils import utc_now_naive

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.slow,
    pytest.mark.asyncio,
    pytest.mark.skipif(
        os.getenv("HEALTH_DAILY_RECOVERY_E2E") != "true",
        reason="须在健康隔离槽位停止 Compose Worker 后运行",
    ),
]


@pytest_asyncio.fixture
async def recovery_runtime(initial_runtime, tmp_path):  # noqa: F811
    """协议服务与 Worker 均由本 fixture 创建，只终止自己持有的子进程。"""
    assert os.getenv("HEALTH_CONSULTATION_E2E_ISOLATED") == "true"
    client, users, current, consent = initial_runtime
    gate, entered = threading.Event(), threading.Event()
    requests = []

    class Catalog(BaseHTTPRequestHandler):
        """在目录返回前提供可观察阻塞点，不替换业务 service。"""

        def do_GET(self):
            requests.append(self.path)
            entered.set()
            if not gate.wait(120):
                self.send_error(503)
                return
            body = json.dumps(
                {"code": 0, "data": {"items": [sku(stock=20)], "catalog_version": "synthetic-1", "has_more": False}}
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def do_POST(self):
            requests.append("UNEXPECTED_POST")
            self.send_error(400)

        def log_message(self, format, *args):
            """不记录合成协议正文。"""

    servers = [
        ThreadingHTTPServer(("0.0.0.0", 8773), InitialPlannerReplayHandler),
        ThreadingHTTPServer(("0.0.0.0", 8774), Catalog),
    ]
    for server in servers:
        threading.Thread(target=server.serve_forever, daemon=True).start()
    workers, logs = [], []

    def start_worker():
        """使用 shipping 入口和真实队列，目录连接到本 fixture 服务。"""
        log = (tmp_path / f"worker-{len(workers)}.log").open("w")
        logs.append(log)
        env = {
            **os.environ,
            "HEALTH_COMMERCE_URL": f"http://localhost:{servers[1].server_port}",
            "HEALTH_COMMERCE_CLIENT_ID": "synthetic",
            "HEALTH_COMMERCE_CLIENT_SECRET": "synthetic-catalog-secret",
            "HEALTH_COMMERCE_SOURCE_SECRET": "synthetic-daily-source-secret-32bytes",
        }
        process = subprocess.Popen([sys.executable, "-m", "server.worker_main"], env=env, stdout=log, stderr=log)
        workers.append(process)
        return process

    async def stop_workers():
        """先停止本 fixture 的执行进程，再允许清理其业务记录。"""
        for process in workers:
            if process.poll() is None:
                process.terminate()
                try:
                    await asyncio.to_thread(process.wait, 20)
                except subprocess.TimeoutExpired:
                    process.kill()
                    await asyncio.to_thread(process.wait, 10)

    try:
        worker = start_worker()
        yield client, users, current, consent, gate, entered, requests, worker, start_worker, stop_workers
    finally:
        gate.set()
        try:
            await stop_workers()
        finally:
            try:
                await close_queue_clients()
            finally:
                for server in servers:
                    await asyncio.to_thread(server.shutdown)
                    server.server_close()
                for log in logs:
                    log.close()


@pytest.mark.parametrize("interruption", ["none", "kill", "revoke", "revoke_before_publish"])
async def test_saved_agent_checkpoint_finishes_without_page_and_survives_worker_loss(recovery_runtime, interruption):
    """恢复保留真实回执，任务去重；撤回同意后菜单不得成为可见安排。"""
    client, users, current, consent, gate, entered, requests, worker, start_worker, stop_workers = recovery_runtime
    uid, headers = users[0]["uid"], users[0]["headers"]
    bound, initial = await bind_initial(client, users, current, family=False)
    assert bound.status_code == 201, bound.text
    key = str(uuid4())
    response = await client.post(
        "/api/agent/runs",
        headers=headers,
        json={
            "agent_slug": "health-meal-planner",
            "thread_id": bound.json()["thread_id"],
            "query": f"INITIAL_PLANNER_E2E:{uuid4().hex}:daily",
            "meta": {"request_id": key},
        },
    )
    assert response.status_code == 200, response.text
    run_id = response.json()["run_id"]
    await collect_sse(client, headers, run_id)
    response = await client.get(f"/api/agent/runs/{run_id}/result", headers=headers)
    assert response.json()["status"] == "completed", response.text
    payload = json.loads(response.json()["output"])
    assert payload["explanation"] == "合成恢复检查：按现有程序计算的三餐继续保存。"
    response = await client.post("/api/family", headers=headers, json={"name": "合成恢复家庭"})
    assert response.status_code == 200, response.text
    family = response.json()
    member = next(m for m in family["members"] if m["is_self"])
    rid = str(uuid4())
    path = f"/api/family/{family['id']}/daily-arrangements/2026-10-08"
    try:
        async with pg_manager.get_async_session_context() as db:
            recipe = await db.get(RecipeVersion, current["recipe"])
            recipe_hash = input_fingerprint(
                {
                    "ingredients": recipe.ingredients,
                    "yield_grams": str(recipe.yield_grams),
                    "nutrients": recipe.nutrients,
                    "dataset_version": recipe.dataset_version,
                }
            )
            db.add(
                HealthRecipeCommerceSource(
                    recipe_version_id=recipe.id,
                    recipe_hash=recipe_hash,
                    steps=["合成做法，仅测试"],
                    ingredient_codes={item["food"]["id"]: "food-A" for item in recipe.ingredients},
                    source_ref="synthetic-recovery",
                    published_by=users[2]["uid"],
                )
            )
            db.add(
                HealthDailyArrangement(
                    id=rid,
                    actor_uid=uid,
                    family_id=family["id"],
                    plan_date=date(2026, 10, 8),
                    version=1,
                    status="generating",
                    request_id=str(uuid4()),
                    snapshot={},
                    selection={
                        "initial": {k: v for k, v in initial.items() if k != "client_request_id"},
                        "agent_result": {"payload": payload, "task_key": key, "run_id": run_id},
                    },
                    sources={
                        "account_ref": "uid:" + uid,
                        "members": {
                            current["member"]: {
                                "id": member["id"],
                                "name": member["name"],
                                "version": member["version"],
                                "healthMemberId": current["member"],
                            }
                        },
                    },
                )
            )
        # 仅显式登记一次后台工作；此后只读 PG，模拟页面关闭。
        response = await client.post(path + "/resume", headers=headers)
        assert response.status_code == 200, response.text
        assert await asyncio.to_thread(entered.wait, 30), "Worker 未到达目录检查点"
        async with pg_manager.get_async_session_context() as db:
            tasks = list(
                (
                    await db.scalars(select(TaskRecord).where(TaskRecord.payload["arrangement_id"].as_string() == rid))
                ).all()
            )
            assert len(tasks) == 1 and tasks[0].status == "running"
            original_task = tasks[0].id
            plans = list((await db.scalars(select(HealthMealPlan).where(HealthMealPlan.actor_uid == uid))).all())
            assert len(plans) == 1
            plan_id = plans[0].id
        await publish_task(original_task)
        interrupted = interruption in {"kill", "revoke"}
        if interrupted:
            worker.kill()
            await asyncio.to_thread(worker.wait, 10)
            async with pg_manager.get_async_session_context() as db:
                stopped = await db.get(TaskRecord, original_task)
                assert stopped.status == "running" and stopped.lease_expires_at is not None
                if interruption == "revoke":
                    (
                        await db.get(HealthProcessingConsent, (current["member"], uid, "meal_plan"))
                    ).revoked_at = utc_now_naive()
            start_worker()
        elif interruption == "revoke_before_publish":
            async with pg_manager.get_async_session_context() as db:
                (
                    await db.get(HealthProcessingConsent, (current["member"], uid, "meal_plan"))
                ).revoked_at = utc_now_naive()
        gate.set()

        async def read_state():
            async with pg_manager.get_async_session_context() as db:
                row = await db.get(HealthDailyArrangement, rid)
                tasks = list(
                    (
                        await db.scalars(
                            select(TaskRecord).where(TaskRecord.payload["arrangement_id"].as_string() == rid)
                        )
                    ).all()
                )
                return row, tasks

        row, tasks = await wait_until(
            read_state,
            lambda x: x[0].status != "generating" and all(t.status in {"success", "failed", "cancelled"} for t in x[1]),
            timeout=90,
        )
        assert row.id == rid and row.version == 1
        assert len(tasks) == (2 if interrupted else 1)
        if interrupted:
            original = next(t for t in tasks if t.id == original_task)
            assert original.status == "failed" and original.error.startswith("worker_lease_expired:")
            assert row.selection["recovery_count"] == 1
        assert all(t.attempt_count == 1 for t in tasks)
        assert all(t.worker_id is None and t.lease_expires_at is None for t in tasks)
        async with pg_manager.get_async_session_context() as db:
            assert await db.scalar(select(func.count()).select_from(AgentRun).where(AgentRun.uid == uid)) == 1
            assert (
                await db.scalar(select(func.count()).select_from(HealthMealPlan).where(HealthMealPlan.actor_uid == uid))
                == 1
            )
        if interruption in {"revoke", "revoke_before_publish"}:
            assert row.status == "failed" and row.snapshot == {}
            assert all(t.status == "failed" for t in tasks)
            failed = next(t for t in tasks if t.id != original_task) if interrupted else tasks[0]
            assert "请先同意当前用途、处理方及政策" in failed.error
        else:
            successful = tasks[0] if interruption == "none" else next(t for t in tasks if t.id != original_task)
            assert successful.status == "success"
            assert row.status == "ready" and row.snapshot["plan_id"] == plan_id
            assert row.snapshot["analysis"]["run_id"] == run_id
            assert [m["type"] for m in row.snapshot["meals"]] == ["breakfast", "lunch", "dinner"]
            assert len({p["agent_task_id"] for p in row.selection["purchase_payloads"].values()}) == 3
            before = deepcopy(row.selection["purchase_payloads"])
            response = await client.get(path, headers=headers)
            assert response.status_code == 200 and response.json()["plan_id"] == plan_id
            assert (await client.get(path, headers=users[1]["headers"])).status_code == 404
            assert (await read_state())[0].selection["purchase_payloads"] == before
        assert "UNEXPECTED_POST" not in requests, "用户未点采购，不允许发布采购包"
    finally:
        gate.set()
        await stop_workers()
        async with pg_manager.get_async_session_context() as db:
            await db.execute(delete(TaskRecord).where(TaskRecord.payload["arrangement_id"].as_string() == rid))
            await db.execute(delete(HealthDailyArrangement).where(HealthDailyArrangement.id == rid))
            await db.execute(
                delete(HealthRecipeCommerceSource).where(
                    HealthRecipeCommerceSource.recipe_version_id == current["recipe"]
                )
            )
            await db.execute(delete(FamilyAudit).where(FamilyAudit.family_id == family["id"]))
            await db.execute(delete(FamilyMember).where(FamilyMember.family_id == family["id"]))
            await db.execute(delete(FamilyArchive).where(FamilyArchive.id == family["id"]))

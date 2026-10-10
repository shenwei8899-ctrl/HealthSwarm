"""隔离槽位的固定健康图门禁：真实Worker结果和无跳过的测试回执。"""

import asyncio
import os
from pathlib import Path
import subprocess
import socket
import sys
import time
import xml.etree.ElementTree as ET

import httpx
from sqlalchemy import text

from yuxi.storage.postgres.manager import pg_manager


async def verify_isolation():
    """先核对真实数据库及API，拒绝在日常服务批准合成处理方。"""
    if os.getenv("HEALTH_CONSULTATION_E2E_ISOLATED") != "true":
        raise RuntimeError("门禁仅允许明确标记的独立合成槽位")
    pg_manager.initialize()
    try:
        async with pg_manager.get_async_session_context() as session:
            database = await session.scalar(text("SELECT current_database()"))
            if database != "health_consultation_e2e":
                raise RuntimeError("门禁数据库不属于独立合成槽位")
        async with httpx.AsyncClient(timeout=5) as client:
            ready = await client.get("http://localhost:5050/api/system/ready")
            ready.raise_for_status()
    finally:
        await pg_manager.close()


def run_gate():
    """只管理本进程启动的协议回放，不停止API、Worker或其他进程。"""
    asyncio.run(verify_isolation())
    cases = [
        ("health_consultation_replay_server.py", 8766, "e2e/test_health_nutritionist_e2e.py"),
        ("health_consultation_replay_server.py", 8766, "e2e/test_health_evidence_lexical_e2e.py"),
        ("health_meal_planner_replay_server.py", 8768, "e2e/test_health_meal_planner_e2e.py"),
        (
            "health_diet_analysis_replay_server.py",
            8769,
            "e2e/test_health_diet_analysis_e2e.py::test_analysis_worker_independent_consent_and_authoritative_result",
        ),
        (
            "health_quality_replay_server.py",
            8771,
            "e2e/test_health_quality_e2e.py::test_quality_actual_worker_two_turns_and_illegal_final_selectors",
        ),
        (
            None,
            8776,
            "e2e/test_health_purchase_e2e.py::test_purchase_worker_current_receipt_checkpoint_and_negative_final_outputs",
        ),
        (
            "health_next_day_planner_replay_server.py",
            8774,
            "e2e/test_health_next_day_proposal_e2e.py::test_worker_tomorrow_proposal_exact_identity_sources_and_user_only_write",
        ),
        (
            "health_agent_personal_target_replay_server.py",
            8775,
            "e2e/test_health_agent_personal_targets_e2e.py::test_bound_target_real_worker_current_reference_and_source_withdrawal",
        ),
        (
            None,
            None,
            "integration/services/test_health_next_day_proposal_http.py",
        ),
        (
            None,
            None,
            "integration/services/test_health_evidence_search_visibility_http.py",
        ),
    ]
    output = Path("test/.tmp/health-agent-replay-gate")
    output.mkdir(parents=True, exist_ok=True)
    for number, (script, port, test_case) in enumerate(cases):
        if port is not None:
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=1):
                    pass
            except OSError:
                pass
            else:
                raise RuntimeError(f"回放端口{port}已有服务，拒绝替换或停止它")
        with (output / f"replay-{number}-{port}.log").open("w", encoding="utf-8") as log:
            # 无脚本时由fixture启动回放，或当前用例不需要模型。
            process = (
                subprocess.Popen([sys.executable, f"test/support/{script}"], stdout=log, stderr=log)
                if script is not None
                else None
            )
            try:
                deadline = time.monotonic() + 30
                while process is not None:
                    if process.poll() is not None:
                        raise RuntimeError(f"协议回放{port}启动失败")
                    try:
                        with socket.create_connection(("127.0.0.1", port), timeout=1):
                            pass
                        break
                    except OSError:
                        if time.monotonic() >= deadline:
                            raise RuntimeError(f"协议回放{port}未监听") from None
                        time.sleep(0.2)
                junit = output / f"result-{number}.xml"
                subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "pytest",
                        f"test/{test_case}",
                        "-q",
                        "--tb=short",
                        f"--junitxml={junit}",
                        "-o",
                        f"cache_dir={output}/pytest-cache",
                    ],
                    check=True,
                )
                tests = ET.parse(junit).getroot().findall(".//testcase")
                if not tests or any(case.find("skipped") is not None for case in tests):
                    raise RuntimeError("健康门禁没有实际执行全部选择用例，不能把跳过计为通过")
            finally:
                if process is not None and process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=5)
    print("健康固定图门禁通过：实际Worker与PG回读用例均执行，零跳过。")


if __name__ == "__main__":
    run_gate()

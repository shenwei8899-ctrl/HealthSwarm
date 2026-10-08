"""验证健康进程预算、依赖隔离与三项短期租约。"""

import asyncio
import subprocess
import sys
from pathlib import Path

import pytest

from server import worker_health
from yuxi.services import worker_health_service


@pytest.mark.unit
def test_cold_health_entry_does_not_import_business_runtime() -> None:
    """冷入口禁止装配模型、任务执行器与数据库，导入必须在原预算内完成。"""
    code = """
import importlib.abc, sys
class RejectBusinessImports(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.startswith(('yuxi.agents', 'yuxi.models', 'yuxi.repositories',
                               'yuxi.storage.postgres', 'yuxi.services.run_worker',
                               'yuxi.services.chat_service', 'yuxi.services.task_queue_service')):
            raise AssertionError('health entry imported business runtime: ' + fullname)
sys.meta_path.insert(0, RejectBusinessImports())
import server.worker_health
print('lightweight health entry imported')
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=Path(__file__).resolve().parents[3],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "lightweight health entry imported"


@pytest.mark.unit
@pytest.mark.parametrize("failure", [(None, -2), ("", 5000), ("stale", -1), ("expired", 0), ("long", 65001)])
@pytest.mark.parametrize("failed_lease_index", [0, 1, 2])
@pytest.mark.asyncio
async def test_each_invalid_lease_fails_closed(failure, failed_lease_index) -> None:
    """逐项破坏来源，不能被另外两项正常租约覆盖。"""
    leases = worker_health_service.WORKER_HEALTH_LEASES

    class RedisLease:
        """按租约索引提供独立值与 TTL。"""

        async def get(self, key):
            """返回指定坏来源或有效事实。"""
            return failure[0] if key == leases[failed_lease_index][0] else "healthy"

        async def pttl(self, key):
            """对长 TTL 用各自上限，避免只检验一种租约。"""
            limit = dict(leases)[key]
            if key != leases[failed_lease_index][0]:
                return limit
            return limit + 1 if failure[0] == "long" else failure[1]

    with pytest.raises(worker_health_service.WorkerUnavailableError):
        await worker_health_service.probe_worker_health(RedisLease())


@pytest.mark.unit
@pytest.mark.asyncio
async def test_probe_timeout_closes_redis_client(monkeypatch) -> None:
    """命令无响应时按内部预算失败，关闭本探针独占连接。"""
    closed = []

    class BlockedRedis:
        """挂起真实操作边界，关闭仍然可执行。"""

        async def get(self, key):
            """等待超过当前预算。"""
            await asyncio.sleep(1)

        async def aclose(self):
            """记录连接归还。"""
            closed.append(True)

    async def create_client(*args, **kwargs):
        """提供属于本次进程的连接。"""
        return BlockedRedis()

    monkeypatch.setattr(worker_health, "create_async_redis_client", create_client)
    monkeypatch.setattr(worker_health, "PROBE_TIMEOUT_SECONDS", 0.001)
    with pytest.raises(TimeoutError):
        await worker_health.check_worker_health()
    assert closed == [True]


@pytest.mark.unit
def test_failed_cli_emits_only_exception_type(monkeypatch, capsys) -> None:
    """异常消息中的凭据不能进入 Docker 或 CI 输出。"""

    async def fail():
        """制造带敏感信息的底层失败。"""
        raise ConnectionError("redis://private-secret@private-host")

    monkeypatch.setattr(worker_health, "check_worker_health", fail)
    assert worker_health.main() == 1
    output = capsys.readouterr()
    assert output.out == ""
    assert output.err == "worker health failed: ConnectionError\n"


@pytest.mark.unit
def test_successful_cli_is_silent(monkeypatch, capsys) -> None:
    """正常探针只通过退出码表达结果。"""

    async def healthy():
        """完成一次成功检查。"""
        return None

    monkeypatch.setattr(worker_health, "check_worker_health", healthy)
    assert worker_health.main() == 0
    assert capsys.readouterr() == ("", "")

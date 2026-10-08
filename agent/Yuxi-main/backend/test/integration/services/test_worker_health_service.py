"""使用真实 Redis 的独占键空间验证 worker 健康契约。"""

import asyncio
import os
import sys
from uuid import uuid4

import pytest
import pytest_asyncio

from yuxi.services import worker_health_service
from yuxi.storage.redis import create_async_redis_client

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest_asyncio.fixture
async def health_redis(monkeypatch):
    """三项短期事实使用唯一命名空间，不能改写运行 worker 的真实键。"""
    redis = await create_async_redis_client()
    namespace = f"pytest-health-{uuid4().hex}"
    leases = tuple(
        (f"{namespace}:{i}", limit) for i, (_, limit) in enumerate(worker_health_service.WORKER_HEALTH_LEASES)
    )
    monkeypatch.setattr(worker_health_service, "WORKER_HEALTH_LEASES", leases)
    try:
        for key, limit in leases:
            await redis.set(key, "current-worker", px=limit)
        yield redis, leases
    finally:
        await redis.delete(*(key for key, _ in leases))
        await redis.aclose()


async def test_current_bounded_redis_leases_are_healthy(health_redis):
    """实际 GET/PTTL 证明有效三项事实通过。"""
    redis, leases = health_redis
    await worker_health_service.probe_worker_health(redis)
    for key, limit in leases:
        assert await redis.get(key) == "current-worker"
        assert 0 < await redis.pttl(key) <= limit


@pytest.mark.parametrize("lease_index", [0, 1, 2])
@pytest.mark.parametrize("failure", ["missing", "persistent", "too_long", "empty", "expired"])
async def test_each_real_invalid_lease_is_rejected(health_redis, lease_index, failure):
    """制造真实缺失、永久、过长、空值或过期键，其他来源仍有效。"""
    redis, leases = health_redis
    key, limit = leases[lease_index]
    if failure == "missing":
        await redis.delete(key)
        assert await redis.pttl(key) == -2
    elif failure == "persistent":
        await redis.persist(key)
        assert await redis.pttl(key) == -1
    elif failure == "too_long":
        await redis.pexpire(key, limit + 60000)
        assert await redis.pttl(key) > limit
    elif failure == "empty":
        await redis.set(key, "", px=limit)
        assert await redis.get(key) == ""
    else:
        await redis.pexpire(key, 1)
        for _ in range(100):
            if await redis.pttl(key) == -2:
                break
            await asyncio.sleep(0.005)
        assert await redis.pttl(key) == -2

    with pytest.raises(worker_health_service.WorkerUnavailableError):
        await worker_health_service.probe_worker_health(redis)
    for other_key, other_limit in leases:
        if other_key != key:
            assert await redis.get(other_key) == "current-worker"
            assert 0 < await redis.pttl(other_key) <= other_limit


async def test_cli_wrong_redis_destination_fails_without_connection_details():
    """新进程读取无服务的 Redis 地址，不能继承已有健康连接或泄露地址。"""
    env = {**os.environ, "REDIS_URL": "redis://health-probe-secret@127.0.0.1:1/0"}
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "server.worker_health",
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=10)
    finally:
        if process.returncode is None:
            process.kill()
            await process.wait()
    assert process.returncode == 1
    assert stdout == b""
    assert stderr == b"worker health failed: ConnectionError\n"

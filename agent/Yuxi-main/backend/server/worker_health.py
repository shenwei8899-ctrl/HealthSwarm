"""供 Docker 与 CI 调用的轻量 worker 健康入口。"""

import asyncio
import sys

from yuxi.services.worker_health_service import probe_worker_health
from yuxi.storage.redis import RedisConfig, create_async_redis_client

PROBE_TIMEOUT_SECONDS = 2.0


async def check_worker_health() -> None:
    """在固定预算内读取同一队列的租约并归还独占连接。"""
    redis = await create_async_redis_client(
        RedisConfig.from_env(
            socket_timeout=PROBE_TIMEOUT_SECONDS,
            socket_connect_timeout=PROBE_TIMEOUT_SECONDS,
        ),
        ping=False,
    )
    try:
        await asyncio.wait_for(probe_worker_health(redis), timeout=PROBE_TIMEOUT_SECONDS)
    finally:
        await redis.aclose()


def main() -> int:
    """只报告失败类型，避免 Redis 配置与错误消息进入探针输出。"""
    try:
        asyncio.run(check_worker_health())
    except Exception as exc:
        print(f"worker health failed: {type(exc).__name__}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

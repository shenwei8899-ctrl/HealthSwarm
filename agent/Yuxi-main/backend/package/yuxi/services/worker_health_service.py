"""兼容 worker 的短期消费与收敛健康契约，不装配业务执行器。"""

import os

WORKER_HEALTH_CONTRACT = "agent-run-v1"
WORKER_HEALTH_KEY = f"yuxi:worker:health:{WORKER_HEALTH_CONTRACT}"
WORKER_HEALTH_INTERVAL_SECONDS = float(os.getenv("WORKER_HEALTH_INTERVAL_SECONDS", "5"))
if not 0 < WORKER_HEALTH_INTERVAL_SECONDS <= 10:
    raise ValueError("WORKER_HEALTH_INTERVAL_SECONDS 必须大于 0 且不超过 10")
WORKER_HEALTH_MAX_TTL_MS = int((WORKER_HEALTH_INTERVAL_SECONDS + 1) * 1000)
RUN_RECONCILIATION_SECONDS = 30
WORKER_RECONCILIATION_HEALTH_KEY = f"{WORKER_HEALTH_KEY}:lease-reconciliation"
WORKER_RECONCILIATION_HEALTH_TTL_SECONDS = RUN_RECONCILIATION_SECONDS * 2 + 5
TASK_RECONCILIATION_SECONDS = 30.0
TASK_RECONCILIATION_HEALTH_KEY = "yuxi:worker:health:durable-task-reconciliation-v1"
TASK_RECONCILIATION_HEALTH_TTL_SECONDS = int(TASK_RECONCILIATION_SECONDS * 2 + 5)
WORKER_HEALTH_LEASES = (
    (WORKER_HEALTH_KEY, WORKER_HEALTH_MAX_TTL_MS),
    (WORKER_RECONCILIATION_HEALTH_KEY, WORKER_RECONCILIATION_HEALTH_TTL_SECONDS * 1000),
    (TASK_RECONCILIATION_HEALTH_KEY, TASK_RECONCILIATION_HEALTH_TTL_SECONDS * 1000),
)


class WorkerUnavailableError(RuntimeError):
    """当前队列没有完成启动且仍在续租的兼容 worker。"""


async def probe_worker_health(redis) -> None:
    """三项成功事实均须存在且具有当前契约内的短期 TTL。"""
    for key, max_ttl_ms in WORKER_HEALTH_LEASES:
        value = await redis.get(key)
        ttl_ms = await redis.pttl(key)
        if not value or ttl_ms <= 0 or ttl_ms > max_ttl_ms:
            raise WorkerUnavailableError("worker health lease missing or invalid")

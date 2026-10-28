"""通过已有持久Task完成每日安排，不依赖页面存活。"""

import asyncio
from datetime import date

from sqlalchemy import select

from yuxi.repositories.daily_arrangement_repository import DailyArrangementRepository
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.services.task_service import tasker
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_health import HealthDailyArrangement


async def queue_daily_in_session(session, row):
    """安排与执行请求同事务提交；恢复仍使用同一业务版本和阶段结果。"""
    payload = {
        "uid": row.actor_uid,
        "family_id": row.family_id,
        "date": row.plan_date.isoformat(),
        "arrangement_id": row.id,
        "version": row.version,
    }
    task, _ = await tasker.create_unique_in_session(
        session,
        name="完成今日安排",
        task_type="daily_arrangement_v1",
        payload=payload,
        payload_match={
            **payload,
            "recovery_count": row.selection.get("recovery_count", 0),
        },
        timeout_seconds=600,
    )
    return task


async def request_daily_resume(uid, fid, day, *, retry_failed=False):
    """HTTP只登记后台恢复；读取不会发起模型或采购请求。"""
    from yuxi.services.daily_arrangement_service import (
        authorize_daily_agent_result,
        authorize_sources,
        read_daily_arrangement,
        retained_purchase_payloads,
    )

    task = None
    async with pg_manager.get_async_session_context() as session:
        _, row = await DailyArrangementRepository(session, uid, fid).context(day, lock=True)
        if row is not None:
            await authorize_sources(session, uid, row)
            if row.status == "failed" and retry_failed:
                if row.selection.get("agent_result"):
                    try:
                        await authorize_daily_agent_result(session, uid, row.selection)
                    except HealthVisionError as error:
                        if error.code != "policy_changed":
                            raise
                        # 当前成员来源和同意已通过，明确重试才重建旧处理快照。
                        row.selection = {
                            **{
                                key: value
                                for key, value in row.selection.items()
                                if key not in {"agent_result", "purchase_catalog_version"}
                            },
                            "purchase_payloads": retained_purchase_payloads(
                                row.selection,
                                row.selection["initial"].get("change_meal"),
                            ),
                        }
                row.status = "generating"
                # 外部服务失败保留模型回执与已发布采购请求，只显式失败的分析才重做。
                row.selection = {
                    **{key: value for key, value in row.selection.items() if key != "failure_message"},
                    "recovery_count": 0,
                }
                if not row.selection.get("agent_result"):
                    attempt = row.selection.get("attempt", 0) + 1
                    row.selection = {
                        **row.selection,
                        "attempt": attempt,
                        "retry_limit": attempt + 2,
                    }
            if row.status == "generating":
                task = await queue_daily_in_session(session, row)
    if task:
        await tasker.publish(task)
    return await read_daily_arrangement(uid, fid, day)


async def run_daily_arrangement(context):
    """持有任务租约轮询原Run，外部暂时异常重放已持久化的同一请求。"""
    from yuxi.services.daily_arrangement_service import resume_daily_arrangement

    payload = context.payload
    uid, fid, day = (
        payload["uid"],
        payload["family_id"],
        date.fromisoformat(payload["date"]),
    )
    failures = 0
    for _ in range(150):
        await context.raise_if_cancelled()
        async with pg_manager.get_async_session_context() as session:
            _, row = await DailyArrangementRepository(session, uid, fid).context(day)
            if row is None or row.version != payload["version"] or row.status != "generating":
                return {
                    "arrangement_id": payload["arrangement_id"],
                    "version": payload["version"],
                }
        try:
            if not row.selection.get("agent_result"):
                from yuxi.services.miniapp_profile_coding import (
                    prepare_daily_profile_coding,
                )

                await prepare_daily_profile_coding(uid, row.sources, row.selection["initial"], context)
            async with pg_manager.get_async_session_context() as session:
                _, current = await DailyArrangementRepository(session, uid, fid).context(day, lock=True)
                if current.version == payload["version"] and current.status == "generating":
                    current.selection = {
                        **current.selection,
                        "preparation_stage": "arranging",
                    }
            completed = await resume_daily_arrangement(uid, fid, day)
            if completed["status"] == "ready":
                from yuxi.services.onboarding_preparation_service import (
                    finish_onboarding_preparations,
                )

                await finish_onboarding_preparations(uid, fid, day, completed)
            failures = 0
        except HealthVisionError as error:
            if error.status < 500 or error.code in {
                "commerce_not_configured",
                "daily_dependencies_not_ready",
            }:
                raise
            failures += 1
            if failures >= 3:
                raise
        await asyncio.sleep(2 if not failures else 5)
    raise HealthVisionError("daily_processing_timeout", "原安排仍未处理完成，可重试恢复", 503)


async def fail_daily_arrangement(session, task_record, error):
    """失联时有限重建持久Task，其他错误保留快照与阶段结果等待重试。"""
    payload = task_record.payload
    row = await session.scalar(
        select(HealthDailyArrangement)
        .where(
            HealthDailyArrangement.id == payload["arrangement_id"],
            HealthDailyArrangement.actor_uid == payload["uid"],
            HealthDailyArrangement.family_id == payload["family_id"],
        )
        .with_for_update()
    )
    if row is None or row.version != payload["version"] or row.status != "generating":
        return
    count = row.selection.get("recovery_count", 0)
    if error.startswith(("worker_lease_expired:", "worker_shutdown:")) and count < 2:
        row.selection = {**row.selection, "recovery_count": count + 1}
        # 旧任务在同一事务中进入终态，新任务由既有pending publisher补发。
        await queue_daily_in_session(session, row)
        return
    row.status = "failed"
    row.selection = {
        **row.selection,
        "failure_message": "今日安排暂未处理完成，可以重试恢复；已有档案和安排已保留。",
    }

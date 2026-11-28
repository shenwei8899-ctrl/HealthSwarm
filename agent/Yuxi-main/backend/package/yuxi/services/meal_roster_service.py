"""保存就餐目标和单餐例外；用餐保护只读取现有有效记餐。"""

import asyncio
from fastapi import HTTPException
from datetime import date, datetime
from uuid import NAMESPACE_URL, uuid5
from zoneinfo import ZoneInfo

from sqlalchemy import select

from yuxi.services.family_service import FamilyService
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_health import HealthDailyMealPlan
from yuxi.utils.datetime_utils import utc_now_naive

MEALS = ("breakfast", "lunch", "dinner")


async def current_roster(session, row, *, lock=False):
    """旧独立标记不再决定用餐事实，逐次读取当前有效记餐保护原安排。"""
    from yuxi.repositories.meal_execution_repository import MealExecutionRepository

    if row is None:
        return {}
    state = roster_intent((row.meal_sources or {}).get("_roster", {}))
    archive = getattr(row, "archive_meals", None) or {}
    protected = (
        await MealExecutionRepository(session).protected_meals(row.family_id, row.plan_date, archive, lock=lock)
        if archive
        else set()
    )
    for meal in MEALS:
        policy = state.get(meal, {})
        if meal in protected:
            policy = {
                **policy,
                "execution_locked": True,
                "status": "ready",
                "target_ids": sorted(str(m["id"]) for m in (row.archive_meals or {}).get(meal, {}).get("members", [])),
            }
        if policy:
            state[meal] = policy
    return state


def roster_intent(state):
    """仅保留名单意图和任务状态，不保存派生锁或旧用餐确认。"""
    result = {}
    for key, value in state.items():
        if key not in MEALS:
            result[key] = value
            continue
        policy = {
            name: data
            for name, data in value.items()
            if name not in {"execution_locked", "consumed_at", "confirmed_by"}
        }
        if policy.get("status") == "consumed":
            policy["status"] = "ready"
        result[key] = policy
    return result


def roster_targets(archive, state, old_diners, new_diners):
    """仅更新沿用默认名单且未确认用餐的已存在餐次。"""
    targets = {}
    for meal, saved in archive.items():
        if meal not in MEALS:
            continue
        policy = state.get(meal, {})
        if policy.get("execution_locked") or policy.get("mode") == "explicit":
            continue
        previous = sorted(m["id"] for m in saved.get("members", []))
        # 旧版本没有意图字段，不覆盖与原默认名单不同的单餐安排。
        if policy.get("mode") != "default" and previous != sorted(old_diners):
            continue
        if previous != sorted(new_diners) or policy.get("target_ids", previous) != sorted(new_diners):
            targets[meal] = sorted(new_diners)
    return targets


async def schedule_default_roster(session, uid, family, previous):
    """档案保存事务内登记所有未执行日期的更新，不依赖页面继续运行。"""
    diners = sorted((family.settings or {}).get("default_diners", []))
    if diners == sorted(previous) or not diners:
        return
    from yuxi.services.exclusive_roster_service import schedule_exclusive_roster

    await schedule_exclusive_roster(session, uid, family)
    today = datetime.now(ZoneInfo("Asia/Shanghai")).date()
    rows = (
        await session.scalars(
            select(HealthDailyMealPlan)
            .where(
                HealthDailyMealPlan.family_id == family.id,
                HealthDailyMealPlan.is_shared.is_(True),
                HealthDailyMealPlan.plan_date >= today,
            )
            .order_by(HealthDailyMealPlan.plan_date)
        )
    ).all()
    for row in rows:
        state = await current_roster(session, row, lock=True)
        targets = roster_targets(row.archive_meals or {}, state, previous, diners)
        if targets:
            await register_roster(session, uid, row, targets, mode="default")


async def change_roster(uid, fid, day, data):
    """在当前日期版本下更新名单，用餐确认由原记餐链路拥有。"""
    from yuxi.services.daily_meal_plan_service import current_row
    from yuxi.services.task_service import tasker
    from yuxi.services.health_nutrition_service import input_fingerprint

    fingerprint = input_fingerprint(data.model_dump(mode="json"))
    task = None
    async with pg_manager.get_async_session_context() as session:
        row = await current_row(session, uid, fid, day, lock=True)
        today = datetime.now(ZoneInfo("Asia/Shanghai")).date()
        if day < today or row is None:
            raise HealthVisionError("roster_history_readonly", "历史餐单保留原安排", 409)
        state = await current_roster(session, row, lock=True)
        key = str(data.client_request_id)
        if state.get("request_id") == key:
            if state.get("fingerprint") != fingerprint:
                raise HealthVisionError("request_conflict", "同一请求不能更改成员选择", 409)
            return {"version": row.version, "roster": state}
        if row.version != data.version:
            raise HealthVisionError("daily_plan_version_changed", "餐单已更新，请重新读取成员", 409)
        meals = list(data.meal_types)
        if any(m not in (row.archive_meals or {}) for m in meals):
            raise HealthVisionError("meal_absent", "所选餐次尚未生成", 409)
        if data.consumed:
            raise HealthVisionError("meal_recording_required", "请通过记餐流程确认实际用餐", 409)
        service = FamilyService(session, uid)
        for mid in data.member_ids:
            await service.context(fid, str(mid))
        targets = {m: sorted(map(str, data.member_ids)) for m in meals if not state.get(m, {}).get("execution_locked")}
        if not targets:
            raise HealthVisionError("meal_has_records", "所选餐次已有记餐，保留原安排", 409)
        task = await register_roster(session, uid, row, targets, mode="explicit", request_id=key)
        latest = {**row.meal_sources["_roster"], "fingerprint": fingerprint}
        row.meal_sources = {**row.meal_sources, "_roster": latest}
        result = {"version": row.version, "roster": row.meal_sources["_roster"]}
    if task:
        await tasker.publish(task)
    return result


async def register_roster(session, uid, row, targets, *, mode, request_id=None):
    """名单目标和任务原子写入，提升每日版本阻止旧任务发布。"""
    from yuxi.services.task_service import tasker

    state = await current_roster(session, row, lock=True)
    for meal, ids in targets.items():
        state[meal] = {
            **state.get(meal, {}),
            "mode": mode or state.get(meal, {}).get("mode", "default"),
            "target_ids": ids,
            "status": "pending",
        }
    revision = row.version + 1
    payload = {"uid": uid, "family_id": row.family_id, "date": str(row.plan_date), "revision": revision}
    task, _ = await tasker.create_unique_in_session(
        session,
        name="按新就餐成员更新餐单",
        task_type="meal_roster_v1",
        payload=payload,
        payload_match=payload,
        timeout_seconds=1200,
    )
    session.info.setdefault("meal_roster_tasks", []).append(task)
    state.pop("active_request", None)
    state.update(task_id=task.id, revision=revision, request_id=request_id)
    row.meal_sources = {**row.meal_sources, "_roster": roster_intent(state)}
    row.version, row.updated_at = revision, utc_now_naive()
    return task


async def run_roster_update(context):
    """逐组提交已有参考配餐任务，重启复用相同请求，不伪造成员或份量。"""
    from yuxi.services.daily_meal_plan_service import current_row, pending_request
    from yuxi.services.health_task_service import create_health_task_entry, read_health_task
    from yuxi.services.health_task_types import HealthTaskEntryInput
    from yuxi.repositories.family_repository import FamilyRepository
    from yuxi.services.agent_request_service import AgentRequestInput, RunOrigin, submit_agent_request
    from yuxi.services.input_message_service import build_chat_input_message
    from yuxi.storage.postgres.models_business import User

    payload = context.payload
    uid, fid, day = payload["uid"], payload["family_id"], date.fromisoformat(payload["date"])
    for _ in range(250):
        await context.raise_if_cancelled()
        async with pg_manager.get_async_session_context() as session:
            row = await current_row(session, uid, fid, day, lock=True)
            state = await current_roster(session, row, lock=True)
            if state.get("revision") != payload["revision"]:
                return {"status": "superseded"}
            row.meal_sources = {**row.meal_sources, "_roster": roster_intent(state)}
            groups = {}
            for meal in MEALS:
                policy = state.get(meal, {})
                if policy.get("status") == "pending" and not policy.get("execution_locked"):
                    groups.setdefault(tuple(policy["target_ids"]), []).append(meal)
            if not groups:
                return {"status": "completed"}
            ids, meals = next(iter(groups.items()))
            key = str(uuid5(NAMESPACE_URL, f"roster:{fid}:{day}:{payload['revision']}:{','.join(meals)}"))
            pending = await pending_request(session, row, viewer_uid=uid)
            wait_previous = (
                pending
                and pending.get("request_id") != key
                and pending["status"] in {"queued", "dispatched", "pending", "running", "cancel_requested"}
            )
            anchor = await FamilyRepository(session).linked_health_member(fid, ids[0])
            active = state.get("active_request")
            if active and active["meals"] == meals:
                base = active["base"]
            else:
                base = row.version
                state = {**state, "active_request": {"meals": meals, "base": base}}
                row.meal_sources = {**row.meal_sources, "_roster": roster_intent(state)}
        key = str(uuid5(NAMESPACE_URL, f"roster:{fid}:{day}:{payload['revision']}:{','.join(meals)}"))
        if wait_previous:
            await asyncio.sleep(2)
            continue
        entry = await create_health_task_entry(
            uid,
            anchor,
            HealthTaskEntryInput.model_validate(
                {
                    "task_type": "reference_meal_preview",
                    "client_request_id": key,
                    "selection": {
                        "mode": "reference",
                        "family_id": fid,
                        "plan_date": str(day),
                        "participant_ids": list(ids),
                        "meal_types": meals,
                        "daily_base_version": base,
                    },
                }
            ),
        )
        if entry.entry_status != "ready":
            raise HealthVisionError("roster_not_ready", "成员资料或配餐服务尚未就绪，原餐单保留", 409)
        try:
            async with pg_manager.get_async_session_context() as session:
                user = await session.scalar(select(User).where(User.uid == uid))
                await submit_agent_request(
                    request_input=AgentRequestInput(
                        agent_slug=entry.agent_slug,
                        thread_id=str(entry.thread_id),
                        request_id=key,
                        input_message=build_chat_input_message(
                            "请按绑定的最新就餐成员及饮食限制重新安排指定餐次，使用参考配餐工具核对并保存；保留未指定餐次。",
                            None,
                        ),
                        origin=RunOrigin(source="chat", channel="miniapp"),
                    ),
                    current_user=user,
                    db=session,
                )
        except HTTPException as error:
            if error.status_code != 423:
                raise
            await asyncio.sleep(2)
            continue
        for _ in range(150):
            await context.raise_if_cancelled()
            task = await read_health_task(uid, key)
            if (
                task.result is not None
                or task.execution_status in {"failed", "cancelled", "interrupted"}
                or task.request_status in {"failed", "cancelled", "rejected"}
            ):
                async with pg_manager.get_async_session_context() as session:
                    row = await current_row(session, uid, fid, day)
                    state = await current_roster(session, row)
                    if state.get("revision") != payload["revision"]:
                        return {"status": "superseded"}
                    if any(state.get(m, {}).get("status") == "pending" for m in meals):
                        raise HealthVisionError(
                            "roster_update_incomplete", "成员更新尚未完成，请重试或补充配餐信息", 409
                        )
                break
            await asyncio.sleep(2)
        else:
            raise HealthVisionError("roster_update_timeout", "成员更新超时，原餐单保留", 503)
    raise HealthVisionError("roster_update_timeout", "成员更新未完成", 503)


async def fail_roster_update(session, record, error):
    """失败只标记同一目标版本，保留已有餐单内容。"""
    p = record.payload
    # Task payload 已由服务端登记；离家账号的任务也必须收敛，不能依赖其已撤销的读取权限。
    row = await session.scalar(
        select(HealthDailyMealPlan)
        .where(
            HealthDailyMealPlan.family_id == p["family_id"],
            HealthDailyMealPlan.plan_date == date.fromisoformat(p["date"]),
            HealthDailyMealPlan.is_shared.is_(True),
        )
        .with_for_update()
    )
    state = dict((row.meal_sources or {}).get("_roster", {})) if row else {}
    if state.get("revision") != p["revision"]:
        return
    for meal in MEALS:
        if state.get(meal, {}).get("status") == "pending":
            state[meal] = {**state[meal], "status": "failed"}
    row.meal_sources = {**row.meal_sources, "_roster": roster_intent(state)}


async def verify_roster_publish(session, row, meals, participants):
    """发布与用餐确认共用每日锁；完成前不覆盖已用餐或新的成员目标。"""
    if row is None:
        return
    if row.plan_date < datetime.now(ZoneInfo("Asia/Shanghai")).date():
        raise HealthVisionError("roster_history_readonly", "历史餐单保留原安排", 409)
    state = await current_roster(session, row, lock=True)
    for meal in meals:
        policy = state.get(meal, {})
        if not policy:
            from yuxi.storage.postgres.models_business import FamilyArchive

            family = await session.get(FamilyArchive, row.family_id)
            defaults = sorted((family.settings or {}).get("default_diners", []))
            policy = {
                "mode": "default" if sorted(participants) == defaults else "explicit",
                "target_ids": sorted(participants),
            }
            state[meal] = policy
        if policy.get("execution_locked"):
            raise HealthVisionError("meal_has_records", "本餐已有记餐，保留原餐单", 409)
        if policy.get("status") in {"pending", "failed"} and sorted(participants) != policy["target_ids"]:
            raise HealthVisionError("roster_changed", "就餐成员已更新，旧结果不能覆盖", 409)
        if policy.get("status") not in {"pending", "failed"} and policy.get("target_ids") != sorted(participants):
            state[meal] = {**policy, "mode": "explicit", "target_ids": sorted(participants), "status": "ready"}
        elif policy.get("target_ids") == sorted(participants):
            state[meal] = {**policy, "status": "ready"}
    row.meal_sources = {**row.meal_sources, "_roster": roster_intent(state)}

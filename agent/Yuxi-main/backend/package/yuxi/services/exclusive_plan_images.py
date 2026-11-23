"""专属菜单图片独立生成，读取只查询来源绑定的公共缓存。"""

import asyncio
from copy import deepcopy

from yuxi.repositories.exclusive_plan_repository import ExclusivePlanRepository
from yuxi.services.exclusive_plan_service import PREVIEW_POLICY, exclusive_context
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.services.reference_recipe_presentation import generated_recipe_image, prepare_recipe_images, recipe_image_key
from yuxi.services.task_service import tasker
from yuxi.services.service_notice_service import require_service_notice
from yuxi.storage.postgres.manager import pg_manager


async def start_plan_images(uid, fid, gid, *, retry=False):
    """显式登记旧计划补图；自动进入页面不重复已结束的尝试。"""
    async with pg_manager.get_async_session_context() as session:
        row, context = await image_context(session, uid, fid, gid)
        from yuxi.services.exclusive_plan_tasks import validate_saved_days

        for entries in row.progress["tiers"].values():
            await validate_saved_days(session, context, entries)
        previous = await tasker.find_task_by_payload(
            task_type="exclusive_recipe_images_v1", payload_match={"group_id": gid}
        )
        if previous and (previous.status not in {"failed", "cancelled"} or not retry):
            return {"status": previous.status}
        await require_service_notice(session, uid)
        task, created = await queue_plan_images(session, row)
    if created:
        await tasker.publish(task)
    return {"status": task.status}


async def read_plan_images(uid, fid, gid, tier, day_no):
    """仅返回当前一天已经核验原文的图片及持久任务状态。"""
    async with pg_manager.get_async_session_context() as session:
        row, context = await image_context(session, uid, fid, gid)
        entries = [e for e in row.progress["tiers"].get(tier, []) if e["day"]["day_no"] == day_no]
        if not entries:
            raise HealthVisionError("not_found", "计划日期不存在", 404)
        from yuxi.services.exclusive_plan_tasks import validate_saved_days

        await validate_saved_days(session, context, entries)
        dishes = deepcopy([d for e in entries for m in e["meals"] for d in m["dishes"]])
    task = await tasker.find_task_by_payload(task_type="exclusive_recipe_images_v1", payload_match={"group_id": gid})
    images = await cached_plan_images(dishes)
    return {"day_no": day_no, "status": task.status if task else "not_started", "images": images}


async def run_plan_images(context):
    """分批重新核验已保存原谱，网络生成时不持家庭事务。"""
    uid, fid, gid = (context.payload[k] for k in ("uid", "family_id", "group_id"))
    async with pg_manager.get_async_session_context() as session:
        await require_service_notice(session, uid)
        row, _ = await image_context(session, uid, fid, gid)
        dishes = list(
            {
                recipe_image_key(d): deepcopy(d)
                for entries in row.progress["tiers"].values()
                for e in entries
                for m in e["meals"]
                for d in m["dishes"]
            }.values()
        )
    failed = 0
    for offset in range(0, len(dishes), 3):
        await context.raise_if_cancelled()
        batch = dishes[offset : offset + 3]
        async with pg_manager.get_async_session_context() as session:
            _, current = await image_context(session, uid, fid, gid)
            from yuxi.services.exclusive_reference_plan import verified_reference_document
            from yuxi.services.daily_dish_swap_service import require_recipe_quotes
            from yuxi.services.reference_meal_plan_service import (
                reference_member_restrictions,
                reference_restriction_conflict,
            )

            for dish in batch:
                document = await verified_reference_document(session, current, dish)
                require_recipe_quotes(dish, document)
                if reference_restriction_conflict(
                    document["content"], reference_member_restrictions(current["current"]["members"])
                ):
                    raise HealthVisionError("source_invalidated", "菜谱不符合当前限制", 410)
        results = await prepare_recipe_images([{"dishes": batch}])
        failed += sum(not result for result in results)
        await context.set_progress(min(offset + 3, len(dishes)) / max(len(dishes), 1) * 100, "正在补齐菜品图片")
    if failed:
        raise RuntimeError("Exclusive recipe images incomplete; retry missing images")
    return {"group_id": gid, "dish_count": len(dishes)}


async def cached_plan_images(dishes):
    """按来源键去重并限制对象存储并发，缺图保留明确空值。"""
    unique = {recipe_image_key(d): d for d in dishes}
    semaphore = asyncio.Semaphore(6)

    async def read(key, dish):
        """单份图只查询一次，不触发生成。"""
        async with semaphore:
            return key, await generated_recipe_image(dish, strict=True)

    found = dict(await asyncio.gather(*(read(k, d) for k, d in unique.items())))
    return [{"file_id": d["file_id"], **found[recipe_image_key(d)]} for d in unique.values()]


async def queue_plan_images(session, row):
    """由菜单发布或显式补图事务创建任务意图，提交后再投递。"""
    payload = {"uid": row.actor_uid, "family_id": row.family_id, "group_id": row.id}
    return await tasker.create_unique_in_session(
        session,
        name="补齐专属计划菜品图片",
        task_type="exclusive_recipe_images_v1",
        payload=payload,
        payload_match={"group_id": row.id},
        timeout_seconds=7200,
    )


async def image_context(session, uid, fid, gid):
    """后台与HTTP都重验家庭访问、计划归属及当前成员授权依据。"""
    repo = ExclusivePlanRepository(session, uid, fid)
    await repo.context()
    row = await repo.find(group_id=gid)
    if row is None or row.status != "ready" or row.policy != PREVIEW_POLICY:
        raise HealthVisionError("not_found", "计划不存在或尚未就绪", 404)
    current = await exclusive_context(session, uid, fid, row.policy, load_documents=False)
    if current["basis_hash"] != row.basis_hash:
        raise HealthVisionError("source_invalidated", "计划依据已变化，请重新准备", 410)
    return row, current

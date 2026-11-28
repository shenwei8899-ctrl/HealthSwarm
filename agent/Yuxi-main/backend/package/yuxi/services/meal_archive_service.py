"""我的餐单按当前家庭权限读取最新成功日快照。"""

import asyncio
import copy
import re

from fastapi import HTTPException
from yuxi.repositories.meal_archive_repository import (
    archive_family_visible,
    archive_row,
    archive_rows,
    archive_source_cache,
    stored_meal,
)
from yuxi.services.daily_meal_plan_service import MEALS
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.services.recipe_image_identity import recipe_image_key
from yuxi.services.reference_recipe_presentation import stored_recipe_image
from yuxi.storage.postgres.manager import pg_manager
from yuxi.utils import logger

ARCHIVE_IMAGE_TIMEOUT_SECONDS = 1.0


async def list_meal_archive(uid, family_id, *, before=None, limit=20):
    """读取日期倒序的成功餐单，不触发生成或专业采用。"""
    async with pg_manager.get_async_session_context() as session:
        if not await archive_family_visible(session, uid, family_id):
            raise HTTPException(404, "家庭不存在或不可访问")
        rows = await archive_rows(session, uid, family_id, before=before, limit=limit)
        return {
            "plans": await archive_with_images(session, rows[:limit]),
            "next_before": rows[limit - 1].plan_date.isoformat() if len(rows) > limit else None,
        }


async def read_meal_archive(uid, family_id, day):
    """历史展示不受商品库存和当前模型状态影响。"""
    async with pg_manager.get_async_session_context() as session:
        row = await archive_row(session, uid, family_id, day)
        if row is None or not row.archive_meals:
            raise HealthVisionError("meal_archive_absent", "这一天还没有已生成的餐单", 404)
        return (await archive_with_images(session, [row]))[0]


def archive_response(row):
    """响应只含归档展示，不暴露来源证明、请求或健康档案。"""
    return {
        "id": row.id,
        "family_id": row.family_id,
        "plan_date": str(row.plan_date),
        "version": row.version,
        "meals": [copy.deepcopy(row.archive_meals[kind]) for kind in MEALS if kind in row.archive_meals],
    }


async def archive_with_images(session, rows):
    """给已授权的保存餐单补充现成图片，不生成图片或回写历史快照。"""
    plans = [archive_response(row) for row in rows]
    needs_sources = any(
        not dish.get("recipe_image_key") for plan in plans for meal in plan["meals"] for dish in meal.get("dishes", [])
    )
    cache = await archive_source_cache(session, rows) if needs_sources else {}
    pending = {}
    for row, plan in zip(rows, plans, strict=True):
        for meal in plan["meals"]:
            kind = meal["meal_type"]
            saved = None
            for dish in meal.get("dishes", []):
                key = dish.pop("recipe_image_key", None)
                if not key:
                    ref = (row.meal_sources or {}).get(kind)
                    if (
                        ref
                        and ref.get("kind") == "selection"
                        and any(origin.get("frozen") for origin in ref.get("dish_sources", []))
                    ):
                        continue
                    if ref:
                        if saved is None:
                            saved = (
                                await stored_meal(
                                    session,
                                    row.family_id,
                                    row.plan_date,
                                    ref,
                                    kind,
                                    cache=cache,
                                )
                                or {}
                            )
                        originals = [
                            item
                            for item in saved.get("dishes", [])
                            if all(
                                item.get(field) == dish.get(field)
                                for field in (
                                    "file_id",
                                    "chunk_id",
                                    "name",
                                    "ingredients",
                                    "steps",
                                )
                            )
                            and item.get("source")
                        ]
                        if len(originals) == 1:
                            key = recipe_image_key(originals[0])
                if isinstance(key, str) and re.fullmatch(r"recipe-illustrations/gpt-v1/[0-9a-f]{64}\.webp", key):
                    pending.setdefault(key, []).append(dish)
    semaphore = asyncio.Semaphore(6)

    async def attach(key, dishes):
        """同一图片只查询一次，失败时保留快照已有图片。"""
        async with semaphore:
            image = await stored_recipe_image(key)
        for dish in dishes:
            dish.update(image)

    if pending:
        try:
            await asyncio.wait_for(
                asyncio.gather(*(attach(key, dishes) for key, dishes in pending.items())),
                timeout=ARCHIVE_IMAGE_TIMEOUT_SECONDS,
            )
        except TimeoutError:
            logger.warning("Archive image lookup timed out: image_count={}", len(pending))
    return plans

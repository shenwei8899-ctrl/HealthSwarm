"""按日浏览：授权始终新查，原谱仅在绑定版本变化后重验。"""

from datetime import date

import asyncio
from collections import defaultdict
from pydantic import ValidationError
from minio.error import S3Error
from urllib3.exceptions import HTTPError as StorageHTTPError

from yuxi.repositories.exclusive_plan_browse_repository import ExclusivePlanBrowseRepository
from yuxi.services.exclusive_plan_types import EXCLUSIVE_PLAN_DAYS
from yuxi.services.exclusive_plan_service import PREVIEW_POLICY, exclusive_context, TIERS
from yuxi.services.exclusive_reference_plan import TIER_TARGETS, summarize_reference_prices, validate_reference_day
from yuxi.services.health_nutrition_service import input_fingerprint
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.services.recipe_translation_service import translation_key, checked_chinese_display
from yuxi.knowledge.utils.kb_utils import parse_minio_url
from yuxi.storage.minio import StorageError, get_minio_client
from yuxi.storage.postgres.manager import pg_manager


async def read_plan_summary(uid, fid, gid=None):
    """列表展示已发布摘要；当前权限和整体依据仍逐次检查。"""
    async with pg_manager.get_async_session_context() as session:
        repo = ExclusivePlanBrowseRepository(session, uid, fid)
        row = await repo.summary(gid)
        if row is None:
            return {"status": "empty", "group_id": None, "plans": []}
        if row["policy"] == PREVIEW_POLICY and row["status"] == "ready":
            context = await exclusive_context(
                session,
                uid,
                fid,
                row["policy"],
                day=date.fromisoformat(row["selection"]["plan_date"]),
                start_date=row["selection"]["plan_date"],
                load_documents=False,
            )
            from yuxi.services.diet_stage_plan_history import historical_goal_context

            context = await historical_goal_context(
                session, context, row.get("sources"), row["policy"], row["selection"]["plan_date"])
            valid = context["basis_hash"] == row["basis_hash"]
            tiers = row["tiers"] or {}
            complete = all(
                [entry.get("day", {}).get("day_no") for entry in tiers.get(tier) or []]
                == list(range(1, EXCLUSIVE_PLAN_DAYS + 1))
                for tier in TIERS
            )
            plans = (
                [
                    {
                        "tier_code": tier,
                        "tier_name": name,
                        "difference": TIER_TARGETS[tier],
                        "pricing": summarize_reference_prices(tiers[tier], include_gaps=False),
                        "tier_cost_status": "unverified",
                    }
                    for tier, name in TIERS.items()
                ]
                if row["status"] == "ready" and valid and complete
                else []
            )
            return {
                "group_id": row["id"],
                "status": (
                    ("stale" if row["status"] == "ready" and not complete else row["status"]) if valid else "stale"
                ),
                "plans": plans,
                "preview_only": True,
                "completed_days": sum(len(d) for d in (row["tiers"] or {}).values()),
                "total_days": EXCLUSIVE_PLAN_DAYS * len(TIERS),
                "period_days": EXCLUSIVE_PLAN_DAYS,
                "members": [{"member_ref": hid, "name": s["name"]} for hid, s in context["sources"]["members"].items()],
                "error": row["error"],
            }

    # 完整读取拥有独立事务；外层家庭行锁释放后才能调用，并固定已选推荐组。
    from yuxi.services.exclusive_plan_service import read_exclusive_plan

    return await read_exclusive_plan(uid, fid, row["id"])

async def read_plan_directory(uid, fid, gid, tier):
    """目录只核对授权、整体依据和数据库来源版本，不读取对象原文。"""
    async with pg_manager.get_async_session_context() as session:
        repo, header, context = await browse_context(session, uid, fid, gid, tier)
        sources = await source_metadata(repo, header["days"], context)
        days = []
        for day in header["days"]:
            fingerprints = [sources.get(source_key(s)) for s in day["sources"] or []]
            days.append(
                {k: day[k] for k in ("day_no", "plan_date", "content_version")}
                | {
                    "version": input_fingerprint(fingerprints),
                    "available": all(source_matches(s, sources.get(source_key(s))) for s in day["sources"] or []),
                }
            )
        return {
            "group_id": gid,
            "tier_code": tier,
            "tier_name": TIERS[tier],
            "period_days": EXCLUSIVE_PLAN_DAYS,
            "days": days,
            "version": input_fingerprint([header["basis_hash"], days]),
        }


async def read_plan_day(uid, fid, gid, tier, number, known_version=None, *, for_images=False):
    """对象元数据也属于版本；删除或旁路覆盖不能沿用上次通过回执。"""
    async with pg_manager.get_async_session_context() as session:
        repo, header, context = await browse_context(session, uid, fid, gid, tier)
        day = next((d for d in header["days"] if d["day_no"] == number), None)
        if day is None:
            raise HealthVisionError("not_found", "计划日期不存在", 404)
        sources = await source_metadata(repo, [day], context)
        for source in day["sources"] or []:
            if not source_matches(source, sources.get(source_key(source))):
                raise HealthVisionError("source_invalidated", "当天菜谱来源已变化，请更新计划", 410)
        objects = await source_objects(sources)
        entry = await repo.day(gid, tier, number)
        # 译文属于展示版本；译文改变也不能返回客户端的旧内容。
        dishes = [d for m in entry["meals"] for d in m["dishes"]]
        translations = await repo.translations([translation_key(d) for d in dishes])
        displays = []
        preserved = {
            id(d) for meal in entry["meals"]
            if meal["meal_type"] in entry.get("roster_preserved_meals", []) for d in meal["dishes"]
        }
        for dish in dishes:
            if id(dish) in preserved:
                displays.append(None)
                continue
            record = translations.get(translation_key(dish))
            try:
                displays.append(
                    checked_chinese_display(dish, record.display)
                    if record is not None and record.source == dish["source"]
                    else None
                )
            except (HealthVisionError, ValidationError):
                displays.append(None)
        version = input_fingerprint(
            {
                "validator": "exclusive-day-v1",
                "basis": header["basis_hash"],
                "entry": entry,
                "sources": [[list(k), v] for k, v in sorted(sources.items())],
                "objects": objects,
                "displays": displays,
            }
        )
        receipt = await repo.receipt(gid, tier, number)
        if receipt is None or receipt.version != version:
            await prepare_documents(context, sources, objects)
            await validate_reference_day(session, context, entry, require_translation=False)
            await repo.verified(gid, tier, number, version)
        if for_images:
            return {"raw_dishes": dishes}
        if known_version == version:
            return {"unchanged": True, "day_no": number, "version": version}
        projected = []
        for dish, display in zip(dishes, displays):
            visible = display or dish
            meal_type = next(m["meal_type"] for m in entry["meals"] if dish in m["dishes"])
            projected.append(
                {
                    "id": meal_type + ":" + dish["file_id"],
                    "meal_type": meal_type,
                    "recipe_name": visible["name"],
                    "ingredients": visible["ingredients"],
                    "steps": visible["steps"],
                    "source": dish["source"],
                    "portion_note": dish.get("portion_note"),
                    "roster_preserved": meal_type in entry.get("roster_preserved_meals", []),
                    "recipe_snapshot": {k: dish.get(k) for k in ("image_url", "cooking_minutes", "source")},
                }
            )
            if (
                display is None and id(dish) not in preserved
                and sources.get(source_key(dish), {}).get("search_excluded")
            ):
                projected[-1].update(
                    recipe_name="菜谱暂不可展示",
                    ingredients=[],
                    steps=[],
                    portion_note=None,
                    recipe_snapshot={},
                    translation_status="unavailable",
                )
        return {"unchanged": False, "version": version, "day_no": number, "day": {**entry["day"], "meals": projected}}


async def browse_context(session, uid, fid, gid, tier):
    """任何缓存命中之前都检查当前家庭、成员授权及原计划依据。"""
    if tier not in TIERS:
        raise HealthVisionError("not_found", "计划档位不存在", 404)
    repo = ExclusivePlanBrowseRepository(session, uid, fid)
    header = await repo.header(gid, tier)
    if (
        header["status"] != "ready"
        or header["policy"] != PREVIEW_POLICY
        or [day["day_no"] for day in header["days"] or []] != list(range(1, EXCLUSIVE_PLAN_DAYS + 1))
    ):
        raise HealthVisionError("exclusive_preview_unavailable", "计划尚未就绪，请返回计划页", 409)
    try:
        context = await exclusive_context(
            session,
            uid,
            fid,
            header["policy"],
            day=date.fromisoformat(header["selection"]["plan_date"]),
            start_date=header["selection"]["plan_date"],
            load_documents=False,
        )
    except HealthVisionError as error:
        if error.status in (409, 410, 422):
            raise HealthVisionError("plan_basis_changed", error.message, error.status) from None
        raise
    from yuxi.services.diet_stage_plan_history import historical_goal_context

    context = await historical_goal_context(
        session, context, header.get("sources"), header["policy"], header["selection"]["plan_date"])
    if context["basis_hash"] != header["basis_hash"]:
        raise HealthVisionError("plan_basis_changed", "成员资料或计划依据已变化，请重新核对计划", 410)
    return repo, header, context


async def source_metadata(repo, days, context):
    """批量比对真实内容指纹，分片变化不依赖更新时间是否前进。"""
    references = [s for day in days for s in day["sources"] or []]
    ids = {s["file_id"] for s in references}
    kb_ids = context["current"]["sources"]["recipe_kb_ids"]
    files, chunks = await repo.sources(ids, kb_ids)
    grouped = defaultdict(list)
    for chunk in chunks:
        grouped[chunk.file_id].append(chunk)
    result = {}
    for file in files:
        parts = grouped[file.file_id]
        if (
            file.status != "indexed"
            or file.is_folder
            or not file.content_hash
            or not parts
            or not (file.minio_url or file.path)
        ):
            continue
        signature = input_fingerprint([(c.chunk_id, c.content) for c in parts])
        for chunk in parts:
            if chunk.kb_id != file.kb_id:
                continue
            result[(file.file_id, chunk.chunk_id)] = {
                "file_id": file.file_id,
                "chunk_id": chunk.chunk_id,
                "kb_id": file.kb_id,
                "filename": file.filename,
                "file_hash": file.content_hash,
                "chunks_hash": signature,
                "path": file.minio_url or file.path,
            }
            result[(file.file_id, chunk.chunk_id)]["search_excluded"] = bool(
                (file.processing_params or {}).get("recipe_search_excluded")
            )
    return result


def source_key(source):
    """缓存身份始终包含文件及分片。"""
    return source["file_id"], source["chunk_id"]


def source_matches(expected, actual):
    """来源失效只影响引用该来源的日期。"""
    return actual is not None and all(
        expected.get(k) == actual.get(k)
        for k in ("file_id", "chunk_id", "kb_id", "filename", "file_hash", "chunks_hash")
    )


async def source_objects(sources):
    """只对当天原谱做有界并发 HEAD；数据库会话不参与并发操作。"""
    semaphore = asyncio.Semaphore(6)
    client = get_minio_client().client

    async def inspect(path):
        """缺失对象必须拒绝旧缓存，不能伪装为未变化。"""
        async with semaphore:
            try:
                bucket, key = parse_minio_url(path)
                stat = await asyncio.to_thread(client.stat_object, bucket, key)
                return path, {
                    "etag": stat.etag,
                    "version_id": stat.version_id,
                    "size": stat.size,
                    "modified": str(stat.last_modified),
                }
            except (StorageError, S3Error, OSError, ValueError):
                raise HealthVisionError("reference_source_unavailable", "当天菜谱原文暂不可读取", 410) from None
            except StorageHTTPError:
                raise HealthVisionError("storage_unavailable", "原文存储暂时无法连接，请稍后重试", 503) from None

    return dict(await asyncio.gather(*(inspect(path) for path in {s["path"] for s in sources.values()})))


async def prepare_documents(context, sources, objects):
    """冷缓存只下载当天原文，同一文件的不同分片共用一次读取。"""
    import hashlib

    semaphore = asyncio.Semaphore(6)

    async def download(path):
        """原始字节必须与数据库记录的完整内容哈希一致。"""
        async with semaphore:
            bucket, key = parse_minio_url(path)
            try:
                raw = await get_minio_client().adownload_file(bucket, key)
                expected = next(s["file_hash"] for s in sources.values() if s["path"] == path)
                if len(raw) > 65536 or hashlib.sha256(raw).hexdigest() != expected:
                    raise ValueError("source hash mismatch")
                return path, raw.decode("utf-8")
            except (ValueError, UnicodeError, OSError, StorageError):
                raise HealthVisionError("reference_source_unavailable", "当天菜谱原文无法核对", 410) from None

    contents = dict(await asyncio.gather(*(download(path) for path in objects)))
    context["verified_documents"] = {
        key: {**source, "scope": "reference_recipe", "content": contents[source["path"]]}
        for key, source in sources.items()
    }

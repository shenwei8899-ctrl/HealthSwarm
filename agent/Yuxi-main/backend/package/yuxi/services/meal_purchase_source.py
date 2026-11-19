"""采购读取已发布快照和数据库版本；展示装配与原文件下载不参与采购。"""

import copy
import json

from yuxi.services.health_nutrition_service import input_fingerprint
from yuxi.services.health_vision_types import HealthVisionError


async def selected_purchase_origins(session, uid, family_id, day, meal_type, version, keys):
    """从当前共享索引解析本次选择，其他餐次不参与。"""
    from yuxi.services.daily_meal_plan_service import current_row
    from yuxi.services.meal_dish_service import dish_key
    from yuxi.storage.postgres.models_health import HealthDailyArrangement, HealthInitialPlanPreview

    row = await current_row(session, uid, family_id, day)
    if row is None or row.version != version:
        raise HealthVisionError("daily_plan_version_changed", "餐单已更新，请重新打开采购", 409)
    ref = (row.meal_sources or {}).get(meal_type)
    if not ref or len(keys) != len(set(keys)):
        raise HealthVisionError("dish_scope_invalid", "采购菜品不属于本餐，请重新读取", 422)
    if ref["kind"] == "selection":
        origins = ref.get("dish_sources", [])
    else:
        model = HealthInitialPlanPreview if ref["kind"] == "reference" else HealthDailyArrangement
        saved = await session.get(model, ref["id"])
        meal = next(
            (
                m
                for m in (saved.snapshot if saved else {}).get("meals", [])
                if m.get("meal_type", m.get("type")) == meal_type
            ),
            {},
        )
        origins = [
            {"source": ref, "date": str(day), "meal_type": meal_type, "dish_key": dish_key(d)}
            for d in meal.get("dishes", [])
        ]
    if not origins or any(k not in {o["dish_key"] for o in origins} for k in keys):
        raise HealthVisionError("dish_scope_invalid", "采购菜品不属于本餐，请重新读取", 422)
    resolved, cache = [], {}
    for origin in origins:
        if keys and origin["dish_key"] not in keys:
            continue
        result = await purchase_origin(session, uid, family_id, origin, cache)
        if ref["kind"] == "selection" and {m["id"] for m in result[2]} != set(ref.get("member_ids", [])):
            raise HealthVisionError("dish_members_changed", "就餐成员已有变化，请重新读取餐单", 409)
        dish = copy.deepcopy(result[0])
        dish.update(dish_key=origin["dish_key"], origin=origin)
        resolved.append((dish, *result[1:]))
    return resolved


async def purchase_origin(session, uid, family_id, origin, cache):
    """沿用来源授权并复用本请求中已核对的发布快照。"""
    from yuxi.services.meal_dish_service import dish_key, read_origin
    from yuxi.storage.postgres.models_health import HealthInitialPlanPreview

    ref = origin["source"]
    if ref["kind"] == "formal":
        # 正式营养审核仍由其原 Owner 校验；同一请求内每个来源只校验一次。
        key = input_fingerprint(origin.get("frozen") or [ref, origin["date"], origin["meal_type"]])
        if key not in cache:
            cache[key] = await read_origin(session, uid, family_id, origin)
        _, meal, members, source = cache[key]
        dish = next((d for d in meal.get("dishes", []) if dish_key(d) == origin["dish_key"]), None)
        if dish:
            from yuxi.storage.postgres.models_health import HealthRecipeCommerceSource

            mapping = await session.get(HealthRecipeCommerceSource, dish["recipeVersion"])
            if mapping is None:
                raise HealthVisionError("dish_mapping_missing", "该菜品的食材采购映射尚未发布", 409)
            source = {
                **source,
                "procurement_mapping": {
                    "recipe_hash": mapping.recipe_hash,
                    "ingredient_codes": mapping.ingredient_codes,
                },
            }
    elif ref["kind"] == "reference":
        key = ("reference", ref["id"])
        if key not in cache:
            saved = await session.get(HealthInitialPlanPreview, ref["id"])
            cache[key] = await published_reference(session, family_id, origin["date"], saved)
        source = cache[key]
        meal = next((m for m in source["meals"] if m.get("meal_type", m.get("type")) == origin["meal_type"]), {})
        members = meal.get("members", source.get("members", []))
        dish = next((d for d in meal.get("dishes", []) if dish_key(d) == origin["dish_key"]), None)
        if dish:
            await recipe_metadata(session, dish, source.get("purchase_restrictions", []))
    elif ref["kind"] == "replacement":
        from yuxi.services.daily_dish_swap_service import meal_context

        _, _, members, _ = await purchase_origin(session, uid, family_id, origin["anchor"], cache)
        saved = origin["snapshot"]
        context = await meal_context(
            session, origin["actor_uid"], family_id, origin["date"], origin["meal_type"], members
        )
        if {"memory": {}, **context["sources"]} != {"memory": {}, **saved["context_sources"]}:
            raise HealthVisionError("dish_members_changed", "就餐成员资料已变化，请重新核对餐单", 409)
        dish = saved["dish"]
        await recipe_metadata(session, dish)
        members = context["members"]
        meal = {"meal_type": origin["meal_type"], "dishes": [dish], "members": members}
        source = {**saved, "meals": [meal], "members": members, "source_owner": origin["actor_uid"]}
    else:
        raise HealthVisionError("dish_source_invalid", "菜谱来源无法读取", 409)
    if dish is None:
        raise HealthVisionError("dish_source_changed", "原餐单已没有这道菜，请重新读取", 409)
    return copy.deepcopy(dish), meal, members, source


async def published_reference(session, family_id, day, saved):
    """核对最终采用结果与当前授权绑定，不重播展示工具。"""
    from yuxi.services.health_consultation_service import require_consultation
    from yuxi.repositories.health_task_repository import HealthTaskRepository
    from yuxi.services.reference_meal_plan_types import REFERENCE_CATALOG_CHAIN_VERSION
    from yuxi.storage.postgres.models_business import AgentRun

    if (
        saved is None
        or saved.selection.get("family_id") != family_id
        or saved.selection.get("plan_date") != str(day)
        or saved.selection.get("mode") != "reference"
        or saved.snapshot.get("catalog_chain_version") != REFERENCE_CATALOG_CHAIN_VERSION
    ):
        raise HealthVisionError("dish_source_changed", "餐单来源已变化，请重新安排", 409)
    run = await session.get(AgentRun, saved.run_id)
    if (
        run is None
        or run.uid != saved.actor_uid
        or run.status != "completed"
        or run.conversation_id != saved.conversation_id
        or run.agent_slug != "health-meal-planner"
    ):
        raise HealthVisionError("reference_not_completed", "参考餐单尚未完成发布", 409)
    # 保留处理配置、用途同意和当前档案授权；不重播搜索/原文/媒体工具回执。
    binding, _ = await require_consultation(
        session, run.uid, run.conversation_thread_id, expected=(run.input_payload or {}).get("health_processing") or {}
    )
    fixed = binding.initial_planner_selection or {}
    if (
        saved.conversation_id != binding.conversation_id
        or saved.member_id != binding.member_id
        or saved.selection != fixed.get("selection")
        or input_fingerprint(saved.snapshot.get("sources")) != fixed.get("source_hash")
        or any(
            saved.snapshot.get(key) != value
            for key, value in {
                "scope": "daily_reference",
                "status": "reference_ready",
                "professional_status": "not_reviewed",
                "nutrition_status": "not_calculated",
            }.items()
        )
    ):
        raise HealthVisionError("reference_receipt_invalid", "参考餐单的授权来源不一致，请重新安排", 409)
    message = await HealthTaskRepository(session).final_message(run)
    try:
        adopted = json.loads(message.content)
        valid = adopted.get("preview_id") == saved.id
    except (AttributeError, TypeError, ValueError):
        valid = False
    if not valid:
        raise HealthVisionError("reference_receipt_invalid", "该参考结果未被当前运行最终采用", 409)
    from yuxi.services.reference_meal_plan_service import bound_reference_context, reference_member_restrictions
    from yuxi.services.health_memory_context_service import memory_restrictions_for_plan

    current = await bound_reference_context(session, run.uid, binding)
    restrictions = reference_member_restrictions(current["members"]) + await memory_restrictions_for_plan(
        session, run, binding, current
    )
    return {**saved.snapshot, "source_owner": saved.actor_uid, "purchase_restrictions": restrictions}


async def recipe_metadata(session, dish, restrictions=()):
    """只比较所选菜谱的文件与分片版本。"""
    from yuxi.services.health_family_kb_service import configured_health_kb_ids
    from yuxi.repositories.meal_purchase_repository import recipe_version

    file, chunks = await recipe_version(session, dish["file_id"], configured_health_kb_ids("health-meal-planner"))
    expected = dish.get("source", {})
    if (
        file is None
        or file.is_folder
        or file.status != "indexed"
        or file.kb_id != expected.get("kb_id")
        or file.content_hash != expected.get("file_hash")
    ):
        raise HealthVisionError("dish_source_changed", "菜谱来源版本已变化，请重新安排", 409)
    if not any(c.chunk_id == dish["chunk_id"] for c in chunks) or input_fingerprint(
        [(c.chunk_id, c.content) for c in chunks]
    ) != expected.get("chunks_hash"):
        raise HealthVisionError("dish_source_changed", "菜谱分片版本已变化，请重新安排", 409)
    from yuxi.services.reference_meal_plan_service import reference_restriction_conflict

    if reference_restriction_conflict("\n".join(c.content for c in chunks), restrictions):
        raise HealthVisionError("reference_restriction_conflict", "所选菜谱含当前明确限制的食材", 422)

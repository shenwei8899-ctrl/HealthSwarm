"""每日计划的当前餐次引用；来源内容和授权仍由原业务服务拥有。"""

from uuid import uuid4

from sqlalchemy import select, text

from yuxi.repositories.daily_arrangement_repository import DailyArrangementRepository
from yuxi.services.family_service import FamilyService
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_health import HealthDailyMealPlan, HealthInitialPlanPreview
from yuxi.utils.datetime_utils import utc_now_naive

MEALS = ("breakfast", "lunch", "dinner")


async def current_row(session, uid, family_id, day, *, lock=False):
    """以账号、家庭和日期定位当前引用，写入时串行化并发首次创建。"""
    if lock:
        await session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
            {"key": f"daily-meal-plan:{uid}:{family_id}:{day}"},
        )
    await FamilyService(session, uid).context(family_id)
    return await session.scalar(
        select(HealthDailyMealPlan).where(
            HealthDailyMealPlan.actor_uid == uid,
            HealthDailyMealPlan.family_id == family_id,
            HealthDailyMealPlan.plan_date == day,
        )
    )


async def legacy_sources(session, uid, family_id, day):
    """没有关联记录时读取已有正式安排或最近完成的参考结果。"""
    from yuxi.services.daily_arrangement_service import authorize_sources
    from yuxi.services.reference_meal_plan_service import read_reference_plan_in_session
    from yuxi.repositories.health_task_repository import HealthTaskRepository
    from yuxi.storage.postgres.models_business import AgentRun
    import json

    _, arrangement = await DailyArrangementRepository(session, uid, family_id).context(day)
    if arrangement and arrangement.snapshot and arrangement.snapshot.get("status") == "ready":
        await authorize_sources(session, uid, arrangement, published=True)
        source = {"kind": "formal", "id": arrangement.id, "version": arrangement.snapshot["version"]}
        return {meal["type"]: source for meal in arrangement.snapshot["meals"]}

    runs = (
        (
            await session.scalars(
                select(AgentRun)
                .join(HealthInitialPlanPreview, AgentRun.id == HealthInitialPlanPreview.run_id)
                .where(
                    HealthInitialPlanPreview.actor_uid == uid,
                    AgentRun.status == "completed",
                    HealthInitialPlanPreview.selection["mode"].as_string() == "reference",
                    HealthInitialPlanPreview.selection["family_id"].as_string() == family_id,
                    HealthInitialPlanPreview.selection["plan_date"].as_string() == day.isoformat(),
                )
                .order_by(AgentRun.finished_at.desc().nullslast(), AgentRun.created_at.desc(), AgentRun.id.desc())
            )
        )
        .unique()
        .all()
    )
    for run in runs:
        message = await HealthTaskRepository(session).final_message(run)
        preview_id = json.loads(message.content).get("preview_id")
        if preview_id:
            _, plan = await read_reference_plan_in_session(session, uid, preview_id)
            return {meal["meal_type"]: {"kind": "reference", "id": preview_id} for meal in plan["meals"]}
    return {}


async def read_current_plan(uid, family_id, day):
    """回读每个来源并重验权限，结果不会触发模型或写入。"""
    from yuxi.services.daily_arrangement_service import authorize_sources
    from yuxi.services.reference_meal_plan_service import read_reference_plan_in_session

    async with pg_manager.get_async_session_context() as session:
        row = await current_row(session, uid, family_id, day)
        refs = dict(row.meal_sources) if row else await legacy_sources(session, uid, family_id, day)
        sources, meals = {}, []
        for kind in MEALS:
            ref = refs.get(kind)
            if not ref:
                continue
            key = (ref["kind"], ref["id"], ref.get("version"))
            if key not in sources:
                if ref["kind"] == "reference":
                    _, source = await read_reference_plan_in_session(session, uid, ref["id"])
                    if (
                        source.get("plan_date") != day.isoformat()
                        or source.get("sources", {}).get("family_id") != family_id
                    ):
                        raise HealthVisionError("daily_plan_source_invalid", "餐单日期或家庭不一致", 409)
                elif ref["kind"] == "formal":
                    _, arrangement = await DailyArrangementRepository(session, uid, family_id).context(day)
                    if (
                        not arrangement
                        or arrangement.id != ref["id"]
                        or not arrangement.snapshot
                        or arrangement.snapshot.get("version") != ref.get("version")
                    ):
                        raise HealthVisionError("daily_plan_source_changed", "今日计划来源已变化，请重新核对", 409)
                    await authorize_sources(session, uid, arrangement, published=True)
                    source = arrangement.snapshot
                else:
                    raise HealthVisionError("daily_plan_source_invalid", "今日计划来源无法核对", 409)
                sources[key] = source
            source = sources[key]
            meal = next((item for item in source["meals"] if item.get("meal_type", item.get("type")) == kind), None)
            if meal is None:
                raise HealthVisionError("daily_plan_source_invalid", "今日计划餐次无法核对", 409)
            meals.append(
                {
                    "meal_type": kind,
                    "source": ref,
                    "meal": meal,
                    "members": meal.get("members", source.get("members", [])),
                }
            )
        purchase_options = []
        for key, source in sources.items():
            selected = {
                item["meal_type"]
                for item in meals
                if item["source"]["kind"] == key[0] and item["source"]["id"] == key[1]
            }
            original = {item.get("meal_type", item.get("type")) for item in source["meals"]}
            if key[0] == "reference" and source.get("purchase_items"):
                from yuxi.services.reference_meal_plan_service import select_reference_purchase_items

                items = select_reference_purchase_items(source, sorted(selected))
                ingredients = {
                    ingredient
                    for meal in source["meals"]
                    if meal["meal_type"] in selected
                    for dish in meal["dishes"]
                    for ingredient in dish["ingredients"]
                }
                if not items:
                    continue
                purchase_options.append(
                    {
                        "kind": "reference",
                        "id": key[1],
                        "meal_types": sorted(selected),
                        "items": items,
                        "gaps": [gap for gap in source.get("purchase_gaps", []) if gap["ingredient"] in ingredients],
                        "quantity_notice": "数量沿用原餐单的采购建议，可能包含其他餐次份量，请核对包装数量。"
                        if selected != original
                        else "请核对商品与包装数量。",
                    }
                )
            if key[0] == "formal" and len(selected) == 3 and selected == original:
                purchase_options.append(
                    {"kind": "formal", "id": key[1], "version": key[2], "meal_types": sorted(selected)}
                )
        formal = None
        if len(sources) == 1 and len(meals) == 3:
            key, source = next(iter(sources.items()))
            if key[0] == "formal":
                formal = source
        pending = await pending_request(session, row) if row else None
        return {
            "status": "ready" if meals else "absent",
            "id": row.id if row else None,
            "version": row.version if row else 0,
            "date": day.isoformat(),
            "meals": meals,
            "formal_arrangement": formal,
            "purchase_options": purchase_options,
            "pending": pending,
        }


async def pending_request(session, row):
    """请求与运行表持有终态；索引只保存可恢复的请求身份。"""
    from yuxi.storage.postgres.models_business import AgentRun, AgentRunRequest

    saved = row.pending or {}
    if not saved.get("request_id"):
        return None
    request = await session.scalar(select(AgentRunRequest).where(AgentRunRequest.request_id == saved["request_id"]))
    if request is None or request.uid != row.actor_uid or request.conversation_thread_id != saved.get("thread_id"):
        raise HealthVisionError("daily_plan_request_invalid", "饮食计划请求无法核对", 409)
    run = await session.get(AgentRun, request.dispatched_run_id) if request.dispatched_run_id else None
    status = run.status if run is not None else request.status
    result = {"request_id": request.request_id, "thread_id": request.conversation_thread_id, "status": status}
    if status == "completed":
        from yuxi.services.health_task_service import read_health_task_in_session

        task = await read_health_task_in_session(session, row.actor_uid, request.request_id)
        if task.result and task.result.result_type == "needs_input":
            result.update(
                status="needs_input",
                questions=task.result.questions,
                member_id=task.member_id,
                selection=saved.get("selection"),
            )
    return result


async def reserve_reference_request(session, uid, binding, request):
    """同一账号、家庭、日期只登记一个未结束的计划任务。"""
    from datetime import date
    from yuxi.services.reference_meal_plan_service import reference_binding

    if not reference_binding(binding):
        return
    selection = binding.initial_planner_selection["selection"]
    base = selection.get("daily_base_version")
    if base is None:
        return
    day, family_id = date.fromisoformat(selection["plan_date"]), selection["family_id"]
    row = await current_row(session, uid, family_id, day, lock=True)
    if (row.version if row else 0) != base:
        raise HealthVisionError("daily_plan_version_changed", "饮食计划已更新，请重新读取后操作", 409)
    if row:
        pending = await pending_request(session, row)
        if (
            pending
            and pending["request_id"] != request.request_id
            and pending["status"] in {"queued", "dispatched", "pending", "running", "cancel_requested"}
        ):
            raise HealthVisionError("daily_plan_busy", "该日饮食计划正在生成，请读取已有任务", 423)
    else:
        refs = await legacy_sources(session, uid, family_id, day)
        row = HealthDailyMealPlan(
            id=str(uuid4()), actor_uid=uid, family_id=family_id, plan_date=day, version=0, meal_sources=refs, pending={}
        )
        session.add(row)
    row.pending = {
        "request_id": request.request_id,
        "thread_id": request.conversation_thread_id,
        "selection": selection,
    }


async def require_current_reference_purchase(session, uid, daily, preview_id, plan):
    """采购餐次必须仍属于当前每日版本的同一参考来源。"""
    from datetime import date

    day = date.fromisoformat(daily["date"])
    if plan["plan_date"] != daily["date"] or plan["sources"]["family_id"] != daily["family_id"]:
        raise HealthVisionError("daily_plan_source_invalid", "采购餐单日期或家庭不符", 409)
    row = await current_row(session, uid, daily["family_id"], day)
    if (row.version if row else 0) != daily["version"]:
        raise HealthVisionError("daily_plan_version_changed", "饮食计划已更新，请重新核对采购", 409)
    refs = dict(row.meal_sources) if row else await legacy_sources(session, uid, daily["family_id"], day)
    selected = {meal for meal, ref in refs.items() if ref.get("kind") == "reference" and ref.get("id") == preview_id}
    requested = daily.get("meal_types", [])
    if (
        not requested
        or len(requested) != len(set(requested))
        or not set(requested).issubset(selected)
        or not selected.issubset({meal["meal_type"] for meal in plan["meals"]})
    ):
        raise HealthVisionError("daily_plan_source_changed", "采购来源中的餐次已变化，请重新核对", 409)


async def require_formal_current_in_session(
    session, uid, family_id, day, arrangement_id, version, daily_version, meals
):
    """正式餐次详情、成员调整和采购都绑定同一每日版本。"""
    row = await current_row(session, uid, family_id, day)
    if (row.version if row else 0) != daily_version:
        raise HealthVisionError("daily_plan_version_changed", "饮食计划已更新，请重新读取", 409)
    refs = dict(row.meal_sources) if row else await legacy_sources(session, uid, family_id, day)
    expected = {"kind": "formal", "id": arrangement_id, "version": version}
    if any(refs.get(meal) != expected for meal in meals):
        raise HealthVisionError("daily_plan_source_changed", "所选餐次已调整，请重新读取", 409)


async def require_formal_current(uid, family_id, day, arrangement_id, version, daily_version, meals):
    """HTTP调用方复用当前计划校验。"""
    async with pg_manager.get_async_session_context() as session:
        await require_formal_current_in_session(
            session, uid, family_id, day, arrangement_id, version, daily_version, meals
        )


async def publish_reference_in_session(session, run, content):
    """完成事务中按初始版本替换选定餐次，不写入其他餐次。"""
    import json
    from yuxi.services.health_consultation_service import require_consultation
    from yuxi.services.reference_meal_plan_service import reference_binding

    processing = (run.input_payload or {}).get("health_processing")
    if not isinstance(processing, dict) or not processing.get("initial_selection_hash"):
        return
    binding, _ = await require_consultation(
        session, run.uid, run.conversation_thread_id, expected=processing, lock=True
    )
    if not reference_binding(binding):
        return
    selection = binding.initial_planner_selection["selection"]
    base = selection.get("daily_base_version")
    preview_id = json.loads(content).get("preview_id")
    if base is None or not preview_id:
        return
    preview = await session.get(HealthInitialPlanPreview, preview_id)
    if preview is None or preview.run_id != run.id:
        raise HealthVisionError("daily_plan_source_invalid", "餐单结果不属于当前任务", 409)
    from datetime import date

    day = date.fromisoformat(selection["plan_date"])
    family_id = selection["family_id"]
    row = await current_row(session, run.uid, family_id, day, lock=True)
    current_version = row.version if row else 0
    if current_version != base:
        raise HealthVisionError("daily_plan_version_changed", "今日计划已有更新，请重新读取后调整", 409)
    refs = dict(row.meal_sources) if row else await legacy_sources(session, run.uid, family_id, day)
    if row is None:
        row = HealthDailyMealPlan(
            id=str(uuid4()), actor_uid=run.uid, family_id=family_id, plan_date=day, version=0, meal_sources={}
        )
        session.add(row)
    for meal in preview.snapshot["meals"]:
        refs[meal["meal_type"]] = {"kind": "reference", "id": preview_id}
    row.meal_sources, row.version, row.updated_at = refs, current_version + 1, utc_now_naive()
    if (row.pending or {}).get("request_id") == run.request_id:
        row.pending = {}


async def publish_formal_in_session(session, uid, family_id, day, arrangement, base, changed_meal):
    """正式安排完成时更新同一索引，并保留其他独立来源的餐次。"""
    if base is None:
        return
    row = await current_row(session, uid, family_id, day, lock=True)
    version = row.version if row else 0
    if version != base:
        raise HealthVisionError("daily_plan_version_changed", "饮食计划已有更新，请重新读取后调整", 409)
    refs = dict(row.meal_sources) if row else await legacy_sources(session, uid, family_id, day)
    if row is None:
        row = HealthDailyMealPlan(
            id=str(uuid4()), actor_uid=uid, family_id=family_id, plan_date=day, version=0, meal_sources={}
        )
        session.add(row)
    source = {"kind": "formal", "id": arrangement.id, "version": arrangement.snapshot["version"]}
    for meal in MEALS:
        previous = refs.get(meal, {})
        if (
            not changed_meal
            or meal == changed_meal
            or previous.get("kind") == "formal"
            and previous.get("id") == arrangement.id
        ):
            refs[meal] = source
    row.meal_sources, row.version, row.updated_at = refs, version + 1, utc_now_naive()

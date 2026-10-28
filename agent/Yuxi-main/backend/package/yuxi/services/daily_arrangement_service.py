"""建档后的每日安排：复用真实Agent、营养校验和不可变保存。"""

import os
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo
from uuid import NAMESPACE_URL, uuid4, uuid5

from sqlalchemy import select

from yuxi.repositories.daily_arrangement_repository import DailyArrangementRepository
from yuxi.repositories.health_quality_repository import HealthQualityRepository
from yuxi.repositories.health_vision_repository import HealthVisionRepository
from yuxi.services.daily_arrangement_projection import ingredient_requirements, meal_views
from yuxi.services.daily_commerce_service import (
    commerce_request,
    current_catalog,
    match_requirements,
    match_meal_requirements,
    packages_in_stock,
    refresh_purchase_items,
    sku_matches_plan,
)
from yuxi.services.family_service import FamilyService
from yuxi.services.commerce_sku_selection import purchase_authority
from yuxi.services.health_initial_meal_plan_types import InitialPlanSelection
from yuxi.services.health_initial_meal_plan_service import save_initial_plan
from yuxi.services.health_meal_plan_types import MealPlanSave
from yuxi.services.health_nutrition_service import input_fingerprint
from yuxi.services.health_task_service import create_health_task_entry, read_health_task
from yuxi.services.health_task_types import HealthTaskEntryInput
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_business import AgentRun, User
from yuxi.storage.postgres.models_health import (
    HealthDailyArrangement,
    HealthFamilyProfileLink,
    HealthQualityCheck,
    HealthRecipeCommerceSource,
    RecipeVersion,
)
from yuxi.utils.datetime_utils import utc_now_naive


async def read_daily_arrangement(uid, fid, day):
    """当天重进只读已保存结果，尚未生成只返回状态。"""
    async with pg_manager.get_async_session_context() as db:
        _, row = await DailyArrangementRepository(db, uid, fid).context(day)
        if row is None:
            return {"status": "absent", "date": day.isoformat()}
        changed = await authorize_sources(db, uid, row, published=True, allow_changed=True)
        if changed:
            return {
                "status": "stale",
                "date": day.isoformat(),
                "id": row.id,
                "message": "家庭档案已更新，正在重新安排今日三餐。",
            }
        if row.snapshot:
            return {
                **row.snapshot,
                "update": {
                    "status": row.status,
                    "version": row.version,
                    "message": row.selection.get("failure_message", ""),
                },
            }
        return {
            "status": row.status,
            "date": day.isoformat(),
            "id": row.id,
            "message": row.selection.get("failure_message", ""),
        }


async def start_daily_arrangement(uid, fid, data):
    """首开按每日唯一约束创建；超时重放不重新创建Agent任务。"""
    from yuxi.services.daily_arrangement_tasks import queue_daily_in_session
    from yuxi.services.task_service import tasker
    from yuxi.services.daily_meal_plan_service import current_row

    async with pg_manager.get_async_session_context() as db:
        family, row = await DailyArrangementRepository(db, uid, fid).context(data.date, lock=True)
        if row:
            changed = await authorize_sources(db, uid, row, allow_changed=True)
            if not changed:
                return (
                    row.snapshot
                    if row.status == "ready"
                    else {"status": row.status, "date": data.date.isoformat(), "id": row.id}
                )
        selection, sources = await daily_selection(db, uid, family, data.date, allow_interpretation=True)
        if row is None:
            row = HealthDailyArrangement(id=str(uuid4()), actor_uid=uid, family_id=fid, plan_date=data.date)
            db.add(row)
        else:
            row.version += 1
        row.status, row.request_id = "generating", str(data.client_request_id)
        current_plan = await current_row(db, uid, fid, data.date)
        row.selection = {
            "initial": selection.model_dump(mode="json"),
            "attempt": 0,
            "daily_base_version": current_plan.version if current_plan else 0,
        }
        row.sources, row.snapshot = sources, {}
        await db.flush()
        task = await queue_daily_in_session(db, row)
        result = {"status": "generating", "date": data.date.isoformat(), "id": row.id}
    await tasker.publish(task)
    return result


async def resume_daily_arrangement(uid, fid, day):
    """Worker继续已登记请求；失败后的明确重试由HTTP登记用例拥有。"""
    async with pg_manager.get_async_session_context() as db:
        _, row = await DailyArrangementRepository(db, uid, fid).context(day, lock=True)
        if row is None:
            return {"status": "absent", "date": day.isoformat()}
        await authorize_sources(db, uid, row)
        if row.status == "ready":
            return row.snapshot
        if row.selection.get("agent_result") and row.status != "failed":
            await authorize_daily_agent_result(db, uid, row.selection)
        if row.status == "failed":
            return {
                "status": "failed",
                "date": day.isoformat(),
                "id": row.id,
                "message": row.selection.get("failure_message", "今日安排暂未完成，请重试。"),
            }
        selection, rid, sources, version, previous = (
            dict(row.selection),
            row.id,
            dict(row.sources),
            row.version,
            dict(row.snapshot),
        )
    initial = selection["initial"]
    anchor = sorted(initial["profile_versions"])[0]
    attempt = selection.get("attempt", 0)
    task_key = str(uuid5(NAMESPACE_URL, f"daily-agent:{uid}:{rid}:{version}:{attempt}"))
    recovered = selection.get("agent_result")
    if recovered:
        payload, task_key, run_id = recovered["payload"], recovered["task_key"], recovered["run_id"]
    else:
        entry = await create_health_task_entry(
            uid,
            anchor,
            HealthTaskEntryInput.model_validate(
                {
                    "task_type": "initial_meal_preview",
                    "client_request_id": task_key,
                    "selection": initial,
                }
            ),
        )
        if entry.entry_status != "ready":
            raise HealthVisionError("daily_dependencies_not_ready", "营养师服务暂未就绪，系统已保留本次安排请求", 503)
        from yuxi.services.agent_request_service import AgentRequestInput, RunOrigin, submit_agent_request
        from yuxi.services.input_message_service import build_chat_input_message

        async with pg_manager.get_async_session_context() as db:
            user = await db.scalar(select(User).where(User.uid == uid))
            await submit_agent_request(
                request_input=AgentRequestInput(
                    agent_slug=entry.agent_slug,
                    thread_id=str(entry.thread_id),
                    request_id=task_key,
                    input_message=build_chat_input_message(
                        "请按本线程已绑定的成员、日期、档案和批准规则生成完整早餐、午餐、晚餐。使用初始配餐工具，系统会检查全部食材可售性。最终JSON除preview_id外，请给出explanation：解释本份菜单怎样兼顾各成员已有饮食限制和搭配需要。不增加常规补资料步骤，不编造营养数字、医嘱或来源。",
                        None,
                    ),
                    origin=RunOrigin(source="chat", channel="miniapp"),
                ),
                current_user=user,
                db=db,
            )
        task = await read_health_task(uid, task_key)
        if task.result is None:
            return {"status": "generating", "date": day.isoformat(), "id": rid}
        result = task.result.model_dump(mode="json")
        payload = result.get("data", {})
        if result.get("result_type") == "needs_input" and result.get("questions"):
            return await fail_daily(uid, fid, day, version, attempt, "；".join(result["questions"]))
        if (
            result.get("result_type") != "meal_plan_preview"
            or payload.get("status") != "ready"
            or not payload.get("explanation", "").strip()
        ):
            if attempt < selection.get("retry_limit", 2):
                async with pg_manager.get_async_session_context() as db:
                    _, row = await DailyArrangementRepository(db, uid, fid).context(day, lock=True)
                    if row.status == "ready":
                        await authorize_sources(db, uid, row)
                        return row.snapshot
                    if row.version == version and row.selection.get("attempt", 0) == attempt:
                        row.selection = {**row.selection, "attempt": attempt + 1}
                return {"status": "generating", "date": day.isoformat(), "id": rid}
            return await fail_daily(
                uid, fid, day, version, attempt, "今日安排暂未完整生成，请重试分析；已有资料不需要重复填写"
            )
        run_id = task.run_id
        async with pg_manager.get_async_session_context() as db:
            _, row = await DailyArrangementRepository(db, uid, fid).context(day, lock=True)
            if row.version != version:
                raise HealthVisionError("daily_version_changed", "安排已更新，请重新读取", 409)
            if row.status == "ready":
                await authorize_sources(db, uid, row)
                return row.snapshot
            if row.selection.get("attempt", 0) != attempt:
                return {"status": "generating", "date": day.isoformat(), "id": rid}
            row.selection = {
                **row.selection,
                "agent_result": {"payload": payload, "task_key": task_key, "run_id": run_id},
            }
    saved = await save_initial_plan(
        uid,
        anchor,
        MealPlanSave(
            client_request_id=uuid5(NAMESPACE_URL, "daily-save:" + rid + ":" + str(version) + ":" + str(attempt)),
            preview_id=payload["preview_id"],
        ),
    )
    async with pg_manager.get_async_session_context() as db:
        mappings = {
            mapping.recipe_version_id: mapping
            for mapping in (await db.scalars(select(HealthRecipeCommerceSource))).all()
        }
        recipes = {
            recipe.id: recipe
            for recipe in (await db.scalars(select(RecipeVersion).where(RecipeVersion.id.in_(mappings)))).all()
        }
    meals = meal_views(saved, mappings, sources["members"], anchor, recipes)
    catalog = await current_catalog()
    changed = initial.get("change_meal")
    requirements_by_meal = {
        meal["type"]: ingredient_requirements(saved, mappings, meal["type"])
        for meal in meals
        if not changed or meal["type"] == changed
    }
    selected_items = match_meal_requirements(requirements_by_meal, catalog)
    if not selected_items:
        if attempt < selection.get("retry_limit", 2):
            async with pg_manager.get_async_session_context() as db:
                _, row = await DailyArrangementRepository(db, uid, fid).context(day, lock=True)
                if row.status == "ready":
                    await authorize_sources(db, uid, row)
                    return row.snapshot
                if row.version == version and row.selection.get("attempt", 0) == attempt:
                    refreshed = {
                        key: value
                        for key, value in row.selection.items()
                        if key not in {"agent_result", "purchase_catalog_version", "purchase_payloads"}
                    }
                    row.selection = {
                        **refreshed,
                        "purchase_payloads": retained_purchase_payloads(row.selection, changed),
                        "attempt": attempt + 1,
                    }
            return {"status": "generating", "date": day.isoformat(), "id": rid}
        return await fail_daily(uid, fid, day, version, attempt, "食材库存已变化，请重试核对可购买搭配")
    async with pg_manager.get_async_session_context() as db:
        _, row = await DailyArrangementRepository(db, uid, fid).context(day, lock=True)
        if row.version != version:
            raise HealthVisionError("daily_version_changed", "安排已更新，请重新读取", 409)
        if row.status == "ready":
            await authorize_sources(db, uid, row)
            return row.snapshot
        if row.selection.get("attempt", 0) != attempt:
            return {"status": "generating", "date": day.isoformat(), "id": rid}
        catalog_version = row.selection.get("purchase_catalog_version", catalog["version"])
        row.selection = {**row.selection, "purchase_catalog_version": catalog_version}
    for meal in meals:
        if initial.get("change_meal") and initial["change_meal"] != meal["type"]:
            old = next(item for item in previous["meals"] if item["type"] == meal["type"])
            if meal["dishes"] != old["dishes"] or meal["memberNotes"] != old["memberNotes"]:
                raise HealthVisionError("daily_unchanged_meal_modified", "单餐调整影响了其他餐次，系统已停止保存", 409)
            meal["purchase"] = old["purchase"]
            continue
        requirements = ingredient_requirements(saved, mappings, meal["type"])
        package_key = str(uuid5(NAMESPACE_URL, f"daily-purchase:{rid}:{version}:{attempt}:{meal['type']}"))
        purchase_payload = {
            "agent_task_id": package_key,
            "family_ref": fid,
            "user_ref": sources["account_ref"],
            "menu_version_ref": saved["plan_id"] + ":" + str(saved["version"]),
            "catalog_version": catalog_version,
            "agent_source_proof": daily_commerce_source(uid, fid, day, rid, meal),
            "meal_date": day.isoformat(),
            "ingredient_requirements": requirements,
            "items": [
                {"sku_id": item["sku_id"], "quantity": item["quantity"]}
                for item in (selected_items or {}).get(meal["type"], [])
            ],
            "expires_at": datetime.combine(day + timedelta(days=1), time.min, ZoneInfo("Asia/Shanghai")).isoformat(),
            "nutrition_validation": {
                "status": "passed",
                "validation_id": saved["quality_check"]["check_id"],
                "rules_version": str(initial["rule_version"]),
                "summary": "程序校验通过；非专业人员审核结论",
            },
            "recipes": [
                {
                    "recipe_ref": dish["id"],
                    "recipe_version": dish["recipeVersion"],
                    "recipe_name": dish["name"],
                    "meal_type": meal["type"],
                    "ingredients": dish["ingredients"],
                    "steps": dish["steps"],
                }
                for dish in meal["dishes"]
            ],
        }
        async with pg_manager.get_async_session_context() as db:
            _, row = await DailyArrangementRepository(db, uid, fid).context(day, lock=True)
            if row.version != version or row.selection.get("attempt", 0) != attempt:
                raise HealthVisionError("daily_version_changed", "安排已更新，请重新读取", 409)
            payloads = dict(row.selection.get("purchase_payloads", {}))
            purchase_payload = payloads.setdefault(meal["type"], purchase_payload)
            row.selection = {**row.selection, "purchase_payloads": payloads}
        # 食材匹配先保存，用户明确购买时才以商城会员发布采购包。
        meal["purchase"] = {
            "status": "matched",
            "catalog_version": catalog_version,
            "ingredient_requirements": purchase_payload["ingredient_requirements"],
            "items": [
                {
                    **item,
                    "sku": next((sku for sku in catalog["items"] if str(sku["sku_id"]) == str(item["sku_id"])), {}),
                }
                for item in purchase_payload["items"]
            ],
        }
    # 发布端可能选择与预筛不同的SKU；最后按实际返回的三餐包合计复核。
    catalog = await current_catalog()
    if not packages_in_stock([meal["purchase"] for meal in meals if not changed or meal["type"] == changed], catalog):
        if attempt < selection.get("retry_limit", 2):
            async with pg_manager.get_async_session_context() as db:
                _, row = await DailyArrangementRepository(db, uid, fid).context(day, lock=True)
                if row.status == "ready":
                    await authorize_sources(db, uid, row)
                    return row.snapshot
                if row.version == version and row.selection.get("attempt", 0) == attempt:
                    row.selection = {
                        **{
                            key: value
                            for key, value in row.selection.items()
                            if key not in {"agent_result", "purchase_catalog_version", "purchase_payloads"}
                        },
                        "purchase_payloads": retained_purchase_payloads(row.selection, changed),
                        "attempt": attempt + 1,
                    }
            return {"status": "generating", "date": day.isoformat(), "id": rid}
        return await fail_daily(uid, fid, day, version, attempt, "逐餐食材库存核对未完成，请重试")
    snapshot = {
        "status": "ready",
        "id": rid,
        "version": version,
        "date": day.isoformat(),
        "saved": True,
        "plan_id": saved["plan_id"],
        "plan_version": saved["version"],
        "quality_check_id": saved["quality_check"]["check_id"],
        "analysis": {
            "source": "agent",
            "text": payload["explanation"],
            "request_id": task_key,
            "run_id": run_id,
            "knowledge_sources": payload.get("knowledge_sources", []),
        },
        "validation": {"status": "passed", "sources": payload["sources"]},
        "procurement": {"checked": True, "catalog_version": catalog["version"]},
        "meals": meals,
    }
    async with pg_manager.get_async_session_context() as db:
        _, row = await DailyArrangementRepository(db, uid, fid).context(day, lock=True)
        await authorize_sources(db, uid, row)
        if row.version != version:
            raise HealthVisionError("daily_version_changed", "本餐安排已更新，请重新读取", 409)
        if row.status == "ready":
            return row.snapshot
        if row.selection.get("attempt", 0) != attempt:
            return {"status": "generating", "date": day.isoformat(), "id": rid}
        await authorize_daily_agent_result(db, uid, row.selection)
        row.snapshot, row.status, row.updated_at = snapshot, "ready", utc_now_naive()
        await authorize_sources(db, uid, row)
        from yuxi.services.daily_meal_plan_service import publish_formal_in_session

        await publish_formal_in_session(
            db, uid, fid, day, row, row.selection.get("daily_base_version"), initial.get("change_meal")
        )
    return await read_daily_arrangement(uid, fid, day)


async def change_daily_members(uid, fid, day, data):
    """同键单餐调整绑定原保存版本；没有任何订单或履约写入。"""
    from yuxi.services.daily_arrangement_tasks import queue_daily_in_session
    from yuxi.services.task_service import tasker
    from yuxi.services.daily_meal_plan_service import current_row

    digest = input_fingerprint(data.model_dump(mode="json", exclude_none=True))
    async with pg_manager.get_async_session_context() as db:
        family, row = await DailyArrangementRepository(db, uid, fid).context(day, lock=True)
        if row is None:
            raise HealthVisionError("daily_not_found", "今日安排尚未保存", 404)
        await authorize_sources(db, uid, row)
        if row.selection.get("change_key") == str(data.client_request_id):
            if row.selection["change_digest"] != digest:
                raise HealthVisionError("request_conflict", "同一请求不能更改就餐成员", 409)
            return {"status": row.status, "date": day.isoformat(), "id": row.id}
        if row.status != "ready" or row.version != data.version:
            raise HealthVisionError("daily_version_changed", "已有安排正在更新，请重新读取", 409)
        if getattr(data, "daily_plan_version", None) is not None:
            from yuxi.services.daily_meal_plan_service import require_formal_current_in_session

            await require_formal_current_in_session(
                db, uid, fid, day, row.id, data.version, data.daily_plan_version, [data.meal]
            )
        participation = {meal["type"]: [person["id"] for person in meal["members"]] for meal in row.snapshot["meals"]}
        ids = [str(mid) for mid in data.member_ids]
        if len(set(ids)) != len(ids):
            raise HealthVisionError("duplicate_members", "本餐就餐成员不能重复", 422)
        participation[data.meal] = ids
        selected, sources = await daily_selection(
            db, uid, family, day, participation=participation, allow_interpretation=True
        )
        selected.base_plan_id, selected.base_plan_version, selected.change_meal = (
            row.snapshot["plan_id"],
            row.snapshot["plan_version"],
            data.meal,
        )
        current_plan = await current_row(db, uid, fid, day)
        row.selection = {
            "initial": selected.model_dump(mode="json"),
            "daily_base_version": current_plan.version if current_plan else 0,
            "attempt": 0,
            "purchase_payloads": {
                key: payload
                for key, payload in row.selection.get("purchase_payloads", {}).items()
                if key != data.meal and not key.startswith("daily:")
            },
            "purchase_attempts": {
                key: attempt
                for key, attempt in row.selection.get("purchase_attempts", {}).items()
                if key != data.meal and not key.startswith("daily:")
            },
            "purchase_payload_attempts": {
                key: attempt
                for key, attempt in row.selection.get("purchase_payload_attempts", {}).items()
                if key != data.meal and not key.startswith("daily:")
            },
            "purchase_inflight": {
                key: attempt
                for key, attempt in row.selection.get("purchase_inflight", {}).items()
                if key != data.meal and not key.startswith("daily:")
            },
            "change_key": str(data.client_request_id),
            "change_digest": digest,
            "published_sources": row.sources,
        }
        row.sources, row.status, row.version = sources, "generating", row.version + 1
        task = await queue_daily_in_session(db, row)
        result = {"status": row.status, "date": day.isoformat(), "id": row.id}
    await tasker.publish(task)
    return result


async def daily_selection(db, uid, family, day, *, participation=None, allow_interpretation=False):
    """默认成员来自服务端设置，关联使用明确ID，规则由后端配置。"""
    diners = (
        sorted({mid for ids in participation.values() for mid in ids})
        if participation
        else (family.settings or {}).get("default_diners", [])
    )
    links = list(
        (
            await db.scalars(
                select(HealthFamilyProfileLink).where(
                    HealthFamilyProfileLink.family_id == family.id, HealthFamilyProfileLink.source_member_id.in_(diners)
                )
            )
        ).all()
    )
    if not diners or len(links) != len(diners):
        raise HealthVisionError(
            "daily_member_sources_unavailable", "家庭成员的配餐来源尚未完成服务端同步，暂不能生成今日安排", 503
        )
    quality, members, versions = HealthQualityRepository(db), {}, {}
    service = FamilyService(db, uid)
    for link in sorted(links, key=lambda value: value.member_id):
        for scope in ("ai_use", "profile_view", "diet_edit"):
            await HealthVisionRepository(db).authorize(link.member_id, uid, scope)
        _, member = await service.context(family.id, link.source_member_id)
        profile = await quality.profile_projection(link.member_id)
        if profile["status"] != "ready" and not (
            allow_interpretation and profile["reason"] == "profile_coding_unavailable"
        ):
            if profile.get("reason") == "profile_coding_rules_unavailable":
                raise HealthVisionError(
                    "daily_rules_unavailable",
                    "配餐所需的营养规则或档案编码规则尚未配置完成，档案已保存，请等待服务配置后继续准备",
                    503,
                )
            raise HealthVisionError(
                "daily_profile_source_unavailable", "营养师的档案来源尚未同步完成，系统会保留已有建档", 503
            )
        members[link.member_id] = {
            "id": member.id,
            "name": member.name,
            "version": member.version,
            "healthMemberId": link.member_id,
        }
        versions[link.member_id] = profile["version"] or member.version
    rule_code = os.environ.get("HEALTH_DAILY_RULE_CODE", "")
    rules = await quality.rules(rule_code)
    if not rule_code or rules is None:
        raise HealthVisionError("daily_rules_unavailable", "营养规则服务尚未就绪，暂不能生成今日安排", 503)
    ids = sorted(versions)
    source_to_health = {link.source_member_id: link.member_id for link in links}
    selected = InitialPlanSelection(
        kind="family",
        purchase_required=True,
        plan_date=day,
        rule_code=rule_code,
        rule_version=rules.version,
        profile_versions=versions,
        meals=[
            {
                "meal_type": meal,
                "participant_ids": [source_to_health[mid] for mid in participation[meal]] if participation else ids,
            }
            for meal in ("breakfast", "lunch", "dinner")
        ],
    )
    return selected, {
        "members": members,
        "account_ref": "uid:" + uid,
        "default_diners": sorted((family.settings or {}).get("default_diners", [])),
    }


async def authorize_sources(db, uid, row, *, published=False, allow_changed=False):
    """再次打开、恢复、详情都重验成员权限和真实档案版本。"""
    service = FamilyService(db, uid)
    sources = (
        row.selection.get("published_sources", row.sources) if published and row.status != "ready" else row.sources
    )
    family, _ = await service.context(row.family_id)
    previous_diners = sources.get("default_diners")
    # 旧来源未记录默认集合；逐餐参加者并集不能反推默认值，否则升级会抹去单餐调整。
    changed = previous_diners is not None and previous_diners != sorted(
        (family.settings or {}).get("default_diners", [])
    )
    for hid, source in sources["members"].items():
        _, member = await service.context(row.family_id, source["id"])
        for scope in ("ai_use", "profile_view", "diet_edit"):
            await HealthVisionRepository(db).authorize(hid, uid, scope)
        if member.version != source["version"]:
            if not allow_changed:
                raise HealthVisionError("daily_sources_changed", "档案已更新，原安排需要重新分析", 409)
            changed = True
    if row.snapshot and (row.status == "ready" or published):
        try:
            await validate_daily_quality(db, uid, row.snapshot)
        except HealthVisionError:
            if not allow_changed:
                raise
            changed = True
    if changed and not allow_changed:
        raise HealthVisionError("daily_sources_changed", "档案或默认就餐成员已更新，原安排需要重新分析", 409)
    return changed


async def authorize_daily_agent_result(db, uid, selection):
    """恢复和发布沿用原 Run 的处理快照，重验全部就餐成员的当前同意。"""
    from yuxi.services.health_consultation_service import require_consultation

    recovered = selection["agent_result"]
    run = await db.get(AgentRun, recovered["run_id"])
    if (
        run is None
        or run.uid != uid
        or run.agent_slug != "health-meal-planner"
        or run.status != "completed"
        or run.request_id != recovered["task_key"]
    ):
        raise HealthVisionError("source_invalidated", "原配餐运行已失效，请重新生成安排", 409)
    processing = run.input_payload.get("health_processing")
    initial = InitialPlanSelection.model_validate(selection["initial"]).model_dump(mode="json")
    if not processing or not processing.get("initial_selection_hash"):
        raise HealthVisionError("source_invalidated", "原配餐来源已变化，请重新生成安排", 409)
    binding, _ = await require_consultation(db, uid, run.conversation_thread_id, expected=processing, lock=True)
    if not binding.initial_planner_selection or binding.initial_planner_selection["selection"] != initial:
        raise HealthVisionError("source_invalidated", "原配餐来源已变化，请重新生成安排", 409)


async def publish_daily_purchase(uid, fid, day, meal_type, arrangement_id, version):
    """用户明确采购后发布同一餐版本；重试沿用持久化幂等键。"""
    async with pg_manager.get_async_session_context() as db:
        _, row = await DailyArrangementRepository(db, uid, fid).context(day, lock=True)
        if row is None or row.id != arrangement_id or row.version != version or row.status != "ready":
            raise HealthVisionError("daily_version_changed", "本餐安排已更新，请重新读取", 409)
        await authorize_sources(db, uid, row)
        meal = (
            row.selection["daily_purchases"][meal_type]
            if meal_type.startswith("daily:")
            else next(item for item in row.snapshot["meals"] if item["type"] == meal_type)
        )
        payload = row.selection.get("purchase_payloads", {}).get(meal_type)
        if meal["purchase"].get("package_sn"):
            await validate_daily_purchase_composition(payload)
            return {"arrangement_id": row.id, "version": row.version, "purchase": meal["purchase"]}
        if not payload:
            raise HealthVisionError("daily_purchase_unavailable", "本餐采购来源不完整，请重新安排", 409)
        attempt = row.selection.get("purchase_attempts", {}).get(meal_type, 0)
        inflight = row.selection.get("purchase_inflight", {}).get(meal_type)
        # 已发出而结果不确定的请求必须重放原商品及原键，不可因库存预占换包。
        if inflight != attempt:
            catalog = await current_catalog()
            if attempt > row.selection.get("purchase_payload_attempts", {}).get(meal_type, 0) or not packages_in_stock(
                [payload], catalog
            ):
                items = match_requirements(payload["ingredient_requirements"], catalog)
                if not items:
                    raise HealthVisionError("daily_purchase_unavailable", "食材组成、审核或库存已变化，请重新核对", 409)
                payload = {
                    **payload,
                    "catalog_version": catalog["version"],
                    "items": [{"sku_id": item["sku_id"], "quantity": item["quantity"]} for item in items],
                }
            row.selection = {
                **row.selection,
                "purchase_payloads": {**row.selection["purchase_payloads"], meal_type: payload},
                "purchase_payload_attempts": {**row.selection.get("purchase_payload_attempts", {}), meal_type: attempt},
                "purchase_inflight": {**row.selection.get("purchase_inflight", {}), meal_type: attempt},
            }
        if attempt:
            payload = {**payload, "agent_task_id": str(uuid5(NAMESPACE_URL, f"{payload['agent_task_id']}:{attempt}"))}
    package = await commerce_request(
        "POST",
        "/api/v1/integration/ai/recommendation-packages",
        payload,
        request_id=payload["agent_task_id"],
    )
    if package.get("status") != "available" or package.get("trade_validation_status") != "passed":
        # 只有明确返回失败才推进重试代；网络超时继续重放原键以确认原结果。
        async with pg_manager.get_async_session_context() as db:
            _, row = await DailyArrangementRepository(db, uid, fid).context(day, lock=True)
            if row is not None and row.id == arrangement_id and row.version == version:
                attempts = dict(row.selection.get("purchase_attempts", {}))
                if attempts.get(meal_type, 0) == attempt:
                    attempts[meal_type] = attempt + 1
                    row.selection = {**row.selection, "purchase_attempts": attempts}
        raise HealthVisionError("daily_purchase_unavailable", "本餐食材库存已变化，请重新核对", 409)
    purchase = {
        **meal["purchase"],
        "status": "published",
        "package_sn": package["package_sn"],
        "package_version": package["package_version"],
        "items": [
            {"sku_id": item.get("sku_id") or (item.get("sku") or {}).get("sku_id"), "quantity": item.get("quantity")}
            for item in package.get("items", [])
        ],
    }
    async with pg_manager.get_async_session_context() as db:
        _, row = await DailyArrangementRepository(db, uid, fid).context(day, lock=True)
        if row is None or row.id != arrangement_id or row.version != version or row.status != "ready":
            raise HealthVisionError("daily_version_changed", "本餐安排已更新，请重新读取", 409)
        await authorize_sources(db, uid, row)
        if meal_type.startswith("daily:"):
            purchases = dict(row.selection["daily_purchases"])
            purchases[meal_type] = {"purchase": purchase}
            row.selection = {**row.selection, "daily_purchases": purchases}
        else:
            row.snapshot = {
                **row.snapshot,
                "meals": [
                    {**item, "purchase": purchase} if item["type"] == meal_type else item
                    for item in row.snapshot["meals"]
                ],
            }
    return {"arrangement_id": arrangement_id, "version": version, "purchase": purchase}


async def read_daily_purchase(uid, fid, day, meal_type, arrangement_id, version):
    """刷新已保存食材的实时商品状态，查看不会发布采购或改购物车。"""
    snapshot = await read_daily_arrangement(uid, fid, day)
    if snapshot.get("status") != "ready" or snapshot["id"] != arrangement_id or snapshot["version"] != version:
        raise HealthVisionError("daily_version_changed", "本餐安排已更新，请重新读取", 409)
    meal = next(item for item in snapshot["meals"] if item["type"] == meal_type)
    async with pg_manager.get_async_session_context() as db:
        _, row = await DailyArrangementRepository(db, uid, fid).context(day)
        if row is None or row.version != version or row.status != "ready":
            raise HealthVisionError("daily_version_changed", "本餐安排已更新，请重新读取", 409)
        payload = row.selection.get("purchase_payloads", {}).get(meal_type, {})
        pending = not meal["purchase"].get("package_sn") and row.selection.get("purchase_inflight", {}).get(
            meal_type
        ) == row.selection.get("purchase_attempts", {}).get(meal_type, 0)
    purchase = {
        **meal["purchase"],
        "ingredient_requirements": meal["purchase"].get("ingredient_requirements")
        or payload.get("ingredient_requirements", []),
    }
    catalog = await current_catalog()
    original_items = payload.get("items", purchase["items"]) if not purchase.get("package_sn") else purchase["items"]
    items = await refresh_purchase_items(original_items, catalog, purchase["items"])
    available = packages_in_stock([{**purchase, "items": items}], catalog)
    if not available and not pending and not purchase.get("package_sn"):
        alternatives = match_requirements(purchase["ingredient_requirements"], catalog)
        if alternatives:
            items, available = alternatives, True
    return {
        "arrangement_id": arrangement_id,
        "version": version,
        "purchase": {
            **purchase,
            "items": items,
            "available": available,
            "confirmation_pending": pending,
            "catalog_version": catalog["version"],
            "message": "上次采购结果尚未确认，请继续核对原结果。"
            if pending
            else ""
            if available
            else "本餐部分食材已不可售，请重新核对安排或稍后重试。",
        },
    }


async def fail_daily(uid, fid, day, version, attempt, message):
    """保留原任务和失败结局；只有用户重试才开启下一组有界分析。"""
    async with pg_manager.get_async_session_context() as db:
        _, row = await DailyArrangementRepository(db, uid, fid).context(day, lock=True)
        if row.version == version and row.status != "ready" and row.selection.get("attempt", 0) == attempt:
            row.status = "failed"
            row.selection = {**row.selection, "failure_message": message}
    return await read_daily_arrangement(uid, fid, day)


def daily_commerce_source(uid, fid, day, rid, meal):
    """每餐摘要绑定已保存内容，单餐调整后其他餐的采购依据继续有效。"""
    from yuxi.services.health_commerce_service import sign_commerce_source

    return sign_commerce_source(
        {
            "kind": "daily_arrangement",
            "uid": uid,
            "family_id": fid,
            "date": day.isoformat(),
            "arrangement_id": rid,
            "meal": meal["type"],
            "meal_hash": input_fingerprint({key: meal[key] for key in ("type", "members", "dishes", "memberNotes")}),
        }
    )


async def validate_daily_commerce_source(source):
    """结算回读发布中的同一餐，档案撤权或本餐替换后拒绝旧采购来源。"""
    snapshot = await read_daily_arrangement(source["uid"], source["family_id"], date.fromisoformat(source["date"]))
    if snapshot.get("status") != "ready" or snapshot.get("id") != source["arrangement_id"]:
        raise HealthVisionError("source_invalidated", "今日安排采购来源尚未保存或已变化", 410)
    for item in source.get("meals", [source]):
        meal = next((meal for meal in snapshot["meals"] if meal["type"] == item["meal"]), None)
        if (
            meal is None
            or input_fingerprint({key: meal[key] for key in ("type", "members", "dishes", "memberNotes")})
            != item["meal_hash"]
        ):
            raise HealthVisionError("source_invalidated", "本餐安排已更新，请重新核对采购清单", 410)
    meal_types = sorted(item["meal"] for item in source.get("meals", [source]))
    scope = "daily:" + ",".join(meal_types) if "meals" in source else meal_types[0]
    async with pg_manager.get_async_session_context() as db:
        from yuxi.services.daily_meal_plan_service import current_row

        current_plan = await current_row(db, source["uid"], source["family_id"], date.fromisoformat(source["date"]))
        if current_plan and any(
            current_plan.meal_sources.get(meal, {}).get("kind") != "formal"
            or current_plan.meal_sources.get(meal, {}).get("id") != source["arrangement_id"]
            for meal in meal_types
        ):
            raise HealthVisionError("source_invalidated", "今日饮食计划已更换餐次，请重新核对采购", 410)
        _, row = await DailyArrangementRepository(db, source["uid"], source["family_id"]).context(
            date.fromisoformat(source["date"])
        )
        if row is None or row.version != snapshot["version"] or row.status != "ready":
            raise HealthVisionError("source_invalidated", "今日安排已变化，请重新核对", 410)
        payload = row.selection.get("purchase_payloads", {}).get(scope)
        await validate_daily_purchase_composition(payload)
        return purchase_authority(payload)


def retained_purchase_payloads(selection, changed):
    """单餐库存重试保留其他餐原来源，汇总需以新餐次重新建立。"""
    return {
        key: payload
        for key, payload in selection.get("purchase_payloads", {}).items()
        if changed and key != changed and not key.startswith("daily:")
    }


async def validate_daily_quality(db, uid, snapshot):
    """精确绑定已存整份菜单的检查，旧版本仅按同一菜单版本唯一查回。"""
    from yuxi.services.health_quality_service import validate_quality_check

    query = select(HealthQualityCheck).where(
        HealthQualityCheck.actor_uid == uid,
        HealthQualityCheck.plan_id == snapshot.get("plan_id"),
        HealthQualityCheck.plan_version == snapshot.get("plan_version"),
    )
    if snapshot.get("quality_check_id"):
        query = query.where(HealthQualityCheck.id == snapshot["quality_check_id"])
    checks = list((await db.scalars(query)).all()) if snapshot.get("plan_id") else []
    if len(checks) != 1:
        raise HealthVisionError("source_invalidated", "原安排缺少唯一营养检查依据，请重新安排", 410)
    await validate_quality_check(db, uid, checks[0])
    if checks[0].snapshot.get("safety_check", {}).get("status") != "passed":
        raise HealthVisionError("source_invalidated", "原安排营养检查已失效，请重新安排", 410)


async def validate_daily_purchase_composition(payload):
    """回源仅复验审核和组成，预占库存由商城自己的结算事务核对。"""
    if not payload or not payload.get("items"):
        raise HealthVisionError("source_invalidated", "本次采购缺少已保存商品来源", 410)
    from urllib.parse import quote

    for item in payload["items"]:
        sku = await commerce_request(
            "GET", "/api/v1/integration/ai/catalog/skus/" + quote(str(item["sku_id"]), safe="")
        )
        if not sku_matches_plan(sku, payload["ingredient_requirements"], allow_reserved=True):
            raise HealthVisionError("source_invalidated", "商品组成或食材审核已变化，请重新核对", 410)

"""建档后的每日安排：复用真实Agent、营养校验和不可变保存。"""

import os
from datetime import datetime, time, timedelta
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
    packages_in_stock,
)
from yuxi.services.family_service import FamilyService
from yuxi.services.health_commerce_service import daily_source_proof
from yuxi.services.health_initial_meal_plan_types import InitialPlanSelection
from yuxi.services.health_initial_meal_plan_service import save_initial_plan
from yuxi.services.health_meal_plan_types import MealPlanSave
from yuxi.services.health_nutrition_service import input_fingerprint
from yuxi.services.health_quality_service import validate_quality_check
from yuxi.services.health_task_service import create_health_task_entry, read_health_task
from yuxi.services.health_task_types import HealthTaskEntryInput
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_business import User
from yuxi.storage.postgres.models_health import (
    HealthDailyArrangement,
    HealthFamilyProfileLink,
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
        await authorize_sources(db, uid, row)
        if row.status == "ready":
            return row.snapshot
        return {
            "status": row.status,
            "date": day.isoformat(),
            "id": row.id,
            "message": row.selection.get("failure_message", ""),
        }


async def start_daily_arrangement(uid, fid, data):
    """首开按每日唯一约束创建；超时重放不重新创建Agent任务。"""
    async with pg_manager.get_async_session_context() as db:
        family, row = await DailyArrangementRepository(db, uid, fid).context(data.date, lock=True)
        if row:
            await authorize_sources(db, uid, row)
            return (
                row.snapshot
                if row.status == "ready"
                else {"status": row.status, "date": data.date.isoformat(), "id": row.id}
            )
        selection, sources = await daily_selection(db, uid, family, data.date)
        row = HealthDailyArrangement(
            id=str(uuid4()),
            actor_uid=uid,
            family_id=fid,
            plan_date=data.date,
            status="generating",
            request_id=str(data.client_request_id),
            selection={"initial": selection.model_dump(mode="json"), "attempt": 0},
            sources=sources,
            snapshot={},
        )
        db.add(row)
        await db.flush()
        return {"status": "generating", "date": data.date.isoformat(), "id": row.id}


async def resume_daily_arrangement(uid, fid, day, *, retry_failed=False):
    """POST继续原请求，最终保存与读取分离，GET不发起生成或下单。"""
    async with pg_manager.get_async_session_context() as db:
        _, row = await DailyArrangementRepository(db, uid, fid).context(day, lock=True)
        if row is None:
            return {"status": "absent", "date": day.isoformat()}
        await authorize_sources(db, uid, row)
        if row.status == "ready":
            return row.snapshot
        if row.status == "failed":
            if not retry_failed:
                return {
                    "status": "failed",
                    "date": day.isoformat(),
                    "id": row.id,
                    "message": row.selection.get("failure_message", "今日安排暂未完成，请重试。"),
                }
            attempt = row.selection.get("attempt", 0) + 1
            row.selection = {
                **{
                    key: value
                    for key, value in row.selection.items()
                    if key not in {"agent_result", "purchase_catalog_version", "failure_message"}
                },
                "attempt": attempt,
                "retry_limit": attempt + 2,
            }
            row.status = "generating"
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
    if not match_requirements(ingredient_requirements(saved, mappings), catalog):
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
                        if key not in {"agent_result", "purchase_catalog_version"}
                    }
                    row.selection = {**refreshed, "attempt": attempt + 1}
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
        requirements = ingredient_requirements(saved, mappings, meal["type"])
        package_key = str(uuid5(NAMESPACE_URL, f"daily-purchase-source-v1:{rid}:{version}:{attempt}:{meal['type']}"))
        package = await commerce_request(
            "POST",
            "/api/v1/integration/ai/recommendation-packages",
            {
                "agent_task_id": package_key,
                "family_ref": fid,
                "user_ref": sources["account_ref"],
                "menu_version_ref": saved["plan_id"] + ":" + str(saved["version"]),
                "catalog_version": catalog_version,
                "meal_date": day.isoformat(),
                "ingredient_requirements": requirements,
                "expires_at": datetime.combine(
                    day + timedelta(days=1), time.min, ZoneInfo("Asia/Shanghai")
                ).isoformat(),
                "nutrition_validation": {
                    "status": "passed",
                    "validation_id": saved["quality_check"]["check_id"],
                    "rules_version": str(initial["rule_version"]),
                    "summary": "程序校验通过；非专业人员审核结论",
                },
                "agent_source_proof": daily_source_proof(uid, fid, day, rid, version, attempt, sources, saved, meal),
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
            },
            request_id=package_key,
        )
        if package.get("status") != "available" or package.get("trade_validation_status") != "passed":
            raise HealthVisionError("daily_purchase_unavailable", "本餐食材匹配尚未通过，系统将继续核对", 503)
        meal["purchase"] = {
            "package_sn": package["package_sn"],
            "package_version": package["package_version"],
            "items": [
                {
                    "sku_id": item.get("sku_id") or (item.get("sku") or {}).get("sku_id"),
                    "quantity": item.get("quantity"),
                }
                for item in package.get("items", [])
            ],
        }
    # 发布端可能选择与预筛不同的SKU；最后按实际返回的三餐包合计复核。
    catalog = await current_catalog()
    if not packages_in_stock([meal["purchase"] for meal in meals], catalog):
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
                            if key not in {"agent_result", "purchase_catalog_version"}
                        },
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
        "analysis": {"source": "agent", "text": payload["explanation"], "request_id": task_key, "run_id": run_id},
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
        await validate_saved_daily_plan(db, uid, row, snapshot)
        row.snapshot, row.status, row.updated_at = snapshot, "ready", utc_now_naive()
    return await read_daily_arrangement(uid, fid, day)


async def change_daily_members(uid, fid, day, data):
    """同键单餐调整绑定原保存版本；没有任何订单或履约写入。"""
    digest = input_fingerprint(data.model_dump(mode="json"))
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
        participation = {meal["type"]: [person["id"] for person in meal["members"]] for meal in row.snapshot["meals"]}
        ids = [str(mid) for mid in data.member_ids]
        if len(set(ids)) != len(ids):
            raise HealthVisionError("duplicate_members", "本餐就餐成员不能重复", 422)
        participation[data.meal] = ids
        selected, sources = await daily_selection(db, uid, family, day, participation=participation)
        selected.base_plan_id, selected.base_plan_version, selected.change_meal = (
            row.snapshot["plan_id"],
            row.snapshot["plan_version"],
            data.meal,
        )
        row.selection = {
            "initial": selected.model_dump(mode="json"),
            "attempt": 0,
            "change_key": str(data.client_request_id),
            "change_digest": digest,
        }
        row.sources, row.status, row.version = sources, "generating", row.version + 1
        return {"status": row.status, "date": day.isoformat(), "id": row.id}


async def daily_selection(db, uid, family, day, *, participation=None):
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
        if profile["status"] != "ready":
            raise HealthVisionError(
                "daily_profile_source_unavailable", "营养师的档案来源尚未同步完成，系统会保留已有建档", 503
            )
        members[link.member_id] = {
            "id": member.id,
            "name": member.name,
            "version": member.version,
            "healthMemberId": link.member_id,
        }
        versions[link.member_id] = profile["version"]
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
    user = await db.scalar(select(User).where(User.uid == uid))
    return selected, {"members": members, "account_ref": str(user.id)}


async def authorize_sources(db, uid, row):
    """读取和恢复重验成员来源；已保存安排继续核对原质量收据。"""
    service = FamilyService(db, uid)
    for hid, source in row.sources["members"].items():
        _, member = await service.context(row.family_id, source["id"])
        if member.version != source["version"]:
            raise HealthVisionError("daily_sources_changed", "档案已更新，原安排需要重新分析", 409)
        for scope in ("ai_use", "profile_view", "diet_edit"):
            await HealthVisionRepository(db).authorize(hid, uid, scope)
    if row.status == "ready":
        return await validate_saved_daily_plan(db, uid, row, row.snapshot)


async def validate_saved_daily_plan(db, uid, row, snapshot):
    """原保存幂等键定位质量收据，来源失效只拒绝当前使用而不改写历史。"""
    save_key = uuid5(NAMESPACE_URL, f"daily-save:{row.id}:{row.version}:{row.selection.get('attempt', 0)}")
    check_key = str(uuid5(NAMESPACE_URL, f"health-initial-generation:{uid}:{save_key}"))
    check = await HealthQualityRepository(db).check_receipt(uid, check_key)
    if (
        check is None
        or check.plan_id != snapshot.get("plan_id")
        or check.plan_version != snapshot.get("plan_version")
        or check.rule_code != row.selection.get("initial", {}).get("rule_code")
        or check.snapshot.get("safety_check", {}).get("status") != "passed"
    ):
        raise HealthVisionError("source_invalidated", "今日安排的原营养检查无法核对，请重新分析", 410)
    await validate_quality_check(db, uid, check)
    return check


async def fail_daily(uid, fid, day, version, attempt, message):
    """保留原任务和失败结局；只有用户重试才开启下一组有界分析。"""
    async with pg_manager.get_async_session_context() as db:
        _, row = await DailyArrangementRepository(db, uid, fid).context(day, lock=True)
        if row.version == version and row.status != "ready" and row.selection.get("attempt", 0) == attempt:
            row.status = "failed"
            row.selection = {**row.selection, "failure_message": message}
    return await read_daily_arrangement(uid, fid, day)

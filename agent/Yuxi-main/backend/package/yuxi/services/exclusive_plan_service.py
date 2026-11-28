"""专属计划的首开复用、来源授权、菜单预览和历史商城引用。"""

from datetime import date, datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import select

from yuxi.repositories.exclusive_plan_repository import ExclusivePlanRepository
from yuxi.repositories.health_vision_repository import HealthVisionRepository
from yuxi.services.exclusive_plan_generation import TIERS, content_hash
from yuxi.services.exclusive_reference_plan import (
    CAPABILITY_NOTICE,
    REFERENCE_POLICY,
    TIER_TARGETS,
    TIER_REFERENCE_CENTS,
    exclusive_reference_context,
    reference_member_restrictions,
    summarize_reference_prices,
)
from yuxi.services.family_service import FamilyService
from yuxi.services.health_initial_meal_plan_service import initial_catalog_in_session
from yuxi.services.health_nutrition_service import input_fingerprint
from yuxi.services.health_vision_service import health_vision_service
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.services.task_service import tasker
from yuxi.services.service_notice_service import require_service_notice
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_health import HealthExclusivePlanGroup, HealthRecipeCommerceSource


PREVIEW_POLICY = REFERENCE_POLICY


async def start_exclusive_plan(uid, fid, data, *, only_missing=False, required_member=None):
    """首开按语义依据复用；只有明确换一套才创建新推荐组。"""
    if data.action == "retry" and data.group_id:
        from yuxi.services.exclusive_roster_service import retry_exclusive_roster

        pending_roster = await retry_exclusive_roster(uid, fid, data.group_id)
        if pending_roster is not None:
            return pending_roster
    policy = PREVIEW_POLICY
    task = None
    async with pg_manager.get_async_session_context() as session:
        repo = ExclusivePlanRepository(session, uid, fid)
        await repo.context(lock=True)
        if only_missing:
            latest = await repo.find(lock=True)
            if latest is not None and latest.policy == PREVIEW_POLICY:
                return None
        await require_service_notice(session, uid)
        previous = await repo.find(request_id=str(data.client_request_id), lock=True)
        requested = previous or (
            await repo.find(group_id=str(data.group_id), lock=True)
            if data.group_id and data.action != "regenerate"
            else None
        )
        anchor = (
            date.fromisoformat(requested.selection["plan_date"])
            if requested and requested.policy == policy
            else datetime.now(ZoneInfo("Asia/Shanghai")).date()
        )
        context = await exclusive_context(
            session, uid, fid, policy, day=anchor, start_date=anchor, allow_interpretation=True
        )
        if required_member and required_member not in context["sources"]["members"]:
            raise HealthVisionError("not_found", "该成员不属于本次家庭就餐成员", 404)
        if previous and (previous.policy != policy or previous.basis_hash != context["basis_hash"]):
            raise HealthVisionError("source_version_conflict", "档案已变化，请重新发起计划请求", 409)
        row = requested
        if row and row.policy.get("version") in {"agent-preview-v1", "exclusive-reference-v2"} and previous is None:
            row = None
        if row and row.basis_hash != context["basis_hash"]:
            raise HealthVisionError("source_version_conflict", "档案或计划规则已变化，请重新准备", 409)
        if row is None and data.action != "regenerate":
            row = await repo.find(basis_hash=context["basis_hash"], lock=True)
        if row is not None and row.status == "ready":
            from yuxi.services.exclusive_plan_tasks import validate_saved_days

            try:
                for entries in row.progress.get("tiers", {}).values():
                    await validate_saved_days(session, context, entries)
            except HealthVisionError as error:
                if error.code not in {"source_invalidated", "reference_source_unavailable"}:
                    raise
                row.status = "stale"
                if previous:
                    raise HealthVisionError("source_version_conflict", "原方案来源已失效，请重新准备", 409) from error
                row = None
        if row is not None and row.status == "stale":
            row = None
        if row is None:
            row = HealthExclusivePlanGroup(
                id=str(uuid4()),
                actor_uid=uid,
                family_id=fid,
                request_id=str(data.client_request_id),
                basis_hash=context["basis_hash"],
                status="generating",
                attempt=0,
                selection=context["selection"].model_dump(mode="json"),
                sources=context["sources"],
                policy=policy,
                progress={"tiers": {}, "composition": "reference"},
            )
            session.add(row)
            await session.flush()
        elif data.action == "retry" and row.status == "failed":
            row.status = "generating"
            row.attempt += 1
            row.progress = {key: value for key, value in row.progress.items() if key not in {"error", "recovery_count"}}
        if row.status == "generating":
            task = await queue_exclusive_in_session(session, row)
        result = project_group(row, context["sources"], current=context["current"])
    if task:
        await tasker.publish(task)
    return result


async def read_exclusive_plan(uid, fid, group_id=None, *, tier=None):
    """读回同一任务；不因刷新、切档或返回重新生成。"""
    async with pg_manager.get_async_session_context() as session:
        repo = ExclusivePlanRepository(session, uid, fid)
        await repo.context()
        row = await repo.find(group_id=group_id)
        if row is None:
            return {"status": "empty", "group_id": None, "plans": []}
        if tier is None and row.progress.get("roster_update") and row.status in {"generating", "failed"}:
            return project_group(row, row.sources)
        if row.policy.get("version") in {"agent-preview-v1", "exclusive-reference-v2"}:
            if tier is not None:
                raise HealthVisionError("source_invalidated", "计划口径已更新，请重新准备", 410)
            return {"status": "stale", "group_id": row.id, "plans": [], "message": "计划口径已更新，请重新准备"}
        if tier is None and row.policy != PREVIEW_POLICY and row.status in {"failed", "stale"}:
            return {"status": "stale", "group_id": row.id, "plans": [], "message": "可重新生成专属计划"}
        if tier is not None and (tier not in TIERS or row.policy != PREVIEW_POLICY or row.status != "ready"):
            raise HealthVisionError("exclusive_preview_unavailable", "计划预览尚未就绪，请返回计划页", 404)
        context = await exclusive_context(
            session,
            uid,
            fid,
            row.policy,
            day=date.fromisoformat(row.selection["plan_date"]) if row.policy == PREVIEW_POLICY else None,
            start_date=row.selection["plan_date"] if row.policy == PREVIEW_POLICY else None,
            allow_interpretation=True,
            load_documents=False,
        )
        from yuxi.services.diet_stage_plan_history import historical_goal_context

        context = await historical_goal_context(session, context, row.sources, row.policy, row.selection["plan_date"])
        if row.basis_hash != context["basis_hash"]:
            if tier is not None:
                raise HealthVisionError("source_invalidated", "档案或计划规则已更新，请重新准备", 410)
            return {"status": "stale", "group_id": row.id, "plans": [], "message": "档案或计划规则已更新"}
        if row.status == "ready":
            from yuxi.services.exclusive_plan_tasks import validate_saved_days

            try:
                tiers = row.progress.get("tiers", {})
                for entries in [tiers.get(tier, [])] if tier else tiers.values():
                    await validate_saved_days(session, context, entries)
            except HealthVisionError as error:
                if error.code not in {"source_invalidated", "reference_source_unavailable"} or tier is not None:
                    raise
                return {"status": "stale", "group_id": row.id, "plans": [], "message": error.message}
        if tier is not None:
            return project_preview(row, tier, context["sources"], current=context["current"])
        return project_group(row, context["sources"], current=context["current"])


async def exclusive_context(
    session, uid, fid, policy, *, allow_interpretation=False, day=None, start_date=None, load_documents=True
):
    """新版复用今日餐单依据，历史正式计划继续核对批准规则。"""
    if policy == PREVIEW_POLICY:
        return await exclusive_reference_context(
            session,
            uid,
            fid,
            day=day or datetime.now(ZoneInfo("Asia/Shanghai")).date(),
            start_date=start_date,
            load_documents=load_documents,
        )
    from yuxi.services.daily_arrangement_service import daily_selection

    family, _ = await FamilyService(session, uid).context(fid)
    day = day or datetime.now(ZoneInfo("Asia/Shanghai")).date()
    selection, sources = await daily_selection(session, uid, family, day, allow_interpretation=allow_interpretation)
    anchor = sorted(sources["members"])[0]
    current, recipes, foods, refs = await initial_catalog_in_session(session, uid, anchor, selection)
    if current["rules"]["status"] != "ready":
        raise HealthVisionError("exclusive_plan_rules_missing", "审核规则尚未准备好", 503)
    config = await health_vision_service.configuration(session)
    processing = config["meal_plan"]
    if not processing["available"]:
        raise HealthVisionError("daily_dependencies_not_ready", "配餐处理配置尚未确认", 503)
    profiles = {}
    for hid, source in sources["members"].items():
        await HealthVisionRepository(session).require_consent(
            hid,
            uid,
            "meal_plan",
            {
                "model": processing["model"],
                "processor": processing["processor"],
                "policy_version": config["policy_version"],
            },
        )
        _, member = await FamilyService(session, uid).context(fid, source["id"])
        projection = current["profiles"][hid]
        profiles[hid] = {
            "family_member_id": source["id"],
            "profile": {
                key: value
                for key, value in member.profile.items()
                if key not in {"avatar", "avatar_url", "name", "display_name"}
            },
            "professional": projection["payload"] if projection.get("source_kind") != "user_reported" else None,
        }
    basis = input_fingerprint(
        {
            "profiles": profiles,
            "rules": current["rules"]["content_hash"],
            "policy": {"hash": policy["hash"], "version": policy["version"]},
            "processing": {"processor": processing["processor"], "policy_version": config["policy_version"]},
        }
    )
    mappings = {
        row.recipe_version_id: row
        for row in (
            await session.scalars(
                select(HealthRecipeCommerceSource).where(HealthRecipeCommerceSource.recipe_version_id.in_(recipes))
            )
        ).all()
    }
    return {
        "selection": selection,
        "sources": sources,
        "basis_hash": basis,
        "current": current,
        "recipes": recipes,
        "foods": foods,
        "refs": refs,
        "mappings": mappings,
        "preference_members": [value["profile"] for value in profiles.values()],
    }


async def queue_exclusive_in_session(session, row):
    """与推荐组同事务保存任务，提交后由调用者投递。"""
    payload = {"uid": row.actor_uid, "family_id": row.family_id, "group_id": row.id, "attempt": row.attempt}
    task, _ = await tasker.create_unique_in_session(
        session,
        name="准备家庭专属计划",
        task_type="exclusive_plan_v1",
        payload=payload,
        payload_match=payload,
        timeout_seconds=1800,
    )
    return task


def project_group(row, sources, *, current=None):
    """只返回状态，以及已发布的三档摘要或历史商城引用。"""
    progress = row.progress
    completed = sum(len(days) for days in progress.get("tiers", {}).values())
    plans = []
    if row.status == "ready":
        plans = (
            [
                {
                    "tier_code": tier,
                    "tier_name": name,
                    "difference": TIER_TARGETS[tier],
                    "reference_price": {
                        "min_cent": TIER_REFERENCE_CENTS[tier][0],
                        "max_cent": TIER_REFERENCE_CENTS[tier][1],
                        "unit": "person_day",
                    },
                    "pricing": project_reference_pricing(
                        row, progress["tiers"][tier], sources, current=current, include_gaps=False
                    ),
                    "tier_cost_status": "unverified",
                }
                for tier, name in TIERS.items()
            ]
            if row.policy == PREVIEW_POLICY
            else list(progress.get("receipts", {}).values())
        )
    return {
        "group_id": row.id,
        "status": row.status,
        "completed_days": completed,
        "total_days": row.policy.get("day_count", 21) * len(TIERS),
        "period_days": row.policy.get("day_count", 21),
        **({"start_date": row.selection["plan_date"]} if row.policy == PREVIEW_POLICY else {}),
        "members": [{"member_ref": hid, "name": source["name"]} for hid, source in sources["members"].items()],
        "plans": plans,
        "preview_only": row.policy == PREVIEW_POLICY,
        "professional_status": "not_reviewed" if row.policy == PREVIEW_POLICY else None,
        "nutrition_status": "not_calculated" if row.policy == PREVIEW_POLICY else None,
        "notice": CAPABILITY_NOTICE if row.policy == PREVIEW_POLICY else None,
        "error": progress.get("error"),
        "updated_at": row.updated_at.isoformat() + "Z",
    }


def project_preview(row, tier, sources, *, current=None):
    """返回完整每日原谱、食材、采购缺口和部分小计。"""
    entries = row.progress.get("tiers", {}).get(tier, [])
    if [entry["day"]["day_no"] for entry in entries] != list(range(1, row.policy.get("day_count", 21) + 1)):
        raise HealthVisionError("exclusive_preview_unavailable", "计划预览尚未就绪，请返回计划页", 404)
    return {
        "group_id": row.id,
        "tier_code": tier,
        "tier_name": TIERS[tier],
        "period_days": row.policy.get("day_count", 21),
        **({"start_date": row.selection["plan_date"]} if row.policy == PREVIEW_POLICY else {}),
        "difference": TIER_TARGETS[tier] + "；实际完整费用尚未核定",
        "professional_status": "not_reviewed",
        "nutrition_status": "not_calculated",
        "notice": CAPABILITY_NOTICE,
        "reference_price": {
            "min_cent": TIER_REFERENCE_CENTS[tier][0],
            "max_cent": TIER_REFERENCE_CENTS[tier][1],
            "unit": "person_day",
        },
        "pricing": project_reference_pricing(row, entries, sources, current=current),
        "tier_cost_status": "unverified",
        "members": [{"display_alias": member["name"]} for member in sources["members"].values()],
        "days": [
            {
                "day_no": entry["day"]["day_no"],
                "plan_date": entry["day"]["plan_date"],
                "procurement": entry["procurement"],
                "meals": [
                    {
                        "id": meal["meal_type"] + ":" + dish["file_id"],
                        "meal_type": meal["meal_type"],
                        "recipe_name": dish["name"],
                        "ingredients": dish["ingredients"],
                        "steps": dish["steps"],
                        "source": dish["source"],
                        "portion_note": dish.get("portion_note"),
                        "roster_preserved": meal["meal_type"] in entry.get("roster_preserved_meals", []),
                        "recipe_snapshot": {key: dish.get(key) for key in ("image_url", "cooking_minutes", "source")},
                    }
                    for meal in entry["meals"]
                    for dish in meal["dishes"]
                ],
            }
            for entry in entries
        ],
    }


def project_reference_pricing(row, entries, sources, *, current=None, include_gaps=True):
    """摘要与详情共用任务快照、实际就餐成员及当前限制计算采购费用。"""
    restrictions = (
        reference_member_restrictions(current["members"]) + current.get("memory_restrictions", []) if current else ()
    )
    return summarize_reference_prices(
        entries,
        catalog=row.progress.get("catalog_snapshot"),
        member_count=len(sources["members"]),
        restrictions=restrictions,
        include_gaps=include_gaps,
    )


def export_payload(row, tier):
    """保存完整导出后再发送；重试始终使用原任务号及原内容。"""
    from yuxi.services.health_commerce_service import sign_commerce_source

    members = sorted(row.sources["members"])
    payload = {
        "agent_task_id": f"exclusive:{row.id}:{tier}",
        "family_ref": row.family_id,
        "user_ref": "uid:" + row.actor_uid,
        "member_refs": members,
        "member_aliases": {hid: row.sources["members"][hid]["name"] for hid in members},
        "profile_version_refs": [f"{hid}:{row.selection['profile_versions'][hid]}" for hid in members],
        "recommendation_group_ref": row.id,
        "tier_code": tier,
        "tier_policy_version": row.policy["version"],
        "basis_hash": row.basis_hash,
        "plan_name": TIERS[tier] + " · 21 天家庭计划",
        "plan_days": 21,
        "delivery_frequency": "selectable" if row.progress.get("composition") == "reference" else "daily",
        "display": {"image_url": None},
        "days": [entry["day"] for entry in row.progress["tiers"][tier]],
        "nutrition_validation": {
            "status": "passed",
            "validation_id": f"exclusive:{row.id}:{tier}",
            "rules_version": f"{row.selection['rule_code']}:{row.selection['rule_version']}",
        },
    }
    payload["agent_source_proof"] = sign_commerce_source(
        {
            "kind": "service_plan",
            "uid": row.actor_uid,
            "family_id": row.family_id,
            "group_id": row.id,
            "tier_code": tier,
            "plan_version": 1,
            "policy_version": row.policy["version"],
            "basis_hash": row.basis_hash,
            "content_hash": content_hash(payload),
        }
    )
    return payload

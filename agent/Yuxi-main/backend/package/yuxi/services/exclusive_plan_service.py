"""专属计划的首开复用、来源授权与真实商城结果引用。"""

from datetime import datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import select

from yuxi.repositories.exclusive_plan_repository import ExclusivePlanRepository
from yuxi.repositories.health_vision_repository import HealthVisionRepository
from yuxi.services.daily_arrangement_service import daily_selection
from yuxi.services.daily_commerce_service import commerce_request
from yuxi.services.exclusive_plan_generation import TIERS, content_hash
from yuxi.services.family_service import FamilyService
from yuxi.services.health_initial_meal_plan_service import initial_catalog_in_session
from yuxi.services.health_nutrition_service import input_fingerprint
from yuxi.services.health_vision_service import health_vision_service
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.services.task_service import tasker
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_health import HealthExclusivePlanGroup, HealthRecipeCommerceSource


async def start_exclusive_plan(uid, fid, data, *, required_member=None):
    """首开按语义依据复用；只有明确换一套才创建新推荐组。"""
    policy = await read_plan_policy()
    task = None
    async with pg_manager.get_async_session_context() as session:
        repo = ExclusivePlanRepository(session, uid, fid)
        await repo.context(lock=True)
        context = await exclusive_context(session, uid, fid, policy, allow_interpretation=True)
        if required_member and required_member not in context["sources"]["members"]:
            raise HealthVisionError("not_found", "该成员不属于本次家庭就餐成员", 404)
        previous = await repo.find(request_id=str(data.client_request_id), lock=True)
        if previous and previous.basis_hash != context["basis_hash"]:
            raise HealthVisionError("source_version_conflict", "档案已变化，请重新发起计划请求", 409)
        row = previous or (await repo.find(group_id=str(data.group_id), lock=True) if data.group_id else None)
        if row and row.basis_hash != context["basis_hash"]:
            raise HealthVisionError("source_version_conflict", "档案或计划规则已变化，请重新准备", 409)
        if row is None and data.action != "regenerate":
            row = await repo.find(basis_hash=context["basis_hash"], lock=True)
        if row is not None and row.status == "ready":
            from yuxi.services.exclusive_plan_tasks import validate_saved_days

            try:
                for entries in row.progress.get("tiers", {}).values():
                    validate_saved_days(context, entries)
            except HealthVisionError as error:
                if error.code != "source_invalidated":
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
                progress={"tiers": {}, "exports": {}, "receipts": {}},
            )
            session.add(row)
            await session.flush()
        elif data.action == "retry" and row.status == "failed":
            row.status = "generating"
            row.attempt += 1
            row.progress = {key: value for key, value in row.progress.items() if key not in {"error", "recovery_count"}}
        if row.status == "generating":
            task = await queue_exclusive_in_session(session, row)
        result = project_group(row, context["sources"])
    if task:
        await tasker.publish(task)
    return result


async def read_exclusive_plan(uid, fid, group_id=None):
    """读回同一任务；不因刷新、切档或返回重新生成。"""
    policy = await read_plan_policy()
    async with pg_manager.get_async_session_context() as session:
        repo = ExclusivePlanRepository(session, uid, fid)
        await repo.context()
        row = await repo.find(group_id=group_id)
        if row is None:
            return {"status": "empty", "group_id": None, "plans": []}
        context = await exclusive_context(session, uid, fid, policy, allow_interpretation=True)
        if row.basis_hash != context["basis_hash"]:
            return {"status": "stale", "group_id": row.id, "plans": [], "message": "档案或计划规则已更新"}
        if row.status == "ready":
            from yuxi.services.exclusive_plan_tasks import validate_saved_days

            try:
                for entries in row.progress.get("tiers", {}).values():
                    validate_saved_days(context, entries)
            except HealthVisionError as error:
                if error.code != "source_invalidated":
                    raise
                return {"status": "stale", "group_id": row.id, "plans": [], "message": error.message}
        return project_group(row, context["sources"])


async def read_plan_policy():
    """没有真实商城规则时明确未就绪，不填演示金额。"""
    result = await commerce_request("GET", "/api/v1/integration/ai/plan-policy")
    if result.get("status") != "ready":
        raise HealthVisionError("exclusive_plan_policy_missing", "专属计划暂未开放", 503)
    return result["policy"]


async def exclusive_context(session, uid, fid, policy, *, allow_interpretation=False, day=None):
    """用授权字段及批准规则形成依据，名字或头像变化不重做餐单。"""
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


def project_group(row, sources):
    """只暴露状态与当前组商城引用，不把尚未完整校验的菜单当作结果。"""
    progress = row.progress
    completed = sum(len(days) for days in progress.get("tiers", {}).values())
    return {
        "group_id": row.id,
        "status": row.status,
        "completed_days": completed,
        "total_days": 63,
        "members": [{"member_ref": hid, "name": source["name"]} for hid, source in sources["members"].items()],
        "plans": list(progress.get("receipts", {}).values()) if row.status == "ready" else [],
        "error": progress.get("error"),
        "updated_at": row.updated_at.isoformat() + "Z",
    }


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
        "delivery_frequency": "daily",
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

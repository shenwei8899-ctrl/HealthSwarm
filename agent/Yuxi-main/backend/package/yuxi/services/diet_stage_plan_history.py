"""行为目标变化允许历史只读，其他配餐依据继续严格核对。"""

from copy import deepcopy

from sqlalchemy import select

from yuxi.services.health_nutrition_service import input_fingerprint
from yuxi.storage.postgres.models_business import FamilyMember, FamilyProfileRevision


def without_behavior_goals(profile):
    """只剔除阶段拥有的行为目标，不剔除限制、医嘱、身体数据。"""
    result = deepcopy(profile)
    for key in ("goal", "health_goals", "diet_stage_managed"):
        result.pop(key, None)
    if "dietary_details" in result:
        result["dietary_details"].pop("goals", None)
    return result


async def historical_goal_context(session, context, stored_sources, policy, start_date):
    """仅用于已存菜单读取；新生成始终绑定当前目标。"""
    if not stored_sources or context.get("mode") != "reference":
        return context
    previous = (stored_sources.get("reference") or {}).get("members", {})
    actual = context["current"]["sources"]["members"]
    if set(previous) != set(actual):
        return context
    restored = deepcopy(context)
    changed = False
    for mid, source in actual.items():
        old = previous[mid]
        if old == source:
            continue
        member = await session.get(FamilyMember, mid)
        snapshot = await session.scalar(
            select(FamilyProfileRevision).where(
                FamilyProfileRevision.member_id == mid, FamilyProfileRevision.version == old["version"]
            )
        )
        if (
            member is None
            or not member.profile.get("diet_stage_managed")
            or snapshot is None
            or input_fingerprint(snapshot.profile) != old["profile_hash"]
            or without_behavior_goals(snapshot.profile) != without_behavior_goals(member.profile)
        ):
            return context
        restored["current"]["sources"]["members"][mid] = deepcopy(old)
        hid = old["health_member_id"]
        restored["sources"]["members"][hid] = deepcopy(stored_sources["members"][hid])
        changed = True
    if changed:
        restored["sources"]["reference"] = deepcopy(restored["current"]["sources"])
        restored["basis_hash"] = input_fingerprint(
            {"sources": restored["current"]["sources"], "policy": policy, "start_date": str(start_date)}
        )
    return restored

"""明确提交建档后的AI来源桥接；保留自述和专业规则的区别。"""

import os
from datetime import date, datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import select

from yuxi.repositories.family_repository import FamilyRepository
from yuxi.services.family_service import authorized_fields
from yuxi.services.health_nutrition_service import input_fingerprint
from yuxi.services.health_quality_types import ProfileProjection, QualityRules
from yuxi.services.health_quality_checks import external_projection
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.storage.postgres.models_health import (
    FamilyMember,
    HealthFamilyProfileLink,
    HealthGrant,
    HealthProcessingConsent,
    HealthMiniappProfileCoding,
)
from yuxi.utils.datetime_utils import utc_now_naive


async def bind_submitted_profile(session, uid, family, members, consent):
    """只有用户在保存并分析时明确接受的当前处理方可建立用途来源。"""
    from yuxi.services.health_vision_service import health_vision_service

    config = await health_vision_service.configuration(session)
    configured = config["meal_plan"]
    if not configured["available"] or consent != {
        "processor": configured["processor"],
        "policy_version": config["policy_version"],
    }:
        raise HealthVisionError("policy_changed", "分析处理方配置已变化，请重新读取后保存", 409)
    for member in members:
        # 已认领家人的AI权限不能由家庭管理员代为建立。
        if member.subject_uid not in (None, uid):
            continue
        link = await session.scalar(
            select(HealthFamilyProfileLink).where(HealthFamilyProfileLink.source_member_id == member.id)
        )
        if link is None:
            health = FamilyMember(
                id=str(uuid4()),
                owner_uid=uid,
                display_name=member.name,
                relationship_label="本人" if member.subject_uid == uid else member.relationship,
            )
            session.add(health)
            await session.flush()
            link = HealthFamilyProfileLink(
                member_id=health.id,
                source_member_id=member.id,
                family_id=family.id,
                actor_uid=uid,
                source_kind="miniapp_reported",
            )
            session.add(link)
            session.add(HealthGrant(member_id=health.id, actor_uid=uid, scopes=["ai_use", "diet_edit", "profile_view"]))
        elif link.actor_uid != uid:
            if (
                link.source_kind != "miniapp_reported"
                or member.subject_uid != uid
                or link.actor_uid != family.owner_uid
            ):
                raise HealthVisionError("profile_link_conflict", "成员已有独立的分析来源，请使用原有授权", 409)
            health = await session.get(FamilyMember, link.member_id)
            if health is None or health.owner_uid != link.actor_uid:
                raise HealthVisionError("profile_link_conflict", "成员分析来源归属已变化，请重新核对", 409)
            previous = await session.get(HealthGrant, (link.member_id, link.actor_uid))
            if previous is not None:
                previous.revoked_at = utc_now_naive()
            health.owner_uid = uid
            health.relationship_label = "本人"
            link.actor_uid = uid
            own_grant = await session.get(HealthGrant, (link.member_id, uid))
            if own_grant is None:
                session.add(
                    HealthGrant(member_id=link.member_id, actor_uid=uid, scopes=["ai_use", "diet_edit", "profile_view"])
                )
            else:
                own_grant.scopes, own_grant.revoked_at = ["ai_use", "diet_edit", "profile_view"], None
            from yuxi.repositories.health_quality_repository import HealthQualityRepository

            await HealthQualityRepository(session).invalidate(member_id=link.member_id, reason="member_claimed")
        # 既有专业确认来源保留原语义，不能因再次建档降为自述并丢失临床资料。
        for purpose in ("meal_plan",):
            record = await session.get(HealthProcessingConsent, (link.member_id, uid, purpose))
            if record is None:
                record = HealthProcessingConsent(member_id=link.member_id, actor_uid=uid, purpose=purpose)
                session.add(record)
            record.processor, record.policy_version, record.granted_at, record.revoked_at = (
                configured["processor"],
                config["policy_version"],
                utc_now_naive(),
                None,
            )


async def submitted_profile_projection(session, link):
    """从当前正式字段和批准编码规则投影，不伪造外部专业确认。"""
    if link.source_kind == "self_confirmed":
        from yuxi.repositories.health_family_profile_repository import HealthFamilyProfileRepository

        try:
            await HealthFamilyProfileRepository(session).confirmed_source(link.member_id)
        except HealthVisionError as error:
            if error.code != "family_profile_unconfirmed":
                raise
            return {**external_projection(None, "profile", link.member_id), "reason": error.code}
    repo = FamilyRepository(session)
    family = await repo.get_family(link.family_id, link.actor_uid)
    member = await repo.member(link.family_id, link.source_member_id) if family else None
    if member is None or not member.is_active or member.subject_uid not in (None, link.actor_uid):
        raise HealthVisionError("source_invalidated", "建档成员归属或授权已变化", 410)
    allowed = authorized_fields(family, member, link.actor_uid, family_sharing=True)
    if not {"birth_date", "dietary_details"} <= allowed:
        raise HealthVisionError("source_invalidated", "建档来源字段已不可读取", 410)
    result = {
        "id": member.id,
        "version": member.version,
        "content_hash": input_fingerprint(member.profile),
        "status": "not_ready",
        "reason": "profile_coding_rules_unavailable",
        "payload": None,
        "attestation": None,
        "source_kind": "user_reported",
    }
    if link.source_kind == "self_confirmed":
        from yuxi.services.miniapp_profile_types import miniapp_onboarding_ready

        if not miniapp_onboarding_ready(member, family):
            return {**result, "reason": "family_profile_incomplete"}
    from yuxi.repositories.health_quality_repository import HealthQualityRepository

    rule_code = os.environ.get("HEALTH_DAILY_RULE_CODE", "")
    record = await HealthQualityRepository(session).rules(rule_code)
    rules = external_projection(record, "rules", rule_code)
    if rules["status"] != "ready":
        return result
    approved = QualityRules.model_validate(rules["payload"])
    mapping = approved.miniapp_profile_codes
    if mapping is None:
        return result
    profile_hash = input_fingerprint(member.profile)
    coding = await session.get(HealthMiniappProfileCoding, (link.member_id, profile_hash, rules["content_hash"]))
    try:
        if coding is not None:
            from yuxi.services.miniapp_profile_coding import validated_profile_mapping

            mapping = validated_profile_mapping(member.profile, mapping, coding.coding)
        payload = code_submitted_profile(member.profile, approved, mapping)
    except (KeyError, ValueError):
        return {**result, "reason": "profile_coding_unavailable"}
    return {
        **result,
        "status": "ready",
        "reason": None,
        "payload": payload,
        "content_hash": input_fingerprint({"profile": member.profile, "rule_hash": rules["content_hash"]}),
        "display_name": member.name,
        "source_kind": "user_reported",
        "reported_notes": {
            key: (member.profile.get("dietary_details") or {}).get(key)
            for key in (
                "goals",
                "cuisines",
                "tastePreferences",
                "flavors",
                "recentNote",
                "hypoglycemiaRisk",
                "kidneyCondition",
                "clinicianGuidance",
            )
        },
        "attestation": {
            "source_kind": "user_reported",
            "family_id": family.id,
            "source_member_id": member.id,
            "version": member.version,
            "coding_rule_version": record.version,
            "coding_rule_hash": rules["content_hash"],
        },
    }


def code_submitted_profile(profile, rules, mapping):
    """年龄段和文本到编码完全由已发布规则提供，缺项保持未知或不可用。"""
    born = date.fromisoformat(profile["birth_date"]) if profile.get("birth_date") else None
    today = datetime.now(ZoneInfo("Asia/Shanghai")).date()
    age = today.year - born.year - ((today.month, today.day) < (born.month, born.day)) if born else None
    populations = [
        code
        for span, code in mapping.get("population_age_ranges", {}).items()
        if age is not None and int(span.split(":")[0]) <= age <= int(span.split(":")[1])
    ]
    if len(populations) != 1 or populations[0] not in rules.allowed_population_codes:
        raise ValueError("没有明确批准的人群编码")
    dietary = profile.get("dietary_details") or {}
    values = {}
    for target, state_key, list_key in (
        ("conditions", "healthStatus", "conditions"),
        ("allergies", "allergyStatus", "allergies"),
        ("intolerances", "intoleranceStatus", "intolerances"),
        ("avoidances", "avoidanceStatus", "avoidances"),
        ("doctor_requirements", "doctorStatus", "clinicianGuidance"),
    ):
        state = dietary.get(state_key, "unknown")
        items = dietary.get(list_key) or []
        if isinstance(items, str):
            items = [items]
        if target == "conditions":
            items = [dietary.get("otherCondition", "") if item == "其他" else item for item in items]
        values[target] = {
            "state": "specified" if state == "set" else state,
            "codes": list(dict.fromkeys(mapping[target][label] for label in items)) if state == "set" else [],
        }
    preferences = dietary.get("cuisines", []) + dietary.get("tastePreferences", []) + dietary.get("flavors", [])
    preference_codes = list(
        dict.fromkeys(
            mapping.get("preferences", {})[label] for label in preferences if label in mapping.get("preferences", {})
        )
    )
    values["preferences"] = {"state": "specified" if preference_codes else "unknown", "codes": preference_codes}
    return ProfileProjection(
        population_code=populations[0],
        age_years=age,
        sex_code=mapping.get("sex", {}).get(profile.get("sex")),
        weight_kg=dietary.get("statedWeightKg"),
        height_cm=profile.get("height_cm"),
        activity_code=mapping.get("activity", {}).get(profile.get("activity_level")),
        **values,
    ).model_dump(mode="json")

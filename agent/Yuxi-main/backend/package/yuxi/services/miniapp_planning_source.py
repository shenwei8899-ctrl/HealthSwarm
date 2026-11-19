"""明确提交建档后的AI来源桥接；保留自述和专业规则的区别。"""

import os
from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select

from yuxi.repositories.family_repository import FamilyRepository
from yuxi.services.family_service import authorized_fields
from yuxi.services.health_nutrition_service import input_fingerprint
from yuxi.services.health_quality_types import ProfileProjection, QualityRules
from yuxi.services.health_quality_checks import external_projection
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.storage.postgres.models_health import (
    HealthProcessingConsent,
    HealthMiniappProfileCoding,
)
from yuxi.utils.datetime_utils import utc_now_naive


async def bind_submitted_profile(session, uid, family, members, consent):
    """只有用户在保存并分析时明确接受的当前处理方可建立用途来源。"""
    from yuxi.services.health_vision_service import health_vision_service

    config = await health_vision_service.configuration(session)
    purpose = consent.get("purpose", "meal_plan")
    if purpose not in {"consultation", "meal_plan"}:
        raise HealthVisionError("invalid_purpose", "请选择营养咨询或餐单分析用途", 422)
    configured = config[purpose]
    expected = {
        "processor": configured["processor"],
        "policy_version": config["policy_version"],
    }
    if "purpose" in consent:
        expected["purpose"] = purpose
    if not configured["available"] or consent != expected:
        raise HealthVisionError("policy_changed", "分析处理方配置已变化，请重新读取后保存", 409)
    from yuxi.services.family_service import FamilyService
    from yuxi.services.miniapp_report_service import ensure_member_reports
    from yuxi.repositories.health_vision_repository import HealthVisionRepository

    service = FamilyService(session, uid)
    for member in members:
        current_family, current = await service.context(family.id, member.id)
        link = await ensure_member_reports(service, current_family, current)
        await HealthVisionRepository(session).authorize(link.member_id, uid, "ai_use")
        # 旧客户端的明确同意仍留审计记录，不转移成员归属，也不改写账号 grant。
        record = await session.get(HealthProcessingConsent, (link.member_id, uid, purpose))
        if record is None:
            record = HealthProcessingConsent(member_id=link.member_id, actor_uid=uid, purpose=purpose)
            session.add(record)
        record.processor, record.policy_version, record.granted_at, record.revoked_at = (
            configured["processor"], config["policy_version"], utc_now_naive(), None,
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
    from yuxi.storage.postgres.models_business import FamilyArchive

    family = await session.scalar(select(FamilyArchive).where(
        FamilyArchive.id == link.family_id, FamilyArchive.archived_at.is_(None)
    ))
    member = await repo.member(link.family_id, link.source_member_id) if family else None
    if member is None or not member.is_active or member.family_id != link.family_id:
        raise HealthVisionError("source_invalidated", "建档成员已不在当前家庭", 410)
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
    from yuxi.services.miniapp_profile_types import miniapp_onboarding_ready, miniapp_profile_complete

    complete = (
        miniapp_onboarding_ready(member, family)
        if link.source_kind == "self_confirmed"
        else miniapp_profile_complete(member)
    )
    if not complete:
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
    except HealthVisionError as error:
        if error.code != "profile_coding_rules_unavailable":
            raise
        return result
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
        raise HealthVisionError(
            "profile_coding_rules_unavailable", "系统尚未配置对应人群的配餐规则，已填写资料无需重复提交", 503
        )
    sex_code = mapping.get("sex", {}).get(profile.get("sex"))
    if sex_code is None:
        raise HealthVisionError(
            "profile_coding_rules_unavailable", "系统的性别编码规则尚未配置完成，已填写资料无需重复提交", 503
        )
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
        sex_code=sex_code,
        weight_kg=dietary.get("statedWeightKg"),
        height_cm=profile.get("height_cm"),
        activity_code=mapping.get("activity", {}).get(profile.get("activity_level")),
        **values,
    ).model_dump(mode="json")

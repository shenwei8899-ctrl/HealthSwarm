"""原建档页面的云端版本、成员归属和原请求恢复。"""

from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import text
from yuxi.services.family_service import (
    FamilyService,
    is_adult,
    member_view,
)
from yuxi.services.health_nutrition_service import input_fingerprint
from yuxi.services.miniapp_profile_types import (
    miniapp_onboarding_ready,
    miniapp_profile_complete,
    saved_miniapp_member,
)
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_business import FamilyMember, FamilyProfileRevision
from yuxi.storage.postgres.models_health import (
    HealthMiniappProfileReceipt,
)
from yuxi.utils.datetime_utils import utc_now_naive


async def read_miniapp_profile(uid, fid):
    """读取当前字段授权内的正式成员及默认就餐者。"""
    async with pg_manager.get_async_session_context() as db:
        service = FamilyService(db, uid)
        family, _ = await service.context(fid)
        return await profile_result(service, family)


async def start_miniapp_analysis(uid, fid, data):
    """核对已保存成员后，同事务建立来源和用途同意；重放不恢复撤回记录。"""
    from pydantic import ValidationError
    from yuxi.services.health_vision_types import HealthVisionError
    from yuxi.services.miniapp_planning_source import bind_submitted_profile

    digest = input_fingerprint(data.model_dump(mode="json"))
    async with pg_manager.get_async_session_context() as db:
        await db.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
            {"key": f"miniapp-profile:{uid}:{data.client_request_id}"},
        )
        service = FamilyService(db, uid)
        family, member = await service.context(fid, str(data.member_id))
        receipt = await db.get(HealthMiniappProfileReceipt, (uid, str(data.client_request_id)))
        if receipt:
            if receipt.family_id != fid or receipt.fingerprint != digest:
                raise HealthVisionError("request_conflict", "同一确认请求不能改变成员、版本或用途", 409)
            return await profile_result(service, family)
        automatic = data.action == "open_consultation"
        service.require_version(member, data.expected_version)
        try:
            saved_miniapp_member(member)
        except ValidationError as exc:
            labels = {
                "birth_date": "出生日期",
                "height_cm": "身高",
                "activity_level": "日常活动量",
                "sex": "性别",
                "name": "姓名或称呼",
                "statedWeightKg": "体重",
                "weight_kg": "体重",
                "dietary": "饮食与健康资料",
            }
            messages = list(
                dict.fromkeys(
                    error["msg"].removeprefix("Value error, ")
                    if error["type"] == "value_error"
                    else "请核对" + labels.get(str(error["loc"][-1]), "饮食与健康资料")
                    for error in exc.errors()
                )
            )
            raise HealthVisionError("profile_incomplete", "请补充资料：" + "；".join(messages), 422) from None
        if automatic:
            from yuxi.services.health_vision_service import health_vision_service

            config = await health_vision_service.configuration(db)
            configured = config["consultation"]
            if not configured["available"]:
                raise HealthVisionError("configuration_unavailable", "营养咨询服务暂未就绪，档案已保存", 503)
            from yuxi.services.miniapp_report_service import ensure_member_reports
            from yuxi.repositories.health_vision_repository import HealthVisionRepository

            link = await ensure_member_reports(service, family, member)
            await HealthVisionRepository(db).authorize(link.member_id, uid, "ai_use")
            return await profile_result(service, family)
        processing = {
            "purpose": data.purpose,
            "processor": data.processor,
            "policy_version": data.policy_version,
        }
        await bind_submitted_profile(db, uid, family, [member], processing)
        member.invitation_analysis_pending = False
        member.confirmed_version, member.confirmed_at = member.version, utc_now_naive()
        db.add(
            HealthMiniappProfileReceipt(
                actor_uid=uid,
                request_id=str(data.client_request_id),
                family_id=fid,
                fingerprint=digest,
                member_refs={member.id: member.id},
            )
        )
        await service.repo.audit(
            fid,
            member.id,
            uid,
            "miniapp.analysis.consent",
            member.version,
        )
        await db.flush()
        return await profile_result(service, family)


async def save_miniapp_profile(uid, fid, data):
    """完整建档、历史及幂等收据同事务提交，不隐式授予模型权限。"""
    async with pg_manager.get_async_session_context() as db:
        return await save_miniapp_profile_in_session(db, uid, fid, data)


async def save_miniapp_profile_in_session(db, uid, fid, data):
    """保存与准备登记共享事务，保留原建档收据及字段授权规则。"""
    digest = input_fingerprint(data.submission_dump())
    await db.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
        {"key": f"miniapp-profile:{uid}:{data.client_request_id}"},
    )
    service = FamilyService(db, uid)
    family, _ = await service.context(fid)
    receipt = await db.get(HealthMiniappProfileReceipt, (uid, str(data.client_request_id)))
    if receipt:
        if receipt.family_id != fid or receipt.fingerprint != digest:
            raise HTTPException(409, "同一保存请求不能改变建档内容")
        return {**await profile_result(service, family), "memberRefs": receipt.member_refs}
    if data.analysis_consent is not None and data.analysis_consent.get("purpose") not in {
        "consultation",
        "meal_plan",
    }:
        raise HTTPException(
            409,
            "当前小程序版本不能确认分析同意，请更新小程序后在成员家庭档案中明确确认；本次未保存资料或改变授权。",
        )
    member_only = data.scope == "self"
    if family.owner_uid != uid and not member_only:
        raise HTTPException(403, "请由家庭创建者维护默认就餐设置")
    if not member_only and family.version != data.family_version:
        raise HTTPException(409, "家庭档案已更新，请重新读取后保存")
    actor = await service.repo.subject_member(fid, uid)
    if member_only and (len(data.members) != 1 or str(data.members[0].member_id) != actor.id):
        raise HTTPException(403, "受邀建档只能填写和确认本人档案")
    refs, used, submitted = {}, set(), []
    family_changed = False
    for draft in data.members:
        if draft.member_id:
            _, member = await service.context(fid, str(draft.member_id))
            service.require_version(member, draft.version)
        elif draft.relation == "本人":
            member = actor
        else:
            member = FamilyMember(
                id=str(uuid4()),
                family_id=fid,
                name=draft.name,
                relationship=draft.relation,
                profile={},
                version=1,
            )
            db.add(member)
            family_changed = True
            await db.flush()
        if member.id in used or draft.relation == "本人" and member.subject_uid != uid:
            raise HTTPException(422, "成员身份引用不一致")
        used.add(member.id)
        changes = {
            "sex": draft.sex,
            "birth_date": draft.birth_date.isoformat() if draft.birth_date else None,
            "height_cm": draft.height_cm,
            "goal": "、".join(draft.dietary.goals) or None,
            "allergens": draft.dietary.allergies if draft.dietary.allergyStatus != "unknown" else None,
            "avoidances": draft.dietary.avoidances if draft.dietary.avoidanceStatus != "unknown" else None,
            "doctor_instructions": draft.dietary.clinicianGuidance or None,
            "dietary_details": {
                **draft.dietary.model_dump(mode="json"),
                "statedWeightKg": draft.weight_kg,
            },
        }
        if draft.activity_level is not None:
            changes["activity_level"] = draft.activity_level
        service.require_fields(family, member, changes, write=True)
        from yuxi.services.diet_stage_guard import require_stage_goal_entry

        require_stage_goal_entry(member.profile or {}, {**(member.profile or {}), **changes})
        relationship = member.relationship if member_only else draft.relation
        if member.name != draft.name or member.relationship != relationship:
            if member.subject_uid and member.subject_uid != uid:
                raise HTTPException(403, "其他已认领成员的身份不能由此建档修改")
            member.name, member.relationship = draft.name, relationship
            family_changed = True
            member.relationship_version = (member.relationship_version or 1) + 1
        if any((member.profile or {}).get(key) != value for key, value in changes.items()):
            birth_changed = (member.profile or {}).get("birth_date") != changes["birth_date"]
            member.profile = {**(member.profile or {}), **changes}
            if birth_changed and member.guardian_status in {"pending", "approved"}:
                member.guardian_status = "revoked"
                member.guardian_version += 1
                await service.repo.audit(fid, member.id, uid, "guardian.revoke", member.guardian_version)
            if birth_changed and member.subject_uid and not is_adult(member):
                for ward in await service.repo.members(fid):
                    if ward.guardian_uid == member.subject_uid and ward.guardian_status in {"pending", "approved"}:
                        ward.guardian_status = "revoked"
                        ward.guardian_version += 1
                        await service.repo.audit(fid, ward.id, uid, "guardian.revoke", ward.guardian_version)
            member.version += 1
            member.confirmed_at = None
            member.updated_at = utc_now_naive()
            db.add(
                FamilyProfileRevision(
                    member_id=member.id,
                    version=member.version,
                    profile=member.profile,
                    actor_uid=uid,
                )
            )
            health_id = await service.repo.linked_health_member(fid, member.id)
            if health_id:
                from yuxi.repositories.health_quality_repository import (
                    HealthQualityRepository,
                )

                await HealthQualityRepository(db).invalidate(member_id=health_id, reason="family_profile_changed")
        refs[draft.client_ref] = member.id
        submitted.append(member)
        if member.subject_uid == uid:
            member.invitation_review_pending = False
        member.confirmed_version = member.version
        member.confirmed_at = utc_now_naive()
    from yuxi.services.miniapp_report_service import ensure_member_reports

    for member in submitted:
        await ensure_member_reports(service, family, member)
    if data.analysis_consent is not None or data.plan_consent is not None:
        from yuxi.services.miniapp_planning_source import bind_submitted_profile
        from yuxi.services.health_vision_types import HealthVisionError

        # 当前家庭成员可使用所有已提交的共享档案。
        analysis_members = submitted
        if data.analysis_consent is not None:
            await bind_submitted_profile(db, uid, family, analysis_members, data.analysis_consent)
        if data.plan_consent is not None:
            if data.plan_consent.get("purpose") != "meal_plan":
                raise HealthVisionError("invalid_purpose", "请选择餐单分析用途", 422)
            await bind_submitted_profile(db, uid, family, analysis_members, data.plan_consent)
        for member in analysis_members:
            member.invitation_analysis_pending = False
    if not member_only:
        settings = {
            **(family.settings or {}),
            "default_diners": [refs[ref] for ref in data.default_diners],
            "usage_mode": data.usage_mode,
            "miniapp_onboarded": True,
        }
        if family_changed or family.settings != settings:
            family.settings = settings
            family.version += 1
    db.add(
        HealthMiniappProfileReceipt(
            actor_uid=uid,
            request_id=str(data.client_request_id),
            family_id=fid,
            fingerprint=digest,
            member_refs=refs,
        )
    )
    await service.repo.audit(fid, None, uid, "miniapp.onboarding.save", family.version)
    await db.flush()
    return {**await profile_result(service, family), "memberRefs": refs}


async def profile_result(service, family):
    """只投影当前可读资料；不把空字段改成无疾病或无过敏。"""
    from yuxi.services.diet_stage_summaries import family_stage_summaries

    summaries = await family_stage_summaries(service.db, family.id)
    members = []
    actor = None
    for member in await service.repo.members(family.id):
        if not member.is_active:
            continue
        if member.subject_uid == service.uid:
            actor = member
        health_id = await service.repo.linked_health_member(family.id, member.id)
        if not health_id:
            from yuxi.services.miniapp_report_service import ensure_member_reports

            health_id = (await ensure_member_reports(service, family, member)).member_id
        view = member_view(family, member, service.uid)
        profile = view.get("profile") or {}
        dietary = {
            "recentNote": profile.get("medical_history") or "",
            "doctorStatus": "set" if profile.get("doctor_instructions") else "unknown",
            "clinicianGuidance": profile.get("doctor_instructions") or "",
            "allergyStatus": "unknown"
            if profile.get("allergens") is None
            else "set"
            if profile["allergens"]
            else "none",
            "allergies": profile.get("allergens") or [],
            "avoidanceStatus": "unknown"
            if profile.get("avoidances") is None
            else "set"
            if profile["avoidances"]
            else "none",
            "avoidances": profile.get("avoidances") or [],
            "goals": [profile["goal"]] if profile.get("goal") else [],
            **(profile.get("dietary_details") or {}),
        }
        members.append(
            {
                "id": member.id,
                "memberId": member.person_id or member.id,
                "healthMemberId": health_id,
                "stageManaged": bool(member.profile.get("diet_stage_managed")),
                "stageSummary": summaries.get(member.id) if {"goal", "dietary_details"} <= set(view["allowed_fields"]) else None,
                "version": member.version,
                "relationshipVersion": member.relationship_version,
                "isSelf": member.subject_uid == service.uid,
                "canConfirmAnalysis": member.is_active,
                "confirmed": member.confirmed_version == member.version,
                "editableFields": view["editable_fields"],
                "claimed": member.subject_uid is not None,
                "name": member.name,
                "relation": "本人" if member.subject_uid == service.uid else member.relationship,
                "birthDate": profile.get("birth_date") or "",
                "gender": {"female": "女", "male": "男"}.get(profile.get("sex"), "未填写"),
                "height": profile.get("height_cm") or "",
                "weight": dietary.get("statedWeightKg") or "",
                **dietary,
                "activityLevel": profile.get("activity_level") or "",
            }
        )
    settings = family.settings or {}
    return {
        "householdId": family.id,
        "householdName": family.name,
        "familyVersion": family.version,
        "usageMode": settings.get("usage_mode", "家庭使用"),
        "defaultDiners": settings.get("default_diners", []),
        "onboarded": miniapp_onboarding_ready(actor, family),
        "completeProfile": miniapp_profile_complete(actor),
        "invitationReviewPending": bool(actor and actor.invitation_review_pending),
        "invitationAnalysisPending": bool(actor and actor.invitation_analysis_pending),
        "selfMemberId": actor.id if actor else None,
        "selfPersonId": (actor.person_id or actor.id) if actor else None,
        "isOwner": family.owner_uid == service.uid,
        "members": members,
        "source": "api",
    }

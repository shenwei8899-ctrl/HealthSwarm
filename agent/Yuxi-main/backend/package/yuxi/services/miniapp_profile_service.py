"""原建档页面的云端版本、成员归属和原请求恢复。"""

from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import text, select
from sqlalchemy.dialects.postgresql import insert

from yuxi.services.family_service import FamilyService, member_view, is_adult, guardian_active
from yuxi.services.health_nutrition_service import input_fingerprint
from yuxi.services.miniapp_profile_types import MiniappMemberInput, miniapp_onboarding_ready, miniapp_profile_complete
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_business import FamilyMember, FamilyProfileRevision
from yuxi.storage.postgres.models_health import HealthMiniappProfileReceipt, HealthProcessingConsent, HealthGrant
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
        if member.subject_uid != uid and not guardian_active(member, uid):
            raise HealthVisionError("member_consent_required", "请由成员本人或已验证的监护人确认分析同意", 403)
        receipt = await db.get(HealthMiniappProfileReceipt, (uid, str(data.client_request_id)))
        if receipt:
            if receipt.family_id != fid or receipt.fingerprint != digest:
                raise HealthVisionError("request_conflict", "同一确认请求不能改变成员、版本或用途", 409)
            return await profile_result(service, family)
        automatic = data.action == "open_consultation"
        if automatic and member.subject_uid != uid:
            raise HealthVisionError("member_unavailable", "只能自动衔接当前账号本人的营养咨询", 403)
        service.require_version(member, data.expected_version)
        profile = member.profile or {}
        try:
            MiniappMemberInput.model_validate(
                {
                    "client_ref": member.id,
                    "member_id": member.id,
                    "version": member.version,
                    "name": member.name,
                    "relation": member.relationship,
                    "birth_date": profile.get("birth_date"),
                    "sex": profile.get("sex") or "unspecified",
                    "height_cm": profile.get("height_cm"),
                    "dietary": profile.get("dietary_details") or {},
                }
            )
        except ValidationError as exc:
            labels = {
                "birth_date": "出生日期",
                "height_cm": "身高",
                "sex": "性别",
                "name": "姓名或称呼",
                "statedWeightKg": "体重",
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

            # 本人读取完整且当前的服务端资料即可衔接咨询，不要求额外确认步骤。
            if member.confirmed_version != member.version:
                member.confirmed_version, member.confirmed_at = member.version, utc_now_naive()
            config = await health_vision_service.configuration(db)
            configured = config["consultation"]
            if not configured["available"]:
                raise HealthVisionError("configuration_unavailable", "营养咨询服务暂未就绪，档案已保存", 503)
            processing = {
                "purpose": "consultation",
                "processor": configured["processor"],
                "policy_version": config["policy_version"],
            }
            health_id = await service.repo.linked_health_member(fid, member.id)
            existing = None
            if health_id:
                grant = await db.get(HealthGrant, (health_id, uid), populate_existing=True)
                if grant is not None and (grant.revoked_at is not None or "ai_use" not in grant.scopes):
                    return await profile_result(service, family)
                if grant is not None:
                    # 与主动停用的写入按同一用途行排序，不反向获取健康成员锁。
                    await db.execute(
                        insert(HealthProcessingConsent)
                        .values(
                            member_id=health_id,
                            actor_uid=uid,
                            purpose="consultation",
                            processor=processing["processor"],
                            policy_version=processing["policy_version"],
                            granted_at=utc_now_naive(),
                        )
                        .on_conflict_do_nothing(index_elements=["member_id", "actor_uid", "purpose"])
                    )
                    existing = await db.scalar(
                        select(HealthProcessingConsent)
                        .where(
                            HealthProcessingConsent.member_id == health_id,
                            HealthProcessingConsent.actor_uid == uid,
                            HealthProcessingConsent.purpose == "consultation",
                        )
                        .with_for_update()
                        .execution_options(populate_existing=True)
                    )
            if existing is not None and existing.revoked_at is not None:
                return await profile_result(service, family)
            if (
                existing is not None
                and existing.processor == processing["processor"]
                and existing.policy_version == processing["policy_version"]
            ):
                return await profile_result(service, family)
        else:
            processing = {"purpose": data.purpose, "processor": data.processor, "policy_version": data.policy_version}
        await bind_submitted_profile(db, uid, family, [member], processing)
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
            "miniapp.consultation.open" if automatic else "miniapp.analysis.consent",
            member.version,
        )
        await db.flush()
        return await profile_result(service, family)


async def save_miniapp_profile(uid, fid, data):
    """完整建档、历史及幂等收据同事务提交，不隐式授予模型权限。"""
    digest = input_fingerprint(data.model_dump(mode="json"))
    async with pg_manager.get_async_session_context() as db:
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
            return await profile_result(service, family)
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
        for draft in data.members:
            if draft.member_id:
                _, member = await service.context(fid, str(draft.member_id))
                service.require_version(member, draft.version)
            elif draft.relation == "本人":
                member = actor
            else:
                member = FamilyMember(
                    id=str(uuid4()), family_id=fid, name=draft.name, relationship=draft.relation, profile={}, version=1
                )
                db.add(member)
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
                "dietary_details": {**draft.dietary.model_dump(mode="json"), "statedWeightKg": draft.weight_kg},
            }
            service.require_fields(family, member, changes, write=True)
            relationship = member.relationship if member_only else draft.relation
            if member.name != draft.name or member.relationship != relationship:
                if member.subject_uid and member.subject_uid != uid:
                    raise HTTPException(403, "其他已认领成员的身份不能由此建档修改")
                member.name, member.relationship = draft.name, relationship
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
                        member_id=member.id, version=member.version, profile=member.profile, actor_uid=uid
                    )
                )
                health_id = await service.repo.linked_health_member(fid, member.id)
                if health_id:
                    from yuxi.repositories.health_quality_repository import HealthQualityRepository

                    await HealthQualityRepository(db).invalidate(member_id=health_id, reason="family_profile_changed")
            refs[draft.client_ref] = member.id
            submitted.append(member)
            if member.subject_uid == uid:
                member.confirmed_version = member.version
                member.confirmed_at = utc_now_naive()
        if data.analysis_consent is not None:
            from yuxi.services.miniapp_planning_source import bind_submitted_profile

            # 建档页的用途复选框只确认本人；监护人分析须从具体儿童档案明确确认。
            analysis_members = [member for member in submitted if member.subject_uid == uid]
            await bind_submitted_profile(db, uid, family, analysis_members, data.analysis_consent)
        if not member_only:
            family.settings = {
                **(family.settings or {}),
                "default_diners": [refs[ref] for ref in data.default_diners],
                "usage_mode": data.usage_mode,
                "miniapp_onboarded": True,
            }
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
        return await profile_result(service, family)


async def profile_result(service, family):
    """只投影当前可读资料；不把空字段改成无疾病或无过敏。"""
    members = []
    actor = None
    for member in await service.repo.members(family.id):
        if not member.is_active:
            continue
        if member.subject_uid == service.uid:
            actor = member
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
                "healthMemberId": await service.repo.linked_health_member(family.id, member.id),
                "version": member.version,
                "relationshipVersion": member.relationship_version,
                "isSelf": member.subject_uid == service.uid,
                "canConfirmAnalysis": member.subject_uid == service.uid or guardian_active(member, service.uid),
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
        "selfMemberId": actor.id if actor else None,
        "isOwner": family.owner_uid == service.uid,
        "members": members,
        "source": "api",
    }

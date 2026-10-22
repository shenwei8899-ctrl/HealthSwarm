"""原建档页面的云端版本、成员归属和原请求恢复。"""

from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import text

from yuxi.services.family_service import FamilyService, member_view, is_adult
from yuxi.services.health_nutrition_service import input_fingerprint
from yuxi.services.miniapp_profile_types import miniapp_onboarding_ready
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_business import FamilyMember, FamilyProfileRevision
from yuxi.storage.postgres.models_health import HealthMiniappProfileReceipt
from yuxi.utils.datetime_utils import utc_now_naive


async def read_miniapp_profile(uid, fid):
    """读取当前字段授权内的正式成员及默认就餐者。"""
    async with pg_manager.get_async_session_context() as db:
        service = FamilyService(db, uid)
        family, _ = await service.context(fid)
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

            await bind_submitted_profile(db, uid, family, submitted, data.analysis_consent)
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
        dietary = profile.get("dietary_details") or {}
        if not dietary:
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
            }
        members.append(
            {
                "id": member.id,
                "healthMemberId": await service.repo.linked_health_member(family.id, member.id),
                "version": member.version,
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
        "selfMemberId": actor.id if actor else None,
        "isOwner": family.owner_uid == service.uid,
        "members": members,
        "source": "api",
    }

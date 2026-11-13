"""普通家庭档案保存时建立报告关联，不建立 AI 用途同意。"""

from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select

from yuxi.services.health_vision_types import FAMILY_REPORT_SCOPES
from yuxi.storage.postgres.models_health import (
    FamilyMember,
    HealthFamilyProfileLink,
    HealthGrant,
    HealthProfileSnapshot,
)


async def enable_reports(service, family_id: str, member_id: str, expected_version: int):
    """兼容旧客户端；有效家庭关系已经包含报告访问。"""
    family, member = await service.context(family_id, member_id)
    service.require_version(member, expected_version)
    link = await ensure_member_reports(service, family, member)
    await service.db.commit()
    return {"member_id": link.member_id, "scopes": sorted(FAMILY_REPORT_SCOPES)}


async def ensure_member_reports(service, family, member):
    """复用唯一成员身份，并在调用方档案事务中登记普通报告权限。"""
    db = service.db
    link = await db.scalar(
        select(HealthFamilyProfileLink).where(HealthFamilyProfileLink.source_member_id == member.id).with_for_update()
    )
    if link is None:
        candidates = (
            list(
                (
                    await db.scalars(
                        select(FamilyMember).where(
                            FamilyMember.owner_uid == service.uid,
                            FamilyMember.relationship_label == "本人",
                            FamilyMember.id.not_in(select(HealthFamilyProfileLink.member_id)),
                            FamilyMember.id.not_in(select(HealthProfileSnapshot.member_id)),
                        )
                    )
                ).all()
            )
            if member.subject_uid == service.uid
            else []
        )
        # 独立专业来源和多个不明确对象保留原样，普通家庭档案使用自己的唯一关联。
        reuse = len(candidates) == 1
        preferred_id = member.person_id
        if not reuse and preferred_id and await db.get(FamilyMember, preferred_id) is not None:
            # 人员编号可延续，旧家庭的健康记录仍使用原有存储键。
            preferred_id = None
        health = (
            candidates[0]
            if reuse
            else FamilyMember(
                id=preferred_id or str(uuid4()),
                owner_uid=service.uid,
                display_name=member.name,
                relationship_label="本人" if member.subject_uid == service.uid else member.relationship,
            )
        )
        if not reuse:
            db.add(health)
            await db.flush()
        link = HealthFamilyProfileLink(
            member_id=health.id,
            source_member_id=member.id,
            family_id=family.id,
            actor_uid=service.uid,
            source_kind="miniapp_reported",
        )
        db.add(link)
    else:
        if link.family_id != family.id or await db.get(FamilyMember, link.member_id) is None:
            raise HTTPException(409, "成员的健康档案关联已变化，请重新核对")

    if member.person_id is None:
        member.person_id = link.member_id
    grant = await db.get(HealthGrant, (link.member_id, service.uid), populate_existing=True)
    if grant is None:
        grant = HealthGrant(member_id=link.member_id, actor_uid=service.uid, scopes=sorted(FAMILY_REPORT_SCOPES))
        db.add(grant)
        changed = True
    else:
        changed = grant.revoked_at is None and not FAMILY_REPORT_SCOPES <= set(grant.scopes)
        if changed:
            grant.scopes = sorted(set(grant.scopes) | FAMILY_REPORT_SCOPES)
    if changed:
        await service.repo.audit(family.id, member.id, service.uid, "reports.profile_link", member.version)
    await db.flush()
    return link

"""外部档案、批准规则与专业资格的版本投影导入和撤回。"""

from datetime import UTC
from uuid import uuid4

from sqlalchemy import select

from yuxi.repositories.health_quality_repository import HealthQualityRepository
from yuxi.repositories.health_vision_repository import HealthVisionRepository
from yuxi.services.health_evidence_service import require_evidence_admin
from yuxi.services.health_quality_checks import external_projection, projection_digest
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_business import User
from yuxi.storage.postgres.models_health import HealthProfileSnapshot, HealthRuleSnapshot, HealthProfessionalReviewer
from yuxi.utils.datetime_utils import utc_now_naive


def import_parts(data):
    """同一归一化依据同时用于摘要与有效期，禁止未来确认或已过期导入。"""
    attested = data.attested_at.astimezone(UTC).replace(tzinfo=None)
    valid_until = data.valid_until.astimezone(UTC).replace(tzinfo=None)
    if attested > utc_now_naive() or valid_until <= utc_now_naive():
        raise HealthVisionError("external_version_invalid", "外部确认时间或有效期无效", 422)
    proof = data.model_dump(mode="json", exclude={"payload"})
    payload = data.payload.model_dump(mode="json") if hasattr(data, "payload") else {}
    # 新增可空目标字段缺失时保持历史导入指纹，同版本重放不因模型默认扩展冲突。
    for field in (
        "sex_code",
        "weight_kg",
        "height_cm",
        "activity_code",
        "personal_targets",
        "meal_target_shares",
        "meal_generation",
    ):
        if payload.get(field) is None:
            payload.pop(field, None)
    return payload, proof, attested, valid_until


async def import_profile_projection(uid, member_id, data):
    """成员编辑授权的管理员只登记外部已确认投影，不执行建档确认。"""
    payload, proof, attested, valid_until = import_parts(data)
    digest = projection_digest("profile", member_id, data.version, payload, proof)
    async with pg_manager.get_async_session_context() as session:
        await require_evidence_admin(session, uid)
        await HealthVisionRepository(session).authorize(member_id, uid, "profile_edit", lock=True)
        repo = HealthQualityRepository(session)
        latest = await repo.profile(member_id)
        existing = await session.scalar(
            select(HealthProfileSnapshot).where(
                HealthProfileSnapshot.member_id == member_id, HealthProfileSnapshot.version == data.version
            )
        )
        if existing is not None:
            if existing.content_hash != digest:
                raise HealthVisionError("version_conflict", "同一外部档案版本不能改变内容或依据", 409)
            return {"scope": "nutrition_safety_projection", **external_projection(latest, "profile", member_id)}
        if data.version != (latest.version + 1 if latest is not None else 1):
            raise HealthVisionError("version_conflict", "外部档案投影须按当前版本递增", 409)
        row = HealthProfileSnapshot(
            id=str(uuid4()),
            member_id=member_id,
            version=data.version,
            payload=payload,
            attestation=proof,
            content_hash=digest,
            attested_at=attested,
            valid_until=valid_until,
            imported_by=uid,
        )
        session.add(row)
        await repo.invalidate(member_id=member_id, reason="profile_changed")
        return {"scope": "nutrition_safety_projection", **external_projection(row, "profile", member_id)}


async def read_profile_projection(uid, member_id):
    """只向当前完整档案读取授权返回营养安全投影，缺失不补齐。"""
    async with pg_manager.get_async_session_context() as session:
        await HealthVisionRepository(session).authorize(member_id, uid, "profile_view")
        row = await HealthQualityRepository(session).profile(member_id)
        return {"scope": "nutrition_safety_projection", **external_projection(row, "profile", member_id)}


async def revoke_profile_projection(uid, member_id, version):
    """同版本撤回幂等，旧确认导入不能复活撤回。"""
    async with pg_manager.get_async_session_context() as session:
        await require_evidence_admin(session, uid)
        await HealthVisionRepository(session).authorize(member_id, uid, "profile_edit", lock=True)
        repo = HealthQualityRepository(session)
        row = await session.scalar(
            select(HealthProfileSnapshot).where(
                HealthProfileSnapshot.member_id == member_id, HealthProfileSnapshot.version == version
            )
        )
        if row is None:
            raise HealthVisionError("not_found", "外部档案版本不存在", 404)
        row.revoked_at = row.revoked_at or utc_now_naive()
        if row.id == (await repo.profile(member_id)).id:
            await repo.invalidate(member_id=member_id, reason="profile_revoked")
        return {"version": version, "revoked": True}


async def import_approved_rules(uid, data):
    """管理员登记专业内容方批准的规则，工具不接收未经审核医学参数。"""
    payload, proof, attested, valid_until = import_parts(data)
    digest = projection_digest("rules", data.rule_code, data.version, payload, proof)
    async with pg_manager.get_async_session_context() as session:
        await require_evidence_admin(session, uid)
        repo = HealthQualityRepository(session)
        latest = await repo.rules(data.rule_code, lock=True)
        existing = await session.scalar(
            select(HealthRuleSnapshot).where(
                HealthRuleSnapshot.rule_code == data.rule_code, HealthRuleSnapshot.version == data.version
            )
        )
        if existing is not None:
            if existing.content_hash != digest:
                raise HealthVisionError("version_conflict", "同一批准规则版本不能改变内容或依据", 409)
            return external_projection(latest, "rules", data.rule_code)
        if data.version != (latest.version + 1 if latest is not None else 1):
            raise HealthVisionError("version_conflict", "批准规则须按当前版本递增", 409)
        row = HealthRuleSnapshot(
            id=str(uuid4()),
            rule_code=data.rule_code,
            version=data.version,
            payload=payload,
            attestation=proof,
            content_hash=digest,
            attested_at=attested,
            valid_until=valid_until,
            imported_by=uid,
        )
        session.add(row)
        await repo.invalidate(rule_code=data.rule_code, reason="rules_changed")
        return external_projection(row, "rules", data.rule_code)


async def read_approved_rules(uid, rule_code):
    """批准目录不含成员私有资料，但仍要求有效账号。"""
    async with pg_manager.get_async_session_context() as session:
        if not await session.scalar(select(User.uid).where(User.uid == uid, User.is_deleted == 0)):
            raise HealthVisionError("not_found", "账号不可用", 404)
        row = await HealthQualityRepository(session).rules(rule_code)
        return external_projection(row, "rules", rule_code)


async def revoke_approved_rules(uid, rule_code, version):
    """来源锁内撤回与检查、批准排序。"""
    async with pg_manager.get_async_session_context() as session:
        await require_evidence_admin(session, uid)
        repo = HealthQualityRepository(session)
        await repo.lock_key(f"health-rules:{rule_code}")
        row = await session.scalar(
            select(HealthRuleSnapshot).where(
                HealthRuleSnapshot.rule_code == rule_code, HealthRuleSnapshot.version == version
            )
        )
        if row is None:
            raise HealthVisionError("not_found", "批准规则版本不存在", 404)
        row.revoked_at = row.revoked_at or utc_now_naive()
        if row.id == (await repo.rules(rule_code)).id:
            await repo.invalidate(rule_code=rule_code, reason="rules_revoked")
        return {"version": version, "revoked": True}


async def register_professional_reviewer(uid, data):
    """资格登记由另一位管理员记录外部凭据，禁止自授资格。"""
    _, proof, attested, valid_until = import_parts(data)
    async with pg_manager.get_async_session_context() as session:
        await require_evidence_admin(session, uid)
        if uid == data.reviewer_uid:
            raise HealthVisionError("self_registration_forbidden", "不能为自己登记专业审核资格", 403)
        if not await session.scalar(select(User.uid).where(User.uid == data.reviewer_uid, User.is_deleted == 0)):
            raise HealthVisionError("not_found", "审核人员不存在", 404)
        repo = HealthQualityRepository(session)
        await repo.lock_key(f"health-reviewer:{data.reviewer_uid}")
        latest = await session.scalar(
            select(HealthProfessionalReviewer)
            .where(HealthProfessionalReviewer.reviewer_uid == data.reviewer_uid)
            .order_by(HealthProfessionalReviewer.version.desc())
            .limit(1)
        )
        digest = projection_digest("reviewer", data.reviewer_uid, data.version, {}, proof)
        existing = await session.get(HealthProfessionalReviewer, (data.reviewer_uid, data.version))
        if existing is not None:
            if existing.content_hash != digest:
                raise HealthVisionError("version_conflict", "同一资格版本不能改变外部依据", 409)
            return {
                "reviewer_uid": data.reviewer_uid,
                "version": latest.version,
                "revoked": latest.revoked_at is not None,
            }
        if data.version != (latest.version + 1 if latest is not None else 1):
            raise HealthVisionError("version_conflict", "审核资格须按当前版本递增", 409)
        session.add(
            HealthProfessionalReviewer(
                reviewer_uid=data.reviewer_uid,
                version=data.version,
                attestation=proof,
                content_hash=digest,
                attested_at=attested,
                valid_until=valid_until,
                registered_by=uid,
            )
        )
        await repo.invalidate(reviewer_uid=data.reviewer_uid, reason="reviewer_changed")
        return {"reviewer_uid": data.reviewer_uid, "version": data.version, "revoked": False}


async def revoke_professional_reviewer(uid, reviewer_uid, version):
    """撤回资格同时使该资格批准的方案失效。"""
    async with pg_manager.get_async_session_context() as session:
        await require_evidence_admin(session, uid)
        repo = HealthQualityRepository(session)
        await repo.lock_key(f"health-reviewer:{reviewer_uid}")
        row = await session.get(HealthProfessionalReviewer, (reviewer_uid, version))
        if row is None:
            raise HealthVisionError("not_found", "审核资格版本不存在", 404)
        row.revoked_at = row.revoked_at or utc_now_naive()
        await repo.invalidate(reviewer_uid=reviewer_uid, reviewer_version=version, reason="reviewer_revoked")
        return {"version": version, "revoked": True}

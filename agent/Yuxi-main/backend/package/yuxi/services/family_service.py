"""家庭档案用例：权限、版本、幂等、事务与统计。"""

import hashlib
import uuid
from datetime import date, datetime, timedelta, UTC
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from yuxi.repositories.family_repository import FamilyRepository
from yuxi.services.family_schemas import (
    METRIC_FIELDS,
    METRIC_UNITS,
    PROFILE_FIELDS,
    REQUIRED_PROFILE_FIELDS,
    validate_metric_values,
)
from yuxi.storage.postgres.models_business import FamilyArchive, FamilyMeasurement, FamilyMember, FamilyProfileRevision
from yuxi.utils.datetime_utils import format_utc_datetime, utc_now_naive
from yuxi.utils.auth_utils import AuthUtils

DISPLAY_ZONE = ZoneInfo("Asia/Shanghai")


def is_adult(member):
    """一期按本人填写的出生日期限制成年成员授权；不替代身份核验。"""
    born = (member.profile or {}).get("birth_date")
    if not born:
        return False
    birth_date = date.fromisoformat(born)
    today = datetime.now(DISPLAY_ZONE).date()
    return today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day)) >= 18


def authorized_fields(family, member, uid, now=None):
    """本人管理自身；管理员仅在明确用途与有效期内访问授予字段。"""
    if member.subject_uid == uid:
        return PROFILE_FIELDS | METRIC_FIELDS.keys()
    now = now or utc_now_naive()
    if (
        family.owner_uid == uid
        and member.subject_uid
        and is_adult(member)
        and member.grant_purpose == "family_nutrition"
        and member.grant_expires_at
        and member.grant_expires_at > now
    ):
        return set(member.grant_fields or [])
    return set()


def member_view(family, member, uid):
    """按当前访问范围投影，隐藏未经授权的字段及其完整度。"""
    allowed = authorized_fields(family, member, uid)
    profile = {key: value for key, value in (member.profile or {}).items() if key in allowed}
    missing = [key for key in REQUIRED_PROFILE_FIELDS if key in allowed and profile.get(key) in (None, "", [])]
    full_profile_access = set(REQUIRED_PROFILE_FIELDS) <= allowed
    return {
        "id": member.id,
        "name": member.name,
        "relationship": member.relationship,
        "is_self": member.subject_uid == uid,
        "claimed": member.subject_uid is not None,
        "profile": profile,
        "allowed_fields": sorted(allowed),
        "version": member.version,
        "confirmed": member.confirmed_version == member.version if full_profile_access else None,
        "missing_fields": missing,
        "ready": full_profile_access and not missing and member.confirmed_version == member.version,
        "updated_at": format_utc_datetime(member.updated_at),
        "authorization": {
            "fields": sorted(allowed) if member.subject_uid != uid else sorted(member.grant_fields or []),
            "expires_at": format_utc_datetime(member.grant_expires_at),
            "purpose": member.grant_purpose,
        }
        if member.subject_uid == uid or family.owner_uid == uid
        else None,
    }


def measurement_view(record):
    """返回带来源、更正版本及固定单位的实测记录。"""
    return {
        "id": record.id,
        "member_id": record.member_id,
        "kind": record.kind,
        "values": record.values,
        "measured_at": format_utc_datetime(record.measured_at),
        "unit": METRIC_UNITS[record.kind],
        "source": record.source,
        "condition": record.condition,
        "note": record.note,
        "version": record.version,
        "previous": record.previous or [],
    }


class FamilyService:
    """持有家庭事务，并在每次读取或副作用前执行授权校验。"""

    def __init__(self, db, uid):
        self.db, self.uid = db, str(uid)
        self.repo = FamilyRepository(db)

    async def context(self, fid, mid=None):
        """获取可访问家庭和严格属于该家庭的成员。"""
        family = await self.repo.get_family(fid, self.uid)
        if family is None:
            raise HTTPException(404, "家庭不存在或不可访问")
        member = await self.repo.member(fid, mid) if mid else None
        if mid and member is None:
            raise HTTPException(404, "成员不存在")
        return family, member

    def require_fields(self, family, member, fields):
        """授权字段必须覆盖此次读写；空白和过期都拒绝。"""
        if not set(fields) <= authorized_fields(family, member, self.uid):
            raise HTTPException(403, "请由成员本人授权对应字段")

    def require_version(self, member, expected):
        """拒绝基于旧版本覆盖最新档案。"""
        if member.version != expected:
            raise HTTPException(409, "档案已更新，请重新核对")

    async def list_families(self):
        """列表只包含家庭关系元信息。"""
        families = await self.repo.list_families(self.uid)
        return [{"id": row.id, "name": row.name, "is_owner": row.owner_uid == self.uid} for row in families]

    async def family(self, fid):
        """返回当前字段范围内的档案，记录访问。"""
        family, _ = await self.context(fid)
        members = await self.repo.members(fid)
        result = {
            "id": fid,
            "name": family.name,
            "is_owner": family.owner_uid == self.uid,
            "members": [member_view(family, member, self.uid) for member in members],
        }
        await self.repo.audit(fid, None, self.uid, "profiles.read")
        await self.db.commit()
        return result

    async def create_family(self, name, username):
        """每个用户管理一个家庭；重复相同请求返回已有家庭。"""
        existing = await self.repo.owned_family(self.uid)
        if existing:
            if existing.name != name:
                raise HTTPException(409, "当前账户已经管理一个家庭")
            return await self.family(existing.id)
        family = FamilyArchive(id=str(uuid.uuid4()), owner_uid=self.uid, name=name)
        member = FamilyMember(
            id=str(uuid.uuid4()), family_id=family.id, subject_uid=self.uid, name=username, relationship="本人"
        )
        try:
            self.db.add(family)
            await self.db.flush()
            self.db.add(member)
            await self.repo.audit(family.id, member.id, self.uid, "family.create")
            await self.db.commit()
        except IntegrityError:
            await self.db.rollback()
            existing = await self.repo.owned_family(self.uid)
            if existing and existing.name == name:
                return await self.family(existing.id)
            raise HTTPException(409, "当前账户已经管理一个家庭") from None
        return await self.family(family.id)

    async def add_member(self, fid, name, relationship):
        """仅管理员新增成员关系；健康信息须本人认领后授权。"""
        family, _ = await self.context(fid)
        if family.owner_uid != self.uid:
            raise HTTPException(403, "仅家庭管理员可添加成员")
        members = await self.repo.members(fid)
        if len(members) >= 30:
            raise HTTPException(422, "一个家庭最多30名成员")
        member = FamilyMember(id=str(uuid.uuid4()), family_id=fid, name=name, relationship=relationship)
        self.db.add(member)
        await self.db.flush()
        result = member_view(family, member, self.uid)
        await self.repo.audit(fid, member.id, self.uid, "member.create")
        await self.db.commit()
        return result

    async def invite(self, fid, mid):
        """只向管理员返回一次性短期邀请；数据库保存摘要。"""
        family, member = await self.context(fid, mid)
        if family.owner_uid != self.uid or member.subject_uid:
            raise HTTPException(403, "当前成员不能重新邀请")
        if not member.invite_expires_at or member.invite_expires_at <= utc_now_naive():
            member.invite_expires_at = utc_now_naive() + timedelta(days=2)
        key, _, _ = AuthUtils.derive_api_key(f"family-invitation:{member.invite_expires_at.isoformat()}", member.id)
        code = "family_" + key.removeprefix("yxkey_")
        member.invite_hash = hashlib.sha256(code.encode()).hexdigest()
        await self.repo.audit(fid, mid, self.uid, "member.invite")
        await self.db.commit()
        return {"code": code, "expires_at": format_utc_datetime(member.invite_expires_at)}

    async def join(self, code):
        """已登录的本人认领关系，不自动开放健康信息。"""
        digest = hashlib.sha256(code.encode()).hexdigest()
        candidate = await self.repo.invitation(digest)
        if candidate is None:
            raise HTTPException(410, "邀请已失效")
        fid, mid = candidate.family_id, candidate.id
        family = await self.db.scalar(select(FamilyArchive).where(FamilyArchive.id == fid).with_for_update())
        member = await self.repo.member(fid, mid)
        await self.db.refresh(member)
        valid = member.invite_hash == digest and member.invite_expires_at and member.invite_expires_at > utc_now_naive()
        if valid and member.subject_uid == self.uid:
            return await self.family(fid)
        if (
            member.invite_hash != digest
            or member.subject_uid
            or not member.invite_expires_at
            or member.invite_expires_at <= utc_now_naive()
        ):
            raise HTTPException(410, "邀请已失效")
        if family.owner_uid == self.uid or await self.repo.subject_member(fid, self.uid):
            raise HTTPException(409, "当前账户已经是此家庭成员")
        member.subject_uid = self.uid
        await self.repo.audit(fid, mid, self.uid, "member.claim")
        await self.db.commit()
        return await self.family(fid)

    async def authorization(self, fid, mid, fields, purpose, expires_at):
        """仅档案本人可授予或撤回向家庭管理员开放的字段。"""
        family, member = await self.context(fid, mid)
        if member.subject_uid != self.uid:
            raise HTTPException(403, "授权须由成员本人确认")
        if fields and not is_adult(member):
            raise HTTPException(422, "请先在本人档案填写出生日期；一期仅支持成年成员向管理员授权")
        member.grant_fields = sorted(set(fields))
        member.grant_purpose = purpose
        member.grant_expires_at = expires_at.astimezone(UTC).replace(tzinfo=None)
        result = member_view(family, member, self.uid)
        await self.repo.audit(fid, mid, self.uid, "authorization.change")
        await self.db.commit()
        return result

    async def update_profile(self, fid, mid, payload):
        """按授予字段和当前版本修改，保存新的完整快照。"""
        family, member = await self.context(fid, mid)
        changes = payload.profile.model_dump(mode="json", exclude_unset=True)
        if not changes:
            raise HTTPException(422, "没有档案变更")
        self.require_fields(family, member, changes)
        self.require_version(member, payload.expected_version)
        member.profile = {**(member.profile or {}), **changes}
        member.version += 1
        member.updated_at = utc_now_naive()
        self.db.add(
            FamilyProfileRevision(member_id=mid, version=member.version, profile=member.profile, actor_uid=self.uid)
        )
        result = member_view(family, member, self.uid)
        await self.repo.audit(fid, mid, self.uid, "profile.update", member.version)
        await self.db.commit()
        return result

    async def confirm(self, fid, mid, expected_version):
        """本人核对当前档案，不用管理员身份代替本人确认。"""
        family, member = await self.context(fid, mid)
        if member.subject_uid != self.uid:
            raise HTTPException(403, "档案确认须由本人完成")
        self.require_version(member, expected_version)
        member.confirmed_version = member.version
        result = member_view(family, member, self.uid)
        await self.repo.audit(fid, mid, self.uid, "profile.confirm", member.version)
        await self.db.commit()
        return result

    async def history(self, fid, mid):
        """历史快照同样使用当前授权，撤回不能通过历史绕过。"""
        family, member = await self.context(fid, mid)
        allowed = authorized_fields(family, member, self.uid) & PROFILE_FIELDS
        if not allowed:
            raise HTTPException(403, "无档案访问权限")
        records = await self.repo.revisions(mid)
        result = [
            {
                "version": row.version,
                "profile": {k: v for k, v in row.profile.items() if k in allowed},
                "created_at": format_utc_datetime(row.created_at),
            }
            for row in records
        ]
        await self.repo.audit(fid, mid, self.uid, "profile.history")
        await self.db.commit()
        return result

    async def measurements(self, fid, mid, kind=None, days=30):
        """查询当前授权指标的历史，返回最多1000条并明确截断。"""
        family, member = await self.context(fid, mid)
        allowed = authorized_fields(family, member, self.uid) & METRIC_FIELDS.keys()
        if not allowed or (kind and kind not in allowed):
            raise HTTPException(403, "无指标访问权限")
        start = datetime.now(DISPLAY_ZONE).date() - timedelta(days=days - 1)
        since = datetime.combine(start, datetime.min.time(), DISPLAY_ZONE).astimezone(UTC).replace(tzinfo=None)
        records = await self.repo.measurements([mid], [kind] if kind else allowed, since=since, limit=1001)
        result = {"items": [measurement_view(row) for row in records[:1000]], "truncated": len(records) > 1000}
        await self.repo.audit(fid, mid, self.uid, "measurements.read")
        await self.db.commit()
        return result

    async def add_measurement(self, fid, mid, payload):
        """幂等创建实测记录，不把失败或重试当成新增摄入。"""
        family, member = await self.context(fid, mid)
        self.require_fields(family, member, [payload.kind])
        intent = payload.model_dump(mode="json")
        rid = str(payload.id)
        existing = await self.repo.measurement(rid)
        if existing:
            if existing.member_id != mid or existing.created_by != self.uid or existing.creation_intent != intent:
                raise HTTPException(409, "记录ID已经用于其他请求")
            return measurement_view(existing)
        record = FamilyMeasurement(
            id=rid,
            member_id=mid,
            kind=payload.kind,
            values=payload.values,
            measured_at=payload.measured_at.astimezone(UTC).replace(tzinfo=None),
            source=payload.source,
            condition=payload.condition,
            note=payload.note,
            created_by=self.uid,
            creation_intent=intent,
        )
        try:
            self.db.add(record)
            await self.db.flush()
            await self.repo.audit(fid, mid, self.uid, "measurement.create", 1)
            result = measurement_view(record)
            await self.db.commit()
        except IntegrityError:
            await self.db.rollback()
            raise HTTPException(409, "记录ID已经用于其他请求") from None
        return result

    async def correct_measurement(self, fid, mid, rid, payload):
        """更正创建新版本，保留旧值与更正时间。"""
        family, member = await self.context(fid, mid)
        record = await self.repo.measurement(rid)
        if record is None or record.member_id != mid:
            raise HTTPException(404, "记录不存在")
        self.require_fields(family, member, [record.kind])
        if record.version != payload.expected_version:
            raise HTTPException(409, "记录已更新")
        try:
            validate_metric_values(record.kind, payload.values)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        record.previous = [
            *(record.previous or []),
            {
                "version": record.version,
                "values": record.values,
                "note": record.note,
                "corrected_at": format_utc_datetime(utc_now_naive()),
            },
        ]
        record.values, record.note = payload.values, payload.note
        record.version += 1
        record.updated_at = utc_now_naive()
        result = measurement_view(record)
        await self.repo.audit(fid, mid, self.uid, "measurement.correct", record.version)
        await self.db.commit()
        return result

    async def statistics(self, fid, days=30):
        """仅汇总当前可见实测记录，不计算跨成员的医学平均值。"""
        family, _ = await self.context(fid)
        members = await self.repo.members(fid)
        today = datetime.now(DISPLAY_ZONE).date()
        start = today - timedelta(days=days - 1)
        since = datetime.combine(start, datetime.min.time(), DISPLAY_ZONE).astimezone(UTC).replace(tzinfo=None)
        until = (
            datetime.combine(today + timedelta(days=1), datetime.min.time(), DISPLAY_ZONE)
            .astimezone(UTC)
            .replace(tzinfo=None)
        )
        visible = {row.id: authorized_fields(family, row, self.uid) for row in members}
        records = await self.repo.measurements(list(visible), since=since, until=until)
        records = [row for row in records if row.kind in visible[row.member_id]]
        dates = {(start + timedelta(days=index)).isoformat(): 0 for index in range(days)}
        counts = {kind: 0 for kind in METRIC_FIELDS}
        for row in records:
            day = row.measured_at.replace(tzinfo=UTC).astimezone(DISPLAY_ZONE).date().isoformat()
            dates[day] += 1
            counts[row.kind] += 1
        result = {
            "member_count": len(members),
            "visible_member_count": sum(bool(fields) for fields in visible.values()),
            "ready_member_count": sum(member_view(family, row, self.uid)["ready"] for row in members),
            "record_count": len(records),
            "record_member_count": len({row.member_id for row in records}),
            "daily_counts": [{"date": key, "count": value} for key, value in dates.items()],
            "metric_counts": counts,
            "from": start.isoformat(),
            "to": today.isoformat(),
            "as_of": format_utc_datetime(utc_now_naive()),
            "timezone": "Asia/Shanghai",
        }
        await self.repo.audit(fid, None, self.uid, "statistics.read")
        await self.db.commit()
        return result

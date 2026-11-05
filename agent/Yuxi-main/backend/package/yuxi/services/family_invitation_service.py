"""两类邀请的安全预览、明确接受与拒绝，不在预览中返回健康档案。"""

import hashlib
import hmac
import re
from datetime import timedelta
from uuid import UUID, uuid4

from fastapi import HTTPException

from yuxi.storage.postgres.models_business import FamilyMember
from yuxi.utils.auth_utils import AuthUtils
from yuxi.utils.datetime_utils import format_utc_datetime, utc_now_naive


class FamilyInvitationService:
    """复用家庭事务和成员唯一约束，普通卡片允许多个账号分别接受。"""

    def __init__(self, service):
        """调用方负责认证，家庭服务负责共同事务。"""
        self.service = service
        self.repo = service.repo

    async def create(self, fid):
        """仅家庭创建人生成不绑定成员、无到期时间的普通邀请。"""
        family, _ = await self.service.context(fid)
        if family.owner_uid != self.service.uid:
            raise HTTPException(403, "仅家庭创建人可以发出家庭邀请")
        await self.repo.audit(fid, None, self.service.uid, "family.invite")
        await self.service.db.commit()
        return {"code": family_invite_code(fid, family.invitation_version), "kind": "family", "expires_at": None}

    async def prepare(self, fid):
        """创建人一次准备全部可邀请选项；凭证只在当前家庭事务提交后返回。"""
        family, _ = await self.service.context(fid)
        if family.owner_uid != self.service.uid:
            raise HTTPException(403, "仅家庭创建人可以邀请家人")
        options = []
        for member in await self.repo.members(fid):
            if member.is_active and member.subject_uid is None:
                ticket = prepare_member_invitation(member)
                options.append({"key": member.id, "member_id": member.id, "name": member.name, **ticket})
        options.append(
            {
                "key": "family",
                "member_id": None,
                "name": "邀请其他家人",
                "code": family_invite_code(fid, family.invitation_version),
                "expires_at": None,
                "version": family.invitation_version,
            }
        )
        await self.repo.audit(fid, None, self.service.uid, "family.invite.prepare")
        await self.service.db.commit()
        return {"options": options}

    async def revoke(self, fid, expected_version):
        """按原版本幂等撤销普通邀请，保留所有已加入关系。"""
        family, _ = await self.service.context(fid)
        if family.owner_uid != self.service.uid:
            raise HTTPException(403, "仅家庭创建人可以撤销邀请")
        current = family.invitation_version
        if current == expected_version:
            family.invitation_version += 1
            await self.repo.audit(fid, None, self.service.uid, "family.invite.revoke")
            await self.service.db.commit()
        elif current != expected_version + 1:
            raise HTTPException(409, "邀请已变化，请重新读取后再操作")
        return {"revoked": True, "version": family.invitation_version}

    async def preview(self, code):
        """接受前仅展示邀请人、家庭和共享说明，不返回任何成员健康资料。"""
        family, member = await self.resolve(code)
        actor = await self.repo.subject_member(family.id, self.service.uid)
        own_claim = member is not None and member.subject_uid == self.service.uid
        can_accept = not actor or actor.is_active and (member is None or own_claim)
        state = "available"
        if actor:
            state = "inactive" if not actor.is_active else "already_joined" if can_accept else "member_conflict"
        return {
            "kind": "member" if member else "family",
            "family_id": family.id,
            "family_name": family.name,
            "inviter_name": await self.repo.inviter_name(family.owner_uid) or "家人",
            "member_name": member.name if member else None,
            "member_id": member.id if member else None,
            "already_accepted": bool(actor and actor.is_active and (member is None or own_claim)),
            "can_accept": bool(can_accept),
            "state": state,
            "sharing": [
                "有效家庭成员可查看和维护普通健康档案，包括健康情况、用药、饮食偏好与限制",
                "家庭内共享实测指标、普通档案修改历史与共同饮食安排",
                "有效家庭成员可查看、上传和核对家庭成员的体检报告",
                "加入家庭不代表同意 AI 分析，AI 用途单独确认",
            ],
        }

    async def accept(self, code, username):
        """明确接受才建立成员关系，重复接受不创建第二份档案。"""
        if not code.startswith("familyshare_"):
            return await self.service.join(code)
        family, _ = await self.resolve(code)
        actor = await self.repo.subject_member(family.id, self.service.uid)
        if actor is not None:
            if not actor.is_active:
                raise HTTPException(403, "当前家庭关系已停用，请联系家庭创建人")
            return await self.service.family(family.id)
        if sum(member.is_active for member in await self.repo.members(family.id)) >= 30:
            raise HTTPException(422, "一个家庭最多30名有效成员")
        actor = FamilyMember(
            id=str(uuid4()),
            family_id=family.id,
            subject_uid=self.service.uid,
            name=username or "我",
            relationship="家人",
            profile={},
            version=1,
            invitation_review_pending=True,
            invitation_analysis_pending=True,
        )
        self.service.db.add(actor)
        await self.service.db.flush()
        from yuxi.services.miniapp_report_service import ensure_member_reports

        await ensure_member_reports(self.service, family, actor)
        await self.repo.audit(family.id, actor.id, self.service.uid, "family.invite.accept")
        await self.service.db.commit()
        return await self.service.family(family.id)

    async def decline(self, code):
        """拒绝只记录决定，不加入家庭、不创建或认领档案。"""
        family, member = await self.resolve(code)
        await self.repo.audit(family.id, member.id if member else None, self.service.uid, "family.invite.decline")
        await self.service.db.commit()
        return {"declined": True}

    async def resolve(self, code):
        """先验证签名或摘要，再锁定家庭并重验绑定档案的可认领性。"""
        member = None
        if code.startswith("familyshare_"):
            match = re.fullmatch(r"familyshare_([0-9a-f]{32})_([A-Za-z0-9_-]{20,100})", code)
            if not match:
                raise HTTPException(410, "邀请已失效")
            fid = str(UUID(hex=match[1]))
        else:
            member = await self.repo.invitation(hashlib.sha256(code.encode()).hexdigest())
            if member is None:
                raise HTTPException(410, "邀请已失效")
            fid = member.family_id
        family = await self.repo.invitation_family(fid)
        if family is None:
            raise HTTPException(410, "邀请已失效")
        if member is None and not hmac.compare_digest(code, family_invite_code(fid, family.invitation_version)):
            raise HTTPException(410, "邀请已失效")
        if member is not None:
            await self.service.db.refresh(member)
            if (
                not member.is_active
                or member.invite_hash != hashlib.sha256(code.encode()).hexdigest()
                or member.subject_uid not in (None, self.service.uid)
                or member.subject_uid is None
                and (not member.invite_expires_at or member.invite_expires_at <= utc_now_naive())
            ):
                raise HTTPException(410, "邀请已失效或档案已由其他账号认领")
        return family, member


def family_invite_code(fid, version=0):
    """普通邀请凭证由服务端密钥派生，不包含健康信息。"""
    scope = "family-share" if not version else f"family-share:{version}"
    key, _, _ = AuthUtils.derive_api_key(scope, fid)
    return "familyshare_" + UUID(fid).hex + "_" + key.removeprefix("yxkey_")


def prepare_member_invitation(member):
    """在调用方的家庭锁内复用未到期凭证，数据库仅保存摘要。"""
    if not member.invite_expires_at or member.invite_expires_at <= utc_now_naive():
        member.invite_expires_at = utc_now_naive() + timedelta(days=2)
    key, _, _ = AuthUtils.derive_api_key(f"family-invitation:{member.invite_expires_at.isoformat()}", member.id)
    code = "family_" + key.removeprefix("yxkey_")
    member.invite_hash = hashlib.sha256(code.encode()).hexdigest()
    return {"code": code, "expires_at": format_utc_datetime(member.invite_expires_at)}

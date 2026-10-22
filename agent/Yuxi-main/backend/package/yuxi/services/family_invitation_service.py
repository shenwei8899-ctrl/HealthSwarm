"""两类邀请的安全预览、明确接受与拒绝，不在预览中返回健康档案。"""

import hashlib
import hmac
import re
from uuid import UUID, uuid4

from fastapi import HTTPException

from yuxi.storage.postgres.models_business import FamilyMember
from yuxi.utils.auth_utils import AuthUtils
from yuxi.utils.datetime_utils import utc_now_naive


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
        return {"code": family_invite_code(fid), "kind": "family", "expires_at": None}

    async def preview(self, code):
        """接受前仅展示邀请人、家庭和共享说明，不返回任何成员健康资料。"""
        family, member = await self.resolve(code)
        actor = await self.repo.subject_member(family.id, self.service.uid)
        own_claim = member is not None and member.subject_uid == self.service.uid
        can_accept = not actor or actor.is_active and (member is None or own_claim)
        return {
            "kind": "member" if member else "family",
            "family_id": family.id,
            "family_name": family.name,
            "inviter_name": await self.repo.inviter_name(family.owner_uid) or "家人",
            "member_name": member.name if member else None,
            "member_id": member.id if member else None,
            "already_accepted": bool(actor and actor.is_active and (member is None or own_claim)),
            "can_accept": bool(can_accept),
            "sharing": [
                "家庭成员与共同饮食安排",
                "配餐所需的过敏、不耐受、忌口和医生饮食要求",
                "体检报告另经本人同意后共享",
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
        actor = FamilyMember(
            id=str(uuid4()),
            family_id=family.id,
            subject_uid=self.service.uid,
            name=username or "我",
            relationship="家人",
            profile={},
            version=1,
        )
        self.service.db.add(actor)
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
            if not hmac.compare_digest(code, family_invite_code(fid)):
                raise HTTPException(410, "邀请已失效")
        else:
            member = await self.repo.invitation(hashlib.sha256(code.encode()).hexdigest())
            if member is None:
                raise HTTPException(410, "邀请已失效")
            fid = member.family_id
        family = await self.repo.invitation_family(fid)
        if family is None:
            raise HTTPException(410, "邀请已失效")
        if member is not None:
            await self.service.db.refresh(member)
            if (
                not member.is_active
                or not member.invite_expires_at
                or member.invite_expires_at <= utc_now_naive()
                or member.subject_uid not in (None, self.service.uid)
            ):
                raise HTTPException(410, "邀请已失效或档案已由其他账号认领")
        return family, member


def family_invite_code(fid):
    """普通邀请凭证由服务端密钥派生，不包含健康信息。"""
    key, _, _ = AuthUtils.derive_api_key("family-share", fid)
    return "familyshare_" + UUID(fid).hex + "_" + key.removeprefix("yxkey_")

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
        current = await self.repo.active_membership(self.service.uid)
        family, member = await self.resolve(code, current.family_id if current else None)
        actor = await self.repo.subject_member(family.id, self.service.uid)
        own_claim = member is not None and member.subject_uid == self.service.uid
        can_accept = not actor or actor.is_active and (member is None or own_claim)
        state = "available"
        if actor:
            state = "inactive" if not actor.is_active else "already_joined" if can_accept else "member_conflict"
        switch = None
        if state == "available" and current and current.family_id != family.id:
            source, _ = await self.service.context(current.family_id)
            others = await self.successors(source, current)
            transfer = source.pending_owner_transfer or {}
            can_accept = not others or any(
                row.id == transfer.get("member_id")
                and row.relationship_version == transfer.get("member_version")
                and transfer.get("accepted")
                for row in others
            )
            state = "switch" if can_accept else "transfer_required"
            switch = {
                "family_id": source.id,
                "family_name": source.name,
                "successors": [{"id": row.id, "name": row.name} for row in others],
                "transfer": transfer or None,
            }
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
            "switch": switch,
            "sharing": [
                "有效家庭成员可查看和维护普通健康档案，包括健康情况、用药、饮食偏好与限制",
                "家庭内共享实测指标、普通档案修改历史与共同饮食安排",
                "有效家庭成员可查看、上传和核对家庭成员的体检报告",
                "加入家庭不代表同意 AI 分析，AI 用途单独确认",
            ],
        }

    async def accept(self, code, username, expected_family_id=None, expected_transfer_id=None):
        """明确接受才建立成员关系，重复接受不创建第二份档案。"""
        await self.repo.lock_membership(self.service.uid)
        current = await self.repo.active_membership(self.service.uid)
        family, reserved = await self.resolve(code, current.family_id if current else None)
        actor = await self.repo.subject_member(family.id, self.service.uid)
        if actor is not None:
            if not actor.is_active:
                raise HTTPException(403, "当前家庭关系已停用，请联系家庭创建人")
            if reserved and reserved.id != actor.id:
                raise HTTPException(409, "邀请对应另一份成员档案")
            return await self.service.family(family.id)
        if reserved is None and sum(member.is_active for member in await self.repo.members(family.id)) >= 30:
            raise HTTPException(422, "一个家庭最多30名有效成员")
        if (current.family_id if current else None) != expected_family_id:
            raise HTTPException(409, "当前家庭已变化，请重新查看并确认邀请")
        person_id = None
        if current:
            source, _ = await self.service.context(current.family_id)
            person_id = current.person_id or await self.repo.linked_health_member(source.id, current.id) or current.id
            current.person_id = person_id
            await self.leave_for_switch(source, current, expected_transfer_id)
        actor = reserved
        if actor is None:
            actor = FamilyMember(
                id=str(uuid4()), family_id=family.id, name=username or "我", relationship="家人", profile={}, version=1
            )
            self.service.db.add(actor)
        actor.subject_uid = self.service.uid
        if person_id:
            actor.person_id = person_id
        actor.invitation_review_pending = actor.invitation_analysis_pending = True
        actor.confirmed_version = actor.confirmed_at = None
        await self.service.db.flush()
        from yuxi.services.miniapp_report_service import ensure_member_reports

        await ensure_member_reports(self.service, family, actor)
        await self.repo.audit(family.id, actor.id, self.service.uid, "family.invite.accept")
        await self.service.db.commit()
        return await self.service.family(family.id)

    async def propose_transfer(self, fid, member_id):
        """现任管理员指定接手人，留待本人确认。"""
        family, _ = await self.service.context(fid)
        current = await self.repo.subject_member(fid, self.service.uid)
        target = next((row for row in await self.successors(family, current) if row.id == member_id), None)
        if target is None:
            raise HTTPException(403, "请由现任管理员选择原家庭中的有效成员")
        transfer = family.pending_owner_transfer or {}
        if transfer.get("member_id") != target.id or transfer.get("member_version") != target.relationship_version:
            transfer = {
                "id": str(uuid4()),
                "member_id": target.id,
                "member_version": target.relationship_version,
                "accepted": False,
            }
            family.pending_owner_transfer = transfer
            await self.repo.audit(fid, target.id, self.service.uid, "family.transfer.proposed")
        await self.service.db.commit()
        return transfer

    async def confirm_transfer(self, fid, transfer_id):
        """只允许被指定成员确认；生效时仍要验证身份。"""
        family, _ = await self.service.context(fid)
        actor = await self.repo.subject_member(fid, self.service.uid)
        transfer = family.pending_owner_transfer or {}
        if (
            transfer.get("id") != transfer_id
            or transfer.get("member_id") != actor.id
            or transfer.get("member_version") != actor.relationship_version
        ):
            raise HTTPException(404, "未找到需要你确认的交接")
        if not transfer.get("accepted"):
            family.pending_owner_transfer = {**transfer, "accepted": True}
            await self.repo.audit(fid, actor.id, self.service.uid, "family.transfer.accepted")
        await self.service.db.commit()
        return {"accepted": True}

    async def leave_for_switch(self, family, current, expected_transfer_id):
        """退出、原家庭交接或归档由加入事务统一提交。"""
        if family.owner_uid == self.service.uid:
            others = await self.successors(family, current)
            if others:
                transfer = family.pending_owner_transfer or {}
                target = next((row for row in others if row.id == transfer.get("member_id")), None)
                if (
                    target is None
                    or transfer.get("id") != expected_transfer_id
                    or target.relationship_version != transfer.get("member_version")
                    or not transfer.get("accepted")
                ):
                    raise HTTPException(409, "原家庭仍有成员，请先完成管理员交接")
                family.owner_uid = target.subject_uid
                await self.repo.audit(family.id, target.id, self.service.uid, "family.transfer.completed")
            else:
                family.archived_at = utc_now_naive()
                await self.repo.audit(family.id, current.id, self.service.uid, "family.archive")
            family.pending_owner_transfer = None
            family.invitation_version += 1
            family.version += 1
            for member in await self.repo.members(family.id):
                member.invite_hash = member.invite_expires_at = None
                # 旧字段授权只面向原管理员，绝不随管理权转移。
                member.grant_fields, member.grant_edit_fields = [], []
                member.grant_expires_at = member.grant_purpose = None
        await self.service.set_membership_status(family, current, False, "member.switch_leave")
        await self.service.db.flush()

    async def successors(self, family, current):
        """可接手人必须是同家庭内已认领且有效的其他账号。"""
        if family.owner_uid != self.service.uid:
            return []
        return [
            row
            for row in await self.repo.members(family.id)
            if row.id != current.id and row.is_active and row.subject_uid
        ]

    async def decline(self, code):
        """拒绝只记录决定，不加入家庭、不创建或认领档案。"""
        family, member = await self.resolve(code)
        await self.repo.audit(family.id, member.id if member else None, self.service.uid, "family.invite.decline")
        await self.service.db.commit()
        return {"declined": True}

    async def resolve(self, code, source_family_id=None):
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
        family = (await self.repo.lock_families({fid, source_family_id} - {None})).get(fid)
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

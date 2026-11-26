"""好友邀请签名收据与注册、建档事务衔接。"""

import hmac
import re
import secrets
import time

from yuxi.repositories.referral_repository import ReferralRepository
from yuxi.utils.auth_utils import AuthUtils
from yuxi.utils.datetime_utils import format_utc_datetime

CODE_PATTERN = r"[A-Za-z0-9_-]{24}"
REFERRAL_LIFETIME = 7 * 24 * 60 * 60


async def resolve_referral(db, code, channel):
    """只对有效入口签发七天收据，不公开邀请人的身份。"""
    if await ReferralRepository(db).valid_code(code) is None:
        return {"valid": False}
    issued = int(time.time())
    body = f"{issued}.{code}.{channel}"
    signature, _, _ = AuthUtils.derive_api_key("friend-referral-receipt", body)
    return {"valid": True, "receipt": f"{body}.{signature}", "expires_at": issued + REFERRAL_LIFETIME}


async def bind_new_referral(db, uid, receipt):
    """无效或过期入口不阻止注册；只有新账号创建分支调用。"""
    if not receipt:
        return
    parts = receipt.split(".")
    if len(parts) != 4:
        return
    issued, code, channel, signature = parts
    if (
        not re.fullmatch(r"[0-9]{1,12}", issued)
        or not re.fullmatch(CODE_PATTERN, code)
        or channel not in {"share", "qr"}
        or not re.fullmatch(r"yxkey_[0-9a-f]{48}", signature)
    ):
        return
    if not 0 <= time.time() - int(issued) < REFERRAL_LIFETIME:
        return
    expected, _, _ = AuthUtils.derive_api_key("friend-referral-receipt", ".".join(parts[:3]))
    if not hmac.compare_digest(signature, expected):
        return
    repo = ReferralRepository(db)
    row = await repo.valid_code(code)
    if row is not None and row.inviter_uid != uid:
        await repo.bind(uid, row, channel)


async def prepare_referral(db, uid):
    """账号稳定邀请码用于分享及小程序码。"""
    row = await ReferralRepository(db).prepare(uid, secrets.token_urlsafe(18))
    return {
        "code": row.code,
        "enabled": row.enabled,
        "path": "/pages/index/index?ref=" + row.code,
        "title": "分享给你一个家庭营养师，一起把每天吃什么安排好。",
    }


async def referral_records(db, uid, before, limit):
    """只展示已完成建档的匿名记录，成功编号保持稳定。"""
    total, rows, more = await ReferralRepository(db).records(uid, before, limit)
    return {
        "total": total,
        "items": [
            {"label": f"好友{row.success_number:03d}", "completed_at": format_utc_datetime(row.completed_at)}
            for row in rows
        ],
        "next_cursor": rows[-1].success_number if more else None,
    }

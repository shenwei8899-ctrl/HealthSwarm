"""好友邀请公开解析与当前账号匿名记录。"""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from server.utils.auth_middleware import get_db, get_required_user
from yuxi.services.login_rate_limit_service import extract_client_ip
from yuxi.services.referral_service import CODE_PATTERN, prepare_referral, referral_records, resolve_referral
from yuxi.services.referral_qrcode import referral_qrcode
from yuxi.storage.postgres.models_business import User
from yuxi.storage.redis import get_async_redis_client


def no_store(response: Response):
    """个人邀请结果不由共享代理缓存。"""
    response.headers["Cache-Control"] = "no-store"


referrals = APIRouter(prefix="/referrals", tags=["referrals"], dependencies=[Depends(no_store)])


class ResolveInput(BaseModel):
    """入口只能提交短邀请码及受限来源类型。"""

    model_config = ConfigDict(extra="forbid")
    code: str = Field(pattern="^" + CODE_PATTERN + "$")
    channel: Literal["share", "qr"] = "share"


@referrals.post("/resolve")
async def resolve_entry(payload: ResolveInput, request: Request, db: AsyncSession = Depends(get_db)):
    """匿名入口按网络来源限流，不泄露邀请人姓名。"""
    import hashlib

    redis = await get_async_redis_client()
    key = "friend-referral:resolve:" + hashlib.sha256(extract_client_ip(request).encode()).hexdigest()
    count = await redis.incr(key)
    if count == 1:
        await redis.expire(key, 60)
    if count > 60:
        raise HTTPException(429, "操作过于频繁，请稍后再试")
    return await resolve_referral(db, payload.code, payload.channel)


@referrals.post("/mine")
async def prepare(user: User = Depends(get_required_user), db: AsyncSession = Depends(get_db)):
    """读取或幂等创建当前账号的专属入口。"""
    result = await prepare_referral(db, user.uid)
    await db.commit()
    return result


@referrals.get("/mine/records")
async def records(
    before: int | None = Query(default=None, ge=1),
    limit: int = Query(default=20, ge=1, le=50),
    user: User = Depends(get_required_user),
    db: AsyncSession = Depends(get_db),
):
    """当前登录账号是唯一查询主体。"""
    return await referral_records(db, user.uid, before, limit)


@referrals.get("/mine/qrcode")
async def qrcode(
    env_version: Literal["release", "trial", "develop"] | None = Query(default=None),
    user: User = Depends(get_required_user),
    db: AsyncSession = Depends(get_db),
):
    """小程序码固定归属当前账号，不接受任意邀请人参数。"""
    result = await prepare_referral(db, user.uid)
    await db.commit()
    if not result["enabled"]:
        raise HTTPException(409, "当前邀请入口已停用")
    return await referral_qrcode(result["code"], env_version)

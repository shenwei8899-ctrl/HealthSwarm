"""微信 code 交换、普通账号关联与最小家庭状态投影。"""

import asyncio
import hashlib
import json
import os
import re
import secrets
import time
from dataclasses import dataclass, field
from datetime import timedelta
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, build_opener

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from yuxi.repositories.family_repository import FamilyRepository
from yuxi.repositories.wechat_identity_repository import WechatIdentityRepository
from yuxi.services.miniapp_profile_types import miniapp_onboarding_ready
from yuxi.services.login_rate_limit_service import (
    check_login_rate_limit,
    clear_login_failures,
    record_login_failure,
)
from yuxi.storage.postgres.models_business import User
from yuxi.utils.auth_utils import AuthUtils
from yuxi.utils.datetime_utils import utc_now_naive


@dataclass(frozen=True)
class WechatSettings:
    """微信密钥来自服务端环境，公开投影只输出 AppID 和可用状态。"""

    enabled: bool
    appid: str
    secret: str = field(repr=False)
    auto_register: bool
    department_id: int | None

    @classmethod
    def load(cls):
        """读取明确启用的配置；部门缺失阻止首次注册。"""
        raw_department = os.getenv("WECHAT_USER_DEPARTMENT_ID", "").strip()
        return cls(
            enabled=os.getenv("WECHAT_LOGIN_ENABLED", "false").lower() == "true",
            appid=os.getenv("WECHAT_APP_ID", "").strip(),
            secret=os.getenv("WECHAT_APP_SECRET", "").strip(),
            auto_register=os.getenv("WECHAT_AUTO_REGISTER", "false").lower() == "true",
            department_id=int(raw_department) if raw_department.isdigit() and int(raw_department) > 0 else None,
        )

    def public(self):
        """不返回 AppSecret，也不把占位 AppID 宣告为就绪。"""
        available = self.enabled and bool(re.fullmatch(r"wx[0-9a-fA-F]{16}", self.appid)) and bool(self.secret)
        return {"available": available, "appid": self.appid if available else None}


class WechatLoginService:
    """复用普通业务账号和 JWT，不创建家庭或健康授权。"""

    def __init__(self, db, settings=None):
        """当前请求拥有唯一登录事务。"""
        self.db = db
        self.settings = settings or WechatSettings.load()
        self.repo = WechatIdentityRepository(db)

    async def login(self, payload, client_ip):
        """验证微信和绑定凭据后提交关联，成功响应只包含业务会话。"""
        if not self.settings.public()["available"]:
            raise HTTPException(503, {"code": "WECHAT_NOT_CONFIGURED", "message": "微信登录服务尚未配置完成"})
        identifier = payload.identifier or "wechat-login"
        allowed, retry_after = await check_login_rate_limit(client_ip, identifier)
        if not allowed:
            raise HTTPException(429, "登录尝试过于频繁，请稍后再试", headers={"Retry-After": str(retry_after)})

        try:
            openid = await exchange_wechat_code(self.settings, payload.code.get_secret_value())
        except HTTPException as exc:
            if exc.status_code == 401:
                await record_login_failure(client_ip, identifier)
            raise
        digest = hashlib.sha256(f"{self.settings.appid}:{openid}".encode()).hexdigest()
        await self.repo.lock_identity(self.settings.appid, digest)
        identity = await self.repo.identity(self.settings.appid, digest)
        if identity:
            user = await self.repo.user(identity.user_id)
            self.require_user(user)
            if payload.identifier and payload.identifier not in {user.uid, user.phone_number}:
                raise HTTPException(409, {"code": "WECHAT_ALREADY_BOUND", "message": "此微信已关联其他业务账号"})
        elif payload.identifier:
            user = await self.repo.login_user(payload.identifier)
            if user and not user.is_deleted:
                self.require_user(user)
            if (
                user is None
                or user.is_deleted
                or not AuthUtils.verify_password(user.password_hash, payload.password.get_secret_value())
            ):
                await record_login_failure(client_ip, identifier)
                if user and not user.is_deleted:
                    user.increment_failed_login()
                    await self.db.commit()
                raise HTTPException(401, {"code": "INVALID_BINDING_CREDENTIALS", "message": "账号或密码错误"})
        else:
            if not self.settings.auto_register:
                raise HTTPException(
                    503, {"code": "WECHAT_REGISTRATION_NOT_READY", "message": "微信新用户注册尚未配置完成，请稍后重试"}
                )
            if not self.settings.department_id or not await self.repo.department(self.settings.department_id):
                raise HTTPException(503, {"code": "WECHAT_REGISTRATION_NOT_READY", "message": "新用户注册尚未配置完成"})
            uid = "wx_" + secrets.token_hex(12)
            user = User(
                uid=uid,
                username="微信用户_" + secrets.token_hex(8),
                role="user",
                department_id=self.settings.department_id,
                password_hash=AuthUtils.hash_password(secrets.token_urlsafe(48)),
            )
            self.db.add(user)
            await self.db.flush()

        try:
            if not identity:
                await self.repo.bind(self.settings.appid, digest, user)
            user.reset_failed_login()
            user.last_login = utc_now_naive()
            expires_at = int(time.time()) + 7 * 24 * 60 * 60
            token = AuthUtils.create_access_token({"sub": str(user.id), "login_channel": "wechat"}, expires_delta=timedelta(days=7))
            context = await self.session_context(user)
            await self.db.commit()
        except IntegrityError:
            await self.db.rollback()
            raise HTTPException(
                409, {"code": "WECHAT_BINDING_CONFLICT", "message": "账号已关联微信，请核对后重新登录"}
            ) from None
        await clear_login_failures(client_ip, identifier)
        return {**context, "access_token": token, "token_type": "bearer", "expires_at": expires_at}

    async def payment_identity(self, user, code, client_ip):
        """用新鲜微信凭证证明当前账号已有的绑定，不注册或重绑身份。"""
        self.require_user(user)
        if not self.settings.public()["available"]:
            raise HTTPException(503, {"code": "WECHAT_NOT_CONFIGURED", "message": "微信登录服务尚未配置完成"})
        identifier = f"wechat-payment:{user.id}"
        allowed, retry_after = await check_login_rate_limit(client_ip, identifier)
        if not allowed:
            raise HTTPException(429, "验证尝试过于频繁，请稍后再试", headers={"Retry-After": str(retry_after)})

        try:
            openid = await exchange_wechat_code(self.settings, code)
        except HTTPException as exc:
            if exc.status_code == 401:
                await record_login_failure(client_ip, identifier)
            raise
        digest = hashlib.sha256(f"{self.settings.appid}:{openid}".encode()).hexdigest()
        await self.repo.lock_identity(self.settings.appid, digest)
        identity = await self.repo.identity(self.settings.appid, digest)
        if identity is None or identity.user_id != user.id:
            await record_login_failure(client_ip, identifier)
            raise HTTPException(
                409, {"code": "WECHAT_PAYMENT_IDENTITY_MISMATCH", "message": "请使用已关联当前账号的微信验证支付身份"}
            )
        current_user = await self.repo.user(identity.user_id)
        self.require_user(current_user)
        await clear_login_failures(client_ip, identifier)
        return {
            "account": {"id": current_user.id, "uid": current_user.uid},
            "wechat_authenticated": True,
            "appid": self.settings.appid,
            "openid": openid,
        }

    async def session_context(self, user):
        """当前账号与家庭关系是投影来源，仅公开本人基础档案就绪状态。"""
        self.require_user(user)
        repo = FamilyRepository(self.db)
        families = []
        for family in await repo.list_families(user.uid):
            members = await repo.members(family.id)
            member = next((m for m in members if m.subject_uid == user.uid and m.is_active), None)
            ready = miniapp_onboarding_ready(member, family)
            families.append(
                {
                    "id": family.id,
                    "name": family.name,
                    "is_owner": family.owner_uid == user.uid,
                    "onboarding_required": not ready,
                }
            )
        return {"account": {"id": user.id, "uid": user.uid, "name": user.username}, "families": families}

    @staticmethod
    def require_user(user):
        """停用、管理员、未分配部门与被锁定账号不获得微信业务会话。"""
        if user is None or user.is_deleted:
            raise HTTPException(403, "账号已停用，请联系管理员")
        if user.role != "user":
            raise HTTPException(403, "微信登录仅开放普通用户账号")
        if user.is_login_locked():
            raise HTTPException(423, "登录被锁定，请稍后重试")
        if user.department_id is None:
            raise HTTPException(403, "账号尚未分配部门，请联系管理员")


async def exchange_wechat_code(settings, code):
    """只联系微信固定 HTTPS 服务，不记录含密钥的请求 URL。"""
    query = urlencode(
        {"appid": settings.appid, "secret": settings.secret, "js_code": code, "grant_type": "authorization_code"}
    )
    try:
        raw = await asyncio.to_thread(fetch_wechat_response, query)
        body = json.loads(raw)
    except (HTTPError, URLError, TimeoutError, OSError, ValueError):
        raise HTTPException(
            502, {"code": "WECHAT_UPSTREAM_UNAVAILABLE", "message": "微信登录暂不可用，请稍后重试"}
        ) from None
    if not isinstance(body, dict):
        raise HTTPException(502, "微信返回的数据无效")
    error = body.get("errcode", 0)
    if error in {40029, 40163}:
        raise HTTPException(401, {"code": "WECHAT_CODE_INVALID", "message": "微信登录凭证已失效，请重新登录"})
    if (
        error != 0
        or not isinstance(body.get("openid"), str)
        or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", body["openid"])
    ):
        raise HTTPException(502, {"code": "WECHAT_EXCHANGE_FAILED", "message": "微信登录未完成，请稍后重试"})
    return body["openid"]


def fetch_wechat_response(query):
    """固定地址、限制响应体、禁止携密钥跳转；异常由上层转换。"""
    opener = build_opener(NoWechatRedirect())
    with opener.open("https://api.weixin.qq.com/sns/jscode2session?" + query, timeout=10) as response:
        body = response.read(65537)
        if len(body) > 65536:
            raise ValueError("微信响应超出限制")
        return body


class NoWechatRedirect(HTTPRedirectHandler):
    """凭证交换禁止跟随重定向。"""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        """不允许把密钥发送到其他地址。"""
        raise ValueError("微信凭证交换拒绝重定向")

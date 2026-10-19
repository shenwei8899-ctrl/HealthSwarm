"""微信小程序登录协议入口，复用现有业务认证依赖。"""

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator
from sqlalchemy.ext.asyncio import AsyncSession

from server.utils.auth_middleware import get_db, get_required_user
from yuxi.services.login_rate_limit_service import extract_client_ip
from yuxi.services.wechat_login_service import WechatLoginService, WechatSettings
from yuxi.storage.postgres.models_business import User


class WechatLoginInput(BaseModel):
    """前端只提交临时 code，以及显式绑定时的已有账号凭据。"""

    model_config = ConfigDict(extra="forbid")
    code: SecretStr = Field(min_length=1, max_length=256)
    identifier: str | None = Field(default=None, min_length=1, max_length=100)
    password: SecretStr | None = Field(default=None, min_length=1, max_length=128)

    @model_validator(mode="after")
    def binding_pair(self):
        """绑定必须同时提交账号与密码。"""
        if (self.identifier is None) != (self.password is None):
            raise ValueError("账号与密码必须同时提供")
        return self


def private_response(response: Response):
    """登录与会话数据禁止缓存。"""
    response.headers["Cache-Control"] = "no-store"


class WechatPaymentIdentityInput(BaseModel):
    """支付身份仅接收临时 code，账号由认证依赖确定。"""

    model_config = ConfigDict(extra="forbid")
    code: SecretStr = Field(min_length=1, max_length=256)


wechat_auth = APIRouter(prefix="/auth/wechat", tags=["wechat-auth"], dependencies=[Depends(private_response)])


@wechat_auth.get("/config")
async def wechat_config():
    """公开可用状态与 AppID，缺配置时保持不可用。"""
    return WechatSettings.load().public()


@wechat_auth.post("/login")
async def wechat_login(payload: WechatLoginInput, request: Request, db: AsyncSession = Depends(get_db)):
    """服务端交换微信身份，返回普通用户业务会话。"""
    return await WechatLoginService(db).login(payload, extract_client_ip(request))


@wechat_auth.get("/session")
async def wechat_session(user: User = Depends(get_required_user), db: AsyncSession = Depends(get_db)):
    """重新核对账号和当前可访问家庭，支持尚未建档的新用户。"""
    return await WechatLoginService(db).session_context(user)


@wechat_auth.post("/payment-identity")
async def wechat_payment_identity(
    payload: WechatPaymentIdentityInput,
    request: Request,
    user: User = Depends(get_required_user),
    db: AsyncSession = Depends(get_db),
):
    """向商城证明临时微信凭证与当前业务账号的既有关联。"""
    return await WechatLoginService(db).payment_identity(
        user, payload.code.get_secret_value(), extract_client_ip(request)
    )

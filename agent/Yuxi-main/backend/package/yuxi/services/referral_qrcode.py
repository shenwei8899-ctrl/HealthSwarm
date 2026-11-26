"""固定微信上游的小程序码生成与共享缓存。"""

import base64
import json
import os

import httpx
from fastapi import HTTPException

from yuxi.storage.redis import get_async_redis_client
from yuxi.services.wechat_login_service import WechatSettings


async def referral_qrcode(code, env_version=None):
    """服务端凭据不出站到客户端，外部失败不生成示意码。"""
    settings = WechatSettings.load()
    env = env_version or os.getenv("WECHAT_REFERRAL_ENV_VERSION", "release")
    if not settings.public()["available"] or env not in {"release", "trial", "develop"}:
        raise HTTPException(503, "邀请小程序码尚未配置")
    redis = await get_async_redis_client()
    key = f"friend-referral:qr:{settings.appid}:{env}:{code}"
    cached = await redis.get(key)
    if cached:
        return {"image_base64": cached.decode() if isinstance(cached, bytes) else cached}
    token_key = f"friend-referral:wechat-token:{settings.appid}"
    token = await redis.get(token_key)
    if isinstance(token, bytes):
        token = token.decode()
    try:
        async with httpx.AsyncClient(timeout=12, follow_redirects=False) as client:
            if not token:
                response = await client.get(
                    "https://api.weixin.qq.com/cgi-bin/token",
                    params={"grant_type": "client_credential", "appid": settings.appid, "secret": settings.secret},
                )
                response.raise_for_status()
                data = response.json()
                token = data.get("access_token")
                if not isinstance(token, str) or not token or len(token) > 1024:
                    raise ValueError("微信凭证不可用")
                await redis.set(token_key, token, ex=max(60, min(int(data.get("expires_in", 7200)) - 300, 6900)))
            response = await client.post(
                "https://api.weixin.qq.com/wxa/getwxacodeunlimit",
                params={"access_token": token},
                json={
                    "scene": "r=" + code,
                    "page": "pages/index/index",
                    "env_version": env,
                    # 落地页由服务端固定；允许开发/体验阶段尚未发布的同一路径。
                    "check_path": False,
                    "width": 430,
                },
            )
            response.raise_for_status()
            raw = response.content
            if not (raw.startswith(b"\x89PNG\r\n\x1a\n") or raw.startswith(b"\xff\xd8\xff")) or len(raw) > 1024 * 1024:
                try:
                    if response.json().get("errcode") in {40001, 40014, 42001}:
                        await redis.delete(token_key)
                except (ValueError, AttributeError):
                    pass
                raise ValueError("微信未返回有效小程序码")
    except (httpx.HTTPError, ValueError, TypeError, json.JSONDecodeError):
        raise HTTPException(502, "邀请小程序码暂时无法生成，请稍后重试") from None
    encoded = base64.b64encode(raw).decode()
    await redis.set(key, encoded, ex=86400)
    return {"image_base64": encoded}

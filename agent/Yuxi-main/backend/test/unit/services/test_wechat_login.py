"""微信配置、固定供应商协议及敏感响应边界。"""

import json
from urllib.parse import parse_qs

import pytest
from fastapi import HTTPException

from yuxi.services import wechat_login_service as service


def test_configuration_is_explicit_and_does_not_publish_secret(monkeypatch):
    """启用、有效 AppID 与服务器密钥同时存在才公开可用。"""
    for key in ("WECHAT_LOGIN_ENABLED", "WECHAT_APP_ID", "WECHAT_APP_SECRET"):
        monkeypatch.delenv(key, raising=False)
    assert service.WechatSettings.load().public() == {"available": False, "appid": None}
    monkeypatch.setenv("WECHAT_LOGIN_ENABLED", "true")
    monkeypatch.setenv("WECHAT_APP_ID", "touristappid")
    monkeypatch.setenv("WECHAT_APP_SECRET", "synthetic-secret")
    assert service.WechatSettings.load().public()["available"] is False
    monkeypatch.setenv("WECHAT_APP_ID", "wx1234567890abcdef")
    settings = service.WechatSettings.load()
    assert settings.public() == {"available": True, "appid": "wx1234567890abcdef"}
    assert "synthetic-secret" not in repr(settings)
    assert settings.auto_register is False


@pytest.mark.asyncio
async def test_provider_uses_configured_app_and_returns_only_verified_openid(monkeypatch):
    """客户端无法指定供应商 URL，微信 session_key 不成为业务结果。"""
    captured = []

    def fetch(query):
        """替代外部微信响应，保留实际参数装配。"""
        captured.append(parse_qs(query))
        return json.dumps({"openid": "synthetic-openid", "session_key": "private-key"}).encode()

    monkeypatch.setattr(service, "fetch_wechat_response", fetch)
    settings = service.WechatSettings(True, "wx1234567890abcdef", "server-secret", False, None)
    assert await service.exchange_wechat_code(settings, "client-code") == "synthetic-openid"
    assert captured == [
        {
            "appid": [settings.appid],
            "secret": ["server-secret"],
            "js_code": ["client-code"],
            "grant_type": ["authorization_code"],
        }
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body,status",
    [
        ({"errcode": 40029, "errmsg": "private"}, 401),
        ({"errcode": 40163}, 401),
        ({"errcode": 45011}, 502),
        ({"session_key": "private"}, 502),
        ({"openid": "bad/id"}, 502),
        ([], 502),
        ("invalid json", 502),
    ],
)
async def test_invalid_provider_response_never_authenticates(monkeypatch, body, status):
    """失效凭证与上游错误分别转换，不泄露微信原始错误信息。"""
    raw = b"invalid json" if body == "invalid json" else json.dumps(body).encode()
    monkeypatch.setattr(service, "fetch_wechat_response", lambda query: raw)
    settings = service.WechatSettings(True, "wx1234567890abcdef", "server-secret", False, None)
    with pytest.raises(HTTPException) as error:
        await service.exchange_wechat_code(settings, "client-code")
    assert error.value.status_code == status
    assert "private" not in str(error.value.detail)


def test_redirect_cannot_forward_server_credentials():
    """跨地址跳转在真正的网络执行边界被拒绝。"""
    with pytest.raises(ValueError, match="重定向"):
        service.NoWechatRedirect().redirect_request(None, None, 302, "", {}, "https://other.invalid")

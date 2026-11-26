"""好友邀请签名、有效期与新账号关联边界。"""

from unittest.mock import AsyncMock
from types import SimpleNamespace

import pytest

from yuxi.services import referral_service as service


@pytest.fixture
def repository(monkeypatch):
    """仅替代持久层，独立数据库测试另验证实际约束。"""
    monkeypatch.setenv("API_KEY_DERIVATION_SECRET", "synthetic-referral-secret-0000000000000000")
    repo = SimpleNamespace(valid_code=AsyncMock(return_value=SimpleNamespace(inviter_uid="inviter")), bind=AsyncMock())
    monkeypatch.setattr(service, "ReferralRepository", lambda db: repo)
    return repo


@pytest.mark.asyncio
async def test_receipt_is_signed_and_binds_only_verified_source(repository, monkeypatch):
    """篡改邀请码、来源或时间均不能产生邀请关系。"""
    monkeypatch.setattr(service.time, "time", lambda: 1000000)
    result = await service.resolve_referral(None, "a" * 24, "qr")
    await service.bind_new_referral(None, "new-user", result["receipt"])
    assert repository.bind.await_args.args[0] == "new-user"
    assert repository.bind.await_args.args[2] == "qr"
    repository.bind.reset_mock()
    for bad in (
        result["receipt"].replace("a" * 24, "b" * 24),
        result["receipt"].replace(".qr.", ".share."),
        "invalid",
        "1000000." + "a" * 24 + ".share.é",
        "²." + "a" * 24 + ".share.yxkey_" + "0" * 48,
        "",
        None,
    ):
        await service.bind_new_referral(None, "new-user", bad)
    repository.bind.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("image", [b"\x89PNG\r\n\x1a\nsynthetic", b"\xff\xd8\xffsynthetic"])
async def test_qrcode_accepts_real_image_formats_and_fixed_destination(monkeypatch, image):
    """微信返回 PNG 或 JPEG 均可使用，凭据不进入客户端投影。"""
    import base64
    import httpx
    from yuxi.services import referral_qrcode as qr

    monkeypatch.setenv("WECHAT_LOGIN_ENABLED", "true")
    monkeypatch.setenv("WECHAT_APP_ID", "wx1234567890abcdef")
    monkeypatch.setenv("WECHAT_APP_SECRET", "synthetic-secret")
    redis = SimpleNamespace(get=AsyncMock(side_effect=[None, "synthetic-token"]), set=AsyncMock())
    monkeypatch.setattr(qr, "get_async_redis_client", AsyncMock(return_value=redis))

    def handle(request):
        """仅替换外部供应商，保留真实 HTTP 请求装配。"""
        assert request.url.host == "api.weixin.qq.com"
        assert request.url.path == "/wxa/getwxacodeunlimit"
        assert b'"page":"pages/index/index"' in request.content
        assert b'"check_path":false' in request.content
        assert b'"env_version":"develop"' in request.content
        return httpx.Response(200, content=image)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handle))
    monkeypatch.setattr(qr.httpx, "AsyncClient", lambda **kwargs: client)
    result = await qr.referral_qrcode("a" * 24, "develop")
    assert base64.b64decode(result["image_base64"]) == image
    assert set(result) == {"image_base64"}


@pytest.mark.asyncio
async def test_expired_future_disabled_and_self_receipts_do_not_bind(repository, monkeypatch):
    """七天与未来时间由服务端验证；停用入口和自己不归因。"""
    monkeypatch.setattr(service.time, "time", lambda: 1000000)
    receipt = (await service.resolve_referral(None, "a" * 24, "share"))["receipt"]
    for now in (999999, 1000000 + service.REFERRAL_LIFETIME):
        monkeypatch.setattr(service.time, "time", lambda: now)
        await service.bind_new_referral(None, "new", receipt)
    monkeypatch.setattr(service.time, "time", lambda: 1000000)
    await service.bind_new_referral(None, "inviter", receipt)
    repository.valid_code.return_value = None
    await service.bind_new_referral(None, "new", receipt)
    assert await service.resolve_referral(None, "a" * 24, "share") == {"valid": False}
    repository.bind.assert_not_awaited()

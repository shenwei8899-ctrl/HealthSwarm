"""验证音频边界、供应商签名与错误投影。"""

import base64
import json

import httpx
import pytest

from yuxi.services import health_voice_service as service


@pytest.fixture
def configured(monkeypatch):
    """显式配置合成凭据，不调用外部服务。"""
    monkeypatch.setenv("HEALTH_ASR_ENABLED", "1")
    monkeypatch.setenv("HEALTH_ASR_SECRET_ID", "synthetic-id")
    monkeypatch.setenv("HEALTH_ASR_SECRET_KEY", "synthetic-key")


@pytest.mark.parametrize(
    "data,format,rate,channels,code",
    [
        (b"\0" * 16000, "mp3", 16000, 1, "VOICE_FORMAT_INVALID"),
        (b"\0" * 16000, "PCM", 8000, 1, "VOICE_FORMAT_INVALID"),
        (b"\0" * 16000, "PCM", 16000, 2, "VOICE_FORMAT_INVALID"),
        (b"\0" * 15998, "PCM", 16000, 1, "VOICE_SIZE_INVALID"),
        (b"\0" * 16001, "PCM", 16000, 1, "VOICE_SIZE_INVALID"),
        (b"\0" * (service.MAX_AUDIO_BYTES + 2), "PCM", 16000, 1, "VOICE_SIZE_INVALID"),
        (b"RIFF" + b"\0" * 15996, "PCM", 16000, 1, "VOICE_FORMAT_INVALID"),
    ],
)
async def test_invalid_audio_never_reaches_provider(data, format, rate, channels, code):
    """拒绝格式、声道、长度和实际封装不符的输入。"""
    with pytest.raises(service.VoiceError) as caught:
        await service.transcribe("actor", "voice-test-123", data, format, rate, channels)
    assert caught.value.code == code


async def test_disabled_provider_is_explicit(monkeypatch):
    """没有真实配置不能返回假转写。"""
    monkeypatch.delenv("HEALTH_ASR_ENABLED", raising=False)
    assert service.configuration()["available"] is False
    with pytest.raises(service.VoiceError, match="尚未配置"):
        await service.transcribe("actor", "voice-test-123", b"\0" * 16000, "PCM", 16000, 1)


@pytest.mark.parametrize(
    "payload,status,expected",
    [
        ({"Response": {"Result": "  今天吃什么  "}}, 200, "今天吃什么"),
        ({"Response": {"Result": " "}}, 200, "VOICE_EMPTY"),
        ({"Response": {"Error": {"Message": "private supplier details"}}}, 200, "VOICE_PROVIDER_FAILED"),
        ({"Response": []}, 200, "VOICE_PROVIDER_FAILED"),
        ({"unexpected": "response"}, 200, "VOICE_PROVIDER_UNAVAILABLE"),
        ({}, 503, "VOICE_PROVIDER_UNAVAILABLE"),
    ],
)
async def test_provider_contract(configured, monkeypatch, payload, status, expected):
    """验证真实请求编码和供应商失败的稳定公开响应。"""
    original_client = httpx.AsyncClient
    requests = []

    def respond(request):
        """记录协议并返回合成供应商响应。"""
        requests.append(request)
        return httpx.Response(status, json=payload)

    monkeypatch.setattr(
        service.httpx,
        "AsyncClient",
        lambda **options: original_client(**options, transport=httpx.MockTransport(respond)),
    )
    if expected.startswith("VOICE_"):
        with pytest.raises(service.VoiceError) as caught:
            await service.recognize_pcm(b"\0" * 16000)
        assert caught.value.code == expected
        assert "private supplier" not in str(caught.value)
    else:
        assert await service.recognize_pcm(b"\0" * 16000) == expected
    request = requests[0]
    body = json.loads(request.content)
    assert request.url == "https://asr.tencentcloudapi.com/"
    assert base64.b64decode(body["Data"]) == b"\0" * 16000
    assert body["DataLen"] == 16000 and body["VoiceFormat"] == "pcm"
    assert request.headers["X-TC-Action"] == "SentenceRecognition"
    assert "TC3-HMAC-SHA256 Credential=synthetic-id/" in request.headers["Authorization"]
    assert "synthetic-key" not in request.headers["Authorization"]


def test_signature_changes_with_payload_and_does_not_expose_secret(configured):
    """签名绑定请求体和UTC日期。"""
    headers = service.signed_headers('{"Data":"AAA="}', 1700000000)
    assert "/2023-11-14/asr/tc3_request" in headers["Authorization"]
    assert headers["X-TC-Timestamp"] == "1700000000"
    assert headers["Authorization"] != service.signed_headers('{"Data":"BBB="}', 1700000000)["Authorization"]

"""短语音转写：音频仅驻留请求内存，结果按用户短期缓存。"""

import asyncio
import base64
import hashlib
import hmac
import json
import os
import re
import time
from datetime import UTC, datetime
from uuid import uuid4

import httpx
from redis.exceptions import RedisError

from yuxi.storage.redis import get_async_redis_client

MAX_AUDIO_BYTES = 16000 * 2 * 60
RESULT_TTL = 300


class VoiceError(Exception):
    """向客户端公开稳定错误，不转发供应商响应正文。"""

    def __init__(self, code: str, message: str, status: int = 400):
        self.code, self.message, self.status = code, message, status
        super().__init__(message)


def configuration() -> dict:
    """只公开能力状态和处理方，不公开凭据。"""
    available = os.getenv("HEALTH_ASR_ENABLED") == "1" and all(
        os.getenv(name, "").strip() for name in ("HEALTH_ASR_SECRET_ID", "HEALTH_ASR_SECRET_KEY")
    )
    return {"available": available, "processor": "腾讯云语音识别", "max_seconds": 60}


async def transcribe(
    uid: str, request_id: str, data: bytes, audio_format: str, sample_rate: int, channels: int
) -> dict:
    """校验音频并以用户和请求键隔离转写、限流及五分钟重试。"""
    if not re.fullmatch(r"[A-Za-z0-9_-]{8,100}", request_id):
        raise VoiceError("VOICE_REQUEST_INVALID", "语音请求标识无效")
    if audio_format != "PCM" or sample_rate != 16000 or channels != 1:
        raise VoiceError("VOICE_FORMAT_INVALID", "录音须为16kHz单声道PCM，请重新录音")
    if not 16000 <= len(data) <= MAX_AUDIO_BYTES or len(data) % 2:
        raise VoiceError("VOICE_SIZE_INVALID", "录音须为0.5至60秒，请重新录音", 413)
    if data.startswith((b"RIFF", b"ID3", b"OggS", b"fLaC")):
        raise VoiceError("VOICE_FORMAT_INVALID", "录音实际格式与PCM声明不符")
    if not configuration()["available"]:
        raise VoiceError("VOICE_NOT_READY", "语音识别服务尚未配置，请暂用文字输入", 503)
    digest = hashlib.sha256(data).hexdigest()
    user_key = hashlib.sha256(str(uid).encode()).hexdigest()
    key = f"health:voice:{user_key}:{request_id}"
    token = uuid4().hex
    try:
        redis = await get_async_redis_client()
        cached = await redis.get(key)
        if cached:
            return read_cached(cached, digest)
        if not await redis.set(key + ":lock", token, ex=60, nx=True):
            raise VoiceError("VOICE_IN_PROGRESS", "这段语音正在识别，请稍后重试", 409)
        try:
            cached = await redis.get(key)
            if cached:
                return read_cached(cached, digest)
            count = await redis.eval(
                "local count=redis.call('INCR',KEYS[1]); "
                "if count==1 then redis.call('EXPIRE',KEYS[1],60) end; return count",
                1,
                f"health:voice:rate:{user_key}",
            )
            if count > 10:
                raise VoiceError("VOICE_RATE_LIMITED", "语音操作较频繁，请一分钟后再试", 429)
            text = await recognize_pcm(data)
            result = {"text": text, "client_request_id": request_id}
            await redis.set(key, json.dumps({"digest": digest, "result": result}, ensure_ascii=False), ex=RESULT_TTL)
            return result
        finally:
            await redis.eval(
                "if redis.call('GET',KEYS[1])==ARGV[1] then return redis.call('DEL',KEYS[1]) end; return 0",
                1,
                key + ":lock",
                token,
            )
    except (RedisError, RuntimeError) as error:
        raise VoiceError("VOICE_UNAVAILABLE", "语音服务暂不可用，请稍后重试", 503) from error


def read_cached(cached: str, digest: str) -> dict:
    """同一请求键只允许重放原音频的结果。"""
    saved = json.loads(cached)
    if saved["digest"] != digest:
        raise VoiceError("VOICE_REQUEST_CONFLICT", "同一语音请求不能更换录音文件", 409)
    return saved["result"]


async def recognize_pcm(data: bytes) -> str:
    """调用固定腾讯云端点，限制整次调用时长并拒绝空识别。"""
    body = json.dumps(
        {
            "EngSerViceType": "16k_zh",
            "SourceType": 1,
            "VoiceFormat": "pcm",
            "Data": base64.b64encode(data).decode("ascii"),
            "DataLen": len(data),
            "UsrAudioKey": uuid4().hex,
        },
        separators=(",", ":"),
    )
    headers = signed_headers(body, int(time.time()))
    try:
        async with asyncio.timeout(30), httpx.AsyncClient(timeout=25, follow_redirects=False) as client:
            response = await client.post("https://asr.tencentcloudapi.com/", content=body, headers=headers)
            response.raise_for_status()
            result = response.json()["Response"]
    except (TimeoutError, httpx.HTTPError, ValueError, KeyError, TypeError) as error:
        raise VoiceError("VOICE_PROVIDER_UNAVAILABLE", "语音识别暂未完成，请稍后重试", 502) from error
    if not isinstance(result, dict) or result.get("Error"):
        raise VoiceError("VOICE_PROVIDER_FAILED", "语音识别服务返回失败，请稍后重试", 502)
    text = result.get("Result")
    if not isinstance(text, str) or not text.strip():
        raise VoiceError("VOICE_EMPTY", "没有识别到内容，请重新录音", 422)
    return text.strip()


def signed_headers(body: str, timestamp: int) -> dict:
    """按腾讯云TC3协议签名，请求凭据仅来自服务端环境。"""
    secret_id = os.environ["HEALTH_ASR_SECRET_ID"].strip()
    secret_key = os.environ["HEALTH_ASR_SECRET_KEY"].strip()
    date = datetime.fromtimestamp(timestamp, UTC).strftime("%Y-%m-%d")
    content_type = "application/json; charset=utf-8"
    canonical_headers = f"content-type:{content_type}\nhost:asr.tencentcloudapi.com\n"
    body_hash = hashlib.sha256(body.encode()).hexdigest()
    canonical = f"POST\n/\n\n{canonical_headers}\ncontent-type;host\n{body_hash}"
    scope = f"{date}/asr/tc3_request"
    to_sign = f"TC3-HMAC-SHA256\n{timestamp}\n{scope}\n{hashlib.sha256(canonical.encode()).hexdigest()}"
    date_key = hmac.new(("TC3" + secret_key).encode(), date.encode(), hashlib.sha256).digest()
    service_key = hmac.new(date_key, b"asr", hashlib.sha256).digest()
    signing_key = hmac.new(service_key, b"tc3_request", hashlib.sha256).digest()
    signature = hmac.new(signing_key, to_sign.encode(), hashlib.sha256).hexdigest()
    return {
        "Content-Type": content_type,
        "Host": "asr.tencentcloudapi.com",
        "Authorization": (
            f"TC3-HMAC-SHA256 Credential={secret_id}/{scope}, SignedHeaders=content-type;host, Signature={signature}"
        ),
        "X-TC-Action": "SentenceRecognition",
        "X-TC-Version": "2019-06-14",
        "X-TC-Timestamp": str(timestamp),
        "X-TC-Region": os.getenv("HEALTH_ASR_REGION", "ap-shanghai"),
    }

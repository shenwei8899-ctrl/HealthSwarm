from __future__ import annotations

import json
from contextlib import contextmanager

import pytest
import yuxi.models.providers.cache as cache_module
from yuxi.models.providers.cache import REDIS_CACHE_KEY, ModelCache, ModelInfo

pytestmark = pytest.mark.unit


class _FakeRedis:
    def __init__(self):
        self.data: dict[str, str] = {}
        self.get_calls = 0

    def get(self, key: str) -> str | None:
        self.get_calls += 1
        return self.data.get(key)

    def set(self, key: str, value: str) -> bool:
        self.data[key] = value
        return True


def _patch_redis(monkeypatch: pytest.MonkeyPatch, redis: _FakeRedis) -> None:
    @contextmanager
    def fake_sync_redis_client(*args, **kwargs):
        del args, kwargs
        yield redis

    monkeypatch.setattr(cache_module, "sync_redis_client", fake_sync_redis_client)


def test_model_cache_prefers_model_base_url_override(monkeypatch):
    saved_cache = {}

    class Provider:
        is_enabled = True
        provider_id = "alibaba-cn"
        api_key = "sk-test"
        api_key_env = None
        provider_type = "openai"
        base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
        embedding_base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1/embeddings"
        rerank_base_url = "https://dashscope.aliyuncs.com/compatible-api/v1/reranks"
        headers_json = {}
        extra_json = {}
        include_user_uid = True
        enabled_models = [
            {
                "id": "qwen3-rerank",
                "type": "rerank",
                "display_name": "Qwen3 Rerank",
                "base_url_override": "https://invalid.example/rerank",
            }
        ]

    cache = ModelCache()
    monkeypatch.setattr(cache, "_save_cache", lambda data: saved_cache.update(data))

    cache.rebuild([Provider()])

    assert saved_cache["alibaba-cn:qwen3-rerank"].base_url == "https://invalid.example/rerank"
    assert saved_cache["alibaba-cn:qwen3-rerank"].include_user_uid is True


def test_model_cache_loads_from_redis_and_uses_local_ttl(monkeypatch: pytest.MonkeyPatch):
    redis = _FakeRedis()
    _patch_redis(monkeypatch, redis)
    redis.data[REDIS_CACHE_KEY] = json.dumps(
        {
            "provider:chat": {
                "provider_id": "provider",
                "model_id": "chat",
                "model_type": "chat",
                "display_name": "Chat",
                "api_key": "sk-test",
                "base_url": "https://example.com/v1",
                "provider_type": "openai",
                "request_body_overrides": {"enable_thinking": False},
            }
        }
    )
    cache = ModelCache()

    info = cache.get_model_info("provider:chat")
    cached_info = cache.get_model_info("provider:chat")

    assert info is not None
    assert cached_info is info
    assert info.base_url == "https://example.com/v1"
    assert info.request_body_overrides == {"enable_thinking": False}
    assert redis.get_calls == 1


def test_model_cache_save_writes_redis_json(monkeypatch: pytest.MonkeyPatch):
    redis = _FakeRedis()
    _patch_redis(monkeypatch, redis)
    cache = ModelCache()
    info = ModelInfo(
        provider_id="provider",
        model_id="chat",
        model_type="chat",
        display_name="Chat",
        api_key="sk-test",
        base_url="https://example.com/v1",
        provider_type="openai",
        request_body_overrides={"enable_thinking": True},
        include_user_uid=True,
    )

    cache._save_cache({info.spec: info})

    payload = json.loads(redis.data[REDIS_CACHE_KEY])
    assert payload[info.spec]["base_url"] == "https://example.com/v1"
    assert payload[info.spec]["request_body_overrides"] == {"enable_thinking": True}
    assert payload[info.spec]["include_user_uid"] is True

    reloaded = ModelCache()
    assert reloaded.get_model_info("provider:chat").include_user_uid is True


def test_model_cache_defaults_include_user_uid_to_false(monkeypatch: pytest.MonkeyPatch):
    """存量 Redis 缓存缺省该字段时按关闭处理，不因 KeyError 中断模型加载。"""
    redis = _FakeRedis()
    _patch_redis(monkeypatch, redis)
    redis.data[REDIS_CACHE_KEY] = json.dumps(
        {
            "provider:chat": {
                "provider_id": "provider",
                "model_id": "chat",
                "model_type": "chat",
                "display_name": "Chat",
                "api_key": "sk-test",
                "base_url": "https://example.com/v1",
                "provider_type": "openai",
            }
        }
    )

    info = ModelCache().get_model_info("provider:chat")
    assert info.include_user_uid is False


@pytest.mark.parametrize("change", ["endpoint", "removed", "unavailable"])
def test_explicit_refresh_does_not_reuse_warm_model_view(monkeypatch, change):
    """审批刷新立即发现端点修改、模型移除或 Redis 读取失败。"""
    redis = _FakeRedis()
    _patch_redis(monkeypatch, redis)
    info = ModelInfo("synthetic", "fixed", "chat", "Synthetic", "synthetic-key", "http://old.invalid", "openai")
    redis.data[REDIS_CACHE_KEY] = json.dumps({info.spec: info.to_dict()})
    cache = ModelCache()
    assert cache.get_model_info(info.spec).base_url == "http://old.invalid"
    if change == "endpoint":
        value = info.to_dict()
        value["base_url"] = "http://new.invalid"
        redis.data[REDIS_CACHE_KEY] = json.dumps({info.spec: value})
    elif change == "removed":
        redis.data[REDIS_CACHE_KEY] = "{}"
    else:

        def unavailable(_key):
            """故障注入仅作用于 Redis wire 读取。"""
            raise ConnectionError("synthetic Redis unavailable")

        monkeypatch.setattr(redis, "get", unavailable)
    assert cache.get_model_info(info.spec).base_url == "http://old.invalid"
    cache.refresh()
    current = cache.get_model_info(info.spec)
    if change == "endpoint":
        assert current.base_url == "http://new.invalid"
    else:
        assert current is None

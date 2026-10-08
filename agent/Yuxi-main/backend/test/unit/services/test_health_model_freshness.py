"""健康外呼不能由旧模型投影继续授权。"""

import json
from contextlib import contextmanager
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from yuxi.models.providers import cache as cache_module
from yuxi.models.providers import repository as provider_repository
from yuxi.services import health_vision_tasks as tasks
from yuxi.services.health_vision_service import processor_identity
from yuxi.services.health_vision_types import HealthVisionError


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kind,change",
    [
        (kind, change)
        for kind in ("meal", "report")
        for change in [
            "unchanged",
            "removed",
            "endpoint",
            "unreadable",
            "database_disabled",
            "credential_removed",
            "database_endpoint",
            "database_headers",
            "database_overrides",
            "database_model_removed",
            "database_type",
            "database_provider_type",
            "database_credential_rotated",
        ]
    ]
    + [
        ("report", "ocr_credential_removed"),
        ("report", "ocr_credential_rotated"),
        ("meal", "empty_bindings"),
        ("meal", "database_deleted"),
        ("meal", "prompt_changed"),
    ],
)
async def test_worker_rejects_model_change_despite_warm_projection(monkeypatch, kind, change):
    """独立旧投影与数据库 oracle；每种失效均在外呼之前拒绝。"""
    info = cache_module.ModelInfo(
        provider_id="synthetic",
        model_id="fixed",
        model_type="chat",
        display_name="合成模型",
        api_key="synthetic-key",
        base_url="https://old.example.invalid/v1",
        provider_type="openai",
    )
    wire = {info.spec: info.to_dict()}

    class Redis:
        """仅模拟 wire 与读取故障，不触碰运行中的 Redis。"""

        def get(self, _key):
            """读取已显式设置的投影。"""
            if change == "unreadable" and not wire:
                raise ConnectionError("synthetic unavailable")
            return json.dumps(wire)

    @contextmanager
    def redis_client():
        """提供局部合成 Redis。"""
        yield Redis()

    monkeypatch.setattr(cache_module, "sync_redis_client", redis_client)
    cache = cache_module.ModelCache()
    assert cache.get_model_info(info.spec) == info
    if change in {"removed", "unreadable"}:
        wire.clear()
    elif change == "endpoint":
        wire[info.spec] = replace(info, base_url="https://changed.example.invalid/v1").to_dict()
    provider = SimpleNamespace(
        provider_id=info.provider_id,
        provider_type="openai",
        is_enabled=change not in {"database_disabled", "empty_bindings"},
        api_key="" if change == "credential_removed" else info.api_key,
        api_key_env=None,
        base_url=info.base_url,
        enabled_models=[{"id": "fixed", "type": "chat", "display_name": info.display_name}],
        embedding_base_url=None,
        rerank_base_url=None,
        headers_json={},
        extra_json={},
        include_user_uid=False,
    )
    if change == "database_endpoint":
        provider.base_url = "https://changed.example.invalid/v1"
    elif change == "database_headers":
        provider.headers_json = {"X-Synthetic": "changed"}
    elif change == "database_overrides":
        provider.enabled_models[0]["request_body_overrides"] = {"enable_thinking": True}
    elif change == "database_model_removed":
        provider.enabled_models = []
    elif change == "database_type":
        provider.enabled_models[0]["type"] = "embedding"
    elif change == "database_provider_type":
        provider.provider_type = "anthropic"
    elif change == "database_credential_rotated":
        provider.api_key = "synthetic-new-key"
    monkeypatch.setattr(
        provider_repository,
        "get_model_provider",
        AsyncMock(return_value=None if change == "database_deleted" else provider),
    )
    monkeypatch.setattr(tasks, "model_cache", cache)
    from yuxi.services import health_vision_service as service

    monkeypatch.setattr(service, "model_cache", cache)
    fingerprint = "" if change == "empty_bindings" else processor_identity(kind, info)
    values = {f"{kind}_model": info.spec, "policy_version": "synthetic", f"approved_{kind}_processor": fingerprint}
    monkeypatch.setattr(
        tasks,
        "resolve_ocr_task_params",
        AsyncMock(
            return_value={
                "_ocr_processor_kwargs": {}
                if change == "ocr_credential_removed"
                else {
                    "api_token": "synthetic-new-ocr-key" if change == "ocr_credential_rotated" else "synthetic-ocr-key"
                },
            }
        ),
    )
    monkeypatch.setattr(tasks, "health_vision_opts", SimpleNamespace(get=AsyncMock(return_value=values)))
    monkeypatch.setattr(tasks.HealthVisionRepository, "authorize", AsyncMock(return_value=SimpleNamespace()))
    monkeypatch.setattr(tasks.HealthVisionRepository, "require_consent", AsyncMock())
    monkeypatch.setattr(tasks.HealthVisionRepository, "active_uploads", AsyncMock(return_value=[]))
    job = SimpleNamespace(
        member_id="synthetic-member",
        actor_uid="synthetic-actor",
        kind=kind,
        input_snapshot={
            "model": info.spec,
            "processor": fingerprint,
            "policy_version": "synthetic",
            "prompt_version": "health-vision-v1" if change == "prompt_changed" else "health-meal-v2",
        },
    )
    if change == "unchanged":
        _member, uploads = await tasks.check_job_access(
            None,
            job,
            expected_ocr_kwargs={"api_token": "synthetic-ocr-key"} if kind == "report" else None,
        )
        assert uploads == []
    else:
        with pytest.raises(HealthVisionError, match="policy_changed"):
            await tasks.check_job_access(
                None,
                job,
                expected_ocr_kwargs={"api_token": "synthetic-ocr-key"} if kind == "report" else None,
            )


@pytest.mark.asyncio
async def test_constructed_consultation_model_cannot_keep_rotated_credentials(monkeypatch):
    """投影已同步也不能继续使用旧实例；真实 loader 不发起网络请求。"""
    from yuxi.models import chat
    from yuxi.agents.buildin.health_consultation import graph
    from yuxi.services import health_consultation_service as consultation

    old = cache_module.ModelInfo(
        provider_id="synthetic",
        model_id="fixed",
        model_type="chat",
        display_name="合成",
        api_key="synthetic-old-key",
        base_url="https://example.invalid/v1",
        provider_type="openai",
    )
    current = old
    cache = SimpleNamespace(get_model_info=lambda _spec: current)
    monkeypatch.setattr(chat, "model_cache", cache)
    monkeypatch.setattr(graph, "model_cache", cache)
    monkeypatch.setattr(consultation, "require_consultation_attempt", AsyncMock())
    model = chat.load_chat_model(old.spec)
    assert model.openai_api_key.get_secret_value() == "synthetic-old-key"
    middleware = graph.HealthAuthorizationMiddleware(old)
    runtime = SimpleNamespace(context=SimpleNamespace(model=old.spec))
    await middleware.abefore_model({"messages": []}, runtime)
    current = replace(old, api_key="synthetic-new-key")
    assert processor_identity("consultation", current) == processor_identity("consultation", old)
    with pytest.raises(HealthVisionError, match="policy_changed"):
        await middleware.abefore_model({"messages": []}, runtime)
    assert model.openai_api_key.get_secret_value() == "synthetic-old-key"

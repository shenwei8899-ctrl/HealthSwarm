"""图片协议、真实格式校验及失败终态回归。"""

import base64
import io
import json
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from PIL import Image

from yuxi.services import reference_recipe_image_tasks as tasks
from yuxi.services import reference_recipe_presentation as images


@pytest.fixture
def dish():
    return {
        "name": "蒸蛋",
        "ingredients": ["鸡蛋"],
        "steps": ["蒸熟"],
        "source": {"file_id": "recipe-1"},
        "health_profile": "must-not-send",
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("suffix", ["", "/images/generations"])
async def test_seedream_protocol_and_uploaded_webp(monkeypatch, dish, suffix):
    monkeypatch.setenv("RECIPE_IMAGE_API_KEY", "test-credential")
    monkeypatch.setenv("RECIPE_IMAGE_BASE_URL", "https://image.example/api/v3" + suffix)
    monkeypatch.setenv("RECIPE_IMAGE_MODEL", "doubao-seedream-5-0-flash-260915")
    monkeypatch.setattr(images, "generated_recipe_image", AsyncMock(return_value={}))
    upload = AsyncMock()
    monkeypatch.setattr(images, "get_minio_client", lambda: SimpleNamespace(aupload_file=upload))
    raw = io.BytesIO()
    Image.new("RGB", (1024, 1024), "white").save(raw, format="PNG")

    def respond(request):
        assert str(request.url) == "https://image.example/api/v3/images/generations"
        body = json.loads(request.content)
        assert body["response_format"] == "b64_json" and body["size"] == "2K"
        assert "quality" not in body and "sequential_image_generation" not in body
        assert "must-not-send" not in body["prompt"]
        assert body["model"] == "doubao-seedream-5-0-flash-260915"
        return httpx.Response(200, json={"data": [{"b64_json": base64.b64encode(raw.getvalue()).decode()}]})

    factory = httpx.AsyncClient
    monkeypatch.setattr(images.httpx, "AsyncClient", lambda **kw: factory(transport=httpx.MockTransport(respond), **kw))
    await images.generate_recipe_image(dish)
    args = upload.await_args.args
    assert args[:2] == ("public", images.recipe_image_key(dish)) and args[3] == "image/webp"
    with Image.open(io.BytesIO(args[2])) as result:
        assert result.format == "WEBP" and result.size == (720, 720)


@pytest.mark.asyncio
async def test_cached_image_never_calls_paid_provider(monkeypatch, dish):
    monkeypatch.delenv("RECIPE_IMAGE_API_KEY", raising=False)
    monkeypatch.setattr(images, "generated_recipe_image", AsyncMock(return_value={"image_url": "/existing.webp"}))
    await images.generate_recipe_image(dish)


@pytest.mark.asyncio
@pytest.mark.parametrize("missing", ["RECIPE_IMAGE_API_KEY", "RECIPE_IMAGE_BASE_URL"])
async def test_missing_image_config_is_explicit(monkeypatch, dish, missing):
    monkeypatch.setenv("RECIPE_IMAGE_API_KEY", "test-credential")
    monkeypatch.setenv("RECIPE_IMAGE_BASE_URL", "https://image.example/api/v3")
    monkeypatch.delenv(missing)
    monkeypatch.setattr(images, "generated_recipe_image", AsyncMock(return_value={}))
    with pytest.raises(ValueError, match="configuration missing"):
        await images.generate_recipe_image(dish)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [{"data": []}, {"data": [{"b64_json": "invalid!"}]}, {"data": [{"url": "https://untrusted.example/picture"}]}],
)
async def test_invalid_provider_content_is_not_published(monkeypatch, dish, payload):
    monkeypatch.setenv("RECIPE_IMAGE_API_KEY", "test-credential")
    monkeypatch.setenv("RECIPE_IMAGE_BASE_URL", "https://image.example/api/v3")
    monkeypatch.setattr(images, "generated_recipe_image", AsyncMock(return_value={}))
    upload = AsyncMock()
    monkeypatch.setattr(images, "get_minio_client", lambda: SimpleNamespace(aupload_file=upload))
    factory = httpx.AsyncClient
    monkeypatch.setattr(
        images.httpx,
        "AsyncClient",
        lambda **kw: factory(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload)), **kw),
    )
    assert await images.prepare_recipe_images([{"dishes": [dish]}]) == [False]
    upload.assert_not_awaited()


@pytest.mark.asyncio
async def test_partial_image_failure_cannot_be_task_success(monkeypatch):
    @asynccontextmanager
    async def session():
        yield SimpleNamespace(
            get=AsyncMock(
                return_value=SimpleNamespace(snapshot={"scope": "daily_reference", "meals": [{"dishes": [{}, {}]}]})
            )
        )

    monkeypatch.setattr(tasks.pg_manager, "get_async_session_context", session)
    monkeypatch.setattr(images, "prepare_recipe_images", AsyncMock(return_value=[True, False]))
    with pytest.raises(RuntimeError, match="incomplete"):
        await tasks.run_reference_recipe_images(SimpleNamespace(payload={"preview_id": "preview-1"}))

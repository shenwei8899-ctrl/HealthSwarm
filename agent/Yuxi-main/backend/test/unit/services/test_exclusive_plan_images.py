"""专属计划图片复用、后台租约及读取无生成副作用。"""

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from yuxi.services import exclusive_plan_images as images
from yuxi.services.health_vision_types import HealthVisionError


def dish(file_id="one"):
    """只含公开原谱事实的合成菜。"""
    return {
        "file_id": file_id,
        "chunk_id": "chunk",
        "name": "菠菜",
        "ingredients": ["菠菜100克"],
        "steps": ["炒熟"],
        "source": {"file_id": file_id, "file_hash": "hash"},
    }


@pytest.mark.asyncio
async def test_cached_images_deduplicate_and_never_generate(monkeypatch):
    """同来源只查一次；缺图不会调用付费服务。"""
    read = AsyncMock(side_effect=[{"image_url": "/minio/public/one.webp"}, {}])
    monkeypatch.setattr(images, "generated_recipe_image", read)
    generate = AsyncMock(side_effect=AssertionError("GET不能生成图片"))
    monkeypatch.setattr(images, "prepare_recipe_images", generate)
    result = await images.cached_plan_images([dish(), dish(), dish("two")])
    assert result == [{"file_id": "one", "image_url": "/minio/public/one.webp"}, {"file_id": "two"}]
    assert read.await_count == 2
    generate.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid,failed", [(False, False), (True, False), (False, True)])
async def test_image_task_rechecks_source_before_generation_and_holds_no_family_lock(monkeypatch, invalid, failed):
    """失效原谱不能出图；生成网络发生于释放事务之后，失败不伪装成功。"""
    from yuxi.services import exclusive_reference_plan as reference
    from yuxi.services import daily_dish_swap_service as swap

    transactions = []

    @asynccontextmanager
    async def session_context():
        """记录公开图片网络请求之前的事务边界。"""
        transactions.append(True)
        try:
            yield None
        finally:
            transactions.pop()

    entry = {"meals": [{"dishes": [dish(), dish()]}]}
    row = SimpleNamespace(progress={"tiers": {"economy": [entry]}})
    current = {"current": {"members": []}}
    monkeypatch.setattr(images.pg_manager, "get_async_session_context", session_context)
    monkeypatch.setattr(images, "image_context", AsyncMock(return_value=(row, current)))
    verified = AsyncMock(return_value={"content": "# 菠菜"})
    if invalid:
        verified.side_effect = HealthVisionError("source_invalidated", "来源改变", 410)
    monkeypatch.setattr(reference, "verified_reference_document", verified)
    monkeypatch.setattr(swap, "require_recipe_quotes", lambda *_: None)

    async def generate(meals):
        """不持事务、组内重复菜只生成一次。"""
        assert not transactions
        assert meals == [{"dishes": [dish()]}]
        return [not failed]

    generate_mock = AsyncMock(side_effect=generate)
    monkeypatch.setattr(images, "prepare_recipe_images", generate_mock)
    context = SimpleNamespace(
        payload={"uid": "self", "family_id": "family", "group_id": "group"},
        raise_if_cancelled=AsyncMock(),
        set_progress=AsyncMock(),
    )
    if invalid:
        with pytest.raises(HealthVisionError):
            await images.run_plan_images(context)
        generate_mock.assert_not_awaited()
    elif failed:
        with pytest.raises(RuntimeError, match="incomplete"):
            await images.run_plan_images(context)
    else:
        assert await images.run_plan_images(context) == {"group_id": "group", "dish_count": 1}
        context.raise_if_cancelled.assert_awaited_once()


@pytest.mark.asyncio
async def test_task_status_is_sampled_before_images(monkeypatch):
    """任务完成交错不会把早先缺图与success组合导致停止轮询。"""
    from yuxi.services import exclusive_plan_tasks

    row = SimpleNamespace(progress={"tiers": {"economy": [{"day": {"day_no": 1}, "meals": [{"dishes": [dish()]}]}]}})

    @asynccontextmanager
    async def transaction():
        """模拟已经授权的计划读取。"""
        yield None

    monkeypatch.setattr(images.pg_manager, "get_async_session_context", transaction)
    monkeypatch.setattr(images, "image_context", AsyncMock(return_value=(row, {})))
    monkeypatch.setattr(exclusive_plan_tasks, "validate_saved_days", AsyncMock())
    events = []

    async def status(**kwargs):
        """先读到running，后面的缓存读取才与完成交错。"""
        events.append("status")
        return SimpleNamespace(status="running")

    async def cached(dishes):
        """对象读取过程中任务可能完成；本响应仍保持running。"""
        events.append("images")
        return [{"file_id": "one"}]

    monkeypatch.setattr(images.tasker, "find_task_by_payload", status)
    monkeypatch.setattr(images, "cached_plan_images", cached)
    result = await images.read_plan_images("self", "family", "group", "economy", 1)
    assert events == ["status", "images"]
    assert result["status"] == "running"

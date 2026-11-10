"""检索性能改动保持身份匹配事实，并让任务心跳能够继续执行。"""

import asyncio
import json
import threading
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from langchain_core.messages import ToolMessage

from yuxi.agents.buildin.health_meal_planner.graph import MealPlanResultMiddleware
from yuxi.services import reference_recipe_index as search
from yuxi.services.reference_recipe_matching import (
    ReferenceProductIndex, reference_ingredient_candidates, reference_ingredient_matches,
)


@pytest.mark.parametrize("product_level", [True, False])
def test_compact_matching_equals_full_candidates_and_does_not_cache_later_catalog(product_level):
    """精简检索计算不得改变歧义、缺货规格、可选食材和后来目录的结果。"""
    products = [
        {"product_id": "egg", "sku_id": "1", "product_name": "鸡蛋", "price_cent": 500,
         "available_quantity": 0, "sale_status": "unavailable"},
        {"product_id": "egg", "sku_id": "2", "product_name": "鸡蛋", "price_cent": 900,
         "available_quantity": 5, "sale_status": "available"},
        {"product_id": "okra", "sku_id": "3", "product_name": "秋葵", "price_cent": 700,
         "available_quantity": 4, "ingredients": [{"name": "秋葵", "aliases": ["黄秋葵", "青菜"]}]},
        {"product_id": "green", "sku_id": "4", "product_name": "菠菜", "price_cent": 200,
         "available_quantity": 3, "ingredients": [{"name": "菠菜", "aliases": ["青菜"]}]},
    ]
    if not product_level:
        products = [{k: v for k, v in p.items() if k != "product_id"} for p in products]
    ingredients = ("鸡蛋 2个", "水 100克", "黄秋葵 200克", "青菜 100克", "鸭蛋 2个", "salt (optional)")
    full = reference_ingredient_candidates(ingredients, products)
    expected = [{
        "ingredient": g["ingredient"], "food": g["food"], "status": g["status"],
        "product_id": str(g["candidate_products"][0]["product_id"]) if g.get("candidate_products") else None,
        "sku_id": str(g["candidate_skus"][0]["sku_id"]) if g["candidate_skus"] else None,
    } for g in full]
    index = ReferenceProductIndex(products)
    assert reference_ingredient_matches(ingredients, products, index=index) == expected
    assert reference_ingredient_matches(ingredients, products, index=index) == expected
    assert [(r["food"], r["status"], r["product_id"], r["sku_id"]) for r in expected] == [
        ("鸡蛋", "matched", "egg" if product_level else None, "2"),
        ("水", "cooking_water", None, None),
        ("秋葵", "matched", "okra" if product_level else None, None if product_level else "3"),
        (None, "needs_confirmation", None, None),
        (None, "needs_confirmation", None, None),
        ("盐", "optional_not_selected", None, None),
    ]
    assert reference_ingredient_matches(("鸡蛋 2个",), [])[0]["status"] == "missing_product"


@pytest.mark.asyncio
@pytest.mark.parametrize("batch", [False, True])
async def test_search_allows_event_loop_heartbeat_during_cpu_work(monkeypatch, batch):
    """真实异步入口的同步排名发生在后台线程，不能把心跳一起堵住。"""
    rows = [("egg", "kb", "家常菜谱_鸡蛋羹.md", "hash", "chunk",
             "# 鸡蛋羹\n## 食材\n- 鸡蛋1个\n## 做法\n1. 蒸熟")]
    session = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(all=lambda: rows)))
    monkeypatch.setattr(search, "configured_health_kb_ids", lambda _: ("kb",))
    original = search.rank_prepared_reference_recipes
    main_thread = threading.get_ident()
    started = threading.Event()
    release = threading.Event()
    observed = []

    def delayed(*args, **kwargs):
        observed.append(threading.get_ident())
        started.set()
        release.wait(0.5)
        return original(*args, **kwargs)

    monkeypatch.setattr(search, "rank_prepared_reference_recipes", delayed)
    call = (search.purchasable_reference_recipes_batch(session, [], ["鸡蛋"])
            if batch else search.purchasable_reference_recipes(session, [], "鸡蛋"))
    task = asyncio.create_task(call)
    for _ in range(100):
        if started.is_set():
            break
        await asyncio.sleep(0.005)
    assert started.is_set()
    # 工作尚未结束时，事件循环已能运行到这里并发出心跳/释放信号。
    assert not task.done()
    assert observed == [observed[0]] and observed[0] != main_thread
    release.set()
    result = await task
    assert (result[0] if batch else result)[0]["file_id"] == "egg"


@pytest.mark.asyncio
async def test_cancelled_requests_cannot_start_more_than_two_cpu_jobs(monkeypatch):
    """原生 task.cancel 不释放仍在执行的线程槽，重复重试不会堆积 CPU 线程。"""
    session = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(all=lambda: [])))
    monkeypatch.setattr(search, "configured_health_kb_ids", lambda _: ("kb",))
    release = threading.Event()
    lock = threading.Lock()
    started = []

    def delayed(rows, products, queries, excluded_file_ids=None):
        with lock:
            started.append(queries[0])
        release.wait(3)
        return [[]]

    monkeypatch.setattr(search, "rank_reference_recipe_batch", delayed)
    tasks = [asyncio.create_task(search.purchasable_reference_recipes_batch(session, [], [str(i)])) for i in range(2)]
    third = None
    try:
        for _ in range(200):
            if len(started) == 2:
                break
            await asyncio.sleep(0.005)
        assert len(started) == 2
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        third = asyncio.create_task(search.purchasable_reference_recipes_batch(session, [], ["third"]))
        await asyncio.sleep(0.05)
        assert len(started) == 2
        assert not third.done()
        release.set()
        assert await third == [[]]
        assert started[-1] == "third"
    finally:
        release.set()
        await asyncio.gather(*tasks, *([third] if third else []), return_exceptions=True)


def test_model_projection_keeps_nutrition_and_identity_without_changing_receipt():
    """模型不再重复接收每个规格的同份详情，服务端的完整采购回执不变。"""
    product = {"product_id": "1", "product_name": "鸡蛋", "product_description": "真实营养原文",
               "allergen_codes": ["egg"], "data_issues": ["待核实"], "image_url": "image",
               "skus": [{"sku_id": "2", "price_cent": 500, "product_description": "真实营养原文"}]}
    payload = {"products": [product], "catalog": [product], "catalog_version": "v1"}
    message = ToolMessage(json.dumps(payload), name="find_reference_products", tool_call_id="call")
    projected = MealPlanResultMiddleware._compact_reference_products(message)
    compact = json.loads(projected.content)
    assert compact["products"][0] == {k: v for k, v in product.items() if k not in {"image_url", "skus"}}
    assert compact["catalog_version"] == "v1"
    assert "catalog" not in compact
    assert json.loads(message.content) == payload
    assert projected.tool_call_id == message.tool_call_id

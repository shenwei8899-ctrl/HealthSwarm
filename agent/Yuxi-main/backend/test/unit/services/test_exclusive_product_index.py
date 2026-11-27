"""固定目录只准备一次，计价结果仍遵循原采购规则。"""

from copy import deepcopy
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

from yuxi.services import exclusive_reference_plan as reference
from test.unit.services.test_exclusive_plan_prices import meals, reference_context, sku


def test_one_day_builds_one_index_for_candidates_and_procurement(monkeypatch):
    """单日全部候选及采购比较共用索引，旧实现会逐菜构建。"""
    original = reference.ReferenceProductIndex
    builds = []

    def build(products):
        """保留真实索引与计价，仅记录构建次数。"""
        builds.append(products)
        return original(products)

    monkeypatch.setattr(reference, "ReferenceProductIndex", build)
    result = reference.generate_reference_day(reference_context(), "economy", [], "stable", {"items": [sku()]})
    assert len(result["meals"]) == 3
    assert result["procurement"]["pricing"]["matched_subtotal_cent"] > 0
    assert len(builds) == 1


@pytest.mark.parametrize("changes", [{}, {"price_cent": 0}, {"available_quantity": 0}, {"price_cent": None}])
@pytest.mark.parametrize("ingredients", [("大米100克",), ("大米100克", "菠菜适量"), ("大米1杯",)])
def test_shared_index_preserves_procurement_and_cost(changes, ingredients):
    """共享准备结果保持金额、未知食材和库存缺口完全一致。"""
    catalog = {"items": [sku(**changes)], "version": "synthetic"}
    before = deepcopy(catalog)
    index = reference.ReferenceProductIndex(catalog["items"])
    expected = reference.reference_procurement(meals(*ingredients), catalog)
    assert reference.reference_procurement(meals(*ingredients), catalog, product_index=index) == expected
    assert reference.recipe_cost_evidence(ingredients, catalog, product_index=index) == reference.recipe_cost_evidence(
        ingredients, catalog
    )
    assert catalog == before


def test_new_snapshot_uses_new_price_even_with_same_version():
    """两个独立快照不共享商品引用及食材解析缓存。"""
    first = {"items": [sku(price_cent=500)], "version": "same"}
    second = {"items": [sku(price_cent=1000)], "version": "same"}
    assert reference.recipe_cost_evidence(("大米100克",), first) == 100
    assert reference.recipe_cost_evidence(("大米100克",), second) == 200


def test_shared_index_does_not_cache_restriction_results():
    """同食材解析可复用，每次采购仍核对传入限制。"""
    catalog = {"items": [sku()]}
    index = reference.ReferenceProductIndex(catalog["items"])
    for restrictions in [(), ["大米"], ()]:
        assert reference.reference_procurement(
            meals("大米100克"), catalog, restrictions, product_index=index
        ) == reference.reference_procurement(meals("大米100克"), catalog, restrictions)


def test_unavailable_catalog_keeps_purchase_gaps_with_shared_index():
    """空目录仍保留未计价食材，不产生完整报价。"""
    catalog = {"items": [], "status": "unavailable"}
    index = reference.ReferenceProductIndex([])
    result = reference.reference_procurement(meals("大米100克"), catalog, product_index=index)
    assert result == reference.reference_procurement(meals("大米100克"), catalog)
    assert result["purchase_gaps"][0]["reason"] == "catalog_unavailable"
    assert result["pricing"]["matched_subtotal_cent"] is None


@pytest.mark.asyncio
async def test_three_tier_task_reuses_index_and_rebuilds_on_resume(monkeypatch):
    """真实生成函数跨三档复用；进程恢复重建索引并保留已保存天序。"""
    from yuxi.services import exclusive_plan_tasks as tasks

    row = SimpleNamespace(progress={"tiers": {}}, selection={"plan_date": "2099-01-01"})
    catalog = {"items": [sku()]}
    original = reference.ReferenceProductIndex
    builds, progress = [], []

    def build(products):
        """记录真正建立的索引。"""
        result = original(products)
        builds.append(result)
        return result

    @asynccontextmanager
    async def session():
        """单元测试隔离持久化，生成与计价保持真实。"""
        yield None

    async def owned(*args, **kwargs):
        """返回本测试的任务状态。"""
        return row

    async def inputs(*args, day, **kwargs):
        """提供每一天的合成原谱。"""
        result = reference_context()
        result["selection"].plan_date = day
        # 固定成员和家庭，使日期之外的输入在恢复时保持一致。
        result["selection"].family_id = selection.family_id
        result["selection"].participant_ids = selection.participant_ids
        return result

    async def validate(*args):
        """事务和来源授权由原有集成测试验证。"""

    async def document(session, file_id, chunk_id):
        """对象存储返回固定合成原谱，保留真实来源复核和采购重算。"""
        prepared = next(item for item in documents if item["source"]["file_id"] == file_id)
        return {**prepared["source"], "content": prepared["content"], "chunks_hash": prepared["chunks_hash"]}

    async def save(fn):
        """执行原逐日保存回调。"""
        await fn(None, None)

    async def report(*args):
        """第一天保存后模拟执行中断。"""
        progress.append(args)
        if len(progress) == 1:
            raise InterruptedError("synthetic interruption")

    selection = reference_context()["selection"]
    documents = reference_context()["documents"]
    context = SimpleNamespace(raise_if_cancelled=validate, run_owned_transaction=save, set_progress=report)
    monkeypatch.setattr(tasks.pg_manager, "get_async_session_context", session)
    monkeypatch.setattr(tasks, "owned_group", owned)
    monkeypatch.setattr(tasks, "exclusive_context", inputs)
    monkeypatch.setattr(tasks, "assert_basis", lambda *args: None)
    monkeypatch.setattr(reference, "recipe_document", document)
    monkeypatch.setattr(tasks, "ReferenceProductIndex", build)
    monkeypatch.setattr(reference, "ReferenceProductIndex", build)

    with pytest.raises(InterruptedError):
        await tasks.generate_exclusive_tiers(context, "actor", "family", "stable", tasks.PREVIEW_POLICY, catalog)
    assert len(builds) == 1
    first = deepcopy(row.progress["tiers"]["economy"][0])
    await tasks.generate_exclusive_tiers(context, "actor", "family", "stable", tasks.PREVIEW_POLICY, catalog)
    assert len(builds) == 2
    assert builds[0] is not builds[1]
    assert row.progress["tiers"]["economy"][0] == first
    assert all(len(row.progress["tiers"][tier]) == 7 for tier in tasks.TIERS)
    assert len(progress) == 21

"""采购范围和摘要回归；外部授权的 HTTP/PG 证据由集成测试拥有。"""

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock
from datetime import date

import pytest
from yuxi.services import meal_purchase_source as source
from yuxi.services import meal_dish_service as purchase
from yuxi.services.health_vision_types import HealthVisionError


def test_current_memory_restricts_final_sku_even_when_recipe_has_no_conflict():
    resolved = [({"ingredients": ["大米"]}, {}, [], {"purchase_restrictions": ["牛肉"]})]
    purchase.validate_purchase_restrictions(resolved, [{"product_description": "大米"}])
    with pytest.raises(HealthVisionError, match="采购商品"):
        purchase.validate_purchase_restrictions(resolved, [{"product_description": "beef"}])


@pytest.mark.asyncio
async def test_signed_purchase_rechecks_new_memory_when_sku_identity_is_unchanged(monkeypatch):
    from contextlib import asynccontextmanager
    from yuxi.storage.postgres.manager import pg_manager
    from yuxi.services import daily_commerce_service as commerce
    import time

    resolved = [({"ingredients": ["大米"]}, {}, [], {"purchase_restrictions": []})]
    sku = {"sku_id": "rice", "product_description": "beef"}
    receipt = {"expires_at": time.time()+100, "scope_hash_version": 2, "uid": "self",
               "family_id": "family", "date": "2026-11-19", "meal_type": "dinner", "version": 1,
               "dish_keys": ["rice"], "scope_hash": purchase.procurement_hash(resolved),
               "items": [{"sku_id": "rice", "quantity": 1, "identity": purchase.merchant_facts(sku)}]}

    @asynccontextmanager
    async def transaction():
        """隔离连接，实际执行回源用例和商品限制检查。"""
        yield None

    monkeypatch.setattr(pg_manager, "get_async_session_context", transaction)
    monkeypatch.setattr(source, "selected_purchase_origins", AsyncMock(return_value=resolved))
    monkeypatch.setattr(commerce, "current_catalog", AsyncMock(return_value={"items": [sku]}))
    assert (await purchase.validate_selection_purchase(receipt))["available"]
    resolved[0][3]["purchase_restrictions"] = ["牛肉"]
    assert purchase.procurement_hash(resolved) == receipt["scope_hash"]
    with pytest.raises(HealthVisionError, match="采购商品"):
        await purchase.validate_selection_purchase(receipt)


@pytest.mark.asyncio
async def test_current_memory_restriction_blocks_selected_recipe_without_object_download(monkeypatch):
    from yuxi.repositories import meal_purchase_repository as repo
    from yuxi.services import health_family_kb_service as kb

    text = "牛肉100克"
    file = SimpleNamespace(is_folder=False, status="indexed", kb_id="recipes", content_hash="v1")
    chunks = [SimpleNamespace(chunk_id="chunk", content=text)]
    monkeypatch.setattr(repo, "recipe_version", AsyncMock(return_value=(file, chunks)))
    monkeypatch.setattr(kb, "configured_health_kb_ids", lambda role: ["recipes"])
    dish = {"file_id": "beef", "chunk_id": "chunk", "source": {
        "kb_id": "recipes", "file_hash": "v1", "chunks_hash": source.input_fingerprint([("chunk", text)])}}
    await source.recipe_metadata(None, dish, [])
    with pytest.raises(HealthVisionError, match="当前明确限制"):
        await source.recipe_metadata(None, dish, ["牛肉"])


@pytest.mark.asyncio
async def test_only_selected_origin_is_resolved(monkeypatch):
    from yuxi.services import daily_meal_plan_service as daily

    origins = [{"dish_key": k, "source": {"kind": "reference", "id": k}} for k in ("fish", "rice")]
    row = SimpleNamespace(
        version=4,
        meal_sources={
            "dinner": {"kind": "selection", "dish_sources": origins, "member_ids": ["self"]},
            "lunch": {"kind": "invalid"},
        },
    )
    monkeypatch.setattr(daily, "current_row", AsyncMock(return_value=row))
    reader = AsyncMock(return_value=({"ingredients": ["鱼100克"]}, {}, [{"id": "self"}], {}))
    monkeypatch.setattr(source, "purchase_origin", reader)
    result = await source.selected_purchase_origins(None, "self", "family", date(2026, 11, 17), "dinner", 4, ["fish"])
    assert reader.await_count == 1 and reader.call_args.args[3] is origins[0]
    assert result[0][0]["dish_key"] == "fish"
    for keys in (["foreign"], ["fish", "fish"]):
        with pytest.raises(HealthVisionError, match="采购菜品"):
            await source.selected_purchase_origins(None, "self", "family", date(2026, 11, 17), "dinner", 4, keys)
    with pytest.raises(HealthVisionError, match="餐单已更新"):
        await source.selected_purchase_origins(None, "self", "family", date(2026, 11, 17), "dinner", 3, ["fish"])


def test_procurement_digest_ignores_nested_media_but_binds_selected_mapping():
    dish = {"ingredients": ["鱼100克"], "origin": {"snapshot": {"dish": {"image_url": "old"}}}}
    saved = {
        "product_matches": [
            {"ingredient_refs": ["鱼100克"], "product_id": "fish", "image_url": "old"},
            {"ingredient_refs": ["米100克"], "product_id": "rice"},
        ]
    }
    result = [(dish, {}, [], saved)]
    digest = purchase.procurement_hash(result)
    modified = deepcopy(result)
    modified[0][0]["origin"]["snapshot"]["dish"]["image_url"] = "new"
    modified[0][3]["product_matches"][0]["image_url"] = "new"
    modified[0][3]["product_matches"][1]["product_id"] = "different-rice"
    assert purchase.procurement_hash(modified) == digest
    modified[0][3]["product_matches"][0]["product_id"] = "different-fish"
    assert purchase.procurement_hash(modified) != digest
    formal = [(dish, {}, [], {"procurement_mapping": {"recipe_hash": "v1", "ingredient_codes": {"food": "fish"}}})]
    digest = purchase.procurement_hash(formal)
    formal[0][3]["procurement_mapping"]["ingredient_codes"]["food"] = "rice"
    assert purchase.procurement_hash(formal) != digest


@pytest.mark.asyncio
async def test_resolved_purchase_does_not_read_origin_again(monkeypatch):
    from test.unit.services.test_meal_dish_product_purchase import purchase_case

    dish, saved, catalog = purchase_case()
    reader = AsyncMock(side_effect=AssertionError("duplicate origin read"))
    monkeypatch.setattr(purchase, "read_origin", reader)
    selected = {**dish, "origin": {"source": {"kind": "reference"}}}
    items, _, _ = await purchase.purchase_items(
        None, "self", "family", [selected], catalog, resolved=[(dish, {}, [], saved)]
    )
    assert len(items) == 2
    reader.assert_not_awaited()


@pytest.mark.asyncio
async def test_reference_purchase_requires_completed_adopted_authorized_binding(monkeypatch):
    from yuxi.services import reference_meal_plan_service as reference
    from yuxi.services import health_memory_context_service as memory
    monkeypatch.setattr(reference, "bound_reference_context", AsyncMock(return_value={"members": []}))
    restrictions = AsyncMock(return_value=[])
    monkeypatch.setattr(memory, "memory_restrictions_for_plan", restrictions)
    from yuxi.services import health_consultation_service as consent
    from yuxi.repositories.health_task_repository import HealthTaskRepository
    from yuxi.services.reference_meal_plan_types import REFERENCE_CATALOG_CHAIN_VERSION

    selected = {"family_id": "family", "plan_date": "2026-11-17", "mode": "reference"}
    saved = SimpleNamespace(
        id="preview",
        run_id="run",
        actor_uid="self",
        conversation_id="thread",
        member_id="member",
        selection=selected,
        snapshot={
            "sources": {"profile": "v1"},
            "catalog_chain_version": REFERENCE_CATALOG_CHAIN_VERSION,
            "scope": "daily_reference",
            "status": "reference_ready",
            "professional_status": "not_reviewed",
            "nutrition_status": "not_calculated",
        },
    )
    run = SimpleNamespace(
        uid="self",
        status="completed",
        conversation_thread_id="thread",
        input_payload={},
        conversation_id="thread",
        agent_slug="health-meal-planner",
    )
    binding = SimpleNamespace(
        conversation_id="thread",
        member_id="member",
        initial_planner_selection={
            "selection": deepcopy(selected),
            "source_hash": source.input_fingerprint(saved.snapshot["sources"]),
        },
    )
    session = SimpleNamespace(get=AsyncMock(return_value=run))
    authorization = AsyncMock(return_value=(binding, {}))
    message = AsyncMock(return_value=SimpleNamespace(content='{"preview_id":"preview"}'))
    monkeypatch.setattr(consent, "require_consultation", authorization)
    monkeypatch.setattr(HealthTaskRepository, "final_message", message)
    assert (await source.published_reference(session, "family", "2026-11-17", saved))["source_owner"] == "self"

    for field, bad, error in [
        ("actor_uid", "other", "尚未完成发布"),
        ("conversation_id", "foreign", "尚未完成发布"),
        ("member_id", "foreign", "授权来源"),
        ("selection", {**selected, "meal_types": []}, "授权来源"),
        ("snapshot", {**saved.snapshot, "sources": {}}, "授权来源"),
    ]:
        broken = deepcopy(saved)
        setattr(broken, field, bad)
        with pytest.raises(HealthVisionError, match=error):
            await source.published_reference(session, "family", "2026-11-17", broken)
    run.status = "running"
    with pytest.raises(HealthVisionError, match="尚未完成发布"):
        await source.published_reference(session, "family", "2026-11-17", saved)
    run.status = "completed"
    for field, bad in [("conversation_id", "foreign"), ("agent_slug", "health-consultation")]:
        previous = getattr(run, field)
        setattr(run, field, bad)
        with pytest.raises(HealthVisionError, match="尚未完成发布"):
            await source.published_reference(session, "family", "2026-11-17", saved)
        setattr(run, field, previous)
    for field in ("scope", "status", "professional_status", "nutrition_status"):
        broken = deepcopy(saved)
        broken.snapshot[field] = "invalid"
        with pytest.raises(HealthVisionError, match="授权来源"):
            await source.published_reference(session, "family", "2026-11-17", broken)
    message.return_value.content = '{"preview_id":"another"}'
    with pytest.raises(HealthVisionError, match="最终采用"):
        await source.published_reference(session, "family", "2026-11-17", saved)
    authorization.side_effect = HealthVisionError("forbidden", "授权已撤销", 403)
    with pytest.raises(HealthVisionError, match="授权已撤销"):
        await source.published_reference(session, "family", "2026-11-17", saved)
    authorization.side_effect = None
    message.return_value.content = '{"preview_id":"preview"}'
    restrictions.side_effect = HealthVisionError("memory_changed", "记忆已变化", 409)
    with pytest.raises(HealthVisionError, match="记忆已变化"):
        await source.published_reference(session, "family", "2026-11-17", saved)


@pytest.mark.asyncio
async def test_recipe_purchase_checks_metadata_without_display_or_object_download(monkeypatch):
    from yuxi.repositories import meal_purchase_repository as repo
    from yuxi.services import health_family_kb_service as kb

    file = SimpleNamespace(is_folder=False, status="indexed", kb_id="recipes", content_hash="v1")
    chunk = SimpleNamespace(chunk_id="chunk", content="合成原文")
    reader = AsyncMock(return_value=(file, [chunk]))
    monkeypatch.setattr(repo, "recipe_version", reader)
    monkeypatch.setattr(kb, "configured_health_kb_ids", lambda role: ["recipes"])
    dish = {
        "file_id": "fish",
        "chunk_id": "chunk",
        "source": {
            "kb_id": "recipes",
            "file_hash": "v1",
            "chunks_hash": source.input_fingerprint([("chunk", "合成原文")]),
        },
    }
    await source.recipe_metadata(None, dish)
    assert reader.call_args.args == (None, "fish", ["recipes"])
    for field, bad in [("is_folder", True), ("status", "pending"), ("kb_id", "foreign"), ("content_hash", "v2")]:
        old = getattr(file, field)
        setattr(file, field, bad)
        with pytest.raises(HealthVisionError, match="来源版本"):
            await source.recipe_metadata(None, dish)
        setattr(file, field, old)
    chunk.content = "变更后的正文"
    with pytest.raises(HealthVisionError, match="分片版本"):
        await source.recipe_metadata(None, dish)
    reader.return_value = (file, [])
    with pytest.raises(HealthVisionError, match="分片版本"):
        await source.recipe_metadata(None, dish)


@pytest.mark.asyncio
async def test_formal_purchase_reuses_quality_owner_and_binds_mapping(monkeypatch):
    meal = {"dishes": [{"dish_key": "fish", "recipeVersion": "v1"}, {"dish_key": "rice", "recipeVersion": "v2"}]}
    reader = AsyncMock(return_value=(meal["dishes"][0], meal, [{"id": "self"}], {}))
    monkeypatch.setattr(purchase, "read_origin", reader)
    mapping = SimpleNamespace(recipe_hash="recipe-hash", ingredient_codes={"food": "fish"})
    session = SimpleNamespace(get=AsyncMock(return_value=mapping))
    origin = {
        "source": {"kind": "formal", "id": "plan", "version": 1},
        "date": "2026-11-17",
        "meal_type": "dinner",
        "dish_key": "fish",
    }
    cache = {}
    result = await source.purchase_origin(session, "self", "family", origin, cache)
    assert result[3]["procurement_mapping"] == {"recipe_hash": "recipe-hash", "ingredient_codes": {"food": "fish"}}
    result = await source.purchase_origin(session, "self", "family", {**origin, "dish_key": "rice"}, cache)
    assert result[0]["recipeVersion"] == "v2" and reader.await_count == 1
    session.get.return_value = None
    with pytest.raises(HealthVisionError, match="采购映射尚未发布"):
        await source.purchase_origin(session, "self", "family", origin, cache)


@pytest.mark.asyncio
async def test_replacement_purchase_requires_current_anchor_and_profile(monkeypatch):
    from yuxi.services import daily_dish_swap_service as swap

    anchor = {
        "source": {"kind": "reference", "id": "original"},
        "date": "2026-11-17",
        "meal_type": "dinner",
        "dish_key": "fish",
    }
    dish = {"dish_key": "new", "file_id": "new", "ingredients": ["鱼"]}
    saved = {"dish": dish, "context_sources": {"profile": "v1"}, "product_matches": []}
    origin = {
        "source": {"kind": "replacement"},
        "anchor": anchor,
        "snapshot": saved,
        "actor_uid": "self",
        "date": "2026-11-17",
        "meal_type": "dinner",
    }
    context = {"sources": {"profile": "v1", "memory": {}}, "members": [{"id": "self"}]}
    monkeypatch.setattr(swap, "meal_context", AsyncMock(return_value=context))
    metadata = AsyncMock()
    monkeypatch.setattr(source, "recipe_metadata", metadata)
    cache = {
        ("reference", "original"): {
            "meals": [{"meal_type": "dinner", "dishes": [{"dish_key": "fish"}]}],
            "members": [{"id": "self"}],
        }
    }
    result = await source.purchase_origin(None, "self", "family", origin, cache)
    assert result[0] == dish and result[3]["product_matches"] == []
    context["sources"] = {"profile": "v2"}
    with pytest.raises(HealthVisionError, match="就餐成员资料"):
        await source.purchase_origin(None, "self", "family", origin, cache)
    cache[("reference", "original")]["meals"][0]["dishes"] = []
    with pytest.raises(HealthVisionError, match="原餐单已没有"):
        await source.purchase_origin(None, "self", "family", origin, cache)

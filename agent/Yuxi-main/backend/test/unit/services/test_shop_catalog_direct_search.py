"""商城数据库直读只用于有限商品发现，交易仍按商城事实复核。"""

from contextlib import asynccontextmanager
from copy import deepcopy
import json
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from yuxi.repositories import shop_catalog_repository as catalog_repo
from yuxi.services import conversation_purchase_service as service
from yuxi.services.health_vision_types import HealthVisionError

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]


def sku(sid):
    """构造与商城详情契约一致的合成商品。"""
    return {
        "sku_id": str(sid),
        "product_id": str(sid),
        "product_name": "合成燕麦" + str(sid),
        "category_code": "grain",
        "net_content": {"value": "500", "unit": "g"},
        "product_description": "合成配料说明",
        "price_cent": 1200,
        "sale_status": "available",
        "available_quantity": 5,
        "ingredients": [],
        "allergen_codes": [],
    }


def row(sid):
    """数据库只返回候选索引，不携带商品配料正文。"""
    return {
        "sku_id": sid,
        "product_name": "合成燕麦" + str(sid),
        "category_code": "grain",
        "net_content_value": "500",
        "net_content_unit": "g",
    }


class FakeConnection:
    """记录只读事务与参数化查询的最小连接替身。"""

    def __init__(self, rows):
        self.rows = rows
        self.calls = []
        self.closed = False

    @asynccontextmanager
    async def transaction(self, **options):
        self.calls.append(("transaction", options))
        yield

    async def fetch(self, sql, *args):
        self.calls.append(("fetch", sql, args))
        return self.rows

    async def fetchval(self, sql):
        self.calls.append(("fetchval", sql))
        return "catalog-test-1"

    async def close(self):
        self.closed = True


async def test_direct_search_is_bounded_parameterized_and_readonly(monkeypatch):
    """特殊查询词只作为参数，数据库最多给出一页与是否有下一页。"""
    monkeypatch.setenv("HEALTH_COMMERCE_SEARCH_DSN", "postgresql://readonly@example.invalid/shop")
    connection = FakeConnection([row(i) for i in range(1, 12)])
    monkeypatch.setattr(catalog_repo.asyncpg, "connect", AsyncMock(return_value=connection))

    page = await catalog_repo.search_shop_catalog("燕麦%_\\", 0, ["grain"])

    assert len(page["items"]) == 3
    assert page["next_offset"] == 3
    assert page["version"] == "catalog-test-1"
    assert connection.calls[0] == ("transaction", {"isolation": "repeatable_read", "readonly": True})
    _, sql, args = connection.calls[1]
    assert "LIMIT 4 OFFSET $3" in sql and "review_status = 'approved'" in sql
    assert args[:3] == ("燕麦%_\\", "%燕麦\\%\\_\\\\%", 0)
    assert args[4] == ["grain"]
    assert "business_category_code = ANY($5::text[])" in sql
    assert "regexp_replace(g.title, '[[:space:]]+', '', 'g') ILIKE" in sql
    assert connection.closed is True


async def test_direct_search_normalizes_whitespace_like_catalog_query_deduplication(monkeypatch):
    """空白不同的同义查询须命中同一商品，避免后续查询被去重后漏掉。"""
    monkeypatch.setenv("HEALTH_COMMERCE_SEARCH_DSN", "postgresql://readonly@example.invalid/shop")
    connection = FakeConnection([row(1)])
    monkeypatch.setattr(catalog_repo.asyncpg, "connect", AsyncMock(return_value=connection))

    await catalog_repo.search_shop_catalog("燕 麦", 0, ["grain"])

    _, _, args = connection.calls[1]
    assert args[0:2] == ("燕麦", "%燕麦%")


async def test_direct_search_requires_a_configured_readonly_connection(monkeypatch):
    """未配置商城库时不尝试连接其他数据库。"""
    monkeypatch.delenv("HEALTH_COMMERCE_SEARCH_DSN", raising=False)
    with pytest.raises(HealthVisionError, match="commerce_not_configured"):
        await catalog_repo.search_shop_catalog("燕麦", 0, ["grain"])


async def test_direct_search_reports_database_outage(monkeypatch):
    """已配置连接失败时明确报错，不暗中读取完整目录。"""
    monkeypatch.setenv("HEALTH_COMMERCE_SEARCH_DSN", "postgresql://readonly@example.invalid/shop")
    monkeypatch.setattr(catalog_repo.asyncpg, "connect", AsyncMock(side_effect=OSError("synthetic outage")))
    with pytest.raises(HealthVisionError, match="commerce_unavailable"):
        await catalog_repo.search_shop_catalog("燕麦", 0, ["grain"])


async def test_restriction_alias_ambiguity_stays_unknown(monkeypatch):
    """同名别名映射多个食材时不能据此宣称商品可购买。"""
    monkeypatch.setenv("HEALTH_COMMERCE_SEARCH_DSN", "postgresql://readonly@example.invalid/shop")
    connection = FakeConnection(
        [
            {"name": "花生", "ingredient_code": "peanut"},
            {"name": "花生", "ingredient_code": "other"},
            {"name": "牛奶", "ingredient_code": "milk"},
        ]
    )
    monkeypatch.setattr(catalog_repo.asyncpg, "connect", AsyncMock(return_value=connection))
    codes = await catalog_repo.lookup_restriction_codes(["花生", "牛奶"])
    assert codes == {"花生": None, "牛奶": "milk"}
    restricted = sku(1)
    restricted["data_completeness"] = "complete"
    restricted["ingredients"] = [
        {
            "ingredient_id": "1",
            "ingredient_code": "oat",
            "name": "燕麦",
            "review_status": "approved",
            "net_unit": "g",
            "net_value": "500",
        }
    ]
    profile = {"dietary_details": {"allergyStatus": "set", "allergies": ["花生"]}}
    assert (
        service.catalog_purchase_available(profile, restricted, {"items": [restricted], "restriction_codes": codes})
        is False
    )
    assert connection.calls[0] == ("transaction", {"readonly": True})
    assert connection.closed is True


async def test_direct_candidates_read_only_three_current_sku_details(monkeypatch):
    """数据库候选最多只对三个 SKU 读取商城详情。"""
    monkeypatch.setattr(
        service,
        "search_shop_catalog",
        AsyncMock(return_value={"items": [row(i) for i in range(1, 4)], "version": "v1", "next_offset": 3}),
    )
    requests = []

    async def request(method, path):
        requests.append((method, path))
        return sku(path.rsplit("/", 1)[-1])

    monkeypatch.setattr(service, "commerce_request", request)
    catalog = await service.direct_shop_catalog("燕麦", 0, ["grain"])
    assert len(catalog["index"]) == 3
    assert [item["sku_id"] for item in catalog["items"]] == ["1", "2", "3"]
    assert [path.rsplit("/", 1)[-1] for _, path in requests] == ["1", "2", "3"]

    async def updated_detail(method, path):
        detail = sku(path.rsplit("/", 1)[-1])
        detail["product_name"] = "商城新名称"
        detail["net_content"] = {"value": "250", "unit": "g"}
        return detail

    monkeypatch.setattr(service, "commerce_request", updated_detail)
    refreshed = await service.direct_shop_catalog("燕麦", 0, ["grain"])
    assert refreshed["index"][0]["name"] == "商城新名称"
    assert refreshed["index"][0]["spec"] == service.public_offer(refreshed["items"][0])["spec"]

    async def changed(method, path):
        detail = sku(path.rsplit("/", 1)[-1])
        detail["sale_status"] = "unavailable"
        return detail

    monkeypatch.setattr(service, "commerce_request", changed)
    with pytest.raises(HealthVisionError, match="catalog_changed"):
        await service.direct_shop_catalog("燕麦", 0, ["grain"])

    async def wrong_category(method, path):
        detail = sku(path.rsplit("/", 1)[-1])
        detail["category_code"] = "fruit"
        return detail

    monkeypatch.setattr(service, "commerce_request", wrong_category)
    with pytest.raises(HealthVisionError, match="catalog_changed"):
        await service.direct_shop_catalog("燕麦", 0, ["grain"])


@pytest.mark.parametrize("configured", [False, True])
async def test_consultation_switches_only_when_shop_dsn_is_configured(monkeypatch, configured):
    """缺少商城只读连接时，原有完整目录路径保持可用。"""
    monkeypatch.setenv("HEALTH_COMMERCE_SOURCE_SECRET", "synthetic-conversation-source-secret-0123456789")
    if configured:
        monkeypatch.setenv("HEALTH_COMMERCE_SEARCH_DSN", "postgresql://readonly@example.invalid/shop")
    else:
        monkeypatch.delenv("HEALTH_COMMERCE_SEARCH_DSN", raising=False)

    @asynccontextmanager
    async def session():
        yield object()

    profile = {"dietary_details": {}}
    member = SimpleNamespace(id="member", confirmed_version=1, profile=profile)
    run = SimpleNamespace(uid="self", id="run", request_id="request", input_payload={"health_processing": {}})
    monkeypatch.setattr(service.pg_manager, "get_async_session_context", session)
    consultation = SimpleNamespace(
        require_consultation_attempt=AsyncMock(),
        require_consultation=AsyncMock(return_value=(SimpleNamespace(member_id="member"), None)),
    )
    monkeypatch.setitem(sys.modules, "yuxi.services.health_consultation_service", consultation)
    monkeypatch.setattr(service.HealthConsultationRepository, "require_attempt", AsyncMock(return_value=run))
    monkeypatch.setattr(service, "require_shopping_member", AsyncMock(return_value=member))
    monkeypatch.setattr(
        service.ConversationPurchaseRepository,
        "catalog_profile_payloads",
        AsyncMock(return_value=[json.dumps({"categories": [{"category_code": "grain"}]})]),
    )
    monkeypatch.setattr(service, "validate_catalog_profile_payload", AsyncMock())
    monkeypatch.setattr(service, "current_restriction_codes", AsyncMock(return_value={}))
    legacy = AsyncMock(return_value={"version": "legacy", "items": [sku(1)]})
    direct = AsyncMock(
        return_value={
            "direct_search": True,
            "version": "direct",
            "items": [sku(1)],
            "index": [row(1)],
            "next_offset": None,
        }
    )
    monkeypatch.setattr(service, "current_catalog", legacy)
    monkeypatch.setattr(service, "direct_shop_catalog", direct)

    result = await service.find_conversation_packages(
        SimpleNamespace(uid="self", thread_id="thread"), "燕麦", category_codes=["grain"]
    )
    assert len(result["offers"]) == 1
    assert service.decode_offer(result["offers"][0]["offer_token"]).get("catalog_lookup") == (
        "shop_db_v1" if configured else None
    )
    assert direct.await_count == int(configured)
    assert legacy.await_count == int(not configured)


async def test_direct_receipt_rechecks_one_sku_and_restriction(monkeypatch):
    """受限档案可按当前食材代码核对，商品变化使旧回执失效。"""
    monkeypatch.setenv("HEALTH_COMMERCE_SOURCE_SECRET", "synthetic-conversation-source-secret-0123456789")
    current = sku(1)
    current["data_completeness"] = "complete"
    current["ingredients"] = [
        {
            "ingredient_id": "1",
            "ingredient_code": "oat",
            "name": "燕麦",
            "review_status": "approved",
            "net_unit": "g",
            "net_value": "500",
        }
    ]
    profile = {
        "dietary_details": {
            "allergyStatus": "set",
            "allergies": ["花生"],
            "intoleranceStatus": "none",
            "avoidanceStatus": "none",
            "doctorStatus": "none",
        }
    }
    source = {
        "kind": "conversation_catalog",
        "trade_policy": "catalog_v1",
        "catalog_lookup": "shop_db_v1",
        "uid": "self",
        "run_id": "run",
        "request_id": "request",
        "member_id": "member",
        "sku_id": "1",
        "expires_at": service.time.time() + 600,
        "profile_hash": service.input_fingerprint(profile),
        "composition_hash": service.composition_hash(current),
        "description_hash": service.description_hash(current),
    }
    token = service.encode_offer(source)
    run = SimpleNamespace(uid="self", id="run", request_id="request")
    binding = SimpleNamespace(member_id="member")
    monkeypatch.setattr(service, "require_shopping_member", AsyncMock(return_value=SimpleNamespace(profile=profile)))
    monkeypatch.setattr(service, "current_catalog", AsyncMock(side_effect=AssertionError("不得读取完整目录")))
    monkeypatch.setattr(service, "current_restriction_codes", AsyncMock(return_value={"花生": "peanut"}))
    fetch = AsyncMock(return_value=current)
    monkeypatch.setattr(service, "commerce_request", fetch)

    _, offers = await service.offers_for_answer(
        object(), run, binding, "[食材包:" + token + "]", publication=True, use_selection=False
    )
    assert len(offers) == 1 and offers[0]["available"] is True
    fetch.assert_awaited_once_with("GET", "/api/v1/integration/ai/catalog/skus/1")

    changed = deepcopy(current)
    changed["allergen_codes"] = ["peanut"]
    fetch.return_value = changed
    with pytest.raises(HealthVisionError, match="purchase_source_changed"):
        await service.offers_for_answer(
            object(), run, binding, "[食材包:" + token + "]", publication=True, use_selection=False
        )


async def test_direct_purchase_rechecks_sku_without_full_catalog(monkeypatch):
    """发布采购包时只回读选中 SKU，包装变化后拒绝发布。"""
    monkeypatch.setenv("HEALTH_COMMERCE_SOURCE_SECRET", "synthetic-conversation-source-secret-0123456789")
    current = sku(1)
    source = {
        "kind": "conversation_catalog",
        "catalog_lookup": "shop_db_v1",
        "uid": "self",
        "run_id": "run",
        "request_id": "request",
        "member_id": "member",
        "sku_id": "1",
        "catalog_version": "catalog-test-1",
        "composition_hash": service.composition_hash(current),
        "description_hash": service.description_hash(current),
    }
    token = service.encode_offer(source)
    monkeypatch.setattr(
        service,
        "read_conversation_purchase",
        AsyncMock(return_value={"offers": [{"offer_token": token, "available": True}]}),
    )
    monkeypatch.setattr(service, "current_catalog", AsyncMock(side_effect=AssertionError("不得读取完整目录")))
    requests = []

    async def request(method, path, payload=None, *, request_id=None):
        requests.append((method, path, payload, request_id))
        return current if method == "GET" else {"package_sn": "synthetic-package"}

    monkeypatch.setattr(service, "commerce_request", request)
    result = await service.publish_conversation_purchase("self", "request", token)
    assert result["package"]["package_sn"] == "synthetic-package"
    assert [method for method, _, _, _ in requests] == ["GET", "POST"]
    assert requests[0][1] == "/api/v1/integration/ai/catalog/skus/1"
    assert requests[1][2]["items"] == [{"sku_id": "1", "quantity": 1}]

    current = {**current, "net_content": {"value": "250", "unit": "g"}}
    requests.clear()
    with pytest.raises(HealthVisionError, match="purchase_source_changed"):
        await service.publish_conversation_purchase("self", "request", token)
    assert [method for method, _, _, _ in requests] == ["GET"]

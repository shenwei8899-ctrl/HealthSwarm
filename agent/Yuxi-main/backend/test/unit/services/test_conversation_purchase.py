"""真实目录协议、签名回执和本人边界的负向测试。"""

from copy import deepcopy
from types import SimpleNamespace

import pytest

from yuxi.services import conversation_purchase_service as purchase
from yuxi.services.health_vision_types import HealthVisionError


@pytest.fixture
def catalog(monkeypatch):
    """字段按商城 CatalogService 的实际公开契约构造。"""
    monkeypatch.setenv("HEALTH_COMMERCE_SOURCE_SECRET", "synthetic-conversation-source-secret-0123456789")
    return {
        "version": "catalog-1",
        "items": [
            {
                "sku_id": "31",
                "product_name": "青椒肉丝食材包",
                "price_cent": 2500,
                "net_content": {"value": "500.000", "unit": "g"},
                "available_quantity": 5,
                "sale_status": "available",
                "data_completeness": "complete",
                "allergen_codes": [],
                "ingredients": [
                    {
                        "ingredient_id": "11",
                        "ingredient_code": "pepper",
                        "name": "青椒",
                        "review_status": "approved",
                        "net_value": "500",
                        "net_unit": "g",
                        "convert_ratio": "0.8",
                        "loss_rate": "0.1",
                    }
                ],
            }
        ],
    }


def test_real_catalog_spec_and_edible_coverage(catalog):
    """规格来自嵌套 net_content，可食覆盖量不能把损耗前净重当需求。"""
    item = catalog["items"][0]
    assert purchase.public_offer(item)["spec"] == "500.000g"
    assert str(purchase.edible_amount(item["ingredients"][0])) == "360.00"
    assert purchase.package_available({}, item, catalog)
    changed = deepcopy(item)
    changed["net_content"]["value"] = "250.000"
    assert purchase.composition_hash(changed) != purchase.composition_hash(item)


@pytest.mark.parametrize(
    "change",
    [
        lambda item: item.update(available_quantity=0),
        lambda item: item.update(data_completeness="partial"),
        lambda item: item["ingredients"][0].update(review_status="pending"),
        lambda item: item["ingredients"][0].update(loss_rate="NaN"),
        lambda item: item["ingredients"][0].update(ingredient_code=""),
    ],
)
def test_unverifiable_packages_are_not_offered(catalog, change):
    """库存、审核映射与换算缺失都不能显示可购买。"""
    change(catalog["items"][0])
    assert not purchase.package_available({}, catalog["items"][0], catalog)


def test_known_or_unresolvable_restrictions_do_not_claim_safety(catalog):
    """匹配禁忌与无法解释的硬限制均停止推荐。"""
    item = catalog["items"][0]
    for restriction in ["青椒", "无法映射的过敏原"]:
        assert not purchase.package_available(
            {"dietary_details": {"allergyStatus": "set", "allergies": [restriction]}}, item, catalog
        )


def test_signed_receipt_cannot_be_forged_or_borrowed(catalog):
    """签名防改商品；有效凭据也不能跨账号、请求、Run 或成员。"""
    source = {
        "kind": "conversation_package",
        "uid": "self",
        "run_id": "run",
        "request_id": "request",
        "member_id": "member",
    }
    token = purchase.encode_offer(source)
    assert purchase.decode_offer(token) == source
    with pytest.raises(HealthVisionError):
        purchase.decode_offer(token[:-10] + "aaaaaaaaaa")
    for field in ["uid", "run_id", "request_id", "member_id"]:
        other = {**source, field: "other"}
        with pytest.raises(HealthVisionError):
            purchase.verify_offer_owner(
                other, SimpleNamespace(uid="self", id="run", request_id="request"), SimpleNamespace(member_id="member")
            )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "selection,empty_reason,expected",
    [
        ([{"sku_id": "not-queried", "reason": "未经查询"}], "", "catalog_selection_invalid"),
        ([{"sku_id": "31", "reason": ""}], "", "catalog_selection_invalid"),
        ([{"sku_id": "31", "reason": "已查到"}] * 2, "", "catalog_selection_invalid"),
        ([], "", "catalog_selection_invalid"),
    ],
)
async def test_selection_rejects_unqueried_or_unexplained_products(monkeypatch, selection, empty_reason, expected):
    """只验证真实选择入口的拒绝边界，不模拟选择算法。"""
    import json
    from contextlib import asynccontextmanager
    from unittest.mock import AsyncMock
    from yuxi.services import health_consultation_service as consultation

    @asynccontextmanager
    async def session():
        """本例没有持久写入，仓储只提供当前轮审计记录。"""
        yield object()

    monkeypatch.setattr(purchase.pg_manager, "get_async_session_context", session)
    monkeypatch.setattr(consultation, "require_consultation_attempt", AsyncMock())
    monkeypatch.setattr(consultation, "require_consultation", AsyncMock(return_value=(object(), None)))
    monkeypatch.setattr(
        purchase.HealthConsultationRepository,
        "require_attempt",
        AsyncMock(return_value=SimpleNamespace(id="run", input_payload={"health_processing": {}})),
    )
    monkeypatch.setattr(
        purchase.ConversationPurchaseRepository,
        "catalog_profile_payloads",
        AsyncMock(return_value=[json.dumps({"offers": [{"sku_id": "31", "reference": "real-query-reference"}]})]),
    )
    monkeypatch.setattr(purchase, "validate_catalog_profile_payload", AsyncMock())
    with pytest.raises(HealthVisionError, match=expected):
        await purchase.select_conversation_products(
            SimpleNamespace(uid="self", thread_id="thread"), selection, empty_reason
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("change", [None, "version", "profile"])
async def test_catalog_payload_and_history_recheck_current_confirmed_profile(monkeypatch, change):
    """直接经过真实校验器，旧工具正文不能绕过档案版本与内容失效。"""
    import json
    from unittest.mock import AsyncMock

    member = SimpleNamespace(
        id="self-member", confirmed_version=1, profile={"allergens": [], "activity_level": "light"}
    )
    payload = {"catalog_context_version": 1, "profile_context": purchase.dietary_profile_context(member)}
    if change == "version":
        member.confirmed_version = 2
    if change == "profile":
        member.profile = {**member.profile, "allergens": ["合成新过敏原"]}
    current_member = AsyncMock(return_value=member)
    monkeypatch.setattr(purchase, "require_shopping_member", current_member)
    monkeypatch.setattr(
        purchase.ConversationPurchaseRepository,
        "catalog_profile_payloads",
        AsyncMock(return_value=[json.dumps(payload)]),
    )
    session, binding = object(), object()
    if change is None:
        await purchase.validate_catalog_profile_payload(session, binding, payload, lock=True)
        await purchase.validate_catalog_profile_history(session, binding, lock=True)
        assert current_member.await_count == 2
        current_member.assert_awaited_with(session, binding, lock=True)
    else:
        with pytest.raises(HealthVisionError, match="profile_source_changed"):
            await purchase.validate_catalog_profile_payload(session, binding, payload, lock=True)
        with pytest.raises(HealthVisionError, match="profile_source_changed"):
            await purchase.validate_catalog_profile_history(session, binding, lock=True)

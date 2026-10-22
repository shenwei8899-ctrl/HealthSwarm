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

"""按商品保存的参考菜可以生成采购建议，缺口与既有事实保持独立。"""

from copy import deepcopy
from unittest.mock import AsyncMock

import pytest

from yuxi.services import meal_dish_service as service
from yuxi.services.daily_commerce_service import group_catalog_products
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.services.reference_meal_plan_service import reference_product, reference_product_group


def purchase_case():
    """米按质量凑包，盐用量未知，罗勒保持真实缺口。"""
    rice = {
        "product_id": "rice",
        "sku_id": "rice-250",
        "product_name": "大米",
        "sku_name": "250克",
        "net_content": {"value": "250", "unit": "g"},
        "price_cent": 400,
        "sale_status": "available",
        "available_quantity": 20,
        "ingredients": [],
        "product_description": "大米",
        "allergen_codes": [],
        "category_code": "grain",
    }
    salt = {
        **rice,
        "product_id": "salt",
        "sku_id": "salt-500",
        "product_name": "盐",
        "product_description": "盐",
        "sku_name": "500克",
        "price_cent": 200,
    }
    other = {**rice, "product_id": "other", "sku_id": "other", "product_name": "晚餐食材"}
    catalog = {"version": "synthetic", "items": [rice, salt, other]}
    products = group_catalog_products(catalog["items"])
    original = {"ingredients": ["大米300克", "Salt", "Basil", "~½ tablespoon water"]}
    source = {
        "members": [],
        "meals": [{"dishes": [original]}],
        "purchase_items": [],
        "product_matches": [
            reference_product_group(products[0], ["大米300克"]),
            reference_product_group(products[1], ["Salt"]),
            reference_product_group(products[2], ["晚餐食材100克"]),
        ],
        "purchase_gaps": [
            {"ingredient": "Basil", "reason": "needs_confirmation", "sku_id": None},
            {"ingredient": "~½ tablespoon water", "reason": "needs_confirmation", "sku_id": None},
        ],
    }
    return original, source, catalog


@pytest.mark.asyncio
async def test_product_matches_reach_purchase_and_gaps_remain_unmatched(monkeypatch):
    original, source, catalog = purchase_case()
    saved = deepcopy(source)
    monkeypatch.setattr(service, "read_origin", AsyncMock(return_value=(original, {}, [], source)))
    items, requirements, gaps = await service.purchase_items(
        None, "self", "family", [{"origin": {"source": {"kind": "reference"}}}], catalog
    )
    assert [(i["sku_id"], i["quantity"]) for i in items] == [("rice-250", 2), ("salt-500", 1)]
    assert requirements == []
    assert {g["ingredient"] for g in gaps} == {"Basil", "~½ tablespoon water"}
    assert all(g["purchase_mode"] == "self_purchase" and g["sku_id"] is None for g in gaps)
    assert source == saved


@pytest.mark.parametrize(
    "mutation,code",
    [
        ("sold_out", "dish_stock_missing"),
        ("off_sale", "dish_stock_missing"),
        ("removed", "dish_stock_missing"),
        ("renamed", "dish_product_changed"),
        ("description", "dish_product_changed"),
        ("restriction", "reference_restriction_conflict"),
    ],
)
def test_changed_or_conflicting_products_cannot_be_purchased(mutation, code):
    original, source, catalog = purchase_case()
    if mutation == "sold_out":
        catalog["items"][0]["available_quantity"] = 0
    if mutation == "off_sale":
        catalog["items"][0]["sale_status"] = "off_sale"
    if mutation == "removed":
        catalog["items"].pop(0)
    if mutation == "renamed":
        catalog["items"][0]["product_name"] = "其他商品"
    if mutation == "description":
        catalog["items"][0]["product_description"] = "资料已改变"
    if mutation == "restriction":
        source["members"] = [{"allergens": ["大米"]}]
    with pytest.raises(HealthVisionError, match=code):
        service.reference_product_packages(original, source, catalog)


def test_current_specs_and_prices_are_used_without_changing_saved_product():
    original, source, catalog = purchase_case()
    catalog["items"].append(
        {
            **catalog["items"][0],
            "sku_id": "rice-500",
            "sku_name": "500克",
            "net_content": {"value": "500", "unit": "g"},
            "price_cent": 600,
        }
    )
    chosen = service.reference_product_packages(original, source, catalog)
    assert chosen[0]["sku_id"] == "rice-500" and chosen[0]["quantity"] == 1
    assert chosen[0]["price_cent"] == 600


def test_known_mass_does_not_choose_cheaper_unconvertible_pack():
    original, source, catalog = purchase_case()
    catalog["items"].append(
        {
            **catalog["items"][0],
            "sku_id": "unknown-pack",
            "price_cent": 1,
            "net_content": {"value": "1", "unit": "piece"},
        }
    )
    chosen = service.reference_product_packages(original, source, catalog)
    assert chosen[0]["sku_id"] == "rice-250" and chosen[0]["quantity"] == 2
    catalog["items"][0]["net_content"] = None
    with pytest.raises(HealthVisionError, match="dish_stock_missing"):
        service.reference_product_packages(original, source, catalog)


@pytest.mark.asyncio
@pytest.mark.parametrize("mutation", ["missing", "duplicate", "gap_overlap"])
async def test_incomplete_or_overlapping_matches_still_fail(monkeypatch, mutation):
    original, source, catalog = purchase_case()
    if mutation == "missing":
        source["product_matches"].pop(0)
    if mutation == "duplicate":
        source["product_matches"].append(deepcopy(source["product_matches"][0]))
    if mutation == "gap_overlap":
        source["purchase_gaps"].append({"ingredient": "大米300克", "reason": "no_match"})
    monkeypatch.setattr(service, "read_origin", AsyncMock(return_value=(original, {}, [], source)))
    with pytest.raises(HealthVisionError, match="dish_ingredients_missing"):
        await service.purchase_items(None, "self", "family", [{"origin": {"source": {"kind": "reference"}}}], catalog)


@pytest.mark.asyncio
async def test_legacy_sku_snapshot_remains_supported(monkeypatch):
    original, source, catalog = purchase_case()
    source["product_matches"] = []
    source["purchase_items"] = [
        {**reference_product(catalog["items"][0], 2), "ingredient_refs": ["大米300克"]},
        {**reference_product(catalog["items"][1], 1), "ingredient_refs": ["Salt"]},
    ]
    monkeypatch.setattr(service, "read_origin", AsyncMock(return_value=(original, {}, [], source)))
    items, _, _ = await service.purchase_items(
        None, "self", "family", [{"origin": {"source": {"kind": "reference"}}}], catalog
    )
    assert [(i["sku_id"], i["quantity"]) for i in items] == [("rice-250", 2), ("salt-500", 1)]


@pytest.mark.asyncio
async def test_shared_product_is_scoped_per_dish_then_mass_is_merged(monkeypatch):
    original, source, catalog = purchase_case()
    source["meals"].append({"dishes": [deepcopy(original)]})
    monkeypatch.setattr(service, "read_origin", AsyncMock(return_value=(original, {}, [], source)))
    dishes = [{"origin": {"source": {"kind": "reference"}}}] * 2
    items, _, gaps = await service.purchase_items(None, "self", "family", dishes, catalog)
    assert [(i["sku_id"], i["quantity"]) for i in items] == [("rice-250", 3), ("salt-500", 2)]
    assert len(gaps) == 2

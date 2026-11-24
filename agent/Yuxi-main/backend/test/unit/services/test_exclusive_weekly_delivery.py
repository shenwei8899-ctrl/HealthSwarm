"""周配送建议验证逐项覆盖、包装取整和未知状态，不使用供应商真实数据。"""

from copy import deepcopy

from yuxi.services.exclusive_delivery_suggestions import suggest_deliveries
from yuxi.services.exclusive_plan_purchase import assemble_purchase
from test.unit.services.test_exclusive_plan_purchase import catalog, plan


def rule(days):
    """合成已确认规则，不能作为正式食材保鲜依据。"""
    return {"review_status": "approved", "max_days": days, "condition": "ambient", "version": "synthetic-v1", "source": "synthetic-test"}


def demand(day, food="大米", amount="100克"):
    """保留日期、餐次及原谱来源。"""
    return {"day_no": day, "food": food, "ingredient": food + amount, "recipe_name": "合成餐品", "file_id": "recipe", "meal_type": "lunch", "status": "matched"}


def test_bulk_food_arrives_once_while_fresh_food_is_split_without_duplicate_demands():
    days = plan()["days"]
    ingredients = [demand(n) for n in range(1, 8)] + [demand(n, "菠菜") for n in range(1, 8)]
    products = catalog()
    products["storage_rules"] = {"大米": rule(7), "菠菜": rule(3)}
    result = suggest_deliveries(ingredients, days, products, [])
    assert [batch["day_no"] for batch in result["batches"]] == [1, 4, 7]
    rice = [item for batch in result["batches"] for item in batch["items"] if item["food"] == "大米"]
    assert len(rice) == 1 and rice[0]["quantity_g"] == 700
    spinach = [item for batch in result["batches"] for item in batch["items"] if item["food"] == "菠菜"]
    assert [item["use_days"] for item in spinach] == [[1, 2, 3], [4, 5, 6], [7]]
    covered = [key for batch in result["batches"] for item in batch["items"] for key in item["demand_ids"]]
    assert len(covered) == len(set(covered)) == len(ingredients)
    assert sum(item["quantity_g"] for item in spinach) == 700
    assert result["shipping_fee_cent"] is None and result["payable_amount_cent"] is None


def test_batch_packaging_is_rounded_per_delivery_instead_of_reusing_weekly_pack_total():
    ingredients = [demand(1, amount="200克"), demand(7, amount="200克")]
    products = catalog()
    products["storage_rules"] = {"大米": rule(1)}
    result = suggest_deliveries(ingredients, plan()["days"], products, [])
    assert result["goods_subtotal_cent"] == 1000
    assert [batch["items"][0]["product"]["quantity"] for batch in result["batches"]] == [1, 1]
    products["storage_rules"]["大米"] = rule(7)
    once = suggest_deliveries(ingredients, plan()["days"], products, [])
    assert once["goods_subtotal_cent"] == 500


def test_missing_rules_and_unknown_amounts_use_original_daily_arrangement():
    products = catalog()
    products["storage_rules"] = {"大米": {**rule(7), "review_status": "draft"}}
    result = suggest_deliveries([demand(1), demand(2, amount="适量")], plan()["days"], products, [])
    assert result["pending"] == []
    assert [batch["day_no"] for batch in result["batches"]] == [1, 2]
    assert result["batches"][1]["items"][0]["quantity_g"] is None
    assert all(item["storage_max_days"] is None for batch in result["batches"] for item in batch["items"])


def test_rules_and_menu_changes_invalidate_the_purchase_scope():
    products = catalog()
    products["storage_rules"] = {"大米": rule(7)}
    first = assemble_purchase(plan(), products, [])
    changed = deepcopy(products)
    changed["storage_rules"]["大米"]["version"] = "synthetic-v2"
    assert assemble_purchase(plan(), changed, [])["scope_hash"] != first["scope_hash"]
    changed_plan = plan()
    changed_plan["days"][0]["plan_date"] = "2026-12-01"
    assert assemble_purchase(changed_plan, products, [])["scope_hash"] != first["scope_hash"]


def test_stock_is_checked_across_batches_instead_of_promising_repeated_single_batch_stock():
    products = catalog(available_quantity=1)
    products["storage_rules"] = {"大米": rule(1)}
    result = suggest_deliveries([demand(1), demand(7)], plan()["days"], products, [])
    assert result["stock_issues"] == ["rice"]
    assert result["goods_estimate_complete"] is False


def test_durable_food_first_used_late_still_joins_the_first_delivery():
    products = catalog()
    products["storage_rules"] = {"大米": rule(7)}
    result = suggest_deliveries([demand(6)], plan()["days"], products, [])
    assert result["batches"][0]["day_no"] == 1
    assert result["batches"][0]["items"][0]["use_days"] == [6]


def test_live_catalog_path_preserves_only_consistent_approved_storage_rules():
    from yuxi.services.exclusive_delivery_suggestions import catalog_storage_rules
    item = catalog()["items"][0]
    assert catalog_storage_rules([item]) == {}
    confirmed = {**item, "storage_rule": rule(7)}
    assert catalog_storage_rules([confirmed]) == {"大米": rule(7)}
    assert catalog_storage_rules([confirmed, item]) == {}
    other = {**confirmed, "storage_rule": rule(2)}
    assert catalog_storage_rules([confirmed, other]) == {}

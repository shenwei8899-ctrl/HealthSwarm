"""按原谱使用日和已确认储存规则生成建议，不拥有供应商预约或交易状态。"""

from collections import defaultdict
from decimal import Decimal

from yuxi.services.health_nutrition_service import input_fingerprint


def suggest_deliveries(ingredients, days, catalog, restrictions, *, purchase_items=None):
    """用量不明仍保留可调整包装；无储存规则沿用按使用日配送建议。"""
    from yuxi.services.exclusive_reference_plan import explicit_grams, price_ingredient_group
    from yuxi.services.reference_recipe_matching import ReferenceProductIndex

    dates = {day["day_no"]: day.get("plan_date") for day in days}
    rules = catalog.get("storage_rules") or {}
    groups, demands, self_prepare = defaultdict(list), [], []
    purchasable = {item["food"]: item for item in purchase_items} if purchase_items is not None else None
    for position, ingredient in enumerate(ingredients):
        if ingredient["status"] == "self_prepare":
            continue
        demand = {
            "id": str(position),
            "day_no": ingredient["day_no"],
            "use_date": dates[ingredient["day_no"]],
            "meal_type": ingredient["meal_type"],
            "recipe_name": ingredient["recipe_name"],
            "file_id": ingredient["file_id"],
            "ingredient": ingredient["ingredient"],
            "food": ingredient.get("food"),
            "quantity_g": None,
            "quantity_basis": "original_recipe",
        }
        grams = explicit_grams(ingredient["ingredient"])
        if grams is not None:
            demand["quantity_g"] = float(grams)
        demands.append(demand)
        if purchasable is not None and demand["food"] not in purchasable:
            self_prepare.append(demand)
            continue
        rule = rules.get(demand["food"]) if isinstance(rules, dict) else None
        groups[demand["food"] or demand["ingredient"]].append((demand, rule if approved_storage_rule(rule) else None))

    batches = {}
    index = ReferenceProductIndex(catalog.get("items", []))
    for food, entries in sorted(groups.items()):
        entries.sort(key=lambda entry: (entry[0]["day_no"], entry[0]["id"]))
        # 同一食材从首次使用日开始覆盖已确认的保存窗口，不按整餐切割。
        while entries:
            first, rule = entries[0]
            # 没有储存规则不阻断采购，沿用旧排期默认的按使用日安排。
            width = rule["max_days"] if rule else 1
            delivery_day = 1 if width >= len(days) else first["day_no"]
            end_day = delivery_day + width - 1
            allocated = [entry[0] for entry in entries if entry[0]["day_no"] <= end_day]
            entries = [entry for entry in entries if entry[0]["day_no"] > end_day]
            known = all(entry["quantity_g"] is not None for entry in allocated)
            grams = sum(
                (Decimal(str(entry["quantity_g"])) for entry in allocated if entry["quantity_g"] is not None),
                Decimal(0),
            )
            matched, _reason, _detail = price_ingredient_group(
                {"food": food, "rows": [], "known": known, "grams": grams},
                index,
                catalog,
                restrictions,
            )
            if matched is None and purchasable is not None and food in purchasable:
                original = purchasable[food]
                matched = {
                    "sku_id": original["sku_id"],
                    "quantity": 1,
                    "quantity_confirmed": False,
                    "subtotal_cent": None,
                }
            batch = batches.setdefault(
                delivery_day,
                {
                    "day_no": delivery_day,
                    "suggested_date": dates[delivery_day],
                    "timing": "用餐前，具体送达时间待确认",
                    "items": [],
                },
            )
            batch["items"].append(
                {
                    "food": food,
                    "quantity_g": float(grams) if known else None,
                    "quantity_confirmed": known,
                    "quantity_basis": "original_recipe",
                    "use_days": sorted({entry["day_no"] for entry in allocated}),
                    "demand_ids": [entry["id"] for entry in allocated],
                    "storage_condition": rule["condition"] if rule else None,
                    "storage_max_days": rule["max_days"] if rule else None,
                    "storage_rule_version": rule["version"] if rule else None,
                    "storage_rule_source": rule["source"] if rule else None,
                    "schedule_basis": "storage_rule" if rule else "daily",
                    "product": matched,
                }
            )

    ordered = [
        dict(batch, batch_no=position + 1) for position, batch in enumerate(v for _, v in sorted(batches.items()))
    ]
    products = [item["product"] for batch in ordered for item in batch["items"]]
    known_products = [item for item in products if item and type(item.get("subtotal_cent")) is int]
    subtotal = sum(item["subtotal_cent"] for item in known_products) if known_products else None
    sku_totals = defaultdict(int)
    for product in products:
        if product:
            sku_totals[product["sku_id"]] += product["quantity"]
    stock = {str(item["sku_id"]): item.get("available_quantity") for item in catalog.get("items", [])}
    stock_issues = [
        sid for sid, quantity in sku_totals.items() if type(stock.get(sid)) is not int or stock[sid] < quantity
    ]
    complete = bool(products) and all(products) and len(known_products) == len(products) and not stock_issues
    result = {
        "status": "suggested",
        "batches": ordered,
        "pending": [],
        "self_prepare": self_prepare,
        "demands": demands,
        "goods_subtotal_cent": subtotal,
        "goods_estimate_complete": bool(complete),
        "shipping_fee_cent": None,
        "payable_amount_cent": None,
        "supplier_status": "pending",
        "stock_issues": stock_issues,
        "notice": "按原谱参考用量建议分趟，家庭实际用量与送达时间待确认；配送费待定，尚未预约配送。",
    }
    result["version"] = input_fingerprint(result)
    return result


def approved_storage_rule(rule):
    """仅消费带审核状态、条件和来源版本的规则，不推断商品保鲜期。"""
    return (
        isinstance(rule, dict)
        and rule.get("review_status") == "approved"
        and type(rule.get("max_days")) is int
        and rule["max_days"] > 0
        and rule.get("condition") in {"ambient", "refrigerated", "frozen"}
        and isinstance(rule.get("version"), str)
        and bool(rule["version"].strip())
        and isinstance(rule.get("source"), str)
        and bool(rule["source"].strip())
    )


def catalog_storage_rules(items):
    """从目录商品的已确认规则取一致口径，缺失或冲突时继续待核对。"""
    from yuxi.services.reference_recipe_matching import product_foods

    candidates = defaultdict(list)
    for item in items:
        foods = product_foods(item)
        if len(foods) == 1:
            candidates[next(iter(foods))].append(item.get("storage_rule"))
    return {
        food: rules[0]
        for food, rules in candidates.items()
        if all(approved_storage_rule(rule) and rule == rules[0] for rule in rules)
    }

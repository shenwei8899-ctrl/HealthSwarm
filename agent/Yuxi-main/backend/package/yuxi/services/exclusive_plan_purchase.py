"""整份专属计划采购：菜单来源复核独立于商品资格，缺口不冒充零价。"""

import time
from datetime import date, datetime, UTC
from decimal import Decimal
from uuid import NAMESPACE_URL, uuid5

from yuxi.services.health_nutrition_service import input_fingerprint
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.services.exclusive_plan_types import EXCLUSIVE_PLAN_DAYS
from yuxi.services.exclusive_delivery_suggestions import suggest_deliveries


def plan_meals(plan):
    """汇总全部 7 天原谱，保留重复出现的实际食材用量。"""
    if [day.get("day_no") for day in plan.get("days", [])] != list(range(1, EXCLUSIVE_PLAN_DAYS + 1)):
        raise HealthVisionError("exclusive_purchase_incomplete", "整周7天计划尚未就绪，请重新读取", 409)
    return [
        {
            "day_no": day["day_no"],
            "plan_date": day.get("plan_date"),
            "meal_type": dish["meal_type"],
            "dishes": [
                {
                    "name": dish["recipe_name"],
                    "file_id": dish["source"]["file_id"],
                    "ingredients": dish["ingredients"],
                }
            ],
        }
        for day in plan["days"]
        for dish in day["meals"]
        if not dish.get("roster_preserved")
    ]


def assemble_purchase(plan, catalog, restrictions):
    """按食材身份合并包装；未知家庭用量只给可手调的初始包装数。"""
    from yuxi.services.exclusive_reference_plan import (
        reference_procurement,
        price_ingredient_group,
        reference_price_summary,
    )
    from yuxi.services.reference_recipe_matching import ReferenceProductIndex, product_foods
    from yuxi.services.reference_meal_plan_service import (
        reference_product_composition,
        reference_restriction_conflict,
        product_facts,
    )

    meals = plan_meals(plan)
    index = ReferenceProductIndex(catalog["items"])
    procurement = reference_procurement(meals, catalog, restrictions)
    groups, gaps, items = {}, {}, {}
    for row in procurement["ingredients"]:
        if row["status"] == "self_prepare":
            continue
        key = row["food"] or row["ingredient"]
        group = groups.setdefault(key, {"food": row["food"], "rows": [], "known": True, "grams": Decimal(0)})
        group["rows"].append(row)
        from yuxi.services.exclusive_reference_plan import explicit_grams

        grams = explicit_grams(row["ingredient"])
        group["known"] &= grams is not None
        group["grams"] += grams or Decimal(0)
    for key, group in groups.items():
        matched, reason, detail = price_ingredient_group(group, index, catalog, restrictions)
        candidates = [
            sku for product in index.by_food.get(group["food"], []) for sku in (product.get("skus") or [product])
        ]
        eligible = [
            sku
            for sku in candidates
            if sku.get("sale_status") == "available"
            and type(sku.get("available_quantity")) is int
            and sku["available_quantity"] > 0
            and type(sku.get("price_cent")) is int
            and sku["price_cent"] >= 0
            and product_foods(sku) == {group["food"]}
            and not reference_restriction_conflict(reference_product_composition(sku), restrictions)
        ]
        sku = next((sku for sku in eligible if matched and str(sku["sku_id"]) == matched["sku_id"]), None)
        # 无法核算用量仍可由用户按实际需要选择包装，不伪称已覆盖7天份量。
        if sku is None and eligible:
            sku = min(eligible, key=lambda value: (value["price_cent"], str(value["sku_id"])))
        if sku is None:
            gaps[key] = {
                "ingredient": key,
                "label": key,
                "reason": reason,
                "detail": detail,
                "price_cent": None,
                "purchase_mode": "self_prepare_or_confirm",
            }
            continue
        sid = str(sku["sku_id"])
        quantity = matched["quantity"] if matched and sid == matched["sku_id"] else 1
        if sid in items:
            raise HealthVisionError("exclusive_purchase_mapping", "同一包装对应多种食材，请重新核对", 409)
        items[sid] = {
            "sku_id": sid,
            "food": group["food"],
            "quantity": quantity,
            "sku": sku,
            "quantity_confirmed": bool(matched),
            "facts_hash": input_fingerprint(product_facts(sku)),
        }
    delivery = suggest_deliveries(
        procurement["ingredients"], plan["days"], catalog, restrictions, purchase_items=list(items.values())
    )
    fingerprint = input_fingerprint(
        {
            "delivery_version": delivery["version"],
            "group_id": plan["group_id"],
            "tier": plan["tier_code"],
            "plan": meals,
            "items": [{key: item[key] for key in ("sku_id", "quantity", "facts_hash")} for item in items.values()],
        }
    )
    return {
        "group_id": plan["group_id"],
        "tier_code": plan["tier_code"],
        "scope_hash": fingerprint,
        "days": EXCLUSIVE_PLAN_DAYS,
        "period_days": EXCLUSIVE_PLAN_DAYS,
        "delivery_suggestions": delivery,
        "catalog_version": catalog.get("version"),
        "available": bool(items),
        "items": list(items.values()),
        "gaps": list(gaps.values()),
        "pricing": reference_price_summary(procurement, EXCLUSIVE_PLAN_DAYS, len(plan.get("members", []))),
        "notice": (
            "采购范围为整周7天计划；包装数量可调整，不代表已核定家庭7天用量。配送费待定。未匹配食材需自行准备。"
        ),
    }


async def read_purchase(uid, family_id, group_id, tier):
    """先重新核对账号、家庭、授权、档案和原谱，再读取当前商品。"""
    from yuxi.services.exclusive_plan_service import read_exclusive_plan
    from yuxi.services.exclusive_reference_plan import optional_exclusive_catalog, exclusive_reference_context
    from yuxi.services.reference_meal_plan_service import reference_member_restrictions
    from yuxi.storage.postgres.manager import pg_manager

    plan = await read_exclusive_plan(uid, family_id, group_id, tier=tier)
    async with pg_manager.get_async_session_context() as session:
        context = await exclusive_reference_context(
            session,
            uid,
            family_id,
            day=date.fromisoformat(plan["days"][0]["plan_date"]) if plan["days"][0].get("plan_date") else None,
            start_date=plan["days"][0].get("plan_date"),
            load_documents=False,
        )
        restrictions = reference_member_restrictions(context["current"]["members"]) + context["current"].get(
            "memory_restrictions", []
        )
    catalog = await optional_exclusive_catalog()
    return {
        **assemble_purchase(plan, catalog, restrictions),
        "tier_name": plan["tier_name"],
        "members": plan["members"],
    }


async def publish_purchase(uid, family_id, group_id, tier, scope_hash):
    """显式购买才幂等发布签名商品包，之后复用今日餐单的购物车结算。"""
    from yuxi.services.daily_commerce_service import commerce_request
    from yuxi.services.health_commerce_service import sign_commerce_source

    result = await read_purchase(uid, family_id, group_id, tier)
    if result["scope_hash"] != scope_hash:
        raise HealthVisionError("exclusive_purchase_changed", "计划或商品已变化，请重新核对采购", 409)
    if not result["items"]:
        raise HealthVisionError("exclusive_purchase_unavailable", "暂无可购买商品，未匹配食材可自行准备", 409)
    # 十分钟窗口限定商品包寿命，重复提交沿用同一来源与任务号。
    expiry = (int(time.time()) // 600 + 2) * 600
    source = {
        "kind": "exclusive_purchase",
        "uid": uid,
        "family_id": family_id,
        "group_id": group_id,
        "tier_code": tier,
        "scope_hash": scope_hash,
        "expires_at": expiry,
        "catalog_version": result["catalog_version"],
        "delivery_requirements": purchase_delivery_requirements(result),
    }
    source["menu_version_ref"] = "exclusive-purchase:" + input_fingerprint(source)
    task = str(uuid5(NAMESPACE_URL, source["menu_version_ref"]))
    payload = {
        "agent_task_id": task,
        "family_ref": "exclusive-purchase:" + family_id,
        "user_ref": "uid:" + uid,
        "menu_version_ref": source["menu_version_ref"],
        "catalog_version": result["catalog_version"],
        "ingredient_requirements": [],
        "items": [{"sku_id": i["sku_id"], "quantity": i["quantity"]} for i in result["items"]],
        "expires_at": datetime.fromtimestamp(expiry, UTC).isoformat(),
        "nutrition_validation": {
            "status": "reference_only",
            "validation_id": task,
            "rules_version": "",
            "summary": "整周7天计划食材采购，家庭用量待确认",
        },
        "agent_source_proof": sign_commerce_source(source),
    }
    result["package"] = await commerce_request(
        "POST", "/api/v1/integration/ai/recommendation-packages", payload, request_id=task
    )
    return result


async def validate_purchase_source(source):
    """结算回源时复核整份计划和商品身份，不使用客户端上传的菜单。"""
    if type(source.get("expires_at")) is not int or source["expires_at"] <= time.time():
        raise HealthVisionError("source_invalidated", "采购已过期，请重新打开计划购买", 410)
    result = await read_purchase(source["uid"], source["family_id"], source["group_id"], source["tier_code"])
    if result["scope_hash"] != source["scope_hash"] or not result["items"]:
        raise HealthVisionError("source_invalidated", "计划依据或商品已变化，请重新采购", 410)
    if "delivery_requirements" in source and source["delivery_requirements"] != purchase_delivery_requirements(result):
        raise HealthVisionError("source_invalidated", "配送依据已变化，请重新采购", 410)
    return {
        "available": True,
        "selection_mode": "reference",
        "items": [{"sku_id": item["sku_id"], "quantity": item["quantity"]} for item in result["items"]],
    }


def purchase_delivery_requirements(purchase):
    """仅向商城提供 SKU 使用日及已审核储存依据，不传成员健康或完整菜谱。"""
    from yuxi.services.exclusive_delivery_suggestions import approved_storage_rule

    suggestions = purchase["delivery_suggestions"]
    result = []
    for item in purchase["items"]:
        uses = [demand for demand in suggestions["demands"] if demand["food"] == item["food"]]
        entries = [row for batch in suggestions["batches"] for row in batch["items"] if row["food"] == item["food"]]
        first = entries[0] if entries else {}
        rule = {
            "review_status": "approved",
            "condition": first.get("storage_condition"),
            "max_days": first.get("storage_max_days"),
            "version": first.get("storage_rule_version"),
            "source": first.get("storage_rule_source"),
        }
        sku_rule = item["sku"].get("storage_rule")
        if approved_storage_rule(sku_rule):
            rule = sku_rule
        known = all(use["quantity_g"] is not None and use["quantity_g"] > 0 for use in uses)
        result.append(
            {
                "sku_id": item["sku_id"],
                "food": item["food"],
                "storage_rule": rule if approved_storage_rule(rule) else None,
                "uses": [{"day_no": use["day_no"], "weight": use["quantity_g"] if known else 1} for use in uses],
            }
        )
    return {"version": 1, "period_days": EXCLUSIVE_PLAN_DAYS, "items": result}

"""整份专属计划采购：菜单来源复核独立于商品资格，缺口不冒充零价。"""

import time
from datetime import UTC, datetime
from decimal import Decimal
from uuid import NAMESPACE_URL, uuid5

from yuxi.services.health_nutrition_service import input_fingerprint
from yuxi.services.health_vision_types import HealthVisionError


def plan_meals(plan):
    """汇总全部 21 天原谱，保留重复出现的实际食材用量。"""
    if [day.get("day_no") for day in plan.get("days", [])] != list(range(1, 22)):
        raise HealthVisionError("exclusive_purchase_incomplete", "整份21天计划尚未就绪，请重新读取", 409)
    return [
        {
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
    ]


def assemble_purchase(plan, catalog, restrictions):
    """按食材身份合并包装；未知家庭用量只给可手调的初始包装数。"""
    from yuxi.services.exclusive_reference_plan import reference_procurement, price_ingredient_group
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
        # 无法核算用量仍可由用户按实际需要选择包装，不伪称已覆盖21天份量。
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
            "quantity": quantity,
            "sku": sku,
            "quantity_confirmed": bool(matched),
            "facts_hash": input_fingerprint(product_facts(sku)),
        }
    fingerprint = input_fingerprint(
        {
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
        "days": 21,
        "catalog_version": catalog.get("version"),
        "available": bool(items),
        "items": list(items.values()),
        "gaps": list(gaps.values()),
        "notice": "采购范围为整份21天计划；包装数量可调整，不代表已核定家庭21天用量。未匹配食材需自行准备。",
    }


async def read_purchase(uid, family_id, group_id, tier):
    """先重新核对账号、家庭、授权、档案和原谱，再读取当前商品。"""
    from yuxi.services.exclusive_plan_service import read_exclusive_plan
    from yuxi.services.exclusive_reference_plan import optional_exclusive_catalog, exclusive_reference_context
    from yuxi.services.reference_meal_plan_service import reference_member_restrictions
    from yuxi.storage.postgres.manager import pg_manager

    plan = await read_exclusive_plan(uid, family_id, group_id, tier=tier)
    async with pg_manager.get_async_session_context() as session:
        context = await exclusive_reference_context(session, uid, family_id)
        restrictions = reference_member_restrictions(context["current"]["members"]) + context["current"].get(
            "memory_restrictions", []
        )
    catalog = await optional_exclusive_catalog()
    return assemble_purchase(plan, catalog, restrictions)


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
            "summary": "整份21天计划食材采购，家庭用量待确认",
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
    return {
        "available": True,
        "selection_mode": "reference",
        "items": [{"sku_id": item["sku_id"], "quantity": item["quantity"]} for item in result["items"]],
    }

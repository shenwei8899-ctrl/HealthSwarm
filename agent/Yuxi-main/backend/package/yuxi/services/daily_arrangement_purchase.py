"""今日采购先合并所选餐次的食材，再按商城整包装匹配。"""

from decimal import Decimal
from uuid import NAMESPACE_URL, uuid5

from yuxi.repositories.daily_arrangement_repository import DailyArrangementRepository
from yuxi.services.daily_arrangement_service import authorize_sources, publish_daily_purchase, read_daily_arrangement
from yuxi.services.daily_commerce_service import (
    current_catalog,
    match_requirements,
    packages_in_stock,
    refresh_purchase_items,
)
from yuxi.services.health_commerce_service import sign_commerce_source
from yuxi.services.health_nutrition_service import input_fingerprint
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.storage.postgres.manager import pg_manager


async def read_daily_summary(uid, fid, day, arrangement_id, version, meal_types):
    """只读汇总所选餐次，不能将各餐已经取整的包装相加。"""
    if len(set(meal_types)) != len(meal_types):
        raise HealthVisionError("duplicate_meals", "采购餐次不能重复", 422)
    snapshot = await read_daily_arrangement(uid, fid, day)
    if snapshot.get("status") != "ready" or snapshot["id"] != arrangement_id or snapshot["version"] != version:
        raise HealthVisionError("daily_version_changed", "今日安排已更新，请返回重新读取", 409)
    meals = [meal for meal in snapshot["meals"] if meal["type"] in meal_types]
    if len(meals) != len(meal_types):
        raise HealthVisionError("daily_purchase_unavailable", "所选餐次尚未保存", 409)
    async with pg_manager.get_async_session_context() as db:
        _, row = await DailyArrangementRepository(db, uid, fid).context(day)
        if row is None or row.version != version:
            raise HealthVisionError("daily_version_changed", "今日安排已更新，请返回重新读取", 409)
        payloads = row.selection.get("purchase_payloads", {})
        scope = "daily:" + ",".join(sorted(meal_types))
        inflight_payload = payloads.get(scope, {})
        pending = bool(inflight_payload) and row.selection.get("purchase_inflight", {}).get(scope) == row.selection.get(
            "purchase_attempts", {}
        ).get(scope, 0)
        published = (
            row.selection.get("daily_purchases", {})
            .get("daily:" + ",".join(sorted(meal_types)), {})
            .get("purchase", {})
        )
    requirements = {}
    for meal in meals:
        original = meal["purchase"].get("ingredient_requirements") or payloads.get(meal["type"], {}).get(
            "ingredient_requirements"
        )
        if not original:
            raise HealthVisionError("daily_purchase_unavailable", "已保存餐次缺少食材来源，请重新安排", 409)
        for item in original:
            key = (item.get("ingredient_code") or item["ingredient_id"], item["required_unit"], item.get("food_id"))
            if (
                key in requirements
                and item.get("sku_id")
                and any(
                    requirements[key].get(field) != item.get(field) for field in ("merchant_snapshot", "source_ref")
                )
            ):
                raise HealthVisionError("sku_binding_changed", "不同餐次商品来源不一致，请重新核对", 409)
            if key not in requirements:
                requirements[key] = {**item, "required_value": Decimal(0)}
            requirements[key]["required_value"] += Decimal(item["required_value"])
    merged = [{**item, "required_value": str(item["required_value"])} for item in requirements.values()]
    catalog = await current_catalog()
    items = match_requirements(merged, catalog)
    pending = pending and not published.get("package_sn")
    if published.get("package_sn") or pending:
        saved_items = published.get("items", []) + [item for meal in meals for item in meal["purchase"]["items"]]
        items = await refresh_purchase_items(
            (published if published.get("package_sn") else inflight_payload)["items"], catalog, saved_items
        )
    available = bool(items) and packages_in_stock([{"items": items, "ingredient_requirements": merged}], catalog)
    return {
        "arrangement_id": arrangement_id,
        "version": version,
        "purchase": {
            "status": "matched",
            "catalog_version": catalog["version"],
            "ingredient_requirements": merged,
            "items": items or [],
            "available": available,
            "confirmation_pending": pending,
            "message": "上次采购结果尚未确认，请继续核对原结果。"
            if pending
            else ""
            if available
            else "所选餐次部分食材暂不可售，请调整餐次或稍后重试。",
        },
    }


async def publish_daily_summary(uid, fid, day, arrangement_id, version, meal_types):
    """明确采购时保存汇总来源，网络重试重放同一份采购请求。"""
    scope = "daily:" + ",".join(sorted(meal_types))
    preview = await read_daily_summary(uid, fid, day, arrangement_id, version, meal_types)
    if not preview["purchase"]["available"] and not preview["purchase"].get("confirmation_pending"):
        raise HealthVisionError("daily_purchase_unavailable", preview["purchase"]["message"], 409)
    async with pg_manager.get_async_session_context() as db:
        _, row = await DailyArrangementRepository(db, uid, fid).context(day, lock=True)
        if row is None or row.id != arrangement_id or row.version != version or row.status != "ready":
            raise HealthVisionError("daily_version_changed", "今日安排已更新，请返回重新读取", 409)
        await authorize_sources(db, uid, row)
        payloads = dict(row.selection.get("purchase_payloads", {}))
        if scope not in payloads:
            meals = [meal for meal in row.snapshot["meals"] if meal["type"] in meal_types]
            originals = [payloads[meal["type"]] for meal in meals]
            payloads[scope] = {
                **originals[0],
                "agent_task_id": str(uuid5(NAMESPACE_URL, f"daily-summary:{arrangement_id}:{version}:{scope}")),
                "catalog_version": preview["purchase"]["catalog_version"],
                "ingredient_requirements": preview["purchase"]["ingredient_requirements"],
                "items": [
                    {"sku_id": item["sku_id"], "quantity": item["quantity"]} for item in preview["purchase"]["items"]
                ],
                "recipes": [recipe for original in originals for recipe in original["recipes"]],
                "agent_source_proof": sign_commerce_source(
                    {
                        "kind": "daily_arrangement",
                        "uid": uid,
                        "family_id": fid,
                        "date": day.isoformat(),
                        "arrangement_id": arrangement_id,
                        "meals": [
                            {
                                "meal": meal["type"],
                                "meal_hash": input_fingerprint(
                                    {key: meal[key] for key in ("type", "members", "dishes", "memberNotes")}
                                ),
                            }
                            for meal in meals
                        ],
                    }
                ),
            }
            purchases = {**row.selection.get("daily_purchases", {}), scope: {"purchase": preview["purchase"]}}
            row.selection = {**row.selection, "purchase_payloads": payloads, "daily_purchases": purchases}
    return await publish_daily_purchase(uid, fid, day, scope, arrangement_id, version)

"""调用既有商城签名接口，按版本缓存完整目录并幂等保存推荐版本。"""

import asyncio
from copy import deepcopy
import hashlib
import hmac
import json
import os
import time
from decimal import Decimal, InvalidOperation, ROUND_CEILING
from urllib.parse import quote, urlencode, urlsplit
from uuid import uuid4

import httpx

from yuxi.services.health_vision_types import HealthVisionError
from yuxi.services.commerce_sku_selection import direct_sku_matches, match_direct


_CATALOG_PROBE_TTL_SECONDS = 30.0
_catalog_snapshot: dict | None = None
_catalog_last_probe = 0.0
_catalog_refresh_lock = asyncio.Lock()


async def commerce_request(method, path, payload=None, *, request_id=None):
    """密钥只从后端环境读取；同一业务重试使用新nonce和原幂等键。"""
    origin = (os.environ.get("HEALTH_COMMERCE_URL") or os.environ.get("HEALTH_COMMERCE_API_URL", "")).rstrip("/")
    parsed = urlsplit(origin)
    client_id = os.environ.get("HEALTH_COMMERCE_CLIENT_ID", "")
    secret = os.environ.get("HEALTH_COMMERCE_CLIENT_SECRET", "")
    if (
        not client_id
        or not secret
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or not parsed.hostname
        or parsed.scheme != "https"
        and not (
            parsed.scheme == "http"
            and (
                parsed.hostname in {"127.0.0.1", "localhost"}
                or parsed.hostname == "host.docker.internal"
                and os.environ.get("HEALTH_COMMERCE_ALLOW_DOCKER_HOST") == "1"
                or os.environ.get("HEALTH_COMMERCE_ALLOW_INTERNAL_HTTP") == "1"
            )
        )
    ):
        raise HealthVisionError("commerce_not_configured", "食材服务尚未配置完成，系统暂不能生成可采购安排", 503)
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")) if payload is not None else ""
    timestamp, nonce = str(int(time.time())), uuid4().hex
    canonical = "\n".join((method, urlsplit(path).path, timestamp, nonce, hashlib.sha256(body.encode()).hexdigest()))
    headers = {
        "X-Client-Id": client_id,
        "X-Timestamp": timestamp,
        "X-Nonce": nonce,
        "X-Signature": hmac.new(secret.encode(), canonical.encode(), hashlib.sha256).hexdigest(),
        "Content-Type": "application/json",
    }
    if request_id:
        headers["Idempotency-Key"] = request_id
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=False) as client:
            response = await client.request(method, origin + path, content=body.encode(), headers=headers)
        result = response.json()
    except (httpx.HTTPError, ValueError):
        raise HealthVisionError("commerce_unavailable", "食材服务暂时无法核对，正在保留原安排请求", 503) from None
    if response.status_code >= 400 or result.get("code") != 0:
        raise HealthVisionError("commerce_unavailable", "食材匹配或库存核对尚未完成，请稍后重试", 503)
    return result["data"]


def reset_catalog_cache():
    """清空进程内目录快照；供进程生命周期和确定性测试使用。"""
    global _catalog_snapshot, _catalog_last_probe, _catalog_refresh_lock
    _catalog_snapshot = None
    _catalog_last_probe = 0.0
    _catalog_refresh_lock = asyncio.Lock()


def _filtered_catalog(snapshot, category_codes):
    result = deepcopy(snapshot)
    if category_codes is not None:
        selected = set(category_codes)
        result["items"] = [item for item in result["items"] if item.get("category_code") in selected]
    return result


async def _load_full_catalog(expected_version):
    """完整分页只在版本变化时执行；跨页变化时从第一页重读。"""
    for _ in range(2):
        items, cursor, seen, version = [], "", set(), None
        while True:
            params = {"limit": 200, "cursor": cursor, "available_only": 0}
            page = await commerce_request(
                "GET", "/api/v1/integration/ai/catalog/products?" + urlencode(params, doseq=True)
            )
            if version is not None and version != page["catalog_version"]:
                break
            version = page["catalog_version"]
            items.extend(page["items"])
            if not page.get("has_more"):
                if expected_version and version != expected_version:
                    expected_version = version
                    break
                return {"items": items, "version": version}
            cursor = page.get("next_cursor")
            if not cursor or cursor in seen:
                raise HealthVisionError("catalog_invalid", "食材目录分页暂时无法核对", 503)
            seen.add(cursor)
    raise HealthVisionError("catalog_changed", "食材目录正在更新，请稍后重试", 503)


async def current_catalog(category_codes=None):
    """短周期探测版本；版本未变复用全量快照并在内存按分类过滤。"""
    global _catalog_snapshot, _catalog_last_probe
    if category_codes is not None and (
        not isinstance(category_codes, list)
        or not 1 <= len(category_codes) <= 4
        or any(not isinstance(code, str) or not code or len(code) > 50 for code in category_codes)
    ):
        raise HealthVisionError("catalog_category_invalid", "商品分类选择无效", 422)
    now = time.monotonic()
    if _catalog_snapshot is not None and now - _catalog_last_probe < _CATALOG_PROBE_TTL_SECONDS:
        return _filtered_catalog(_catalog_snapshot, category_codes)
    async with _catalog_refresh_lock:
        now = time.monotonic()
        if _catalog_snapshot is not None and now - _catalog_last_probe < _CATALOG_PROBE_TTL_SECONDS:
            return _filtered_catalog(_catalog_snapshot, category_codes)
        summary = await commerce_request("GET", "/api/v1/integration/ai/catalog/version")
        version = summary.get("catalog_version")
        if not isinstance(version, str) or not version:
            raise HealthVisionError("catalog_invalid", "商城目录版本无法核对", 503)
        if _catalog_snapshot is None or _catalog_snapshot.get("version") != version:
            _catalog_snapshot = await _load_full_catalog(version)
        _catalog_last_probe = time.monotonic()
        return _filtered_catalog(_catalog_snapshot, category_codes)


def group_catalog_products(items):
    """按稳定商品身份聚合规格；价格和库存只属于规格，不参与商品匹配。"""
    grouped = {}
    for sku in items:
        # 历史测试和旧快照可能没有 product_id；仅以 SKU 身份降级，不合并不同规格。
        product_id = str(sku.get("product_id") or sku.get("sku_id") or "").strip()
        if not product_id:
            continue
        product = grouped.setdefault(
            product_id,
            {
                key: deepcopy(value)
                for key, value in sku.items()
                if key
                not in {
                    "sku_id",
                    "sku_code",
                    "sku_name",
                    "price_cent",
                    "available_quantity",
                    "sale_status",
                    "net_content_value",
                    "net_content_unit",
                }
            }
            | {"product_id": product_id, "skus": []},
        )
        product["skus"].append(deepcopy(sku))
    return list(grouped.values())


async def current_product_catalog(category_codes=None):
    """读取动态商城目录并按商品聚合全部已发布规格。"""
    catalog = await current_catalog(category_codes)
    return {"version": catalog["version"], "items": group_catalog_products(catalog["items"])}


async def refresh_purchase_items(items, catalog, saved_items):
    """目录省略不可售商品时保留原采购身份与快照，缺少快照则读取单品真值。"""
    current = {str(item["sku_id"]): item for item in catalog["items"]}
    saved = {str(item["sku_id"]): item["sku"] for item in saved_items if item.get("sku")}
    result = []
    for item in items:
        sid = str(item["sku_id"])
        sku = current.get(sid)
        if sku is None:
            sku = item.get("sku") or saved.get(sid)
            if not sku:
                sku = await commerce_request("GET", "/api/v1/integration/ai/catalog/skus/" + quote(sid, safe=""))
            sku = {**sku, "sku_id": sid, "sale_status": "unavailable", "available_quantity": 0}
        result.append({**item, "sku": sku})
    return result


def match_requirements(requirements, catalog):
    """按有审核映射的净可食克数选整包，全部需求共享SKU库存上限。"""
    result = match_meal_requirements({"meal": requirements}, catalog)
    return result["meal"] if result else None


def match_meal_requirements(meals, catalog):
    """跨餐回溯分配同一库存，逐餐凑整包并保留实际选定SKU。"""
    if not meals or any(not requirements for requirements in meals.values()):
        return None
    if any(r.get("sku_id") for rows in meals.values() for r in rows):
        return match_direct(meals, catalog)
    groups = []
    for meal, requirement in ((meal, r) for meal, requirements in meals.items() for r in requirements):
        code = requirement.get("ingredient_code") or requirement["ingredient_id"]
        grams = Decimal(requirement["required_value"])
        if not grams.is_finite() or grams <= 0:
            return None
        candidates = []
        for sku in catalog["items"]:
            if not sku_matches_plan(sku, meals[meal]):
                continue
            for mapping in sku.get("ingredients", []):
                if (
                    mapping.get("ingredient_code") != code
                    or mapping.get("net_unit") != "g"
                    or mapping.get("review_status") != "approved"
                ):
                    continue
                net = (
                    Decimal(str(mapping.get("net_value", 0)))
                    * Decimal(str(mapping.get("convert_ratio", 1)))
                    * (1 - Decimal(str(mapping.get("loss_rate", 0))))
                )
                if net <= 0:
                    continue
                quantity = int((grams / net).to_integral_value(rounding=ROUND_CEILING))
                sid = str(sku["sku_id"])
                available = int(sku.get("available_quantity", 0))
                if quantity <= available:
                    candidates.append((quantity * int(sku["price_cent"]), sid, quantity, sku, meal))
        if not candidates:
            return None
        groups.append(sorted(candidates, key=lambda candidate: (candidate[0], candidate[1])))
    # 先分配候选最少的食材，库存冲突时尝试其它实际SKU，不能只试最便宜的一项。
    groups.sort(key=len)
    remaining = {str(sku["sku_id"]): int(sku.get("available_quantity", 0)) for sku in catalog["items"]}
    chosen = []

    def allocate(index):
        """回溯共享库存冲突，不因贪心选择误判无货。"""
        if index == len(groups):
            return True
        for _, sid, quantity, sku, meal in groups[index]:
            if quantity > remaining[sid]:
                continue
            remaining[sid] -= quantity
            chosen.append((sid, quantity, sku, meal))
            if allocate(index + 1):
                return True
            chosen.pop()
            remaining[sid] += quantity
        return False

    if not allocate(0):
        return None
    selected = {meal: {} for meal in meals}
    for sid, quantity, sku, meal in chosen:
        selected[meal].setdefault(sid, {"sku_id": sid, "quantity": 0, "sku": sku})["quantity"] += quantity
    return {meal: list(items.values()) for meal, items in selected.items()}


def packages_in_stock(packages, catalog):
    """以商城实际逐餐整包匹配为准，合计共享SKU后复核当前可售数量。"""
    stock = {str(sku["sku_id"]): sku for sku in catalog["items"]}
    totals = {}
    for package in packages:
        if not package.get("items"):
            return False
        for item in package["items"]:
            sid = str(item.get("sku_id") or (item.get("sku") or {}).get("sku_id") or "")
            if not sku_matches_plan(stock.get(sid, {}), package.get("ingredient_requirements", [])):
                return False
            quantity = item.get("quantity")
            if not isinstance(quantity, int) or isinstance(quantity, bool) or quantity <= 0:
                return False
            totals[sid] = totals.get(sid, 0) + quantity
    return bool(totals) and all(
        sid in stock
        and stock[sid].get("sale_status") == "available"
        and quantity <= int(stock[sid].get("available_quantity", 0))
        for sid, quantity in totals.items()
    )


def sku_matches_plan(sku, requirements, *, allow_reserved=False):
    """采购只覆盖已校验菜单配料；额外配料或交叉过敏原须重新配餐。"""
    if any(r.get("sku_id") for r in requirements):
        return direct_sku_matches(sku, requirements, allow_reserved)
    codes = {row.get("ingredient_code") or row["ingredient_id"] for row in requirements}
    ingredients = sku.get("ingredients") or []
    if (
        not codes
        or not ingredients
        or sku.get("data_completeness") != "complete"
        or (
            sku.get("sale_status") != "available"
            and not (allow_reserved and sku.get("unavailable_reason") == "out_of_stock")
        )
        or not set(sku.get("allergen_codes") or []).issubset(codes)
    ):
        return False
    for mapping in ingredients:
        if (
            not mapping.get("ingredient_id")
            or mapping.get("ingredient_code") not in codes
            or mapping.get("review_status") != "approved"
            or mapping.get("net_unit") != "g"
        ):
            return False
        try:
            amount = (
                Decimal(str(mapping.get("net_value", 0)))
                * Decimal(str(mapping.get("convert_ratio", 1)))
                * (1 - Decimal(str(mapping.get("loss_rate", 0))))
            )
            if not amount.is_finite() or amount <= 0:
                return False
        except (InvalidOperation, ValueError):
            return False
    return True

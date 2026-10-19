"""调用既有商城签名接口，完整分页读取库存并幂等保存推荐版本。"""

import hashlib
import hmac
import json
import os
import time
from decimal import Decimal, ROUND_CEILING
from urllib.parse import urlencode, urlsplit
from uuid import uuid4

import httpx

from yuxi.services.health_vision_types import HealthVisionError


async def commerce_request(method, path, payload=None, *, request_id=None):
    """密钥只从后端环境读取；同一业务重试使用新nonce和原幂等键。"""
    origin = os.environ.get("HEALTH_COMMERCE_API_URL", "").rstrip("/")
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


async def current_catalog():
    """读取完整可售目录，跨页版本变化时重读而不是混合库存。"""
    for _ in range(2):
        items, cursor, seen, version = [], "", set(), None
        while True:
            page = await commerce_request(
                "GET", "/api/v1/integration/ai/catalog/products?" + urlencode({"limit": 200, "cursor": cursor})
            )
            if version is not None and version != page["catalog_version"]:
                break
            version = page["catalog_version"]
            items.extend(page["items"])
            if not page.get("has_more"):
                return {"items": items, "version": version}
            cursor = page.get("next_cursor")
            if not cursor or cursor in seen:
                raise HealthVisionError("catalog_invalid", "食材目录分页暂时无法核对", 503)
            seen.add(cursor)
    raise HealthVisionError("catalog_changed", "食材目录正在更新，请稍后重试", 503)


def match_requirements(requirements, catalog):
    """按有审核映射的净可食克数选整包，全部需求共享SKU库存上限。"""
    if not requirements:
        return None
    groups = []
    for requirement in requirements:
        code, grams = requirement["ingredient_id"], Decimal(requirement["required_value"])
        candidates = []
        for sku in catalog["items"]:
            if sku.get("sale_status") != "available":
                continue
            for mapping in sku.get("ingredients", []):
                if mapping.get("ingredient_code") != code or mapping.get("net_unit") != "g":
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
                    candidates.append((quantity * int(sku["price_cent"]), sid, quantity, sku))
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
        for _, sid, quantity, sku in groups[index]:
            if quantity > remaining[sid]:
                continue
            remaining[sid] -= quantity
            chosen.append((sid, quantity, sku))
            if allocate(index + 1):
                return True
            chosen.pop()
            remaining[sid] += quantity
        return False

    if not allocate(0):
        return None
    selected = {}
    for sid, quantity, sku in chosen:
        selected.setdefault(sid, {"sku_id": sid, "quantity": 0, "sku": sku})["quantity"] += quantity
    return list(selected.values())


def packages_in_stock(packages, catalog):
    """以商城实际逐餐整包匹配为准，合计共享SKU后复核当前可售数量。"""
    stock = {str(sku["sku_id"]): sku for sku in catalog["items"]}
    totals = {}
    for package in packages:
        if not package.get("items"):
            return False
        for item in package["items"]:
            sid = str(item.get("sku_id") or (item.get("sku") or {}).get("sku_id") or "")
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

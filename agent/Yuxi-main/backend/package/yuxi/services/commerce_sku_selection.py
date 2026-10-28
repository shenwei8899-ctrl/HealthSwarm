"""Agent 的配方食品直接选择商城规格；不借用商城的营养审核结论。"""

from decimal import Decimal, InvalidOperation, ROUND_CEILING

from pydantic import BaseModel, ConfigDict, Field

from yuxi.services.health_vision_types import HealthVisionError


class RecipeSkuBinding(BaseModel):
    """真实配方来源发布者提供采购换算，商品快照由服务端读取。"""

    model_config = ConfigDict(extra="forbid")
    sku_id: str = Field(pattern=r"^[1-9][0-9]{0,15}$")
    purchase_grams_per_food_gram: Decimal = Field(gt=0, le=1000, max_digits=12, decimal_places=6)
    source_ref: str = Field(min_length=1, max_length=500)


def merchant_identity(sku):
    """保存商品身份与包装；价格和可售库存另行实时核对。"""
    return {
        key: sku.get(key)
        for key in ("product_id", "sku_id", "product_name", "sku_name", "sku_code", "category_code", "net_content")
    }


def pack_grams(sku):
    """只转换同量纲质量单位，不把毫升或件数猜成克数。"""
    net = sku.get("net_content") or {}
    try:
        amount = Decimal(str(net.get("value", 0)))
        multiplier = {"g": Decimal(1), "kg": Decimal(1000)}.get(net.get("unit"))
        if multiplier is None or not amount.is_finite() or amount <= 0:
            return None
        return amount * multiplier
    except (InvalidOperation, ValueError, TypeError):
        return None


async def resolve_binding(binding, fetch):
    """保留可追溯的真实食品采购换算，不生成营养或专业批准记录。"""
    data = RecipeSkuBinding.model_validate(binding)
    if not data.source_ref.strip():
        raise HealthVisionError("sku_binding_invalid", "请提供真实商品换算来源", 422)
    sku = await fetch("GET", "/api/v1/integration/ai/catalog/skus/" + data.sku_id)
    if str(sku.get("sku_id")) != data.sku_id or not pack_grams(sku):
        raise HealthVisionError("sku_binding_invalid", "商品规格不存在或缺少可用于该配方的质量净含量", 422)
    return {**data.model_dump(mode="json"), "merchant_snapshot": merchant_identity(sku)}


def selected_requirement(binding, food_id, grams):
    """把配方食品量按 Agent 已保存来源换成待采购商品克数。"""
    amount = Decimal(str(grams)) * Decimal(str(binding["purchase_grams_per_food_gram"]))
    if not amount.is_finite() or amount <= 0:
        raise HealthVisionError("sku_binding_invalid", "配方采购换算无效", 422)
    return {
        "ingredient_id": "sku:" + binding["sku_id"],
        "ingredient_code": "sku:" + binding["sku_id"],
        "sku_id": binding["sku_id"],
        "food_id": food_id,
        "required_value": str(amount),
        "required_unit": "g",
        "merchant_snapshot": binding["merchant_snapshot"],
        "source_ref": binding["source_ref"],
    }


def direct_requirements(requirements):
    """新协议以逐项明确规格为界，禁止半份请求回退旧自动匹配。"""
    return bool(requirements) and all(isinstance(r, dict) and r.get("sku_id") for r in requirements)


def direct_sku_matches(sku, requirements, allow_reserved=False):
    """商品身份及包装变化需要 Agent 重建来源；营养校验仍由配方服务负责。"""
    own = [r for r in requirements if str(r.get("sku_id")) == str(sku.get("sku_id"))]
    if not direct_requirements(requirements) or not own or not pack_grams(sku):
        return False
    if sku.get("sale_status") != "available" and not (
        allow_reserved and sku.get("unavailable_reason") == "out_of_stock"
    ):
        return False
    if not isinstance(sku.get("price_cent"), int) or sku["price_cent"] <= 0:
        return False
    return all(r.get("required_unit") == "g" and r.get("merchant_snapshot") == merchant_identity(sku) for r in own)


def match_direct(meals, catalog):
    """按 Agent 明确选中的规格凑整包，跨餐共享库存，不代换食材。"""
    current = {str(s["sku_id"]): s for s in catalog["items"]}
    remaining = {sid: int(s.get("available_quantity", 0)) for sid, s in current.items()}
    result = {}
    for meal, requirements in meals.items():
        if not direct_requirements(requirements):
            return None
        amounts = {}
        for r in requirements:
            sid = str(r["sku_id"])
            if sid not in current or not direct_sku_matches(current[sid], requirements):
                return None
            try:
                value = Decimal(str(r["required_value"]))
                if not value.is_finite() or value <= 0:
                    return None
            except (KeyError, InvalidOperation, ValueError):
                return None
            amounts[sid] = amounts.get(sid, Decimal(0)) + value
        result[meal] = []
        for sid, amount in amounts.items():
            quantity = int((amount / pack_grams(current[sid])).to_integral_value(rounding=ROUND_CEILING))
            if quantity > remaining[sid]:
                return None
            remaining[sid] -= quantity
            result[meal].append({"sku_id": sid, "quantity": quantity, "sku": current[sid]})
    return result


def purchase_authority(payload):
    """回源确认只返回已保存的采购上下文，不返回健康档案。"""
    if not isinstance(payload, dict) or not direct_requirements(payload.get("ingredient_requirements")):
        return None
    if payload.get("nutrition_validation", {}).get("status") != "passed":
        raise HealthVisionError("source_invalidated", "餐单尚未通过 Agent 校验", 410)
    ids = {str(r["sku_id"]) for r in payload["ingredient_requirements"]}
    items = payload.get("items", [])
    if (
        not items
        or len({str(i.get("sku_id")) for i in items}) != len(items)
        or {str(i.get("sku_id")) for i in items} != ids
        or any(type(i.get("quantity")) is not int or i["quantity"] <= 0 for i in items)
    ):
        raise HealthVisionError("source_invalidated", "已保存的采购规格或数量不完整", 410)
    return {
        key: payload[key]
        for key in (
            "user_ref",
            "family_ref",
            "menu_version_ref",
            "ingredient_requirements",
            "items",
            "nutrition_validation",
        )
    }

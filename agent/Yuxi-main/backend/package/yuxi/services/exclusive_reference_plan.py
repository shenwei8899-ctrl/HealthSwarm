"""以今日餐单原谱规划连续菜单，采购与计价只附加事实和缺口。"""

import asyncio
import re
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation, ROUND_CEILING

from yuxi.repositories.family_repository import FamilyRepository
from yuxi.services.daily_commerce_service import current_catalog, sku_matches_plan
from yuxi.services.family_service import FamilyService
from yuxi.services.health_nutrition_service import input_fingerprint
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.services.reference_meal_composition import is_plain_reference_staple, validate_reference_meal_composition
from yuxi.services.reference_meal_plan_service import (
    checked_reference_meals,
    recipe_document,
    reference_context_in_session,
    reference_member_restrictions,
    reference_product_composition,
    reference_restriction_conflict,
)
from yuxi.services.reference_meal_plan_types import ReferenceMeal, ReferenceSelection
from yuxi.services.reference_menu_candidates import reference_coverage_message, reference_menu_options
from yuxi.services.reference_recipe_index import (
    prepare_reference_documents,
    rank_prepared_reference_recipes,
    reference_recipe_rows,
)
from yuxi.services.reference_recipe_matching import (
    ReferenceProductIndex,
    ingredient_food_for_products,
    optional_reference_ingredient,
    product_foods,
)
from yuxi.services.reference_recipe_variety import validate_variety, variety_context

REFERENCE_POLICY = {"version": "exclusive-reference-v2", "hash": "exclusive-reference-v2"}
TIER_TARGETS = {
    "economy": "以较低食材费用为目标",
    "standard": "以适中食材费用为目标",
    "premium": "以较高食材费用为目标",
}
CAPABILITY_NOTICE = "当前沿用今日餐单口径生成21天参考菜单，未作专业审核，个人营养量和家庭份量尚未核定。"
PRICE_NOTICE = "小计仅按已核对原谱用量计算所需包装，未核定家庭份量，不代表完整计划预算，不用于比较三档总费用。"


async def exclusive_reference_context(session, uid, fid, *, day=None):
    """复用今日餐单授权边界，来源不依赖审核配方或采购目录。"""
    family, _ = await FamilyService(session, uid).context(fid)
    diners = sorted((family.settings or {}).get("default_diners", []))
    if not diners:
        raise HealthVisionError("reference_member_required", "请先选择家庭默认就餐成员", 422)
    anchor = await FamilyRepository(session).linked_health_member(fid, diners[0])
    selection = ReferenceSelection(family_id=fid, plan_date=day or date.today(), participant_ids=diners)
    current = await reference_context_in_session(session, uid, anchor, selection.model_dump(mode="json"))
    from yuxi.services.health_memory_context_service import account_plan_restrictions

    memories = await account_plan_restrictions(session, uid, current)
    if memories:
        current["sources"]["memory_restrictions"] = memories
    current["memory_restrictions"] = [fact["restriction"] for fact in memories]
    sources = {
        "members": {
            source["health_member_id"]: {
                "id": mid,
                "name": next(m["name"] for m in current["members"] if m["id"] == mid),
                **source,
            }
            for mid, source in current["sources"]["members"].items()
        },
        "reference": current["sources"],
    }
    documents = await asyncio.to_thread(prepare_reference_documents, await reference_recipe_rows(session))
    return {
        "mode": "reference",
        "selection": selection,
        "sources": sources,
        "current": current,
        "basis_hash": input_fingerprint({"sources": current["sources"], "policy": REFERENCE_POLICY}),
        "documents": documents,
        "verified_documents": {},
    }


async def optional_exclusive_catalog():
    """采购服务不可用只形成可观察缺口，不能撤销菜单。"""
    try:
        return {**await current_catalog(), "status": "available"}
    except HealthVisionError as error:
        if not error.code.startswith(("commerce_", "catalog_")):
            raise
        return {"items": [], "version": None, "status": "unavailable", "error_code": error.code}


def generate_reference_day(context, tier, previous, seed, catalog):
    """共用今日选菜和跨日去重；只有可靠费用资料参与三档排序。"""
    selection = context["selection"].model_dump(mode="json")
    history = [(selection["family_id"], entry["day"]["plan_date"], entry["meals"]) for entry in previous[-14:]]
    variety = variety_context(history, selection, context["current"]["members"])
    variety["seed"] += f":{seed}:{tier}"
    restrictions = reference_member_restrictions(context["current"]["members"]) + context["current"].get(
        "memory_restrictions", []
    )
    reference_restriction_conflict("", restrictions)
    variety["restrictions"] = restrictions
    ranked = rank_prepared_reference_recipes(
        context["documents"],
        None,
        set(),
        "",
        len(context["documents"]),
        {},
        variety=variety,
    )
    documents = {document["source"]["file_id"]: document for document in context["documents"]}
    ranked = [
        item
        for item in ranked
        if not is_plain_reference_staple(
            item["name"],
            documents[item["file_id"]]["parsed"].ingredients,
        )
    ]
    costs = {
        item["file_id"]: recipe_cost_evidence(documents[item["file_id"]]["parsed"].ingredients, catalog)
        for item in ranked
    }
    known = sorted({value for value in costs.values() if value is not None})
    if known:
        target = known[0] if tier == "economy" else known[-1] if tier == "premium" else known[len(known) // 2]
        # 缺失资料不冒充便宜或昂贵；保留偏好/去重排序作为同级依据。
        ranked.sort(
            key=lambda item: (
                costs[item["file_id"]] is None,
                abs(costs[item["file_id"]] - target) if costs[item["file_id"]] is not None else 0,
            )
        )
    options = reference_menu_options([ranked], selection, history, (), None)
    if not options["menus"]:
        raise HealthVisionError(
            "exclusive_menu_insufficient", reference_coverage_message(options["coverage_gaps"]), 422
        )
    meals = []
    for meal in options["menus"][0]:
        dishes = []
        for item in meal["dishes"]:
            document = documents[item["file_id"]]
            parsed, source = document["parsed"], document["source"]
            dishes.append(
                {
                    "file_id": source["file_id"],
                    "chunk_id": source["chunk_id"],
                    "name": parsed.name,
                    "ingredients": list(parsed.ingredients),
                    "steps": list(parsed.steps),
                    "source": {**source, "chunks_hash": document["chunks_hash"]},
                }
            )
        meals.append({"meal_type": meal["meal_type"], "dishes": dishes})
    validate_reference_meal_composition(meals, selection)
    return {
        "mode": "reference",
        "meals": meals,
        "day": {"day_no": len(previous) + 1, "plan_date": selection["plan_date"]},
        "tier_target": TIER_TARGETS[tier],
        "tier_cost_status": "evidence_available"
        if any(value is not None for value in costs.values())
        else "unverified",
        "procurement": reference_procurement(meals, catalog, restrictions),
    }


async def validate_reference_days(session, context, entries):
    """保存、发布和读取均重验原谱及限制；不读取商品或采购映射。"""
    history = []
    restrictions = context["current"].get("memory_restrictions", [])
    for entry in entries:
        if entry.get("mode") != "reference":
            raise HealthVisionError("source_invalidated", "旧版计划需重新准备", 410)
        if sorted(meal["meal_type"] for meal in entry["meals"]) != ["breakfast", "dinner", "lunch"]:
            raise HealthVisionError("source_invalidated", "计划三餐不完整，请重新准备", 410)
        documents = context["verified_documents"]
        meals = []
        for meal in entry["meals"]:
            dishes = []
            for dish in meal["dishes"]:
                key = dish["file_id"], dish["chunk_id"]
                if key not in documents:
                    documents[key] = await recipe_document(session, *key)
                document = documents[key]
                if reference_restriction_conflict(document["content"], restrictions):
                    raise HealthVisionError("reference_restriction_conflict", "计划菜谱不符合当前记忆限制", 422)
                if any(
                    document.get(field) != dish["source"].get(field)
                    for field in (
                        "file_id",
                        "chunk_id",
                        "kb_id",
                        "filename",
                        "file_hash",
                        "chunks_hash",
                    )
                ):
                    raise HealthVisionError("source_invalidated", "计划菜谱来源已变化，请重新准备", 410)
                dishes.append({key: dish[key] for key in ("file_id", "chunk_id", "name", "ingredients", "steps")})
            meals.append(ReferenceMeal.model_validate({"meal_type": meal["meal_type"], "dishes": dishes}))
        from types import SimpleNamespace

        checked = checked_reference_meals(SimpleNamespace(meals=meals), documents, context["current"]["members"])
        selection = context["selection"].model_dump(mode="json") | {"plan_date": entry["day"]["plan_date"]}
        if history and (
            entry["day"]["day_no"] != entries[len(history) - 1]["day"]["day_no"] + 1
            or date.fromisoformat(selection["plan_date"]) != date.fromisoformat(history[-1][1]) + timedelta(days=1)
        ):
            raise HealthVisionError("source_invalidated", "计划日期不连续，请重新准备", 410)
        validate_reference_meal_composition(checked, selection)
        validate_variety(history[-14:], selection, checked)
        history.append((selection["family_id"], selection["plan_date"], checked))
        entry["meals"] = checked


def reference_procurement(meals, catalog, restrictions=()):
    """保留每道菜的原谱食材；以明确克重和单食材包装计算部分小计。"""
    index = ReferenceProductIndex(catalog["items"])
    rows, groups = [], {}
    for meal in meals:
        for dish in meal["dishes"]:
            for line in dish["ingredients"]:
                food = ingredient_food_for_products(line, catalog["items"], index=index)
                row = {
                    "ingredient": line,
                    "recipe_name": dish["name"],
                    "meal_type": meal["meal_type"],
                    "file_id": dish["file_id"],
                    "food": food,
                }
                rows.append(row)
                if food == "水" or optional_reference_ingredient(line):
                    row.update(
                        status="self_prepare", detail="烹饪用水，自行准备" if food == "水" else "原谱可选食材，自行决定"
                    )
                    continue
                group = groups.setdefault(food or line, {"food": food, "rows": [], "grams": Decimal(0), "known": True})
                group["rows"].append(row)
                grams = explicit_grams(line)
                group["known"] &= grams is not None
                group["grams"] += grams or Decimal(0)
    matched, gaps = [], []
    for group in groups.values():
        item, reason, detail = price_ingredient_group(group, index, catalog, restrictions)
        if item:
            matched.append(item)
        for row in group["rows"]:
            row.update(
                status="matched" if item else "unpriced",
                detail=detail,
                reason=reason,
                sku_id=item["sku_id"] if item else None,
            )
            if not item:
                gaps.append({**row, "purchase_mode": "self_prepare_or_confirm", "price_cent": None})
    return {
        "status": "partial" if gaps else "matched" if matched else "self_prepare",
        "catalog_status": catalog.get("status", "available"),
        "catalog_version": catalog.get("version"),
        "catalog_error_code": catalog.get("error_code"),
        "ingredients": rows,
        "matched_items": matched,
        "purchase_gaps": gaps,
        "pricing": {
            "matched_subtotal_cent": sum(item["subtotal_cent"] for item in matched) if matched else None,
            "unpriced_ingredients": gaps,
            "status": "partial" if matched and gaps else "matched_only" if matched else "unavailable",
            "complete_estimate": False,
            "notice": PRICE_NOTICE,
        },
    }


def summarize_reference_prices(entries):
    """仅合计已匹配小计，未知日不补零，不计算档间价格顺序。"""
    values = [entry["procurement"]["pricing"]["matched_subtotal_cent"] for entry in entries]
    gaps = [
        dict(gap, day_no=entry["day"]["day_no"]) for entry in entries for gap in entry["procurement"]["purchase_gaps"]
    ]
    known = [value for value in values if value is not None]
    return {
        "matched_subtotal_cent": sum(known) if known else None,
        "unpriced_ingredients": gaps,
        "status": "partial" if known and gaps else "matched_only" if known else "unavailable",
        "complete_estimate": False,
        "notice": PRICE_NOTICE,
    }


def recipe_cost_evidence(ingredients, catalog):
    """只有必需食材均有原谱克重及可靠单价时才提供费用排序依据。"""
    procurement = reference_procurement(
        [
            {
                "meal_type": "lunch",
                "dishes": [
                    {"name": "候选", "file_id": "candidate", "ingredients": ingredients},
                ],
            }
        ],
        catalog,
    )
    if procurement["purchase_gaps"]:
        return None
    # 按食材净用量成本排序，避免用更贵包装制造品质档。
    items = procurement["matched_items"]
    return sum(Decimal(item["ingredient_cost_cent"]) for item in items) if items else None


def explicit_grams(line):
    """仅接受原谱明确的单个克/千克用量，不猜测杯、个、适量或范围。"""
    amounts = re.findall(
        r"(?<![\d./\-–~至])(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>公斤|千克|公克|克|kg\b|g\b)", line, re.I
    )
    if len(amounts) != 1 or re.search(r"\d\s*[-–~至/,，]\s*\d|[½¼¾⅓⅔]", line):
        return None
    value, unit = amounts[0]
    grams = Decimal(value) * (1000 if unit.lower() in {"kg", "公斤", "千克"} else 1)
    return grams if grams > 0 else None


def price_ingredient_group(group, index, catalog, restrictions):
    """采购事实不足时返回缺口，不让附加匹配影响菜单。"""

    def gap(reason, detail):
        """统一待确认文案。"""
        return None, reason, detail + "；可自行准备或待确认"

    if catalog.get("status") == "unavailable":
        return gap("catalog_unavailable", "商品目录暂不可用")
    food = group["food"]
    if not food:
        return gap("mapping_missing", "食材身份或采购映射尚未核对")
    products = index.by_food.get(food, [])
    if not products:
        return gap("no_match", "尚未匹配商品")
    if not group["known"]:
        return gap("quantity_unconfirmed", "原谱缺少可换算的明确克重，尚不能核算家庭采购量")
    skus = [sku for product in products for sku in (product.get("skus") or [product])]
    eligible, reasons = [], set()
    for sku in skus:
        if (
            sku.get("sale_status") != "available"
            or type(sku.get("available_quantity")) is not int
            or sku["available_quantity"] <= 0
        ):
            reasons.add("stock_unconfirmed")
            continue
        if type(sku.get("price_cent")) is not int or sku["price_cent"] < 0:
            reasons.add("price_missing")
            continue
        mappings = sku.get("ingredients") or []
        codes = {mapping.get("ingredient_code") for mapping in mappings}
        # 复合包装不按单一食材重复计价，继续保留待确认。
        if len(mappings) != 1 or len(codes) != 1 or None in codes or product_foods(sku) != {food}:
            reasons.add("mapping_missing")
            continue
        requirements = [{"ingredient_code": next(iter(codes)), "required_value": str(group["grams"])}]
        if not sku_matches_plan(sku, requirements):
            reasons.add("specification_unconfirmed")
            continue
        if reference_restriction_conflict(reference_product_composition(sku), restrictions):
            reasons.add("product_restriction_conflict")
            continue
        mapping = mappings[0]
        try:
            net = (
                Decimal(str(mapping["net_value"]))
                * Decimal(str(mapping.get("convert_ratio", 1)))
                * (1 - Decimal(str(mapping.get("loss_rate", 0))))
            )
            quantity = int((group["grams"] / net).to_integral_value(rounding=ROUND_CEILING))
        except (InvalidOperation, ValueError, ZeroDivisionError):
            reasons.add("specification_unconfirmed")
            continue
        if quantity > sku["available_quantity"]:
            reasons.add("stock_unconfirmed")
            continue
        eligible.append(
            {
                "food": food,
                "sku_id": str(sku["sku_id"]),
                "product_name": sku.get("product_name"),
                "specification": sku.get("sku_name"),
                "quantity": quantity,
                "price_cent": sku["price_cent"],
                "subtotal_cent": quantity * sku["price_cent"],
                "required_grams": str(group["grams"]),
                "ingredient_cost_cent": str(group["grams"] / net * sku["price_cent"]),
                "ingredient_refs": [row["ingredient"] for row in group["rows"]],
            }
        )
    if eligible:
        return (
            min(eligible, key=lambda item: (item["subtotal_cent"], item["sku_id"])),
            None,
            "按原谱明确克重核算包装，家庭份量待确认",
        )
    reason = next(
        (
            reason
            for reason in (
                "price_missing",
                "specification_unconfirmed",
                "mapping_missing",
                "stock_unconfirmed",
                "product_restriction_conflict",
            )
            if reason in reasons
        ),
        "needs_confirmation",
    )
    return gap(
        reason,
        {
            "price_missing": "缺少商品价格",
            "specification_unconfirmed": "包装净重或食材换算资料待确认",
            "mapping_missing": "采购映射不足或为复合包装",
            "stock_unconfirmed": "库存不足或尚未确认",
            "product_restriction_conflict": "候选商品含明确限制成分",
        }.get(reason, "采购资料待确认"),
    )

"""以今日餐单原谱规划连续菜单，采购与计价只附加事实和缺口。"""

import asyncio
import re
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation, ROUND_CEILING, ROUND_HALF_UP

from yuxi.repositories.family_repository import FamilyRepository
from yuxi.services.daily_commerce_service import current_catalog, sku_matches_plan
from yuxi.services.family_service import FamilyService
from yuxi.services.health_nutrition_service import input_fingerprint
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.services.reference_meal_composition import (
    is_plain_reference_staple,
    reference_meal_targets,
    validate_reference_meal_composition,
)
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
    parse_reference_recipe,
    product_foods,
)
from yuxi.services.reference_recipe_variety import validate_variety, variety_context

from yuxi.services.exclusive_plan_types import EXCLUSIVE_PLAN_DAYS

REFERENCE_POLICY = {"version": "exclusive-week-v1", "hash": "exclusive-week-v1", "day_count": EXCLUSIVE_PLAN_DAYS}
TIER_TARGETS = {
    "economy": "以较低食材费用为目标",
    "standard": "以适中食材费用为目标",
    "premium": "以较高食材费用为目标",
}
TIER_REFERENCE_CENTS = {"economy": (1000, 2000), "standard": (3000, 5000), "premium": (5000, 10000)}
CAPABILITY_NOTICE = "当前沿用今日餐单口径生成7天参考菜单，未作专业审核，个人营养量和家庭份量尚未核定。"
PRICE_NOTICE = (
    "按整期合并采购包装计算，参考人均费用为总价除以天数及本计划就餐人数；家庭份量尚未核定，未匹配食材不计入完整总价。"
)


async def exclusive_reference_context(session, uid, fid, *, day=None, start_date=None, load_documents=True):
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
    documents = (
        await asyncio.to_thread(prepare_reference_documents, await reference_recipe_rows(session))
        if load_documents
        else []
    )
    return {
        "mode": "reference",
        "selection": selection,
        "sources": sources,
        "current": current,
        "basis_hash": input_fingerprint(
            {
                "sources": current["sources"],
                "policy": REFERENCE_POLICY,
                "start_date": str(start_date or selection.plan_date),
            }
        ),
        "documents": documents,
        "verified_documents": {},
    }


async def optional_exclusive_catalog():
    """采购服务不可用只形成可观察缺口，不能撤销菜单。"""
    try:
        from yuxi.services.exclusive_delivery_suggestions import catalog_storage_rules

        catalog = await current_catalog()
        return {**catalog, "status": "available", "storage_rules": catalog_storage_rules(catalog.get("items", []))}
    except HealthVisionError as error:
        if not error.code.startswith(("commerce_", "catalog_")):
            raise
        return {"items": [], "version": None, "status": "unavailable", "error_code": error.code}


def generate_reference_day(context, tier, previous, seed, catalog, *, cost_cache=None, product_index=None):
    """共用今日选菜和跨日去重；只有可靠费用资料参与三档排序。"""
    if product_index is None:
        product_index = ReferenceProductIndex(catalog["items"])
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
    # 缓存仅属于单次任务及其固定商品快照；原谱分片变化后重新计价。
    cost_cache = {} if cost_cache is None else cost_cache
    costs = {}
    for item in ranked:
        document = documents[item["file_id"]]
        key = item["file_id"], document["chunks_hash"]
        if key not in cost_cache:
            cost_cache[key] = recipe_cost_evidence(document["parsed"].ingredients, catalog, product_index=product_index)
        costs[item["file_id"]] = cost_cache[key]
    if any(value is not None for value in costs.values()):
        lower, upper = TIER_REFERENCE_CENTS[tier]
        dish_count = sum(target["shared_min"] for target in reference_meal_targets(selection).values())
        target = Decimal(lower + upper) * len(selection["participant_ids"]) / (2 * dish_count)
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
    candidates = []
    for menu in options["menus"]:
        meals = []
        for meal in menu:
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
        all_meals = [meal for entry in previous for meal in entry["meals"]] + meals
        procurement = reference_procurement(all_meals, catalog, restrictions, product_index=product_index)
        # 只比较现有有限备选；区间外仍可采用，不按预算重排或放宽饮食限制。
        total = procurement["pricing"]["matched_subtotal_cent"]
        known = total is not None and not procurement["purchase_gaps"]
        average = Decimal(total) / ((len(previous) + 1) * len(selection["participant_ids"])) if known else None
        lower, upper = TIER_REFERENCE_CENTS[tier]
        distance = max(lower - average, average - upper, Decimal(0)) if known else Decimal(0)
        candidates.append(((not known, distance), meals))
    meals = min(candidates, key=lambda candidate: candidate[0])[1]
    validate_reference_meal_composition(meals, selection)
    return {
        "mode": "reference",
        "meals": meals,
        "day": {"day_no": len(previous) + 1, "plan_date": selection["plan_date"]},
        "tier_target": TIER_TARGETS[tier],
        "tier_cost_status": "evidence_available"
        if any(value is not None for value in costs.values())
        else "unverified",
        "procurement": reference_procurement(meals, catalog, restrictions, product_index=product_index),
    }


async def prepare_reference_day(session, context, entry, catalog, *, product_index=None):
    """新菜单从摘要一致的完整原谱取内容，再严格核验并重算采购。"""
    for meal in entry["meals"]:
        for dish in meal["dishes"]:
            document = await verified_reference_document(session, context, dish)
            parsed = parse_reference_recipe(document["content"])
            if parsed is None or parsed.review_sections:
                raise HealthVisionError("reference_quote_invalid", "菜谱完整原文暂时无法完整解析", 422)
            dish.update(name=parsed.name, ingredients=list(parsed.ingredients), steps=list(parsed.steps))
    await validate_reference_days(session, context, [entry])
    entry["procurement"] = reference_procurement(
        entry["meals"],
        catalog,
        reference_member_restrictions(context["current"]["members"])
        + context["current"].get("memory_restrictions", []),
        product_index=product_index,
    )


async def validate_reference_days(session, context, entries):
    """发布整期菜单时保留连续日期和跨日重复检查。"""
    history = []
    for entry in entries:
        checked = await validate_reference_day(session, context, entry)
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


async def validate_reference_day(session, context, entry, *, require_translation=True):
    """浏览只验证当天原谱及三餐组成，不冒充整期跨日校验。"""
    if entry.get("mode") != "reference":
        raise HealthVisionError("source_invalidated", "旧版计划需重新准备", 410)
    if sorted(meal["meal_type"] for meal in entry["meals"]) != ["breakfast", "dinner", "lunch"]:
        raise HealthVisionError("source_invalidated", "计划三餐不完整，请重新准备", 410)
    documents = context["verified_documents"]
    meals = []
    for meal in entry["meals"]:
        dishes = []
        for dish in meal["dishes"]:
            await verified_reference_document(session, context, dish)
            dishes.append({key: dish[key] for key in ("file_id", "chunk_id", "name", "ingredients", "steps")})
        meals.append(ReferenceMeal.model_validate({"meal_type": meal["meal_type"], "dishes": dishes}))
    from types import SimpleNamespace

    checked = checked_reference_meals(
        SimpleNamespace(meals=meals), documents, context["current"]["members"], require_translation=require_translation
    )
    selection = context["selection"].model_dump(mode="json") | {"plan_date": entry["day"]["plan_date"]}
    validate_reference_meal_composition(checked, selection)
    return checked


async def verified_reference_document(session, context, dish):
    """回读原谱并比对选菜时的完整来源，缓存仅用于本次验证。"""
    key = dish["file_id"], dish["chunk_id"]
    documents = context["verified_documents"]
    if key not in documents:
        documents[key] = await recipe_document(session, *key)
    document = documents[key]
    if reference_restriction_conflict(document["content"], context["current"].get("memory_restrictions", [])):
        raise HealthVisionError("reference_restriction_conflict", "计划菜谱不符合当前记忆限制", 422)
    if any(
        document.get(field) != dish["source"].get(field)
        for field in ("file_id", "chunk_id", "kb_id", "filename", "file_hash", "chunks_hash")
    ):
        raise HealthVisionError("source_invalidated", "计划菜谱来源已变化，请重新准备", 410)
    return document


def reference_procurement(meals, catalog, restrictions=(), *, product_index=None):
    """保留每道菜的原谱食材；以明确克重和单食材包装计算部分小计。"""
    index = product_index if product_index is not None else ReferenceProductIndex(catalog["items"])
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
                    **({"day_no": meal["day_no"]} if "day_no" in meal else {}),
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


def summarize_reference_prices(entries, *, catalog=None, member_count=0, restrictions=(), include_gaps=True):
    """有商品快照时合并整期包装；旧小计保持部分金额，不冒充完整报价。"""
    if catalog is not None:
        meals = [{**meal, "day_no": entry["day"]["day_no"]} for entry in entries for meal in entry["meals"]]
        procurement = reference_procurement(meals, catalog, restrictions)
        return reference_price_summary(procurement, len(entries), member_count, include_gaps=include_gaps)
    values = [entry["procurement"]["pricing"]["matched_subtotal_cent"] for entry in entries]
    gaps = [
        dict(gap, day_no=entry["day"]["day_no"]) for entry in entries for gap in entry["procurement"]["purchase_gaps"]
    ]
    known = [value for value in values if value is not None]
    return {
        "matched_subtotal_cent": sum(known) if known else None,
        "total_cent": None,
        "per_person_day_cent": None,
        "day_count": len(entries),
        "member_count": member_count,
        **({"unpriced_ingredients": gaps} if include_gaps else {"unpriced_ingredient_count": len(gaps)}),
        "status": "partial" if known and gaps else "matched_only" if known else "unavailable",
        "complete_estimate": False,
        "notice": PRICE_NOTICE,
    }


def reference_price_summary(procurement, day_count, member_count, *, include_gaps=True):
    """先取合并采购总额，再按天数及绑定人数折算，展示时才舍入到分。"""
    gaps = procurement["purchase_gaps"]
    subtotal = procurement["pricing"]["matched_subtotal_cent"]
    total = subtotal if not gaps else None
    average = (
        int((Decimal(total) / (day_count * member_count)).quantize(Decimal(1), rounding=ROUND_HALF_UP))
        if total is not None and day_count > 0 and member_count > 0
        else None
    )
    result = {
        **procurement["pricing"],
        "total_cent": total,
        "per_person_day_cent": average,
        "day_count": day_count,
        "member_count": member_count,
    }
    if not include_gaps:
        result.pop("unpriced_ingredients", None)
        result["unpriced_ingredient_count"] = len(gaps)
    return result


def recipe_cost_evidence(ingredients, catalog, *, product_index=None):
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
        product_index=product_index,
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

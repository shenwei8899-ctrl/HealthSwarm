"""审核目录内组合三档三餐；金额、商品规格和履约由商城决定。"""

import hashlib
import json
from collections import defaultdict
from decimal import ROUND_CEILING, Decimal

from yuxi.services.daily_arrangement_projection import allocated_meals, ingredient_requirements
from yuxi.services.daily_commerce_service import sku_matches_plan
from yuxi.services.health_initial_meal_generation import generate_initial_plan
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.services.reference_meal_composition import (
    is_plain_reference_staple,
    validate_reference_meal_composition,
)
from yuxi.services.reference_recipe_variety import candidate_priority, dish_keys, validate_variety, variety_context

TIERS = {"economy": "经济型", "standard": "标准型", "premium": "品质型"}


def generate_exclusive_day(
    selection,
    current,
    recipes,
    foods,
    refs,
    mappings,
    catalog,
    policy,
    tier,
    previous,
    seed,
    *,
    reference_composition,
    preference_members=(),
):
    """先限制审核目录与跨日重复，再由共用引擎验证所有成员的实际份量。"""
    preview = "config" not in policy
    config = policy.get("config", {})
    tier_rule = config["tiers"][tier] if not preview else {}
    day_no = len(previous) + 1
    allowed = set(map(str, tier_rule.get("allowed_recipe_version_ids", recipes)))
    allowed_skus = set(map(str, tier_rule.get("allowed_sku_ids", (item["sku_id"] for item in catalog["items"]))))
    recent_dishes = {
        key
        for entry in previous[-1:]
        for dish in entry["day"]["meals"]
        for key in dish_keys({"name": dish["recipe_name"], "file_id": dish["recipe_version_ref"]})
    }
    variety_selection = {"family_id": seed, "plan_date": selection.plan_date.isoformat()}
    history = (
        [(seed, entry["spec"]["plan_date"], menu_dishes(entry["day"]["meals"])) for entry in previous[-14:]]
        if preview
        else []
    )
    eligible = {
        rid: recipe
        for rid, recipe in recipes.items()
        if rid in allowed
        and rid in mappings
        and mappings[rid].recipe_hash == refs.get(rid)
        and mappings[rid].steps
        and (
            not reference_composition
            or not is_plain_reference_staple(recipe.name, [item["food"]["name"] for item in recipe.ingredients])
        )
        and all(item["food"]["id"] in mappings[rid].ingredient_codes for item in recipe.ingredients)
        and all(isinstance(value, str) for value in mappings[rid].ingredient_codes.values())
        and (
            not dish_keys({"name": recipe.name, "file_id": rid}) & recent_dishes
            if preview
            else repeat_allowed(rid, previous, day_no, tier_rule["repeat"], config["repeat_identity"])
        )
    }
    stock = {
        **catalog,
        "items": [item for item in catalog["items"] if str(item["sku_id"]) in allowed_skus],
    }

    selected_products = None

    def purchasable(snapshot):
        """同日按实际成员用量合并配料，拒绝附加未校验成分。"""
        nonlocal selected_products
        if reference_composition and not matches_daily_composition(snapshot, selection):
            return False
        if preview:
            try:
                validate_variety(history, variety_selection, allocated_menu_dishes(snapshot))
            except HealthVisionError as error:
                if error.code not in {"reference_recipe_repeated", "reference_menu_repeated"}:
                    raise
                return False
        requirements = ingredient_requirements(snapshot, mappings)
        selected_products = match_batch_requirements(requirements, stock, tier=tier if preview else None)
        return bool(selected_products)

    variety = variety_context(history, variety_selection, preference_members) if reference_composition else None

    def rank(rid):
        """沿用今日餐单的口味排序，稳定打散同分候选。"""
        name = eligible[rid].name
        preference = candidate_priority(dish_keys({"name": name}), " ".join([name, *mappings[rid].steps]), variety)
        rotation = hashlib.sha256(f"{seed}:{tier}:{day_no}:{rid}".encode()).hexdigest()
        return tuple(-value for value in preference), rotation

    priority = {rid: index + 1 for index, rid in enumerate(sorted(eligible, key=rank))}
    result = generate_initial_plan(
        selection, current, eligible, foods, refs, purchase_validator=purchasable, recipe_priority=priority
    )
    if result["status"] != "ready":
        raise HealthVisionError(
            "exclusive_plan_no_match", "当前审核食谱和有价商品无法配齐符合要求的三餐，请核对菜谱和商品后重试", 422
        )
    exported = export_day(result["plan_snapshot"], mappings, recipes, stock, day_no)
    entry = {
        "day": exported,
        "spec": result["plan_spec"],
        "snapshot": result["plan_snapshot"],
        "safety_check": result["safety_check"],
        "candidate_sources": result["candidate_sources"],
    }
    if preview:
        products = {str(item["sku_id"]): item for item in stock["items"]}
        entry["priced_products"] = [
            {
                **item,
                "product_name": products[item["sku_id"]]["product_name"],
                "image_url": products[item["sku_id"]].get("image_url"),
                "specification": products[item["sku_id"]].get("sku_name"),
            }
            for item in selected_products
        ]
    return entry


def menu_dishes(meals):
    """把已保存的菜品提供给今日餐单的验重规则。"""
    grouped = defaultdict(list)
    for dish in meals:
        grouped[dish["meal_type"]].append({"name": dish["recipe_name"], "file_id": dish["recipe_version_ref"]})
    return [{"meal_type": key, "dishes": dishes} for key, dishes in grouped.items()]


def allocated_menu_dishes(snapshot, *, include_ingredients=False):
    """将同一餐的家庭分配归并为一组共用菜。"""
    meals = defaultdict(dict)
    for _, meal in allocated_meals(snapshot):
        for dish in meal["dishes"]:
            rid = dish["recipe_version_id"]
            meals[meal["meal_type"]][rid] = {
                "file_id": rid,
                "name": dish["name"],
                **({"ingredients": [item["name"] for item in dish["ingredients"]]} if include_ingredients else {}),
            }
    return [{"meal_type": key, "dishes": list(dishes.values())} for key, dishes in meals.items()]


def matches_daily_composition(snapshot, selection):
    """按今日餐单的道数和菜品规则核对审核配方组合。"""
    meals = {meal["meal_type"]: meal["dishes"] for meal in allocated_menu_dishes(snapshot, include_ingredients=True)}
    for requested in selection.meals:
        meal_type = requested.meal_type
        try:
            validate_reference_meal_composition(
                [{"meal_type": meal_type, "dishes": meals.get(meal_type, [])}],
                {"meal_types": [meal_type], "participant_ids": list(requested.participant_ids)},
            )
        except HealthVisionError as error:
            if error.code != "reference_meal_incomplete":
                raise
            return False
    return True


def repeat_allowed(rid, previous, day_no, rule, identities):
    """审核身份是重复口径；改菜名不会改变统计。"""
    identity = identities[rid]
    dish_days, main_days = [], []
    for entry in previous:
        day = entry["day"]
        used = [identities[meal["recipe_version_ref"]] for meal in day["meals"]]
        if any(value["dish_key"] == identity["dish_key"] for value in used):
            dish_days.append(int(day["day_no"]))
        if any(value["main_ingredient_key"] == identity["main_ingredient_key"] for value in used):
            main_days.append(int(day["day_no"]))
    return not (
        dish_days
        and day_no - max(dish_days) <= rule["dish_gap_days"]
        or sum(day >= day_no - 6 for day in dish_days) >= rule["dish_max_per_7_days"]
        or sum(day >= day_no - 6 for day in main_days) >= rule["main_ingredient_max_per_7_days"]
    )


def export_day(snapshot, mappings, recipes, catalog, day_no):
    """保留逐成员份量和实际菜谱配料，按餐分组允许多道菜。"""
    dishes = {}
    for mid, meal in allocated_meals(snapshot):
        for dish in meal["dishes"]:
            rid = dish["recipe_version_id"]
            value = dishes.setdefault(
                (meal["meal_type"], rid),
                {
                    "meal_type": meal["meal_type"],
                    "recipe_ref": recipes[rid].record_code or rid,
                    "recipe_version_ref": rid,
                    "recipe_name": dish["name"],
                    "member_portions": [],
                    "steps": mappings[rid].steps,
                    "image_url": (mappings[rid].presentation or {}).get("image_url"),
                    "cooking_minutes": (mappings[rid].presentation or {}).get("cooking_minutes"),
                    "requirements": defaultdict(Decimal),
                },
            )
            value["member_portions"].append({"member_ref": mid, "grams": str(dish["planned_grams"])})
            for ingredient in dish["ingredients"]:
                value["requirements"][mappings[rid].ingredient_codes[ingredient["food_id"]]] += Decimal(
                    ingredient["planned_grams"]
                )
    meals = []
    for value in dishes.values():
        requirements = value.pop("requirements")
        meals.append(
            {
                **value,
                "ingredient_requirements": [
                    {"ingredient_code": code, "required_value": str(grams), "required_unit": "g"}
                    for code, grams in sorted(requirements.items())
                ],
            }
        )
    requirements = ingredient_requirements(snapshot, mappings)
    return {
        "day_no": day_no,
        "meals": meals,
        "eligible_sku_ids": sorted(
            str(item["sku_id"]) for item in catalog["items"] if sku_matches_plan(item, requirements)
        ),
    }


def content_hash(payload):
    """与商城共享规范化数字摘要，凭据绑定完整导出内容。"""
    fields = {
        "family_ref",
        "user_ref",
        "member_refs",
        "profile_version_refs",
        "recommendation_group_ref",
        "tier_code",
        "tier_policy_version",
        "basis_hash",
        "days",
        "nutrition_validation",
    }
    if payload.get("delivery_frequency") == "selectable":
        fields.add("delivery_frequency")

    def normalize(value):
        """JSON 数字转换为相同的十进制文本，布尔和空值保留语义。"""
        if isinstance(value, dict):
            return {key: normalize(item) for key, item in value.items()}
        if isinstance(value, list):
            return [normalize(item) for item in value]
        if isinstance(value, bool):
            return value
        if isinstance(value, int):
            return str(value)
        if isinstance(value, float):
            return f"{value:.8f}".rstrip("0").rstrip(".")
        return value

    raw = json.dumps(
        normalize({key: value for key, value in payload.items() if key in fields}),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(raw.encode()).hexdigest()


def match_batch_requirements(requirements, catalog, *, tier=None):
    """同批复合包装一次覆盖全部成分；候选库存不足时回溯其他真实商品。"""
    if not requirements:
        return None
    needed = {item["ingredient_code"]: Decimal(str(item["required_value"])) for item in requirements}
    candidates = []
    for sku in catalog["items"]:
        if not sku_matches_plan(sku, requirements):
            continue
        coverage = {}
        for mapping in sku.get("ingredients", []):
            if mapping.get("net_unit") != "g" or mapping.get("review_status") != "approved":
                continue
            code = mapping["ingredient_code"]
            net = (
                Decimal(str(mapping["net_value"]))
                * Decimal(str(mapping.get("convert_ratio", 1)))
                * (1 - Decimal(str(mapping.get("loss_rate", 0))))
            )
            if code in needed and net > 0:
                coverage[code] = coverage.get(code, Decimal(0)) + net
        if coverage:
            candidates.append((sku, coverage))
    candidates.sort(key=lambda pair: (int(pair[0]["price_cent"]), str(pair[0]["sku_id"])))
    visits = 0

    def search(remaining, stock, chosen):
        """每次满足一项仍缺的食材，用有界回溯避免贪心误报无货。"""
        nonlocal visits
        visits += 1
        if visits > 10000:
            return None
        code = next((code for code in sorted(remaining) if remaining[code] > 0), None)
        if code is None:
            return chosen
        eligible = [index for index, (_, coverage) in enumerate(candidates) if code in coverage]
        if tier:
            # 按覆盖当前缺口所需的实际包装总价排序，而非单包价。
            eligible.sort(
                key=lambda index: (
                    candidates[index][0]["price_cent"]
                    * int((remaining[code] / candidates[index][1][code]).to_integral_value(rounding=ROUND_CEILING)),
                    str(candidates[index][0]["sku_id"]),
                )
            )
            if tier == "premium":
                eligible.reverse()
            elif tier == "standard":
                middle = (len(eligible) - 1) / 2
                eligible = [index for _, index in sorted(enumerate(eligible), key=lambda pair: abs(pair[0] - middle))]
        for index in eligible:
            _, coverage = candidates[index]
            quantity = int((remaining[code] / coverage[code]).to_integral_value(rounding=ROUND_CEILING))
            if quantity > stock[index]:
                continue
            rest = {key: max(Decimal(0), value - coverage.get(key, 0) * quantity) for key, value in remaining.items()}
            available = stock.copy()
            available[index] -= quantity
            selected = chosen.copy()
            selected[index] = selected.get(index, 0) + quantity
            result = search(rest, available, selected)
            if result is not None:
                return result
        return None

    result = search(needed, [int(sku.get("available_quantity", 0)) for sku, _ in candidates], {})
    if result is None:
        return None
    return [{"sku_id": str(candidates[index][0]["sku_id"]), "quantity": quantity} for index, quantity in result.items()]

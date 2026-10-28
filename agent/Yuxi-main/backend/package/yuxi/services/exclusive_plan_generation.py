"""审核目录内组合三档三餐；金额、商品规格和履约由商城决定。"""

import hashlib
import json
from collections import defaultdict
from decimal import ROUND_CEILING, Decimal

from yuxi.services.daily_arrangement_projection import allocated_meals, ingredient_requirements
from yuxi.services.daily_commerce_service import sku_matches_plan
from yuxi.services.health_initial_meal_generation import generate_initial_plan
from yuxi.services.health_vision_types import HealthVisionError

TIERS = {"economy": "经济型", "standard": "标准型", "premium": "品质型"}


def generate_exclusive_day(selection, current, recipes, foods, refs, mappings, catalog, policy, tier, previous, seed):
    """先限制审核目录与跨日重复，再由共用引擎验证所有成员的实际份量。"""
    config = policy["config"]
    tier_rule = config["tiers"][tier]
    day_no = len(previous) + 1
    allowed = set(map(str, tier_rule["allowed_recipe_version_ids"]))
    eligible = {
        rid: recipe
        for rid, recipe in recipes.items()
        if rid in allowed
        and rid in mappings
        and mappings[rid].recipe_hash == refs.get(rid)
        and mappings[rid].steps
        and all(item["food"]["id"] in mappings[rid].ingredient_codes for item in recipe.ingredients)
        and all(isinstance(value, str) for value in mappings[rid].ingredient_codes.values())
        and repeat_allowed(rid, previous, day_no, tier_rule["repeat"], config["repeat_identity"])
    }
    stock = {
        **catalog,
        "items": [
            item for item in catalog["items"] if str(item["sku_id"]) in set(map(str, tier_rule["allowed_sku_ids"]))
        ],
    }

    def purchasable(snapshot):
        """同日按实际成员用量合并配料，拒绝附加未校验成分。"""
        requirements = ingredient_requirements(snapshot, mappings)
        return bool(requirements and match_batch_requirements(requirements, stock))

    priority = {
        rid: int(hashlib.sha256(f"{seed}:{tier}:{day_no}:{rid}".encode()).hexdigest()[:8], 16) for rid in eligible
    }
    result = generate_initial_plan(
        selection, current, eligible, foods, refs, purchase_validator=purchasable, recipe_priority=priority
    )
    if result["status"] != "ready":
        raise HealthVisionError(
            "exclusive_plan_no_match", "当前审核食谱或供货范围无法组成符合要求的完整计划，请调整配置后重试", 422
        )
    exported = export_day(result["plan_snapshot"], mappings, recipes, stock, day_no)
    return {
        "day": exported,
        "spec": result["plan_spec"],
        "snapshot": result["plan_snapshot"],
        "safety_check": result["safety_check"],
        "candidate_sources": result["candidate_sources"],
    }


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
                    "image_url": None,
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


def match_batch_requirements(requirements, catalog):
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
        for index, (sku, coverage) in enumerate(candidates):
            if code not in coverage:
                continue
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

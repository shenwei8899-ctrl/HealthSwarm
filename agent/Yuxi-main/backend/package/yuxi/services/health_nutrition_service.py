"""食品版本驱动的确定性营养计算，不接受模型营养值。"""

import hashlib
import json
from decimal import Decimal, ROUND_HALF_UP

from yuxi.services.health_vision_types import NUTRIENTS, HealthVisionError, MealPayload

CALCULATION_VERSION = "recipe-portions-v2"


def input_fingerprint(value: dict) -> str:
    """稳定序列化用于版本快照与幂等冲突检查。"""
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def recipe_nutrients(ingredients: list[dict], yield_grams: Decimal) -> dict:
    """以净成品重计算每百克，原料营养缺失不能变成零。"""
    result = {}
    for code in NUTRIENTS:
        values = [entry["food"]["nutrients"].get(code) for entry in ingredients]
        result[code] = (
            None
            if any(value is None for value in values)
            else str(
                sum(Decimal(str(value)) * Decimal(entry["grams"]) for entry, value in zip(ingredients, values))
                / yield_grams
            )
        )
    return result


def _source(record, id_key: str) -> dict:
    return {
        id_key: record.id,
        **{
            key: getattr(record, key)
            for key in ("name", "dataset_version", "source", "license", "edition", "cooking_state")
        },
        "recipe_estimated": id_key == "recipe_version_id" or bool(getattr(record, "recipe_estimated", False)),
    }


def _round(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def calculate_nutrition(
    payload: MealPayload, foods: dict, recipes: dict | None = None, portions: dict | None = None
) -> dict:
    """按最终可食净重和个人比例计算，油糖只在明确配方中替换。"""
    recipes, portions = recipes or {}, portions or {}
    totals = {key: Decimal(0) for key in NUTRIENTS}
    missing, items, sources = [], [], []
    estimated = False
    active_items = [item for item in payload.items if not item.excluded]
    if not active_items:
        missing.append({"reason": "no_items"})
    for item in active_items:
        food, recipe = foods.get(str(item.food_id)), recipes.get(str(item.recipe_version_id))
        grams = item.grams
        portion = portions.get(str(item.portion_reference_id))
        if item.portion_reference_id:
            if portion is None:
                raise HealthVisionError("portion_not_found", "份量参考版本不存在")
            if portion.food_id != (str(item.food_id) if item.food_id else None) or portion.recipe_version_id != (
                str(item.recipe_version_id) if item.recipe_version_id else None
            ):
                raise HealthVisionError("portion_mapping_mismatch", "份量参考不适用于此食品或食谱版本")
            grams = Decimal(str(portion.grams_per_unit)) * item.portion_count
            if grams > 10000:
                raise HealthVisionError("portion_limit", "换算后的成品重量不能超过 10000 克")
        if (
            (food is None and recipe is None)
            or grams is None
            or item.share_ratio is None
            or item.portion_source == "unknown"
        ):
            missing.append({"item_id": str(item.item_id), "reason": "food_or_portion_missing"})
            continue
        adjustment_foods = [foods.get(str(entry.food_id)) for entry in item.adjustments]
        if any(record is None for record in adjustment_foods):
            raise HealthVisionError("adjustment_food_not_found", "油糖调整须使用已发布食品版本")
        added_grams = sum((entry.grams for entry in item.adjustments), Decimal(0))
        if added_grams >= grams:
            raise HealthVisionError("adjustment_weight_invalid", "最终成品净重须大于调整油糖重量")
        replaced_roles = {entry.role for entry in item.adjustments if entry.mode == "replace"}
        contributions = []
        if recipe is not None:
            found_roles = {entry["role"] for entry in recipe.ingredients}
            if replaced_roles - found_roles:
                raise HealthVisionError("replacement_role_missing", "原配方没有明确的对应油糖原料，不能替换")
            removed_grams = sum(
                (Decimal(entry["grams"]) for entry in recipe.ingredients if entry["role"] in replaced_roles), Decimal(0)
            )
            baseline_yield = Decimal(str(recipe.yield_grams)) - removed_grams
            if baseline_yield <= 0:
                raise HealthVisionError("replacement_yield_invalid", "移除配方油糖后的净成品重量无效")
            scale = (grams - added_grams) / baseline_yield
            for entry in recipe.ingredients:
                if entry["role"] not in replaced_roles:
                    contributions.append((entry["food"]["nutrients"], Decimal(entry["grams"]) * scale))
            recipe_source = _source(recipe, "recipe_version_id")
            recipe_source.update({"yield_grams": str(recipe.yield_grams), "ingredients": recipe.ingredients})
            sources.append(recipe_source)
        else:
            contributions.append((food.nutrients, grams - added_grams))
            sources.append(_source(food, "food_id"))
        for adjustment, adjustment_food in zip(item.adjustments, adjustment_foods):
            contributions.append((adjustment_food.nutrients, adjustment.grams))
            sources.append({**_source(adjustment_food, "food_id"), "adjustment": adjustment.model_dump(mode="json")})
        if portion is not None:
            sources.append(
                {
                    "portion_reference_id": portion.id,
                    **{
                        key: str(getattr(portion, key))
                        for key in (
                            "unit_label",
                            "grams_per_unit",
                            "source",
                            "license",
                            "edition",
                            "dataset_version",
                            "applicable_scope",
                        )
                    },
                    "portion_count": str(item.portion_count),
                }
            )
        eaten_grams = grams * item.share_ratio
        item_totals = {}
        for code in NUTRIENTS:
            known_amount = sum(
                (
                    Decimal(str(values[code])) * weight * item.share_ratio / Decimal(100)
                    for values, weight in contributions
                    if values.get(code) is not None
                ),
                Decimal(0),
            )
            totals[code] += known_amount
            if any(values.get(code) is None for values, _ in contributions):
                missing.append({"item_id": str(item.item_id), "nutrient": code, "reason": "nutrient_missing"})
                item_totals[code] = None
            else:
                item_totals[code] = _round(known_amount)
        estimated |= (
            item.portion_source == "estimated" or recipe is not None or bool(getattr(food, "recipe_estimated", False))
        )
        estimated |= any(bool(record.recipe_estimated) for record in adjustment_foods)
        items.append({"item_id": str(item.item_id), "eaten_grams": str(eaten_grams), "nutrients": item_totals})
    incomplete_codes = {entry.get("nutrient") for entry in missing}
    incomplete_portion = any("nutrient" not in entry for entry in missing)
    known = {code: _round(value) for code, value in totals.items()}
    return {
        "complete": not missing,
        "estimated": estimated,
        "missing": missing,
        "items": items,
        "sources": sources,
        "units": NUTRIENTS,
        "known_subtotals": known,
        "totals": {
            code: None if incomplete_portion or code in incomplete_codes else value for code, value in known.items()
        },
        "calculation_version": CALCULATION_VERSION,
    }

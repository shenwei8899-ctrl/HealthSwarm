"""按本 Run 已打开的原谱装配参考稿，不让模型重写来源事实。"""

from copy import deepcopy
from typing import Literal
from uuid import UUID

from pydantic import Field, TypeAdapter, field_validator, model_validator

from yuxi.services.health_vision_types import HealthDTO, HealthVisionError
from yuxi.services.recipe_translation_types import RecipeChineseDisplay
from yuxi.services.reference_meal_composition import MAX_REFERENCE_DISHES
from yuxi.services.reference_meal_plan_types import ReferenceDishAssignment, ReferencePlanDraft


class ReferenceReadDish(ReferenceDishAssignment):
    """只选择本轮已打开的原谱，可另给中文展示和制作估时。"""

    file_id: str = Field(min_length=1, max_length=64)
    chunk_id: str = Field(min_length=1, max_length=128)
    display_zh: RecipeChineseDisplay | None = None
    cooking_minutes: int | None = Field(default=None, ge=1, le=1440, strict=True)


class ReferenceReadMeal(HealthDTO):
    """餐次必须明确，不能借选菜扩展用户选择范围。"""

    meal_type: Literal["breakfast", "lunch", "dinner"]
    dishes: list[ReferenceReadDish] = Field(min_length=1, max_length=MAX_REFERENCE_DISHES)


class ReferenceReadPurchase(HealthDTO):
    """Agent 只从服务端候选中选择 SKU 和包装数量。"""

    sku_id: str = Field(min_length=1, max_length=80)
    quantity: int = Field(ge=1, le=99, strict=True)
    candidate_keys: list[str] = Field(min_length=1, max_length=450)


class ReferenceReadProduct(HealthDTO):
    """Agent 只从本轮候选商品中选择商品身份，不决定规格和包装数量。"""

    product_id: str = Field(min_length=1, max_length=80)
    candidate_keys: list[str] = Field(min_length=1, max_length=450)


class ReferenceReadSelection(HealthDTO):
    """用已读原谱装配菜品，食材对应与缺口由服务端生成。"""

    use_read_recipes: Literal[True]
    auto_purchase_matches: Literal[True]
    meals: list[ReferenceReadMeal] = Field(min_length=1, max_length=3)
    product_matches: list[ReferenceReadProduct] = Field(default_factory=list, max_length=30)

    @field_validator("use_read_recipes", "auto_purchase_matches", mode="before")
    @classmethod
    def explicit_agreement(cls, value):
        """数字和字符串不能冒充明确启用的布尔开关。"""
        if value is not True:
            raise ValueError("须明确选择采用本轮已读原谱和商品匹配")
        return value

    @model_validator(mode="after")
    def unique_choices(self):
        """重复餐次和规格不能隐藏覆盖或重复包装数量。"""
        if len({meal.meal_type for meal in self.meals}) != len(self.meals):
            raise ValueError("参考餐次不能重复")
        if len({item.product_id for item in self.product_matches}) != len(self.product_matches):
            raise ValueError("相同商品须合并食材引用")
        keys = [key for item in self.product_matches for key in item.candidate_keys]
        if len(keys) != len(set(keys)):
            raise ValueError("每个候选食材只能选择一次")
        return self


class ReferenceTranslationCorrection(HealthDTO):
    """只修正本 Run 已选择原谱的中文展示，不重新选择餐次或商品。"""

    file_id: str = Field(min_length=1, max_length=64)
    chunk_id: str = Field(min_length=1, max_length=128)
    display_zh: RecipeChineseDisplay


class ReferenceOptionDish(HealthDTO):
    """用本次读取回执的选项标识菜谱及被替代的共用菜。"""

    recipe_option: str = Field(pattern=r"^r[0-9a-f]{16}$")
    display_zh: RecipeChineseDisplay | None = None
    cooking_minutes: int | None = Field(default=None, ge=1, le=1440, strict=True)
    alternative_for: list[UUID] = Field(default_factory=list, max_length=20)
    replaces_recipe_option: str | None = Field(default=None, pattern=r"^r[0-9a-f]{16}$")


class ReferenceOptionMeal(ReferenceReadMeal):
    """保存工具按选项编号选择餐次菜谱。"""

    dishes: list[ReferenceOptionDish] = Field(min_length=1, max_length=MAX_REFERENCE_DISHES)


class ReferenceOptionSelection(ReferenceReadSelection):
    """模型保存契约只接受菜谱选项。"""

    meals: list[ReferenceOptionMeal] = Field(min_length=1, max_length=3)


class ReferenceOptionTranslationCorrection(HealthDTO):
    """按首次保存提交的选项修正译文。"""

    recipe_option: str = Field(pattern=r"^r[0-9a-f]{16}$")
    display_zh: RecipeChineseDisplay


_read_selection = TypeAdapter(ReferenceOptionSelection | ReferenceReadSelection)


def apply_reference_translation_correction(original, corrections) -> dict:
    """沿用首次保存的全部选择，只覆盖明确指定原谱的译文。"""

    selected = deepcopy(original)
    baseline = deepcopy(original)
    for meal in baseline.get("meals", []):
        if isinstance(meal, dict) and isinstance(meal.get("dishes"), list):
            for dish in meal["dishes"]:
                if isinstance(dish, dict):
                    dish.pop("display_zh", None)
    validated = (
        _read_selection.validate_python(baseline)
        if "use_read_recipes" in original
        else ReferencePlanDraft.model_validate(baseline)
    )
    by_option = isinstance(validated, ReferenceOptionSelection)
    patch_model = ReferenceOptionTranslationCorrection if by_option else ReferenceTranslationCorrection
    fields = ("recipe_option",) if by_option else ("file_id", "chunk_id")
    patches = [patch_model.model_validate(item).model_dump(mode="json") for item in corrections]
    displays = {tuple(item[field] for field in fields): item["display_zh"] for item in patches}
    if not patches or len(displays) != len(patches):
        raise HealthVisionError("reference_translation_correction_invalid", "译文修正须指定不重复的已选菜谱", 422)
    dishes = [dish for meal in selected["meals"] for dish in meal["dishes"]]
    if displays.keys() - {tuple(dish[field] for field in fields) for dish in dishes}:
        raise HealthVisionError("reference_translation_correction_invalid", "译文修正只能引用首次已选菜谱", 422)
    for dish in dishes:
        if display := displays.get(tuple(dish[field] for field in fields)):
            dish["display_zh"] = display
    return type(validated).model_validate(selected).model_dump(mode="json")


async def assemble_reference_selection(context, payload, *, allow_purchase_fallback=False) -> "ReferencePlanDraft":
    """重验本轮读取来源后装配原 DTO，保存及发布仍由原 service 执行。"""
    from yuxi.services.health_meal_plan_service import require_planner_run
    from yuxi.services.reference_meal_plan_service import (
        bound_reference_context,
        recipe_document,
        same_reference_document,
        tool_payloads,
    )
    from yuxi.services.reference_meal_plan_types import ReferencePlanDraft
    from yuxi.services.reference_recipe_matching import parse_reference_recipe
    from yuxi.services.recipe_translation_service import cached_chinese_display
    from yuxi.storage.postgres.manager import pg_manager

    selected = _read_selection.validate_python(payload)
    async with pg_manager.get_async_session_context() as session:
        run, binding = await require_planner_run(session, context)
        current = await bound_reference_context(session, context.uid, binding)
        if {meal.meal_type for meal in selected.meals} != set(current["selection"]["meal_types"]):
            raise HealthVisionError("reference_meals_mismatch", "餐次须与用户明确选择一致", 422)
        receipts = await tool_payloads(session, run, "read_reference_recipe")
        if isinstance(selected, ReferenceOptionSelection):
            selected = _resolve_recipe_options(selected, receipts)
        opened = {(item["file_id"], item["chunk_id"]): item for item in receipts}
        reads = await tool_payloads(session, run, "find_reference_products")
        seen = {str(sku["sku_id"]): sku for read in reads for sku in read.get("catalog", [])}
        from yuxi.services.daily_commerce_service import group_catalog_products

        read_products = [product for read in reads for product in read.get("products", [])]
        if not read_products:
            read_products = group_catalog_products(list(seen.values()))
        seen_products = {str(product["product_id"]): product for product in read_products}
        for receipt in receipts:
            for group in receipt.get("recipe_check", {}).get("ingredient_matches", []):
                for product in group.get("candidate_products", []):
                    seen_products.setdefault(str(product["product_id"]), product)
        if not reads and not any(receipt.get("catalog_version") for receipt in receipts):
            raise HealthVisionError("reference_product_required", "请打开本轮菜谱并核对商城食材", 409)
        if not seen_products and selected.product_matches:
            raise HealthVisionError("reference_product_required", "本轮已读分类没有可选择的在售商品", 409)
        if any(item.product_id not in seen_products for item in selected.product_matches):
            raise HealthVisionError("reference_product_changed", "只能选择本轮已读取的商城商品", 409)

        documents, meals, issued_candidates, issued_products = {}, [], {}, {}
        for meal in selected.meals:
            dishes = []
            for choice in meal.dishes:
                key = (choice.file_id, choice.chunk_id)
                receipt = opened.get(key)
                if receipt is None:
                    raise HealthVisionError("reference_receipt_invalid", "餐单使用了本 Run 未打开的菜谱", 409)
                issued = receipt.get("recipe_check", {}).get("ingredient_matches")
                if not isinstance(issued, list) or any(
                    not isinstance(group, dict)
                    or not isinstance(group.get("candidate_key"), str)
                    or not isinstance(group.get("candidate_skus", []), list)
                    or not isinstance(group.get("candidate_products", []), list)
                    for group in issued
                ):
                    raise HealthVisionError("reference_receipt_invalid", "菜谱候选回执缺失，请重新读取原谱", 409)
                for group in issued:
                    issued_candidates[group["candidate_key"]] = {
                        str(candidate["sku_id"])
                        for candidate in group["candidate_skus"]
                        if isinstance(candidate, dict) and candidate.get("sku_id") is not None
                    }
                    issued_products[group["candidate_key"]] = {
                        str(candidate["product_id"])
                        for candidate in group.get("candidate_products", [])
                        if isinstance(candidate, dict) and candidate.get("product_id") is not None
                    }
                if key not in documents:
                    fresh = await recipe_document(session, *key)
                    if not same_reference_document(fresh, receipt):
                        raise HealthVisionError("source_invalidated", "菜谱正文已变化，请重新读取", 410)
                    parsed = parse_reference_recipe(fresh["content"])
                    if parsed is None or parsed.review_sections:
                        raise HealthVisionError("reference_quote_invalid", "菜谱完整食材或步骤仍需核对", 422)
                    documents[key] = fresh, parsed
                fresh, parsed = documents[key]
                dish = {
                    **choice.model_dump(mode="json", include={"alternative_for", "replaces_file_id"}),
                    "file_id": choice.file_id,
                    "chunk_id": choice.chunk_id,
                    "name": parsed.name,
                    "ingredients": list(parsed.ingredients),
                    "steps": list(parsed.steps),
                    "portion_quote": None,
                    "nutrition_quote": None,
                    "cooking_minutes": choice.cooking_minutes,
                    "display_zh": choice.display_zh.model_dump(mode="json") if choice.display_zh else None,
                }
                if dish["display_zh"] is None:
                    source = {
                        key: fresh[key]
                        for key in ("file_id", "chunk_id", "kb_id", "filename", "file_hash", "chunks_hash")
                    }
                    dish["display_zh"] = await cached_chinese_display(session, {**dish, "source": source})
                dishes.append(dish)
            meals.append({"meal_type": meal.meal_type, "dishes": dishes})
        products, gaps = _product_choices(
            meals,
            selected.product_matches,
            seen_products,
            issued_candidates=issued_products,
            allow_purchase_fallback=allow_purchase_fallback,
        )
        return ReferencePlanDraft.model_validate(
            {"meals": meals, "product_matches": products, "purchase_items": [], "purchase_gaps": gaps}
        )


def _resolve_recipe_options(selected, receipts) -> ReferenceReadSelection:
    """从当前运行的已读回执恢复原始来源编号。"""
    opened = {item["recipe_option"]: item for item in receipts if "recipe_option" in item}
    payload = selected.model_dump(mode="json")
    for meal in payload["meals"]:
        shared_options = {dish["recipe_option"] for dish in meal["dishes"] if not dish["alternative_for"]}
        for dish in meal["dishes"]:
            option = dish.pop("recipe_option")
            replaces = dish.pop("replaces_recipe_option")
            if option not in opened:
                raise HealthVisionError(
                    "reference_recipe_option_invalid", "请选择本轮已打开原谱回执中的 recipe_option", 422
                )
            if replaces is not None and (replaces not in shared_options or replaces not in opened):
                raise HealthVisionError(
                    "reference_recipe_option_invalid", "替代菜须引用本餐已选共用菜的 recipe_option", 422
                )
            receipt = opened[option]
            dish.update(
                file_id=receipt["file_id"],
                chunk_id=receipt["chunk_id"],
                replaces_file_id=opened[replaces]["file_id"] if replaces is not None else None,
            )
    return ReferenceReadSelection.model_validate(payload)


def _product_choices(meals, selections, seen, *, issued_candidates=None, allow_purchase_fallback=False):
    """把菜谱食材绑定到商品；规格、价格和库存留到购买动作再核对。"""
    from yuxi.services.reference_recipe_matching import reference_ingredient_candidates

    ingredients = tuple(
        dict.fromkeys(ingredient for meal in meals for dish in meal["dishes"] for ingredient in dish["ingredients"])
    )
    if any(item.product_id not in seen for item in selections):
        raise HealthVisionError("reference_product_changed", "只能选择本轮已读取的商城商品", 409)
    groups = reference_ingredient_candidates(ingredients, list(seen.values()))
    by_key = {group["candidate_key"]: group for group in groups}
    refs = {item.product_id: [] for item in selections}
    selected_keys = set()
    for item in selections:
        invalid = []
        for key in item.candidate_keys:
            group = by_key.get(key)
            issued = issued_candidates.get(key, set()) if issued_candidates is not None else None
            allowed = (
                {str(candidate["product_id"]) for candidate in group.get("candidate_products", [])} if group else set()
            )
            if issued is not None:
                allowed &= issued
            if group is None or item.product_id not in allowed:
                invalid.append(key)
                continue
            refs[item.product_id].append(group["ingredient"])
            selected_keys.add(key)
        if invalid and not allow_purchase_fallback:
            raise HealthVisionError("reference_ingredient_mismatch", "所选商品不属于菜谱回执中的候选组", 422)
    # 只在已识别食材的当前合法候选与已发出回执交集中推荐商品；不决定购买规格或数量。
    if issued_candidates is not None:
        for group in groups:
            key = group["candidate_key"]
            if key in selected_keys or group["status"] != "matched":
                continue
            allowed = {str(item["product_id"]) for item in group.get("candidate_products", [])}
            allowed &= issued_candidates.get(key, set())
            if allowed:
                product_id = min(allowed)
                refs.setdefault(product_id, []).append(group["ingredient"])
                selected_keys.add(key)
    gaps = _candidate_gaps(groups, selected_keys, allow_purchase_fallback)
    return [
        {"product_id": product_id, "ingredient_refs": ingredient_refs}
        for product_id, ingredient_refs in refs.items()
        if ingredient_refs
    ], gaps


def _candidate_gaps(groups, selected_keys, allow_purchase_fallback):
    """统一生成没有商品匹配的真实缺口。"""
    gaps = []
    for group in groups:
        ingredient = group["ingredient"]
        if group["candidate_key"] in selected_keys:
            continue
        if group["status"] == "cooking_water":
            gaps.append({"ingredient": ingredient, "reason": "not_sold", "detail": "原谱烹饪用水，不作为商城商品。"})
        elif group["status"] == "optional_not_selected":
            gaps.append(
                {
                    "ingredient": ingredient,
                    "reason": "optional_not_selected",
                    "detail": "原谱明确可选食材，本次未选择。",
                }
            )
        elif group["status"] == "matched":
            if not allow_purchase_fallback:
                raise HealthVisionError(
                    "reference_ingredient_mismatch", "请从该食材的candidate_products中选择商品", 422
                )
            gaps.append(
                {
                    "ingredient": ingredient,
                    "reason": "needs_confirmation",
                    "detail": "需自行购买：未能确认对应商城商品。",
                }
            )
        elif group["status"] in {"missing_product", "needs_confirmation"}:
            reason = "no_match" if group["status"] == "missing_product" else "needs_confirmation"
            detail = (
                "需自行购买：本轮商城商品名称中未找到对应食材。"
                if reason == "no_match"
                else "需自行购买并核对菜谱中的具体品种、形态和用量。"
            )
            gaps.append({"ingredient": ingredient, "reason": reason, "detail": detail})
        else:
            raise HealthVisionError("reference_purchase_reason_invalid", "食材匹配状态无法核对", 422)
    return gaps


def _purchase_choices(meals, selections, seen, *, issued_candidates=None, allow_purchase_fallback=False):
    """按商品名核对候选；Agent 只决定候选 SKU 与包装数。"""
    from yuxi.services.reference_recipe_matching import reference_ingredient_candidates

    ingredients = tuple(
        dict.fromkeys(ingredient for meal in meals for dish in meal["dishes"] for ingredient in dish["ingredients"])
    )
    if any(item.sku_id not in seen for item in selections):
        raise HealthVisionError("reference_product_changed", "只能选择本轮已读取的商城商品", 409)
    groups = reference_ingredient_candidates(ingredients, list(seen.values()))
    by_key = {group["candidate_key"]: group for group in groups}
    refs = {item.sku_id: [] for item in selections}
    quantities = {item.sku_id: item.quantity for item in selections}
    selected_keys = set()
    for item in selections:
        invalid = []
        for key in item.candidate_keys:
            group = by_key.get(key)
            issued = issued_candidates.get(key, set()) if issued_candidates is not None else None
            allowed = {str(candidate["sku_id"]) for candidate in group.get("candidate_skus", [])} if group else set()
            if issued is not None:
                allowed &= issued
            if group is None or item.sku_id not in allowed or key in selected_keys:
                invalid.append(key)
                continue
            refs[item.sku_id].append(group["ingredient"])
            selected_keys.add(key)
        if invalid and not allow_purchase_fallback:
            raise HealthVisionError("reference_ingredient_mismatch", "所选规格不属于菜谱回执中的候选组", 422)
    gaps = []
    for group in groups:
        ingredient = group["ingredient"]
        if group["candidate_key"] in selected_keys:
            continue
        if group["status"] == "cooking_water":
            gaps.append({"ingredient": ingredient, "reason": "not_sold", "detail": "原谱烹饪用水，不作为商城商品。"})
        elif group["status"] == "optional_not_selected":
            gaps.append(
                {
                    "ingredient": ingredient,
                    "reason": "optional_not_selected",
                    "detail": "原谱明确可选食材，本次未选择。",
                }
            )
        elif group["status"] == "matched":
            if not allow_purchase_fallback:
                raise HealthVisionError(
                    "reference_ingredient_mismatch", "请从该食材的candidate_skus中选择规格及包装数量", 422
                )
            gaps.append(
                {
                    "ingredient": ingredient,
                    "reason": "needs_confirmation",
                    "detail": "需自行购买：未能确认适合当前就餐成员和菜谱用量的包装规格。",
                }
            )
        elif group["status"] in {"missing_product", "needs_confirmation"}:
            reason = "no_match" if group["status"] == "missing_product" else "needs_confirmation"
            detail = (
                "需自行购买：本轮已查询的商城商品名称中未找到对应食材。"
                if reason == "no_match"
                else "需自行购买并核对菜谱中的具体品种、形态和用量。"
            )
            gaps.append(
                {
                    "ingredient": ingredient,
                    "reason": reason,
                    "detail": detail,
                }
            )
        else:
            raise HealthVisionError("reference_purchase_reason_invalid", "食材匹配状态无法核对", 422)
    items = [
        {"sku_id": sku_id, "quantity": quantities[sku_id], "ingredient_refs": ingredient_refs}
        for sku_id, ingredient_refs in refs.items()
        if ingredient_refs
    ]
    return items, gaps

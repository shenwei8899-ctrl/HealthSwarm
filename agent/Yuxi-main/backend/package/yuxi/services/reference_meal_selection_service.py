"""按本 Run 已打开的原谱装配参考稿，不让模型重写来源事实。"""

from copy import deepcopy
from typing import TYPE_CHECKING, Literal

from pydantic import Field, field_validator, model_validator

from yuxi.services.health_vision_types import HealthDTO, HealthVisionError
from yuxi.services.recipe_translation_types import RecipeChineseDisplay

if TYPE_CHECKING:
    from yuxi.services.reference_meal_plan_types import ReferencePlanDraft


class ReferenceReadDish(HealthDTO):
    """只选择本轮已打开的原谱，可另给中文展示和制作估时。"""

    file_id: str = Field(min_length=1, max_length=64)
    chunk_id: str = Field(min_length=1, max_length=128)
    display_zh: RecipeChineseDisplay | None = None
    cooking_minutes: int | None = Field(default=None, ge=1, le=1440, strict=True)


class ReferenceReadMeal(HealthDTO):
    """餐次必须明确，不能借选菜扩展用户选择范围。"""

    meal_type: Literal["breakfast", "lunch", "dinner"]
    dishes: list[ReferenceReadDish] = Field(min_length=1, max_length=5)


class ReferenceReadPurchase(HealthDTO):
    """包装数量必须显式给出，不代表个人食用量。"""

    sku_id: str = Field(min_length=1, max_length=80)
    quantity: int = Field(ge=1, le=99, strict=True)


class ReferenceReadSelection(HealthDTO):
    """明确采用程序的原谱装配和已读商品匹配，不接收原文副本。"""

    use_read_recipes: Literal[True]
    auto_purchase_matches: Literal[True]
    meals: list[ReferenceReadMeal] = Field(min_length=1, max_length=3)
    purchase_items: list[ReferenceReadPurchase] = Field(min_length=1, max_length=30)

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
        if len({item.sku_id for item in self.purchase_items}) != len(self.purchase_items):
            raise ValueError("相同规格须合并数量")
        return self


class ReferenceTranslationCorrection(HealthDTO):
    """只修正本 Run 已选择原谱的中文展示，不重新选择餐次或商品。"""

    file_id: str = Field(min_length=1, max_length=64)
    chunk_id: str = Field(min_length=1, max_length=128)
    display_zh: RecipeChineseDisplay


def apply_reference_translation_correction(original, corrections) -> dict:
    """沿用首次保存的全部选择，只覆盖明确指定原谱的译文。"""
    from yuxi.services.reference_meal_plan_types import ReferencePlanDraft

    model = ReferenceReadSelection if "use_read_recipes" in original else ReferencePlanDraft
    selected = deepcopy(original)
    baseline = deepcopy(original)
    for meal in baseline.get("meals", []):
        if isinstance(meal, dict) and isinstance(meal.get("dishes"), list):
            for dish in meal["dishes"]:
                if isinstance(dish, dict):
                    dish.pop("display_zh", None)
    model.model_validate(baseline)
    patches = [ReferenceTranslationCorrection.model_validate(item) for item in corrections]
    if not patches or len({(item.file_id, item.chunk_id) for item in patches}) != len(patches):
        raise HealthVisionError("reference_translation_correction_invalid", "译文修正须指定不重复的已选菜谱", 422)
    dishes = {(dish["file_id"], dish["chunk_id"]) for meal in selected["meals"] for dish in meal["dishes"]}
    if any((item.file_id, item.chunk_id) not in dishes for item in patches):
        raise HealthVisionError("reference_translation_correction_invalid", "译文修正只能引用首次已选菜谱", 422)
    displays = {(item.file_id, item.chunk_id): item.display_zh.model_dump(mode="json") for item in patches}
    for meal in selected["meals"]:
        for dish in meal["dishes"]:
            if display := displays.get((dish["file_id"], dish["chunk_id"])):
                dish["display_zh"] = display
    return model.model_validate(selected).model_dump(mode="json")


async def assemble_reference_selection(context, payload) -> "ReferencePlanDraft":
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

    selected = ReferenceReadSelection.model_validate(payload)
    async with pg_manager.get_async_session_context() as session:
        run, binding = await require_planner_run(session, context)
        current = await bound_reference_context(session, context.uid, binding)
        if {meal.meal_type for meal in selected.meals} != set(current["selection"]["meal_types"]):
            raise HealthVisionError("reference_meals_mismatch", "餐次须与用户明确选择一致", 422)
        receipts = await tool_payloads(session, run, "read_reference_recipe")
        opened = {(item["file_id"], item["chunk_id"]): item for item in receipts}
        reads = await tool_payloads(session, run, "find_reference_products")
        seen = {str(sku["sku_id"]): sku for read in reads for sku in read.get("catalog", [])}
        if not seen:
            raise HealthVisionError("reference_product_required", "请先按商城分类读取在售商品", 409)
        if any(item.sku_id not in seen for item in selected.purchase_items):
            raise HealthVisionError("reference_product_changed", "只能选择本轮已读取的商城商品", 409)

        documents, meals = {}, []
        for meal in selected.meals:
            dishes = []
            for choice in meal.dishes:
                key = (choice.file_id, choice.chunk_id)
                receipt = opened.get(key)
                if receipt is None:
                    raise HealthVisionError("reference_receipt_invalid", "餐单使用了本 Run 未打开的菜谱", 409)
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
        items, gaps = _purchase_choices(meals, selected.purchase_items, seen)
        return ReferencePlanDraft.model_validate({"meals": meals, "purchase_items": items, "purchase_gaps": gaps})


def _purchase_choices(meals, selections, seen):
    """按已读匹配生成原文对应；只剔除与原谱无关的模型附带规格。"""
    from yuxi.services.reference_recipe_matching import ingredient_food, product_food, reference_ingredient_matches

    ingredients = tuple(
        dict.fromkeys(ingredient for meal in meals for dish in meal["dishes"] for ingredient in dish["ingredients"])
    )
    selected_products = [seen[item.sku_id] for item in selections]
    chosen_matches = reference_ingredient_matches(ingredients, selected_products)
    known_matches = reference_ingredient_matches(ingredients, list(seen.values()))
    refs = {item.sku_id: [] for item in selections}
    gaps = []
    for chosen, known in zip(chosen_matches, known_matches, strict=True):
        ingredient = known["ingredient"]
        if chosen["status"] == "matched":
            refs[chosen["sku_id"]].append(ingredient)
        elif known["status"] == "cooking_water":
            gaps.append({"ingredient": ingredient, "reason": "not_sold", "detail": "原谱烹饪用水，不作为商城商品。"})
        elif chosen["status"] == "optional_not_selected":
            gaps.append(
                {
                    "ingredient": ingredient,
                    "reason": "optional_not_selected",
                    "detail": "原谱明确可选食材，本次未选择。",
                }
            )
        elif known["status"] == "matched":
            raise HealthVisionError("reference_product_required", "请明确选择匹配食材的 SKU 及包装数量", 422)
        elif known["status"] in {"missing_product", "needs_confirmation"}:
            reason = "no_match" if known["status"] == "missing_product" else "needs_confirmation"
            detail = (
                "需自行准备：本轮已查询的商城商品中未找到匹配项。"
                if reason == "no_match"
                else "需自行准备并核对原谱品种、形态和用量：尚未确认对应商城商品。"
            )
            gaps.append({"ingredient": ingredient, "reason": reason, "detail": detail})
        else:
            raise HealthVisionError("reference_purchase_reason_invalid", "食材匹配状态无法核对", 422)
    ingredient_foods = {ingredient_food(ingredient) for ingredient in ingredients}
    ingredient_foods.discard(None)
    for item in selections:
        if refs[item.sku_id]:
            continue
        food = product_food(str(seen[item.sku_id].get("product_name") or ""))
        if food is None or food in ingredient_foods:
            raise HealthVisionError("reference_ingredient_mismatch", "所选规格无法核对，请检查食材或库存", 422)
    items = [
        {"sku_id": item.sku_id, "quantity": item.quantity, "ingredient_refs": refs[item.sku_id]}
        for item in selections
        if refs[item.sku_id]
    ]
    if not items:
        raise HealthVisionError("reference_product_required", "菜品缺少已核对的商城食材，不能保存餐单", 422)
    return items, gaps

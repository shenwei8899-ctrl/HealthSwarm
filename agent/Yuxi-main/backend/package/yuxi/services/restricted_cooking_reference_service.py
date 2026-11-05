"""只展示受控做法资料，未核对个人限制时不形成餐单或采购结果。"""

from copy import deepcopy
import json
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from yuxi.services.health_meal_plan_types import CookingCandidateMealChoice
from yuxi.services.health_nutrition_service import input_fingerprint
from yuxi.services.health_vision_types import HealthDTO, HealthVisionError
from yuxi.services.reference_recipe_matching import ingredient_food

DATA_PATH = Path(__file__).parent / "data/restricted_cooking_references_v1.json"


class CookingReferenceSource(HealthDTO):
    """整理稿来源明确区别于逐字原文及医学适用性审核。"""

    title: str = Field(min_length=1, max_length=300)
    url: str = Field(min_length=1, max_length=1200, pattern=r"^https://")
    kind: Literal["source_based_notes"]
    hash_algorithm: Literal["sha256"]
    hash_scope: Literal["reference_without_source_content_hash_canonical_json_utf8"]
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    notes: str = Field(min_length=1, max_length=1200)


class ControlledCookingReference(HealthDTO):
    """有限整理稿只允许一个明确原料加水，不作过敏分类证明。"""

    id: str = Field(min_length=1, max_length=100)
    meal_types: list[Literal["breakfast", "lunch", "dinner"]] = Field(min_length=1, max_length=3)
    name: str = Field(min_length=1, max_length=120)
    ingredient_food: Literal["鸡蛋", "大米", "土豆", "胡萝卜"]
    ingredients: list[str] = Field(min_length=1, max_length=2)
    steps: list[str] = Field(min_length=1, max_length=20)
    no_added_oil: bool = Field(strict=True)
    no_added_salt: bool = Field(strict=True)
    source: CookingReferenceSource

    @model_validator(mode="after")
    def single_original_food(self):
        """原料身份只限制资料范围，不能据此推断个人可食用。"""
        identities = [ingredient_food(value) for value in self.ingredients]
        if (
            not self.no_added_oil
            or not self.no_added_salt
            or self.ingredient_food not in identities
            or any(value not in {self.ingredient_food, "水"} for value in identities)
            or len(set(self.meal_types)) != len(self.meal_types)
            or any(not step.strip() for step in self.steps)
        ):
            raise ValueError("整理稿必须为明确单一天然原料加水的无添加油盐做法")
        return self


def restricted_cooking_catalog(current):
    """按当前所选餐次返回完整整理稿及版本，不声明个人限制已核验。"""
    references = _load_references() if _candidate_context_allowed(current) else []
    meal_types = set(current["selection"]["meal_types"])
    items = [item for item in references if meal_types.intersection(item["meal_types"])]
    return {"catalog_hash": input_fingerprint({"schema_version": 1, "references": items}), "items": items}


def build_restricted_cooking_candidates(current, context_receipt, candidate_meals):
    """从本轮已读目录装配资料候选，不写预览、日计划或采购。"""
    if not isinstance(context_receipt, dict) or any(
        key not in context_receipt or context_receipt[key] != current[key] for key in ("selection", "members")
    ):
        raise HealthVisionError("reference_receipt_invalid", "做法资料回执与当前成员或餐次不一致", 409)
    if context_receipt.get("sources") != current.get("sources"):
        raise HealthVisionError("source_invalidated", "成员资料来源已变化，请重新读取做法资料", 410)
    catalog = restricted_cooking_catalog(current)
    if context_receipt.get("cooking_reference_candidates") != catalog:
        raise HealthVisionError("source_invalidated", "做法资料或已读候选目录已变化，请重新读取", 410)
    if not isinstance(candidate_meals, list) or not 1 <= len(candidate_meals) <= 3:
        raise HealthVisionError("reference_candidate_invalid", "须选择当前餐次的做法资料编号", 422)
    selections = [CookingCandidateMealChoice.model_validate(item) for item in candidate_meals]
    chosen_meals = [item.meal_type for item in selections]
    chosen_ids = [candidate_id for item in selections for candidate_id in item.candidate_ids]
    if (
        len(set(chosen_meals)) != len(chosen_meals)
        or set(chosen_meals) != set(current["selection"]["meal_types"])
        or len(set(chosen_ids)) != len(chosen_ids)
    ):
        raise HealthVisionError("reference_candidate_invalid", "做法资料不能重复或超出当前所选餐次", 422)
    references = {item["id"]: item for item in catalog["items"]}
    selections.sort(key=lambda item: ("breakfast", "lunch", "dinner").index(item.meal_type))
    meals, normalized = [], []
    for selection in selections:
        candidate_ids = sorted(selection.candidate_ids)
        if any(
            candidate_id not in references or selection.meal_type not in references[candidate_id]["meal_types"]
            for candidate_id in candidate_ids
        ):
            raise HealthVisionError("reference_candidate_invalid", "只能选择本轮已读且属于当前餐次的做法资料", 422)
        normalized.append({"meal_type": selection.meal_type, "candidate_ids": candidate_ids})
        meals.append({"meal_type": selection.meal_type, "dishes": [deepcopy(references[cid]) for cid in candidate_ids]})
    restrictions = _stated_restrictions(current["members"])
    return {
        "status": "reference_candidates",
        "scope": "cooking_reference",
        "plan_date": current["selection"]["plan_date"],
        "selection": deepcopy(current["selection"]),
        "members": deepcopy(current["members"]),
        "candidate_selection": normalized,
        "meals": meals,
        "restriction_verification": {
            "status": "unresolved",
            "restrictions": restrictions,
        },
        "purchase_items": [],
        "purchase_allowed": False,
        "unresolved_materials": [
            "实际原料、商品标签及配料完整性仍需核对。",
            "生产、储存和烹饪中的过敏原交叉接触情况仍需核对。",
            "现有过敏、忌口、不耐受及医嘱均未完成个人适用性核验。",
            "医嘱执行、个人份量和营养量尚未核定。",
        ],
        "notice": (
            "以下仅为按公开来源整理的做法资料候选，供核对参考；不是已安排餐单或个人适用推荐。"
            "原料标签、配料及交叉接触风险和医嘱仍待核对，不能据此认定个人可安全食用；"
            "未保存日计划，不生成采购。"
        ),
    }


def _load_references():
    """每次重读受控文件，整理稿内容或来源改变时不沿用旧回执。"""
    try:
        data = json.loads(DATA_PATH.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or set(data) != {"schema_version", "references"} or data["schema_version"] != 1:
            raise ValueError("未知整理稿版本")
        if not isinstance(data["references"], list) or not data["references"]:
            raise ValueError("整理稿目录为空")
        references = [ControlledCookingReference.model_validate(item).model_dump() for item in data["references"]]
        if len({item["id"] for item in references}) != len(references):
            raise ValueError("整理稿编号重复")
        for item in references:
            material = deepcopy(item)
            claimed = material["source"].pop("content_hash")
            if input_fingerprint(material) != claimed:
                raise ValueError("整理稿来源摘要不一致")
        return references
    except (OSError, UnicodeError, ValueError):
        raise HealthVisionError("reference_source_unavailable", "受控做法整理稿暂时无法完整核对", 503) from None


def _candidate_context_allowed(current):
    """有限原文仅控制资料开放，任何其他限制继续保留原追问路径。"""
    members = current["members"]
    fields = ("allergens", "avoidances", "intolerances", "doctor_instructions")
    if not members or any(member.get(field) is None for member in members for field in fields):
        return False
    limited_terms = {
        "麸质谷物",
        "麸质谷物过敏",
        "麸质",
        "麸质不耐受",
        "大豆",
        "含大豆",
        "大豆不耐受",
        "少吃重油重盐",
    }
    meat_terms = {"牛肉", "羊肉", "牛羊肉", "beef", "veal", "lamb", "mutton", "goat meat"}
    terms = {" ".join(item["text"].casefold().split()) for item in _stated_restrictions(members)}
    return bool(terms & limited_terms) and not terms - limited_terms - meat_terms


def _stated_restrictions(members):
    """逐成员保留限制原文及字段，不把资料候选解释为已核验。"""
    result = []
    for member in members:
        for field in ("allergens", "avoidances", "intolerances", "doctor_instructions"):
            values = member.get(field) or []
            if isinstance(values, str):
                values = [values]
            result.extend({"member_id": member["id"], "field": field, "text": value} for value in values if value)
    return result

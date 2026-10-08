"""照片观察的独立边界 oracle，不调用云模型。"""

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from pydantic import ValidationError

from yuxi.services import health_vision_provider as provider
from yuxi.services.health_vision_types import HealthVisionError, MealPayload


def meal_payload():
    """人工定义两张照片、两个视角与一个菜品，不由实现生成期望。"""
    return {
        "meal_type": "lunch",
        "eaten_at": "2026-10-05T12:00:00+08:00",
        "photos": [
            {"image_index": 0, "upload_id": str(uuid4()), "upload_page_index": 0},
            {"image_index": 1, "upload_id": str(uuid4()), "upload_page_index": 0},
        ],
        "items": [
            {
                "item_id": str(uuid4()),
                "name": "合成蔬菜",
                "visible_ingredients": ["青菜", "胡萝卜"],
                "locations": [
                    {"image_index": 0, "bbox": [0.1, 0.2, 0.8, 0.9]},
                    {"image_index": 1, "bbox": [0.2, 0.1, 0.7, 0.8]},
                ],
            }
        ],
    }


def test_meal_observations_roundtrip_and_legacy_defaults():
    """观察不会产生重量或营养，旧草稿及人工項保持无虚构来源。"""
    raw = meal_payload()
    dto = MealPayload.model_validate(raw).model_dump(mode="json")
    assert dto["photos"] == raw["photos"]
    assert dto["items"][0]["visible_ingredients"] == ["青菜", "胡萝卜"]
    assert dto["items"][0]["locations"] == raw["items"][0]["locations"]
    assert dto["items"][0]["grams"] is None and dto["items"][0]["share_ratio"] is None
    assert "nutrients" not in dto["items"][0]
    legacy = MealPayload.model_validate(
        {
            "meal_type": "lunch",
            "eaten_at": raw["eaten_at"],
            "items": [{"item_id": str(uuid4()), "name": "人工项"}],
        }
    ).model_dump(mode="json")
    assert legacy["photos"] == []
    assert legacy["items"][0]["locations"] == [] and legacy["items"][0]["visible_ingredients"] == []


@pytest.mark.parametrize(
    "change",
    [
        "outside",
        "zero",
        "inverted",
        "nan",
        "short",
        "missing_photo",
        "duplicate_location",
        "duplicate_photo",
        "wrong_order",
        "empty_ingredient",
        "long_ingredient",
        "too_many_ingredients",
        "negative_index",
        "float_index",
        "foreign_location_key",
    ],
)
def test_invalid_meal_observations_fail_closed(change):
    """归一化框与视角绑定都在真实 DTO 边界拒绝。"""
    raw = meal_payload()
    item = raw["items"][0]
    boxes = {
        "outside": [-0.1, 0.2, 0.8, 0.9],
        "zero": [0.1, 0.2, 0.1, 0.9],
        "inverted": [0.8, 0.2, 0.1, 0.9],
        "nan": [float("nan"), 0.2, 0.8, 0.9],
        "short": [0.1, 0.2, 0.8],
    }
    if change in boxes:
        item["locations"][0]["bbox"] = boxes[change]
    elif change == "missing_photo":
        raw["photos"].pop()
    elif change == "duplicate_location":
        item["locations"] = [item["locations"][0]] * 2
    elif change == "duplicate_photo":
        raw["photos"][1]["upload_id"] = raw["photos"][0]["upload_id"]
    elif change == "wrong_order":
        raw["photos"].reverse()
    elif change == "empty_ingredient":
        item["visible_ingredients"] = ["   "]
    elif change == "long_ingredient":
        item["visible_ingredients"] = ["a" * 81]
    elif change == "too_many_ingredients":
        item["visible_ingredients"] = ["青菜"] * 21
    elif change == "negative_index":
        item["locations"][0]["image_index"] = -1
    elif change == "float_index":
        item["locations"][0]["image_index"] = 0.5
    else:
        item["locations"][0]["confidence"] = 1
    with pytest.raises(ValidationError):
        MealPayload.model_validate(raw)


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["missing_photo", "duplicate_location", "zero", "ingredient_nutrition", "upload_id"])
async def test_model_cannot_invent_photo_or_nutrition(monkeypatch, change):
    """模型返回的序号须属于实际外发图片，不追加自动纠正调用。"""
    raw = deepcopy(meal_payload()["items"][0])
    raw.pop("item_id")
    if change == "missing_photo":
        raw["locations"][1]["image_index"] = 2
    elif change == "duplicate_location":
        raw["locations"][1]["image_index"] = 0
    elif change == "zero":
        raw["locations"][0]["bbox"] = [0.1, 0.2, 0.1, 0.9]
    elif change == "ingredient_nutrition":
        raw["visible_ingredients"] = [{"name": "米", "protein_g": 2}]
    else:
        raw["upload_id"] = str(uuid4())
    call = AsyncMock(return_value=({"items": [raw]}, {"model": "fixed"}))
    monkeypatch.setattr(provider, "call_json_model", call)
    with pytest.raises(HealthVisionError) as rejected:
        await provider.recognize_meal("synthetic/fixed", [b"first", b"second"], SimpleNamespace())
    assert rejected.value.code == "model_schema_invalid" and call.await_count == 1

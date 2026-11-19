"""普通咨询最终答复中的菜品展示数据。"""

import json
import re
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError


class DishSuggestion(BaseModel):
    """一项可直接显示的饮食选择。"""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=100)
    reason: str = Field(min_length=1, max_length=400)


DISH_SUGGESTIONS = TypeAdapter(Annotated[list[DishSuggestion], Field(max_length=6)])
SECTION = "\n<dish_suggestions>"
OFFER_MARKER = re.compile(r"\[食材包:[^\]\n]*(?:\]|$)")


def public_consultation_text(content: str) -> str:
    """移除旧采购标记。"""
    return OFFER_MARKER.sub("", content).strip()


def split_dish_suggestions(content: str) -> tuple[str, list[dict]]:
    """从最终模型文本提取有界的结构化建议，保留普通正文。"""
    text, separator, encoded = ("\n" + content).partition(SECTION)
    text = public_consultation_text(text)
    if not separator or not text or not encoded.rstrip().endswith("</dish_suggestions>"):
        return text, []
    payload = encoded.rstrip().removesuffix("</dish_suggestions>").strip()
    if len(payload) > 5000:
        return text, []
    try:
        cards = DISH_SUGGESTIONS.validate_python(json.loads(payload))
    except (ValidationError, ValueError):
        return text, []
    return text, [card.model_dump() for card in cards]


def stored_dish_suggestions(metadata: dict | None) -> list[dict] | None:
    """从已发布答复提取同轮卡片。"""
    try:
        fields = (metadata or {}).get("additional_kwargs", {})
        payload = fields.get("dish_suggestions")
        if payload is None:
            return None
        cards = DISH_SUGGESTIONS.validate_python(payload)
    except (AttributeError, ValidationError):
        return []
    return [card.model_dump() for card in cards]

"""营养候选导入只做准备，不隐式审核或发布。"""

import json
from typing import Literal
from uuid import UUID

from pydantic import Field, JsonValue, model_validator

from yuxi.services.health_vision_types import HealthDTO
from yuxi.services.health_nutrition_service import input_fingerprint


class NutritionImportInput(HealthDTO):
    """固定单位的有限 JSON 批次，每行保留原字段供核对。"""

    client_request_id: UUID
    kind: Literal["food", "recipe"]
    rows: list[dict[str, JsonValue]] = Field(min_length=1, max_length=500)
    units: Literal["per_100g:kcal,g,mg"] = "per_100g:kcal,g,mg"

    @model_validator(mode="after")
    def size_limit(self):
        """拒绝超大候选，不将任意文件作为可执行导入脚本。"""
        if len(json.dumps(self.rows, ensure_ascii=False).encode()) > 1_000_000:
            raise ValueError("单批候选正文不能超过1MB")
        return self

    def fingerprint(self):
        """重试沿用同一候选批次。"""
        return input_fingerprint(self.model_dump(mode="json"))

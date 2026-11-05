"""人民币价格批准和费用上界，零值与缺失分别处理。"""

from datetime import datetime
from decimal import Decimal, ROUND_CEILING
from typing import Literal

from pydantic import Field, model_validator

from yuxi.services.health_vision_types import HealthDTO

MAX_CALL_CEILING_CNY = Decimal("40")
HEALTH_BUDGET_PURPOSES = {"consultation", "indicator_review", "diet_analysis", "meal", "report"}


class HealthAiOpeningInput(HealthDTO):
    """管理员核对启用当月已发生及未决费用后登记一次期初占用。"""

    occupied_cny: Decimal = Field(ge=0, max_digits=18, decimal_places=6)
    evidence: str = Field(min_length=10, max_length=2000)
    verified: Literal[True]


class HealthAiPriceInput(HealthDTO):
    """管理员核验整个请求计费上界后登记，不能仅填写宣传单价。"""

    kind: Literal["model", "ocr"]
    billing_mode: Literal["paid", "free_quota"] = "paid"
    stops_when_quota_exhausted: Literal[True] | None = None
    model_spec: str = Field(default="", max_length=256)
    ocr_endpoint: str = Field(default="", max_length=512)
    currency: Literal["CNY"] = "CNY"
    input_cny_per_million: Decimal | None = Field(default=None, ge=0, le=10000, max_digits=14, decimal_places=6)
    output_cny_per_million: Decimal | None = Field(default=None, ge=0, le=10000, max_digits=14, decimal_places=6)
    max_input_tokens: int | None = Field(default=None, ge=1, le=2000000, strict=True)
    max_output_tokens: int | None = Field(default=None, ge=1, le=32768, strict=True)
    fixed_cny_per_page: Decimal | None = Field(default=None, ge=0, le=40, max_digits=10, decimal_places=6)
    valid_until: datetime
    evidence: str = Field(min_length=10, max_length=2000)
    upper_bound_verified: Literal[True]

    @model_validator(mode="after")
    def complete_price(self):
        """只接受包含所有计费项的模型上界或 OCR 单页固定收费。"""
        if self.valid_until.tzinfo is None:
            raise ValueError("价格有效期必须包含时区")
        token_fields = (
            self.input_cny_per_million,
            self.output_cny_per_million,
            self.max_input_tokens,
            self.max_output_tokens,
        )
        if self.kind == "model":
            if (
                not self.model_spec
                or self.ocr_endpoint
                or self.fixed_cny_per_page is not None
                or any(v is None for v in token_fields)
            ):
                raise ValueError("模型价格需要输入输出单价、供应商输入硬上限及输出上限")
        elif (
            not self.ocr_endpoint.startswith("https://")
            or self.model_spec
            or self.fixed_cny_per_page is None
            or any(v is not None for v in token_fields)
        ):
            raise ValueError("OCR 需要 HTTPS 端点和涵盖所有费用的单页固定价格")
        if self.billing_mode == "free_quota":
            if self.kind != "ocr" or self.stops_when_quota_exhausted is not True or self.fixed_cny_per_page != 0:
                raise ValueError("免费额度仅支持 OCR，须确认耗尽即停止且单页费用为零")
        elif self.stops_when_quota_exhausted is not None:
            raise ValueError("耗尽停止声明仅用于免费 OCR")
        elif not 0 < self.ceiling_cny <= MAX_CALL_CEILING_CNY:
            raise ValueError("单次可证明费用上界须大于零且不超过40元")
        return self

    @property
    def ceiling_cny(self) -> Decimal:
        """用人民币百万分之一向上取整，不低估预留。"""
        if self.kind == "ocr":
            return self.fixed_cny_per_page
        return round_charge(
            (self.max_input_tokens * self.input_cny_per_million + self.max_output_tokens * self.output_cny_per_million)
            / 1000000
        )


def round_charge(amount: Decimal) -> Decimal:
    """费用按微元向上取整。"""
    return amount.quantize(Decimal("0.000001"), rounding=ROUND_CEILING)

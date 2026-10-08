"""分析模型只能选择服务器来源或提出补充问题。"""

from typing import Annotated
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo
from uuid import UUID

from pydantic import Field, model_validator

from yuxi.services.health_vision_types import HealthDTO


class DietAnalysisSelection(HealthDTO):
    """分析范围限定为一个已确认餐次及其确认版本。"""

    record_id: UUID
    source_version: Annotated[int, Field(strict=True, gt=0)]


class DietAnalysisPeriod(HealthDTO):
    """以北京时间自然日定义日、7日或30日分析窗口。"""

    period_days: Annotated[int, Field(strict=True)]
    end_date: date

    @model_validator(mode="after")
    def supported_window(self):
        """窗口口径只接受已定义的三种天数。"""
        if self.period_days not in (1, 7, 30):
            raise ValueError("分析窗口仅支持1、7或30天")
        try:
            start = self.end_date - timedelta(days=self.period_days - 1)
            datetime.combine(start, time.min, tzinfo=ZoneInfo("Asia/Shanghai")).astimezone(UTC)
        except OverflowError:
            raise ValueError("分析窗口起点超出日期范围") from None
        return self


class DietAnalysisFeedbackSource(HealthDTO):
    """持久化分析所引用的当前账号反馈版本。"""

    feedback_id: UUID
    version: Annotated[int, Field(strict=True, gt=0)]


class DietAnalysisAnswer(HealthDTO):
    """最终选择与问题互斥，不接受营养值或审核结论。"""

    record_id: UUID | None = None
    source_version: Annotated[int, Field(strict=True, gt=0)] | None = None
    period_days: Annotated[int, Field(strict=True)] | None = None
    end_date: date | None = None
    questions: list[Annotated[str, Field(min_length=1, max_length=200)]] = Field(default_factory=list, max_length=3)

    @model_validator(mode="after")
    def require_selection_or_questions(self):
        """拒绝空答案、不完整来源和双重输出。"""
        selected = self.record_id is not None and self.source_version is not None
        period = self.period_days is not None and self.end_date is not None
        if (
            sum((bool(self.questions), selected, period)) != 1
            or (self.record_id is None) != (self.source_version is None)
            or (self.period_days is None) != (self.end_date is None)
        ):
            raise ValueError("请选择餐次与确认版本，或提出补充问题")
        if period:
            DietAnalysisPeriod(period_days=self.period_days, end_date=self.end_date)
        if any(not question.strip() for question in self.questions):
            raise ValueError("补充问题不能为空")
        return self

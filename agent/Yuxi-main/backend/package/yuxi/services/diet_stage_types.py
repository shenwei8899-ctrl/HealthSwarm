"""阶段输入与日期、计次的确定性规则。"""

import calendar
from datetime import date, datetime, timedelta
from typing import Annotated, Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from pydantic import Field, model_validator

from yuxi.services.health_vision_types import HealthDTO, HealthVisionError

ShortText = Annotated[str, Field(min_length=1, max_length=200)]


class StageAction(HealthDTO):
    """一次任务目标次数为一，习惯可重复但不推断完成。"""

    id: UUID | None = None
    title: ShortText
    target: Annotated[int, Field(strict=True, ge=1, le=7)] = 1
    count: Annotated[int, Field(strict=True, ge=0, le=7)] = 0

    @model_validator(mode="after")
    def within_target(self):
        """次数不得超过目标，不接受空白标题。"""
        if self.count > self.target or not self.title.strip():
            raise ValueError("请填写有效行动和次数")
        return self


class StageWrite(HealthDTO):
    """冻结完整写入；同一请求键不能更换内容。"""

    client_request_id: UUID
    expected_version: Annotated[int, Field(strict=True, ge=0)]
    profile_version: Annotated[int, Field(strict=True, ge=1)] | None = None
    goals: list[Annotated[str, Field(min_length=1, max_length=80)]] = Field(min_length=1, max_length=2)
    actions: list[StageAction] = Field(min_length=1, max_length=5)
    draft_id: UUID
    previous_stage_id: UUID | None = None

    @model_validator(mode="after")
    def unique_goals(self):
        """去重前即拒绝重复及空白目标。"""
        if any(not text.strip() for text in self.goals) or len(set(self.goals)) != len(self.goals):
            raise ValueError("请选择一至两个不同目标")
        return self


class WeekWrite(HealthDTO):
    """提交绝对完成次数，避免客户端重放增量。"""

    client_request_id: UUID
    expected_version: Annotated[int, Field(strict=True, ge=1)]
    actions: list[StageAction] = Field(min_length=1, max_length=5)


class StageGenerate(HealthDTO):
    """普通读取不生成；建议和复盘显式使用既有用途同意。"""

    client_request_id: UUID
    kind: Literal["draft", "review", "week"]
    stage_id: UUID | None = None
    goals: list[ShortText] = Field(default_factory=list, max_length=2)
    note: str = Field(default="", max_length=1000)


class StageDraft(HealthDTO):
    """模型只建议行为目标和可执行任务。"""

    goals: list[Annotated[str, Field(min_length=1, max_length=80)]] = Field(min_length=1, max_length=2)
    actions: list[StageAction] = Field(min_length=1, max_length=5)
    reason: str = Field(min_length=1, max_length=1200)


class StageSummary(HealthDTO):
    """报告差值由程序单独展示，模型不输出营养阈值或临床结论。"""

    summary: str = Field(min_length=1, max_length=2400)
    observations: list[ShortText] = Field(default_factory=list, max_length=4)
    next_steps: list[ShortText] = Field(default_factory=list, max_length=3)


def stage_today():
    """统一北京时间日期。"""
    return datetime.now(ZoneInfo("Asia/Shanghai")).date()


def review_date(start):
    """三个自然月，月底截到实际月末。"""
    month = start.year * 12 + start.month - 1 + 3
    year, month = divmod(month, 12)
    return date(year, month + 1, min(start.day, calendar.monthrange(year, month + 1)[1]))


def week_window(start, stop, day):
    """连续七天，阶段末周不延伸到未来阶段。"""
    if day < start or day >= stop:
        raise HealthVisionError("stage_week_closed", "该日期不在本阶段内", 409)
    first = start + timedelta(days=((day - start).days // 7) * 7)
    return first, min(first + timedelta(days=7), stop)

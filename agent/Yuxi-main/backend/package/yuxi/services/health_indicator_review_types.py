"""指标回顾的固定日期和版本选择，不含模型参数。"""

from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from uuid import UUID

from pydantic import Field, model_validator

from yuxi.services.health_vision_types import HealthDTO


class IndicatorRecordRef(HealthDTO):
    """客户端只能选择实际记录的版本。"""

    record_id: UUID
    version: int = Field(gt=0, strict=True)


class IndicatorSelection(HealthDTO):
    """北京时间自然日范围，空选择表示范围内最近一百条。"""

    start_date: date
    end_date: date
    records: list[IndicatorRecordRef] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def bounded_window(self):
        """拒绝倒序、过长和重复记录，保留每个来源版本。"""
        if not 0 <= (self.end_date - self.start_date).days < 366:
            raise ValueError("请选择不超过366天的日期范围")
        if len({item.record_id for item in self.records}) != len(self.records):
            raise ValueError("记录不能重复")
        self.records.sort(key=lambda item: str(item.record_id))
        return self


def indicator_review(payload, fields, kind):
    """程序统计只解释所选事实，不推断诊断或填补测量值。"""
    rows = payload["records"]
    groups = {}
    for row in rows:
        condition = row.get("condition", "same_observation")
        groups.setdefault(condition, []).append(row)
    summaries = []
    for condition, items in groups.items():
        statistics = {}
        for field in fields:
            values = [Decimal(str(item[field])) for item in items]
            statistics[field] = {
                "count": len(values),
                "minimum": str(min(values)),
                "maximum": str(max(values)),
                "mean": str((sum(values) / len(values)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
            }
        summaries.append({"condition": condition, "statistics": statistics})
    questions = []
    if not rows:
        questions.append("该范围没有可用记录，请补充实际测量时间、原值和测量条件。")
    if payload["truncated"]:
        questions.append("当前仅回顾最近100条，请缩短日期范围或明确选择记录。")
    if kind == "blood_pressure":
        questions.append("如需进一步解释，请补充测量前休息情况及是否连续复测。")
    elif kind == "blood_lipids":
        questions.append("如需进一步解释，请补充本次检测是否空腹及报告参考范围。")
    else:
        questions.append("如需进一步解释，请补充测量方式及进餐、运动与测量的时间关系。")
    return {
        "status": "facts_ready" if rows else "no_data",
        "statistics_scope": "returned_records_only",
        "groups": summaries,
        "questions": questions,
        "missing_context": {
            "blood_pressure": ["rest_before_measurement", "repeat_measurement"],
            "blood_lipids": ["fasting", "laboratory_reference_range"],
            "blood_glucose": ["measurement_method", "meal_exercise_timing"],
        }[kind],
        "reviewed_explanations": [],
        "citations": [],
        "evidence_status": "not_requested",
        "individual_recommendation": None,
    }

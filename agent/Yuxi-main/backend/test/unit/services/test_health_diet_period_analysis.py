"""周期缺失、独立手算、反馈分母和模型窗口选择的事实验证。"""

from datetime import date
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from test.unit.services.test_health_diet_analysis import synthetic_record
from yuxi.agents.toolkits.diet_analyst import analyze_confirmed_period as period_tool
from yuxi.services.health_diet_analysis_service import analyze_confirmed_period
from yuxi.services.health_diet_analysis_types import DietAnalysisAnswer, DietAnalysisPeriod


@pytest.mark.parametrize("period_days", [1, 7, 30])
def test_period_known_sums_do_not_replace_missing_or_unrecorded_days(period_days):
    """120加未知不能变成完整120，反馈不能改变营养或解释趋势。"""
    first, unknown = synthetic_record(), synthetic_record()
    unknown.snapshot["nutrition"]["totals"]["energy_kcal"] = None
    unknown.snapshot["meal"]["eaten_at"] = "2026-10-06T16:00:00+00:00"
    confirmation = SimpleNamespace(id=str(uuid4()), draft_id=str(uuid4()), draft_version=1)
    feedback = SimpleNamespace(id=str(uuid4()), version=2, details={"tags": ["too_salty"], "consumption": "half"})
    period = DietAnalysisPeriod(period_days=period_days, end_date=date(2026, 10, 7))
    result = analyze_confirmed_period(
        first.member_id, period, [(first, confirmation), (unknown, confirmation)], [feedback]
    )
    assert result["nutrition"]["totals"]["energy_kcal"] == {
        "recorded_total": None,
        "known_sum": "120.00",
        "known_records": 1,
        "missing_records": 1,
    }
    assert result["nutrition"]["totals"]["protein_g"]["recorded_total"] == "12.00"
    assert result["nutrition"]["totals"]["sodium_mg"]["known_sum"] is None
    assert result["coverage"]["days_with_records"] == 1
    assert len(result["coverage"]["dates_without_records"]) == period_days - 1
    assert result["days"][-1]["record_count"] == 2
    if period_days > 1:
        assert result["days"][0]["nutrition"]["protein_g"]["recorded_total"] is None
    assert result["feedback"]["tag_counts"] == {"too_salty": 1}
    assert result["feedback"]["consumption_counts"] == {"half": 1}
    assert result["feedback"]["record_denominator"] == 2
    assert result["feedback"]["records_without_feedback"] == 1
    assert result["feedback"]["nutrition_recalculated"] is False
    assert result["feedback_sources"] == [{"feedback_id": feedback.id, "version": 2}]
    assert result["trend"]["direction"] is None
    assert result["personal_target"] is None


def test_empty_period_and_true_zero_are_distinct():
    """空窗口未知，有来源真实零值则保留零。"""
    period = DietAnalysisPeriod(period_days=7, end_date=date(2026, 10, 7))
    empty = analyze_confirmed_period("member", period, [], [], invalidated=1)
    assert empty["coverage"]["record_count"] == 0 and empty["coverage"]["excluded_invalidated_records"] == 1
    assert empty["nutrition"]["totals"]["energy_kcal"]["known_sum"] is None
    assert len(empty["coverage"]["dates_without_records"]) == 7
    record = synthetic_record()
    record.snapshot["nutrition"]["totals"]["energy_kcal"] = "0"
    confirmed = SimpleNamespace(id=str(uuid4()), draft_id=str(uuid4()), draft_version=1)
    zero = analyze_confirmed_period("member", period, [(record, confirmed)], [])
    assert zero["nutrition"]["totals"]["energy_kcal"]["recorded_total"] == "0"


@pytest.mark.parametrize(
    "body",
    [
        {"period_days": True, "end_date": "2026-10-07"},
        {"period_days": 2, "end_date": "2026-10-07"},
        {"period_days": 7, "end_date": "0001-01-01"},
        {"period_days": 1, "end_date": "0001-01-01"},
        {"period_days": 7, "end_date": "0001-01-07"},
        {"period_days": 30, "end_date": "0001-01-20"},
        {"period_days": 7},
        {"end_date": "2026-10-07"},
        {"period_days": 7, "end_date": "2026-10-07", "record_id": str(uuid4()), "source_version": 1},
        {"period_days": 7, "end_date": "2026-10-07", "questions": ["哪天？"]},
        {"period_days": 7, "end_date": "2026-10-07", "energy_kcal": 120},
    ],
)
def test_period_final_rejects_forged_or_ambiguous_window(body):
    """选择结构在模型JSON边界互斥，不能附加营养或混入单餐。"""
    with pytest.raises(ValidationError):
        DietAnalysisAnswer.model_validate(body)


def test_period_tool_schema_hides_identity():
    """周期工具只接收自然日窗口，运行身份不可由模型指定。"""
    assert set(period_tool.tool_call_schema.model_json_schema()["properties"]) == {"period_days", "end_date"}
    selected = DietAnalysisAnswer.model_validate({"period_days": 30, "end_date": "2026-10-07"})
    assert selected.period_days == 30 and selected.end_date == date(2026, 10, 7)

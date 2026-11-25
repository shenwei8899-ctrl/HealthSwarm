"""阶段日期、原始报告、旧目标入口及事实边界。"""

from copy import deepcopy
from datetime import date
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from yuxi.services.diet_stage_guard import require_stage_goal_entry
from yuxi.services.diet_stage_plan_history import without_behavior_goals
from yuxi.services.diet_stage_sources import frozen_review_valid, report_comparisons
from yuxi.services.diet_stage_tasks import model_facts, validate_behavior_result
from yuxi.services.diet_stage_types import StageAction, StageDraft, StageWrite, review_date, week_window
from yuxi.services.health_vision_types import HealthVisionError


@pytest.mark.parametrize(
    ("start", "expected"),
    [
        ("2026-11-25", "2027-02-25"),
        ("2026-11-30", "2027-02-28"),
        ("2027-11-30", "2028-02-29"),
    ],
)
def test_three_calendar_months_respect_actual_month_end(start, expected):
    assert review_date(date.fromisoformat(start)).isoformat() == expected


def test_action_weeks_start_on_confirmation_day_and_end_inside_stage():
    start, stop = date(2026, 11, 25), date(2027, 2, 25)
    assert week_window(start, stop, date(2026, 12, 1)) == (start, date(2026, 12, 2))
    assert week_window(start, stop, date(2027, 2, 24)) == (date(2027, 2, 24), stop)
    with pytest.raises(HealthVisionError):
        week_window(start, stop, stop)


def test_blank_duplicate_and_too_many_goals_cannot_be_confirmed():
    body = dict(
        client_request_id=uuid4(),
        expected_version=0,
        profile_version=1,
        draft_id=uuid4(),
        actions=[{"title": "准备早餐"}],
    )
    for goals in ([" "], ["目标", "目标"], ["一", "二", "三"]):
        with pytest.raises(ValidationError):
            StageWrite(**body, goals=goals)
    with pytest.raises(ValidationError):
        StageAction(title="记录", target=1, count=2)


def test_model_cannot_add_clinical_or_source_fields_to_structured_draft():
    with pytest.raises(ValidationError):
        StageDraft(goals=["规律三餐"], actions=[{"title": "准备早餐"}], reason="先从行为开始", sodium_target=100)


def test_legacy_goal_writes_blocked_but_unrelated_profile_changes_remain_allowed():
    original = {
        "diet_stage_managed": True,
        "goal": "规律三餐",
        "health_goals": [],
        "dietary_details": {"goals": ["规律三餐"], "allergies": []},
    }
    for field in ("goal", "health_goals", "dietary_details"):
        changed = deepcopy(original)
        changed[field] = (
            {"goals": ["新目标"]} if field == "dietary_details" else [] if field == "health_goals" else "新目标"
        )
        if changed == original:
            changed[field] = [{"description": "新目标"}]
        with pytest.raises(HTTPException) as error:
            require_stage_goal_entry(original, changed)
        assert error.value.status_code == 409
    changed = deepcopy(original)
    changed["dietary_details"]["allergies"] = ["测试食材"]
    require_stage_goal_entry(original, changed)
    require_stage_goal_entry({}, {"goal": "首次目标"})


def observation(day, value, *, unit="mmol/L", fasting="yes", key=None):
    return {
        "id": key or str(uuid4()),
        "name": "测试指标",
        "observation_code": "glucose",
        "observed_at": day,
        "value_raw": str(value),
        "value_numeric": str(value),
        "unit_raw": unit,
        "fasting": fasting,
    }


def test_report_order_uses_exam_date_and_baseline_before_phase_not_upload_order():
    rows = [observation("2026-12-01", 5), observation("2026-10-01", 7), observation("2026-11-20", 6)]
    window = {"start_date": "2026-11-01", "end_date": "2026-12-31"}
    item = report_comparisons(rows, window)[0]
    assert item["previous"]["observed_at"] == "2026-10-01"
    assert item["current"]["observed_at"] == "2026-12-01"
    assert item["delta"] == "-2"
    assert "临床" in item["note"]


@pytest.mark.parametrize("change", [{"unit": "mg/dL"}, {"fasting": "unknown"}])
def test_unit_and_sampling_ambiguity_never_produce_difference(change):
    rows = [observation("2026-10-01", 7), observation("2026-12-01", 5, **change)]
    assert report_comparisons(rows, {"start_date": "2026-11-01", "end_date": "2026-12-31"})[0]["delta"] is None


def test_same_day_duplicates_are_not_arbitrarily_chosen_for_comparison():
    rows = [observation("2026-10-01", 7), observation("2026-12-01", 5), observation("2026-12-01", 4)]
    assert report_comparisons(rows, {"start_date": "2026-11-01", "end_date": "2026-12-31"})[0]["delta"] is None


def test_single_report_is_baseline_and_unknown_code_cannot_be_name_merged():
    rows = [observation("2026-12-01", 5)]
    rows.append({**observation("2026-10-01", 7), "observation_code": "unknown"})
    item = report_comparisons(rows, {"start_date": "2026-11-01", "end_date": "2026-12-31"})[0]
    assert item["previous"] is None and item["delta"] is None


def test_two_old_reports_cannot_be_shown_as_change_within_current_phase():
    rows = [observation("2026-01-01", 7), observation("2026-02-01", 5)]
    assert report_comparisons(rows, {"start_date": "2026-11-01", "end_date": "2026-12-31"}) == []


def test_frozen_summary_accepts_new_sources_but_not_withdrawn_or_corrected_sources():
    old = {key: [] for key in ("records", "reports", "memories", "conversations", "feedback")}
    old["records"] = [{"id": "r", "version": 1}]
    fresh = deepcopy(old)
    fresh["reports"].append({"id": "new", "value_raw": "5"})
    assert frozen_review_valid(old, fresh)
    fresh["records"][0]["version"] = 2
    assert not frozen_review_valid(old, fresh)
    fresh["records"] = []
    assert not frozen_review_valid(old, fresh)


def test_only_behavior_fields_can_be_ignored_when_reading_old_plan():
    old = {"goal": "旧目标", "dietary_details": {"goals": ["旧目标"], "allergies": ["测试"]}}
    new = {
        "goal": "新目标",
        "diet_stage_managed": True,
        "dietary_details": {"goals": ["新目标"], "allergies": ["测试"]},
    }
    assert without_behavior_goals(old) == without_behavior_goals(new)
    new["dietary_details"]["allergies"] = []
    assert without_behavior_goals(old) != without_behavior_goals(new)


def test_model_input_has_no_raw_report_evidence_and_marks_partial_conversations():
    source = {
        "records": [],
        "conversations": [{"id": 1, "text": "x" * 19000}],
        "window": {"start_date": "2026-11-01", "end_date": "2026-12-01"},
        "stage": None,
        "requested_goals": [],
        "note": "",
        "profile": {},
        "weeks": [],
        "memories": [],
        "reports": [{"confirmation_id": "c", "observed_at": "2026-11-20", "evidence": "private page"}],
    }
    result = model_facts(source)
    assert result["messages_are_partial"] is True
    assert result["report_count"] == 1 and "private page" not in str(result)
    assert result["recorded_days"] == {}


@pytest.mark.parametrize("text", ["建议停药", "每日控制到1000千卡", "血糖目标5.5mmol/L"])
def test_model_cannot_turn_behavior_suggestions_into_medication_or_clinical_targets(text):
    with pytest.raises(HealthVisionError):
        validate_behavior_result({"summary": text})


def test_family_soft_ranking_uses_all_selected_members_behavior_goals():
    from yuxi.services.reference_recipe_variety import candidate_priority, variety_context

    selection = {"family_id": "synthetic-family", "plan_date": "2026-11-25"}
    members = [{"dietary": {}, "stage_goals": ["规律三餐"]},
               {"dietary": {}, "stage_goals": ["增加蒸煮菜品", "增加蔬菜搭配"]}]
    context = variety_context([], selection, members)
    assert candidate_priority(set(), "Steam broccoli", context) > candidate_priority(set(), "Fry chicken", context)
    opposite = variety_context([], selection, [{"dietary": {}, "stage_goals": ["不要增加蔬菜"]}])
    assert candidate_priority(set(), "broccoli", opposite) == candidate_priority(set(), "rice", opposite)

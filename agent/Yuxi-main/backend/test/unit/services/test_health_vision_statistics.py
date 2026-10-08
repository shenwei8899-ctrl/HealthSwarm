"""运行统计使用独立手算分母，不把服务成功当识别准确率。"""

from copy import deepcopy
from datetime import datetime, timedelta

import pytest

from yuxi.services.health_vision_statistics import summarize_vision_statistics


def task(queue=1, duration=2, **changes):
    """合成持久时间点，不调用识图或复用统计算法。"""
    created = datetime(2026, 10, 4, 10)
    return {
        "status": "success",
        "error_code": None,
        "phase": "ready",
        "created_at": created,
        "started_at": created + timedelta(seconds=queue),
        "completed_at": created + timedelta(seconds=queue + duration),
        **changes,
    }


def report_item(item_id, **changes):
    """原始候选带 OCR 来源，日期补充与测量纠错分开。"""
    return {
        "field_id": item_id,
        "name": "合成指标",
        "value_raw": "6.8",
        "unit_raw": "mmol/L",
        "observation_code": "glucose",
        "reference_raw": "原始范围",
        "source": "ocr",
        **changes,
    }


def review(kind, items, *, job_id="synthetic-job", **changes):
    """生产接口之外显式准备独立输入及原始快照。"""
    collection = "fields" if kind == "report" else "items"
    payload = {collection: items}
    return {
        "job_id": job_id,
        "original_payload": deepcopy(payload),
        "payload": deepcopy(payload),
        "snapshot": None,
        **changes,
    }


def test_empty_statistics_keep_unknown_rates_times_and_cost():
    result = summarize_vision_statistics([], [], "report")
    assert result["tasks"]["queue"] == {"sample_count": 0, "p50_seconds": None, "p95_seconds": None}
    assert result["tasks"]["execution"]["p95_seconds"] is None
    assert result["reviews"]["modification_rate_percent"] is None
    assert result["nutrition"]["incomplete_rate_percent"] is None
    assert result["cost"]["amount"] is None


def test_nearest_rank_counts_all_samples_and_terminal_failures_not_only_success():
    rows = [task(queue=number, duration=number * 2) for number in range(1, 21)]
    rows[0].update(status="failed", error_code="provider_timeout")
    rows[1].update(phase="partial_ready")
    result = summarize_vision_statistics(rows, [], "report")["tasks"]
    assert result["sample_count"] == 20
    assert result["queue"] == {"sample_count": 20, "p50_seconds": 10, "p95_seconds": 19}
    assert result["execution"] == {"sample_count": 20, "p50_seconds": 20, "p95_seconds": 38}
    assert result["states"] == {"failed": 1, "success": 19}
    assert result["failure_codes"] == {"provider_timeout": 1}
    assert result["partial_report_count"] == 1


def test_missing_negative_and_unfinished_times_are_not_zero_duration_samples():
    created = datetime(2026, 10, 4, 10)
    rows = [
        task(started_at=None, completed_at=None, status="failed"),
        task(queue=-1, duration=-1),
        task(status="running", completed_at=created + timedelta(hours=2)),
        task(created_at=None, started_at=None),
        task(queue=0, duration=0),
    ]
    result = summarize_vision_statistics(rows, [], "report")["tasks"]
    assert result["sample_count"] == 5
    assert result["queue"] == {"sample_count": 2, "p50_seconds": 0, "p95_seconds": 1}
    assert result["execution"] == {"sample_count": 1, "p50_seconds": 0, "p95_seconds": 0}
    assert result["failure_codes"] == {"task_failed": 1}


@pytest.mark.parametrize(
    "key,new_value",
    [
        ("name", "纠错名称"),
        ("observation_code", "unknown"),
        ("value_raw", "7.1"),
        ("unit_raw", "mg/dL"),
        ("reference_raw", "纠错范围"),
    ],
)
def test_report_changes_include_only_eligible_original_items(key, new_value):
    row = review("report", [report_item("a"), report_item("b")])
    row["payload"]["fields"][0][key] = new_value
    result = summarize_vision_statistics([], [row], "report")["reviews"]
    assert (result["original_items"], result["modified_items"], result["modification_rate_percent"]) == (2, 1, 50)


def test_report_exclusion_additions_context_and_manual_reprocess_baseline_are_separate():
    row = review(
        "report",
        [
            report_item("a"),
            report_item("b"),
            report_item("c"),
            report_item("d", evidence={"page_index": 1}),
            report_item("manual-before", source="manual"),
        ],
    )
    row["payload"]["fields"][0].update(observed_at="2026-10-04", fasting="yes", review_flags=[])
    row["payload"]["fields"][1].update(excluded=True, value_raw="123")
    row["payload"]["fields"] = [item for item in row["payload"]["fields"] if item["field_id"] != "c"]
    row["payload"]["fields"].append(report_item("new", source="manual"))
    row["payload"]["excluded_pages"] = [1]
    manual = review("report", [report_item("m", source="manual")], job_id=None)
    manual["payload"]["fields"][0]["value_raw"] = "7.1"
    result = summarize_vision_statistics([], [row, manual], "report")["reviews"]
    assert result == {
        "confirmed_drafts": 2,
        "model_drafts": 1,
        "original_items": 4,
        "modified_items": 0,
        "excluded_items": 3,
        "added_items": 1,
        "modification_rate_percent": 0,
    }


def test_meal_name_corrections_do_not_count_portions_mappings_or_manual_records():
    row = review(
        "meal", [{"item_id": "a", "name": "米饭"}, {"item_id": "b", "name": "鱼"}, {"item_id": "c", "name": "鸡肉"}]
    )
    row["payload"]["items"][0].update(grams="100", food_id="food", share_ratio="0.5", portion_source="weighed")
    row["payload"]["items"][1]["name"] = "豆腐"
    row["payload"]["items"][2]["excluded"] = True
    manual = review("meal", [{"item_id": "m", "name": "人工"}], job_id=None)
    result = summarize_vision_statistics([], [row, manual], "meal")["reviews"]
    assert result["modified_items"] == 1 and result["original_items"] == 3
    assert result["excluded_items"] == 1 and result["modification_rate_percent"] == 33.33


def test_nutrition_uses_only_confirmed_snapshot_including_unknown_portions():
    rows = []
    for index, source in enumerate(["unknown", "estimated", "weighed", "manual"]):
        snapshot = {
            "nutrition": {"complete": index >= 2},
            "meal": {
                "items": [
                    {"portion_source": source, "excluded": False},
                    {"portion_source": "weighed", "excluded": True},
                ]
            },
        }
        rows.append(review("meal", [], job_id=None, snapshot=snapshot))
    result = summarize_vision_statistics([], rows, "meal")["nutrition"]
    assert result == {
        "sample_count": 4,
        "incomplete_count": 2,
        "incomplete_rate_percent": 50,
        "portion_sources": {"unknown": 1, "estimated": 1, "weighed": 1, "manual": 1},
    }


def test_projection_does_not_return_private_payloads_errors_ids_or_names():
    rows = [task(error="synthetic-private-error", name="synthetic-private-name", payload={"private": True})]
    result = summarize_vision_statistics(rows, [review("report", [report_item("private-id")])], "report")
    assert "synthetic-private" not in str(result) and "private-id" not in str(result)
    assert "accuracy" not in str(result)

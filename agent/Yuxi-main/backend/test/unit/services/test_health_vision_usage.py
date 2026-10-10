"""模型用量采用独立整数预期，未知、零和费用分别验证。"""

import pytest

from yuxi.services.health_vision_usage import normalize_token_usage, summarize_vision_usage, vision_usage_receipt


@pytest.mark.parametrize(
    "usage",
    [
        None,
        [],
        {},
        {"input_tokens": 1, "output_tokens": 2},
        {"input_tokens": True, "output_tokens": 2, "total_tokens": 3},
        {"input_tokens": "1", "output_tokens": 2, "total_tokens": 3},
        {"input_tokens": 1.0, "output_tokens": 2, "total_tokens": 3},
        {"input_tokens": -1, "output_tokens": 2, "total_tokens": 1},
        {"input_tokens": 1, "output_tokens": 2, "total_tokens": 4},
        {"input_tokens": 10**13, "output_tokens": 0, "total_tokens": 10**13},
    ],
)
def test_missing_invalid_or_inconsistent_usage_is_unknown(usage):
    assert normalize_token_usage(usage) is None


def test_receipt_drops_provider_private_metadata_and_preserves_explicit_zero():
    receipt = vision_usage_receipt(
        [
            {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "patient": "private-value"},
            None,
        ]
    )
    assert receipt == {
        "schema_version": 1,
        "scope": "successful_attempt_model_calls",
        "calls": [{"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}, None],
    }
    assert "private" not in str(receipt)


def test_known_sum_excludes_missing_calls_failed_facts_and_legacy_tasks():
    tasks = [
        {
            "status": "success",
            "result": {
                "provider_usage": vision_usage_receipt(
                    [
                        {"input_tokens": 7, "output_tokens": 11, "total_tokens": 18},
                        {"input_tokens": 2, "output_tokens": 3, "total_tokens": 5},
                        None,
                    ]
                )
            },
        },
        {"status": "success", "result": {"result_id": "legacy"}},
        {
            "status": "failed",
            "result": {
                "provider_usage": vision_usage_receipt(
                    [{"input_tokens": 100, "output_tokens": 200, "total_tokens": 300}]
                )
            },
        },
    ]
    result = summarize_vision_usage(tasks)
    assert result == {
        "scope": "successful_attempt_model_calls",
        "receipt_task_count": 1,
        "unknown_task_count": 2,
        "reported_call_count": 2,
        "missing_call_count": 1,
        "reported_tokens": {"input_tokens": 9, "output_tokens": 14, "total_tokens": 23},
        "complete": False,
        "billing_complete": False,
    }


@pytest.mark.parametrize("tasks", [[], [{"status": "success", "result": None}]])
def test_absent_reports_keep_totals_unknown(tasks):
    result = summarize_vision_usage(tasks)
    assert result["reported_tokens"] == {"input_tokens": None, "output_tokens": None, "total_tokens": None}
    assert not result["complete"] and not result["billing_complete"]


def test_explicit_all_zero_is_complete_for_the_recorded_scope():
    result = summarize_vision_usage(
        [
            {
                "status": "success",
                "result": {
                    "provider_usage": vision_usage_receipt([{"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}])
                },
            }
        ]
    )
    assert result["reported_tokens"] == {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    assert result["reported_call_count"] == 1 and result["missing_call_count"] == 0
    assert result["complete"] and not result["billing_complete"]


@pytest.mark.parametrize(
    "calls,version,scope",
    [
        ([], 1, "successful_attempt_model_calls"),
        ([None] * 101, 1, "successful_attempt_model_calls"),
        ([None], 2, "successful_attempt_model_calls"),
        ([None], True, "successful_attempt_model_calls"),
        ([None], 1, "all_provider_billing"),
    ],
)
def test_malformed_persisted_receipt_does_not_assert_known_coverage(calls, version, scope):
    result = summarize_vision_usage(
        [
            {
                "status": "success",
                "result": {"provider_usage": {"schema_version": version, "scope": scope, "calls": calls}},
            }
        ]
    )
    assert result["unknown_task_count"] == 1 and result["receipt_task_count"] == 0
    assert result["reported_call_count"] == 0 and not result["complete"]

"""个人目标回放oracle拒绝错误检查值，而非配合实现生成预期。"""

import json
from copy import deepcopy
from importlib import import_module
from pathlib import Path

import pytest


@pytest.fixture
def quality_protocol(monkeypatch):
    """独立可执行服务器按脚本模块路径加载。"""
    monkeypatch.syspath_prepend(str(Path(__file__).parents[2] / "support"))
    return import_module("test.support.health_quality_replay_server").quality_delta


def personal_receipt_body():
    """300与330目标冲突及全部营养均为独立固定手算oracle。"""
    receipt = {
        "check_id": "00000000-0000-4000-8000-000000000001",
        "nutrition": {
            "totals": {
                "energy_kcal": "300.00",
                "protein_g": "30.00",
                "fat_g": "6.00",
                "carbohydrate_g": "60.00",
                "sodium_mg": "150.00",
            }
        },
        "professional_review": "not_a_professional_decision",
        "safety_check": {
            "status": "conflict",
            "checks_version": "quality-rules-v2-personal",
            "missing": [],
            "conflicts": [
                {"path": "nutrition.energy_kcal", "code": "approved_nutrient_range", "reason": "计划量超出当前批准范围"}
            ],
            "personal_targets": {
                "status": "ready",
                "energy_kcal": "330",
                "bounds": {"energy_kcal": {"minimum": "330", "maximum": "330"}},
            },
        },
    }
    body = {
        "model": "deterministic-quality-20261007",
        "stream": True,
        "tools": [{"function": {"name": n}} for n in ("get_quality_review_context", "check_selected_plan_quality")],
        "messages": [
            {"role": "system", "content": "slug: family-quality-review"},
            {"role": "user", "content": "QUALITY_E2E:" + "a" * 32 + ":valid:personal"},
            {"role": "tool", "tool_call_id": "check-" + "a" * 32, "content": json.dumps(receipt)},
        ],
    }
    return body, receipt


def test_personal_protocol_selects_only_conflict_check_id(quality_protocol):
    """合成冲突亦可形成工程检查收据，无专业批准字段。"""
    body, receipt = personal_receipt_body()
    delta, final = quality_protocol("Bearer synthetic-quality-key", body)
    assert final and json.loads(delta["content"]) == {"check_id": receipt["check_id"]}


@pytest.mark.parametrize("change", ["status", "energy", "bound", "conflict", "nutrition"])
def test_personal_protocol_rejects_wrong_target_or_quality_result(quality_protocol, change):
    """移除实际个人约束或报告错误数值时独立oracle必须失败。"""
    body, receipt = personal_receipt_body()
    broken = deepcopy(receipt)
    if change == "status":
        broken["safety_check"]["status"] = "passed"
    elif change == "energy":
        broken["safety_check"]["personal_targets"]["energy_kcal"] = "300"
    elif change == "bound":
        broken["safety_check"]["personal_targets"]["bounds"]["energy_kcal"]["minimum"] = "300"
    elif change == "conflict":
        broken["safety_check"]["conflicts"] = []
    else:
        broken["nutrition"]["totals"]["protein_g"] = "0"
    body["messages"][-1]["content"] = json.dumps(broken)
    with pytest.raises(ValueError, match="independent_.*oracle_failed"):
        quality_protocol("Bearer synthetic-quality-key", body)

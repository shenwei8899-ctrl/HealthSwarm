"""整份组合的独立数值对照与确认输入边界。"""

from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

from yuxi.services.health_meal_plan_types import SafeRegenerationInput
from yuxi.services.health_safe_plan_regeneration_service import search_plan_combinations


def test_joint_solution_and_search_limit_differ_from_exhaustive_failure():
    """必须共同调整才能合格，搜索截断不能报告组合无解。"""
    options = [[(Decimal(i), f"{group}{i}", None) for i in range(3)] for group in ["a", "b"]]
    values = [[0, 2, 3], [0, 1, 2]]

    def evaluate(indices):
        return indices if sum(values[p][i] for p, i in enumerate(indices)) == 5 else None

    result, searched = search_plan_combinations(options, evaluate)
    assert result == (2, 2) and searched == {"examined": 9, "limited": False, "max_states": 10000}
    result, stopped = search_plan_combinations(options, evaluate, max_states=2)
    assert result is None and stopped["limited"] is True and stopped["examined"] == 1
    result, exhausted = search_plan_combinations(options, lambda indices: None)
    assert result is None and exhausted["limited"] is False and exhausted["examined"] == 9


def test_least_difference_deterministic_result_examines_later_combination():
    """两个独立约束先排除低差异选项，合法组合按总差异选择。"""
    options = [
        [(Decimal(0), "old", None), (Decimal(2), "new", None)],
        [(Decimal(0), "old", None), (Decimal(1), "new", None)],
    ]

    def evaluate(indices):
        return indices if indices[0] == 1 else None

    first, _ = search_plan_combinations(options, evaluate)
    second, _ = search_plan_combinations(options, evaluate)
    assert first == second == (1, 0)


def test_budget_cannot_drop_cheaper_frontier_and_return_more_expensive_solution():
    """差异2与100均合格；预算不能丢掉前者后把后者宣称完成。"""
    options = [[(Decimal(i), f"a{i}", None) for i in [0, 1, 2]], [(Decimal(i), f"b{i}", None) for i in [0, 100, 200]]]

    def evaluate(indices):
        return indices if indices in {(2, 0), (0, 1)} else None

    selected, limited = search_plan_combinations(options, evaluate, max_states=3)
    assert selected is None and limited["limited"] is True
    selected, searched = search_plan_combinations(options, evaluate)
    assert selected == (2, 0) and searched["limited"] is False


@pytest.mark.parametrize("field", ["plan_spec", "nutrition", "grams", "safety_check", "professional_review"])
def test_confirmation_rejects_client_generated_plan_or_decision(field):
    """服务器摘要是唯一确认输入，外部方案和决定不能注入。"""
    body = {
        "version": 1,
        "rule_code": "synthetic",
        "rule_version": 1,
        "profile_version": 1,
        "client_request_id": str(uuid4()),
        "preview_hash": "a" * 64,
    }
    with pytest.raises(ValidationError):
        SafeRegenerationInput.model_validate({**body, field: "forged"})


def test_confirmation_requires_digest_and_strict_source_versions():
    """摘要与版本不能用空值、模糊文本或布尔值替代。"""
    body = {
        "version": 1,
        "rule_code": "synthetic",
        "rule_version": 1,
        "profile_version": 1,
        "client_request_id": str(uuid4()),
        "preview_hash": "a" * 64,
    }
    for update in [{"preview_hash": "arbitrary"}, {"version": True}, {"rule_version": "1"}, {"profile_version": 0}]:
        with pytest.raises(ValidationError):
            SafeRegenerationInput.model_validate({**body, **update})

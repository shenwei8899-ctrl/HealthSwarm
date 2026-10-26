# ruff: noqa: F811 -- pytest 注入共享隔离 fixture。
"""仅在允许发起新咨询的入口展示预算诊断。"""

from unittest.mock import AsyncMock
import pytest

from test.unit.services.test_health_capabilities import capability_sources  # noqa: F401
from test.unit.services.test_health_readiness import readiness_sources  # noqa: F401
from yuxi.services import health_ai_budget_service as budget
from yuxi.services import health_vision_service as vision
from yuxi.services import health_readiness_service as readiness

pytestmark = pytest.mark.asyncio


@pytest.mark.parametrize("code", ["budget_price_unavailable", "budget_exceeded"])
async def test_budget_only_decorates_available_consultation_entry(readiness_sources, monkeypatch, code):
    """预算缺项明确显示，人工录入与其他独立用途不被错误禁用。"""
    check = AsyncMock(return_value={"available": False, "reason_code": code, "reason": "合成预算原因"})
    monkeypatch.setattr(budget, "model_budget_readiness", check)
    monkeypatch.setattr(vision, "current_health_model_info", AsyncMock(return_value=object()))
    result = await readiness.member_readiness(readiness_sources.uid, readiness_sources.member_id)
    entries = {entry.entry_type: entry for entry in result.entries}
    assert entries["consultation"].status == "unavailable"
    assert entries["consultation"].configuration_reason_code == code
    restored = type(result).model_validate_json(result.model_dump_json())
    assert next(entry for entry in restored.entries if entry.entry_type == "consultation").configuration_reason_code == code
    assert (
        entries["manual_report"].status
        == entries["manual_meal"].status
        == entries["diet_analysis"].status
        == "available"
    )


async def test_budget_never_supersedes_missing_authorization(readiness_sources, monkeypatch):
    """无AI授权时优先保留真实权限原因，也不读取预算数据。"""
    readiness_sources.health.visible_member_scopes.return_value = (readiness_sources.user, {"profile_view"})
    check = AsyncMock(side_effect=AssertionError("不应读取预算"))
    monkeypatch.setattr(budget, "model_budget_readiness", check)
    result = await readiness.member_readiness(readiness_sources.uid, readiness_sources.member_id)
    entry = next(e for e in result.entries if e.entry_type == "consultation")
    assert entry.reason_code == "missing_scopes"
    check.assert_not_awaited()

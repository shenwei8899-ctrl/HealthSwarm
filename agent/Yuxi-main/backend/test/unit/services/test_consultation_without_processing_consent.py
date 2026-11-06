"""咨询沿用成员权限，不再受独立处理同意记录阻断。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from test.unit.services.test_health_capabilities import capability_sources  # noqa: F401
from test.unit.services.test_health_readiness import readiness_sources  # noqa: F401
from yuxi.repositories.health_vision_repository import HealthVisionRepository
from yuxi.services.health_readiness_service import member_readiness
from yuxi.services.health_vision_types import HealthVisionError


@pytest.mark.asyncio
@pytest.mark.parametrize("state", ["missing", "revoked", "processor_changed", "policy_changed"])
async def test_consultation_does_not_require_processing_consent(state):
    """旧记录的四类失败状态均不增加一次咨询确认。"""
    record = (
        None
        if state == "missing"
        else SimpleNamespace(
            revoked_at="synthetic-time" if state == "revoked" else None,
            processor="old" if state == "processor_changed" else "current",
            policy_version="old" if state == "policy_changed" else "current",
        )
    )
    repo = HealthVisionRepository(SimpleNamespace(get=AsyncMock(return_value=record)))
    await repo.require_consent("member", "actor", "consultation", {"processor": "current", "policy_version": "current"})


@pytest.mark.asyncio
@pytest.mark.parametrize("purpose", ["report", "meal", "meal_plan", "diet_analysis", "quality_review", "purchase"])
async def test_other_purposes_still_require_processing_consent(purpose):
    """咨询简化不改变照片、配餐和其他结构化用途。"""
    repo = HealthVisionRepository(SimpleNamespace(get=AsyncMock(return_value=None)))
    with pytest.raises(HealthVisionError) as denied:
        await repo.require_consent("member", "actor", purpose, {"processor": "current", "policy_version": "current"})
    assert denied.value.code == "consent_required"


@pytest.mark.asyncio
@pytest.mark.parametrize("revoked", [False, True])
async def test_consultation_entry_is_available_with_missing_or_revoked_processing_record(readiness_sources, revoked):  # noqa: F811
    """真实就绪聚合使用真实用途校验，不让旧记录再次阻断聊天入口。"""
    sources = readiness_sources
    record = SimpleNamespace(revoked_at="synthetic-time", processor="old", policy_version="old") if revoked else None
    repo = HealthVisionRepository(SimpleNamespace(get=AsyncMock(return_value=record)))
    sources.health.require_consent = repo.require_consent
    result = await member_readiness(sources.uid, sources.member_id)
    consultation = next(entry for entry in result.entries if entry.entry_type == "consultation")
    assert consultation.status == "available" and consultation.reason_code is None

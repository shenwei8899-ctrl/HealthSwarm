"""餐单当前不可采用时的专业复核状态投影。"""

from types import SimpleNamespace

import pytest

from yuxi.services import health_quality_service as service
from yuxi.services.health_vision_types import HealthVisionError


class EmptyCandidates:
    """当前没有仍获批准的专业复核。"""

    def all(self):
        return []


class ApprovalSession:
    """批准候选查询返回空，最近状态另经repository读取。"""

    async def scalars(self, _query):
        return EmptyCandidates()


@pytest.mark.asyncio
@pytest.mark.parametrize("state", [None, "draft", "pending_review", "returned", "invalidated"])
async def test_unavailable_plan_preserves_actual_current_review_state(monkeypatch, state):
    """未审核与失效分别显示，并保留真实当前版本的收据引用。"""
    latest = (
        SimpleNamespace(
            id="review-current",
            check_id="check-current",
            status=state,
            invalidation_reason="weight_measurement_changed" if state == "invalidated" else None,
        )
        if state is not None
        else None
    )

    class Repository:
        """断言查询使用授权操作者和当前餐单版本。"""

        def __init__(self, session):
            assert isinstance(session, ApprovalSession)

        async def plan(self, uid, plan_id, *, lock):
            assert (uid, plan_id, lock) == ("actor", "plan-current", True)
            return SimpleNamespace(version=3)

        async def latest_plan_review(self, uid, plan_id, version):
            assert (uid, plan_id, version) == ("actor", "plan-current", 3)
            return latest

    monkeypatch.setattr(service, "HealthQualityRepository", Repository)

    async def revalidate(_session, uid, case_id):
        assert (uid, case_id) == ("actor", "review-current")
        return latest, None, False

    monkeypatch.setattr(service, "review_case_in_session", revalidate)
    result = await service.approved_plan_state_in_session(ApprovalSession(), "actor", "plan-current", 3)
    assert result["available"] is False
    assert result["reason"] == "current_professional_approval_required"
    assert result["professional_review"] == (state or "not_reviewed")
    assert result["review_id"] == ("review-current" if latest is not None else None)
    assert result["check_id"] == ("check-current" if latest is not None else None)
    assert result["invalidation_reason"] == ("weight_measurement_changed" if state == "invalidated" else None)


@pytest.mark.asyncio
async def test_unapproved_review_is_revalidated_before_current_state_projection(monkeypatch):
    """没有主动变更的自然过期也必须触发现有来源门禁，不能继续显示待审核。"""
    latest = SimpleNamespace(
        id="review-current", check_id="check-current", status="pending_review", invalidation_reason=None
    )

    class Repository:
        def __init__(self, _session):
            pass

        async def plan(self, *_args, **_kwargs):
            return SimpleNamespace(version=3)

        async def latest_plan_review(self, *_args):
            return latest

    async def expired_source(_session, uid, case_id):
        assert (uid, case_id) == ("actor", "review-current")
        latest.status = "invalidated"
        latest.invalidation_reason = "source_changed_or_expired"
        return latest, None, False

    monkeypatch.setattr(service, "HealthQualityRepository", Repository)
    monkeypatch.setattr(service, "review_case_in_session", expired_source)
    result = await service.approved_plan_state_in_session(ApprovalSession(), "actor", "plan-current", 3)
    assert result["professional_review"] == "invalidated"
    assert result["invalidation_reason"] == "source_changed_or_expired"


@pytest.mark.asyncio
async def test_old_plan_version_is_rejected_before_review_projection(monkeypatch):
    """旧修订不能查询或继承新版本的复核状态。"""

    class Repository:
        """只有当前餐单读取可执行。"""

        def __init__(self, _session):
            pass

        async def plan(self, _uid, _plan_id, *, lock):
            assert lock is True
            return SimpleNamespace(version=4)

        async def latest_plan_review(self, *_args):
            pytest.fail("旧版本不得读取当前复核")

    monkeypatch.setattr(service, "HealthQualityRepository", Repository)
    with pytest.raises(HealthVisionError) as error:
        await service.approved_plan_state_in_session(ApprovalSession(), "actor", "plan-current", 3)
    assert error.value.code == "version_conflict"

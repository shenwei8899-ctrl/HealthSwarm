"""用途同意必须约束真实处理、每次模型调用和四类咨询历史。"""

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from yuxi.repositories.health_consultation_repository import EDUCATION_HEALTH_AGENTS, HealthConsultationRepository
from yuxi.repositories.health_vision_repository import HealthVisionRepository
from yuxi.services import health_consultation_service as service
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.storage.postgres.models_business import Conversation
from yuxi.storage.postgres.models_health import HealthProcessingConsent
from yuxi.utils.datetime_utils import utc_now_naive


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["current", "missing", "revoked", "processor", "policy"])
async def test_consultation_processing_rechecks_real_consent_row(case):
    """用途、处理方、政策和撤回状态均由持久化同意行决定。"""
    snapshot = {"processor": "synthetic", "policy_version": "policy"}
    consent = SimpleNamespace(processor="synthetic", policy_version="policy", revoked_at=None)
    if case == "revoked":
        consent.revoked_at = utc_now_naive()
    elif case == "processor":
        consent.processor = "previous"
    elif case == "policy":
        consent.policy_version = "previous"
    session = SimpleNamespace(get=AsyncMock(return_value=None if case == "missing" else consent))
    repo = HealthVisionRepository(session)

    if case == "current":
        await repo.require_consent("member", "actor", "consultation", snapshot)
    else:
        with pytest.raises(HealthVisionError, match="consent_required") as denied:
            await repo.require_consent("member", "actor", "consultation", snapshot)
        assert denied.value.status == 403
    session.get.assert_awaited_once_with(
        HealthProcessingConsent, ("member", "actor", "consultation"), populate_existing=True
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["current", "missing", "revoked", "processor", "policy"])
async def test_model_attempt_uses_current_processing_consent(monkeypatch, case):
    """真实模型前置服务保留冻结配置，当前同意失效即停止该次模型调用。"""
    snapshot = {"model": "synthetic/fixed", "processor": "synthetic", "policy_version": "policy"}
    consent = SimpleNamespace(processor="synthetic", policy_version="policy", revoked_at=None)
    if case == "revoked":
        consent.revoked_at = utc_now_naive()
    elif case == "processor":
        consent.processor = "previous"
    elif case == "policy":
        consent.policy_version = "previous"
    binding = SimpleNamespace(member_id="member", conversation_id=1)

    async def get_row(model, key, **kwargs):
        """只模拟真实数据库读取，不替代用途同意检查。"""
        if model is Conversation:
            return SimpleNamespace(agent_id="health-consultation")
        assert model is HealthProcessingConsent and key == ("member", "actor", "consultation")
        return None if case == "missing" else consent

    session = SimpleNamespace(get=AsyncMock(side_effect=get_row))

    @asynccontextmanager
    async def session_context():
        yield session

    run = SimpleNamespace(agent_slug="health-consultation", input_payload={"health_processing": snapshot})
    monkeypatch.setattr(service.pg_manager, "get_async_session_context", session_context)
    monkeypatch.setattr(HealthConsultationRepository, "require_attempt", AsyncMock(return_value=run))
    monkeypatch.setattr(HealthConsultationRepository, "authorize", AsyncMock(return_value=binding))
    monkeypatch.setattr(
        service.health_vision_service,
        "configuration",
        AsyncMock(
            return_value={
                "policy_version": "policy",
                "consultation": {"available": True, **snapshot},
            }
        ),
    )
    skill = AsyncMock(return_value=SimpleNamespace(source_type="builtin", enabled=True))
    monkeypatch.setattr(service.SkillRepository, "get_by_slug", skill)
    context = SimpleNamespace(uid="actor", thread_id="thread", model=snapshot["model"])

    if case == "current":
        await service.require_consultation_attempt(context)
        skill.assert_awaited()
    else:
        with pytest.raises(HealthVisionError, match="consent_required") as denied:
            await service.require_consultation_attempt(context)
        assert denied.value.status == 403
        skill.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("agent_slug", sorted(EDUCATION_HEALTH_AGENTS))
@pytest.mark.parametrize("revoked", [False, True])
async def test_education_history_rechecks_active_consent(monkeypatch, agent_slug, revoked):
    """保留成员 grant 的真实历史授权仍拒绝四种 Agent 的已撤回用途同意。"""
    from yuxi.repositories.health_family_profile_repository import HealthFamilyProfileRepository
    from yuxi.repositories.health_weight_repository import HealthWeightRepository
    from yuxi.repositories.health_blood_pressure_repository import HealthBloodPressureRepository
    from yuxi.repositories.health_blood_glucose_repository import HealthBloodGlucoseRepository
    from yuxi.repositories.health_blood_lipids_repository import HealthBloodLipidsRepository
    from yuxi.repositories.health_diet_correction_repository import HealthDietCorrectionRepository
    from yuxi.services import conversation_purchase_service

    binding = SimpleNamespace(member_id="member", conversation_id=1)
    consent = SimpleNamespace(revoked_at=utc_now_naive() if revoked else None)
    conversation = SimpleNamespace(agent_id=agent_slug)

    async def get_row(model, key, **kwargs):
        """保留真实 repository 流程，仅按模型提供合成行。"""
        if model is Conversation:
            return conversation
        assert model is HealthProcessingConsent and key == ("member", "actor", "consultation")
        return consent

    session = SimpleNamespace(
        scalar=AsyncMock(side_effect=[binding, None, None, None]),
        get=AsyncMock(side_effect=get_row),
        execute=AsyncMock(return_value=SimpleNamespace(all=lambda: [])),
        scalars=AsyncMock(return_value=SimpleNamespace(all=lambda: [])),
    )
    monkeypatch.setattr(
        HealthVisionRepository,
        "authorize",
        AsyncMock(return_value=SimpleNamespace(owner_uid="actor", relationship_label="本人")),
    )
    for repo in (
        HealthFamilyProfileRepository,
        HealthWeightRepository,
        HealthBloodPressureRepository,
        HealthBloodGlucoseRepository,
        HealthBloodLipidsRepository,
    ):
        monkeypatch.setattr(repo, "validate_history", AsyncMock())
    monkeypatch.setattr(HealthDietCorrectionRepository, "validate_consultation_history", AsyncMock())
    monkeypatch.setattr(conversation_purchase_service, "validate_catalog_profile_history", AsyncMock())

    if revoked:
        with pytest.raises(HealthVisionError, match="consent_required") as denied:
            await HealthConsultationRepository(session).authorize("actor", "thread", preview_history=True)
        assert denied.value.status == 403
    else:
        assert await HealthConsultationRepository(session).authorize("actor", "thread", preview_history=True) is binding

"""正式来源重验与真实目标、初始配餐和质量消费者的拒绝边界。"""

from contextlib import asynccontextmanager
from copy import deepcopy
from datetime import datetime, timedelta, UTC
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from test.unit.services.test_health_meal_planner import spec_input
from test.unit.services.test_health_quality import profile_payload, rules_payload
from yuxi.repositories.health_family_profile_repository import HealthFamilyProfileRepository
from yuxi.repositories.health_quality_repository import HealthQualityRepository
from yuxi.repositories.health_vision_repository import HealthVisionRepository
from yuxi.services import health_initial_meal_plan_service, health_personal_target_service, health_quality_service
from yuxi.services.health_quality_checks import external_projection, projection_digest
from yuxi.services.health_vision_types import HealthVisionError


def family_source():
    """合成来源独立于安全载荷及其就绪状态。"""
    return {
        "family_id": "synthetic-family",
        "source_member_id": "synthetic-source-member",
        "confirmed_version": 1,
        "source_hash": "b" * 64,
    }


def snapshot(member_id, *, source=None, kind="profile", payload=None):
    """仅构造有效合成外部资料；源码来源另由仓储重验。"""
    now = datetime.now(UTC)
    proof = {
        "version": 1,
        "attested_at": (now - timedelta(minutes=1)).isoformat(),
        "valid_until": (now + timedelta(days=1)).isoformat(),
    }
    if source is not None:
        proof["family_profile_source"] = source
    body = payload if payload is not None else profile_payload()
    return SimpleNamespace(
        id=f"synthetic-{kind}",
        version=1,
        payload=body,
        attestation=proof,
        content_hash=projection_digest(kind, member_id, 1, body, proof),
        attested_at=datetime.fromisoformat(proof["attested_at"]).replace(tzinfo=None),
        valid_until=datetime.fromisoformat(proof["valid_until"]).replace(tzinfo=None),
        revoked_at=None,
    )


@pytest.mark.asyncio
async def test_unlinked_legacy_projection_keeps_independent_contract(monkeypatch):
    """无正式关联的既有专业资料不被伪造成本人档案。"""
    member_id = "synthetic-member"
    row = snapshot(member_id)
    repo = HealthQualityRepository(None)
    repo.profile = AsyncMock(return_value=row)
    monkeypatch.setattr(HealthFamilyProfileRepository, "confirmed_source", AsyncMock(return_value=None), raising=False)

    result = await repo.profile_projection(member_id)

    assert result == external_projection(row, "profile", member_id)
    assert "family_profile_source" not in result["attestation"]


@pytest.mark.asyncio
async def test_current_source_preserves_professionally_unknown_fields(monkeypatch):
    """来源匹配不把不耐受未知改成明确无或安全通过。"""
    payload = profile_payload()
    payload["intolerances"] = {"state": "unknown", "codes": []}
    row = snapshot("synthetic-member", source=family_source(), payload=payload)
    repo = HealthQualityRepository(None)
    repo.profile = AsyncMock(return_value=row)
    monkeypatch.setattr(
        HealthFamilyProfileRepository, "confirmed_source", AsyncMock(return_value=family_source()), raising=False
    )

    result = await repo.profile_projection("synthetic-member")

    assert result["status"] == "ready"
    assert result["payload"]["intolerances"] == {"state": "unknown", "codes": []}
    assert result["attestation"]["family_profile_source"] == family_source()


@pytest.mark.asyncio
@pytest.mark.parametrize("fault", ["unmapped", "missing_link", "family", "member", "version", "hash", "bool"])
async def test_source_difference_hides_latest_payload_without_fallback(monkeypatch, fault):
    """正式关联及完整来源摘要均须一致，JSON改型也不继承旧确认。"""
    actual = family_source()
    recorded = deepcopy(actual)
    if fault == "missing_link":
        actual = None
    elif fault == "unmapped":
        recorded = None
    elif fault == "family":
        recorded["family_id"] = "other-family"
    elif fault == "member":
        recorded["source_member_id"] = "other-member"
    elif fault == "version":
        recorded["confirmed_version"] = 2
    elif fault == "hash":
        recorded["source_hash"] = "c" * 64
    else:
        recorded["confirmed_version"] = True
    row = snapshot("synthetic-member", source=recorded)
    repo = HealthQualityRepository(None)
    repo.profile = AsyncMock(return_value=row)
    monkeypatch.setattr(
        HealthFamilyProfileRepository, "confirmed_source", AsyncMock(return_value=actual), raising=False
    )

    result = await repo.profile_projection("synthetic-member")

    assert result["status"] == "not_ready"
    assert result["reason"] == (
        "family_profile_source_unmapped" if fault == "unmapped" else "family_profile_source_changed"
    )
    assert result["payload"] is None and result["attestation"] is None
    assert result["id"] == row.id and result["content_hash"] == row.content_hash
    repo.profile.assert_awaited_once_with("synthetic-member")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "code,status,reason",
    [
        ("family_profile_unconfirmed", 409, "family_profile_unconfirmed"),
        ("not_found", 404, "family_profile_source_unavailable"),
    ],
)
async def test_unconfirmed_or_unavailable_source_hides_payload(monkeypatch, code, status, reason):
    """来源错误只暴露明确未就绪状态，不公开旧专业正文。"""
    repo = HealthQualityRepository(None)
    repo.profile = AsyncMock(return_value=snapshot("synthetic-member", source=family_source()))
    monkeypatch.setattr(
        HealthFamilyProfileRepository,
        "confirmed_source",
        AsyncMock(side_effect=HealthVisionError(code, "合成来源拒绝", status)),
        raising=False,
    )

    result = await repo.profile_projection("synthetic-member")

    assert result["status"] == "not_ready" and result["reason"] == reason
    assert result["payload"] is None and result["attestation"] is None


@pytest.mark.asyncio
async def test_unexpected_source_error_is_not_disguised_as_missing_data(monkeypatch):
    """来源查询的其他失败不能静默降为资料不足。"""
    repo = HealthQualityRepository(None)
    repo.profile = AsyncMock(return_value=snapshot("synthetic-member", source=family_source()))
    monkeypatch.setattr(
        HealthFamilyProfileRepository,
        "confirmed_source",
        AsyncMock(side_effect=HealthVisionError("unexpected_failure", "合成错误", 500)),
        raising=False,
    )

    with pytest.raises(HealthVisionError, match="unexpected_failure"):
        await repo.profile_projection("synthetic-member")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "fault,reason", [("missing", "not_delivered"), ("revoked", "revoked"), ("hash", "integrity_mismatch")]
)
async def test_external_failure_is_not_replaced_by_formal_source(monkeypatch, fault, reason):
    """正式来源有效也不能恢复缺失、撤回或篡改的专业投影。"""
    row = snapshot("synthetic-member", source=family_source())
    if fault == "missing":
        row = None
    elif fault == "revoked":
        row.revoked_at = datetime.now(UTC).replace(tzinfo=None)
    else:
        row.payload = {**row.payload, "age_years": 99}
    repo = HealthQualityRepository(None)
    repo.profile = AsyncMock(return_value=row)
    source = AsyncMock(return_value=family_source())
    monkeypatch.setattr(HealthFamilyProfileRepository, "confirmed_source", source, raising=False)

    result = await repo.profile_projection("synthetic-member")

    assert result["status"] == "not_ready" and result["reason"] == reason and result["payload"] is None
    source.assert_not_awaited()


@pytest.fixture
def changed_source(monkeypatch):
    """真实统一解析器消费有效专业投影和已更正的正式来源。"""
    member_id = str(uuid4())
    profile = snapshot(member_id, source=family_source())
    actual = {**family_source(), "confirmed_version": 2, "source_hash": "c" * 64}
    rules = snapshot("synthetic-rules", kind="rules", payload=rules_payload())
    monkeypatch.setattr(HealthQualityRepository, "profile", AsyncMock(return_value=profile))
    monkeypatch.setattr(HealthQualityRepository, "rules", AsyncMock(return_value=rules))
    monkeypatch.setattr(HealthQualityRepository, "lock_profile_sources", AsyncMock())
    monkeypatch.setattr(
        HealthFamilyProfileRepository, "confirmed_source", AsyncMock(return_value=actual), raising=False
    )
    monkeypatch.setattr(HealthVisionRepository, "authorize", AsyncMock())
    return member_id


@pytest.mark.asyncio
async def test_personal_targets_reject_stale_formal_source(monkeypatch, changed_source):
    """目标服务不能重新解析原始投影而绕过正式版本失效。"""

    @asynccontextmanager
    async def session_context():
        """该单测仅隔离事务设备，不模拟目标结论。"""
        yield None

    monkeypatch.setattr(health_personal_target_service.pg_manager, "get_async_session_context", session_context)
    selection = SimpleNamespace(rule_code="synthetic-rules", profile_version=1, rule_version=1)

    result = await health_personal_target_service.read_personal_targets("synthetic-owner", changed_source, selection)

    assert result["status"] == "not_ready"
    assert result["sources"]["profile"]["reason"] == "family_profile_source_changed"
    assert "bounds" not in result


@pytest.mark.asyncio
async def test_initial_plan_context_exposes_stale_source_without_professional_payload(changed_source):
    """初始个人与家庭生成共享的上下文不得传递旧编码正文。"""
    selected = SimpleNamespace(profile_versions={changed_source: 1}, rule_code="synthetic-rules", rule_version=1)

    result = await health_initial_meal_plan_service.initial_context_in_session(
        None, "synthetic-owner", changed_source, selected
    )

    assert result["profiles"][changed_source]["status"] == "not_ready"
    assert result["profiles"][changed_source]["payload"] is None
    assert result["sources"]["profiles"][changed_source]["reason"] == "family_profile_source_changed"


@pytest.mark.asyncio
async def test_saved_plan_quality_cannot_pass_with_stale_formal_source(monkeypatch, changed_source):
    """质量Owner使用当前来源，完整手算营养不能掩盖档案更正。"""
    calculated = {
        "nutrition": {
            "totals": {
                "energy_kcal": "300",
                "protein_g": "30",
                "fat_g": "6",
                "carbohydrate_g": "60",
                "sodium_mg": "150",
            }
        }
    }
    plan = SimpleNamespace(
        id="synthetic-plan", member_id=changed_source, version=1, spec=spec_input(str(uuid4())), snapshot=calculated
    )
    monkeypatch.setattr(HealthQualityRepository, "plan", AsyncMock(return_value=plan))
    monkeypatch.setattr(HealthQualityRepository, "ingredients", AsyncMock(return_value=({}, {})))
    monkeypatch.setattr(health_quality_service, "calculate_in_session", AsyncMock(return_value=calculated))
    selection = SimpleNamespace(plan_id=plan.id, plan_version=1, rule_code="synthetic-rules")

    current = await health_quality_service.quality_context_in_session(None, "synthetic-owner", selection)
    result = health_quality_service.quality_snapshot(current)

    assert result["safety_check"]["status"] == "unknown"
    assert {"path": "profile", "reason": "family_profile_source_changed"} in result["safety_check"]["missing"]
    assert current["profile"]["payload"] is None

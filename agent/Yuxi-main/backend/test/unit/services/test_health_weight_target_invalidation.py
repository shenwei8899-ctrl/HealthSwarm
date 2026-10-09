"""正式实测写事务精确失效体重来源，真实 PG 语义由 integration 证明。"""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from yuxi.repositories.family_repository import FamilyRepository
from yuxi.repositories.health_quality_repository import HealthQualityRepository
from yuxi.services.family_schemas import MeasurementUpdate, MeasurementVoid, MemberStatusInput
from yuxi.services.family_service import FamilyService


pytestmark = [pytest.mark.unit, pytest.mark.asyncio]


@pytest.fixture
def write_context(monkeypatch):
    """使用合成家庭和当前实测验证服务最终对象及提交顺序。"""
    fid, mid, rid, health_id = [str(uuid4()) for _ in range(4)]
    stamp = datetime(2026, 10, 1, 1)
    events = []

    async def commit():
        events.append("commit")

    async def invalidate(repository, **kwargs):
        events.append(kwargs)

    monkeypatch.setattr(HealthQualityRepository, "invalidate", invalidate)
    db = SimpleNamespace(commit=AsyncMock(side_effect=commit), add=Mock(), flush=AsyncMock(), scalar=AsyncMock())
    family = SimpleNamespace(id=fid, owner_uid="owner")
    member = SimpleNamespace(
        id=mid,
        subject_uid="subject",
        name="合成成员",
        relationship="家人",
        is_active=True,
        relationship_version=1,
        profile={"birth_date": "1990-01-01"},
        version=1,
        confirmed_version=1,
        confirmed_at=stamp,
        updated_at=stamp,
        grant_fields=["weight"],
        grant_edit_fields=["weight"],
        grant_expires_at=datetime(2027, 1, 1),
        grant_purpose="family_nutrition",
        invite_hash=None,
        invite_expires_at=None,
    )
    record = SimpleNamespace(
        id=rid,
        member_id=mid,
        kind="weight",
        values={"weight": 60.0},
        measured_at=stamp,
        source="synthetic-scale",
        condition="",
        note="合成初测",
        created_by="subject",
        version=1,
        updated_at=stamp,
        previous=[],
        voided_at=None,
        voided_by=None,
        void_reason=None,
    )
    service = FamilyService(db, "subject")
    service.context = AsyncMock(return_value=(family, member))
    service.repo.measurement = AsyncMock(return_value=record)
    service.repo.members = AsyncMock(return_value=[member])
    service.repo.actor_names = AsyncMock(return_value={"subject": "合成成员"})
    service.repo.audit = AsyncMock()
    service.repo.linked_health_member = AsyncMock(return_value=health_id)
    service.repo.linked_weight_target_member = AsyncMock(return_value=health_id)
    return SimpleNamespace(
        service=service, family=family, member=member, record=record, health_id=health_id, events=events
    )


async def test_selected_weight_correction_invalidates_before_commit(write_context):
    """变更保留旧值并在相同写事务内失效当前来源。"""
    ctx = write_context
    result = await ctx.service.correct_measurement(
        ctx.family.id,
        ctx.member.id,
        ctx.record.id,
        MeasurementUpdate(expected_version=1, values={"weight": 62}, note="合成更正"),
    )
    assert result["version"] == 2 and result["values"] == {"weight": 62}
    assert ctx.record.previous[0]["values"] == {"weight": 60}
    assert ctx.events == [{"member_id": ctx.health_id, "reason": "weight_measurement_changed"}, "commit"]


async def test_identical_correction_preserves_selected_record_version(write_context):
    """相同完整事实不生成新版本，也不让当前营养来源失效。"""
    ctx = write_context
    result = await ctx.service.correct_measurement(
        ctx.family.id,
        ctx.member.id,
        ctx.record.id,
        MeasurementUpdate(
            expected_version=1,
            values={"weight": 60},
            note="合成初测",
            measured_at=ctx.record.measured_at.replace(tzinfo=UTC),
            source="synthetic-scale",
            condition="",
        ),
    )
    assert result["version"] == 1 and ctx.record.previous == []
    assert ctx.events == ["commit"]
    ctx.service.repo.linked_weight_target_member.assert_not_awaited()


@pytest.mark.parametrize("operation", ["correct", "void"])
async def test_unselected_weight_write_preserves_other_nutrition_source(write_context, operation):
    """另一条实测或旧专业导入没有当前绑定，不失效无关营养流程。"""
    ctx = write_context
    ctx.service.repo.linked_weight_target_member.return_value = None
    if operation == "correct":
        result = await ctx.service.correct_measurement(
            ctx.family.id,
            ctx.member.id,
            ctx.record.id,
            MeasurementUpdate(expected_version=1, values={"weight": 62}, note="合成更正"),
        )
    else:
        result = await ctx.service.void_measurement(
            ctx.family.id, ctx.member.id, ctx.record.id, MeasurementVoid(expected_version=1, reason="合成作废")
        )
    assert result["version"] == 2 and ctx.events == ["commit"]


async def test_selected_weight_void_is_immediate_and_replay_does_not_repeat(write_context):
    """首次作废失效来源，幂等重放保留版本、历史与原失效动作。"""
    ctx = write_context
    payload = MeasurementVoid(expected_version=1, reason="合成作废")
    first = await ctx.service.void_measurement(ctx.family.id, ctx.member.id, ctx.record.id, payload)
    replay = await ctx.service.void_measurement(ctx.family.id, ctx.member.id, ctx.record.id, payload)
    assert first == replay and first["version"] == 2 and len(ctx.record.previous) == 1
    assert ctx.events == [{"member_id": ctx.health_id, "reason": "weight_measurement_changed"}, "commit", "commit"]


async def test_other_metric_correction_does_not_touch_weight_source(write_context):
    """其他独立指标的版本变化不失效既有体重营养来源。"""
    ctx = write_context
    ctx.record.kind, ctx.record.values, ctx.record.condition = "blood_glucose", {"glucose": 5.6}, "fasting"
    result = await ctx.service.correct_measurement(
        ctx.family.id,
        ctx.member.id,
        ctx.record.id,
        MeasurementUpdate(expected_version=1, values={"glucose": 6}, note="合成血糖更正"),
    )
    assert result["version"] == 2 and result["values"] == {"glucose": 6}
    assert ctx.events == ["commit"]
    ctx.service.repo.linked_weight_target_member.assert_not_awaited()


@pytest.mark.parametrize("fault", ["version", "voided", "unauthorized"])
async def test_rejected_correction_does_not_mutate_or_invalidate(write_context, fault):
    """旧版本、已作废和无授权均在更正及来源失效之前拒绝。"""
    ctx = write_context
    expected = 2 if fault == "version" else 1
    if fault == "voided":
        ctx.record.voided_at = ctx.record.measured_at
    elif fault == "unauthorized":
        ctx.service.uid = "outsider"
    with pytest.raises(HTTPException) as error:
        await ctx.service.correct_measurement(
            ctx.family.id,
            ctx.member.id,
            ctx.record.id,
            MeasurementUpdate(expected_version=expected, values={"weight": 62}, note="合成更正"),
        )
    assert error.value.status_code == (403 if fault == "unauthorized" else 409)
    assert ctx.record.version == 1 and ctx.record.values == {"weight": 60}
    assert ctx.record.previous == [] and ctx.events == []


async def test_member_deactivation_invalidates_and_restore_does_not_revive(write_context):
    """停用收敛质量与采用；恢复仅恢复关系，授权和旧营养批准不恢复。"""
    ctx = write_context
    ctx.service.uid = "owner"
    stopped = await ctx.service.member_status(
        ctx.family.id, ctx.member.id, MemberStatusInput(expected_version=1, is_active=False)
    )
    assert stopped["is_active"] is False and stopped["relationship_version"] == 2
    assert ctx.events == [{"member_id": ctx.health_id, "reason": "family_profile_source_unavailable"}, "commit"]
    restored = await ctx.service.member_status(
        ctx.family.id, ctx.member.id, MemberStatusInput(expected_version=2, is_active=True)
    )
    assert restored["is_active"] is True and restored["relationship_version"] == 3
    assert ctx.member.grant_fields == ctx.member.grant_edit_fields == []
    assert ctx.events[-1] == "commit" and len(ctx.events) == 3


@pytest.mark.parametrize("fault", [None, "record", "family", "member", "legacy", "malformed", "unlinked"])
async def test_repository_uses_only_current_projection_explicit_record(fault):
    """最高专业投影的明确记录归属决定精确失效，缺失不回退旧版。"""
    fid, mid, rid, health_id = [str(uuid4()) for _ in range(4)]
    source = {"family_id": fid, "source_member_id": mid, "record_id": rid, "version": 1}
    if fault in {"record", "family", "member"}:
        source[{"record": "record_id", "family": "family_id", "member": "source_member_id"}[fault]] = str(uuid4())
    proof = {"weight_measurement_source": source}
    if fault == "legacy":
        proof = {}
    elif fault == "malformed":
        proof = {"weight_measurement_source": "invalid"}
    db = SimpleNamespace(scalar=AsyncMock(return_value=SimpleNamespace(attestation=proof)))
    repo = FamilyRepository(db)
    repo.linked_health_member = AsyncMock(return_value=None if fault == "unlinked" else health_id)
    assert await repo.linked_weight_target_member(fid, mid, rid) == (health_id if fault is None else None)

"""独立血糖投影、条件校验与持久引用失效。"""

from copy import deepcopy
from datetime import datetime
from types import SimpleNamespace

import pytest

from test.unit.services.test_health_weight import PERIOD, set_history, weight_repo, weight_use  # noqa: F401
from yuxi.repositories import health_measurement_repository as boundary
from yuxi.repositories.health_blood_glucose_repository import HealthBloodGlucoseRepository
from yuxi.services.health_vision_types import HealthVisionError


@pytest.fixture
def glucose_repo(weight_repo, monkeypatch):  # noqa: F811
    """共用真实授权边界 fixture，仅切换血糖字段与专用依赖表。"""
    state = weight_repo
    state.repo = HealthBloodGlucoseRepository(state.session)
    monkeypatch.setattr(boundary, "authorized_fields", lambda family, member, uid: {"blood_glucose"})
    return state


def glucose_record(*, glucose=5.5, condition="fasting", version=1):
    """合成记录保留必要条件及不能外发的备注历史。"""
    return SimpleNamespace(
        id="glucose-record",
        values={"glucose": glucose},
        condition=condition,
        measured_at=datetime(2026, 10, 8, 1, 2, 3),
        source="manual",
        version=version,
        note="synthetic-private-note",
        previous=[{"glucose": 5.4}],
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("condition", ["fasting", "after_meal_2h", "random"])
async def test_glucose_projection_preserves_declared_condition_without_clinical_classification(glucose_repo, condition):
    """未确认基础档案仍读取必要实测，三类条件均保持原值。"""
    state = glucose_repo
    state.measurements.return_value = ([glucose_record(condition=condition)], 1)
    payload = await state.repo.read("actor", "health-self", PERIOD)
    assert payload["records"] == [
        {
            "record_id": "glucose-record",
            "glucose": 5.5,
            "condition": condition,
            "unit": "mmol/L",
            "measured_at": "2026-10-08T01:02:03Z",
            "source": "manual",
            "version": 1,
        }
    ]
    assert payload["status"] == "ready" and payload["code"] == "self_blood_glucose_records"
    assert payload["period"] == PERIOD and payload["limit"] == 20 and payload["truncated"] is False
    assert payload["full_health_profile_available"] is payload["nutrition_safety_ready"] is False
    assert "synthetic-private" not in str(payload)
    state.source.version = state.source.confirmed_version = 9
    assert await state.repo.read("actor", "health-self", PERIOD) == payload
    state.measurements.assert_awaited_with(
        ["formal-self"], ["blood_glucose"], since=datetime(2026, 9, 8, 16), until=datetime(2026, 10, 8, 16), limit=20
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("condition", ["", None, "after_meal", "自行猜测", True, ["fasting"]])
async def test_invalid_stored_glucose_condition_is_rejected(glucose_repo, condition):
    """存量数据的未知或非法条件不能伪装成可解释测量。"""
    glucose_repo.measurements.return_value = ([glucose_record(condition=condition)], 1)
    with pytest.raises(HealthVisionError, match="blood_glucose_source_changed") as error:
        await glucose_repo.repo.read("actor", "health-self", PERIOD)
    assert error.value.status == 410
    glucose_repo.audit.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "values",
    [
        {},
        {"glucose": 0},
        {"glucose": True},
        {"glucose": "5.5"},
        {"glucose": float("nan")},
        {"glucose": float("inf")},
        {"glucose": 5.5, "weight": 60},
        [],
    ],
)
async def test_invalid_stored_glucose_values_are_rejected(glucose_repo, values):
    """缺失、非数值和其他指标均不能转为零值或外发。"""
    row = glucose_record()
    row.values = values
    glucose_repo.measurements.return_value = ([row], 1)
    with pytest.raises(HealthVisionError, match="blood_glucose_source_changed"):
        await glucose_repo.repo.read("actor", "health-self", PERIOD)


@pytest.mark.asyncio
@pytest.mark.parametrize("linked", [False, True])
async def test_empty_glucose_receipt_tracks_new_link_or_record(glucose_repo, linked):
    """未关联与空测量都属于后续轮次的真实依赖。"""
    state = glucose_repo
    link = state.link
    if not linked:
        state.link = None
    payload = await state.repo.read("actor", "health-self", PERIOD)
    assert payload["code"] == ("blood_glucose_missing" if linked else "blood_glucose_not_linked")
    await state.repo.record_use(SimpleNamespace(id="run", uid="actor", conversation_id=7), payload)
    query = state.session.execute.await_args.args[0].compile()
    assert "health_blood_glucose_use" in str(query) and query.params["record_refs"] == []
    assert query.params["source_member_id"] == ("formal-self" if linked else None)
    set_history(state, [weight_use(payload)])
    state.link = link
    if linked:
        state.measurements.return_value = ([glucose_record()], 1)
    with pytest.raises(HealthVisionError, match="blood_glucose_source_changed"):
        await state.repo.validate_history("actor", state.binding)


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["condition", "glucose", "revoke", "field"])
async def test_glucose_history_and_checkpoint_fail_on_condition_or_permission_change(glucose_repo, monkeypatch, change):
    """即使数值与版本未改变，条件变化也必须改变摘要并拒绝旧回执。"""
    state = glucose_repo
    row = glucose_record()
    state.measurements.return_value = ([row], 1)
    payload = await state.repo.read("actor", "health-self", PERIOD)
    receipt = weight_use(payload)
    state.session.scalar.return_value = receipt
    set_history(state, [receipt])
    await state.repo.validate_history("actor", state.binding)
    await state.repo.validate_tool_payload("actor", state.binding, payload)
    if change == "condition":
        row.condition = "after_meal_2h"
    elif change == "glucose":
        row.values = {"glucose": 5.6}
    elif change == "revoke":
        state.authorize.side_effect = HealthVisionError("not_found", "合成撤回", 404)
    else:
        monkeypatch.setattr(boundary, "authorized_fields", lambda family, member, uid: {"weight"})
    for checkpoint in (False, True):
        with pytest.raises(HealthVisionError, match="blood_glucose_source_changed") as error:
            if checkpoint:
                await state.repo.validate_tool_payload("actor", state.binding, payload)
            else:
                await state.repo.validate_history("actor", state.binding)
        assert error.value.status == 410


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["condition", "version", "hash", "receipt", "extra"])
async def test_glucose_checkpoint_rejects_forged_or_unrecorded_payload(glucose_repo, change):
    """不能用真实回执授权改写正文，缺少回执也不能仅凭当前值外发。"""
    state = glucose_repo
    state.measurements.return_value = ([glucose_record()], 1)
    payload = await state.repo.read("actor", "health-self", PERIOD)
    state.session.scalar.return_value = weight_use(payload)
    forged = deepcopy(payload)
    if change == "condition":
        forged["records"][0]["condition"] = "random"
    elif change == "version":
        forged["records"][0]["version"] = True
    elif change == "hash":
        forged["source_hash"] = {"forged": "hash"}
    elif change == "receipt":
        state.session.scalar.return_value = None
    else:
        forged["note"] = "synthetic-forged"
    with pytest.raises(HealthVisionError, match="blood_glucose_source_changed"):
        await state.repo.validate_tool_payload("actor", state.binding, forged)

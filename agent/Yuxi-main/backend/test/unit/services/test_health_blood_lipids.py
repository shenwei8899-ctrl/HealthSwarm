"""血脂四项同条原值、必要字段及独立回执失效。"""

from copy import deepcopy
from datetime import datetime
from types import SimpleNamespace

import pytest

from test.unit.services.test_health_weight import PERIOD, set_history, weight_repo, weight_use  # noqa: F401
from yuxi.repositories import health_measurement_repository as boundary
from yuxi.repositories.health_blood_lipids_repository import HealthBloodLipidsRepository
from yuxi.services.health_vision_types import HealthVisionError


@pytest.fixture
def lipids_repo(weight_repo, monkeypatch):  # noqa: F811
    """沿实际共享授权与分页边界，仅切换血脂类型和回执表。"""
    state = weight_repo
    state.repo = HealthBloodLipidsRepository(state.session)
    monkeypatch.setattr(boundary, "authorized_fields", lambda family, member, uid: {"blood_lipids"})
    return state


def lipids_record(*, values=None, version=1):
    """同一份合成测量附带不能外发的条件与更正历史。"""
    return SimpleNamespace(
        id="lipids-record",
        values={"tc": 4.5, "tg": 1.2, "hdl": 1.3, "ldl": 2.6} if values is None else values,
        condition="不得外发的自定义条件",
        measured_at=datetime(2026, 10, 8, 1, 2, 3),
        source="synthetic-lipid-lab",
        version=version,
        note="synthetic-private-note",
        previous=[{"ldl": 2.5}],
    )


@pytest.mark.asyncio
async def test_lipids_projection_preserves_same_record_four_values_without_ratios(lipids_repo):
    """整条四项及来源保持原值，未确认档案不提升专业安全状态。"""
    state = lipids_repo
    state.measurements.return_value = ([lipids_record()], 1)
    payload = await state.repo.read("actor", "health-self", PERIOD)
    assert payload["records"] == [
        {
            "record_id": "lipids-record",
            "tc": 4.5,
            "tg": 1.2,
            "hdl": 1.3,
            "ldl": 2.6,
            "unit": "mmol/L",
            "measured_at": "2026-10-08T01:02:03Z",
            "source": "synthetic-lipid-lab",
            "version": 1,
        }
    ]
    assert payload["status"] == "ready" and payload["code"] == "self_blood_lipids_records"
    assert payload["period"] == PERIOD and payload["limit"] == 20 and payload["truncated"] is False
    assert payload["full_health_profile_available"] is payload["nutrition_safety_ready"] is False
    assert "condition" not in payload["records"][0] and "synthetic-private" not in str(payload)
    state.source.version = state.source.confirmed_version = 9
    assert await state.repo.read("actor", "health-self", PERIOD) == payload
    state.measurements.assert_awaited_with(
        ["formal-self"], ["blood_lipids"], since=datetime(2026, 9, 8, 16), until=datetime(2026, 10, 8, 16), limit=20
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("missing", ["tc", "tg", "hdl", "ldl"])
async def test_lipids_missing_any_component_cannot_be_filled_or_sent(lipids_repo, missing):
    """四项中任何未知值都拒绝整条公开，不补零也不跨记录拼接。"""
    row = lipids_record()
    row.values.pop(missing)
    lipids_repo.measurements.return_value = ([row], 1)
    with pytest.raises(HealthVisionError, match="blood_lipids_source_changed") as error:
        await lipids_repo.repo.read("actor", "health-self", PERIOD)
    assert error.value.status == 410
    lipids_repo.audit.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["tc", "tg", "hdl", "ldl"])
@pytest.mark.parametrize("bad", [True, "2.6", 0, -1, float("nan"), float("inf"), None])
async def test_lipids_each_component_rejects_invalid_persisted_value(lipids_repo, field, bad):
    """持久化边界逐项拒绝非数值、非有限值和无效正值。"""
    row = lipids_record()
    row.values[field] = bad
    lipids_repo.measurements.return_value = ([row], 1)
    with pytest.raises(HealthVisionError, match="blood_lipids_source_changed"):
        await lipids_repo.repo.read("actor", "health-self", PERIOD)


@pytest.mark.asyncio
@pytest.mark.parametrize("values", [[], {}, {"tc": 4.5, "tg": 1.2, "hdl": 1.3, "ldl": 2.6, "glucose": 5.5}])
async def test_lipids_rejects_non_record_or_other_measurement_fields(lipids_repo, values):
    """不能把不同指标或非法值结构作为完整四项外发。"""
    lipids_repo.measurements.return_value = ([lipids_record(values=values)], 1)
    with pytest.raises(HealthVisionError, match="blood_lipids_source_changed"):
        await lipids_repo.repo.read("actor", "health-self", PERIOD)


@pytest.mark.asyncio
@pytest.mark.parametrize("linked", [False, True])
async def test_empty_lipids_receipt_tracks_new_link_or_record(lipids_repo, linked):
    """未关联和无记录也登记真实依赖，事实补充后旧缺口失效。"""
    state = lipids_repo
    link = state.link
    if not linked:
        state.link = None
    payload = await state.repo.read("actor", "health-self", PERIOD)
    assert payload["code"] == ("blood_lipids_missing" if linked else "blood_lipids_not_linked")
    await state.repo.record_use(SimpleNamespace(id="run", uid="actor", conversation_id=7), payload)
    query = state.session.execute.await_args.args[0].compile()
    assert "health_blood_lipids_use" in str(query) and query.params["record_refs"] == []
    assert query.params["source_member_id"] == ("formal-self" if linked else None)
    set_history(state, [weight_use(payload)])
    state.link = link
    if linked:
        state.measurements.return_value = ([lipids_record()], 1)
    with pytest.raises(HealthVisionError, match="blood_lipids_source_changed"):
        await state.repo.validate_history("actor", state.binding)


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["tc", "tg", "hdl", "ldl", "revoke", "field"])
async def test_lipids_history_and_checkpoint_reject_single_component_or_permission_change(
    lipids_repo, monkeypatch, change
):
    """单项原值变化纳入摘要，任一撤权也拒绝旧历史和checkpoint。"""
    state = lipids_repo
    row = lipids_record()
    state.measurements.return_value = ([row], 1)
    payload = await state.repo.read("actor", "health-self", PERIOD)
    receipt = weight_use(payload)
    state.session.scalar.return_value = receipt
    set_history(state, [receipt])
    await state.repo.validate_history("actor", state.binding)
    await state.repo.validate_tool_payload("actor", state.binding, payload)
    if change in {"tc", "tg", "hdl", "ldl"}:
        row.values[change] += 0.1
    elif change == "revoke":
        state.authorize.side_effect = HealthVisionError("not_found", "合成撤回", 404)
    else:
        monkeypatch.setattr(boundary, "authorized_fields", lambda family, member, uid: {"weight"})
    for checkpoint in (False, True):
        with pytest.raises(HealthVisionError, match="blood_lipids_source_changed") as error:
            if checkpoint:
                await state.repo.validate_tool_payload("actor", state.binding, payload)
            else:
                await state.repo.validate_history("actor", state.binding)
        assert error.value.status == 410


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["ldl", "version", "hash", "receipt", "extra"])
async def test_lipids_checkpoint_rejects_forged_or_unrecorded_four_item_payload(lipids_repo, change):
    """真实回执不能授权改写正文或补入非必要条件。"""
    state = lipids_repo
    state.measurements.return_value = ([lipids_record()], 1)
    payload = await state.repo.read("actor", "health-self", PERIOD)
    state.session.scalar.return_value = weight_use(payload)
    forged = deepcopy(payload)
    if change == "ldl":
        forged["records"][0]["ldl"] = 2.7
    elif change == "version":
        forged["records"][0]["version"] = True
    elif change == "hash":
        forged["source_hash"] = {"forged": "hash"}
    elif change == "receipt":
        state.session.scalar.return_value = None
    else:
        forged["records"][0]["condition"] = "自定义条件"
    with pytest.raises(HealthVisionError, match="blood_lipids_source_changed"):
        await state.repo.validate_tool_payload("actor", state.binding, forged)

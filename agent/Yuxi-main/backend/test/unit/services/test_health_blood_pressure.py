"""本人血压原值、专用回执及共享体重链路的负向验证。"""

from copy import deepcopy
from contextlib import asynccontextmanager
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from langchain_core.messages import ToolMessage
from pydantic import ValidationError

from test.unit.services.test_health_weight import PERIOD, set_history, weight_repo, weight_use  # noqa: F401
from test.unit.services.test_health_weight_publication import checkpoint_guard, tool_runtime  # noqa: F401
from yuxi.agents.toolkits.health import get_member_blood_pressure_records
from yuxi.repositories import health_measurement_repository as boundary
from yuxi.repositories.health_blood_pressure_repository import HealthBloodPressureRepository
from yuxi.repositories.health_blood_glucose_repository import HealthBloodGlucoseRepository
from yuxi.repositories.health_blood_lipids_repository import HealthBloodLipidsRepository
from yuxi.repositories.health_consultation_repository import HealthConsultationRepository
from yuxi.repositories.health_family_profile_repository import HealthFamilyProfileRepository
from yuxi.repositories.health_weight_repository import HealthWeightRepository
from yuxi.services import health_blood_pressure_service, health_consultation_service
from yuxi.services.health_agent_roles import consultation_skill_prompt, health_agent_roles
from yuxi.services.health_family_profile_service import validate_profile_publication
from yuxi.services.health_vision_types import HealthVisionError


@pytest.fixture
def bp_repo(weight_repo, monkeypatch):  # noqa: F811
    """共用真实持久化边界fixture，切换当前血压消费者与字段授权。"""
    state = weight_repo
    state.repo = HealthBloodPressureRepository(state.session)
    monkeypatch.setattr(boundary, "authorized_fields", lambda family, member, uid: {"blood_pressure"})
    return state


def bp_record(*, systolic=120, diastolic=80, version=1):
    """人工合成独立血压，含不能外发的其他属性。"""
    return SimpleNamespace(
        id="bp-record",
        values={"systolic": systolic, "diastolic": diastolic},
        measured_at=datetime(2026, 10, 8, 1, 2, 3),
        source="manual",
        version=version,
        note="synthetic-private-note",
        previous=[{"systolic": 130}],
        condition="synthetic-private-condition",
    )


@pytest.mark.asyncio
async def test_blood_pressure_is_independent_minimal_raw_projection(bp_repo):
    """档案未确认也返回原数值、mmHg和独立版本，不外发备注或作医学判断。"""
    state = bp_repo
    state.measurements.return_value = ([bp_record(systolic=120.5)], 1)
    payload = await state.repo.read("actor", "health-self", PERIOD)
    assert payload["records"] == [
        {
            "record_id": "bp-record",
            "systolic": 120.5,
            "diastolic": 80,
            "unit": "mmHg",
            "measured_at": "2026-10-08T01:02:03Z",
            "source": "manual",
            "version": 1,
        }
    ]
    assert payload["status"] == "ready" and payload["code"] == "self_blood_pressure_records"
    assert payload["period"] == PERIOD and payload["limit"] == 20 and payload["truncated"] is False
    assert payload["full_health_profile_available"] is payload["nutrition_safety_ready"] is False
    assert "synthetic-private" not in str(payload) and "confirmed_version" not in payload
    state.source.version = state.source.confirmed_version = 9
    assert await state.repo.read("actor", "health-self", PERIOD) == payload
    state.measurements.assert_awaited_with(
        ["formal-self"],
        ["blood_pressure"],
        since=datetime(2026, 9, 8, 16),
        until=datetime(2026, 10, 8, 16),
        limit=20,
    )
    state.audit.assert_awaited_with("family", "formal-self", "actor", "agent_blood_pressure_read")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "values",
    [
        {"systolic": 120},
        {"systolic": 120, "diastolic": 0},
        {"systolic": 80, "diastolic": 80},
        {"systolic": 79, "diastolic": 80},
        {"systolic": True, "diastolic": 80},
        {"systolic": 120, "diastolic": "80"},
        {"systolic": float("inf"), "diastolic": 80},
        {"systolic": 120, "diastolic": float("nan")},
        {"systolic": 120, "diastolic": 80, "weight": 60},
        [],
    ],
)
async def test_invalid_stored_blood_pressure_fails_closed(bp_repo, values):
    """已有数据也必须遵守家庭测量数值约束，非法记录不伪装为缺失。"""
    row = bp_record()
    row.values = values
    bp_repo.measurements.return_value = ([row], 1)
    with pytest.raises(HealthVisionError, match="blood_pressure_source_changed") as error:
        await bp_repo.repo.read("actor", "health-self", PERIOD)
    assert error.value.status == 410
    bp_repo.audit.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("linked", [False, True])
async def test_blood_pressure_empty_and_unlinked_use_are_real_dependencies(bp_repo, linked):
    """空集和未关联都登记专用回执，未来新增与关联使原缺口失效。"""
    state = bp_repo
    link = state.link
    if not linked:
        state.link = None
    payload = await state.repo.read("actor", "health-self", PERIOD)
    assert payload["code"] == ("blood_pressure_missing" if linked else "blood_pressure_not_linked")
    await state.repo.record_use(SimpleNamespace(id="run", uid="actor", conversation_id=7), payload)
    query = state.session.execute.await_args.args[0].compile()
    assert "health_blood_pressure_use" in str(query) and query.params["record_refs"] == []
    assert query.params["member_id"] == "health-self" and query.params["source_member_id"] == (
        "formal-self" if linked else None
    )
    set_history(state, [weight_use(payload)])
    state.link = link
    if linked:
        state.measurements.return_value = ([bp_record()], 1)
    with pytest.raises(HealthVisionError, match="blood_pressure_source_changed"):
        await state.repo.validate_history("actor", state.binding)


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["correction", "source", "field", "revoke", "truncated"])
async def test_blood_pressure_history_invalidates_without_new_tool(bp_repo, monkeypatch, change):
    """独立版本、来源、范围选择和字段授权变化均让派生历史停止复用。"""
    state = bp_repo
    state.measurements.return_value = ([bp_record()], 1)
    payload = await state.repo.read("actor", "health-self", PERIOD)
    set_history(state, [weight_use(payload)])
    state.audit.reset_mock()
    if change == "correction":
        state.measurements.return_value = ([bp_record(systolic=121, diastolic=81, version=2)], 1)
    elif change == "source":
        state.source.id = "other-source"
    elif change == "field":
        monkeypatch.setattr(boundary, "authorized_fields", lambda family, member, uid: {"weight"})
    elif change == "revoke":
        state.authorize.side_effect = HealthVisionError("not_found", "合成撤回", 404)
    else:
        state.measurements.return_value = ([bp_record() for _ in range(21)], 21)
    with pytest.raises(HealthVisionError, match="blood_pressure_source_changed") as error:
        await state.repo.validate_history("actor", state.binding)
    assert error.value.status == 410
    state.audit.assert_not_awaited()
    assert state.authorize.await_args.kwargs["lock"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["systolic", "diastolic", "version_bool", "number_float", "extra"])
async def test_real_receipt_cannot_authorize_blood_pressure_checkpoint_tampering(bp_repo, change):
    """真实线程回执不能授权伪造数值、Python相等的JSON类型或额外正文。"""
    state = bp_repo
    state.measurements.return_value = ([bp_record()], 1)
    current = await state.repo.read("actor", "health-self", PERIOD)
    state.session.scalar.return_value = weight_use(current)
    await state.repo.validate_tool_payload("actor", state.binding, current)
    forged = deepcopy(current)
    if change in {"systolic", "diastolic"}:
        forged["records"][0][change] += 1
    elif change == "version_bool":
        forged["records"][0]["version"] = True
        assert forged == current
    elif change == "number_float":
        forged["records"][0]["systolic"] = 120.0
        assert forged == current
    else:
        forged["note"] = "synthetic-forged"
    with pytest.raises(HealthVisionError, match="blood_pressure_source_changed"):
        await state.repo.validate_tool_payload("actor", state.binding, forged)


@pytest.mark.asyncio
async def test_current_blood_pressure_without_receipt_is_not_a_trusted_checkpoint(bp_repo):
    """即使正文与当前读取一致，未经工具持久登记也拒绝进入模型。"""
    current = await bp_repo.repo.read("actor", "health-self", PERIOD)
    with pytest.raises(HealthVisionError, match="blood_pressure_source_changed"):
        await bp_repo.repo.validate_tool_payload("actor", bp_repo.binding, current)
    assert "health_blood_pressure_use" in str(bp_repo.session.scalar.await_args.args[0])


@pytest.mark.asyncio
@pytest.mark.parametrize("source_hash", [{"forged": "hash"}, ["forged"], True, None])
async def test_forged_hash_json_types_fail_before_database_lookup(bp_repo, source_hash):
    """模型工具JSON不能让回执查询收到非字符串hash参数。"""
    payload = await bp_repo.repo.read("actor", "health-self", PERIOD)
    payload["source_hash"] = source_hash
    with pytest.raises(HealthVisionError, match="blood_pressure_source_changed"):
        await bp_repo.repo.validate_tool_payload("actor", bp_repo.binding, payload)
    bp_repo.session.scalar.assert_not_awaited()


@pytest.mark.asyncio
async def test_stored_receipt_refs_cannot_replace_version_with_boolean(bp_repo):
    """持久化JSON回执与原测量版本必须按JSON类型精确核对。"""
    state = bp_repo
    state.measurements.return_value = ([bp_record()], 1)
    payload = await state.repo.read("actor", "health-self", PERIOD)
    receipt = weight_use(payload)
    receipt.record_refs[0]["version"] = True
    state.session.scalar.return_value = receipt
    set_history(state, [receipt])
    with pytest.raises(HealthVisionError, match="blood_pressure_source_changed"):
        await state.repo.validate_history("actor", state.binding)
    with pytest.raises(HealthVisionError, match="blood_pressure_source_changed"):
        await state.repo.validate_tool_payload("actor", state.binding, payload)


def test_blood_pressure_tool_has_no_model_query_arguments_and_remains_partial():
    """工具的身份及日期不可选；角色目录和发布Skill仍明确安全范围未完成。"""
    assert get_member_blood_pressure_records.tool_call_schema.model_json_schema()["properties"] == {}
    for field in ("uid", "member_id", "thread_id", "kind", "period", "limit"):
        with pytest.raises(ValidationError):
            get_member_blood_pressure_records.args_schema.model_validate({"runtime": tool_runtime(), field: "forged"})
    assert "get_member_blood_pressure_records" in consultation_skill_prompt()
    roles = {item["role"]: item for item in health_agent_roles()["roles"]}
    assert roles["health-profile"]["status"] == "partial"
    assert health_agent_roles()["full_health_profile_available"] is False


@pytest.mark.asyncio
async def test_blood_pressure_tool_delegates_only_injected_context(monkeypatch):
    """模型无法替换服务端上下文，授权错误不被吞掉。"""
    runtime = tool_runtime()
    read = AsyncMock(return_value={"code": "blood_pressure_missing", "records": []})
    monkeypatch.setattr(health_blood_pressure_service, "blood_pressure_records_for_run", read)
    assert await get_member_blood_pressure_records.ainvoke({"runtime": runtime}) == read.return_value
    read.assert_awaited_once_with(runtime.context)
    read.side_effect = HealthVisionError("consent_required", "合成撤回", 403)
    with pytest.raises(HealthVisionError, match="consent_required"):
        await get_member_blood_pressure_records.ainvoke({"runtime": runtime})


@pytest.mark.asyncio
@pytest.mark.parametrize("content", ['{"records":[]}', "not-json", '{"records":'])
async def test_blood_pressure_checkpoint_guard_selects_own_repository(checkpoint_guard, monkeypatch, content):  # noqa: F811
    """血压checkpoint走专用依赖表，非法JSON在进入数据库前明确失效。"""
    validate = AsyncMock()
    monkeypatch.setattr(HealthBloodPressureRepository, "validate_tool_payload", validate)
    message = ToolMessage(name="get_member_blood_pressure_records", tool_call_id="bp-call", content=content)
    if content == '{"records":[]}':
        await health_consultation_service.require_consultation_attempt(checkpoint_guard.context, [message])
        validate.assert_awaited_once_with(checkpoint_guard.context.uid, checkpoint_guard.binding, {"records": []})
    else:
        with pytest.raises(HealthVisionError, match="blood_pressure_source_changed"):
            await health_consultation_service.require_consultation_attempt(checkpoint_guard.context, [message])
        validate.assert_not_awaited()
    checkpoint_guard.validate.assert_not_awaited()


@pytest.mark.asyncio
async def test_consultation_and_final_publication_recheck_both_measurement_dependencies(monkeypatch):
    """真实authorize编排在只读和发布锁边界分别重验体重、血压和档案。"""
    binding = SimpleNamespace(
        member_id="health-self",
        conversation_id=7,
        initial_planner_selection=None,
        family_planner_selection=None,
        personal_target_selection=None,
    )
    conversation = SimpleNamespace(agent_id="health-consultation")

    async def scalar(statement):
        """绑定查询返回当前行；精确目标依赖查询没有匹配Run。"""
        if "personal_target_selection_hash" in statement.compile().params.values():
            assert "agent_runs.conversation_id" in str(statement)
            assert binding.conversation_id in statement.compile().params.values()
            return None
        assert "FROM health_consultation JOIN conversations" in str(statement)
        return binding

    session = SimpleNamespace(scalar=AsyncMock(side_effect=scalar), get=AsyncMock(return_value=conversation))
    monkeypatch.setattr(boundary.HealthVisionRepository, "authorize", AsyncMock())
    profile, weight, bp = AsyncMock(), AsyncMock(), AsyncMock()
    monkeypatch.setattr(HealthFamilyProfileRepository, "validate_history", profile)
    monkeypatch.setattr(HealthWeightRepository, "validate_history", weight)
    monkeypatch.setattr(HealthBloodPressureRepository, "validate_history", bp)
    monkeypatch.setattr(HealthBloodGlucoseRepository, "validate_history", AsyncMock())
    monkeypatch.setattr(HealthBloodLipidsRepository, "validate_history", AsyncMock())
    await HealthConsultationRepository(session).authorize("actor", "thread")
    for guard in (profile, weight, bp):
        guard.assert_awaited_once_with("actor", binding, lock=False)

    async def require(session, uid, thread_id, *, expected, lock):
        """保留来源授权编排，隔离本测试无关的配置与Skill读取。"""
        assert lock is True and expected == {"processor": "approved"}
        return await HealthConsultationRepository(session).authorize(uid, thread_id, lock=lock), expected

    monkeypatch.setattr(health_consultation_service, "require_consultation", require)
    run = SimpleNamespace(
        uid="actor",
        conversation_thread_id="thread",
        input_payload={"health_processing": {"processor": "approved"}, "model": "provider/fixed"},
    )
    bp.side_effect = HealthVisionError("blood_pressure_source_changed", "合成迟到更正", 410)
    with pytest.raises(HealthVisionError, match="blood_pressure_source_changed"):
        await validate_profile_publication(session, run)
    bp.assert_awaited_with("actor", binding, lock=True)


@pytest.mark.asyncio
@pytest.mark.parametrize("approved", [False, True])
async def test_blood_pressure_run_service_requires_attempt_and_frozen_approval(monkeypatch, approved):
    """血压外呼前持有效attempt与冻结同意，来源成员始终来自当前绑定。"""
    session = object()

    @asynccontextmanager
    async def transaction():
        """隔离数据库连接，验证拥有事务的实际服务顺序。"""
        yield session

    context = tool_runtime().context
    snapshot = {"processor": "approved"} if approved else None
    run = SimpleNamespace(input_payload={"health_processing": snapshot})
    binding = SimpleNamespace(member_id="server-bound")
    attempt = AsyncMock(return_value=run)
    require = AsyncMock(return_value=(binding, snapshot))
    read, record = AsyncMock(return_value={"records": []}), AsyncMock()
    monkeypatch.setattr(health_blood_pressure_service.pg_manager, "get_async_session_context", transaction)
    monkeypatch.setattr(health_blood_pressure_service.HealthConsultationRepository, "require_attempt", attempt)
    monkeypatch.setattr(health_consultation_service, "require_consultation", require)
    monkeypatch.setattr(HealthBloodPressureRepository, "read", read)
    monkeypatch.setattr(HealthBloodPressureRepository, "record_use", record)
    if approved:
        assert await health_blood_pressure_service.blood_pressure_records_for_run(context) == {"records": []}
        require.assert_awaited_once_with(
            session, context.uid, context.thread_id, context.model, expected=snapshot, lock=True
        )
        read.assert_awaited_once_with(context.uid, "server-bound")
        record.assert_awaited_once_with(run, {"records": []})
    else:
        with pytest.raises(HealthVisionError, match="policy_changed"):
            await health_blood_pressure_service.blood_pressure_records_for_run(context)
        require.assert_not_awaited()
        read.assert_not_awaited()
        record.assert_not_awaited()
    attempt.assert_awaited_once_with(context, lock=True)

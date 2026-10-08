"""本人实测体重的最小投影、冻结范围和真实依赖边界。"""

from contextlib import asynccontextmanager
from copy import deepcopy
from datetime import UTC, date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.exc import SQLAlchemyError

from yuxi.repositories import health_weight_repository as repository
from yuxi.repositories import health_measurement_repository as measurement_boundary
from yuxi.services import health_weight_service as service
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.storage.postgres.models_health import HealthConsultation, HealthFamilyProfileLink

PERIOD = {"start_date": "2026-09-09", "end_date": "2026-10-08", "timezone": "Asia/Shanghai"}


@pytest.fixture
def weight_repo(monkeypatch):
    """仅伪造持久化读取，保留真实投影、时间边界和依赖校验代码。"""
    health = SimpleNamespace(owner_uid="actor", relationship_label="本人")
    binding = SimpleNamespace(member_id="health-self", actor_uid="actor", conversation_id=7)
    link = SimpleNamespace(
        member_id="health-self", source_member_id="formal-self", family_id="family", actor_uid="actor"
    )
    source = SimpleNamespace(id="formal-self", subject_uid="actor", profile={}, version=8, confirmed_version=None)

    async def get(model, key, **kwargs):
        if model is HealthFamilyProfileLink:
            return state.link
        if model is HealthConsultation:
            return binding
        raise AssertionError(model)

    session = SimpleNamespace(
        get=AsyncMock(side_effect=get),
        execute=AsyncMock(),
        scalar=AsyncMock(return_value=None),
        scalars=AsyncMock(return_value=SimpleNamespace(all=lambda: [])),
    )
    authorize = AsyncMock(return_value=health)
    source_read = AsyncMock(return_value=(SimpleNamespace(owner_uid="actor"), source))
    measurements, audit = AsyncMock(return_value=[]), AsyncMock()
    monkeypatch.setattr(measurement_boundary.HealthVisionRepository, "authorize", authorize)
    monkeypatch.setattr(measurement_boundary.HealthFamilyProfileRepository, "source", source_read)
    monkeypatch.setattr(measurement_boundary.FamilyRepository, "measurements", measurements)
    monkeypatch.setattr(measurement_boundary.FamilyRepository, "audit", audit)
    monkeypatch.setattr(measurement_boundary, "authorized_fields", lambda family, member, uid: {"weight"})
    state = SimpleNamespace(
        repo=repository.HealthWeightRepository(session),
        session=session,
        health=health,
        binding=binding,
        link=link,
        source=source,
        authorize=authorize,
        source_read=source_read,
        measurements=measurements,
        audit=audit,
    )
    return state


def weight_record(record_id="weight-record", *, value=60.5, version=1):
    """正文包含不应外发的备注、历史和非体重字段。"""
    return SimpleNamespace(
        id=record_id,
        values={"weight": value},
        measured_at=datetime(2026, 10, 8, 1, 2, 3),
        source="manual",
        version=version,
        note="synthetic-private-note",
        previous=[{"values": {"weight": 50}, "note": "synthetic-private-history"}],
        condition="synthetic-private-condition",
        private_other_metric=999,
    )


def weight_use(payload):
    """构造持久化引用形状，不从生产hash算法计算期望正文。"""
    return SimpleNamespace(
        payload_hash=payload["source_hash"],
        member_id=payload["member_id"],
        source_member_id=payload["source_member_id"],
        start_date=date(2026, 9, 9),
        end_date=date(2026, 10, 8),
        record_refs=[{"record_id": row["record_id"], "version": row["version"]} for row in payload["records"]],
    )


def set_history(state, uses):
    """让真实线程依赖查询返回预先登记的引用。"""
    state.session.scalars.return_value = SimpleNamespace(all=lambda: uses)


@pytest.mark.asyncio
async def test_read_projects_only_independent_weight_without_profile_confirmation(weight_repo):
    """基础档案尚未确认也可读实测，只返回必要字段和独立版本。"""
    state = weight_repo
    state.measurements.return_value = [weight_record()]
    payload = await state.repo.read("actor", "health-self", PERIOD)
    assert payload["records"] == [
        {
            "record_id": "weight-record",
            "value": 60.5,
            "unit": "kg",
            "measured_at": "2026-10-08T01:02:03Z",
            "source": "manual",
            "version": 1,
        }
    ]
    assert payload["status"] == "ready" and payload["code"] == "self_weight_records"
    assert payload["member_id"] == "health-self" and payload["source_member_id"] == "formal-self"
    assert payload["limit"] == 20 and payload["period"] == PERIOD and not payload["truncated"]
    assert payload["full_health_profile_available"] is payload["nutrition_safety_ready"] is False
    assert "synthetic-private" not in str(payload) and "confirmed_version" not in payload
    state.authorize.assert_awaited_once_with("health-self", "actor", "profile_view", lock=True)
    state.source_read.assert_awaited_once_with("actor", state.link, lock=True)
    state.measurements.assert_awaited_once_with(
        ["formal-self"], ["weight"], since=datetime(2026, 9, 8, 16), until=datetime(2026, 10, 8, 16), limit=21
    )
    state.audit.assert_awaited_once_with("family", "formal-self", "actor", "agent_weight_read")


@pytest.mark.asyncio
async def test_original_weight_json_hash_remains_compatible_after_shared_repository(weight_repo):
    """旧体重协议固定anchor来自改造前源码，不用当前producer生成预期摘要。"""
    state = weight_repo
    state.measurements.return_value = [weight_record(value=60)]
    payload = await state.repo.read("actor", "health-self", PERIOD)
    assert payload["source_hash"] == "4d111a0bbaba5caded3a1f767c01f096742d3533ff04a5bcb6894f4bca66a0ba"


def test_current_range_uses_thirty_shanghai_natural_days(monkeypatch):
    """UTC仍为前一天时，范围以北京时间日期计算并包含当天整天。"""

    class FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 10, 7, 16, 3, tzinfo=UTC).astimezone(tz)

    monkeypatch.setattr(measurement_boundary, "datetime", FrozenDatetime)
    period, since, until = repository.HealthWeightRepository.period_window()
    assert period == PERIOD
    assert since == datetime(2026, 9, 8, 16) and until == datetime(2026, 10, 8, 16)


@pytest.mark.parametrize(
    "period",
    [
        [],
        {},
        {**PERIOD, "timezone": "UTC"},
        {**PERIOD, "start_date": "2026-09-08"},
        {**PERIOD, "end_date": "2026-10-09"},
        {**PERIOD, "start_date": "20260909"},
        {**PERIOD, "end_date": None},
        {**PERIOD, "extra": "forged"},
        {"start_date": "9999-12-02", "end_date": "9999-12-31", "timezone": "Asia/Shanghai"},
    ],
)
def test_frozen_range_rejects_noncanonical_or_expanded_period(period):
    """checkpoint不能改变时区、扩大范围或携带额外查询指令。"""
    with pytest.raises(HealthVisionError, match="weight_source_changed"):
        repository.HealthWeightRepository.period_window(period)


@pytest.mark.asyncio
async def test_read_truncates_at_twenty_and_hash_includes_selection(weight_repo):
    """第21条仅确定截断状态，未外发数据变化不编造额外记录。"""
    state = weight_repo
    state.measurements.return_value = [weight_record(f"record-{index}") for index in range(21)]
    payload = await state.repo.read("actor", "health-self", PERIOD)
    assert len(payload["records"]) == 20 and payload["truncated"] is True
    assert [row["record_id"] for row in payload["records"]] == [f"record-{index}" for index in range(20)]
    assert payload["source_hash"] == state.repo.payload_hash({**payload, "source_hash": "forged-self-hash"})
    assert state.repo.payload_hash({**payload, "truncated": False}) != payload["source_hash"]


@pytest.mark.asyncio
async def test_independent_measurement_hash_does_not_depend_on_profile_version(weight_repo):
    """仅编辑或确认基础档案不改变独立测量的引用摘要。"""
    state = weight_repo
    state.measurements.return_value = [weight_record()]
    original = await state.repo.read("actor", "health-self", PERIOD)
    state.source.version = 9
    state.source.confirmed_version = 9
    state.source.profile = {"height_cm": 172}
    current = await state.repo.read("actor", "health-self", PERIOD)
    assert current == original


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "values",
    [
        {"weight": 0},
        {"weight": -1},
        {"weight": float("nan")},
        {"weight": float("inf")},
        {"weight": True},
        {"weight": None},
        {"weight": "60"},
        {},
        {"weight": 60, "glucose": 5},
        [],
    ],
)
async def test_invalid_persisted_weight_cannot_be_sent_or_disguised_as_missing(weight_repo, values):
    """持久化边界拒绝非法实测，缺失查询结果与无效记录严格区分。"""
    state = weight_repo
    record = weight_record()
    record.values = values
    state.measurements.return_value = [record]
    with pytest.raises(HealthVisionError, match="weight_source_changed") as error:
        await state.repo.read("actor", "health-self", PERIOD)
    assert error.value.status == 410
    state.audit.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("field,value", [("owner_uid", "other"), ("relationship_label", "母亲")])
async def test_health_access_does_not_allow_nonself_weight(weight_repo, field, value):
    """管理员或健康授权不能把他人对象当成本人实测来源。"""
    state = weight_repo
    setattr(state.health, field, value)
    with pytest.raises(HealthVisionError) as error:
        await state.repo.read("actor", "health-self", PERIOD)
    assert error.value.status == 404
    state.source_read.assert_not_awaited()
    state.measurements.assert_not_awaited()


@pytest.mark.asyncio
async def test_missing_formal_weight_field_fails_before_measurements(weight_repo, monkeypatch):
    """正式家庭字段授权也须覆盖weight，不能因本人健康授权省略校验。"""
    state = weight_repo
    monkeypatch.setattr(measurement_boundary, "authorized_fields", lambda family, member, uid: {"height_cm"})
    with pytest.raises(HealthVisionError) as error:
        await state.repo.read("actor", "health-self", PERIOD)
    assert error.value.status == 403
    state.measurements.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("linked", [False, True])
async def test_empty_or_unlinked_reads_still_record_server_bound_dependency(weight_repo, linked):
    """未关联和空结果都记录引用，避免后续新增数据被当作没有依赖。"""
    state = weight_repo
    if not linked:
        state.link = None
    payload = await state.repo.read("actor", "health-self", PERIOD)
    assert payload["status"] == "not_ready" and payload["records"] == []
    assert payload["code"] == ("weight_missing" if linked else "weight_not_linked")
    run = SimpleNamespace(id="run", uid="actor", conversation_id=7)
    await state.repo.record_use(run, payload)
    query = state.session.execute.await_args.args[0].compile()
    assert query.params["member_id"] == "health-self"
    assert query.params["source_member_id"] == ("formal-self" if linked else None)
    assert query.params["record_refs"] == [] and query.params["start_date"] == date(2026, 9, 9)
    assert query.params["end_date"] == date(2026, 10, 8)
    assert "note" not in str(query.params) and "value" not in query.params


@pytest.mark.asyncio
async def test_record_use_rejects_member_from_payload_instead_of_server_binding(weight_repo):
    """保存回执时成员必须来自真实consultation，而非工具正文的伪造ID。"""
    state = weight_repo
    payload = await state.repo.read("actor", "health-self", PERIOD)
    payload["member_id"] = "other-member"
    with pytest.raises(HealthVisionError, match="weight_source_changed"):
        await state.repo.record_use(SimpleNamespace(id="run", uid="actor", conversation_id=7), payload)
    state.session.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_history_keeps_frozen_period_and_no_write_locks_or_audit(weight_repo, monkeypatch):
    """历史翌日或多年后重验原查询区间；只读访问不反向取得家庭写锁。"""
    state = weight_repo
    state.measurements.return_value = [weight_record()]
    payload = await state.repo.read("actor", "health-self", PERIOD)
    set_history(state, [weight_use(payload)])
    state.source_read.reset_mock()
    state.audit.reset_mock()

    class FutureDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            raise AssertionError("历史重读不可重新选取今天的日期范围")

    monkeypatch.setattr(measurement_boundary, "datetime", FutureDatetime)
    await state.repo.validate_history("actor", state.binding)
    state.source_read.assert_awaited_once_with("actor", state.link, lock=False)
    assert state.authorize.await_args.kwargs["lock"] is False
    assert state.measurements.await_args.kwargs["since"] == datetime(2026, 9, 8, 16)
    state.audit.assert_not_awaited()
    query = str(state.session.scalars.await_args.args[0])
    assert "conversation_id" in query and "agent_runs.uid" in query


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["correction", "numeric_body", "source", "empty_insert", "unlink", "link"])
async def test_thread_dependency_invalidates_correction_and_empty_selection_changes(weight_repo, change):
    """即使下一轮不调用工具，已引用记录、空结果和来源变化也阻止旧回答。"""
    state = weight_repo
    if change not in {"empty_insert", "link"}:
        state.measurements.return_value = [weight_record()]
    if change == "link":
        state.link = None
    payload = await state.repo.read("actor", "health-self", PERIOD)
    set_history(state, [weight_use(payload)])
    if change == "correction":
        state.measurements.return_value = [weight_record(version=2)]
    elif change == "numeric_body":
        state.measurements.return_value = [weight_record(value=61.5)]
    elif change == "source":
        state.source.id = "different-formal-self"
    elif change == "empty_insert":
        state.measurements.return_value = [weight_record()]
    elif change == "unlink":
        state.link = None
    else:
        state.link = SimpleNamespace(family_id="family")
    with pytest.raises(HealthVisionError) as error:
        await state.repo.validate_history("actor", state.binding)
    assert error.value.code == "weight_source_changed" and error.value.status == 410


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [403, 404])
async def test_history_source_or_authorization_revocation_becomes_explicit_invalidation(weight_repo, status):
    """已登记依赖的权限或正式来源撤回，统一为旧输入失效。"""
    state = weight_repo
    payload = await state.repo.read("actor", "health-self", PERIOD)
    set_history(state, [weight_use(payload)])
    state.authorize.side_effect = HealthVisionError("not_found", "合成撤回", status)
    with pytest.raises(HealthVisionError, match="weight_source_changed") as error:
        await state.repo.validate_history("actor", state.binding)
    assert error.value.status == 410


@pytest.mark.asyncio
async def test_history_does_not_mask_database_error(weight_repo):
    """数据库故障不能被伪装为用户更正或授权撤回。"""
    state = weight_repo
    payload = await state.repo.read("actor", "health-self", PERIOD)
    set_history(state, [weight_use(payload)])
    state.authorize.side_effect = SQLAlchemyError("synthetic database unavailable")
    with pytest.raises(SQLAlchemyError):
        await state.repo.validate_history("actor", state.binding)


@pytest.mark.asyncio
@pytest.mark.parametrize("ready", [False, True])
async def test_checkpoint_requires_real_thread_receipt_even_for_missing_result(weight_repo, ready):
    """自洽hash或真实当前空结果不能替代真实线程已登记的外呼依赖。"""
    state = weight_repo
    if ready:
        state.measurements.return_value = [weight_record()]
    payload = await state.repo.read("actor", "health-self", PERIOD)
    with pytest.raises(HealthVisionError, match="weight_source_changed"):
        await state.repo.validate_tool_payload("actor", state.binding, payload)
    state.session.scalar.return_value = weight_use(payload)
    await state.repo.validate_tool_payload("actor", state.binding, payload)
    query = str(state.session.scalar.await_args.args[0])
    assert "conversation_id" in query and "agent_runs.uid" in query and "health_weight_use.member_id" in query
    assert state.source_read.await_args.kwargs["lock"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["value", "extra_body", "source", "period", "refs"])
async def test_checkpoint_rejects_forged_body_or_receipt_metadata(weight_repo, change):
    """真实回执也不能授权伪造正文、来源、冻结范围或引用版本。"""
    state = weight_repo
    state.measurements.return_value = [weight_record()]
    payload = await state.repo.read("actor", "health-self", PERIOD)
    use = weight_use(payload)
    state.session.scalar.return_value = use
    payload = deepcopy(payload)
    if change == "value":
        payload["records"][0]["value"] = 99
    elif change == "extra_body":
        payload["note"] = "synthetic-private-forged"
    elif change == "source":
        use.source_member_id = "other-member"
    elif change == "period":
        use.end_date = date(2026, 10, 9)
    else:
        use.record_refs[0]["version"] = 3
    with pytest.raises(HealthVisionError, match="weight_source_changed"):
        await state.repo.validate_tool_payload("actor", state.binding, payload)


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["version_bool", "truncated_int", "limit_float", "value_float"])
async def test_checkpoint_rejects_equal_python_values_with_changed_json_types(weight_repo, change):
    """真实摘要不能掩盖JSON类型篡改，即使Python相等判断仍成立。"""
    state = weight_repo
    state.measurements.return_value = [weight_record(value=60, version=1)]
    current = await state.repo.read("actor", "health-self", PERIOD)
    state.session.scalar.return_value = weight_use(current)
    payload = deepcopy(current)
    if change == "version_bool":
        payload["records"][0]["version"] = True
    elif change == "truncated_int":
        payload["truncated"] = 0
    elif change == "limit_float":
        payload["limit"] = 20.0
    else:
        payload["records"][0]["value"] = 60.0
    assert payload == current and payload["source_hash"] == current["source_hash"]
    with pytest.raises(HealthVisionError, match="weight_source_changed") as error:
        await state.repo.validate_tool_payload("actor", state.binding, payload)
    assert error.value.status == 410


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", [None, [], {}, {"status": "not_ready"}])
async def test_checkpoint_rejects_unstructured_payload(weight_repo, payload):
    """旧缺口形状或不可核对输入不能默认放行。"""
    with pytest.raises(HealthVisionError, match="weight_source_changed"):
        await weight_repo.repo.validate_tool_payload("actor", weight_repo.binding, payload)


@pytest.mark.asyncio
@pytest.mark.parametrize("snapshot", [None, {"processor": "approved", "policy_version": "policy"}])
async def test_run_service_requires_attempt_frozen_approval_and_server_binding(monkeypatch, snapshot):
    """Agent路径先验当前attempt和冻结同意，再按服务端member保存空结果依赖。"""
    from yuxi.services import health_consultation_service

    session = object()

    @asynccontextmanager
    async def session_context():
        yield session

    context = SimpleNamespace(uid="actor", thread_id="thread", model="provider/fixed")
    run = SimpleNamespace(input_payload={"health_processing": snapshot})
    binding = SimpleNamespace(member_id="bound-self")
    attempt = AsyncMock(return_value=run)
    require = AsyncMock(return_value=(binding, snapshot))
    read = AsyncMock(return_value={"status": "not_ready"})
    record = AsyncMock()
    monkeypatch.setattr(service.pg_manager, "get_async_session_context", session_context)
    monkeypatch.setattr(service.HealthConsultationRepository, "require_attempt", attempt)
    monkeypatch.setattr(health_consultation_service, "require_consultation", require)
    monkeypatch.setattr(service.HealthWeightRepository, "read", read)
    monkeypatch.setattr(service.HealthWeightRepository, "record_use", record)
    if snapshot is None:
        with pytest.raises(HealthVisionError, match="policy_changed"):
            await service.weight_records_for_run(context)
        require.assert_not_awaited()
        read.assert_not_awaited()
        record.assert_not_awaited()
    else:
        assert await service.weight_records_for_run(context) == {"status": "not_ready"}
        require.assert_awaited_once_with(session, "actor", "thread", "provider/fixed", expected=snapshot, lock=True)
        read.assert_awaited_once_with("actor", "bound-self")
        record.assert_awaited_once_with(run, {"status": "not_ready"})
    attempt.assert_awaited_once_with(context, lock=True)

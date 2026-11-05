"""真实记餐服务区分说话账号本人和咨询绑定的家人。"""

from contextlib import asynccontextmanager
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from yuxi.services import health_chat_meal_service as service
from yuxi.services import health_consultation_service
from yuxi.services.health_chat_meal_types import ChatMealStatement
from yuxi.services.health_vision_types import HealthVisionError


@pytest.fixture
def recording_dependencies(monkeypatch):
    """保留真实服务与原文解析，仅替代数据库、咨询审批和最终写入边界。"""
    session = object()

    @asynccontextmanager
    async def session_context():
        yield session

    mother = SimpleNamespace(id=str(uuid4()), owner_uid="actor", relationship_label="母亲", display_name="合成妈妈")
    self_member = SimpleNamespace(
        id=str(uuid4()), owner_uid="actor", relationship_label="本人", display_name="合成本人"
    )
    source = SimpleNamespace(id=str(uuid4()), content="我今天午餐吃了米饭", created_at=datetime(2026, 11, 6, 4))
    snapshot = {"model": "synthetic/fixed", "processor": "synthetic", "policy_version": "synthetic"}
    run = SimpleNamespace(
        agent_slug="health-consultation", request_id=str(uuid4()), input_payload={"health_processing": snapshot}
    )
    binding = SimpleNamespace(member_id=mother.id)
    access = AsyncMock(return_value=[(mother, {"ai_use", "diet_edit"}), (self_member, {"ai_use", "diet_edit"})])
    authorize, consent, record = AsyncMock(), AsyncMock(), AsyncMock()
    monkeypatch.setattr(service.pg_manager, "get_async_session_context", session_context)
    monkeypatch.setattr(service.HealthConsultationRepository, "require_attempt", AsyncMock(return_value=run))
    monkeypatch.setattr(
        health_consultation_service, "require_consultation", AsyncMock(return_value=(binding, snapshot))
    )
    monkeypatch.setattr(service.HealthMemoryRepository, "source_message", AsyncMock(return_value=source))
    monkeypatch.setattr(service.HealthVisionRepository, "list_member_access", access)
    monkeypatch.setattr(service.HealthVisionRepository, "authorize", authorize)
    monkeypatch.setattr(service.HealthVisionRepository, "require_consent", consent)
    monkeypatch.setattr(service.HealthChatMealRepository, "user_sources", AsyncMock(return_value=[source]))
    monkeypatch.setattr(service, "record_meal", record)
    monkeypatch.setattr(service, "chat_meal_receipts", AsyncMock(return_value=[]))
    return SimpleNamespace(
        context=SimpleNamespace(uid="actor", thread_id="thread", model=snapshot["model"]),
        mother=mother,
        self_member=self_member,
        source=source,
        access=access,
        authorize=authorize,
        consent=consent,
        record=record,
    )


@pytest.mark.asyncio
async def test_first_person_records_account_self_in_family_consultation(recording_dependencies):
    """咨询绑定妈妈时，“我”仍把实际摄入写到当前账号的本人。"""
    deps = recording_dependencies
    statement = ChatMealStatement(source_quotes=[deps.source.content], meal_type="lunch", items=[{"name": "米饭"}])

    await service.record_chat_meal(deps.context, statement)

    data = deps.record.await_args.args[1]
    assert str(data.member_id) == deps.self_member.id and str(data.member_id) != deps.mother.id
    assert data.meal.items[0].name == "米饭"
    assert {call.args[0] for call in deps.authorize.await_args_list} == {deps.self_member.id}
    assert {call.args[0] for call in deps.consent.await_args_list} == {deps.self_member.id}


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["missing", "foreign_owner", "non_self_label", "ambiguous", "missing_scope"])
async def test_first_person_without_unique_authorized_self_never_records_family(recording_dependencies, case):
    """本人缺失、身份不符、重名或缺记餐授权时不能借家人绑定落盘。"""
    deps = recording_dependencies
    members = [(deps.mother, {"ai_use", "diet_edit"})]
    if case != "missing":
        if case == "foreign_owner":
            deps.self_member.owner_uid = "other"
        elif case == "non_self_label":
            deps.self_member.relationship_label = "母亲"
        members.append((deps.self_member, {"ai_use"} if case == "missing_scope" else {"ai_use", "diet_edit"}))
        if case == "ambiguous":
            members.append(
                (
                    SimpleNamespace(id=str(uuid4()), owner_uid="actor", relationship_label="本人"),
                    {"ai_use", "diet_edit"},
                )
            )
    deps.access.return_value = members
    statement = ChatMealStatement(source_quotes=[deps.source.content], meal_type="lunch", items=[{"name": "米饭"}])

    with pytest.raises(HealthVisionError, match="meal_subject_unclear") as denied:
        await service.record_chat_meal(deps.context, statement)

    assert denied.value.status == 422
    deps.record.assert_not_awaited()
    deps.authorize.assert_not_awaited()
    deps.consent.assert_not_awaited()


@pytest.mark.asyncio
async def test_explicit_family_subject_keeps_independent_recording_authorization(recording_dependencies):
    """明确妈妈的实际摄入仍按目标成员分别校验授权和用途同意。"""
    deps = recording_dependencies
    deps.source.content = "妈妈今天午餐吃了米饭"
    statement = ChatMealStatement(
        subject="妈妈", source_quotes=[deps.source.content], meal_type="lunch", items=[{"name": "米饭"}]
    )

    await service.record_chat_meal(deps.context, statement)

    assert str(deps.record.await_args.args[1].member_id) == deps.mother.id
    assert [call.args for call in deps.authorize.await_args_list] == [
        (deps.mother.id, "actor", "ai_use"),
        (deps.mother.id, "actor", "diet_edit"),
        (deps.mother.id, "actor", "ai_use"),
    ]
    assert deps.consent.await_count == 2

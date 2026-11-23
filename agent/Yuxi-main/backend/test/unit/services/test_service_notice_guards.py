"""从真实发起及恢复入口证明未确认账号不会先调用模型或排队。"""

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

from fastapi import HTTPException
import pytest

from yuxi.services import daily_arrangement_tasks as daily_tasks
from yuxi.services import daily_arrangement_service as daily
from yuxi.services import health_consultation_service as consultation
from yuxi.services import health_intent_router_service as intent
from yuxi.services import miniapp_profile_coding as coding
from yuxi.services.health_intent_router_types import HealthIntentInput
from yuxi.storage.postgres.models_business import ServiceNoticeAcknowledgement
from yuxi.storage.postgres.manager import pg_manager


@pytest.fixture
def unconfirmed_database(monkeypatch):
    conversation = SimpleNamespace(id=19, agent_id="health-consultation")

    class Session:
        async def get(self, model, *_args, **_kwargs):
            return None if model is ServiceNoticeAcknowledgement else conversation

    @asynccontextmanager
    async def session_context():
        yield Session()

    monkeypatch.setattr(pg_manager, "get_async_session_context", session_context)
    return conversation


@pytest.mark.asyncio
async def test_chat_intent_rejects_before_claim_or_model(unconfirmed_database, monkeypatch):
    from yuxi.repositories.health_intent_repository import HealthIntentRepository

    monkeypatch.setattr(
        consultation, "require_consultation", AsyncMock(return_value=(SimpleNamespace(conversation_id=19), {}))
    )
    claim, model = AsyncMock(), AsyncMock()
    monkeypatch.setattr(HealthIntentRepository, "claim", claim)
    monkeypatch.setattr(intent, "analyze_health_intent", model)
    data = HealthIntentInput(text="合成含糊问题", client_request_id=uuid4(), thread_id=uuid4())
    with pytest.raises(HTTPException) as error:
        await intent.route_health_intent("unconfirmed", data)
    assert error.value.detail["code"] == "SERVICE_NOTICE_REQUIRED"
    claim.assert_not_awaited()
    model.assert_not_awaited()


@pytest.mark.asyncio
async def test_legacy_pending_profile_coding_cannot_call_model(unconfirmed_database, monkeypatch):
    model = AsyncMock()
    monkeypatch.setattr(coding, "call_json_model", model)
    with pytest.raises(HTTPException):
        await coding.prepare_daily_profile_coding("unconfirmed", {"members": {"member": {}}}, {}, object())
    model.assert_not_awaited()


@pytest.mark.asyncio
async def test_failed_daily_retry_cannot_change_state_or_publish(unconfirmed_database, monkeypatch):
    row = SimpleNamespace(status="failed", selection={})
    monkeypatch.setattr(daily_tasks.DailyArrangementRepository, "context", AsyncMock(return_value=(None, row)))
    monkeypatch.setattr(daily, "authorize_sources", AsyncMock())
    publish = AsyncMock()
    monkeypatch.setattr(daily_tasks.tasker, "publish", publish)
    with pytest.raises(HTTPException):
        await daily_tasks.request_daily_resume("unconfirmed", "family", "day", retry_failed=True)
    assert row.status == "failed"
    publish.assert_not_awaited()


@pytest.mark.asyncio
async def test_worker_recovery_queue_requires_account_notice(unconfirmed_database, monkeypatch):
    queue = AsyncMock()
    monkeypatch.setattr(daily_tasks.tasker, "create_unique_in_session", queue)
    async with pg_manager.get_async_session_context() as session:
        with pytest.raises(HTTPException):
            await daily_tasks.queue_daily_in_session(session, SimpleNamespace(actor_uid="unconfirmed"))
    queue.assert_not_awaited()


@pytest.mark.asyncio
async def test_legacy_pending_consultation_rechecks_notice_before_model(unconfirmed_database, monkeypatch):
    """迁移前已排队的 Run 不能沿恢复或模型调用入口绕过账号确认。"""
    from yuxi.repositories.health_consultation_repository import HealthConsultationRepository

    run = SimpleNamespace(input_payload={"health_processing": {"model": "synthetic:model"}})
    monkeypatch.setattr(HealthConsultationRepository, "require_attempt", AsyncMock(return_value=run))
    authorize = AsyncMock()
    monkeypatch.setattr(consultation, "require_consultation", authorize)
    context = SimpleNamespace(uid="unconfirmed", thread_id="synthetic-thread", model="synthetic:model")
    with pytest.raises(HTTPException) as error:
        await consultation.require_consultation_attempt(context)
    assert error.value.detail["code"] == "SERVICE_NOTICE_REQUIRED"
    authorize.assert_not_awaited()

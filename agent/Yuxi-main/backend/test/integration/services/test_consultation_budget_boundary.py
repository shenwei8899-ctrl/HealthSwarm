# ruff: noqa: F811 -- pytest 注入共享隔离 fixture。
"""预算只约束新外呼，不改变处理审批及已有结果的可见性。"""

from contextlib import asynccontextmanager
from dataclasses import dataclass
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from langchain.agents import create_agent
from langchain_core.messages import HumanMessage
from sqlalchemy import select

from test.integration.services.test_health_ai_budget_pg import (  # noqa: F401
    budget_db,
    seed_price,
    ensure_live_api_schema,
    cleanup_test_sandboxes,
    cleanup_test_knowledge_resources,
)
from yuxi.agents.middlewares.health_budget import HealthAiBudgetMiddleware
from yuxi.models.chat import load_chat_model
from yuxi.models.providers.cache import ModelInfo, model_cache
from yuxi.services import health_ai_budget_service as budget
from yuxi.services import health_consultation_service as consultation
from yuxi.services import health_task_service as tasks
from yuxi.services import health_vision_service as vision
from yuxi.storage.postgres.models_business import Conversation
from yuxi.storage.postgres.models_health_budget import HealthAiMonth, HealthAiCall

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.mark.parametrize("state", ["last_reservation", "exhausted", "price_removed"])
async def test_budget_does_not_reauthorize_reserved_call_or_hide_saved_answer(budget_db, monkeypatch, state):
    """真实预算表、真实配置及授权流程证明最后一份预留可外呼，终态仍可回读。"""
    info = ModelInfo(
        provider_id="synthetic",
        model_id="fixed",
        model_type="chat",
        display_name="合成",
        api_key="synthetic",
        base_url="https://synthetic.invalid/v1",
        provider_type="openai",
    )
    monkeypatch.setattr(model_cache, "get_model_info", lambda _: info)
    monkeypatch.setattr(model_cache, "refresh", lambda: None)
    monkeypatch.setattr(vision, "current_health_model_info", AsyncMock(return_value=info))
    processor = vision.processor_identity("consultation", info)
    policy = {
        "policy_version": "synthetic-policy",
        "consultation_model": info.spec,
        "approved_consultation_processor": processor,
    }
    monkeypatch.setattr(vision, "health_vision_opts", SimpleNamespace(get=AsyncMock(return_value=policy)))
    monkeypatch.setattr(vision, "resolve_ocr_task_params", AsyncMock(return_value={"_ocr_processor_kwargs": {}}))
    thread, member = str(uuid4()), str(uuid4())
    binding = SimpleNamespace(member_id=member, conversation_id=7)
    snapshot = {"model": info.spec, "processor": processor, "policy_version": policy["policy_version"]}
    run = SimpleNamespace(
        id="synthetic-run",
        status="completed",
        agent_slug="health-consultation",
        conversation_thread_id=thread,
        conversation_id=7,
        input_payload={"health_processing": snapshot},
    )
    monkeypatch.setattr(consultation.HealthConsultationRepository, "authorize", AsyncMock(return_value=binding))
    monkeypatch.setattr(consultation.HealthConsultationRepository, "require_attempt", AsyncMock(return_value=run))
    monkeypatch.setattr(consultation.HealthVisionRepository, "require_consent", AsyncMock())
    monkeypatch.setattr(
        consultation.SkillRepository,
        "get_by_slug",
        AsyncMock(return_value=SimpleNamespace(source_type="builtin", enabled=True)),
    )

    original_context = budget_db.get_async_session_context

    class AuthorizationSession:
        """只替代与预算无关的已批准配置及有效业务身份来源。"""

        def __init__(self, db):
            self.db = db

        def __getattr__(self, name):
            return getattr(self.db, name)

        async def get(self, model, key, **kwargs):
            if model is Conversation:
                return SimpleNamespace(agent_id="health-consultation")
            return await self.db.get(model, key, **kwargs)

        async def scalar(self, statement, **kwargs):
            if "health_food_record" in str(statement):
                return 0
            return await self.db.scalar(statement, **kwargs)

    @asynccontextmanager
    async def context():
        async with original_context() as db:
            yield AuthorizationSession(db)

    monkeypatch.setattr(consultation.pg_manager, "get_async_session_context", context)
    if state != "price_removed":
        await seed_price(budget_db, budget.model_target(info))
    async with original_context() as db:
        account = (await db.scalars(select(HealthAiMonth))).one()
        account.occupied_cny = Decimal("30") if state == "last_reservation" else Decimal("40")

    if state == "last_reservation":

        @dataclass
        class Context:
            """服务端固定的当前尝试身份。"""

            model: str = info.spec
            thread_id: str = thread
            uid: str = "actor"
            run_id: str = "synthetic-run"

        sent = []

        async def send(client, request, **kwargs):
            async with original_context() as db:
                account = (await db.scalars(select(HealthAiMonth))).one()
                assert account.occupied_cny == Decimal("40")
            sent.append(request)
            return httpx.Response(
                200,
                request=request,
                json={
                    "id": "synthetic-response",
                    "object": "chat.completion",
                    "created": 1,
                    "model": "fixed",
                    "choices": [
                        {"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": "合成解释"}}
                    ],
                    "usage": {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18},
                },
            )

        monkeypatch.setattr(httpx.AsyncClient, "send", send)
        graph = create_agent(
            model=load_chat_model(info.spec),
            tools=[],
            middleware=[HealthAiBudgetMiddleware("consultation")],
            context_schema=Context,
        )
        result = await graph.ainvoke({"messages": [HumanMessage(content="合成问题")]}, context=Context())
        assert result["messages"][-1].content == "合成解释" and len(sent) == 1
        async with original_context() as db:
            call = (await db.scalars(select(HealthAiCall))).one()
            assert call.status == "settled" and call.charged_cny == Decimal("0.09")

    request = SimpleNamespace(
        request_id="request", agent_slug="health-consultation", conversation_thread_id=thread, status="dispatched"
    )
    message = SimpleNamespace(id=12, content="已保存的合成回复")
    monkeypatch.setattr(
        tasks,
        "HealthTaskRepository",
        lambda _: SimpleNamespace(
            request_context=AsyncMock(return_value=(request, binding, run)),
            final_message=AsyncMock(return_value=message),
        ),
    )
    monkeypatch.setattr(
        tasks, "HealthEvidenceRepository", lambda _: SimpleNamespace(validate_citations=AsyncMock(return_value={}))
    )
    monkeypatch.setattr("yuxi.services.health_family_kb_service.validate_family_kb_answer", AsyncMock())
    monkeypatch.setattr(
        "yuxi.services.conversation_purchase_service.offers_for_answer", AsyncMock(return_value=(message.content, []))
    )
    answer = await tasks.read_health_task("actor", "request")
    assert answer.execution_status == "completed" and answer.result.answer == message.content
    async with context() as db:
        authorized, _ = await consultation.require_consultation(db, "actor", thread, preview_history=True)
        assert authorized.member_id == member

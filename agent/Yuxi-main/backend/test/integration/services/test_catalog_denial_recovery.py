"""真实 PG 所有权及 checkpoint 验证普通咨询的商城拒绝与续轮。"""

import os
from datetime import timedelta
from uuid import uuid4
from unittest.mock import AsyncMock

import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from test.integration.services.test_account_family_memory import memory_run_fixture
from test.integration.services.test_health_family_profile_http import (  # noqa: F401
    family_profile_http,
    cleanup_test_sandboxes,
    cleanup_test_knowledge_resources,
    ensure_live_api_schema,
)
from test.support.health_budget_stub import stub_agent_budget
from yuxi.agents.buildin.health_consultation import graph as graph_module
from yuxi.agents.context import BaseContext
from yuxi.services import health_consultation_service as service
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.storage.postgres.models_business import AgentRun, Skill
from yuxi.storage.postgres.models_health import HealthProcessingConsent
from yuxi.utils.datetime_utils import utc_now_naive

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]
DENIAL = "本轮没有商城商品请求，未查询商品。请使用已授权的资料工具核对限制，随后完成普通咨询；不要再次调用商城工具。"


@pytest.mark.parametrize("legacy", [False, True])
async def test_shipping_graph_recovers_denial_and_followup_from_postgres(family_profile_http, monkeypatch, legacy):  # noqa: F811
    """正式构图、权限和 PG 回读共同证明拒绝后可完成及续轮。"""
    client, sessions, identities = family_profile_http
    context, binding, _, _ = await memory_run_fixture(client, sessions, identities["self"], quote="鸡蛋有什么营养")
    snapshot = {"model": context.model, "processor": "synthetic-processor", "policy_version": "synthetic-policy"}
    async with sessions.begin() as session:
        run = await session.get(AgentRun, context.run_id)
        run.input_payload = {"health_processing": snapshot}
        session.add(
            HealthProcessingConsent(
                member_id=binding.member_id,
                actor_uid=context.uid,
                purpose="consultation",
                processor=snapshot["processor"],
                policy_version=snapshot["policy_version"],
            )
        )
        session.add(
            Skill(
                slug="family-nutritionist",
                name="合成测试",
                description="合成测试",
                source_type="builtin",
                dir_path="synthetic",
                share_config={},
                enabled=True,
            )
        )
    monkeypatch.setattr(
        service.health_vision_service,
        "configuration",
        AsyncMock(
            return_value={"policy_version": snapshot["policy_version"], "consultation": {"available": True, **snapshot}}
        ),
    )
    # 记忆、反馈和引用有独立测试；保留本次目标的实际权限、商品守卫与来源校验。
    from yuxi.agents.middlewares import health_memory_context
    from yuxi.services import health_meal_feedback_service, health_evidence_service

    monkeypatch.setattr(health_memory_context, "process_memory_for_run", AsyncMock())
    monkeypatch.setattr(health_memory_context, "memory_context_for_run", AsyncMock(return_value={}))
    monkeypatch.setattr(
        health_meal_feedback_service, "filter_health_history", AsyncMock(side_effect=lambda _, m, **kw: m)
    )
    monkeypatch.setattr(health_evidence_service, "validate_nutrition_answer", AsyncMock())
    monkeypatch.setattr(graph_module.SteerMiddleware, "_jump_if_steer_requested", AsyncMock(return_value=None))
    monkeypatch.setattr(graph_module.model_cache, "get_model_info", lambda _: None)
    from yuxi.services import conversation_purchase_service

    catalog = AsyncMock(side_effect=AssertionError("商城不应执行"))
    monkeypatch.setattr(conversation_purchase_service, "get_conversation_categories", catalog)
    model_inputs = []

    class ReplayModel(GenericFakeChatModel):
        """有意模拟一次误调用，记录真实模型输入工具集。"""

        def bind_tools(self, tools, **kwargs):
            """工具实际绑定仍遵守正式中间件过滤。"""
            assert not {"get_food_categories", "find_food_packages", "select_food_products"} & {t.name for t in tools}
            return self

        def _generate(self, messages, *args, **kwargs):
            """回读模型边界，失败来源不能进入这里。"""
            model_inputs.append(messages)
            return super()._generate(messages, *args, **kwargs)

    def finalize(call_id):
        """构造无正文的标准最终阶段调用。"""
        return AIMessage(content="", tool_calls=[{"id": call_id, "name": "finalize_health_answer", "args": {}}])

    outputs = (
        []
        if legacy
        else [AIMessage(content="", tool_calls=[{"id": "blocked-call", "name": "get_food_categories", "args": {}}])]
    ) + [
        finalize("finish-first"),
        AIMessage(content="鸡蛋含有蛋白质，具体以实际食物资料为准。"),
        finalize("finish-second"),
        AIMessage(content="继续回答合成追问。"),
    ]
    model = ReplayModel(messages=iter(outputs))
    stub_agent_budget(monkeypatch, model)
    monkeypatch.setattr(graph_module, "load_chat_model", lambda **kw: model)
    ctx = BaseContext(**vars(context), tools=service.HEALTH_TOOL_NAMES)
    ctx._runtime_prepared = True
    config = {"configurable": {"thread_id": ctx.thread_id}, "recursion_limit": 50}
    dsn = (os.getenv("FAMILY_TEST_POSTGRES_URL") or os.environ["POSTGRES_URL"]).replace("+asyncpg", "")
    async with AsyncPostgresSaver.from_conn_string(dsn) as saver:
        await saver.setup()
        backend = graph_module.HealthConsultationAgent()
        monkeypatch.setattr(backend, "_get_checkpointer", AsyncMock(return_value=saver))
        graph = await backend.get_graph(context=ctx)
        human = HumanMessage(content="鸡蛋有什么营养", additional_kwargs={"health_request_id": ctx.request_id})
        if legacy:
            # 持久化旧格式，再从真实 checkpoint 恢复，而不是重建内存消息。
            await graph.aupdate_state(
                config,
                {
                    "messages": [
                        human,
                        AIMessage(
                            content="", tool_calls=[{"id": "blocked-call", "name": "get_food_categories", "args": {}}]
                        ),
                        ToolMessage(
                            content=DENIAL, name="get_food_categories", tool_call_id="blocked-call", status="error"
                        ),
                    ]
                },
            )
            result = await graph.ainvoke(None, config=config, context=ctx)
        else:
            result = await graph.ainvoke({"messages": [human]}, config=config, context=ctx)
        assert result["messages"][-1].content == "鸡蛋含有蛋白质，具体以实际食物资料为准。"
        checkpoint = await saver.aget_tuple(config)
        saved = checkpoint.checkpoint["channel_values"]["messages"]
        receipts = [m for m in saved if isinstance(m, ToolMessage) and m.name == "get_food_categories"]
        assert len(receipts) == 1 and receipts[0].status == "error" and receipts[0].content == DENIAL
        assert (
            ("catalog_guard" not in receipts[0].additional_kwargs)
            if legacy
            else (
                receipts[0].additional_kwargs["catalog_guard"]
                == {"reason": "no_product_intent", "request_id": ctx.request_id}
            )
        )
        # 下一请求使用新 Run/Request 身份，同时复用原 PG checkpoint。
        previous_id = ctx.run_id
        ctx.request_id, ctx.run_id = str(uuid4()), str(uuid4())
        async with sessions.begin() as session:
            old = await session.get(AgentRun, previous_id)
            old.status, old.worker_id, old.lease_expires_at = "completed", None, None
            session.add(
                AgentRun(
                    id=ctx.run_id,
                    request_id=ctx.request_id,
                    uid=ctx.uid,
                    agent_slug=old.agent_slug,
                    conversation_thread_id=ctx.thread_id,
                    conversation_id=old.conversation_id,
                    runtime_scope_id=ctx.thread_id,
                    status="running",
                    worker_id=ctx.worker_id,
                    lease_expires_at=utc_now_naive() + timedelta(minutes=5),
                    input_payload={"health_processing": snapshot},
                )
            )
        resumed = await backend.get_graph(context=ctx)
        result = await resumed.ainvoke(
            {"messages": [HumanMessage(content="继续说说", additional_kwargs={"health_request_id": ctx.request_id})]},
            config=config,
            context=ctx,
        )
        persisted = (await saver.aget_tuple(config)).checkpoint["channel_values"]["messages"]
        assert result["messages"][-1].content == persisted[-1].content == "继续回答合成追问。"
        catalog.assert_not_awaited()
        # 真正的商品错误依然阻断，正常拒绝也不能绕过运行所有权。
        with pytest.raises(HealthVisionError, match="source_invalidated"):
            await service.require_consultation_attempt(
                ctx,
                [
                    *persisted,
                    ToolMessage(
                        name="get_food_categories",
                        tool_call_id="real-failure",
                        content="商品来源已撤回",
                        status="error",
                    ),
                ],
            )
        calls_before = len(model_inputs)
        async with sessions.begin() as session:
            run = await session.get(AgentRun, ctx.run_id)
            run.worker_id = "replaced-worker"
        with pytest.raises(HealthVisionError, match="execution_not_owned"):
            await resumed.ainvoke({"messages": [HumanMessage(content="再次追问")]}, config=config, context=ctx)
        assert len(model_inputs) == calls_before

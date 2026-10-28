"""真实生产生命周期验证角色步数；业务依赖 oracle 不替代 PG、Worker 或 provider。"""

import ast
import importlib
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest
from langchain.agents import create_agent
from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import AIMessageChunk, HumanMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.errors import GraphRecursionError
from langgraph.stream.transformers import CustomTransformer

from test.unit.middlewares.test_health_final_answer import (
    Context,
    ControlledStreamModel,
    production,
    production_middleware,
    tool_chunk,
    usage,
)
from yuxi.services.health_vision_types import HealthVisionError


BACKEND = Path(__file__).resolve().parents[3]
ROLES = ("health-consultation", "health-blood-glucose", "health-blood-lipids", "health-blood-pressure")


def owner_step_limit(role, *, reference=False):
    """原样执行真实 Owner 的赋值和仓库角色常量，避免导入 Linux service 依赖。"""
    repository = BACKEND / "package/yuxi/repositories/health_consultation_repository.py"
    tree = ast.parse(repository.read_text(encoding="utf-8"))
    constants = [
        node
        for node in tree.body
        if isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name)
        and (node.targets[0].id.endswith("_SLUG") or node.targets[0].id == "EDUCATION_HEALTH_AGENTS")
    ]
    scope = {}
    exec(compile(ast.Module(body=constants, type_ignores=[]), str(repository), "exec"), scope)
    service = BACKEND / "package/yuxi/services/health_consultation_service.py"
    tree = ast.parse(service.read_text(encoding="utf-8"))
    prepare = next(
        node
        for node in tree.body
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "prepare_consultation_context"
    )
    assignment = next(
        node
        for node in ast.walk(prepare)
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Attribute)
            and isinstance(target.value, ast.Name)
            and target.value.id == "context"
            and target.attr == "max_execution_steps"
            for target in node.targets
        )
    )
    context = SimpleNamespace()
    scope.update(
        context=context,
        run=SimpleNamespace(agent_slug=role),
        binding=SimpleNamespace(),
        tools=["get_member_blood_glucose_records", "query_reviewed_nutrition_knowledge"],
        reference_binding=lambda binding: reference,
    )
    exec(compile(ast.Module(body=[assignment], type_ignores=[]), str(service), "exec"), scope)
    return context.max_execution_steps


def production_lifecycle_classes(model_info):
    """原样加载图内授权与引用类，实际 before/after/wrap 方法全部参与执行。"""
    source = BACKEND / "package/yuxi/agents/buildin/health_consultation/graph.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    classes = [
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name in {"HealthAuthorizationMiddleware", "HealthCitationMiddleware"}
    ]
    assert len(classes) == 2
    scope = {
        "AgentMiddleware": AgentMiddleware,
        "HumanMessage": HumanMessage,
        "HealthVisionError": HealthVisionError,
        "model_cache": SimpleNamespace(get_model_info=lambda spec: model_info),
    }
    exec(compile(ast.Module(body=classes, type_ignores=[]), str(source), "exec"), scope)
    return scope["HealthAuthorizationMiddleware"], scope["HealthCitationMiddleware"]


@pytest.fixture
def lifecycle_oracles(monkeypatch):
    """只替换业务服务和预算存储/模型工厂，不替换任何 middleware 生命周期。"""
    observed = {"authorization": [], "history": [], "citations": [], "steer": [], "reserve": [], "settle": []}
    model_slot = {}
    monkeypatch.setattr(usage, "model_cache", SimpleNamespace(get_model_info=lambda spec: None))

    async def require_attempt(context, messages=None):
        """模拟已拥有的本轮执行及有效用途审批。"""
        observed["authorization"].append((context.run_id, messages is not None))

    async def filter_history(context, messages, *, persist_uses=True):
        """保留合成输入，并记录最终引用检查确实走不落库分支。"""
        observed["history"].append(persist_uses)
        return messages

    async def validate_answer(context, text, messages):
        """仅记录本轮实际正文；真实来源与授权仍需独立 PG 验收。"""
        observed["citations"].append(text)

    async def should_steer(run_id):
        """本轮不插队，但真实 Steer 的两个生命周期节点继续执行。"""
        observed["steer"].append(run_id)
        return False

    async def reserve(purpose, owner_id, spec):
        """记录逐次预留边界，不建立实际财务账本。"""
        reservation = SimpleNamespace(call_id=len(observed["reserve"]) + 1)
        observed["reserve"].append((purpose, owner_id, spec))
        return reservation

    def reserved_model(reservation, **kwargs):
        """复现预算替换模型行为，Final 必须在此之后附加自己的 callback。"""
        return model_slot["model"].model_copy(update={"callbacks": None})

    async def settle(reservation, token_usage=None):
        """记录真实预算 middleware 的成功结算调用。"""
        observed["settle"].append(reservation.call_id)

    def install(name, **members):
        """临时模块随 monkeypatch 回收，避免加载业务服务的 Linux 或 PG 入口。"""
        module = ModuleType("yuxi.services." + name)
        module.__dict__.update(members)
        monkeypatch.setitem(sys.modules, module.__name__, module)
        monkeypatch.setattr(importlib.import_module("yuxi.services"), name, module, raising=False)

    install("health_consultation_service", require_consultation_attempt=require_attempt)
    install("health_family_kb_service", filter_family_kb_history=lambda messages: messages)
    install("health_meal_feedback_service", filter_health_history=filter_history)
    install("health_evidence_service", validate_nutrition_answer=validate_answer)
    install("agent_request_queue_service", should_end_run_for_steer=should_steer)
    install("health_ai_budget_service", reserve_model=reserve, reserved_chat_model=reserved_model, settle=settle)
    return observed, model_slot


async def run_complete_lifecycle(role, limit, oracles):
    """四模型阶段经过真实生产节点和 v3 桥，单独控制 LangGraph 超级步上限。"""
    observed, model_slot = oracles
    kind = "blood_glucose" if role == "health-consultation" else role.removeprefix("health-").replace("-", "_")

    async def records() -> str:
        """返回合成的授权记录，不读取数据库。"""
        return "synthetic authorized records"

    async def knowledge() -> str:
        """返回合成科普回执，不查询知识库。"""
        return "synthetic reviewed knowledge"

    record_tool = tool("get_member_" + kind + "_records")(records)
    knowledge_tool = tool("query_reviewed_nutrition_knowledge")(knowledge)
    model = ControlledStreamModel(
        plan=[
            [tool_chunk(record_tool.name)],
            [tool_chunk(knowledge_tool.name)],
            [tool_chunk(production.finalize_health_answer.name)],
            [AIMessageChunk(content="合成首句。"), AIMessageChunk(content="合成次句。")],
        ]
    )
    model_slot["model"] = model
    context = Context()
    context.model = "synthetic:lifecycle"
    context.uid = "synthetic-lifecycle-user"
    model_info = object()
    authorization, citation = production_lifecycle_classes(model_info=model_info)
    steer = production_middleware("steer")
    catalog = production_middleware("health_catalog")
    budget = production_middleware("health_budget")
    graph = create_agent(
        model,
        tools=[record_tool, knowledge_tool, production.finalize_health_answer],
        middleware=[
            steer.SteerMiddleware(),
            authorization(model_info),
            catalog.HealthCatalogMiddleware(),
            budget.HealthAiBudgetMiddleware("consultation" if role == "health-consultation" else "indicator_review"),
            citation(),
            production.HealthFinalAnswerMiddleware(),
            usage.TokenUsageMiddleware(),
        ],
        context_schema=Context,
        checkpointer=InMemorySaver(),
    )
    config = {"configurable": {"thread_id": context.thread_id}, "recursion_limit": limit}
    custom, failure = [], None
    try:
        async with await graph.astream_events(
            {"messages": [HumanMessage("合成指标回顾；不查询或推荐商品。外部数据依赖使用unit oracle。 ")]},
            context=context,
            config=config,
            version="v3",
            transformers=[CustomTransformer],
        ) as events:
            async for event in events:
                if event["method"] == "custom":
                    value = event["params"]["data"]
                    custom.append(value)
                    if value["type"] == "health_final_answer_delta":
                        assert len(observed["reserve"]) == 4 and len(observed["settle"]) == 3
    except GraphRecursionError as error:
        failure = error
    state = await graph.aget_state(config)
    return SimpleNamespace(model=model, custom=custom, state=state, failure=failure, observed=observed)


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ROLES)
async def test_owner_limit_completes_full_production_lifecycle(role, lifecycle_oracles):
    """无商品权限的普通咨询及三指标均能完成29超级步，不改全局默认。"""
    limit = owner_step_limit(role)
    assert limit == 40
    result = await run_complete_lifecycle(role, limit, lifecycle_oracles)
    assert result.failure is None and result.state.next == ()
    assert result.state.metadata["step"] == 29
    assert len(result.model.calls) == len(result.observed["reserve"]) == len(result.observed["settle"]) == 4
    assert result.state.values["health_answer_phase"] == "final"
    assert result.state.values["messages"][-1].text == "合成首句。合成次句。"
    assert result.observed["citations"] == ["合成首句。合成次句。"]
    assert len(result.observed["authorization"]) == 8
    assert result.observed["history"].count(False) == 1
    assert len(result.observed["steer"]) == 5
    assert [call["tool_choice"] for call in result.model.calls] == ["any", "any", "any", None]
    assert [value["type"] for value in result.custom] == [
        "health_final_answer_start",
        "health_final_answer_delta",
        "health_final_answer_delta",
        "health_final_answer_end",
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ROLES)
async def test_legacy_twenty_steps_stops_before_finalize_and_any_custom(role, lifecycle_oracles):
    """旧上限在第三次模型后失败，负控不能被简化生命周期或默认高limit掩盖。"""
    result = await run_complete_lifecycle(role, 20, lifecycle_oracles)
    assert isinstance(result.failure, GraphRecursionError)
    assert result.state.metadata["step"] == 20
    assert result.state.next == ("HealthCitationMiddleware.after_model",)
    assert result.state.values["health_answer_phase"] == "tools"
    assert len(result.model.calls) == len(result.observed["reserve"]) == 3
    assert not result.custom and not result.observed["citations"]
    assert not any(
        isinstance(message, ToolMessage) and message.name == production.finalize_health_answer.name
        for message in result.state.values["messages"]
    )


@pytest.mark.parametrize(
    "role,reference,expected",
    [
        ("health-diet-analyst", False, 20),
        ("health-meal-planner", False, 40),
        ("health-meal-planner", True, 80),
        ("health-quality", False, 40),
        ("health-purchase", False, 40),
    ],
)
def test_non_education_owner_limits_remain_unchanged(role, reference, expected):
    """角色修改不扩大非教育任务原有限制。"""
    assert owner_step_limit(role, reference=reference) == expected

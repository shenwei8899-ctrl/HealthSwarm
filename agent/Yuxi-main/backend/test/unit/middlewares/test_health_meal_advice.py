"""普通用餐建议与真实商品请求分流，不用脚本模型声称验证真实回复。"""

import ast
import json
from contextlib import asynccontextmanager
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from langchain.agents import create_agent
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage
from langchain_core.tools import tool

from test.unit.middlewares.test_health_catalog_final_answer import catalog, catalog_graph, human
from test.unit.middlewares.test_health_final_answer import ControlledStreamModel, production, tool_chunk
from yuxi.services.health_meal_plan_types import PlannerAnswer
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.services.reference_meal_plan_types import ReferencePlanDraft

BACKEND = Path(__file__).resolve().parents[3]


def consultation_prompt():
    """执行生产提示表达式，并使用当前真实内置 Skill 正文。"""
    source = BACKEND / "package/yuxi/services/health_consultation_service.py"
    node = next(
        item
        for item in ast.parse(source.read_text(encoding="utf-8")).body
        if isinstance(item, ast.Assign) and any(getattr(t, "id", "") == "CONSULTATION_PROMPT" for t in item.targets)
    )
    skill = BACKEND / "package/yuxi/agents/skills/buildin/family-nutritionist/SKILL.md"
    namespace = {
        "CONSULTATION_SKILL_SNAPSHOT": {},
        "consultation_skill_prompt": lambda snapshot: skill.read_text(encoding="utf-8"),
    }
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(source), "exec"), namespace)
    return namespace["CONSULTATION_PROMPT"]


def reference_prompt():
    """读取生产参考提示；绑定日期只提供合成明确选择。"""
    source = BACKEND / "package/yuxi/services/health_consultation_service.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    constant = next(
        item
        for item in tree.body
        if isinstance(item, ast.Assign) and any(getattr(t, "id", "") == "REFERENCE_MEAL_PROMPT" for t in item.targets)
    )
    branch = next(
        item
        for item in ast.walk(tree)
        if isinstance(item, ast.If)
        and isinstance(item.test, ast.BoolOp)
        and any(
            isinstance(value, ast.Call) and getattr(value.func, "id", "") == "reference_binding"
            for value in item.test.values
        )
    )
    namespace = {
        "REFERENCE_MEAL_PROMPT": ast.literal_eval(constant.value),
        "run": SimpleNamespace(agent_slug="synthetic-planner"),
        "PLANNER_SLUG": "synthetic-planner",
        "reference_binding": lambda binding: True,
        "binding": SimpleNamespace(initial_planner_selection={"selection": {"plan_date": "2026-10-28"}}),
    }
    exec(compile(ast.Module(body=[branch], type_ignores=[]), str(source), "exec"), namespace)
    return namespace["prompt"]


@pytest.mark.parametrize(
    "text",
    [
        "直接配餐",
        "今晚吃什么",
        "给我安排晚餐",
        "推荐几道菜",
        "帮我选食材做晚饭",
        "已经买了鸡蛋，晚餐怎么安排",
        "想吃昨天买的南瓜，推荐一道菜",
        "推荐晚餐，我昨天买了鸡蛋",
        "已经下单了鸡肉，帮我安排晚餐",
    ],
)
def test_meal_ideas_do_not_require_catalog(text):
    """普通候选请求不依赖商品调用，也不因配餐措辞变成保存请求。"""
    assert catalog.food_product_intent(text) is False


@pytest.mark.parametrize(
    "text",
    [
        "推荐可以买的食材",
        "商城有什么商品",
        "查询鸡蛋商品营养",
        "这道菜有没有食材包",
        "查询鸡蛋商品营养，我不需要购买",
        "不要推荐商品，请查询鸡蛋商品营养",
        "不想买食材，但请查询鸡蛋商品营养",
        "不需要买东西，请查询鸡蛋商品营养",
        "请帮我下单一份鸡肉",
    ],
)
def test_explicit_product_requests_keep_catalog_obligation(text):
    """明确商品意图继续受真实查询和选择协议约束。"""
    assert catalog.food_product_intent(text) is True


@pytest.mark.parametrize(
    "text",
    [
        "不用查商城，给我安排晚餐",
        "不买商品，只聊吃什么",
        "不要推荐商品。",
        "不需要购买商品，给我安排晚餐",
        "我不想买食材，只想聊今晚吃什么",
        "不需要买东西，帮我安排晚餐",
        "不用帮我下单，聊聊晚餐",
    ],
)
def test_explicit_product_refusal_does_not_force_a_catalog_request(text):
    """明确拒绝商品的日常讨论保持普通咨询。"""
    assert catalog.food_product_intent(text) is False


class AdvicePromptReplayModel(ControlledStreamModel):
    """回放断言模型确实收到当前固定提示，不替代真实模型的语义遵循。"""

    async def _astream(self, messages, **kwargs):
        """实际请求包含非保存及限制条款，且没有配餐保存工具。"""
        prompt = messages[0].content
        assert "无需用户提供食谱材料或来源" in prompt
        assert "已确认过敏、忌口及医嘱" in prompt
        assert "不保存" in prompt
        assert "- 个人餐单或换菜：引导用户明确选择配餐任务" not in prompt
        assert not {"save_reference_meal_plan", "preview_meal_plan"} & set(kwargs.get("tools", []))
        async for chunk in super()._astream(messages, **kwargs):
            yield chunk


@tool
async def get_complete_health_profile() -> str:
    """返回合成已确认限制，真实授权与档案读取不在本回放范围。"""
    return json.dumps(
        {
            "status": "ready",
            "confirmed_version": 1,
            "profile": {"dietary_details": {"allergies": ["牛奶"], "clinicianGuidance": "合成医嘱：避免含酒精食材"}},
            "nutrition_safety_ready": False,
        },
        ensure_ascii=False,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "text",
    ["直接配餐", "给我安排晚餐", "今晚吃什么", "我不想买食材，只想聊今晚吃什么", "不需要买东西，帮我安排晚餐"],
)
async def test_meal_advice_can_finish_without_catalog_round_trips(text):
    """真实组装图允许直接完成准备；旧广义强制查询会在同一路径失败。"""
    model = AdvicePromptReplayModel(
        plan=[
            [tool_chunk(production.finalize_health_answer.name)],
            [AIMessageChunk(content="合成候选建议，未保存餐单。")],
        ]
    )
    graph, custom, budget = await catalog_graph(model, [human(text)], system_prompt=consultation_prompt())
    assert budget.calls == len(model.calls) == 2
    assert [call["tool_choice"] for call in model.calls] == ["any", None]
    assert [item["content"] for item in custom if item["type"] == "health_final_answer_delta"] == [
        "合成候选建议，未保存餐单。"
    ]
    state = await graph.aget_state({"configurable": {"thread_id": "synthetic-thread"}})
    assert state.values["messages"][-1].text == "合成候选建议，未保存餐单。"


@pytest.mark.asyncio
async def test_meal_advice_reads_confirmed_restrictions_without_product_or_save_calls():
    """组装路径保留已授权事实，并允许不给候选附加商品浏览。"""
    answer = "合成候选：讨论南瓜；避开牛奶及含酒精食材，未保存或核算个人营养。"
    model = AdvicePromptReplayModel(
        plan=[
            [tool_chunk(get_complete_health_profile.name)],
            [tool_chunk(production.finalize_health_answer.name)],
            [AIMessageChunk(content=answer)],
        ]
    )
    graph, custom, budget = await catalog_graph(
        model,
        [human("按我已确认的忌口安排晚餐，只需要候选")],
        system_prompt=consultation_prompt(),
        extra_tools=(get_complete_health_profile,),
    )
    state = await graph.aget_state({"configurable": {"thread_id": "synthetic-thread"}})
    receipts = [message for message in state.values["messages"] if message.type == "tool"]
    assert [message.name for message in receipts] == [get_complete_health_profile.name, "finalize_health_answer"]
    assert json.loads(receipts[0].content)["profile"]["dietary_details"] == {
        "allergies": ["牛奶"],
        "clinicianGuidance": "合成医嘱：避免含酒精食材",
    }
    assert state.values["messages"][-1].text == answer
    assert [item["content"] for item in custom if item["type"] == "health_final_answer_delta"] == [answer]
    assert budget.calls == len(model.calls) == 3


def test_consultation_skill_does_not_turn_ordinary_advice_into_a_saved_plan():
    """实际固定提示包含当前 Skill，显式区分普通建议与保存和商品动作。"""
    prompt = consultation_prompt()
    assert "直接配餐" in prompt and "不保存" in prompt
    assert "无需用户提供食谱材料或来源" in prompt
    assert "仅当用户明确查询商品、选购或商品营养时" in prompt
    assert "- 个人餐单或换菜：引导用户明确选择配餐任务" not in prompt
    assert "先用自然语言回答，再原样附上工具返回的" not in prompt


def test_reference_source_gap_is_not_an_impossible_user_recipe_request():
    """固定缺源协议说明不能保存，只追问可解决的偏好限制。"""
    prompt = reference_prompt()
    assert "当前资料不足以保存" in prompt
    assert "不得要求用户提供食谱材料、原文或来源" in prompt
    assert "偏好" in prompt and "限制" in prompt
    assert "逐字引用" in prompt and "本Run保存回执ID" in prompt
    assert "固定为2026-10-28" in prompt and "{plan_date}" not in prompt


@pytest.mark.asyncio
async def test_reference_source_gap_keeps_explicit_needs_input_without_saving():
    """真实结果 Owner 接受明确缺源事实，并且不会进入保存回执路径。"""
    source = BACKEND / "package/yuxi/services/reference_meal_plan_service.py"
    node = next(
        item
        for item in ast.parse(source.read_text(encoding="utf-8")).body
        if isinstance(item, ast.AsyncFunctionDef) and item.name == "reference_answer_in_session"
    )
    authorization = AsyncMock()
    read_saved = AsyncMock(side_effect=AssertionError("缺源问题不应读取或保存餐单"))
    namespace = {"bound_reference_context": authorization, "reference_result_in_session": read_saved}
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(source), "exec"), namespace)
    answer = PlannerAnswer(questions=["当前资料不足以保存：受控资料没有可核对的日常食谱。"])
    run = type("SyntheticRun", (), {"uid": "synthetic-user"})()

    result = await namespace["reference_answer_in_session"]("synthetic-session", run, "synthetic-binding", answer)

    assert result == {"status": "needs_input", "questions": answer.questions}
    authorization.assert_awaited_once_with("synthetic-session", run.uid, "synthetic-binding")
    read_saved.assert_not_awaited()


@pytest.mark.asyncio
async def test_assembled_reference_prompt_preserves_other_meals_when_only_dinner_is_selected():
    """实际提示送入真实工具节点；脚本只提交晚餐，不证明真实模型或PG合并语义。"""
    current = {
        "meals": [
            {"meal_type": meal, "dishes": [{"name": meal + "-original"}]} for meal in ["breakfast", "lunch", "dinner"]
        ]
    }
    original = deepcopy(current)
    submitted = []

    @tool
    async def get_reference_plan_context() -> dict:
        """返回仅选择晚餐、附带合成当前三餐的上下文。"""
        return {
            "selection": {"plan_date": "2026-10-28", "meal_types": ["dinner"]},
            "current_daily_plan": deepcopy(current),
        }

    @tool
    async def save_reference_meal_plan(meals: list[dict]) -> dict:
        """记录提交餐次；原保存 Owner 的范围拒绝由独立负例覆盖。"""
        assert {meal["meal_type"] for meal in meals} == {"dinner"}
        submitted.extend(deepcopy(meals))
        return {"preview_id": "synthetic-selected-dinner"}

    class ReferenceScopeReplayModel(GenericFakeChatModel):
        """确保组装模型请求确实携带部署兼容的保留约束。"""

        def bind_tools(self, tools, **kwargs):
            """保留标准 ToolNode 执行。"""
            return self

        def _generate(self, messages, stop=None, run_manager=None, **kwargs):
            """旧提示在首次模型调用处失败，避免仅断言测试自产文本。"""
            prompt = messages[0].content
            assert "current_daily_plan" in prompt and "不得改写其他餐次" in prompt
            assert "未提供" in prompt and "不得臆造当前计划" in prompt
            return super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)

    model = ReferenceScopeReplayModel(
        messages=iter(
            [
                AIMessage(content="", tool_calls=[{"name": "get_reference_plan_context", "args": {}, "id": "context"}]),
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "save_reference_meal_plan",
                            "args": {"meals": [{"meal_type": "dinner", "dishes": [{"name": "synthetic-replacement"}]}]},
                            "id": "save",
                        }
                    ],
                ),
                AIMessage(content='{"preview_id":"synthetic-selected-dinner"}'),
            ]
        )
    )
    graph = create_agent(
        model, tools=[get_reference_plan_context, save_reference_meal_plan], system_prompt=reference_prompt()
    )
    result = await graph.ainvoke({"messages": [HumanMessage("只改今天晚餐，其他两餐保留")]})

    assert [meal["meal_type"] for meal in submitted] == ["dinner"]
    assert current == original
    assert result["messages"][-1].text == '{"preview_id":"synthetic-selected-dinner"}'


@pytest.mark.asyncio
async def test_reference_save_owner_still_rejects_an_unselected_breakfast():
    """原保存 Owner 拒绝额外餐次，不通过提示兼容放松集合校验。"""
    source = BACKEND / "package/yuxi/services/reference_meal_plan_service.py"
    node = next(
        item
        for item in ast.parse(source.read_text(encoding="utf-8")).body
        if isinstance(item, ast.AsyncFunctionDef) and item.name == "save_reference_plan"
    )

    @asynccontextmanager
    async def transaction():
        """仅提供合成事务边界，不连接数据库。"""
        yield "synthetic-session"

    namespace = {
        "ReferencePlanDraft": ReferencePlanDraft,
        "HealthVisionError": HealthVisionError,
        "pg_manager": SimpleNamespace(get_async_session_context=transaction),
        "require_planner_run": AsyncMock(return_value=("synthetic-run", "synthetic-binding")),
        "bound_reference_context": AsyncMock(return_value={"selection": {"meal_types": ["dinner"]}}),
        "tool_payloads": AsyncMock(return_value=[]),
    }
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(source), "exec"), namespace)
    dish = {
        "file_id": "synthetic-file",
        "chunk_id": "synthetic-chunk",
        "name": "合成菜",
        "ingredients": ["南瓜"],
        "steps": ["合成步骤"],
    }
    draft = {
        "meals": [{"meal_type": meal, "dishes": [dish]} for meal in ["breakfast", "dinner"]],
        "purchase_items": [],
        "purchase_gaps": [{"ingredient": "南瓜", "reason": "no_match", "detail": "合成无匹配"}],
    }

    with pytest.raises(HealthVisionError) as failure:
        await namespace["save_reference_plan"](SimpleNamespace(uid="synthetic-user"), draft)
    assert failure.value.code == "reference_meals_mismatch"

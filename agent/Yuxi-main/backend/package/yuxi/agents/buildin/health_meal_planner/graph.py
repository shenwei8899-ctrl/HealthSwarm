"""受限配餐师复用Run执行与PG checkpoint，最终结果来自服务器回执。"""

import json
from contextlib import aclosing

from langchain.agents import create_agent
from langchain.agents.middleware import AgentMiddleware

from yuxi.agents.base import BaseAgent
from yuxi.agents.buildin.health_consultation.graph import HealthAuthorizationMiddleware
from yuxi.agents.middlewares import SteerMiddleware, TokenUsageMiddleware
from yuxi.agents.toolkits.meal_planner import (
    search_meal_plan_recipes,
    preview_meal_plan,
    get_family_plan_context,
    preview_family_plan_swap,
    preview_family_plan_regeneration,
    preview_family_plan_participation,
    get_initial_plan_context,
    preview_initial_meal_plan,
)
from yuxi.services.health_family_planner_types import FAMILY_PLANNER_TOOLS
from yuxi.services.health_initial_meal_plan_types import INITIAL_PLANNER_TOOLS
from yuxi.services.health_safe_planner_types import SAFE_PLANNER_TOOLS
from yuxi.agents.toolkits.safe_meal_planner import (
    get_safe_plan_context,
    preview_safe_plan_swap,
    preview_safe_plan_regeneration,
)
from yuxi.models.chat import load_chat_model
from yuxi.models.providers.cache import model_cache


class MealPlanResultMiddleware(AgentMiddleware):
    """模型不能自行输出菜谱、营养或审核事实。"""

    async def aafter_model(self, state, runtime):
        """保持消息身份，将最终回执替换为权威结构化快照。"""
        from yuxi.services.health_meal_plan_service import planner_final_result

        message = state["messages"][-1]
        if message.type == "ai" and not message.tool_calls:
            result = await planner_final_result(runtime.context, message.text)
            return {"messages": [message.model_copy(update={"content": json.dumps(result, ensure_ascii=False)})]}


class HealthMealPlannerAgent(BaseAgent):
    """初始配餐、单成员草稿或已选餐单的只读预览，由服务器装配资源。"""

    name = "基础配餐师"
    description = "初始三餐及明确选定个人/家庭餐单的安全换菜和重算预览；专业批准由审核流程处理。"

    async def _stream_input_with_state(self, graph_input, *, context, **kwargs):
        """保留工具审计和核验后的checkpoint；消息正文在发布端过滤。"""
        async with aclosing(super()._stream_input_with_state(graph_input, context=context, **kwargs)) as stream:
            async for mode, payload in stream:
                if mode in {"messages", "checkpoint"} or (mode == "stream_event" and payload.get("method") == "tools"):
                    yield mode, payload

    async def get_graph(self, *, context, **kwargs):
        """固定工具与发布Skill，不加载个人扩展或默认模型。"""
        from yuxi.services.health_consultation_service import require_consultation_attempt

        if not getattr(context, "_runtime_prepared", False):
            raise ValueError("构图需要已准备的 Context")
        await require_consultation_attempt(context)
        if tuple(context.tools) == SAFE_PLANNER_TOOLS:
            tools = [get_safe_plan_context, preview_safe_plan_swap, preview_safe_plan_regeneration]
        elif tuple(context.tools) == INITIAL_PLANNER_TOOLS:
            tools = [get_initial_plan_context, preview_initial_meal_plan]
        elif tuple(context.tools) == FAMILY_PLANNER_TOOLS:
            tools = [
                get_family_plan_context,
                preview_family_plan_swap,
                preview_family_plan_regeneration,
                preview_family_plan_participation,
            ]
        elif context.tools == ["search_meal_plan_recipes", "preview_meal_plan"]:
            tools = [search_meal_plan_recipes, preview_meal_plan]
        else:
            raise ValueError("配餐工具必须是服务器固定模式")
        return create_agent(
            model=load_chat_model(fully_specified_name=context.model, session_id=context.thread_id),
            tools=tools,
            system_prompt=context.system_prompt,
            middleware=[
                SteerMiddleware(),
                HealthAuthorizationMiddleware(model_cache.get_model_info(context.model)),
                MealPlanResultMiddleware(),
                TokenUsageMiddleware(),
            ],
            context_schema=self.context_schema,
            checkpointer=await self._get_checkpointer(),
        )

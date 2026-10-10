"""受限饮食分析复用PG运行，最终输出由确认来源重新投影。"""

import json
from contextlib import aclosing

from langchain.agents import create_agent
from langchain.agents.middleware import AgentMiddleware

from yuxi.agents.base import BaseAgent
from yuxi.agents.buildin.health_consultation.graph import HealthAuthorizationMiddleware
from yuxi.agents.middlewares import SteerMiddleware, TokenUsageMiddleware
from yuxi.agents.toolkits.diet_analyst import (
    list_analysis_meals,
    analyze_confirmed_meal,
    analyze_confirmed_period,
    get_bound_personal_targets,
    get_selected_meal_feedback,
    record_selected_meal_feedback,
)
from yuxi.models.chat import load_chat_model
from yuxi.models.providers.cache import model_cache


class DietAnalysisResultMiddleware(AgentMiddleware):
    """模型选择与事实输出分别校验。"""

    async def aafter_model(self, state, runtime):
        """保持消息身份，只发布服务器核验后的结构化分析。"""
        from yuxi.services.health_diet_analysis_service import analyst_final_result

        message = state["messages"][-1]
        if message.type == "ai" and not message.tool_calls:
            result = await analyst_final_result(runtime.context, message.text)
            return {"messages": [message.model_copy(update={"content": json.dumps(result, ensure_ascii=False)})]}


class HealthDietAnalystAgent(BaseAgent):
    """确认记录事实与显式当前目标并列，历史达标及趋势等待专业规则。"""

    name = "饮食分析师"
    description = "分析确认单餐与1/7/30日记录事实和缺失，可只读用户明确绑定的当前目标；不判历史达标或趋势。"

    async def _stream_input_with_state(self, graph_input, *, context, **kwargs):
        """模型原始文字不作为分析结果发布。"""
        async with aclosing(super()._stream_input_with_state(graph_input, context=context, **kwargs)) as stream:
            async for mode, payload in stream:
                if mode in {"messages", "checkpoint"} or (mode == "stream_event" and payload.get("method") == "tools"):
                    yield mode, payload

    async def get_graph(self, *, context, **kwargs):
        """PG反馈模式两工具，普通分析三工具，绑定目标分析四个只读工具。"""
        from yuxi.services.health_consultation_service import require_consultation_attempt
        from yuxi.services.health_dialog_feedback_service import is_feedback_conversation
        from yuxi.services.health_agent_personal_target_service import is_personal_target_conversation

        if not getattr(context, "_runtime_prepared", False):
            raise ValueError("构图需要已准备的 Context")
        await require_consultation_attempt(context)
        feedback_mode = await is_feedback_conversation(context)
        tools = (
            [get_selected_meal_feedback, record_selected_meal_feedback]
            if feedback_mode
            else [list_analysis_meals, analyze_confirmed_meal, analyze_confirmed_period]
        )
        if not feedback_mode and await is_personal_target_conversation(context):
            tools.append(get_bound_personal_targets)
        return create_agent(
            model=load_chat_model(fully_specified_name=context.model, session_id=context.thread_id),
            tools=tools,
            system_prompt=context.system_prompt,
            middleware=[
                SteerMiddleware(),
                HealthAuthorizationMiddleware(model_cache.get_model_info(context.model)),
                DietAnalysisResultMiddleware(),
                TokenUsageMiddleware(),
            ],
            context_schema=self.context_schema,
            checkpointer=await self._get_checkpointer(),
        )

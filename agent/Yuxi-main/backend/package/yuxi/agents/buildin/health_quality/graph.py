"""独立质量Agent复用PG执行，只选择确定性工程检查回执。"""

import json
from contextlib import aclosing

from langchain.agents import create_agent
from langchain.agents.middleware import AgentMiddleware

from yuxi.agents.base import BaseAgent
from yuxi.agents.buildin.health_consultation.graph import HealthAuthorizationMiddleware
from yuxi.agents.middlewares import SteerMiddleware, TokenUsageMiddleware
from yuxi.agents.toolkits.quality import get_quality_review_context, check_selected_plan_quality
from yuxi.models.chat import load_chat_model
from yuxi.models.providers.cache import model_cache


class QualityResultMiddleware(AgentMiddleware):
    """最终选择与当前来源分别校验。"""

    async def aafter_model(self, state, runtime):
        """保持模型消息身份，只投影服务器检查结果。"""
        from yuxi.services.health_quality_service import quality_final_result

        message = state["messages"][-1]
        if message.type == "ai" and not message.tool_calls:
            result = await quality_final_result(runtime.context, message.text)
            return {"messages": [message.model_copy(update={"content": json.dumps(result, ensure_ascii=False)})]}


class HealthQualityAgent(BaseAgent):
    """独立工程检查，专业决定由授权人员完成。"""

    name = "质量检查师"
    description = "按外部确认档案与批准规则检查保存方案；专业批准独立办理。"

    async def _stream_input_with_state(self, graph_input, *, context, **kwargs):
        """模型原始文字不作为质量及批准结论发布。"""
        async with aclosing(super()._stream_input_with_state(graph_input, context=context, **kwargs)) as stream:
            async for mode, payload in stream:
                if mode in {"messages", "checkpoint"} or (mode == "stream_event" and payload.get("method") == "tools"):
                    yield mode, payload

    async def get_graph(self, *, context, **kwargs):
        """固定两工具和内置Skill，不装配用户工具或批准能力。"""
        from yuxi.services.health_consultation_service import require_consultation_attempt

        if not getattr(context, "_runtime_prepared", False):
            raise ValueError("构图需要已准备的Context")
        await require_consultation_attempt(context)
        return create_agent(
            model=load_chat_model(fully_specified_name=context.model, session_id=context.thread_id),
            tools=[get_quality_review_context, check_selected_plan_quality],
            system_prompt=context.system_prompt,
            middleware=[
                SteerMiddleware(),
                HealthAuthorizationMiddleware(model_cache.get_model_info(context.model)),
                QualityResultMiddleware(),
                TokenUsageMiddleware(),
            ],
            context_schema=self.context_schema,
            checkpointer=await self._get_checkpointer(),
        )

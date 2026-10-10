"""采购固定图仅读取授权需求并引用当前Run回执。"""

import json
from contextlib import aclosing

from langchain.agents import create_agent
from langchain.agents.middleware import AgentMiddleware

from yuxi.agents.base import BaseAgent
from yuxi.agents.buildin.health_consultation.graph import HealthAuthorizationMiddleware
from yuxi.agents.middlewares import SteerMiddleware, TokenUsageMiddleware
from yuxi.agents.toolkits.purchase import get_purchase_requirements, preview_purchase_requirements
from yuxi.models.chat import load_chat_model
from yuxi.models.providers.cache import model_cache
from yuxi.services.health_purchase_types import PURCHASE_TOOLS


class PurchaseResultMiddleware(AgentMiddleware):
    """只有服务端回执可以形成模型最终业务结果。"""

    async def aafter_model(self, state, runtime):
        """保留消息身份，正文替换为重验过的权威结果。"""
        from yuxi.services.health_purchase_service import purchase_final_result

        message = state["messages"][-1]
        if message.type == "ai" and not message.tool_calls:
            result = await purchase_final_result(runtime.context, message.text)
            return {"messages": [message.model_copy(update={"content": json.dumps(result, ensure_ascii=False)})]}


class HealthPurchaseAgent(BaseAgent):
    """使用独立采购用途、固定工具及PG checkpoint。"""

    name = "采购助手"
    description = "解释有效采用餐单的可食食材净需求；商品与真实交易依赖待定。"

    async def _stream_input_with_state(self, graph_input, *, context, **kwargs):
        """工具与checkpoint可审计，普通输出经发布端完整重验。"""
        async with aclosing(super()._stream_input_with_state(graph_input, context=context, **kwargs)) as stream:
            async for mode, payload in stream:
                if mode in {"messages", "checkpoint"} or (mode == "stream_event" and payload.get("method") == "tools"):
                    yield mode, payload

    async def get_graph(self, *, context, **kwargs):
        """模型和工具由固定健康入口准备，拒绝默认模型和个人扩展。"""
        from yuxi.services.health_consultation_service import require_consultation_attempt

        if not getattr(context, "_runtime_prepared", False) or tuple(context.tools) != PURCHASE_TOOLS:
            raise ValueError("采购构图需要已准备的固定工具Context")
        await require_consultation_attempt(context)
        return create_agent(
            model=load_chat_model(fully_specified_name=context.model, session_id=context.thread_id),
            tools=[get_purchase_requirements, preview_purchase_requirements],
            system_prompt=context.system_prompt,
            middleware=[
                SteerMiddleware(),
                HealthAuthorizationMiddleware(model_cache.get_model_info(context.model)),
                PurchaseResultMiddleware(),
                TokenUsageMiddleware(),
            ],
            context_schema=self.context_schema,
            checkpointer=await self._get_checkpointer(),
        )

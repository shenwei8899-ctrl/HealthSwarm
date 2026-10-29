"""受限配餐师复用Run执行与PG checkpoint，最终结果来自服务器回执。"""

import json
from contextlib import aclosing

from langchain.agents import create_agent
from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI

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
    query_initial_nutrition_knowledge,
    get_reference_plan_context,
    search_reference_recipes,
    read_reference_recipe,
    save_reference_meal_plan,
)
from yuxi.agents.toolkits.health import query_family_nutrition_knowledge
from yuxi.services.health_family_planner_types import FAMILY_PLANNER_TOOLS
from yuxi.services.health_initial_meal_plan_types import INITIAL_PLANNER_TOOLS
from yuxi.services.health_safe_planner_types import SAFE_PLANNER_TOOLS
from yuxi.services.reference_meal_plan_types import REFERENCE_TOOLS
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.agents.toolkits.safe_meal_planner import (
    get_safe_plan_context,
    preview_safe_plan_swap,
    preview_safe_plan_regeneration,
)
from yuxi.models.chat import load_chat_model
from yuxi.models.providers.cache import model_cache


class MealPlanResultMiddleware(AgentMiddleware):
    """模型不能自行输出菜谱、营养或审核事实。"""

    async def awrap_model_call(self, request, handler):
        """本轮参考餐单保存成功后，只进行一次真实的无工具最终调用。"""
        from yuxi.services.health_meal_plan_service import planner_final_result

        preview_id = self._saved_reference_preview(request.state, request.runtime.context)
        if preview_id is None:
            tools = tuple(name for name in request.runtime.context.tools if name != "query_family_nutrition_knowledge")
            if tools == REFERENCE_TOOLS and request.tools and isinstance(request.model, ChatOpenAI):
                # 已观测到并行空参数反复消耗步数；准备阶段逐次取得可核验回执。
                request = request.override(model_settings={**request.model_settings, "parallel_tool_calls": False})
            return await handler(request)

        # 当前 Run 的完成审计、成员权限和菜谱原文仍由原服务重验。
        await planner_final_result(request.runtime.context, json.dumps({"preview_id": preview_id}))
        original = request.system_message.text if request.system_message else ""
        instruction = (
            "本轮所选餐次已通过保存工具完成，资料准备结束。"
            "当前仅生成最终回复，不再检索、调用工具或修改餐单。"
            f'最终仅输出 {{"preview_id":"{preview_id}"}}，服务器将重新核对并装配已保存的真实餐单。'
        )
        return await handler(
            request.override(
                tools=[],
                tool_choice=None,
                response_format=None,
                system_message=SystemMessage(content=f"{original}\n\n{instruction}"),
            )
        )

    async def aafter_model(self, state, runtime):
        """保持消息身份，将最终回执替换为权威结构化快照。"""
        from yuxi.services.health_meal_plan_service import planner_final_result

        message = state["messages"][-1]
        preview_id = self._saved_reference_preview(state, runtime.context)
        if preview_id is not None and message.type == "ai" and (message.tool_calls or message.invalid_tool_calls):
            raise HealthVisionError("planner_finalization_invalid", "餐单保存后的最终回复不允许继续调用工具", 422)
        if message.type == "ai" and not message.tool_calls:
            answer = json.dumps({"preview_id": preview_id}) if preview_id is not None else message.text
            result = await planner_final_result(runtime.context, answer)
            return {"messages": [message.model_copy(update={"content": json.dumps(result, ensure_ascii=False)})]}

    @staticmethod
    def _saved_reference_preview(state, context):
        """仅选择当前请求消息之后唯一的成功保存回执，不沿用旧轮次。"""
        tools = tuple(name for name in context.tools if name != "query_family_nutrition_knowledge")
        if tools != REFERENCE_TOOLS:
            return None

        messages = state.get("messages", [])
        for index in range(len(messages) - 1, -1, -1):
            human = messages[index]
            if isinstance(human, HumanMessage):
                if human.additional_kwargs.get("health_request_id") != context.request_id:
                    return None
                break
        else:
            return None

        previews = set()
        for message in messages[index + 1 :]:
            if not (
                isinstance(message, ToolMessage)
                and message.name == "save_reference_meal_plan"
                and message.status == "success"
            ):
                continue
            try:
                payload = json.loads(message.content)
                preview_id = payload.get("preview_id") if isinstance(payload, dict) else None
                if not isinstance(preview_id, str) or not preview_id:
                    raise ValueError("缺少参考餐单回执")
            except (TypeError, ValueError):
                raise HealthVisionError("reference_receipt_invalid", "参考餐单保存回执无法核对", 409) from None
            previews.add(preview_id)
        if len(previews) > 1:
            raise HealthVisionError("reference_receipt_invalid", "本轮存在多个不同参考餐单，请重新生成", 409)
        return next(iter(previews), None)


class HealthMealPlannerAgent(BaseAgent):
    """初始配餐、单成员草稿或已选餐单的只读预览，由服务器装配资源。"""

    name = "基础配餐师"
    description = "知识库日常参考餐单，以及正式个人/家庭餐单的换菜和重算预览；营养缺项明确展示，专业审核独立处理。"

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
        planner_tools = [name for name in context.tools if name != "query_family_nutrition_knowledge"]
        if tuple(planner_tools) == REFERENCE_TOOLS:
            tools = [
                get_reference_plan_context,
                search_reference_recipes,
                read_reference_recipe,
                save_reference_meal_plan,
            ]
        elif tuple(planner_tools) == SAFE_PLANNER_TOOLS:
            tools = [get_safe_plan_context, preview_safe_plan_swap, preview_safe_plan_regeneration]
        elif tuple(planner_tools) == INITIAL_PLANNER_TOOLS:
            tools = [get_initial_plan_context, preview_initial_meal_plan, query_initial_nutrition_knowledge]
        elif tuple(planner_tools) == FAMILY_PLANNER_TOOLS:
            tools = [
                get_family_plan_context,
                preview_family_plan_swap,
                preview_family_plan_regeneration,
                preview_family_plan_participation,
            ]
        elif planner_tools == ["search_meal_plan_recipes", "preview_meal_plan"]:
            tools = [search_meal_plan_recipes, preview_meal_plan]
        else:
            raise ValueError("配餐工具必须是服务器固定模式")
        if "query_family_nutrition_knowledge" in context.tools:
            tools.append(query_family_nutrition_knowledge)
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

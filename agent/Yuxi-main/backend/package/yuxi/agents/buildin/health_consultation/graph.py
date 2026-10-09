"""复用既有 Run 与 checkpoint 的受限健康咨询执行图。"""

from langchain.agents import create_agent
from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import HumanMessage

from yuxi.agents.base import BaseAgent
from yuxi.agents.middlewares import SteerMiddleware, TokenUsageMiddleware
from yuxi.agents.toolkits.health import (
    get_confirmed_diet,
    get_confirmed_profile,
    get_complete_health_profile,
    get_member_weight_records,
    get_member_blood_pressure_records,
    get_member_blood_glucose_records,
    get_member_blood_lipids_records,
    query_reviewed_nutrition_knowledge,
    get_member_memories,
    remember_member_fact,
    get_meal_feedback,
)
from yuxi.models.chat import load_chat_model
from yuxi.models.providers.cache import model_cache
from yuxi.services.health_vision_types import HealthVisionError


class HealthAuthorizationMiddleware(AgentMiddleware):
    """每次模型外呼前重查用途、成员权限和执行 lease。"""

    def __init__(self, model_info):
        """运行期绑定已构造模型配置，凭据不进入持久快照或公开响应。"""
        self.model_info = model_info

    async def abefore_model(self, state, runtime):
        """已缓存的历史健康消息也不能绕过权限撤回。"""
        from yuxi.services.health_consultation_service import require_consultation_attempt

        await require_consultation_attempt(runtime.context, state.get("messages", []))
        if model_cache.get_model_info(runtime.context.model) != self.model_info:
            raise HealthVisionError("policy_changed", "模型运行配置已变化，请重新提交咨询", 409)
        # 服务器请求标识随用户消息进入 checkpoint，写入后崩溃也可追溯该轮。
        human = next((item for item in reversed(state.get("messages", [])) if isinstance(item, HumanMessage)), None)
        if human is not None and "health_request_id" not in human.additional_kwargs:
            return {
                "messages": [
                    human.model_copy(
                        update={
                            "additional_kwargs": {
                                **human.additional_kwargs,
                                "health_request_id": runtime.context.request_id,
                            }
                        }
                    )
                ]
            }

    async def awrap_model_call(self, request, handler):
        """模型输入排除已经修改或撤回的历史记忆轮次。"""
        from yuxi.services.health_meal_feedback_service import filter_health_history

        messages = await filter_health_history(request.runtime.context, request.messages)
        return await handler(request.override(messages=messages))


class HealthConsultationAgent(BaseAgent):
    """健康咨询仅使用授权记录、自述记忆及审核科普。"""

    name = "成员专属营养咨询"
    description = "读取成员已确认记录和审核通用科普，校验营养证据引用，不生成治疗或个人配餐方案。"

    async def get_graph(self, *, context, **kwargs):
        """构图前核对审批，工具名单由本后端固定。"""
        from yuxi.services.health_consultation_service import CONSULTATION_PROMPT, require_consultation_attempt

        if not getattr(context, "_runtime_prepared", False):
            raise ValueError("构图需要已准备的 Context")
        await require_consultation_attempt(context)
        model_info = model_cache.get_model_info(context.model)
        return create_agent(
            model=load_chat_model(fully_specified_name=context.model, session_id=context.thread_id),
            tools=[
                get_confirmed_profile,
                get_confirmed_diet,
                get_complete_health_profile,
                get_member_weight_records,
                get_member_blood_pressure_records,
                get_member_blood_glucose_records,
                get_member_blood_lipids_records,
                query_reviewed_nutrition_knowledge,
                get_member_memories,
                remember_member_fact,
                get_meal_feedback,
            ],
            system_prompt=CONSULTATION_PROMPT,
            middleware=[
                SteerMiddleware(),
                HealthAuthorizationMiddleware(model_info),
                HealthCitationMiddleware(),
                TokenUsageMiddleware(),
            ],
            context_schema=self.context_schema,
            checkpointer=await self._get_checkpointer(),
        )


class HealthCitationMiddleware(AgentMiddleware):
    """质量角色第一阶段只校验引用来源，不声称完成临床结论审核。"""

    async def aafter_model(self, state, runtime):
        """工具调用后的最终文本在运行成功前核对引用。"""
        from yuxi.services.health_evidence_service import validate_nutrition_answer

        message = state["messages"][-1]
        if message.type == "ai" and not message.tool_calls:
            from yuxi.services.health_meal_feedback_service import filter_health_history

            await filter_health_history(runtime.context, state["messages"], persist_uses=False)
            await validate_nutrition_answer(runtime.context, message.text, state["messages"])

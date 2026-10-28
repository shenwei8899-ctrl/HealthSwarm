"""工具决策结束后，在不携带工具的最终调用中输出可信正文增量。"""

from typing import NotRequired
from uuid import uuid4

from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import AgentState
from langchain_core.callbacks import AsyncCallbackHandler, AsyncCallbackManager
from langchain_core.messages import AIMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.config import get_stream_writer
from langgraph.prebuilt.tool_node import ToolRuntime
from langgraph.types import Command

from yuxi.services.health_vision_types import HealthVisionError


class HealthFinalAnswerState(AgentState):
    """最终阶段只属于当前请求，不能沿用上一轮 checkpoint 的标记。"""

    health_final_request_id: NotRequired[str]
    health_answer_phase: NotRequired[str]


@tool
def finalize_health_answer(runtime: ToolRuntime) -> Command:
    """本轮所需资料和业务工具已准备完成时单独调用；不传答案，随后生成最终正文。"""
    return Command(
        update={
            "health_final_request_id": runtime.context.request_id,
            "health_answer_phase": "final",
            "messages": [ToolMessage(content="资料准备完成，进入最终正文阶段。", tool_call_id=runtime.tool_call_id)],
        }
    )


class HealthFinalAnswerMiddleware(AgentMiddleware[HealthFinalAnswerState]):
    """规划轮保留原工具，最终轮使用同一预算模型但不绑定任何工具。"""

    state_schema = HealthFinalAnswerState

    async def abefore_agent(self, state, runtime):
        """新请求清除旧阶段，同请求恢复保留已完成的资料准备。"""
        if state.get("health_final_request_id") != runtime.context.request_id:
            return {"health_final_request_id": runtime.context.request_id, "health_answer_phase": "tools"}

    async def awrap_model_call(self, request, handler):
        """只在受控最终调用中发 custom；普通 ReAct 文本始终保持私有。"""
        final = (
            request.state.get("health_final_request_id") == request.runtime.context.request_id
            and request.state.get("health_answer_phase") == "final"
        )
        if not final:
            prompt = (
                "当前是资料准备阶段。保留并使用本轮所需的原业务工具，不撰写给用户的最终正文。"
                "准备完成后必须单独调用 finalize_health_answer，不要先生成完整答案，也不要把答案放入工具参数。"
            )
            return await handler(
                request.override(
                    system_message=self._system_message(request, prompt),
                    tool_choice=request.tool_choice if request.tool_choice is not None else "any",
                )
            )

        # 预算已准备本轮模型；继续使用标准 handler，让用量和执行链看到真正的无工具请求。
        prompt = (
            "资料准备已经结束。当前只生成给用户的最终正文，不再调用工具或输出分析、工具计划。"
            "继续遵守原有用途、专业安全与引用规则，只使用本轮实际取得的资料和业务结果。"
        )
        context = request.runtime.context
        route = {
            "request_id": context.request_id,
            "run_id": context.run_id,
            "thread_id": context.thread_id,
            "message_id": str(uuid4()),
        }
        writer = get_stream_writer()
        callback = HealthFinalAnswerCallback(writer, route)
        callbacks = AsyncCallbackManager.configure(inheritable_callbacks=request.model.callbacks)
        callbacks.add_handler(callback, inherit=False)
        model = request.model.model_copy(update={"callbacks": callbacks})
        writer({"type": "health_final_answer_start", **route})
        response = await handler(
            request.override(
                model=model,
                tools=[],
                tool_choice=None,
                response_format=None,
                system_message=self._system_message(request, prompt),
            )
        )
        message = response.result[0]
        if not isinstance(message, AIMessage) or not message.text:
            raise HealthVisionError("answer_stream_empty", "本次咨询未生成答复，请重新提交", 422)
        if message.tool_calls or message.invalid_tool_calls:
            raise HealthVisionError("answer_stream_tool_call", "最终答复阶段不允许调用工具，请重新提交咨询", 422)
        writer({"type": "health_final_answer_end", "offset": callback.offset, **callback.route})
        return response

    async def aafter_model(self, state, runtime):
        """工具准备必须显式结束，禁止模型跳过阶段或并行提交结束动作。"""
        message = state["messages"][-1]
        if not isinstance(message, AIMessage):
            return None
        if state.get("health_answer_phase") != "final":
            calls = message.tool_calls
            if not calls or any(call["name"] == finalize_health_answer.name for call in calls) and len(calls) != 1:
                raise HealthVisionError("answer_finalization_required", "答复准备阶段未正常结束，请重新提交咨询", 422)

    @staticmethod
    def _system_message(request, instruction):
        """保持原系统安全约束，只追加当前阶段说明。"""
        original = request.system_message.text if request.system_message else ""
        return SystemMessage(content=f"{original}\n\n{instruction}")


class HealthFinalAnswerCallback(AsyncCallbackHandler):
    """只绑定本轮无工具模型，在模型完成前转发纯文字，不转发推理或工具块。"""

    raise_error = True

    def __init__(self, writer, route):
        """回调状态只存于本次模型调用，不进入 checkpoint 或模型输入。"""
        self.writer = writer
        self.route = dict(route)
        self.offset = 0

    async def on_stream_event(self, event, **kwargs):
        """只消费 BaseAgent 的 v3 协议，避免供应商 token 回调和桥接事件重复发布。"""
        content = event.get("content") or {}
        delta = event.get("delta") or {}
        fields = delta.get("fields") or {}
        if any("tool" in str(value.get("type", "")) for value in (content, delta, fields)):
            raise HealthVisionError("answer_stream_tool_call", "最终答复阶段不允许调用工具，请重新提交咨询", 422)
        if event.get("event") == "content-block-delta" and delta.get("type") == "text-delta":
            text = delta.get("text")
            if isinstance(text, str) and text:
                self.writer({"type": "health_final_answer_delta", "content": text, "offset": self.offset, **self.route})
                self.offset += len(text)

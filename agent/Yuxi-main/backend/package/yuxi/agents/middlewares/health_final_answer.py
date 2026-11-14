"""工具决策结束后，在不携带工具的最终调用中输出可信正文增量。"""

import json
from typing import NotRequired
from uuid import uuid4

from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import AgentState
from langchain_core.callbacks import AsyncCallbackHandler, AsyncCallbackManager
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.config import get_stream_writer
from langgraph.prebuilt.tool_node import ToolRuntime
from langgraph.types import Command

from yuxi.services.health_evidence_types import ConsultationAnswer, CONSULTATION_CITATIONS_KEY
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.agents.middlewares.health_catalog_context import catalog_selection_ready


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

    async def awrap_tool_call(self, request, handler):
        """独立选品成功时由原工具节点转入正文，不额外消耗每轮图执行步数。"""
        result = await handler(request)
        if request.tool_call["name"] != "select_food_products" or not isinstance(result, ToolMessage):
            return result
        request_id = request.runtime.context.request_id
        if request.state.get("health_final_request_id") == request_id and catalog_selection_ready(
            [*request.state.get("messages", []), result], request_id
        ):
            return Command(
                update={
                    "messages": [result],
                    "health_final_request_id": request_id,
                    "health_answer_phase": "final",
                }
            )
        return result

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
            if "select_food_products" in {tool.name for tool in request.tools}:
                prompt += (
                    "商品选品时若本轮所有资料已经齐备，可在select_food_products同时传ready_to_answer=true，"
                    "成功后系统直接进入最终正文，无需再调用finalize_health_answer。若仍需其他工具则传false。"
                )
            response = await handler(
                request.override(
                    system_message=self._system_message(request, prompt),
                    tool_choice=request.tool_choice if request.tool_choice is not None else "any",
                )
            )
            message = getattr(response, "model_response", response).result[-1]
            if isinstance(message, AIMessage):
                calls = message.tool_calls
                if not calls or any(call["name"] == finalize_health_answer.name for call in calls) and len(calls) != 1:
                    raise HealthVisionError(
                        "answer_finalization_required", "答复准备阶段未正常结束，请重新提交咨询", 422
                    )
            return response

        # 预算已准备本轮模型；继续使用标准 handler，让用量和执行链看到真正的无工具请求。
        prompt = (
            "资料准备已经结束。当前只生成给用户的最终正文，不再调用工具或输出分析、工具计划。"
            "以最新用户消息为本轮任务，结合历史理解追问；除非本轮明确要求回顾、比较或汇总，否则不重复回答历史问题，也不自动续答旧轮未完成的问题。"
            "继续遵守原有用途、专业安全与引用规则，只使用本轮实际取得的资料和业务结果。"
        )
        family_ids = self._citation_ids(request, "query_family_nutrition_knowledge", "sources", "source_id")
        evidence_ids = self._citation_ids(request, "query_reviewed_nutrition_knowledge", "citations", "citation_id")
        buffered = bool(family_ids or evidence_ids)
        prompt += "正文不要写资料或证据标记。没有直接支持本题的资料时，如实说明缺口。"
        if buffered:
            prompt += (
                "只返回一个 JSON 对象，不加代码围栏。answer 是自然语言正文；citations 是实际采用的引用数组，"
                "每项仅有 kind 和 id；kind 为 family 或 reviewed。相关背景不必引用，无直接依据时数组为空。"
                "本轮可选 ID：" + json.dumps({"family": family_ids, "reviewed": evidence_ids})
            )
        context = request.runtime.context
        route = {
            "request_id": context.request_id,
            "run_id": context.run_id,
            "thread_id": context.thread_id,
            "message_id": str(uuid4()),
        }
        writer = get_stream_writer()
        callback = HealthFinalAnswerCallback(writer, route, buffer=buffered)
        callbacks = AsyncCallbackManager.configure(inheritable_callbacks=request.model.callbacks)
        callbacks.add_handler(callback, inherit=False)
        model_updates = {"callbacks": callbacks}
        if buffered and isinstance(request.model, ChatOpenAI):
            # The final response is parsed as ConsultationAnswer. A prompt alone
            # does not make OpenAI-compatible providers return a JSON object.
            model_updates["model_kwargs"] = {
                **request.model.model_kwargs,
                "response_format": {"type": "json_object"},
            }
        model = request.model.model_copy(update=model_updates)
        writer({"type": "health_final_answer_start", **route, **({} if buffered else {"citations": []})})
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
        answer = message.text
        citations = []
        if buffered:
            try:
                result = ConsultationAnswer.model_validate_json(answer)
                available = {"family": set(family_ids), "reviewed": set(evidence_ids)}
                if any(str(ref.id) not in available[ref.kind] for ref in result.citations):
                    raise ValueError("引用不属于本轮")
                answer = result.answer
                citations = [ref.model_dump(mode="json") for ref in result.citations]
            except ValueError as error:
                raise HealthVisionError("citation_invalid", "本次答复未能核对引用，请重新提交问题", 409) from error
        response.result[0] = message.model_copy(
            update={
                "content": answer,
                "additional_kwargs": {**message.additional_kwargs, CONSULTATION_CITATIONS_KEY: citations},
            }
        )
        if buffered:
            writer(
                {"type": "health_final_answer_delta", "content": answer, "offset": 0, "citations": citations, **route}
            )
        writer({"type": "health_final_answer_end", "offset": len(answer) if buffered else callback.offset, **route})
        return response

    @staticmethod
    def _system_message(request, instruction):
        """保持原系统安全约束，只追加当前阶段说明。"""
        original = request.system_message.text if request.system_message else ""
        return SystemMessage(content=f"{original}\n\n{instruction}")

    @staticmethod
    def _citation_ids(request, tool_name, result_key, id_key):
        messages = request.messages
        index = next((i for i in range(len(messages) - 1, -1, -1) if isinstance(messages[i], HumanMessage)), None)
        if (
            index is None
            or messages[index].additional_kwargs.get("health_request_id") != request.runtime.context.request_id
        ):
            return []
        ids = []
        for message in messages[index + 1 :]:
            if not isinstance(message, ToolMessage) or message.name != tool_name or message.status == "error":
                continue
            try:
                payload = json.loads(message.content)
            except (TypeError, ValueError):
                continue
            entries = payload.get(result_key) if isinstance(payload, dict) else None
            if isinstance(entries, list):
                ids.extend(
                    entry[id_key] for entry in entries if isinstance(entry, dict) and isinstance(entry.get(id_key), str)
                )
        return list(dict.fromkeys(ids))


class HealthFinalAnswerCallback(AsyncCallbackHandler):
    """只绑定本轮无工具模型，在模型完成前转发纯文字，不转发推理或工具块。"""

    raise_error = True

    def __init__(self, writer, route, *, buffer=False):
        """回调状态只存于本次模型调用，不进入 checkpoint 或模型输入。"""
        self.writer = writer
        self.route = dict(route)
        self.offset = 0
        self.buffer = buffer

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
                if not self.buffer:
                    self.writer(
                        {"type": "health_final_answer_delta", "content": text, "offset": self.offset, **self.route}
                    )
                self.offset += len(text)

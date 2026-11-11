"""受限配餐师复用Run执行与PG checkpoint，最终结果来自服务器回执。"""

import json
from contextlib import aclosing

from langchain.agents import create_agent
from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from pydantic import ValidationError

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
    find_reference_products,
    search_reference_recipes,
    read_reference_recipe,
    save_reference_meal_plan,
    reference_save_failure_index,
)
from yuxi.agents.toolkits.health import query_family_nutrition_knowledge
from yuxi.services.health_family_planner_types import FAMILY_PLANNER_TOOLS
from yuxi.services.health_initial_meal_plan_types import INITIAL_PLANNER_TOOLS
from yuxi.services.health_safe_planner_types import SAFE_PLANNER_TOOLS
from yuxi.services.reference_meal_plan_types import REFERENCE_TOOLS
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.services.health_meal_plan_types import PlannerAnswer
from yuxi.agents.toolkits.safe_meal_planner import (
    get_safe_plan_context,
    preview_safe_plan_swap,
    preview_safe_plan_regeneration,
)
from yuxi.models.chat import ChatCompletionsAdapter, load_chat_model
from yuxi.models.providers.cache import model_cache


class ReferenceContextMiddleware(AgentMiddleware):
    """每轮配餐先读取当前授权档案和商城分类，续改也不沿用旧轮回执。"""

    async def awrap_model_call(self, request, handler):
        """前置工具成功后才开放后续配餐工具，服务端仍重新校验来源。"""
        tools = tuple(name for name in request.runtime.context.tools if name != "query_family_nutrition_knowledge")
        if tools == REFERENCE_TOOLS:
            current = request.state.get("messages", [])
            start = next((i for i in range(len(current) - 1, -1, -1) if isinstance(current[i], HumanMessage)), None)
            if (
                start is None
                or current[start].additional_kwargs.get("health_request_id") != request.runtime.context.request_id
            ):
                raise HealthVisionError("reference_request_mismatch", "当前配餐轮次无法核对", 409)
            receipts = [
                m for m in current[start + 1 :] if isinstance(m, ToolMessage) and m.name == "get_reference_plan_context"
            ]
            if not any(m.status == "success" for m in receipts):
                if receipts:
                    raise HealthVisionError("reference_context_unavailable", "当前档案和商城分类读取失败，请重试", 409)
                context_tools = [
                    tool for tool in request.tools if getattr(tool, "name", None) == "get_reference_plan_context"
                ]
                if not context_tools:
                    raise HealthVisionError("reference_context_unavailable", "配餐资料读取工具暂不可用", 503)
                return await handler(
                    request.override(
                        tools=context_tools,
                        tool_choice={"type": "function", "function": {"name": "get_reference_plan_context"}},
                        model_settings={**request.model_settings, "parallel_tool_calls": False},
                    )
                )
        return await handler(request)


class MealPlanResultMiddleware(AgentMiddleware):
    """模型不能自行输出菜谱、营养或审核事实。"""

    async def awrap_model_call(self, request, handler):
        """本轮参考餐单保存成功后，只进行一次真实的无工具最终调用。"""
        from yuxi.services.health_meal_plan_service import planner_final_result

        tools = tuple(name for name in request.runtime.context.tools if name != "query_family_nutrition_knowledge")
        if tools == REFERENCE_TOOLS:
            messages = self._reference_model_messages(request)
            if messages != request.messages:
                request = request.override(messages=messages)
        preview_id = self._saved_reference_preview(request.state, request.runtime.context)
        if preview_id is None:
            tools = tuple(name for name in request.runtime.context.tools if name != "query_family_nutrition_knowledge")
            save_failure = None
            correction_kind = "save"
            if tools == REFERENCE_TOOLS:
                messages = request.state.get("messages", [])
                save_failure = reference_save_failure_index(messages, request.runtime.context.request_id)
                save_error_code = (
                    json.loads(messages[save_failure].content).get("error_code") if save_failure is not None else None
                )
                if save_failure is not None:
                    if save_error_code == "reference_quote_invalid":
                        correction_kind = "quote"
                    elif save_error_code in {"recipe_translation_missing", "recipe_translation_invalid"}:
                        correction_kind = "translation"
                    if "save_reference_meal_plan" not in {getattr(tool, "name", None) for tool in request.tools}:
                        raise HealthVisionError(
                            f"reference_{correction_kind}_correction_invalid", "餐单保存修正工具当前不可用", 422
                        )
                    if any(isinstance(message, AIMessage) for message in messages[save_failure + 1 :]):
                        raise HealthVisionError(
                            "reference_translation_correction_invalid"
                            if correction_kind == "translation"
                            else f"reference_{correction_kind}_correction_exhausted",
                            "餐单保存修正未完成，本轮已停止，请重新生成",
                            422,
                        )
                    request = request.override(
                        tools=[
                            tool for tool in request.tools if getattr(tool, "name", None) == "save_reference_meal_plan"
                        ],
                        tool_choice={"type": "function", "function": {"name": "save_reference_meal_plan"}},
                    )

            if tools == REFERENCE_TOOLS and request.tools and isinstance(request.model, ChatCompletionsAdapter):
                # 工具参数接收完整响应后再执行；不改变原模型或无工具最终回复。
                recovery_tool = self._reference_parameter_recovery(request)
                if save_failure is not None:
                    recovery_tool = "save_reference_meal_plan"
                original = request.system_message.text if request.system_message else ""
                request = request.override(
                    model=request.model.model_copy(update={"complete_tool_responses": True}),
                    model_settings={**request.model_settings, "parallel_tool_calls": False},
                    tool_choice=(
                        {"type": "function", "function": {"name": recovery_tool}}
                        if recovery_tool is not None
                        else request.tool_choice
                    ),
                    system_message=SystemMessage(
                        content=f"{original}\n\n每次只调用一个工具，并填写该工具的全部必填参数。"
                        "portion_quote、nutrition_quote只能逐字引用已读取原文；无对应说明时提交null或不填，"
                        "不得估算、拼接、翻译或将个人食用份量冒充原文引句。"
                        + (
                            "上次整批调用缺少必填参数，真实工具反馈已保留；"
                            "本次只纠正指定工具的一个调用，参数必须取自本轮已读取的真实资料，不猜测查询结果或来源标识。"
                            if recovery_tool is not None and save_failure is None
                            else ""
                        )
                        + (
                            "餐单中文译文校验失败。本次只调用一次save_reference_meal_plan，且只提交translation_correction："
                            "列出需修正的首次已选菜谱file_id、chunk_id和完整display_zh。"
                            "首次保存的餐次、菜谱和商品由服务端保留；不得重新提交read_selection、meals或product_matches。"
                            "按真实错误定位译文，保持原文数量、时间、单位和步骤顺序。"
                            if save_error_code in {"recipe_translation_missing", "recipe_translation_invalid"}
                            else "所选商品未对应本次原谱食材。本次只调用一次save_reference_meal_plan，"
                            "重新核对已读原谱recipe_check中的candidate_products；product_matches只提交候选product_id和对应candidate_keys。"
                            "不得自行提交ingredient_refs或purchase_gaps；无候选食材由后台保留为自行购买。"
                            if save_error_code == "reference_ingredient_mismatch"
                            else "餐单保存校验失败，按最新真实工具反馈修正；"
                            "原文、采购对应、中文译文各仅有一次修正机会。"
                            "按反馈纠正餐次、规格或食材采购对应，不编造商品或原因；只调用一次保存工具。"
                            if save_failure is not None
                            else ""
                        )
                    ),
                )
            response = await handler(request)
            if (
                tools == REFERENCE_TOOLS
                and save_failure is None
                and self._reference_save_ready(request)
                and response.result
                and isinstance(response.result[-1], AIMessage)
            ):
                answer = response.result[-1]
                if not answer.tool_calls and not answer.invalid_tool_calls:
                    try:
                        PlannerAnswer.model_validate_json(answer.text)
                    except ValidationError:
                        save_tool = next(tool for tool in request.tools if tool.name == "save_reference_meal_plan")
                        original = request.system_message.text if request.system_message else ""
                        return await handler(
                            request.override(
                                tools=[save_tool],
                                tool_choice={"type": "function", "function": {"name": "save_reference_meal_plan"}},
                                model_settings={**request.model_settings, "parallel_tool_calls": False},
                                system_message=SystemMessage(
                                    content=f"{original}\n\n已读取本轮档案、商品和原谱，但上一条回复没有提交餐单回执。"
                                    "现在只调用一次save_reference_meal_plan；餐次、菜谱、原料与商品必须来自本轮真实读取，"
                                    "缺货和无法证明匹配的食材如实保留缺口。不要直接输出餐单正文。"
                                ),
                            )
                        )
            return response

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
                messages=[next(message for message in reversed(request.messages) if isinstance(message, HumanMessage))],
                system_message=SystemMessage(content=f"{original}\n\n{instruction}"),
            )
        )

    async def aafter_model(self, state, runtime):
        """保持消息身份，将最终回执替换为权威结构化快照。"""
        from yuxi.services.health_meal_plan_service import planner_final_result

        message = state["messages"][-1]
        preview_id = self._saved_reference_preview(state, runtime.context)
        save_failure = None
        if (
            tuple(name for name in runtime.context.tools if name != "query_family_nutrition_knowledge")
            == REFERENCE_TOOLS
        ):
            save_failure = reference_save_failure_index(state["messages"], runtime.context.request_id)
        if (
            preview_id is None
            and save_failure is not None
            and message.type == "ai"
            and (
                message.invalid_tool_calls
                or len(message.tool_calls) != 1
                or message.tool_calls[0]["name"] != "save_reference_meal_plan"
            )
        ):
            error_code = json.loads(state["messages"][save_failure].content).get("error_code")
            kind = (
                "quote"
                if error_code == "reference_quote_invalid"
                else "translation"
                if error_code in {"recipe_translation_missing", "recipe_translation_invalid"}
                else "save"
            )
            raise HealthVisionError(
                f"reference_{kind}_correction_invalid", "餐单保存修正须只提交一个保存调用，本轮已停止", 422
            )
        if preview_id is not None and message.type == "ai" and (message.tool_calls or message.invalid_tool_calls):
            raise HealthVisionError("planner_finalization_invalid", "餐单保存后的最终回复不允许继续调用工具", 422)
        if message.type == "ai" and not message.tool_calls:
            answer = json.dumps({"preview_id": preview_id}) if preview_id is not None else message.text
            result = await planner_final_result(runtime.context, answer)
            return {"messages": [message.model_copy(update={"content": json.dumps(result, ensure_ascii=False)})]}

    @staticmethod
    def _reference_model_messages(request):
        """模型不再重复读取旧轮工具流水；原 checkpoint 和当前轮来源回执保持完整。"""
        messages = request.messages
        for index in range(len(messages) - 1, -1, -1):
            if isinstance(messages[index], HumanMessage):
                if messages[index].additional_kwargs.get("health_request_id") != request.runtime.context.request_id:
                    return messages
                return [
                    message
                    for message in messages[:index]
                    if not isinstance(message, ToolMessage)
                    and not (isinstance(message, AIMessage) and (message.tool_calls or message.invalid_tool_calls))
                ] + [MealPlanResultMiddleware._compact_reference_products(message) for message in messages[index:]]
        return messages

    @staticmethod
    def _compact_reference_products(message):
        """模型读取完整原谱字段与精简商品候选；审计保留未裁剪回执。"""
        if (
            not isinstance(message, ToolMessage)
            or message.name not in {"find_reference_products", "read_reference_recipe"}
            or message.status != "success"
        ):
            return message
        try:
            payload = json.loads(message.content)
        except (TypeError, ValueError):
            return message
        if not isinstance(payload, dict):
            return message
        if message.name == "read_reference_recipe":
            from copy import deepcopy

            payload = deepcopy(payload)
            for item in payload.get("items", [payload]):
                if not isinstance(item, dict) or not isinstance(item.get("recipe_check"), dict):
                    return message
                check = item["recipe_check"]
                if check.get("status") != "needs_review" and all(
                    key in check for key in ("name", "ingredients", "steps")
                ):
                    item.pop("content", None)
                for group in check.get("ingredient_matches", []):
                    group.pop("candidate_skus", None)
                    group["candidate_products"] = [
                        {key: value for key, value in product.items() if key in {"product_id", "product_name"}}
                        for product in group.get("candidate_products", [])
                    ]
            return message.model_copy(
                update={"content": json.dumps(payload, ensure_ascii=False, separators=(",", ":"))}
            )
        if not isinstance(payload.get("products"), list) or not payload["products"]:
            return message
        if any(not isinstance(product, dict) for product in payload["products"]):
            return message
        compact = {key: value for key, value in payload.items() if key not in {"catalog", "products"}}
        compact["products"] = [
            {key: value[:320] if key == "product_description" and isinstance(value, str) else value
             for key, value in product.items() if key not in {"skus", "image_url"}}
            for product in payload["products"]
        ]
        return message.model_copy(update={"content": json.dumps(compact, ensure_ascii=False, separators=(",", ":"))})

    @staticmethod
    def _reference_parameter_recovery(request):
        """只用当前请求真实缺参反馈选择下一节点工具，单次缺参失败即停止。"""
        messages = request.state.get("messages", [])
        for index in range(len(messages) - 1, -1, -1):
            if isinstance(messages[index], HumanMessage):
                if messages[index].additional_kwargs.get("health_request_id") != request.runtime.context.request_id:
                    return None
                break
        else:
            return None

        current = messages[index + 1 :]
        for index in range(len(current) - 1, -1, -1):
            if isinstance(current[index], AIMessage):
                calls = current[index].tool_calls
                feedback = current[index + 1 :]
                break
        else:
            return None

        required_tools = {
            "find_reference_products",
            "search_reference_recipes",
            "read_reference_recipe",
            "save_reference_meal_plan",
        }
        allowed = {getattr(tool, "name", None) for tool in request.tools} & required_tools
        if not calls or any(call["name"] not in allowed or call["args"] != {} for call in calls):
            return None
        call_ids = {call["id"] for call in calls}
        if None in call_ids or "" in call_ids or len(call_ids) != len(calls):
            return None
        if len(feedback) != len(calls) or any(not isinstance(item, ToolMessage) for item in feedback):
            return None
        results = {item.tool_call_id: item for item in feedback}
        if set(results) != call_ids or any(
            results[call["id"]].status != "error" or results[call["id"]].name != call["name"] for call in calls
        ):
            return None
        if len(calls) == 1:
            raise HealthVisionError(
                "reference_tool_parameters_invalid", "配餐工具缺少必要参数，本轮已停止，请重新生成", 422
            )
        return calls[0]["name"]

    @staticmethod
    def _reference_save_ready(request):
        """仅本轮已成功读取档案、商品和原谱时才补一次遗漏的保存调用。"""
        if "save_reference_meal_plan" not in {getattr(tool, "name", None) for tool in request.tools}:
            return False
        messages = request.state.get("messages", [])
        for index in range(len(messages) - 1, -1, -1):
            if isinstance(messages[index], HumanMessage):
                if messages[index].additional_kwargs.get("health_request_id") != request.runtime.context.request_id:
                    return False
                break
        else:
            return False
        read = {
            message.name
            for message in messages[index + 1 :]
            if isinstance(message, ToolMessage) and message.status == "success"
        }
        return {
            "get_reference_plan_context",
            "find_reference_products",
            "search_reference_recipes",
            "read_reference_recipe",
        } <= read

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
                find_reference_products,
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
                ReferenceContextMiddleware(),
                MealPlanResultMiddleware(),
                TokenUsageMiddleware(),
            ],
            context_schema=self.context_schema,
            checkpointer=await self._get_checkpointer(),
        )

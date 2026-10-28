"""普通配菜咨询必须查询真实商城并提交结构化选品结果。"""

import re

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import HumanMessage, ToolMessage

from yuxi.services.health_vision_types import HealthVisionError


class HealthCatalogMiddleware(AgentMiddleware):
    """只约束有商品工具的本轮咨询，重试继续经过原有预算与权限检查。"""

    async def awrap_model_call(self, request, handler):
        """已查询却未选择时不允许直接以普通文字完成本轮。"""
        available = {tool.name for tool in request.tools}
        if not {"find_food_packages", "select_food_products"} <= available:
            return await handler(request)
        human_index = next(
            (i for i in range(len(request.messages) - 1, -1, -1) if isinstance(request.messages[i], HumanMessage)),
            None,
        )
        if human_index is None:
            return await handler(request)
        human = request.messages[human_index]
        if human.additional_kwargs.get("health_request_id") != request.runtime.context.request_id:
            raise HealthVisionError("catalog_request_mismatch", "当前商品咨询轮次无法核对", 409)
        current = request.messages[human_index + 1 :]
        queried = [
            m for m in current if isinstance(m, ToolMessage) and m.name == "find_food_packages" and m.status != "error"
        ]
        selected = any(
            isinstance(m, ToolMessage) and m.name == "select_food_products" and m.status != "error" for m in current
        )
        final = (
            request.state.get("health_final_request_id") == request.runtime.context.request_id
            and request.state.get("health_answer_phase") == "final"
        )
        if final:
            if not queried and food_product_intent(human.text):
                raise HealthVisionError("catalog_tool_required", "本轮商品查询未完成，请重试", 409)
            if queried and not selected:
                raise HealthVisionError("catalog_selection_required", "本轮商品选择未完成，请重试", 409)
            # 最终正文只能生成一次；目录义务必须在任何公开增量产生前完成。
            return await handler(request)

        forced = None
        if not queried and food_product_intent(human.text):
            forced = "find_food_packages"
        elif queried and not selected and len(queried) >= 4:
            forced = "select_food_products"
        response = await handler(request.override(tool_choice=tool_choice(forced)) if forced else request)
        calls = [
            call
            for message in getattr(response, "model_response", response).result
            for call in getattr(message, "tool_calls", [])
        ]
        if forced and not any(call["name"] == forced for call in calls):
            raise HealthVisionError("catalog_tool_required", "本轮商品查询未完成，请重试", 409)
        finishing = not calls or any(call["name"] == "finalize_health_answer" for call in calls)
        if queried and not selected and finishing:
            response = await handler(request.override(tool_choice=tool_choice("select_food_products")))
            if not any(
                call["name"] == "select_food_products"
                for message in getattr(response, "model_response", response).result
                for call in getattr(message, "tool_calls", [])
            ):
                raise HealthVisionError("catalog_selection_required", "本轮商品选择未完成，请重试", 409)
        return response


def food_product_intent(text):
    """识别普通选菜请求；纯科普及明确拒绝商品推荐不强制查商城。"""
    if re.search(
        r"(?:不要|不用|不需要|别)(?:再|给我|为我|向我|帮我)?(?:推荐商品|推荐食材|推荐食物|商品推荐|食材推荐|配菜|查询商城|展示商品|显示商品|推荐)(?:[，。！？、\s]|$)",
        text,
    ):
        return False
    return bool(
        re.search(
            r"配菜|吃什么|吃点什么|做什么菜|安排.{0,12}(?:早餐|午餐|晚餐|三餐|吃)|推荐.{0,12}(?:菜|食材|食物|商品)|(?:商城|商店).{0,12}(?:商品|食材|营养|卖)|(?:挑|选|买).{0,8}(?:食材|食物|菜)",
            text,
        )
    )


def tool_choice(name):
    """沿用当前模型供应商支持的指定工具协议。"""
    return {"type": "function", "function": {"name": name}}

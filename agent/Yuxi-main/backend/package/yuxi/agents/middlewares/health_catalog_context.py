"""合并同轮商品查询与模型输入，原始业务回执继续由服务端校验。"""

import json
import re

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage


class HealthCatalogContextMiddleware(AgentMiddleware):
    """使用当前消息中的调用身份去重，不跨请求缓存成员或商品资料。"""

    async def awrap_tool_call(self, request, handler):
        """已有成功回执后，顺序及并行重复调用只返回原调用位置。"""
        key = catalog_query_key(request.tool_call)
        if key is None:
            return await handler(request)
        messages = current_turn(request.state["messages"])
        results = {
            message.tool_call_id: message
            for message in messages
            if isinstance(message, ToolMessage) and message.status == "success"
        }
        for message in messages:
            if not isinstance(message, AIMessage):
                continue
            for call in message.tool_calls:
                if call["id"] == request.tool_call["id"]:
                    return await handler(request)
                if catalog_query_key(call) != key:
                    continue
                result = results.get(call["id"])
                if not successful_catalog_result(result):
                    continue
                return ToolMessage(
                    name="find_food_packages",
                    tool_call_id=request.tool_call["id"],
                    content=json.dumps(
                        {
                            "duplicate_query": True,
                            "original_tool_call_id": call["id"],
                            "offers": [],
                            "message": (
                                "相同查询已有结果，请读取原调用，不重复浏览。需要其他商品时使用具体食材名或下一页。"
                                "此提示不代表新查到商品或通过校验。"
                            ),
                        },
                        ensure_ascii=False,
                    ),
                )
        return await handler(request)

    async def awrap_model_call(self, request, handler):
        """仅投影已授权模型输入；checkpoint、审计、选品和发布继续使用原回执。"""
        return await handler(request.override(messages=compact_catalog_messages(request.messages)))


def current_turn(messages):
    """以最后一条用户消息隔离本轮，恢复时仍由已有调用与回执决定去重。"""
    start = next((i for i in range(len(messages) - 1, -1, -1) if isinstance(messages[i], HumanMessage)), 0)
    return messages[start:]


def catalog_query_key(call):
    """只归一化商城已支持的名称和分页；非法或未知参数仍交原工具校验。"""
    if call.get("name") != "find_food_packages":
        return None
    args = call.get("args", {})
    if not isinstance(args, dict) or set(args) - {"query", "offset"}:
        return None
    query, offset = args.get("query", ""), args.get("offset", 0)
    if not isinstance(query, str) or len(query) > 80 or type(offset) is not int or not 0 <= offset <= 10000:
        return None
    return re.sub(r"\s+", "", query).casefold(), offset


def successful_catalog_result(message):
    """只有真实商品结果可以抑制后续查询，失败或去重提示不算来源。"""
    if message is None or message.name != "find_food_packages" or not isinstance(message.content, str):
        return False
    try:
        payload = json.loads(message.content)
    except ValueError:
        return False
    return isinstance(payload, dict) and isinstance(payload.get("offers"), list) and not payload.get("duplicate_query")


def compact_catalog_messages(messages):
    """同轮相同目录只传一次，商品说明保留原文，签名及完整档案仍留在原消息。"""
    projected, indexes = [], {}
    for message in messages:
        if isinstance(message, HumanMessage):
            indexes = {}
        if not isinstance(message, ToolMessage) or message.name not in {"find_food_packages", "select_food_products"}:
            projected.append(message)
            continue
        if message.status != "success" or not isinstance(message.content, str):
            projected.append(message)
            continue
        try:
            payload = json.loads(message.content)
        except ValueError:
            projected.append(message)
            continue
        # 新版选品依据 SKU；旧版依赖正文 reference 中的完整签名，保持旧格式原样。
        if not isinstance(payload, dict) or payload.get("catalog_context_version") != 1:
            projected.append(message)
            continue
        index = payload.get("catalog_index")
        if isinstance(index, list):
            identity = json.dumps([payload.get("catalog_version"), index], sort_keys=True, ensure_ascii=False)
            if identity in indexes:
                del payload["catalog_index"]
                payload["catalog_index_from_tool_call_id"] = indexes[identity]
            else:
                indexes[identity] = message.tool_call_id
        for offer in payload.get("offers", []):
            if not isinstance(offer, dict):
                continue
            offer.pop("offer_token", None)
            description, note = offer.get("product_description"), offer.get("note")
            if isinstance(description, str) and description and isinstance(note, str) and note.endswith(description):
                offer["note"] = note[: -len(description)].rstrip()
        projected.append(message.model_copy(update={"content": json.dumps(payload, ensure_ascii=False)}))
    return projected

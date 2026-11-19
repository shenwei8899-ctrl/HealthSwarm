"""商城意图与守卫拒绝回执的共享协议，拒绝回执不构成商品来源。"""

import re

from langchain_core.messages import ToolMessage


CATALOG_TOOL_NAMES = frozenset({"get_food_categories", "find_food_packages", "select_food_products"})
NON_PRODUCT_CATALOG_MESSAGE = (
    "本轮没有商城商品请求，未查询商品。请使用已授权的资料工具核对限制，随后完成普通咨询；不要再次调用商城工具。"
)


def is_catalog_intent_denial(message, human, calls):
    """只识别无购买意图轮次中与实际声明调用配对的固定拒绝。"""
    if (
        not isinstance(message, ToolMessage)
        or message.name not in CATALOG_TOOL_NAMES
        or message.status != "error"
        or message.content != NON_PRODUCT_CATALOG_MESSAGE
        or human is None
        or calls.get(message.tool_call_id) != message.name
    ):
        return False
    request_id = human.additional_kwargs.get("health_request_id")
    if not isinstance(request_id, str) or not request_id or food_product_intent(human.text):
        return False
    # 已上线的旧拒绝没有标识；仍必须匹配所属用户轮次、调用身份和固定正文。
    if "catalog_guard" not in message.additional_kwargs:
        return True
    return message.additional_kwargs["catalog_guard"] == {"reason": "no_product_intent", "request_id": request_id}


def food_product_intent(text):
    """明确商品请求和下午加餐选品查询真实目录。"""
    purchase_action = r"(?:买|购买|选购|采购|下单|加购|购物)"
    reject_catalog = bool(
        re.search(
            r"(?:不要|不用|不需要|不想|别)(?:再|给我|为我|向我|帮我|去)*"
            r"(?:推荐|查询|查|展示|显示|购买|选购)?(?:商品|商城|食材包)",
            text,
        )
    )
    for clause in re.split(r"[，,。！？!?；;\n]|但是|不过|但", text):
        if re.search(r"(?:不想|不需要|不用|不要|别|不)(?:再|给我|为我|向我|帮我|去)*" + purchase_action, clause):
            continue
        clause = re.sub(
            r"(?:不要|不用|不需要|不想|别|不买)(?:再|给我|为我|向我|帮我)?"
            r"(?:(?:推荐|查询|查|展示|显示|购买|选购)?(?:商品|商城|食材包)|"
            r"推荐食材|推荐食物|商品推荐|商城推荐|食材推荐|配菜|推荐|购物|购买)(?:[、\s]|$)",
            " ",
            clause,
        )
        if re.search(
            r"商品|食材包|\bsku\b|商城|商店|价格|售价|库存|多少钱|哪里有卖|"
            rf"(?:想|要|准备|帮我|给我).{{0,8}}{purchase_action}(?![了过的])|"
            rf"(?:可以|能|哪里|怎么|如何){purchase_action}|"
            rf"^(?:请)?{purchase_action}(?![了过的])|{purchase_action}(?:什么|哪些|几|点|些|一|这|那)",
            clause,
            re.IGNORECASE,
        ):
            return True
        if not reject_catalog and re.search(
            r"(?:下午|午后)(?:的)?(?:加餐|茶|点心).{0,12}(?:吃|喝|选|推荐|买|有什么|啥|什么)",
            clause,
        ):
            return True
    return False

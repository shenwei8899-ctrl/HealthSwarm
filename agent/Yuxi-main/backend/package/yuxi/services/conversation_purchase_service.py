"""AI 按购买意图查询真实食材包，签名回执绑定同一 Run、本人和商品组成。"""

import base64
import hashlib
import hmac
import json
import re
import time
from decimal import Decimal, InvalidOperation
from uuid import NAMESPACE_URL, uuid5

from yuxi.repositories.conversation_purchase_repository import ConversationPurchaseRepository
from yuxi.repositories.health_consultation_repository import HealthConsultationRepository
from yuxi.repositories.health_task_repository import HealthTaskRepository
from yuxi.services.daily_commerce_service import current_catalog, commerce_request
from yuxi.services.health_commerce_service import sign_commerce_source
from yuxi.services.health_nutrition_service import input_fingerprint
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.storage.postgres.manager import pg_manager

OFFER_PATTERN = re.compile(r"\[食材包:([A-Za-z0-9_-]{100,4096})\]")


async def find_conversation_packages(context, query):
    """只有模型识别到选购需求才调用；读取目录不创建会员、采购包或订单。"""
    from yuxi.services.health_consultation_service import require_consultation, require_consultation_attempt

    await require_consultation_attempt(context)
    catalog = await current_catalog()
    async with pg_manager.get_async_session_context() as session:
        run = await HealthConsultationRepository(session).require_attempt(context)
        binding, _ = await require_consultation(
            session, context.uid, context.thread_id, expected=run.input_payload["health_processing"]
        )
        member = await require_shopping_member(session, binding)
        offers = []
        for item in catalog["items"]:
            if normalized(query) not in normalized(item.get("product_name", "")):
                continue
            if not package_available(member.profile, item, catalog):
                continue
            source = {
                "kind": "conversation_package",
                "uid": context.uid,
                "member_id": binding.member_id,
                "run_id": run.id,
                "request_id": run.request_id,
                "query": query,
                "catalog_version": catalog["version"],
                "sku_id": str(item["sku_id"]),
                "composition_hash": composition_hash(item),
                "profile_hash": input_fingerprint(member.profile),
                "expires_at": int(time.time()) + 1800,
            }
            token = encode_offer(source)
            offers.append({**public_offer(item), "reference": "[食材包:" + token + "]"})
            if len(offers) == 3:
                break
        return {
            "offers": offers,
            "message": "请在自然语言说明后原样附上所选 reference；仅显示真实包，不改写今日餐单。"
            if offers
            else "没有查到配料信息完整、可售且能核对已知限制的对应食材包；不要编造商品或声称已加入购物车。",
        }


async def offers_for_answer(session, run, binding, content, *, publication=False):
    """结果只采用同 Run 的签名回执，价格与库存每次从商城回读。"""
    tokens = list(dict.fromkeys(OFFER_PATTERN.findall(content)))
    if "[食材包:" in OFFER_PATTERN.sub("", content) or len(tokens) > 3:
        raise HealthVisionError("purchase_receipt_invalid", "食材包回执无法核对", 409)
    if not tokens:
        return content, []
    member = await require_shopping_member(session, binding)
    catalog = await current_catalog()
    offers = []
    for token in tokens:
        source = decode_offer(token)
        verify_offer_owner(source, run, binding)
        item = next((item for item in catalog["items"] if str(item["sku_id"]) == source["sku_id"]), None)
        available = bool(
            item
            and source["expires_at"] > time.time()
            and source["profile_hash"] == input_fingerprint(member.profile)
            and source["composition_hash"] == composition_hash(item)
            and package_available(member.profile, item, catalog)
        )
        if publication and not available:
            raise HealthVisionError("purchase_source_changed", "食材包或本人资料已变化，请重新查询", 409)
        offers.append(
            {
                **(public_offer(item) if item else {"name": "原食材包"}),
                "offer_token": token,
                "request_id": run.request_id,
                "available": available,
            }
        )
    return OFFER_PATTERN.sub("", content).strip(), offers


async def read_conversation_purchase(uid, request_id):
    """历史和购买页均回读同一完成消息，不信任客户端传来的商品字段。"""
    from yuxi.services.health_consultation_service import require_consultation

    async with pg_manager.get_async_session_context() as session:
        repo = HealthTaskRepository(session)
        _, binding, run = await repo.request_context(uid, request_id)
        if run is None or run.status != "completed" or run.agent_slug != "health-consultation":
            raise HealthVisionError("purchase_source_unavailable", "对话尚未完成或不是食材包来源", 409)
        await require_consultation(
            session, uid, run.conversation_thread_id, expected=run.input_payload["health_processing"]
        )
        message = await repo.final_message(run)
        _, offers = await offers_for_answer(session, run, binding, message.content)
        return {"request_id": request_id, "offers": offers}


async def publish_conversation_purchase(uid, request_id, token):
    """用户明确购买后才发布一个真实食材包，重复提交沿用确定性任务号。"""
    result = await read_conversation_purchase(uid, request_id)
    offer = next((offer for offer in result["offers"] if hmac.compare_digest(offer["offer_token"], token)), None)
    if not offer or not offer["available"]:
        raise HealthVisionError("purchase_source_changed", "食材包已变化或不可购买，请重新查询", 409)
    source = decode_offer(token)
    catalog = await current_catalog()
    item = next((item for item in catalog["items"] if str(item["sku_id"]) == source["sku_id"]), None)
    if not item or composition_hash(item) != source["composition_hash"]:
        raise HealthVisionError("purchase_source_changed", "食材包配料已变化", 409)
    task = str(uuid5(NAMESPACE_URL, "conversation-package:" + hashlib.sha256(token.encode()).hexdigest()))
    requirements = [
        {
            "ingredient_id": row["ingredient_id"],
            "ingredient_code": row["ingredient_code"],
            "required_value": str(edible_amount(row)),
            "required_unit": row["net_unit"],
        }
        for row in item["ingredients"]
    ]
    payload = {
        "agent_task_id": task,
        "family_ref": "conversation:" + request_id,
        "user_ref": "uid:" + uid,
        "menu_version_ref": "conversation:" + request_id,
        "catalog_version": source["catalog_version"],
        "ingredient_requirements": requirements,
        "items": [{"sku_id": item["sku_id"], "quantity": 1}],
        "nutrition_validation": {
            "status": "passed",
            "validation_id": request_id,
            "rules_version": source["composition_hash"],
            "summary": "通用食材包配料与已知限制核对，不是个体化配餐或医疗建议",
        },
        "agent_source_proof": sign_commerce_source(source),
    }
    package = await commerce_request("POST", "/api/v1/integration/ai/recommendation-packages", payload, request_id=task)
    return {"request_id": request_id, "package": package, "offer": offer}


async def validate_conversation_source(session, source):
    """商城核价和下单回源时重验完成消息、本人、配料及已知限制。"""
    from yuxi.services.health_consultation_service import require_consultation

    repo = HealthTaskRepository(session)
    _, binding, run = await repo.request_context(source["uid"], source["request_id"])
    if run is None or run.status != "completed":
        raise HealthVisionError("purchase_source_unavailable", "对话采购来源尚未完成", 409)
    await require_consultation(
        session, source["uid"], run.conversation_thread_id, expected=run.input_payload["health_processing"]
    )
    message = await repo.final_message(run)
    token = encode_offer(source)
    if token not in OFFER_PATTERN.findall(message.content):
        raise HealthVisionError("purchase_receipt_invalid", "该食材包未出现在当前对话的最终答复", 403)
    _, offers = await offers_for_answer(session, run, binding, message.content)
    if not any(offer["offer_token"] == token and offer["available"] for offer in offers):
        raise HealthVisionError("purchase_source_changed", "对话食材包来源已失效", 410)


async def require_shopping_member(session, binding):
    """只能使用当前本人已确认的档案，不能借购包查询读取他人健康资料。"""
    from yuxi.repositories.health_vision_repository import HealthVisionRepository
    from yuxi.services.miniapp_profile_types import miniapp_onboarding_ready

    await HealthVisionRepository(session).authorize(binding.member_id, binding.actor_uid, "profile_view")
    member = await ConversationPurchaseRepository(session).source_member(binding.member_id, binding.actor_uid)
    if member is None or not miniapp_onboarding_ready(member, None):
        raise HealthVisionError("purchase_profile_required", "请先核对并确认本人健康档案", 409)
    return member


def normalized(value):
    """仅用于目录中真实商品的短菜名匹配。"""
    return re.sub(r"\s+", "", str(value)).casefold()


def package_available(profile, item, catalog):
    """完整审核配料才能核对限制；无法解释的硬限制不推测为安全。"""
    ingredients = item.get("ingredients") or []
    if item.get("data_completeness") != "complete":
        return False
    if item.get("sale_status") != "available" or int(item.get("available_quantity") or 0) < 1 or not ingredients:
        return False
    if any(
        row.get("review_status") != "approved"
        or not row.get("ingredient_id")
        or not row.get("ingredient_code")
        or not row.get("net_unit")
        or edible_amount(row) <= 0
        for row in ingredients
    ):
        return False
    dietary = profile.get("dietary_details") or {}
    if dietary.get("doctorStatus") == "set":
        return False
    names = {
        normalized(row.get("name")): row.get("ingredient_code")
        for sku in catalog["items"]
        for row in sku.get("ingredients", [])
        if row.get("name") and row.get("ingredient_code")
    }
    codes = {row.get("ingredient_code") for row in ingredients} | set(item.get("allergen_codes") or [])
    for state, field in [
        ("allergyStatus", "allergies"),
        ("intoleranceStatus", "intolerances"),
        ("avoidanceStatus", "avoidances"),
    ]:
        for restriction in dietary.get(field, []) if dietary.get(state) == "set" else []:
            code = names.get(normalized(restriction))
            if not code or code in codes:
                return False
    return True


def edible_amount(row):
    """与商城覆盖量契约一致，净含量乘换算率和可食比例。"""
    try:
        amount = (
            Decimal(str(row.get("net_value", 0)))
            * Decimal(str(row.get("convert_ratio", 1)))
            * (1 - Decimal(str(row.get("loss_rate", 0))))
        )
        return amount if amount.is_finite() and amount > 0 else Decimal(0)
    except (InvalidOperation, ValueError):
        return Decimal(0)


def composition_hash(item):
    """价格和库存由核价更新，配料与规格变化使旧购买依据失效。"""
    return input_fingerprint(
        {key: item.get(key) for key in ["sku_id", "product_name", "net_content", "ingredients", "allergen_codes"]}
    )


def public_offer(item):
    """只公开商城商品字段，不向商城或客户端发送健康档案。"""
    return {
        "name": item.get("product_name", ""),
        "sku_id": str(item["sku_id"]),
        "price_cent": item.get("price_cent"),
        "image_url": item.get("image_url", ""),
        "spec": str((item.get("net_content") or {}).get("value", ""))
        + str((item.get("net_content") or {}).get("unit", "")),
        "ingredients": [row.get("name") or row.get("ingredient_code") for row in item.get("ingredients", [])],
        "note": "通用食材包；价格、库存和配送以下单前核对为准，不代表个体化配餐结论。",
    }


def encode_offer(source):
    """回执无需另一张状态表，完整来源以服务端签名并绑定原 Run。"""
    proof = sign_commerce_source(source)
    return base64.urlsafe_b64encode(json.dumps(proof, separators=(",", ":")).encode()).decode().rstrip("=")


def decode_offer(token):
    """任何来自模型、历史或客户端的回执都必须验证原始签名。"""
    try:
        if not re.fullmatch(r"[A-Za-z0-9_-]{100,4096}", token):
            raise ValueError("invalid token")
        proof = json.loads(base64.urlsafe_b64decode(token + "=" * (-len(token) % 4)))
        source = json.loads(proof["payload"])
        if (
            not hmac.compare_digest(proof["signature"], sign_commerce_source(source)["signature"])
            or source["kind"] != "conversation_package"
        ):
            raise ValueError("invalid proof")
        return source
    except (ValueError, KeyError, TypeError):
        raise HealthVisionError("purchase_receipt_invalid", "食材包回执无效，请重新询问", 403) from None


def verify_offer_owner(source, run, binding):
    """有效签名也不能被相邻请求、其他成员或账号借用。"""
    if (source.get("uid"), source.get("run_id"), source.get("request_id"), source.get("member_id")) != (
        run.uid,
        run.id,
        run.request_id,
        binding.member_id,
    ):
        raise HealthVisionError("purchase_receipt_invalid", "食材包不属于当前对话和本人", 403)

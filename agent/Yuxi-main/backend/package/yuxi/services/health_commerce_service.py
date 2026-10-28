"""已批准采用的可食需求经审核换算后连接独立商城，不生成餐单。"""

import hashlib
import hmac
import json
import os
import time
from datetime import UTC, datetime
from decimal import Decimal, ROUND_UP
from urllib.parse import urlsplit
from uuid import UUID, uuid4

import httpx
from pydantic import Field, ValidationError

from yuxi.repositories.user_repository import UserRepository
from yuxi.services.health_nutrition_service import input_fingerprint
from yuxi.services.health_purchase_service import purchase_requirements
from yuxi.services.health_purchase_types import PurchaseSelection
from yuxi.services.health_vision_types import HealthDTO, HealthVisionError
from yuxi.storage.postgres.manager import pg_manager


class IngredientMapping(HealthDTO):
    """换算依据明确绑定食品版本与烹饪状态，不能按名称推测。"""

    food_id: UUID
    cooking_state: str = Field(min_length=1, max_length=40)
    ingredient_code: str = Field(min_length=1, max_length=50)
    purchase_grams_per_edible_gram: Decimal = Field(gt=0, le=1000, decimal_places=6)
    source_ref: str = Field(min_length=1, max_length=200)
    approved_by: str = Field(min_length=1, max_length=100)
    valid_until: datetime


class SourceProof(HealthDTO):
    """来源凭据只供商城后端回源，不向用户返回健康资料。"""

    payload: str = Field(min_length=1, max_length=65536)
    signature: str = Field(pattern=r"^[a-f0-9]{64}$")


def commerce_configuration():
    """只返回缺失项，不公开连接凭据和专业映射内容。"""
    missing = []
    base = os.getenv("HEALTH_COMMERCE_URL", "").rstrip("/")
    try:
        parts = urlsplit(base)
    except ValueError:
        parts = urlsplit("")
    local = parts.hostname in {"localhost", "127.0.0.1"}
    if os.getenv("HEALTH_COMMERCE_ALLOW_DOCKER_HOST") == "1":
        local = local or parts.hostname == "host.docker.internal"
    if (
        not parts.hostname
        or parts.username
        or parts.password
        or parts.query
        or parts.fragment
        or parts.path
        or not (parts.scheme == "https" or parts.scheme == "http" and local)
    ):
        missing.append("HEALTH_COMMERCE_URL")
    if not os.getenv("HEALTH_COMMERCE_CLIENT_ID"):
        missing.append("HEALTH_COMMERCE_CLIENT_ID")
    if len(os.getenv("HEALTH_COMMERCE_CLIENT_SECRET", "")) < 32:
        missing.append("HEALTH_COMMERCE_CLIENT_SECRET")
    if len(os.getenv("HEALTH_COMMERCE_SOURCE_SECRET", "")) < 32:
        missing.append("HEALTH_COMMERCE_SOURCE_SECRET")
    try:
        mappings = [
            IngredientMapping.model_validate(row)
            for row in json.loads(os.getenv("HEALTH_COMMERCE_INGREDIENT_MAP", "[]"))
        ]
        keys = [(row.food_id, row.cooking_state) for row in mappings]
        if not keys or len(keys) != len(set(keys)):
            raise ValueError("empty or duplicate mapping")
        if any(row.valid_until.tzinfo is None or row.valid_until <= datetime.now(UTC) for row in mappings):
            raise ValueError("expired or unzoned mapping")
    except (ValueError, TypeError, ValidationError):
        missing.append("HEALTH_COMMERCE_INGREDIENT_MAP")
        mappings = []
    return {"available": not missing, "missing_configuration": missing}, base, mappings


def require_commerce_configuration():
    """配置不完整时拒绝发送采购请求。"""
    status, base, mappings = commerce_configuration()
    if not status["available"]:
        raise HealthVisionError("commerce_unavailable", "餐单采购配置未就绪", 503)
    return base, mappings


def convert_requirements(current, mappings):
    """净可食量只通过已审核系数转换，采购克数向上取三位小数。"""
    if current["status"] != "requirements_ready":
        raise HealthVisionError("inventory_confirmation_required", "请明确确认库存后生成采购清单", 409)
    lookup = {(str(row.food_id), row.cooking_state): row for row in mappings}
    grouped = {}
    for item in current["items"]:
        mapping = lookup.get((item["food_id"], item["cooking_state"]))
        if mapping is None:
            raise HealthVisionError("ingredient_mapping_missing", "食品版本或烹饪状态缺少已审核的采购换算", 409)
        value = Decimal(item["net_required_grams"]) * mapping.purchase_grams_per_edible_gram
        grouped[mapping.ingredient_code] = grouped.get(mapping.ingredient_code, Decimal(0)) + value
    result = [
        {
            "ingredient_code": code,
            "required_value": str(value.quantize(Decimal(".001"), rounding=ROUND_UP)),
            "required_unit": "g",
            "is_optional": False,
        }
        for code, value in sorted(grouped.items())
        if value > 0
    ]
    if not result:
        raise HealthVisionError("purchase_not_needed", "当前库存已覆盖餐单，无需购买", 409)
    return result


async def mall_request(base, path, *, payload=None, key=None):
    """商城签名绑定原始正文；超时不自动重试，固定任务号支持用户重试。"""
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode() if payload is not None else b""
    method = "POST" if payload is not None else "GET"
    stamp, nonce = str(int(time.time())), uuid4().hex
    canonical = "\n".join([method, path, stamp, nonce, hashlib.sha256(body).hexdigest()])
    signature = hmac.new(os.environ["HEALTH_COMMERCE_CLIENT_SECRET"].encode(), canonical.encode(), "sha256").hexdigest()
    headers = {
        "X-Client-Id": os.environ["HEALTH_COMMERCE_CLIENT_ID"],
        "X-Timestamp": stamp,
        "X-Nonce": nonce,
        "X-Signature": signature,
        "Content-Type": "application/json",
    }
    if key:
        headers["Idempotency-Key"] = key
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=False, trust_env=False) as client:
            response = await client.request(method, base + path, content=body, headers=headers)
        data = response.json()
    except (httpx.HTTPError, ValueError):
        raise HealthVisionError("commerce_unavailable", "商城暂不可用，请查询后重试原操作", 503) from None
    if response.status_code != 200 or data.get("code") != 0:
        raise HealthVisionError("commerce_rejected", "商城拒绝采购请求，请检查会员关联、服务签名和商品配置", 409)
    return data["data"]


async def export_adopted_purchase(uid, member_id, selected):
    """交易身份和营养通过状态来自服务器有效采用，客户端只指定采用及库存。"""
    current = await purchase_requirements(uid, member_id, selected)
    base, mappings = require_commerce_configuration()
    requirements = convert_requirements(current, mappings)
    mapping_hash = input_fingerprint([row.model_dump(mode="json") for row in mappings])
    source = {
        "uid": uid,
        "member_id": member_id,
        "selection": selected.model_dump(mode="json"),
        "source_hash": current["source_hash"],
        "mapping_hash": mapping_hash,
    }
    proof = sign_commerce_source(source)
    catalog = await mall_request(base, "/api/v1/integration/ai/catalog/products")
    task = "adoption-" + input_fingerprint({"source": source, "catalog": catalog["catalog_version"]})
    payload = {
        "agent_task_id": task,
        "family_ref": "adoption:" + str(selected.adoption_id),
        "user_ref": "uid:" + uid,
        "menu_version_ref": f"{current['sources']['plan_id']}:{selected.plan_version}",
        "catalog_version": catalog["catalog_version"],
        "meal_date": current["sources"]["plan_date"],
        "nutrition_validation": {
            "status": "passed",
            "validation_id": str(selected.adoption_id),
            "rules_version": current["source_hash"],
        },
        "ingredient_requirements": requirements,
        "agent_source_proof": proof,
    }
    package = await mall_request(
        base, "/api/v1/integration/ai/recommendation-packages", payload=payload, key=task[-64:]
    )
    return {
        "source": "approved_adopted_plan",
        "adoption_id": str(selected.adoption_id),
        "requirements": requirements,
        "package": package,
        "ai_generation_performed": False,
    }


async def validate_source_proof(proof):
    """校验签名后重新核对全体权限、采用、专业来源与映射，拒绝返回原始资料。"""
    secret = os.environ.get("HEALTH_COMMERCE_SOURCE_SECRET", "")
    if len(secret) < 32:
        raise HealthVisionError("commerce_unavailable", "餐单来源校验服务未就绪", 503)
    expected = hmac.new(secret.encode(), proof.payload.encode(), "sha256").hexdigest()
    if not hmac.compare_digest(expected, proof.signature):
        raise HealthVisionError("source_proof_invalid", "来源凭据无效", 403)
    try:
        source = json.loads(proof.payload)
        user = await UserRepository().get_by_uid(source["uid"])
        if user is None or user.is_deleted or user.is_login_locked() or not user.department_id:
            raise HealthVisionError("source_invalidated", "餐单采购账号当前不可用", 410)
        if source.get("kind") == "service_plan":
            from yuxi.services.exclusive_plan_tasks import validate_exclusive_source

            await validate_exclusive_source(source)
            return {"available": True}
        if source.get("kind") in {"conversation_package", "conversation_catalog"}:
            from yuxi.services.conversation_purchase_service import validate_conversation_source

            async with pg_manager.get_async_session_context() as session:
                return await validate_conversation_source(session, source)
        if source.get("kind") == "reference_plan":
            from yuxi.services.reference_meal_plan_service import validate_reference_purchase_source

            async with pg_manager.get_async_session_context() as session:
                return await validate_reference_purchase_source(session, source)
        if source.get("kind") == "daily_arrangement":
            from yuxi.services.daily_arrangement_service import validate_daily_commerce_source

            authority = await validate_daily_commerce_source(source)
            return {"available": True, **({"purchase_authority": authority} if authority else {})}
        _, mappings = require_commerce_configuration()
        selected = PurchaseSelection.model_validate(source["selection"])
        current = await purchase_requirements(source["uid"], source["member_id"], selected)
        if source["source_hash"] != current["source_hash"] or source["mapping_hash"] != input_fingerprint(
            [row.model_dump(mode="json") for row in mappings]
        ):
            raise HealthVisionError("source_invalidated", "采用来源或采购换算已变化", 410)
        convert_requirements(current, mappings)
    except (KeyError, TypeError, ValueError, ValidationError):
        raise HealthVisionError("source_proof_invalid", "来源凭据无效", 403) from None
    return {"available": True}


def sign_commerce_source(source):
    """签名仅包含服务器来源标识和摘要，商城回源核对后才能结算。"""
    secret = os.environ.get("HEALTH_COMMERCE_SOURCE_SECRET", "")
    if len(secret) < 32:
        raise HealthVisionError("commerce_unavailable", "餐单来源校验服务未就绪", 503)
    raw = json.dumps(source, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return {"payload": raw, "signature": hmac.new(secret.encode(), raw.encode(), "sha256").hexdigest()}

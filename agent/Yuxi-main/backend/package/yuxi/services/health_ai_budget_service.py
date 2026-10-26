"""五类健康 AI 共用的人民币月预算与供应商调用账本。"""

import hashlib
import os
from dataclasses import dataclass, field, replace
from datetime import UTC
from decimal import Decimal
from uuid import uuid4
from zoneinfo import ZoneInfo

from yuxi.models.providers.cache import model_cache
from yuxi.repositories.health_ai_budget_repository import HealthAiBudgetRepository
from yuxi.services.health_ai_budget_types import (
    HEALTH_BUDGET_PURPOSES,
    MONTHLY_LIMIT_CNY,
    HealthAiPriceInput,
    round_charge,
)
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.services.health_vision_usage import normalize_token_usage
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_health_budget import HealthAiCall, HealthAiMonth, HealthAiOpening, HealthAiPrice


@dataclass(frozen=True)
class BudgetReservation:
    """严格模式绑定已提交预留；参考模式不虚构价格和费用记录。"""

    call_id: str | None
    price: HealthAiPriceInput | None
    model_info: object = field(default=None, repr=False)


async def approve_price(uid: str, data: HealthAiPriceInput):
    """仅管理路由调用；核验价格目标并追加版本，不重置月占用。"""
    from yuxi.services.health_vision_service import current_health_model_info
    from yuxi.services.ocr_service import resolve_ocr_task_params

    if data.kind == "model":
        async with pg_manager.get_async_session_context() as session:
            info = await current_health_model_info(session, data.model_spec)
        target = model_target(info)
    else:
        from yuxi.knowledge.parser.paddleocr_api import DEFAULT_PADDLEOCR_API_URL

        params = (await resolve_ocr_task_params({"ocr_engine": "paddleocr_vl_1_6"}))["_ocr_processor_kwargs"]
        endpoint = (params.get("api_url") or DEFAULT_PADDLEOCR_API_URL).rstrip("/")
        if data.ocr_endpoint.rstrip("/") != endpoint or not params.get("api_token"):
            raise HealthVisionError("budget_price_unavailable", "OCR 价格须绑定当前处理配置", 409)
        target = ocr_target(endpoint, params["api_token"])
    async with pg_manager.get_async_session_context() as session:
        repo = HealthAiBudgetRepository(session)
        await repo.lock()
        now = await repo.now()
        until = data.valid_until.astimezone(UTC).replace(tzinfo=None)
        if until <= now:
            raise HealthVisionError("budget_price_unavailable", "价格批准已过期", 422)
        for old in await repo.prices(target):
            old.enabled = False
        record = HealthAiPrice(
            id=str(uuid4()),
            target=target,
            kind=data.kind,
            specification=data.model_dump(mode="json"),
            approved_by=uid,
            approved_at=now,
            valid_until=until,
        )
        session.add(record)
    return {"id": record.id, "currency": "CNY", "ceiling_cny": str(data.ceiling_cny), "valid_until": data.valid_until}


async def reserve(purpose: str, owner_id: str, target: str, *, call_id: str | None = None) -> BudgetReservation:
    """提交全项目预留后才允许外呼，数据库不可用时不降级。"""
    if purpose not in HEALTH_BUDGET_PURPOSES or not owner_id or len(owner_id) > 64:
        raise HealthVisionError("budget_context_invalid", "健康预算调用归属无效", 422)
    advisory = budget_mode() == "advisory" and purpose in {"consultation", "indicator_review", "diet_analysis"}
    call_id = call_id or str(uuid4())
    async with pg_manager.get_async_session_context() as session:
        repo = HealthAiBudgetRepository(session)
        await repo.lock()
        if await repo.call(call_id) is not None:
            raise HealthVisionError("budget_call_replayed", "此调用已预留，不能再次发送供应商请求", 409)
        now = await repo.now()
        if advisory:
            month = budget_month(now)
            account = await repo.month(month)
            if account is None:
                session.add(HealthAiMonth(month=month, occupied_cny=Decimal(0), blocked=True))
            else:
                account.blocked = True
            # 记录严格账本已不完整，切回严格模式时不能沿用旧余额放行。
            return BudgetReservation(None, None)
        row = await repo.price(target, now)
        if row is None:
            raise HealthVisionError("budget_price_unavailable", "计费依据或费用上界未就绪，可使用人工录入", 503)
        price = HealthAiPriceInput.model_validate(row.specification)
        month = budget_month(now)
        opening = await repo.opening()
        if opening is None or month < opening.month:
            raise HealthVisionError("budget_price_unavailable", "启用当月的既有费用尚未核对，可使用人工录入", 503)
        account = await repo.month(month)
        if account is None:
            account = HealthAiMonth(month=month, occupied_cny=Decimal(0), blocked=False)
            session.add(account)
            await session.flush()
        if account.blocked or account.occupied_cny + price.ceiling_cny > MONTHLY_LIMIT_CNY:
            raise HealthVisionError("budget_exceeded", "健康 AI 本月剩余额度不足或待核账，可使用人工录入", 429)
        account.occupied_cny += price.ceiling_cny
        session.add(
            HealthAiCall(
                id=call_id,
                month=month,
                price_id=row.id,
                purpose=purpose,
                owner_id=owner_id,
                reserved_cny=price.ceiling_cny,
                created_at=now,
            )
        )
    return BudgetReservation(call_id, price)


async def settle(reservation: BudgetReservation, usage=None, *, fixed_charge: bool = False):
    """完整回执按原批准价格结算；未知与超界保留全部占用。"""
    if reservation.call_id is None:
        # 参考模式的用量由Run模型审计及识图任务回执持久化，人民币金额保持未知。
        return
    async with pg_manager.get_async_session_context() as session:
        repo = HealthAiBudgetRepository(session)
        await repo.lock()
        call = await repo.call(reservation.call_id)
        if call is None:
            raise HealthVisionError("budget_context_invalid", "费用预留不存在", 409)
        if call.status != "reserved":
            return
        # 结算只信数据库中当次价格，调用方不能降低预留或改换单价。
        price_row = await session.get(HealthAiPrice, call.price_id)
        price = HealthAiPriceInput.model_validate(price_row.specification)
        account = await repo.month(call.month)
        tokens = normalize_token_usage(usage)
        amount = None
        if fixed_charge and price.kind == "ocr":
            amount = price.fixed_cny_per_page
        elif tokens is not None and price.kind == "model":
            call.input_tokens, call.output_tokens = tokens["input_tokens"], tokens["output_tokens"]
            if call.input_tokens > price.max_input_tokens or call.output_tokens > price.max_output_tokens:
                account.blocked, price_row.enabled = True, False
            else:
                amount = round_charge(
                    (
                        call.input_tokens * price.input_cny_per_million
                        + call.output_tokens * price.output_cny_per_million
                    )
                    / 1000000
                )
        call.status = "unknown" if amount is None else "settled"
        call.finished_at = await repo.now()
        if amount is not None:
            call.charged_cny = amount
            account.occupied_cny -= call.reserved_cny - amount


async def budget_status():
    """管理员读取完整月占用与最近调用，不暴露健康正文或凭据。"""
    mode = budget_mode()
    async with pg_manager.get_async_session_context() as session:
        repo = HealthAiBudgetRepository(session)
        await repo.lock()
        month = budget_month(await repo.now())
        account = await repo.month(month)
        occupied = account.occupied_cny if account else Decimal(0)
        opening = await repo.opening()
        amounts_known = mode == "strict" and opening is not None and not (account and account.blocked)
        return {
            "month": str(month),
            "timezone": "Asia/Shanghai",
            "currency": "CNY",
            "mode": mode,
            "advisory_purposes": ["consultation", "indicator_review", "diet_analysis"] if mode == "advisory" else [],
            "reference_budget_cny": str(MONTHLY_LIMIT_CNY),
            "limit_cny": str(MONTHLY_LIMIT_CNY) if mode == "strict" else None,
            "occupied_cny": str(occupied) if amounts_known else None,
            "remaining_cny": str(MONTHLY_LIMIT_CNY - occupied) if amounts_known else None,
            "blocked": mode == "strict" and bool(account and account.blocked),
            "usage_source": "agent_run_model_audit_and_vision_task_receipts",
            "initialized": opening is not None,
            "calls": [
                {
                    "id": c.id,
                    "purpose": c.purpose,
                    "owner_id": c.owner_id,
                    "status": c.status,
                    "reserved_cny": str(c.reserved_cny),
                    "charged_cny": str(c.charged_cny) if c.charged_cny is not None else None,
                }
                for c in await repo.calls(month)
            ],
        }


async def initialize_budget(uid, data):
    """锁内一次性确认期初占用，同内容重放不重置额度。"""
    async with pg_manager.get_async_session_context() as session:
        repo = HealthAiBudgetRepository(session)
        await repo.lock()
        opening = await repo.opening()
        if opening is not None:
            if opening.occupied_cny != data.occupied_cny or opening.evidence != data.evidence:
                raise HealthVisionError("budget_opening_conflict", "预算期初已确认，不能覆盖或清零", 409)
            return {"month": str(opening.month), "occupied_cny": str(opening.occupied_cny)}
        month = budget_month(await repo.now())
        if await repo.month(month) is not None:
            raise HealthVisionError("budget_opening_conflict", "当月已有调用或待核账记录，不能用期初覆盖", 409)
        session.add(
            HealthAiOpening(id=1, month=month, occupied_cny=data.occupied_cny, evidence=data.evidence, approved_by=uid)
        )
        session.add(HealthAiMonth(month=month, occupied_cny=data.occupied_cny, blocked=False))
    return {"month": str(month), "occupied_cny": str(data.occupied_cny)}


def model_target(info) -> str:
    """凭据、端点或可覆盖请求参数变化均使旧价格失效。"""
    from yuxi.services.health_vision_service import processor_identity

    if (
        info is None
        or not info.api_key
        or info.provider_type not in {"openai", "openrouter"}
        or (
            info.request_body_overrides
            and not (
                info.provider_type == "openai"
                and info.model_id == "deepseek-flash"
                and info.base_url.rstrip("/") in {"https://api.deepseek.com", "https://api.deepseek.com/v1"}
                and info.request_body_overrides == {"thinking": {"type": "disabled"}}
            )
        )
    ):
        raise HealthVisionError("budget_price_unavailable", "模型计费配置未就绪或存在请求覆盖", 503)
    return hashlib.sha256((processor_identity("meal", info) + ":" + info.api_key).encode()).hexdigest()


def ocr_target(endpoint: str, token: str) -> str:
    """OCR 单页价格绑定端点和实际计费账号。"""
    return hashlib.sha256(("ocr:" + endpoint.rstrip("/") + ":" + token).encode()).hexdigest()


def budget_month(utc_time):
    """按预留时刻的北京时间自然月归账，迟到结算仍使用原月份。"""
    return utc_time.replace(tzinfo=UTC).astimezone(ZoneInfo("Asia/Shanghai")).date().replace(day=1)


async def model_budget_readiness(session, info):
    """只读核对模型目标、有效价格、期初与当前月余量，不创建预留。"""
    try:
        target = model_target(info)
    except HealthVisionError:
        return {
            "available": False,
            "reason_code": "budget_price_unavailable",
            "reason": "模型计费参数尚未就绪，请联系管理员",
        }
    if budget_mode() == "advisory":
        return {"available": True, "reason_code": None, "reason": None}
    repo = HealthAiBudgetRepository(session)
    now = await repo.now()
    record = await repo.price(target, now)
    if record is None:
        return {
            "available": False,
            "reason_code": "budget_price_unavailable",
            "reason": "模型价格或费用上界尚未配置，请联系管理员",
        }
    opening = await repo.opening()
    if opening is None or budget_month(now) < opening.month:
        return {
            "available": False,
            "reason_code": "budget_price_unavailable",
            "reason": "本月预算期初尚未核对，请联系管理员",
        }
    price = HealthAiPriceInput.model_validate(record.specification)
    account = await repo.month(budget_month(now))
    occupied = account.occupied_cny if account else Decimal(0)
    if (account and account.blocked) or occupied + price.ceiling_cny > MONTHLY_LIMIT_CNY:
        return {
            "available": False,
            "reason_code": "budget_exceeded",
            "reason": "本月健康 AI 可用额度不足或待核账，请稍后再试",
        }
    return {"available": True, "reason_code": None, "reason": None}


async def reserve_model(purpose: str, owner_id: str, spec: str) -> BudgetReservation:
    """绑定模型快照，严格模式在外呼前核对价格与额度。"""
    info = model_cache.get_model_info(spec)
    reservation = await reserve(purpose, owner_id, model_target(info))
    return replace(reservation, model_info=info)


def reserved_chat_model(reservation: BudgetReservation, **kwargs):
    """核对预留配置后同步构造固定实例，不能将旧价格应用于新端点。"""
    from yuxi.models.chat import load_chat_model_from_info

    info = reservation.model_info
    if info is None or model_cache.get_model_info(info.spec) != info:
        raise HealthVisionError("policy_changed", "预算等待期间模型配置已变化，请重新提交", 409)
    max_tokens = reservation.price.max_output_tokens if reservation.price is not None else 2048
    return load_chat_model_from_info(info, **kwargs, max_retries=0, max_tokens=max_tokens)


def budget_mode() -> str:
    """只有显式参考模式可放宽金额门槛，配置错误不得自动放行。"""
    mode = os.getenv("HEALTH_AI_BUDGET_MODE", "strict")
    if mode not in {"strict", "advisory"}:
        raise ValueError("HEALTH_AI_BUDGET_MODE 必须为 strict 或 advisory")
    return mode

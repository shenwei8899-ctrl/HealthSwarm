"""北京时间每日入口、可追溯日终消息摘录及自动补跑。"""

import hashlib
import json
from datetime import UTC, datetime, timedelta, timezone

from yuxi.repositories.health_consultation_repository import HealthConsultationRepository
from yuxi.repositories.health_daily_repository import HealthDailyRepository
from yuxi.repositories.health_vision_repository import HealthVisionRepository
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.storage.postgres.manager import pg_manager
from yuxi.utils.datetime_utils import format_utc_datetime, utc_now_naive
from yuxi.utils.logging_config import logger


def business_date(now=None):
    """服务器按北京时间零点切分；朴素时间按既有 UTC 存储解释。"""
    now = now or datetime.now(UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    return now.astimezone(timezone(timedelta(hours=8))).date()


async def require_current_day(session, uid, thread_id):
    """历史每日会话只读；旧请求重放在接入层此前已返回。"""
    daily = await HealthDailyRepository(session).for_thread(uid, thread_id)
    if daily is not None and daily.business_date != business_date():
        raise HealthVisionError("daily_conversation_closed", "该日对话已归档，请进入今天的营养咨询", 409)


async def daily_history(uid, member_id, before=None):
    """日期列表不泄露摘要正文；正文独立检查当前来源。"""
    async with pg_manager.get_async_session_context() as session:
        health = HealthVisionRepository(session)
        for scope in ("ai_use", "report_view", "diet_edit"):
            await health.authorize(member_id, uid, scope)
        rows = await HealthDailyRepository(session).history(uid, member_id, before)
        return {
            "days": [
                {
                    "date": day.business_date.isoformat(),
                    "thread_id": thread,
                    "summary_available": day.summary is not None,
                    "summary_version": day.summary_version,
                }
                for day, thread in rows
            ],
            "next_before": rows[-1][0].business_date.isoformat() if len(rows) == 30 else None,
        }


def message_digest(messages):
    """只摘要实际成功消息，来源与截断显式返回，不推导临床结论或餐单。"""
    rows = list(reversed(messages[:1000]))
    sources = [
        {
            "message_id": row.id,
            "request_id": row.request_id,
            "role": row.role,
            "content": row.content,
            "created_at": format_utc_datetime(row.created_at),
        }
        for row in rows
    ]
    fingerprint = hashlib.sha256(json.dumps(sources, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    excerpts = [
        {"message_id": row.id, "role": row.role, "excerpt": row.content[:300], "truncated": len(row.content) > 300}
        for row in rows
    ]
    return fingerprint, {
        "kind": "message_digest",
        "source_message_ids": [row.id for row in rows],
        "message_count": len(rows),
        "truncated": len(messages) > 1000,
        "excerpts": excerpts,
        "tomorrow_mentions": [
            item for row, item in zip(rows, excerpts) if row.role == "user" and "明天" in row.content
        ],
        "open_item_mentions": [
            item
            for row, item in zip(rows, excerpts)
            if row.role == "user" and any(word in row.content for word in ("还没", "未完成", "待处理"))
        ],
        "meal_plan_generated": False,
    }


async def daily_summary(uid, thread_id, *, refresh=False):
    """当前来源一致才展示摘要；补跑在同一 PG 事务发布唯一版本。"""
    async with pg_manager.get_async_session_context() as session:
        binding = await HealthConsultationRepository(session).authorize(uid, thread_id, lock=refresh)
        repo = HealthDailyRepository(session)
        daily = await repo.for_thread(uid, thread_id)
        if daily is None or daily.member_id != binding.member_id:
            raise HealthVisionError("not_found", "每日对话不存在或无权访问", 404)
        if daily.business_date >= business_date():
            if refresh:
                raise HealthVisionError("day_not_closed", "日终摘要在北京时间零点后生成", 409)
            return {"status": "day_open", "date": daily.business_date.isoformat(), "summary": None}
        messages = await repo.source_messages(daily, thread_id)
        if messages is None:
            return {"status": "waiting_for_requests", "date": daily.business_date.isoformat(), "summary": None}
        fingerprint, digest = message_digest(messages)
        if refresh:
            if daily.summary_fingerprint != fingerprint:
                daily.summary, daily.summary_fingerprint = digest, fingerprint
                daily.summary_version += 1
                daily.summary_generated_at = utc_now_naive()
            daily.summary_checked_at = utc_now_naive()
        if daily.summary_fingerprint != fingerprint:
            return {
                "status": "pending" if daily.summary is None else "stale",
                "date": daily.business_date.isoformat(),
                "summary": None,
            }
        return {
            "status": "ready",
            "date": daily.business_date.isoformat(),
            "version": daily.summary_version,
            "generated_at": format_utc_datetime(daily.summary_generated_at),
            "summary": daily.summary,
        }


async def summarize_closed_health_days(ctx):
    """worker 分钟扫描提供原子补跑；单日失败不阻断其他成员。"""
    async with pg_manager.get_async_session_context() as session:
        rows = await HealthDailyRepository(session).due(business_date())
        due = [(day.actor_uid, thread) for day, thread in rows]
        for day, _ in rows:
            day.summary_checked_at = utc_now_naive()
    for uid, thread in due:
        try:
            await daily_summary(uid, thread, refresh=True)
        except HealthVisionError:
            # 撤权及已删除会话不读取私有正文；下一轮仍重查授权。
            continue
        except Exception:
            logger.error("健康日终摘要生成失败，等待下一轮补跑", exc_info=False)

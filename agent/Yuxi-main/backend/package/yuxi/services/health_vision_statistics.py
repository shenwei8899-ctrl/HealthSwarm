"""成员识图统计从持久事实派生，不报告模型准确率或猜测费用。"""

from collections import Counter
from datetime import timedelta
from math import ceil

from yuxi.repositories.health_vision_repository import HealthVisionRepository
from yuxi.storage.postgres.manager import pg_manager
from yuxi.utils.datetime_utils import format_utc_datetime, utc_now_naive


async def vision_statistics(uid: str, member_id: str, kind: str):
    """读取当前成员及用途的三十天摘要；与授权撤回共用成员锁。"""
    end = utc_now_naive()
    start = end - timedelta(days=30)
    async with pg_manager.get_async_session_context() as session:
        repo = HealthVisionRepository(session)
        await repo.authorize(member_id, uid, "report_view" if kind == "report" else "diet_edit", lock=True)
        tasks, reviews = await repo.statistics_sources(member_id, kind, start, end)
        return {
            "kind": kind,
            "window_start": format_utc_datetime(start),
            "window_end": format_utc_datetime(end),
            **summarize_vision_statistics(tasks, reviews, kind),
        }


def summarize_vision_statistics(tasks: list, reviews: list, kind: str) -> dict:
    """独立统计执行样本和确认样本，未知耗时与零分母保持为空。"""
    states, failures = Counter(), Counter()
    queue, execution = [], []
    partial = 0
    for task in tasks:
        states[task["status"]] += 1
        if task["status"] == "failed":
            failures[task["error_code"] or "task_failed"] += 1
        partial += task["status"] == "success" and task["phase"] == "partial_ready"
        created, started, completed = (task[key] for key in ("created_at", "started_at", "completed_at"))
        if created is not None and started is not None and started >= created:
            queue.append((started - created).total_seconds())
        if (
            task["status"] in {"success", "failed", "cancelled"}
            and started is not None
            and completed is not None
            and completed >= started
        ):
            execution.append((completed - started).total_seconds())

    original_count = modified = excluded = added = model_reviews = 0
    portions = Counter()
    meal_logs = incomplete_logs = 0
    for review in reviews:
        original, current = review["original_payload"], review["payload"]
        id_key, collection = ("field_id", "fields") if kind == "report" else ("item_id", "items")
        if review["job_id"] is not None:
            model_reviews += 1
            original_ids = {item[id_key] for item in original[collection]}
            originals = {
                item[id_key]: item for item in original[collection] if kind == "meal" or item["source"] == "ocr"
            }
            confirmed = {item[id_key]: item for item in current[collection]}
            original_count += len(originals)
            comparison_keys = (
                ("name", "observation_code", "value_raw", "unit_raw", "reference_raw")
                if kind == "report"
                else ("name",)
            )
            for item_id, before in originals.items():
                after = confirmed.get(item_id)
                page_excluded = (
                    kind == "report"
                    and after is not None
                    and after.get("evidence")
                    and after["evidence"]["page_index"] in current.get("excluded_pages", [])
                )
                if after is None or after.get("excluded") or page_excluded:
                    excluded += 1
                elif any(before.get(key) != after.get(key) for key in comparison_keys):
                    modified += 1
            added += sum(
                item_id not in original_ids and not item.get("excluded") for item_id, item in confirmed.items()
            )
        if kind == "meal" and review["snapshot"] is not None:
            snapshot = review["snapshot"]
            meal_logs += 1
            incomplete_logs += not snapshot["nutrition"]["complete"]
            portions.update(item["portion_source"] for item in snapshot["meal"]["items"] if not item["excluded"])

    def timing(values):
        """最近秩百分位同时给样本数；没有时间点不补零。"""
        values = sorted(values)
        return {
            "sample_count": len(values),
            "p50_seconds": round(values[ceil(len(values) * 0.5) - 1], 3) if values else None,
            "p95_seconds": round(values[ceil(len(values) * 0.95) - 1], 3) if values else None,
        }

    return {
        "tasks": {
            "sample_count": len(tasks),
            "states": dict(states),
            "failure_codes": dict(failures),
            "partial_report_count": partial,
            "queue": timing(queue),
            "execution": timing(execution),
        },
        "reviews": {
            "confirmed_drafts": len(reviews),
            "model_drafts": model_reviews,
            "original_items": original_count,
            "modified_items": modified,
            "excluded_items": excluded,
            "added_items": added,
            "modification_rate_percent": round(modified * 100 / original_count, 2) if original_count else None,
        },
        "nutrition": {
            "sample_count": meal_logs,
            "incomplete_count": incomplete_logs,
            "incomplete_rate_percent": round(incomplete_logs * 100 / meal_logs, 2) if meal_logs else None,
            "portion_sources": dict(portions),
        },
        "cost": {"amount": None, "reason": "缺少供应商计费账本及批准单价，费用未知"},
    }

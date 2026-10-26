"""逐日检查点与幂等导出，使用既有 Worker lease 保证旧执行者不能写回。"""

import asyncio
from copy import deepcopy
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select

from yuxi.repositories.exclusive_plan_repository import ExclusivePlanRepository
from yuxi.services.daily_commerce_service import commerce_request, current_catalog
from yuxi.services.daily_arrangement_projection import ingredient_requirements
from yuxi.services.exclusive_plan_generation import TIERS, content_hash, generate_exclusive_day
from yuxi.services.exclusive_plan_service import (
    exclusive_context,
    export_payload,
    queue_exclusive_in_session,
    read_plan_policy,
)
from yuxi.services.health_family_safe_plan_service import check_family_trial
from yuxi.services.health_family_meal_plan_types import FamilyMealPlanSpec
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.services.miniapp_profile_coding import prepare_daily_profile_coding
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_health import HealthExclusivePlanGroup
from yuxi.utils.datetime_utils import utc_now_naive


async def run_exclusive_plan(context):
    """恢复已有天序和导出回执，不覆盖另一尝试或已购买的商城快照。"""
    uid, fid, gid = (context.payload[key] for key in ("uid", "family_id", "group_id"))
    policy = await read_plan_policy()
    async with pg_manager.get_async_session_context() as session:
        row = await owned_group(session, context)
        initial = await exclusive_context(session, uid, fid, policy, allow_interpretation=True)
        assert_basis(row, initial)
    await prepare_daily_profile_coding(uid, initial["sources"], initial["selection"].model_dump(mode="json"), context)
    try:
        for tier in TIERS:
            for _ in range(21):
                await context.raise_if_cancelled()
                async with pg_manager.get_async_session_context() as session:
                    row = await owned_group(session, context)
                    previous = deepcopy(row.progress.get("tiers", {}).get(tier, []))
                    if len(previous) == 21:
                        break
                    day = date.fromisoformat(row.selection["plan_date"]) + timedelta(days=len(previous))
                    inputs = await exclusive_context(session, uid, fid, policy, day=day)
                    assert_basis(row, inputs)
                    validate_saved_days(inputs, previous)
                catalog = await current_catalog()
                generated = await asyncio.to_thread(
                    generate_exclusive_day,
                    inputs["selection"],
                    inputs["current"],
                    inputs["recipes"],
                    inputs["foods"],
                    inputs["refs"],
                    inputs["mappings"],
                    catalog,
                    policy,
                    tier,
                    previous,
                    gid,
                )

                async def save_day(session, _record):
                    """持有任务和推荐组行锁，写入前重验来源。"""
                    current_row = await owned_group(session, context, lock=True)
                    fresh = await exclusive_context(session, uid, fid, policy, day=day)
                    assert_basis(current_row, fresh)
                    validate_saved_days(fresh, [generated])
                    progress = deepcopy(current_row.progress)
                    saved = progress.setdefault("tiers", {}).setdefault(tier, [])
                    if len(saved) != len(previous):
                        raise HealthVisionError("exclusive_progress_conflict", "计划进度已变化，请恢复原任务", 409)
                    saved.append(generated)
                    current_row.progress, current_row.updated_at = progress, utc_now_naive()

                await context.run_owned_transaction(save_day)
                await context.set_progress(
                    (list(TIERS).index(tier) * 21 + len(previous) + 1) / 63 * 90, "正在准备三档餐单"
                )

        for tier in TIERS:
            await context.raise_if_cancelled()

            async def save_export(session, _record):
                """先落完整请求，商城回源验证和网络重试读取同一份内容。"""
                row = await owned_group(session, context, lock=True)
                fresh = await exclusive_context(session, uid, fid, policy)
                assert_basis(row, fresh)
                for entries in row.progress["tiers"].values():
                    validate_saved_days(fresh, entries)
                progress = deepcopy(row.progress)
                progress.setdefault("exports", {}).setdefault(tier, export_payload(row, tier))
                row.progress = progress

            await context.run_owned_transaction(save_export)
            async with pg_manager.get_async_session_context() as session:
                row = await owned_group(session, context)
                payload = deepcopy(row.progress["exports"][tier])
            receipt = await commerce_request(
                "POST", "/api/v1/integration/ai/service-plans", payload, request_id=f"exclusive:{gid}:{tier}"
            )
            if receipt.get("status") != "available":
                receipt = await commerce_request(
                    "POST",
                    f"/api/v1/integration/ai/service-plans/{receipt['plan_sn']}/trade-validate",
                    {"plan_version": receipt["plan_version"]},
                    request_id=f"xp:{gid}:{tier}:r:{context.payload['attempt']}",
                )
            if receipt.get("status") != "available":
                raise HealthVisionError(
                    "exclusive_trade_not_ready", "当前商品或费用尚未核对完成，已保留餐单，可稍后重试", 503
                )

            async def save_receipt(session, _record):
                """只记录商城正式返回的计划号和版本。"""
                row = await owned_group(session, context, lock=True)
                progress = deepcopy(row.progress)
                progress.setdefault("receipts", {})[tier] = {
                    key: receipt[key] for key in ("plan_sn", "plan_version", "tier_code")
                }
                row.progress, row.updated_at = progress, utc_now_naive()

            await context.run_owned_transaction(save_receipt)

        async def finish(session, _record):
            """三档全部可用且来源仍有效时才发布推荐组。"""
            row = await owned_group(session, context, lock=True)
            fresh = await exclusive_context(session, uid, fid, policy)
            assert_basis(row, fresh)
            for entries in row.progress["tiers"].values():
                validate_saved_days(fresh, entries)
            if set(row.progress["receipts"]) != set(TIERS):
                raise HealthVisionError("exclusive_incomplete", "三档计划尚未完整", 503)
            row.status, row.updated_at = "ready", utc_now_naive()

        await context.run_owned_transaction(finish)
        return {"group_id": gid, "status": "ready"}
    except HealthVisionError as error:
        public_error = {"code": error.code, "message": error.message, "retryable": error.status >= 500}

        async def save_error(session, _record):
            """只保存业务错误投影，完整已生成天序仍用于恢复。"""
            row = await owned_group(session, context, lock=True)
            row.status = "failed"
            row.progress = {
                **row.progress,
                "error": public_error,
            }
            row.updated_at = utc_now_naive()

        await context.run_owned_transaction(save_error)
        raise


async def validate_exclusive_source(source):
    """签名校验后，回读准确推荐组和全部当前授权、食谱、配料及规则。"""
    async with pg_manager.get_async_session_context() as session:
        repo = ExclusivePlanRepository(session, source["uid"], source["family_id"])
        await repo.context()
        row = await repo.find(group_id=source["group_id"])
        tier = source["tier_code"]
        exported = row.progress.get("exports", {}).get(tier)
        if (
            not exported
            or source.get("plan_version") != 1
            or content_hash(exported) != source.get("content_hash")
            or row.basis_hash != source.get("basis_hash")
            or row.policy["version"] != source.get("policy_version")
        ):
            raise HealthVisionError("source_invalidated", "计划来源与所选版本不一致", 410)
        fresh = await exclusive_context(session, row.actor_uid, row.family_id, row.policy)
        assert_basis(row, fresh)
        entries = row.progress.get("tiers", {}).get(tier, [])
        if len(entries) != 21:
            raise HealthVisionError("source_invalidated", "计划尚未包含完整21天三餐", 410)
        validate_saved_days(fresh, entries)


async def fail_exclusive_plan(session, task_record, error):
    """失联最多自动恢复两次，其余失败保留进度供用户明确重试。"""
    payload = task_record.payload
    row = await session.scalar(
        select(HealthExclusivePlanGroup)
        .where(HealthExclusivePlanGroup.id == payload["group_id"], HealthExclusivePlanGroup.actor_uid == payload["uid"])
        .with_for_update()
    )
    if row is None or row.status != "generating" or row.attempt != payload["attempt"]:
        return
    count = row.progress.get("recovery_count", 0)
    if error.startswith(("worker_lease_expired:", "worker_shutdown:")) and count < 2:
        row.attempt += 1
        row.progress = {**row.progress, "recovery_count": count + 1}
        await queue_exclusive_in_session(session, row)
    else:
        row.status = "failed"
        row.progress = {
            **row.progress,
            "error": {
                "code": "exclusive_task_failed",
                "message": "计划暂未准备完成，已有进度已保留",
                "retryable": True,
            },
        }
    row.updated_at = utc_now_naive()


async def owned_group(session, context, *, lock=False):
    """领域版本与任务 attempt 一起拒绝旧执行者。"""
    payload = context.payload
    repo = ExclusivePlanRepository(session, payload["uid"], payload["family_id"])
    await repo.context(lock=True)
    row = await repo.find(group_id=payload["group_id"], lock=lock)
    if row.attempt != payload["attempt"] or row.status != "generating":
        raise HealthVisionError("exclusive_attempt_changed", "计划任务已更新", 409)
    return row


def assert_basis(row, context):
    """相关档案或规则变化必须重新准备，不能混入旧三档结果。"""
    if row.basis_hash != context["basis_hash"]:
        raise HealthVisionError("exclusive_sources_changed", "档案或规则已变化，请重新准备专属计划", 409)


def validate_saved_days(context, entries):
    """来源变化后不靠旧 passed 字段放行；重新验证保存菜单。"""
    for entry in entries:
        used = entry["candidate_sources"]["recipes"]
        if any(context["refs"].get(rid) != saved for rid, saved in used.items()):
            raise HealthVisionError("source_invalidated", "计划使用的审核食谱已变化", 410)
        spec = FamilyMealPlanSpec.model_validate(entry["spec"])
        check, sources = check_family_trial(
            context["current"], spec, entry["snapshot"], context["foods"], context["refs"]
        )
        if check["status"] != "passed" or sources != entry["candidate_sources"]:
            raise HealthVisionError("source_invalidated", "计划的饮食限制或配料来源已变化", 410)
        for meal in entry["day"]["meals"]:
            rid = meal["recipe_version_ref"]
            mapping = context["mappings"].get(rid)
            if mapping is None or mapping.recipe_hash != context["refs"][rid] or not mapping.steps:
                raise HealthVisionError("source_invalidated", "计划的食谱采购映射已变化", 410)
        # 映射编号不能依靠菜名重建；逐餐重新合并明确编码并比较。
        for meal_type in ("breakfast", "lunch", "dinner"):
            actual = ingredient_requirements(entry["snapshot"], context["mappings"], meal_type)
            expected = {}
            for meal in entry["day"]["meals"]:
                if meal["meal_type"] == meal_type:
                    for ingredient in meal["ingredient_requirements"]:
                        code = ingredient["ingredient_code"]
                        expected[code] = expected.get(code, Decimal(0)) + Decimal(ingredient["required_value"])
            if {item["ingredient_code"]: Decimal(item["required_value"]) for item in actual} != expected:
                raise HealthVisionError("source_invalidated", "计划配料的采购编码已变化", 410)

"""建档准备：原子登记、后台衔接及现有每日结果的授权投影。"""

from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert

from yuxi.repositories.daily_arrangement_repository import DailyArrangementRepository
from yuxi.services.family_service import FamilyService, guardian_active
from yuxi.services.health_daily_service import business_date
from yuxi.services.health_nutrition_service import input_fingerprint
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.services.miniapp_profile_service import save_miniapp_profile_in_session
from yuxi.services.miniapp_profile_types import MiniappProfileInput, miniapp_profile_complete
from yuxi.services.task_service import tasker
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_health import (
    HealthGrant,
    HealthOnboardingPreparation,
    HealthProcessingConsent,
)
from yuxi.utils.datetime_utils import utc_now_naive


class OnboardingPreparationInput(MiniappProfileInput):
    """原表单与本次按钮明确接受的咨询、配餐处理说明。"""

    processing_consents: list[dict[str, str]] = Field(default_factory=list, max_length=2)


class SavedPreparationInput(BaseModel):
    """只引用当前服务端档案，不允许客户端再次提交或覆盖资料。"""

    model_config = ConfigDict(extra="forbid")
    client_request_id: UUID


async def start_saved_preparation(uid, fid, data):
    """老账号、跨天和改档案后从已保存来源准备，重复进入复用同日任务。"""
    from yuxi.services.health_vision_service import health_vision_service

    digest = input_fingerprint({"action": "prepare_saved", "request_id": str(data.client_request_id)})
    async with pg_manager.get_async_session_context() as db:
        service = FamilyService(db, uid)
        family, _ = await service.context(fid)
        await db.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
            {"key": f"onboarding-request:{uid}:{data.client_request_id}"},
        )
        await lock_preparation(db, uid, fid)
        row = await db.scalar(
            select(HealthOnboardingPreparation).where(
                HealthOnboardingPreparation.actor_uid == uid,
                HealthOnboardingPreparation.request_id == str(data.client_request_id),
            )
        )
        task = None
        if row is not None:
            if row.family_id != fid or row.fingerprint != digest:
                raise HealthVisionError("request_conflict", "同一准备请求不能改变家庭或操作", 409)
        else:
            actor = await service.repo.subject_member(fid, uid)
            if not miniapp_profile_complete(actor):
                raise HealthVisionError("profile_incomplete", "请补充本人档案后继续准备", 422)
            sources = await preparation_sources(service, family)
            latest = await latest_preparation(db, uid, fid)
            if latest is not None and latest.sources == sources and latest.plan_date == business_date():
                # 每个请求键都留下固定引用；响应丢失后不能随来源变化改指向新任务。
                row = HealthOnboardingPreparation(
                    id=str(uuid4()),
                    actor_uid=uid,
                    family_id=fid,
                    request_id=str(data.client_request_id),
                    fingerprint=digest,
                    plan_date=latest.plan_date,
                    sources=latest.sources,
                    consents=latest.consents,
                    result={"reused_preparation_id": latest.id},
                    status="alias",
                )
                db.add(row)
                await db.flush()
            else:
                config = await health_vision_service.configuration(db)
                consents = [
                    {
                        "purpose": purpose,
                        "processor": config[purpose]["processor"],
                        "policy_version": config["policy_version"],
                    }
                    for purpose in ("consultation", "meal_plan")
                    if config[purpose].get("available") and config[purpose].get("processor")
                ]
                # 沿用已批准的本人自动衔接；不改档案内容、版本或他人默认就餐设置。
                actor.confirmed_version, actor.confirmed_at = actor.version, utc_now_naive()
                row = HealthOnboardingPreparation(
                    id=str(uuid4()),
                    actor_uid=uid,
                    family_id=fid,
                    request_id=str(data.client_request_id),
                    fingerprint=digest,
                    plan_date=business_date(),
                    sources=sources,
                    consents=consents,
                    result={},
                    status="pending",
                )
                db.add(row)
                await db.flush()
                task = await queue_preparation(db, row)
        pid = row.id
    if task is not None:
        await tasker.publish(task)
    return await read_onboarding_preparation(uid, fid, pid)


async def start_onboarding_preparation(uid, fid, data):
    """保存、收据与后台任务同事务提交，重放不重复保存或启动。"""
    digest = input_fingerprint(data.model_dump(mode="json"))
    async with pg_manager.get_async_session_context() as db:
        service = FamilyService(db, uid)
        family, _ = await service.context(fid)
        await db.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
            {"key": f"onboarding-request:{uid}:{data.client_request_id}"},
        )
        await lock_preparation(db, uid, fid)
        row = await db.scalar(
            select(HealthOnboardingPreparation).where(
                HealthOnboardingPreparation.actor_uid == uid,
                HealthOnboardingPreparation.request_id == str(data.client_request_id),
            )
        )
        if row is not None:
            if row.family_id != fid or row.fingerprint != digest:
                raise HealthVisionError("request_conflict", "同一准备请求不能改变建档内容", 409)
            task = None
        else:
            # 另一设备连点的新键也复用同一份已保存来源；不同资料仍走原版本校验。
            latest = await latest_preparation(db, uid, fid)
            body = MiniappProfileInput.model_validate(data.model_dump(exclude={"processing_consents"}))
            if latest is not None and latest.fingerprint == digest:
                row, task = latest, None
            else:
                saved = await save_miniapp_profile_in_session(db, uid, fid, body)
                family, _ = await service.context(fid)
                sources = await preparation_sources(service, family)
                latest = await latest_preparation(db, uid, fid)
                if latest is not None and latest.sources == sources and latest.plan_date == business_date():
                    # 新键也固定首次复用目标，响应丢失后的重放不能改指向新来源。
                    row = HealthOnboardingPreparation(
                        id=str(uuid4()),
                        actor_uid=uid,
                        family_id=fid,
                        request_id=str(data.client_request_id),
                        fingerprint=digest,
                        plan_date=latest.plan_date,
                        sources=latest.sources,
                        consents=latest.consents,
                        result={"reused_preparation_id": latest.id},
                        status="alias",
                    )
                    db.add(row)
                    await db.flush()
                    task = None
                else:
                    row = HealthOnboardingPreparation(
                        id=str(uuid4()),
                        actor_uid=uid,
                        family_id=fid,
                        request_id=str(data.client_request_id),
                        fingerprint=digest,
                        plan_date=business_date(),
                        sources=sources,
                        consents=data.processing_consents,
                        result={},
                        status="pending",
                    )
                    db.add(row)
                    await db.flush()
                    task = await queue_preparation(db, row)
                assert saved["completeProfile"] or saved["onboarded"]
        pid = row.id
    if task is not None:
        await tasker.publish(task)
    return await read_onboarding_preparation(uid, fid, pid)


async def read_onboarding_preparation(uid, fid, preparation_id=None):
    """只读真实状态；完成结果重新校验权限、日期和档案版本。"""
    from yuxi.services.daily_arrangement_service import read_daily_arrangement
    from yuxi.services.health_consultation_service import require_consultation

    async with pg_manager.get_async_session_context() as db:
        service = FamilyService(db, uid)
        family, _ = await service.context(fid)
        row = (
            await require_preparation(db, uid, fid, preparation_id)
            if preparation_id
            else await latest_preparation(db, uid, fid)
        )
        if row is None:
            return {"status": "absent"}
        base = {
            "id": row.id,
            "request_id": row.request_id,
            "date": row.plan_date.isoformat(),
            "profile_saved": True,
            "stage": "analyzing",
            "status": "preparing",
            "retryable": True,
            "thread_id": row.result.get("thread_id"),
            "message": "",
        }
        if row.plan_date != business_date():
            return {
                **base,
                "status": "stale",
                "retryable": True,
                "error_code": "preparation_date_changed",
                "message": "日期已更新，将读取已保存档案为今天继续准备。",
            }
        if row.sources != await preparation_sources(service, family):
            return {
                **base,
                "status": "stale",
                "retryable": True,
                "error_code": "preparation_sources_changed",
                "message": "档案或就餐成员已更新，请核对最新资料后重新准备。",
            }
        if row.status == "failed":
            return {
                **base,
                "status": "failed",
                "retryable": row.error_code
                not in {
                    "processing_consent_revoked",
                    "preparation_policy_changed",
                    "preparation_sources_changed",
                    "daily_member_sources_unavailable",
                    "daily_member_consent_required",
                },
                "error_code": row.error_code,
                "message": row.error_message,
            }
        if not row.result.get("thread_id"):
            return base
        try:
            await require_consultation(db, uid, row.result["thread_id"])
        except HealthVisionError as error:
            return {
                **base,
                "status": "blocked",
                "retryable": False,
                "error_code": error.code,
                "message": error.message,
            }
        _, daily = await DailyArrangementRepository(db, uid, fid).context(row.plan_date)
        if daily is None:
            return base
        phase = daily.selection.get("preparation_stage", "analyzing")
        base["stage"] = phase if phase in {"analyzing", "arranging"} else "arranging"
        if daily.status == "failed":
            return {
                **base,
                "status": "failed",
                "stage": base["stage"],
                "error_code": "daily_preparation_failed",
                "message": daily.selection.get("failure_message", "今日安排暂未完成，请继续准备。"),
            }
        day, expected = row.plan_date, dict(row.result)
    try:
        arrangement = await read_daily_arrangement(uid, fid, day)
    except HealthVisionError as error:
        return {
            **base,
            "status": "blocked",
            "retryable": error.status >= 500,
            "error_code": error.code,
            "message": error.message,
        }
    if arrangement["status"] == "stale":
        return {
            **base,
            "status": "stale",
            "retryable": True,
            "message": "安排来源已变化，请核对档案后重新准备。",
        }
    if arrangement["status"] == "ready" and arrangement.get("saved") and arrangement.get("analysis", {}).get("text"):
        if not prepared_arrangement_complete(arrangement, day.isoformat()):
            return {
                **base,
                "status": "blocked",
                "retryable": False,
                "error_code": "preparation_result_incomplete",
                "message": "三餐详情尚未完整保存，请核对原安排。",
            }
        if expected.get("arrangement_id") and arrangement["id"] != expected["arrangement_id"]:
            raise HealthVisionError("preparation_result_changed", "准备结果已更新，请重新读取", 409)
        return {
            **base,
            "status": "ready",
            "stage": "ready",
            "retryable": False,
            "arrangement": arrangement,
        }
    return base


async def resume_onboarding_preparation(uid, fid, preparation_id):
    """显式继续失败阶段；已保存档案和有效模型结果不重复生成。"""
    from yuxi.services.daily_arrangement_tasks import request_daily_resume

    async with pg_manager.get_async_session_context() as db:
        service = FamilyService(db, uid)
        family, _ = await service.context(fid)
        await lock_preparation(db, uid, fid)
        row = await require_preparation(db, uid, fid, preparation_id)
        if row.sources != await preparation_sources(service, family):
            raise HealthVisionError(
                "preparation_sources_changed",
                "档案已更新，请核对最新资料后重新准备",
                409,
            )
        if row.plan_date != business_date():
            raise HealthVisionError("preparation_date_changed", "日期已更新，请读取当前准备", 409)
        if row.status == "failed":
            from yuxi.services.health_vision_service import health_vision_service

            config = await health_vision_service.configuration(db)
            row.consents = [
                {
                    "purpose": purpose,
                    "processor": config[purpose]["processor"],
                    "policy_version": config["policy_version"],
                }
                for purpose in ("consultation", "meal_plan")
                if config[purpose].get("available") and config[purpose].get("processor")
            ]
            row.attempt += 1
            row.status, row.error_code, row.error_message = "pending", None, None
            task = await queue_preparation(db, row)
        else:
            task = None
        day, waiting = row.plan_date, row.status in {"waiting", "ready"}
    if task is not None:
        await tasker.publish(task)
    elif waiting:
        await request_daily_resume(uid, fid, day, retry_failed=True)
    return await read_onboarding_preparation(uid, fid, preparation_id)


async def run_onboarding_preparation(context):
    """短任务衔接档案来源、每日会话和现有配餐任务，不等待子任务。"""
    from types import SimpleNamespace
    from yuxi.services.daily_arrangement_service import start_daily_arrangement
    from yuxi.services.health_consultation_service import create_daily_consultation
    from yuxi.services.miniapp_planning_source import bind_submitted_profile
    from yuxi.services.health_vision_service import health_vision_service

    payload = context.payload
    uid, fid, pid = payload["uid"], payload["family_id"], payload["preparation_id"]
    health_id = None

    async def bind(session, _task_record):
        """在当前任务租约内核对来源与本次用途说明。"""
        nonlocal health_id
        row = await require_preparation(session, uid, fid, pid)
        if row.attempt != payload["attempt"]:
            return
        service = FamilyService(session, uid)
        family, _ = await service.context(fid)
        if row.sources != await preparation_sources(service, family) or row.plan_date != business_date():
            raise HealthVisionError("preparation_sources_changed", "资料或日期已变化，请重新核对", 409)
        config = await health_vision_service.configuration(session)
        supplied = {item.get("purpose"): item for item in row.consents}
        members = await service.repo.members(fid)
        permitted = [m for m in members if m.subject_uid == uid or guardian_active(m, uid)]
        for purpose in ("consultation", "meal_plan"):
            configured = config[purpose]
            expected = {
                "purpose": purpose,
                "processor": configured["processor"],
                "policy_version": config["policy_version"],
            }
            if not configured["available"]:
                raise HealthVisionError(
                    "daily_dependencies_not_ready",
                    configured.get("reason") or "咨询或配餐服务暂未配置完成，档案已保存",
                    503,
                )
            if supplied.get(purpose) != expected:
                raise HealthVisionError(
                    "preparation_policy_changed",
                    "咨询或配餐处理说明已更新，请核对后继续准备；档案已保存",
                    409,
                )
            for member in permitted:
                hid = await service.repo.linked_health_member(fid, member.id)
                if hid:
                    grant = await session.get(HealthGrant, (hid, uid), populate_existing=True)
                    # 与显式停用串行，检查至绑定期间不让撤回记录被覆盖。
                    await session.execute(
                        insert(HealthProcessingConsent)
                        .values(
                            member_id=hid,
                            actor_uid=uid,
                            purpose=purpose,
                            processor=expected["processor"],
                            policy_version=expected["policy_version"],
                            granted_at=utc_now_naive(),
                        )
                        .on_conflict_do_nothing(index_elements=["member_id", "actor_uid", "purpose"])
                    )
                    consent = await session.scalar(
                        select(HealthProcessingConsent)
                        .where(
                            HealthProcessingConsent.member_id == hid,
                            HealthProcessingConsent.actor_uid == uid,
                            HealthProcessingConsent.purpose == purpose,
                        )
                        .with_for_update()
                        .execution_options(populate_existing=True)
                    )
                    if (
                        grant is not None
                        and (grant.revoked_at is not None or "ai_use" not in grant.scopes)
                        or consent is not None
                        and consent.revoked_at is not None
                    ):
                        raise HealthVisionError(
                            "processing_consent_revoked",
                            "该成员的分析授权已停用，请在成员档案中核对；档案已保存",
                            403,
                        )
            await bind_submitted_profile(session, uid, family, permitted, expected)
        actor = await service.repo.subject_member(fid, uid)
        health_id = await service.repo.linked_health_member(fid, actor.id)

    async def checkpoint(session, **values):
        """只有当前 attempt 可以更新衔接引用。"""
        row = await require_preparation(session, uid, fid, pid)
        if row.attempt == payload["attempt"]:
            row.result = {**row.result, **values}
            row.updated_at = utc_now_naive()

    try:
        await context.run_owned_transaction(bind)
        if health_id is None:
            return {"superseded": True}
        thread = await create_daily_consultation(uid, health_id)
        await context.run_owned_transaction(
            lambda session, _task_record: checkpoint(session, thread_id=thread["thread_id"])
        )
        daily = await start_daily_arrangement(
            uid, fid, SimpleNamespace(date=business_date(), client_request_id=UUID(pid))
        )

        async def linked(session, _task_record):
            """配餐已经独立登记，准备任务立即释放执行槽位。"""
            await checkpoint(session, arrangement_id=daily["id"])
            row = await require_preparation(session, uid, fid, pid)
            if row.attempt == payload["attempt"]:
                _, current = await DailyArrangementRepository(session, uid, fid).context(business_date())
                row.status = "ready" if current is not None and current.status == "ready" else "waiting"

        await context.run_owned_transaction(linked)
        return {"preparation_id": pid, "arrangement_id": daily["id"]}
    except HealthVisionError as error:
        failure_code, failure_message = error.code, error.message
        if failure_code == "daily_member_sources_unavailable":
            failure_message = "部分就餐成员尚未完成分析授权或档案关联，请在家庭档案中核对；已填写资料已保存。"

        async def failed(session, _task_record):
            """保留完成引用，公开稳定的业务错误。"""
            row = await require_preparation(session, uid, fid, pid)
            if row.attempt == payload["attempt"]:
                row.status, row.error_code, row.error_message = (
                    "failed",
                    failure_code,
                    failure_message,
                )

        await context.run_owned_transaction(failed)
        return {"preparation_id": pid, "error_code": error.code}


async def fail_onboarding_preparation(session, task_record, error):
    """失联及进程错误保留准备记录，可从同一档案继续。"""
    payload = task_record.payload
    row = await session.get(HealthOnboardingPreparation, payload["preparation_id"], with_for_update=True)
    if row is not None and row.attempt == payload["attempt"]:
        row.status = "failed"
        row.error_code = "preparation_interrupted"
        row.error_message = "准备暂时中断，档案已保存，可以继续原准备。"


async def finish_onboarding_preparations(uid, fid, day, arrangement):
    """配餐成功后保存完成引用，业务有效性仍由原结果读取校验。"""
    async with pg_manager.get_async_session_context() as db:
        service = FamilyService(db, uid)
        family, _ = await service.context(fid)
        rows = (
            await db.scalars(
                select(HealthOnboardingPreparation)
                .where(
                    HealthOnboardingPreparation.actor_uid == uid,
                    HealthOnboardingPreparation.family_id == fid,
                    HealthOnboardingPreparation.plan_date == day,
                    HealthOnboardingPreparation.status == "waiting",
                )
                .with_for_update()
            )
        ).all()
        sources = await preparation_sources(service, family)
        for row in rows:
            if (
                row.sources == sources
                and row.result.get("thread_id")
                and row.result.get("arrangement_id") == arrangement["id"]
            ):
                row.status, row.updated_at = "ready", utc_now_naive()


def prepared_arrangement_complete(value, day):
    """准备入口只接受完整已保存三餐及真实分析来源。"""
    analysis, meals = value.get("analysis", {}), value.get("meals", [])
    if (
        value.get("date") != day
        or value.get("saved") is not True
        or not isinstance(value.get("version"), int)
        or value["version"] < 1
        or value.get("validation", {}).get("status") != "passed"
        or value.get("procurement", {}).get("checked") is not True
        or analysis.get("source") != "agent"
        or not analysis.get("request_id")
        or not analysis.get("run_id")
        or not analysis.get("text", "").strip()
        or len(meals) != 3
        or {meal.get("type") for meal in meals} != {"breakfast", "lunch", "dinner"}
    ):
        return False
    for meal in meals:
        purchase, dishes, members = meal.get("purchase", {}), meal.get("dishes", []), meal.get("members", [])
        notes = meal.get("memberNotes", [])
        if (
            not dishes
            or not members
            or not meal.get("detail_ref")
            or not meal.get("nutrition")
            or not meal.get("nutritionSource")
            or any(
                not dish.get("id")
                or not dish.get("name")
                or not dish.get("recipeVersion")
                or not dish.get("ingredients")
                or not dish.get("steps")
                for dish in dishes
            )
            or any(
                not member.get("id")
                or not member.get("name")
                or not any(note.get("memberId") == member.get("id") and note.get("dishes") for note in notes)
                for member in members
            )
        ):
            return False
        matched = (
            purchase.get("status") == "matched"
            and purchase.get("catalog_version")
            and purchase.get("ingredient_requirements")
            and purchase.get("items")
            and all(
                item.get("sku", {}).get("sku_id")
                and type(item.get("quantity")) is int
                and item["quantity"] > 0
                and type(item.get("sku", {}).get("price_cent")) is int
                for item in purchase["items"]
            )
        )
        published = (
            purchase.get("package_sn")
            and type(purchase.get("package_version")) is int
            and purchase["package_version"] > 0
        )
        if not matched and not published:
            return False
    return True


async def preparation_sources(service, family):
    """按实际已保存成员及默认就餐者绑定版本。"""
    members = await service.repo.members(family.id)
    return {
        "family_version": family.version,
        "members": {member.id: member.version for member in members if member.is_active},
        "default_diners": sorted((family.settings or {}).get("default_diners", [])),
    }


async def lock_preparation(db, uid, fid):
    """同账号家庭的首开与恢复串行，数据库唯一键兜底。"""
    await db.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
        {"key": f"onboarding:{uid}:{fid}"},
    )


async def latest_preparation(db, uid, fid):
    """只查调用账号当前家庭的最新准备。"""
    return await db.scalar(
        select(HealthOnboardingPreparation)
        .where(
            HealthOnboardingPreparation.actor_uid == uid,
            HealthOnboardingPreparation.family_id == fid,
            HealthOnboardingPreparation.status != "alias",
        )
        .order_by(
            HealthOnboardingPreparation.created_at.desc(),
            HealthOnboardingPreparation.id.desc(),
        )
        .limit(1)
    )


async def require_preparation(db, uid, fid, pid):
    """准备ID不能绕过家庭或账号归属。"""
    await FamilyService(db, uid).context(fid)
    row = await db.get(HealthOnboardingPreparation, str(pid), with_for_update=True)
    if row is None or row.actor_uid != uid or row.family_id != fid:
        raise HealthVisionError("not_found", "准备记录不存在或无权访问", 404)
    if row.status == "alias":
        target = await db.get(HealthOnboardingPreparation, row.result["reused_preparation_id"], with_for_update=True)
        if target is None or target.actor_uid != uid or target.family_id != fid or target.status == "alias":
            raise HealthVisionError("preparation_reference_invalid", "原准备引用已失效，请重新读取", 409)
        row = target
    return row


async def queue_preparation(db, row):
    """状态与Task同事务登记，提交后由调用方发布。"""
    payload = {
        "uid": row.actor_uid,
        "family_id": row.family_id,
        "preparation_id": row.id,
        "attempt": row.attempt,
    }
    task, _ = await tasker.create_unique_in_session(
        db,
        name="衔接建档准备",
        task_type="onboarding_preparation_v1",
        payload=payload,
        payload_match=payload,
        timeout_seconds=120,
    )
    row.task_id = task.id
    return task

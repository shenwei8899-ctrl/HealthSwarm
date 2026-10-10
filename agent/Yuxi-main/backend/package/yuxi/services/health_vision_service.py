"""私有识图、人工纠错及一次确认的用例事务。"""

import asyncio
import hashlib
from datetime import timedelta
from uuid import uuid4

from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from yuxi.config.options import health_vision_opts, invalidate_option_cache, update_option_value
from yuxi.models.providers.cache import ModelInfo, model_cache
from yuxi.models.providers import repository as provider_repository
from yuxi.repositories.health_vision_repository import HealthVisionRepository
from yuxi.services.health_media_service import prepare_upload
from yuxi.services.health_nutrition_service import (
    CALCULATION_VERSION,
    calculate_nutrition,
    input_fingerprint,
    recipe_nutrients,
)
from yuxi.services.health_vision_types import (
    HEALTH_SCOPES,
    MEAL_PROMPT_VERSION,
    DraftInput,
    HealthVisionError,
    MealPayload,
    ReportPayload,
    ReportPreparationInput,
    ReportReprocessInput,
    VisionConfigurationInput,
    VisionTaskInput,
)
from yuxi.services.ocr_service import resolve_ocr_task_params
from yuxi.services.task_service import tasker
from yuxi.storage.minio import get_minio_client
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_business import TaskRecord
from yuxi.storage.postgres.models_health import (
    DietLog,
    FamilyMember,
    FoodRecord,
    HealthGrant,
    HealthObservation,
    HealthProcessingConsent,
    NutritionCalculation,
    PrivateUpload,
    PortionReference,
    RecipeVersion,
    VisionConfirmation,
    VisionDraft,
    VisionJob,
    VisionRevision,
)
from yuxi.utils.datetime_utils import format_utc_datetime, utc_now_naive

PRIVATE_BUCKET = "health-private"
MEAL_MODEL_ID = "qwen3-vl-flash-2026-01-22"


async def current_health_model_info(session, spec):
    """在已刷新的运行投影上核对 PG 当前配置；不一致时关闭健康能力。"""
    provider_id, separator, model_id = spec.partition(":")
    if not separator:
        return None
    provider = await provider_repository.get_model_provider(session, provider_id)
    if provider is None or not provider.is_enabled:
        return None
    model = next((item for item in provider.enabled_models or [] if item["id"] == model_id), None)
    if model is None:
        return None
    current = ModelInfo.from_provider(provider, model)
    if (
        not current.api_key
        or current.model_type != "chat"
        or current.provider_type not in {"openai", "openrouter"}
        or model_cache.get_model_info(spec) != current
    ):
        return None
    return current


def processor_identity(kind, info, ocr_kwargs=None):
    """实际端点和请求配置绑定审批，指纹不公开凭据或内部 URL。"""
    if info is None:
        return ""
    binding = {
        "spec": info.spec,
        "type": info.provider_type,
        "base_url": info.base_url,
        "headers": info.headers,
        "extra": info.extra,
        "overrides": info.request_body_overrides,
    }
    if kind == "report":
        binding["ocr_endpoint"] = (ocr_kwargs or {}).get(
            "api_url"
        ) or "https://paddleocr.aistudio-app.com/api/v2/ocr/jobs"
    digest = input_fingerprint(binding)
    return f"{'paddleocr-vl-1.6+' if kind == 'report' else ''}{info.provider_id[:64]}:{digest}"


def serialize_draft(record):
    """只输出复核数据，不返回内部对象键或供应商凭据。"""
    return {
        "id": record.id,
        "member_id": record.member_id,
        "kind": record.kind,
        "version": record.version,
        "review_status": record.review_status,
        "payload": record.payload,
        "model_version": record.model_version,
        "parser_version": record.parser_version,
        "created_at": format_utc_datetime(record.created_at),
    }


def require_editable(record, version: int):
    """过期、已确认或陈旧版本不能改变已接受的事实。"""
    if record.review_status != "pending_confirmation" or record.version != version:
        raise HealthVisionError("version_conflict", "草稿已变化或已确认，请刷新", 409)
    if record.created_at < utc_now_naive() - timedelta(days=7):
        raise HealthVisionError("draft_expired", "草稿超过 7 天，请重新录入或识别", 410)


class HealthVisionService:
    """HTTP 和 worker 共享的健康用例入口。"""

    async def configuration(self, session=None):
        """配置状态只读探测，不发起供应商或模型调用。"""
        if session is None:
            async with pg_manager.get_async_session_context() as session:
                return await self.configuration(session)
        model_cache.refresh()
        values = await health_vision_opts.get(session)
        result = {
            "policy_version": values.get("policy_version") or "",
            "report": {},
            "meal": {},
            "limits": {
                "image_mb": 10,
                "pdf_mb": 20,
                "report_pages": 20,
                "meal_images": 3,
                "member_active_tasks": 2,
                "account_daily_tasks": 10,
                "total_daily_tasks": 100,
            },
            "model_options": [
                {"spec": info.spec, "name": info.display_name}
                for info in model_cache.get_all_specs("chat")
                if info.api_key
            ],
        }
        for kind in ("report", "meal", "consultation", "meal_plan", "diet_analysis", "quality_review", "purchase"):
            spec = values.get(f"{kind}_model") or ""
            info = await current_health_model_info(session, spec) if spec else None
            reason = None
            if not result["policy_version"]:
                reason = "尚未审批云处理政策"
            elif info is None or not info.api_key:
                reason = "请先配置并启用模型供应商及识别模型"
            elif kind == "meal" and info.model_id != MEAL_MODEL_ID:
                reason = f"饮食模型须使用已冻结版本 {MEAL_MODEL_ID}"
            ocr_kwargs = {}
            if kind == "report":
                try:
                    params = await resolve_ocr_task_params({"ocr_engine": "paddleocr_vl_1_6"}, session)
                    ocr_kwargs = params["_ocr_processor_kwargs"]
                    if not params["_ocr_processor_kwargs"].get("api_token"):
                        reason = "请在 OCR 配置中填写 PaddleOCR 凭据"
                except ValueError:
                    reason = "PaddleOCR 未配置"
            processor = processor_identity(kind, info, ocr_kwargs)
            if reason is None and values.get(f"approved_{kind}_processor") != processor:
                reason = "供应商端点或请求配置已变化，请重新审批服务配置并取得用途同意"
            result[kind] = {"available": reason is None, "reason": reason, "model": spec, "processor": processor}
        result["food_count"] = int(await session.scalar(select(func.count()).select_from(FoodRecord)) or 0)
        return result

    async def configure(self, uid: str, data: VisionConfigurationInput):
        """管理员选择既有供应商模型，不接收业务客户端任意端点。"""
        model_cache.refresh()
        approved = {
            f"approved_{kind}_processor": ""
            for kind in ("report", "meal", "consultation", "meal_plan", "diet_analysis", "quality_review", "purchase")
        }
        for kind, spec in (
            ("report", data.report_model),
            ("meal", data.meal_model),
            ("consultation", data.consultation_model),
            ("meal_plan", data.meal_plan_model),
            ("diet_analysis", data.diet_analysis_model),
            ("quality_review", data.quality_review_model),
            ("purchase", data.purchase_model),
        ):
            if not spec:
                continue
            async with pg_manager.get_async_session_context() as session:
                info = await current_health_model_info(session, spec)
            if (
                info is None
                or not info.api_key
                or info.model_type != "chat"
                or info.provider_type not in {"openai", "openrouter"}
            ):
                raise HealthVisionError("model_not_configured", "请选择已配置凭据的兼容模型")
            if kind == "meal" and info.model_id != MEAL_MODEL_ID:
                raise HealthVisionError("model_version_required", f"饮食模型须为 {MEAL_MODEL_ID}")
            if any(alias in info.model_id.lower() for alias in ("latest", "preview")):
                raise HealthVisionError("model_version_required", "请使用经验证的固定版本，而非浮动别名")
            ocr_kwargs = {}
            if kind == "report":
                params = await resolve_ocr_task_params({"ocr_engine": "paddleocr_vl_1_6"})
                ocr_kwargs = params["_ocr_processor_kwargs"]
                if not ocr_kwargs.get("api_token"):
                    raise HealthVisionError("provider_not_configured", "请先配置 PaddleOCR 凭据", 503)
            approved[f"approved_{kind}_processor"] = processor_identity(kind, info, ocr_kwargs)
        async with pg_manager.get_async_session_context() as session:
            await update_option_value(
                session,
                health_vision_opts.key,
                {
                    "report_model": data.report_model,
                    "meal_model": data.meal_model,
                    "consultation_model": data.consultation_model,
                    "meal_plan_model": data.meal_plan_model,
                    "diet_analysis_model": data.diet_analysis_model,
                    "quality_review_model": data.quality_review_model,
                    "purchase_model": data.purchase_model,
                    "policy_version": data.policy_version,
                    **approved,
                },
                uid,
            )
        await invalidate_option_cache(health_vision_opts.key)
        return await self.configuration()

    async def members(self, uid: str):
        """读取当前账号已授权成员。"""
        async with pg_manager.get_async_session_context() as session:
            records = await HealthVisionRepository(session).list_members(uid)
            return [
                {
                    "id": item.id,
                    "display_name": item.display_name,
                    "relationship_label": item.relationship_label,
                    "is_owner": item.owner_uid == uid,
                    "scopes": (await session.get(HealthGrant, (item.id, uid))).scopes,
                }
                for item in records
            ]

    async def create_member(self, uid: str, data):
        """建档显式确认代理依据，只给建档账号发初始 grant。"""
        member_id = str(uuid4())
        async with pg_manager.get_async_session_context() as session:
            session.add(
                FamilyMember(
                    id=member_id,
                    owner_uid=uid,
                    display_name=data.display_name,
                    relationship_label=data.relationship_label,
                )
            )
            await session.flush()
            session.add(HealthGrant(member_id=member_id, actor_uid=uid, scopes=sorted(HEALTH_SCOPES)))
        return {"id": member_id}

    async def grant(self, uid: str, member_id: str, data):
        """同一成员锁下保存或撤回授权。"""
        async with pg_manager.get_async_session_context() as session:
            await HealthVisionRepository(session).set_grant(member_id, uid, data.actor_uid, data.scopes)
            if not {"diet_edit", "profile_view"} <= set(data.scopes):
                from yuxi.repositories.health_quality_repository import HealthQualityRepository

                await HealthQualityRepository(session).invalidate(
                    member_id=member_id, actor_uid=data.actor_uid, reason="applicant_grant_revoked"
                )
            if not {"professional_review", "profile_view"} <= set(data.scopes):
                from yuxi.repositories.health_quality_repository import HealthQualityRepository

                await HealthQualityRepository(session).invalidate(
                    member_id=member_id, reviewer_uid=data.actor_uid, reason="reviewer_grant_revoked"
                )
        return {"saved": True}

    async def consent(self, uid: str, member_id: str, data):
        """用途同意和访问授权分开，不把上传视为同意。"""
        config = await self.configuration()
        if data.accepted and (
            data.processor != config[data.purpose]["processor"]
            or data.policy_version != config["policy_version"]
            or not config[data.purpose]["available"]
        ):
            raise HealthVisionError("policy_changed", "处理配置未就绪或已变化，请刷新", 409)
        async with pg_manager.get_async_session_context() as session:
            await HealthVisionRepository(session).authorize(member_id, uid, "ai_use", lock=True)
            record = await session.get(HealthProcessingConsent, (member_id, uid, data.purpose))
            if record is None:
                record = HealthProcessingConsent(member_id=member_id, actor_uid=uid, purpose=data.purpose)
                session.add(record)
            record.processor, record.policy_version = data.processor, data.policy_version
            record.granted_at = utc_now_naive()
            record.revoked_at = None if data.accepted else utc_now_naive()
        return {"accepted": data.accepted}

    async def upload(self, uid: str, member_id: str, purpose: str, data: bytes, *, rotation=0, deskew_angle=0):
        """先验证授权和真实内容，随机私有对象最后与 PG 绑定。"""
        scope = "report_upload" if purpose == "report" else "diet_edit"
        async with pg_manager.get_async_session_context() as session:
            await HealthVisionRepository(session).authorize(member_id, uid, scope)
        try:
            preparation = ReportPreparationInput(rotation=rotation, deskew_angle=deskew_angle)
        except ValidationError:
            raise HealthVisionError("report_transform_invalid", "报告处理角度无效") from None
        mime, pages = await asyncio.to_thread(prepare_upload, data, purpose, preparation)
        if sum(len(page["data"]) for page in pages) > 50 * 1024 * 1024:
            raise HealthVisionError("processed_file_too_large", "处理后的页图超过 50MB，请拆分报告", 413)
        upload_id, client, keys, page_records = str(uuid4()), get_minio_client(), [], []
        original_key = f"uploads/{upload_id}/original"
        try:
            await client.aupload_file(PRIVATE_BUCKET, original_key, data, mime)
            keys.append(original_key)
            for page in pages:
                key = f"uploads/{upload_id}/pages/{page['page_index']}.png"
                await client.aupload_file(PRIVATE_BUCKET, key, page["data"], "image/png")
                keys.append(key)
                page_records.append({**{k: v for k, v in page.items() if k != "data"}, "object_key": key})
            async with pg_manager.get_async_session_context() as session:
                await HealthVisionRepository(session).authorize(member_id, uid, scope, lock=True)
                session.add(
                    PrivateUpload(
                        id=upload_id,
                        actor_uid=uid,
                        member_id=member_id,
                        purpose=purpose,
                        original_key=original_key,
                        sha256=hashlib.sha256(data).hexdigest(),
                        mime=mime,
                        byte_size=len(data),
                        pages=page_records,
                        status="active",
                    )
                )
        except Exception:
            for key in keys:
                await client.adelete_file(PRIVATE_BUCKET, key)
            raise
        return {"upload_id": upload_id, "purpose": purpose, "mime": mime, "page_count": len(pages), "status": "ready"}

    async def preview(self, uid: str, upload_id: str, page_index: int | None):
        """授权代理返回私有字节，不产生公共地址。"""
        async with pg_manager.get_async_session_context() as session:
            repo = HealthVisionRepository(session)
            record = await session.get(PrivateUpload, upload_id)
            scope = "report_view" if record and record.purpose == "report" else "diet_edit"
            record = await repo.upload(upload_id, uid, scope)
            key, mime = record.original_key, record.mime
            if page_index is not None:
                if page_index >= len(record.pages):
                    raise HealthVisionError("not_found", "页面不存在", 404)
                key, mime = record.pages[page_index]["object_key"], "image/png"
            content = await get_minio_client().adownload_file(PRIVATE_BUCKET, key)
            await repo.upload(upload_id, uid, scope)
        return content, mime

    async def create_task(
        self,
        uid: str,
        kind: str,
        data,
        *,
        parent_task_id: str | None = None,
        report_reprocess: ReportReprocessInput | None = None,
    ):
        """成员和用途绑定，提交持久意图后才投递 ARQ。"""
        member_id = str(data.member_id)
        request_payload = data.model_dump(mode="json")
        if report_reprocess is not None:
            request_payload["reprocess"] = report_reprocess.model_dump(mode="json")
        fingerprint = input_fingerprint(request_payload)
        config = await self.configuration()
        task = None
        async with pg_manager.get_async_session_context() as session:
            # 全局额度只在短创建事务排序，不占 worker 或外呼槽。
            await session.execute(select(func.pg_advisory_xact_lock(94721940)))
            repo = HealthVisionRepository(session)
            await repo.authorize(member_id, uid, "report_upload" if kind == "report" else "diet_edit", lock=True)
            draft = None
            if report_reprocess is not None:
                draft = await repo.draft(str(report_reprocess.draft_id), uid, "report", write=True)
                if kind != "report" or draft.member_id != member_id:
                    raise HealthVisionError("not_found", "草稿不存在或无权访问", 404)
            previous = await repo.find_job_request(uid, member_id, kind, str(data.client_request_id))
            if previous:
                if previous.fingerprint != fingerprint:
                    raise HealthVisionError("idempotency_conflict", "同一请求标识对应不同内容", 409)
                await repo.active_uploads(previous)
                return {
                    "task_id": previous.task_id,
                    "execution_status": (await session.get(TaskRecord, previous.task_id)).status,
                }
            if report_reprocess is not None:
                require_editable(draft, report_reprocess.version)
                payload = ReportPayload.model_validate(draft.payload)
                failed_indices = {page.page_index for page in payload.pages if page.status == "failed"}
                if not set(report_reprocess.page_indices) <= failed_indices:
                    raise HealthVisionError("report_reprocess_invalid", "只能重识别当前草稿中的失败页")
                if await repo.has_active_report_reprocess(draft.id):
                    raise HealthVisionError("reprocess_conflict", "该草稿已有重识别任务，请等待任务结束", 409)
            if not config[kind]["available"]:
                raise HealthVisionError("provider_not_configured", config[kind]["reason"], 503)
            await repo.authorize(member_id, uid, "ai_use")
            snapshot = {
                "model": config[kind]["model"],
                "processor": config[kind]["processor"],
                "policy_version": config["policy_version"],
                "meal_type": data.meal_type,
                "eaten_at": data.eaten_at.isoformat() if data.eaten_at else None,
                "prompt_version": MEAL_PROMPT_VERSION if kind == "meal" else "health-vision-v1",
            }
            await repo.require_consent(member_id, uid, kind, snapshot)
            if parent_task_id is not None and kind == "report":
                parent = await repo.job(parent_task_id, uid, write=True)
                if (
                    parent.actor_uid == uid
                    and parent.member_id == member_id
                    and parent.kind == kind
                    and parent.upload_ids == [str(item) for item in data.upload_ids]
                    and all(
                        parent.input_snapshot.get(key) == snapshot[key]
                        for key in ("model", "processor", "policy_version", "prompt_version")
                    )
                ):
                    snapshot["provider_jobs"] = list(parent.input_snapshot.get("provider_jobs", []))
                elif report_reprocess is not None and any(
                    parent.input_snapshot.get(key) != snapshot[key]
                    for key in ("model", "processor", "policy_version", "prompt_version")
                ):
                    raise HealthVisionError("policy_changed", "重识别处理政策或模型已变化，请重新建任务复核", 409)
            if report_reprocess is not None:
                snapshot["reprocess"] = report_reprocess.model_dump(mode="json")
            if kind == "meal" and (
                len(data.upload_ids) > 3
                or data.meal_type is None
                or data.eaten_at is None
                or data.eaten_at.tzinfo is None
            ):
                raise HealthVisionError("meal_input_invalid", "一餐需要 1 至 3 张图片、餐次及含时区的就餐时间")
            if kind == "report" and (data.meal_type is not None or data.eaten_at is not None):
                raise HealthVisionError("report_input_invalid", "报告任务不能包含饮食参数")
            job = VisionJob(
                id=str(uuid4()),
                member_id=member_id,
                actor_uid=uid,
                kind=kind,
                request_id=str(data.client_request_id),
                fingerprint=fingerprint,
                upload_ids=[str(item) for item in data.upload_ids],
                input_snapshot=snapshot,
                parent_task_id=parent_task_id,
                phase="validating",
            )
            uploads = await repo.active_uploads(job)
            if sum(len(upload.pages) for upload in uploads) > (20 if kind == "report" else 3):
                raise HealthVisionError("page_limit", "报告最多 20 页，饮食最多 3 张图", 413)
            active, daily, total = await repo.task_counts(uid, member_id)
            if active >= 2 or daily >= 10 or total >= 100:
                raise HealthVisionError("budget_exceeded", "任务额度已达上限，可使用人工录入", 429)
            task = await tasker.create_in_session(
                session,
                name="健康报告提取" if kind == "report" else "饮食照片识别",
                task_type="report_extract_v1" if kind == "report" else "meal_recognize_v1",
                payload={"job_id": job.id},
                timeout_seconds=600,
            )
            job.task_id = task.id
            session.add(job)
        await tasker.publish(task)
        return {"task_id": task.id, "execution_status": "pending", "review_status": "not_ready"}

    async def jobs(self, uid: str, member_id: str):
        """工作台列表只显示授权用途，草稿与执行状态分开。"""
        async with pg_manager.get_async_session_context() as session:
            repo = HealthVisionRepository(session)
            grant = await session.get(HealthGrant, (member_id, uid))
            scope = next(
                (
                    value
                    for value in ("report_view", "diet_edit", "report_upload", "profile_edit", "ai_use")
                    if grant and value in grant.scopes
                ),
                "report_view",
            )
            await repo.authorize(member_id, uid, scope)
            result = []
            for job, task in await repo.list_jobs(member_id):
                try:
                    await repo.authorize(member_id, uid, "report_view" if job.kind == "report" else "diet_edit")
                    await repo.active_uploads(job)
                except HealthVisionError:
                    continue
                result.append(
                    self._serialize_job(
                        job, task, await session.get(VisionDraft, job.result_id) if job.result_id else None
                    )
                )
            drafts = []
            for draft in await repo.list_drafts(member_id):
                try:
                    await repo.authorize(member_id, uid, "report_view" if draft.kind == "report" else "diet_edit")
                except HealthVisionError:
                    continue
                if draft.job_id:
                    try:
                        await repo.active_uploads(await session.get(VisionJob, draft.job_id))
                    except HealthVisionError:
                        continue
                drafts.append(serialize_draft(draft))
            return {"jobs": result, "drafts": drafts}

    async def get_job(self, uid: str, task_id: str):
        """每次轮询重新授权，不信任客户端已知任务 ID。"""
        async with pg_manager.get_async_session_context() as session:
            job = await HealthVisionRepository(session).job(task_id, uid)
            task = await session.get(TaskRecord, task_id)
            response = self._serialize_job(
                job, task, await session.get(VisionDraft, job.result_id) if job.result_id else None
            )
            response["uploads"] = [
                {
                    "upload_id": upload_id,
                    "pages": [
                        {"page_index": page["page_index"], "width": page["width"], "height": page["height"]}
                        for page in (await session.get(PrivateUpload, upload_id)).pages
                    ],
                }
                for upload_id in job.upload_ids
            ]
            return response

    async def cancel(self, uid: str, task_id: str):
        """成员授权与取消意图在同一个事务执行，禁止迟到提交。"""
        async with pg_manager.get_async_session_context() as session:
            repo = HealthVisionRepository(session)
            # Task 的锁顺序与 success hook 一致，避免取消与授权行锁倒序。
            task = await session.scalar(select(TaskRecord).where(TaskRecord.id == task_id).with_for_update())
            job = await repo.job(task_id, uid, write=True)
            if task.status not in {"pending", "running"}:
                return self._serialize_job(job, task)
            task.cancel_requested = 1
            if task.status == "pending":
                task.status, task.message, task.completed_at, task.dedupe_key = (
                    "cancelled",
                    "任务已取消",
                    utc_now_naive(),
                    None,
                )
                job.error_code = "cancelled"
            return self._serialize_job(job, task)

    async def retry(self, uid: str, task_id: str, request_id):
        """显式新建任务，不复活旧终态或改变已确认数据。"""
        async with pg_manager.get_async_session_context() as session:
            job = await HealthVisionRepository(session).job(task_id, uid, write=True)
            task = await session.get(TaskRecord, task_id)
            if task.status not in {"failed", "cancelled"}:
                raise HealthVisionError("retry_conflict", "仅失败或取消的任务可以重试", 409)
            data = VisionTaskInput(
                member_id=job.member_id,
                upload_ids=job.upload_ids,
                client_request_id=request_id,
                meal_type=job.input_snapshot.get("meal_type"),
                eaten_at=job.input_snapshot.get("eaten_at"),
            )
            reprocess = job.input_snapshot.get("reprocess")
        return await self.create_task(
            uid,
            job.kind,
            data,
            parent_task_id=task_id,
            report_reprocess=ReportReprocessInput.model_validate({**reprocess, "client_request_id": request_id})
            if reprocess
            else None,
        )

    async def reprocess_report(self, uid: str, data: ReportReprocessInput):
        """来源从授权草稿派生，最终创建事务再次锁定并校验版本。"""
        async with pg_manager.get_async_session_context() as session:
            draft = await HealthVisionRepository(session).draft(str(data.draft_id), uid, "report")
            if not draft.job_id:
                raise HealthVisionError("report_reprocess_invalid", "人工草稿没有可重识别的报告源")
            source = await session.get(VisionJob, draft.job_id)
            request = VisionTaskInput(
                member_id=draft.member_id, upload_ids=source.upload_ids, client_request_id=data.client_request_id
            )
            parent_task_id = source.task_id
        return await self.create_task(uid, "report", request, parent_task_id=parent_task_id, report_reprocess=data)

    async def manual_draft(self, uid: str, data: DraftInput):
        """无供应商时允许人工录入，且不伪造识别来源。"""
        payload = (data.report if data.kind == "report" else data.meal).model_dump(mode="json")
        if data.kind == "report" and (
            payload["pages"] or any(field["source"] != "manual" for field in payload["fields"])
        ):
            raise HealthVisionError("manual_evidence_invalid", "手工录入只能使用人工来源")
        if data.kind == "meal" and payload["photos"]:
            raise HealthVisionError("manual_evidence_invalid", "人工饮食草稿不能伪造照片来源")
        draft_id, member_id = str(uuid4()), str(data.member_id)
        async with pg_manager.get_async_session_context() as session:
            await HealthVisionRepository(session).authorize(
                member_id, uid, "profile_edit" if data.kind == "report" else "diet_edit", lock=True
            )
            draft = VisionDraft(
                id=draft_id,
                member_id=member_id,
                kind=data.kind,
                payload=payload,
                original_payload=payload,
                review_status="pending_confirmation",
                version=1,
                created_at=utc_now_naive(),
            )
            session.add(draft)
        return serialize_draft(draft)

    async def get_draft(self, uid: str, draft_id: str, kind: str):
        """读当前候选与其版本。"""
        async with pg_manager.get_async_session_context() as session:
            return serialize_draft(await HealthVisionRepository(session).draft(draft_id, uid, kind))

    async def patch_draft(self, uid: str, draft_id: str, kind: str, data):
        """人工修订保留抽取证据，版本变化使旧计算失效。"""
        payload_model = data.report if kind == "report" else data.meal
        if payload_model is None or (data.meal is not None if kind == "report" else data.report is not None):
            raise HealthVisionError("payload_invalid", "修改内容与草稿用途不一致")
        payload = payload_model.model_dump(mode="json")
        ids = [
            item["field_id" if kind == "report" else "item_id"]
            for item in payload["fields" if kind == "report" else "items"]
        ]
        if len(ids) != len(set(ids)):
            raise HealthVisionError("duplicate_item", "结果项不能重复")
        async with pg_manager.get_async_session_context() as session:
            draft = await HealthVisionRepository(session).draft(draft_id, uid, kind, write=True)
            require_editable(draft, data.version)
            if kind == "report":
                original_pages = ReportPayload.model_validate(draft.original_payload).model_dump(mode="json")["pages"]
                if payload["pages"] != original_pages:
                    raise HealthVisionError("evidence_invalid", "处理页面信息不可修改或伪造")
                original = {item["field_id"]: item for item in draft.original_payload["fields"]}
                for field in payload["fields"]:
                    source = original.get(field["field_id"])
                    if field["source"] == "ocr" and (source is None or field["evidence"] != source["evidence"]):
                        raise HealthVisionError("evidence_invalid", "原文证据不可修改或伪造")
            else:
                original = MealPayload.model_validate(draft.original_payload).model_dump(mode="json")
                if payload["photos"] != original["photos"]:
                    raise HealthVisionError("evidence_invalid", "照片来源不可修改或伪造")
                sources = {item["item_id"]: item for item in original["items"]}
                for item in payload["items"]:
                    locations = sources.get(item["item_id"], {}).get("locations", [])
                    if item["locations"] != locations:
                        raise HealthVisionError("evidence_invalid", "模型原位置不可修改或伪造")
            draft.payload, draft.version = payload, draft.version + 1
            session.add(
                VisionRevision(
                    id=str(uuid4()),
                    draft_id=draft.id,
                    version=draft.version,
                    actor_uid=uid,
                    payload=payload,
                    reason=data.reason,
                )
            )
            return serialize_draft(draft)

    async def calculate(self, uid: str, draft_id: str, version: int):
        """食品映射由用户选择的已发布记录决定。"""
        async with pg_manager.get_async_session_context() as session:
            draft = await HealthVisionRepository(session).draft(draft_id, uid, "meal", write=True)
            require_editable(draft, version)
            payload = MealPayload.model_validate(draft.payload)
            ids = {str(item.food_id) for item in payload.items if item.food_id}
            ids.update(str(entry.food_id) for item in payload.items for entry in item.adjustments)
            foods = {
                item.id: item
                for item in (await session.scalars(select(FoodRecord).where(FoodRecord.id.in_(ids)))).all()
            }
            recipe_ids = {str(item.recipe_version_id) for item in payload.items if item.recipe_version_id}
            portion_ids = {str(item.portion_reference_id) for item in payload.items if item.portion_reference_id}
            recipes = {
                item.id: item
                for item in (await session.scalars(select(RecipeVersion).where(RecipeVersion.id.in_(recipe_ids)))).all()
            }
            portions = {
                item.id: item
                for item in (
                    await session.scalars(select(PortionReference).where(PortionReference.id.in_(portion_ids)))
                ).all()
            }
            result = calculate_nutrition(payload, foods, recipes, portions)
            calculation = NutritionCalculation(
                id=str(uuid4()),
                draft_id=draft.id,
                draft_version=draft.version,
                input_hash=input_fingerprint(draft.payload),
                input_snapshot=draft.payload,
                result=result,
                calculation_version=CALCULATION_VERSION,
            )
            session.add(calculation)
            return {"calculation_id": calculation.id, "draft_version": version, **result}

    async def confirm(self, uid: str, draft_id: str, kind: str, data):
        """行锁、重放指纹、业务记录和确认审计同事务提交。"""
        fingerprint = input_fingerprint({"draft_id": draft_id, **data.model_dump(mode="json")})
        async with pg_manager.get_async_session_context() as session:
            repo = HealthVisionRepository(session)
            draft = await repo.draft(draft_id, uid, kind, write=True)
            previous = await repo.find_confirmation(uid, draft.member_id, kind, str(data.client_request_id))
            if previous:
                if previous.fingerprint != fingerprint:
                    raise HealthVisionError("idempotency_conflict", "同一确认标识对应不同内容", 409)
                return {"confirmation_id": previous.id, "target_ids": previous.target_ids, "review_status": "confirmed"}
            require_editable(draft, data.version)
            confirmation = VisionConfirmation(
                id=str(uuid4()),
                draft_id=draft.id,
                draft_version=draft.version,
                actor_uid=uid,
                member_id=draft.member_id,
                kind=kind,
                request_id=str(data.client_request_id),
                fingerprint=fingerprint,
                target_ids=[],
            )
            session.add(confirmation)
            await session.flush()
            targets = []
            if kind == "report":
                payload = ReportPayload.model_validate(draft.payload)
                if any(
                    page.status == "failed" and page.page_index not in payload.excluded_pages for page in payload.pages
                ):
                    raise HealthVisionError("report_pages_incomplete", "请重新上传失败页，或明确排除失败页后保存再确认")
                accepted = [
                    field
                    for field in payload.fields
                    if not field.excluded
                    and (not field.evidence or field.evidence.page_index not in payload.excluded_pages)
                ]
                if not accepted or any(not field.value_raw for field in accepted):
                    raise HealthVisionError("report_incomplete", "至少保留一项有原始结果的指标")
                if data.calculation_id:
                    raise HealthVisionError("report_input_invalid", "报告确认不接受营养计算")
                for field in accepted:
                    target_id = str(uuid4())
                    targets.append(target_id)
                    session.add(
                        HealthObservation(
                            id=target_id,
                            member_id=draft.member_id,
                            confirmation_id=confirmation.id,
                            field_id=str(field.field_id),
                            snapshot=field.model_dump(mode="json"),
                        )
                    )
            else:
                calculation = (
                    await session.get(NutritionCalculation, str(data.calculation_id)) if data.calculation_id else None
                )
                if (
                    calculation is None
                    or calculation.draft_id != draft.id
                    or calculation.draft_version != draft.version
                    or calculation.input_hash != input_fingerprint(draft.payload)
                ):
                    raise HealthVisionError("calculation_stale", "请先计算当前草稿的营养预览", 409)
                if not calculation.result["complete"] and not data.accept_incomplete:
                    raise HealthVisionError("nutrition_incomplete", "营养数据不完整；请补充或明确接受不完整日记")
                target_id = str(uuid4())
                targets.append(target_id)
                session.add(
                    DietLog(
                        id=target_id,
                        member_id=draft.member_id,
                        confirmation_id=confirmation.id,
                        calculation_id=calculation.id,
                        snapshot={"meal": draft.payload, "nutrition": calculation.result},
                    )
                )
            confirmation.target_ids = targets
            draft.review_status = "confirmed"
            return {"confirmation_id": confirmation.id, "target_ids": targets, "review_status": "confirmed"}

    async def records(self, uid: str, member_id: str, kind: str):
        """只读取确认事务留下的正式快照。"""
        async with pg_manager.get_async_session_context() as session:
            repo = HealthVisionRepository(session)
            await repo.authorize(member_id, uid, "report_view" if kind == "report" else "diet_edit")
            result = []
            for record in await repo.list_records(member_id, kind):
                confirmation = await session.get(VisionConfirmation, record.confirmation_id)
                try:
                    await repo.draft(confirmation.draft_id, uid, kind)
                except HealthVisionError:
                    continue
                result.append(
                    {"id": record.id, "snapshot": record.snapshot, "created_at": format_utc_datetime(record.created_at)}
                )
            return result

    async def foods(self, query: str):
        """提供已发布食品供人工映射。"""
        async with pg_manager.get_async_session_context() as session:
            return [self.serialize_food(item) for item in await HealthVisionRepository(session).foods(query)]

    async def publish_food(self, uid: str, data):
        """带来源和许可的食品版本只追加，不覆盖历史计算。"""
        try:
            async with pg_manager.get_async_session_context() as session:
                record = FoodRecord(id=str(uuid4()), published_by=uid, **data.model_dump(mode="json"))
                session.add(record)
                await session.flush()
                return self.serialize_food(record)
        except IntegrityError:
            raise HealthVisionError("food_version_exists", "该食品数据版本已经发布", 409) from None

    async def recipes(self, query: str):
        """配方仅返回已发布、不可修改的版本。"""
        async with pg_manager.get_async_session_context() as session:
            records = await HealthVisionRepository(session).recipes(query)
            return [self._serialize_recipe(record) for record in records]

    async def portions(self, food_id: str | None, recipe_version_id: str | None):
        """参考规格严格绑定目标版本，不能跨食物套用碗勺重量。"""
        if bool(food_id) == bool(recipe_version_id):
            raise HealthVisionError("portion_mapping_required", "须选择一种食品或食谱版本")
        async with pg_manager.get_async_session_context() as session:
            records = await HealthVisionRepository(session).portions(food_id, recipe_version_id)
            return [self._serialize_portion(record) for record in records]

    async def publish_recipe(self, uid: str, data):
        """服务端由原料版本和净成品重量推导营养，不接受客户端营养值。"""
        try:
            async with pg_manager.get_async_session_context() as session:
                ingredients = []
                for ingredient in data.ingredients:
                    food = await session.get(FoodRecord, str(ingredient.food_id))
                    if food is None:
                        raise HealthVisionError("ingredient_not_found", "食谱原料须使用已发布食品版本")
                    ingredients.append(
                        {"food": self.serialize_food(food), "grams": str(ingredient.grams), "role": ingredient.role}
                    )
                record = RecipeVersion(
                    id=str(uuid4()),
                    published_by=uid,
                    **data.model_dump(mode="json", exclude={"ingredients", "yield_grams"}),
                    yield_grams=data.yield_grams,
                    ingredients=ingredients,
                    nutrients=recipe_nutrients(ingredients, data.yield_grams),
                )
                session.add(record)
                await session.flush()
                return self._serialize_recipe(record)
        except IntegrityError:
            raise HealthVisionError("recipe_version_exists", "该食谱数据版本已经发布", 409) from None

    async def publish_portion(self, uid: str, data):
        """发布有来源的实测参考，既不自动应用，也不宣称用户已经称重。"""
        try:
            async with pg_manager.get_async_session_context() as session:
                target = await session.get(
                    FoodRecord if data.food_id else RecipeVersion, str(data.food_id or data.recipe_version_id)
                )
                if target is None:
                    raise HealthVisionError("portion_target_not_found", "份量参考须绑定已发布版本")
                record = PortionReference(
                    id=str(uuid4()),
                    published_by=uid,
                    **data.model_dump(mode="json", exclude={"grams_per_unit"}),
                    grams_per_unit=data.grams_per_unit,
                )
                session.add(record)
                await session.flush()
                return self._serialize_portion(record)
        except IntegrityError:
            raise HealthVisionError("portion_version_exists", "该份量参考版本已经发布", 409) from None

    @staticmethod
    def _serialize_recipe(record):
        """返回配方的不可变原料与来源快照。"""
        fields = (
            "id",
            "record_code",
            "name",
            "cooking_state",
            "source",
            "license",
            "edition",
            "dataset_version",
            "ingredients",
            "nutrients",
        )
        return {
            **{key: getattr(record, key) for key in fields},
            "yield_grams": str(record.yield_grams),
            "recipe_estimated": True,
        }

    @staticmethod
    def _serialize_portion(record):
        """公开规格无发布账号。"""
        fields = (
            "id",
            "food_id",
            "recipe_version_id",
            "unit_label",
            "source",
            "license",
            "edition",
            "dataset_version",
            "applicable_scope",
        )
        return {**{key: getattr(record, key) for key in fields}, "grams_per_unit": str(record.grams_per_unit)}

    async def delete_upload(self, uid: str, upload_id: str):
        """先使源和派生结果不可读，再删除本次对象的精确键。"""
        async with pg_manager.get_async_session_context() as session:
            repo = HealthVisionRepository(session)
            upload = await session.get(PrivateUpload, upload_id)
            if upload is None:
                raise HealthVisionError("not_found", "文件不存在或无权访问", 404)
            await repo.authorize(
                upload.member_id, uid, "profile_edit" if upload.purpose == "report" else "diet_edit", lock=True
            )
            upload.status = "deleted"
            keys = [upload.original_key, *[page["object_key"] for page in upload.pages]]
            for job in (await session.scalars(select(VisionJob).where(VisionJob.member_id == upload.member_id))).all():
                if upload_id not in job.upload_ids:
                    continue
                job.error_code = "source_invalidated"
                keys.extend(
                    key
                    for key in job.input_snapshot.get("raw_result_keys", [])
                    if key.startswith(f"results/{job.task_id}/")
                )
                if job.result_id:
                    draft = await session.get(VisionDraft, job.result_id)
                    draft.review_status = "invalidated"
                    if draft.raw_result_key:
                        keys.append(draft.raw_result_key)
        for key in keys:
            await get_minio_client().adelete_file(PRIVATE_BUCKET, key)
        return {"status": "deleted"}

    @staticmethod
    def _serialize_job(job, task, draft=None):
        """映射真实 Task 状态，不暴露 payload、错误正文或 lease。"""
        return {
            "task_id": job.task_id,
            "kind": job.kind,
            "execution_status": task.status,
            "phase": job.phase,
            "progress": task.progress,
            "cancel_requested": bool(task.cancel_requested),
            "result_id": job.result_id,
            "review_status": draft.review_status if draft else "not_ready",
            "error_code": job.error_code,
            "created_at": format_utc_datetime(job.created_at),
        }

    @staticmethod
    def serialize_food(record):
        """公开食品数据不包含发布账号。"""
        return {
            key: getattr(record, key)
            for key in (
                "id",
                "record_code",
                "name",
                "cooking_state",
                "source",
                "license",
                "edition",
                "dataset_version",
                "nutrients",
                "recipe_estimated",
            )
        }


health_vision_service = HealthVisionService()

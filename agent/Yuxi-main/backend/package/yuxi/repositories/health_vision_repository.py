"""健康领域查询及成员授权边界；事务由 service 拥有。"""

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import aliased

from yuxi.services.health_vision_types import FAMILY_REPORT_SCOPES, HEALTH_SCOPES, HealthVisionError
from yuxi.services.health_family_meal_plan_types import plan_member_ids
from yuxi.storage.postgres.models_business import TaskRecord, User, FamilyArchive, FamilyMember as SourceMember
from yuxi.storage.postgres.models_health import (
    DietLog,
    FamilyMember,
    FoodRecord,
    HealthFamilyProfileLink,
    HealthGrant,
    HealthObservation,
    HealthProcessingConsent,
    PrivateUpload,
    PortionReference,
    RecipeVersion,
    VisionConfirmation,
    VisionDraft,
    VisionJob,
)
from yuxi.utils.datetime_utils import utc_now_naive
from yuxi.storage.postgres.models_health_budget import HealthAiCall


class HealthVisionRepository:
    """家庭报告随有效家庭关系共享，独立健康用途仍读取原有授权。"""

    def __init__(self, session):
        self.session = session

    async def authorize(self, member_id: str, uid: str, scope: str, *, lock: bool = False):
        """写用例先锁成员，使撤回和写入按同一边界排序。"""
        shared = False
        if scope in FAMILY_REPORT_SCOPES:
            shared = await self._authorize_report_link(member_id, uid, lock=lock)
        elif lock:
            link = await self.session.get(HealthFamilyProfileLink, member_id, populate_existing=True)
            if link is not None:
                await self.session.scalar(
                    select(FamilyArchive).where(FamilyArchive.id == link.family_id).with_for_update()
                )
        stmt = select(FamilyMember).where(FamilyMember.id == member_id)
        if lock:
            stmt = stmt.with_for_update()
        member = await self.session.scalar(stmt)
        grant = await self.session.get(HealthGrant, (member_id, uid), populate_existing=True)
        user = await self.session.scalar(select(User).where(User.uid == uid, User.is_deleted == 0))
        if member is None or user is None:
            raise HealthVisionError("not_found", "资源不存在或无权访问", 404)
        if scope not in FAMILY_REPORT_SCOPES:
            await self._require_processing_owner(member)
        if not shared and (grant is None or grant.revoked_at is not None or scope not in grant.scopes):
            raise HealthVisionError("not_found", "资源不存在或无权访问", 404)
        return member

    async def list_members(self, uid: str):
        """供既有健康业务读取同一可见成员集合。"""
        return [member for member, _ in await self.list_member_access(uid)]

    async def list_member_access(self, uid: str):
        """家庭报告与独立授权合并列出，退出家庭后不返回残留关联。"""
        actor = aliased(SourceMember)
        shared = (
            select(HealthFamilyProfileLink.member_id)
            .join(SourceMember, SourceMember.id == HealthFamilyProfileLink.source_member_id)
            .join(FamilyArchive, FamilyArchive.id == HealthFamilyProfileLink.family_id)
            .join(actor, actor.family_id == FamilyArchive.id)
            .where(
                SourceMember.family_id == FamilyArchive.id,
                FamilyArchive.archived_at.is_(None),
                SourceMember.is_active.is_(True),
                actor.subject_uid == uid,
                actor.is_active.is_(True),
            )
        )
        linked = select(HealthFamilyProfileLink.member_id)
        records = await self.session.execute(
            select(FamilyMember, HealthGrant, FamilyMember.id.in_(shared))
            .outerjoin(HealthGrant, and_(HealthGrant.member_id == FamilyMember.id, HealthGrant.actor_uid == uid))
            .where(
                or_(
                    FamilyMember.id.in_(shared),
                    and_(
                        FamilyMember.id.not_in(linked), HealthGrant.actor_uid == uid, HealthGrant.revoked_at.is_(None)
                    ),
                )
            )
            .where(select(User.uid).where(User.uid == uid, User.is_deleted == 0).exists())
            .order_by(FamilyMember.created_at)
        )
        result = []
        for member, grant, shared_access in records:
            scopes = set(FAMILY_REPORT_SCOPES) if shared_access else set()
            if grant is not None and grant.revoked_at is None:
                scopes.update(scope for scope in grant.scopes if scope in HEALTH_SCOPES)
            result.append((member, scopes))
        return result

    async def visible_member_scopes(self, member_id: str, uid: str):
        """能力读取先证明有效账号与非空合法授权，不设管理员旁路。"""
        user = await self.session.scalar(select(User).where(User.uid == uid, User.is_deleted == 0))
        member = await self.session.get(FamilyMember, member_id)
        if user is None or member is None:
            raise HealthVisionError("not_found", "资源不存在或无权访问", 404)
        shared = await self._authorize_report_link(member_id, uid, lock=False)
        grant = await self.session.get(HealthGrant, (member_id, uid), populate_existing=True)
        scopes = set(FAMILY_REPORT_SCOPES) if shared else set()
        if grant is not None and grant.revoked_at is None:
            scopes.update(scope for scope in grant.scopes if scope in HEALTH_SCOPES)
        if scopes:
            return user, scopes
        raise HealthVisionError("not_found", "资源不存在或无权访问", 404)

    async def authorize_plan_members(self, anchor_id, uid, spec, scopes, *, lock=False):
        """所有参与者按ID持锁授权，不以入口成员替代其他成员。"""
        ids = plan_member_ids(anchor_id, spec)
        for member_id in ids:
            for index, scope in enumerate(scopes):
                await self.authorize(member_id, uid, scope, lock=lock and index == 0)
        return ids

    async def set_grant(self, member_id: str, uid: str, target_uid: str, scopes: list[str]):
        """只有建档人可改变授权，空 scope 撤回访问。"""
        member = await self.authorize(member_id, uid, "profile_edit", lock=True)
        if member.owner_uid != uid or not set(scopes) <= HEALTH_SCOPES:
            raise HealthVisionError("not_found", "资源不存在或无权访问", 404)
        await self._require_processing_owner(member)
        if not await self.session.scalar(select(User.uid).where(User.uid == target_uid, User.is_deleted == 0)):
            raise HealthVisionError("not_found", "资源不存在或无权访问", 404)
        grant = await self.session.get(HealthGrant, (member_id, target_uid))
        if grant is None:
            grant = HealthGrant(member_id=member_id, actor_uid=target_uid)
            self.session.add(grant)
        grant.scopes = scopes
        grant.revoked_at = None if scopes else utc_now_naive()

    async def require_consent(self, member_id: str, uid: str, purpose: str, snapshot: dict):
        """咨询沿用成员访问权限，其他处理用途仍核对当前同意。"""
        if purpose == "consultation":
            return
        consent = await self.session.get(HealthProcessingConsent, (member_id, uid, purpose), populate_existing=True)
        if (
            consent is None
            or consent.revoked_at is not None
            or consent.processor != snapshot["processor"]
            or consent.policy_version != snapshot["policy_version"]
        ):
            raise HealthVisionError("consent_required", "请先同意当前用途、处理方及政策", 403)

    async def processing_consent(self, member_id: str, uid: str, purpose: str):
        """读取当前账号的用途授权，不代替成员访问校验。"""
        return await self.session.get(HealthProcessingConsent, (member_id, uid, purpose), populate_existing=True)

    async def nutrition_inputs(self, meal):
        """只读取本人明确选择的已发布食品、菜谱与份量版本。"""
        food_ids = {str(item.food_id) for item in meal.items if item.food_id}
        food_ids.update(str(entry.food_id) for item in meal.items for entry in item.adjustments)
        inputs = []
        for model, ids in (
            (FoodRecord, food_ids),
            (RecipeVersion, {str(item.recipe_version_id) for item in meal.items if item.recipe_version_id}),
            (PortionReference, {str(item.portion_reference_id) for item in meal.items if item.portion_reference_id}),
        ):
            inputs.append(
                {row.id: row for row in (await self.session.scalars(select(model).where(model.id.in_(ids)))).all()}
            )
        return inputs

    async def upload(self, upload_id: str, uid: str, scope: str):
        """预览和删除从有效源对象授权。"""
        record = await self.session.get(PrivateUpload, upload_id, populate_existing=True)
        if record is None or record.status != "active":
            raise HealthVisionError("not_found", "文件不存在或无权访问", 404)
        await self.authorize(record.member_id, uid, scope)
        return record

    async def job(self, task_id: str, uid: str, *, write: bool = False):
        """读执行状态也逐次检查成员授权和源对象。"""
        job = await self.session.scalar(select(VisionJob).where(VisionJob.task_id == task_id))
        if job is None:
            raise HealthVisionError("not_found", "任务不存在或无权访问", 404)
        scope = (
            "profile_edit" if write and job.kind == "report" else "report_view" if job.kind == "report" else "diet_edit"
        )
        await self.authorize(job.member_id, uid, scope, lock=write)
        await self.active_uploads(job)
        return job

    async def active_uploads(self, job):
        """删除、跨成员或跨用途源文件不能产生新结果。"""
        records = []
        for upload_id in job.upload_ids:
            upload = await self.session.get(PrivateUpload, upload_id, populate_existing=True)
            if (
                upload is None
                or upload.status != "active"
                or upload.member_id != job.member_id
                or upload.purpose != job.kind
            ):
                raise HealthVisionError("source_invalidated", "源文件已删除或不可用", 410)
            records.append(upload)
        return records

    async def draft(self, draft_id: str, uid: str, kind: str, *, write: bool = False):
        """以成员行锁串行纠错、计算、确认和撤回。"""
        record = await self.session.get(VisionDraft, draft_id)
        if record is None or record.kind != kind:
            raise HealthVisionError("not_found", "草稿不存在或无权访问", 404)
        scope = "profile_edit" if write and kind == "report" else "report_view" if kind == "report" else "diet_edit"
        await self.authorize(record.member_id, uid, scope, lock=write)
        if write:
            record = await self.session.scalar(
                select(VisionDraft)
                .where(VisionDraft.id == draft_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        if record.job_id:
            await self.active_uploads(await self.session.get(VisionJob, record.job_id))
        return record

    async def find_job_request(self, uid: str, member_id: str, kind: str, request_id: str):
        """幂等键绑定账号、成员和操作。"""
        return await self.session.scalar(
            select(VisionJob).where(
                VisionJob.actor_uid == uid,
                VisionJob.member_id == member_id,
                VisionJob.kind == kind,
                VisionJob.request_id == request_id,
            )
        )

    async def has_active_report_reprocess(self, draft_id: str):
        """成员锁内检查同草稿活动任务，拒绝重复付费重识别。"""
        return (
            await self.session.scalar(
                select(VisionJob.id)
                .join(TaskRecord, TaskRecord.id == VisionJob.task_id)
                .where(
                    VisionJob.input_snapshot["reprocess"]["draft_id"].as_string() == draft_id,
                    TaskRecord.status.in_(["pending", "running"]),
                )
                .limit(1)
            )
            is not None
        )

    async def find_confirmation(self, uid: str, member_id: str, kind: str, request_id: str):
        """确认重放依赖唯一记录而不是客户端状态。"""
        return await self.session.scalar(
            select(VisionConfirmation).where(
                VisionConfirmation.actor_uid == uid,
                VisionConfirmation.member_id == member_id,
                VisionConfirmation.kind == kind,
                VisionConfirmation.request_id == request_id,
            )
        )

    async def list_jobs(self, member_id: str, *, kind: str | None = None, limit: int = 50, offset: int = 0):
        """最近任务与 Task 真实状态关联。"""
        stmt = (
            select(VisionJob, TaskRecord)
            .join(TaskRecord, TaskRecord.id == VisionJob.task_id)
            .where(VisionJob.member_id == member_id)
        )
        if kind is not None:
            stmt = stmt.where(VisionJob.kind == kind)
        return (
            await self.session.execute(
                stmt.order_by(VisionJob.created_at.desc(), VisionJob.id.asc()).limit(limit).offset(offset)
            )
        ).all()

    async def list_drafts(self, member_id: str, *, kind: str | None = None, limit: int = 50, offset: int = 0):
        """提供可刷新恢复的草稿列表。"""
        stmt = select(VisionDraft).where(VisionDraft.member_id == member_id)
        if kind is not None:
            stmt = stmt.where(VisionDraft.kind == kind)
        return list(
            (
                await self.session.scalars(
                    stmt.order_by(VisionDraft.created_at.desc(), VisionDraft.id.asc()).limit(limit).offset(offset)
                )
            ).all()
        )

    async def list_records(self, member_id: str, kind: str, *, limit: int = 100, offset: int = 0):
        """仅返回已提交的正式业务快照。"""
        model = HealthObservation if kind == "report" else DietLog
        return list(
            (
                await self.session.scalars(
                    select(model)
                    .where(model.member_id == member_id)
                    .order_by(model.created_at.desc(), model.id.asc())
                    .limit(limit)
                    .offset(offset)
                )
            ).all()
        )

    async def foods(self, query: str):
        """只从已审核的版本检索，不按模型名称自动映射。"""
        return list(
            (
                await self.session.scalars(
                    select(FoodRecord)
                    .where(FoodRecord.name.contains(query, autoescape=True))
                    .order_by(FoodRecord.name)
                    .limit(50)
                )
            ).all()
        )

    async def recipes(self, query: str):
        """文字按字面匹配已发布配方，不把通配符当查询语法。"""
        return list(
            (
                await self.session.scalars(
                    select(RecipeVersion)
                    .where(RecipeVersion.name.contains(query, autoescape=True))
                    .order_by(RecipeVersion.name)
                    .limit(100)
                )
            ).all()
        )

    async def has_published_recipes(self):
        """发布目录存在性不证明任何菜谱适用于当前成员。"""
        return await self.session.scalar(select(RecipeVersion.id).limit(1)) is not None

    async def has_published_nutrition(self):
        """只表达已发布营养目录存在，不证明所选食材和份量可计算。"""
        return await self.session.scalar(select(FoodRecord.id).limit(1)) is not None

    async def portions(self, food_id: str | None, recipe_version_id: str | None):
        """返回与指定不可变版本关联的参考规格。"""
        condition = (
            PortionReference.food_id == food_id if food_id else PortionReference.recipe_version_id == recipe_version_id
        )
        return list(
            (
                await self.session.scalars(
                    select(PortionReference).where(condition).order_by(PortionReference.unit_label).limit(100)
                )
            ).all()
        )

    async def task_counts(self, uid: str, member_id: str):
        """额度从数据库事实计算，并由创建事务的锁串行校验。"""
        today = utc_now_naive().replace(hour=0, minute=0, second=0, microsecond=0)
        rejected = aliased(VisionJob)
        unused_report_failures = (
            select(rejected.id)
            .join(TaskRecord, TaskRecord.id == rejected.task_id)
            .where(
                rejected.kind == "report",
                rejected.error_code == "budget_price_unavailable",
                TaskRecord.status == "failed",
                or_(
                    rejected.input_snapshot["provider_jobs"].as_string().is_(None),
                    rejected.input_snapshot["provider_jobs"].as_string() == "[]",
                ),
                ~select(HealthAiCall.id).where(HealthAiCall.owner_id == rejected.task_id).exists(),
            )
        )
        # 配置在外呼前拒绝的报告不消耗识别次数；任何 OCR 受理或模型预留仍计数。
        counted = (
            select(func.count())
            .select_from(VisionJob)
            .where(VisionJob.created_at >= today, VisionJob.id.not_in(unused_report_failures))
        )
        active = await self.session.scalar(
            select(func.count())
            .select_from(VisionJob)
            .join(TaskRecord, TaskRecord.id == VisionJob.task_id)
            .where(VisionJob.member_id == member_id, TaskRecord.status.in_(["pending", "running"]))
        )
        daily = await self.session.scalar(counted.where(VisionJob.actor_uid == uid))
        total = await self.session.scalar(counted)
        return int(active or 0), int(daily or 0), int(total or 0)

    async def statistics_sources(self, member_id: str, kind: str, start, end):
        """读取完整窗口及当前有效源，不以最近列表充当统计样本。"""
        active_uploads = set(
            (
                await self.session.scalars(
                    select(PrivateUpload.id).where(
                        PrivateUpload.member_id == member_id,
                        PrivateUpload.purpose == kind,
                        PrivateUpload.status == "active",
                    )
                )
            ).all()
        )

        def source_visible(upload_ids):
            """空源仅用于人工草稿；识图任务必须仍有有效源。"""
            return bool(upload_ids) and all(upload_id in active_uploads for upload_id in upload_ids)

        tasks = (
            (
                await self.session.execute(
                    select(
                        VisionJob.upload_ids,
                        VisionJob.error_code,
                        VisionJob.phase,
                        TaskRecord.status,
                        TaskRecord.created_at,
                        TaskRecord.started_at,
                        TaskRecord.completed_at,
                        TaskRecord.result,
                    )
                    .join(TaskRecord, TaskRecord.id == VisionJob.task_id)
                    .where(
                        VisionJob.member_id == member_id,
                        VisionJob.kind == kind,
                        TaskRecord.created_at >= start,
                        TaskRecord.created_at < end,
                    )
                )
            )
            .mappings()
            .all()
        )
        reviews = (
            (
                await self.session.execute(
                    select(
                        VisionDraft.original_payload,
                        VisionDraft.payload,
                        VisionDraft.job_id,
                        VisionJob.upload_ids,
                        DietLog.snapshot,
                    )
                    .select_from(VisionDraft)
                    .join(VisionConfirmation, VisionConfirmation.draft_id == VisionDraft.id)
                    .outerjoin(VisionJob, VisionJob.id == VisionDraft.job_id)
                    .outerjoin(DietLog, DietLog.confirmation_id == VisionConfirmation.id)
                    .where(
                        VisionDraft.member_id == member_id,
                        VisionDraft.kind == kind,
                        VisionDraft.review_status == "confirmed",
                        VisionConfirmation.created_at >= start,
                        VisionConfirmation.created_at < end,
                    )
                )
            )
            .mappings()
            .all()
        )
        return (
            [row for row in tasks if source_visible(row["upload_ids"])],
            [row for row in reviews if row["job_id"] is None or source_visible(row["upload_ids"])],
        )

    async def _require_processing_owner(self, member):
        """代建报告不授予他人的处理权，旧关联同样核对当前本人或监护身份。"""
        from yuxi.services.family_service import guardian_active

        link = await self.session.get(HealthFamilyProfileLink, member.id, populate_existing=True)
        if link is None:
            return
        family = await self.session.get(FamilyArchive, link.family_id, populate_existing=True)
        source = await self.session.get(SourceMember, link.source_member_id, populate_existing=True)
        if (
            family is None
            or family.archived_at is not None
            or source is None
            or not source.is_active
            or member.owner_uid != link.actor_uid
            or source.subject_uid != link.actor_uid
            and not guardian_active(source, link.actor_uid)
        ):
            raise HealthVisionError("not_found", "资源不存在或无权访问", 404)

    async def _authorize_report_link(self, member_id: str, uid: str, *, lock: bool):
        """报告沿用有效家庭成员关系；家庭锁先于健康成员锁。"""
        link = await self.session.get(HealthFamilyProfileLink, member_id, populate_existing=True)
        if link is None:
            return False
        family_query = select(FamilyArchive).where(
            FamilyArchive.id == link.family_id, FamilyArchive.archived_at.is_(None)
        )
        if lock:
            family_query = family_query.with_for_update()
        family = await self.session.scalar(family_query)
        source = await self.session.get(SourceMember, link.source_member_id, populate_existing=True)
        actor = await self.session.scalar(
            select(SourceMember.id)
            .where(
                SourceMember.family_id == link.family_id,
                SourceMember.subject_uid == uid,
                SourceMember.is_active.is_(True),
            )
            .limit(1)
        )
        if (
            family is None
            or source is None
            or source.family_id != link.family_id
            or not source.is_active
            or actor is None
        ):
            raise HealthVisionError("not_found", "报告档案当前不存在或无权访问", 404)
        return True

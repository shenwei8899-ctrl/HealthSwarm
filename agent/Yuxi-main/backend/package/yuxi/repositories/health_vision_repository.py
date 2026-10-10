"""健康领域查询及成员授权边界；事务由 service 拥有。"""

from sqlalchemy import func, select

from yuxi.services.health_vision_types import HEALTH_SCOPES, HealthVisionError
from yuxi.services.health_family_meal_plan_types import plan_member_ids
from yuxi.storage.postgres.models_business import TaskRecord, User
from yuxi.storage.postgres.models_health import (
    DietLog,
    FamilyMember,
    FoodRecord,
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


class HealthVisionRepository:
    """所有私有资源从成员 grant 查询，不授予管理员旁路。"""

    def __init__(self, session):
        self.session = session

    async def authorize(self, member_id: str, uid: str, scope: str, *, lock: bool = False):
        """写用例先锁成员，使撤回和写入按同一边界排序。"""
        stmt = select(FamilyMember).where(FamilyMember.id == member_id)
        if lock:
            stmt = stmt.with_for_update()
        member = await self.session.scalar(stmt)
        grant = await self.session.get(HealthGrant, (member_id, uid), populate_existing=True)
        user = await self.session.scalar(select(User).where(User.uid == uid, User.is_deleted == 0))
        if member is None or user is None or grant is None or grant.revoked_at is not None or scope not in grant.scopes:
            raise HealthVisionError("not_found", "资源不存在或无权访问", 404)
        return member

    async def list_members(self, uid: str):
        """只展示有当前有效授权的成员。"""
        return list(
            (
                await self.session.scalars(
                    select(FamilyMember)
                    .join(HealthGrant, HealthGrant.member_id == FamilyMember.id)
                    .where(HealthGrant.actor_uid == uid, HealthGrant.revoked_at.is_(None))
                    .order_by(FamilyMember.created_at)
                )
            ).all()
        )

    async def visible_member_scopes(self, member_id: str, uid: str):
        """能力读取先证明有效账号与非空合法授权，不设管理员旁路。"""
        row = (
            await self.session.execute(
                select(User, HealthGrant.scopes)
                .join(HealthGrant, HealthGrant.actor_uid == User.uid)
                .join(FamilyMember, FamilyMember.id == HealthGrant.member_id)
                .where(
                    User.uid == uid,
                    User.is_deleted == 0,
                    FamilyMember.id == member_id,
                    HealthGrant.revoked_at.is_(None),
                )
            )
        ).one_or_none()
        if row is not None:
            user, scopes = row
            if isinstance(scopes, list) and scopes and all(isinstance(s, str) and s in HEALTH_SCOPES for s in scopes):
                return user, set(scopes)
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
        if not await self.session.scalar(select(User.uid).where(User.uid == target_uid, User.is_deleted == 0)):
            raise HealthVisionError("not_found", "资源不存在或无权访问", 404)
        grant = await self.session.get(HealthGrant, (member_id, target_uid))
        if grant is None:
            grant = HealthGrant(member_id=member_id, actor_uid=target_uid)
            self.session.add(grant)
        grant.scopes = scopes
        grant.revoked_at = None if scopes else utc_now_naive()

    async def require_consent(self, member_id: str, uid: str, purpose: str, snapshot: dict):
        """处理方或政策变化必须重新同意。"""
        consent = await self.session.get(HealthProcessingConsent, (member_id, uid, purpose), populate_existing=True)
        if (
            consent is None
            or consent.revoked_at is not None
            or consent.processor != snapshot["processor"]
            or consent.policy_version != snapshot["policy_version"]
        ):
            raise HealthVisionError("consent_required", "请先同意当前用途、处理方及政策", 403)

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

    async def list_jobs(self, member_id: str):
        """最近任务与 Task 真实状态关联。"""
        return (
            await self.session.execute(
                select(VisionJob, TaskRecord)
                .join(TaskRecord, TaskRecord.id == VisionJob.task_id)
                .where(VisionJob.member_id == member_id)
                .order_by(VisionJob.created_at.desc())
                .limit(50)
            )
        ).all()

    async def list_drafts(self, member_id: str):
        """提供可刷新恢复的草稿列表。"""
        return list(
            (
                await self.session.scalars(
                    select(VisionDraft)
                    .where(VisionDraft.member_id == member_id)
                    .order_by(VisionDraft.created_at.desc())
                    .limit(50)
                )
            ).all()
        )

    async def list_records(self, member_id: str, kind: str):
        """仅返回已提交的正式业务快照。"""
        model = HealthObservation if kind == "report" else DietLog
        return list(
            (
                await self.session.scalars(
                    select(model).where(model.member_id == member_id).order_by(model.created_at.desc()).limit(100)
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
        active = await self.session.scalar(
            select(func.count())
            .select_from(VisionJob)
            .join(TaskRecord, TaskRecord.id == VisionJob.task_id)
            .where(VisionJob.member_id == member_id, TaskRecord.status.in_(["pending", "running"]))
        )
        daily = await self.session.scalar(
            select(func.count()).select_from(VisionJob).where(VisionJob.actor_uid == uid, VisionJob.created_at >= today)
        )
        total = await self.session.scalar(
            select(func.count()).select_from(VisionJob).where(VisionJob.created_at >= today)
        )
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

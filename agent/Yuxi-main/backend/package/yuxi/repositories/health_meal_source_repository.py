"""记餐资料沿用固定角色绑定和当前账号的知识库读取权限。"""

import os
import re

from sqlalchemy import or_, select

from yuxi.permissions import ResourcePermission, resolve_knowledge_base_permission
from yuxi.repositories.health_vision_repository import HealthVisionRepository
from yuxi.services.health_vision_types import HealthVisionError, MealItem
from yuxi.services.health_source_types import knowledge_source_reference, parse_knowledge_source
from yuxi.storage.postgres.models_business import User
from yuxi.storage.postgres.models_knowledge import KnowledgeBase, KnowledgeChunk, KnowledgeFile
from yuxi.storage.postgres.models_health import VisionJob


class HealthMealSourceRepository:
    """仅读取本次查询命中的完整分片，不发布或修改专业数据。"""

    def __init__(self, session):
        """来源读取与确认共用用例事务。"""
        self.session = session

    async def bases(self, uid, *, lock=False):
        """角色绑定之外的私有库仍须已有读取权，不按名称推断授权。"""
        user = await self.session.scalar(select(User).where(User.uid == uid, User.is_deleted == 0))
        if user is None:
            raise HealthVisionError("not_found", "账号不存在或无权访问", 404)
        fixed = {os.getenv(key, "").strip() for key in ("HEALTH_FAMILY_NUTRITION_KB_ID", "HEALTH_RECIPE_KB_ID")}
        stmt = select(KnowledgeBase).order_by(KnowledgeBase.kb_id)
        if lock:
            stmt = stmt.with_for_update(read=True)
        return [
            base.kb_id
            for base in (await self.session.scalars(stmt)).all()
            if base.kb_id in fixed or resolve_knowledge_base_permission(user, base) != ResourcePermission.NONE
        ]

    async def search(self, uid, query):
        """按标题字面检索，正文含菜名但主题不同的文档不自动匹配。"""
        ids = await self.bases(uid)
        archives = await self.bound_archives()
        derived = [
            select(KnowledgeChunk.file_id).where(
                KnowledgeChunk.content.contains("原有资料定位：" + reference, autoescape=True)
            )
            for reference in archives
        ]
        return list(
            (
                await self.session.scalars(
                    select(KnowledgeFile)
                    .where(
                        or_(KnowledgeFile.kb_id.in_(ids), *(KnowledgeFile.file_id.in_(stmt) for stmt in derived)),
                        KnowledgeFile.is_folder.is_(False),
                        KnowledgeFile.status.in_(["indexed", "done"]),
                        KnowledgeFile.content_hash.is_not(None),
                        KnowledgeFile.file_size > 0,
                        KnowledgeFile.filename.icontains(query, autoescape=True),
                    )
                    .order_by(KnowledgeFile.filename, KnowledgeFile.file_id)
                    .limit(60)
                )
            ).all()
        )

    async def document(self, uid, kb_id, file_id, *, lock=False):
        """每次消费重验库、文件归属与分片版本，确认时持共享锁。"""
        direct = kb_id in await self.bases(uid, lock=lock)
        stmt = select(KnowledgeFile).where(KnowledgeFile.kb_id == kb_id, KnowledgeFile.file_id == file_id)
        if lock:
            stmt = stmt.with_for_update(read=True)
        file = await self.session.scalar(stmt.execution_options(populate_existing=True))
        if (
            file is None
            or file.is_folder
            or not file.file_size
            or not file.content_hash
            or file.status not in {"indexed", "done"}
        ):
            raise HealthVisionError("meal_source_unavailable", "营养原件已不可用，请重新匹配", 409)
        chunks = (
            select(KnowledgeChunk)
            .where(
                KnowledgeChunk.kb_id == kb_id,
                KnowledgeChunk.file_id == file_id,
            )
            .order_by(KnowledgeChunk.chunk_index, KnowledgeChunk.chunk_id)
        )
        if lock:
            chunks = chunks.with_for_update(read=True)
        rows = list((await self.session.scalars(chunks.execution_options(populate_existing=True))).all())
        content = "\n".join(row.content for row in rows)
        if not rows or len(content) > 500000:
            raise HealthVisionError("meal_source_unavailable", "资料缺少可解析的营养正文", 409)
        parent_source = None
        if not direct:
            # 只使用已绑定原始归档的同一管理者制作的索引卡，不开放该私有库其余资料。
            parents = await self.bound_archives(lock=lock)
            match = re.search(r"(?m)^- 原有资料定位：(knowledge://[^\s]+)\s*$", content)
            parent_source = match.group(1) if match else None
            parent = parents.get(parent_source)
            base = await self.session.scalar(select(KnowledgeBase).where(KnowledgeBase.kb_id == kb_id))
            if (
                not parent
                or not parent.created_by
                or file.created_by != parent.created_by
                or base.created_by != parent.created_by
            ):
                raise HealthVisionError("meal_source_unavailable", "营养来源不存在或无权使用，请重新匹配", 409)
            parse_knowledge_source(parent_source)
        return file, content, parent_source

    async def bound_archives(self, *, lock=False):
        """派生卡只继承当前固定库内有摘要的原始归档范围。"""
        ids = [os.getenv(key, "").strip() for key in ("HEALTH_FAMILY_NUTRITION_KB_ID", "HEALTH_RECIPE_KB_ID")]
        stmt = (
            select(KnowledgeFile)
            .join(KnowledgeBase, KnowledgeBase.kb_id == KnowledgeFile.kb_id)
            .where(
                KnowledgeFile.kb_id.in_(ids),
                KnowledgeFile.is_folder.is_(False),
                KnowledgeFile.filename.iendswith(".zip"),
                KnowledgeFile.content_hash.is_not(None),
                KnowledgeFile.file_size > 0,
            )
            .order_by(KnowledgeFile.kb_id, KnowledgeFile.file_id)
        )
        if lock:
            stmt = stmt.with_for_update(read=True, of=KnowledgeFile)
        return {
            knowledge_source_reference(row.kb_id, row.file_id, row.content_hash): row
            for row in (await self.session.scalars(stmt.execution_options(populate_existing=True))).all()
        }

    async def require_snapshot_access(self, uid, sources, *, meal=None):
        """历史数值保留当时版本，私有原件的当前读取范围仍须有效。"""
        for source in sources:
            if source.get("photo_estimate"):
                await self.photo_estimate(
                    uid,
                    MealItem.model_validate(
                        {
                            "item_id": source["item_id"],
                            "name": source["name"],
                            "photo_estimate": source["photo_estimate"],
                        }
                    ),
                )
        for item in (meal or {}).get("items", []):
            if item.get("photo_estimate"):
                await self.photo_estimate(uid, MealItem.model_validate(item))
        references = [source for source in sources if source.get("nutrition_source")]
        if not references:
            return
        ids, parents = await self.bases(uid), await self.bound_archives()
        for source in references:
            kb, fid, _ = parse_knowledge_source(source["nutrition_source"]["reference"])
            file = await self.session.scalar(
                select(KnowledgeFile).where(KnowledgeFile.kb_id == kb, KnowledgeFile.file_id == fid)
            )
            if file is None or file.is_folder:
                raise HealthVisionError("source_invalidated", "餐次营养原件已不可读取", 410)
            if kb in ids:
                continue
            parent = parents.get(source.get("parent_source"))
            base = await self.session.scalar(select(KnowledgeBase).where(KnowledgeBase.kb_id == kb))
            if (
                not parent
                or not parent.created_by
                or file.created_by != parent.created_by
                or base.created_by != parent.created_by
            ):
                raise HealthVisionError("source_invalidated", "餐次营养资料授权已变化", 410)

    async def photo_estimate(self, uid, item, *, lock=False):
        """从有效照片的原始结果取值，跨成员复制仍须拥有源成员读取权。"""
        estimate = item.photo_estimate
        if estimate is None or estimate.draft_id is None:
            raise HealthVisionError("meal_estimate_invalid", "照片估计缺少有效来源，请重新识别", 422)
        draft = await HealthVisionRepository(self.session).draft(str(estimate.draft_id), uid, "meal", write=lock)
        job = await self.session.get(VisionJob, draft.job_id) if draft.job_id else None
        if (
            job is None
            or not job.upload_ids
            or job.result_id != draft.id
            or job.phase != "ready"
            or draft.review_status not in {"pending_confirmation", "confirmed"}
        ):
            raise HealthVisionError("source_invalidated", "照片估计来源已失效，请重新识别", 410)
        original = next(
            (row for row in draft.original_payload.get("items", []) if row["item_id"] == str(item.item_id)), None
        )
        original = MealItem.model_validate(original) if original else None
        if original is None or original.name != item.name or original.photo_estimate != estimate:
            raise HealthVisionError("meal_estimate_changed", "菜品或原始估计已变化，请重新识别或匹配资料", 409)
        return original.photo_estimate, draft.model_version, job.input_snapshot.get("prompt_version")

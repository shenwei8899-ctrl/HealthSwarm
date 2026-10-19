"""知识库原件在营养发布和消费事务中的当前状态。"""

from sqlalchemy import select, tuple_

from yuxi.permissions import ResourcePermission, resolve_knowledge_base_permission
from yuxi.services.health_source_types import knowledge_source_reference, parse_knowledge_source
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.storage.postgres.models_business import User
from yuxi.storage.postgres.models_knowledge import KnowledgeBase, KnowledgeFile


class HealthSourceRepository:
    """复用用例事务和知识库权限，不复制原始资料。"""

    def __init__(self, session):
        """来源锁持续到调用方完成发布或读取。"""
        self.session = session

    async def document_reference(self, uid, kb_id, file_id):
        """只有可管理该知识库的管理员能将原件登记为公开专业数据来源。"""
        user = await self.session.scalar(select(User).where(User.uid == uid, User.is_deleted == 0))
        base = await self.session.scalar(
            select(KnowledgeBase).where(KnowledgeBase.kb_id == kb_id).with_for_update(read=True)
        )
        if (
            user is None
            or user.role not in {"admin", "superadmin"}
            or base is None
            or resolve_knowledge_base_permission(user, base) != ResourcePermission.MANAGE
        ):
            raise HealthVisionError("source_access_required", "需要该知识库的资料管理权限", 403)
        file = await self.session.scalar(
            select(KnowledgeFile)
            .where(KnowledgeFile.kb_id == kb_id, KnowledgeFile.file_id == file_id)
            .with_for_update(read=True)
        )
        if file is None or file.is_folder or not file.content_hash or not file.file_size:
            raise HealthVisionError("knowledge_source_unavailable", "原始资料不存在或缺少内容摘要", 409)
        return {
            "source_ref": knowledge_source_reference(kb_id, file_id, file.content_hash),
            "kb_id": kb_id,
            "file_id": file_id,
            "filename": file.filename,
            "content_hash": file.content_hash,
            "status": file.status,
            "professional_approval": False,
        }

    async def require_publication_source(self, uid, value):
        """替代发布入口同样核对管理权、归属与用户选定摘要。"""
        parsed = parse_knowledge_source(value)
        if parsed is None:
            return
        current = await self.document_reference(uid, parsed[0], parsed[1])
        if current["source_ref"] != value:
            raise HealthVisionError("knowledge_source_changed", "原始资料已变化，请重新核对并选择", 409)

    async def current_sources(self, values):
        """公开业务仅检查已发布引用的原件状态，不暴露原件正文或绕过知识库读取权。"""
        result = {}
        linked = {}
        for value in sorted(set(values)):
            try:
                parsed = parse_knowledge_source(value)
            except HealthVisionError:
                result[value] = False
                continue
            if parsed is None:
                result[value] = True
                continue
            linked[value] = parsed
        if not linked:
            return result
        pairs = sorted({(kb, file) for kb, file, _ in linked.values()})
        files = {
            (file.kb_id, file.file_id): file
            for file in (
                await self.session.scalars(
                    select(KnowledgeFile)
                    .join(KnowledgeBase, KnowledgeBase.kb_id == KnowledgeFile.kb_id)
                    .where(tuple_(KnowledgeFile.kb_id, KnowledgeFile.file_id).in_(pairs))
                    .order_by(KnowledgeFile.kb_id, KnowledgeFile.file_id)
                    .with_for_update(read=True, of=KnowledgeFile)
                )
            ).all()
        }
        for value, (kb_id, file_id, digest) in linked.items():
            file = files.get((kb_id, file_id))
            result[value] = bool(file and not file.is_folder and file.file_size and file.content_hash == digest)
        return result

    async def require_current_sources(self, values):
        """计算和正式确认再次检查来源，历史记录保留当时快照。"""
        if not all((await self.current_sources(values)).values()):
            raise HealthVisionError("knowledge_source_changed", "知识库来源已变化或不可用，请重新核对", 409)

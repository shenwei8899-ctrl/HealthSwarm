"""采购仅读取所选菜谱的数据库版本，不下载展示原件。"""

from sqlalchemy import select

from yuxi.storage.postgres.models_knowledge import KnowledgeChunk, KnowledgeFile


async def recipe_version(session, file_id, kb_ids):
    """在当前角色绑定库内读取文件和有序分片版本。"""
    file = await session.scalar(
        select(KnowledgeFile).where(KnowledgeFile.file_id == file_id, KnowledgeFile.kb_id.in_(kb_ids))
    )
    if file is None:
        return None, []
    chunks = list(
        (
            await session.scalars(
                select(KnowledgeChunk)
                .where(KnowledgeChunk.file_id == file.file_id, KnowledgeChunk.kb_id == file.kb_id)
                .order_by(KnowledgeChunk.chunk_index, KnowledgeChunk.id)
            )
        ).all()
    )
    return file, chunks

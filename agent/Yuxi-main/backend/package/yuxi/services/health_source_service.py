"""为专业资料发布提供当前知识库原件引用。"""

from yuxi.repositories.health_source_repository import HealthSourceRepository
from yuxi.storage.postgres.manager import pg_manager


async def read_nutrition_source(uid, kb_id, file_id):
    """普通管理读取不触发模型、解析或专业批准。"""
    async with pg_manager.get_async_session_context() as session:
        return await HealthSourceRepository(session).document_reference(uid, kb_id, file_id)

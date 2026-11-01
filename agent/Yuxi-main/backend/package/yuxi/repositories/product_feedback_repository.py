"""产品意见的账号归属、提交互斥和分页查询。"""

from sqlalchemy import select, text

from yuxi.storage.postgres.models_business import ProductFeedback


class ProductFeedbackRepository:
    """由调用服务拥有事务，提交锁覆盖对象上传与最终数据库写入。"""

    def __init__(self, db):
        self.db = db

    async def locked(self, feedback_id):
        """相同提交编号串行处理，避免并发上传覆盖或重复提交。"""
        await self.db.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
            {"key": "product-feedback:" + feedback_id},
        )
        return await self.get(feedback_id)

    async def get(self, feedback_id):
        """读取反馈记录，访问权限由服务在返回数据前执行。"""
        return await self.db.get(ProductFeedback, feedback_id, populate_existing=True)

    async def create(self, feedback_id, user_id):
        """在已持有编号锁的事务内创建草稿。"""
        row = ProductFeedback(id=feedback_id, user_id=user_id, images=[], status="draft")
        self.db.add(row)
        await self.db.flush()
        return row

    async def submitted(self, offset, limit):
        """管理入口仅列出已提交意见。"""
        rows = await self.db.scalars(
            select(ProductFeedback)
            .where(ProductFeedback.status == "submitted")
            .order_by(ProductFeedback.submitted_at.desc(), ProductFeedback.id)
            .offset(offset)
            .limit(limit)
        )
        return list(rows)

"""选中文字引用的正式消息与模型输入依赖查询。"""

from sqlalchemy import or_, select

from yuxi.storage.postgres.models_business import Message


class HealthReplyQuoteRepository:
    """引用共享锁保留到调用者拥有的发布事务结束。"""

    def __init__(self, session):
        self.session = session

    async def source(self, conversation_id, quote):
        """按已授权会话及唯一来源定位正式助手消息。"""
        statement = select(Message).where(Message.conversation_id == conversation_id, Message.role == "assistant")
        if quote.source_message_id is not None:
            statement = statement.where(Message.id == quote.source_message_id)
        else:
            statement = statement.where(Message.request_id == str(quote.source_request_id))
        return list(await self.session.scalars(statement.with_for_update(read=True)))

    async def context_quotes(self, run):
        """当前输入及其之前的引用均属于本线程可见模型历史。"""
        messages = await self.session.scalars(
            select(Message)
            .where(
                Message.conversation_id == run.conversation_id,
                Message.role == "user",
                Message.id <= run.input_message_id,
                or_(
                    Message.id == run.input_message_id,
                    Message.delivery_status.not_in(("queued", "cancelled", "rejected")),
                ),
            )
            .order_by(Message.id)
        )
        return [
            message.extra_metadata["reply_quote"]
            for message in messages
            if isinstance(message.extra_metadata, dict) and message.extra_metadata.get("reply_quote")
        ]

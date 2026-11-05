"""对话记餐来源和回执查询，事务与授权由用例持有。"""

from sqlalchemy import cast, select
from sqlalchemy.dialects.postgresql import JSONB

from yuxi.storage.postgres.models_business import Message
from yuxi.storage.postgres.models_health import DietLog, VisionConfirmation


class HealthChatMealRepository:
    """复用饮食确认和记录元数据，不建立第二套饮食事实。"""

    def __init__(self, session):
        """接收用例拥有的事务。"""
        self.session = session

    async def user_sources(self, run, current):
        """最多六条当前及此前用户消息，排除排队的后续请求。"""
        rows = list(
            (
                await self.session.scalars(
                    select(Message)
                    .where(
                        Message.conversation_id == run.conversation_id,
                        Message.role == "user",
                        Message.created_at < current.created_at,
                        Message.delivery_status.notin_(["queued", "cancelled", "rejected"]),
                    )
                    .order_by(Message.created_at.desc(), Message.id.desc())
                    .limit(5)
                )
            ).all()
        )
        return [*reversed(rows), current]

    async def receipts(self, uid, reference):
        """按服务器线程或请求引用返回本账号的真实记餐记录。"""
        return list(
            (
                await self.session.scalars(
                    select(DietLog)
                    .join(VisionConfirmation, VisionConfirmation.id == DietLog.confirmation_id)
                    .where(
                        VisionConfirmation.actor_uid == uid,
                        DietLog.snapshot["recording"]["source"].as_string() == "chat_actual_intake",
                        cast(DietLog.snapshot["recording"]["references"], JSONB).contains([reference]),
                    )
                    .order_by(DietLog.created_at, DietLog.id)
                )
            ).all()
        )

"""每日健康会话、摘要来源与 worker 扫描查询。"""

from sqlalchemy import or_, select

from yuxi.repositories.agent_run_repository import TERMINAL_RUN_STATUSES
from yuxi.storage.postgres.models_business import AgentRun, AgentRunRequest, Conversation, Message, Project
from yuxi.storage.postgres.models_health import HealthDailyConversation
from yuxi.repositories.health_memory_repository import HealthMemoryRepository
from yuxi.repositories.health_meal_feedback_repository import HealthMealFeedbackRepository


class HealthDailyRepository:
    """查询复用私有会话及项目归属；不建立家庭共享执行线程。"""

    def __init__(self, session):
        self.session = session

    async def for_scope(self, uid, member_id, day):
        """唯一日键与成员锁共同防止并发重复创建。"""
        return await self.session.scalar(
            select(HealthDailyConversation).where(
                HealthDailyConversation.actor_uid == uid,
                HealthDailyConversation.member_id == member_id,
                HealthDailyConversation.business_date == day,
            )
        )

    async def for_thread(self, uid, thread_id):
        """读取当前账号线程的日归属，不接受客户端日期覆盖。"""
        return await self.session.scalar(
            select(HealthDailyConversation)
            .join(
                Conversation,
                Conversation.id == HealthDailyConversation.conversation_id,
            )
            .where(
                HealthDailyConversation.actor_uid == uid, Conversation.uid == uid, Conversation.thread_id == thread_id
            )
        )

    async def history(self, uid, member_id, before=None):
        """按日期分页只读取当前仍可见的私有会话。"""
        stmt = self.visible().where(
            HealthDailyConversation.actor_uid == uid, HealthDailyConversation.member_id == member_id
        )
        if before is not None:
            stmt = stmt.where(HealthDailyConversation.business_date < before)
        return list(
            (await self.session.execute(stmt.order_by(HealthDailyConversation.business_date.desc()).limit(30))).all()
        )

    def visible(self):
        """当前 Conversation 与 Project 是可见性的事实 Owner。"""
        return (
            select(HealthDailyConversation, Conversation.thread_id)
            .join(
                Conversation,
                Conversation.id == HealthDailyConversation.conversation_id,
            )
            .join(Project, Project.id == Conversation.project_id)
            .where(
                Conversation.status == "active",
                Project.status == "active",
                Conversation.uid == HealthDailyConversation.actor_uid,
                Project.uid == HealthDailyConversation.actor_uid,
            )
        )

    async def due(self, today):
        """按上次扫描时间轮转，避免已生成的日期饿死历史补跑。"""
        return list(
            (
                await self.session.execute(
                    self.visible()
                    .where(HealthDailyConversation.business_date < today)
                    .order_by(
                        HealthDailyConversation.summary_checked_at.asc().nullsfirst(),
                        HealthDailyConversation.business_date,
                    )
                    .limit(100)
                )
            ).all()
        )

    async def source_messages(self, daily, thread_id):
        """未结束请求先等待，失败 Run 和被撤回的记忆来源不入摘要。"""
        pending = await self.session.scalar(
            select(AgentRunRequest.id)
            .outerjoin(
                AgentRun,
                AgentRun.request_id == AgentRunRequest.request_id,
            )
            .where(
                AgentRunRequest.conversation_thread_id == thread_id,
                or_(
                    AgentRunRequest.status == "queued",
                    (AgentRunRequest.status == "dispatched")
                    & or_(AgentRun.id.is_(None), AgentRun.status.notin_(TERMINAL_RUN_STATUSES)),
                ),
            )
            .limit(1)
        )
        if pending is not None:
            return None
        suppressed = HealthMemoryRepository(self.session).invalid_requests(daily.actor_uid, daily.member_id)
        feedback_suppressed = await HealthMealFeedbackRepository(self.session).invalid_requests(
            daily.actor_uid, daily.member_id
        )
        return list(
            (
                await self.session.scalars(
                    select(Message)
                    .join(
                        AgentRun,
                        AgentRun.request_id == Message.request_id,
                    )
                    .where(
                        Message.conversation_id == daily.conversation_id,
                        AgentRun.status == "completed",
                        Message.role.in_(("user", "assistant")),
                        Message.message_type == "text",
                        Message.delivery_status == "complete",
                        Message.content != "",
                        Message.request_id.notin_(suppressed),
                        Message.request_id.notin_(feedback_suppressed),
                    )
                    .order_by(Message.id.desc())
                    .limit(1001)
                )
            ).all()
        )

"""对话购包复用现有 Run、最终消息和本人档案，不建立第二份执行状态。"""

from sqlalchemy import select

from yuxi.storage.postgres.models_business import (
    FamilyMember,
    AgentRun,
    Message,
    TOOL_AUDIT_MESSAGE_TYPE,
)
from yuxi.storage.postgres.models_health import HealthFamilyProfileLink


class ConversationPurchaseRepository:
    """购买来源固定到咨询绑定的本人成员。"""

    def __init__(self, session):
        """沿用调用方事务。"""
        self.session = session

    async def source_member(self, member_id, uid, *, lock=False):
        """只读当前本人已关联的来源，不能从客户端更换家庭或成员。"""
        stmt = (
            select(FamilyMember)
            .join(
                HealthFamilyProfileLink,
                HealthFamilyProfileLink.source_member_id == FamilyMember.id,
            )
            .where(
                HealthFamilyProfileLink.member_id == member_id,
                HealthFamilyProfileLink.actor_uid == uid,
                FamilyMember.subject_uid == uid,
                FamilyMember.is_active.is_(True),
            )
        )
        if lock:
            stmt = stmt.with_for_update(of=FamilyMember)
        return await self.session.scalar(stmt)

    async def catalog_profile_payloads(
        self, binding, *, run_id=None, tool_names=("find_food_packages", "select_food_products")
    ):
        """只取同本人咨询中的已完成真实商品工具审计。"""
        stmt = (
            select(Message.content)
            .join(AgentRun, AgentRun.id == Message.run_id)
            .where(
                AgentRun.uid == binding.actor_uid,
                AgentRun.conversation_id == binding.conversation_id,
                Message.conversation_id == binding.conversation_id,
                Message.role == "tool",
                Message.message_type == TOOL_AUDIT_MESSAGE_TYPE,
                Message.execution_status == "completed",
                Message.extra_metadata["tool_name"].as_string().in_(tool_names),
            )
        )
        if run_id is not None:
            stmt = stmt.where(AgentRun.id == run_id)
        return list(await self.session.scalars(stmt.order_by(Message.id)))

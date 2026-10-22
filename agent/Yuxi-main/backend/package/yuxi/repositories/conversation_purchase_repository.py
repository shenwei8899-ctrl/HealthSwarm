"""对话购包复用现有 Run、最终消息和本人档案，不建立第二份执行状态。"""

from sqlalchemy import select

from yuxi.storage.postgres.models_business import FamilyMember
from yuxi.storage.postgres.models_health import HealthFamilyProfileLink


class ConversationPurchaseRepository:
    """购买来源固定到咨询绑定的本人成员。"""

    def __init__(self, session):
        """沿用调用方事务。"""
        self.session = session

    async def source_member(self, member_id, uid):
        """只读当前本人已关联的来源，不能从客户端更换家庭或成员。"""
        return await self.session.scalar(
            select(FamilyMember)
            .join(HealthFamilyProfileLink, HealthFamilyProfileLink.source_member_id == FamilyMember.id)
            .where(
                HealthFamilyProfileLink.member_id == member_id,
                HealthFamilyProfileLink.actor_uid == uid,
                FamilyMember.subject_uid == uid,
                FamilyMember.is_active.is_(True),
            )
        )

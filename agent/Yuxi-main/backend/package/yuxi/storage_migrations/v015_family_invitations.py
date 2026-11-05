"""统一邀请的撤销版本与本人核对状态。"""

from sqlalchemy import text


async def upgrade_family_invitations(manager):
    """保留已有关系及授权，重复执行不重置邀请版本或核对状态。"""
    statements = (
        "ALTER TABLE family_archives ADD COLUMN IF NOT EXISTS invitation_version INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE family_members ADD COLUMN IF NOT EXISTS invitation_review_pending BOOLEAN NOT NULL DEFAULT false",
        "ALTER TABLE family_members ADD COLUMN IF NOT EXISTS "
        "invitation_analysis_pending BOOLEAN NOT NULL DEFAULT false",
    )
    async with manager.async_engine.begin() as connection:
        for statement in statements:
            await connection.execute(text(statement))

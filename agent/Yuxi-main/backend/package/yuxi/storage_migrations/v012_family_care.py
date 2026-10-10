"""家庭共同生活设置和独立审核监护关系的增量迁移。"""

from sqlalchemy import text


async def upgrade_family_care(manager):
    """旧档案保持原值；重复升级不恢复或创建任何授权。"""
    statements = (
        "ALTER TABLE family_archives ADD COLUMN IF NOT EXISTS settings JSONB NOT NULL DEFAULT '{}'::jsonb",
        "ALTER TABLE family_archives ADD COLUMN IF NOT EXISTS version INTEGER NOT NULL DEFAULT 1",
        "ALTER TABLE family_members ADD COLUMN IF NOT EXISTS guardian_uid VARCHAR REFERENCES users(uid)",
        "ALTER TABLE family_members ADD COLUMN IF NOT EXISTS guardian_status VARCHAR(20)",
        "ALTER TABLE family_members ADD COLUMN IF NOT EXISTS guardian_relationship VARCHAR(30)",
        "ALTER TABLE family_members ADD COLUMN IF NOT EXISTS guardian_birth_date DATE",
        "ALTER TABLE family_members ADD COLUMN IF NOT EXISTS guardian_version INTEGER NOT NULL DEFAULT 1",
        "ALTER TABLE family_members ADD COLUMN IF NOT EXISTS guardian_expires_at TIMESTAMP",
        "ALTER TABLE family_members ADD COLUMN IF NOT EXISTS guardian_reviewed_by VARCHAR REFERENCES users(uid)",
        "ALTER TABLE family_members ADD COLUMN IF NOT EXISTS guardian_reviewed_at TIMESTAMP",
    )
    async with manager.async_engine.begin() as connection:
        for statement in statements:
            await connection.execute(text(statement))

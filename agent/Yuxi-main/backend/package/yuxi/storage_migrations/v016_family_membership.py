"""有效家庭归属的唯一性及归档和交接状态。"""

from sqlalchemy import text


async def upgrade_family_membership(manager):
    """现有多家庭归属需要明确处理后才能启用唯一索引。"""
    async with manager.async_engine.begin() as connection:
        duplicates = await connection.scalar(
            text(
                "SELECT count(*) FROM (SELECT subject_uid FROM family_members "
                "WHERE is_active AND subject_uid IS NOT NULL GROUP BY subject_uid HAVING count(*) > 1) conflicts"
            )
        )
        if duplicates:
            raise RuntimeError(f"有 {duplicates} 个账号存在多个有效家庭归属，需明确处理后重试迁移")
        for statement in (
            "ALTER TABLE family_archives ADD COLUMN IF NOT EXISTS archived_at TIMESTAMP",
            "ALTER TABLE family_archives ADD COLUMN IF NOT EXISTS pending_owner_transfer JSONB",
            "ALTER TABLE family_members ADD COLUMN IF NOT EXISTS person_id VARCHAR(36)",
            """DO $$ BEGIN
                IF to_regclass('health_family_profile_link') IS NOT NULL THEN
                    UPDATE family_members AS member SET person_id = link.member_id
                    FROM health_family_profile_link AS link
                    WHERE member.id = link.source_member_id AND member.person_id IS NULL;
                END IF;
            END $$""",
            "UPDATE family_members SET person_id = id WHERE person_id IS NULL",
            "ALTER TABLE family_archives DROP CONSTRAINT IF EXISTS family_archives_owner_uid_key",
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_active_family_owner ON family_archives (owner_uid) "
            "WHERE archived_at IS NULL",
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_active_family_subject ON family_members (subject_uid) "
            "WHERE is_active AND subject_uid IS NOT NULL",
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_active_family_person ON family_members (person_id) "
            "WHERE is_active AND person_id IS NOT NULL",
        ):
            await connection.execute(text(statement))

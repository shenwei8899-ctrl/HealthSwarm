"""账号家庭记忆来源及请求处理收据的增量迁移。"""

from sqlalchemy import text

from yuxi.storage.postgres.models_health import HealthMemoryProcessing


async def upgrade_account_memory(manager):
    """从旧版本幂等补列；无真实关联的历史记录保留空来源。"""
    async with manager.async_engine.begin() as connection:
        await connection.run_sync(lambda conn: HealthMemoryProcessing.__table__.create(conn, checkfirst=True))
        backfill = not await connection.scalar(
            text("""
            SELECT EXISTS (SELECT 1 FROM information_schema.columns
            WHERE table_schema = current_schema() AND table_name = 'health_memory_fact' AND column_name = 'provenance')
        """)
        )
        for table in ("health_memory_fact", "health_memory_revision"):
            await connection.execute(
                text(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS provenance JSONB NOT NULL DEFAULT '{{}}'::jsonb")
            )
        if backfill:
            await connection.execute(
                text("""
            UPDATE health_memory_fact fact
            SET provenance = jsonb_build_object(
                'family_id', link.family_id, 'source_member_id', link.source_member_id,
                'subject_label', member.name, 'family_label', family.name
            )
            FROM health_family_profile_link link
            JOIN family_members member ON member.id = link.source_member_id AND member.family_id = link.family_id
            JOIN family_archives family ON family.id = link.family_id
            WHERE fact.member_id = link.member_id AND fact.provenance = '{}'::jsonb
        """)
            )
            await connection.execute(
                text("""
            UPDATE health_memory_revision revision SET provenance = fact.provenance
            FROM health_memory_fact fact
            WHERE revision.fact_id = fact.id AND revision.provenance = '{}'::jsonb
        """)
            )
        await connection.execute(
            text("""
            CREATE INDEX IF NOT EXISTS ix_health_memory_account_family
            ON health_memory_fact (actor_uid, (provenance->>'family_id'), id) WHERE status = 'active'
        """)
        )

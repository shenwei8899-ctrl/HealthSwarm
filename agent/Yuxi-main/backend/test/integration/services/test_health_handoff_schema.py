"""28→29真实PG迁移保留旧咨询且重复执行幂等。"""

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from test.integration.services.test_schema_migration_version import (
    _create_isolated_manager,
    _drop_isolated_schema,
    _scoped_manager,
)
from yuxi import storage_migration
from yuxi.storage.postgres.manager import BUSINESS_SCHEMA_VERSION, KNOWLEDGE_SCHEMA_VERSION, HEALTH_SCHEMA_VERSION
from yuxi.storage_migrations.v071_workdirs import V071WorkdirMigrationPlan
from yuxi.storage.postgres.models_business import User, Conversation, Project
from yuxi.storage.postgres.models_health import FamilyMember, HealthConsultation

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_28_to_29_preserves_existing_binding_and_repeats(monkeypatch, tmp_path):
    """运行实际main升级分支，验证旧来源和新交接字段均不被重写。"""
    schema, admin, engine, manager = await _create_isolated_manager("pytest_handoff_schema")
    try:
        await manager.create_business_tables()
        await manager.create_schema_version_table()
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions.begin() as session:
            session.add(User(uid="synthetic", username="synthetic", password_hash="not-a-password"))
            await session.flush()
            session.add(
                FamilyMember(id="member", owner_uid="synthetic", display_name="合成", relationship_label="本人")
            )
            session.add(
                Project(
                    id="synthetic-project",
                    uid="synthetic",
                    selection_status="implicit",
                    directory_mode="managed",
                    workdir_path="projects/synthetic",
                )
            )
            await session.flush()
            conversation = Conversation(
                uid="synthetic",
                thread_id="synthetic-thread",
                agent_id="health-consultation",
                project_id="synthetic-project",
            )
            session.add(conversation)
            await session.flush()
            cid = conversation.id
            session.add(
                HealthConsultation(
                    conversation_id=cid, member_id="member", actor_uid="synthetic", request_id="synthetic-request"
                )
            )
        async with engine.begin() as conn:
            await conn.execute(text("ALTER TABLE health_consultation DROP COLUMN handoff_selection"))
        for domain, version in (
            ("business", BUSINESS_SCHEMA_VERSION),
            ("knowledge", KNOWLEDGE_SCHEMA_VERSION),
            ("health", 28),
        ):
            await manager.record_schema_version(domain, version)

        async def unrelated(*_args, **_kwargs):
            """不执行文件迁移或运行收敛。"""

        async def no_workdir(_session):
            """当前测试没有工作目录。"""
            return V071WorkdirMigrationPlan(False, (), ())

        monkeypatch.setattr(storage_migration, "read_v071_workdir_plan", no_workdir)
        for name in (
            "_legacy_skill_roots_exist",
            "_legacy_system_config_exists",
            "runtime_storage_requires_quiescence",
        ):
            monkeypatch.setattr(storage_migration, name, lambda: False)
        for name in ("_converge_database_state", "migrate_shared_skills"):
            monkeypatch.setattr(storage_migration, name, unrelated)
        for name in ("mark_v071_skills_migrated", "migrate_runtime_storage_identity"):
            monkeypatch.setattr(storage_migration, name, lambda: None)
        monkeypatch.setattr(storage_migration, "get_legacy_storage_dir", lambda: tmp_path / "absent")
        for _ in range(2):
            scoped = _scoped_manager(engine)
            scoped.AsyncSession = async_sessionmaker(engine, expire_on_commit=False)
            monkeypatch.setattr(storage_migration, "pg_manager", scoped)
            await storage_migration.main()
            async with engine.connect() as conn:
                assert (
                    await conn.scalar(text("SELECT version FROM yuxi_schema_migrations WHERE domain='health'"))
                    == HEALTH_SCHEMA_VERSION
                )
                row = (
                    await conn.execute(
                        text(
                            "SELECT member_id,request_id,handoff_selection FROM health_consultation "
                            "WHERE conversation_id=:id"
                        ),
                        {"id": cid},
                    )
                ).one()
                assert tuple(row) == ("member", "synthetic-request", None)
    finally:
        await _drop_isolated_schema(schema, admin, engine)

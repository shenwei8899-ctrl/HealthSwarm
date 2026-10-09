"""正式Schema12→当前版本入口与旧单成员绑定在隔离PG上保持。"""

from datetime import datetime

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker

from test.integration.services.test_schema_migration_version import _create_isolated_manager, _drop_isolated_schema
from test.support.health_schema_legacy import remove_schema21_safe_planner_structures
from yuxi import storage_migration
from yuxi.storage.postgres.models_business import User, Project, Conversation
from yuxi.storage.postgres.models_health import FamilyMember, HealthConsultation
from yuxi.storage.postgres.manager import BUSINESS_SCHEMA_VERSION, KNOWLEDGE_SCHEMA_VERSION, HEALTH_SCHEMA_VERSION
from yuxi.storage_migrations.v071_workdirs import V071WorkdirMigrationPlan

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.fixture(scope="session", autouse=True)
def ensure_live_api_schema():
    """本文件使用独立Schema，正式库不降版。"""


@pytest.fixture(scope="session", autouse=True)
def cleanup_test_knowledge_resources():
    """没有创建知识资源。"""
    yield


@pytest.fixture(scope="session", autouse=True)
def cleanup_test_sandboxes():
    """没有创建沙盒。"""
    yield


async def test_formal_schema12_upgrade_preserves_old_binding_and_is_idempotent(monkeypatch, tmp_path):
    """删除新增结构重建真正12库，运行main而非直接调用DDL证明分支。"""
    schema, admin, engine, manager = await _create_isolated_manager("pytest_family_planner_schema")
    try:
        await manager.create_business_tables()
        await manager.create_schema_version_table()
        async with engine.begin() as connection:
            await connection.execute(text("DROP TABLE health_family_planner_preview"))
            await connection.execute(text("ALTER TABLE health_consultation DROP COLUMN family_planner_selection"))
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions.begin() as session:
            session.add(User(uid="synthetic-owner", username="synthetic-owner", password_hash="not-a-password"))
            await session.flush()
            session.add(
                FamilyMember(
                    id="synthetic-member",
                    owner_uid="synthetic-owner",
                    display_name="合成旧成员",
                    relationship_label="本人",
                )
            )
            session.add(
                Project(
                    id="synthetic-project",
                    uid="synthetic-owner",
                    selection_status="implicit",
                    directory_mode="managed",
                    workdir_path="projects/synthetic",
                )
            )
            await session.flush()
            conversation = Conversation(
                uid="synthetic-owner",
                thread_id="synthetic-old-thread",
                agent_id="health-meal-planner",
                project_id="synthetic-project",
            )
            session.add(conversation)
            await session.flush()
            await session.execute(
                text(
                    "INSERT INTO health_consultation (conversation_id, member_id, actor_uid, request_id, created_at) "
                    "VALUES (:id, 'synthetic-member', 'synthetic-owner', 'synthetic-old-request', :created)"
                ),
                {"id": conversation.id, "created": datetime(2026, 10, 7, 10)},
            )
            conversation_id = conversation.id
        for domain, version in (
            ("business", BUSINESS_SCHEMA_VERSION),
            ("knowledge", KNOWLEDGE_SCHEMA_VERSION),
            ("health", 12),
        ):
            await manager.record_schema_version(domain, version)

        await remove_schema21_safe_planner_structures(engine)

        async def unrelated(*_args, **_kwargs):
            """只隔离不属于健康DDL的文件和运行收敛副作用。"""

        async def no_workdir(_session):
            return V071WorkdirMigrationPlan(False, (), ())

        monkeypatch.setattr(storage_migration, "pg_manager", manager)
        monkeypatch.setattr(storage_migration, "read_v071_workdir_plan", no_workdir)
        monkeypatch.setattr(storage_migration, "_legacy_skill_roots_exist", lambda: False)
        monkeypatch.setattr(storage_migration, "_legacy_system_config_exists", lambda: False)
        monkeypatch.setattr(storage_migration, "runtime_storage_requires_quiescence", lambda: False)
        monkeypatch.setattr(storage_migration, "_converge_database_state", unrelated)
        monkeypatch.setattr(storage_migration, "migrate_shared_skills", unrelated)
        monkeypatch.setattr(storage_migration, "mark_v071_skills_migrated", lambda: None)
        monkeypatch.setattr(storage_migration, "migrate_runtime_storage_identity", lambda: None)
        monkeypatch.setattr(storage_migration, "get_legacy_storage_dir", lambda: tmp_path / "nonexistent")
        # main会关闭manager；两次执行分别以同一隔离engine重新装配，核对幂等。
        from test.integration.services.test_schema_migration_version import _scoped_manager

        for _ in range(2):
            manager = _scoped_manager(engine)
            manager.AsyncSession = sessions
            monkeypatch.setattr(storage_migration, "pg_manager", manager)
            await storage_migration.main()
            async with sessions() as session:
                assert (
                    await session.scalar(text("SELECT version FROM yuxi_schema_migrations WHERE domain = 'health'"))
                    == HEALTH_SCHEMA_VERSION
                )
                assert await session.scalar(text("SELECT to_regclass('health_family_planner_preview')")) is not None
                old = await session.scalar(
                    select(HealthConsultation).where(HealthConsultation.conversation_id == conversation_id)
                )
                assert old.member_id == "synthetic-member" and old.actor_uid == "synthetic-owner"
                assert old.request_id == "synthetic-old-request" and old.created_at == datetime(2026, 10, 7, 10)
                assert old.family_planner_selection is None
    finally:
        await _drop_isolated_schema(schema, admin, engine)

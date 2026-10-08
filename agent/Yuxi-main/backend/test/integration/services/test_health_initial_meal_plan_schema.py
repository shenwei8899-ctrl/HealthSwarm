"""正式13/14→15迁移保留旧预览和家庭绑定，重复执行幂等。"""

from datetime import datetime
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from test.integration.services.test_schema_migration_version import (
    _create_isolated_manager,
    _drop_isolated_schema,
    _scoped_manager,
)
from test.unit.services.test_health_meal_planner import spec_input
from yuxi import storage_migration
from yuxi.storage.postgres.manager import BUSINESS_SCHEMA_VERSION, KNOWLEDGE_SCHEMA_VERSION, HEALTH_SCHEMA_VERSION
from yuxi.storage.postgres.models_business import User, Project, Conversation
from yuxi.storage.postgres.models_health import (
    FamilyMember,
    HealthMealPlanPreview,
    HealthConsultation,
    HealthInitialPlanPreview,
)
from yuxi.storage_migrations.v071_workdirs import V071WorkdirMigrationPlan

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.fixture(scope="session", autouse=True)
def ensure_live_api_schema():
    """独立Schema不降低正式库版本。"""


@pytest.fixture(scope="session", autouse=True)
def cleanup_test_knowledge_resources():
    """不创建知识资源。"""
    yield


@pytest.fixture(scope="session", autouse=True)
def cleanup_test_sandboxes():
    """不创建沙盒。"""
    yield


@pytest.mark.parametrize("source_version", [13, 14])
async def test_formal_upgrade_preserves_old_previews_and_family_binding(monkeypatch, tmp_path, source_version):
    """还原13/14存量结构，实际main增量分支保留旧数据并可重复执行。"""
    schema, admin, engine, manager = await _create_isolated_manager("pytest_initial_plan_schema")
    try:
        await manager.create_business_tables()
        await manager.create_schema_version_table()
        async with engine.begin() as conn:
            if source_version == 13:
                await conn.execute(text("DROP TABLE health_initial_plan_preview"))
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        member_id, preview_id = str(uuid4()), str(uuid4())
        initial_id = str(uuid4())
        spec, snapshot = spec_input(str(uuid4())), {"legacy": "preserve-current-fields"}
        family_selection = {"selection": {"legacy_family_source": "preserve"}, "source_hash": "a" * 64}
        stamp = datetime(2026, 10, 7, 12)
        async with sessions.begin() as session:
            session.add(
                User(uid="synthetic-initial-owner", username="synthetic-initial-owner", password_hash="not-a-password")
            )
            await session.flush()
            session.add(
                FamilyMember(
                    id=member_id,
                    owner_uid="synthetic-initial-owner",
                    display_name="合成旧成员",
                    relationship_label="本人",
                )
            )
            session.add(
                Project(
                    id="synthetic-initial-project",
                    uid="synthetic-initial-owner",
                    selection_status="implicit",
                    directory_mode="managed",
                    workdir_path="projects/synthetic",
                )
            )
            await session.flush()
            conversation = Conversation(
                uid="synthetic-initial-owner",
                thread_id=str(uuid4()),
                agent_id="health-meal-planner",
                project_id="synthetic-initial-project",
            )
            session.add(conversation)
            await session.flush()
            conversation_id = conversation.id
            session.add(
                HealthConsultation(
                    conversation_id=conversation_id,
                    member_id=member_id,
                    actor_uid="synthetic-initial-owner",
                    request_id=str(uuid4()),
                    family_planner_selection=family_selection,
                    created_at=stamp,
                )
            )
            session.add(
                HealthMealPlanPreview(
                    id=preview_id,
                    actor_uid="synthetic-initial-owner",
                    member_id=member_id,
                    spec=spec,
                    snapshot=snapshot,
                    created_at=stamp,
                )
            )
            if source_version == 14:
                session.add(
                    HealthInitialPlanPreview(
                        id=initial_id,
                        actor_uid="synthetic-initial-owner",
                        member_id=member_id,
                        selection={"legacy_initial": "preserve"},
                        snapshot={"legacy_initial_result": "preserve"},
                        created_at=stamp,
                    )
                )
        async with engine.begin() as conn:
            await conn.execute(text("ALTER TABLE health_consultation DROP COLUMN initial_planner_selection"))
            if source_version == 14:
                await conn.execute(text("ALTER TABLE health_initial_plan_preview DROP COLUMN run_id"))
                await conn.execute(text("ALTER TABLE health_initial_plan_preview DROP COLUMN conversation_id"))
        for domain, version in (
            ("business", BUSINESS_SCHEMA_VERSION),
            ("knowledge", KNOWLEDGE_SCHEMA_VERSION),
            ("health", source_version),
        ):
            await manager.record_schema_version(domain, version)

        async def unrelated(*_args, **_kwargs):
            """隔离与健康DDL无关的文件和运行收敛副作用。"""

        async def no_workdir(_session):
            """无历史工作目录迁移。"""
            return V071WorkdirMigrationPlan(False, (), ())

        monkeypatch.setattr(storage_migration, "read_v071_workdir_plan", no_workdir)
        monkeypatch.setattr(storage_migration, "_legacy_skill_roots_exist", lambda: False)
        monkeypatch.setattr(storage_migration, "_legacy_system_config_exists", lambda: False)
        monkeypatch.setattr(storage_migration, "runtime_storage_requires_quiescence", lambda: False)
        monkeypatch.setattr(storage_migration, "_converge_database_state", unrelated)
        monkeypatch.setattr(storage_migration, "migrate_shared_skills", unrelated)
        monkeypatch.setattr(storage_migration, "mark_v071_skills_migrated", lambda: None)
        monkeypatch.setattr(storage_migration, "migrate_runtime_storage_identity", lambda: None)
        monkeypatch.setattr(storage_migration, "get_legacy_storage_dir", lambda: tmp_path / "nonexistent")
        for _ in range(2):
            manager = _scoped_manager(engine)
            manager.AsyncSession = sessions
            monkeypatch.setattr(storage_migration, "pg_manager", manager)
            await storage_migration.main()
            async with sessions() as session:
                assert (
                    await session.scalar(text("SELECT version FROM yuxi_schema_migrations WHERE domain='health'"))
                    == HEALTH_SCHEMA_VERSION
                )
                assert await session.scalar(text("SELECT to_regclass('health_initial_plan_preview')")) is not None
                old = await session.get(HealthMealPlanPreview, preview_id)
                bound = await session.get(HealthConsultation, conversation_id)
                assert old.spec == spec and old.snapshot == snapshot and old.created_at == stamp and old.run_id is None
                assert bound.family_planner_selection == family_selection and bound.created_at == stamp
                assert bound.initial_planner_selection is None
                if source_version == 14:
                    initial = await session.get(HealthInitialPlanPreview, initial_id)
                    assert initial.selection == {"legacy_initial": "preserve"} and initial.snapshot == {
                        "legacy_initial_result": "preserve"
                    }
                    assert initial.created_at == stamp and initial.run_id is None and initial.conversation_id is None
    finally:
        await _drop_isolated_schema(schema, admin, engine)

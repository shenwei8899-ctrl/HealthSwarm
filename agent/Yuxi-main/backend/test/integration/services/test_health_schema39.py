"""健康版本 38 两种发布结构在真实 PostgreSQL 上收敛。"""

from unittest.mock import AsyncMock

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker
from yuxi.storage.postgres.models_business import User
from yuxi.storage.postgres.models_health import FamilyMember, HealthMemoryFact

from test.integration.services.test_schema_migration_version import (
    _create_isolated_manager, _drop_isolated_schema,
    ensure_live_api_schema, cleanup_test_knowledge_resources, cleanup_test_sandboxes,
)
from yuxi.storage.postgres.manager import HEALTH_SCHEMA_VERSION
from yuxi import storage_migration
from yuxi.storage_migrations.v071_workdirs import V071WorkdirMigrationPlan

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.mark.parametrize("shape", ["37", "38_memory", "38_presentation", "38_complete", "39"])
async def test_converges_both_release_shapes_without_losing_rows(shape, monkeypatch, tmp_path):
    """部分结构与完整结构重复迁移后保留原行并同时具备两项能力。"""
    schema, admin, engine, manager = await _create_isolated_manager("pytest_health39")
    try:
        await manager.create_business_tables()
        await manager.create_health_tables()
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions.begin() as session:
            session.add(User(uid="synthetic-owner", username="synthetic-owner", password_hash="synthetic"))
            await session.flush()
            session.add(FamilyMember(id="synthetic-member", owner_uid="synthetic-owner", display_name="合成成员", relationship_label="本人"))
            await session.flush()
            session.add(HealthMemoryFact(id="synthetic-fact", actor_uid="synthetic-owner", member_id="synthetic-member", fact_key="coriander", kind="preference", content="不喜欢香菜", version=7, status="active"))
        async with engine.begin() as connection:
            if shape in ("37", "38_presentation"):
                await connection.execute(text("DROP TABLE health_memory_processing"))
                for table in ("health_memory_fact", "health_memory_revision"):
                    await connection.execute(text(f"ALTER TABLE {table} DROP COLUMN provenance CASCADE"))
            if shape in ("37", "38_memory"):
                await connection.execute(text("ALTER TABLE health_recipe_commerce_source DROP COLUMN presentation"))
        await manager.create_schema_version_table()
        await manager.record_schema_version("business", storage_migration.BUSINESS_SCHEMA_VERSION)
        await manager.record_schema_version("knowledge", storage_migration.KNOWLEDGE_SCHEMA_VERSION)
        await manager.record_schema_version("health", int(shape.split("_")[0]))
        manager.AsyncSession = sessions
        monkeypatch.setattr(manager, "initialize", lambda: None)
        monkeypatch.setattr(manager, "close", AsyncMock())
        monkeypatch.setattr(storage_migration, "pg_manager", manager)
        monkeypatch.setattr(storage_migration, "read_v071_workdir_plan", AsyncMock(return_value=V071WorkdirMigrationPlan(False, (), ())))
        for name in ("_legacy_skill_roots_exist", "_legacy_system_config_exists", "runtime_storage_requires_quiescence"):
            monkeypatch.setattr(storage_migration, name, lambda: False)
        monkeypatch.setattr(storage_migration, "get_legacy_storage_dir", lambda: tmp_path)
        monkeypatch.setattr(storage_migration, "_converge_database_state", AsyncMock())
        monkeypatch.setattr(storage_migration, "migrate_shared_skills", AsyncMock())
        monkeypatch.setattr(storage_migration, "mark_v071_skills_migrated", lambda: None)
        monkeypatch.setattr(storage_migration, "migrate_runtime_storage_identity", lambda: None)
        for _ in range(2):
            await storage_migration.main()
            assert (await manager.get_schema_versions())["health"] == 39
            async with engine.connect() as connection:
                columns = set((await connection.execute(text("SELECT table_name,column_name FROM information_schema.columns WHERE table_schema=current_schema()"))).all())
                assert ("health_recipe_commerce_source", "presentation") in columns
                assert ("health_memory_fact", "provenance") in columns
                assert ("health_memory_revision", "provenance") in columns
                assert ("health_memory_processing", "request_id") in columns
                assert (await connection.execute(text("SELECT content,version FROM health_memory_fact WHERE id='synthetic-fact'"))).one() == ("不喜欢香菜", 7)
        assert HEALTH_SCHEMA_VERSION == 39
    finally:
        await _drop_isolated_schema(schema, admin, engine)

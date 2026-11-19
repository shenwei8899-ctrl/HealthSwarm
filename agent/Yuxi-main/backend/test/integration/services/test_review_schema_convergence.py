"""独立 PostgreSQL 验证两条 schema 38 分支及 39 的向前收敛。"""

import os
from pathlib import Path
from uuid import uuid4
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from yuxi import storage_migration as migration
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_business import Base
from yuxi.storage.postgres import models_health, models_knowledge  # noqa: F401
from yuxi.storage_migrations.v071_workdirs import V071WorkdirMigrationPlan

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.fixture(scope="session", autouse=True)
def cleanup_test_sandboxes():
    """本文件只使用显式数据库连接，不创建或连接任何 sandbox。"""
    yield


async def test_current_meal_memory_uses_real_account_and_family_scope(monkeypatch):
    """真实 PG 召回仅当前账号、当前家庭、实际参与者的有效记忆。"""
    from yuxi.services.health_memory_context_service import memory_facts_for_meal
    from yuxi.storage.postgres.models_business import User, FamilyArchive, FamilyMember as SourceMember
    from yuxi.storage.postgres.models_health import FamilyMember, HealthFamilyProfileLink, HealthMemoryFact

    url = os.getenv("REVIEW_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("需要显式配置独立 REVIEW_TEST_POSTGRES_URL")
    schema = "review_" + uuid4().hex
    control = create_async_engine(url)
    async with control.begin() as connection:
        await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_async_engine(url, connect_args={"server_settings": {"search_path": schema}})
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with sessions.begin() as session:
            session.add_all([User(uid=uid, username=uid, password_hash="synthetic") for uid in ("actor", "other")])
            await session.flush()
            session.add(FamilyArchive(id="family", owner_uid="actor", name="合成家庭"))
            await session.flush()
            session.add_all(
                [
                    SourceMember(id="self", family_id="family", subject_uid="actor", name="本人", relationship="本人"),
                    SourceMember(id="other", family_id="family", subject_uid="other", name="家人", relationship="家人"),
                    FamilyMember(id="health", owner_uid="actor", display_name="本人", relationship_label="本人"),
                    FamilyMember(id="other-health", owner_uid="other", display_name="家人", relationship_label="家人"),
                ]
            )
            await session.flush()
            session.add_all(
                [
                    HealthFamilyProfileLink(
                        member_id="health", source_member_id="self", family_id="family", actor_uid="actor"
                    ),
                    HealthFamilyProfileLink(
                        member_id="other-health", source_member_id="other", family_id="family", actor_uid="other"
                    ),
                ]
            )
            for fid, actor, member, family, status in [
                ("valid", "actor", "health", "family", "active"),
                ("other-account", "other", "health", "family", "active"),
                ("other-participant", "actor", "other-health", "family", "active"),
                ("old-family", "actor", "health", "old-family", "active"),
                ("withdrawn", "actor", "health", "family", "revoked"),
            ]:
                session.add(
                    HealthMemoryFact(
                        id=fid,
                        actor_uid=actor,
                        member_id=member,
                        fact_key=fid,
                        provenance={
                            "family_id": family,
                            "source_member_id": "self" if member == "health" else "other",
                            "entity": "牛肉",
                        },
                        kind="restriction",
                        content="不吃牛肉",
                        status=status,
                        version=1,
                    )
                )
        current = {"sources": {"family_id": "family", "members": {"self": {"health_member_id": "health"}}}}
        async with sessions.begin() as session:
            rows = await memory_facts_for_meal(session, "actor", current)
            assert [row.id for row in rows] == ["valid"]
        async with sessions.begin() as session:
            fact = await session.get(HealthMemoryFact, "valid")
            fact.status = "revoked"
            fact.version = 2
        async with sessions.begin() as session:
            assert await memory_facts_for_meal(session, "actor", current) == []
    finally:
        await engine.dispose()
        async with control.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await control.dispose()


@pytest.mark.parametrize("baseline", ["fresh", "37", "38-presentation", "38-memory", "39"])
async def test_historical_health_structures_converge_and_repeat(monkeypatch, tmp_path, baseline):
    """真实 DDL 保留历史数据，补齐所有字段后才记录 40；重复运行不改写。"""
    url = os.getenv("REVIEW_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("需要显式配置独立 REVIEW_TEST_POSTGRES_URL")
    schema = "review_" + uuid4().hex
    control = create_async_engine(url)
    async with control.begin() as connection:
        await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_async_engine(url, connect_args={"server_settings": {"search_path": schema}})
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
            # 模拟已存在业务基表的历史安装，而不是用 SQLite 代替 PostgreSQL。
            if baseline not in ("38-presentation",):
                await connection.execute(text("ALTER TABLE health_recipe_commerce_source DROP COLUMN presentation"))
            if baseline not in ("38-memory", "39"):
                await connection.execute(text("DROP TABLE health_memory_processing"))
                await connection.execute(text("ALTER TABLE health_memory_revision DROP COLUMN provenance"))
                await connection.execute(text("ALTER TABLE health_memory_fact DROP COLUMN provenance"))
            if baseline != "39":
                await connection.execute(text("ALTER TABLE health_daily_meal_plan DROP COLUMN archive_meals"))
            await connection.execute(
                text(
                    "INSERT INTO users (username,uid,password_hash,role,login_failed_count,is_deleted) "
                    "VALUES ('review','review','synthetic','user',0,0)"
                )
            )
        monkeypatch.setattr(pg_manager, "async_engine", engine)
        monkeypatch.setattr(pg_manager, "AsyncSession", async_sessionmaker(engine, expire_on_commit=False))
        monkeypatch.setattr(pg_manager, "_initialized", True)
        monkeypatch.setattr(pg_manager, "initialize", lambda: None)
        monkeypatch.setattr(pg_manager, "close", AsyncMock())
        monkeypatch.setattr(
            migration, "read_v071_workdir_plan", AsyncMock(return_value=V071WorkdirMigrationPlan(False, (), ()))
        )
        monkeypatch.setattr(migration, "_legacy_skill_roots_exist", lambda: False)
        monkeypatch.setattr(migration, "_legacy_system_config_exists", lambda: False)
        monkeypatch.setattr(migration, "runtime_storage_requires_quiescence", lambda: False)
        monkeypatch.setattr(migration, "_converge_database_state", AsyncMock())
        monkeypatch.setattr(migration, "get_legacy_storage_dir", lambda: Path(tmp_path))
        monkeypatch.setattr(migration, "migrate_shared_skills", AsyncMock())
        monkeypatch.setattr(migration, "mark_v071_skills_migrated", lambda: None)
        monkeypatch.setattr(migration, "migrate_runtime_storage_identity", lambda: None)
        await pg_manager.create_schema_version_table()
        await pg_manager.record_schema_version("business", migration.BUSINESS_SCHEMA_VERSION)
        await pg_manager.record_schema_version("knowledge", migration.KNOWLEDGE_SCHEMA_VERSION)
        if baseline != "fresh":
            await pg_manager.record_schema_version("health", int(baseline.split("-")[0]))
        for _ in range(2):
            await migration.main()
            assert (await pg_manager.get_schema_versions())["health"] == 40
            async with engine.connect() as connection:
                columns = set(
                    (
                        await connection.execute(
                            text(
                                "SELECT table_name,column_name FROM information_schema.columns "
                                "WHERE table_schema=current_schema()"
                            )
                        )
                    ).all()
                )
                assert ("health_recipe_commerce_source", "presentation") in columns
                assert ("health_memory_fact", "provenance") in columns
                assert ("health_memory_revision", "provenance") in columns
                assert ("health_daily_meal_plan", "archive_meals") in columns
                assert await connection.scalar(text("SELECT to_regclass('health_memory_processing') IS NOT NULL"))
                assert await connection.scalar(text("SELECT count(*) FROM users WHERE uid='review'")) == 1
    finally:
        await engine.dispose()
        async with control.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await control.dispose()

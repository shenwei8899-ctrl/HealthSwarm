"""正式health15→18迁移保留旧成员授权和咨询，约束与重放使用隔离PG。"""

from datetime import datetime
from uuid import uuid4

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import async_sessionmaker

from test.integration.services.test_schema_migration_version import (
    _create_isolated_manager,
    _drop_isolated_schema,
    _scoped_manager,
)
from yuxi import storage_migration
from yuxi.storage.postgres.manager import BUSINESS_SCHEMA_VERSION, KNOWLEDGE_SCHEMA_VERSION
from yuxi.storage.postgres.models_business import Conversation, Project, User
from yuxi.storage.postgres.models_health import FamilyMember, HealthConsultation, HealthGrant
from yuxi.storage_migrations.v071_workdirs import V071WorkdirMigrationPlan

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.fixture(scope="session", autouse=True)
def ensure_live_api_schema():
    """独立Schema测试不迁移或降级运行中API数据库。"""


@pytest.fixture(scope="session", autouse=True)
def cleanup_test_knowledge_resources():
    """不创建知识资源。"""
    yield


@pytest.fixture(scope="session", autouse=True)
def cleanup_test_sandboxes():
    """不创建沙盒。"""
    yield


def isolate_other_migration_effects(monkeypatch, tmp_path):
    """只隔离文件、Skills和运行收敛，健康DDL仍经正式main执行。"""

    async def unrelated(*_args, **_kwargs):
        """没有本测试范围之外的迁移副作用。"""

    async def no_workdir(_session):
        """没有历史工作目录需要切换。"""
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


async def prepare_schema15(manager, engine):
    """删除新增结构形成真正旧Schema，不用当前ORM预建结果充当迁移证据。"""
    await manager.create_business_tables()
    await manager.create_schema_version_table()
    async with engine.begin() as connection:
        await connection.execute(text("DROP TABLE health_blood_pressure_use"))
        await connection.execute(text("DROP TABLE health_weight_use"))
        await connection.execute(text("DROP TABLE health_family_profile_use"))
        await connection.execute(text("DROP TABLE health_family_profile_link"))
    for domain, version in (
        ("business", BUSINESS_SCHEMA_VERSION),
        ("knowledge", KNOWLEDGE_SCHEMA_VERSION),
        ("health", 15),
    ):
        await manager.record_schema_version(domain, version)


def profile_constraints(connection):
    """从真实PG目录读取主键、唯一约束和外键，不复用ORM期望。"""
    inspector = inspect(connection)
    result = {}
    for table in ("health_family_profile_link", "health_family_profile_use"):
        result[table] = {
            "primary": inspector.get_pk_constraint(table)["constrained_columns"],
            "unique": [row["column_names"] for row in inspector.get_unique_constraints(table)],
            "foreign": {
                (tuple(row["constrained_columns"]), row["referred_table"], tuple(row["referred_columns"]))
                for row in inspector.get_foreign_keys(table)
            },
        }
    return result


async def test_formal_schema15_upgrade_preserves_member_grant_and_consultation(monkeypatch, tmp_path):
    """真实main补齐两表，重放后旧成员、grant、咨询及时间戳完全保持。"""
    schema, admin, engine, manager = await _create_isolated_manager("pytest_family_profile_schema")
    try:
        await prepare_schema15(manager, engine)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        member_id, request_id, thread_id = str(uuid4()), str(uuid4()), str(uuid4())
        uid = "synthetic-family-profile-owner"
        stamp = datetime(2026, 10, 7, 12)
        scopes = ["diet_edit", "ai_use", "profile_view"]
        async with sessions.begin() as session:
            session.add(User(uid=uid, username=uid, password_hash="not-a-password"))
            await session.flush()
            session.add(
                FamilyMember(
                    id=member_id,
                    owner_uid=uid,
                    display_name="合成旧健康成员",
                    relationship_label="本人",
                    created_at=stamp,
                )
            )
            session.add(
                Project(
                    id="synthetic-family-profile-project",
                    uid=uid,
                    selection_status="implicit",
                    directory_mode="managed",
                    workdir_path="projects/synthetic",
                )
            )
            await session.flush()
            session.add(HealthGrant(member_id=member_id, actor_uid=uid, scopes=scopes, revoked_at=None))
            conversation = Conversation(
                uid=uid,
                thread_id=thread_id,
                agent_id="health-consultation",
                project_id="synthetic-family-profile-project",
            )
            session.add(conversation)
            await session.flush()
            conversation_id = conversation.id
            session.add(
                HealthConsultation(
                    conversation_id=conversation_id,
                    member_id=member_id,
                    actor_uid=uid,
                    request_id=request_id,
                    created_at=stamp,
                )
            )

        isolate_other_migration_effects(monkeypatch, tmp_path)
        for _ in range(2):
            manager = _scoped_manager(engine)
            manager.AsyncSession = sessions
            monkeypatch.setattr(storage_migration, "pg_manager", manager)
            await storage_migration.main()
            async with sessions() as session:
                assert (
                    await session.scalar(text("SELECT version FROM yuxi_schema_migrations WHERE domain='health'")) == 18
                )
                member = await session.get(FamilyMember, member_id)
                assert (member.owner_uid, member.display_name, member.relationship_label, member.created_at) == (
                    uid,
                    "合成旧健康成员",
                    "本人",
                    stamp,
                )
                grant = await session.get(HealthGrant, (member_id, uid))
                assert grant.scopes == scopes and grant.revoked_at is None
                bound = await session.get(HealthConsultation, conversation_id)
                assert (bound.member_id, bound.actor_uid, bound.request_id, bound.created_at) == (
                    member_id,
                    uid,
                    request_id,
                    stamp,
                )
                assert bound.family_planner_selection is None and bound.initial_planner_selection is None
                assert (await session.get(Conversation, conversation_id)).thread_id == thread_id
                for table in ("health_family_profile_link", "health_family_profile_use"):
                    assert await session.scalar(text(f"SELECT COUNT(*) FROM {table}")) == 0
            async with engine.connect() as connection:
                constraints = await connection.run_sync(profile_constraints)
            link, use = constraints["health_family_profile_link"], constraints["health_family_profile_use"]
            assert link["primary"] == ["member_id"]
            assert ["source_member_id"] in link["unique"]
            assert link["foreign"] == {
                (("member_id",), "family_member", ("id",)),
                (("source_member_id",), "family_members", ("id",)),
                (("family_id",), "family_archives", ("id",)),
                (("actor_uid",), "users", ("uid",)),
            }
            assert use["primary"] == ["run_id", "payload_hash"]
            assert use["foreign"] == {
                (("run_id",), "agent_runs", ("id",)),
                (("member_id",), "family_member", ("id",)),
                (("source_member_id",), "family_members", ("id",)),
            }
    finally:
        await _drop_isolated_schema(schema, admin, engine)


async def test_formal_migration_rejects_future_health_schema_without_new_ddl(monkeypatch, tmp_path):
    """未来版本不能降级或运行健康DDL，拒绝后独立回读原版本和缺失表。"""
    schema, admin, engine, manager = await _create_isolated_manager("pytest_family_profile_future")
    try:
        await prepare_schema15(manager, engine)
        await manager.record_schema_version("health", 19)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        manager.AsyncSession = sessions
        isolate_other_migration_effects(monkeypatch, tmp_path)
        monkeypatch.setattr(storage_migration, "pg_manager", manager)
        with pytest.raises(RuntimeError, match="Unsupported health schema version: 19"):
            await storage_migration.main()
        async with sessions() as session:
            assert await session.scalar(text("SELECT version FROM yuxi_schema_migrations WHERE domain='health'")) == 19
            for table in ("health_family_profile_link", "health_family_profile_use"):
                assert await session.scalar(text("SELECT to_regclass(:table)"), {"table": table}) is None
    finally:
        await _drop_isolated_schema(schema, admin, engine)

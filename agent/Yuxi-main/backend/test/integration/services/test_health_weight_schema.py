"""正式health16→18迁移保留家庭实测及健康绑定，真实PG验证依赖表。"""

import os
from datetime import datetime
from uuid import uuid4

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from test.integration.services.test_health_family_profile_schema import isolate_other_migration_effects
from yuxi import storage_migration
from yuxi.storage.postgres.manager import BUSINESS_SCHEMA_VERSION, KNOWLEDGE_SCHEMA_VERSION, PostgresManager
from yuxi.storage.postgres.models_business import (
    AgentRun,
    Conversation,
    FamilyArchive,
    FamilyMeasurement,
    FamilyMember as SourceMember,
    Project,
    User,
)
from yuxi.storage.postgres.models_health import (
    FamilyMember,
    HealthConsultation,
    HealthFamilyProfileLink,
    HealthFamilyProfileUse,
    HealthGrant,
)

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.fixture(scope="session", autouse=True)
def ensure_live_api_schema():
    """独立schema迁移不接触运行中API数据库。"""


@pytest.fixture(scope="session", autouse=True)
def cleanup_test_knowledge_resources():
    """本文件没有创建知识资源。"""
    yield


@pytest.fixture(scope="session", autouse=True)
def cleanup_test_sandboxes():
    """本文件没有创建沙盒。"""
    yield


async def test_formal_schema16_upgrade_preserves_family_weight_and_health_facts(monkeypatch, tmp_path):
    """真实main两次迁移，旧实测、历史、映射、grant及咨询逐字段保持。"""
    schema, admin, engine, manager = await create_weight_schema()
    try:
        await prepare_schema16(manager, engine)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        uid = "synthetic-weight-migration-owner"
        ids = {
            name: str(uuid4())
            for name in ("family", "source", "measurement", "health", "request", "thread", "project", "run")
        }
        stamp = datetime(2026, 10, 8, 1)
        scopes = ["profile_view", "profile_edit", "ai_use", "diet_edit", "report_view"]
        previous = [
            {"version": 1, "values": {"weight": 59}, "note": "合成旧测量", "corrected_at": "2026-10-08T02:00:00Z"}
        ]
        async with sessions.begin() as session:
            session.add(User(uid=uid, username=uid, password_hash="not-a-password"))
            await session.flush()
            session.add(FamilyArchive(id=ids["family"], owner_uid=uid, name="合成旧家庭", created_at=stamp))
            session.add(
                FamilyMember(
                    id=ids["health"],
                    owner_uid=uid,
                    display_name="合成健康本人",
                    relationship_label="本人",
                    created_at=stamp,
                )
            )
            session.add(
                Project(
                    id=ids["project"],
                    uid=uid,
                    selection_status="implicit",
                    directory_mode="managed",
                    workdir_path="projects/synthetic-weight",
                )
            )
            await session.flush()
            session.add(
                SourceMember(
                    id=ids["source"],
                    family_id=ids["family"],
                    subject_uid=uid,
                    name="合成本人",
                    relationship="本人",
                    profile={"height_cm": 171},
                    version=2,
                    confirmed_version=2,
                    updated_at=stamp,
                )
            )
            conversation = Conversation(
                uid=uid, thread_id=ids["thread"], agent_id="health-consultation", project_id=ids["project"]
            )
            session.add(conversation)
            await session.flush()
            conversation_id = conversation.id
            session.add(HealthGrant(member_id=ids["health"], actor_uid=uid, scopes=scopes))
            session.add(
                HealthConsultation(
                    conversation_id=conversation_id,
                    member_id=ids["health"],
                    actor_uid=uid,
                    request_id=ids["request"],
                    created_at=stamp,
                )
            )
            session.add(
                AgentRun(
                    id=ids["run"],
                    request_id=str(uuid4()),
                    uid=uid,
                    agent_slug="health-consultation",
                    conversation_id=conversation_id,
                    conversation_thread_id=ids["thread"],
                    runtime_scope_id=ids["thread"],
                    status="completed",
                )
            )
            await session.flush()
            session.add(
                FamilyMeasurement(
                    id=ids["measurement"],
                    member_id=ids["source"],
                    kind="weight",
                    values={"weight": 60},
                    measured_at=stamp,
                    source="synthetic-weight-scale",
                    condition="合成条件",
                    note="合成更正测量",
                    created_by=uid,
                    creation_intent={"synthetic": True},
                    version=2,
                    previous=previous,
                    updated_at=stamp,
                )
            )
            session.add(
                HealthFamilyProfileLink(
                    member_id=ids["health"],
                    source_member_id=ids["source"],
                    family_id=ids["family"],
                    actor_uid=uid,
                    created_at=stamp,
                )
            )
            session.add(
                HealthFamilyProfileUse(
                    run_id=ids["run"],
                    payload_hash="a" * 64,
                    member_id=ids["health"],
                    source_member_id=ids["source"],
                    version=2,
                )
            )
        isolate_other_migration_effects(monkeypatch, tmp_path)
        for _ in range(2):
            manager = scoped_weight_manager(engine)
            manager.AsyncSession = sessions
            monkeypatch.setattr(storage_migration, "pg_manager", manager)
            await storage_migration.main()
            async with sessions() as session:
                assert (
                    await session.scalar(text("SELECT version FROM yuxi_schema_migrations WHERE domain='health'")) == 18
                )
                record = await session.get(FamilyMeasurement, ids["measurement"])
                assert (
                    record.member_id,
                    record.kind,
                    record.values,
                    record.measured_at,
                    record.source,
                    record.condition,
                    record.note,
                    record.version,
                    record.previous,
                    record.creation_intent,
                    record.created_by,
                    record.updated_at,
                ) == (
                    ids["source"],
                    "weight",
                    {"weight": 60},
                    stamp,
                    "synthetic-weight-scale",
                    "合成条件",
                    "合成更正测量",
                    2,
                    previous,
                    {"synthetic": True},
                    uid,
                    stamp,
                )
                source = await session.get(SourceMember, ids["source"])
                assert (
                    source.family_id,
                    source.subject_uid,
                    source.profile,
                    source.version,
                    source.confirmed_version,
                ) == (ids["family"], uid, {"height_cm": 171}, 2, 2)
                member = await session.get(FamilyMember, ids["health"])
                assert member.owner_uid == uid and member.created_at == stamp
                grant = await session.get(HealthGrant, (ids["health"], uid))
                assert grant.scopes == scopes and grant.revoked_at is None
                binding = await session.get(HealthConsultation, conversation_id)
                assert (binding.member_id, binding.actor_uid, binding.request_id, binding.created_at) == (
                    ids["health"],
                    uid,
                    ids["request"],
                    stamp,
                )
                link = await session.get(HealthFamilyProfileLink, ids["health"])
                assert (link.source_member_id, link.family_id, link.actor_uid, link.created_at) == (
                    ids["source"],
                    ids["family"],
                    uid,
                    stamp,
                )
                use = await session.get(HealthFamilyProfileUse, (ids["run"], "a" * 64))
                assert use.member_id == ids["health"] and use.source_member_id == ids["source"] and use.version == 2
                assert await session.scalar(text("SELECT COUNT(*) FROM health_weight_use")) == 0
            async with engine.connect() as connection:
                constraints = await connection.run_sync(weight_constraints)
            assert constraints["primary"] == ["run_id", "payload_hash"]
            assert constraints["foreign"] == {
                (("run_id",), "agent_runs", ("id",)),
                (("member_id",), "family_member", ("id",)),
                (("source_member_id",), "family_members", ("id",)),
            }
            assert constraints["nullable"] == {
                "run_id": False,
                "payload_hash": False,
                "member_id": False,
                "source_member_id": True,
                "start_date": False,
                "end_date": False,
                "record_refs": False,
            }
            assert constraints["run_delete"] == "CASCADE"
    finally:
        await drop_weight_schema(schema, admin, engine)


async def test_formal_weight_migration_rejects_future_version_before_ddl(monkeypatch, tmp_path):
    """未来health19明确拒绝，不创建新表或静默改写版本。"""
    schema, admin, engine, manager = await create_weight_schema()
    try:
        await prepare_schema16(manager, engine)
        await manager.record_schema_version("health", 19)
        manager.AsyncSession = async_sessionmaker(engine, expire_on_commit=False)
        isolate_other_migration_effects(monkeypatch, tmp_path)
        monkeypatch.setattr(storage_migration, "pg_manager", manager)
        with pytest.raises(RuntimeError, match="Unsupported health schema version: 19"):
            await storage_migration.main()
        async with engine.connect() as connection:
            assert (
                await connection.scalar(text("SELECT version FROM yuxi_schema_migrations WHERE domain='health'")) == 19
            )
            assert await connection.scalar(text("SELECT to_regclass('health_weight_use')")) is None
    finally:
        await drop_weight_schema(schema, admin, engine)


async def create_weight_schema():
    """只在真实PG新建唯一schema，构建不触碰单例的独立manager。"""
    schema = "pytest_weight_schema_" + uuid4().hex[:16]
    dsn = os.environ["POSTGRES_URL"]
    admin = create_async_engine(dsn, pool_pre_ping=True)
    async with admin.begin() as connection:
        await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_async_engine(dsn, pool_pre_ping=True, connect_args={"server_settings": {"search_path": schema}})
    return schema, admin, engine, scoped_weight_manager(engine)


def scoped_weight_manager(engine):
    """独立manager保留正式迁移方法和数据库连接生命周期。"""
    manager = object.__new__(PostgresManager)
    PostgresManager.__init__(manager)
    manager.async_engine = engine
    manager._initialized = True
    return manager


async def prepare_schema16(manager, engine):
    """移除新增结构构造真实旧16，不用当前ORM表充当迁移证据。"""
    await manager.create_business_tables()
    await manager.create_schema_version_table()
    async with engine.begin() as connection:
        await connection.execute(text("DROP TABLE health_blood_pressure_use"))
        await connection.execute(text("DROP TABLE health_weight_use"))
    for domain, version in (
        ("business", BUSINESS_SCHEMA_VERSION),
        ("knowledge", KNOWLEDGE_SCHEMA_VERSION),
        ("health", 16),
    ):
        await manager.record_schema_version(domain, version)


def weight_constraints(connection):
    """独立PG目录读回主键、外键、空值约束及Run删除级联。"""
    inspector = inspect(connection)
    foreign = inspector.get_foreign_keys("health_weight_use")
    return {
        "primary": inspector.get_pk_constraint("health_weight_use")["constrained_columns"],
        "foreign": {
            (tuple(row["constrained_columns"]), row["referred_table"], tuple(row["referred_columns"]))
            for row in foreign
        },
        "nullable": {row["name"]: row["nullable"] for row in inspector.get_columns("health_weight_use")},
        "run_delete": next(
            row["options"].get("ondelete") for row in foreign if row["constrained_columns"] == ["run_id"]
        ),
    }


async def drop_weight_schema(schema, admin, engine):
    """仅清理本轮唯一schema和连接。"""
    await engine.dispose()
    async with admin.begin() as connection:
        await connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
    await admin.dispose()

"""真实health18→当前正式迁移，保留体重回执、本人关联及独立测量。"""

from datetime import date, datetime
from uuid import uuid4

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import async_sessionmaker

from test.integration.services.test_health_family_profile_schema import isolate_other_migration_effects
from test.integration.services.test_health_weight_schema import (
    create_weight_schema,
    drop_weight_schema,
    scoped_weight_manager,
)
from yuxi import storage_migration
from yuxi.storage.postgres.manager import BUSINESS_SCHEMA_VERSION, KNOWLEDGE_SCHEMA_VERSION, HEALTH_SCHEMA_VERSION
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
    HealthGrant,
    HealthWeightUse,
    HealthBloodPressureUse,
)

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.fixture(scope="session", autouse=True)
def ensure_live_api_schema():
    """仅测试唯一schema，不修改运行中API数据库。"""


@pytest.fixture(scope="session", autouse=True)
def cleanup_test_knowledge_resources():
    """本文件没有创建知识资源。"""
    yield


@pytest.fixture(scope="session", autouse=True)
def cleanup_test_sandboxes():
    """本文件没有创建沙盒。"""
    yield


async def test_formal_schema18_upgrade_preserves_weight_receipts_and_blood_pressure_facts(monkeypatch, tmp_path):
    """正式main两次执行，旧18体重与血压摘要、关联、授权及血压历史逐字段不变。"""
    schema, admin, engine, manager = await create_weight_schema()
    try:
        await prepare_schema18(manager, engine)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        uid, ids = (
            "synthetic-bp-migration",
            {name: str(uuid4()) for name in ("family", "source", "health", "bp", "weight", "project", "thread", "run")},
        )
        stamp = datetime(2026, 10, 8, 1, 2, 3)
        async with sessions.begin() as session:
            session.add(User(uid=uid, username=uid, password_hash="not-a-password"))
            await session.flush()
            session.add_all(
                [
                    FamilyArchive(id=ids["family"], owner_uid=uid, name="合成家庭"),
                    FamilyMember(id=ids["health"], owner_uid=uid, display_name="合成本人", relationship_label="本人"),
                    Project(
                        id=ids["project"],
                        uid=uid,
                        selection_status="implicit",
                        directory_mode="managed",
                        workdir_path="projects/synthetic-bp",
                    ),
                ]
            )
            await session.flush()
            session.add(
                SourceMember(
                    id=ids["source"],
                    family_id=ids["family"],
                    subject_uid=uid,
                    name="合成本人",
                    relationship="本人",
                    profile={},
                    version=1,
                    confirmed_version=None,
                )
            )
            conversation = Conversation(
                uid=uid, thread_id=ids["thread"], agent_id="health-consultation", project_id=ids["project"]
            )
            session.add(conversation)
            await session.flush()
            session.add_all(
                [
                    HealthGrant(member_id=ids["health"], actor_uid=uid, scopes=["profile_view", "ai_use"]),
                    HealthConsultation(
                        conversation_id=conversation.id, member_id=ids["health"], actor_uid=uid, request_id=str(uuid4())
                    ),
                    HealthFamilyProfileLink(
                        member_id=ids["health"], source_member_id=ids["source"], family_id=ids["family"], actor_uid=uid
                    ),
                    AgentRun(
                        id=ids["run"],
                        request_id=str(uuid4()),
                        uid=uid,
                        agent_slug="health-consultation",
                        conversation_id=conversation.id,
                        conversation_thread_id=ids["thread"],
                        runtime_scope_id=ids["thread"],
                        status="completed",
                    ),
                ]
            )
            await session.flush()
            session.add_all(
                [
                    FamilyMeasurement(
                        id=ids["bp"],
                        member_id=ids["source"],
                        kind="blood_pressure",
                        values={"systolic": 121, "diastolic": 81},
                        measured_at=stamp,
                        source="manual",
                        condition="合成条件",
                        note="合成更正备注",
                        created_by=uid,
                        creation_intent={"synthetic": True},
                        version=2,
                        previous=[{"version": 1, "values": {"systolic": 120, "diastolic": 80}}],
                    ),
                    FamilyMeasurement(
                        id=ids["weight"],
                        member_id=ids["source"],
                        kind="weight",
                        values={"weight": 60},
                        measured_at=stamp,
                        source="device",
                        created_by=uid,
                        creation_intent={"synthetic": True},
                        version=1,
                    ),
                    HealthBloodPressureUse(
                        run_id=ids["run"],
                        payload_hash="b" * 64,
                        member_id=ids["health"],
                        source_member_id=ids["source"],
                        start_date=date(2026, 9, 9),
                        end_date=date(2026, 10, 8),
                        record_refs=[{"record_id": ids["bp"], "version": 2}],
                    ),
                    HealthWeightUse(
                        run_id=ids["run"],
                        payload_hash="a" * 64,
                        member_id=ids["health"],
                        source_member_id=ids["source"],
                        start_date=date(2026, 9, 9),
                        end_date=date(2026, 10, 8),
                        record_refs=[{"record_id": ids["weight"], "version": 1}],
                    ),
                ]
            )
        async with sessions() as session:
            before = await preserved_facts(session, ids)
        isolate_other_migration_effects(monkeypatch, tmp_path)
        for _ in range(2):
            scoped = scoped_weight_manager(engine)
            scoped.AsyncSession = sessions
            monkeypatch.setattr(storage_migration, "pg_manager", scoped)
            await storage_migration.main()
            async with sessions() as session:
                assert (
                    await session.scalar(text("SELECT version FROM yuxi_schema_migrations WHERE domain='health'"))
                    == HEALTH_SCHEMA_VERSION
                )
                assert await preserved_facts(session, ids) == before
                for table in ("health_blood_glucose_use", "health_blood_lipids_use"):
                    assert await session.scalar(text(f"SELECT COUNT(*) FROM {table}")) == 0
            for table in ("health_blood_glucose_use", "health_blood_lipids_use"):
                async with engine.connect() as connection:
                    constraints = await connection.run_sync(measurement_use_constraints, table)
                assert constraints == {
                    "primary": ["run_id", "payload_hash"],
                    "foreign": {
                        (("run_id",), "agent_runs", ("id",)),
                        (("member_id",), "family_member", ("id",)),
                        (("source_member_id",), "family_members", ("id",)),
                    },
                    "nullable": {
                        "run_id": False,
                        "payload_hash": False,
                        "member_id": False,
                        "source_member_id": True,
                        "start_date": False,
                        "end_date": False,
                        "record_refs": False,
                    },
                    "run_delete": "CASCADE",
                }
    finally:
        await drop_weight_schema(schema, admin, engine)


async def test_formal_schema19_rejects_future_version_without_creating_blood_glucose_table(monkeypatch, tmp_path):
    """未知未来版本失败在DDL前，既有18结构和未来标记保持。"""
    schema, admin, engine, manager = await create_weight_schema()
    try:
        await prepare_schema18(manager, engine)
        await manager.record_schema_version("health", HEALTH_SCHEMA_VERSION + 1)
        manager.AsyncSession = async_sessionmaker(engine, expire_on_commit=False)
        isolate_other_migration_effects(monkeypatch, tmp_path)
        monkeypatch.setattr(storage_migration, "pg_manager", manager)
        with pytest.raises(RuntimeError, match=f"Unsupported health schema version: {HEALTH_SCHEMA_VERSION + 1}"):
            await storage_migration.main()
        async with engine.connect() as connection:
            assert (
                await connection.scalar(text("SELECT version FROM yuxi_schema_migrations WHERE domain='health'"))
                == HEALTH_SCHEMA_VERSION + 1
            )
            assert await connection.scalar(text("SELECT to_regclass('health_blood_glucose_use')")) is None
            assert await connection.scalar(text("SELECT to_regclass('health_blood_lipids_use')")) is None
            assert await connection.scalar(text("SELECT to_regclass('health_weight_use')")) is not None
    finally:
        await drop_weight_schema(schema, admin, engine)


async def prepare_schema18(manager, engine):
    """移除18之后的血糖和血脂表，保留原体重与血压回执。"""
    await manager.create_business_tables()
    await manager.create_schema_version_table()
    async with engine.begin() as connection:
        await connection.execute(text("DROP TABLE health_blood_glucose_use"))
        await connection.execute(text("DROP TABLE health_blood_lipids_use"))
        for table in ("health_blood_glucose_use", "health_blood_lipids_use"):
            assert await connection.scalar(text("SELECT to_regclass(:table)"), {"table": table}) is None
    for domain, version in (
        ("business", BUSINESS_SCHEMA_VERSION),
        ("knowledge", KNOWLEDGE_SCHEMA_VERSION),
        ("health", 18),
    ):
        await manager.record_schema_version(domain, version)


async def preserved_facts(session, ids):
    """读回旧表全部字段，在升级前后比较实际数据，不引用新增实现。"""
    facts = {}
    for table, column, identifier in (
        ("family_measurements", "id", ids["bp"]),
        ("family_measurements", "id", ids["weight"]),
        ("family_members", "id", ids["source"]),
        ("family_member", "id", ids["health"]),
        ("health_family_profile_link", "member_id", ids["health"]),
        ("health_grant", "member_id", ids["health"]),
        ("health_weight_use", "run_id", ids["run"]),
        ("health_blood_pressure_use", "run_id", ids["run"]),
    ):
        facts[table + identifier] = dict(
            (
                await session.execute(
                    text(f'SELECT * FROM "{table}" WHERE "{column}"=:identifier'), {"identifier": identifier}
                )
            )
            .mappings()
            .one()
        )
    return facts


def measurement_use_constraints(connection, table):
    """直接从PG系统目录读取指定测量回执表的约束。"""
    inspector = inspect(connection)
    foreign = inspector.get_foreign_keys(table)
    return {
        "primary": inspector.get_pk_constraint(table)["constrained_columns"],
        "foreign": {
            (tuple(row["constrained_columns"]), row["referred_table"], tuple(row["referred_columns"]))
            for row in foreign
        },
        "nullable": {row["name"]: row["nullable"] for row in inspector.get_columns(table)},
        "run_delete": next(
            row["options"].get("ondelete") for row in foreign if row["constrained_columns"] == ["run_id"]
        ),
    }

"""真实health19→20正式迁移保留体重、血压、血糖事实与三种引用。"""

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
from yuxi.storage.postgres.manager import BUSINESS_SCHEMA_VERSION, KNOWLEDGE_SCHEMA_VERSION
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
    HealthBloodGlucoseUse,
    HealthBloodPressureUse,
    HealthConsultation,
    HealthFamilyProfileLink,
    HealthGrant,
    HealthWeightUse,
)

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.fixture(scope="session", autouse=True)
def ensure_live_api_schema():
    """只在独立唯一schema执行迁移，不修改运行中API数据库。"""


@pytest.fixture(scope="session", autouse=True)
def cleanup_test_knowledge_resources():
    """本文件没有创建知识资源。"""
    yield


@pytest.fixture(scope="session", autouse=True)
def cleanup_test_sandboxes():
    """本文件没有创建沙盒。"""
    yield


async def test_formal_schema19_upgrade_preserves_three_measurements_and_receipts(monkeypatch, tmp_path):
    """正式main执行两次，旧19的三类测量、回执、关联与授权逐字段不变。"""
    schema, admin, engine, manager = await create_weight_schema()
    try:
        await prepare_schema19(manager, engine)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        uid = "synthetic-lipids-migration"
        ids = {
            name: str(uuid4())
            for name in ("family", "source", "health", "bp", "weight", "glucose", "project", "thread", "run")
        }
        stamp = datetime(2026, 10, 8, 1, 2, 3)
        async with sessions.begin() as session:
            session.add(User(uid=uid, username=uid, password_hash="not-a-password"))
            await session.flush()
            session.add_all(
                [
                    FamilyArchive(id=ids["family"], owner_uid=uid, name="合成血脂迁移家庭"),
                    FamilyMember(id=ids["health"], owner_uid=uid, display_name="合成本人", relationship_label="本人"),
                    Project(
                        id=ids["project"],
                        uid=uid,
                        selection_status="implicit",
                        directory_mode="managed",
                        workdir_path="projects/synthetic-lipids",
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
                        condition="合成血压条件",
                        note="合成血压更正备注",
                        created_by=uid,
                        creation_intent={"synthetic": True, "values": {"systolic": 120, "diastolic": 80}},
                        version=2,
                        previous=[{"version": 1, "values": {"systolic": 120, "diastolic": 80}}],
                    ),
                    FamilyMeasurement(
                        id=ids["weight"],
                        member_id=ids["source"],
                        kind="weight",
                        values={"weight": 61},
                        measured_at=stamp,
                        source="device",
                        condition="合成体重条件",
                        note="合成体重更正备注",
                        created_by=uid,
                        creation_intent={"synthetic": True, "values": {"weight": 60}},
                        version=2,
                        previous=[{"version": 1, "values": {"weight": 60}}],
                    ),
                    FamilyMeasurement(
                        id=ids["glucose"],
                        member_id=ids["source"],
                        kind="blood_glucose",
                        values={"glucose": 5.5},
                        measured_at=stamp,
                        source="synthetic-glucose-device",
                        condition="after_meal_2h",
                        note="合成血糖仅更正条件",
                        created_by=uid,
                        creation_intent={"synthetic": True, "values": {"glucose": 5.5}, "condition": "fasting"},
                        version=2,
                        previous=[{"version": 1, "values": {"glucose": 5.5}, "condition": "fasting"}],
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
                        record_refs=[{"record_id": ids["weight"], "version": 2}],
                    ),
                    HealthBloodGlucoseUse(
                        run_id=ids["run"],
                        payload_hash="c" * 64,
                        member_id=ids["health"],
                        source_member_id=ids["source"],
                        start_date=date(2026, 9, 9),
                        end_date=date(2026, 10, 8),
                        record_refs=[{"record_id": ids["glucose"], "version": 2}],
                    ),
                ]
            )
        async with sessions() as session:
            before = await preserved_facts(session, ids)
            assert before["family_measurements" + ids["glucose"]]["condition"] == "after_meal_2h"
            assert before["family_measurements" + ids["glucose"]]["previous"] == [
                {"version": 1, "values": {"glucose": 5.5}, "condition": "fasting"}
            ]
        isolate_other_migration_effects(monkeypatch, tmp_path)
        for _ in range(2):
            scoped = scoped_weight_manager(engine)
            scoped.AsyncSession = sessions
            monkeypatch.setattr(storage_migration, "pg_manager", scoped)
            await storage_migration.main()
            async with sessions() as session:
                assert (
                    await session.scalar(text("SELECT version FROM yuxi_schema_migrations WHERE domain='health'")) == 20
                )
                assert await preserved_facts(session, ids) == before
                assert await session.scalar(text("SELECT COUNT(*) FROM health_blood_lipids_use")) == 0
            async with engine.connect() as connection:
                constraints = await connection.run_sync(lipids_constraints)
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


async def test_formal_schema20_rejects_future21_before_creating_blood_lipids_table(monkeypatch, tmp_path):
    """未来21标记在DDL前拒绝，旧19三种回执结构与未来标记均保持。"""
    schema, admin, engine, manager = await create_weight_schema()
    try:
        await prepare_schema19(manager, engine)
        await manager.record_schema_version("health", 21)
        manager.AsyncSession = async_sessionmaker(engine, expire_on_commit=False)
        isolate_other_migration_effects(monkeypatch, tmp_path)
        monkeypatch.setattr(storage_migration, "pg_manager", manager)
        with pytest.raises(RuntimeError, match="Unsupported health schema version: 21"):
            await storage_migration.main()
        async with engine.connect() as connection:
            assert (
                await connection.scalar(text("SELECT version FROM yuxi_schema_migrations WHERE domain='health'")) == 21
            )
            assert await connection.scalar(text("SELECT to_regclass('health_blood_lipids_use')")) is None
            for table in ("health_weight_use", "health_blood_pressure_use", "health_blood_glucose_use"):
                assert await connection.scalar(text(f"SELECT to_regclass('{table}')")) is not None
    finally:
        await drop_weight_schema(schema, admin, engine)


async def prepare_schema19(manager, engine):
    """只移除血脂新表形成真实旧19，三种既有回执表保持存在。"""
    await manager.create_business_tables()
    await manager.create_schema_version_table()
    async with engine.begin() as connection:
        await connection.execute(text("DROP TABLE health_blood_lipids_use"))
    for domain, version in (
        ("business", BUSINESS_SCHEMA_VERSION),
        ("knowledge", KNOWLEDGE_SCHEMA_VERSION),
        ("health", 19),
    ):
        await manager.record_schema_version(domain, version)


async def preserved_facts(session, ids):
    """直接读旧表全部字段，不用新增血脂模型生成保留断言。"""
    facts = {}
    for table, column, identifier in (
        ("family_measurements", "id", ids["bp"]),
        ("family_measurements", "id", ids["weight"]),
        ("family_measurements", "id", ids["glucose"]),
        ("family_members", "id", ids["source"]),
        ("family_member", "id", ids["health"]),
        ("health_family_profile_link", "member_id", ids["health"]),
        ("health_grant", "member_id", ids["health"]),
        ("health_weight_use", "run_id", ids["run"]),
        ("health_blood_pressure_use", "run_id", ids["run"]),
        ("health_blood_glucose_use", "run_id", ids["run"]),
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


def lipids_constraints(connection):
    """从真实PG目录核对新增血脂回执的主外键、可空来源与级联约束。"""
    inspector = inspect(connection)
    foreign = inspector.get_foreign_keys("health_blood_lipids_use")
    return {
        "primary": inspector.get_pk_constraint("health_blood_lipids_use")["constrained_columns"],
        "foreign": {
            (tuple(row["constrained_columns"]), row["referred_table"], tuple(row["referred_columns"]))
            for row in foreign
        },
        "nullable": {row["name"]: row["nullable"] for row in inspector.get_columns("health_blood_lipids_use")},
        "run_delete": next(
            row["options"].get("ondelete") for row in foreign if row["constrained_columns"] == ["run_id"]
        ),
    }

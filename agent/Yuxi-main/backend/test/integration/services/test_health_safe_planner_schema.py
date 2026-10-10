"""真实 health20→当前版本正式迁移保留旧事实，并在 DDL 前拒绝未来版本。"""

from datetime import date, datetime
from uuid import uuid4

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker

from test.integration.services.test_health_family_profile_schema import isolate_other_migration_effects
from test.integration.services.test_schema_migration_version import (
    _create_isolated_manager,
    _drop_isolated_schema,
    _scoped_manager,
)
from test.support.health_schema_legacy import (
    assert_schema21_safe_planner_absent,
    remove_schema21_safe_planner_structures,
)
from yuxi import storage_migration
from yuxi.storage.postgres.manager import BUSINESS_SCHEMA_VERSION, HEALTH_SCHEMA_VERSION, KNOWLEDGE_SCHEMA_VERSION
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
    HealthBloodLipidsUse,
    HealthBloodPressureUse,
    HealthConsultation,
    HealthFamilyPlannerPreview,
    HealthFamilyProfileLink,
    HealthFamilyProfileUse,
    HealthGrant,
    HealthInitialPlanPreview,
    HealthMealPlan,
    HealthMealPlanPreview,
    HealthMealPlanRevision,
    HealthWeightUse,
)

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.fixture(scope="session", autouse=True)
def ensure_live_api_schema():
    """只在唯一隔离 Schema 执行正式迁移，不降级运行实例。"""


@pytest.fixture(scope="session", autouse=True)
def cleanup_test_knowledge_resources():
    """本文件没有创建知识资源。"""
    yield


@pytest.fixture(scope="session", autouse=True)
def cleanup_test_sandboxes():
    """本文件没有创建沙盒。"""
    yield


async def test_formal_schema20_upgrade_preserves_old_facts_and_repeats(monkeypatch, tmp_path):
    """真实 main 连续运行两次，保留旧绑定、预览、餐单与四类 Run 测量引用。"""
    schema, admin, engine, manager = await _create_isolated_manager("pytest_safe_planner_schema")
    try:
        sessions, ids = await prepare_schema20(manager, engine)
        async with sessions() as session:
            before = await preserved_schema20_facts(session)
            binding = before["health_consultation"][0]
            assert binding["family_planner_selection"] == {"legacy_family": "retain", "source_hash": "a" * 64}
            assert binding["initial_planner_selection"] == {"legacy_initial": "retain", "source_hash": "b" * 64}
            assert len(before["family_measurements"]) == 4
        isolate_other_migration_effects(monkeypatch, tmp_path)
        for iteration in range(2):
            scoped = _scoped_manager(engine)
            scoped.AsyncSession = sessions
            monkeypatch.setattr(storage_migration, "pg_manager", scoped)
            await storage_migration.main()
            async with sessions() as session:
                assert (
                    await session.scalar(text("SELECT version FROM yuxi_schema_migrations WHERE domain='health'"))
                    == HEALTH_SCHEMA_VERSION
                )
                assert await preserved_schema20_facts(session) == before
                assert await session.scalar(text("SELECT safe_planner_selection FROM health_consultation")) is None
                assert await session.scalar(text("SELECT COUNT(*) FROM health_safe_planner_preview")) == iteration * 2
            async with engine.connect() as connection:
                catalog = await connection.run_sync(safe_planner_catalog)
            assert catalog == {
                "primary": ["id"],
                "foreign": {
                    (("actor_uid",), "users", ("uid",), None),
                    (("conversation_id",), "health_consultation", ("conversation_id",), "CASCADE"),
                    (("run_id",), "agent_runs", ("id",), "CASCADE"),
                },
                "nullable": {
                    "id": False,
                    "actor_uid": False,
                    "conversation_id": False,
                    "run_id": False,
                    "operation": False,
                    "parameters": False,
                    "snapshot": False,
                    "created_at": False,
                },
                "json_types": {"parameters": "JSONB", "snapshot": "JSONB"},
                "run_index": True,
                "operation_check": ["ck_health_safe_planner_operation"],
                "selection": {"nullable": True, "type": "JSONB"},
            }
            if iteration == 0:
                for operation in ("swap", "regeneration"):
                    await insert_safe_receipt(sessions, ids, operation)

        async with sessions() as session:
            assert (
                await session.execute(
                    text("SELECT operation, parameters, snapshot FROM health_safe_planner_preview ORDER BY operation")
                )
            ).all() == [
                ("regeneration", {"synthetic": "parameters"}, {"synthetic": "snapshot"}),
                ("swap", {"synthetic": "parameters"}, {"synthetic": "snapshot"}),
            ]
        with pytest.raises(IntegrityError, match="ck_health_safe_planner_operation"):
            await insert_safe_receipt(sessions, ids, "participation")
        async with sessions() as session:
            assert await session.scalar(text("SELECT COUNT(*) FROM health_safe_planner_preview")) == 2
    finally:
        await _drop_isolated_schema(schema, admin, engine)


async def test_formal_current_schema_rejects_future_before_safe_planner_ddl(monkeypatch, tmp_path):
    """未来版本标记在健康 DDL 前拒绝，旧事实与缺失的新表、新列均保持。"""
    schema, admin, engine, manager = await _create_isolated_manager("pytest_safe_planner_future")
    try:
        sessions, _ids = await prepare_schema20(manager, engine)
        async with sessions() as session:
            before = await preserved_schema20_facts(session)
        await manager.record_schema_version("health", HEALTH_SCHEMA_VERSION + 1)
        manager.AsyncSession = sessions
        isolate_other_migration_effects(monkeypatch, tmp_path)
        monkeypatch.setattr(storage_migration, "pg_manager", manager)
        with pytest.raises(RuntimeError, match=f"Unsupported health schema version: {HEALTH_SCHEMA_VERSION + 1}"):
            await storage_migration.main()
        async with sessions() as session:
            await assert_schema21_safe_planner_absent(session)
            assert (
                await session.scalar(text("SELECT version FROM yuxi_schema_migrations WHERE domain='health'"))
                == HEALTH_SCHEMA_VERSION + 1
            )
            assert await preserved_schema20_facts(session) == before
    finally:
        await _drop_isolated_schema(schema, admin, engine)


async def prepare_schema20(manager, engine):
    """写入合成20事实后删除21结构，明确证明迁移前的表与列缺失。"""
    await manager.create_business_tables()
    await manager.create_schema_version_table()
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    ids = {name: str(uuid4()) for name in ("family", "source", "member", "project", "thread", "run", "plan")}
    uid = "synthetic-safe-planner-migration"
    stamp = datetime(2026, 10, 8, 1, 2, 3)
    async with sessions.begin() as session:
        session.add(User(uid=uid, username=uid, password_hash="not-a-password"))
        await session.flush()
        session.add_all(
            [
                FamilyArchive(id=ids["family"], owner_uid=uid, name="合成旧家庭"),
                FamilyMember(
                    id=ids["member"],
                    owner_uid=uid,
                    display_name="合成成员",
                    relationship_label="本人",
                    created_at=stamp,
                ),
                Project(
                    id=ids["project"],
                    uid=uid,
                    selection_status="implicit",
                    directory_mode="managed",
                    workdir_path="projects/synthetic-safe-planner",
                ),
            ]
        )
        await session.flush()
        session.add(
            SourceMember(
                id=ids["source"],
                family_id=ids["family"],
                subject_uid=uid,
                name="合成成员",
                relationship="本人",
                profile={"height_cm": 170, "synthetic": True},
                version=3,
                confirmed_version=3,
            )
        )
        conversation = Conversation(
            uid=uid, thread_id=ids["thread"], agent_id="health-meal-planner", project_id=ids["project"]
        )
        session.add(conversation)
        await session.flush()
        ids["conversation"] = conversation.id
        ids["uid"] = uid
        session.add_all(
            [
                HealthConsultation(
                    conversation_id=conversation.id,
                    member_id=ids["member"],
                    actor_uid=uid,
                    request_id=str(uuid4()),
                    family_planner_selection={"legacy_family": "retain", "source_hash": "a" * 64},
                    initial_planner_selection={"legacy_initial": "retain", "source_hash": "b" * 64},
                    created_at=stamp,
                ),
                HealthGrant(member_id=ids["member"], actor_uid=uid, scopes=["profile_view", "ai_use"]),
                HealthFamilyProfileLink(
                    member_id=ids["member"], source_member_id=ids["source"], family_id=ids["family"], actor_uid=uid
                ),
                AgentRun(
                    id=ids["run"],
                    request_id=str(uuid4()),
                    uid=uid,
                    agent_slug="health-meal-planner",
                    conversation_id=conversation.id,
                    conversation_thread_id=ids["thread"],
                    runtime_scope_id=ids["thread"],
                    status="completed",
                ),
                HealthMealPlan(
                    id=ids["plan"],
                    actor_uid=uid,
                    member_id=ids["member"],
                    version=2,
                    spec={"synthetic": "old-spec"},
                    snapshot={"synthetic": "old-nutrition"},
                    created_at=stamp,
                    updated_at=stamp,
                ),
            ]
        )
        await session.flush()
        session.add_all(
            [
                HealthMealPlanPreview(
                    id=str(uuid4()),
                    actor_uid=uid,
                    member_id=ids["member"],
                    run_id=ids["run"],
                    spec={"legacy": "single"},
                    snapshot={"legacy": "single-snapshot"},
                    created_at=stamp,
                ),
                HealthInitialPlanPreview(
                    id=str(uuid4()),
                    actor_uid=uid,
                    member_id=ids["member"],
                    conversation_id=conversation.id,
                    run_id=ids["run"],
                    selection={"legacy": "initial"},
                    snapshot={"legacy": "initial-snapshot"},
                    created_at=stamp,
                ),
                HealthFamilyPlannerPreview(
                    id=str(uuid4()),
                    actor_uid=uid,
                    conversation_id=conversation.id,
                    run_id=ids["run"],
                    operation="participation",
                    parameters={"legacy": "family"},
                    snapshot={"legacy": "family-snapshot"},
                    created_at=stamp,
                ),
                HealthMealPlanRevision(
                    id=str(uuid4()),
                    plan_id=ids["plan"],
                    actor_uid=uid,
                    request_id=str(uuid4()),
                    fingerprint="c" * 64,
                    version=2,
                    reason="合成旧修改",
                    spec={"synthetic": "old-spec"},
                    snapshot={"synthetic": "old-nutrition"},
                    created_at=stamp,
                ),
                HealthFamilyProfileUse(
                    run_id=ids["run"],
                    payload_hash="d" * 64,
                    member_id=ids["member"],
                    source_member_id=ids["source"],
                    version=3,
                ),
            ]
        )
        for kind, values, use_model, digest in (
            ("weight", {"weight": 61}, HealthWeightUse, "e"),
            ("blood_pressure", {"systolic": 121, "diastolic": 81}, HealthBloodPressureUse, "f"),
            ("blood_glucose", {"glucose": 5.5}, HealthBloodGlucoseUse, "1"),
            ("blood_lipids", {"tc": 4.8, "tg": 1.4, "hdl_c": 1.3, "ldl_c": 2.7}, HealthBloodLipidsUse, "2"),
        ):
            record_id = str(uuid4())
            session.add(
                FamilyMeasurement(
                    id=record_id,
                    member_id=ids["source"],
                    kind=kind,
                    values=values,
                    measured_at=stamp,
                    source="synthetic-device",
                    condition="synthetic-condition",
                    note="合成更正记录",
                    created_by=uid,
                    creation_intent={"synthetic": True, "values": values},
                    version=2,
                    previous=[{"version": 1, "values": values, "note": "合成旧记录"}],
                    updated_at=stamp,
                )
            )
            session.add(
                use_model(
                    run_id=ids["run"],
                    payload_hash=digest * 64,
                    member_id=ids["member"],
                    source_member_id=ids["source"],
                    start_date=date(2026, 9, 9),
                    end_date=date(2026, 10, 8),
                    record_refs=[{"record_id": record_id, "version": 2}],
                )
            )
    await remove_schema21_safe_planner_structures(engine)
    for domain, version in (
        ("business", BUSINESS_SCHEMA_VERSION),
        ("knowledge", KNOWLEDGE_SCHEMA_VERSION),
        ("health", 20),
    ):
        await manager.record_schema_version(domain, version)
    return sessions, ids


async def preserved_schema20_facts(session):
    """直接读取旧表所有字段，不以当前 ORM 的新增字段生成保留 oracle。"""
    facts = {}
    for table in (
        "users",
        "family_archives",
        "family_members",
        "family_member",
        "family_measurements",
        "health_grant",
        "health_family_profile_link",
        "health_family_profile_use",
        "projects",
        "conversations",
        "agent_runs",
        "health_consultation",
        "health_meal_plan_preview",
        "health_initial_plan_preview",
        "health_family_planner_preview",
        "health_meal_plan",
        "health_meal_plan_revision",
        "health_weight_use",
        "health_blood_pressure_use",
        "health_blood_glucose_use",
        "health_blood_lipids_use",
    ):
        projection = "to_jsonb(fact) - 'safe_planner_selection'" if table == "health_consultation" else "to_jsonb(fact)"
        rows = (await session.scalars(text(f'SELECT {projection} FROM "{table}" AS fact ORDER BY {projection}'))).all()
        assert rows, f"旧事实表 {table} 应保留合成数据"
        facts[table] = rows
    return facts


def safe_planner_catalog(connection):
    """从 PG 目录独立读取新表的主外键、索引、JSONB 与绑定列约束。"""
    inspector = inspect(connection)
    table = "health_safe_planner_preview"
    columns = inspector.get_columns(table)
    selection = next(
        row for row in inspector.get_columns("health_consultation") if row["name"] == "safe_planner_selection"
    )
    return {
        "primary": inspector.get_pk_constraint(table)["constrained_columns"],
        "foreign": {
            (
                tuple(row["constrained_columns"]),
                row["referred_table"],
                tuple(row["referred_columns"]),
                row["options"].get("ondelete"),
            )
            for row in inspector.get_foreign_keys(table)
        },
        "nullable": {row["name"]: row["nullable"] for row in columns},
        "json_types": {row["name"]: str(row["type"]) for row in columns if row["name"] in {"parameters", "snapshot"}},
        "run_index": any(row["column_names"] == ["run_id"] for row in inspector.get_indexes(table)),
        "operation_check": [row["name"] for row in inspector.get_check_constraints(table)],
        "selection": {"nullable": selection["nullable"], "type": str(selection["type"])},
    }


async def insert_safe_receipt(sessions, ids, operation):
    """用真实 SQL 写入回执，验证迁移后的操作约束与幂等重放保留。"""
    async with sessions.begin() as session:
        await session.execute(
            text(
                "INSERT INTO health_safe_planner_preview "
                "(id, actor_uid, conversation_id, run_id, operation, parameters, snapshot, created_at) "
                "VALUES (:id, :uid, :conversation, :run, :operation, "
                '\'{"synthetic":"parameters"}\'::jsonb, \'{"synthetic":"snapshot"}\'::jsonb, :created)'
            ),
            {
                "id": str(uuid4()),
                "uid": ids["uid"],
                "conversation": ids["conversation"],
                "run": ids["run"],
                "operation": operation,
                "created": datetime(2026, 10, 9, 1, 2, 3),
            },
        )

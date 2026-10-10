"""真实隔离PG的health21→22采购绑定/回执升级与重复迁移。"""

from datetime import datetime
from uuid import uuid4

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import async_sessionmaker

from test.integration.services.test_health_family_profile_schema import isolate_other_migration_effects
from test.integration.services.test_schema_migration_version import _create_isolated_manager, _drop_isolated_schema
from yuxi import storage_migration
from yuxi.storage.postgres import manager as manager_module
from yuxi.storage.postgres.models_business import User, Project, Conversation
from yuxi.storage.postgres.models_health import FamilyMember, HealthGrant, HealthConsultation

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.fixture(scope="session", autouse=True)
def ensure_live_api_schema():
    """只用独立Schema，不迁移主API数据库。"""


@pytest.fixture(scope="session", autouse=True)
def cleanup_test_knowledge_resources():
    """没有共享HTTP知识资源。"""
    yield


@pytest.fixture(scope="session", autouse=True)
def cleanup_test_sandboxes():
    """没有沙盒副作用。"""
    yield


async def test_formal_schema21_purchase_upgrade_preserves_binding_and_replays(monkeypatch, tmp_path):
    schema, admin, engine, manager = await _create_isolated_manager("pytest_purchase_schema")
    try:
        await manager.create_business_tables()
        await manager.create_schema_version_table()
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        uid, member, thread, request = "synthetic-purchase-schema", str(uuid4()), str(uuid4()), str(uuid4())
        stamp = datetime(2026, 10, 10, 1, 2, 3)
        async with sessions.begin() as session:
            session.add(User(uid=uid, username=uid, password_hash="not-a-password"))
            await session.flush()
            session.add(
                FamilyMember(
                    id=member, owner_uid=uid, display_name="合成旧成员", relationship_label="本人", created_at=stamp
                )
            )
            session.add(
                Project(
                    id="synthetic-purchase-project",
                    uid=uid,
                    selection_status="implicit",
                    directory_mode="managed",
                    workdir_path="projects/synthetic",
                )
            )
            await session.flush()
            session.add(HealthGrant(member_id=member, actor_uid=uid, scopes=["diet_edit"], revoked_at=None))
            conversation = Conversation(
                uid=uid, thread_id=thread, agent_id="health-consultation", project_id="synthetic-purchase-project"
            )
            session.add(conversation)
            await session.flush()
            cid = conversation.id
            session.add(
                HealthConsultation(
                    conversation_id=cid, member_id=member, actor_uid=uid, request_id=request, created_at=stamp
                )
            )
        async with engine.begin() as conn:
            await conn.execute(text("DROP TABLE health_purchase_preview"))
            await conn.execute(text("ALTER TABLE health_consultation DROP COLUMN IF EXISTS purchase_selection"))
            assert await conn.scalar(text("SELECT to_regclass('health_purchase_preview')")) is None
            assert (
                await conn.scalar(
                    text(
                        "SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=current_schema() "
                        "AND table_name='health_consultation' AND column_name='purchase_selection'"
                    )
                )
                == 0
            )
        for domain, version in (
            ("business", manager_module.BUSINESS_SCHEMA_VERSION),
            ("knowledge", manager_module.KNOWLEDGE_SCHEMA_VERSION),
            ("health", 21),
        ):
            await manager.record_schema_version(domain, version)
        manager.AsyncSession = sessions
        isolate_other_migration_effects(monkeypatch, tmp_path)
        monkeypatch.setattr(storage_migration, "pg_manager", manager)
        monkeypatch.setattr(storage_migration, "HEALTH_SCHEMA_VERSION", 22)
        monkeypatch.setattr(manager_module, "HEALTH_SCHEMA_VERSION", 22)
        for iteration in range(2):
            await storage_migration.main()
            async with sessions() as session:
                assert (
                    await session.scalar(text("SELECT version FROM yuxi_schema_migrations WHERE domain='health'")) == 22
                )
                saved = (
                    await session.execute(
                        text(
                            "SELECT actor_uid, member_id, request_id, created_at, purchase_selection "
                            "FROM health_consultation WHERE conversation_id=:cid"
                        ),
                        {"cid": cid},
                    )
                ).one()
                assert saved[:4] == (uid, member, request, stamp)
                assert saved.purchase_selection == (None if iteration == 0 else {"synthetic": "selected"})
            async with engine.connect() as conn:
                facts = await conn.run_sync(purchase_constraints)
                assert facts == {
                    "unique_run": True,
                    "snapshot": "JSONB",
                    "selection": "JSONB",
                    "foreign_tables": {"users", "health_consultation", "agent_runs"},
                }
            if iteration == 0:
                async with sessions.begin() as session:
                    await session.execute(
                        text(
                            "UPDATE health_consultation SET purchase_selection='{"
                            + '"synthetic":"selected"'
                            + "}'::jsonb WHERE conversation_id=:cid"
                        ),
                        {"cid": cid},
                    )
    finally:
        await _drop_isolated_schema(schema, admin, engine)


def purchase_constraints(conn):
    """数据库目录是约束oracle，不复用ORM期望。"""
    inspector = inspect(conn)
    columns = {item["name"]: str(item["type"]) for item in inspector.get_columns("health_purchase_preview")}
    selection = {item["name"]: str(item["type"]) for item in inspector.get_columns("health_consultation")}
    return {
        "unique_run": any(
            item["column_names"] == ["run_id"] for item in inspector.get_unique_constraints("health_purchase_preview")
        ),
        "snapshot": columns["snapshot"],
        "selection": selection["purchase_selection"],
        "foreign_tables": {item["referred_table"] for item in inspector.get_foreign_keys("health_purchase_preview")},
    }

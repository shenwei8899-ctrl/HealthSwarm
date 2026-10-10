"""隔离PG22→23增加唯一目标绑定列，旧业务绑定及采购选择原样保留。"""

from datetime import datetime
from uuid import uuid4

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import async_sessionmaker

from test.integration.services.test_health_family_profile_schema import isolate_other_migration_effects
from test.integration.services.test_schema_migration_version import _create_isolated_manager, _drop_isolated_schema
from yuxi import storage_migration
from yuxi.storage.postgres import manager as manager_module
from yuxi.storage.postgres.models_business import Conversation, Project, User
from yuxi.storage.postgres.models_health import FamilyMember, HealthConsultation

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.fixture(scope="session", autouse=True)
def ensure_live_api_schema():
    """仅私有Schema，不迁移HTTP实例或其它业务数据库。"""


@pytest.fixture(scope="session", autouse=True)
def cleanup_test_knowledge_resources():
    """未创建共享知识资源。"""
    yield


@pytest.fixture(scope="session", autouse=True)
def cleanup_test_sandboxes():
    """未创建沙盒资源。"""
    yield


async def test_schema22_target_upgrade_preserves_original_binding_and_repeat_migration(monkeypatch, tmp_path):
    schema, admin, engine, manager = await _create_isolated_manager("pytest_agent_target_schema")
    try:
        await manager.create_business_tables()
        await manager.create_schema_version_table()
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        uid, member, thread, request = "synthetic-target-schema", str(uuid4()), str(uuid4()), str(uuid4())
        stamp = datetime(2026, 10, 10, 1, 2, 3)
        purchase = {"selection": {"synthetic": "purchase22"}, "source_hash": "a" * 64}
        target = {
            "selection": {"rule_code": "synthetic-target", "profile_version": 2, "rule_version": 2},
            "source_hash": "b" * 64,
        }
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
                    id="synthetic-target-project",
                    uid=uid,
                    selection_status="implicit",
                    directory_mode="managed",
                    workdir_path="projects/synthetic",
                )
            )
            await session.flush()
            conversation = Conversation(
                uid=uid, thread_id=thread, agent_id="health-consultation", project_id="synthetic-target-project"
            )
            session.add(conversation)
            await session.flush()
            cid = conversation.id
            session.add(
                HealthConsultation(
                    conversation_id=cid,
                    member_id=member,
                    actor_uid=uid,
                    request_id=request,
                    created_at=stamp,
                    purchase_selection=purchase,
                )
            )
        async with engine.begin() as conn:
            await conn.execute(text("ALTER TABLE health_consultation DROP COLUMN IF EXISTS personal_target_selection"))
            assert (
                await conn.scalar(
                    text(
                        "SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=current_schema() "
                        "AND table_name='health_consultation' AND column_name='personal_target_selection'"
                    )
                )
                == 0
            )
        for domain, version in (
            ("business", manager_module.BUSINESS_SCHEMA_VERSION),
            ("knowledge", manager_module.KNOWLEDGE_SCHEMA_VERSION),
            ("health", 22),
        ):
            await manager.record_schema_version(domain, version)
        manager.AsyncSession = sessions
        isolate_other_migration_effects(monkeypatch, tmp_path)
        monkeypatch.setattr(storage_migration, "pg_manager", manager)
        monkeypatch.setattr(storage_migration, "HEALTH_SCHEMA_VERSION", 23)
        monkeypatch.setattr(manager_module, "HEALTH_SCHEMA_VERSION", 23)
        for iteration in range(2):
            await storage_migration.main()
            async with sessions() as session:
                assert (
                    await session.scalar(text("SELECT version FROM yuxi_schema_migrations WHERE domain='health'")) == 23
                )
                saved = (
                    await session.execute(
                        text(
                            "SELECT actor_uid, member_id, request_id, created_at, purchase_selection, "
                            "personal_target_selection FROM health_consultation WHERE conversation_id=:cid"
                        ),
                        {"cid": cid},
                    )
                ).one()
                assert saved[:5] == (uid, member, request, stamp, purchase)
                assert saved.personal_target_selection == (None if iteration == 0 else target)
            async with engine.connect() as conn:
                column = await conn.run_sync(target_column)
                assert column == {"type": "JSONB", "nullable": True, "default": None}
            if iteration == 0:
                async with sessions.begin() as session:
                    await session.execute(
                        text(
                            "UPDATE health_consultation SET personal_target_selection = "
                            "jsonb_build_object('selection', jsonb_build_object('rule_code','synthetic-target',"
                            "'profile_version',2,'rule_version',2),'source_hash',CAST(:hash AS TEXT)) "
                            "WHERE conversation_id=:cid"
                        ),
                        {"hash": "b" * 64, "cid": cid},
                    )
    finally:
        await _drop_isolated_schema(schema, admin, engine)


def target_column(conn):
    """数据库目录独立核对列类型、可空和旧行默认，不复用ORM定义。"""
    item = next(
        column
        for column in inspect(conn).get_columns("health_consultation")
        if column["name"] == "personal_target_selection"
    )
    return {"type": str(item["type"]), "nullable": item["nullable"], "default": item["default"]}

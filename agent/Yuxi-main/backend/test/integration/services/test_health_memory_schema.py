"""已有健康行的增量迁移与重复 DDL 使用真实隔离 PostgreSQL Schema。"""

import pytest
from datetime import date
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker

from test.integration.services.test_schema_migration_version import _create_isolated_manager, _drop_isolated_schema
from test.support.health_schema_legacy import remove_schema21_safe_planner_structures
from yuxi.storage.postgres.models_business import User
from yuxi.storage.postgres.models_health import (
    FamilyMember,
    HealthMemoryFact,
    HealthMealPlan,
    HealthMealPlanPreview,
    HealthMealPlanRevision,
    HealthQualityCheck,
    HealthProfessionalReview,
    HealthReviewAction,
    HealthNextDayProposal,
    HealthMealPlanAdoption,
    HealthMealPlanAdoptionMember,
    HealthMealPlanAdoptionAction,
)
from yuxi.storage.postgres.manager import HEALTH_SCHEMA_VERSION

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.fixture(scope="session", autouse=True)
def ensure_live_api_schema():
    """本文件只使用隔离 Schema。"""


@pytest.fixture(scope="session", autouse=True)
def cleanup_test_knowledge_resources():
    """本文件不创建知识资源。"""
    yield


@pytest.fixture(scope="session", autouse=True)
def cleanup_test_sandboxes():
    """本文件不创建沙盒。"""
    yield


@pytest.mark.parametrize("legacy_version", [4, 5, 6, 7, 8, 9, 10, 11])
async def test_incremental_health_tables_preserve_existing_rows_and_repeat(legacy_version):
    """旧结构缺少新增表；执行真实迁移 Owner 后原行与版本内容均保留。"""
    schema, admin, engine, manager = await _create_isolated_manager("pytest_health_memory_schema")
    try:
        await manager.create_business_tables()
        await manager.create_schema_version_table()
        async with engine.begin() as connection:
            await connection.execute(text("DROP TABLE health_meal_plan_adoption_member"))
            for table in (
                ("health_meal_plan_adoption_action", "health_meal_plan_adoption", "health_next_day_proposal")
                if legacy_version < 11
                else ()
            ):
                await connection.execute(text(f"DROP TABLE {table}"))
            for table in (
                (
                    "health_quality_conversation",
                    "health_review_action",
                    "health_professional_review",
                    "health_quality_check",
                    "health_professional_reviewer",
                    "health_rule_snapshot",
                    "health_profile_snapshot",
                )
                if legacy_version < 10
                else ()
            ):
                await connection.execute(text(f"DROP TABLE {table}"))
            for table in ("health_feedback_write", "health_feedback_conversation") if legacy_version < 9 else ():
                await connection.execute(text(f"DROP TABLE {table}"))
            if legacy_version < 8:
                for table in ("health_meal_plan_revision", "health_meal_plan", "health_meal_plan_preview"):
                    await connection.execute(text(f"DROP TABLE {table}"))
            for table in ("meal_feedback_use", "meal_feedback_revision", "meal_feedback") if legacy_version < 7 else ():
                await connection.execute(text(f"DROP TABLE {table}"))
            if legacy_version < 6:
                await connection.execute(text("DROP TABLE health_memory_use"))
            if legacy_version == 4:
                for table in ("health_daily_conversation", "health_memory_revision", "health_memory_fact"):
                    await connection.execute(text(f"DROP TABLE {table}"))
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions.begin() as session:
            session.add(User(uid="synthetic-owner", username="synthetic-owner", password_hash="not-a-password"))
            await session.flush()
            session.add(
                FamilyMember(
                    id="synthetic-member",
                    owner_uid="synthetic-owner",
                    display_name="合成旧成员",
                    relationship_label="本人",
                )
            )
            await session.flush()
            if legacy_version >= 5:
                session.add(
                    HealthMemoryFact(
                        id="synthetic-fact",
                        actor_uid="synthetic-owner",
                        member_id="synthetic-member",
                        fact_key="preference",
                        content="合成旧记忆",
                        kind="preference",
                        version=3,
                        status="revoked",
                    )
                )
            if legacy_version >= 8:
                session.add(
                    HealthMealPlanPreview(
                        id="synthetic-preview",
                        actor_uid="synthetic-owner",
                        member_id="synthetic-member",
                        spec={"migration": "old-spec"},
                        snapshot={"migration": "old-nutrition"},
                    )
                )
                session.add(
                    HealthMealPlan(
                        id="synthetic-plan",
                        actor_uid="synthetic-owner",
                        member_id="synthetic-member",
                        version=2,
                        spec={"migration": "old-spec"},
                        snapshot={"migration": "old-nutrition"},
                    )
                )
                await session.flush()
                session.add(
                    HealthMealPlanRevision(
                        id="synthetic-plan-revision",
                        plan_id="synthetic-plan",
                        actor_uid="synthetic-owner",
                        request_id="synthetic-plan-request",
                        fingerprint="1" * 64,
                        version=2,
                        reason="迁移保留旧版",
                        spec={"migration": "old-spec"},
                        snapshot={"migration": "old-nutrition"},
                    )
                )
            if legacy_version >= 10:
                session.add(
                    HealthQualityCheck(
                        id="synthetic-check",
                        actor_uid="synthetic-owner",
                        member_id="synthetic-member",
                        plan_id="synthetic-plan",
                        plan_version=2,
                        rule_code="synthetic-rule",
                        request_id="synthetic-check-request",
                        fingerprint="2" * 64,
                        snapshot={"migration": "old-quality"},
                    )
                )
                await session.flush()
                session.add(
                    HealthProfessionalReview(
                        id="synthetic-review",
                        check_id="synthetic-check",
                        actor_uid="synthetic-owner",
                        member_id="synthetic-member",
                        version=3,
                        status="returned",
                    )
                )
                await session.flush()
                session.add(
                    HealthReviewAction(
                        id="synthetic-review-action",
                        review_id="synthetic-review",
                        actor_uid="synthetic-owner",
                        request_id="synthetic-review-request",
                        fingerprint="3" * 64,
                        version=3,
                        status="returned",
                        reason="合成旧审核证据",
                        evidence_refs=["synthetic:old-proof"],
                    )
                )
            if legacy_version == 11:
                session.add(
                    HealthMealPlanAdoption(
                        id="synthetic-old-active-adoption",
                        actor_uid="synthetic-owner",
                        member_id="synthetic-member",
                        plan_id="synthetic-plan",
                        plan_version=2,
                        plan_date=date(2026, 10, 8),
                        review_id="synthetic-review",
                        status="active",
                        version=3,
                        sources={"migration": "old-active-sources"},
                        snapshot={"migration": "old-active-snapshot"},
                    )
                )
        await remove_schema21_safe_planner_structures(engine)
        await manager.record_schema_version("health", legacy_version)
        for iteration in range(2):
            await manager.create_health_tables()
            await manager.record_schema_version("health", HEALTH_SCHEMA_VERSION)
            if iteration == 0 and legacy_version == 10:
                async with sessions.begin() as session:
                    session.add(
                        HealthNextDayProposal(
                            id="synthetic-proposal",
                            actor_uid="synthetic-owner",
                            member_id="synthetic-member",
                            preview_id="synthetic-preview",
                            source_date=date(2026, 10, 7),
                            plan_date=date(2026, 10, 8),
                            request_id="synthetic-proposal-request",
                            fingerprint="4" * 64,
                            source_hash="5" * 64,
                            snapshot={"migration": "new-proposal"},
                        )
                    )
                    session.add(
                        HealthMealPlanAdoption(
                            id="synthetic-adoption",
                            actor_uid="synthetic-owner",
                            member_id="synthetic-member",
                            plan_id="synthetic-plan",
                            plan_version=2,
                            plan_date=date(2026, 10, 8),
                            review_id="synthetic-review",
                            status="invalidated",
                            version=2,
                            sources={"migration": "new-sources"},
                            snapshot={"migration": "new-adoption"},
                        )
                    )
                    await session.flush()
                    session.add(
                        HealthMealPlanAdoptionAction(
                            id="synthetic-adoption-action",
                            adoption_id="synthetic-adoption",
                            actor_uid="synthetic-owner",
                            request_id="synthetic-adoption-request",
                            fingerprint="6" * 64,
                            operation="adopt",
                            version=1,
                            reason="合成采用证据",
                        )
                    )
        async with sessions() as session:
            member = await session.get(FamilyMember, "synthetic-member")
            assert member.display_name == "合成旧成员" and member.owner_uid == "synthetic-owner"
            if legacy_version >= 5:
                fact = await session.get(HealthMemoryFact, "synthetic-fact")
                assert (fact.content, fact.version, fact.status) == ("合成旧记忆", 3, "revoked")
            if legacy_version >= 8:
                plan = await session.get(HealthMealPlan, "synthetic-plan")
                assert plan.version == 2 and plan.spec == {"migration": "old-spec"}
                assert plan.snapshot == {"migration": "old-nutrition"}
                revision = await session.get(HealthMealPlanRevision, "synthetic-plan-revision")
                assert revision.snapshot == plan.snapshot and revision.fingerprint == "1" * 64
            if legacy_version == 10:
                review = await session.get(HealthProfessionalReview, "synthetic-review")
                assert (review.status, review.version) == ("returned", 3)
                assert (await session.get(HealthReviewAction, "synthetic-review-action")).evidence_refs == [
                    "synthetic:old-proof"
                ]
                assert (await session.get(HealthNextDayProposal, "synthetic-proposal")).snapshot == {
                    "migration": "new-proposal"
                }
                adopted = await session.get(HealthMealPlanAdoption, "synthetic-adoption")
                assert adopted.snapshot == {"migration": "new-adoption"} and adopted.sources == {
                    "migration": "new-sources"
                }
                assert adopted.version == 2 and adopted.status == "invalidated"
                assert (await session.get(HealthMealPlanAdoptionAction, "synthetic-adoption-action")).version == 1
            if legacy_version == 11:
                pointer = await session.get(
                    HealthMealPlanAdoptionMember, ("synthetic-owner", "synthetic-member", date(2026, 10, 8))
                )
                adopted = await session.get(HealthMealPlanAdoption, "synthetic-old-active-adoption")
                assert pointer.adoption_id == adopted.id
                assert (adopted.status, adopted.version, adopted.snapshot, adopted.sources) == (
                    "active",
                    3,
                    {"migration": "old-active-snapshot"},
                    {"migration": "old-active-sources"},
                )
            for table in (
                "health_meal_plan_preview",
                "health_meal_plan",
                "health_meal_plan_revision",
                "meal_feedback",
                "meal_feedback_revision",
                "meal_feedback_use",
                "health_memory_fact",
                "health_memory_revision",
                "health_memory_use",
                "health_daily_conversation",
                "health_feedback_conversation",
                "health_feedback_write",
                "health_profile_snapshot",
                "health_rule_snapshot",
                "health_professional_reviewer",
                "health_quality_check",
                "health_professional_review",
                "health_review_action",
                "health_quality_conversation",
                "health_next_day_proposal",
                "health_meal_plan_adoption",
                "health_meal_plan_adoption_member",
                "health_meal_plan_adoption_action",
            ):
                assert await session.scalar(text("SELECT to_regclass(:name)"), {"name": table}) is not None
            assert list((await session.scalars(select(FamilyMember))).all()) == [member]
        assert (await manager.get_schema_versions())["health"] == HEALTH_SCHEMA_VERSION
    finally:
        await _drop_isolated_schema(schema, admin, engine)

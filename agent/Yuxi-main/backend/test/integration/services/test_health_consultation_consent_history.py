"""咨询用途同意撤回后，已存在会话也不能公开历史。"""

from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import async_sessionmaker

from test.integration.services.test_schema_migration_version import _create_isolated_manager, _drop_isolated_schema
from yuxi.repositories.conversation_repository import ConversationRepository
from yuxi.repositories.health_consultation_repository import EDUCATION_HEALTH_AGENTS, HealthConsultationRepository
from yuxi.services.conversation_service import require_user_conversation
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.storage.postgres.models_business import Conversation, Project, User
from yuxi.storage.postgres.models_health import FamilyMember, HealthConsultation, HealthGrant, HealthProcessingConsent
from yuxi.utils.datetime_utils import utc_now_naive

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_revoked_consultation_consent_hides_existing_threads():
    """真实 PG 中保留成员 grant 时，撤回用途同意仍拒绝四类科普会话历史。"""
    schema, admin_engine, engine, manager = await _create_isolated_manager("pytest_consultation_consent_history")
    try:
        await manager.create_business_tables()
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        uid, member_id, project_id = [str(uuid4()) for _ in range(3)]
        thread_ids = {agent_slug: str(uuid4()) for agent_slug in EDUCATION_HEALTH_AGENTS}
        async with sessions.begin() as session:
            session.add(User(uid=uid, username=uid, password_hash="synthetic"))
            await session.flush()
            session.add(FamilyMember(id=member_id, owner_uid=uid, display_name="合成成员", relationship_label="本人"))
            session.add(
                Project(
                    id=project_id,
                    uid=uid,
                    selection_status="implicit",
                    directory_mode="managed",
                    workdir_path=f"projects/{project_id}",
                )
            )
            await session.flush()
            session.add(HealthGrant(member_id=member_id, actor_uid=uid, scopes=["ai_use", "profile_view"]))
            for agent_slug, thread_id in thread_ids.items():
                conversation = Conversation(uid=uid, thread_id=thread_id, agent_id=agent_slug, project_id=project_id)
                session.add(conversation)
                await session.flush()
                session.add(
                    HealthConsultation(
                        conversation_id=conversation.id,
                        member_id=member_id,
                        actor_uid=uid,
                        request_id=str(uuid4()),
                    )
                )
            session.add(
                HealthProcessingConsent(
                    member_id=member_id,
                    actor_uid=uid,
                    purpose="consultation",
                    processor="synthetic-processor",
                    policy_version="synthetic-policy",
                )
            )

        async with sessions.begin() as session:
            for thread_id in thread_ids.values():
                binding = await HealthConsultationRepository(session).authorize(uid, thread_id)
                assert binding.member_id == member_id
                visible = await require_user_conversation(ConversationRepository(session), thread_id, uid)
                assert visible.id == binding.conversation_id

        async with sessions.begin() as session:
            consent = await session.get(HealthProcessingConsent, (member_id, uid, "consultation"))
            consent.revoked_at = utc_now_naive()

        async with sessions.begin() as session:
            for thread_id in thread_ids.values():
                with pytest.raises(HealthVisionError, match="consent_required"):
                    await HealthConsultationRepository(session).authorize(uid, thread_id, lock=True)
                with pytest.raises(HTTPException, match="对话线程不存在或无权访问"):
                    await require_user_conversation(ConversationRepository(session), thread_id, uid)
    finally:
        await _drop_isolated_schema(schema, admin_engine, engine)

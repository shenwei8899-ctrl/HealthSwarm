"""配餐参考来源的真实 PostgreSQL、HTTP 回读和恢复边界。"""

import json
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from server.routers.chat_router import chat
from server.routers.health_vision_router import health_vision
from server.utils.auth_middleware import get_db, get_required_user, get_superadmin_user
from test.integration.services.test_schema_migration_version import _create_isolated_manager, _drop_isolated_schema
from yuxi.services import health_family_kb_service as service, health_task_service
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.storage.postgres.models_business import (
    TOOL_AUDIT_MESSAGE_TYPE,
    AgentRun,
    AgentRunRequest,
    Conversation,
    Message,
    Project,
    User,
)
from yuxi.storage.postgres.models_health import FamilyMember, HealthConsultation, HealthGrant
from yuxi.storage.postgres.models_knowledge import KnowledgeBase, KnowledgeChunk, KnowledgeFile

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.fixture(scope="session", autouse=True)
def ensure_live_api_schema():
    """本文件仅操作独立测试 Schema。"""


@pytest.fixture(scope="session", autouse=True)
def cleanup_test_knowledge_resources():
    """知识数据随独立 Schema 清理。"""
    yield


@pytest.fixture(scope="session", autouse=True)
def cleanup_test_sandboxes():
    """本测试无需沙盒。"""
    yield


async def test_recipe_reference_publication_replay_and_http_invalidate(monkeypatch):
    """参考可追溯但不能当正式依据；改版、解绑和删除拒绝旧来源。"""
    schema, admin, engine, manager = await _create_isolated_manager("pytest_planner_recipe")
    try:
        await manager.create_business_tables()
        await manager.create_knowledge_tables()
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        manager.AsyncSession = sessions
        uid, member_id, project_id, thread_id, run_id, request_id = [str(uuid4()) for _ in range(6)]
        kb_id, file_id, chunk_id, source_id, tool_id = [str(uuid4()) for _ in range(5)]
        monkeypatch.setenv(service.RECIPE_KB_ID_ENV, kb_id)
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
            session.add(KnowledgeBase(kb_id=kb_id, name="合成菜谱参考", kb_type="milvus"))
            await session.flush()
            conversation = Conversation(
                uid=uid, thread_id=thread_id, agent_id=service.PLANNER_SLUG, project_id=project_id
            )
            session.add(conversation)
            await session.flush()
            session.add(HealthGrant(member_id=member_id, actor_uid=uid, scopes=["ai_use", "report_view", "diet_edit"]))
            session.add(
                HealthConsultation(
                    conversation_id=conversation.id, member_id=member_id, actor_uid=uid, request_id=str(uuid4())
                )
            )
            file = KnowledgeFile(
                file_id=file_id, kb_id=kb_id, filename="合成烹饪资料.md", status="indexed", content_hash="v1"
            )
            session.add(file)
            await session.flush()
            chunk = KnowledgeChunk(
                chunk_id=chunk_id, file_id=file_id, kb_id=kb_id, chunk_index=0, content="合成烹饪方法参考。"
            )
            session.add(chunk)
            run = AgentRun(
                id=run_id,
                conversation_id=conversation.id,
                conversation_thread_id=thread_id,
                runtime_scope_id=thread_id,
                agent_slug=service.PLANNER_SLUG,
                uid=uid,
                status="completed",
                request_id=request_id,
                input_payload={"health_processing": {"synthetic": True}},
                manifest={"resources": {"tools": [service.TOOL_NAME]}},
            )
            session.add(run)
            await session.flush()
            incoming = Message(
                conversation_id=conversation.id,
                role="user",
                content="合成配餐测试",
                request_id=request_id,
                run_id=run_id,
            )
            session.add(incoming)
            await session.flush()
            run.input_message_id = incoming.id
            session.add(
                AgentRunRequest(
                    request_id=request_id,
                    uid=uid,
                    agent_slug=service.PLANNER_SLUG,
                    conversation_thread_id=thread_id,
                    input_message_id=incoming.id,
                    input_payload=run.input_payload,
                    status="dispatched",
                    dispatched_run_id=run_id,
                )
            )
        async with sessions.begin() as session:
            file = await session.scalar(select(KnowledgeFile).where(KnowledgeFile.file_id == file_id))
            chunk = await session.scalar(select(KnowledgeChunk).where(KnowledgeChunk.chunk_id == chunk_id))
            source = service._project_source(kb_id, file, chunk, source_id)
            receipt = {
                "status": "ok",
                "scope": "recipe_reference",
                "query": "合成烹饪",
                "kb_ids": [kb_id],
                "sources": [source],
            }
            receipt_text = json.dumps(receipt, ensure_ascii=False)
            audit = Message(
                conversation_id=conversation.id,
                role="tool",
                message_type=TOOL_AUDIT_MESSAGE_TYPE,
                run_id=run_id,
                request_id=request_id,
                operation_id=tool_id,
                execution_status="completed",
                content=receipt_text,
                extra_metadata={
                    "tool_name": service.TOOL_NAME,
                    "tool_call_id": tool_id,
                    "output": {"type": "tool", "status": "success", "content": receipt_text},
                },
            )
            session.add(audit)
            payload = {
                "questions": ["请先选择已发布菜谱。"],
                **health_task_service.PLANNER_BOUNDARY,
                "status": "needs_input",
            }
            answer = json.dumps(payload, ensure_ascii=False)
            output = Message(
                conversation_id=conversation.id, role="assistant", content=answer, request_id=request_id, run_id=run_id
            )
            session.add(output)
            await session.flush()
            audit_id = audit.id
            run = await session.get(AgentRun, run_id)
            run.output_message_id = output.id

        binding = SimpleNamespace(
            conversation_id=conversation.id,
            member_id=member_id,
            actor_uid=uid,
            initial_planner_selection=None,
            family_planner_selection=None,
            safe_planner_selection=None,
        )
        context = SimpleNamespace(thread_id=thread_id, uid=uid)
        tool_message = SimpleNamespace(tool_call_id=tool_id, status="success", content=receipt_text)

        async def synthetic_policy(_session, _uid, _thread, **kwargs):
            return binding, kwargs.get("expected")

        monkeypatch.setattr(health_task_service, "pg_manager", manager)
        monkeypatch.setattr(health_task_service, "require_consultation", synthetic_policy)
        app = FastAPI()
        app.include_router(chat, prefix="/api")
        app.include_router(health_vision, prefix="/api")
        app.dependency_overrides[get_required_user] = lambda: SimpleNamespace(uid=uid)
        app.dependency_overrides[get_superadmin_user] = lambda: SimpleNamespace(uid=uid)

        async def isolated_session():
            async with sessions.begin() as session:
                yield session

        app.dependency_overrides[get_db] = isolated_session

        async def verify_current(*, invalid=False):
            """真实回执、当前行和 HTTP 投影在同一阶段核对。"""
            async with sessions.begin() as session:
                run = await session.get(AgentRun, run_id)
                checks = [
                    lambda: service.validate_family_kb_publication(session, run, binding, answer),
                    lambda: health_task_service.validate_task_business_result(session, run, binding, payload, answer),
                    lambda: service.validate_family_kb_checkpoint(session, context, binding, tool_message),
                    lambda: service.validate_family_kb_audit(session, awaitable_audit),
                ]
                awaitable_audit = await session.get(Message, audit_id)
                for check in checks:
                    if invalid:
                        with pytest.raises(HealthVisionError, match="source_invalidated"):
                            await check()
                    else:
                        await check()
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
                audits = await client.get(f"/api/chat/thread/{thread_id}/audits")
                task = await client.get(f"/api/health/v1/tasks/{request_id}")
            if invalid:
                assert audits.status_code == task.status_code == 410, (audits.text, task.text)
                assert source_id not in audits.text and payload["questions"][0] not in task.text
            else:
                assert audits.status_code == task.status_code == 200, (audits.text, task.text)
                assert source_id in audits.text
                assert task.json()["result"]["questions"] == payload["questions"]

        await verify_current()
        async with sessions.begin() as session:
            run = await session.get(AgentRun, run_id)
            with pytest.raises(HealthVisionError, match="citation_invalid"):
                await service.validate_family_kb_publication(session, run, binding, f"[资料:{source_id}]")
            # 邻运行请求和其他角色的回执均不能通过审计或重放。
            audit = await session.get(Message, audit_id)
            audit.request_id = str(uuid4())
        await verify_current(invalid=True)
        async with sessions.begin() as session:
            audit = await session.get(Message, audit_id)
            audit.request_id = request_id
            run = await session.get(AgentRun, run_id)
            run.agent_slug = "health-consultation"
        async with sessions.begin() as session:
            with pytest.raises(HealthVisionError, match="source_invalidated"):
                await service.validate_family_kb_checkpoint(session, context, binding, tool_message)
            with pytest.raises(HealthVisionError, match="source_invalidated"):
                await service.validate_family_kb_audit(session, await session.get(Message, audit_id))
        async with sessions.begin() as session:
            run = await session.get(AgentRun, run_id)
            run.agent_slug = service.PLANNER_SLUG
        for value in ("", str(uuid4())):
            monkeypatch.setenv(service.RECIPE_KB_ID_ENV, value)
            await verify_current(invalid=True)
        monkeypatch.setenv(service.RECIPE_KB_ID_ENV, kb_id)
        async with sessions.begin() as session:
            chunk = await session.scalar(select(KnowledgeChunk).where(KnowledgeChunk.chunk_id == chunk_id))
            chunk.content = "改版后的合成烹饪方法。"
        await verify_current(invalid=True)
        async with sessions.begin() as session:
            chunk = await session.scalar(select(KnowledgeChunk).where(KnowledgeChunk.chunk_id == chunk_id))
            chunk.content = source["content"]
        await verify_current()
        async with sessions.begin() as session:
            await session.delete(
                await session.scalar(select(KnowledgeChunk).where(KnowledgeChunk.chunk_id == chunk_id))
            )
        await verify_current(invalid=True)
    finally:
        await _drop_isolated_schema(schema, admin, engine)

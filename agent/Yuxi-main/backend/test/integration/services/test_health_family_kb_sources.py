"""家庭科普同 Run 审计和当前分片在隔离 PostgreSQL Schema 中核对。"""

import asyncio
import json
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import delete, select, text, update
from sqlalchemy.ext.asyncio import async_sessionmaker

from server.routers.health_vision_router import health_vision
from server.utils.auth_middleware import get_required_user
from test.integration.services.test_schema_migration_version import _create_isolated_manager, _drop_isolated_schema
from yuxi.repositories.health_consultation_repository import HealthConsultationRepository
from yuxi.services import health_family_kb_service as service, health_task_service
from yuxi.services.health_evidence_service import read_public_consultation_answer
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.storage.postgres.models_business import (
    AgentRun,
    AgentRunRequest,
    Conversation,
    Message,
    Project,
    TOOL_AUDIT_MESSAGE_TYPE,
    User,
)
from yuxi.storage.postgres.models_knowledge import KnowledgeBase, KnowledgeChunk, KnowledgeFile
from yuxi.storage.postgres.models_health import (
    FamilyMember,
    HealthConsultation,
    HealthGrant,
    HealthProcessingConsent,
)

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.fixture(scope="session", autouse=True)
def ensure_live_api_schema():
    """只使用本测试独立 Schema，不检查运行中 API。"""


@pytest.fixture(scope="session", autouse=True)
def cleanup_test_knowledge_resources():
    """测试知识文件只存在于独立 Schema。"""
    yield


@pytest.fixture(scope="session", autouse=True)
def cleanup_test_sandboxes():
    """本测试不创建沙盒资源。"""
    yield


async def test_persisted_family_source_is_required_and_invalidates_after_reindex(monkeypatch):
    """真实 PG 审计准许当前答复；任务 HTTP 在分片改写或删除后均拒绝旧正文。"""
    schema, admin_engine, engine, manager = await _create_isolated_manager("pytest_health_family_kb")
    try:
        await manager.create_business_tables()
        await manager.create_knowledge_tables()
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        manager.AsyncSession = sessions
        uid, member_id, project_id, thread_id, run_id, request_id = [str(uuid4()) for _ in range(6)]
        kb_id, file_id, chunk_id, source_id = [str(uuid4()) for _ in range(4)]
        monkeypatch.setenv(service.KB_ID_ENV, kb_id)
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
            session.add(KnowledgeBase(kb_id=kb_id, name="合成家庭营养库", kb_type="milvus"))
            await session.flush()
            conversation = Conversation(
                uid=uid, thread_id=thread_id, agent_id="health-consultation", project_id=project_id
            )
            session.add(conversation)
            await session.flush()
            session.add(HealthGrant(member_id=member_id, actor_uid=uid, scopes=["ai_use"]))
            session.add(
                HealthProcessingConsent(
                    member_id=member_id,
                    actor_uid=uid,
                    purpose="consultation",
                    processor="synthetic-test",
                    policy_version="synthetic-test",
                )
            )
            session.add(
                HealthConsultation(
                    conversation_id=conversation.id,
                    member_id=member_id,
                    actor_uid=uid,
                    request_id=str(uuid4()),
                )
            )
            session.add(
                KnowledgeFile(file_id=file_id, kb_id=kb_id, filename="合成科普.md", status="indexed", content_hash="v1")
            )
            await session.flush()
            session.add(
                KnowledgeChunk(
                    chunk_id=chunk_id, file_id=file_id, kb_id=kb_id, chunk_index=0, content="合成一般科普资料。"
                )
            )
            session.add(
                AgentRun(
                    id=run_id,
                    conversation_id=conversation.id,
                    conversation_thread_id=thread_id,
                    runtime_scope_id=thread_id,
                    agent_slug="health-consultation",
                    uid=uid,
                    status="completed",
                    request_id=request_id,
                    input_payload={"health_processing": {"synthetic": "family-kb"}},
                    manifest={
                        "resources": {
                            "tools": [
                                "query_family_nutrition_knowledge",
                                "query_reviewed_nutrition_knowledge",
                                "get_member_memories",
                            ]
                        }
                    },
                )
            )
            await session.flush()
            input_message = Message(
                conversation_id=conversation.id,
                role="user",
                content="合成家庭营养科普问题",
                request_id=request_id,
                run_id=run_id,
            )
            session.add(input_message)
            await session.flush()
            run = await session.get(AgentRun, run_id)
            run.input_message_id = input_message.id
            session.add(
                AgentRunRequest(
                    request_id=request_id,
                    uid=uid,
                    agent_slug="health-consultation",
                    conversation_thread_id=thread_id,
                    input_message_id=input_message.id,
                    input_payload=run.input_payload,
                    status="dispatched",
                    dispatched_run_id=run_id,
                )
            )

        async with sessions.begin() as session:
            file = await session.scalar(select(KnowledgeFile).where(KnowledgeFile.file_id == file_id))
            chunk = await session.scalar(select(KnowledgeChunk).where(KnowledgeChunk.chunk_id == chunk_id))
            source = service._project_source(kb_id, file, chunk, source_id)
            tool_call_id = str(uuid4())
            payload = {
                "status": "ok",
                "scope": "general_education",
                "query": "合成一般科普",
                "kb_id": kb_id,
                "sources": [source],
            }
            family_audit = Message(
                conversation_id=conversation.id,
                role="tool",
                message_type=TOOL_AUDIT_MESSAGE_TYPE,
                run_id=run_id,
                request_id=request_id,
                operation_id=tool_call_id,
                execution_status="completed",
                content=json.dumps(payload, ensure_ascii=False),
                extra_metadata={
                    "tool_name": service.TOOL_NAME,
                    "tool_call_id": tool_call_id,
                    "output": {"type": "tool", "status": "success", "content": json.dumps(payload, ensure_ascii=False)},
                },
            )
            session.add(family_audit)
            await session.flush()
            family_audit_id = family_audit.id
        answer = f"一般科普资料参见《{source['filename']}》[资料:{source_id}]"
        binding = SimpleNamespace(conversation_id=conversation.id, member_id=member_id, actor_uid=uid)
        context = SimpleNamespace(thread_id=thread_id, uid=uid)
        tool_message = SimpleNamespace(
            tool_call_id=tool_call_id, status="success", content=json.dumps(payload, ensure_ascii=False)
        )
        async with sessions.begin() as session:
            output = Message(
                conversation_id=conversation.id,
                role="assistant",
                content=answer,
                request_id=request_id,
                run_id=run_id,
            )
            session.add(output)
            await session.flush()
            run = await session.get(AgentRun, run_id)
            run.output_message_id = output.id

        async def current_consultation(_session, _uid, _thread_id, **kwargs):
            return binding, kwargs.get("expected")

        monkeypatch.setattr(health_task_service, "pg_manager", manager)
        monkeypatch.setattr(health_task_service, "require_consultation", current_consultation)
        app = FastAPI()
        app.include_router(health_vision, prefix="/api")
        app.dependency_overrides[get_required_user] = lambda: SimpleNamespace(uid=uid)

        async def read_task():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
                return await client.get(f"/api/health/v1/tasks/{request_id}")

        async with sessions.begin() as session:
            run = await session.get(AgentRun, run_id)
            await service.validate_family_kb_publication(session, run, binding, answer)
            await service.validate_family_kb_answer(session, run, binding, answer)
            await service.validate_family_kb_checkpoint(session, context, binding, tool_message)
            await service.validate_family_kb_audit(session, await session.get(Message, family_audit_id))
            await HealthConsultationRepository(session).authorize(uid, thread_id)
            assert (await read_public_consultation_answer(session, run, uid)).content == answer
        task = await read_task()
        assert task.status_code == 200 and task.json()["result"]["answer"] == answer, task.text

        legacy_run_id = str(uuid4())
        async with sessions.begin() as session:
            session.add(
                AgentRun(
                    id=legacy_run_id,
                    conversation_id=conversation.id,
                    conversation_thread_id=thread_id,
                    runtime_scope_id=thread_id,
                    agent_slug="health-consultation",
                    uid=uid,
                    status="completed",
                    request_id=str(uuid4()),
                    manifest={"resources": {"tools": ["get_confirmed_profile"]}},
                )
            )
        async with sessions.begin() as session:
            run = await session.get(AgentRun, run_id)
            with pytest.raises(HealthVisionError, match="not_found"):
                await HealthConsultationRepository(session).authorize(uid, thread_id)
            with pytest.raises(HealthVisionError, match="not_found"):
                await read_public_consultation_answer(session, run, uid)
        async with sessions.begin() as session:
            await session.delete(await session.get(AgentRun, legacy_run_id))

        async with sessions.begin() as session:
            old_profile_audit = Message(
                conversation_id=conversation.id,
                role="tool",
                message_type=TOOL_AUDIT_MESSAGE_TYPE,
                run_id=run_id,
                request_id=request_id,
                operation_id=str(uuid4()),
                execution_status="completed",
                content="合成旧档案工具结果",
                extra_metadata={"tool_name": "get_confirmed_profile"},
            )
            session.add(old_profile_audit)
            await session.flush()
            old_profile_audit_id = old_profile_audit.id
        async with sessions.begin() as session:
            run = await session.get(AgentRun, run_id)
            with pytest.raises(HealthVisionError, match="not_found"):
                await HealthConsultationRepository(session).authorize(uid, thread_id)
            with pytest.raises(HealthVisionError, match="not_found"):
                await read_public_consultation_answer(session, run, uid)
        async with sessions.begin() as session:
            await session.delete(await session.get(Message, old_profile_audit_id))

        async with sessions.begin() as session:
            chunk = await session.scalar(select(KnowledgeChunk).where(KnowledgeChunk.chunk_id == chunk_id))
            chunk.content = "合成资料已重新解析。"
        async with sessions.begin() as session:
            run = await session.get(AgentRun, run_id)
            with pytest.raises(HealthVisionError, match="source_invalidated"):
                await read_public_consultation_answer(session, run, uid)
            with pytest.raises(HealthVisionError, match="source_invalidated"):
                await service.validate_family_kb_checkpoint(session, context, binding, tool_message)
            with pytest.raises(HealthVisionError, match="source_invalidated"):
                await service.validate_family_kb_audit(session, await session.get(Message, family_audit_id))
        changed = await read_task()
        assert changed.status_code == 410 and changed.json()["code"] == "source_invalidated", changed.text
        assert answer not in changed.text

        async with sessions.begin() as session:
            chunk = await session.scalar(select(KnowledgeChunk).where(KnowledgeChunk.chunk_id == chunk_id))
            chunk.content = source["content"]
        restored = await read_task()
        assert restored.status_code == 200 and restored.json()["result"]["answer"] == answer, restored.text

        async with sessions.begin() as session:
            chunk = await session.scalar(select(KnowledgeChunk).where(KnowledgeChunk.chunk_id == chunk_id))
            await session.delete(chunk)
        deleted = await read_task()
        assert deleted.status_code == 410 and deleted.json()["code"] == "source_invalidated", deleted.text
        assert answer not in deleted.text
    finally:
        await _drop_isolated_schema(schema, admin_engine, engine)


async def test_publication_holds_source_share_locks_until_transaction_finishes(monkeypatch):
    """发布事务结束前，来源文件改写和分片删除都必须被真实 PG 行锁阻塞。"""
    schema, admin_engine, engine, manager = await _create_isolated_manager("pytest_health_family_kb_lock")
    writers: list[asyncio.Task] = []
    try:
        await manager.create_business_tables()
        await manager.create_knowledge_tables()
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        uid, project_id, thread_id, run_id, request_id = [str(uuid4()) for _ in range(5)]
        kb_id, file_id, chunk_id, source_id = [str(uuid4()) for _ in range(4)]
        tool_call_id = str(uuid4())
        monkeypatch.setenv(service.KB_ID_ENV, kb_id)

        async with sessions.begin() as session:
            session.add(User(uid=uid, username=uid, password_hash="synthetic"))
            await session.flush()
            session.add(
                Project(
                    id=project_id,
                    uid=uid,
                    selection_status="implicit",
                    directory_mode="managed",
                    workdir_path=f"projects/{project_id}",
                )
            )
            session.add(KnowledgeBase(kb_id=kb_id, name="合成家庭营养库", kb_type="milvus"))
            await session.flush()
            conversation = Conversation(
                uid=uid, thread_id=thread_id, agent_id="health-consultation", project_id=project_id
            )
            session.add(conversation)
            await session.flush()
            file = KnowledgeFile(
                file_id=file_id,
                kb_id=kb_id,
                filename="发布锁科普.md",
                status="indexed",
                content_hash="v1",
            )
            session.add(file)
            await session.flush()
            chunk = KnowledgeChunk(
                chunk_id=chunk_id,
                file_id=file_id,
                kb_id=kb_id,
                chunk_index=0,
                content="发布锁一般科普资料。",
            )
            session.add(chunk)
            run = AgentRun(
                id=run_id,
                conversation_id=conversation.id,
                conversation_thread_id=thread_id,
                runtime_scope_id=thread_id,
                agent_slug="health-consultation",
                uid=uid,
                status="completed",
                request_id=request_id,
                manifest={"resources": {"tools": [service.TOOL_NAME]}},
            )
            session.add(run)
            await session.flush()
            source = service._project_source(kb_id, file, chunk, source_id)
            payload = {
                "status": "ok",
                "scope": "general_education",
                "query": "发布锁一般科普",
                "kb_id": kb_id,
                "sources": [source],
            }
            payload_json = json.dumps(payload, ensure_ascii=False)
            session.add(
                Message(
                    conversation_id=conversation.id,
                    role="tool",
                    message_type=TOOL_AUDIT_MESSAGE_TYPE,
                    run_id=run_id,
                    request_id=request_id,
                    operation_id=tool_call_id,
                    execution_status="completed",
                    content=payload_json,
                    extra_metadata={
                        "tool_name": service.TOOL_NAME,
                        "tool_call_id": tool_call_id,
                        "output": {"type": "tool", "status": "success", "content": payload_json},
                    },
                )
            )

        answer = f"一般科普资料参见《{source['filename']}》[资料:{source_id}]"
        binding = SimpleNamespace(conversation_id=conversation.id, actor_uid=uid)
        writer_started = {name: asyncio.Event() for name in ("file", "chunk")}
        writer_committed = {name: asyncio.Event() for name in ("file", "chunk")}
        writer_pids: dict[str, int] = {}

        async def rewrite_file() -> None:
            """尝试在独立事务中改写已引用文件版本。"""
            async with sessions.begin() as session:
                writer_pids["file"] = await session.scalar(text("SELECT pg_backend_pid()"))
                writer_started["file"].set()
                await session.execute(
                    update(KnowledgeFile).where(KnowledgeFile.file_id == file_id).values(content_hash="v2")
                )
            writer_committed["file"].set()

        async def delete_chunk() -> None:
            """尝试在独立事务中删除已引用分片。"""
            async with sessions.begin() as session:
                writer_pids["chunk"] = await session.scalar(text("SELECT pg_backend_pid()"))
                writer_started["chunk"].set()
                await session.execute(delete(KnowledgeChunk).where(KnowledgeChunk.chunk_id == chunk_id))
            writer_committed["chunk"].set()

        async def wait_until_blocked(writer_pid: int, publication_pid: int) -> None:
            """等待 PostgreSQL 报告写事务正由发布事务阻塞。"""
            deadline = asyncio.get_running_loop().time() + 5
            while asyncio.get_running_loop().time() < deadline:
                async with sessions() as session:
                    blockers = await session.scalar(
                        text("SELECT pg_blocking_pids(:writer_pid)"), {"writer_pid": writer_pid}
                    )
                if publication_pid in blockers:
                    return
                await asyncio.sleep(0.02)
            raise AssertionError(f"写事务 {writer_pid} 未被发布事务 {publication_pid} 阻塞")

        try:
            async with sessions.begin() as publication_session:
                publication_pid = await publication_session.scalar(text("SELECT pg_backend_pid()"))
                run = await publication_session.get(AgentRun, run_id)
                await service.validate_family_kb_publication(publication_session, run, binding, answer)

                writers = [asyncio.create_task(rewrite_file()), asyncio.create_task(delete_chunk())]
                await asyncio.gather(*(event.wait() for event in writer_started.values()))
                await asyncio.gather(
                    *(wait_until_blocked(writer_pids[name], publication_pid) for name in ("file", "chunk"))
                )
                assert not any(event.is_set() for event in writer_committed.values())
        finally:
            if writers:
                await asyncio.gather(*writers, return_exceptions=True)

        assert all(event.is_set() for event in writer_committed.values())
        async with sessions.begin() as session:
            run = await session.get(AgentRun, run_id)
            with pytest.raises(HealthVisionError) as invalidated:
                await service.validate_family_kb_answer(session, run, binding, answer)
        assert invalidated.value.code == "source_invalidated"
        assert invalidated.value.status == 410
    finally:
        await _drop_isolated_schema(schema, admin_engine, engine)

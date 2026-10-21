"""按健康角色绑定知识库的一般科普检索与当前来源校验。"""

import hashlib
import json
import os
import re
from itertools import zip_longest
from uuid import UUID, uuid4

from langchain_core.messages import HumanMessage, ToolMessage
from sqlalchemy import select

from yuxi.knowledge.base import FileStatus
from yuxi.knowledge.implementations.milvus import OrphanedMilvusHitsError
from yuxi.knowledge.runtime import knowledge_base
from yuxi.repositories.health_consultation_repository import (
    CONSULTATION_SLUG,
    GLUCOSE_SLUG,
    LIPIDS_SLUG,
    PRESSURE_SLUG,
    PLANNER_SLUG,
    EDUCATION_HEALTH_AGENTS,
    HealthConsultationRepository,
)
from yuxi.repositories.tool_message_audit_repository import ToolMessageAuditRepository
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_business import AgentRun, Conversation, Message, TOOL_AUDIT_MESSAGE_TYPE
from yuxi.storage.postgres.models_knowledge import KnowledgeBase, KnowledgeChunk, KnowledgeFile
from yuxi.utils.datetime_utils import format_utc_datetime

TOOL_NAME = "query_family_nutrition_knowledge"
KB_ID_ENV = "HEALTH_FAMILY_NUTRITION_KB_ID"
RECIPE_KB_ID_ENV = "HEALTH_RECIPE_KB_ID"
KNOWLEDGE_HEALTH_AGENTS = EDUCATION_HEALTH_AGENTS | {PLANNER_SLUG}
INDICATOR_KB_ENVS = {
    GLUCOSE_SLUG: "HEALTH_BLOOD_GLUCOSE_KB_IDS",
    LIPIDS_SLUG: "HEALTH_BLOOD_LIPIDS_KB_IDS",
    PRESSURE_SLUG: "HEALTH_BLOOD_PRESSURE_KB_IDS",
}
MAX_SOURCES = 4
MAX_SOURCE_CHARS = 1200
SOURCE_KEYS = frozenset(
    {
        "source_id",
        "kb_id",
        "file_id",
        "chunk_id",
        "filename",
        "file_content_hash",
        "file_updated_at",
        "chunk_hash",
        "content",
    }
)
SOURCE_MARKER = re.compile(r"\[资料:([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\]")


def filter_family_kb_history(messages):
    """模型输入删除含家庭库回执的旧轮次，当前轮必须重新检索。"""
    chunks, chunk = [], []
    for message in messages:
        if isinstance(message, HumanMessage) and chunk:
            chunks.append(chunk)
            chunk = []
        chunk.append(message)
    if chunk:
        chunks.append(chunk)

    filtered = []
    for index, turn in enumerate(chunks):
        historical_family_turn = index < len(chunks) - 1 and any(
            isinstance(message, ToolMessage) and message.name == TOOL_NAME for message in turn
        )
        if historical_family_turn:
            filtered.extend(message for message in turn if isinstance(message, HumanMessage))
        else:
            filtered.extend(turn)
    return filtered


async def search_family_nutrition_knowledge(context, query: str) -> dict:
    """按真实 Run 角色检索固定库，返回经 PG 重验的有界科普片段。"""
    if not isinstance(query, str) or not 1 <= len(query.strip()) <= 120:
        raise HealthVisionError("knowledge_query_invalid", "请使用简短的营养科普主题词", 422)
    query = query.strip()
    async with pg_manager.get_async_session_context() as session:
        run, _ = await _authorized_run(session, context)
        agent_slug = run.agent_slug
        kb_ids = configured_health_kb_ids(agent_slug)
        for kb_id in kb_ids:
            await _require_fixed_kb(session, kb_id)

    hit_groups = []
    try:
        for kb_id in kb_ids:
            retrieved = await knowledge_base.retrieve(
                kb_id,
                query,
                final_top_k=MAX_SOURCES,
                search_mode="keyword",
                use_reranker=False,
                use_graph_retrieval=False,
                read_only=True,
            )
            hits = retrieved.get("results") if isinstance(retrieved, dict) else None
            if not isinstance(hits, list):
                raise ValueError("invalid knowledge results")
            hit_groups.append([(kb_id, hit) for hit in hits[:MAX_SOURCES]])
    except OrphanedMilvusHitsError as error:
        raise HealthVisionError("source_invalidated", "家庭科普检索命中已失效，请稍后重试", 410) from error
    except Exception as error:
        raise HealthVisionError("knowledge_unavailable", "家庭营养科普资料暂不可用，请稍后再试", 503) from error
    async with pg_manager.get_async_session_context() as session:
        current_run, _ = await _authorized_run(session, context)
        if current_run.agent_slug != agent_slug or configured_health_kb_ids(agent_slug) != kb_ids:
            raise HealthVisionError("source_invalidated", "科普知识库绑定已变化，请重新检索", 410)
        for kb_id in kb_ids:
            await _require_fixed_kb(session, kb_id)
        sources = []
        seen_chunks = set()
        # 每库取一条后再取下一轮，保持配置顺序并避免首库占满结果。
        hits = [item for group in zip_longest(*hit_groups) for item in group if item is not None]
        for kb_id, hit in hits:
            if len(sources) == MAX_SOURCES:
                break
            if not isinstance(hit, dict) or hit.get("kb_id") != kb_id:
                continue
            chunk_id, file_id = hit.get("id"), hit.get("file_id")
            if not isinstance(chunk_id, str) or not isinstance(file_id, str) or (kb_id, chunk_id) in seen_chunks:
                continue
            chunk = await session.scalar(
                select(KnowledgeChunk).where(
                    KnowledgeChunk.chunk_id == chunk_id,
                    KnowledgeChunk.file_id == file_id,
                    KnowledgeChunk.kb_id == kb_id,
                )
            )
            file = await session.scalar(
                select(KnowledgeFile).where(KnowledgeFile.file_id == file_id, KnowledgeFile.kb_id == kb_id)
            )
            if (
                chunk is None
                or file is None
                or file.status != FileStatus.INDEXED
                or not file.filename.strip()
                or not chunk.content.strip()
                or chunk.content != hit.get("content")
            ):
                continue
            sources.append(_project_source(kb_id, file, chunk, str(uuid4())))
            seen_chunks.add((kb_id, chunk_id))
    if hits and not sources:
        raise HealthVisionError("source_invalidated", "家庭科普检索命中已失效，请稍后重试", 410)

    return {
        "status": "ok" if sources else "insufficient_material",
        "scope": "recipe_reference" if agent_slug == PLANNER_SLUG else "general_education",
        "query": query,
        **({"kb_id": kb_ids[0]} if agent_slug == CONSULTATION_SLUG else {"kb_ids": list(kb_ids)}),
        "sources": sources,
    }


async def validate_family_kb_checkpoint(session, context, binding, tool_message) -> None:
    """模型重放前核对 ToolMessage 来自同线程真实审计及当前分片。"""
    operation_id = getattr(tool_message, "tool_call_id", None)
    if not isinstance(operation_id, str) or getattr(tool_message, "status", None) == "error":
        raise HealthVisionError("source_invalidated", "家庭科普历史来源无法核对", 410)
    rows = (
        await session.execute(
            select(Message, AgentRun)
            .join(AgentRun, AgentRun.id == Message.run_id)
            .where(
                Message.operation_id == operation_id,
                Message.message_type == TOOL_AUDIT_MESSAGE_TYPE,
                Message.role == "tool",
                Message.conversation_id == binding.conversation_id,
                AgentRun.conversation_id == binding.conversation_id,
                AgentRun.conversation_thread_id == context.thread_id,
                AgentRun.uid == context.uid,
                AgentRun.agent_slug.in_(KNOWLEDGE_HEALTH_AGENTS),
            )
        )
    ).all()
    if len(rows) != 1:
        raise HealthVisionError("source_invalidated", "家庭科普历史来源无法核对", 410)
    audit, source_run = rows[0]
    conversation = await session.get(Conversation, binding.conversation_id)
    if (
        conversation is None
        or conversation.agent_id != source_run.agent_slug
        or conversation.uid != context.uid
        or conversation.thread_id != context.thread_id
        or audit.execution_status != "completed"
        or (audit.extra_metadata or {}).get("tool_name") != TOOL_NAME
        or audit.request_id != source_run.request_id
        or audit.content != getattr(tool_message, "content", None)
    ):
        raise HealthVisionError("source_invalidated", "家庭科普历史来源无法核对", 410)
    try:
        payload = json.loads(audit.content)
    except (TypeError, ValueError):
        raise HealthVisionError("source_invalidated", "家庭科普历史来源无法解析", 410) from None
    await _validate_payload(session, payload, agent_slug=source_run.agent_slug)


async def validate_family_kb_audit(session, audit) -> bool:
    """核对审计归属；仅已完成输出可在重验当前来源后公开。"""
    metadata = audit.extra_metadata if isinstance(audit.extra_metadata, dict) else {}
    if (
        audit.message_type != TOOL_AUDIT_MESSAGE_TYPE
        or audit.role != "tool"
        or audit.execution_status not in {"running", "failed", "completed", "interrupted", "abandoned"}
        or metadata.get("tool_name") != TOOL_NAME
        or not isinstance(audit.operation_id, str)
        or not audit.operation_id
        or metadata.get("tool_call_id") != audit.operation_id
    ):
        raise HealthVisionError("source_invalidated", "家庭科普工具审计无法核对", 410)
    run = await session.scalar(
        select(AgentRun)
        .join(Conversation, Conversation.id == AgentRun.conversation_id)
        .where(
            AgentRun.id == audit.run_id,
            AgentRun.conversation_id == audit.conversation_id,
            AgentRun.request_id == audit.request_id,
            AgentRun.agent_slug.in_(KNOWLEDGE_HEALTH_AGENTS),
            Conversation.agent_id == AgentRun.agent_slug,
            Conversation.uid == AgentRun.uid,
            Conversation.thread_id == AgentRun.conversation_thread_id,
        )
    )
    if run is None:
        raise HealthVisionError("source_invalidated", "家庭科普工具审计与运行不符", 410)
    if audit.execution_status != "completed":
        return False
    output = metadata.get("output")
    if isinstance(output, dict):
        if output.get("status") == "error":
            return False
        output = output.get("content")
    if output is None:
        raise HealthVisionError("source_invalidated", "家庭科普工具审计缺少输出", 410)
    output_content = output if isinstance(output, str) else json.dumps(output, ensure_ascii=False, default=str)
    if audit.content != output_content:
        raise HealthVisionError("source_invalidated", "家庭科普工具审计输出不一致", 410)
    try:
        payload = json.loads(audit.content)
    except (TypeError, ValueError):
        raise HealthVisionError("source_invalidated", "家庭科普工具审计无法解析", 410) from None
    try:
        await _validate_payload(session, payload, agent_slug=run.agent_slug)
    except HealthVisionError as error:
        if error.code == "knowledge_unavailable":
            raise HealthVisionError("source_invalidated", "家庭科普工具审计来源已不可用", 410) from error
        raise
    return True


async def validate_family_kb_publication(session, run, binding, content: str) -> None:
    """最终发布只接受本 Run 成功工具审计里的当前科普来源。"""
    await _validate_answer_sources(session, run, binding, content, lock_sources=True)


async def validate_family_kb_answer(session, run, binding, content: str) -> None:
    """公开已完成答复前重验所用资料仍属于当前固定库版本。"""
    await _validate_answer_sources(session, run, binding, content)


async def validate_family_kb_model_answer(context, content: str) -> None:
    """模型生成科普正文后，发布前先校验本 Run 的资料来源标记。"""
    async with pg_manager.get_async_session_context() as session:
        run, binding = await _authorized_run(session, context)
        await _validate_answer_sources(session, run, binding, content, require_tool_audit=True)


def configured_health_kb_ids(agent_slug: str) -> tuple[str, ...]:
    """配餐资料独立绑定，其他角色沿用既有科普范围。"""
    if agent_slug != PLANNER_SLUG:
        return configured_education_kb_ids(agent_slug)
    kb_id = os.getenv(RECIPE_KB_ID_ENV, "").strip()
    if not kb_id or "," in kb_id:
        raise HealthVisionError("knowledge_unavailable", "菜谱资料库尚未正确配置", 503)
    return (kb_id,)


def configured_family_kb_id() -> str:
    """配置缺失时拒绝检索，不按名称猜测或回退到其他知识库。"""
    kb_id = os.getenv(KB_ID_ENV, "").strip()
    if not kb_id:
        raise HealthVisionError("knowledge_unavailable", "家庭营养科普资料尚未配置", 503)
    return kb_id


def configured_education_kb_ids(agent_slug: str) -> tuple[str, ...]:
    """每角色最多五个固定 ID，空值或重复配置均拒绝，不扩大检索范围。"""
    if agent_slug == CONSULTATION_SLUG:
        return (configured_family_kb_id(),)
    env_name = INDICATOR_KB_ENVS.get(agent_slug)
    if env_name is None:
        raise HealthVisionError("not_found", "该角色没有专题科普知识库", 404)
    ids = tuple(value.strip() for value in os.getenv(env_name, "").split(","))
    if not 1 <= len(ids) <= 5 or any(not value for value in ids) or len(set(ids)) != len(ids):
        raise HealthVisionError("knowledge_unavailable", "专题科普知识库尚未正确配置", 503)
    return ids


async def _authorized_run(session, context):
    """工具本身重验当前 attempt、成员绑定及咨询用途。"""
    from yuxi.services.health_consultation_service import require_consultation

    run = await HealthConsultationRepository(session).require_attempt(context, lock=True)
    if run.agent_slug not in KNOWLEDGE_HEALTH_AGENTS:
        raise HealthVisionError("not_found", "科普工具仅用于成员咨询与指标助手", 404)
    snapshot = (run.input_payload or {}).get("health_processing")
    if not snapshot:
        raise HealthVisionError("policy_changed", "咨询运行缺少处理审批快照", 409)
    binding, _ = await require_consultation(
        session, context.uid, context.thread_id, context.model, expected=snapshot, lock=True
    )
    if binding.conversation_id != run.conversation_id or binding.actor_uid != context.uid:
        raise HealthVisionError("not_found", "家庭营养科普工具与当前成员咨询不符", 404)
    return run, binding


async def _require_fixed_kb(session, kb_id: str) -> KnowledgeBase:
    """固定 ID 只能指向当前存在的 Milvus 知识库。"""
    kb = await session.scalar(select(KnowledgeBase).where(KnowledgeBase.kb_id == kb_id))
    if kb is None or kb.kb_type != "milvus":
        raise HealthVisionError("knowledge_unavailable", "家庭营养科普资料暂不可用，请检查知识库绑定", 503)
    return kb


def _project_source(kb_id: str, file: KnowledgeFile, chunk: KnowledgeChunk, source_id: str) -> dict:
    """只给模型短正文和可核对的文件、分片版本。"""
    return {
        "source_id": source_id,
        "kb_id": kb_id,
        "file_id": file.file_id,
        "chunk_id": chunk.chunk_id,
        "filename": file.filename,
        "file_content_hash": file.content_hash,
        "file_updated_at": format_utc_datetime(file.updated_at),
        "chunk_hash": hashlib.sha256(chunk.content.encode()).hexdigest(),
        "content": chunk.content[:MAX_SOURCE_CHARS],
    }


async def _validate_payload(
    session, payload: dict, *, agent_slug: str = CONSULTATION_SLUG, lock_sources: bool = False
) -> list[dict]:
    """逐片段重读 PG 来源，拒绝审计正文篡改、改版与失效文件。"""
    try:
        kb_ids = configured_health_kb_ids(agent_slug)
        for kb_id in kb_ids:
            await _require_fixed_kb(session, kb_id)
    except HealthVisionError as error:
        if error.code == "knowledge_unavailable":
            raise HealthVisionError("source_invalidated", "科普来源绑定已不可用，请重新咨询", 410) from error
        raise
    scope_key = "kb_id" if agent_slug == CONSULTATION_SLUG else "kb_ids"
    scope_value = kb_ids[0] if agent_slug == CONSULTATION_SLUG else list(kb_ids)
    if (
        not isinstance(payload, dict)
        or set(payload) != {"status", "scope", "query", scope_key, "sources"}
        or payload[scope_key] != scope_value
        or payload["scope"] != ("recipe_reference" if agent_slug == PLANNER_SLUG else "general_education")
        or not isinstance(payload["query"], str)
        or not 1 <= len(payload["query"].strip()) <= 120
        or not isinstance(payload["sources"], list)
        or len(payload["sources"]) > MAX_SOURCES
        or payload["status"] != ("ok" if payload["sources"] else "insufficient_material")
    ):
        raise HealthVisionError("source_invalidated", "家庭科普来源格式或范围已失效", 410)

    seen_ids = set()
    for source in payload["sources"]:
        if not isinstance(source, dict) or set(source) != SOURCE_KEYS:
            raise HealthVisionError("source_invalidated", "家庭科普来源格式已失效", 410)
        source_id = source["source_id"]
        try:
            if str(UUID(source_id)) != source_id or source_id in seen_ids:
                raise ValueError
        except (TypeError, ValueError, AttributeError):
            raise HealthVisionError("source_invalidated", "家庭科普来源标识无效", 410) from None
        seen_ids.add(source_id)
        kb_id = source["kb_id"]
        if kb_id not in kb_ids or not all(isinstance(source[key], str) for key in ("file_id", "chunk_id")):
            raise HealthVisionError("source_invalidated", "家庭科普来源不属于固定知识库", 410)
        file_query = select(KnowledgeFile).where(
            KnowledgeFile.file_id == source["file_id"], KnowledgeFile.kb_id == kb_id
        )
        chunk_query = select(KnowledgeChunk).where(
            KnowledgeChunk.chunk_id == source["chunk_id"],
            KnowledgeChunk.file_id == source["file_id"],
            KnowledgeChunk.kb_id == kb_id,
        )
        if lock_sources:
            file_query = file_query.with_for_update(read=True).execution_options(populate_existing=True)
            chunk_query = chunk_query.with_for_update(read=True).execution_options(populate_existing=True)
        file = await session.scalar(file_query)
        chunk = await session.scalar(chunk_query)
        if (
            file is None
            or chunk is None
            or file.status != FileStatus.INDEXED
            or not file.filename.strip()
            or not chunk.content.strip()
        ):
            raise HealthVisionError("source_invalidated", "家庭科普资料已删除或重新解析", 410)
        if source != _project_source(kb_id, file, chunk, source_id):
            raise HealthVisionError("source_invalidated", "家庭科普资料版本已变化", 410)
    return payload["sources"]


async def _validate_answer_sources(
    session,
    run,
    binding,
    content: str,
    *,
    require_tool_audit: bool = False,
    lock_sources: bool = False,
) -> None:
    """按同 Run 持久工具回执校验独立资料标识和当前来源。"""
    if run.agent_slug not in KNOWLEDGE_HEALTH_AGENTS:
        if isinstance(content, str) and "[资料:" in content:
            raise HealthVisionError("citation_invalid", "该角色不能引用家庭营养知识库", 409)
        return
    if not isinstance(content, str):
        raise HealthVisionError("answer_invalid", "营养咨询答复必须为文本", 409)
    env_name = (
        RECIPE_KB_ID_ENV
        if run.agent_slug == PLANNER_SLUG
        else KB_ID_ENV
        if run.agent_slug == CONSULTATION_SLUG
        else INDICATOR_KB_ENVS[run.agent_slug]
    )
    if (
        run.agent_slug != PLANNER_SLUG
        and not require_tool_audit
        and not os.getenv(env_name, "").strip()
        and "[资料:" not in content
    ):
        return
    marker_ids = SOURCE_MARKER.findall(content)
    if content.count("[资料:") != len(marker_ids):
        raise HealthVisionError("citation_invalid", "答复包含无法校验的家庭资料标识", 409)
    if binding.conversation_id != run.conversation_id or binding.actor_uid != run.uid:
        raise HealthVisionError("citation_invalid", "家庭资料引用与当前咨询线程不符", 409)
    audits = await ToolMessageAuditRepository(session).list_for_run(run.id)
    sources_by_id = {}
    retrieved = False
    saw_audit = False
    for audit in audits:
        if (audit.extra_metadata or {}).get("tool_name") != TOOL_NAME:
            continue
        saw_audit = True
        if (
            audit.message_type != TOOL_AUDIT_MESSAGE_TYPE
            or audit.role != "tool"
            or audit.execution_status != "completed"
            or audit.conversation_id != run.conversation_id
            or audit.request_id != run.request_id
        ):
            raise HealthVisionError("source_invalidated", "家庭科普工具回执无法核对", 410)
        try:
            payload = json.loads(audit.content)
        except (TypeError, ValueError):
            raise HealthVisionError("source_invalidated", "家庭科普工具回执无法解析", 410) from None
        sources = await _validate_payload(session, payload, agent_slug=run.agent_slug, lock_sources=lock_sources)
        retrieved = retrieved or bool(sources)
        for source in sources:
            if source["source_id"] in sources_by_id:
                raise HealthVisionError("source_invalidated", "家庭科普来源标识重复", 410)
            sources_by_id[source["source_id"]] = source
    if require_tool_audit and not saw_audit:
        raise HealthVisionError("source_invalidated", "家庭科普工具回执缺失", 410)
    if run.agent_slug == PLANNER_SLUG:
        # 配餐只发布程序回执；文档来源保留在工具审计，不伪装成已批准菜谱。
        if marker_ids:
            raise HealthVisionError("citation_invalid", "菜谱参考片段不能充当餐单批准依据", 409)
        return
    if retrieved and not marker_ids:
        raise HealthVisionError("citation_invalid", "答复缺少本轮家庭资料引用", 409)
    for source_id in marker_ids:
        source = sources_by_id.get(source_id)
        if source is None or source["filename"] not in content:
            raise HealthVisionError("citation_invalid", "答复引用了非本轮家庭资料或缺少文件名", 409)

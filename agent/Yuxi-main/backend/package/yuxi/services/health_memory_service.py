"""家庭营养师的成员自述读写、撤回与模型历史失效。"""

from contextlib import nullcontext
import hashlib
import json
from uuid import uuid4

from langchain_core.messages import HumanMessage, ToolMessage

from yuxi.repositories.health_consultation_repository import HealthConsultationRepository
from yuxi.repositories.health_memory_repository import HealthMemoryRepository
from yuxi.repositories.health_vision_repository import HealthVisionRepository
from yuxi.services.health_memory_types import validate_memory_statement
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_health import HealthMemoryFact, HealthMemoryRevision
from yuxi.utils.datetime_utils import format_utc_datetime, utc_now_naive


def memory_result(fact):
    """公开版本与自述标签，不暴露账号及原会话正文。"""
    return {
        "memory_id": fact.id,
        "fact_key": fact.fact_key,
        "content": fact.content,
        "kind": fact.kind,
        "version": fact.version,
        "status": fact.status,
        "source_type": "user_self_report",
        "professional_review": "not_reviewed",
        "formal_profile": False,
        "updated_at": format_utc_datetime(fact.updated_at),
    }


async def list_member_memory(uid, member_id):
    """当前授权账号只查看自己维护的成员记忆。"""
    async with pg_manager.get_async_session_context() as session:
        await HealthVisionRepository(session).authorize(member_id, uid, "ai_use")
        rows = await HealthMemoryRepository(session).list_active(uid, member_id)
        return {"memories": [memory_result(row) for row in rows[:100]], "truncated": len(rows) > 100}


async def memory_history(uid, fact_id):
    """回读当前版本及不可变来源供用户管理。"""
    async with pg_manager.get_async_session_context() as session:
        repo = HealthMemoryRepository(session)
        fact = await repo.get(uid, fact_id)
        if fact is None:
            raise HealthVisionError("not_found", "记忆不存在或无权访问", 404)
        await HealthVisionRepository(session).authorize(fact.member_id, uid, "ai_use")
        return {
            **memory_result(fact),
            "revisions": [
                {
                    "version": row.version,
                    "content": row.content,
                    "kind": row.kind,
                    "status": row.status,
                    "source_message_id": row.source_message_id,
                    "source_run_id": row.source_run_id,
                    "created_at": format_utc_datetime(row.created_at),
                }
                for row in await repo.revisions(fact.id)
            ],
        }


async def change_member_memory(uid, fact_id, data, *, revoke=False):
    """用户显式编辑或撤回；重复请求返回原收据，不隐式恢复旧事实。"""
    async with pg_manager.get_async_session_context() as session:
        repo = HealthMemoryRepository(session)
        fact = await repo.get(uid, fact_id)
        if fact is None:
            raise HealthVisionError("not_found", "记忆不存在或无权访问", 404)
        await HealthVisionRepository(session).authorize(fact.member_id, uid, "profile_edit", lock=True)
        await HealthVisionRepository(session).authorize(fact.member_id, uid, "ai_use")
        await session.refresh(fact)
        source_hash = hashlib.sha256(f"manage:{fact.id}".encode()).hexdigest()
        request_id = str(data.client_request_id)
        previous = await repo.receipt(uid, request_id, source_hash)
        content, kind = (fact.content, fact.kind) if revoke else (data.content, data.kind)
        status = "revoked" if revoke else "active"
        if previous:
            if (
                previous.version != data.version + 1
                or previous.status != status
                or (not revoke and (previous.content != content or previous.kind != kind))
            ):
                raise HealthVisionError("request_conflict", "同一请求不能改变记忆操作", 409)
            return memory_result(fact)
        if fact.version != data.version or fact.status != "active":
            raise HealthVisionError("version_conflict", "记忆版本已变化，请刷新后操作", 409)
        fact.version += 1
        fact.content, fact.kind, fact.status = content, kind, status
        fact.updated_at = utc_now_naive()
        session.add(
            HealthMemoryRevision(
                id=str(uuid4()),
                fact_id=fact.id,
                actor_uid=uid,
                version=fact.version,
                request_id=request_id,
                source_hash=source_hash,
                content=content,
                kind=kind,
                status=status,
            )
        )
        await session.flush()
        return memory_result(fact)


async def member_memory_for_run(context, statement=None):
    """有效 worker 与用途授权后读取或持久化本轮明确成员自述。"""
    from yuxi.services.health_consultation_service import require_consultation

    async with pg_manager.get_async_session_context() as session:
        run = await HealthConsultationRepository(session).require_attempt(context, lock=True)
        snapshot = (run.input_payload or {}).get("health_processing")
        if not snapshot:
            raise HealthVisionError("policy_changed", "咨询缺少处理审批快照", 409)
        binding, _ = await require_consultation(
            session, context.uid, context.thread_id, context.model, expected=snapshot, lock=True
        )
        repo = HealthMemoryRepository(session)
        if statement is None:
            rows = await repo.list_active(context.uid, binding.member_id)
            await repo.record_uses(run, [(row.id, row.version) for row in rows[:100]])
            return {"memories": [memory_result(row) for row in rows[:100]], "truncated": len(rows) > 100}
        member = await HealthVisionRepository(session).authorize(
            binding.member_id, context.uid, "profile_edit", lock=True
        )
        source = await repo.source_message(run)
        if source is None:
            raise HealthVisionError("memory_source_invalid", "当前用户消息无法核对", 409)
        validate_memory_statement(member, context.uid, statement["subject"], statement["quote"], source.content)
        source_hash = hashlib.sha256(statement["quote"].encode()).hexdigest()
        receipt = await repo.receipt(context.uid, context.request_id, source_hash)
        if receipt:
            fact = await repo.get(context.uid, receipt.fact_id)
            if fact.fact_key != statement["fact_key"] or receipt.kind != statement["kind"]:
                raise HealthVisionError("request_conflict", "同一原文不能重放为不同记忆", 409)
            return {**memory_result(fact), "written_version": receipt.version, "replayed": True}
        fact = await repo.slot(context.uid, binding.member_id, statement["fact_key"])
        if fact is None:
            fact = HealthMemoryFact(
                id=str(uuid4()),
                actor_uid=context.uid,
                member_id=binding.member_id,
                fact_key=statement["fact_key"],
                version=1,
            )
            session.add(fact)
        else:
            fact.version += 1
        fact.content, fact.kind, fact.status = statement["quote"], statement["kind"], "active"
        fact.updated_at = utc_now_naive()
        await session.flush()
        session.add(
            HealthMemoryRevision(
                id=str(uuid4()),
                fact_id=fact.id,
                actor_uid=context.uid,
                version=fact.version,
                request_id=context.request_id,
                source_hash=source_hash,
                source_message_id=source.id,
                source_run_id=run.id,
                content=fact.content,
                kind=fact.kind,
                status=fact.status,
            )
        )
        await session.flush()
        await repo.supersede_run_use(run, fact)
        return {**memory_result(fact), "written_version": fact.version, "replayed": False}


async def filter_memory_history(context, messages, *, session=None, persist_uses=True):
    """失效记忆的历史轮次不再进入模型，当前轮次失效则明确终止。"""
    chunks, chunk = [], []
    for message in messages:
        if isinstance(message, HumanMessage) and chunk:
            chunks.append(chunk)
            chunk = []
        chunk.append(message)
    if chunk:
        chunks.append(chunk)
    async with nullcontext(session) if session is not None else pg_manager.get_async_session_context() as session:
        repo = HealthMemoryRepository(session)
        uses = await repo.history_uses(context.uid, context.thread_id)
        invalid_requests = {
            request for request, _, version, status, current in uses if status != "active" or version != current
        }
        references = []
        filtered = []
        binding = None
        for index, chunk in enumerate(chunks):
            requests = {
                message.additional_kwargs.get("health_request_id")
                for message in chunk
                if isinstance(message, HumanMessage)
            }
            invalid = bool(requests & invalid_requests)
            chunk_refs = [(fact, version) for request, fact, version, _, _ in uses if request in requests]
            for message_index, message in enumerate(chunk):
                if not isinstance(message, ToolMessage) or message.name not in {
                    "get_member_memories",
                    "remember_member_fact",
                }:
                    continue
                if message.status == "error":
                    raise HealthVisionError("memory_history_invalid", "历史记忆工具未形成可核对来源", 409)
                try:
                    payload = json.loads(message.content)
                    if message.name == "get_member_memories" and (
                        not isinstance(payload, dict)
                        or set(payload) != {"memories", "truncated"}
                        or not isinstance(payload["memories"], list)
                        or type(payload["truncated"]) is not bool
                    ):
                        raise ValueError("记忆读取投影无效")
                    tool_references = payload["memories"] if message.name == "get_member_memories" else [payload]
                    for ref_index, reference in enumerate(tool_references):
                        public_keys = {
                            "memory_id",
                            "fact_key",
                            "content",
                            "kind",
                            "version",
                            "status",
                            "source_type",
                            "professional_review",
                            "formal_profile",
                            "updated_at",
                        }
                        if not isinstance(reference, dict):
                            raise ValueError("记忆正文无效")
                        extra_keys = set(reference) - public_keys
                        if extra_keys == {"superseded_by_same_request"}:
                            if reference["superseded_by_same_request"] is not True:
                                raise ValueError("记忆替换标记无效")
                        elif message.name == "remember_member_fact" and extra_keys == {"written_version", "replayed"}:
                            if (
                                type(reference["written_version"]) is not int
                                or reference["written_version"] < 1
                                or type(reference["replayed"]) is not bool
                            ):
                                raise ValueError("记忆写入回执无效")
                        elif extra_keys or message.name == "remember_member_fact":
                            raise ValueError("记忆包含未核对正文")
                        fact = await repo.get(context.uid, reference["memory_id"])
                        if fact is not None and fact.status == "active":
                            if binding is None:
                                binding = await HealthConsultationRepository(session).authorize(
                                    context.uid, context.thread_id
                                )
                            if fact.member_id != binding.member_id:
                                raise HealthVisionError("memory_history_invalid", "历史记忆不属于当前成员", 409)
                        if fact is not None and fact.status == "active" and fact.version != reference["version"]:
                            own = next(iter(requests - {None}), None)
                            if own and await repo.own_revision(context.uid, fact.id, fact.version, own):
                                reference = {**memory_result(fact), "superseded_by_same_request": True}
                                tool_references[ref_index] = reference
                                rewritten = (
                                    {**payload, "memories": tool_references}
                                    if message.name == "get_member_memories"
                                    else reference
                                )
                                chunk[message_index] = message.model_copy(
                                    update={"content": json.dumps(rewritten, ensure_ascii=False)}
                                )
                        invalid = (
                            invalid or fact is None or fact.status != "active" or fact.version != reference["version"]
                        )
                        if fact is not None and fact.status == "active" and fact.version == reference["version"]:
                            expected = memory_result(fact)
                            if "written_version" in reference:
                                if reference["written_version"] > fact.version:
                                    raise ValueError("记忆写入版本无效")
                                expected.update(
                                    written_version=reference["written_version"], replayed=reference["replayed"]
                                )
                            elif "superseded_by_same_request" in reference:
                                expected["superseded_by_same_request"] = True
                            if json.dumps(reference, sort_keys=True) != json.dumps(expected, sort_keys=True):
                                raise HealthVisionError("memory_history_invalid", "历史记忆正文或来源无法核对", 409)
                        chunk_refs.append((reference["memory_id"], reference["version"]))
                except (ValueError, TypeError, KeyError):
                    raise HealthVisionError("memory_history_invalid", "历史记忆无法核对", 409) from None
            if invalid and index == len(chunks) - 1:
                raise HealthVisionError("memory_changed", "本轮记忆已变化，请重新提交问题", 409)
            if not invalid:
                filtered.extend(chunk)
                references.extend(chunk_refs)
        if references and persist_uses:
            from yuxi.services.health_consultation_service import require_consultation

            run = await HealthConsultationRepository(session).require_attempt(context, lock=True)
            await require_consultation(
                session,
                context.uid,
                context.thread_id,
                context.model,
                expected=run.input_payload["health_processing"],
                lock=True,
            )
            # 获取成员锁之后再次核对，避免校验与提交之间发生撤回。
            for fact_id, version in set(references):
                fact = await repo.get(context.uid, fact_id)
                if fact is None or fact.status != "active" or fact.version != version:
                    raise HealthVisionError("memory_changed", "本轮记忆已变化，请重新提交问题", 409)
            await repo.record_uses(run, references)
        return filtered

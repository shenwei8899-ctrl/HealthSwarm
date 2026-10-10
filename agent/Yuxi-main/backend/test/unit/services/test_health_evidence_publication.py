"""最终事务引用、缺引用及 fresh SHARE 锁的独立 oracle。"""

import hashlib
import inspect
import os
import textwrap
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.dialects.postgresql import dialect

from yuxi.repositories.health_evidence_repository import HealthEvidenceRepository
from yuxi.repositories import health_evidence_repository as repository
from yuxi.services import health_consultation_service as consultation
from yuxi.services import health_evidence_service as service
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.utils.datetime_utils import utc_now_naive

REFERENCE = "11111111-1111-1111-1111-111111111111"


@pytest.fixture(autouse=True)
def controlled_publication_mutation(monkeypatch):
    """显式启用时只修改测试进程函数副本，分别检验发布与fresh/SHARE协议。"""
    mode = os.getenv("HEALTH_EVIDENCE_MUTATION")
    if mode in {"publication_gate", "publication_lock"}:
        owner, attribute = service, "validate_evidence_publication"
        original = service.validate_evidence_publication
        old, new = (
            (
                "await HealthEvidenceRepository(session).validate_citations"
                "(ids, binding, run.uid, run_id=run.id, lock=True)",
                "return None",
            )
            if mode == "publication_gate"
            else ("lock=True", "lock=False")
        )
        expected = 1 if mode == "publication_gate" else 2
    elif mode in {"citation_fresh", "citation_share", "search_fresh", "search_share"}:
        owner = HealthEvidenceRepository
        attribute = "search" if mode.startswith("search_") else "validate_citations"
        original = getattr(owner, attribute)
        old, new = (
            (".execution_options(populate_existing=True)", ".execution_options()")
            if mode.endswith("fresh")
            else (".with_for_update(read=True)", ".execution_options()")
        )
        expected = 1
    else:
        return
    source = textwrap.dedent(inspect.getsource(original))
    assert source.count(old) == expected, "变异只允许明确且仍存在的当前Owner边界"

    async def mutated(*args, **kwargs):
        scope = dict(original.__globals__)
        exec(compile(source.replace(old, new), "<controlled_evidence_publication_mutation>", "exec"), scope)
        return await scope[original.__name__](*args, **kwargs)

    monkeypatch.setattr(owner, attribute, mutated)


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["missing_snapshot", "wrong_actor", "wrong_thread", "malformed", "missing_citation"])
async def test_final_publication_refuses_unproved_final_body(monkeypatch, case):
    run = SimpleNamespace(
        id="run",
        uid="actor",
        conversation_thread_id="thread",
        conversation_id=7,
        input_payload={"health_processing": {"processor": "synthetic"}},
    )
    binding = SimpleNamespace(conversation_id=7, actor_uid="actor", member_id="member")
    session = SimpleNamespace(scalar=AsyncMock(return_value="retrieved-citation"))
    content = f"合成科普[证据:{REFERENCE}]"
    if case == "missing_snapshot":
        run.input_payload = {}
    elif case == "wrong_actor":
        binding.actor_uid = "foreign"
    elif case == "wrong_thread":
        binding.conversation_id = 8
    elif case == "malformed":
        content = "[证据:forged]"
    else:
        content = "漏掉本次检索全部依据"
    require = AsyncMock(return_value=(binding, {}))
    monkeypatch.setattr(consultation, "require_consultation", require)
    validate = AsyncMock()
    monkeypatch.setattr(service.HealthEvidenceRepository, "validate_citations", validate)
    with pytest.raises(HealthVisionError):
        await service.validate_evidence_publication(session, run, content)
    validate.assert_not_awaited()


@pytest.mark.asyncio
async def test_final_publication_rechecks_only_adopted_same_run_with_lock(monkeypatch):
    run = SimpleNamespace(
        id="run",
        uid="actor",
        conversation_thread_id="thread",
        conversation_id=7,
        input_payload={"health_processing": {"processor": "synthetic"}},
    )
    binding = SimpleNamespace(conversation_id=7, actor_uid="actor", member_id="member")
    session = SimpleNamespace(scalar=AsyncMock(return_value="unused-citation"))
    require = AsyncMock(return_value=(binding, {}))
    monkeypatch.setattr(consultation, "require_consultation", require)
    validate = AsyncMock()
    monkeypatch.setattr(service.HealthEvidenceRepository, "validate_citations", validate)
    await service.validate_evidence_publication(session, run, f"合成科普[证据:{REFERENCE}][证据:{REFERENCE}]")
    require.assert_awaited_once_with(
        session, "actor", "thread", expected=run.input_payload["health_processing"], lock=True
    )
    validate.assert_awaited_once_with([REFERENCE], binding, "actor", run_id="run", lock=True)
    session.scalar.assert_not_awaited()


@pytest.mark.asyncio
async def test_no_knowledge_retrieval_allows_plain_consultation(monkeypatch):
    run = SimpleNamespace(
        id="run",
        uid="actor",
        conversation_thread_id="thread",
        conversation_id=7,
        input_payload={"health_processing": {"processor": "synthetic"}},
    )
    binding = SimpleNamespace(conversation_id=7, actor_uid="actor", member_id="member")
    session = SimpleNamespace(scalar=AsyncMock(return_value=None))
    monkeypatch.setattr(consultation, "require_consultation", AsyncMock(return_value=(binding, {})))
    await service.validate_evidence_publication(session, run, "请补充当前问题")


@pytest.mark.asyncio
async def test_publication_proof_uses_share_lock_fresh_instances_and_stable_source_order():
    content = "合成科普"
    citation = SimpleNamespace(id=REFERENCE, run_id="run", content_hash=hashlib.sha256(content.encode()).hexdigest())
    source = SimpleNamespace(
        id="source",
        title="合成科普",
        source_version="v1",
        source_ref="synthetic://source",
        reviewed_at=utc_now_naive(),
        content=content,
        content_hash=citation.content_hash,
        valid_until=utc_now_naive() + timedelta(days=1),
        revoked_at=None,
    )
    session = SimpleNamespace(execute=AsyncMock(return_value=[(citation, source)]))
    binding = SimpleNamespace(conversation_id=7, member_id="member")
    await HealthEvidenceRepository(session).validate_citations([REFERENCE], binding, "actor", run_id="run", lock=True)
    statement = session.execute.await_args.args[0]
    sql = str(statement.compile(dialect=dialect()))
    assert "FOR SHARE" in sql and "ORDER BY nutrition_evidence.id, nutrition_evidence_citation.id" in sql
    assert statement.get_execution_options().get("populate_existing") is True


@pytest.mark.asyncio
@pytest.mark.parametrize("code", ["source_invalidated", "citation_invalid"])
async def test_final_publication_propagates_current_source_or_same_run_proof_failure(monkeypatch, code):
    """发布不能吞掉当前权威来源拒绝并继续提交正文。"""
    run = SimpleNamespace(
        id="run",
        uid="actor",
        conversation_thread_id="thread",
        conversation_id=7,
        input_payload={"health_processing": {"processor": "synthetic"}},
    )
    binding = SimpleNamespace(conversation_id=7, actor_uid="actor", member_id="member")
    monkeypatch.setattr(consultation, "require_consultation", AsyncMock(return_value=(binding, {})))
    proof = AsyncMock(
        side_effect=HealthVisionError(code, "合成当前证据拒绝", 410 if code == "source_invalidated" else 409)
    )
    monkeypatch.setattr(HealthEvidenceRepository, "validate_citations", proof)
    with pytest.raises(HealthVisionError, match=code):
        await service.validate_evidence_publication(object(), run, f"候选正文[证据:{REFERENCE}]")
    proof.assert_awaited_once_with([REFERENCE], binding, "actor", run_id="run", lock=True)


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["revoked", "expired", "changed_content", "changed_receipt", "other_run"])
async def test_locked_citation_proof_rejects_current_invalid_source_or_other_run(case):
    """实际Repository拒绝撤回、过期、内容变化以及他Run引用。"""
    content = "当前合成知识"
    digest = hashlib.sha256(content.encode()).hexdigest()
    citation = SimpleNamespace(id=REFERENCE, run_id="run", content_hash=digest)
    source = SimpleNamespace(
        id="source",
        title="合成科普",
        source_version="v1",
        source_ref="synthetic://source",
        reviewed_at=utc_now_naive(),
        content=content,
        content_hash=digest,
        valid_until=utc_now_naive() + timedelta(days=1),
        revoked_at=None,
    )
    if case == "revoked":
        source.revoked_at = utc_now_naive()
    elif case == "expired":
        source.valid_until = utc_now_naive() - timedelta(seconds=1)
    elif case == "changed_content":
        source.content = "已变化的来源"
    elif case == "changed_receipt":
        citation.content_hash = "foreign-hash"
    else:
        citation.run_id = "other-run"
    session = SimpleNamespace(execute=AsyncMock(return_value=[(citation, source)]))
    binding = SimpleNamespace(conversation_id=7, member_id="member")
    with pytest.raises(HealthVisionError, match="citation_invalid" if case == "other_run" else "source_invalidated"):
        await HealthEvidenceRepository(session).validate_citations(
            [REFERENCE], binding, "actor", run_id="run", lock=True
        )
    statement = session.execute.await_args.args[0]
    compiled = statement.compile(dialect=dialect())
    assert {"conversation_id_1": 7, "member_id_1": "member", "actor_uid_1": "actor"}.items() <= compiled.params.items()
    assert "FOR SHARE" in str(compiled)
    assert statement.get_execution_options().get("populate_existing") is True


@pytest.mark.asyncio
async def test_index_hit_reloads_current_source_with_share_lock_before_projection(monkeypatch):
    """索引命中只定位候选，返回值仍须来自fresh且被锁定的PG来源。"""
    content = "合成知识原文"
    digest = hashlib.sha256(content.encode()).hexdigest()
    source = SimpleNamespace(
        id="source",
        title="合成科普",
        source_version="v1",
        content=content,
        content_hash=digest,
        valid_until=utc_now_naive() + timedelta(days=1),
        revoked_at=None,
    )
    session = SimpleNamespace(
        execute=AsyncMock(return_value=[("source", "v1", digest, "合成科普", content)]),
        scalars=AsyncMock(return_value=[source]),
    )
    index = AsyncMock(return_value=[SimpleNamespace(evidence_id="source", source_version="v1", content_hash=digest)])
    monkeypatch.setattr(repository, "search_evidence_index", index)
    assert await HealthEvidenceRepository(session).search("知识") == [source]
    statement = session.scalars.await_args.args[0]
    sql = str(statement.compile(dialect=dialect()))
    assert "FOR SHARE" in sql and "ORDER BY nutrition_evidence.id" in sql
    assert statement.get_execution_options().get("populate_existing") is True
    index.assert_awaited_once()

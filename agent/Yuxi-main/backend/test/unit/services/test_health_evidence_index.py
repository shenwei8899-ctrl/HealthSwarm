"""限定科普索引的独立固定词法 oracle、容量和取消负控。"""

import asyncio
import threading
from contextvars import ContextVar

import pytest
from numpy import zeros
from scipy.sparse import csr_matrix
from sklearn.feature_extraction.text import TfidfVectorizer

from test.support.health_evidence_evaluation import evaluate_evidence_retrieval
from yuxi.services import health_evidence_index as index
from yuxi.services.health_vision_types import HealthVisionError


def document(identity, content, title="", version="v1"):
    return index.EvidenceIndexDocument(identity, version, "a" * 64, title, content)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "documents,query,expected",
    [
        ([], "盐", []),
        ([document("a", "盐及饮水")], "!!!", []),
        ([document("a", "盐及饮水")], "钙", []),
        ([document("a", "盐及饮水")], "盐", ["a"]),
        ([document("a", "Protein fiber")], "PROTEIN FIBER", ["a"]),
        ([document("a", "Protein fiber")], "%", []),
        ([document("a", "合成营养知识")], "不存在的合成词", []),
        ([document("a", "膳食纤维示例。其他段落饮水。"), document("b", "只有膳食纤维")], "膳食纤维 饮水", ["a"]),
    ],
)
async def test_literal_terms_and_one_character_are_ranked(documents, query, expected):
    """词法项全部存在，无全文原查询也可命中；零值候选不得被丢弃。"""
    assert [hit.evidence_id for hit in await index.search_evidence_index(documents, query)] == expected


@pytest.mark.asyncio
async def test_ties_are_stable_top_five_and_hits_carry_no_body():
    docs = [document(str(number), "同样的盐合成片段", version="v3") for number in (7, 1, 6, 2, 5, 3, 4)]
    hits = await index.search_evidence_index(docs, "盐")
    assert [hit.evidence_id for hit in hits] == ["1", "2", "3", "4", "5"]
    assert vars(hits[0]) == {"evidence_id": "1", "source_version": "v3", "content_hash": "a" * 64}


@pytest.mark.asyncio
async def test_tfidf_ranks_relevant_terms_before_extra_text():
    docs = [document("a", "protein fiber"), document("b", "protein content other random examples fiber")]
    assert [hit.evidence_id for hit in await index.search_evidence_index(docs, "protein fiber")][0] == "a"


@pytest.mark.asyncio
async def test_literal_candidate_zero_vector_falls_back_to_stable_id(monkeypatch):
    class ZeroQueryVectorizer(TfidfVectorizer):
        def transform(self, raw_documents):
            return csr_matrix(zeros((len(raw_documents), len(self.vocabulary_))))

    monkeypatch.setattr("sklearn.feature_extraction.text.TfidfVectorizer", ZeroQueryVectorizer)
    docs = [document("b", "盐"), document("a", "盐")]
    assert [hit.evidence_id for hit in await index.search_evidence_index(docs, "盐")] == ["a", "b"]


@pytest.mark.asyncio
@pytest.mark.parametrize("capacity", ["sources", "document", "total", "features"])
async def test_capacity_fails_before_matrix_without_truncation(monkeypatch, capacity):
    docs = [document("a", "protein fiber")]
    query = "protein"
    if capacity == "sources":
        docs, query = [document(str(i), "盐") for i in range(1001)], "盐"
    elif capacity == "document":
        docs, query = [document("a", "盐" * 4201)], "盐"
    elif capacity == "total":
        monkeypatch.setattr(index, "MAX_EVIDENCE_INDEX_CHARACTERS", 3)
        docs, query = [document("a", "盐盐"), document("b", "盐盐")], "盐"
    else:
        monkeypatch.setattr(index, "MAX_EVIDENCE_INDEX_FEATURES", 2)
    monkeypatch.setattr(TfidfVectorizer, "fit_transform", lambda *_: pytest.fail("容量超界不得构造矩阵"))
    with pytest.raises(HealthVisionError) as failure:
        await index.search_evidence_index(docs, query)
    assert (failure.value.code, failure.value.status) == ("evidence_index_capacity_exceeded", 503)


@pytest.mark.asyncio
async def test_cancelled_native_build_holds_permit_and_queued_cancel_does_not_submit(monkeypatch):
    entered, release = threading.Event(), threading.Event()
    calls = []
    request_context = ContextVar("phase4_test_context", default=None)
    request_context.set("must-not-be-exported")

    def blocked_build(documents, terms, cancelled):
        assert request_context.get() is None
        calls.append("native")
        entered.set()
        assert release.wait(3)
        return []

    original = index._rank_documents
    monkeypatch.setattr(index, "_rank_documents", blocked_build)
    first = asyncio.create_task(index.search_evidence_index([document("a", "盐")], "盐"))
    try:
        async with asyncio.timeout(3):
            while not entered.is_set():
                await asyncio.sleep(0.005)
        first.cancel()
        with pytest.raises(asyncio.CancelledError):
            await first
        assert index._INDEX_BUILD_LOCK.locked()
        second = asyncio.create_task(index.search_evidence_index([document("b", "盐")], "盐"))
        await asyncio.sleep(0.03)
        assert calls == ["native"]
        second.cancel()
        with pytest.raises(asyncio.CancelledError):
            await second
        assert calls == ["native"] and index._INDEX_BUILD_LOCK.locked()
    finally:
        release.set()
        async with asyncio.timeout(3):
            while index._INDEX_BUILD_LOCK.locked():
                await asyncio.sleep(0.005)
    monkeypatch.setattr(index, "_rank_documents", original)
    assert [hit.evidence_id for hit in await index.search_evidence_index([document("a", "盐")], "盐")] == ["a"]


@pytest.mark.parametrize(
    "retrieved,gold,k,expected",
    [
        (["first", "second"], ["first", "second"], 2, {"recall@2": 1.0, "f1@2": 1.0}),
        (["first", "second"], ["first", "second"], 5, {"recall@5": 1.0, "f1@5": 4 / 7}),
        (["first"], ["first", "second"], 2, {"recall@2": 0.5, "f1@2": 0.5}),
        (["first", "first"], ["first", "second"], 2, {"recall@2": 0.5, "f1@2": 0.5}),
        (["first", "forged"], ["first", "second"], 2, {"recall@2": 0.5, "f1@2": 0.5}),
        ([], ["first", "second"], 2, {"recall@2": 0.0, "f1@2": 0.0}),
    ],
)
def test_actual_ids_use_existing_recall_f1_against_independent_gold(retrieved, gold, k, expected):
    """漏依据、重复和伪造 ID 不提升覆盖率；期望由固定手算值提供。"""
    result = evaluate_evidence_retrieval(retrieved, gold, k=k)
    assert result["status"] == "synthetic_evaluated" and result["metrics"] == pytest.approx(expected)


def test_no_gold_cannot_claim_professional_quality():
    assert evaluate_evidence_retrieval(["first"], [], k=5) == {"status": "not_evaluated", "metrics": {}}

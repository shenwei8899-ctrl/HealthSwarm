"""当前审核科普片段的有界本地词法索引，不保存来源或执行状态。"""

import asyncio
import re
import threading
from dataclasses import dataclass

from yuxi.services.health_vision_types import HealthVisionError

MAX_EVIDENCE_INDEX_SOURCES = 1000
MAX_EVIDENCE_INDEX_DOCUMENT_CHARACTERS = 4200
MAX_EVIDENCE_INDEX_CHARACTERS = 4_200_000
MAX_EVIDENCE_INDEX_FEATURES = 100_000
_INDEX_BUILD_LOCK = threading.Lock()


@dataclass(frozen=True)
class EvidenceIndexDocument:
    """PG 当前片段的不可变计算输入，不含成员或运行上下文。"""

    evidence_id: str
    source_version: str
    content_hash: str
    title: str
    content: str


@dataclass(frozen=True)
class EvidenceIndexHit:
    """检索候选只携带待 PG 重验的来源，不携带正文。"""

    evidence_id: str
    source_version: str
    content_hash: str


async def search_evidence_index(documents: list[EvidenceIndexDocument], query: str) -> list[EvidenceIndexHit]:
    """后台计算当前语料；取消不释放仍在运行的纯计算构建锁。"""
    if (
        len(documents) > MAX_EVIDENCE_INDEX_SOURCES
        or any(
            len(document.title) + len(document.content) > MAX_EVIDENCE_INDEX_DOCUMENT_CHARACTERS
            for document in documents
        )
        or sum(len(document.title) + len(document.content) for document in documents) > MAX_EVIDENCE_INDEX_CHARACTERS
    ):
        raise HealthVisionError("evidence_index_capacity_exceeded", "审核科普语料超过本地检索容量", 503)
    terms = tuple(re.findall(r"\w+", query.casefold()))
    if not documents or not terms:
        return []
    # 先在 event loop 排队，不为取消的排队请求提交线程；锁在线程真正结束时释放。
    while not _INDEX_BUILD_LOCK.acquire(blocking=False):
        await asyncio.sleep(0.01)
    cancelled = threading.Event()
    # run_in_executor 不传播 Run Context；线程仅得到公开语料、词法查询与取消标志。
    try:
        future = asyncio.get_running_loop().run_in_executor(None, _rank_evidence, documents, terms, cancelled)
    except BaseException:
        _INDEX_BUILD_LOCK.release()
        raise
    future.add_done_callback(_consume_compute_error)
    try:
        return await asyncio.shield(future)
    except asyncio.CancelledError:
        cancelled.set()
        raise


def _rank_evidence(documents, terms, cancelled):
    """构建锁只在线程真正结束时释放，排队取消不进入矩阵计算。"""
    try:
        if cancelled.is_set():
            return []
        return _rank_documents(documents, terms, cancelled)
    finally:
        _INDEX_BUILD_LOCK.release()


def _rank_documents(documents, terms, cancelled):
    """纯 TF-IDF 计算不接触 Session、模型、文件或 Run 上下文。"""
    texts = [f"{document.title}\n{document.content}".casefold() for document in documents]
    candidates = [i for i, text in enumerate(texts) if all(term in text for term in terms)]
    if not candidates:
        return []

    from numpy import float32
    from sklearn.feature_extraction.text import TfidfVectorizer

    vectorizer = TfidfVectorizer(analyzer="char_wb", ngram_range=(1, 3), lowercase=False, dtype=float32)
    analyzer = vectorizer.build_analyzer()
    vocabulary = {}
    for text in texts:
        if cancelled.is_set():
            return []
        for feature in analyzer(text):
            if feature not in vocabulary:
                vocabulary[feature] = len(vocabulary)
                if len(vocabulary) > MAX_EVIDENCE_INDEX_FEATURES:
                    raise HealthVisionError(
                        "evidence_index_capacity_exceeded",
                        "审核科普词法特征超过本地检索容量",
                        503,
                    )
    if cancelled.is_set():
        return []
    vectorizer.set_params(vocabulary=vocabulary)
    matrix = vectorizer.fit_transform(texts)
    if cancelled.is_set():
        return []
    query_vector = vectorizer.transform([" ".join(terms)])
    scores = (matrix @ query_vector.T).toarray().ravel()
    selected = sorted(candidates, key=lambda i: (-float(scores[i]), documents[i].evidence_id))[:5]
    return [
        EvidenceIndexHit(
            documents[i].evidence_id,
            documents[i].source_version,
            documents[i].content_hash,
        )
        for i in selected
    ]


def _consume_compute_error(future):
    """取消的 awaiter 不再接收结果，但仍收敛纯线程的失败。"""
    if not future.cancelled():
        future.exception()

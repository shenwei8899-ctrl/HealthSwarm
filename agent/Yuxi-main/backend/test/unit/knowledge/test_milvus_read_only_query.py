"""家庭库只读 BM25 查询不得改写现有 Milvus 集合。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from yuxi.knowledge.implementations import milvus
from yuxi.knowledge.read_models import KnowledgeBaseConfig


def _collection(*, model="embedding-v1", bm25=True):
    fields = [
        SimpleNamespace(name="content", dtype=milvus.DataType.VARCHAR, params={"enable_analyzer": True}),
        SimpleNamespace(name=milvus.CONTENT_SPARSE_FIELD, dtype=milvus.DataType.SPARSE_FLOAT_VECTOR),
    ]
    functions = (
        [
            SimpleNamespace(
                type=milvus.FunctionType.BM25,
                input_field_names=["content"],
                output_field_names=[milvus.CONTENT_SPARSE_FIELD],
            )
        ]
        if bm25
        else []
    )
    hit = SimpleNamespace(
        distance=0.8,
        entity={"content": "合成营养资料", "chunk_id": "chunk-1", "file_id": "file-1", "chunk_index": 0},
    )
    return SimpleNamespace(
        description=f"Knowledge base collection using {model}",
        schema=SimpleNamespace(fields=fields, functions=functions),
        load=Mock(),
        search=Mock(return_value=[[hit]]),
    )


def _query_setup(monkeypatch, *, exists=True, collection=None):
    kb = object.__new__(milvus.MilvusKB)
    kb.collections = {"kb-1": _collection(model="stale-cache")}
    kb.connection_alias = "test-connection"
    has_collection = Mock(return_value=exists)
    constructor_calls = []

    class FakeCollection:
        def __new__(cls, *args, **kwargs):
            constructor_calls.append((args, kwargs))
            return collection

    drop_collection = Mock(side_effect=AssertionError("read-only query must not drop collection"))
    create_collection = Mock(side_effect=AssertionError("read-only query must not create collection"))
    normal_loader = AsyncMock(side_effect=AssertionError("read-only query must not use write-capable loader"))
    monkeypatch.setattr(milvus.utility, "has_collection", has_collection)
    monkeypatch.setattr(milvus.utility, "drop_collection", drop_collection)
    monkeypatch.setattr(milvus, "Collection", FakeCollection)
    monkeypatch.setattr(milvus.connections, "disconnect", Mock())
    monkeypatch.setattr(
        milvus.model_cache, "get_model_info", lambda _: SimpleNamespace(model_id="embedding-v1", model_type="embedding")
    )
    monkeypatch.setattr(kb, "_create_new_collection", create_collection)
    monkeypatch.setattr(kb, "_get_or_create_milvus_collection", normal_loader)
    monkeypatch.setattr(kb, "_get_embedding_function", Mock(side_effect=AssertionError("BM25 must not embed query")))
    monkeypatch.setattr(kb, "_hydrate_chunk_sources", AsyncMock(side_effect=lambda _kb_id, chunks: chunks))
    config = KnowledgeBaseConfig(
        kb_id="kb-1",
        kb_type="milvus",
        embedding_model_spec="provider:embedding-v1",
        query_params={"options": {"search_mode": "vector", "use_reranker": True, "use_graph_retrieval": True}},
    )
    return kb, config, has_collection, constructor_calls, drop_collection, create_collection, normal_loader


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("exists", "model", "bm25", "error"),
    [
        (False, "embedding-v1", True, "unavailable"),
        (True, "other-model", True, "does not match"),
        (True, "embedding-v10", True, "does not match"),
        (True, "embedding-v1", False, "no BM25"),
    ],
)
async def test_read_only_query_rejects_missing_or_incompatible_collection_without_mutation(
    monkeypatch, exists, model, bm25, error
):
    collection = _collection(model=model, bm25=bm25)
    kb, config, has_collection, constructor_calls, drop, create, normal_loader = _query_setup(
        monkeypatch, exists=exists, collection=collection
    )

    with pytest.raises(ValueError, match=error):
        await kb.aquery(
            "营养主题",
            "kb-1",
            config=config,
            agent_call=True,
            read_only=True,
            search_mode="keyword",
            use_reranker=False,
            use_graph_retrieval=False,
        )

    has_collection.assert_called_once_with("kb-1", using="test-connection")
    assert len(constructor_calls) == int(exists)
    collection.load.assert_not_called()
    drop.assert_not_called()
    create.assert_not_called()
    normal_loader.assert_not_awaited()


@pytest.mark.asyncio
async def test_read_only_keyword_query_uses_existing_bm25_collection(monkeypatch):
    collection = _collection()
    kb, config, has_collection, constructor_calls, drop, create, normal_loader = _query_setup(
        monkeypatch, collection=collection
    )

    result = await kb.aquery(
        "营养主题",
        "kb-1",
        config=config,
        agent_call=True,
        read_only=True,
        search_mode="keyword",
        use_reranker=False,
        use_graph_retrieval=False,
        final_top_k=4,
    )

    assert result[0]["content"] == "合成营养资料"
    assert result[0]["metadata"]["chunk_id"] == "chunk-1"
    has_collection.assert_called_once_with("kb-1", using="test-connection")
    assert constructor_calls == [((), {"name": "kb-1", "using": "test-connection"})]
    collection.load.assert_called_once_with()
    assert collection.search.call_args.kwargs["anns_field"] == milvus.CONTENT_SPARSE_FIELD
    assert collection.search.call_args.kwargs["param"]["metric_type"] == "BM25"
    drop.assert_not_called()
    create.assert_not_called()
    normal_loader.assert_not_awaited()


@pytest.mark.asyncio
async def test_read_only_keyword_query_reports_all_orphaned_hits(monkeypatch):
    """Milvus 有命中但 PG 来源全失效时，不能伪装成真正零命中。"""
    collection = _collection()
    kb, config, *_ = _query_setup(monkeypatch, collection=collection)
    monkeypatch.setattr(kb, "_hydrate_chunk_sources", AsyncMock(return_value=[]))

    with pytest.raises(milvus.OrphanedMilvusHitsError, match="all PostgreSQL sources are missing"):
        await kb.aquery(
            "营养主题",
            "kb-1",
            config=config,
            agent_call=True,
            read_only=True,
            search_mode="keyword",
            use_reranker=False,
            use_graph_retrieval=False,
        )

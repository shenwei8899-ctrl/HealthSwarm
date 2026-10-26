"""原文地址绑定具体知识文件和实际读取行号。"""
from unittest.mock import AsyncMock

import pytest

from yuxi.knowledge.base import KnowledgeBase
from yuxi.knowledge.manager import KnowledgeBaseManager


def test_search_result_includes_local_document_address_without_exposing_storage_paths():
    result = KnowledgeBase.build_search_output(
        "kb_source",
        [{"content": "ingredients", "metadata": {"file_id": "file_recipe", "path": "/private/source.md"}}],
    )["results"][0]
    assert result["metadata"]["citation_url"] == "/knowledge/source/kb_source/file_recipe"
    assert "path" not in result["metadata"]


def test_search_result_without_a_document_id_does_not_invent_a_citation():
    result = KnowledgeBase.build_search_output("kb_source", [{"content": "excerpt"}])["results"][0]
    assert "citation_url" not in result["metadata"]


@pytest.mark.asyncio
async def test_document_address_preserves_the_actual_opened_window(monkeypatch):
    manager = object.__new__(KnowledgeBaseManager)
    monkeypatch.setattr(manager, "_require_kb_supports_documents", AsyncMock())
    monkeypatch.setattr(manager, "open_file_content", AsyncMock(return_value={
        "start_line": 21, "end_line": 28, "total_lines": 57, "offset": 20, "window_size": 8,
        "has_more_before": True, "has_more_after": True, "next_offset": 28, "content": "21\tingredients",
    }))
    result = await manager.open_document("kb_source", "file_recipe", offset=20, limit=8)
    assert result["citation_url"] == "/knowledge/source/kb_source/file_recipe?line=21"
    assert result["content"] == "21\tingredients"

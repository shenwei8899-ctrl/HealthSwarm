import asyncio
import re
from types import SimpleNamespace

import pytest

from yuxi.knowledge.utils import kb_utils
from yuxi.knowledge.utils.kb_utils import build_kb_image_proxy_url, prepare_item_metadata


def test_build_kb_image_proxy_url_uses_private_bucket_proxy_path():
    url = build_kb_image_proxy_url("db_1/kb-images/1710000000000_diagram.png")

    assert url == "/api/knowledge/databases/db_1/images/kb-images/1710000000000_diagram.png"


def test_build_kb_image_proxy_url_encodes_special_chars_but_keeps_slashes():
    url = build_kb_image_proxy_url("db_1/kb-images/1710000000000_user 1.png")

    assert url == "/api/knowledge/databases/db_1/images/kb-images/1710000000000_user%201.png"


@pytest.mark.parametrize("object_name", ["db_1/images/a.png", "/kb-images/a.png", "db_1"])
def test_build_kb_image_proxy_url_rejects_invalid_object_name(object_name):
    with pytest.raises(ValueError, match="知识库图片对象名"):
        build_kb_image_proxy_url(object_name)


async def test_prepare_item_metadata_preserves_uploaded_file_size():
    item = "minio://knowledgebases/db/upload/demo.txt"
    params = {
        "content_hashes": {item: "hash"},
        "file_sizes": {item: 1234},
    }

    metadata = await prepare_item_metadata(item, "file", "db", params=params)

    assert metadata["size"] == 1234
    assert "file_sizes" not in (metadata.get("processing_params") or {})


async def test_prepare_item_metadata_uses_source_path_as_display_filename():
    item = "minio://knowledgebases/db/upload/intro_1710000000000.md"
    params = {
        "content_hashes": {item: "hash"},
        "source_path": "guides/setup/Intro.MD",
    }

    metadata = await prepare_item_metadata(item, "file", "db", params=params)

    assert metadata["filename"] == "guides/setup/Intro.MD"
    assert metadata["file_type"] == "md"
    assert metadata["path"] == item


async def test_prepare_item_metadata_preserves_preprocessed_file_size():
    item = "minio://knowledgebases/db/upload/page.html"
    params = {
        "_preprocessed_map": {
            item: {
                "path": item,
                "content_hash": "hash",
                "filename": "https://example.com",
                "file_size": 5678,
            }
        }
    }

    metadata = await prepare_item_metadata(item, "file", "db", params=params)

    assert metadata["size"] == 5678
    assert "_preprocessed_map" not in (metadata.get("processing_params") or {})


async def test_prepare_item_metadata_rejects_direct_url_content_type():
    with pytest.raises(ValueError, match="Unsupported content_type"):
        await prepare_item_metadata("https://example.com", "url", "db")


@pytest.mark.parametrize("preprocessed", [False, True])
async def test_same_item_concurrent_creation_uses_long_unique_ids_with_frozen_short_hash(monkeypatch, preprocessed):
    """冻结旧摘要与时间，两个入口的同名并发仍分配不同长 ID。"""
    monkeypatch.setattr(kb_utils, "time", SimpleNamespace(time=lambda: 1710000000.0), raising=False)
    monkeypatch.setattr(kb_utils, "hashstr", lambda *args, **kwargs: "aaaaaa", raising=False)
    item = "minio://knowledgebases/db/upload/same.md"
    params = {"content_hashes": {item: "a" * 64}, "file_sizes": {item: 12}}
    if preprocessed:
        params["_preprocessed_map"] = {item: {"path": item, "content_hash": "a" * 64, "filename": "same.md"}}

    records = await asyncio.gather(*(prepare_item_metadata(item, "file", "db", params=params) for _ in range(32)))

    assert len({record["file_id"] for record in records}) == 32
    assert all(re.fullmatch(r"file_[0-9a-f]{32}", record["file_id"]) for record in records)

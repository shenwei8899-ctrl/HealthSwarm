"""连接已导入菜谱目录与现有参考餐单来源回执。"""

import asyncio
import hashlib
import os

from yuxi.repositories.reference_recipe_catalog_repository import catalog_recipe_row, catalog_recipe_rows
from yuxi.services.health_nutrition_service import input_fingerprint
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.services.reference_recipe_matching import parse_reference_recipe

CATALOG_SOURCE = "recipe_catalog"
CATALOG_PREFIX = "pg:"
CATALOG_IMAGE_LIMIT = 10 * 1024 * 1024
CATALOG_IMAGE_SUFFIX = {"image/jpeg": "jpg", "image/webp": "webp"}


def new_reference_uses_catalog():
    """只给新绑定启用目录，旧绑定继续走原知识库。"""
    source = os.getenv("HEALTH_REFERENCE_RECIPE_SOURCE", "knowledge").strip() or "knowledge"
    if source not in {"postgres", "knowledge"}:
        raise HealthVisionError("reference_catalog_unavailable", "参考菜谱来源配置无效", 503)
    return source == "postgres"


async def catalog_search_rows(session):
    """把两张表一致的可用菜谱转换为现有排行器的单文档输入。"""
    rows = await catalog_recipe_rows(session)
    if not rows:
        raise HealthVisionError("reference_catalog_unavailable", "菜谱数据库还没有导入菜谱", 503)

    def prepare():
        return [
            (doc["file_id"], doc["kb_id"], doc["filename"], doc["file_hash"], doc["chunk_id"], doc["content"])
            for row in rows
            if (doc := _catalog_document(row)) is not None
        ]

    return await asyncio.to_thread(prepare)


async def read_catalog_document(session, file_id, chunk_id):
    """用稳定 ID 重读目录，拒绝损坏、不一致或已移除的菜谱。"""
    if chunk_id != CATALOG_SOURCE:
        raise HealthVisionError("reference_source_unavailable", "数据库菜谱来源不可核对", 410)
    row = await catalog_recipe_row(session, file_id.removeprefix(CATALOG_PREFIX))
    if row is None or (document := _catalog_document(row)) is None:
        raise HealthVisionError("reference_source_unavailable", "数据库菜谱来源不可核对", 410)
    return document


async def freeze_catalog_cover(session, document):
    """冻结经哈希核对的书面菜谱参考图，存储键与用户及餐单无关。"""
    cover = document.get("catalog_cover")
    if not cover:
        return {}
    from yuxi.storage.minio import get_minio_client

    row = await catalog_recipe_row(session, document["recipe_id"], include_image=True)
    raw = bytes(row["image_bytes"] or b"") if row else b""
    mime = cover.get("mime", "image/jpeg")
    if (
        catalog_image_mime(raw) != mime
        or row["image_mime"] != mime
        or hashlib.sha256(raw).hexdigest() != cover["sha256"]
    ):
        raise HealthVisionError("reference_catalog_image_invalid", "菜谱参考图与数据库记录不一致", 410)
    key = f"reference-recipes/catalog/{cover['sha256']}.{CATALOG_IMAGE_SUFFIX[mime]}"
    await get_minio_client().aupload_file("public", key, raw, mime)
    return {
        "image_url": "/minio/public/" + key,
        "image_source": {
            "image_role": "ai_generated" if cover["label"] == "AI 生成示意图" else "reference",
            "label": cover["label"],
        },
    }


def catalog_image_mime(raw):
    """识别符合大小和容器头要求的 JPEG 或 WebP。"""
    if len(raw) > CATALOG_IMAGE_LIMIT:
        return None
    if raw.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if len(raw) >= 12 and raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        if int.from_bytes(raw[4:8], "little") + 8 == len(raw):
            return "image/webp"
    return None


def catalog_recipe_text(name, ingredients, steps):
    """验证结构化条目可经当前参考餐单解析器完整回读。"""
    if (
        not isinstance(name, str)
        or not 1 <= len(name) <= 120
        or not isinstance(ingredients, list)
        or not 1 <= len(ingredients) <= 30
        or not isinstance(steps, list)
        or not 1 <= len(steps) <= 20
        or any(not isinstance(line, str) or not line.strip() for line in [*ingredients, *steps])
    ):
        return None
    content = "\n".join(
        [f"# {name}", "## 食材", *(f"- {x}" for x in ingredients), "## 做法", *(f"- {x}" for x in steps)]
    )
    parsed = parse_reference_recipe(content)
    if (
        parsed is None
        or parsed.review_sections
        or parsed.name != name
        or parsed.ingredients != tuple(ingredients)
        or parsed.steps != tuple(steps)
    ):
        return None
    return content


def _catalog_document(row):
    """用同一份原始事实产生展示正文和稳定的变更指纹。"""
    recipe_id, name, ingredients, steps = (row[key] for key in ("id", "name", "ingredients", "steps"))
    if not isinstance(recipe_id, str) or not 1 <= len(recipe_id) <= 61 or ingredients != row["ingredient_lines"]:
        return None
    if not (content := catalog_recipe_text(name, ingredients, steps)):
        return None
    digest = (row["image_sha256"] or "").strip()
    cover = (
        {"sha256": digest, "label": (row["image_label"] or "菜谱参考图")[:80]}
        if row["image_mime"] in CATALOG_IMAGE_SUFFIX
        and len(digest) == 64
        and all(c in "0123456789abcdef" for c in digest)
        else None
    )
    if cover and row["image_mime"] == "image/webp":
        cover["mime"] = "image/webp"
    filename = f"{name}.md"
    return {
        "scope": "reference_recipe",
        "file_id": CATALOG_PREFIX + recipe_id,
        "chunk_id": CATALOG_SOURCE,
        "kb_id": CATALOG_SOURCE,
        "recipe_id": recipe_id,
        "filename": filename,
        "file_hash": input_fingerprint([recipe_id, content, cover]),
        "chunks_hash": input_fingerprint([(CATALOG_SOURCE, content)]),
        "content": content,
        "catalog_cover": cover,
    }

"""从核对后的清单导入参考菜谱及原图；不覆盖任何已有菜谱。"""

import argparse
import asyncio
import base64
import hashlib
import io
import json
import os
import re
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit

import asyncpg
from PIL import Image

from yuxi.services.reference_catalog_recipe import (
    CATALOG_IMAGE_LIMIT,
    catalog_image_mime,
    catalog_recipe_text,
)


def load_manifest(path):
    """在连接数据库前校验清单、原谱结构和图片实际格式。"""
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, list) or not data:
        raise ValueError("清单必须是非空数组")
    seen = set()
    for entry in data:
        rid = entry["id"]
        if (
            not isinstance(rid, str)
            or not re.fullmatch(r"[a-z0-9_-]{1,61}", rid)
            or rid != "kb-" + entry["source_file_id"]
            or rid in seen
            or not re.fullmatch(r"[a-f0-9]{64}", entry["source_hash"])
        ):
            raise ValueError("清单中有无效或重复的菜谱来源 ID")
        seen.add(rid)
        simplified = _simplify_recipe(entry)
        if not catalog_recipe_text(simplified["name"], simplified["ingredients"], simplified["steps"]):
            raise ValueError(f"{rid} 的菜名、食材或做法无法完整回读")
        url = urlsplit(entry["source_url"])
        if url.scheme not in {"http", "https"} or not url.hostname or url.username or url.password:
            raise ValueError(f"{rid} 的原文出处无效")
        if not entry["category"].strip() or not 1 <= len(entry["image_label"]) <= 80:
            raise ValueError(f"{rid} 的分类或图片说明为空或超出长度")
        if len(entry["image_b64"]) > 4 * ((CATALOG_IMAGE_LIMIT + 2) // 3):
            raise ValueError(f"{rid} 的图片超过大小限制")
        raw = base64.b64decode(entry.pop("image_b64"), validate=True)
        if catalog_image_mime(raw) != entry["image_mime"] or hashlib.sha256(raw).hexdigest() != entry["image_sha256"]:
            raise ValueError(f"{rid} 的图片类型或 SHA-256 不匹配")
        with Image.open(io.BytesIO(raw)) as img:
            expected = {"image/jpeg": "JPEG", "image/webp": "WEBP"}
            if img.format != expected[entry["image_mime"]] or img.width * img.height > 16_000_000:
                raise ValueError(f"{rid} 的图片格式或尺寸不符合要求")
            img.load()
        entry["image_bytes"] = raw
    return data


async def import_catalog(dsn, entries, *, apply=False):
    """用简体正文对账并写入，实际改版停止，已有同配方跳过。"""
    entries = [_simplify_recipe(entry) for entry in entries]
    conn = await asyncpg.connect(dsn)
    try:
        async with conn.transaction(readonly=not apply):
            if apply:
                # 与其他可能写这两张表的任务串行；目录读取仍可进行。
                await conn.execute(
                    "LOCK TABLE recipe_catalog.recipes, recipe_catalog.reference_recipe_ingredient "
                    "IN SHARE ROW EXCLUSIVE MODE"
                )
            rows = await conn.fetch("""
                SELECT r.id, r.name, r.category, r.ingredients::text AS ingredients, r.steps::text AS steps,
                       r.source_url, r.image_mime, r.image_label, r.image_sha256,
                       (SELECT array_agg(i.raw_text ORDER BY i.position)
                        FROM recipe_catalog.reference_recipe_ingredient i WHERE i.recipe_id=r.id) AS ingredient_rows,
                       (SELECT array_agg(i.position ORDER BY i.position)
                        FROM recipe_catalog.reference_recipe_ingredient i WHERE i.recipe_id=r.id) AS positions
                FROM recipe_catalog.recipes r
            """)
            existing = {}
            formulas = {}
            names = set()
            for row in rows:
                record = dict(row)
                for key in ("ingredients", "steps"):
                    record[key] = json.loads(record[key])
                simplified = _simplify_recipe(record)
                existing[record["id"]] = record, simplified
                names.add(simplified["name"])
                formulas.setdefault(_formula(simplified), record["id"])

            summary = {
                "inserted" if apply else "would_insert": 0,
                "unchanged": 0,
                "same_formula": 0,
                "same_name_distinct": 0,
                "ingredient_rows": 0,
            }
            for entry in entries:
                rid = entry["id"]
                if known := existing.get(rid):
                    old, simplified = known
                    fields = (
                        "name",
                        "category",
                        "ingredients",
                        "steps",
                        "source_url",
                        "image_mime",
                        "image_label",
                        "image_sha256",
                    )
                    if (
                        any(simplified[k] != entry[k] for k in fields)
                        or old["ingredient_rows"] != old["ingredients"]
                        or old["positions"] != list(range(len(old["ingredients"])))
                        or await conn.fetchval("SELECT image_bytes FROM recipe_catalog.recipes WHERE id=$1", rid)
                        != entry["image_bytes"]
                    ):
                        raise ValueError(f"{rid} 已存在且内容或图片不同，整批停止，未覆盖")
                    summary["unchanged"] += 1
                    continue
                formula = _formula(entry)
                if formula in formulas:
                    summary["same_formula"] += 1
                    continue
                if entry["name"] in names:
                    summary["same_name_distinct"] += 1
                if apply:
                    await _insert(conn, entry)
                summary["inserted" if apply else "would_insert"] += 1
                summary["ingredient_rows"] += len(entry["ingredients"])
                formulas[formula] = rid
                names.add(entry["name"])
            return summary
    finally:
        await conn.close()


def _simplify_recipe(entry):
    """只转换展示文本，保留配方结构、来源身份和图片。"""
    if any(not isinstance(entry[key], str) for key in ("name", "category", "image_label")) or any(
        not isinstance(entry[key], list) or any(not isinstance(line, str) for line in entry[key])
        for key in ("ingredients", "steps")
    ):
        raise ValueError(f"{entry['id']} 的菜谱展示字段格式无效")
    convert = _simplified_converter().convert
    return {
        **entry,
        "name": convert(entry["name"]),
        "category": convert(entry["category"]),
        "ingredients": [convert(line) for line in entry["ingredients"]],
        "steps": [convert(line) for line in entry["steps"]],
        "image_label": convert(entry["image_label"]),
    }


@lru_cache(maxsize=1)
def _simplified_converter():
    """导入脚本单独加载固定字典。"""
    try:
        from opencc import OpenCC
    except ImportError as error:
        raise ValueError("请使用 uv run --group recipe-import 启动菜谱导入脚本") from error
    return OpenCC("t2s.json")


def _formula(entry):
    """食材多重集合与制作步骤相同才自动跳过，避免按名称去重。"""
    return tuple(sorted(entry["ingredients"])), tuple(entry["steps"])


async def _insert(conn, entry):
    """同一事务保存菜谱与有序原文食材。"""
    await conn.execute(
        """
        INSERT INTO recipe_catalog.recipes
            (id, name, category, ingredients, steps, source_url, image_bytes, image_mime, image_label, image_sha256)
        VALUES ($1, $2, $3, $4::jsonb, $5::jsonb, $6, $7, $8, $9, $10)
    """,
        entry["id"],
        entry["name"],
        entry["category"],
        json.dumps(entry["ingredients"], ensure_ascii=False),
        json.dumps(entry["steps"], ensure_ascii=False),
        entry["source_url"],
        entry["image_bytes"],
        entry["image_mime"],
        entry["image_label"],
        entry["image_sha256"],
    )
    await conn.executemany(
        'INSERT INTO recipe_catalog.reference_recipe_ingredient (recipe_id,"position",raw_text) VALUES ($1,$2,$3)',
        [(entry["id"], pos, raw) for pos, raw in enumerate(entry["ingredients"])],
    )


def main():
    """默认只读预检；应用时显式指定目标和 --apply。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    dsn = os.getenv("REFERENCE_CATALOG_IMPORT_DSN")
    if not dsn:
        parser.error("请设置 REFERENCE_CATALOG_IMPORT_DSN 指向明确的目标库")
    try:
        entries = load_manifest(args.manifest)
        result = asyncio.run(import_catalog(dsn, entries, apply=args.apply))
    except asyncpg.PostgresError as error:
        parser.exit(1, f"菜谱导入失败，数据库事务未提交（SQLSTATE {error.sqlstate}）。\n")
    except (ValueError, KeyError, OSError) as error:
        parser.exit(1, f"菜谱导入失败：{error}\n")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()

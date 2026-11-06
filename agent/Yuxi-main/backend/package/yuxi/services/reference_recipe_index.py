"""用已读商品召回菜谱，完整原文与采购核对由打开和保存步骤拥有。"""

import re

from sqlalchemy import or_, select

from yuxi.services.health_family_kb_service import configured_health_kb_ids
from yuxi.services.health_nutrition_service import input_fingerprint
from yuxi.services.reference_recipe_matching import (
    parse_reference_recipe, product_food, reference_food_mentions, reference_ingredient_matches,
)
from yuxi.storage.postgres.models_knowledge import KnowledgeChunk, KnowledgeFile


async def purchasable_reference_recipes(session, products: list[dict], query: str, limit: int = 9) -> list[dict]:
    """相关菜谱允许有待核对项；原文读取与保存仍需独立验证。"""
    return rank_reference_recipes(await reference_recipe_rows(session), products, query, limit)


async def purchasable_reference_recipes_batch(session, products: list[dict], queries: list[str]) -> list[list[dict]]:
    """批量关键词共用菜谱正文和商品匹配，逐词独立排序。"""
    documents = prepare_reference_documents(await reference_recipe_rows(session))
    available = available_reference_foods(products)
    analyzed = {}
    return [rank_prepared_reference_recipes(documents, products, available, query, 3, analyzed) for query in queries]


async def reference_recipe_rows(session):
    """读取固定知识库中可用于参考餐单的真实菜谱分片。"""
    rows = (
        await session.execute(
            select(
                KnowledgeFile.file_id, KnowledgeFile.kb_id, KnowledgeFile.filename,
                KnowledgeFile.content_hash, KnowledgeChunk.chunk_id, KnowledgeChunk.content,
            )
            .join(KnowledgeChunk, KnowledgeChunk.file_id == KnowledgeFile.file_id)
            .where(
                KnowledgeFile.kb_id.in_(configured_health_kb_ids("health-meal-planner")),
                KnowledgeChunk.kb_id == KnowledgeFile.kb_id,
                KnowledgeFile.is_folder.is_(False), KnowledgeFile.status == "indexed",
                or_(
                    KnowledgeFile.filename.startswith("家常菜谱_", autoescape=True),
                    KnowledgeFile.filename.startswith("烹饪菜谱"),
                    KnowledgeFile.filename.startswith("USDA家庭菜谱"),
                ),
            )
            .order_by(KnowledgeFile.file_id, KnowledgeChunk.chunk_index, KnowledgeChunk.id)
        )
    ).all()
    return rows


def rank_reference_recipes(rows, products: list[dict], query: str, limit: int = 9) -> list[dict]:
    """先满足食材相关性，再优先可解析、采购覆盖较高的简单做法。"""
    return rank_prepared_reference_recipes(
        prepare_reference_documents(rows), products, available_reference_foods(products), query, limit, {}
    )


def prepare_reference_documents(rows):
    """同批查询只拼接一次原谱分片并提取查询无关的召回信息。"""
    documents = {}
    for file_id, kb_id, filename, file_hash, chunk_id, content in rows:
        document = documents.setdefault(file_id, {
            "source": {
                "file_id": file_id, "kb_id": kb_id, "filename": filename,
                "file_hash": file_hash, "chunk_id": chunk_id,
            },
            "chunks": [],
        })
        document["chunks"].append((chunk_id, content))
    prepared = []
    for document in documents.values():
        content = "\n".join(value for _, value in document["chunks"])
        title = re.sub(r"__[0-9a-f]+\.md$", "", document["source"]["filename"], flags=re.I)
        title = title.removesuffix(".md").replace("_", " ").casefold()
        prepared.append({
            **document, "content": content, "body": content.casefold(), "title": title,
            "title_foods": reference_food_mentions(title), "foods": reference_food_mentions(content),
        })
    return prepared


def available_reference_foods(products):
    """只把当前已读且有库存的商品作为召回加分项。"""
    available = {product_food(p.get("product_name", "")) for p in products
                 if p.get("sale_status", "available") == "available" and int(p.get("available_quantity", 0)) > 0}
    available.discard(None)
    return available


def rank_prepared_reference_recipes(documents, products, available, query, limit, analyzed):
    """每个关键词独立评分，复用本次调用已解析的候选原谱。"""
    terms = [term.casefold() for term in re.findall(r"[\w\u4e00-\u9fff]+", query) if len(term) > 1]
    query_foods = reference_food_mentions(query) - {"水", "盐", "糖"}
    methods = [pattern for word, pattern in (
        ("煮", r"\b(?:boil\w*|poach\w*)\b|煮"), ("蒸", r"\bsteam\w*\b|蒸"),
        ("烤", r"\b(?:bak\w*|roast\w*)\b|烤"), ("粥", r"\bporridge\b|粥"),
    ) if word in query]
    candidates = []
    for document in documents:
        title, content = document["title"], document["content"]
        foods = document["foods"]
        title_hits = sum(term in title for term in terms)
        body_hits = sum(term in document["body"] for term in terms)
        title_food_hits = len(document["title_foods"] & query_foods)
        query_hits = len(foods & query_foods)
        stock_hits = len(foods & available)
        if not (title_hits or body_hits or title_food_hits or query_hits):
            continue
        file_id = document["source"]["file_id"]
        if file_id not in analyzed:
            parsed = parse_reference_recipe(content)
            analyzed[file_id] = (
                parsed,
                reference_ingredient_matches(parsed.ingredients, products) if parsed else [],
                input_fingerprint(document["chunks"]),
            )
        parsed, matches, chunks_hash = analyzed[file_id]
        gaps = sum(item["status"] in {"needs_confirmation", "missing_product"} for item in matches)
        usable = parsed is not None and not parsed.review_sections
        covered = sum(item["status"] == "matched" for item in matches)
        required = sum(item["status"] not in {"cooking_water", "optional_not_selected"} for item in matches)
        exact_name = int(len(query.strip()) >= 5 and query.casefold().strip() in title)
        relevant_title = title_food_hits if query_foods else title_hits
        method_hits = sum(bool(re.search(pattern, title, re.I)) for pattern in methods)
        score = (exact_name, bool(relevant_title), usable, method_hits, covered / max(required, 1),
                 -gaps, relevant_title, query_hits, body_hits, stock_hits)
        candidates.append((score, {
            **document["source"], "chunks_hash": chunks_hash,
            "name": parsed.name if parsed else document["source"]["filename"],
            "excerpt": content[:1000],
            "parse_status": "parsed" if parsed else "needs_review",
            "ingredient_matches": matches,
            "review_sections": [section.splitlines()[0][:160] for section in parsed.review_sections] if parsed else [],
            "purchase_status": "needs_review" if not usable else "has_gaps" if gaps else "matched_in_index",
            "notice": "打开完整原文后逐项核对。缺商品先补查，仍缺项可明确列为需自行准备，不冒充商城商品。",
        }))
    candidates.sort(key=lambda pair: (tuple(-value for value in pair[0]), pair[1]["filename"]))
    return [item for _, item in candidates[:limit]]

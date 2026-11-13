"""根据菜名和食材召回候选，保留旧任务的商城排序。"""

import re
import asyncio
import json
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from functools import partial, lru_cache

from sqlalchemy import or_, select

from yuxi.services.health_family_kb_service import configured_health_kb_ids
from yuxi.services.health_nutrition_service import input_fingerprint
from yuxi.services.reference_recipe_matching import (
    ReferenceProductIndex, parse_reference_recipe, product_foods, reference_food_mentions, reference_ingredient_matches,
)
from yuxi.storage.postgres.models_knowledge import KnowledgeChunk, KnowledgeFile

_SEARCH_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="reference-recipes")


async def purchasable_reference_recipes(
    session, products: list[dict] | None, query: str, limit: int = 9, excluded_file_ids: set[str] | None = None,
    *, variety=None,
) -> list[dict]:
    """召回可完整解析的相关菜谱；原文读取与保存仍需独立验证。"""
    rows = await reference_recipe_rows(session)
    return await asyncio.get_running_loop().run_in_executor(
        _SEARCH_EXECUTOR,
        partial(rank_reference_recipes, rows, products, query, limit,
                excluded_file_ids=excluded_file_ids, variety=variety),
    )


async def purchasable_reference_recipes_batch(
    session, products: list[dict] | None, queries: list[str], excluded_file_ids: set[str] | None = None,
    *, variety=None,
) -> list[list[dict]]:
    """批量关键词共用菜谱正文和商品匹配，逐词独立排序。"""
    rows = await reference_recipe_rows(session)
    return await asyncio.get_running_loop().run_in_executor(
        _SEARCH_EXECUTOR, partial(rank_reference_recipe_batch, rows, products, queries, excluded_file_ids,
                                 **({"variety": variety} if variety else {}))
    )


def rank_reference_recipe_batch(rows, products, queries, excluded_file_ids=None, *, variety=None):
    """有界后台计算共用目录索引；不在 Worker 事件循环解析和匹配整库。"""
    documents = prepare_reference_documents(rows)
    available = available_reference_foods(products or [])
    analyzed = {}
    catalog_key = json.dumps(products, ensure_ascii=False, sort_keys=True)
    return [
        rank_prepared_reference_recipes(
            documents, products, available, query, 8, analyzed, excluded_file_ids=excluded_file_ids,
            catalog_key=catalog_key, variety=variety,
        )
        for query in queries
    ]


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


def rank_reference_recipes(
    rows, products: list[dict] | None, query: str, limit: int = 9, excluded_file_ids: set[str] | None = None,
    *, variety=None,
) -> list[dict]:
    """先满足食材相关性，再优先可解析、采购覆盖较高的简单做法。"""
    return rank_prepared_reference_recipes(
        prepare_reference_documents(rows), products, available_reference_foods(products or []), query, limit, {},
        excluded_file_ids=excluded_file_ids, variety=variety,
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
        prepared.append({**document, **prepared_content(document["source"]["filename"], tuple(document["chunks"]))})
    return prepared


@lru_cache(maxsize=8192)
def prepared_content(filename, chunks):
    """以实际分片内容缓存解析；文件删除仍由每次目录查询排除。"""
    content = "\n".join(value for _, value in chunks)
    title = re.sub(r"__[0-9a-f]+\.md$", "", filename, flags=re.I)
    title = title.removesuffix(".md").replace("_", " ").casefold()
    return {"content": content, "body": content.casefold(), "title": title,
            "title_foods": recall_foods(title), "foods": recall_foods(content),
            "parsed": parse_reference_recipe(content), "chunks_hash": input_fingerprint(chunks)}


@lru_cache(maxsize=4)
def cached_product_index(catalog_key):
    """商品全部事实参与缓存键，库存或身份变化立即使用新索引。"""
    return ReferenceProductIndex(json.loads(catalog_key))


@lru_cache(maxsize=16384)
def cached_ingredient_matches(ingredients, catalog_key):
    """只缓存公共商品与原谱匹配，不缓存家庭档案或最终餐单。"""
    return reference_ingredient_matches(ingredients, [], index=cached_product_index(catalog_key))


def available_reference_foods(products):
    """只把当前已读且有库存的商品作为召回加分项。"""
    available = {
        food
        for product in products
        if product.get("sale_status", "available") == "available"
        and int(product.get("available_quantity", 0)) > 0
        for food in product_foods(product)
    }
    return available


def recall_foods(text):
    """通用鱼虾蔬菜词只扩展目录召回，不参与原谱和商品身份校验。"""
    foods = reference_food_mentions(text)
    for food, pattern in {
        "鱼": r"鱼|魚|\b(?:fish|salmon|cod|tilapia|trout)\b",
        "虾": r"虾|蝦|\b(?:shrimp|prawns?)\b",
        "蔬菜": r"蔬菜|时蔬|青菜|\b(?:vegetables?|greens?)\b",
    }.items():
        if re.search(pattern, text, re.I):
            foods.add(food)
    return foods


def rank_prepared_reference_recipes(
    documents, products, available, query, limit, analyzed, excluded_file_ids: set[str] | None = None,
    *, catalog_key=None, variety=None,
):
    """每个关键词独立评分，复用本次调用已解析的候选原谱。"""
    terms = [term.casefold() for term in re.findall(r"[\w\u4e00-\u9fff]+", query) if len(term) > 1]
    catalog_key = catalog_key or json.dumps(products, ensure_ascii=False, sort_keys=True)
    query_foods = recall_foods(query) - {"水", "盐", "糖"}
    methods = [pattern for pattern in (
        r"\b(?:boil\w*|poach\w*)\b|煮", r"\bsteam\w*\b|蒸",
        r"\b(?:bak\w*|roast\w*)\b|烤", r"\b(?:porridge|congee)\b|粥",
        r"\bstir[- ]fr(?:y|ied)\b|炒",
    ) if re.search(pattern, query, re.I)]
    candidates = []
    excluded_file_ids = excluded_file_ids or set()
    for document in documents:
        if document["source"]["file_id"] in excluded_file_ids:
            continue
        title, content = document["title"], document["content"]
        if variety and variety.get("restrictions"):
            from yuxi.services.reference_meal_plan_service import reference_restriction_conflict

            from yuxi.services.health_vision_types import HealthVisionError

            try:
                if reference_restriction_conflict(content, variety["restrictions"]):
                    continue
            except HealthVisionError as error:
                if error.code != "reference_restriction_unverified":
                    raise
                # 未核实限制仍在保存时阻断；检索不取代原文及资料校验。
        foods = document["foods"]
        title_hits = sum(term in title for term in terms)
        body_hits = sum(term in document["body"] for term in terms)
        title_food_hits = len(document["title_foods"] & query_foods)
        query_hits = len(foods & query_foods)
        stock_hits = len(foods & available)
        if not (title_hits or body_hits or title_food_hits or query_hits):
            continue
        file_id = document["source"]["file_id"]
        parsed = document["parsed"]
        if parsed is None or parsed.review_sections:
            continue
        if file_id not in analyzed:
            analyzed[file_id] = (
                parsed,
                deepcopy(cached_ingredient_matches(parsed.ingredients, catalog_key)) if parsed and products is not None else [],
                document["chunks_hash"],
            )
        parsed, matches, chunks_hash = analyzed[file_id]
        from yuxi.services.reference_recipe_variety import dish_keys, candidate_priority, candidate_rotation

        keys = dish_keys({"name": parsed.name, "source": {"file_id": file_id}})
        if variety and keys & variety["excluded"]:
            continue
        gaps = sum(item["status"] in {"needs_confirmation", "missing_product"} for item in matches)
        covered = sum(item["status"] == "matched" for item in matches)
        required = sum(item["status"] not in {"cooking_water", "optional_not_selected"} for item in matches)
        exact_name = int(len(query.strip()) >= 5 and query.casefold().strip() in title)
        relevant_title = title_food_hits if query_foods else title_hits
        method_hits = sum(bool(re.search(pattern, title, re.I)) for pattern in methods)
        coverage = covered / max(required, 1)
        score = (exact_name, bool(relevant_title), method_hits,
                 *candidate_priority(keys, content, variety), coverage >= 0.5, candidate_rotation(keys, variety),
                 coverage, -gaps, relevant_title, query_hits, body_hits, stock_hits)
        candidates.append((score, {
            **document["source"], "chunks_hash": chunks_hash,
            "name": parsed.name,
            "excerpt": content[:320],
            "parse_status": "parsed",
            "ingredient_matches": matches,
            "review_sections": [],
            "purchase_status": "unchecked" if products is None else "has_gaps" if gaps else "matched_in_index",
            "notice": "打开完整原文后逐项核对。缺商品先补查，仍缺项可明确列为需自行准备，不冒充商城商品。",
        }))
    candidates.sort(key=lambda pair: (tuple(-value for value in pair[0]), pair[1]["filename"]))
    return [item for _, item in candidates[:limit]]

"""参考餐单按原位置换一道菜，不重排整餐。"""

import copy
import asyncio
import re
from datetime import datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

from yuxi.services.health_nutrition_service import input_fingerprint
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.services.meal_dish_service import dish_key, freeze_origin, read_origin


async def swap_candidates(uid, family_id, day, version):
    """一次回读全日候选，调用方按菜展示零至三张卡。"""
    from yuxi.services.daily_meal_plan_service import read_current_plan
    from yuxi.storage.postgres.manager import pg_manager

    require_today(day)
    async with pg_manager.get_async_session_context() as session:
        plan = await read_current_plan(uid, family_id, day, session=session)
        require_version(plan, version)
        return {"date": str(day), "version": version, "meals": await plan_candidates(session, uid, family_id, plan)}


async def replace_dish(uid, family_id, day, data):
    """锁住当前日计划，只更新选中位置并保留幂等回执。"""
    from yuxi.services.daily_meal_plan_service import current_row, read_current_plan
    from yuxi.storage.postgres.manager import pg_manager
    from yuxi.utils.datetime_utils import utc_now_naive

    require_today(day)
    fingerprint = input_fingerprint(data.model_dump(mode="json", exclude={"client_request_id"}))
    async with pg_manager.get_async_session_context() as session:
        row = await current_row(session, uid, family_id, day, lock=True)
        plan = await read_current_plan(uid, family_id, day, session=session)
        refs = copy.deepcopy(row.meal_sources) if row else {}
        receipts = refs.get("_swap_receipts", {})
        key = uid + ":" + str(data.client_request_id)
        if key in receipts:
            if receipts[key] != fingerprint:
                raise HealthVisionError("swap_request_conflict", "同一换菜请求不能改选其他菜", 409)
            return plan
        require_version(plan, data.version)
        choices = await plan_candidates(session, uid, family_id, plan)
        choice = next(
            (
                c
                for m in choices
                if m["meal_type"] == data.meal_type
                for d in m["dishes"]
                if d["dish_key"] == data.dish_key
                for c in d["candidates"]
                if c["candidate_id"] == data.candidate_id
            ),
            None,
        )
        if choice is None:
            raise HealthVisionError("swap_candidate_changed", "候选已变化，请重新打开换一换", 409)
        meal = next(m for m in plan["meals"] if m["meal_type"] == data.meal_type)
        origins = [await freeze_origin(session, d["origin"]) for d in meal["meal"]["dishes"]]
        position = next(i for i, d in enumerate(meal["meal"]["dishes"]) if dish_key(d) == data.dish_key)
        anchor = origins[position]
        if anchor["source"]["kind"] == "replacement":
            anchor = anchor["anchor"]
        origins[position] = {
            "source": {"kind": "replacement", "id": str(uuid4()), "version": data.version + 1},
            "date": str(day),
            "meal_type": data.meal_type,
            "dish_key": dish_key(choice["dish"]),
            "anchor": anchor,
            "actor_uid": uid,
            "snapshot": choice["snapshot"],
        }
        refs[data.meal_type] = {
            "kind": "selection",
            "id": str(uuid4()),
            "version": data.version + 1,
            "dish_sources": origins,
            "member_ids": [m["id"] for m in meal["members"]],
        }
        receipts[key] = fingerprint
        refs["_swap_receipts"] = receipts
        row.meal_sources, row.version, row.updated_at = refs, data.version + 1, utc_now_naive()
        await session.flush()
        result = await read_current_plan(uid, family_id, day, session=session)
        await session.commit()
        return result


async def read_replacement(session, uid, family_id, origin):
    """回读时重验授权锚点、成员资料和新菜谱原文。"""
    from yuxi.services.reference_meal_plan_service import recipe_document, reference_restriction_conflict

    _, _, members, _ = await read_origin(session, uid, family_id, origin["anchor"])
    context = await meal_context(session, origin["actor_uid"], family_id, origin["date"], origin["meal_type"], members)
    saved = origin["snapshot"]
    if context["sources"] != saved["context_sources"]:
        raise HealthVisionError("dish_members_changed", "就餐成员资料已变化，请重新核对餐单", 409)
    dish = copy.deepcopy(saved["dish"])
    doc = await recipe_document(session, dish["file_id"], dish["chunk_id"])
    require_recipe_quotes(dish, doc)
    if any(doc[k] != dish["source"][k] for k in ("kb_id", "file_hash", "chunks_hash")):
        raise HealthVisionError("dish_source_changed", "替换菜谱来源已变化，请重新核对餐单", 409)
    restrictions = saved["restrictions"]
    if reference_restriction_conflict(doc["content"], restrictions):
        raise HealthVisionError("reference_restriction_conflict", "替换菜谱不符合当前成员限制", 422)
    from yuxi.services.reference_meal_plan_service import reference_meal_media
    from yuxi.services.reference_recipe_presentation import attach_recipe_products

    meal = {"meal_type": origin["meal_type"], "dishes": [dish], "members": context["members"]}
    meal = attach_recipe_products(await reference_meal_media(session, meal), saved["product_matches"])
    source = {
        "meals": [meal],
        "members": context["members"],
        "source_owner": origin["actor_uid"],
        "product_matches": saved["product_matches"],
        "purchase_gaps": saved["purchase_gaps"],
    }
    return meal["dishes"][0], meal, context["members"], source


async def plan_candidates(session, uid, family_id, plan):
    """每餐只为真实参考菜寻找同类型替代，不更改其他菜的验重规则。"""
    from yuxi.repositories.reference_variety_repository import reference_history
    from yuxi.services.daily_commerce_service import current_product_catalog
    from yuxi.services.reference_meal_plan_service import (
        recipe_document,
        reference_member_restrictions,
        reference_restriction_conflict,
        unverified_reference_restrictions,
        reference_meal_media,
    )
    from yuxi.services.reference_recipe_index import reference_recipe_rows, prepare_reference_documents
    from yuxi.services.reference_recipe_variety import variety_context, dish_keys

    documents = prepare_reference_documents(await reference_recipe_rows(session))
    products = (await current_product_catalog())["items"]
    occupied = set().union(*(dish_keys(d) for m in plan["meals"] for d in m["meal"]["dishes"]))
    result = []
    for meal in plan["meals"]:
        anchors = [d["origin"].get("anchor", d["origin"]) for d in meal["meal"]["dishes"]]
        if not any(a["source"]["kind"] == "reference" for a in anchors):
            result.append({"meal_type": meal["meal_type"], "dishes": []})
            continue
        context = await meal_context(session, uid, family_id, plan["date"], meal["meal_type"], meal["members"])
        restrictions = reference_member_restrictions(context["members"]) + context.get("memory_restrictions", [])
        policy = variety_context(
            await reference_history(session, context["selection"]), context["selection"], context["members"]
        )
        policy["excluded"].update(occupied)
        safe_products = [
            p
            for p in products
            if not unverified_reference_restrictions(restrictions)
            and not reference_restriction_conflict(str(p), restrictions)
        ]
        rows = []
        for original in meal["meal"]["dishes"]:
            candidates = []
            anchor = original["origin"]
            if anchor["source"]["kind"] == "replacement":
                anchor = anchor["anchor"]
            if anchor["source"]["kind"] == "reference" and not unverified_reference_restrictions(restrictions):
                ranked = await asyncio.to_thread(
                    rank_candidates, original, documents, safe_products, restrictions, policy
                )
                for candidate in ranked:
                    doc = await recipe_document(session, candidate["dish"]["file_id"], candidate["dish"]["chunk_id"])
                    if any(doc[k] != candidate["dish"]["source"][k] for k in ("file_hash", "chunks_hash")):
                        continue
                    if reference_restriction_conflict(doc["content"], restrictions):
                        continue
                    try:
                        require_recipe_quotes(candidate["dish"], doc)
                    except HealthVisionError as error:
                        if error.code != "swap_recipe_changed":
                            raise
                        continue
                    display = await reference_meal_media(session, {"dishes": [candidate["dish"]]})
                    candidate["dish"] = display["dishes"][0]
                    candidate["snapshot"] = {
                        **candidate["snapshot"],
                        "dish": candidate["dish"],
                        "context_sources": context["sources"],
                        "restrictions": restrictions,
                    }
                    candidate["candidate_id"] = input_fingerprint(
                        {
                            "uid": uid,
                            "family": family_id,
                            "date": plan["date"],
                            "version": plan["version"],
                            "meal": meal["meal_type"],
                            "original": dish_key(original),
                            "source": candidate["dish"]["source"],
                            "context": context["sources"],
                        }
                    )
                    candidates.append(candidate)
                    if len(candidates) == 3:
                        break
            rows.append({"dish_key": dish_key(original), "candidates": candidates})
        result.append({"meal_type": meal["meal_type"], "dishes": rows})
    return result


def rank_candidates(original, documents, products, restrictions, policy):
    """只按菜品类型和现实准备条件排序，不读取热量或营养数据。"""
    from yuxi.services.reference_meal_plan_service import reference_restriction_conflict, reference_product_group
    from yuxi.services.reference_recipe_matching import reference_ingredient_matches
    from yuxi.services.reference_recipe_variety import dish_keys, candidate_priority
    from yuxi.services.reference_meal_composition import is_plain_reference_staple

    kind = recipe_kind(original["name"], original.get("ingredients", []))
    if not kind:
        return []
    ranked = []
    for document in documents:
        parsed = document["parsed"]
        if not parsed or parsed.review_sections or recipe_kind(parsed.name, parsed.ingredients) != kind:
            continue
        if is_plain_reference_staple(parsed.name, parsed.ingredients):
            continue
        dish = {
            **document["source"],
            "name": parsed.name,
            "ingredients": list(parsed.ingredients),
            "steps": list(parsed.steps),
            "source": {**document["source"], "chunks_hash": document["chunks_hash"]},
            "recipe_text_source": "original",
            "nutrition_status": "not_calculated",
        }
        if dish_keys(dish) & policy["excluded"] or reference_restriction_conflict(document["content"], restrictions):
            continue
        minutes = explicit_minutes(document["content"])
        if minutes:
            dish["cooking_minutes"] = minutes
        matches = reference_ingredient_matches(parsed.ingredients, products)
        mapped, gaps, cost = {}, [], 0
        for match in matches:
            product = next(
                (
                    p
                    for p in products
                    if str(p["product_id"]) == match["product_id"]
                    and any(
                        s.get("sale_status") == "available" and s.get("available_quantity", 0) > 0
                        for s in p.get("skus", [])
                    )
                ),
                None,
            )
            if product:
                pid = str(product["product_id"])
                mapped.setdefault(pid, reference_product_group(product))["ingredient_refs"].append(match["ingredient"])
                prices = [
                    s["price_cent"]
                    for s in product["skus"]
                    if type(s.get("price_cent")) is int
                    and s.get("sale_status") == "available"
                    and s.get("available_quantity", 0) > 0
                ]
                cost += min(prices) if prices else 0
            else:
                reason = {
                    "cooking_water": "not_sold",
                    "optional_not_selected": "optional_not_selected",
                    "needs_confirmation": "needs_confirmation",
                }.get(match["status"], "no_match")
                gaps.append({"ingredient": match["ingredient"], "reason": reason})
        coverage = sum(len(p["ingredient_refs"]) for p in mapped.values()) / max(len(matches), 1)
        score = (
            -coverage,
            *(-v for v in candidate_priority(dish_keys(dish), document["content"], policy)),
            minutes is None,
            minutes or 0,
            not bool(mapped),
            cost,
            str(dish["file_id"]),
        )
        ranked.append(
            (score, {"dish": dish, "snapshot": {"product_matches": list(mapped.values()), "purchase_gaps": gaps}})
        )
    return [candidate for _, candidate in sorted(ranked, key=lambda pair: pair[0])]


async def meal_context(session, uid, family_id, day, meal_type, members):
    """只处理本餐实际成员，复用已有档案字段和配餐用途授权。"""
    from yuxi.repositories.family_repository import FamilyRepository
    from yuxi.services.reference_meal_plan_service import reference_context_in_session
    from yuxi.services.health_memory_context_service import account_plan_restrictions

    anchor = await FamilyRepository(session).linked_health_member(family_id, members[0]["id"])
    current = await reference_context_in_session(
        session,
        uid,
        anchor,
        {
            "mode": "reference",
            "family_id": family_id,
            "plan_date": str(day),
            "participant_ids": [m["id"] for m in members],
            "meal_types": [meal_type],
        },
    )
    memories = await account_plan_restrictions(session, uid, current)
    if memories:
        current["sources"]["memory_restrictions"] = memories
    current["memory_restrictions"] = [fact["restriction"] for fact in memories]
    return current


def recipe_kind(name, ingredients):
    """只识别明确菜品类型，未识别时不猜测可互换关系。"""
    meat = (
        r"鸡|雞|鸭|鴨|牛肉|牛腩|羊肉|猪肉|豬肉|排骨|鱼|魚|虾|蝦|蟹|海鲜|蛤蜊|"
        r"\b(?:chicken|beef|pork|lamb|fish|salmon|cod|shrimp|turkey|crab|clam|seafood)\b"
    )
    for kind, pattern in (
        ("汤羹", r"汤|羹|湯|\b(?:soup|broth|chowder)\b"),
        ("凉菜沙拉", r"沙拉|沙律|凉拌|涼拌|\bsalads?\b"),
        (
            "主食",
            r"饭|飯|面条|麵|吐司|馒头|饼|粥|意面|米粉|\b(?:rice|pasta|noodles|bread|toast|pancakes|oatmeal|pizza)\b",
        ),
        (
            "荤菜",
            meat,
        ),
        (
            "素菜",
            r"荷塘月色|蔬菜|时蔬|菠菜|西兰花|茄子|豆腐|白菜|黄瓜|蘑菇|芦笋|"
            r"\b(?:vegetables|spinach|broccoli|tofu|cabbage|eggplant|zucchini|asparagus)\b",
        ),
    ):
        if re.search(pattern, name, re.I):
            if kind == "素菜" and re.search(meat, " ".join(ingredients), re.I):
                return "荤菜"
            return kind
    return None


def explicit_minutes(content):
    """仅使用原文明确的总时间，不能把单步时间当总时间。"""
    match = re.search(
        r"(?:总(?:制作|用)?时[间長]|制作时间|total\s+time)\s*[:：]\s*(\d{1,3})\s*(?:分钟|minutes?|mins?)", content, re.I
    )
    return int(match[1]) if match and 0 < int(match[1]) <= 1440 else None


def require_recipe_quotes(dish, document):
    """完整原文须与用于排序的分片解析一致，不能凭分片哈希代替原文核对。"""
    from yuxi.services.reference_recipe_matching import parse_reference_recipe
    from yuxi.services.reference_meal_composition import is_plain_reference_staple

    parsed = parse_reference_recipe(document["content"])
    if (
        not parsed
        or parsed.review_sections
        or is_plain_reference_staple(parsed.name, parsed.ingredients)
        or parsed.name != dish["name"]
        or list(parsed.ingredients) != dish["ingredients"]
        or list(parsed.steps) != dish["steps"]
    ):
        raise HealthVisionError("swap_recipe_changed", "候选食材或做法与完整原文不一致，请刷新候选", 409)


def require_today(day):
    """换菜入口只修改当天当前餐单。"""
    if day != datetime.now(ZoneInfo("Asia/Shanghai")).date():
        raise HealthVisionError("swap_date_invalid", "请打开今日餐单换菜", 422)


def require_version(plan, version):
    """过期卡片不能覆盖刚更新的餐单。"""
    if plan["version"] != version:
        raise HealthVisionError("daily_plan_version_changed", "餐单已更新，请刷新后换菜", 409)

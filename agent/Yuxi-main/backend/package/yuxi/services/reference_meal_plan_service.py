"""以当前授权档案、知识原文和同 Run 回执保存日常参考餐单。"""

import hashlib
import json
import re
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import select

from yuxi.repositories.family_repository import FamilyRepository
from yuxi.repositories.health_vision_repository import HealthVisionRepository
from yuxi.repositories.tool_message_audit_repository import ToolMessageAuditRepository
from yuxi.services.daily_commerce_service import commerce_request, current_catalog
from yuxi.services.family_service import FamilyService, authorized_fields
from yuxi.services.health_family_kb_service import configured_health_kb_ids
from yuxi.services.health_meal_plan_service import require_planner_run
from yuxi.services.health_nutrition_service import input_fingerprint
from yuxi.services.health_vision_service import health_vision_service
from yuxi.services.health_vision_types import HealthVisionError, NUTRIENTS
from yuxi.services.miniapp_profile_types import miniapp_onboarding_ready
from yuxi.services.reference_recipe_matching import (
    ingredient_food,
    optional_reference_ingredient,
    parse_reference_recipe,
    product_food,
)
from yuxi.services.reference_meal_plan_types import (
    REFERENCE_CATALOG_CHAIN_VERSION,
    REFERENCE_TOOLS,
    ReferencePlanDraft,
    ReferenceSelection,
)
from yuxi.services.recipe_translation_service import checked_chinese_display, save_chinese_display
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_health import HealthInitialPlanPreview
from yuxi.storage.postgres.models_knowledge import KnowledgeChunk, KnowledgeFile


class ReferencePlanSourceChanged(HealthVisionError):
    """当前授权已核对，仅旧资料或菜谱版本需要重新生成。"""

    def __init__(self, message, selection):
        super().__init__("source_invalidated", message, 410)
        self.selection = selection


def reference_binding(binding):
    """模式只来自服务端绑定，不从模型输出推断。"""
    fixed = getattr(binding, "initial_planner_selection", None)
    selection = fixed.get("selection") if isinstance(fixed, dict) else None
    return isinstance(selection, dict) and selection.get("mode") == "reference"


async def reference_context_in_session(session, uid, anchor, selection):
    """核对每位成员的当前资料、字段范围及独立配餐用途同意。"""
    selected = ReferenceSelection.model_validate(selection)
    family, _ = await FamilyService(session, uid).context(str(selected.family_id))
    health, repo = HealthVisionRepository(session), FamilyRepository(session)
    config = await health_vision_service.configuration(session)
    model = config["meal_plan"]
    if not model["available"]:
        raise HealthVisionError("consultation_unavailable", "参考餐单的配餐处理配置尚未就绪", 503)
    processing = {"model": model["model"], "processor": model["processor"], "policy_version": config["policy_version"]}
    members, sources = [], {}
    for mid in map(str, selected.participant_ids):
        member = await repo.member(family.id, mid)
        hid = await repo.linked_health_member(family.id, mid)
        if member is None or not member.is_active or hid is None:
            raise HealthVisionError("reference_member_unavailable", "所选成员尚未完成资料关联与授权", 409)
        if "dietary_details" not in authorized_fields(family, member, uid, family_sharing=True):
            raise HealthVisionError("not_authorized", "所选成员的饮食资料尚未授权", 403)
        if not miniapp_onboarding_ready(member, family):
            raise HealthVisionError("reference_profile_unconfirmed", "请先核对并确认所选成员的完整档案", 409)
        for scope in ("ai_use", "profile_view", "diet_edit"):
            await health.authorize(hid, uid, scope)
        await health.require_consent(hid, uid, "meal_plan", processing)
        p = member.profile or {}
        sources[mid] = {"health_member_id": hid, "version": member.version, "profile_hash": input_fingerprint(p)}
        dietary = p.get("dietary_details") or {}
        members.append(
            {
                "id": mid,
                "name": member.name,
                "relation": member.relationship,
                "dietary": dietary,
                "allergens": dietary.get("allergies"),
                "avoidances": dietary.get("avoidances"),
                "intolerances": dietary.get("intolerances"),
                "doctor_instructions": dietary.get("clinicianGuidance"),
            }
        )
    if str(anchor) not in {v["health_member_id"] for v in sources.values()}:
        raise HealthVisionError("reference_member_required", "入口成员必须包含在所选就餐者中", 422)
    return {
        "selection": selected.model_dump(mode="json", exclude_none=True),
        "members": members,
        "sources": {
            "family_id": family.id,
            "family_version": family.version,
            "members": sources,
            "recipe_kb_ids": list(configured_health_kb_ids("health-meal-planner")),
        },
    }


async def bound_reference_context(session, uid, binding):
    """资料变化后使旧线程失效，不能继续沿用旧成员快照。"""
    if not reference_binding(binding):
        raise HealthVisionError("reference_mode_required", "当前线程不是日常参考餐单模式", 409)
    fixed = binding.initial_planner_selection
    result = await reference_context_in_session(session, uid, binding.member_id, fixed["selection"])
    if input_fingerprint(result["sources"]) != fixed["source_hash"]:
        raise ReferencePlanSourceChanged("成员资料或知识库绑定已更新，请重新生成参考餐单", result["selection"])
    return result


def product_facts(sku, *, include_description=False):
    """商品身份和包装变化使选择失效，价格与库存继续实时回读。"""
    facts = {
        k: sku.get(k)
        for k in (
            "sku_id",
            "product_id",
            "product_name",
            "sku_name",
            "net_content",
            "ingredients",
            "allergen_codes",
            "data_completeness",
            "data_issues",
        )
    }
    if include_description:
        facts["product_description_hash"] = hashlib.sha256((sku.get("product_description") or "").encode()).hexdigest()
    return facts


def reference_product(sku, quantity=1, *, description_limit=4000):
    """只返回商城事实，配料不完整保持明确提示。"""
    return {
        **product_facts(sku),
        "category_code": sku.get("category_code"),
        "product_description": (sku.get("product_description") or "")[:description_limit],
        "description_truncated": len(sku.get("product_description") or "") > description_limit,
        "quantity": quantity,
        "price_cent": sku.get("price_cent"),
        "image_url": sku.get("image_url", ""),
        "available_quantity": sku.get("available_quantity"),
        "facts_version": 2,
        "facts_hash": input_fingerprint(product_facts(sku, include_description=True)),
        "composition_notice": "商品配料及过敏原资料未完成核对，请结合包装信息确认。"
        if not sku.get("ingredients") or sku.get("data_completeness") != "complete"
        else "商品资料未作个人过敏适用性或专业营养审核，请核对包装信息。",
    }


async def get_reference_context(context):
    """向 Agent 提供授权就餐范围与商城有货分类，不展开商品。"""
    async with pg_manager.get_async_session_context() as session:
        _, binding = await require_planner_run(session, context)
        current = await bound_reference_context(session, context.uid, binding)
    categories = await commerce_request("GET", "/api/v1/integration/ai/catalog/categories")
    if not isinstance(categories.get("items"), list) or not isinstance(categories.get("catalog_version"), str):
        raise HealthVisionError("catalog_invalid", "商城分类暂时无法核对", 503)
    if not categories["items"]:
        raise HealthVisionError("catalog_empty", "商城暂无可核对的在售食材分类", 503)
    if any(
        not isinstance(row, dict)
        or not isinstance(row.get("category_code"), str)
        or not row["category_code"]
        or not isinstance(row.get("name"), str)
        or not isinstance(row.get("product_count"), int)
        or row["product_count"] < 1
        for row in categories["items"]
    ):
        raise HealthVisionError("catalog_invalid", "商城分类暂时无法核对", 503)
    current_plan = None
    if current["selection"].get("daily_base_version") is not None:
        from datetime import date
        from yuxi.services.daily_meal_plan_service import read_current_plan

        current_plan = await read_current_plan(
            context.uid, current["selection"]["family_id"], date.fromisoformat(current["selection"]["plan_date"])
        )
        if current_plan["version"] != current["selection"]["daily_base_version"]:
            raise HealthVisionError("daily_plan_version_changed", "今日计划已有更新，请重新读取后调整", 409)
    unverified = unverified_reference_restrictions(reference_member_restrictions(current["members"]))
    result = {
        "scope": "daily_reference",
        **current,
        "current_daily_plan": current_plan,
        "restriction_verification": {
            "status": "needs_verification" if unverified else "supported_terms",
            "unverified_restrictions": unverified,
            "notice": "仅现有有限牛羊肉名称可核对；其他硬限制及未完整解释的自述须先核实，不能据未命中判定无冲突。",
        },
        "categories": categories["items"],
        "catalog_version": categories["catalog_version"],
        "commerce_notice": None,
        "boundary": "日常烹饪参考，未作专业审核；未核算营养和个人达标结论。",
    }
    if unverified:
        from yuxi.services.restricted_cooking_reference_service import restricted_cooking_catalog

        candidates = restricted_cooking_catalog(current)
        if candidates["items"]:
            result["cooking_reference_candidates"] = candidates
    return result


async def find_reference_products(context, category_codes):
    """仅按本 Run 已读真实分类查商品，保留 SKU 原文回执。"""
    async with pg_manager.get_async_session_context() as session:
        run, binding = await require_planner_run(session, context)
        await bound_reference_context(session, context.uid, binding)
        receipts = await tool_payloads(session, run, "get_reference_plan_context")
        if not receipts:
            raise HealthVisionError("reference_receipt_invalid", "请先读取当前成员和商城分类", 409)
        available = {row["category_code"] for row in receipts[-1].get("categories", [])}
        if (
            not isinstance(category_codes, list)
            or not 1 <= len(category_codes) <= 4
            or any(not isinstance(code, str) for code in category_codes)
            or len(set(category_codes)) != len(category_codes)
            or any(code not in available for code in category_codes)
        ):
            raise HealthVisionError("catalog_category_invalid", "只能查询本轮商城实际有货的分类", 422)
    catalog = await current_catalog(category_codes=category_codes)
    return {
        "category_codes": category_codes,
        "catalog_version": catalog["version"],
        "catalog": [
            reference_product(s, description_limit=320) for s in catalog["items"] if s.get("sale_status") == "available"
        ],
    }


async def search_reference_recipes(context, query):
    """用本 Run 已读商品检索相关菜谱，保留格式和采购待核对项。"""
    batch = isinstance(query, list)
    queries = query if batch else [query]
    if (
        not 1 <= len(queries) <= 4
        or any(not isinstance(value, str) or not 1 <= len(value.strip()) <= 80 for value in queries)
        or len({value.strip() for value in queries}) != len(queries)
    ):
        raise HealthVisionError("knowledge_query_invalid", "请使用简短菜名或食材关键词", 422)
    from yuxi.services.reference_recipe_index import purchasable_reference_recipes, purchasable_reference_recipes_batch

    async with pg_manager.get_async_session_context() as session:
        run, binding = await require_planner_run(session, context)
        await bound_reference_context(session, context.uid, binding)
        reads = await tool_payloads(session, run, "find_reference_products")
        if not reads:
            raise HealthVisionError("reference_product_required", "请先按商城分类读取在售商品", 409)
        products = {str(sku["sku_id"]): sku for read in reads for sku in read.get("catalog", [])}
        items, seen = [], set()
        ranked = (
            await purchasable_reference_recipes_batch(session, list(products.values()), queries)
            if batch
            else [await purchasable_reference_recipes(session, list(products.values()), queries[0])]
        )
        for matches in ranked:
            for item in matches:
                key = (item["file_id"], item["chunk_id"])
                if key not in seen:
                    items.append(item)
                    seen.add(key)
                    if len(items) == 9:
                        break
            if len(items) == 9:
                break
    return {
        "scope": "reference_recipe_search",
        "status": "ok",
        "items": items,
        **({"queries": queries} if batch else {}),
    }


async def recipe_document(session, file_id, chunk_id):
    """打开固定库的完整原始文件，并校验原始字节和分片版本。"""
    from yuxi.knowledge.utils.kb_utils import parse_minio_url
    from yuxi.storage.minio import StorageError, get_minio_client

    kb_ids = configured_health_kb_ids("health-meal-planner")
    file = await session.scalar(
        select(KnowledgeFile)
        .where(KnowledgeFile.file_id == file_id, KnowledgeFile.kb_id.in_(kb_ids))
        .with_for_update(read=True)
    )
    if (
        file is None
        or file.is_folder
        or file.status != "indexed"
        or not (file.minio_url or file.path)
        or not file.content_hash
    ):
        raise HealthVisionError("reference_source_unavailable", "菜谱原文不可核对", 410)
    chunks = list(
        (
            await session.scalars(
                select(KnowledgeChunk)
                .where(KnowledgeChunk.file_id == file_id, KnowledgeChunk.kb_id == file.kb_id)
                .order_by(KnowledgeChunk.chunk_index, KnowledgeChunk.id)
                .with_for_update(read=True)
            )
        ).all()
    )
    if not chunks or not any(chunk.chunk_id == chunk_id for chunk in chunks):
        raise HealthVisionError("reference_source_unavailable", "检索命中的菜谱分片已移除", 410)
    try:
        bucket, name = parse_minio_url(file.minio_url or file.path)
        raw = await get_minio_client().adownload_file(bucket, name)
        if len(raw) > 65536 or hashlib.sha256(raw).hexdigest() != file.content_hash:
            raise ValueError("source hash mismatch")
        content = raw.decode("utf-8")
    except (ValueError, UnicodeError, OSError, StorageError):
        raise HealthVisionError("reference_source_unavailable", "菜谱完整原文暂时无法核对", 410) from None
    return {
        "scope": "reference_recipe",
        "file_id": file.file_id,
        "kb_id": file.kb_id,
        "chunk_id": chunk_id,
        "filename": file.filename,
        "file_hash": file.content_hash,
        "chunks_hash": input_fingerprint([(chunk.chunk_id, chunk.content) for chunk in chunks]),
        "content": content,
    }


async def tool_payloads(session, run, tool_name):
    """只接受当前 Run 已完成且归属一致的工具审计。"""
    values = []
    for audit in await ToolMessageAuditRepository(session).list_for_run(run.id):
        if (audit.extra_metadata or {}).get("tool_name") != tool_name or audit.execution_status != "completed":
            continue
        if audit.request_id != run.request_id or audit.conversation_id != run.conversation_id:
            raise HealthVisionError("reference_receipt_invalid", "参考资料回执归属不一致", 409)
        payload = json.loads(audit.content)
        if tool_name == "read_reference_recipe" and isinstance(payload, dict) and "items" in payload:
            if not isinstance(payload["items"], list) or any(not isinstance(item, dict) for item in payload["items"]):
                raise HealthVisionError("reference_receipt_invalid", "菜谱原文批量回执格式不正确", 409)
            values.extend(payload["items"])
        else:
            values.append(payload)
    return values


async def read_reference_recipe(context, file_id, chunk_id):
    """只打开本 Run 检索过的菜谱，正文中的命令不具有权限。"""
    async with pg_manager.get_async_session_context() as session:
        run, binding = await require_planner_run(session, context)
        await bound_reference_context(session, context.uid, binding)
        hits = await tool_payloads(session, run, "search_reference_recipes")
        if not any(
            i["file_id"] == file_id and i["chunk_id"] == chunk_id for payload in hits for i in payload.get("items", [])
        ):
            raise HealthVisionError("reference_receipt_invalid", "请先检索当前菜谱资料再打开原文", 409)
        document = await recipe_document(session, file_id, chunk_id)
        reads = await tool_payloads(session, run, "find_reference_products")
        products = {str(sku["sku_id"]): sku for read in reads for sku in read.get("catalog", [])}
        check = reference_recipe_check(document["content"], list(products.values()))
        if "name" in check:
            from yuxi.services.recipe_translation_service import cached_chinese_display, needs_translation

            dish = {key: check[key] for key in ("name", "ingredients", "steps")}
            dish.update(
                portion_quote=None,
                nutrition_quote=None,
                source={
                    key: document[key]
                    for key in ("file_id", "chunk_id", "kb_id", "filename", "file_hash", "chunks_hash")
                },
            )
            display = await cached_chinese_display(session, dish)
            check["translation_status"] = (
                "ready"
                if display is not None
                else "required"
                if any(
                    needs_translation(text)
                    for text in (
                        dish["name"],
                        *dish["ingredients"],
                        *dish["steps"],
                    )
                )
                else "not_required"
            )
            if display is not None:
                check["display_zh"] = display
        return {**document, "recipe_check": check}


def reference_recipe_check(content, products):
    """展示完整原文的逐项诊断，商品读取快照不能代替保存时重验。"""
    from yuxi.services.reference_recipe_matching import reference_ingredient_matches

    parsed = parse_reference_recipe(content)
    if parsed is None:
        return {
            "status": "needs_review",
            "notice": (
                "完整原文已返回，但食材或步骤边界尚无法完整解析；请核对原文或换一份可核对菜谱，不能称为知识库无资料。"
            ),
            "ingredient_matches": [],
        }
    matches = reference_ingredient_matches(parsed.ingredients, products)
    return {
        "status": "needs_review"
        if parsed.review_sections
        else "has_gaps"
        if any(i["status"] in {"missing_product", "needs_confirmation"} for i in matches)
        else "matched",
        "name": parsed.name,
        "ingredients": list(parsed.ingredients),
        "steps": list(parsed.steps),
        "review_sections": list(parsed.review_sections),
        "ingredient_matches": matches,
        "notice": (
            "缺商品先补查分类；仍缺项可标为需自行准备。missing_product用no_match，"
            "needs_confirmation用同名原因；附加章节待核对时改选可完整解析的菜谱。"
        ),
    }


def same_reference_document(fresh, receipt):
    """仅以完整来源字段校验原文，附带诊断不参与授权或原文证明。"""
    return all(key in receipt and receipt[key] == value for key, value in fresh.items())


def checked_reference_meals(draft, documents, members):
    """核对原文引句及明确限制，数值和专业状态由服务端固定。"""
    result = []
    restrictions = reference_member_restrictions(members)
    for meal in draft.meals:
        dishes = []
        for dish in meal.dishes:
            doc = documents.get((dish.file_id, dish.chunk_id))
            if doc is None:
                raise HealthVisionError("reference_receipt_invalid", "餐单使用了本 Run 未打开的菜谱", 409)
            quotes = [
                dish.name,
                *dish.ingredients,
                *dish.steps,
                *([dish.portion_quote] if dish.portion_quote else []),
                *([dish.nutrition_quote] if dish.nutrition_quote else []),
            ]
            parsed = parse_reference_recipe(doc["content"])
            if (
                parsed is None
                or parsed.review_sections
                or dish.name != parsed.name
                or tuple(dish.ingredients) != parsed.ingredients
                or tuple(dish.steps) != parsed.steps
                or any(not q.strip() or q not in doc["content"] for q in quotes)
            ):
                raise HealthVisionError("reference_quote_invalid", "菜谱食材或步骤与完整原文不一致", 422)
            if reference_restriction_conflict(doc["content"], restrictions):
                raise HealthVisionError("reference_restriction_conflict", "所选菜谱含已明确填写的过敏或忌口食材", 422)
            checked_chinese_display(
                dish.model_dump(exclude={"display_zh"}),
                dish.display_zh.model_dump() if dish.display_zh else None,
            )
            dishes.append(
                {
                    **dish.model_dump(mode="json", exclude={"display_zh"}),
                    **reference_recipe_media(doc["content"], dish.steps),
                    "source": {
                        k: doc[k] for k in ("file_id", "chunk_id", "kb_id", "filename", "file_hash", "chunks_hash")
                    },
                    "portion_note": "个人份量尚未核定，请参考原食谱并按实际情况调整",
                    "nutrition": {code: None for code in NUTRIENTS},
                    "nutrition_status": "not_calculated",
                }
            )
        result.append({"meal_type": meal.meal_type, "dishes": dishes})
    return sorted(result, key=lambda m: ("breakfast", "lunch", "dinner").index(m["meal_type"]))


def reference_recipe_media(content, steps, source=None):
    """仅采用原食谱正文明确包含的图片，不生成或猜配步骤图。"""
    from urllib.parse import urlsplit

    images = []
    for match in re.finditer(r"!\[[^\]]*\]\(([^\s)]+)(?:\s+[^)]*)?\)", content):
        url = match[1]
        parsed = urlsplit(url)
        if parsed.scheme == "https" and parsed.hostname and not parsed.username and not parsed.password:
            images.append((match.start(), url))
    positions = [content.find(step) if content.count(step) == 1 else -1 for step in steps]
    step_images = []
    for index, position in enumerate(positions):
        end = next((p for p in positions[index + 1 :] if p > position), len(content))
        step_images.append(next((url for start, url in images if position >= 0 and position <= start < end), ""))
    result = {"image_url": images[0][1] if images else "", "step_images": step_images}
    if not images:
        from yuxi.services.recipe_cover_service import recipe_cover

        result.update(recipe_cover(source))
    return result


async def reference_meal_media(session, meal):
    """给已授权且哈希一致的历史菜谱补充展示媒体，不改保存回执。"""
    import copy

    result = copy.deepcopy(meal)
    for dish in result["dishes"]:
        doc = await recipe_document(session, dish["file_id"], dish["chunk_id"])
        if any(doc[k] != dish["source"][k] for k in ("kb_id", "file_hash", "chunks_hash")):
            raise HealthVisionError("source_invalidated", "菜谱来源已变化，请重新读取", 410)
        dish.update(reference_recipe_media(doc["content"], dish["steps"], doc))
        if dish.get("cooking_minutes"):
            from yuxi.services.reference_recipe_presentation import generated_recipe_image

            dish.update(await generated_recipe_image(dish))
    from yuxi.services.recipe_translation_service import attach_chinese_display

    return await attach_chinese_display(session, result)


async def reference_plan_display(session, plan):
    """业务回执校验后附加展示内容，不改写快照及工具完成结果。"""
    import copy

    result = copy.deepcopy(plan)
    from yuxi.services.reference_recipe_presentation import attach_recipe_products

    current = await current_reference_items(result["purchase_items"])
    products = [
        {**item, "image_url": current[str(item["sku_id"])].get("image_url", "")} for item in result["purchase_items"]
    ]
    result["meals"] = [
        attach_recipe_products(await reference_meal_media(session, meal), products) for meal in result["meals"]
    ]
    return result


def products_cover_reference_dishes(meals, items):
    """每道展示菜至少关联一条本 Run 已核对的商城 SKU。"""
    return all(
        any(set(item["ingredient_refs"]) & set(dish["ingredients"]) for item in items)
        for meal in meals
        for dish in meal["dishes"]
    )


async def current_reference_catalog(category_codes):
    """补查超过四类时分批回查，并要求各批属于同一商城版本。"""
    items = []
    version = None
    for offset in range(0, len(category_codes), 4):
        batch = await current_catalog(category_codes=category_codes[offset : offset + 4])
        if version is not None and batch["version"] != version:
            raise HealthVisionError("catalog_changed", "核对商品时商城目录已变化，请重新读取", 503)
        version = batch["version"]
        items.extend(batch["items"])
    return {"items": items, "version": version}


async def current_reference_items(items):
    """发布、回读和采购时重新确认已选 SKU 的身份、上架状态及所需库存。"""
    categories = sorted({item["category_code"] for item in items})
    catalog = await current_reference_catalog(categories)
    current = {str(sku["sku_id"]): sku for sku in catalog["items"]}
    if any(
        (sku := current.get(str(item["sku_id"]))) is None
        or sku.get("sale_status") != "available"
        or int(sku.get("available_quantity", 0)) < item["quantity"]
        or input_fingerprint(product_facts(sku, include_description=item.get("facts_version") == 2))
        != item["facts_hash"]
        for item in items
    ):
        raise HealthVisionError("reference_product_changed", "参考餐单的商品或库存已变化，请重新安排", 410)
    return current


async def save_reference_plan(context, draft):
    """持久化参考结果与真实来源，不能写入正式方案或专业批准。"""
    draft = ReferencePlanDraft.model_validate(draft)
    async with pg_manager.get_async_session_context() as session:
        run, binding = await require_planner_run(session, context)
        current = await bound_reference_context(session, context.uid, binding)
        receipts = await tool_payloads(session, run, "read_reference_recipe")
        if {m.meal_type for m in draft.meals} != set(current["selection"]["meal_types"]):
            raise HealthVisionError("reference_meals_mismatch", "餐次须与用户明确选择一致", 422)
        documents = {}
        for receipt in receipts:
            fresh = await recipe_document(session, receipt["file_id"], receipt["chunk_id"])
            if not same_reference_document(fresh, receipt):
                raise HealthVisionError("source_invalidated", "菜谱正文已变化，请重新读取", 410)
            documents[(fresh["file_id"], fresh["chunk_id"])] = fresh
        meals = checked_reference_meals(draft, documents, current["members"])
        contexts = await tool_payloads(session, run, "get_reference_plan_context")
        if not contexts:
            raise HealthVisionError("reference_receipt_invalid", "请先读取当前成员和商城分类", 409)
        product_reads = await tool_payloads(session, run, "find_reference_products")
        if not product_reads or not draft.purchase_items:
            raise HealthVisionError("reference_product_required", "请先按商城分类取得可售食材，再生成参考餐单", 409)
        if any(g.reason == "catalog_unavailable" for g in draft.purchase_gaps) and (
            draft.purchase_items or not contexts[-1].get("commerce_notice")
        ):
            raise HealthVisionError(
                "reference_purchase_reason_invalid", "商品目录已成功读取，不能标记为接口不可用", 422
            )
        seen = {str(s["sku_id"]): s for read in product_reads for s in read.get("catalog", [])}
        gaps = checked_reference_gaps(draft.purchase_gaps, list(seen.values()))
        selected_codes = sorted(
            {seen[item.sku_id]["category_code"] for item in draft.purchase_items if item.sku_id in seen}
        )
        catalog = await current_reference_catalog(selected_codes) if selected_codes else {"items": []}
        by_sku = {str(s["sku_id"]): s for s in catalog["items"]}
        items = []
        restrictions = reference_member_restrictions(current["members"])
        for requested in draft.purchase_items:
            sku = by_sku.get(requested.sku_id)
            if (
                sku is None
                or requested.sku_id not in seen
                or sku.get("sale_status") != "available"
                or requested.quantity > int(sku.get("available_quantity", 0))
                or seen[requested.sku_id].get("facts_version") != 2
                or input_fingerprint(product_facts(sku, include_description=True))
                != seen[requested.sku_id]["facts_hash"]
            ):
                raise HealthVisionError("reference_product_changed", "所选商品或库存已变化，请重新读取目录", 409)
            if reference_restriction_conflict(reference_product_composition(sku), restrictions):
                raise HealthVisionError("reference_restriction_conflict", "所选商品含已明确填写的过敏或忌口成分", 422)
            identity = product_food(str(sku.get("product_name") or ""))
            if identity is None or any(ingredient_food(ref) != identity for ref in requested.ingredient_refs):
                raise HealthVisionError("reference_ingredient_mismatch", "原谱食材与所选商城商品不相符", 422)
            items.append({**reference_product(sku, requested.quantity), "ingredient_refs": requested.ingredient_refs})
        if not products_cover_reference_dishes(meals, items):
            raise HealthVisionError("reference_product_required", "菜品缺少已核对的商城食材，不能展示为已安排餐单", 409)
        from yuxi.services.reference_recipe_presentation import check_recipe_nutrition, recipe_pairing_summary

        check_recipe_nutrition(meals, items)
        snapshot = {
            "pairing_summary": recipe_pairing_summary(meals, draft),
            "scope": "daily_reference",
            "status": "reference_ready",
            "plan_date": current["selection"]["plan_date"],
            "professional_status": "not_reviewed",
            "nutrition_status": "not_calculated",
            "members": current["members"],
            "meals": meals,
            "purchase_items": items,
            "purchase_gaps": gaps,
            "purchase_status": "partial"
            if any(g["reason"] in {"no_match", "needs_confirmation"} for g in gaps)
            else "selected",
            "catalog_version": catalog.get("version"),
            "catalog_chain_version": REFERENCE_CATALOG_CHAIN_VERSION,
            "sources": current["sources"],
            "notice": "日常烹饪参考，未作专业审核；个人营养量尚未核算。",
        }
        ordered_draft = sorted(draft.meals, key=lambda m: ("breakfast", "lunch", "dinner").index(m.meal_type))
        for draft_meal, saved_meal in zip(ordered_draft, meals, strict=True):
            for requested, saved in zip(draft_meal.dishes, saved_meal["dishes"], strict=True):
                if requested.display_zh:
                    await save_chinese_display(session, saved, requested.display_zh.model_dump(), f"planner:{run.id}")
        pid = str(uuid5(NAMESPACE_URL, "reference-plan:" + run.id + ":" + input_fingerprint(snapshot)))
        row = await session.get(HealthInitialPlanPreview, pid)
        if row is None:
            row = HealthInitialPlanPreview(
                id=pid,
                actor_uid=context.uid,
                member_id=binding.member_id,
                conversation_id=binding.conversation_id,
                run_id=run.id,
                selection={"mode": "reference", **current["selection"]},
                snapshot=snapshot,
            )
            session.add(row)
        result = {"preview_id": pid, **snapshot}
    return result


def checked_reference_gaps(gaps, products):
    """逐项保留真实采购缺口，不把自备食材说成已购或家中已有。"""
    from yuxi.services.reference_recipe_matching import reference_ingredient_matches

    result = []
    for gap in gaps:
        status = reference_ingredient_matches((gap.ingredient,), products)[0]["status"]
        if gap.reason == "not_sold" and cooking_water_ingredient(gap.ingredient):
            result.append(gap.model_dump())
        elif gap.reason == "optional_not_selected" and optional_reference_ingredient(gap.ingredient):
            result.append(gap.model_dump())
        elif gap.reason in {"no_match", "needs_confirmation"} and status in {"missing_product", "needs_confirmation"}:
            # 两种原因都表示自备；最终标签由本轮实际核对结果决定。
            reason = "no_match" if status == "missing_product" else "needs_confirmation"
            detail = (
                "需自行准备：本轮已查询的商城商品中未找到匹配项。"
                if reason == "no_match"
                else "需自行准备并核对原谱品种、形态和用量：尚未确认对应商城商品。"
            )
            result.append({**gap.model_dump(), "reason": reason, "detail": detail})
        else:
            raise HealthVisionError("reference_purchase_reason_invalid", "食材缺口原因与本轮商品核对结果不一致", 422)
    return result


def cooking_water_ingredient(ingredient):
    """只豁免明确写作烹饪用水的原文，不把其他未售食材当作无需采购。"""
    return (
        re.fullmatch(
            r"[\d\s.,/()\-¼½¾⅓⅔⅛⅜⅝⅞]*(?:(?:c|cup|cups|ml|l|克|毫升|杯|碗)\s+)?"
            r"(?:(?:cold|warm|hot|boiling|drinking|清|凉|冷|温|热|饮用|开|沸)\s*)?"
            r"(?:water|水)(?:\s*适量)?",
            ingredient.strip(),
            flags=re.IGNORECASE,
        )
        is not None
    )


async def reference_result_in_session(session, run, binding, preview_id):
    """发布及历史读取均重验原 Run、当前档案和每份原文。"""
    current = await bound_reference_context(session, run.uid, binding)
    row = await session.get(HealthInitialPlanPreview, str(preview_id))
    if (
        row is None
        or row.actor_uid != run.uid
        or row.run_id != run.id
        or row.conversation_id != binding.conversation_id
        or row.member_id != binding.member_id
        or row.selection != current["selection"]
        or any(
            row.snapshot.get(key) != value
            for key, value in {
                "scope": "daily_reference",
                "status": "reference_ready",
                "professional_status": "not_reviewed",
                "nutrition_status": "not_calculated",
            }.items()
        )
    ):
        raise HealthVisionError("reference_receipt_invalid", "参考餐单回执不属于当前运行", 409)
    if row.snapshot.get("catalog_chain_version") != REFERENCE_CATALOG_CHAIN_VERSION:
        raise HealthVisionError("reference_chain_unverified", "旧餐单缺少商城分类和商品核对回执，请重新安排", 410)
    if row.snapshot["sources"] != current["sources"]:
        raise ReferencePlanSourceChanged("参考餐单的成员资料已变化", current["selection"])
    documents = []
    for meal in row.snapshot["meals"]:
        for dish in meal["dishes"]:
            try:
                fresh = await recipe_document(session, dish["file_id"], dish["chunk_id"])
            except HealthVisionError as error:
                if error.code != "reference_source_unavailable":
                    raise
                raise ReferencePlanSourceChanged(error.message, current["selection"]) from error
            if any(fresh[k] != dish["source"][k] for k in ("kb_id", "file_hash", "chunks_hash")):
                raise ReferencePlanSourceChanged("参考餐单的菜谱来源已变化", current["selection"])
            documents.append(fresh)
    restrictions = reference_member_restrictions(current["members"])
    for material in [
        *(doc["content"] for doc in documents),
        *(reference_product_composition(s) for s in row.snapshot["purchase_items"]),
    ]:
        if reference_restriction_conflict(material, restrictions):
            raise HealthVisionError("reference_restriction_conflict", "参考餐单含当前明确限制的食材或成分", 422)
    reference_restriction_conflict("", restrictions)
    await current_reference_items(row.snapshot["purchase_items"])
    return {"preview_id": row.id, **row.snapshot}


def reference_member_restrictions(members):
    """收集当前授权档案的硬限制，医嘱原文也不能作为可忽略偏好。"""
    return [
        str(value).strip()
        for member in members
        for value in [
            *(v for key in ("allergens", "avoidances", "intolerances") for v in (member.get(key) or [])),
            member.get("doctor_instructions") or "",
        ]
        if str(value).strip()
    ]


def unverified_reference_restrictions(restrictions):
    """只接受现有有限词汇的完整条目，不把自由句中的局部识别当作完整解释。"""
    supported = {"牛肉", "羊肉", "牛羊肉", "beef", "veal", "lamb", "mutton", "goat meat"}
    return [term for term in restrictions if " ".join(term.casefold().split()) not in supported]


def reference_product_composition(sku):
    """菜谱保存和历史重验使用相同的商品原始成分文本。"""
    return json.dumps(
        {k: sku.get(k) for k in ("product_name", "sku_name", "ingredients", "allergen_codes", "product_description")},
        ensure_ascii=False,
    )


def reference_restriction_conflict(content, restrictions):
    """整份原文的冲突优先拒绝，词汇不能完整解释的硬限制显式等待核实。"""
    content = content.casefold()
    restrictions = [term.casefold() for term in restrictions]
    # 完整英文肉名由下方整词规则核对；中文和未解释的自由文本保留字面命中。
    if any(
        term in content and (not term.isascii() or unverified_reference_restrictions([term])) for term in restrictions
    ):
        return True
    for names, english in (
        (("牛肉", "牛羊肉"), r"\b(?:beef|veal)\b"),
        (("羊肉", "牛羊肉"), r"\b(?:lamb|mutton|goat\s+meat)\b"),
    ):
        if any(any(name in term for name in names) or re.search(english, term) for term in restrictions):
            if any(name in content for name in names) or re.search(english, content):
                return True
    if unverified_reference_restrictions(restrictions):
        raise HealthVisionError(
            "reference_restriction_unverified",
            "当前硬限制尚无法完整核对菜谱及商品成分，请先核实；不会移除或忽略该限制",
            422,
        )
    return False


async def reference_answer_in_session(session, run, binding, answer):
    """模型最终只选择同 Run 的持久回执或提出补充问题。"""
    current = await bound_reference_context(session, run.uid, binding)
    if answer.candidate_meals:
        from yuxi.services.restricted_cooking_reference_service import build_restricted_cooking_candidates

        if answer.explanation or answer.knowledge_source_ids:
            raise HealthVisionError("planner_output_invalid", "待核对做法只接收当前来源编号", 422)
        receipts = await tool_payloads(session, run, "get_reference_plan_context")
        if not receipts:
            raise HealthVisionError("reference_receipt_invalid", "请先读取当前成员与做法资料", 409)
        return build_restricted_cooking_candidates(
            current, receipts[-1], [meal.model_dump(mode="json") for meal in answer.candidate_meals]
        )
    if answer.questions:
        return {"status": "needs_input", "questions": answer.questions}
    result = await reference_result_in_session(session, run, binding, answer.preview_id)
    receipts = await tool_payloads(session, run, "save_reference_meal_plan")
    if result not in receipts:
        raise HealthVisionError("reference_receipt_invalid", "当前运行缺少保存参考餐单的完成回执", 409)
    return result


async def validate_reference_publication(session, run, binding, content):
    """最终发布不允许模型改写来源、营养缺失或专业状态。"""
    from yuxi.services.health_meal_plan_types import PlannerAnswer

    payload = json.loads(content)
    answer = PlannerAnswer(
        preview_id=payload.get("preview_id"),
        questions=payload.get("questions", []),
        candidate_meals=payload.get("candidate_selection", []),
    )
    current = await reference_answer_in_session(session, run, binding, answer)
    if current != payload:
        raise HealthVisionError("source_invalidated", "参考餐单最终内容与当前回执不一致", 410)


async def validate_reference_tool_payload(session, context, binding, message):
    """恢复前核对真实工具操作归属、固定选择及当前来源。"""
    from yuxi.storage.postgres.models_business import AgentRun, Message, TOOL_AUDIT_MESSAGE_TYPE

    current = await bound_reference_context(session, context.uid, binding)
    name = message.name
    if name not in REFERENCE_TOOLS:
        raise HealthVisionError("source_invalidated", "参考餐单工具不属于固定模式", 410)
    rows = (
        await session.execute(
            select(Message, AgentRun)
            .join(AgentRun, AgentRun.id == Message.run_id)
            .where(
                Message.operation_id == message.tool_call_id,
                Message.conversation_id == binding.conversation_id,
                Message.message_type == TOOL_AUDIT_MESSAGE_TYPE,
                Message.role == "tool",
                AgentRun.conversation_id == binding.conversation_id,
                AgentRun.uid == context.uid,
                AgentRun.conversation_thread_id == context.thread_id,
                AgentRun.agent_slug == "health-meal-planner",
            )
        )
    ).all()
    if len(rows) != 1:
        raise HealthVisionError("source_invalidated", "参考餐单工具缺少唯一真实操作回执", 410)
    audit, original = rows[0]
    if (
        audit.execution_status != "completed"
        or audit.request_id != original.request_id
        or audit.content != message.content
        or (audit.extra_metadata or {}).get("tool_name") != name
        or (original.input_payload or {}).get("health_processing", {}).get("initial_selection_hash")
        != input_fingerprint(binding.initial_planner_selection)
    ):
        raise HealthVisionError("source_invalidated", "参考餐单工具回执或运行选择不符", 410)
    try:
        payload = json.loads(message.content)
        if name == "get_reference_plan_context":
            if any(payload[k] != current[k] for k in ("selection", "members", "sources")):
                raise HealthVisionError("source_invalidated", "参考成员上下文已变化", 410)
        elif name == "find_reference_products":
            if not isinstance(payload.get("category_codes"), list) or not isinstance(payload.get("catalog"), list):
                raise HealthVisionError("source_invalidated", "商城商品回执无法解析", 410)
        elif name == "search_reference_recipes":
            for item in payload["items"]:
                doc = await recipe_document(session, item["file_id"], item["chunk_id"])
                if any(doc[k] != item[k] for k in ("filename", "file_hash", "chunks_hash")):
                    raise HealthVisionError("source_invalidated", "参考检索来源已变化", 410)
        elif name == "read_reference_recipe":
            reads = payload.get("items") if isinstance(payload, dict) and "items" in payload else [payload]
            if (
                not isinstance(reads, list)
                or not 1 <= len(reads) <= 3
                or any(not isinstance(read, dict) for read in reads)
            ):
                raise HealthVisionError("source_invalidated", "菜谱原文回执无法解析", 410)
            for read in reads:
                fresh = await recipe_document(session, read["file_id"], read["chunk_id"])
                if not same_reference_document(fresh, read):
                    raise HealthVisionError("source_invalidated", "恢复时菜谱原文已变化", 410)
        elif payload != await reference_result_in_session(session, original, binding, payload["preview_id"]):
            raise HealthVisionError("source_invalidated", "参考餐单保存回执已变化", 410)
    except (KeyError, TypeError, ValueError):
        raise HealthVisionError("source_invalidated", "参考餐单工具回执无法解析", 410) from None


async def read_reference_plan_in_session(session, uid, preview_id):
    """只公开当前账号已完成 Run 的参考结果，沿用发布校验。"""
    row = await session.get(HealthInitialPlanPreview, str(preview_id))
    if row is None or row.actor_uid != uid or row.selection.get("mode") != "reference":
        raise HealthVisionError("not_found", "参考餐单不存在或不可访问", 404)
    if row.snapshot.get("catalog_chain_version") != REFERENCE_CATALOG_CHAIN_VERSION:
        raise HealthVisionError("reference_chain_unverified", "旧餐单缺少商城分类和商品核对回执，请重新安排", 410)
    from yuxi.services.health_consultation_service import require_consultation
    from yuxi.repositories.health_task_repository import HealthTaskRepository
    from yuxi.storage.postgres.models_business import AgentRun

    run = await session.get(AgentRun, row.run_id)
    if run is None or run.uid != uid or run.status != "completed":
        raise HealthVisionError("reference_not_completed", "参考餐单尚未完成发布", 409)
    await session.refresh(run, ["input_payload"])
    binding, _ = await require_consultation(
        session, uid, run.conversation_thread_id, expected=run.input_payload["health_processing"]
    )
    message = await HealthTaskRepository(session).final_message(run)
    await validate_reference_publication(session, run, binding, message.content)
    payload = json.loads(message.content)
    if payload.get("preview_id") != str(preview_id):
        raise HealthVisionError("reference_receipt_invalid", "该参考结果未被当前运行最终采用", 409)
    return run, payload


async def read_reference_plan(uid, preview_id):
    """私有读取不启动模型、任务或采购写入。"""
    async with pg_manager.get_async_session_context() as session:
        _, payload = await read_reference_plan_in_session(session, uid, preview_id)
        return await reference_plan_display(session, payload)


async def validate_reference_history(session, binding, *, allow_stale_results=False):
    """聊天历史只展示当前来源有效的权威完成结果。"""
    from yuxi.repositories.health_task_repository import HealthTaskRepository
    from yuxi.storage.postgres.models_business import AgentRun, Conversation
    from yuxi.services.health_consultation_service import require_consultation

    conversation = await session.get(Conversation, binding.conversation_id)
    runs = (
        await session.scalars(
            select(AgentRun).where(AgentRun.conversation_id == binding.conversation_id, AgentRun.status == "completed")
        )
    ).all()
    for run in runs:
        if (
            run.uid != binding.actor_uid
            or run.agent_slug != "health-meal-planner"
            or conversation is None
            or run.conversation_thread_id != conversation.thread_id
            or (run.input_payload or {}).get("health_processing", {}).get("initial_selection_hash")
            != input_fingerprint(binding.initial_planner_selection)
        ):
            raise HealthVisionError("source_invalidated", "参考历史所属运行与当前选择不符", 410)
        message = await HealthTaskRepository(session).final_message(run)
        await require_consultation(
            session, run.uid, run.conversation_thread_id, expected=run.input_payload["health_processing"]
        )
        preview_id = json.loads(message.content).get("preview_id")
        if preview_id:
            preview = await session.get(HealthInitialPlanPreview, str(preview_id))
            if (
                preview is None
                or preview.actor_uid != run.uid
                or preview.run_id != run.id
                or preview.conversation_id != binding.conversation_id
            ):
                raise HealthVisionError("reference_receipt_invalid", "参考历史餐单不属于当前运行", 409)
            if (preview.snapshot or {}).get("catalog_chain_version") != REFERENCE_CATALOG_CHAIN_VERSION:
                continue
        try:
            await validate_reference_publication(session, run, binding, message.content)
        except HealthVisionError as error:
            if (
                not preview_id
                or not allow_stale_results
                or error.code
                not in {
                    "reference_product_changed",
                    "reference_source_unavailable",
                    "source_invalidated",
                    "reference_restriction_conflict",
                    "reference_restriction_unverified",
                }
            ):
                raise


async def current_reference_plan(uid, family_id, plan_date):
    """只读当前家庭日期的最近已完成参考结果，不创建准备任务。"""
    from yuxi.storage.postgres.models_business import AgentRun
    from yuxi.repositories.health_task_repository import HealthTaskRepository

    async with pg_manager.get_async_session_context() as session:
        await FamilyService(session, uid).context(family_id)
        runs = (
            (
                await session.scalars(
                    select(AgentRun)
                    .join(HealthInitialPlanPreview, AgentRun.id == HealthInitialPlanPreview.run_id)
                    .where(
                        HealthInitialPlanPreview.actor_uid == uid,
                        AgentRun.status == "completed",
                        HealthInitialPlanPreview.selection["mode"].as_string() == "reference",
                        HealthInitialPlanPreview.selection["family_id"].as_string() == family_id,
                        HealthInitialPlanPreview.selection["plan_date"].as_string() == plan_date.isoformat(),
                    )
                    .order_by(AgentRun.finished_at.desc().nullslast(), AgentRun.created_at.desc(), AgentRun.id.desc())
                )
            )
            .unique()
            .all()
        )
        for run in runs:
            message = await HealthTaskRepository(session).final_message(run)
            selected = json.loads(message.content).get("preview_id")
            if selected:
                try:
                    _, payload = await read_reference_plan_in_session(session, uid, selected)
                except HealthVisionError as error:
                    if error.code in {
                        "reference_product_changed",
                        "reference_source_unavailable",
                        "source_invalidated",
                        "reference_restriction_conflict",
                        "reference_restriction_unverified",
                    }:
                        return {"status": "needs_regeneration", "scope": "daily_reference"}
                    if error.code != "reference_chain_unverified":
                        raise
                    continue
                return await reference_plan_display(session, payload)
        return {"status": "absent", "scope": "daily_reference"}


def select_reference_purchase_items(plan, meal_types):
    """只返回所选餐次实际引用的商品，保留原包装建议和可核对食材。"""
    ingredients = {
        ingredient
        for meal in plan["meals"]
        if meal["meal_type"] in meal_types
        for dish in meal["dishes"]
        for ingredient in dish["ingredients"]
    }
    return [
        {**item, "ingredient_refs": [ref for ref in item["ingredient_refs"] if ref in ingredients]}
        for item in plan["purchase_items"]
        if any(ref in ingredients for ref in item["ingredient_refs"])
    ]


async def validate_reference_purchase_source(session, source):
    """商城回源时核对实际完成结果、当前资料和选定商品事实。"""
    import time

    run, plan = await read_reference_plan_in_session(session, source["uid"], source["preview_id"])
    from datetime import date
    from yuxi.services.daily_meal_plan_service import current_row, require_current_reference_purchase

    daily = source.get("daily_plan")
    if not daily:
        family_id = plan["sources"]["family_id"]
        row = await current_row(session, source["uid"], family_id, date.fromisoformat(plan["plan_date"]))
        daily = {
            "family_id": family_id,
            "date": plan["plan_date"],
            "version": row.version if row else 0,
            "meal_types": [meal["meal_type"] for meal in plan["meals"]],
        }
    # 历史卡片和已签发证明也必须回读当前餐次，不能靠省略每日版本购买旧餐。
    await require_current_reference_purchase(session, source["uid"], daily, source["preview_id"], plan)
    selected_items = (
        select_reference_purchase_items(plan, source["daily_plan"]["meal_types"])
        if source.get("daily_plan")
        else plan["purchase_items"]
    )
    expected = [
        {"sku_id": str(i["sku_id"]), "quantity": i["quantity"], "facts_hash": i["facts_hash"]} for i in selected_items
    ]
    if (
        source["run_id"] != run.id
        or source["request_id"] != run.request_id
        or source["items"] != expected
        or source["source_hash"] != input_fingerprint(plan)
        or source["expires_at"] <= time.time()
    ):
        raise HealthVisionError("source_invalidated", "参考采购来源已变化或过期", 410)
    categories = sorted({item.get("category_code") for item in selected_items if item.get("category_code")})
    catalog = await current_catalog(
        category_codes=categories if all(item.get("category_code") for item in selected_items) else None
    )
    current = {str(s["sku_id"]): s for s in catalog["items"]}
    if any(
        i["sku_id"] not in current
        or input_fingerprint(product_facts(current[i["sku_id"]], include_description=i.get("facts_version") == 2))
        != i["facts_hash"]
        for i in selected_items
    ):
        raise HealthVisionError("reference_product_changed", "参考采购的商品身份或包装已变化", 410)
    await current_reference_items(selected_items)
    return {"available": True, "selection_mode": "reference", "items": expected}


async def publish_reference_purchase(uid, preview_id, daily_plan=None):
    """用户明确采购才发布固定规格和数量，重试使用同一来源和任务号。"""
    from datetime import date, datetime, time, timedelta
    from zoneinfo import ZoneInfo
    from yuxi.services.daily_commerce_service import commerce_request
    from yuxi.services.health_commerce_service import sign_commerce_source

    async with pg_manager.get_async_session_context() as session:
        run, plan = await read_reference_plan_in_session(session, uid, preview_id)
        selected_items = (
            select_reference_purchase_items(plan, daily_plan["meal_types"])
            if daily_plan is not None
            else plan["purchase_items"]
        )
        if not selected_items:
            raise HealthVisionError("reference_items_missing", "该参考餐单未选定可核对的采购商品", 409)
        items = [
            {"sku_id": str(i["sku_id"]), "quantity": i["quantity"], "facts_hash": i["facts_hash"]}
            for i in selected_items
        ]
        expiry = datetime.combine(
            date.fromisoformat(plan["plan_date"]) + timedelta(days=1), time.min, ZoneInfo("Asia/Shanghai")
        )
        source = {
            "kind": "reference_plan",
            "uid": uid,
            "preview_id": str(preview_id),
            "run_id": run.id,
            "request_id": run.request_id,
            "items": items,
            "source_hash": input_fingerprint(plan),
            "expires_at": int(expiry.timestamp()),
        }
        if daily_plan is not None:
            source["daily_plan"] = daily_plan
        await validate_reference_purchase_source(session, source)
    task = str(
        uuid5(
            NAMESPACE_URL,
            "reference-purchase:" + str(preview_id) + (":" + input_fingerprint(daily_plan) if daily_plan else ""),
        )
    )
    payload = {
        "agent_task_id": task,
        "family_ref": "reference:" + str(preview_id),
        "user_ref": "uid:" + uid,
        "menu_version_ref": "reference:" + str(preview_id),
        "catalog_version": plan["catalog_version"],
        "ingredient_requirements": [],
        "items": [{"sku_id": i["sku_id"], "quantity": i["quantity"]} for i in items],
        "expires_at": expiry.isoformat(),
        "nutrition_validation": {
            "status": "reference_only",
            "validation_id": str(preview_id),
            "rules_version": "",
            "summary": "日常参考商品选择，未作营养或专业适用性审核",
        },
        "agent_source_proof": sign_commerce_source(source),
    }
    package = await commerce_request("POST", "/api/v1/integration/ai/recommendation-packages", payload, request_id=task)
    return {"preview_id": str(preview_id), "package": package}

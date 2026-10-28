"""以当前授权档案、知识原文和同 Run 回执保存日常参考餐单。"""

import hashlib
import json
import re
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import case, or_, select

from yuxi.repositories.family_repository import FamilyRepository
from yuxi.repositories.health_vision_repository import HealthVisionRepository
from yuxi.repositories.tool_message_audit_repository import ToolMessageAuditRepository
from yuxi.services.daily_commerce_service import current_catalog
from yuxi.services.family_service import FamilyService, authorized_fields
from yuxi.services.health_family_kb_service import configured_health_kb_ids, search_family_nutrition_knowledge
from yuxi.services.health_meal_plan_service import require_planner_run
from yuxi.services.health_nutrition_service import input_fingerprint
from yuxi.services.health_vision_service import health_vision_service
from yuxi.services.health_vision_types import HealthVisionError, NUTRIENTS
from yuxi.services.miniapp_profile_types import miniapp_onboarding_ready
from yuxi.services.reference_meal_plan_types import REFERENCE_TOOLS, ReferencePlanDraft, ReferenceSelection
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_health import HealthInitialPlanPreview
from yuxi.storage.postgres.models_knowledge import KnowledgeChunk, KnowledgeFile


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
        raise HealthVisionError("source_invalidated", "成员资料或知识库绑定已更新，请重新生成参考餐单", 410)
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


def reference_product(sku, quantity=1):
    """只返回商城事实，配料不完整保持明确提示。"""
    return {
        **product_facts(sku),
        "product_description": (sku.get("product_description") or "")[:4000],
        "description_truncated": len(sku.get("product_description") or "") > 4000,
        "quantity": quantity,
        "price_cent": sku.get("price_cent"),
        "available_quantity": sku.get("available_quantity"),
        "facts_version": 2,
        "facts_hash": input_fingerprint(product_facts(sku, include_description=True)),
        "composition_notice": "商品配料及过敏原资料未完成核对，请结合包装信息确认。"
        if not sku.get("ingredients") or sku.get("data_completeness") != "complete"
        else "商品资料未作个人过敏适用性或专业营养审核，请核对包装信息。",
    }


async def get_reference_context(context):
    """向 Agent 提供当前就餐范围及真实可售规格，不开放专业批准。"""
    async with pg_manager.get_async_session_context() as session:
        _, binding = await require_planner_run(session, context)
        current = await bound_reference_context(session, context.uid, binding)
    notice = None
    try:
        catalog = await current_catalog()
    except HealthVisionError as error:
        if error.code not in {"commerce_not_configured", "commerce_unavailable", "catalog_invalid", "catalog_changed"}:
            raise
        catalog = {"items": []}
        notice = "商品目录暂不可用，仍可生成参考餐单；采购建议暂不提供。"
    current_plan = None
    if current["selection"].get("daily_base_version") is not None:
        from datetime import date
        from yuxi.services.daily_meal_plan_service import read_current_plan

        current_plan = await read_current_plan(
            context.uid, current["selection"]["family_id"], date.fromisoformat(current["selection"]["plan_date"])
        )
        if current_plan["version"] != current["selection"]["daily_base_version"]:
            raise HealthVisionError("daily_plan_version_changed", "今日计划已有更新，请重新读取后调整", 409)
    return {
        "scope": "daily_reference",
        **current,
        "current_daily_plan": current_plan,
        "catalog": [
            reference_product(s)
            for s in catalog["items"]
            if s.get("sale_status") == "available" and int(s.get("available_quantity", 0)) > 0
        ],
        "commerce_notice": notice,
        "boundary": "日常烹饪参考，未作专业审核；未核算营养和个人达标结论。",
    }


async def search_reference_recipes(context, query):
    """固定菜谱库的当前检索结果仅作为后续打开原文的目录。"""
    if not isinstance(query, str) or not 1 <= len(query.strip()) <= 80:
        raise HealthVisionError("knowledge_query_invalid", "请使用简短菜名或食材关键词", 422)
    async with pg_manager.get_async_session_context() as session:
        _, binding = await require_planner_run(session, context)
        await bound_reference_context(session, context.uid, binding)
        terms = [
            term
            for term in re.findall(r"[\w\u4e00-\u9fff]+", query)
            if term not in {"简单", "早餐", "午餐", "晚餐", "制作方法", "做法", "烹饪菜谱", "家常"}
        ]
        # 精确菜名优先，避免广义营养向量结果挤掉库中已有的烹饪步骤。
        matches = (
            (
                await session.execute(
                    select(KnowledgeFile, KnowledgeChunk)
                    .join(KnowledgeChunk, KnowledgeChunk.file_id == KnowledgeFile.file_id)
                    .where(
                        KnowledgeFile.kb_id.in_(configured_health_kb_ids("health-meal-planner")),
                        KnowledgeChunk.kb_id == KnowledgeFile.kb_id,
                        KnowledgeFile.is_folder.is_(False),
                        KnowledgeFile.status == "indexed",
                        KnowledgeChunk.chunk_index == 0,
                        or_(*(KnowledgeFile.filename.contains(term, autoescape=True) for term in terms)),
                    )
                    .order_by(
                        case(
                            (KnowledgeFile.filename.startswith("烹饪菜谱"), 0),
                            (KnowledgeFile.filename.startswith("USDA家庭菜谱"), 1),
                            else_=2,
                        ),
                        KnowledgeFile.filename,
                    )
                    .limit(4)
                )
            ).all()
            if terms
            else []
        )
    material = (
        {
            "status": "ok",
            "sources": [
                {"file_id": file.file_id, "chunk_id": chunk.chunk_id, "content": chunk.content[:1200]}
                for file, chunk in matches
            ],
        }
        if matches
        else await search_family_nutrition_knowledge(context, query)
    )
    async with pg_manager.get_async_session_context() as session:
        _, binding = await require_planner_run(session, context)
        await bound_reference_context(session, context.uid, binding)
        items = []
        for hit in material["sources"]:
            doc = await recipe_document(session, hit["file_id"], hit["chunk_id"])
            items.append(
                {
                    "file_id": doc["file_id"],
                    "chunk_id": doc["chunk_id"],
                    "filename": doc["filename"],
                    "excerpt": hit["content"],
                    "file_hash": doc["file_hash"],
                    "chunks_hash": doc["chunks_hash"],
                }
            )
    return {"scope": "reference_recipe_search", "status": material["status"], "items": items}


async def recipe_document(session, file_id, chunk_id):
    """从当前固定库的已索引分片读取有界正文，保留版本摘要。"""
    kb_ids = configured_health_kb_ids("health-meal-planner")
    file = await session.scalar(
        select(KnowledgeFile)
        .where(KnowledgeFile.file_id == file_id, KnowledgeFile.kb_id.in_(kb_ids))
        .with_for_update(read=True)
    )
    if file is None or file.is_folder or file.status != "indexed":
        raise HealthVisionError("reference_source_unavailable", "菜谱原文已移除或尚未完成索引", 410)
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
    if not chunks:
        raise HealthVisionError("reference_source_unavailable", "菜谱没有可核对正文", 410)
    index = next((i for i, c in enumerate(chunks) if c.chunk_id == chunk_id), None)
    if index is None:
        raise HealthVisionError("reference_source_unavailable", "检索命中的菜谱分片已移除", 410)
    # 从命中位置读取相邻正文，长文件后半部的菜谱仍能打开。
    text = "\n".join(
        [
            *([chunks[index - 1].content[-3000:]] if index else []),
            chunks[index].content[:12000],
            *([chunks[index + 1].content[:3000]] if index + 1 < len(chunks) else []),
        ]
    )
    return {
        "scope": "reference_recipe",
        "file_id": file.file_id,
        "kb_id": file.kb_id,
        "chunk_id": chunk_id,
        "filename": file.filename,
        "file_hash": file.content_hash,
        "chunks_hash": input_fingerprint([(c.chunk_id, c.content) for c in chunks]),
        "content": text,
    }


async def tool_payloads(session, run, tool_name):
    """只接受当前 Run 已完成且归属一致的工具审计。"""
    values = []
    for audit in await ToolMessageAuditRepository(session).list_for_run(run.id):
        if (audit.extra_metadata or {}).get("tool_name") != tool_name or audit.execution_status != "completed":
            continue
        if audit.request_id != run.request_id or audit.conversation_id != run.conversation_id:
            raise HealthVisionError("reference_receipt_invalid", "参考资料回执归属不一致", 409)
        values.append(json.loads(audit.content))
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
        return await recipe_document(session, file_id, chunk_id)


def checked_reference_meals(draft, documents, members):
    """核对原文引句及明确限制，数值和专业状态由服务端固定。"""
    result = []
    restrictions = [
        str(v).strip()
        for m in members
        for key in ("allergens", "avoidances", "intolerances")
        for v in (m.get(key) or [])
        if str(v).strip()
    ]
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
            if any(not q.strip() or q not in doc["content"] for q in quotes):
                raise HealthVisionError("reference_quote_invalid", "菜名、食材或步骤缺少可核对的原文", 422)
            if any(term.casefold() in doc["content"].casefold() for term in restrictions):
                raise HealthVisionError("reference_restriction_conflict", "所选菜谱含已明确填写的过敏或忌口食材", 422)
            dishes.append(
                {
                    **dish.model_dump(mode="json"),
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


async def save_reference_plan(context, draft):
    """持久化参考结果与真实来源，不能写入正式方案或专业批准。"""
    draft = ReferencePlanDraft.model_validate(draft)
    catalog = await current_catalog() if draft.purchase_items else {"items": []}
    by_sku = {str(s["sku_id"]): s for s in catalog["items"]}
    async with pg_manager.get_async_session_context() as session:
        run, binding = await require_planner_run(session, context)
        current = await bound_reference_context(session, context.uid, binding)
        receipts = await tool_payloads(session, run, "read_reference_recipe")
        if {m.meal_type for m in draft.meals} != set(current["selection"]["meal_types"]):
            raise HealthVisionError("reference_meals_mismatch", "餐次须与用户明确选择一致", 422)
        documents = {}
        for receipt in receipts:
            fresh = await recipe_document(session, receipt["file_id"], receipt["chunk_id"])
            if fresh != receipt:
                raise HealthVisionError("source_invalidated", "菜谱正文已变化，请重新读取", 410)
            documents[(fresh["file_id"], fresh["chunk_id"])] = fresh
        meals = checked_reference_meals(draft, documents, current["members"])
        contexts = await tool_payloads(session, run, "get_reference_plan_context")
        if not contexts:
            raise HealthVisionError("reference_receipt_invalid", "请先读取当前成员和商品目录再作采购选择", 409)
        if any(g.reason == "catalog_unavailable" for g in draft.purchase_gaps) and (
            draft.purchase_items or not contexts[-1].get("commerce_notice")
        ):
            raise HealthVisionError(
                "reference_purchase_reason_invalid", "商品目录已成功读取，不能标记为接口不可用", 422
            )
        seen = {str(s["sku_id"]): s for c in contexts for s in c.get("catalog", [])}
        items = []
        restrictions = [
            str(v).strip().casefold()
            for member in current["members"]
            for key in ("allergens", "avoidances", "intolerances")
            for v in (member.get(key) or [])
            if str(v).strip()
        ]
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
            composition = json.dumps(
                {
                    k: sku.get(k)
                    for k in ("product_name", "sku_name", "ingredients", "allergen_codes", "product_description")
                },
                ensure_ascii=False,
            ).casefold()
            if any(term in composition for term in restrictions):
                raise HealthVisionError("reference_restriction_conflict", "所选商品含已明确填写的过敏或忌口成分", 422)
            items.append({**reference_product(sku, requested.quantity), "ingredient_refs": requested.ingredient_refs})
        snapshot = {
            "scope": "daily_reference",
            "status": "reference_ready",
            "plan_date": current["selection"]["plan_date"],
            "professional_status": "not_reviewed",
            "nutrition_status": "not_calculated",
            "members": current["members"],
            "meals": meals,
            "purchase_items": items,
            "purchase_gaps": [gap.model_dump() for gap in draft.purchase_gaps],
            "purchase_status": "partial" if items and draft.purchase_gaps else "selected" if items else "unselected",
            "catalog_version": catalog.get("version"),
            "sources": current["sources"],
            "notice": "日常烹饪参考，未作专业审核；个人营养量尚未核算。",
        }
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
        return {"preview_id": pid, **snapshot}


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
    if row.snapshot["sources"] != current["sources"]:
        raise HealthVisionError("source_invalidated", "参考餐单的成员资料已变化", 410)
    for meal in row.snapshot["meals"]:
        for dish in meal["dishes"]:
            fresh = await recipe_document(session, dish["file_id"], dish["chunk_id"])
            if any(fresh[k] != dish["source"][k] for k in ("kb_id", "file_hash", "chunks_hash")):
                raise HealthVisionError("source_invalidated", "参考餐单的菜谱来源已变化", 410)
    return {"preview_id": row.id, **row.snapshot}


async def reference_answer_in_session(session, run, binding, answer):
    """模型最终只选择同 Run 的持久回执或提出补充问题。"""
    await bound_reference_context(session, run.uid, binding)
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
    answer = PlannerAnswer(preview_id=payload.get("preview_id"), questions=payload.get("questions", []))
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
        elif name == "search_reference_recipes":
            for item in payload["items"]:
                doc = await recipe_document(session, item["file_id"], item["chunk_id"])
                if any(doc[k] != item[k] for k in ("filename", "file_hash", "chunks_hash")):
                    raise HealthVisionError("source_invalidated", "参考检索来源已变化", 410)
        elif name == "read_reference_recipe":
            if payload != await recipe_document(session, payload["file_id"], payload["chunk_id"]):
                raise HealthVisionError("source_invalidated", "恢复时菜谱原文已变化", 410)
        elif payload != await reference_result_in_session(session, original, binding, payload["preview_id"]):
            raise HealthVisionError("source_invalidated", "参考餐单保存回执已变化", 410)
    except (KeyError, TypeError, ValueError):
        raise HealthVisionError("source_invalidated", "参考餐单工具回执无法解析", 410) from None


async def read_reference_plan_in_session(session, uid, preview_id):
    """只公开当前账号已完成 Run 的参考结果，沿用发布校验。"""
    from yuxi.services.health_consultation_service import require_consultation
    from yuxi.repositories.health_task_repository import HealthTaskRepository
    from yuxi.storage.postgres.models_business import AgentRun

    row = await session.get(HealthInitialPlanPreview, str(preview_id))
    if row is None or row.actor_uid != uid or row.selection.get("mode") != "reference":
        raise HealthVisionError("not_found", "参考餐单不存在或不可访问", 404)
    run = await session.get(AgentRun, row.run_id)
    if run is None or run.uid != uid or run.status != "completed":
        raise HealthVisionError("reference_not_completed", "参考餐单尚未完成发布", 409)
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
        return payload


async def validate_reference_history(session, binding):
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
        await validate_reference_publication(session, run, binding, message.content)


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
                _, payload = await read_reference_plan_in_session(session, uid, selected)
                return payload
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
    catalog = await current_catalog()
    current = {str(s["sku_id"]): s for s in catalog["items"]}
    if any(
        i["sku_id"] not in current
        or input_fingerprint(product_facts(current[i["sku_id"]], include_description=i.get("facts_version") == 2))
        != i["facts_hash"]
        for i in selected_items
    ):
        raise HealthVisionError("reference_product_changed", "参考采购的商品身份或包装已变化", 410)
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

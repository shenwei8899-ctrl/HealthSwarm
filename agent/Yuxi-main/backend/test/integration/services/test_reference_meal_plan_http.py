"""真实 TCP/PG 验证参考餐单；商城和精确对象字节接口为合成边界，不代表 Worker。"""

# ruff: noqa: F401,F811 -- 复用真实HTTP及隔离schema fixture。
import json
import hashlib
from copy import deepcopy
from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage, ToolMessage
from langgraph.graph import StateGraph, MessagesState, START, END
from langgraph.prebuilt import ToolNode
from sqlalchemy import func, select, text

from test.integration.services.test_onboarding_preparation_http import (
    family_profile_http,
    ensure_live_api_schema,
    cleanup_test_sandboxes,
    cleanup_test_knowledge_resources,
    isolate_delivery,
    input_for,
    POLICY,
)
from yuxi.agents.base import BaseContext
from yuxi.repositories.health_consultation_repository import HEALTH_AGENT_BACKENDS
from yuxi.repositories.skill_repository import SkillRepository
from yuxi.services import reference_meal_plan_service as service, health_task_service
from yuxi.services.health_consultation_service import require_consultation, require_consultation_attempt
from yuxi.services.health_initial_planner_service import validate_initial_planner_publication, preview_initial_for_run
from yuxi.services.health_meal_plan_service import planner_final_result
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_business import Agent, AgentRun, AgentRunRequest, Message, FamilyMember
from yuxi.storage.postgres.models_health import (
    HealthDailyMealPlan,
    HealthFamilyProfileLink,
    HealthInitialPlanPreview,
    HealthMealPlan,
    HealthProfessionalReview,
    HealthPurchasePreview,
    HealthRuleSnapshot,
    RecipeVersion,
)
from yuxi.storage.postgres.models_knowledge import KnowledgeBase, KnowledgeFile, KnowledgeChunk
from yuxi.utils.datetime_utils import utc_now_naive

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]
ROOT = "/api/health/v1"
TEXT = "# 清粥\n\n## 食材\n- 大米100克\n\n## 做法\n1. 加水煮熟\n\n## 份量\n原食谱供两人食用\n"
SKU = {
    "sku_id": "sku-rice",
    "product_id": "rice",
    "product_name": "大米",
    "sku_name": "一袋",
    "net_content": {"value": "500", "unit": "g"},
    "price_cent": 500,
    "available_quantity": 5,
    "sale_status": "available",
    "ingredients": [],
    "allergen_codes": [],
    "data_completeness": "partial",
    "category_code": "grain",
}


async def setup_reference(
    fixture, monkeypatch, *, allergens=None, avoidances=None, intolerances=None, doctor_instructions=None
):
    """正式建档和同意接口，无正式规则或菜谱，绑定当前知识文件。"""
    client, sessions, users = fixture
    monkeypatch.setenv("HEALTH_RECIPE_KB_ID", "synthetic-reference-kb")
    monkeypatch.setenv("HEALTH_COMMERCE_SOURCE_SECRET", "synthetic-reference-source-secret-at-least-32-chars")

    async def skill(self, slug):
        return SimpleNamespace(source_type="builtin", enabled=True)

    async def runtime(*args):
        return []

    async def catalog(category_codes=None):
        """只替代外部商城，实际分类与保存仍走对应服务。"""
        assert category_codes in (None, ["grain"])
        return {"version": "synthetic-v1", "items": [deepcopy(SKU)]}

    async def categories(method, path, payload=None, **kwargs):
        """合成分类响应不替代商品读取及其审计回执。"""
        assert method == "GET" and path == "/api/v1/integration/ai/catalog/categories"
        return {
            "catalog_version": "synthetic-v1",
            "items": [{"category_code": "grain", "name": "米面", "product_count": 1}],
        }

    objects = {"reference-file.md": TEXT.encode()}
    sessions.reference_objects = objects

    async def download(bucket, name):
        """精确字节替代对象网络；文件哈希及PG分片仍由真实服务校验。"""
        assert bucket == "knowledgebase"
        if name not in objects:
            raise FileNotFoundError(name)
        return objects[name]

    monkeypatch.setattr(SkillRepository, "get_by_slug", skill)
    monkeypatch.setattr(health_task_service, "health_task_runtime_blockers", runtime)
    monkeypatch.setattr(service, "current_catalog", catalog)
    monkeypatch.setattr(service, "commerce_request", categories)
    monkeypatch.setattr("yuxi.storage.minio.get_minio_client", lambda: SimpleNamespace(adownload_file=download))
    family, _, body, headers = await input_for(client, users["self"])
    body.pop("processing_consents")
    if allergens:
        body["members"][0]["dietary"].update(allergyStatus="set", allergies=allergens)
    if avoidances:
        body["members"][0]["dietary"].update(avoidanceStatus="set", avoidances=avoidances)
    if intolerances:
        body["members"][0]["dietary"].update(intoleranceStatus="set", intolerances=intolerances)
    if doctor_instructions is not None:
        body["members"][0]["dietary"].update(doctorStatus="set", clinicianGuidance=doctor_instructions)
    saved = await client.post(f"/api/family/{family['id']}/miniapp-profile", json=body, headers=headers)
    assert saved.status_code == 200, saved.text
    sessions.reference_profile_input = deepcopy(body)
    sessions.reference_profile_input["family_version"] = saved.json()["familyVersion"]
    sessions.reference_profile_input["members"][0]["version"] = saved.json()["members"][0]["version"]
    actor = body["members"][0]["member_id"]
    consent_key = str(uuid4())
    opened = await client.post(
        f"/api/family/{family['id']}/miniapp-profile",
        headers={**users["self"], "Idempotency-Key": consent_key},
        json={
            "action": "start_analysis",
            "client_request_id": consent_key,
            "member_id": actor,
            "expected_version": 2,
            "accepted": True,
            "purpose": "meal_plan",
            **POLICY,
        },
    )
    assert opened.status_code == 200, opened.text
    async with sessions.begin() as db:
        connection = await db.connection()
        await connection.run_sync(
            lambda conn: KnowledgeBase.metadata.create_all(
                conn, tables=[KnowledgeBase.__table__, KnowledgeFile.__table__, KnowledgeChunk.__table__]
            )
        )
        link = await db.scalar(select(HealthFamilyProfileLink).where(HealthFamilyProfileLink.source_member_id == actor))
        mid = link.member_id
        for slug in ("health-meal-planner", "health-consultation"):
            db.add(
                Agent(
                    slug=slug,
                    backend_id=HEALTH_AGENT_BACKENDS[slug],
                    name="合成参考角色",
                    share_config={
                        "version": 2,
                        "read_scope": {"access_level": "global", "department_ids": [], "user_uids": []},
                        "manage_scope": None,
                    },
                )
            )
        db.add(KnowledgeBase(kb_id="synthetic-reference-kb", name="合成食谱", kb_type="milvus"))
        await db.flush()
        db.add(
            KnowledgeFile(
                file_id="reference-file",
                kb_id="synthetic-reference-kb",
                filename="烹饪菜谱｜清粥.md",
                status="indexed",
                content_hash=hashlib.sha256(TEXT.encode()).hexdigest(),
                minio_url="minio://knowledgebase/reference-file.md",
            )
        )
        await db.flush()
        db.add(
            KnowledgeChunk(
                chunk_id="reference-chunk",
                file_id="reference-file",
                kb_id="synthetic-reference-kb",
                chunk_index=0,
                content=TEXT,
            )
        )
    choice = {
        "mode": "reference",
        "family_id": family["id"],
        "plan_date": "2099-01-01",
        "participant_ids": [actor],
        "meal_types": ["breakfast"],
    }
    return client, sessions, users, mid, actor, choice


async def replace_source(current, content):
    """更新本合成对象和真实PG的当前来源版本，不把变字节负控伪装成合法变源。"""
    current[1].reference_objects["reference-file.md"] = content.encode()
    async with current[1].begin() as db:
        file = await db.scalar(select(KnowledgeFile).where(KnowledgeFile.file_id == "reference-file"))
        file.content_hash = hashlib.sha256(content.encode()).hexdigest()
        chunk = await db.scalar(select(KnowledgeChunk).where(KnowledgeChunk.file_id == file.file_id))
        chunk.content = content


async def add_recipe(
    current, file_id, filename, content, *, kb_id="synthetic-reference-kb", status="indexed", folder=False
):
    """为目录边界准备真实PG文件与分片，并保存明确的合成对象字节。"""
    current[1].reference_objects[file_id + ".md"] = content.encode()
    async with current[1].begin() as db:
        db.add(
            KnowledgeFile(
                file_id=file_id,
                kb_id=kb_id,
                filename=filename,
                status=status,
                is_folder=folder,
                content_hash=hashlib.sha256(content.encode()).hexdigest(),
                minio_url=f"minio://knowledgebase/{file_id}.md",
            )
        )
        await db.flush()
        db.add(
            KnowledgeChunk(
                chunk_id=file_id + "-chunk",
                file_id=file_id,
                kb_id=kb_id,
                chunk_index=0,
                content=content,
            )
        )


async def bind_reference(current, **changes):
    """通过统一任务HTTP入口创建真实固定选择线程。"""
    client, _, users, mid, _, choice = current
    key = str(uuid4())
    payload = {"task_type": "reference_meal_preview", "client_request_id": key, "selection": {**choice, **changes}}
    response = await client.post(
        f"{ROOT}/members/{mid}/task-entries", json=payload, headers={**users["self"], "Idempotency-Key": key}
    )
    return response


async def running_context(current, thread, *, read_context=True, read_products=True):
    """合成执行Owner供真实服务边界测试，不声称真实worker证据。"""
    _, sessions, _, _, _, _ = current
    rid, qid = str(uuid4()), str(uuid4())
    async with sessions.begin() as db:
        binding, processing = await require_consultation(db, "self", thread)
        incoming = Message(conversation_id=binding.conversation_id, role="user", content="生成早餐", request_id=qid)
        db.add(incoming)
        await db.flush()
        db.add(
            AgentRun(
                id=rid,
                request_id=qid,
                uid="self",
                agent_slug="health-meal-planner",
                conversation_id=binding.conversation_id,
                conversation_thread_id=thread,
                runtime_scope_id=thread,
                status="running",
                worker_id="synthetic-reference",
                lease_expires_at=utc_now_naive() + timedelta(minutes=10),
                input_message_id=incoming.id,
                input_payload={"health_processing": processing},
            )
        )
        await db.flush()
        db.add(
            AgentRunRequest(
                request_id=qid,
                uid="self",
                agent_slug="health-meal-planner",
                conversation_thread_id=thread,
                status="dispatched",
                input_message_id=incoming.id,
                dispatched_run_id=rid,
            )
        )
    context = BaseContext(
        uid="self",
        thread_id=thread,
        request_id=qid,
        run_id=rid,
        worker_id="synthetic-reference",
        model=processing["model"],
    )
    if read_context:
        await receipt(current[1], context, "get_reference_plan_context", await service.get_reference_context(context))
    if read_products:
        await receipt(
            current[1], context, "find_reference_products", await service.find_reference_products(context, ["grain"])
        )
    return context


async def receipt(sessions, context, name, payload):
    """写入合成已完成工具审计，测试服务消费的实际持久化边界。"""
    op = str(uuid4())
    content = json.dumps(payload, ensure_ascii=False)
    async with sessions.begin() as db:
        run = await db.get(AgentRun, context.run_id)
        db.add(
            Message(
                conversation_id=run.conversation_id,
                role="tool",
                message_type="tool_audit",
                content=content,
                run_id=run.id,
                request_id=run.request_id,
                operation_id=op,
                execution_status="completed",
                delivery_status="complete",
                extra_metadata={"tool_name": name, "tool_call_id": op},
            )
        )
    return ToolMessage(name=name, tool_call_id=op, content=content)


async def grounded_plan(current, context, *, quantity=1, meal_type="breakfast", meal_types=None, read_selection=False):
    """真实服务读取PG原文并保存，采购只选择已见的合成SKU。"""
    sessions = current[1]
    initial = await receipt(
        sessions, context, "get_reference_plan_context", await service.get_reference_context(context)
    )
    products = await receipt(
        sessions, context, "find_reference_products", await service.find_reference_products(context, ["grain"])
    )
    searched = await receipt(
        sessions, context, "search_reference_recipes", await service.search_reference_recipes(context, "清粥")
    )
    doc = await service.read_reference_recipe(context, "reference-file", "reference-chunk")
    opened = await receipt(sessions, context, "read_reference_recipe", doc)
    draft = {
        "meals": [
            {
                "meal_type": meal_type,
                "dishes": [
                    {
                        "file_id": "reference-file",
                        "chunk_id": "reference-chunk",
                        "name": "清粥",
                        "ingredients": ["大米100克"],
                        "steps": ["加水煮熟"],
                        "portion_quote": "原食谱供两人食用",
                    }
                ],
            }
        ],
        "purchase_items": [{"sku_id": "sku-rice", "quantity": quantity, "ingredient_refs": ["大米100克"]}],
        "purchase_gaps": [],
    }
    if meal_types:
        draft["meals"] = [{**draft["meals"][0], "meal_type": item} for item in meal_types]
    arguments = draft
    if read_selection:
        arguments = {
            "read_selection": {
                "use_read_recipes": True,
                "auto_purchase_matches": True,
                "meals": [
                    {
                        "meal_type": meal["meal_type"],
                        "dishes": [{"file_id": "reference-file", "chunk_id": "reference-chunk"}],
                    }
                    for meal in draft["meals"]
                ],
                "purchase_items": [{"sku_id": "sku-rice", "quantity": quantity}],
            }
        }
    from yuxi.agents.toolkits.meal_planner import save_reference_meal_plan

    graph = StateGraph(MessagesState, context_schema=BaseContext)
    graph.add_node("tools", ToolNode([save_reference_meal_plan], handle_tool_errors=False))
    graph.add_edge(START, "tools")
    graph.add_edge("tools", END)
    output = await graph.compile().ainvoke(
        {
            "messages": [
                AIMessage(
                    content="",
                    tool_calls=[
                        {"name": "save_reference_meal_plan", "args": arguments, "id": str(uuid4()), "type": "tool_call"}
                    ],
                )
            ]
        },
        context=context,
    )
    plan = json.loads(output["messages"][-1].content)
    saved = await receipt(sessions, context, "save_reference_meal_plan", plan)
    await require_consultation_attempt(context, [initial, products, searched, opened, saved])
    return plan, opened, draft


async def test_read_selection_three_meals_and_dinner_replacement_preserve_other_sources(
    family_profile_http, monkeypatch
):
    """真实ToolNode选菜、TCP/PG发布三餐，只换晚餐不改早餐午餐，不代表Worker。"""
    current = await setup_reference(family_profile_http, monkeypatch)
    selected = ["breakfast", "lunch", "dinner"]
    bound = await bind_reference(current, daily_base_version=0, meal_types=selected)
    assert bound.status_code == 200, bound.text
    context = await running_context(current, bound.json()["thread_id"])
    plan, _, _ = await grounded_plan(current, context, meal_types=selected, read_selection=True)
    await complete(current, context, plan)
    choice = current[-1]
    path = f"/api/family/{choice['family_id']}/daily-meal-plans/{choice['plan_date']}"
    first = await current[0].get(path, headers=current[2]["self"])
    assert first.status_code == 200 and first.json()["version"] == 1, first.text
    before = {meal["meal_type"]: meal for meal in first.json()["meals"]}
    assert set(before) == set(selected)
    assert all(meal["meal"]["dishes"][0]["ingredients"] == ["大米100克"] for meal in before.values())
    changed = await bind_reference(current, daily_base_version=1, meal_types=["dinner"])
    replacement_context = await running_context(current, changed.json()["thread_id"])
    replacement, _, _ = await grounded_plan(current, replacement_context, meal_type="dinner", read_selection=True)
    await complete(current, replacement_context, replacement)
    second = await current[0].get(path, headers=current[2]["self"])
    assert second.status_code == 200 and second.json()["version"] == 2, second.text
    after = {meal["meal_type"]: meal for meal in second.json()["meals"]}
    assert after["breakfast"] == before["breakfast"] and after["lunch"] == before["lunch"]
    assert after["dinner"]["source"]["id"] == replacement["preview_id"] != plan["preview_id"]
    async with current[1]() as db:
        daily = await db.scalar(select(HealthDailyMealPlan).where(HealthDailyMealPlan.family_id == choice["family_id"]))
        assert daily.version == 2
        assert daily.meal_sources == {
            meal: {"kind": "reference", "id": replacement["preview_id"] if meal == "dinner" else plan["preview_id"]}
            for meal in selected
        }
        assert await db.scalar(select(func.count()).select_from(HealthMealPlan)) == 0
        assert await db.scalar(select(func.count()).select_from(HealthProfessionalReview)) == 0


@pytest.mark.parametrize(
    "change_metadata,code", [(False, "reference_source_unavailable"), (True, "source_invalidated")]
)
async def test_source_object_bytes_and_version_changes_are_rejected_before_resave(
    family_profile_http, monkeypatch, change_metadata, code
):
    """对象字节不匹配与合法新版本都不能沿用已打开的旧回执。"""
    current = await setup_reference(family_profile_http, monkeypatch)
    bound = await bind_reference(current)
    context = await running_context(current, bound.json()["thread_id"])
    _, _, draft = await grounded_plan(current, context)
    changed = TEXT + "\n来源内容已更新\n"
    if change_metadata:
        await replace_source(current, changed)
    else:
        current[1].reference_objects["reference-file.md"] = changed.encode()
    with pytest.raises(HealthVisionError, match=code):
        await service.save_reference_plan(context, draft)
    async with current[1]() as db:
        assert await db.scalar(select(func.count()).select_from(HealthInitialPlanPreview)) == 1


async def complete(current, context, plan):
    """由实际发布校验产生完整结果，再建立权威输出指针。"""
    answer = (
        {"candidate_meals": plan["candidate_selection"]}
        if plan.get("status") == "reference_candidates"
        else {"preview_id": plan["preview_id"]}
    )
    result = await planner_final_result(context, json.dumps(answer))
    content = json.dumps(result, ensure_ascii=False)
    async with current[1].begin() as db:
        run = await db.get(AgentRun, context.run_id)
        await validate_initial_planner_publication(db, run, content)
        from yuxi.services.daily_meal_plan_service import publish_reference_in_session

        await publish_reference_in_session(db, run, content)
        message = Message(
            conversation_id=run.conversation_id,
            role="assistant",
            content=content,
            run_id=run.id,
            request_id=run.request_id,
            delivery_status="complete",
        )
        db.add(message)
        await db.flush()
        run.output_message_id, run.status, run.finished_at = message.id, "completed", utc_now_naive()
    return result


def assert_reference_display(rendered, stored):
    """展示可附加商品及媒体，但不能改写持久化来源、引句或缺失状态。"""
    for key, value in stored.items():
        if key != "meals":
            assert rendered[key] == value
    assert len(rendered["meals"]) == len(stored["meals"])
    for actual, expected in zip(rendered["meals"], stored["meals"], strict=True):
        assert actual["meal_type"] == expected["meal_type"]
        assert len(actual["dishes"]) == len(expected["dishes"])
        for dish, original in zip(actual["dishes"], expected["dishes"], strict=True):
            assert {key: dish[key] for key in original} == original


async def test_daily_plan_merges_selected_meal_rejects_stale_task_and_purchase(family_profile_http, monkeypatch):
    """真实HTTP与PG回读单餐合并、并发版本以及采购来源失效。"""
    current = await setup_reference(family_profile_http, monkeypatch)
    client, sessions, users, _, _, choice = current
    path = f"/api/family/{choice['family_id']}/daily-meal-plans/{choice['plan_date']}"

    async def make(base, meal):
        bound = await bind_reference(current, daily_base_version=base, meal_types=[meal])
        assert bound.status_code == 200, bound.text
        context = await running_context(current, bound.json()["thread_id"])
        plan, _, _ = await grounded_plan(current, context, meal_type=meal)
        return context, plan

    first, breakfast = await make(0, "breakfast")
    await complete(current, first, breakfast)
    read = await client.get(path, headers=users["self"])
    assert read.status_code == 200, read.text
    assert read.json()["version"] == 1
    assert [meal["meal_type"] for meal in read.json()["meals"]] == ["breakfast"]

    published = []

    async def commerce(method, url, payload, **kwargs):
        published.append(payload)
        return {"package_sn": "synthetic-package", "package_version": 1}

    monkeypatch.setattr("yuxi.services.daily_commerce_service.commerce_request", commerce)
    purchase = await client.post(
        path + "/purchase",
        headers=users["self"],
        json={"preview_id": breakfast["preview_id"], "version": 1, "meal_types": ["breakfast"]},
    )
    assert purchase.status_code == 200, purchase.text
    proof = published[0]["agent_source_proof"]

    second, dinner = await make(1, "dinner")
    await complete(current, second, dinner)
    read = await client.get(path, headers=users["self"])
    assert read.status_code == 200, read.text
    assert read.json()["version"] == 2
    assert [(meal["meal_type"], meal["source"]["id"]) for meal in read.json()["meals"]] == [
        ("breakfast", breakfast["preview_id"]),
        ("dinner", dinner["preview_id"]),
    ]
    old_purchase = await client.post(f"{ROOT}/commerce/source-validation", json=proof)
    assert old_purchase.status_code in (409, 410), old_purchase.text

    newer, changed = await make(2, "breakfast")
    older, stale = await make(2, "breakfast")
    await complete(current, newer, changed)
    with pytest.raises(HealthVisionError, match="daily_plan_version_changed"):
        await complete(current, older, stale)
    read = await client.get(path, headers=users["self"])
    assert read.json()["version"] == 3
    assert [meal["source"]["id"] for meal in read.json()["meals"]] == [changed["preview_id"], dinner["preview_id"]]
    denied = await client.get(path, headers=users["other"])
    assert denied.status_code in (403, 404), denied.text


async def test_daily_reference_single_meal_purchase_keeps_current_source_guards(family_profile_http, monkeypatch):
    """单餐采购沿真实HTTP与PG绑定当前版本，不能扩大范围或使用失效来源。"""
    current = await setup_reference(family_profile_http, monkeypatch)
    client, sessions, users, _, _, choice = current
    meals = ["breakfast", "lunch", "dinner"]
    bound = await bind_reference(current, daily_base_version=0, meal_types=meals)
    context = await running_context(current, bound.json()["thread_id"])
    plan, _, _ = await grounded_plan(current, context, meal_types=meals)
    await complete(current, context, plan)
    published = []

    async def commerce(method, url, payload, **kwargs):
        """只隔离外部商城，真实来源证明仍由服务生成和校验。"""
        published.append(payload)
        return {"package_sn": "synthetic-single-meal", "package_version": 1}

    monkeypatch.setattr("yuxi.services.daily_commerce_service.commerce_request", commerce)
    path = f"/api/family/{choice['family_id']}/daily-meal-plans/{choice['plan_date']}/purchase"
    body = {"preview_id": plan["preview_id"], "version": 1, "meal_types": ["lunch"]}
    receipt = await client.post(path, headers=users["self"], json=body)
    assert receipt.status_code == 200, receipt.text
    assert len(published) == 1
    proof = published[0]["agent_source_proof"]
    verified = await client.post(f"{ROOT}/commerce/source-validation", json=proof)
    assert verified.status_code == 200, verified.text
    assert published[0]["items"] == [{"sku_id": "sku-rice", "quantity": 1}]

    for changes in [{"version": 0}, {"meal_types": []}, {"meal_types": ["lunch", "lunch"]}]:
        denied = await client.post(path, headers=users["self"], json={**body, **changes})
        assert denied.status_code in (409, 422), denied.text
    denied = await client.post(path, headers=users["other"], json=body)
    assert denied.status_code in (403, 404), denied.text
    assert len(published) == 1

    changed = await bind_reference(current, daily_base_version=1, meal_types=["lunch"])
    changed_context = await running_context(current, changed.json()["thread_id"])
    changed_plan, _, _ = await grounded_plan(current, changed_context, meal_type="lunch")
    await complete(current, changed_context, changed_plan)
    denied = await client.post(path, headers=users["self"], json={**body, "version": 2})
    assert denied.status_code == 409, denied.text
    assert len(published) == 1
    invalidated = await client.post(f"{ROOT}/commerce/source-validation", json=proof)
    assert invalidated.status_code == 409, invalidated.text


async def test_daily_plan_reserves_one_active_request_and_recovers_after_failure(family_profile_http, monkeypatch):
    """跨线程并发只接受一个未结束请求，终态后允许同版本重试。"""
    from yuxi.services.daily_meal_plan_service import reserve_reference_request

    current = await setup_reference(family_profile_http, monkeypatch)
    first_binding = await bind_reference(current, daily_base_version=0)
    second_binding = await bind_reference(current, daily_base_version=0)
    first = await running_context(current, first_binding.json()["thread_id"])
    second = await running_context(current, second_binding.json()["thread_id"])
    async with current[1].begin() as db:
        binding, _ = await require_consultation(db, "self", first.thread_id)
        request = await db.scalar(select(AgentRunRequest).where(AgentRunRequest.request_id == first.request_id))
        await reserve_reference_request(db, "self", binding, request)
    choice = current[-1]
    path = f"/api/family/{choice['family_id']}/daily-meal-plans/{choice['plan_date']}"
    response = await current[0].get(path, headers=current[2]["self"])
    assert response.status_code == 200, response.text
    assert response.json()["pending"]["request_id"] == first.request_id
    assert response.json()["pending"]["status"] == "running"
    with pytest.raises(HealthVisionError, match="daily_plan_busy"):
        async with current[1].begin() as db:
            binding, _ = await require_consultation(db, "self", second.thread_id)
            request = await db.scalar(select(AgentRunRequest).where(AgentRunRequest.request_id == second.request_id))
            await reserve_reference_request(db, "self", binding, request)
    async with current[1].begin() as db:
        run = await db.get(AgentRun, first.run_id)
        run.status = "failed"
    async with current[1].begin() as db:
        binding, _ = await require_consultation(db, "self", second.thread_id)
        request = await db.scalar(select(AgentRunRequest).where(AgentRunRequest.request_id == second.request_id))
        await reserve_reference_request(db, "self", binding, request)
    response = await current[0].get(path, headers=current[2]["self"])
    assert response.json()["pending"]["request_id"] == second.request_id


async def test_daily_purchase_only_includes_meals_still_using_reference_source(family_profile_http, monkeypatch):
    """整日来源被替换一餐后，剩余餐次仍可核对并购买自己的食材。"""
    current = await setup_reference(family_profile_http, monkeypatch)
    meals = ["breakfast", "lunch", "dinner"]
    bound = await bind_reference(current, daily_base_version=0, meal_types=meals)
    first = await running_context(current, bound.json()["thread_id"])
    original, _, _ = await grounded_plan(current, first, meal_types=meals)
    await complete(current, first, original)
    choice = current[-1]
    path = f"/api/family/{choice['family_id']}/daily-meal-plans/{choice['plan_date']}"
    before = await current[0].get(path, headers=current[2]["self"])
    assert before.status_code == 200, before.text
    assert before.json()["version"] == 1
    original_meals = {meal["meal_type"]: meal for meal in before.json()["meals"]}
    assert set(original_meals) == set(meals)
    published = []

    async def commerce(method, url, payload, **kwargs):
        published.append(payload)
        return {"package_sn": "synthetic-package", "package_version": 1}

    monkeypatch.setattr("yuxi.services.daily_commerce_service.commerce_request", commerce)
    early = await current[0].post(
        f"{ROOT}/reference-meal-plans/{original['preview_id']}/purchase", headers=current[2]["self"]
    )
    assert early.status_code == 200, early.text
    old_proof = published.pop()["agent_source_proof"]
    changed_binding = await bind_reference(current, daily_base_version=1, meal_types=["dinner"])
    changed = await running_context(current, changed_binding.json()["thread_id"])
    replacement, _, _ = await grounded_plan(current, changed, meal_type="dinner")
    await complete(current, changed, replacement)
    response = await current[0].get(path, headers=current[2]["self"])
    assert response.status_code == 200, response.text
    assert response.json()["version"] == 2
    current_meals = {meal["meal_type"]: meal for meal in response.json()["meals"]}
    assert set(current_meals) == set(meals)
    for meal in ("breakfast", "lunch"):
        assert current_meals[meal] == original_meals[meal]
    assert current_meals["dinner"]["source"]["id"] == replacement["preview_id"]
    assert current_meals["dinner"]["source"] != original_meals["dinner"]["source"]
    async with current[1]() as db:
        stored = await db.scalar(
            select(HealthDailyMealPlan).where(HealthDailyMealPlan.family_id == choice["family_id"])
        )
        assert stored.version == 2
        assert stored.meal_sources == {
            meal: {"kind": "reference", "id": replacement["preview_id"] if meal == "dinner" else original["preview_id"]}
            for meal in meals
        }
        old_preview = await db.get(HealthInitialPlanPreview, original["preview_id"])
        assert old_preview.snapshot["meals"] == original["meals"]
    option = next(item for item in response.json()["purchase_options"] if item["id"] == original["preview_id"])
    assert option["meal_types"] == ["breakfast", "lunch"]
    assert "其他餐次" in option["quantity_notice"]
    legacy = await current[0].post(
        f"{ROOT}/reference-meal-plans/{original['preview_id']}/purchase", headers=current[2]["self"]
    )
    assert legacy.status_code == 409, legacy.text
    assert legacy.json()["code"] == "daily_plan_source_changed"
    assert published == []
    invalidated = await current[0].post(f"{ROOT}/commerce/source-validation", json=old_proof)
    assert invalidated.status_code == 409, invalidated.text
    assert invalidated.json()["code"] == "daily_plan_source_changed"
    purchase = await current[0].post(
        path + "/purchase",
        headers=current[2]["self"],
        json={"preview_id": original["preview_id"], "version": 2, "meal_types": option["meal_types"]},
    )
    assert purchase.status_code == 200, purchase.text
    assert published[0]["items"] == [{"sku_id": "sku-rice", "quantity": 1}]
    invalid = await current[0].post(
        path + "/purchase",
        headers=current[2]["self"],
        json={"preview_id": original["preview_id"], "version": 2, "meal_types": meals},
    )
    assert invalid.status_code == 409, invalid.text


async def test_message_submission_reserves_daily_plan_before_commit(family_profile_http, monkeypatch):
    """真实请求服务与PG事务串行登记每日请求，第二线程不能写入。"""
    from fastapi import HTTPException
    from yuxi.services import agent_request_service as intake
    from yuxi.services.input_message_service import build_chat_input_message
    from yuxi.storage.postgres.models_business import User

    current = await setup_reference(family_profile_http, monkeypatch)
    first = await bind_reference(current, daily_base_version=0)
    second = await bind_reference(current, daily_base_version=0)
    assert first.status_code == second.status_code == 200
    monkeypatch.setattr(intake, "get_agent_backend", lambda _backend: object())

    async def workdir(**kwargs):
        return SimpleNamespace(materialize_managed=False)

    async def persist(*, db, request_input, current_user, **kwargs):
        binding, _ = await require_consultation(db, current_user.uid, request_input.thread_id)
        message = Message(
            conversation_id=binding.conversation_id,
            role="user",
            content="合成请求",
            request_id=request_input.request_id,
        )
        db.add(message)
        await db.flush()
        request = AgentRunRequest(
            request_id=request_input.request_id,
            uid=current_user.uid,
            agent_slug=request_input.agent_slug,
            conversation_thread_id=request_input.thread_id,
            status="queued",
            input_message_id=message.id,
        )
        db.add(request)
        await db.flush()
        return request, None

    async def view(*, repo, request):
        return {"request_id": request.request_id, "status": request.status}

    monkeypatch.setattr(intake, "resolve_conversation_workdir_binding", workdir)
    monkeypatch.setattr(intake, "_persist_request", persist)
    monkeypatch.setattr(intake, "request_view", view)
    ids = [str(uuid4()), str(uuid4())]
    for i, bound in enumerate((first, second)):
        async with current[1]() as db:
            user = await db.scalar(select(User).where(User.uid == "self"))
            request = intake.AgentRequestInput(
                agent_slug="health-meal-planner",
                thread_id=bound.json()["thread_id"],
                request_id=ids[i],
                input_message=build_chat_input_message("安排早餐"),
                origin=intake.RunOrigin(source="chat", channel="miniapp"),
            )
            if i == 0:
                assert (await intake.submit_agent_request(request_input=request, current_user=user, db=db))[
                    "status"
                ] == "queued"
            else:
                with pytest.raises(HTTPException) as error:
                    await intake.submit_agent_request(request_input=request, current_user=user, db=db)
                assert error.value.status_code == 423
                await db.rollback()
    async with current[1]() as db:
        assert await db.scalar(select(AgentRunRequest).where(AgentRunRequest.request_id == ids[0])) is not None
        assert await db.scalar(select(AgentRunRequest).where(AgentRunRequest.request_id == ids[1])) is None


async def test_daily_plan_restores_authorized_followup_question(family_profile_http, monkeypatch):
    """用户换设备后仍能读取同一任务的补充问题和绑定范围。"""
    from yuxi.services.daily_meal_plan_service import reserve_reference_request

    current = await setup_reference(family_profile_http, monkeypatch)
    bound = await bind_reference(current, daily_base_version=0)
    context = await running_context(current, bound.json()["thread_id"])
    async with current[1].begin() as db:
        binding, _ = await require_consultation(db, "self", context.thread_id)
        request = await db.scalar(select(AgentRunRequest).where(AgentRunRequest.request_id == context.request_id))
        await reserve_reference_request(db, "self", binding, request)
    result = await planner_final_result(context, json.dumps({"questions": ["早餐需要避开什么食材？"]}))
    content = json.dumps(result, ensure_ascii=False)
    async with current[1].begin() as db:
        run = await db.get(AgentRun, context.run_id)
        await validate_initial_planner_publication(db, run, content)
        message = Message(
            conversation_id=run.conversation_id,
            role="assistant",
            content=content,
            run_id=run.id,
            request_id=run.request_id,
            delivery_status="complete",
        )
        db.add(message)
        await db.flush()
        run.output_message_id, run.status, run.finished_at = message.id, "completed", utc_now_naive()
    choice = current[-1]
    path = f"/api/family/{choice['family_id']}/daily-meal-plans/{choice['plan_date']}"
    response = await current[0].get(path, headers=current[2]["self"])
    assert response.status_code == 200, response.text
    pending = response.json()["pending"]
    assert pending["status"] == "needs_input"
    assert pending["questions"] == ["早餐需要避开什么食材？"]
    assert pending["request_id"] == context.request_id and pending["member_id"] == current[3]
    assert pending["selection"]["daily_base_version"] == 0


async def test_reference_without_formal_rules_publishes_and_reads_same_run(family_profile_http, monkeypatch):
    current = await setup_reference(family_profile_http, monkeypatch)
    client, sessions, users, _, _, choice = current
    bound = await bind_reference(current)
    assert bound.status_code == 200, bound.text
    context = await running_context(current, bound.json()["thread_id"])
    plan, _, _ = await grounded_plan(current, context)
    # 同Run有两份预览，最终只采用第一份。
    second, _, _ = await grounded_plan(current, context, quantity=2)
    assert second["preview_id"] != plan["preview_id"]
    result = await complete(current, context, plan)
    assert result["professional_status"] == "not_reviewed" and result["nutrition_status"] == "not_calculated"
    dish = result["meals"][0]["dishes"][0]
    assert set(dish["nutrition"].values()) == {None}
    for path in (
        f"{ROOT}/reference-meal-plans/{plan['preview_id']}",
        f"/api/family/{choice['family_id']}/reference-meal-plans/{choice['plan_date']}/current",
    ):
        response = await client.get(path, headers=users["self"])
        assert response.status_code == 200, response.text
        assert_reference_display(response.json(), result)
        assert response.headers["cache-control"] == "no-store"
    task = await client.get(f"{ROOT}/tasks/{context.request_id}", headers=users["self"])
    assert task.status_code == 200, task.text
    assert task.json()["task_type"] == "reference_meal_preview"
    assert_reference_display(task.json()["result"]["data"], result)
    history = await client.get(f"/api/chat/thread/{context.thread_id}/history", headers=users["self"])
    assert history.status_code == 200, history.text
    assert plan["preview_id"] in history.text
    assert (
        await client.get(f"{ROOT}/reference-meal-plans/{plan['preview_id']}", headers=users["other"])
    ).status_code == 404
    async with sessions() as db:
        for model in (HealthRuleSnapshot, RecipeVersion, HealthMealPlan, HealthProfessionalReview):
            assert await db.scalar(select(func.count()).select_from(model)) == 0


async def test_reference_source_change_rejects_dedicated_task_and_actual_chat_history(family_profile_http, monkeypatch):
    current = await setup_reference(family_profile_http, monkeypatch)
    client, sessions, users, _, _, _ = current
    bound = await bind_reference(current)
    context = await running_context(current, bound.json()["thread_id"])
    plan, _, _ = await grounded_plan(current, context)
    await complete(current, context, plan)
    async with sessions.begin() as db:
        chunk = await db.scalar(select(KnowledgeChunk))
        chunk.content += "\n已修改正文"
    for path, expected in (
        (f"{ROOT}/reference-meal-plans/{plan['preview_id']}", 410),
        (f"{ROOT}/tasks/{context.request_id}", 410),
        (f"/api/chat/thread/{context.thread_id}/history", 200),
    ):
        response = await client.get(path, headers=users["self"])
        assert response.status_code == expected, response.text
        assert "大米100克" not in response.text
        if path.endswith("/history"):
            assert plan["preview_id"] not in response.text
            assert "请重新安排" in response.text


async def test_reference_rejects_cross_run_unopened_stale_and_formal_tool(family_profile_http, monkeypatch):
    current = await setup_reference(family_profile_http, monkeypatch)
    bound = await bind_reference(current)
    context = await running_context(current, bound.json()["thread_id"])
    plan, opened, draft = await grounded_plan(current, context)
    with pytest.raises(HealthVisionError, match="initial_selection_required"):
        await preview_initial_for_run(context)
    with pytest.raises(HealthVisionError, match="source_invalidated"):
        await require_consultation_attempt(
            context, [ToolMessage(name=opened.name, tool_call_id="forged", content=opened.content)]
        )
    await complete(current, context, plan)
    other = await running_context(current, context.thread_id)
    with pytest.raises(HealthVisionError, match="reference_receipt_invalid"):
        await service.save_reference_plan(other, draft)
    with pytest.raises(HealthVisionError, match="reference_receipt_invalid"):
        await planner_final_result(other, json.dumps({"preview_id": plan["preview_id"]}))
    async with current[1].begin() as db:
        actor = await db.get(FamilyMember, current[4])
        actor.version += 1
    with pytest.raises(HealthVisionError, match="reference_profile_unconfirmed"):
        await service.save_reference_plan(other, draft)


@pytest.mark.parametrize("legacy", [False, True])
async def test_reference_purchase_binds_exact_items_and_invalidates_changed_product(
    family_profile_http, monkeypatch, legacy
):
    current = await setup_reference(family_profile_http, monkeypatch)
    bound = await bind_reference(current)
    context = await running_context(current, bound.json()["thread_id"])
    plan, _, draft = await grounded_plan(current, context)
    if legacy:
        # 先完成合法当前结果，再构造升级前缺少分类商品链版本的已存事实。
        await complete(current, context, plan)
        plan.pop("catalog_chain_version")
        async with current[1].begin() as db:
            row = await db.get(HealthInitialPlanPreview, plan["preview_id"])
            row.snapshot = {k: v for k, v in plan.items() if k != "preview_id"}
            run = await db.get(AgentRun, context.run_id)
            (await db.get(Message, run.output_message_id)).content = json.dumps(plan, ensure_ascii=False)
        for method, path in (
            ("GET", f"{ROOT}/reference-meal-plans/{plan['preview_id']}"),
            ("POST", f"{ROOT}/reference-meal-plans/{plan['preview_id']}/purchase"),
        ):
            denied = await current[0].request(method, path, headers=current[2]["self"])
            assert denied.status_code == 410 and denied.json()["code"] == "reference_chain_unverified", denied.text
        return
    await complete(current, context, plan)
    published = []

    async def publish(method, path, payload, **kwargs):
        published.append(payload)
        return {"package_sn": "synthetic-package", "package_version": 1}

    monkeypatch.setattr("yuxi.services.daily_commerce_service.commerce_request", publish)
    response = await current[0].post(
        f"{ROOT}/reference-meal-plans/{plan['preview_id']}/purchase", headers=current[2]["self"]
    )
    assert response.status_code == 200, response.text
    payload = published[0]
    assert payload["nutrition_validation"]["status"] == "reference_only"
    assert payload["ingredient_requirements"] == []
    source = json.loads(payload["agent_source_proof"]["payload"])
    proof = payload["agent_source_proof"]
    valid = await current[0].post(f"{ROOT}/commerce/source-validation", json=proof)
    assert valid.status_code == 200 and valid.json()["available"], valid.text
    forged = await current[0].post(
        f"{ROOT}/commerce/source-validation",
        json={**proof, "payload": proof["payload"].replace('"quantity":1', '"quantity":5')},
    )
    assert forged.status_code == 403, forged.text
    repeated = await current[0].post(
        f"{ROOT}/reference-meal-plans/{plan['preview_id']}/purchase", headers=current[2]["self"]
    )
    assert repeated.status_code == 200 and published[1] == payload
    async with current[1]() as db:
        assert (await service.validate_reference_purchase_source(db, source))["available"]
        tampered = {**source, "items": [{**source["items"][0], "quantity": 5}]}
        with pytest.raises(HealthVisionError, match="source_invalidated"):
            await service.validate_reference_purchase_source(db, tampered)

    # 缺失映射可选购，商品事实变化不能继续沿用旧快照。
    async def changed_catalog(category_codes=None):
        return {
            "version": "synthetic-v2",
            "items": [{**SKU, **({"allergen_codes": ["花生"]} if legacy else {"product_description": "配料含花生"})}],
        }

    monkeypatch.setattr(service, "current_catalog", changed_catalog)
    async with current[1]() as db:
        with pytest.raises(HealthVisionError, match="reference_product_changed"):
            await service.validate_reference_purchase_source(db, source)


@pytest.mark.parametrize("field", ["allergen_codes", "product_description"])
async def test_unknown_allergen_cannot_pass_recipe_check_before_conflicting_sku(
    family_profile_http, monkeypatch, field
):
    """花生商品仍有明确原文冲突，菜谱兼容性未核实时已先拒绝整单。"""
    current = await setup_reference(family_profile_http, monkeypatch, allergens=["花生"])

    async def conflicting_catalog(category_codes=None):
        return {
            "version": "conflict-v1",
            "items": [{**SKU, field: ["花生"] if field == "allergen_codes" else "配料含花生"}],
        }

    monkeypatch.setattr(service, "current_catalog", conflicting_catalog)
    sku = (await conflicting_catalog())["items"][0]
    assert service.reference_restriction_conflict(service.reference_product_composition(sku), ["花生"]) is True
    bound = await bind_reference(current)
    context = await running_context(current, bound.json()["thread_id"])
    with pytest.raises(HealthVisionError, match="reference_restriction_unverified"):
        await grounded_plan(current, context)
    async with current[1]() as db:
        assert await db.scalar(select(func.count()).select_from(HealthInitialPlanPreview)) == 0


@pytest.mark.parametrize(
    ("field", "restriction", "ingredient"),
    [
        ("allergens", "鸡蛋", "eggs"),
        ("allergens", "牛奶", "milk"),
        ("avoidances", "大豆", "soybeans"),
        ("intolerances", "麸质", "wheat flour"),
    ],
)
@pytest.mark.parametrize("location", ["recipe", "product"])
async def test_unverified_restrictions_block_recipe_and_product_saves(
    family_profile_http, monkeypatch, field, restriction, ingredient, location
):
    """未知双语名称保持未核实，真实读取回执齐全也不能写预览或采购。"""
    current = await setup_reference(family_profile_http, monkeypatch, **{field: [restriction]})
    if location == "recipe":
        await replace_source(current, TEXT + "\n" + ingredient)
    else:

        async def uncertain_catalog(category_codes=None):
            return {"version": "synthetic-uncertain", "items": [{**SKU, "ingredients": [ingredient]}]}

        monkeypatch.setattr(service, "current_catalog", uncertain_catalog)
        with pytest.raises(HealthVisionError, match="reference_restriction_unverified"):
            service.reference_restriction_conflict(ingredient, [restriction])
    bound = await bind_reference(current)
    context = await running_context(current, bound.json()["thread_id"])
    catalog = await service.get_reference_context(context)
    assert catalog["restriction_verification"]["status"] == "needs_verification"
    assert catalog["restriction_verification"]["unverified_restrictions"] == [restriction]
    assert catalog["members"][0][field] == [restriction]
    with pytest.raises(HealthVisionError, match="reference_restriction_unverified"):
        await grounded_plan(current, context)
    async with current[1]() as db:
        assert await db.scalar(select(func.count()).select_from(HealthInitialPlanPreview)) == 0


async def test_unverified_restriction_does_not_hide_quote_or_profile_failure(family_profile_http, monkeypatch):
    """未核实限制之前仍保留具体引文失败与当前资料授权检查。"""
    current = await setup_reference(family_profile_http, monkeypatch, allergens=["鸡蛋"])
    bound = await bind_reference(current)
    context = await running_context(current, bound.json()["thread_id"])
    with pytest.raises(HealthVisionError, match="reference_restriction_unverified"):
        await grounded_plan(current, context)
    invalid = {
        "meals": [
            {
                "meal_type": "breakfast",
                "dishes": [
                    {
                        "file_id": "reference-file",
                        "chunk_id": "reference-chunk",
                        "name": "不存在的菜",
                        "ingredients": ["大米100克"],
                        "steps": ["加水煮熟"],
                    }
                ],
            }
        ],
        "purchase_items": [],
        "purchase_gaps": [{"ingredient": "大米100克", "reason": "no_match", "detail": "合成无匹配"}],
    }
    with pytest.raises(HealthVisionError, match="reference_quote_invalid"):
        await service.save_reference_plan(context, invalid)
    async with current[1].begin() as db:
        actor = await db.get(FamilyMember, current[4])
        actor.version += 1
    with pytest.raises(HealthVisionError, match="reference_profile_unconfirmed"):
        await service.save_reference_plan(context, invalid)


@pytest.mark.parametrize(
    ("restriction", "ingredient", "location", "code"),
    [
        ("鸡蛋", "eggs", "recipe", "reference_restriction_unverified"),
        ("牛奶", "milk", "product", "reference_restriction_unverified"),
        ("牛羊肉", "beef broth", "recipe", "reference_restriction_conflict"),
        ("牛羊肉", "lamb", "product", "reference_restriction_conflict"),
    ],
)
async def test_existing_preview_rechecks_restrictions_for_publication_history_and_purchase(
    family_profile_http, monkeypatch, restriction, ingredient, location, code
):
    """构造升级前回执；当前档案哈希未变，旧结果仍须通过现有限制检查。"""
    current = await setup_reference(family_profile_http, monkeypatch, avoidances=[restriction])
    if location == "recipe":
        await replace_source(current, TEXT + "\n" + ingredient)
    else:

        async def previous_catalog(category_codes=None):
            return {"version": "synthetic-previous", "items": [{**SKU, "ingredients": [ingredient]}]}

        monkeypatch.setattr(service, "current_catalog", previous_catalog)
    bound = await bind_reference(current)
    context = await running_context(current, bound.json()["thread_id"])
    # 仅用于准备旧版已存在的保存/发布事实；所有待测入口恢复真实修复后的检查。
    with monkeypatch.context() as previous:
        previous.setattr(service, "reference_restriction_conflict", lambda content, restrictions: False)
        plan, _, _ = await grounded_plan(current, context)
        await complete(current, context, plan)
    async with current[1]() as db:
        run = await db.get(AgentRun, context.run_id)
        binding, _ = await require_consultation(db, "self", context.thread_id)
        assert (await service.bound_reference_context(db, "self", binding))["sources"] == plan["sources"]
        with pytest.raises(HealthVisionError, match=code):
            await validate_initial_planner_publication(db, run, json.dumps(plan, ensure_ascii=False))
    for path, status in (
        (f"{ROOT}/reference-meal-plans/{plan['preview_id']}", 422),
        (f"{ROOT}/tasks/{context.request_id}", 422),
        (f"/api/chat/thread/{context.thread_id}/history", 200),
    ):
        response = await current[0].get(path, headers=current[2]["self"])
        assert response.status_code == status, response.text
        assert "大米100克" not in response.text
        if path.endswith("/history"):
            assert plan["preview_id"] not in response.text
            assert "请重新安排" in response.text

    async def unexpected_purchase(*args, **kwargs):
        raise AssertionError("未核实或冲突的旧结果不能发布采购")

    monkeypatch.setattr("yuxi.services.daily_commerce_service.commerce_request", unexpected_purchase)
    response = await current[0].post(
        f"{ROOT}/reference-meal-plans/{plan['preview_id']}/purchase", headers=current[2]["self"]
    )
    assert response.status_code == 422, response.text
    assert code in response.text
    async with current[1]() as db:
        with pytest.raises(HealthVisionError, match=code):
            await service.validate_reference_purchase_source(db, {"uid": "self", "preview_id": plan["preview_id"]})
        assert await db.scalar(select(func.count()).select_from(HealthInitialPlanPreview)) == 1


async def test_insufficient_sku_stock_and_unselected_meal_cannot_be_saved(family_profile_http, monkeypatch):
    """目录及选择先被真实读取，负控只改变请求的数量或餐次。"""
    current = await setup_reference(family_profile_http, monkeypatch)
    bound = await bind_reference(current)
    context = await running_context(current, bound.json()["thread_id"])
    plan, _, draft = await grounded_plan(current, context)
    draft["purchase_items"][0]["quantity"] = 6
    with pytest.raises(HealthVisionError, match="reference_product_changed"):
        await service.save_reference_plan(context, draft)
    draft["purchase_items"] = []
    draft["purchase_gaps"] = [{"ingredient": "大米100克", "reason": "needs_confirmation", "detail": "包装待确认"}]
    draft["meals"][0]["meal_type"] = "dinner"
    with pytest.raises(HealthVisionError, match="reference_meals_mismatch"):
        await service.save_reference_plan(context, draft)


async def test_long_document_opens_the_actual_late_search_window(family_profile_http, monkeypatch):
    current = await setup_reference(family_profile_http, monkeypatch)
    async with current[1].begin() as db:
        first = await db.scalar(select(KnowledgeChunk))
        first.content = "无关前言" * 6000
        db.add(
            KnowledgeChunk(
                chunk_id="late-chunk",
                file_id="reference-file",
                kb_id="synthetic-reference-kb",
                chunk_index=1,
                content=TEXT,
            )
        )
    async with current[1]() as db:
        doc = await service.recipe_document(db, "reference-file", "late-chunk")
        assert doc["content"] == TEXT
        assert doc["file_hash"] == hashlib.sha256(TEXT.encode()).hexdigest()


async def test_exact_cooking_title_is_not_displaced_by_clinical_semantic_hits(family_profile_http, monkeypatch):
    """当前烹饪标题与完整原谱优先，疾病目录不扩大候选范围。"""
    current = await setup_reference(family_profile_http, monkeypatch)
    await add_recipe(current, "competing-file", "USDA家庭菜谱｜粥.md", TEXT)
    await add_recipe(current, "earlier-body-file", "烹饪菜谱｜A早餐.md", TEXT)
    for index in range(5):
        await add_recipe(current, f"clinical-{index}", f"官方菜单集合｜{index}清粥临床资料.md", TEXT)
    bound = await bind_reference(current)
    context = await running_context(current, bound.json()["thread_id"])
    hits = await service.search_reference_recipes(context, "清粥")
    assert hits["items"][0]["file_id"] == "reference-file"
    assert {item["file_id"] for item in hits["items"]} == {"reference-file", "competing-file", "earlier-body-file"}
    assert hits["items"][0]["parse_status"] == "parsed"


async def test_home_recipe_title_precedes_other_cooking_matches(family_profile_http, monkeypatch):
    """完整家常原谱不能被同食材但无法解析的烹饪摘要挤走。"""
    current = await setup_reference(family_profile_http, monkeypatch)
    async with current[1].begin() as db:
        file = await db.scalar(select(KnowledgeFile).where(KnowledgeFile.file_id == "reference-file"))
        file.filename = "家常菜谱_红豆米饭_Red Beans and Rice.md"
    for index in range(4):
        await add_recipe(current, f"cooking-rice-{index}", f"烹饪菜谱｜{index}米饭配菜.md", "合成米饭配菜参考")
    bound = await bind_reference(current)
    context = await running_context(current, bound.json()["thread_id"])
    hits = await service.search_reference_recipes(context, "米饭")
    assert len(hits["items"]) == 5
    assert hits["items"][0]["file_id"] == "reference-file"
    await receipt(current[1], context, "search_reference_recipes", hits)
    opened = await service.read_reference_recipe(context, "reference-file", "reference-chunk")
    assert opened["content"] == TEXT


async def test_reference_catalog_summary_preserves_validation_facts(family_profile_http, monkeypatch):
    """上下文只给分类，选中分类详情裁剪仍保留完整商品事实指纹。"""
    current = await setup_reference(family_profile_http, monkeypatch)
    bound = await bind_reference(current)
    context = await running_context(current, bound.json()["thread_id"])
    sku = {**deepcopy(SKU), "product_description": "合成详情" * 800, "data_issues": ["合成缺项" * 200]}
    monkeypatch.setattr(service, "current_catalog", AsyncMock(return_value={"version": "synthetic-v1", "items": [sku]}))
    result = await service.get_reference_context(context)
    assert "catalog" not in result and result["categories"][0]["category_code"] == "grain"
    read = await service.find_reference_products(context, ["grain"])
    summary = read["catalog"][0]
    assert summary["product_description"] == sku["product_description"][:320]
    assert summary["description_truncated"] is True
    for key in (
        "sku_id",
        "product_name",
        "net_content",
        "ingredients",
        "allergen_codes",
        "data_completeness",
        "data_issues",
    ):
        assert summary[key] == sku[key]
    assert summary["facts_hash"] == service.reference_product(sku)["facts_hash"]
    plan, _, _ = await grounded_plan(current, context)
    assert plan["purchase_items"][0]["product_description"] == sku["product_description"]
    assert plan["purchase_items"][0]["data_issues"] == sku["data_issues"]


async def test_home_recipe_catalog_is_bounded_and_does_not_authorize_reading(family_profile_http, monkeypatch):
    """分类上下文不授权原谱读取，实际检索数量与固定库边界保持有限。"""
    current = await setup_reference(family_profile_http, monkeypatch)
    for index in range(12):
        await add_recipe(current, f"home-{index}", f"家常菜谱_大米{index:02}.md", TEXT)
    async with current[1].begin() as db:
        db.add(KnowledgeBase(kb_id="other-home-kb", name="其他合成库", kb_type="milvus"))
    for index, (kb, status, folder, title) in enumerate(
        [
            ("other-home-kb", "indexed", False, "家常菜谱_大米"),
            ("synthetic-reference-kb", "pending", False, "家常菜谱_大米"),
            ("synthetic-reference-kb", "indexed", True, "家常菜谱_大米"),
            ("synthetic-reference-kb", "indexed", False, "分类目录_大米"),
        ]
    ):
        await add_recipe(current, f"excluded-{index}", title + ".md", TEXT, kb_id=kb, status=status, folder=folder)
    bound = await bind_reference(current)
    context = await running_context(current, bound.json()["thread_id"])
    catalog = await service.get_reference_context(context)
    assert "recipe_catalog" not in catalog and catalog["categories"]
    with pytest.raises(HealthVisionError, match="reference_receipt_invalid"):
        await service.read_reference_recipe(context, "reference-file", "reference-chunk")
    hits = await service.search_reference_recipes(context, "大米")
    assert len(hits["items"]) == 9
    assert not any(item["file_id"].startswith("excluded-") for item in hits["items"])


async def test_english_meat_in_source_cannot_bypass_chinese_avoidance(family_profile_http, monkeypatch):
    """当前原文中的英文忌口即使未被模型摘录也不能形成保存结果。"""
    current = await setup_reference(family_profile_http, monkeypatch, avoidances=["牛羊肉"])
    await replace_source(current, TEXT + "\nOptional beef broth")
    bound = await bind_reference(current)
    context = await running_context(current, bound.json()["thread_id"])
    with pytest.raises(HealthVisionError, match="reference_restriction_conflict"):
        await grounded_plan(current, context)
    async with current[1]() as db:
        assert await db.scalar(select(func.count()).select_from(HealthInitialPlanPreview)) == 0


@pytest.mark.parametrize("field", ["ingredients", "product_description"])
async def test_english_meat_in_product_cannot_bypass_chinese_avoidance(family_profile_http, monkeypatch, field):
    """商品配料和说明使用与菜谱相同的已知中英文忌口检查。"""
    current = await setup_reference(family_profile_http, monkeypatch, avoidances=["牛羊肉"])

    async def conflicting_catalog(category_codes=None):
        return {
            "version": "synthetic-english-conflict",
            "items": [{**SKU, field: ["lamb"] if field == "ingredients" else "Contains beef broth"}],
        }

    monkeypatch.setattr(service, "current_catalog", conflicting_catalog)
    bound = await bind_reference(current)
    context = await running_context(current, bound.json()["thread_id"])
    with pytest.raises(HealthVisionError, match="reference_restriction_conflict"):
        await grounded_plan(current, context)
    async with current[1]() as db:
        assert await db.scalar(select(func.count()).select_from(HealthInitialPlanPreview)) == 0


async def test_cooking_body_hit_is_found_before_directory_and_clinical_titles(family_profile_http, monkeypatch):
    """文件跨分片召回仍保留真实文件身份，打开的是完整对象原文。"""
    current = await setup_reference(family_profile_http, monkeypatch)
    full = "# 早餐糊\n\n## 食材\n- 燕麦30克\n\n## 做法\n1. 加水煮熟\n"
    await replace_source(current, full)
    async with current[1].begin() as db:
        file = await db.scalar(select(KnowledgeFile).where(KnowledgeFile.file_id == "reference-file"))
        file.filename = "烹饪菜谱｜早餐糊.md"
        first = await db.scalar(select(KnowledgeChunk).where(KnowledgeChunk.file_id == file.file_id))
        first.content = "来源与介绍"
        db.add(
            KnowledgeChunk(
                chunk_id="cooking-body-hit", file_id=file.file_id, kb_id=file.kb_id, chunk_index=1, content=full
            )
        )
    for index in range(5):
        await add_recipe(current, f"directory-oat-{index}", f"分类目录｜燕麦{index}.md", full)
    bound = await bind_reference(current)
    context = await running_context(current, bound.json()["thread_id"])
    hits = await service.search_reference_recipes(context, "早餐 燕麦")
    assert [(item["file_id"], item["chunk_id"]) for item in hits["items"]] == [("reference-file", "reference-chunk")]
    await receipt(current[1], context, "search_reference_recipes", hits)
    opened = await service.read_reference_recipe(context, "reference-file", "reference-chunk")
    assert opened["content"] == full and opened["recipe_check"]["ingredients"] == ["燕麦30克"]
    with pytest.raises(HealthVisionError, match="reference_receipt_invalid"):
        await service.read_reference_recipe(context, "directory-oat-0", "directory-oat-0-chunk")


async def test_cooking_body_search_keeps_current_kb_and_indexed_file_boundary(family_profile_http, monkeypatch):
    """候选只能来自固定库、已索引且非目录的烹饪文件。"""
    current = await setup_reference(family_profile_http, monkeypatch)
    async with current[1].begin() as db:
        db.add(KnowledgeBase(kb_id="other-recipe-kb", name="其他合成库", kb_type="milvus"))
    content = "# 燕麦糊\n\n## 食材\n- 燕麦30克\n\n## 做法\n1. 加水煮熟\n"
    for index, (kb, status, folder) in enumerate(
        [
            ("other-recipe-kb", "indexed", False),
            ("synthetic-reference-kb", "pending", False),
            ("synthetic-reference-kb", "indexed", True),
        ]
    ):
        await add_recipe(
            current,
            f"excluded-cooking-{index}",
            f"烹饪菜谱｜燕麦糊{index}.md",
            content,
            kb_id=kb,
            status=status,
            folder=folder,
        )
    bound = await bind_reference(current)
    context = await running_context(current, bound.json()["thread_id"])
    assert (await service.search_reference_recipes(context, "燕麦"))["items"] == []


async def test_no_title_match_uses_fixed_kb_indexed_body(family_profile_http, monkeypatch):
    """无标题词命中时仍可从同固定库正文召回，不扩大到其他来源。"""
    current = await setup_reference(family_profile_http, monkeypatch)
    bound = await bind_reference(current)
    context = await running_context(current, bound.json()["thread_id"])
    hits = await service.search_reference_recipes(context, "大米")
    assert [item["file_id"] for item in hits["items"]] == ["reference-file"]
    assert hits["items"][0]["ingredient_matches"][0]["sku_id"] == "sku-rice"
    assert (await service.search_reference_recipes(context, "完全无关关键词"))["items"] == []


async def test_empty_purchase_cannot_claim_catalog_failure_or_bypass_product_requirement(
    family_profile_http, monkeypatch
):
    """当前链路要求真实商城食材，缺SKU不能降成已安排餐单。"""
    current = await setup_reference(family_profile_http, monkeypatch)
    bound = await bind_reference(current)
    context = await running_context(current, bound.json()["thread_id"])
    _, _, draft = await grounded_plan(current, context)
    draft["purchase_items"] = []
    for reason in ("catalog_unavailable", "needs_confirmation"):
        draft["purchase_gaps"] = [{"ingredient": "大米100克", "reason": reason, "detail": "合成待核对说明"}]
        with pytest.raises(HealthVisionError, match="reference_product_required"):
            await service.save_reference_plan(context, draft)
    async with current[1]() as db:
        assert await db.scalar(select(func.count()).select_from(HealthInitialPlanPreview)) == 1


async def test_changed_product_description_requires_fresh_selection(family_profile_http, monkeypatch):
    current = await setup_reference(family_profile_http, monkeypatch)
    bound = await bind_reference(current)
    context = await running_context(current, bound.json()["thread_id"])
    _, _, draft = await grounded_plan(current, context)

    async def changed_catalog(category_codes=None):
        return {"version": "changed-description", "items": [{**SKU, "product_description": "商品含花生"}]}

    monkeypatch.setattr(service, "current_catalog", changed_catalog)
    with pytest.raises(HealthVisionError, match="reference_product_changed"):
        await service.save_reference_plan(context, draft)


@pytest.mark.parametrize("failure_first", [True, False])
async def test_catalog_failure_is_explicit_and_retry_keeps_full_source_checks(
    family_profile_http, monkeypatch, failure_first
):
    """首次或保存重验的目录失败均明确拒绝；恢复后仍需真实商品回执。"""
    current = await setup_reference(family_profile_http, monkeypatch)
    bound = await bind_reference(current)
    context = await running_context(current, bound.json()["thread_id"])
    original = service.current_catalog

    async def fail(category_codes=None):
        raise HealthVisionError("commerce_unavailable", "合成目录暂不可用", 503)

    if failure_first:
        monkeypatch.setattr(service, "current_catalog", fail)
        with pytest.raises(HealthVisionError, match="commerce_unavailable"):
            await service.find_reference_products(context, ["grain"])
        monkeypatch.setattr(service, "current_catalog", original)
    _, _, draft = await grounded_plan(current, context)
    if not failure_first:
        monkeypatch.setattr(service, "current_catalog", fail)
        with pytest.raises(HealthVisionError, match="commerce_unavailable"):
            await service.save_reference_plan(context, draft)
        monkeypatch.setattr(service, "current_catalog", original)
    assert (await service.save_reference_plan(context, draft))["purchase_status"] == "selected"


async def test_reference_quote_failure_audit_then_null_correction(family_profile_http, monkeypatch):
    """真实 ToolNode/v3 审计在两次显式操作之间落库；模型声明合成，不冒充完整 worker。"""
    from langchain_core.messages import HumanMessage
    from langgraph.checkpoint.memory import InMemorySaver
    from langgraph.prebuilt import ToolCallTransformer
    from langgraph.stream.transformers import CustomTransformer
    from yuxi.agents.toolkits.meal_planner import save_reference_meal_plan
    from yuxi.repositories.model_message_audit_repository import ModelMessageAuditRepository
    from yuxi.services.reference_meal_plan_types import REFERENCE_TOOLS
    from yuxi.services.tool_message_audit_service import ToolMessageAuditCollector
    from yuxi.storage.postgres.models_business import ToolCall

    current = await setup_reference(family_profile_http, monkeypatch)
    bound = await bind_reference(current)
    context = await running_context(current, bound.json()["thread_id"])
    context.tools = list(REFERENCE_TOOLS)
    sessions = current[1]
    await receipt(sessions, context, "get_reference_plan_context", await service.get_reference_context(context))
    await receipt(
        sessions, context, "search_reference_recipes", await service.search_reference_recipes(context, "清粥")
    )
    await receipt(
        sessions,
        context,
        "read_reference_recipe",
        await service.read_reference_recipe(context, "reference-file", "reference-chunk"),
    )
    draft = {
        "meals": [
            {
                "meal_type": "breakfast",
                "dishes": [
                    {
                        "file_id": "reference-file",
                        "chunk_id": "reference-chunk",
                        "name": "清粥",
                        "ingredients": ["大米100克"],
                        "steps": ["加水煮熟"],
                        "portion_quote": "个人建议一人份",
                    }
                ],
            }
        ],
        "purchase_items": [{"sku_id": "sku-rice", "quantity": 1, "ingredient_refs": ["大米100克"]}],
        "purchase_gaps": [],
    }
    builder = StateGraph(MessagesState, context_schema=BaseContext)
    builder.add_node("tools", ToolNode([save_reference_meal_plan], handle_tool_errors=False))
    builder.add_edge(START, "tools")
    builder.add_edge("tools", END)
    graph = builder.compile(checkpointer=InMemorySaver(), transformers=[ToolCallTransformer])
    config = {"configurable": {"thread_id": context.thread_id}}
    collector = ToolMessageAuditCollector(
        run_id=context.run_id, request_id=context.request_id, thread_id=context.thread_id, worker_id=context.worker_id
    )
    first_failed_audit = None
    plan = None
    for attempt in range(2):
        call_id = str(uuid4())
        call = {"id": call_id, "name": "save_reference_meal_plan", "args": deepcopy(draft), "type": "tool_call"}
        model_operation = str(uuid4())
        async with sessions.begin() as db:
            repo = ModelMessageAuditRepository(db)
            await repo.start(
                run_id=context.run_id,
                request_id=context.request_id,
                thread_id=context.thread_id,
                worker_id=context.worker_id,
                operation_id=model_operation,
                sequence=attempt * 100,
                started_at=utc_now_naive(),
            )
            await repo.finish(
                run_id=context.run_id,
                request_id=context.request_id,
                thread_id=context.thread_id,
                worker_id=context.worker_id,
                operation_id=model_operation,
                content="",
                finished_at=utc_now_naive(),
                duration_ms=0,
                usage=None,
                metadata={"tool_calls": [call]},
            )
        incoming = (
            [HumanMessage("生成早餐", additional_kwargs={"health_request_id": context.request_id})]
            if not attempt
            else []
        ) + [AIMessage(content="", tool_calls=[call])]
        async with await graph.astream_events(
            {"messages": incoming}, context=context, config=config, version="v3", transformers=[CustomTransformer]
        ) as events:
            async for event in events:
                if event["method"] != "tools":
                    continue
                params = event["params"]
                data = dict(params["data"])
                if isinstance(data.get("output"), ToolMessage):
                    data["output"] = data["output"].model_dump()
                await collector.consume(
                    {
                        "method": "tools",
                        "namespace": params["namespace"],
                        "seq": event["seq"],
                        "timestamp": params["timestamp"],
                        "data": data,
                    }
                )
        state = await graph.aget_state(config)
        result = state.values["messages"][-1]
        async with sessions() as db:
            audit = await db.scalar(
                select(Message).where(
                    Message.run_id == context.run_id,
                    Message.operation_id == call_id,
                    Message.message_type == "tool_audit",
                )
            )
            compat = await db.scalar(select(ToolCall).where(ToolCall.langgraph_tool_call_id == call_id))
            assert audit is not None and compat is not None
            if not attempt:
                assert result.status == "error" and audit.execution_status == "failed" and compat.status == "error"
                assert json.loads(audit.content)["error_code"] == "reference_quote_invalid"
                assert not audit.extra_metadata.get("awaiting_run_terminal")
                assert (
                    await db.scalar(
                        select(func.count())
                        .select_from(HealthInitialPlanPreview)
                        .where(HealthInitialPlanPreview.run_id == context.run_id)
                    )
                    == 0
                )
                first_failed_audit = audit.id
            else:
                assert (
                    result.status == "success" and audit.execution_status == "completed" and compat.status == "success"
                )
                plan = json.loads(result.content)
                assert plan["meals"][0]["dishes"][0]["portion_quote"] is None
                assert (
                    len(
                        await service.tool_payloads(
                            db, await db.get(AgentRun, context.run_id), "save_reference_meal_plan"
                        )
                    )
                    == 1
                )
                assert (await db.get(Message, first_failed_audit)).execution_status == "failed"
        draft["meals"][0]["dishes"][0]["portion_quote"] = None
    assert (await planner_final_result(context, json.dumps({"preview_id": plan["preview_id"]})))["preview_id"] == plan[
        "preview_id"
    ]


@pytest.fixture
async def restricted_cooking_current(family_profile_http, monkeypatch):
    """经真实建档接口保留本次反馈中的四项明确限制。"""
    return await setup_reference(
        family_profile_http,
        monkeypatch,
        allergens=["麸质谷物"],
        intolerances=["大豆不耐受"],
        avoidances=["牛羊肉"],
        doctor_instructions="少吃重油重盐",
    )


def cooking_candidate_selection():
    """只选择受控编号，不让模型填写原料、做法或适用性。"""
    return [{"meal_type": "breakfast", "candidate_ids": ["source-hard-cooked-egg", "source-plain-rice"]}]


async def cooking_candidate_write_state(sessions):
    """回读实际计划、采购及每日行内容和 xmin，不以工具次数代替无写入证据。"""
    async with sessions() as db:
        counts = {
            model.__tablename__: await db.scalar(select(func.count()).select_from(model))
            for model in (HealthInitialPlanPreview, HealthMealPlan, HealthPurchasePreview)
        }
        rows = await db.execute(
            text(
                "SELECT id, actor_uid, family_id, plan_date, version, meal_sources, pending, updated_at, "
                "xmin::text AS row_version FROM health_daily_meal_plan ORDER BY id"
            )
        )
        return {"counts": counts, "daily_rows": [dict(row) for row in rows.mappings()]}


@pytest.mark.parametrize("existing_daily", [False, True])
async def test_restricted_cooking_candidates_publish_and_read_without_plan_writes(
    restricted_cooking_current, monkeypatch, existing_daily
):
    """仅上下文回执即可发布并经 HTTP 回读候选，原每日行逐列及 xmin 不变。"""
    current = restricted_cooking_current
    client, sessions, users, _, _, choice = current
    if existing_daily:
        async with sessions.begin() as db:
            db.add(
                HealthDailyMealPlan(
                    id=str(uuid4()),
                    actor_uid="self",
                    family_id=choice["family_id"],
                    plan_date=date.fromisoformat(choice["plan_date"]),
                    version=0,
                    meal_sources={},
                    pending={},
                )
            )
    before = await cooking_candidate_write_state(sessions)
    assert set(before["counts"].values()) == {0}
    assert len(before["daily_rows"]) == int(existing_daily)
    commerce_calls = []

    async def no_purchase(*args, **kwargs):
        """任何外部采购请求都使本候选场景失败。"""
        commerce_calls.append((args, kwargs))
        raise AssertionError("做法资料候选不能调用采购接口")

    monkeypatch.setattr("yuxi.services.daily_commerce_service.commerce_request", no_purchase)
    bound = await bind_reference(current, daily_base_version=0)
    assert bound.status_code == 200, bound.text
    context = await running_context(current, bound.json()["thread_id"], read_products=False)
    catalog = await service.get_reference_context(context)
    assert catalog["restriction_verification"]["status"] == "needs_verification"
    assert catalog["restriction_verification"]["unverified_restrictions"] == [
        "麸质谷物",
        "大豆不耐受",
        "少吃重油重盐",
    ]
    member = catalog["members"][0]
    assert member["allergens"] == ["麸质谷物"]
    assert member["intolerances"] == ["大豆不耐受"]
    assert member["avoidances"] == ["牛羊肉"]
    assert member["doctor_instructions"] == "少吃重油重盐"
    expected = {item["id"]: item for item in catalog["cooking_reference_candidates"]["items"]}
    assert {"source-hard-cooked-egg", "source-plain-rice"}.issubset(expected)
    selection = cooking_candidate_selection()
    result = await planner_final_result(context, json.dumps({"candidate_meals": selection}))
    assert result["status"] == "reference_candidates" and result["scope"] == "cooking_reference"
    assert result["candidate_selection"] == selection
    assert result["purchase_allowed"] is False and result["purchase_items"] == []
    assert result["restriction_verification"]["status"] == "unresolved"
    assert "preview_id" not in result
    assert result["meals"][0]["dishes"] == [expected[cid] for cid in selection[0]["candidate_ids"]]
    assert await complete(current, context, result) == result
    response = await client.get(f"{ROOT}/tasks/{context.request_id}", headers=users["self"])
    assert response.status_code == 200, response.text
    assert response.json()["result"] == {
        "result_type": "meal_plan_candidates",
        "validation": "current_business_sources",
        "data": result,
    }
    assert response.headers["cache-control"] == "no-store"
    history = await client.get(f"/api/chat/thread/{context.thread_id}/history", headers=users["self"])
    assert history.status_code == 200, history.text
    assert "source-hard-cooked-egg" in history.text and "source-plain-rice" in history.text
    async with sessions() as db:
        audits = list(
            (await db.scalars(select(Message).where(Message.run_id == context.run_id, Message.role == "tool"))).all()
        )
        assert [row.extra_metadata["tool_name"] for row in audits] == ["get_reference_plan_context"]
        run = await db.get(AgentRun, context.run_id)
        message = await db.get(Message, run.output_message_id)
        assert json.loads(message.content) == result and run.status == "completed"
    assert commerce_calls == []
    assert await cooking_candidate_write_state(sessions) == before


@pytest.mark.parametrize("tamper", ["steps", "source_hash", "purchase", "status", "member"])
async def test_restricted_cooking_candidates_reject_tampered_publication_and_task_result(
    restricted_cooking_current, tamper
):
    """发布前拒绝改写，已完成消息被篡改时真实 HTTP 也不展示伪造结果。"""
    current = restricted_cooking_current
    bound = await bind_reference(current)
    assert bound.status_code == 200, bound.text
    context = await running_context(current, bound.json()["thread_id"], read_products=False)
    result = await planner_final_result(context, json.dumps({"candidate_meals": cooking_candidate_selection()}))
    await complete(current, context, result)
    changed = deepcopy(result)
    if tamper == "steps":
        changed["meals"][0]["dishes"][0]["steps"] = ["模型编造的做法"]
    elif tamper == "source_hash":
        changed["meals"][0]["dishes"][0]["source"]["content_hash"] = "0" * 64
    elif tamper == "purchase":
        changed.update(purchase_allowed=True, purchase_items=[{"sku_id": "invented", "quantity": 1}])
    elif tamper == "status":
        changed["status"] = "reference_ready"
    else:
        changed["members"][0]["allergens"] = []
    content = json.dumps(changed, ensure_ascii=False)
    async with current[1].begin() as db:
        run = await db.get(AgentRun, context.run_id)
        with pytest.raises(HealthVisionError, match="source_invalidated"):
            await validate_initial_planner_publication(db, run, content)
        message = await db.get(Message, run.output_message_id)
        message.content = content
    response = await current[0].get(f"{ROOT}/tasks/{context.request_id}", headers=current[2]["self"])
    assert response.status_code == 410, response.text
    assert "meal_plan_candidates" not in response.text
    state = await cooking_candidate_write_state(current[1])
    assert set(state["counts"].values()) == {0} and state["daily_rows"] == []


async def test_restricted_cooking_candidates_reserved_request_has_recoverable_terminal(restricted_cooking_current):
    """请求索引保留恢复入口，候选完成后每日餐次及版本仍为空且停止等待。"""
    from yuxi.services.daily_meal_plan_service import reserve_reference_request

    current = restricted_cooking_current
    client, sessions, users, _, _, choice = current
    bound = await bind_reference(current, daily_base_version=0)
    assert bound.status_code == 200, bound.text
    context = await running_context(current, bound.json()["thread_id"], read_products=False)
    async with sessions.begin() as db:
        binding, _ = await require_consultation(db, "self", context.thread_id)
        request = await db.scalar(select(AgentRunRequest).where(AgentRunRequest.request_id == context.request_id))
        await reserve_reference_request(db, "self", binding, request)
    path = f"/api/family/{choice['family_id']}/daily-meal-plans/{choice['plan_date']}"
    pending = await client.get(path, headers=users["self"])
    assert pending.status_code == 200 and pending.json()["pending"]["status"] == "running", pending.text
    result = await planner_final_result(context, json.dumps({"candidate_meals": cooking_candidate_selection()}))
    await complete(current, context, result)
    response = await client.get(path, headers=users["self"])
    assert response.status_code == 200, response.text
    daily = response.json()
    assert daily["version"] == 0 and daily["meals"] == [] and daily["purchase_options"] == []
    assert daily["pending"] == {
        "status": "reference_candidates",
        "request_id": context.request_id,
        "thread_id": context.thread_id,
        "member_id": current[3],
        "selection": {**choice, "daily_base_version": 0},
    }
    after = await cooking_candidate_write_state(sessions)
    assert set(after["counts"].values()) == {0}
    assert len(after["daily_rows"]) == 1 and after["daily_rows"][0]["meal_sources"] == {}


@pytest.mark.parametrize("fault", ["missing", "incomplete", "other_run"])
async def test_restricted_cooking_candidates_require_completed_same_run_context(restricted_cooking_current, fault):
    """其他 Run 或未完成的上下文审计不能作为候选资料依据。"""
    current = restricted_cooking_current
    bound = await bind_reference(current)
    assert bound.status_code == 200, bound.text
    context = await running_context(
        current, bound.json()["thread_id"], read_context=fault != "missing", read_products=False
    )
    if fault == "incomplete":
        async with current[1].begin() as db:
            audit = await db.scalar(select(Message).where(Message.run_id == context.run_id, Message.role == "tool"))
            audit.execution_status = "running"
    elif fault == "other_run":
        async with current[1].begin() as db:
            previous = await db.get(AgentRun, context.run_id)
            previous.status, previous.finished_at = "failed", utc_now_naive()
            previous.worker_id, previous.lease_expires_at = None, None
        context = await running_context(current, bound.json()["thread_id"], read_context=False, read_products=False)
    with pytest.raises(HealthVisionError, match="reference_receipt_invalid"):
        await planner_final_result(context, json.dumps({"candidate_meals": cooking_candidate_selection()}))
    state = await cooking_candidate_write_state(current[1])
    assert set(state["counts"].values()) == {0} and state["daily_rows"] == []


@pytest.mark.parametrize("change", ["profile", "source"])
async def test_restricted_cooking_candidates_recheck_changed_profile_and_source_hash(
    restricted_cooking_current, monkeypatch, tmp_path, change
):
    """已完成候选仍须重验当前真实档案和受控来源，变更后不再公开旧资料。"""
    current = restricted_cooking_current
    bound = await bind_reference(current)
    assert bound.status_code == 200, bound.text
    context = await running_context(current, bound.json()["thread_id"], read_products=False)
    result = await planner_final_result(context, json.dumps({"candidate_meals": cooking_candidate_selection()}))
    await complete(current, context, result)
    if change == "profile":
        body = deepcopy(current[1].reference_profile_input)
        body["client_request_id"] = str(uuid4())
        body["members"][0]["dietary"]["clinicianGuidance"] += "；另需限制蛋白质"
        response = await current[0].post(
            f"/api/family/{current[-1]['family_id']}/miniapp-profile",
            headers={**current[2]["self"], "Idempotency-Key": body["client_request_id"]},
            json=body,
        )
        assert response.status_code == 200, response.text
    else:
        from yuxi.services import restricted_cooking_reference_service as cooking

        data = json.loads(cooking.DATA_PATH.read_text(encoding="utf-8"))
        item = next(entry for entry in data["references"] if entry["id"] == "source-hard-cooked-egg")
        item["source"]["notes"] += "（已核对的新整理稿版本）"
        material = deepcopy(item)
        material["source"].pop("content_hash")
        item["source"]["content_hash"] = hashlib.sha256(
            json.dumps(material, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        path = tmp_path / "changed-cooking-references.json"
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        monkeypatch.setattr(cooking, "DATA_PATH", path)
    async with current[1]() as db:
        run = await db.get(AgentRun, context.run_id)
        with pytest.raises(HealthVisionError, match="source_invalidated"):
            await validate_initial_planner_publication(db, run, json.dumps(result, ensure_ascii=False))
    response = await current[0].get(f"{ROOT}/tasks/{context.request_id}", headers=current[2]["self"])
    assert response.status_code == 410, response.text
    assert "source-hard-cooked-egg" not in response.text
    state = await cooking_candidate_write_state(current[1])
    assert set(state["counts"].values()) == {0} and state["daily_rows"] == []

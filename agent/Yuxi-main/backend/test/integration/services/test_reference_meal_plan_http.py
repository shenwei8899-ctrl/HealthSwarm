"""真实TCP和隔离PG核对参考餐单的来源、权限与回读；模型和商城使用合成输入。"""

# ruff: noqa: F401,F811 -- 复用真实HTTP及隔离schema fixture。
import json
from copy import deepcopy
from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage, ToolMessage
from langgraph.graph import StateGraph, MessagesState, START, END
from langgraph.prebuilt import ToolNode
from sqlalchemy import func, select

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
    HealthFamilyProfileLink,
    HealthInitialPlanPreview,
    HealthMealPlan,
    HealthProfessionalReview,
    HealthRuleSnapshot,
    RecipeVersion,
)
from yuxi.storage.postgres.models_knowledge import KnowledgeBase, KnowledgeFile, KnowledgeChunk
from yuxi.utils.datetime_utils import utc_now_naive

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]
ROOT = "/api/health/v1"
TEXT = "清粥\n大米100克\n加水煮熟\n原食谱供两人食用"
SKU = {
    "sku_id": "sku-rice",
    "product_id": "rice",
    "product_name": "合成大米",
    "sku_name": "一袋",
    "net_content": {"value": "500", "unit": "g"},
    "price_cent": 500,
    "available_quantity": 5,
    "sale_status": "available",
    "ingredients": [],
    "allergen_codes": [],
    "data_completeness": "partial",
}


async def setup_reference(fixture, monkeypatch, *, allergens=None, avoidances=None, intolerances=None):
    """正式建档和同意接口，无正式规则或菜谱，绑定当前知识文件。"""
    client, sessions, users = fixture
    monkeypatch.setenv("HEALTH_RECIPE_KB_ID", "synthetic-reference-kb")
    monkeypatch.setenv("HEALTH_COMMERCE_SOURCE_SECRET", "synthetic-reference-source-secret-at-least-32-chars")

    async def skill(self, slug):
        return SimpleNamespace(source_type="builtin", enabled=True)

    async def runtime(*args):
        return []

    async def catalog():
        return {"version": "synthetic-v1", "items": [deepcopy(SKU)]}

    async def knowledge(context, query):
        """仅替代外部向量检索，文件和正文仍从真实PG回读。"""
        return {
            "status": "found",
            "sources": [{"file_id": "reference-file", "chunk_id": "reference-chunk", "content": TEXT}],
        }

    monkeypatch.setattr(SkillRepository, "get_by_slug", skill)
    monkeypatch.setattr(health_task_service, "health_task_runtime_blockers", runtime)
    monkeypatch.setattr(service, "current_catalog", catalog)
    monkeypatch.setattr(service, "search_family_nutrition_knowledge", knowledge)
    family, _, body, headers = await input_for(client, users["self"])
    body.pop("processing_consents")
    if allergens:
        body["members"][0]["dietary"].update(allergyStatus="set", allergies=allergens)
    if avoidances:
        body["members"][0]["dietary"].update(avoidanceStatus="set", avoidances=avoidances)
    if intolerances:
        body["members"][0]["dietary"].update(intoleranceStatus="set", intolerances=intolerances)
    saved = await client.post(f"/api/family/{family['id']}/miniapp-profile", json=body, headers=headers)
    assert saved.status_code == 200, saved.text
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
                filename="合成清粥.md",
                status="indexed",
                content_hash="synthetic-v1",
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


async def bind_reference(current, **changes):
    """通过统一任务HTTP入口创建真实固定选择线程。"""
    client, _, users, mid, _, choice = current
    key = str(uuid4())
    payload = {"task_type": "reference_meal_preview", "client_request_id": key, "selection": {**choice, **changes}}
    response = await client.post(
        f"{ROOT}/members/{mid}/task-entries", json=payload, headers={**users["self"], "Idempotency-Key": key}
    )
    return response


async def running_context(current, thread):
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
    return BaseContext(
        uid="self",
        thread_id=thread,
        request_id=qid,
        run_id=rid,
        worker_id="synthetic-reference",
        model=processing["model"],
    )


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


async def grounded_plan(current, context, *, quantity=1, meal_type="breakfast", meal_types=None):
    """真实服务读取PG原文并保存，采购只选择已见的合成SKU。"""
    sessions = current[1]
    initial = await receipt(
        sessions, context, "get_reference_plan_context", await service.get_reference_context(context)
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
                        {"name": "save_reference_meal_plan", "args": draft, "id": str(uuid4()), "type": "tool_call"}
                    ],
                )
            ]
        },
        context=context,
    )
    plan = json.loads(output["messages"][-1].content)
    saved = await receipt(sessions, context, "save_reference_meal_plan", plan)
    await require_consultation_attempt(context, [initial, searched, opened, saved])
    return plan, opened, draft


async def complete(current, context, plan):
    """由实际发布校验产生完整结果，再建立权威输出指针。"""
    result = await planner_final_result(context, json.dumps({"preview_id": plan["preview_id"]}))
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
    choice = current[-1]
    path = f"/api/family/{choice['family_id']}/daily-meal-plans/{choice['plan_date']}"
    response = await current[0].get(path, headers=current[2]["self"])
    assert response.status_code == 200, response.text
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
        assert response.status_code == 200 and response.json() == result, response.text
        assert response.headers["cache-control"] == "no-store"
    task = await client.get(f"{ROOT}/tasks/{context.request_id}", headers=users["self"])
    assert task.status_code == 200, task.text
    assert task.json()["task_type"] == "reference_meal_preview"
    assert task.json()["result"]["data"] == result
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
        (f"/api/chat/thread/{context.thread_id}/history", 404),
    ):
        response = await client.get(path, headers=users["self"])
        assert response.status_code == expected, response.text
        assert "大米100克" not in response.text


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
        # 构造升级前已持久化的字段与回执，读取和购买仍走真实HTTP。
        plan.pop("purchase_status")
        plan.pop("purchase_gaps")
        item = plan["purchase_items"][0]
        for field in ("facts_version", "product_description", "description_truncated", "ingredient_refs"):
            item.pop(field)
        item["facts_hash"] = service.input_fingerprint(service.product_facts(SKU))
        async with current[1].begin() as db:
            row = await db.get(HealthInitialPlanPreview, plan["preview_id"])
            row.snapshot = {k: v for k, v in plan.items() if k != "preview_id"}
            audits = (
                await db.scalars(
                    select(Message).where(Message.run_id == context.run_id, Message.message_type == "tool_audit")
                )
            ).all()
            for audit in audits:
                if (audit.extra_metadata or {}).get("tool_name") == "save_reference_meal_plan":
                    audit.content = json.dumps(plan, ensure_ascii=False)
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
    async def changed_catalog():
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

    async def conflicting_catalog():
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
        async with current[1].begin() as db:
            chunk = await db.scalar(select(KnowledgeChunk))
            chunk.content = TEXT + "\n" + ingredient
    else:

        async def uncertain_catalog():
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
        async with current[1].begin() as db:
            chunk = await db.scalar(select(KnowledgeChunk))
            chunk.content = TEXT + "\n" + ingredient
    else:

        async def previous_catalog():
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
        (f"/api/chat/thread/{context.thread_id}/history", 404),
    ):
        response = await current[0].get(path, headers=current[2]["self"])
        assert response.status_code == status, response.text
        assert "大米100克" not in response.text

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
        assert "大米100克" in doc["content"]
        assert len(doc["content"]) <= 18002


async def test_exact_cooking_title_is_not_displaced_by_clinical_semantic_hits(family_profile_http, monkeypatch):
    """标题命中先于更早排序的正文命中，疾病菜单不能占满结果。"""
    current = await setup_reference(family_profile_http, monkeypatch)
    async with current[1].begin() as db:
        file = await db.scalar(select(KnowledgeFile))
        file.filename = "烹饪菜谱｜清粥.md"
        first = await db.scalar(select(KnowledgeChunk))
        first.content = "大米100克\n加水煮熟"
        for index in range(5):
            fid = f"competing-file-{index}"
            title = "USDA家庭菜谱｜粥.md" if index == 0 else f"官方菜单集合｜{index}粥临床资料.md"
            db.add(
                KnowledgeFile(
                    file_id=fid,
                    kb_id="synthetic-reference-kb",
                    filename=title,
                    status="indexed",
                    content_hash="synthetic-competition",
                )
            )
            await db.flush()
            db.add(
                KnowledgeChunk(
                    chunk_id=f"competing-chunk-{index}",
                    file_id=fid,
                    kb_id="synthetic-reference-kb",
                    chunk_index=0,
                    content="大米100克\n加水煮熟" if index == 0 else "合成竞争资料，粥",
                )
            )
        db.add(
            KnowledgeFile(
                file_id="earlier-body-file",
                kb_id="synthetic-reference-kb",
                filename="烹饪菜谱｜A早餐.md",
                status="indexed",
                content_hash="synthetic-body-competition",
            )
        )
        await db.flush()
        db.add(
            KnowledgeChunk(
                chunk_id="earlier-body-chunk",
                file_id="earlier-body-file",
                kb_id="synthetic-reference-kb",
                chunk_index=0,
                content="粥\n大米100克\n加水煮熟",
            )
        )

    async def unrelated_vector(*args):
        raise AssertionError("精确标题命中时不应再调用语义检索")

    monkeypatch.setattr(service, "search_family_nutrition_knowledge", unrelated_vector)
    bound = await bind_reference(current)
    context = await running_context(current, bound.json()["thread_id"])
    hits = await service.search_reference_recipes(context, "早餐 粥 制作方法")
    assert hits["items"][0]["filename"] == "烹饪菜谱｜清粥.md"
    assert hits["items"][0]["chunk_id"] == "reference-chunk"
    assert hits["items"][1]["filename"] == "USDA家庭菜谱｜粥.md"
    assert hits["items"][2]["file_id"] == "earlier-body-file"
    assert len(hits["items"]) == 3


async def test_home_recipe_title_precedes_other_cooking_matches(family_profile_http, monkeypatch):
    """受控家常菜谱不能因旧前缀遗漏或其他来源先排满四项而丢失。"""
    current = await setup_reference(family_profile_http, monkeypatch)
    async with current[1].begin() as db:
        file = await db.scalar(select(KnowledgeFile))
        file.filename = "家常菜谱_红豆米饭_Red Beans and Rice.md"
        for index in range(4):
            fid = f"cooking-rice-{index}"
            db.add(
                KnowledgeFile(
                    file_id=fid,
                    kb_id=file.kb_id,
                    filename=f"烹饪菜谱｜{index}米饭配菜.md",
                    status="indexed",
                    content_hash="synthetic-competing-cooking",
                )
            )
            await db.flush()
            db.add(
                KnowledgeChunk(
                    chunk_id=f"cooking-rice-chunk-{index}",
                    file_id=fid,
                    kb_id=file.kb_id,
                    chunk_index=0,
                    content="合成米饭配菜参考",
                )
            )

    async def unexpected_fallback(*args):
        raise AssertionError("已索引家常菜谱应由固定库直接检索")

    monkeypatch.setattr(service, "search_family_nutrition_knowledge", unexpected_fallback)
    bound = await bind_reference(current)
    context = await running_context(current, bound.json()["thread_id"])
    hits = await service.search_reference_recipes(context, "米饭")
    assert len(hits["items"]) == 4
    assert hits["items"][0]["file_id"] == "reference-file"
    await receipt(current[1], context, "search_reference_recipes", hits)
    opened = await service.read_reference_recipe(context, "reference-file", "reference-chunk")
    assert opened["content"] == TEXT


async def test_home_recipe_catalog_is_bounded_and_does_not_authorize_reading(family_profile_http, monkeypatch):
    """目录只列固定库的当前家常标题，不扫描正文或替代检索回执。"""
    current = await setup_reference(family_profile_http, monkeypatch)
    first_name = "家常菜谱_00清粥.md"
    names = [first_name, *(f"家常菜谱_合成{i:02}.md" for i in range(61))]
    async with current[1].begin() as db:
        file = await db.scalar(select(KnowledgeFile))
        file.filename = first_name
        db.add(KnowledgeBase(kb_id="other-home-kb", name="其他合成库", kb_type="milvus"))
        await db.flush()
        for index, name in enumerate(names[1:]):
            db.add(
                KnowledgeFile(
                    file_id=f"home-catalog-{index}",
                    kb_id=file.kb_id,
                    filename=name,
                    status="indexed",
                    content_hash="synthetic-home-catalog",
                )
            )
        for index, (kb, status, folder, prefix) in enumerate(
            [
                ("other-home-kb", "indexed", False, "家常菜谱_"),
                (file.kb_id, "pending", False, "家常菜谱_"),
                (file.kb_id, "indexed", True, "家常菜谱_"),
                (file.kb_id, "indexed", False, "分类目录_"),
                (file.kb_id, "indexed", False, "家常菜谱X"),
            ]
        ):
            db.add(
                KnowledgeFile(
                    file_id=f"excluded-home-{index}",
                    kb_id=kb,
                    filename=f"{prefix}000排除{index}.md",
                    status=status,
                    is_folder=folder,
                    content_hash="synthetic-excluded-home",
                )
            )
            await db.flush()
            db.add(
                KnowledgeChunk(
                    chunk_id=f"excluded-home-chunk-{index}",
                    file_id=f"excluded-home-{index}",
                    kb_id=kb,
                    chunk_index=0,
                    content="排除材料的合成做法",
                )
            )
    bound = await bind_reference(current)
    context = await running_context(current, bound.json()["thread_id"])
    catalog = await service.get_reference_context(context)
    assert catalog["recipe_catalog"] == sorted(names)[:60]
    await receipt(current[1], context, "get_reference_plan_context", catalog)
    with pytest.raises(HealthVisionError, match="reference_receipt_invalid"):
        await service.read_reference_recipe(context, "reference-file", "reference-chunk")
    calls = []

    async def empty_fallback(context, query):
        """普通来源过滤后无候选，保留固定库的原有后备检索。"""
        calls.append(query)
        return {"status": "insufficient_material", "sources": []}

    monkeypatch.setattr(service, "search_family_nutrition_knowledge", empty_fallback)
    hits = await service.search_reference_recipes(context, "排除")
    assert calls == ["排除"]
    assert hits["items"] == []


async def test_english_meat_in_source_cannot_bypass_chinese_avoidance(family_profile_http, monkeypatch):
    """当前原文中的英文忌口即使未被模型摘录也不能形成保存结果。"""
    current = await setup_reference(family_profile_http, monkeypatch, avoidances=["牛羊肉"])
    async with current[1].begin() as db:
        chunk = await db.scalar(select(KnowledgeChunk))
        chunk.content = TEXT + "\nOptional beef broth"
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

    async def conflicting_catalog():
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
    """普通菜谱正文可命中食材，目录和疾病标题不能令其失去打开资格。"""
    current = await setup_reference(family_profile_http, monkeypatch)
    async with current[1].begin() as db:
        file = await db.scalar(select(KnowledgeFile))
        file.filename = "烹饪菜谱｜早餐糊.md"
        first = await db.scalar(select(KnowledgeChunk))
        first.content = "来源与介绍"
        db.add_all(
            [
                KnowledgeChunk(
                    chunk_id="cooking-body-hit",
                    file_id=file.file_id,
                    kb_id=file.kb_id,
                    chunk_index=1,
                    content="早餐糊\n燕麦30克\n加水煮熟",
                ),
                KnowledgeChunk(
                    chunk_id="cooking-body-duplicate",
                    file_id=file.file_id,
                    kb_id=file.kb_id,
                    chunk_index=2,
                    content="燕麦的附注",
                ),
            ]
        )
        for index in range(5):
            fid = f"directory-oat-{index}"
            db.add(
                KnowledgeFile(
                    file_id=fid,
                    kb_id=file.kb_id,
                    filename=f"分类目录｜燕麦粥{index}.md" if index < 4 else "疾病食养｜燕麦粥.md",
                    status="indexed",
                    content_hash="synthetic-directory",
                )
            )
            await db.flush()
            db.add(
                KnowledgeChunk(
                    chunk_id=f"directory-oat-chunk-{index}",
                    file_id=fid,
                    kb_id=file.kb_id,
                    chunk_index=0,
                    content="燕麦粥目录，无食材和制作步骤",
                )
            )

    async def unrelated_vector(*args):
        raise AssertionError("普通烹饪正文命中时不应被疾病语义检索替代")

    monkeypatch.setattr(service, "search_family_nutrition_knowledge", unrelated_vector)
    bound = await bind_reference(current)
    context = await running_context(current, bound.json()["thread_id"])
    hits = await service.search_reference_recipes(context, "早餐 燕麦 制作方法")
    assert [(item["file_id"], item["chunk_id"]) for item in hits["items"]] == [("reference-file", "cooking-body-hit")]
    await receipt(current[1], context, "search_reference_recipes", hits)
    opened = await service.read_reference_recipe(context, "reference-file", "cooking-body-hit")
    assert "燕麦30克" in opened["content"]
    with pytest.raises(HealthVisionError, match="reference_receipt_invalid"):
        await service.read_reference_recipe(context, "directory-oat-0", "directory-oat-chunk-0")


async def test_cooking_body_search_keeps_current_kb_and_indexed_file_boundary(family_profile_http, monkeypatch):
    """正文召回不能把别库、未索引文件或目录当成当前菜谱。"""
    current = await setup_reference(family_profile_http, monkeypatch)
    async with current[1].begin() as db:
        db.add(KnowledgeBase(kb_id="other-recipe-kb", name="其他合成库", kb_type="milvus"))
        await db.flush()
        for index, (kb, status, folder) in enumerate(
            [
                ("other-recipe-kb", "indexed", False),
                ("synthetic-reference-kb", "pending", False),
                ("synthetic-reference-kb", "indexed", True),
            ]
        ):
            fid = f"excluded-cooking-{index}"
            db.add(
                KnowledgeFile(
                    file_id=fid,
                    kb_id=kb,
                    filename=f"烹饪菜谱｜早餐糊{index}.md",
                    status=status,
                    is_folder=folder,
                    content_hash="synthetic-excluded",
                )
            )
            await db.flush()
            db.add(
                KnowledgeChunk(
                    chunk_id=f"excluded-chunk-{index}",
                    file_id=fid,
                    kb_id=kb,
                    chunk_index=0,
                    content="燕麦30克 加水煮熟",
                )
            )
    calls = []

    async def semantic(context, query):
        calls.append(query)
        return {"status": "empty", "sources": []}

    monkeypatch.setattr(service, "search_family_nutrition_knowledge", semantic)
    bound = await bind_reference(current)
    context = await running_context(current, bound.json()["thread_id"])
    hits = await service.search_reference_recipes(context, "燕麦")
    assert calls == ["燕麦"]
    assert hits["items"] == []


async def test_no_title_match_keeps_the_fixed_kb_semantic_search(family_profile_http, monkeypatch):
    """标题未知时继续使用原检索Owner，不制造空命中或换库。"""
    current = await setup_reference(family_profile_http, monkeypatch)
    calls = []

    async def semantic(context, query):
        calls.append(query)
        return {
            "status": "ok",
            "sources": [{"file_id": "reference-file", "chunk_id": "reference-chunk", "content": TEXT}],
        }

    monkeypatch.setattr(service, "search_family_nutrition_knowledge", semantic)
    bound = await bind_reference(current)
    context = await running_context(current, bound.json()["thread_id"])
    hits = await service.search_reference_recipes(context, "没有标题的语义主题")
    assert calls == ["没有标题的语义主题"]
    assert hits["items"][0]["file_id"] == "reference-file"


async def test_empty_purchase_explains_reason_and_cannot_claim_catalog_failure(family_profile_http, monkeypatch):
    current = await setup_reference(family_profile_http, monkeypatch)
    bound = await bind_reference(current)
    context = await running_context(current, bound.json()["thread_id"])
    _, _, draft = await grounded_plan(current, context)
    draft["purchase_items"] = []
    draft["purchase_gaps"] = [{"ingredient": "大米100克", "reason": "catalog_unavailable", "detail": "目录不可用"}]
    with pytest.raises(HealthVisionError, match="reference_purchase_reason_invalid"):
        await service.save_reference_plan(context, draft)
    draft["purchase_gaps"][0].update(reason="needs_confirmation", detail="请确认包装是否满足采购需求")
    plan = await service.save_reference_plan(context, draft)
    assert plan["status"] == "reference_ready"
    assert plan["purchase_status"] == "unselected"
    assert plan["purchase_gaps"] == draft["purchase_gaps"]


async def test_changed_product_description_requires_fresh_selection(family_profile_http, monkeypatch):
    current = await setup_reference(family_profile_http, monkeypatch)
    bound = await bind_reference(current)
    context = await running_context(current, bound.json()["thread_id"])
    _, _, draft = await grounded_plan(current, context)

    async def changed_catalog():
        return {"version": "changed-description", "items": [{**SKU, "product_description": "商品含花生"}]}

    monkeypatch.setattr(service, "current_catalog", changed_catalog)
    with pytest.raises(HealthVisionError, match="reference_product_changed"):
        await service.save_reference_plan(context, draft)


@pytest.mark.parametrize("failure_first", [True, False])
async def test_latest_catalog_receipt_decides_unavailability_reason(family_profile_http, monkeypatch, failure_first):
    """重试恢复后的旧错误不能解释空采购，最新失败仍可保留餐单。"""
    current = await setup_reference(family_profile_http, monkeypatch)
    bound = await bind_reference(current)
    context = await running_context(current, bound.json()["thread_id"])
    original = service.current_catalog

    async def fail():
        raise HealthVisionError("commerce_unavailable", "测试目录暂不可用", 503)

    async def failed_receipt():
        monkeypatch.setattr(service, "current_catalog", fail)
        await receipt(current[1], context, "get_reference_plan_context", await service.get_reference_context(context))
        monkeypatch.setattr(service, "current_catalog", original)

    if failure_first:
        await failed_receipt()
    _, _, draft = await grounded_plan(current, context)
    if not failure_first:
        await failed_receipt()
    draft.update(
        purchase_items=[],
        purchase_gaps=[{"ingredient": "大米100克", "reason": "catalog_unavailable", "detail": "商品目录暂不可用"}],
    )
    if failure_first:
        with pytest.raises(HealthVisionError, match="reference_purchase_reason_invalid"):
            await service.save_reference_plan(context, draft)
    else:
        assert (await service.save_reference_plan(context, draft))["purchase_status"] == "unselected"

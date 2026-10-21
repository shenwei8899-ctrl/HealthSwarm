"""隔离API、worker、PG和SSE的配餐师发布与最终输出验收。"""

import json
import os
from types import SimpleNamespace
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import select, delete

from test.e2e.test_health_consultation_e2e import collect_sse, drain_requests, isolated_health  # noqa: F401
from test.integration.services.test_health_vision_http import ROOT, create_member, health_http  # noqa: F401
from test.integration.services.test_health_meal_planner_http import publish_planner_recipe
from yuxi.agents.context import BaseContext
from yuxi.services.health_meal_plan_service import meal_plan_recipes_for_run
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_business import AgentRun, AgentRunRequest, Message
from yuxi.storage.postgres.models_health import DietLog, HealthMealPlan, HealthMealPlanPreview
from yuxi.storage.postgres.models_knowledge import KnowledgeBase, KnowledgeFile, KnowledgeChunk

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.e2e,
    pytest.mark.slow,
    pytest.mark.skipif(os.getenv("HEALTH_CONSULTATION_E2E_ISOLATED") != "true", reason="仅独立合成槽位"),
]


@pytest_asyncio.fixture
async def planner_recipe_library(isolated_health):  # noqa: F811
    """固定隔离库用合成分片和本地向量，不调用外部嵌入。"""
    from pymilvus import utility
    from yuxi.knowledge.implementations.milvus import MilvusKB
    from yuxi.knowledge.cache import delete_cached_kb_config

    kb_id = "pytest_planner_recipes"
    assert os.environ.get("HEALTH_RECIPE_KB_ID") == kb_id
    executor = MilvusKB(work_dir=f"test/.tmp/planner-reference-{uuid4().hex}")
    assert not utility.has_collection(kb_id, using=executor.connection_alias)
    file_id, chunk_id = str(uuid4()), str(uuid4())
    content = "syntheticrecipe steaming method only"
    collection = None
    created_kb = False
    try:
        async with pg_manager.get_async_session_context() as session:
            assert await session.scalar(select(KnowledgeBase).where(KnowledgeBase.kb_id == kb_id)) is None
            session.add(
                KnowledgeBase(
                    kb_id=kb_id, name=kb_id, kb_type="milvus", embedding_model_spec="siliconflow-cn:BAAI/bge-m3"
                )
            )
            await session.flush()
            session.add(
                KnowledgeFile(
                    file_id=file_id, kb_id=kb_id, filename="synthetic-recipe.md", status="indexed", content_hash="v1"
                )
            )
            await session.flush()
            session.add(KnowledgeChunk(chunk_id=chunk_id, file_id=file_id, kb_id=kb_id, chunk_index=0, content=content))
            await session.commit()
            created_kb = True
        await delete_cached_kb_config(kb_id)
        collection = executor._create_new_collection(
            kb_id, SimpleNamespace(dimension=1024, model_id="BAAI/bge-m3"), kb_id
        )
        collection.insert(
            [
                {
                    "id": chunk_id,
                    "content": content,
                    "chunk_id": chunk_id,
                    "file_id": file_id,
                    "chunk_index": 0,
                    "embedding": [0.0] * 1023 + [1.0],
                }
            ]
        )
        collection.flush()
        collection.load()
        yield chunk_id
    finally:
        if collection is not None:
            collection.drop()
        if created_kb:
            async with pg_manager.get_async_session_context() as session:
                await session.execute(delete(KnowledgeBase).where(KnowledgeBase.kb_id == kb_id))
                await session.commit()
            await delete_cached_kb_config(kb_id)


async def test_planner_worker_authoritative_result_independent_consent_and_forged_receipts(
    isolated_health,  # noqa: F811
    planner_recipe_library,
):
    """当前Run回执成功投影；伪造审核字段和跨Run回执都不能成功。"""
    client, users, configuration, consultation_model = isolated_health
    headers, admin = users[0]["headers"], users[2]["headers"]
    provider = f"planner-replay-{uuid4().hex[:12]}"
    created = await client.post(
        "/api/system/model-providers",
        headers=admin,
        json={
            "provider_id": provider,
            "display_name": "Synthetic planner only",
            "provider_type": "openai",
            "base_url": "http://api:8768/v1",
            "api_key": "synthetic-planner-key",
            "capabilities": ["chat"],
            "enabled_models": [
                {
                    "id": "deterministic-meal-plan-20261006",
                    "display_name": "synthetic",
                    "type": "chat",
                    "source": "manual",
                }
            ],
            "is_enabled": True,
        },
    )
    assert created.status_code == 200, created.text
    requests = []
    member = await create_member(client, headers)
    key = str(uuid4())
    bound = await client.post(f"{ROOT}/members/{member}/meal-planner", headers=headers, json={"client_request_id": key})
    assert bound.status_code == 201, bound.text
    thread = bound.json()["thread_id"]
    body = {"agent_slug": "health-meal-planner", "thread_id": thread, "query": "synthetic"}
    try:
        assert not configuration["meal_plan"]["available"]
        unavailable = await client.post(
            "/api/agent/runs", headers=headers, json={**body, "meta": {"request_id": str(uuid4())}}
        )
        assert unavailable.status_code == 503, unavailable.text
        configured = await client.put(
            f"{ROOT}/configuration",
            headers=admin,
            json={
                "consultation_model": consultation_model,
                "meal_plan_model": f"{provider}:deterministic-meal-plan-20261006",
                "policy_version": configuration["policy_version"],
                "cloud_processing_reviewed": True,
            },
        )
        assert configured.status_code == 200 and configured.json()["meal_plan"]["available"], configured.text
        config = configured.json()
        accepted = await client.post(
            f"{ROOT}/members/{member}/processing-consents",
            headers=headers,
            json={
                "purpose": "consultation",
                "accepted": True,
                "processor": config["consultation"]["processor"],
                "policy_version": config["policy_version"],
            },
        )
        assert accepted.status_code == 200
        denied_key = str(uuid4())
        denied = await client.post(
            "/api/agent/runs", headers=headers, json={**body, "meta": {"request_id": denied_key}}
        )
        assert denied.status_code == 403, denied.text
        async with pg_manager.get_async_session_context() as session:
            for model in (AgentRunRequest, AgentRun, Message):
                assert await session.scalar(select(model).where(model.request_id == denied_key)) is None
        consent = await client.post(
            f"{ROOT}/members/{member}/processing-consents",
            headers=headers,
            json={
                "purpose": "meal_plan",
                "accepted": True,
                "processor": config["meal_plan"]["processor"],
                "policy_version": config["policy_version"],
            },
        )
        assert consent.status_code == 200, consent.text
        first_preview = None
        for mode, expected_status in (
            ("valid", "completed"),
            ("invalid", "failed"),
            ("foreign", "failed"),
            ("questions", "completed"),
            ("reference", "completed"),
        ):
            token, request = uuid4().hex, str(uuid4())
            requests.append(request)
            await publish_planner_recipe(client, admin, f"合成配餐E2E-{token}")
            query = f"HEALTH_MEAL_PLANNER_E2E:{token}:{mode}" + (f":{first_preview}" if mode == "foreign" else "")
            started = await client.post(
                "/api/agent/runs", headers=headers, json={**body, "query": query, "meta": {"request_id": request}}
            )
            assert started.status_code == 200, started.text
            run_id = started.json()["run_id"]
            events = await collect_sse(client, headers, run_id)
            assert events[-1][0] == "end" and events[-1][1]["request_id"] == request
            assert not any("message_delta" in str(event) for _, event in events)
            result = await client.get(f"/api/agent/runs/{run_id}/result", headers=headers)
            assert result.json()["status"] == expected_status, result.text
            async with pg_manager.get_async_session_context() as session:
                run = await session.get(AgentRun, run_id)
                output = (
                    await session.get(Message, run.output_message_id) if run.output_message_id is not None else None
                )
                if expected_status == "completed":
                    assert output.run_id == run_id and output.id == result.json()["final_message_id"]
                if mode in {"valid", "reference"}:
                    final = json.loads(output.content)
                    assert final == json.loads(result.json()["output"])
                    assert final["nutrition"]["totals"]["energy_kcal"] == "300.00"
                    assert final["personalized"] is False and final["professional_review"] == "not_reviewed"
                    first_preview = final["preview_id"]
                    preview = await session.get(HealthMealPlanPreview, first_preview)
                    assert (
                        preview.run_id == run_id
                        and preview.actor_uid == users[0]["uid"]
                        and preview.member_id == member
                    )
                    assert preview.snapshot["nutrition"] == final["nutrition"]
                    assert run.input_payload["health_processing"]["processor"] == config["meal_plan"]["processor"]
                    stale = BaseContext(
                        uid=users[0]["uid"],
                        thread_id=thread,
                        run_id=run_id,
                        request_id=request,
                        worker_id="expired-worker",
                        model=run.input_payload["health_processing"]["model"],
                    )
                    if mode == "reference":
                        audits = list(
                            await session.scalars(
                                select(Message).where(
                                    Message.run_id == run_id,
                                    Message.message_type == "tool_audit",
                                    Message.extra_metadata["tool_name"].as_string()
                                    == "query_family_nutrition_knowledge",
                                )
                            )
                        )
                        assert len(audits) == 1 and audits[0].execution_status == "completed"
                        reference = json.loads(audits[0].content)
                        assert reference["scope"] == "recipe_reference"
                        assert reference["sources"][0]["chunk_id"] == planner_recipe_library
                        reference_request, reference_answer = request, output.content
                elif mode == "questions":
                    assert json.loads(output.content)["status"] == "needs_input"
                else:
                    expected_error = "planner_output_invalid" if mode == "invalid" else "planner_receipt_invalid"
                    assert expected_error in run.error_message
                    assert output is None and result.json()["output"] == ""
                    assert (
                        await session.scalar(
                            select(Message).where(
                                Message.run_id == run_id, Message.role == "assistant", Message.message_type == "text"
                            )
                        )
                        is None
                    )
                assert await session.scalar(select(DietLog).where(DietLog.member_id == member)) is None
                assert await session.scalar(select(HealthMealPlan).where(HealthMealPlan.member_id == member)) is None
            if mode == "valid":
                with pytest.raises(HealthVisionError, match="execution_not_owned"):
                    await meal_plan_recipes_for_run(stale, "合成配餐")
        save_key = str(uuid4())
        saved = await client.post(
            f"{ROOT}/members/{member}/meal-plans",
            headers={**headers, "Idempotency-Key": save_key},
            json={"client_request_id": save_key, "preview_id": first_preview},
        )
        assert saved.status_code == 201 and saved.json()["version"] == 1, saved.text
        async with pg_manager.get_async_session_context() as session:
            chunk = await session.scalar(
                select(KnowledgeChunk).where(KnowledgeChunk.chunk_id == planner_recipe_library)
            )
            chunk.content = "syntheticrecipe changed source"
            await session.commit()
        stale_task = await client.get(f"{ROOT}/tasks/{reference_request}", headers=headers)
        assert stale_task.status_code == 410 and reference_answer not in stale_task.text, stale_task.text
    finally:
        await drain_requests(client, headers, requests)
        reset = await client.put(
            f"{ROOT}/configuration",
            headers=admin,
            json={
                "consultation_model": consultation_model,
                "policy_version": configuration["policy_version"],
                "cloud_processing_reviewed": True,
            },
        )
        assert reset.status_code == 200 and not reset.json()["meal_plan"]["available"]
        assert (await client.delete(f"/api/system/model-providers/{provider}", headers=admin)).status_code == 200

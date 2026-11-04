"""真实 TCP 与独立 PostgreSQL 验证营养候选准备和当前就绪状态。"""

from copy import deepcopy
import json
from types import SimpleNamespace
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import func, select

from test.integration.services.test_health_meal_plan_pagination_http import (
    cleanup_test_sandboxes,  # noqa: F401
    cleanup_test_knowledge_resources,  # noqa: F401
    ensure_live_api_schema,  # noqa: F401
    meal_pagination_http,  # noqa: F401
)
from test.integration.services.test_health_quality_http import proof
from test.unit.services.test_health_quality import rules_payload
from yuxi.config.options import health_vision_opts
from yuxi.services import health_family_kb_service, health_knowledge_import_service, health_vision_provider
from yuxi.services.health_vision_service import health_vision_service
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.storage.postgres.models_business import User, ConfigOption
from yuxi.storage.postgres.models_health import FoodRecord, RecipeVersion, NutritionImportBatch, HealthRuleSnapshot
from yuxi.storage.postgres.models_knowledge import KnowledgeBase, KnowledgeFile, KnowledgeChunk

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]
ROOT = "/api/health/v1/nutrition-setup"


@pytest_asyncio.fixture
async def nutrition_http(meal_pagination_http, monkeypatch):  # noqa: F811
    """本轮所有账号、知识库和营养事实均限定于一次性测试 schema。"""
    current = meal_pagination_http
    for key in ("HEALTH_DAILY_RULE_CODE", "HEALTH_FAMILY_NUTRITION_KB_ID", "HEALTH_RECIPE_KB_ID"):
        monkeypatch.setenv(key, "")
    async with current.sessions() as session:
        connection = await session.connection()
        await connection.run_sync(KnowledgeBase.metadata.create_all)
        session.add(
            ConfigOption(
                key=health_vision_opts.key, name=health_vision_opts.name, params=health_vision_opts.params, value={}
            )
        )
        await session.commit()
    return current


async def test_saved_candidates_can_be_recovered_and_corrected_without_publication(nutrition_http):
    """校验失败、恢复、修正、幂等及重新校验都只生成候选。"""
    current = nutrition_http
    body = {"client_request_id": str(uuid4()), "kind": "food", "rows": [food_candidate()]}
    body["rows"][0]["nutrients"]["energy_kcal"] = "-1"
    first = await request(current, "POST", "/imports", json=body)
    assert first.status_code == 201, first.text
    first_report = first.json()
    assert first_report["published_count"] == 0
    assert first_report["summary"] == {"total": 1, "invalid": 1, "pending_review": 0}
    restored = await request(current, "GET", f"/imports/{first_report['id']}")
    assert restored.status_code == 200 and restored.json() == first_report, restored.text
    replay = await request(current, "POST", "/imports", json=body)
    assert replay.status_code == 201 and replay.json() == first_report, replay.text

    corrected = deepcopy(body)
    corrected["rows"][0]["nutrients"]["energy_kcal"] = "100"
    conflict = await request(current, "POST", "/imports", json=corrected)
    assert conflict.status_code == 409 and conflict.json()["code"] == "idempotency_conflict", conflict.text
    corrected["client_request_id"] = str(uuid4())
    second = await request(current, "POST", "/imports", json=corrected)
    assert second.status_code == 201, second.text
    second_report = second.json()
    assert second_report["id"] != first_report["id"]
    assert second_report["summary"] == {"total": 1, "invalid": 0, "pending_review": 1}
    assert second_report["published_count"] == 0
    second_read = await request(current, "GET", f"/imports/{second_report['id']}")
    assert second_read.status_code == 200 and second_read.json() == second_report, second_read.text
    readiness = await request(current, "GET", "/readiness")
    assert readiness.status_code == 200, readiness.text
    assert readiness.json()["candidate_batches"] == {
        "food": {"batches": 2, "rows": 2, "invalid": 1, "pending_review": 1},
        "recipe": {"batches": 0, "rows": 0, "invalid": 0, "pending_review": 0},
    }
    assert readiness.json()["counts"]["foods"] == 0
    assert readiness.json()["counts"]["recipes"] == 0
    async with current.sessions() as session:
        batches = (await session.scalars(select(NutritionImportBatch))).all()
        assert len(batches) == 2 and {row.actor_uid for row in batches} == {"admin"}
        assert {row.id: row.report for row in batches} == {
            first_report["id"]: {key: value for key, value in first_report.items() if key != "id"},
            second_report["id"]: {key: value for key, value in second_report.items() if key != "id"},
        }
        assert await session.scalar(select(func.count()).select_from(FoodRecord)) == 0
        assert await session.scalar(select(func.count()).select_from(RecipeVersion)) == 0
    current.evidence["candidate_readback"] = {"batches": 2, "published_foods": 0, "published_recipes": 0}


async def test_candidates_and_statistics_are_isolated_between_administrators(nutrition_http):
    """普通账号被拒绝，其他管理员看不到批次及行数。"""
    current = nutrition_http
    body = {"client_request_id": str(uuid4()), "kind": "food", "rows": [food_candidate()]}
    saved = await request(current, "POST", "/imports", json=body)
    assert saved.status_code == 201, saved.text
    batch_id = saved.json()["id"]
    for method, path, kwargs in (
        ("GET", "/readiness", {}),
        ("GET", f"/imports/{batch_id}", {}),
        ("POST", "/imports", {"json": {**body, "client_request_id": str(uuid4())}}),
    ):
        denied = await request(current, method, path, actor="owner", **kwargs)
        assert denied.status_code == 403, denied.text
    async with current.sessions() as session:
        other = await session.scalar(select(User).where(User.uid == "other"))
        other.role = "admin"
        await session.commit()
    denied = await request(current, "GET", f"/imports/{batch_id}", actor="other")
    assert denied.status_code == 404 and denied.json()["code"] == "not_found", denied.text
    other_ready = await request(current, "GET", "/readiness", actor="other")
    assert other_ready.status_code == 200, other_ready.text
    assert other_ready.json()["candidate_batches"] == {
        kind: {"batches": 0, "rows": 0, "invalid": 0, "pending_review": 0} for kind in ("food", "recipe")
    }
    admin_ready = await request(current, "GET", "/readiness")
    assert admin_ready.status_code == 200, admin_ready.text
    assert admin_ready.json()["candidate_batches"]["food"]["rows"] == 1
    async with current.sessions() as session:
        rows = (await session.scalars(select(NutritionImportBatch))).all()
        assert len(rows) == 1 and rows[0].id == batch_id and rows[0].actor_uid == "admin"
    current.evidence["isolation_readback"] = {"admin_batches": 1, "other_admin_batches": 0}


async def test_current_rule_status_is_independent_of_historical_version_count(nutrition_http, monkeypatch):
    """历史规则存在不代表当前配置已交付或仍有效。"""
    current = nutrition_http
    code = "synthetic-readiness-" + uuid4().hex
    published = await current.client.post(
        "/api/health/v1/approved-quality-rules",
        headers=current.identities["admin"],
        json={**proof(), "rule_code": code, "status": "approved", "payload": rules_payload()},
    )
    assert published.status_code == 201, published.text
    unconfigured = await request(current, "GET", "/readiness")
    assert unconfigured.status_code == 200, unconfigured.text
    assert unconfigured.json()["counts"]["rule_versions"] == 1
    assert unconfigured.json()["rules"] == {
        "configured": False,
        "code": "",
        "status": "not_ready",
        "reason": "not_configured",
        "version": None,
    }
    monkeypatch.setenv("HEALTH_DAILY_RULE_CODE", "synthetic-not-delivered")
    missing = await request(current, "GET", "/readiness")
    assert missing.status_code == 200, missing.text
    assert missing.json()["rules"]["reason"] == "not_delivered" and not missing.json()["rules_ready"]
    monkeypatch.setenv("HEALTH_DAILY_RULE_CODE", code)
    ready = await request(current, "GET", "/readiness")
    assert ready.status_code == 200, ready.text
    assert ready.json()["rules_ready"] and ready.json()["rules"]["version"] == 1
    revoked = await current.client.post(
        f"/api/health/v1/approved-quality-rules/{code}/versions/1/revoke", headers=current.identities["admin"]
    )
    assert revoked.status_code == 200, revoked.text
    stale = await request(current, "GET", "/readiness")
    assert stale.status_code == 200, stale.text
    assert stale.json()["counts"]["rule_versions"] == 1
    assert not stale.json()["rules_ready"] and stale.json()["rules"]["reason"] == "revoked"
    assert stale.json()["rules"]["version"] == 1
    async with current.sessions() as session:
        rows = (await session.scalars(select(HealthRuleSnapshot))).all()
        assert len(rows) == 1 and rows[0].rule_code == code and rows[0].revoked_at is not None
    current.evidence["rule_readback"] = {"historical_versions": 1, "current_reason": "revoked"}


async def test_knowledge_readiness_requires_existing_supported_binding(nutrition_http, monkeypatch):
    """非空配置不足以证明知识库存在且类型受支持。"""
    current = nutrition_http
    async with current.sessions() as session:
        session.add_all(
            [
                KnowledgeBase(kb_id="synthetic-food", name="合成食品来源", kb_type="milvus", created_by="admin"),
                KnowledgeBase(kb_id="synthetic-recipe", name="合成外部来源", kb_type="dify", created_by="admin"),
            ]
        )
        await session.commit()
    initial = await request(current, "GET", "/readiness")
    assert initial.status_code == 200, initial.text
    assert initial.json()["knowledge_bindings"] == {
        kind: {"configured": False, "available": False, "reason": "not_configured"} for kind in ("food", "recipe")
    }
    monkeypatch.setenv("HEALTH_FAMILY_NUTRITION_KB_ID", " synthetic-food ")
    monkeypatch.setenv("HEALTH_RECIPE_KB_ID", "synthetic-recipe")
    bound = await request(current, "GET", "/readiness")
    assert bound.status_code == 200, bound.text
    assert bound.json()["knowledge_bindings"] == {
        "food": {"configured": True, "available": True, "reason": None},
        "recipe": {"configured": True, "available": False, "reason": "not_found"},
    }
    monkeypatch.setenv("HEALTH_RECIPE_KB_ID", "synthetic-deleted")
    missing = await request(current, "GET", "/readiness")
    assert missing.status_code == 200, missing.text
    assert missing.json()["knowledge_bindings"]["recipe"] == {
        "configured": True,
        "available": False,
        "reason": "not_found",
    }
    async with current.sessions() as session:
        rows = (await session.scalars(select(KnowledgeBase))).all()
        assert {(row.kb_id, row.kb_type) for row in rows} == {
            ("synthetic-food", "milvus"),
            ("synthetic-recipe", "dify"),
        }
    current.evidence["binding_readback"] = {"supported_existing": True, "unsupported_and_missing": False}


@pytest.mark.parametrize("invalidate_during_save", [False, True])
async def test_worker_commits_candidates_and_evidence_atomically(nutrition_http, monkeypatch, invalidate_during_save):
    """来源最后重验失败则回滚已 flush 候选，成功才同批保留证据。"""
    current = nutrition_http
    monkeypatch.setenv("HEALTH_FAMILY_NUTRITION_KB_ID", "synthetic-worker-food")
    content = "合成事务资料：每100克，能量100 kcal，蛋白质10 g。"
    async with current.sessions() as session:
        session.add(
            KnowledgeBase(kb_id="synthetic-worker-food", name="合成事务来源", kb_type="milvus", created_by="admin")
        )
        await session.flush()
        session.add(
            KnowledgeFile(
                kb_id="synthetic-worker-food",
                file_id="synthetic-worker-file",
                filename="合成事务资料.md",
                status="indexed",
                content_hash="synthetic-file-v1",
            )
        )
        await session.flush()
        session.add(
            KnowledgeChunk(
                kb_id="synthetic-worker-food",
                file_id="synthetic-worker-file",
                chunk_id="synthetic-worker-chunk",
                chunk_index=0,
                content=content,
            )
        )
        await session.commit()

    async def retrieve(kb_id, query, **kwargs):
        """仅隔离向量传输；来源投影和保存校验继续读取真实 PG。"""
        assert kb_id == "synthetic-worker-food"
        return {
            "results": [
                {"kb_id": kb_id, "file_id": "synthetic-worker-file", "id": "synthetic-worker-chunk", "content": content}
            ]
        }

    async def configuration(session):
        """固定无外部调用的合成模型配置，不登记专业凭据。"""
        return {"meal_plan": {"available": True, "model": "synthetic-model"}, "policy_version": "synthetic-v1"}

    async def model(model_spec, instruction, messages, context):
        """数值及逐项依据均来自真实检索后送入模型的原文。"""
        assert model_spec == "synthetic-model"
        source = json.loads(messages[0]["text"])["sources"][0]
        assert source["content"] == content
        row = food_candidate()
        del row["license"], row["edition"]
        return {
            "rows": [
                {
                    "data": row,
                    "evidence": [
                        {"field": field, "source_id": source["source_id"], "quote": content}
                        for field in ("nutrients.energy_kcal", "nutrients.protein_g")
                    ],
                }
            ]
        }, {}

    async def owned_transaction(operation):
        """真实 PG 事务负责候选和证据；本用例不声称验证 Worker lease。"""
        async with current.sessions() as session:
            async with session.begin():
                await operation(session, None)

    monkeypatch.setattr(health_family_kb_service.knowledge_base, "retrieve", retrieve)
    monkeypatch.setattr(health_vision_service, "configuration", configuration)
    monkeypatch.setattr(health_vision_provider, "call_json_model", model)
    inserted = []
    if invalidate_during_save:
        original = health_knowledge_import_service.prepare_nutrition_import_in_session

        async def prepare_then_invalidate(session, uid, data):
            """在候选 flush 后注入真实来源改版，触发最终重验拒绝。"""
            report = await original(session, uid, data)
            inserted.append(report["id"])
            file = await session.scalar(select(KnowledgeFile).where(KnowledgeFile.file_id == "synthetic-worker-file"))
            file.content_hash = "synthetic-file-v2"
            await session.flush()
            return report

        monkeypatch.setattr(
            health_knowledge_import_service, "prepare_nutrition_import_in_session", prepare_then_invalidate
        )
    context = SimpleNamespace(
        task_id="synthetic-transaction-" + uuid4().hex,
        payload={"actor_uid": "admin", "kind": "food", "query": "合成事务资料"},
        run_owned_transaction=owned_transaction,
    )
    if invalidate_during_save:
        with pytest.raises(HealthVisionError, match="source_invalidated"):
            await health_knowledge_import_service.run_knowledge_nutrition(context)
        assert len(inserted) == 1, "故障必须发生在真实候选 flush 之后"
    else:
        result = await health_knowledge_import_service.run_knowledge_nutrition(context)
        restored = await request(current, "GET", f"/imports/{result['batch_id']}")
        assert restored.status_code == 200, restored.text
        assert restored.json()["published_count"] == 0
        assert restored.json()["knowledge_sources"][0]["file_content_hash"] == "synthetic-file-v1"
        assert restored.json()["evidence"][0]["row"] == 1
        assert {p["field"] for p in restored.json()["evidence"][0]["proofs"]} == {
            "nutrients.energy_kcal",
            "nutrients.protein_g",
        }
    async with current.sessions() as session:
        batches = (await session.scalars(select(NutritionImportBatch))).all()
        assert len(batches) == (0 if invalidate_during_save else 1)
        if batches:
            assert batches[0].id == result["batch_id"]
            assert batches[0].report == {key: value for key, value in restored.json().items() if key != "id"}
        file = await session.scalar(select(KnowledgeFile).where(KnowledgeFile.file_id == "synthetic-worker-file"))
        assert file.content_hash == "synthetic-file-v1", "失败事务必须连同故障注入的来源改动一起回滚"
        assert await session.scalar(select(func.count()).select_from(FoodRecord)) == 0
        assert await session.scalar(select(func.count()).select_from(RecipeVersion)) == 0
    current.evidence["atomic_candidate_readback"] = {
        "invalidation": invalidate_during_save,
        "candidate_batches": 0 if invalidate_during_save else 1,
        "published_foods": 0,
        "published_recipes": 0,
    }


def food_candidate():
    """合成数值只用于校验和持久化边界，不构成食物营养资料。"""
    return {
        "record_code": "synthetic-readiness-food",
        "name": "合成食品候选",
        "cooking_state": "raw",
        "source": "synthetic:readiness-source",
        "license": "synthetic-only",
        "edition": "synthetic-v1",
        "dataset_version": "synthetic-v1",
        "nutrients": {"energy_kcal": "100", "protein_g": "10", "sodium_mg": None},
    }


async def request(current, method, path, *, actor="admin", **kwargs):
    """保存有界协议证据，不记录凭证或完整响应正文。"""
    response = await current.client.request(method, ROOT + path, headers=current.identities[actor], **kwargs)
    current.evidence["requests"].append(
        {"method": method, "path": ROOT + path, "actor": actor, "status": response.status_code}
    )
    return response

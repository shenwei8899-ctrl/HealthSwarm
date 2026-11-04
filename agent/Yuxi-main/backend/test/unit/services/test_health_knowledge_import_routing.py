"""营养候选提取与保存始终使用同一受控知识库范围。"""

import json
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from yuxi.services import health_family_kb_service as sources
from yuxi.services import health_knowledge_import_service as imports
from yuxi.services import health_evidence_service, health_vision_provider
from yuxi.services.health_vision_service import health_vision_service
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.storage.postgres.models_knowledge import KnowledgeBase, KnowledgeChunk, KnowledgeFile


@pytest.fixture
def knowledge_scope(monkeypatch):
    """保留实际检索和来源验证，仅替换数据库与向量检索传输。"""
    monkeypatch.setenv(sources.KB_ID_ENV, "synthetic-family")
    monkeypatch.setenv(sources.RECIPE_KB_ID_ENV, "synthetic-recipes")
    file = SimpleNamespace(
        file_id="synthetic-file",
        filename="合成营养资料.md",
        status="indexed",
        content_hash="synthetic-file-hash",
        updated_at=datetime(2026, 11, 4, tzinfo=UTC),
    )
    chunk = SimpleNamespace(chunk_id="synthetic-chunk", content="合成资料，仅用于来源路由验证。")

    async def scalar(statement):
        """按实际查询实体提供当前资料，来源范围仍由业务代码校验。"""
        return {
            KnowledgeBase: SimpleNamespace(kb_type="milvus"),
            KnowledgeFile: file,
            KnowledgeChunk: chunk,
        }[statement.column_descriptions[0]["entity"]]

    session = SimpleNamespace(scalar=AsyncMock(side_effect=scalar))

    @asynccontextmanager
    async def transaction():
        """不连接真实数据库。"""
        yield session

    async def retrieve(kb_id, query, **kwargs):
        """仅返回调用方实际请求的知识库命中。"""
        return {"results": [{"id": chunk.chunk_id, "file_id": file.file_id, "kb_id": kb_id, "content": chunk.content}]}

    monkeypatch.setattr(sources.pg_manager, "get_async_session_context", transaction)
    retrieval = AsyncMock(side_effect=retrieve)
    monkeypatch.setattr(sources.knowledge_base, "retrieve", retrieval)
    return SimpleNamespace(session=session, retrieve=retrieval)


@pytest.mark.parametrize("kind", [None, "food", "recipe"])
async def test_candidate_sources_use_matching_fixed_library_and_validate(knowledge_scope, kind):
    """默认消费者仍读家庭库，菜谱只读菜谱库且可按同一范围重验。"""
    options = {} if kind is None else {"kind": kind}
    result = await sources.retrieve_family_nutrition_knowledge("合成资料", **options)
    expected_kb = "synthetic-recipes" if kind == "recipe" else "synthetic-family"
    assert knowledge_scope.retrieve.call_args.args == (expected_kb, "合成资料")
    assert result["scope"] == ("recipe_reference" if kind == "recipe" else "general_education")
    assert [source["kb_id"] for source in result["sources"]] == [expected_kb]
    assert (
        await sources.validate_nutrition_knowledge_sources(knowledge_scope.session, result, **options)
        == result["sources"]
    )


@pytest.mark.parametrize("kind", ["rules", "", None])
async def test_unknown_candidate_kind_never_falls_back_to_a_library(knowledge_scope, kind):
    """非法类型在检索或来源读取前失败。"""
    with pytest.raises(HealthVisionError, match="nutrition_candidate_kind_invalid"):
        await sources.retrieve_family_nutrition_knowledge("合成资料", kind=kind)
    with pytest.raises(HealthVisionError, match="nutrition_candidate_kind_invalid"):
        await sources.validate_nutrition_knowledge_sources(knowledge_scope.session, {}, kind=kind)
    knowledge_scope.retrieve.assert_not_awaited()
    knowledge_scope.session.scalar.assert_not_awaited()
    with pytest.raises(ValidationError):
        imports.KnowledgeNutritionInput(
            client_request_id="11111111-1111-4111-8111-111111111111", kind=kind, query="资料"
        )


@pytest.mark.parametrize("kind,other_kind", [("food", "recipe"), ("recipe", "food")])
async def test_source_receipt_cannot_move_between_candidate_kinds(knowledge_scope, kind, other_kind):
    """另一候选类型的来源回执不能作为本次保存依据。"""
    material = await sources.retrieve_family_nutrition_knowledge("合成资料", kind=kind)
    with pytest.raises(HealthVisionError, match="source_invalidated"):
        await sources.validate_nutrition_knowledge_sources(knowledge_scope.session, material, kind=other_kind)


@pytest.mark.parametrize("kind", ["food", "recipe"])
@pytest.mark.parametrize("new_binding", ["synthetic-rebound", ""])
async def test_binding_change_invalidates_extracted_candidate(knowledge_scope, monkeypatch, kind, new_binding):
    """换绑或删除绑定后拒绝旧来源，不回退到另一库。"""
    material = await sources.retrieve_family_nutrition_knowledge("合成资料", kind=kind)
    monkeypatch.setenv(sources.RECIPE_KB_ID_ENV if kind == "recipe" else sources.KB_ID_ENV, new_binding)
    with pytest.raises(HealthVisionError, match="source_invalidated"):
        await sources.validate_nutrition_knowledge_sources(knowledge_scope.session, material, kind=kind)


@pytest.mark.parametrize("configured", ["", "synthetic-one,synthetic-two"])
async def test_recipe_import_never_uses_family_library_when_unconfigured(knowledge_scope, monkeypatch, configured):
    """菜谱绑定缺失或包含多库时禁止检索，不扩大到家庭库。"""
    monkeypatch.setenv(sources.RECIPE_KB_ID_ENV, configured)
    with pytest.raises(HealthVisionError, match="knowledge_unavailable"):
        await sources.retrieve_family_nutrition_knowledge("合成资料", kind="recipe")
    knowledge_scope.retrieve.assert_not_awaited()


@pytest.fixture
def import_task(knowledge_scope, monkeypatch):
    """经过真实任务、提取与两次来源验证，只隔离模型、权限和持久化。"""
    session = knowledge_scope.session
    batch = SimpleNamespace(report={"status": "prepared_only", "published_count": 0})
    session.scalars = AsyncMock(return_value=SimpleNamespace(all=lambda: []))
    session.get = AsyncMock(return_value=batch)
    configuration = {"meal_plan": {"available": True, "model": "synthetic-model"}, "policy_version": "synthetic"}
    monkeypatch.setattr(health_vision_service, "configuration", AsyncMock(return_value=configuration))
    monkeypatch.setattr(health_evidence_service, "require_evidence_admin", AsyncMock())
    response = {"rows": [{"data": {"name": "合成待审候选"}, "evidence": []}]}
    model = AsyncMock(return_value=(response, {}))
    monkeypatch.setattr(health_vision_provider, "call_json_model", model)
    prepare = AsyncMock(return_value={"id": "synthetic-batch"})
    monkeypatch.setattr(imports, "prepare_nutrition_import_in_session", prepare)

    async def owned_transaction(operation):
        """执行实际任务的证据保存回调。"""
        await operation(session, None)

    context = SimpleNamespace(
        task_id="synthetic-task",
        payload={"actor_uid": "synthetic-admin", "kind": "recipe", "query": "合成资料"},
        run_owned_transaction=owned_transaction,
    )
    return SimpleNamespace(context=context, batch=batch, prepare=prepare, model=model, response=response)


@pytest.mark.parametrize("kind", ["food", "recipe"])
async def test_worker_passes_kind_through_retrieval_and_both_save_checks(knowledge_scope, import_task, kind):
    """任务使用实际来源服务；漏传菜谱类型会被保存前校验拒绝。"""
    import_task.context.payload["kind"] = kind
    result = await imports.run_knowledge_nutrition(import_task.context)
    expected_kb = "synthetic-recipes" if kind == "recipe" else "synthetic-family"
    assert result == {"batch_id": "synthetic-batch"}
    assert knowledge_scope.retrieve.call_args.args == (expected_kb, "合成资料")
    model_input = json.loads(import_task.model.call_args.args[2][0]["text"])
    assert model_input["sources"][0]["kb_id"] == expected_kb
    assert ("ingredients" if kind == "recipe" else "nutrients") in model_input["schema"]["properties"]
    assert import_task.prepare.call_args.args[2].kind == kind
    assert import_task.batch.report["knowledge_sources"][0]["kb_id"] == expected_kb
    assert import_task.batch.report["published_count"] == 0


@pytest.mark.parametrize("kind", ["food", "recipe"])
@pytest.mark.parametrize("changed_at", ["model", "candidate_save"])
async def test_worker_rechecks_binding_before_each_save(knowledge_scope, import_task, monkeypatch, kind, changed_at):
    """提取中及两次保存之间换绑，分别拒绝候选或证据保存。"""
    import_task.context.payload["kind"] = kind
    env_name = sources.RECIPE_KB_ID_ENV if kind == "recipe" else sources.KB_ID_ENV

    async def model(*args):
        """模拟模型返回前发生换绑。"""
        monkeypatch.setenv(env_name, "synthetic-rebound")
        return import_task.response, {}

    async def prepare(*args):
        """模拟候选保存后、证据写入前发生换绑。"""
        monkeypatch.setenv(env_name, "synthetic-rebound")
        return {"id": "synthetic-batch"}

    if changed_at == "model":
        import_task.model.side_effect = model
    else:
        import_task.prepare.side_effect = prepare
    with pytest.raises(HealthVisionError, match="source_invalidated"):
        await imports.run_knowledge_nutrition(import_task.context)
    assert "knowledge_sources" not in import_task.batch.report
    if changed_at == "model":
        import_task.prepare.assert_not_awaited()

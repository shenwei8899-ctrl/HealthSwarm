"""Phase4 待生产窗口迁入 integration/services 的真实 PG/HTTP 语义测试。"""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from test.integration.services.test_health_task_http import verified_task_cleanup  # noqa: F401
from test.integration.services.test_health_vision_http import ROOT, health_http  # noqa: F401
from yuxi.repositories import health_evidence_repository as repository_module
from yuxi.repositories.health_evidence_repository import HealthEvidenceRepository
from yuxi.services import health_evidence_index as index_module
from yuxi.services.health_evidence_index import EvidenceIndexHit
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_health import NutritionEvidence
from yuxi.utils.datetime_utils import utc_now_naive

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def publish(client, admin, token, key, *, version="v1"):
    """真实管理发布接口提供独立审核片段；内容不作为医学材料。"""
    body = {
        "source_ref": f"synthetic://lexical/{token}/{key}",
        "source_version": version,
        "title": f"合成词法{key}",
        "content": f"lexical{token} 膳食纤维示例。另一段另提饮水，{key}。",
        "review_ref": "synthetic://lexical/review",
        "reviewed_by": "synthetic-reviewer",
        "reviewed_at": (datetime.now(UTC) - timedelta(days=1)).isoformat(),
        "valid_until": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
    }
    response = await client.post(f"{ROOT}/nutrition-evidence", headers=admin, json=body)
    assert response.status_code == 201, response.text
    return response.json()["evidence_id"], body


async def test_published_sources_rebuild_after_revoke_expire_and_new_version(health_http):  # noqa: F811
    """同一 repository 每次读当前 PG，过期/撤回后新版本恢复，不复用旧 cache。"""
    client, users = health_http
    token = uuid4().hex
    query = f"lexical{token} 膳食纤维 饮水"
    first, _ = await publish(client, users[2]["headers"], token, "first")
    second, _ = await publish(client, users[2]["headers"], token, "second")
    async with pg_manager.get_async_session_context() as session:
        assert {source.id for source in await HealthEvidenceRepository(session).search(query)} == {first, second}
    denied = await client.delete(f"{ROOT}/nutrition-evidence/{first}", headers=users[0]["headers"])
    assert denied.status_code == 403
    assert (await client.delete(f"{ROOT}/nutrition-evidence/{first}", headers=users[2]["headers"])).status_code == 200
    async with pg_manager.get_async_session_context() as session:
        (await session.get(NutritionEvidence, second)).valid_until = utc_now_naive() - timedelta(seconds=1)
    async with pg_manager.get_async_session_context() as session:
        repository = HealthEvidenceRepository(session)
        assert await repository.search(query) == []
        # 同一 Owner 新建 adapter（进程重启时同样无恢复状态）结果一致。
        assert await HealthEvidenceRepository(session).search(query) == []
    restored, body = await publish(client, users[2]["headers"], token, "first", version="v2")
    async with pg_manager.get_async_session_context() as session:
        sources = await HealthEvidenceRepository(session).search(query)
        assert [(source.id, source.source_version, source.content) for source in sources] == [
            (restored, "v2", body["content"])
        ]
        assert (await session.get(NutritionEvidence, first)).revoked_at is not None
        assert (await session.get(NutritionEvidence, second)).valid_until <= utc_now_naive()


@pytest.mark.parametrize("mutation", ["revoked", "expired", "version", "hash", "content", "title", "deleted"])
async def test_index_hit_rechecks_fresh_locked_row_despite_identity_map(health_http, monkeypatch, mutation):  # noqa: F811
    """首读和索引后第二 Session 修改事实，预载 ORM 旧对象必须被 fresh proof 更新。"""
    client, users = health_http
    token = uuid4().hex
    identity, body = await publish(client, users[2]["headers"], token, mutation)
    original_index = repository_module.search_evidence_index

    async def stale_hit(documents, query):
        hits = await original_index(documents, query)
        assert [hit.evidence_id for hit in hits] == [identity]
        async with pg_manager.get_async_session_context() as other_session:
            source = await other_session.get(NutritionEvidence, identity)
            if mutation == "revoked":
                source.revoked_at = utc_now_naive()
            elif mutation == "expired":
                source.valid_until = utc_now_naive() - timedelta(seconds=1)
            elif mutation == "version":
                source.source_version = "v2"
            elif mutation == "hash":
                source.content_hash = "0" * 64
            elif mutation == "content":
                source.content = "未审核的并发篡改正文"
            elif mutation == "title":
                source.title = "只改标题而不改变正文hash的并发来源"
            else:
                await other_session.delete(source)
        return hits

    monkeypatch.setattr(repository_module, "search_evidence_index", stale_hit)
    async with pg_manager.get_async_session_context() as session:
        old = await session.get(NutritionEvidence, identity)
        assert old.content == body["content"] and old.source_version == "v1"
        with pytest.raises(HealthVisionError) as failure:
            await HealthEvidenceRepository(session).search(f"lexical{token} 膳食纤维 饮水")
        assert (failure.value.code, failure.value.status) == ("source_invalidated", 410)
        assert body["content"] not in str(failure.value)
        if mutation == "revoked":
            assert old.revoked_at is not None, "fresh locked read must populate an already cached instance"
        elif mutation == "version":
            assert old.source_version == "v2"


@pytest.mark.parametrize("forgery", ["missing_id", "wrong_version", "wrong_hash", "duplicate"])
async def test_forged_index_hit_cannot_publish_without_exact_current_proof(health_http, monkeypatch, forgery):  # noqa: F811
    """索引仅是候选，伪造来源或重复项不能绕过真实 PG proof。"""
    client, users = health_http
    token = uuid4().hex
    identity, _ = await publish(client, users[2]["headers"], token, forgery)
    original_index = repository_module.search_evidence_index

    async def forged_hit(documents, query):
        hit = (await original_index(documents, query))[0]
        if forgery == "duplicate":
            return [hit, hit]
        return [
            EvidenceIndexHit(
                str(uuid4()) if forgery == "missing_id" else identity,
                "forged-version" if forgery == "wrong_version" else hit.source_version,
                "0" * 64 if forgery == "wrong_hash" else hit.content_hash,
            )
        ]

    monkeypatch.setattr(repository_module, "search_evidence_index", forged_hit)
    async with pg_manager.get_async_session_context() as session:
        with pytest.raises(HealthVisionError) as failure:
            await HealthEvidenceRepository(session).search(f"lexical{token} 膳食纤维 饮水")
        assert (failure.value.code, failure.value.status) == ("source_invalidated", 410)


@pytest.mark.parametrize("capacity", ["sources", "oversized_row"])
async def test_pg_corpus_capacity_detects_extra_row_or_long_body_before_compute(health_http, monkeypatch, capacity):  # noqa: F811
    """降低片段上限作真实 N+1 负控；异常长 PG 正文不得截短成完整片段。"""
    client, users = health_http
    token = uuid4().hex
    identity, _ = await publish(client, users[2]["headers"], token, "first")
    if capacity == "sources":
        await publish(client, users[2]["headers"], token, "second")
        monkeypatch.setattr(repository_module, "MAX_EVIDENCE_INDEX_SOURCES", 1)
        monkeypatch.setattr(index_module, "MAX_EVIDENCE_INDEX_SOURCES", 1)
    else:
        async with pg_manager.get_async_session_context() as session:
            (await session.get(NutritionEvidence, identity)).content = "异常长合成正文" * 1000
    monkeypatch.setattr(index_module, "_rank_documents", lambda *_: pytest.fail("容量超界不得提交矩阵计算"))
    async with pg_manager.get_async_session_context() as session:
        with pytest.raises(HealthVisionError) as failure:
            await HealthEvidenceRepository(session).search(f"lexical{token} 膳食纤维 饮水")
        assert (failure.value.code, failure.value.status) == ("evidence_index_capacity_exceeded", 503)

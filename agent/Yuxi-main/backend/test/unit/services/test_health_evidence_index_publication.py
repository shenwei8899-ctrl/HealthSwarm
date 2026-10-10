"""后台词法计算返回后，失去执行所有权不得写入引用。"""

import hashlib
from contextlib import asynccontextmanager
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from yuxi.services import health_consultation_service as consultation
from yuxi.services import health_evidence_service as service
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.utils.datetime_utils import utc_now_naive


@pytest.mark.asyncio
@pytest.mark.parametrize("lease_lost", [False, True])
async def test_index_completion_rechecks_attempt_before_adding_any_citation(monkeypatch, lease_lost):
    """旧 attempt 的纯计算结果不能重新进入业务发布链。"""
    context = SimpleNamespace(uid="synthetic-actor", thread_id="synthetic-thread", model="synthetic-model")
    session = SimpleNamespace(add=Mock())
    run = SimpleNamespace(id="synthetic-run", input_payload={"health_processing": {"processor": "synthetic"}})
    binding = SimpleNamespace(conversation_id=7, member_id="synthetic-member")
    content = "合成科普正文"
    source = SimpleNamespace(
        id="synthetic-evidence",
        source_version="v1",
        title="合成科普",
        content=content,
        content_hash=hashlib.sha256(content.encode()).hexdigest(),
        source_ref="synthetic://source",
        reviewed_at=utc_now_naive() - timedelta(days=1),
    )
    attempts = AsyncMock(
        side_effect=[run, HealthVisionError("attempt_lost", "执行已失效", 409)] if lease_lost else [run, run]
    )
    repository = SimpleNamespace(require_attempt=attempts)

    @asynccontextmanager
    async def session_context():
        yield session

    monkeypatch.setattr(service.pg_manager, "get_async_session_context", session_context)
    monkeypatch.setattr(service, "HealthConsultationRepository", lambda _: repository)
    monkeypatch.setattr(consultation, "require_consultation", AsyncMock(return_value=(binding, {})))
    monkeypatch.setattr(service.HealthEvidenceRepository, "search", AsyncMock(return_value=[source]))
    if lease_lost:
        with pytest.raises(HealthVisionError, match="attempt_lost"):
            await service.search_nutrition_evidence(context, "合成")
        session.add.assert_not_called()
    else:
        result = await service.search_nutrition_evidence(context, "合成")
        assert result["status"] == "ok" and result["citations"][0]["evidence_id"] == source.id
        assert result["citations"][0]["scope"] == "general_education"
        session.add.assert_called_once()
    assert attempts.await_count == 2

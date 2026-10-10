"""派生档案回答的失败与中断不公开模型正文。"""

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from langchain_core.messages import AIMessage

from yuxi.services import chat_service
from yuxi.services.health_vision_types import HealthVisionError


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["version_bool", "version_float", "height_integer"])
async def test_profile_checkpoint_requires_exact_json_hash_before_receipt_lookup(change):
    """Python相等的JSON改型也必须因真实内容摘要不符而拒绝。"""
    from yuxi.repositories.health_family_profile_repository import HealthFamilyProfileRepository

    original = {
        "status": "ready",
        "confirmed_version": 1,
        "profile": {"height_cm": 170.0},
        "source": {"source_member_id": "synthetic-source", "version": 1},
    }
    original["source_hash"] = HealthFamilyProfileRepository.payload_hash(original)
    forged = deepcopy(original)
    if change == "version_bool":
        forged["confirmed_version"] = True
    elif change == "version_float":
        forged["source"]["version"] = 1.0
    else:
        forged["profile"]["height_cm"] = 170
    assert forged == original
    assert HealthFamilyProfileRepository.payload_hash(forged) != original["source_hash"]
    session = SimpleNamespace(scalar=AsyncMock(return_value=object()))
    repository = HealthFamilyProfileRepository(session)
    repository.read = AsyncMock(return_value=original)
    binding = SimpleNamespace(conversation_id=7, member_id="synthetic-member")
    await repository.validate_tool_payload("actor", binding, original)
    session.scalar.reset_mock()
    with pytest.raises(HealthVisionError, match="profile_source_changed"):
        await repository.validate_tool_payload("actor", binding, forged)
    session.scalar.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("interrupt", [False, True])
async def test_derived_run_partial_uses_thread_dependency_and_discards_private_body(monkeypatch, interrupt):
    """所有咨询失败均不发布，来源回执不再成为错误正文许可。"""
    session = SimpleNamespace(
        scalar=AsyncMock(return_value="prior-profile-run"), commit=AsyncMock(), rollback=AsyncMock()
    )
    conv = SimpleNamespace(db=session, add_message_by_thread_id=AsyncMock(return_value=SimpleNamespace(id=42)))
    locked = SimpleNamespace(agent_slug="health-consultation", conversation_id=7)
    repo = SimpleNamespace(
        lock_output_persistence=AsyncMock(return_value=locked),
        set_output_message=AsyncMock(),
        set_terminal_status=AsyncMock(return_value=(locked, True)),
        cancel_active_execution_tree_descendants=AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(chat_service, "AgentRunRepository", lambda db: repo)
    monkeypatch.setattr(chat_service, "publish_cancel_signals", AsyncMock())
    output = await chat_service.save_partial_message(
        conv,
        "thread",
        full_msg=AIMessage(content="合成敏感档案正文"),
        run_id="derived-run",
        request_id="request",
        worker_id="worker",
        interrupt_run=interrupt,
    )
    session.scalar.assert_not_awaited()
    if interrupt:
        assert output.id == 42
        kwargs = conv.add_message_by_thread_id.await_args.kwargs
        assert kwargs["content"] == "" and "合成敏感档案正文" not in str(kwargs["extra_metadata"])
        repo.set_terminal_status.assert_awaited_once()
        assert repo.set_terminal_status.await_args.kwargs["error_message"] == "咨询已中断"
    else:
        assert output is None
        conv.add_message_by_thread_id.assert_not_awaited()
        repo.set_output_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_publication_requires_frozen_processing_snapshot():
    """无审批快照的旧运行不能按当前配置冒充已同意。"""
    from yuxi.services.health_family_profile_service import validate_profile_publication

    with pytest.raises(HealthVisionError, match="policy_changed"):
        await validate_profile_publication(None, SimpleNamespace(input_payload={}))

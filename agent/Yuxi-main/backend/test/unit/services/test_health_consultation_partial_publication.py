"""未经完成发布校验的咨询失败正文统一关闭，显式中断仅存固定空消息。"""

import inspect
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from langchain_core.messages import AIMessage

from yuxi.services import chat_service

pytestmark = pytest.mark.asyncio
PRIVATE = "synthetic-private-content-trace-and-error"


@pytest.fixture(autouse=True)
def controlled_mutation(monkeypatch):
    """明确启用时只变异测试进程函数副本，不修改共享生产文件或运行服务。"""
    if os.getenv("HEALTH_PARTIAL_MUTATION") != "disabled_consultation_guard":
        return
    source = inspect.getsource(chat_service.save_partial_message)
    original = 'if locked_run.agent_slug == "health-consultation":'
    assert source.count(original) == 1

    async def mutated(*args, **kwargs):
        # scaffold的Repository mock在调用时已生效，只改变待检业务guard。
        scope = dict(chat_service.__dict__)
        exec(compile(source.replace(original, "if False:"), "<controlled_partial_mutation>", "exec"), scope)
        return await scope["save_partial_message"](*args, **kwargs)

    monkeypatch.setattr(chat_service, "save_partial_message", mutated)


def scaffold(monkeypatch, *, slug="health-consultation", has_use=False, reject_lock=False):
    session = SimpleNamespace(
        scalar=AsyncMock(return_value="prior-source-use" if has_use else None),
        commit=AsyncMock(),
        rollback=AsyncMock(),
    )
    message = SimpleNamespace(id=42)
    conv = SimpleNamespace(db=session, add_message_by_thread_id=AsyncMock(return_value=message))
    locked = SimpleNamespace(agent_slug=slug, conversation_id=7)
    repo = SimpleNamespace(
        lock_output_persistence=AsyncMock(
            side_effect=ValueError("invalid worker/request") if reject_lock else None,
            return_value=locked,
        ),
        set_output_message=AsyncMock(),
        set_terminal_status=AsyncMock(return_value=(locked, True)),
        cancel_active_execution_tree_descendants=AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(chat_service, "AgentRunRepository", lambda db: repo)
    monkeypatch.setattr(chat_service, "publish_cancel_signals", AsyncMock())
    return session, conv, repo, message


async def save(conv, *, interrupt=False, worker="current-worker", request="current-request"):
    return await chat_service.save_partial_message(
        conv,
        "current-thread",
        full_msg=AIMessage(
            content=PRIVATE, additional_kwargs={"private": PRIVATE}, response_metadata={"private": PRIVATE}
        ),
        error_type=PRIVATE,
        error_message=PRIVATE,
        trace_info={"private_trace": PRIVATE},
        run_id="current-run",
        request_id=request,
        worker_id=worker,
        interrupt_run=interrupt,
    )


@pytest.mark.parametrize("has_use", [False, True], ids=["bare", "has_formal_use"])
@pytest.mark.parametrize("interrupt", [False, True], ids=["partial_failure", "explicit_interrupt"])
async def test_consultation_partial_bare_and_formal_source_use_share_closed_publication_boundary(
    monkeypatch, has_use, interrupt
):
    session, conv, repo, message = scaffold(monkeypatch, has_use=has_use)
    output = await save(conv, interrupt=interrupt)
    repo.lock_output_persistence.assert_awaited_once_with(
        "current-run",
        worker_id="current-worker",
        conversation_thread_id="current-thread",
        request_id="current-request",
    )
    session.scalar.assert_not_awaited()
    session.rollback.assert_not_awaited()
    if not interrupt:
        assert output is None
        conv.add_message_by_thread_id.assert_not_awaited()
        repo.set_output_message.assert_not_awaited()
        repo.set_terminal_status.assert_not_awaited()
        session.commit.assert_not_awaited()
        return
    assert output is message
    written = conv.add_message_by_thread_id.await_args.kwargs
    assert written["content"] == "" and written["message_type"] == "text"
    assert written["extra_metadata"] == {"error_type": "interrupted", "is_error": True, "error_message": "咨询已中断"}
    assert PRIVATE not in str(written)
    repo.set_terminal_status.assert_awaited_once_with(
        "current-run",
        status="interrupted",
        error_type="interrupted",
        error_message="咨询已中断",
        token_usage={"available": False},
        worker_id="current-worker",
    )
    repo.set_output_message.assert_awaited_once_with("current-run", 42, worker_id="current-worker")
    session.commit.assert_awaited_once()


@pytest.mark.parametrize("interrupt", [False, True])
async def test_generic_partial_and_interrupt_preserve_existing_body_metadata_and_run_error(monkeypatch, interrupt):
    session, conv, repo, message = scaffold(monkeypatch, slug="synthetic-generic")
    assert await save(conv, interrupt=interrupt) is message
    written = conv.add_message_by_thread_id.await_args.kwargs
    assert written["content"] == PRIVATE and written["extra_metadata"]["private_trace"] == PRIVATE
    assert written["extra_metadata"]["error_message"] == PRIVATE
    assert repo.set_terminal_status.await_count == int(interrupt)
    if interrupt:
        assert repo.set_terminal_status.await_args.kwargs["error_message"] == PRIVATE
    session.commit.assert_awaited_once()


@pytest.mark.parametrize("interrupt", [False, True])
@pytest.mark.parametrize("invalid", ["missing_worker", "missing_request", "rejected_owner"])
async def test_partial_still_requires_current_worker_request_and_repository_guard(monkeypatch, invalid, interrupt):
    session, conv, repo, _ = scaffold(monkeypatch, reject_lock=invalid == "rejected_owner")
    worker = None if invalid == "missing_worker" else "current-worker"
    request = None if invalid == "missing_request" else "current-request"
    if interrupt:
        with pytest.raises(ValueError):
            await save(conv, interrupt=interrupt, worker=worker, request=request)
    else:
        assert await save(conv, interrupt=interrupt, worker=worker, request=request) is None
    conv.add_message_by_thread_id.assert_not_awaited()
    repo.set_output_message.assert_not_awaited()
    repo.set_terminal_status.assert_not_awaited()
    session.commit.assert_not_awaited()
    session.rollback.assert_awaited_once()

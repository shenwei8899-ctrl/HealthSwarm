"""成员主体、持续性、模型历史撤回及北京时间的独立负控。"""

import json
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.prebuilt.tool_node import ToolRuntime
from pydantic import ValidationError

from yuxi.agents.toolkits.health import remember_member_fact
from yuxi.services import health_memory_service as service
from yuxi.services.health_daily_service import business_date, message_digest
from yuxi.services.health_memory_types import validate_memory_statement
from yuxi.services.health_vision_types import HealthVisionError


@pytest.mark.parametrize(
    "quote,subject,owner,relationship,error",
    [
        ("我以后不吃香菜", "我", "actor", "本人", None),
        ("妈妈一直不吃香菜", "妈妈", "actor", "母亲", None),
        ("我今天觉得有点咸", "我", "actor", "本人", "memory_temporary"),
        ("我以后不吃香菜", "我", "other", "本人", "memory_subject_unclear"),
        ("我以后不吃香菜", "我", "actor", "母亲", "memory_subject_unclear"),
        ("妈妈一直不吃香菜", "我", "actor", "本人", "memory_subject_unclear"),
        ("我妈妈长期不吃香菜", "我", "actor", "本人", "memory_subject_unclear"),
        ("我这次觉得有点咸", "我", "actor", "本人", "memory_temporary"),
        ("我刚才有些恶心", "我", "actor", "本人", "memory_temporary"),
        ("我今天觉得有点咸，以后再说", "我", "actor", "本人", "memory_temporary"),
        ("我觉得有点咸", "我", "actor", "本人", "memory_subject_unclear"),
    ],
)
def test_memory_requires_current_member_and_ongoing_statement(quote, subject, owner, relationship, error):
    """模糊成员和一次体验不会写成长久事实。"""
    member = SimpleNamespace(owner_uid=owner, relationship_label=relationship, display_name="妈妈")
    if error:
        with pytest.raises(HealthVisionError, match=error):
            validate_memory_statement(member, "actor", subject, quote, quote)
    else:
        validate_memory_statement(member, "actor", subject, quote, quote)


def test_memory_cannot_invent_source_or_supply_identity():
    """模型只能提供当前原文，不得选账号、成员或来源消息。"""
    member = SimpleNamespace(owner_uid="actor", relationship_label="本人", display_name="合成本人")
    with pytest.raises(HealthVisionError, match="memory_source_invalid"):
        validate_memory_statement(member, "actor", "我", "我以后不吃香菜", "我今天吃饭了")
    assert set(remember_member_fact.tool_call_schema.model_json_schema()["properties"]) == {
        "fact_key",
        "kind",
        "subject",
        "quote",
        "persistence",
    }
    schema = remember_member_fact.args_schema
    payload = {
        "fact_key": "avoid_coriander",
        "kind": "preference",
        "subject": "我",
        "quote": "我以后不吃香菜",
        "persistence": "ongoing",
        "runtime": ToolRuntime(
            state={}, context=None, config={}, stream_writer=lambda _: None, tool_call_id="synthetic", store=None
        ),
    }
    for field in ("uid", "member_id", "source_message_id", "run_id", "runtime"):
        with pytest.raises(ValidationError):
            schema.model_validate({**payload, field: "forged"})
    for changed in ({"kind": "diagnosis"}, {"persistence": "temporary"}, {"fact_key": "../file"}):
        with pytest.raises(ValidationError):
            schema.model_validate({**payload, **changed})


@pytest.mark.asyncio
async def test_revoked_history_removes_source_turn_but_keeps_current_question(monkeypatch):
    """撤回必须改变模型实际输入，不能只在新读取结果中隐藏。"""

    @asynccontextmanager
    async def session_context():
        yield None

    monkeypatch.setattr(service.pg_manager, "get_async_session_context", session_context)
    monkeypatch.setattr(service.HealthMemoryRepository, "history_uses", AsyncMock(return_value=[]))
    monkeypatch.setattr(
        service.HealthMemoryRepository, "get", AsyncMock(return_value=SimpleNamespace(status="revoked", version=2))
    )
    source = HumanMessage(content="我以后不吃香菜")
    receipt = ToolMessage(
        name="remember_member_fact",
        tool_call_id="memory-call",
        content=json.dumps({"memory_id": "synthetic", "version": 1, "written_version": 1, "replayed": False}),
    )
    current = HumanMessage(content="现在有哪些有效记忆？")
    context = SimpleNamespace(uid="actor", thread_id="thread")
    assert await service.filter_memory_history(context, [source, receipt, current]) == [current]
    with pytest.raises(HealthVisionError, match="memory_changed"):
        await service.filter_memory_history(context, [source, receipt])


@pytest.mark.asyncio
async def test_revocation_filters_committed_source_and_derived_answer_without_tool_receipt(monkeypatch):
    """PG 依赖使丢失收据及无工具的派生正文同时失效。"""

    @asynccontextmanager
    async def session_context():
        yield None

    monkeypatch.setattr(service.pg_manager, "get_async_session_context", session_context)
    monkeypatch.setattr(
        service.HealthMemoryRepository,
        "history_uses",
        AsyncMock(return_value=[("source", "fact", 1, "revoked", 2), ("derived", "fact", 1, "revoked", 2)]),
    )
    source = HumanMessage(content="我以后不吃香菜", additional_kwargs={"health_request_id": "source"})
    derived = HumanMessage(content="继续", additional_kwargs={"health_request_id": "derived"})
    answer = AIMessage(content="你不吃香菜")
    current = HumanMessage(content="新的问题", additional_kwargs={"health_request_id": "current"})
    context = SimpleNamespace(uid="actor", thread_id="thread")
    assert await service.filter_memory_history(context, [source, derived, answer, current]) == [current]


@pytest.mark.asyncio
@pytest.mark.parametrize("own_update", [True, False])
async def test_same_request_update_replaces_old_read_but_external_edit_is_rejected(monkeypatch, own_update):
    """同轮读后写可使用新版本；管理修改不能冒充工具自取代。"""

    @asynccontextmanager
    async def session_context():
        yield None

    fact = SimpleNamespace(
        id="fact",
        member_id="member",
        fact_key="preference",
        content="我以后会吃香菜",
        kind="preference",
        version=2,
        status="active",
        updated_at=datetime(2026, 10, 6),
    )
    monkeypatch.setattr(service.pg_manager, "get_async_session_context", session_context)
    monkeypatch.setattr(service.HealthMemoryRepository, "get", AsyncMock(return_value=fact))
    monkeypatch.setattr(
        service.HealthMemoryRepository,
        "history_uses",
        AsyncMock(return_value=[("current", "fact", 2 if own_update else 1, "active", 2)]),
    )
    monkeypatch.setattr(
        service.HealthMemoryRepository, "own_revision", AsyncMock(return_value=object() if own_update else None)
    )
    recorded = AsyncMock()
    monkeypatch.setattr(service.HealthMemoryRepository, "record_uses", recorded)
    run = SimpleNamespace(id="run", input_payload={"health_processing": {}})
    monkeypatch.setattr(service.HealthConsultationRepository, "require_attempt", AsyncMock(return_value=run))
    from yuxi.services import health_consultation_service

    monkeypatch.setattr(health_consultation_service, "require_consultation", AsyncMock())
    monkeypatch.setattr(
        service.HealthConsultationRepository,
        "authorize",
        AsyncMock(return_value=SimpleNamespace(member_id="member")),
    )
    current = HumanMessage(content="我以后会吃香菜", additional_kwargs={"health_request_id": "current"})
    read = ToolMessage(
        name="get_member_memories",
        tool_call_id="read",
        content=json.dumps(
            {"memories": [{"memory_id": "fact", "version": 1, "content": "我以后不吃香菜"}], "truncated": False}
        ),
    )
    context = SimpleNamespace(uid="actor", thread_id="thread", model="synthetic/fixed")
    if own_update:
        messages = await service.filter_memory_history(context, [current, read])
        projection = json.loads(messages[-1].content)["memories"][0]
        assert projection["version"] == 2 and projection["content"] == "我以后会吃香菜"
        assert projection["superseded_by_same_request"] is True
        assert recorded.await_args.args[1] == [("fact", 2), ("fact", 2)]
    else:
        with pytest.raises(HealthVisionError, match="memory_changed"):
            await service.filter_memory_history(context, [current, read])
        recorded.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("tool_name", ["get_member_memories", "remember_member_fact"])
@pytest.mark.parametrize("change", ["content", "kind", "source_type", "version_bool", "other_member"])
async def test_active_memory_checkpoint_matches_original_projection_and_bound_member(monkeypatch, tool_name, change):
    """真实active标识和版本不能为伪造正文、类型或其他成员提供读取权。"""
    fact = SimpleNamespace(
        id="fact",
        member_id="other-member" if change == "other_member" else "member",
        fact_key="avoid_coriander",
        content="我以后不吃香菜",
        kind="preference",
        version=1,
        status="active",
        updated_at=datetime(2026, 10, 6),
    )
    reference = service.memory_result(fact)
    if change == "version_bool":
        reference["version"] = True
    elif change != "other_member":
        reference[change] = {
            "content": "我患有糖尿病",
            "kind": "health_self_report",
            "source_type": "confirmed_profile",
        }[change]
    payload = (
        {"memories": [reference], "truncated": False}
        if tool_name == "get_member_memories"
        else {**reference, "written_version": 1, "replayed": False}
    )
    repository = SimpleNamespace(
        history_uses=AsyncMock(return_value=[]),
        get=AsyncMock(return_value=fact),
        record_uses=AsyncMock(),
    )
    monkeypatch.setattr(service, "HealthMemoryRepository", lambda session: repository)
    monkeypatch.setattr(
        service.HealthConsultationRepository,
        "authorize",
        AsyncMock(return_value=SimpleNamespace(member_id="member")),
    )
    messages = [
        HumanMessage(content="合成问题", additional_kwargs={"health_request_id": "request"}),
        ToolMessage(name=tool_name, tool_call_id="synthetic-call", content=json.dumps(payload)),
    ]
    context = SimpleNamespace(uid="actor", thread_id="thread")
    with pytest.raises(HealthVisionError, match="memory_history_invalid"):
        await service.filter_memory_history(context, messages, session=object(), persist_uses=False)
    repository.record_uses.assert_not_awaited()


@pytest.mark.parametrize(
    "instant,expected",
    [
        (datetime(2026, 10, 6, 15, 59, 59, tzinfo=UTC), "2026-10-06"),
        (datetime(2026, 10, 6, 16, 0, tzinfo=UTC), "2026-10-07"),
        (datetime(2026, 10, 6, 16, 0), "2026-10-07"),
    ],
)
def test_business_date_uses_beijing_midnight(instant, expected):
    """显式 UTC 样例独立校验零点而非采用本机日期。"""
    assert business_date(instant).isoformat() == expected


def test_summary_is_sourced_digest_and_changes_on_late_content():
    """摘要只展示实际提及与来源，内容改变必须使旧摘要失效。"""
    rows = [
        SimpleNamespace(
            id=1, request_id="request", role="user", content="明天的安排还没完成", created_at=datetime(2026, 10, 6)
        )
    ]
    fingerprint, digest = message_digest(rows)
    assert digest["source_message_ids"] == [1] and digest["meal_plan_generated"] is False
    assert digest["tomorrow_mentions"][0]["excerpt"] == rows[0].content
    assert digest["open_item_mentions"][0]["message_id"] == 1
    rows[0].content = "更新的真实内容"
    assert message_digest(rows)[0] != fingerprint

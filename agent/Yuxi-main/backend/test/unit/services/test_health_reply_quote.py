"""引用协议的来源、片段和模型输入验证。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from pydantic import ValidationError

from yuxi.services.health_reply_quote_service import (
    ReplyQuoteInput,
    resolve_reply_quote,
    visible_quote_text,
    compact_quote_text,
    quote_model_input,
)
from yuxi.services.input_message_service import build_chat_input_message
from yuxi.services.health_vision_types import HealthVisionError


def test_quote_requires_one_persisted_locator_and_bounded_text():
    """拒绝空片段、超限文字和混用定位符。"""
    base = {"source_thread_id": uuid4(), "text": "片段"}
    for fields in (
        {},
        {"source_message_id": 0},
        {"source_message_id": 1, "source_request_id": uuid4()},
        {"source_message_id": 1, "text": " "},
        {"source_message_id": 1, "text": "字" * 1201},
    ):
        with pytest.raises(ValidationError):
            ReplyQuoteInput(**{**base, **fields})


def test_quote_context_preserves_question_and_is_present_in_model_input():
    """可见问题原文不被引用包装覆盖。"""
    question = build_chat_input_message("具体怎么判断？")
    quote = {"source_message_id": 42, "text": "份量按实际需要调整。"}
    combined = quote_model_input(question, quote)
    assert combined.content == "具体怎么判断？"
    assert "份量按实际需要调整。" in combined.require_langchain_message().content
    assert combined.require_langchain_message().additional_kwargs["reply_quote"] == quote
    assert question.require_langchain_message().additional_kwargs == {}


def test_internal_markers_are_not_quoteable_and_markdown_does_not_change_a_passage():
    """隐藏来源不能以引用快照重新公开。"""
    visible = visible_quote_text("**份量**按实际需要调整。[资料:internal-secret]（private.md）")
    assert "internal-secret" not in visible and "private.md" not in visible
    assert compact_quote_text("份量按实际需要调整。") in compact_quote_text(visible)


@pytest.mark.asyncio
async def test_resolve_uses_authorized_current_source_and_rejects_forged_passages(monkeypatch):
    """来源权限、正式回执和当前正文共同决定引用。"""
    import json
    from yuxi.repositories.health_consultation_repository import HealthConsultationRepository
    from yuxi.repositories.health_reply_quote_repository import HealthReplyQuoteRepository

    binding = SimpleNamespace(member_id="member", conversation_id=1)
    authorization = AsyncMock(return_value=binding)
    monkeypatch.setattr(HealthConsultationRepository, "authorize", authorization)
    receipt = {"message": "**实际份量**保持未知。", "route": "needs_clarification", "action": "ask"}
    message = SimpleNamespace(
        id=42,
        conversation_id=1,
        delivery_status="complete",
        run_id=None,
        request_id="request",
        content=json.dumps({"result_type": "health_intent", **receipt}),
    )
    read = AsyncMock(return_value=[message])
    monkeypatch.setattr(HealthReplyQuoteRepository, "source", read)
    db = AsyncMock()
    db.get.return_value = SimpleNamespace(extra_metadata={"health_intent_receipts": {"request": {"result": receipt}}})
    thread = str(uuid4())
    value = {"source_thread_id": thread, "source_message_id": 42, "text": "实际份量"}
    result = await resolve_reply_quote(db, "user", thread, value)
    assert result["source_message_id"] == 42 and result["text"] == "实际份量"
    for text in ("已确认吃了500克", "internal-secret"):
        with pytest.raises(HealthVisionError, match="引用内容"):
            await resolve_reply_quote(db, "user", thread, {**value, "text": text})
    read.return_value = []
    with pytest.raises(HealthVisionError, match="原回复"):
        await resolve_reply_quote(db, "user", thread, value)
    read.reset_mock()
    authorization.side_effect = [binding, SimpleNamespace(member_id="another-member", conversation_id=2)]
    with pytest.raises(HealthVisionError, match="成员不一致"):
        await resolve_reply_quote(db, "user", thread, value)
    read.assert_not_awaited()


def test_visible_passage_crosses_list_markers_and_repeated_table_headers():
    """与前端选区相同的阅读顺序，不把列表编号当正文。"""
    assert compact_quote_text("第一项\n\n第二项") == compact_quote_text(visible_quote_text("- 第一项\n- 第二项"))
    assert compact_quote_text("第一项\n\n第二项") == compact_quote_text(visible_quote_text("1. 第一项\n2. 第二项"))
    assert compact_quote_text("名称\n\n甲\n\n份量\n\n少量\n\n名称\n\n乙\n\n份量\n\n适量") == compact_quote_text(
        visible_quote_text("|名称|份量|\n|---|---|\n|甲|少量|\n|乙|适量|")
    )


@pytest.mark.asyncio
async def test_revoked_quote_dependency_blocks_final_publication_and_completed_answer_read(monkeypatch):
    """模型外呼之后以及完成之后，来源失效均不能继续公开复述。"""
    from yuxi.repositories.health_reply_quote_repository import HealthReplyQuoteRepository
    from yuxi.services import health_reply_quote_service as quotes, health_evidence_service as evidence

    monkeypatch.setattr(
        HealthReplyQuoteRepository, "context_quotes", AsyncMock(return_value=[{"source_message_id": 42}])
    )
    monkeypatch.setattr(
        quotes,
        "resolve_reply_quote",
        AsyncMock(side_effect=HealthVisionError("source_invalidated", "原来源已撤回", 410)),
    )
    run = SimpleNamespace(
        id="run",
        input_message_id=9,
        conversation_id=1,
        conversation_thread_id="thread",
        uid="user",
        agent_slug="health-consultation",
        status="completed",
    )
    with pytest.raises(HealthVisionError, match="原来源已撤回"):
        await evidence.validate_evidence_publication(None, run, "模型刚生成的复述")
    with pytest.raises(HealthVisionError, match="原来源已撤回"):
        await evidence.read_public_consultation_answer(
            None, run, "user", binding=SimpleNamespace(conversation_id=1, actor_uid="user")
        )


@pytest.mark.asyncio
async def test_intent_dependencies_reject_revoked_source_and_cycles(monkeypatch):
    """没有Run的分类答复仍继承引用来源，并拒绝循环依赖。"""
    from yuxi.services import health_reply_quote_service as quotes

    dependency = {"source_thread_id": str(uuid4()), "source_message_id": 42, "text": "已撤回片段"}
    message = SimpleNamespace(id=99, conversation_id=1, request_id="intent")
    db = AsyncMock()
    db.get.return_value = SimpleNamespace(
        extra_metadata={"health_intent_receipts": {"intent": {"reply_quote_dependencies": [dependency]}}}
    )
    resolve = AsyncMock(side_effect=HealthVisionError("source_invalidated", "原来源已撤回", 410))
    monkeypatch.setattr(quotes, "resolve_reply_quote", resolve)
    with pytest.raises(HealthVisionError, match="原来源已撤回"):
        await quotes.validate_intent_reply_dependencies(db, message, "user", "thread")
    with pytest.raises(HealthVisionError, match="引用来源链"):
        await quotes.validate_intent_reply_dependencies(db, message, "user", "thread", visited={("intent", 99)})


@pytest.mark.asyncio
async def test_intent_context_never_sends_unpublished_derived_answer(monkeypatch):
    """失效派生正文不能经recent_dialogue回流模型。"""
    from yuxi.services import health_reply_quote_service as quotes

    resolve = AsyncMock(side_effect=HealthVisionError("source_invalidated", "原来源已撤回", 410))
    monkeypatch.setattr(quotes, "resolve_reply_quote", resolve)
    messages = [
        SimpleNamespace(role="user", content="用户问题"),
        SimpleNamespace(id=99, role="assistant", content="失效派生正文"),
    ]
    recent, dependencies = await quotes.intent_dialogue_context(None, "user", str(uuid4()), messages)
    assert recent == [{"role": "user", "text": "用户问题"}] and dependencies == []


@pytest.mark.parametrize("source", [
    "| 餐次 | 食物 |\n| --- | --- |\n| 早餐 | 燕麦牛奶 |",
    "早餐：燕麦牛奶",
    "- 早餐：燕麦牛奶",
])
def test_quote_crosses_meal_heading_and_food(source):
    """引用文本与客户端隐藏表头、移除餐次冒号后的展示一致。"""
    assert compact_quote_text("早餐\n\n燕麦牛奶") in compact_quote_text(visible_quote_text(source))


def test_ordinary_table_retains_labels_and_meal_notes_remain_visible():
    """专用餐次排版不丢掉其他列的提示或普通表头。"""
    source="| 餐次 | 食物 | 提醒 |\n| --- | --- | --- |\n| 早餐 | 燕麦 | 适量 |"
    assert visible_quote_text(source)=="早餐\n\n燕麦\n\n提醒：适量"
    assert visible_quote_text("| 项目 | 数值 |\n| --- | --- |\n| 食物 | 10 |") == "项目\n\n食物\n\n数值\n\n10"


@pytest.mark.parametrize("source, selected", [
    ("- 早餐：燕麦牛奶\n- 提醒：少糖", "早餐：燕麦牛奶"),
    ("- 早餐：燕麦\n  注意少糖\n- 提醒：少盐", "早餐：燕麦\n注意少糖"),
    ("# 早餐：燕麦牛奶", "早餐：燕麦牛奶"),
    ("早餐：燕麦\n其他说明\n午餐：米饭", "其他说明\n午餐：米饭"),
])
def test_mixed_blocks_and_explicit_headings_keep_their_visible_colons(source, selected):
    """客户端不拆分的混合列表、段落内部和显式标题保留原标点。"""
    assert compact_quote_text(selected) in compact_quote_text(visible_quote_text(source))

"""咨询答案的可选后续问题，独立于正文与必须补充的信息。"""

import hashlib
import time
from typing import Literal

from pydantic import Field, field_validator, model_validator

from yuxi.services.health_vision_types import HealthDTO

FOLLOWUPS_KEY = "health_context_followups"


class ChatFollowup(HealthDTO):
    """短标签仅用于显示，question 是点击后实际发送的完整问题。"""

    label: str = Field(min_length=1, max_length=24)
    question: str = Field(min_length=1, max_length=160)

    @field_validator("label", "question", mode="before")
    @classmethod
    def natural_text(cls, value):
        """协议只接受单行自然语言，不接受空白与控制字符。"""
        if not isinstance(value, str) or not value.strip() or any(ord(c) < 32 for c in value):
            raise ValueError("追问必须是单行自然语言")
        return value.strip()


class ChatFollowupOutput(HealthDTO):
    """模型只提供至多两个问题，不携带业务动作。"""

    followups: list[ChatFollowup] = Field(default_factory=list, max_length=2)

    @model_validator(mode="after")
    def distinct_questions(self):
        """重复建议不能占用两个入口。"""
        if len({p.question for p in self.followups}) != len(self.followups):
            raise ValueError("追问不能重复")
        return self


class ChatFollowupResult(ChatFollowupOutput):
    """读取端明确绑定答案，不允许将迟到结果应用到其他消息。"""

    message_id: int = Field(gt=0)
    status: Literal["absent", "pending", "ready", "unavailable"]


def answer_digest(content):
    """建议仅属于生成时的不可变正文。"""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def public_followup_result(message):
    """仅投影已校验字段，过期认领只读地失效，不重新生成。"""
    record = (message.extra_metadata or {}).get(FOLLOWUPS_KEY)
    if not isinstance(record, dict) or record.get("answer_hash") != answer_digest(message.content):
        return ChatFollowupResult(message_id=message.id, status="absent")
    status = record.get("status")
    if status == "pending":
        claimed = record.get("claimed_at")
        status = "pending" if isinstance(claimed, (float, int)) and 0 <= time.time() - claimed < 60 else "unavailable"
    if status not in {"pending", "ready", "unavailable"}:
        status = "unavailable"
    try:
        output = ChatFollowupOutput.model_validate(
            {"followups": record.get("followups", []) if status == "ready" else []}
        )
    except ValueError:
        output, status = ChatFollowupOutput(), "unavailable"
    return ChatFollowupResult(message_id=message.id, status=status, followups=output.followups)

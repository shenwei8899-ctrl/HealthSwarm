"""成员自述记忆的公开输入与持续性边界。"""

import re
from typing import Literal
from uuid import UUID

from pydantic import Field

from yuxi.services.health_vision_types import HealthDTO, HealthVisionError

MemoryKind = Literal["preference", "restriction", "health_self_report"]


class MemoryPatch(HealthDTO):
    """用户显式编辑仍保留自述来源及版本。"""

    client_request_id: UUID
    version: int = Field(ge=1)
    content: str = Field(min_length=1, max_length=500)
    kind: MemoryKind


class MemoryRevoke(HealthDTO):
    """撤回按请求和当前版本幂等执行。"""

    client_request_id: UUID
    version: int = Field(ge=1)


def validate_memory_statement(member, uid, subject, quote, user_content):
    """只接受当前消息中主体明确的持续性自述，不把一次体验升级为限制。"""
    if quote not in user_content:
        raise HealthVisionError("memory_source_invalid", "记忆必须引用本轮用户原文")
    self_subject = subject == "我" and member.owner_uid == uid and member.relationship_label in {"本人", "自己", "我"}
    temporary = any(word in quote for word in ("今天", "这顿", "这一餐", "今晚", "暂时", "这次", "刚才", "以后再说"))
    if temporary:
        raise HealthVisionError("memory_temporary", "本次体验不能写为长期记忆，请关联餐次反馈")
    # 只接收以明确主体及持续性谓语开头的原文，避免“我妈妈”及引述他人。
    statement = quote.strip()
    predicate = r"(?:以后(?:都)?(?:不吃|少吃|要|会|只吃)|一直|长期|从来|习惯|对.+过敏|患有)"
    if not (subject == member.display_name or self_subject) or not re.match(
        rf"^{re.escape(subject)}\s*{predicate}", statement
    ):
        raise HealthVisionError("memory_subject_unclear", "成员归属不明确，请先说明是哪位成员")
